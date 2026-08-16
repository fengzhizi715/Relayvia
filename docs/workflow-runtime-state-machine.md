# Relayvia Workflow Runtime · State Machine & Run Model

Phase 6 建立 Workflow Runtime 的**持久化执行模型与状态机**。它回答的是
"一次 Workflow 执行在 Relayvia 中如何被可靠地表示"，而不是"Node 怎么执行"。
本阶段没有 Executor、没有 Execution Queue、没有 Worker。

## 核心模型关系

```text
Workflow         用户长期维护的可编辑 Definition（Draft）
  ↓
Workflow Version 不可变 Definition Snapshot（Phase 5 保证 Valid）
  ↓
Workflow Run     某一次具体执行实例
  ↓
Node Runs        该 Run 中每个 Graph Node 的执行实例
```

- Run 必须绑定不可变 `workflow_version_id`，禁止直接运行 Draft。
- 不设 `workflow_runs.current_node_id` 游标：Relayvia 支持 Parallel / Condition /
  Merge，真实进度由 **NodeRuns 状态 + Graph** 表达。

## WorkflowRun 模型（`workflow_runs`）

| 字段 | 说明 |
| --- | --- |
| `id` | UUID |
| `workflow_id` / `workflow_version_id` | 绑定不可变 Version |
| `version_number` | Version 序号（便于展示） |
| `status` | 见状态机 |
| `graph_schema_version` / `graph_snapshot_json` | 执行时 Definition Snapshot |
| `execution_snapshot_json` | Registry 非 Secret 配置快照 |
| `input_json` / `variables_json` | Workflow 输入与变量 |
| `error_json` / `waiting_reason` / `waiting_metadata_json` | 结构化错误 / 等待 |
| `started_at` / `finished_at` / `paused_at` / `cancelled_at` | 状态时间戳 |

## NodeRun 模型（`node_runs`）

- `UNIQUE(workflow_run_id, node_id)`：一个 Run 中每个 Definition Node 恰好一个 NodeRun。
- `node_id` = Graph `WorkflowNode.id`（不是独立 DB Entity）。
- `attempt` 表示第几次执行（初始 0；第一次执行 1；Retry 递增）。Retry 不创建第二个
  NodeRun；未来如需每次 Attempt 的独立 Trace，再引入 `NodeExecutionAttempt`。
- Node Output 主存储于 `node_runs.output_json`。

## Workflow Run State Machine

```text
          ┌──────── WAITING ◄────────────────────────┐
          │                                         │
CREATED → RUNNING ───────────┐                      │
          │   │              │                      │
          │   └→ PAUSED ─────┴──────────────────────┘
          │   ├→ COMPLETED
          │   ├→ FAILED
          │   └→ CANCELLED
```

完整迁移表见 `backend/app/runtime/state_machine/__init__.py`。要点：

- `COMPLETED / FAILED / CANCELLED` 为 Terminal，禁止迁出（`INVALID_WORKFLOW_RUN_TRANSITION`，409）。
- 首次 `CREATED → RUNNING` 设置 `started_at`；进入 Terminal 设置 `finished_at`；
  `→ PAUSED` 设置 `paused_at`。
- 所有状态变更必须经 `transition_workflow_run()`，禁止业务代码直接赋值 `run.status`。

## Node Run State Machine

```text
PENDING → QUEUED → RUNNING → {COMPLETED, FAILED, WAITING, RETRYING, CANCELLED}
PENDING → SKIPPED
PENDING → CANCELLED
WAITING → RUNNING
RETRYING → QUEUED
```

`COMPLETED / FAILED / SKIPPED / CANCELLED` 为 Terminal。
`QUEUED / RETRYING` 本阶段只定义状态与迁移，Phase 7 Queue 才真正使用。

## Run Creation

```text
Workflow
  ↓ 选择 Version（workflow_version_id / version / current_version）
  ↓ Version 必须存在（否则 WORKFLOW_HAS_NO_VERSION）
  ↓ 解析 Graph
  ↓ Registry 批加载 → Run Readiness（复用 Phase 5 references 规则）
  ↓ 生成 Graph Snapshot + Execution Snapshot
  ↓ 校验 Run Input（Data Input Schema）
  ↓ 初始化 Variables（Definition Defaults）
  ↓ 创建 WorkflowRun(CREATED)
  ↓ 为每个 Graph Node 创建 NodeRun；Data Input Node → COMPLETED（output = input）
```

## Snapshot Strategy

- **Graph Snapshot**：`graph_snapshot_json`，创建时深拷贝 Version Graph，Draft/Registry
  后续变更不影响历史 Run。
- **Execution Snapshot**：`execution_snapshot_json`（当前 `schema_version: "2"`），保存
  agent / service / service_action 的**非 Secret 调用配置**（endpoint、timeout、
  schema、method/path、retry_policy 等），按 id 去重。
- **Credential**：只保存 `credential_id`。绝不读取/解密/持久化 Secret。
  因此"Runtime Definition 可追踪"不等于"Secret 完全可重放"。

## Runtime Context（Source of Truth）

- `workflow_runs.input_json` = Workflow Input（主存储）。
- `workflow_runs.variables_json` = 变量（Definition Default 初始化）。
- **Node Output 主存储于 `node_runs.output_json`**，不在 context 中重复复制
  （避免双重 Source of Truth）。
- `ContextResolver`（`backend/app/runtime/context/`）解析：
  `workflow.input.*`、`workflow.variables.*`、`nodes.<id>.output.*`、`run.*`。
  缺失值抛 `UNRESOLVED_CONTEXT_REFERENCE`，绝不静默返回 null。无 eval / 模板引擎。

## Pause / Resume / Cancel

- **Pause**：`RUNNING|WAITING → PAUSED`。已执行中的外部调用采用协作式暂停、允许完成；
  尚未 start 的 Task 不会执行，保留到 Resume。
- **Resume**：`PAUSED → RUNNING`，恢复保留 Task 并重新调度已 Ready 的 Node。
- **Cancel**：非 Terminal → `CANCELLED`（terminal 再 cancel 返回 `RUN_ALREADY_TERMINAL`）；
  所有未完成 NodeRun → `CANCELLED`（已完成的历史 NodeRun 保持 `COMPLETED`）。

## Phase 6 vs Phase 7 边界

Phase 6 只建立 Runtime 状态世界。以下**不属于**本阶段：
Execution Queue / Worker / Task Claim、Agent/Service/Tool 真正执行、HTTP Connector
执行、Retry Scheduler、Parallel/Merge Scheduler、Condition 求值、Human Approval
Runtime、Wait Timer、SSE Run Event、Runner、Artifact Runtime。
