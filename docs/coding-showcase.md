# Real Coding Agent Showcase

这两个 Showcase 使用现有 Workflow Runtime、API、独立 Worker 和 Runner，数据库读取根目录
`.env` 的 `RELAYVIA_DATABASE_URL`。可以直接连接腾讯云 MySQL，API/Worker/Runner 在本机运行。
数据库应已执行 Alembic migration。脚本只通过 API 新增测试记录，保留 Version、Run、Event
和 Artifact，不清空表或修改已有 Workflow。

## 准备

- 使用项目 `.venv`，安装 `backend/requirements.txt` 中的依赖。
- 安装 Codex CLI，并通过 `codex login status` 确认已有登录。
- `.env` 中配置数据库、Control Plane Token 和 Credential Encryption Key。
- 默认端口 8000 应空闲，也可通过 `--port` 选择其他端口。
- 第二轮需要已安装并已认证的 OpenCode CLI。

可将 OpenCode 安装到项目忽略的工具目录，而不是增加前端或后端生产依赖：

```bash
npm install --prefix data/coding-showcase/tools --no-audit --no-fund opencode-ai@1.18.34
```

CLI 认证由外部 Agent 自己管理，不将其 Token 复制到 Registry 或 Workflow Snapshot。
Codex Connector 使用 `codex exec --json --sandbox workspace-write`，复用已有 CLI 登录。
OpenCode 本轮通过已有 Tool Node 调用，未宣称已实现原生 OpenCode Agent Connector。

## 运行

```bash
# 仅第一轮：Codex -> Approval -> Output
.venv/bin/python examples/coding_showcase.py --round 1

# 两轮；按已有 OpenCode Provider 修改模型参数
.venv/bin/python examples/coding_showcase.py --round all \
  --opencode-model opencode-go/minimax-m2.7

# 可选择已有 CLI 路径和空闲端口
.venv/bin/python examples/coding_showcase.py --round 2 --port 18000 \
  --opencode /absolute/path/to/opencode --opencode-model provider/model

# 中断时从保存的会话继续；完成的轮次不再次调用 Agent
.venv/bin/python examples/coding_showcase.py --round all \
  --session data/coding-showcase/<UTC timestamp>
```

默认的 OpenCode 模型参数只是该测试环境已有账号的示例，不在 Relayvia 中管理 Provider
或创建 Agent。使用其他认证方式时，先在 OpenCode 自身完成连接，再指定模型。

## 两轮验证内容

第一轮：Input -> Codex -> Human Approval -> Output。Codex 在隔离 worktree 中实现
`slugify`，添加测试并执行 unittest。成功后保存 Patch Artifact，测试脚本把 Patch 下载到另一个
全新 worktree，检查固定验收测试没有被修改，并独立运行至少八个测试。

第二轮：Input -> Codex -> Independent Tests -> OpenCode Review -> Human Approval -> Output。
Tests 和 Review 各自在独立 worktree 中通过 `artifact://` 引用下载同一 Patch，然后执行
`git apply --check` 和 `git apply`。OpenCode 真实审查代码，返回明确的 JSON verdict；Provider
错误、无 verdict、拒绝或 correctness issues 都会使测试失败。

两轮都在 Human Approval 的 WAITING 状态停止并重启 API、Worker 和 Runner，检查等待状态、
已完成的 Codex 输出与 attempt 没有变化，然后通过审批 API **模拟人工批准**，观察 Run 完成。
审批自动提交是测试动作，不代表真实用户进行了人工代码审查。

脚本为可信本机的独立演示仓库显式启用 Runner 的 unsandboxed 模式；Codex 仍使用自身的
workspace-write sandbox。该设置仅属于脚本子进程，不修改根目录 `.env`，也不是部署配置。

## 结果与边界

证据保存在忽略的 `data/coding-showcase/<UTC timestamp>/`：

- `report.json`：结果、Workflow/Run ID、验收结果、OpenCode verdict、重启恢复结果。
- `round*-graph.json`、`round*-run.json`、`round*-events.json`：Definition、Node Trace、持久化事件。
- `round*.diff`：实际代码 Patch；`round*-verification.json`：独立验收日志。
- `api.log`、`worker.log`、`runner.log`：本次独立进程日志。
- `runner-identity.json`、`runtime-secrets.json`：权限 0600 的本地认证文件，不能提交或分享。

运行结束停止本次启动的进程，数据库记录与 Artifact 文件保留用于检查。通过常规前端查看 Run
时，要让 API 使用该次会话的 `RELAYVIA_ARTIFACT_STORAGE_DIR` 才能下载本地 Artifact 内容。

这证明串行 Coding Orchestration、Patch 交接、独立测试、真实 Review 和 WAITING 恢复。
它不验证 Git 自动合并、PR 发布、并行编程、执行中的 Agent 重启恢复或跨主机 Artifact 存储。

## 2026-10-05 实测结果

环境：本地 API/Worker/Runner，腾讯云 MySQL 8.0.30；Codex CLI 0.160.0 使用现有
ChatGPT 登录，OpenCode CLI 1.18.34 使用已有 OpenCode Go 认证，模型为
`opencode-go/minimax-m2.7`。

| 轮次 | 结果 | 独立验收 | Workflow Run |
| --- | --- | --- | --- |
| 1 | COMPLETED；Patch 与审批等待在进程重启后保留 | 15 tests passed | `9cd9f128-ab29-44f7-8746-432c4f2a5178` |
| 2 | COMPLETED；独立测试与真实 OpenCode Review 通过，重启恢复成功 | 16 tests passed | `6f475a1e-06d8-4a06-ac03-0bf846ef9def` |

本次证据目录：`data/coding-showcase/20261005T075948Z/`。审批均由测试脚本调用 API 模拟。
后端全套测试 243 项通过；结果提交/续租修复再次通过 32 项相关测试；腾讯云 MySQL
专项测试 5 项通过，覆盖独立连接下的提交/取消竞态。

真实执行曾发现结果提交死锁与机器心跳持续续租废弃任务的问题。已统一提交锁顺序，
刷新取消竞态中的 Task 状态，并让提交重试期间保持任务心跳；不重新调用外部 Agent。

这两轮历史执行曾缺少 Runner NodeRun 的 `input`、`started_at`、`attempt`。
随后已修复：调度持久化解析后的 Input，领取同步开始时间与 attempt；重试保留首次开始
时间。脚本现在检查这三个字段及其重启后的持久化。上述历史 Run 保留原始证据，不回填
推测值；完整 Trace 的验证结果以修复后的执行为准。

### Runner Trace 修复验证（2026-10-05）

后端全套测试 245 项通过，5 项 MySQL 专项默认跳过；显式连接腾讯云后 MySQL 专项
5 项通过。回归测试覆盖 Tool/Codex Input、类型保留与脱敏、重试、租约过期重新领取。

实际 Runner 验证 Run：`0b90ee68-0ceb-46f5-a45c-59e34fa1ab0f`（COMPLETED）。
Shell 首次失败、重试成功后，NodeRun 的 Input 与 MySQL/API 一致，`attempt=2`，
`started_at=2026-10-05T09:37:49`、`finished_at=2026-10-05T09:37:57`（UTC）；首次
开始时间早于第二次 Task 开始时间。审批等待期间重启 API/Worker/Runner，Input、开始/
结束时间、attempt 均保留。审批通过测试 API 模拟，没有调用外部 Agent。

证据：`data/runner-trace-check/20261005T093743Z/report.json`、`run.json`、`events.json`。
