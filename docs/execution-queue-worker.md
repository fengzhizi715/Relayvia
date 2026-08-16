# Relayvia Execution Queue · Scheduler · Worker

Phase 7 在不引入 Redis / Celery / RabbitMQ 的前提下，建立 Relayvia 自己的
**MySQL-backed Execution Queue + Scheduler + 独立 Worker**。它回答的问题是：

> 一个应该执行的 Node，如何可靠地从 Workflow Runtime 到达 Worker。

链路：

```text
Node Ready
   ↓
Scheduler（幂等）
   ↓
ExecutionTask
   ↓
MySQL Queue
   ↓
Safe Claim（FOR UPDATE SKIP LOCKED）
   ↓
Worker（Lease + Token Fencing）
   ↓
NodeExecutor Boundary
   ↓
Result → NodeRun / WorkflowRun
```

## ExecutionTask Model（`execution_tasks`）

`UNIQUE(node_run_id)`：一个 NodeRun 只有一个逻辑 Task，Task 内部维护 `attempt`。

字段：`id / workflow_run_id / node_run_id / task_type / status / payload_json /
priority / attempt / max_attempts / available_at / locked_by / lease_token /
locked_at / lease_expires_at / execution_key / last_error_json / started_at /
finished_at / created_at / updated_at`。

- `payload_json` 只存指针（`workflow_run_id / node_run_id / node_id`），**不复制**
  Graph Snapshot 或 Execution Snapshot。
- `execution_key = "{run_id}:{node_run_id}"`，Retry 期间保持不变；未来 HTTP Service
  Connector 可映射到 `Idempotency-Key`。
- Claim 查询索引：`(status, available_at, priority, created_at)`。
- **索引权衡**：Claim 现在 join `workflow_runs` 过滤 `status='running'`（保证 Paused /
  Waiting / Terminal 的 Run 不可被 Claim）。该过滤会读取 `workflow_runs.status`
  （已有独立索引），因此 `(status, available_at, priority, created_at)` 不再能完全
  覆盖整个查询。V1 规模下可接受；若 Queue 规模增长，应将 Run 的"可 Claim"状态冗余到
  `execution_tasks` 的派生列并纳入索引，而不是放宽对 Run 状态的检查。

## Task State Machine

```text
PENDING → CLAIMED | CANCELLED
CLAIMED → RUNNING | PENDING | CANCELLED
RUNNING → COMPLETED | RETRY_WAIT | FAILED | CANCELLED | PENDING(lease recovery)
RETRY_WAIT → PENDING | FAILED | CANCELLED
```

`COMPLETED / FAILED / CANCELLED` 为 Terminal。所有变更经 `transition_execution_task()`。

## ExecutionBackend 抽象

```python
class ExecutionBackend:
    async def submit / claim / start / complete / fail / schedule_retry / renew_lease / cancel / recover_expired / promote_due_retries
```

Workflow Runtime / Worker 只依赖该接口，不接触 MySQL 细节。V1 提供
`MySQLExecutionBackend`（`backend/app/infrastructure/execution_backend/`）。

## Claim Algorithm（MySQL 8）

```sql
SELECT ... FROM execution_tasks
WHERE status = 'pending' AND available_at <= NOW()
ORDER BY priority DESC, available_at ASC, created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

- 短事务：`SELECT + 条件 UPDATE(status='pending' 守卫) + COMMIT`。
- 条件 UPDATE 用 `WHERE status = 'pending'` 且校验 `rowcount == 1`，保证即使在不支持
  行锁的方言（如测试用 SQLite）下"一个 Task 只有一个 Owner"。
- 之后 Worker 才真正处理任务；长任务执行期间**不持有任何 DB 事务**。

## Worker Lifecycle

启动：`./run-worker.sh`（等价 `python -m app.workers.workflow_worker`）。

```text
start
 → recovery（recover expired + promote due retries + reconcile active runs）
 → claim
 → no task → sleep(poll) → loop
 → process（start → executor → complete/fail/retry → scheduler）
```

- Worker ID：`worker_<hostname>_<pid>_<uuid>`，用于 `locked_by`。
- Poll Interval 默认 0.5s；Recovery Interval 默认 30s。
- SIGINT / SIGTERM：停止领取新任务、安全退出（当前 Task 尽力完成）。

## Lease / Lease Token（Fencing）

- Claim 生成新 `lease_token`（UUID），设置 `lease_expires_at`。
- `start / complete / fail / schedule_retry / renew_lease` 全部校验
  `locked_by + lease_token`；不匹配直接拒绝。
- Lease 默认 60s，每 20s 续约。
- 旧 Worker 在 Lease 过期后用旧 token 写结果 → **被拒绝**（不会覆盖新 Worker）。

## Expired Task Recovery

`recover_expired()`：`status IN (CLAIMED, RUNNING) AND lease_expires_at < NOW()`
→ 回 `PENDING`（清空锁字段）。NodeRun 保持 QUEUED（CLAIMED）或 RUNNING（RUNNING，
重新执行时由幂等 start 处理）。文档明确：接入非幂等外部 Service 后需处理重复副作用风险。

## Retry

- `attempt` 从 0 起；每次进入 RUNNING 时 `attempt += 1`。
- 外部 `max_retries = 2` → 内部 `max_attempts = 3`。
- 失败且 `attempt + 1 < max_attempts`：Task `RUNNING → RETRY_WAIT`（NodeRun
  `RUNNING → RETRYING`），`available_at = now + backoff`。
- 到期后 `promote_due_retries()`：`RETRY_WAIT → PENDING`（NodeRun `RETRYING → QUEUED`）。
- 耗尽：Task `FAILED`，NodeRun `FAILED`，WorkflowRun 由 Scheduler derive 为 `FAILED`。

## Scheduler

`WorkflowScheduler`（`backend/app/runtime/scheduler/`）：

- `schedule_ready_nodes(run_id)`：只对 **RUNNING** run 的 Ready（PENDING 且所有上游
  COMPLETED）节点创建 Task 并把 NodeRun `PENDING → QUEUED`。
- **幂等**：`UNIQUE(node_run_id)` + 存在性预检；多次调用只产生 1 Task/NodeRun。
- `reconcile_run(run_id)`：修复漏调度、对已取消 run 取消残留工作、并用
  `derive_workflow_state()` 推导/持久化 WorkflowRun 状态（任一 FAILED → FAILED；
  全部 Terminal → COMPLETED；否则 RUNNING）。
- `PAUSED / WAITING / CANCELLED / COMPLETED / FAILED` 的 run 不调度新 Task。

触发点：Start Run、Node 完成后、Worker 周期性 Recovery。

## Recovery / Reconciliation

Worker 启动与每 `WORKER_RECOVERY_INTERVAL` 执行：

```python
run_execution_recovery(
    recover_expired(), promote_due_retries(),
    reconcile active (RUNNING/PAUSED) runs,
)
```

覆盖：Worker 崩溃（Lease 过期）、到期 Retry、Node 已完成但调度丢失（对账补 Task）。

## Delivery Semantics

**Relayvia V1 提供 durable at-least-once task execution。不承诺 exactly-once。**
外部执行成功但 Worker 在写 COMPLETED 前崩溃 → Lease 过期 → Task 重新执行 →
外部副作用可能重复。`execution_key` 供未来 Connector 实现幂等。

## NodeExecutor Boundary

`NodeExecutor.execute(context) → NodeExecutionResult`。`NodeExecutionContext` 包含
node 定义快照、已解析 config/input、execution snapshot、attempt，**不暴露 DB Session**。

默认 `DefaultNodeExecutor` 当前支持：

### HTTP Agent 调用契约

按 Snapshot 中的 `http_method` / `headers` / `timeout` 调用 endpoint，请求体为：

```json
{
  "input": { "…": "resolved input_mapping 结果" },
  "context": { "workflow_run_id": "…", "node_id": "…", "attempt": 1 }
}
```

- 响应必须是 JSON object（或会被包装为 `{"result": …}`）；按 Agent `output_schema`
  校验，通过后写入 `NodeRun.output_json`。
- 这是对外 Agent 的稳定调用契约，接入任何 HTTP Agent 都以此为准。

### HTTP Service Action 调用契约

`input_mapping` 可显式映射为 `{path, query, body}`；path 中的 `{param}` 安全 URL
encode（缺参报 `MISSING_PATH_PARAMETER`），Action 静态 headers 与 Service Credential
由 Connector 使用。若 mapping 不含 `path/query/body` 键，整体作为 body（向后兼容）。

### Condition 与 Data / Logic 节点

- **Condition**：计算表达式，产出 `{"selected_branch": "true|false", "matched": bool}`。
  该输出仅供 Scheduler 分支使用（Validation 禁止用户直接引用 Logic 节点输出）。
- **Data Transform / Output**：对 `mappings` / `output_mapping` 求值（引用已被
  ContextResolver 解析）后写入 output。
- **Parallel / Merge**：当前为**透传**（`output = resolved_input`），只推进状态，**尚未
  实现分支 fan-out / 结果合并语义**。跨分支数据依赖由 Validation 保证不会出现，因此
  不会读到未产生的结果。

### 安全与未实现

Credential 只在 Worker 内按 `credential_id` 临时解密，绝不进入 Snapshot、Output、Task
Payload 或 Error。Human、Wait、Router、Tool 与 Local/Custom Agent 仍返回明确的
`UNSUPPORTED_NODE_EXECUTION`，不会伪装为已执行。HTTP 响应体限制为 1MB
（`MAX_RESPONSE_BYTES`），超限报 `RESPONSE_TOO_LARGE`（非 retryable）。

## Branch and Run Gating

- Condition 完成后，Scheduler 只激活 `selected_branch` 对应的 Edge；未选中分支及其
  无活跃入边的后代递归标记为 `SKIPPED`。汇合节点只等待仍活跃的入边。
- **Pause 是协作式的**：已在执行中的外部调用允许完成，但 Task 的 claim / start 都要求
  父 Run 为 `RUNNING`；已 claim 但尚未 start 的 Task 会回到 `PENDING`，Resume 后继续。
- **Failure 是 fail-fast**：一个 Node 耗尽重试进入 FAILED 后，Scheduler 将同一 Run
  其他非终态 Task / NodeRun 取消。无法强制中断已经发出的外部 HTTP 请求，但其迟到结果
  会被已取消 Task 的 fencing 拒绝。

## Worker 与 Relayvia Runner 的区别

- **Workflow Worker**：Relayvia Server 侧的执行基础设施进程。
- **Relayvia Runner**：用户笔记本 / Mac mini / 内网 / Edge 的本地执行组件。
- Phase 7 不实现 Runner。

## 当前边界

尚未实现：Shell/Git Tool、Codex/Cursor/OpenCode Adapter、Local/Custom Agent、
Human Approval Runtime、Wait Timer、Router、SSE Run Event 与 Artifact Runtime。

## 配置

```text
RELAYVIA_WORKER_ID
RELAYVIA_WORKER_POLL_INTERVAL   (默认 0.5)
RELAYVIA_WORKER_LEASE_SECONDS   (默认 60)
RELAYVIA_WORKER_LEASE_RENEW_INTERVAL (默认 20)
RELAYVIA_WORKER_RECOVERY_INTERVAL   (默认 30)
```
