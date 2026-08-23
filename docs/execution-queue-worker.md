# Relayvia Execution Queue · Scheduler · Worker

Relayvia 在不引入 Redis / Celery / RabbitMQ 的前提下，使用自己的
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
 → 以有上限的并发槽位 process（start → executor → complete/fail/retry → scheduler）
```

- Worker ID：`worker_<hostname>_<pid>_<uuid>`，用于 `locked_by`。
- Poll Interval 默认 0.5s；Recovery Interval 默认 30s；每个 Worker 默认最多并发
  4 个 Task（`RELAYVIA_WORKER_CONCURRENCY`，代码上限 64）。
- SIGINT / SIGTERM：停止领取新任务，已领取 Task 继续写回结果后退出。

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
- Graph Node 显式 `retry.max_retries = 2` → 内部 `max_attempts = 3`。没有显式
  retry 的 Agent、Tool 与内建逻辑节点默认只执行一次；Service Node 则继承其
  Service Action 的 `retry_policy`。
- `max_attempts` 与 `retry_backoff_seconds` 在 Task 入队时写入 payload；Worker
  不再用全局默认值覆盖某个历史 Run 的策略。
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

## Context / Variable Mapping

`ContextResolver`（`backend/app/runtime/context/`）在 Worker 执行前解析 Node 的
`input_mapping` 与 `config`。Connector 只接收已经解析好的参数，**绝不解析
`{{...}}`、绝不访问 WorkflowRun/NodeRun 状态**。

支持引用：

```text
{{workflow.input.<path>}}      # WorkflowRun.input_json
{{workflow.variables.<path>}}  # WorkflowRun.variables_json
{{nodes.<id>.output.<path>}}   # 当前 Run 对应 NodeRun.output_json
{{run.<path>}}                 # Run 元数据
```

- 纯引用（整串只有一个 Reference）**保留原始类型**（string/number/boolean/object/array/null）；
  模板字符串插值结果为 string；dict / list 递归解析。
- 缺失值抛 `UNRESOLVED_CONTEXT_REFERENCE`，Worker 直接产生结构化失败，**不调用 Connector**。
- 静态可见的错误（如 `{{nodes.not_exist.output.x}}`）由 Graph Validation 在 Version 阶段拒绝；
  运行时缺失（字段不存在、上游未产出）由 Resolver 兜底——两层机制。
- **NodeRun.input_json** 持久化真正传给 Execution Unit 的解析结果（Trace 用）；
  Credential 不在其中（`credential_id` 引用单独由 Connector 注入，且不进入 Trace）。

## NodeExecutor Boundary

`NodeExecutor.execute(context) → NodeExecutionResult`。`NodeExecutionContext` 包含
node 定义快照、已解析 config/input、execution snapshot、attempt，**不暴露 DB Session**。

### 统一 Connector Contract

`app.connectors.base` 定义统一契约：`Connector.execute(request) → ExecutionResult`。

```python
ExecutionResult: status(success|failed), output, artifacts, metadata, retryable, error
```

- **Agent / Service**：`HTTPAgentConnector` / `HTTPServiceConnector` 接收
  `HTTPInvocationConfig`（url / method / headers / body / query / timeout /
  credential / retry_on_status），返回 `ExecutionResult`。
- **Tool**：`ToolInvocationConfig` 是 Runner dispatch 的契约。Tool Node 必须指定目标
  `runner_id`，由具备 `shell` capability 的该 Runner 执行；Workflow Worker 不会创建
  shell 子进程，也不会继承 Server 环境变量执行用户命令。
- Connector 只调用外部能力并报告结果；**不修改 WorkflowRun / NodeRun 状态、不调度
  下一个 Node、不决定 Retry**。这些全部由 Runtime 负责。

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

- **Condition**：计算表达式（支持 `== != > >= < <= contains not_contains is_empty is_not_empty`，
  以及递归 `{"and": [...]}` / `{"or": [...]}` 组合），产出
  `{"selected_branch": "true|false", "matched": bool}`。该输出仅供 Scheduler 分支使用
  （Validation 禁止用户直接引用 Logic 节点输出）。
- **Parallel**：完成后同时激活多个后继 Node（可被不同 Worker 并行 Claim），不等待、不聚合。
- **Merge（ALL）**：等待**当前 Run 中实际激活**的所有上游分支完成后才 Ready——未选中的
  Condition 分支（SKIPPED）不阻塞 Merge。
- **Data Transform / Output**：对 `mappings` / `output_mapping` 求值（引用已被
  ContextResolver 解析）后写入 output。

### Tool 节点

`tool`（Shell / Git / Test Command）：Graph Contract 已保留，但必须通过未来的
Relayvia Runner 执行。当前 Server Worker 会返回 `RUNNER_REQUIRED`，不会在服务端
执行命令。

### 安全与未实现

Credential 只在 Worker 内按 `credential_id` 临时解密，绝不进入 Snapshot、Task Payload 或
Error。Connector / Runner 的 **Output、metadata、error 和 Artifact metadata** 都会经过
密钥字段、常见内嵌 secret 格式与当前 Credential 值的脱敏后才持久化到 NodeRun Trace。Router、
Local/Custom/OpenCode/Cursor Agent 没有 Execution Unit 时，Version Validation 会明确拒绝发布，
不会伪装为可运行。HTTP 响应体限制为 1MB
（`MAX_RESPONSE_BYTES`），超限报 `RESPONSE_TOO_LARGE`（非 retryable）。

## Branch and Run Gating

- Condition 完成后，Scheduler 只激活 `selected_branch` 对应的 Edge；未选中分支及其
  无活跃入边的后代递归标记为 `SKIPPED`。汇合节点只等待仍活跃的入边。
- **Pause 是协作式的**：暂停不会主动终止已经开始的外部调用；它只冻结新 claim/start，
  已 claim 未 start 的 Task 会回到 `PENDING`，Resume 后继续。
- **Cancel / Failure 是 fail-fast**：一个 Node 耗尽重试进入 FAILED 后，Scheduler 将同一
  Run 其他非终态 Task / NodeRun 取消。已执行本地命令的 Runner 通过
  `POST /api/runners/{id}/tasks/{task_id}/heartbeat` 收到 durable cancel signal 并终止其
  进程组；迟到结果受 lease / 状态 fencing 拒绝。已发出的第三方 HTTP 请求仍无法被平台
  强制撤销，但其结果同样不会写回。

## Human Approval / Human Input / Wait

等待型节点（`human/approval`、`human/input`、`logic/wait`）由 Worker 置为**持久化
WAITING**，然后**完成并释放 ExecutionTask**——Worker 不因等待而阻塞/占线程。

- `NodeRun.waiting_reason`：`HUMAN_APPROVAL` / `HUMAN_INPUT` / `WAIT_TIMER`；
  `waiting_metadata_json`：Wait 记录 `resume_at`（`now + duration`）。
- 任一 NodeRun 处于 WAITING → `WorkflowRun → WAITING`（`derive_workflow_state`）。
- **恢复驱动**：
  - `POST /api/node-runs/{id}/approve` / `/reject`：`WAITING → COMPLETED`（approve，
    output `{"approved": true}`）或 `WAITING → FAILED`（reject，error `REJECTED`，
    WorkflowRun → FAILED）。随后 Scheduler reconcile 调度下游。
  - `POST /api/node-runs/{id}/submit`：`human/input`，`WAITING → COMPLETED`，
    `output_json = 提交内容`（下游可经 Context Resolver 引用）。
  - Wait 到期：Scheduler `promote_due_waits()` 周期检查 `resume_at <= now` →
    node `WAITING → COMPLETED` → 继续。V1 只实现 `mode=duration`。
- **幂等与并发**：approve/reject/submit 以 `FOR UPDATE` 行锁 + `WAITING` 状态条件更新；
  非 WAITING 的再次操作返回 `409 NODE_RUN_NOT_WAITING`。Wait 到期由 reconcile 幂等推进。
- **Durability**：WAITING 是持久化 DB 状态；Worker / Backend 重启后状态不丢，恢复后继续。

## Artifacts

非 JSON / 大型文件类产物（image / dataset / model / patch / report ...）通过
`artifact://<id>` 引用传递，不进入 NodeRun.output_json 正文。

- **Artifact Entity**（`artifacts` 表）只存 metadata（id / workflow_run_id /
  producer_node_run_id / type / name / uri / size / content_type / metadata）；
  文件内容在 `ArtifactStorage`。
- **LocalArtifactStorage**：文件存于 `data/artifacts/<id>`（`RELAYVIA_ARTIFACT_STORAGE_DIR`
  可配置），key 严格校验（`[A-Za-z0-9_-]+` + root 限制），**防止 Path Traversal**。它只
  适用于 API 与 Worker 共享同一持久化文件系统的单机/共享卷部署。
- **S3ArtifactStorage**：设置 `RELAYVIA_ARTIFACT_STORAGE_BACKEND=s3` 与
  `RELAYVIA_ARTIFACT_S3_BUCKET` 后，API 与 Worker 通过 S3 / MinIO 兼容对象存储读写同一
  object key；认证使用 boto3 标准 provider chain，不把对象存储密钥放入 Credential Registry。
- **产生**：`ExecutionResult.artifacts` 是 Artifact Candidate——
  `{name, type, content_type, content | uri, output_key, metadata}`。
  Server Worker 只接收受大小限制的内存 `content` 或 HTTP(S) 外部 URI，**绝不读取
  Connector 提供的 `local_path`**；本地工作区文件必须由未来 Relayvia Runner 通过受控
  上传契约提交。Worker 在 success 时注册 Artifact → `artifact://<id>`；
  按 `output_key` 写入 NodeRun.output（下游可 `{{nodes.X.output.<key>}}` 引用），
  引用列表存 `node_runs.artifact_refs_json`。Connector 不直接操作 Artifact 状态。
- **外部 URI**（如 HTTP 返回 `artifact_url`）：注册为 external Artifact（无本地文件，
  引用保留原始 URI）。
- **消费**：Context Resolver 只透传 `artifact://` 引用（不读文件）；下游 ExecutionUnit
  通过 Artifact Service 获取 metadata / open 内容。
- **API**：`GET /api/artifacts/{id}`（metadata）、`GET /api/artifacts/{id}/content`
  （下载；external 或无文件 → 404）。
- **Durability**：Artifact metadata + 文件都持久化；Worker 重启后仍可访问。

## Run Trace & SSE

Workflow 执行过程以结构化 `RunEvent` 持久化（`run_events` 表，自增 id 提供稳定总序），
与状态修改同事务写入。普通应用日志是开发/运维用途，RunEvent 才是执行 Trace。

- **事件类型**：`WORKFLOW_STARTED/WAITING/RESUMED/COMPLETED/FAILED/CANCELLED`、
  `NODE_QUEUED/STARTED/RETRYING/WAITING/RESUMED/COMPLETED/FAILED/SKIPPED/CANCELLED`、
  `CONDITION_EVALUATED`（经 `NODE_COMPLETED.payload.selected_branch` 表达）。
- **写入点**：backend（start/complete/fail/retry/wait/cancel）、scheduler（queued/skipped/
  workflow 状态）、service（start/approve/reject/submit/cancel）——全部与状态变更同一事务。
- **Trace API**：`GET /api/workflow-runs/{id}/events?after_id=&limit=`（增量分页）。
- **SSE**：`GET /api/workflow-runs/{id}/events/stream` —— 轮询数据库（无 Redis），
  推送命名事件与 `id:`/`data:` 帧；客户端断线后使用 `Last-Event-ID`（或显式
  `after_id`）续传未消费事件；
  Run 进入终态后流自然结束。数据库始终是 durable Source of Truth。
- **安全**：事件 payload 由 Runtime 构造（不含 NodeRun output 正文），Credential /
  Secret 不进入 Trace / SSE（复用统一脱敏边界）。
- **前端**：Run Detail 以 fetch 流消费 SSE，因此会携带 Control Plane Authorization 并使用
  `VITE_API_BASE_URL`；不会将访问令牌置于 SSE URL 中。

## Relayvia Runner

Tool 节点（shell / git / test_command）不再由 Server Worker 或 FastAPI 执行，而是由
**独立 Runner 进程**（`python -m app.runners.runner` / `./run-runner.sh`）拉取并执行。

- **边界**：Runner 只接收任务、执行本地命令、返回 `ExecutionResult`；不解析 Workflow
  Graph、不调度 Node、不修改 Workflow 状态（状态由 Backend Runtime 负责）。
- **Registry / 心跳**：首次 `POST /api/runners/register` 会一次性返回 enrollment token；
  Runner 将其以 `0600` 本地 identity 文件保存。重启后携带 `runner_id` + token
  重新注册；`heartbeat` / `claim` / `submit-result` 均必须带
  `X-Relayvia-Runner-Token`。数据库仅保存 token 的 SHA-256 hash。心跳更新
  `last_seen_at` 并续约该 Runner 名下 RUNNING 任务的 Lease。OFFLINE 由
  `last_seen_at` 超过 `RELAYVIA_RUNNER_OFFLINE_SECONDS`（默认 60s）判定。
- **拉取执行**：`POST /api/runners/{id}/claim`（Backend 选 capability 匹配、未指定其他
  Runner 的任务，claim 即 RUNNING）、执行、`POST /api/runners/{id}/submit-result`
  （Backend 注册 Artifact、更新 NodeRun、reconcile 调度下游）。
- **Capability 与定向**：`execution_tasks.required_capability`（Tool → `shell`）和
  `runner_id` 同时参与 claim。Tool Node 必须显式指定 `config.runner_id`；Codex Agent
  使用 Registry 的 `agent.runner_id`。创建 Run 时先检查目标 Runner 在线且拥有所需
  Capability，避免本地路径被另一台机器领取。
- **Task 解析**：Backend 在调度时已用 ContextResolver 把 Tool config（command / cwd /
  timeout）解析进 task payload，Runner 不需要 Graph / Context。
- **安全**：`RELAYVIA_RUNNER_ROOT` 是必填项；所有命令在其下运行，working directory
  路径逃逸会被拒绝。Runner 不接收 Backend Credential（Secret 不外发）。每个命令使用
  独立进程组，超时时会终止整组子进程；stdout/stderr 截断并对常见 secret 形式脱敏。
  Artifact 通过 base64 `content` 回传，Backend 注册（复用 Artifact Service）。
- **Runner Lost / Retry**：任务 RUNNING 后 Runner 掉线 → Lease 过期 →
  `recover_expired` 回 PENDING → 可被同一目标 Runner 重领（at-least-once）。所有
  submit 都严格检查 lease expiry；retryable 失败按 Task 的 max attempts / backoff
  进入 `RETRY_WAIT`，与 Server Worker 使用同一状态语义。

## Workspace Manager

Coding 场景的隔离工作目录：Tool 节点可声明 `workspace`（repository + strategy），
由 Runner 在本地准备，并行 Node 不再共享同一工作树。

- **Workspace Entity**（`workspaces` 表）：name / runner_id / repository / path /
  branch / base_branch / workspace_type(local_repository|git_worktree) / status
  (creating|ready|in_use|failed|released) / workflow_run_id / node_run_id。
- **Contract**：`ToolNodeConfig.workspace = {repository, strategy, base_branch}`。
- **创建**：Scheduler 在调度 Tool/Coding Agent 节点时创建 Workspace 记录（CREATING），把
  workspace 配置放入 task payload；实际 git 操作由 Runner 执行（Backend 不碰 Runner
  文件系统）。
- **Branch**：`relayvia/<run_id[:12]>/<node_id>`（每 Run/Node 唯一，互不冲突）。
- **Runner 准备**：`git worktree add -b <branch> <root>/worktrees/<branch>`（branch
  已存在则 attach）；`local` 策略复用主仓库。Repository 必须位于
  `RELAYVIA_RUNNER_ROOT` 内且是合法 Git 仓库（路径逃逸拒绝）。
- **隔离**：并行分支各自 worktree（不同 branch/path），主仓库不被直接修改。
- **Diff / Patch**：命令执行后 Runner 自动生成 `git diff HEAD`（含 untracked，
  intent-to-add）patch 作为 Artifact（`patch.diff`，`output_key=patch`）回传注册。
- **回写**：Runner claim 时写入 `runner_id` 并标为 IN_USE；submit-result 时 Backend
  更新 path/branch/status（成功→released，失败→failed）。手动 release 只能处理非活动
  Workspace；清理策略：Run 完成后保留 worktree 供 Trace/调试，不自动删除。
- **API**：`GET /api/workspaces`、`GET /api/workspaces/{id}`、
  `POST /api/workspaces/{id}/release`。

## Coding Agent Adapter

Coding Agent（Codex / OpenCode / Cursor）作为 **Agent Connector** 通过 Runner +
Workspace 执行；不是新的 Workflow Node Type（Runtime 只认识 `agent` 节点 +
Registry 的 `connector_type`）。

- **Adapter**：`connectors/agents/coding.py` —— `CodingAgentConnector`（标记基类）+
  `CodexConnector`（`build_command`：`<executable> exec --json <task>`，CLI 行为留在
  Adapter）+ `detect_coding_agent_capabilities()`（`shutil.which`，只上报真实安装的
  CLI）。OpenCode / Cursor 类型已保留在 Registry 枚举，Adapter 接口就绪但 V1 未
  production 实现（如实记录）。
- **调度**：Scheduler 对 `connector_type=codex` 的 Agent 节点用 ContextResolver 解析
  `task_template`，构造 Codex 命令（`executable` 取 Registry/默认 `codex`）放入 task
  payload，`required_capability="codex"` 与 Registry `runner_id`，并按其 `workspace`
  配置创建同一 Runner 绑定的 Workspace。
- **执行**：Runner 检测 codex 并上报 `codex` capability；claim 匹配的 coding-agent
  任务，在 Workspace（worktree）内执行命令，自动生成 `git diff` patch Artifact，
  返回 `ExecutionResult`（summary/exit_code/patch）。Backend 注册 patch、更新
  Workspace/NodeRun、reconcile 下游。
- **边界**：Coding Agent Adapter 不解析 `{{}}`（Context 在 Backend 解析）、不修改
  Workflow 状态、不调度、不决定 Retry；超时/失败沿用 Runner 通用机制（进程终止 →
  Failed → Runtime Retry）。
- **安全**：Coding Agent 运行在 Runner Root / Workspace 内；不接收 Backend
  Credential；Secret 不进入 Trace/Artifact。

## Worker 与 Relayvia Runner 的区别

- **Workflow Worker**：Relayvia Server 侧的执行基础设施进程。
- **Relayvia Runner**：用户笔记本 / Mac mini / 内网 / Edge 的本地执行组件。
- Runner 与 Worker 都使用有上限的并发槽位。Runner 默认 2 个
  （`RELAYVIA_RUNNER_CONCURRENCY`，代码上限 32）；共享本地仓库必须保持 1，
  并发 Coding 任务应使用 `worktree` Workspace 隔离。

## 当前边界

已实现：Relayvia Runner dispatch、Codex Adapter、Tool / Codex Worktree 执行，以及 S3/MinIO
兼容 Artifact Storage。尚未实现：OpenCode/Cursor Adapter、Local/Custom Agent 执行、Router
Runtime。上述无执行器能力会在 Version Validation 阶段被拒绝。Human Approval / Human Input、
Wait Timer、Run Trace + SSE 与 Local Artifact Storage 已实现。

## 配置

```text
RELAYVIA_WORKER_ID
RELAYVIA_WORKER_POLL_INTERVAL   (默认 0.5)
RELAYVIA_WORKER_CONCURRENCY     (默认 4，代码上限 64)
RELAYVIA_WORKER_LEASE_SECONDS   (默认 60)
RELAYVIA_WORKER_LEASE_RENEW_INTERVAL (默认 20)
RELAYVIA_WORKER_RECOVERY_INTERVAL   (默认 30)
RELAYVIA_ARTIFACT_STORAGE_DIR        (默认 data/artifacts)
RELAYVIA_ARTIFACT_MAX_BYTES          (默认 104857600)
RELAYVIA_ARTIFACT_STORAGE_BACKEND    (local|s3，默认 local)
RELAYVIA_ARTIFACT_S3_BUCKET          (s3 后端必填)
RELAYVIA_ARTIFACT_S3_PREFIX          (默认 relayvia/artifacts)
RELAYVIA_ARTIFACT_S3_REGION          (可选)
RELAYVIA_ARTIFACT_S3_ENDPOINT_URL    (MinIO/S3 兼容端点可选)
RELAYVIA_RUNNER_ROOT                 (Runner 必填；本地仓库与 worktree 的上级目录)
RELAYVIA_RUNNER_ID_FILE              (默认 ~/.relayvia/runner.json，权限 0600)
RELAYVIA_RUNNER_CONCURRENCY          (默认 2，代码上限 32)
RELAYVIA_RUNNER_SANDBOX_COMMAND      (生产环境必填的 sandbox wrapper 可执行文件)
RELAYVIA_RUNNER_ALLOW_UNSANDBOXED_EXECUTION (仅可信本地开发；默认 false)
```

## P0 Security Boundary

- **Control Plane**：除 `/api/health` 与 Runner 数据面接口外，所有 API 都要求
  `Authorization: Bearer <RELAYVIA_CONTROL_PLANE_TOKEN>`（也可使用
  `X-Relayvia-Control-Plane-Token`）。令牌未配置时 fail closed。
- **Runner enrollment**：首次 `POST /api/runners/register` 必须携带
  `X-Relayvia-Runner-Enrollment-Token`，或使用有效的 Control Plane Token。之后的
  heartbeat / claim / task heartbeat / submit 使用 Runner 自己的一次性 enrollment token。
- **Shell isolation**：Runner Root 不是 Linux/macOS 沙箱。Runner 默认要求外部 Sandbox
  Wrapper；只有显式设置 `RELAYVIA_RUNNER_ALLOW_UNSANDBOXED_EXECUTION=true` 才会在可信
  开发机以 `/bin/sh -lc` 执行命令。
- **URL policy**：默认拒绝解析到私网、loopback、link-local、reserved 地址的 HTTP URL；
  Local/Edge 部署可显式启用 `RELAYVIA_ALLOW_PRIVATE_NETWORK_URLS=true`。
