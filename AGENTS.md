# AGENTS.md

# Relayvia 工程指南

Relayvia 是一个用于连接和编排**已有 AI Agent** 与**已有业务 Service** 的可视化编排平台。

Relayvia **不负责创建 Agent**，也**不负责创建业务 Service**。

Relayvia 的核心职责是：

```text
Existing Agents + Existing Services
              ↓
           Relayvia
              ↓
      Visual Workflow
              ↓
       Workflow Runtime
              ↓
 Execution / Trace / Human
```

一句话定位：

> Relayvia 是已有 Agent 与已有 Service 的统一连接、编排、执行与追踪层。

---

# 1. 产品定位

Relayvia 的产品定位是：

> **Agent & Service Orchestration Platform**

Relayvia 主要负责：

- 接入已有 Agent
- 接入已有 Service
- 对 Agent 与 Service 进行可视化编排
- 执行 Workflow
- 持久化 Workflow 状态
- 在节点之间传递 Context
- 在节点之间传递 Artifact
- 支持异步任务
- 支持等待与恢复
- 支持 Human-in-the-loop
- 提供 Run Trace 与基础可观测能力

Relayvia 必须尽量保持：

- Agent Provider Independent
- Service Provider Independent
- Model Independent
- Runtime Independent
- Framework Independent

一个 Agent 可以由以下任意方式实现：

- Codex
- Cursor
- OpenCode
- Claude Code
- Dify
- LangGraph
- CrewAI
- 自定义 Python Agent
- HTTP Agent
- 未来的 A2A Agent

Relayvia 不应该依赖 Agent 内部的具体实现。

---

# 2. 明确的产品边界

Relayvia V1 **不是 Agent Builder**。

除非需求明确提出，否则不要实现以下能力：

- Agent 创建
- Agent Studio
- Prompt Studio
- Agent System Prompt 管理
- RAG
- Knowledge Base
- Model Provider 管理
- 模型训练
- Agent 微调
- Agent Marketplace
- SaaS Connector Marketplace
- 大量厂商专用 Connector
- 复杂 Multi-Tenant
- 复杂 RBAC
- Billing
- 成本计费
- SLA 管理
- 完整 Enterprise Governance

Agent 的所有权始终属于外部系统。

以下内容由外部 Agent 自己负责：

- Agent Model
- Agent Prompt
- Agent Memory
- Agent Tools
- Agent Knowledge Base
- Agent Internal Workflow
- Agent Lifecycle

Relayvia 只保存调用和编排 Agent 所必需的信息。

---

# 3. V1 核心验证场景

Relayvia V1 必须使用**同一套 Workflow Runtime** 支撑两个完全不同的场景。

## 3.1 场景 A：Coding Agent Orchestration

示例：

```text
Requirement
    ↓
Planner Agent
    ↓
Parallel
 ┌──────┴──────┐
 ↓             ↓
Frontend      Backend
Agent         Agent
 ↓             ↓
Test          Test
 └──────┬──────┘
        ↓
Reviewer Agent
        ↓
Human Approval
        ↓
Git / PR
```

可能接入的已有 Coding Agent：

- Codex
- Cursor
- OpenCode
- Claude Code
- 其他 Coding Agent

该场景用于验证：

- Local Runner
- Agent Adapter
- Workspace Isolation
- Git Branch / Git Worktree
- Parallel Execution
- Tool Execution
- Context Passing
- Human Approval
- Run Trace

---

## 3.2 场景 B：工业 Edge Agent + YoloWebAgent

示例：

```text
Edge Agent
    ↓
Defect / Hard Sample Detection
    ↓
Condition
    ↓
Human Approval
    ↓
YoloWebAgent Service
    ↓
Dataset Import
    ↓
Training Job
    ↓
Wait
    ↓
Evaluation
    ↓
Condition
    ↓
Output
```

Edge Agent 内部可能使用：

- YOLO
- VLM
- LLM

Relayvia 不关心 Edge Agent 内部如何实现。

当 Relayvia 调用 YoloWebAgent 的以下能力时，YoloWebAgent 应优先被建模成 Service：

- Dataset Import
- Training Start
- Training Status
- Evaluation
- Model Export

该场景用于验证：

- Agent + Service Orchestration
- HTTP Service
- Async Job
- Waiting / Resume
- Artifact
- Human Approval
- Durable Workflow State

---

# 4. V1 技术栈

除非明确修改，否则使用以下技术栈。

## 4.1 Frontend

- React
- TypeScript
- React Flow
- Zustand
- TanStack Query

Workflow Canvas 优先使用 React Flow。

除非有明确、经过说明的技术原因，否则不要在 Relayvia Workflow Builder 中引入 Konva。

## 4.2 Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

## 4.3 Database

- MySQL 8

## 4.4 Workflow Runtime

- Relayvia 自己维护的 Workflow Runtime
- MySQL-backed Execution Queue
- 独立 Python Worker

## 4.5 Realtime

V1 优先使用：

- SSE

## 4.6 Local Execution

V1 使用：

- Relayvia Runner
- Python 实现

## 4.7 V1 暂不引入

除非需求明确要求，否则不要主动引入：

- Redis
- Celery
- RabbitMQ
- Kafka
- Temporal
- Kubernetes

未来可以替换或增加这些基础设施，但不允许影响 Workflow Definition Contract。

---

# 5. 核心架构原则

## 5.1 Control Plane 与 Execution Plane 必须分离

FastAPI 属于 Control Plane。

API 进程不得直接执行长时间运行的 Workflow。

推荐结构：

```text
Frontend
   ↓
FastAPI
   ↓
MySQL
   ↓
Execution Queue
   ↓
Worker
   ↓
Execution Unit
```

长任务必须由：

- Worker
- Runner

负责执行。

---

## 5.2 Workflow Engine 必须由 Relayvia 自己拥有

不要把 Relayvia 设计成：

- Celery 的 UI Wrapper
- Temporal 的 UI Wrapper
- 第三方 Workflow Engine 的薄封装

以下概念属于 Relayvia 自己：

- Workflow Definition
- Workflow Version
- Workflow Run
- Node Run
- Workflow State Machine
- Node State Machine
- Context
- Artifact
- Graph Validation
- Execution Scheduling Semantics

底层基础设施可以负责“执行任务”，但不能定义 Relayvia 的产品模型。

---

## 5.3 Connector 与 Workflow Runtime 必须隔离

禁止在 Workflow Runtime 中直接写大量 Provider-specific 逻辑，例如：

```python
if agent == "codex":
    ...
elif agent == "cursor":
    ...
elif agent == "opencode":
    ...
```

Provider-specific 行为必须进入 Connector / Adapter。

推荐架构：

```text
Workflow Runtime
      ↓
Execution Unit
      ↓
Connector
      ↓
External Agent / Service
```

---

# 6. 核心 Domain Model

Relayvia V1 主要围绕以下领域对象设计：

- Agent
- Agent Connector
- Service
- Service Action
- Workflow
- Workflow Version
- Workflow Run
- Node Run
- Execution Task
- Run Event
- Runner
- Credential
- Artifact
- Workspace

不要在缺少明确产品意义时随意增加 Domain Entity。

---

# 7. Workflow Node 类型

Relayvia V1 支持六类主要 Node。

## 7.1 Agent Node

调用一个已经存在的 Agent。

例如：

- Codex
- Cursor
- OpenCode
- HTTP Agent

Agent Node 只引用 Agent Registry 中已经连接的 Agent。

Agent Node 不负责配置：

- Model
- System Prompt
- Temperature
- Knowledge Base
- Internal Memory
- Internal Tool

UI 应使用：

> Connect Agent

而不是：

> Create Agent

---

## 7.2 Service Node

调用已经存在的业务或技术 Service。

V1 首先支持：

- HTTP

未来可支持：

- OpenAPI Import
- Webhook
- gRPC
- GraphQL

V1 不要开始建设大量 SaaS Vendor Connector。

Relayvia 的原则是：

> 业务系统只要能够提供标准 API，就可以接入。

---

## 7.3 Tool Node

Tool 表示执行能力，而不是业务系统。

V1 示例：

- Shell
- Git
- Test Command

Tool 与 Service 在产品模型上保持区分，即使底层最终都可能通过 HTTP 或 Process 调用实现。

---

## 7.4 Logic Node

V1 支持：

- Condition
- Parallel
- Merge
- Router
- Wait

V1 暂不要求：

- Complex Loop
- Nested Loop
- 无限循环
- 复杂 Break / Continue

---

## 7.5 Human Node

V1 支持：

- Human Approval
- Human Input

Human Node 必须支持持久化：

```text
RUNNING
   ↓
WAITING
   ↓
RUNNING
```

Workflow 可以等待数分钟、数小时甚至更久，并在人工操作后继续运行。

---

## 7.6 Data Node

V1 数据能力包括：

- Input
- Transform
- Output
- Variable
- Context Reference

Artifact 与普通 JSON Context 分开处理。

---

# 8. Execution Unit 抽象

可以执行的 Node 应逐步统一到 Execution Unit 抽象。

概念上：

```python
class ExecutionUnit:
    async def execute(...):
        ...

    async def cancel(...):
        ...

    async def status(...):
        ...
```

Execution Unit 可以代表：

- Agent
- Service
- Tool
- 未来的 LLM Node

统一处理：

- Input
- Output
- Schema
- Timeout
- Retry
- Credential Reference
- Execution Metadata

不要把 Connector-specific 配置泄露到通用 Workflow Runtime 中。

---

# 9. Workflow Graph Contract

Workflow Graph 是 Relayvia 的核心持久化 Contract。

必须谨慎设计。

一个 Workflow Version 至少应该可以完整重建可执行 Graph。

概念结构：

```json
{
  "nodes": [],
  "edges": [],
  "variables": {},
  "metadata": {}
}
```

Node 应包含稳定字段，例如：

```json
{
  "id": "node_xxx",
  "type": "agent",
  "name": "Reviewer",
  "config": {},
  "input_mapping": {},
  "position": {}
}
```

不要随意修改已经持久化的 Graph Schema。

任何 Breaking Graph Contract 变更都必须考虑：

- Migration
- Backward Compatibility
- Tests
- Historical Workflow Version

---

# 10. Workflow Version

必须区分：

```text
Workflow
   ↓
Workflow Version
   ↓
Workflow Run Snapshot
```

每一次 Workflow 执行必须绑定：

- 一个不可变 Workflow Version

或：

- 一个不可变 Graph Snapshot

用户修改 Workflow 后：

- 不能影响已经存在的 Run
- 不能修改历史 Version
- 历史 Run 必须仍然能够查看原始执行 Graph

---

# 11. Graph Validation

Workflow 在执行前必须进行 Graph Validation。

V1 至少检查：

- Start 是否存在
- 必要时 End 是否存在
- 非法 Edge
- Self Connection
- 缺失 Node 配置
- 缺失 Agent Reference
- 缺失 Service Reference
- 非法 Context Reference
- Required Input
- Input / Output Schema Compatibility（可判断时）
- Unsupported Cycle
- Branch Validity
- Parallel / Merge 结构是否合法

能够在执行前发现的问题，不要依赖 Runtime 失败。

---

# 12. Workflow State Machine

Workflow 状态必须持久化到 MySQL。

推荐 Workflow Run 状态：

```text
CREATED
RUNNING
WAITING
PAUSED
COMPLETED
FAILED
CANCELLED
```

推荐 Node Run 状态：

```text
PENDING
QUEUED
RUNNING
WAITING
RETRYING
COMPLETED
FAILED
SKIPPED
CANCELLED
```

状态迁移必须明确。

避免使用大量：

```text
is_running
is_finished
is_waiting
```

这种 Boolean 组合模拟状态机。

---

# 13. Durable Execution

Relayvia Workflow 必须是 Database-backed Workflow。

应用、Worker 或 Runner 重启后，不得丢失 Workflow 状态。

以下状态必须能够恢复：

- Waiting for Human Approval
- Waiting for External Job
- Retry Delay
- Partially Completed Workflow
- Completed Node Output
- Workflow Context
- Artifact Reference

不要把 Durable State 只放在进程内存。

---

# 14. MySQL-backed Execution Queue

V1 使用 MySQL 作为 Execution Queue。

Execution Task 建议包含：

```text
id
workflow_run_id
node_run_id
status
payload_json
priority
retry_count
max_retries
available_at
locked_by
locked_at
created_at
started_at
finished_at
```

Worker 必须使用安全的数据库事务 Claim Task。

MySQL 8 可使用类似：

```sql
SELECT ...
FOR UPDATE SKIP LOCKED;
```

避免多个 Worker 重复领取同一个任务。

---

# 15. Execution Backend 抽象

执行队列应该通过统一接口隔离。

概念接口：

```text
ExecutionBackend

submit()
claim()
complete()
fail()
retry()
cancel()
heartbeat()
```

V1：

```text
MySQLExecutionBackend
```

未来可以增加：

```text
RedisExecutionBackend
TemporalExecutionBackend
```

Workflow Runtime 不得直接依赖 MySQL Queue 的内部实现细节。

---

# 16. Context 与变量模型

使用统一、可预测的 Context Reference。

建议：

```text
workflow.input.xxx

workflow.variables.xxx

nodes.<node_id>.output.xxx

run.xxx
```

例如：

```text
{{nodes.contract_agent.output.customer_id}}
```

不要在 Node 之间引入不可见的隐式共享状态。

Node Input / Output 应：

- 可检查
- 可追踪
- 可 Debug

---

# 17. Artifact Model

大型文件或二进制内容不得直接塞进 Node JSON Output。

Coding 场景中的 Artifact 包括：

- Patch
- Source File
- Commit
- Test Report

工业场景中的 Artifact 包括：

- Image
- Image Batch
- Dataset
- Annotation
- Model
- Evaluation Report

Artifact 概念模型：

```text
Artifact

id
type
uri
metadata
producer_node_run_id
workflow_run_id
created_at
```

Node Output 可以引用：

```text
artifact://artifact-id
```

明确区分：

- Context = 结构化 Workflow 数据
- Artifact = 文件、大对象、外部资源

---

# 18. Agent Registry

Relayvia 负责连接 Agent，而不是创建 Agent。

UI 术语：

> Connect Agent

不要使用：

> Create Agent

Agent Registry 只保存调用所需 Metadata。

推荐字段：

```text
id
name
description
connector_type
endpoint
runner_id
capabilities
input_schema
output_schema
credential_id
timeout
status
metadata
```

---

# 19. Service Registry

Relayvia 负责连接已有 Service。

UI 术语：

> Connect Service

一个 Service 可以拥有多个 Service Action。

例如：

```text
YoloWebAgent

├── Import Dataset
├── Start Training
├── Get Training Status
├── Evaluate Model
└── Export Model
```

Service Action 推荐字段：

```text
id
service_id
name
method
path
headers
input_schema
output_schema
timeout
retry_policy
```

---

# 20. Runner

Relayvia Runner 用于在用户本地、内网、边缘环境中执行任务。

典型用途：

- Local Coding Agent
- Git Repository
- Shell
- Local Development Tool
- Private Network Service
- Future Edge Environment

Runner 必须上报 Capability。

例如：

```text
Runner: Mac-Mini

Capabilities:
- codex
- opencode
- git
- shell
- python
- node
```

Runner 状态不能只依赖内存 Connection。

必须持久化：

- last_seen_at
- heartbeat
- capabilities
- status metadata

---

# 21. Workspace Isolation

多个 Coding Agent 并发执行时，默认不要同时修改同一个 Working Directory。

推荐：

```text
Repository

├── worktree/task-a
├── worktree/task-b
└── worktree/review
```

优先通过：

- Git Branch
- Git Worktree

实现 Workspace Isolation。

Workspace Management 与通用 Agent Execution 必须保持概念隔离。

---

# 22. Run Trace 与 Event

每个 Workflow Run 必须可以查看。

每个 Node Run 至少能够查看：

- Input
- Output
- Logs
- Error
- Duration
- Retry Count
- Runner
- Start Time
- End Time

持久化 Run Event。

典型 Event：

```text
WORKFLOW_STARTED
WORKFLOW_WAITING
WORKFLOW_RESUMED
WORKFLOW_COMPLETED
WORKFLOW_FAILED

NODE_QUEUED
NODE_STARTED
NODE_LOG
NODE_COMPLETED
NODE_FAILED
NODE_RETRYING
```

V1 Realtime 优先使用：

- SSE

不要仅仅为了实时 UI 在 V1 引入 Redis。

---

# 23. Credential

Credential 必须集中管理并通过 Reference 使用。

V1 至少支持：

- API Key
- Bearer Token
- Basic Auth

禁止：

- 明文保存 Secret
- 在 API Response 返回 Secret
- 在 Log 中打印 Secret
- 在 Trace 中记录 Secret
- 在 Workflow Snapshot 中复制 Secret
- 在 Node Output 中泄露 Secret

Node / Agent / Service 只保存：

```text
credential_id
```

而不是 Token 本身。

---

# 24. Backend 目录原则

推荐 Domain-oriented 目录。

例如：

```text
backend/

├── app/
│   ├── api/
│   ├── domain/
│   │   ├── agents/
│   │   ├── services/
│   │   ├── workflows/
│   │   ├── runs/
│   │   ├── runners/
│   │   ├── artifacts/
│   │   └── credentials/
│   │
│   ├── connectors/
│   │   ├── agents/
│   │   ├── services/
│   │   └── tools/
│   │
│   ├── runtime/
│   │   ├── orchestrator/
│   │   ├── executor/
│   │   ├── scheduler/
│   │   ├── state_machine/
│   │   ├── validation/
│   │   └── context/
│   │
│   ├── infrastructure/
│   │   ├── database/
│   │   ├── execution_backend/
│   │   └── security/
│   │
│   └── workers/
```

这只是结构指导。

不要为了满足目录形式，过早创建大量空目录和空抽象。

---

# 25. Frontend 目录原则

推荐 Feature-oriented 结构。

例如：

```text
frontend/src/

├── features/
│   ├── agents/
│   ├── services/
│   ├── workflows/
│   ├── runs/
│   └── runners/
│
├── workflow/
│   ├── canvas/
│   ├── nodes/
│   ├── edges/
│   ├── inspector/
│   ├── validation/
│   └── store/
│
├── api/
├── components/
└── shared/
```

Workflow Canvas State 与 Backend Persisted Entity 应保持清晰边界。

---

# 26. Database 规则

数据库 Migration 统一使用：

- Alembic

禁止将生产数据库 Schema 修改逻辑写成应用启动时自动执行的临时脚本。

对于需要：

- Filter
- Sort
- Index
- Join
- Status Query
- Report

的字段，优先使用正常关系型字段。

JSON Column 主要用于：

- Node Config
- Graph Snapshot
- Input Payload
- Output Payload
- Flexible Metadata

不要把整个 Domain Model 都设计成 JSON Blob。

---

# 27. API 规则

优先使用 Resource-oriented API。

例如：

```text
/api/agents
/api/services
/api/workflows
/api/workflow-runs
/api/runners
/api/credentials
```

执行动作可以使用显式 Action Endpoint：

```text
POST /api/workflows/{id}/run

POST /api/workflow-runs/{id}/cancel

POST /api/node-runs/{id}/approve
```

所有 Request / Response 使用 Pydantic Model。

不要直接把 SQLAlchemy ORM Object 暴露成 API Contract。

---

# 28. Error Handling

执行错误必须：

- Structured
- Traceable
- Debuggable

推荐错误结构：

```text
error_code
message
details
retryable
connector
node_run_id
timestamp
```

不要吞掉 Connector Exception。

Provider-specific Exception 应转成 Relayvia Execution Error，同时保留足够的诊断信息。

---

# 29. Testing Priority

测试重点优先覆盖系统不变量，而不是大量 UI Snapshot。

关键测试：

- Graph Validation
- Workflow Version Immutability
- Workflow State Transition
- Node State Transition
- Task Claiming
- Retry
- Parallel Scheduling
- Merge
- WAITING → RUNNING Resume
- Human Approval
- Context Reference Resolution
- Artifact Reference
- Credential Redaction
- Connector Contract

任何涉及 Workflow State / Execution 的 Bug，修复后尽量增加 Regression Test。

---

# 30. AI Coding Agent 开发规则

进行较大修改前：

1. 先理解相关 Domain 与现有 Contract。
2. 先阅读现有代码，再提出架构修改。
3. 不要主动引入超出 V1 范围的基础设施。
4. 优先做最小但完整的修改。
5. 不要悄悄修改 Persisted Schema 或 Public API Contract。
6. 行为发生变化时同步增加或修改测试。
7. 完成前运行相关测试。
8. 修改核心 Contract 时同步更新文档。

对于较大任务：

- 先给出简洁 Implementation Plan
- 再开始 Coding

不要在一个聚焦任务中顺便进行大范围无关重构。

---

# 31. Dependency Discipline

新增 Dependency 前必须判断：

- Python / Browser / 当前技术栈是否已经能够解决？
- 是否真的属于 V1 必需？
- 是否明显增加部署复杂度？
- 是否会污染 Relayvia Domain Contract？
- 是否能够通过 Interface 隔离？

尤其不要主动引入：

- Redis
- Celery
- RabbitMQ
- Kafka
- Temporal

除非：

- 当前需求明确要求
- 或者已经出现 MySQL-backed Execution 无法合理解决的真实技术压力

## 31.1 Python Environment and Dependencies

凡是需要安装 Python 库，必须先创建并使用项目虚拟环境，禁止直接安装到系统或全局 Python 环境。

默认使用项目根目录下的 `.venv`：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install <package>
```

后续运行 Python、测试或相关工具时，也必须使用该虚拟环境中的解释器和依赖。新增依赖应同步记录到项目现有的依赖声明文件（如 `requirements.txt` 或 `pyproject.toml`）中；`.venv` 不应提交到版本库。

---

# 32. V1 Definition of Done

Relayvia V1 不是“画布 UI 完成”就算完成。

V1 至少应该允许用户：

1. Connect 一个已有 HTTP Agent
2. Connect 一个已有 HTTP Service
3. 通过 Relayvia Runner Connect 一个本地 Coding Agent
4. 在 Workflow Builder 中编排这些能力
5. 使用 Condition
6. 使用 Parallel + Merge
7. 使用 Human Approval
8. 将上游 Node Output 映射到下游 Node Input
9. 在 Workflow 中传递 Artifact Reference
10. 保存不可变 Workflow Version
11. 启动 Workflow Run
12. 将执行状态持久化到 MySQL
13. Worker 重启后不丢失 Durable Workflow State
14. 恢复 WAITING Workflow
15. 查看每一个 Node Run
16. 查看 Input / Output / Log / Error / Duration
17. 跑通 Coding Agent Showcase
18. 跑通 Industrial Edge AI Showcase

在完成这些闭环之前，不优先扩大平台功能范围。

---

# 33. V1 明确暂不实现

V1 默认不做：

```text
Agent Builder
Prompt Studio
RAG
Knowledge Base
Model Provider Management
Model Training
Agent Marketplace
SaaS Connector Marketplace
大量 Vendor Connector
Complex Loop
Dynamic Agent Generation
Agent Generated Workflow
Multi Tenant
Complex RBAC
Billing
Cost Accounting
SLA
Full Governance
Redis
Celery
RabbitMQ
Kafka
Temporal
Kubernetes
```

除非用户明确调整 V1 Scope，否则 AI Coding Agent 不应该主动增加这些能力。

---

# 34. Guiding Principle

当架构设计存在多个选择时，优先选择能够强化以下模型的方案：

```text
Existing Capability
        ↓
     Connector
        ↓
     Workflow
        ↓
      Runtime
        ↓
       Trace
```

Relayvia 是 Orchestration Layer。

Relayvia 不应该吸收它所编排的 Agent 与 Service 自己应该承担的职责。

最终始终保持这个边界：

> **Relayvia 不创建能力。Relayvia 连接、编排、执行和追踪已有能力。**
