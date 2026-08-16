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
node 定义快照、已解析 input、execution snapshot、attempt，**不暴露 DB Session**。
Phase 7 默认 `PlaceholderNodeExecutor`（返回 UNSUPPORTED）；FakeExecutor 仅存在于
测试。Phase 8 接入 ExecutionUnit + Connector。

## Worker 与 Relayvia Runner 的区别

- **Workflow Worker**：Relayvia Server 侧的执行基础设施进程。
- **Relayvia Runner**：用户笔记本 / Mac mini / 内网 / Edge 的本地执行组件。
- Phase 7 不实现 Runner。

## Phase 7 vs Phase 8 边界

Phase 7 只做执行基础设施。以下属于 Phase 8+：HTTP Agent/Service Connector 执行、
Shell/Git Tool、Codex/Cursor/OpenCode Adapter、完整 Condition/Parallel/Merge、
Human Approval Runtime、Wait Timer、SSE Run Event、Artifact Runtime。

## 配置

```text
RELAYVIA_WORKER_ID
RELAYVIA_WORKER_POLL_INTERVAL   (默认 0.5)
RELAYVIA_WORKER_LEASE_SECONDS   (默认 60)
RELAYVIA_WORKER_LEASE_RENEW_INTERVAL (默认 20)
RELAYVIA_WORKER_RECOVERY_INTERVAL   (默认 30)
```
