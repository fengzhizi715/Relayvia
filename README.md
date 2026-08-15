# Relayvia

Relayvia 是一个连接、编排、执行和追踪已有 Agent 与 Service 的平台。

当前实现到 Phase 4：Agent/Service Registry、Credential Reference、HTTP Connection Test、Workflow Graph 1.0、不可变 Workflow Version，以及基于 React Flow 的**可视化 Workflow Builder**（Node Palette、Canvas 编辑、Node/Edge Inspector、Input Mapping、Draft 保存 / 恢复、只读 Version 画布）。

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

# 仅启动前端
./run-frontend.sh
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
GET|POST /api/workflows/{id}/versions
GET /api/workflows/{id}/versions/{version}

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
