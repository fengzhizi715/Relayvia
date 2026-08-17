# Relayvia

Relayvia 是一个连接、编排、执行和追踪已有 Agent 与 Service 的平台。

当前实现到 Phase 16：Agent/Service Registry、Credential Reference、Workflow Graph 1.0、不可变 Workflow Version、可视化 Workflow Builder、Validation Engine、Workflow Run / Node Run + Runtime State Machine、**MySQL-backed Execution Queue + Scheduler + 独立 Worker**、**Execution Unit + Connector**、**Context / Variable Mapping**、**Condition / Parallel / Merge**、**Human Approval + Human Input + Wait / Resume**、**Artifact**、**Run Trace + SSE**、**Relayvia Runner**、**Workspace Manager**，以及 **Coding Agent Adapter**（Codex 作为 Agent Connector：Scheduler 解析 task 构造 CLI 命令 → Runner 在 Workspace/Worktree 内执行 → git diff patch Artifact → NodeRun completed；Capability 检测、OpenCode/Cursor 类型保留）。

Execution Queue 文档：[`docs/execution-queue-worker.md`](docs/execution-queue-worker.md)
Runtime 状态机文档：[`docs/workflow-runtime-state-machine.md`](docs/workflow-runtime-state-machine.md)
Validation 文档：[`docs/workflow-validation.md`](docs/workflow-validation.md)

## 本地开发

### 1. 创建 Python 虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

### 2. 启动 MySQL 8

如果本机已安装 Docker：

```bash
docker compose up -d mysql
```

然后复制环境变量模板：

```bash
cp .env.example .env
```

生产环境请替换 `RELAYVIA_CREDENTIAL_ENCRYPTION_KEY`，不要使用示例密钥。

### 3. 执行数据库迁移

```bash
cd backend
../.venv/bin/alembic upgrade head
cd ..
```

### 4. 启动 FastAPI

```bash
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

健康检查地址：<http://localhost:8000/api/health>

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：<http://localhost:5173>

也可以使用项目根目录的启动脚本：

```bash
# 启动后端和前端，Ctrl+C 同时停止
./run-all.sh

# 仅启动后端
./run-backend.sh

# 启动 Worker（MySQL-backed Execution Queue 消费者）
./run-worker.sh

# 启动本地/内网 Runner（必须设置其允许访问的根目录）
RELAYVIA_RUNNER_ROOT=/absolute/path/to/runner-root ./run-runner.sh

# 仅启动前端
./run-frontend.sh
```

可配置的 Worker 环境变量：

```bash
RELAYVIA_WORKER_POLL_INTERVAL=0.5
RELAYVIA_WORKER_LEASE_SECONDS=60
RELAYVIA_WORKER_LEASE_RENEW_INTERVAL=20
RELAYVIA_WORKER_RECOVERY_INTERVAL=30
RELAYVIA_RUNNER_ROOT=/absolute/path/to/runner-root
```

可通过环境变量覆盖默认地址和端口：

```bash
BACKEND_HOST=0.0.0.0 BACKEND_PORT=8000 \
FRONTEND_HOST=0.0.0.0 FRONTEND_PORT=5173 \
./run-all.sh
```

后端开发热重载默认开启；设置 `RELAYVIA_RELOAD=0` 可关闭。

## 测试

```bash
PYTHONPATH=backend .venv/bin/pytest
cd frontend && npm run test && npm run typecheck && npm run build
```

当前提供的 API：

```text
GET|POST /api/agents
GET|PUT|DELETE /api/agents/{id}
POST /api/agents/{id}/test

GET|POST /api/services
GET|PUT|DELETE /api/services/{id}
POST /api/services/{id}/test
GET|POST /api/services/{id}/actions
GET|PUT|DELETE /api/services/{id}/actions/{action_id}

GET|POST /api/credentials
PUT|DELETE /api/credentials/{id}

GET|POST /api/workflows
GET|PUT|DELETE /api/workflows/{id}
GET|PUT /api/workflows/{id}/graph
POST /api/workflows/{id}/validate
GET|POST /api/workflows/{id}/versions
GET /api/workflows/{id}/versions/{version}
POST /api/workflows/{id}/runs

GET /api/workflow-runs
GET /api/workflow-runs/{id}
POST /api/workflow-runs/{id}/start
POST /api/workflow-runs/{id}/pause
POST /api/workflow-runs/{id}/resume
POST /api/workflow-runs/{id}/cancel
GET /api/workflow-runs/{id}/nodes
GET /api/workflow-runs/{id}/nodes/{node_run_id}
GET /api/workflow-runs/{id}/execution-tasks

Workflow Graph Contract 文档：[`docs/workflow-graph-contract.md`](docs/workflow-graph-contract.md)

## Visual Workflow Builder

Workflow 列表点击 **Open Builder** 进入可视化编辑：

- 左侧 Node Palette：Data / Agent / Service / Tool / Logic / Human 六类节点（Router 暂不开放）
- 中间 React Flow Canvas：添加、拖动、连接、删除节点与边；Condition 提供 true / false 两个输出 Handle
- 右侧 Inspector：按节点类型配置（Agent / Service / Tool / Logic / Human / Data），编辑 Input Mapping 与 Context Reference
- 顶部 Toolbar：Draft 状态（Saved / Unsaved / Saving / Failed）、Save Draft、Create Version、Fit View
- Draft 通过 `PUT /api/workflows/{id}/graph` 整体保存（1.5s debounced autosave + 显式保存）；Backend 仍是最终 Contract Authority
- 历史 Version 可点击 **View in Builder** 以只读画布查看

Builder 代码位于 `frontend/src/workflow/`（adapters / factories / store / validation / canvas / nodes / inspector / mapping）。
```
