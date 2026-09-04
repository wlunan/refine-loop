# 接口文档（API Reference）

> 以 `backend/server.py`、`backend/routers/workbench.py` 和 `backend/routers/tasks.py` 的当前实现为准，更新于 2026-09-04。

服务默认监听 `http://127.0.0.1:8000`。启动后可访问 [OpenAPI 文档](http://127.0.0.1:8000/docs)；本文补充 SSE 事件及运行语义。

- 当前没有鉴权；CORS 对所有来源开放。仅适合本机或受控网络，不应直接暴露到公网。
- 前端生产构建产物存在时由同一 FastAPI 服务托管；未构建时访问 `/` 返回 404。
- API 分为工作台（`/api/*`）和长任务管理（`/api/tasks/*`）两组。

## 1. 工作台

### `GET /api/stream`

在后台线程执行文本模式的 Generator → Critic 迭代，并以 SSE 返回生成 token、每轮审查和最终结果。

| 查询参数 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|
| `task` | 是 | — | 去除首尾空白后的任务描述；为空时发送 `error` 后结束。 |
| `domain` | 否 | `general` | 传给 Agent 的领域标识；界面可选 `general`、`code`、`writing`、`design`。 |
| `max_rounds` | 否 | `5` | 最大迭代轮数，必须能转换为整数。 |
| `threshold` | 否 | `85` | 本次运行实例的 Critic 评分阈值；不会修改全局配置，多个工作台运行互不串扰。 |

### `GET /api/stream_files`

文件模式。Generator 在给定目录中调用文件工具和验证工具，Critic 审查工作区快照；每轮 Critic 反馈会拼入下一轮任务。

| 查询参数 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|
| `task` | 是 | — | 任务描述。 |
| `workspace` | 是 | — | 已存在的工作区目录；路由仅检查其是否为目录。 |
| `domain` | 否 | `code` | 传给编排器的领域标识。 |
| `max_rounds` | 否 | `3` | 最大迭代轮数。 |
| `threshold` | 否 | `85` | 本次运行实例的 Critic 评分阈值。 |
| `verification_profile` | 否 | `none` | 确定性验证：`python_pytest`、`python_lint`、`node_build` 或 `none`。配置必需验证后，只有验证通过才算本次运行成功。 |

文件 Agent 可调用 `list_directory`、`read_file`、`write_file`、`edit_file`、`delete_file`、`search_files`、`run_command`、`run_tests`、`run_lint` 和 `run_python`。工具调用上限为 20 步；命令在工作区中通过 shell 执行，使用前应由操作者确认工作区范围和任务内容。

### `GET /api/browse_dir`

供工作台文件夹选择器读取目录。

| 查询参数 | 必填 | 说明 |
|---|---:|---|
| `path` | 否 | 目录路径；省略时 Windows 返回可用盘符，其他系统从 `/` 开始。 |

响应格式：

```json
{
  "path": "E:\\projects",
  "parent": "E:\\",
  "exists": true,
  "dirs": ["demo", "service"]
}
```

不存在或不可读取的目录返回 `exists: false` 或空 `dirs`，而不是 HTTP 错误。

### `POST /api/stop?run_id=...`

请求停止工作台中正在运行的编排器。`run_id` 来自 SSE 的首个 `run_id` 事件。

```json
{"ok": true, "message": "已发送停止请求"}
```

停止是协作式的：编排器会在当前 token、工具步骤或当前阻塞模型调用结束后的检查点停止。SSE 客户端断开时也会调用同一停止逻辑。

## 2. 长任务管理（`/api/tasks`）

任务数据和每轮检查点默认持久化到进程当前工作目录的 `.task_store/`。创建任务不校验工作目录；首次启动时才会创建 `FileWorkspace` 并执行规划。

### `POST /api/tasks`

请求体：

```json
{
  "requirement": "为现有项目添加登录页",
  "workspace_dir": "E:\\projects\\demo",
  "domain": "code",
  "max_rounds": 3,
  "threshold": 85,
  "verification_profile": "python_pytest"
}
```

响应：

```json
{"task_id": "task_1234abcd", "title": "为现有项目添加登录页"}
```

`domain` 默认 `code`。任务创建时会把最大轮数、评分阈值和验证 profile 固化为 `run_config`；后续恢复不会使用其他任务的运行参数。

### `GET /api/tasks`

| 查询参数 | 默认值 | 说明 |
|---|---:|---|
| `status` | — | 可选：`pending`、`planning`、`running`、`paused`、`completed`、`failed`、`cancelled`。非法值返回 400。 |
| `limit` | `50` | 返回数量上限。 |

返回任务摘要数组：`id`、`title`、`status`、`progress_percent`、`subtask_count`、`completed_subtasks`、`created_at`、`error`。

### `GET /api/tasks/{task_id}`

返回完整任务信息，包括工作目录、领域、`run_config`、累计 token、时间戳、任务级错误以及计划中的子任务。子任务字段为 `id`、`title`、`description`、`status`、`dependencies`、`score`、`iterations`、`error`。任务不存在返回 404。

### 任务控制

| 方法 | 路径 | 当前行为 |
|---|---|---|
| `POST` | `/api/tasks/{task_id}/start` | 无计划时先用 LLM 规划，再在后台线程按依赖顺序执行子任务。 |
| `POST` | `/api/tasks/{task_id}/pause` | 向当前执行器请求停止，并把状态置为 `paused`。 |
| `POST` | `/api/tasks/{task_id}/resume` | 重新调用启动流程；不会从检查点恢复未完成子任务的上下文。 |
| `POST` | `/api/tasks/{task_id}/cancel` | 请求停止、状态置为 `cancelled` 并清理运行中资源。 |

这些控制接口的状态错误当前返回 400；其中 `start` 的规划失败也会以 400 返回。

### `GET /api/tasks/{task_id}/progress`

返回 `task_id`、`status`、`progress_percent`、`current_subtask`、`completed_subtasks`、`total_subtasks`、`total_tokens` 和 `message`。任务不存在返回 404。

### `GET /api/tasks/{task_id}/subtasks/{subtask_id}/rounds`

返回该子任务已持久化的检查点数组，每项包括 `round`、`draft`、`score`、`acceptable`、`issues`、`suggestions`、`summary`、`verification_summary`、`tokens_used`、`created_at`。任务不存在返回 404；读取存储异常返回 500。

### `GET /api/tasks/{task_id}/events`

长任务的 SSE 事件流。任务不存在返回 404；空闲超过 30 秒会发送 `: heartbeat` 注释帧。常见事件如下：

| 事件 | 关键字段 |
|---|---|
| `task_started` / `task_planning` / `task_planned` | `task_id`，规划完成时还有 `subtask_count`。 |
| `subtask_started` | `subtask_id`、`title`。 |
| `subtask_progress` | `subtask_id`、`round`、`score`、`draft_preview`。 |
| `verification_completed` | `subtask_id`、`round`、`profile`、`passed`、`results`。 |
| `file_operation` / `file_result` | `subtask_id`、`operation`/`path` 或 `result`、`round`。 |
| `subtask_completed` / `subtask_failed` | 子任务标识，完成时还有 `score`、`iterations`、`tokens_used`；失败时有 `error`。 |
| `task_completed` / `task_failed` / `task_cancelled` | `task_id`、`status` 或 `error`。 |

## 3. 工作台 SSE 协议

响应头为 `Content-Type: text/event-stream`，每帧格式为 `data: <JSON>\n\n`。文本和文件模式均会发送：

| `type` | 字段 | 说明 |
|---|---|---|
| `run_id` | `run_id` | 可传给 `/api/stop` 的运行标识。 |
| `status` | `message` | 开始或过程状态。 |
| `token` | `round`、`token` | 仅文本模式的流式生成增量。 |
| `critic` | `round`、`score`、`acceptable`、`issues`、`suggestions`、`summary` | 每轮审查结果。 |
| `tool` | `subtype`、`round`、`tool`、`arguments`、`result` | 仅文件模式的工具调用或结果；结果默认截断至 2,000 字符。 |
| `verification` | `round`、`profile`、`passed`、`results` | 仅文件模式；每轮受控验证的退出码、输出、超时和耗时证据。 |
| `done` | `final_output`、`iterations`、`converged`、`convergence_reason`、`score_trend`、`total_time`、`verification` | 运行结束结果；文件快照最多推送 20,000 字符。 |
| `error` | `message` | 请求检查或后台运行错误。 |
| `end` | — | 流结束。 |

## 4. 已知限制

- 工作台和长任务都把阈值、轮数和验证 profile 作为运行级配置；全局配置仅提供默认预算和阈值。
- 文件路径校验使用绝对路径和前缀判断，尚未解析符号链接/重解析点；不要把不受信任的链接放入工作区。
- 文件模式提供命令执行工具，`run_command` 使用 `shell=True`；本地工具不等于受隔离的代码执行沙箱。
- 自愈闭环 `SelfHealingOrchestrator` 已有 Python API 与 benchmark 调用，但未注册为 Web 路由或工作台专用模式。

## 来源

`backend/server.py`、`backend/routers/common.py`、`backend/routers/workbench.py`、`backend/routers/tasks.py`、`backend/src/manager/task_manager.py`、`backend/src/executor/task_executor.py`。
