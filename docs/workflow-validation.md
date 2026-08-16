# Relayvia Workflow Validation

本文件描述 Phase 5 的 Workflow Graph Validation Engine。它是 Relayvia 对
“一个工程上合法的 Workflow” 的定义，**后端是唯一权威**。前端（Phase 4 Builder）
只做即时 UX 校验；是否可执行由本 Engine 决定。

核心产品模型：

```text
Draft    可以 Contract 合法但不完整（可保存）
Version  必须通过 Full Validation（不可变、可执行候选）
```

## Validation Pipeline

Validation Engine 位于 `backend/app/runtime/validation/`，入口：

```python
result = validate_graph(graph, context)   # -> ValidationResult
```

`ValidationContext` 携带 Registry 快照（agent / service / service action），
Engine 不查询数据库、不依赖 FastAPI、不执行任何外部请求。

Pipeline 分为六个 pass，按固定顺序执行并稳定排序输出：

| Pass | 规则 | 职责 |
| ---- | ---- | ---- |
| 1 | `identity` | 重复 Node/Edge ID、Edge 指向不存在节点、Self Connection、重复 Connection |
| 2 | `topology` | Entry/Output、Input/Output 边约束、Cycle、Reachability、Dead-end、Parallel/Merge 结构与配对 |
| 3 | `references` | Agent / Service / Service Action 存在性、禁用、健康、Action 归属 |
| 4 | `nodes` | 各类型 Node 配置与 Condition true/false 分支 |
| 5 | `context` | Context Reference 语法、未知 Node/Variable/Input、自引用、前向引用、祖先依赖、Parallel 同级依赖、Output 字段 |
| 6 | `schema` | Input Mapping 必填、额外字段、基础类型兼容（Literal / Reference / Template） |

## Error vs Warning

- **ERROR**：Workflow 不允许进入执行（不可创建 Version）。
- **WARNING**：可以执行，但存在潜在问题（不阻止 Version 创建）。

示例：Agent `enabled=false` 是 ERROR；Agent `status=unhealthy` 是 WARNING
（Health 属于 Runtime Readiness，不是 Definition Correctness）。

## API

```text
POST /api/workflows/{id}/validate
```

- 空 body → 验证当前持久化 Draft。
- `{"graph": {...}}` → 验证传入（可能未保存）的 Graph，不要求先保存。
- 返回 `ValidationResult`：`{ "valid", "errors": [Issue], "warnings": [Issue] }`。

`POST /api/workflows/{id}/versions` 创建 Version 前强制执行 Full Validation：
存在 ERROR 时返回 `422 VALIDATION_FAILED`（`details.errors` 携带完整 Issue 列表），
不创建 Version；WARNING 允许创建。

## ValidationIssue 结构

```json
{
  "code": "SERVICE_ACTION_MISMATCH",
  "severity": "error",
  "message": "Service action does not belong to the referenced service",
  "node_id": "import-dataset",
  "edge_id": null,
  "field": "config.service_action_id",
  "details": {}
}
```

`node_id` / `edge_id` 用于前端定位并聚焦元素；Frontend 只按 `code` 解析，不解析 message。

## Topology Rules

- 恰好一个 `data/input`（0 个 `MISSING_INPUT_NODE`，多个 `MULTIPLE_INPUT_NODES`）。
- 至少一个 `data/output`（`MISSING_OUTPUT_NODE`）。
- `data/input` 不允许 Incoming；`data/output` 不允许 Outgoing。
- Graph 必须是 DAG（Kahn Topological Sort 检测，`UNSUPPORTED_CYCLE`）。
- 从 Entry 不可达的 Node：`UNREACHABLE_NODE`（ERROR）。
- 无法到达任何 Output 的分支：`DEAD_END_BRANCH`（ERROR）。
- 完全重复的 Connection：`DUPLICATE_CONNECTION`（不同 `source_handle` 视为不同语义 Edge）。
- Parallel：`>= 2` outgoing、`== 1` incoming（`INVALID_PARALLEL`）。
- Merge：strategy 仅 `all`、`>= 2` incoming、`== 1` outgoing（`INVALID_MERGE`）。
- Parallel-Merge 配对：某分支绕过 Merge 直达 Output → `INVALID_PARALLEL_MERGE_STRUCTURE`
  （保守启发式；严格 structured-concurrency 分析推迟）。

## Registry Rules

- Agent：`MISSING_AGENT_REFERENCE` / `AGENT_NOT_FOUND` / `AGENT_DISABLED`(ERROR)
  / `AGENT_UNHEALTHY`(WARNING)。
- Service：`MISSING_SERVICE_REFERENCE` / `SERVICE_NOT_FOUND` / `SERVICE_DISABLED`(ERROR)
  / `SERVICE_UNHEALTHY`(WARNING)。
- Service Action：`MISSING_SERVICE_ACTION_REFERENCE` / `SERVICE_ACTION_NOT_FOUND`
  / `SERVICE_ACTION_DISABLED`(ERROR) / `SERVICE_ACTION_MISMATCH`。

Service Node 的 `input_mapping` 既可保持原有的直接 Body 映射，也可使用显式 HTTP
结构：`{ "path": {...}, "query": {...}, "body": {...} }`。后者分别根据 Action 的
`path_schema`、`query_schema`、`input_schema` 校验 required 字段、closed schema 字段和
可判断的类型兼容性。

## Context Rules

仅在 Node 明确允许 Reference 的字段上校验（Agent `task_template`、各可执行 Node
`input_mapping`、Condition `expression.left/right`、Data transform/output mapping），
metadata 等自由文本不扫描。支持 `workflow.input.*`、`workflow.variables.*`、
`nodes.<id>.output.*`、`run.*`。

- 语法错误：`INVALID_CONTEXT_REFERENCE`。
- 未知节点：`UNKNOWN_CONTEXT_NODE`；未知变量：`UNKNOWN_VARIABLE`。
- 自引用：`INVALID_CONTEXT_REFERENCE`。
- **可引用 Output 的节点**：仅 Agent、Service、Data Transform 具有明确输出语义。
  引用 Condition / Parallel / Merge / Router / Human / Tool / Data Input / Data Output
  的 `.output` 一律报 `INVALID_OUTPUT_REFERENCE`，避免产生 Runtime 无法满足的
  数据依赖（例如引用 `{{nodes.<condition>.output.x}}` 会放行但运行期取不到值）。
- 被引用节点必须是当前节点的 Control-Flow 上游（ancestor）：否则
  `INVALID_DATA_DEPENDENCY`；若属 Parallel 同级分支则 `INVALID_PARALLEL_DATA_DEPENDENCY`
  （已经过 Merge 收敛的引用归为前向引用 `INVALID_DATA_DEPENDENCY`，不算同级分支）。
- Closed schema 下字段不存在：`UNKNOWN_WORKFLOW_INPUT` / `INVALID_OUTPUT_REFERENCE`；
  开放/未知 schema 跳过字段级检查（不假装知道）。Data Transform 的 output 字段按其
  `mappings` keys 校验。

## Schema Compatibility（有限、可靠）

- 仅处理顶层 primitive type、required fields、`additionalProperties=false`。
- 类型矩阵：`integer→number` 安全；`number→integer` 为窄化 WARNING；
  其余不一致 → `SCHEMA_TYPE_MISMATCH`（ERROR）。
- Source 分类：Literal 由 Python 值推断；纯 Reference 通过目标 schema 解析类型；
  模板字符串视为 `string`；不可解析值跳过。
- 不做完整 JSON Schema 类型系统、不做深层 structural subtyping。

## Draft vs Version Validation

- **Save Draft**：只做 Contract 校验（含 Registry 引用存在性，Phase 3 行为）。
  允许保存业务不完整 Graph（由 Validate 报告缺失）。
- **Create Version**：先 Full Validation；有 ERROR 则拒绝，WARNING 允许。

## 稳定 Validation Codes

完整列表见 `backend/app/runtime/validation/codes.py`（`ValidationCode` StrEnum）。
新增 code 前先评估是否真的需要独立信号；Frontend 与 API 都依赖这些 code 的稳定性。
