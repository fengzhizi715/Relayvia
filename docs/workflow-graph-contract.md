# Relayvia Workflow Graph Contract 1.0

本文件定义 Phase 3 的 Workflow Definition Contract。它描述“要编排什么”，不描述 Runtime 状态；`task_status`、`started_at`、`finished_at`、日志、重试计数和输出结果属于后续 Run / NodeRun，而不是 Graph。

## Draft 与 Version

`Workflow` 保存可编辑 Draft：

```text
Workflow
  ├── draft_graph_json       editable Graph Schema 1.0
  ├── graph_schema_version   explicit queryable version
  └── current_version        latest immutable version number
```

`POST /api/workflows/{id}/versions` 在事务中锁定 Workflow 行，校验 Draft，复制 Graph JSON，并生成下一个整数 Version。复制后的 `WorkflowVersion.graph_json` 不再受 Draft 修改影响；历史 Version 没有 PUT 或 DELETE API。发布第一个 Version 会把 Workflow 标记为 `active`。没有 Version 的 Workflow 可以 hard delete；已有 Version 的 Workflow 的删除操作改为 `archived`，以保留历史定义。

当前版本只保存 Registry ID，不复制 Agent、Service 或 Service Action 配置。后续 Runtime 需要决定使用 Registry 当前配置，还是在发布时保存 Invocation Snapshot；Phase 3 暂不预设 Runtime 策略。

## Graph 顶层结构

```json
{
  "schema_version": "1.0",
  "nodes": [],
  "edges": [],
  "variables": {},
  "metadata": {}
}
```

`schema_version` 是显式的 Graph Contract 版本。Phase 3 只接受 `1.0`。`nodes` 和 `edges` 是数组；`variables` 是 Workflow 级变量定义；`metadata` 只用于非核心扩展，不能代替核心字段。

## Node 基础 Contract

每个 Node 都有：

```json
{
  "id": "planner",
  "type": "agent",
  "subtype": "agent",
  "name": "Planner",
  "position": {"x": 300, "y": 100},
  "config": {},
  "input_mapping": {},
  "metadata": {}
}
```

Node ID 只在 Graph 内唯一，与数据库 Entity ID 解耦；它同时作为未来 React Flow Node ID。Node name 只是当前 Workflow 中的显示名，不能作为 Registry Reference。

V1 `type` 只有：`agent`、`service`、`tool`、`logic`、`human`、`data`。

## Node Contracts

### Agent

`subtype=agent`，`config`：

```json
{
  "agent_id": "<existing-agent-id>",
  "role": "planner",
  "task_template": "Analyze {{workflow.input.requirement}}",
  "timeout_seconds": 600,
  "retry": {"max_retries": 2}
}
```

只允许通过 `agent_id` 引用 Agent Registry。Graph 不允许保存 `model`、`temperature`、`system_prompt`、`knowledge_base`、Credential Secret 或 Provider-specific 配置。

### Service

`subtype=http`，`config`：

```json
{
  "service_id": "<existing-service-id>",
  "service_action_id": "<existing-service-action-id>",
  "timeout_seconds": 60,
  "retry": {"max_retries": 2}
}
```

保存时必须确认 Service Action 存在且属于该 Service。Graph 不复制 Service Action 的 URL、Headers 或 Credential。

### Tool

`subtype` 为 `shell`、`git` 或 `test_command`，`config`：

```json
{
  "command": "pytest",
  "working_directory": null,
  "timeout_seconds": 600
}
```

Tool Contract 必须由 Relayvia Runner 执行。`config.runner_id` 是运行前必填的目标
Runner 引用；Run 创建时会验证该 Runner 在线且具备 `shell` Capability。Server Worker
不会执行命令。

### Logic

支持以下 subtype：

* `condition`：`config.expression` 为单个比较 `{"left", "operator", "right"}`，或递归组合
  `{"and": [clause, ...]}` / `{"or": [clause, ...]}`（单层内 and/or 不可混用，且不能与比较共存）。
  operator 仅限 `==`、`!=`、`>`、`>=`、`<`、`<=`、`contains`、`not_contains`、`is_empty`、`is_not_empty`。
  左/右值可为字面量或 Context Reference。此扩展向后兼容：原单比较结构不变。
* `parallel`：`config` 为 `{}`；分支只由 Edge 表达。
* `merge`：`config.strategy` 当前为 `all`。
* `router`：当前保留空 `config`，不实现 Runtime 语义。
* `wait`：`config` 为 `{ "mode": "duration", "duration_seconds": 60 }`；其它等待模式留给后续阶段。

Condition 的 true/false 分支使用 Edge 的 `source_handle`，不在 Node Config 中保存 target。

### Human

* `approval`：`config` 为 `title`、可选 `description`、`allow_reject`。
* `input`：`config.form_schema` 为 JSON Schema。

Phase 3 只保存 Contract，不实现 WAITING、审批或恢复 Runtime。

### Data

* `input`：`config.schema` 为 JSON Schema；后续可定义一个 Primary Input Node。
* `transform`：`config.mappings`，只表达 mapping/template/select/rename/constant，不执行任意代码。
* `output`：`config.output_mapping`。

## Input Mapping 与 Context Reference

所有可执行 Node 使用顶层 `input_mapping` 表达数据依赖；`config` 表达 Node 行为。引用语法集中定义在后端 `context_reference` 模块：

```text
{{workflow.input.requirement}}
{{workflow.variables.training_threshold}}
{{nodes.edge_agent.output.hard_sample_count}}
{{run.some_runtime_value}}
```

后端能够 Parse、Validate Syntax 并提取 Node Dependency；Phase 3 不 Resolve Runtime Value。引用到不存在的 Node 会被拒绝。

## Variables

```json
{
  "training_threshold": {
    "type": "number",
    "default": 0.8,
    "description": "Minimum evaluation threshold"
  }
}
```

变量类型为 `string`、`number`、`integer`、`boolean`、`object`、`array`。不定义 Secret Variable；Secret 继续通过 Credential Registry 管理。

## Edge Contract

```json
{
  "id": "edge-planner-reviewer",
  "source": "planner",
  "target": "reviewer",
  "source_handle": "true",
  "target_handle": null,
  "label": "passed",
  "condition": null,
  "metadata": {}
}
```

Edge ID 必须唯一，`source` 和 `target` 必须引用当前 Graph 中存在的 Node。`source_handle` 可表达 Condition 分支；Parallel/Merge 的结构也由 Edge 表达。Phase 5 才做完整的拓扑、Cycle、Branch 和 Schema Compatibility Validation。

## Contract-level Validation

Draft PUT 和 Create Version 都执行同一组校验：

* Graph Schema Version 必须为 `1.0`。
* Pydantic 校验 Node、Config、Position、Variable 和 Edge 的结构。
* Node ID、Edge ID 唯一；Edge source/target 存在。
* JSON Schema 字段有效。
* Context Reference 语法有效，引用 Node 存在。
* Agent Node 的 Agent 存在；Service Node 的 Service 和 Action 存在且匹配。
* disabled Agent/Service/Action 允许被保存，但返回 Warning。

这不是完整 Workflow Graph Validation；Runtime、拓扑、输入输出兼容性和执行可行性留给后续阶段。
