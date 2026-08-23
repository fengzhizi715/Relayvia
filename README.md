# Relayvia

Relayvia 是一个连接、编排、执行和追踪已有 Agent 与 Service 的平台。

当前实现包括：Agent/Service Registry、Credential Reference、Workflow Graph 1.0、不可变 Workflow Version、可视化 Workflow Builder、Validation Engine、Workflow Run / Node Run + Runtime State Machine、**MySQL-backed Execution Queue + Scheduler + 独立 Worker**、**Execution Unit + Connector**、**Context / Variable Mapping**、**Condition / Parallel / Merge**、**Human Approval + Human Input + Wait / Resume**、**Artifact**、**Run Trace + SSE**、**Relayvia Runner**、**Workspace Manager**，以及 **Coding Agent Adapter**（Codex 作为 Agent Connector：Scheduler 解析 task 构造 CLI 命令 → Runner 在 Workspace/Worktree 内执行 → git diff patch Artifact → NodeRun completed；Capability 检测、OpenCode/Cursor 类型保留）。

P1 安全与可运行性边界：取消或 fail-fast 会向正在执行本地命令的 Runner 发出协作式终止信号；
Router、Local/Custom/OpenCode/Cursor 等未安装 Execution Unit 的能力不能发布 Workflow Version；
Connector/Runner 输出会在持久化前脱敏。多主机部署请使用 S3/MinIO Artifact Storage，而非各机器自己的本地目录。

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

生成并填写以下值；受保护 API 在令牌为空时会以 `503` 拒绝请求，而不是匿名运行：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' # control-plane token
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' # runner enrollment token
```

将第一个值填入 `RELAYVIA_CONTROL_PLANE_TOKEN`，第二个填入
`RELAYVIA_RUNNER_ENROLLMENT_TOKEN`。生产环境还必须替换
`RELAYVIA_CREDENTIAL_ENCRYPTION_KEY`，不要使用示例密钥。

本地前端还需要配置同一个 Control Plane Token：

```bash
cp frontend/.env.example frontend/.env
# 将 VITE_RELAYVIA_CONTROL_PLANE_TOKEN 填为 RELAYVIA_CONTROL_PLANE_TOKEN 的值
```

`VITE_*` 变量会进入浏览器包，仅适合可信本地开发。共享环境应由反向代理或 SSO
验证用户身份，再转发到 Relayvia；当前 V1 的共享 bearer token 不是多用户 RBAC。

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

Runner 默认拒绝直接执行 Workflow shell 命令。生产环境请设置
`RELAYVIA_RUNNER_SANDBOX_COMMAND=/absolute/path/to/runner-sandbox`；该 Wrapper 会以
`--root <runner-root> --cwd <working-directory> -- /bin/sh -lc <command>` 形式被调用，
负责实际 OS/container 隔离。仅在完全可信的本地开发机器上，才可显式设置：

```bash
RELAYVIA_RUNNER_ALLOW_UNSANDBOXED_EXECUTION=true
```

`RUNNER_ROOT` 只是工作目录与 Workspace 路径约束，不是安全沙箱。

默认禁止私网、环回与云元数据 HTTP URL，以降低 SSRF 风险。若本地/边缘环境确实需要
连接 `localhost` 或内网服务，显式设置 `RELAYVIA_ALLOW_PRIVATE_NETWORK_URLS=true`。

单机开发默认使用本地 Artifact 目录。API 与 Worker 分布在不同主机时，必须改用共享对象存储：

```bash
RELAYVIA_ARTIFACT_STORAGE_BACKEND=s3
RELAYVIA_ARTIFACT_S3_BUCKET=relayvia-artifacts
# MinIO 等 S3 兼容服务可额外设置：
RELAYVIA_ARTIFACT_S3_ENDPOINT_URL=http://minio.internal:9000
```

对象存储认证遵循 boto3 的标准 credential provider chain；不要将其访问密钥保存到 Relayvia
Credential Registry。

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

真实 MySQL 8 队列测试应使用独立、可销毁且以 `_test` 结尾的数据库。先运行 Alembic migration，
再显式提供连接串：

```bash
RELAYVIA_MYSQL_TEST_URL=mysql+pymysql://relayvia:relayvia@127.0.0.1:3306/relayvia_test \
  PYTHONPATH=backend .venv/bin/pytest backend/tests/test_mysql_integration.py -q
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
