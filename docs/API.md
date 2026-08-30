# 接口文档（API Reference）

> 后端为 FastAPI 服务（默认端口 8000），自动生成的 OpenAPI 文档见 http://127.0.0.1:8000/docs。
> 本文档补充 **SSE 流式接口的事件协议** 与业务语义——这部分在 Swagger 里展示不友好。

- 基础地址：`http://127.0.0.1:8000`
- 认证：无（本地/内网使用，未接入鉴权）
- 接口分两组：**工作台**（`/api/*`）与 **任务管理**（`/api/tasks/*`）

---

## 1. 工作台接口

### 1.1 `GET /api/stream` — 文本模式 SSE 流式迭代

让 Generator/Critic 在后台线程跑文本迭代，通过 SSE 实时推送过程。

| 查询参数 | 必填 | 说明 |
|---------|------|------|
| `task` | ✅ | 任务描述 |
| `domain` | | 领域：`general`/`code`/`writing`/`design`，默认 `general` |
| `max_rounds` | | 最大迭代轮数，默认 `5` |
| `threshold` | | 收敛评分阈值，默认 `85` |

**SSE 事件类型（`data: {"type": ...}`）**

| type | 说明 | 关键字段 |
|------|------|---------|
| `run_id` | 返回本次运行 ID（用于 `/api/stop`） | `run_id` |
| `status` | 状态提示 | `message` |
| `token` | Generator 流式生成的字块 | `round`, `token` |
| `critic` | 每轮 Critic 审查结果 | `round`, `score`, `acceptable`, `issues`, `suggestions`, `summary` |
| `done` | 迭代结束 | `final_output`, `iterations`, `converged`, `convergence_reason`, `score_trend`, `total_time` |
| `error` | 出错 | `message` |
| `end` | 流结束（连接关闭） | — |

### 1.2 `GET /api/stream_files` — 文件模式 SSE 流式迭代

Generator 在指定工作区目录内操作真实文件，Critic 审查文件快照。

| 查询参数 | 必填 | 说明 |
|---------|------|------|
| `task` | ✅ | 任务描述 |
| `workspace` | ✅ | 工作区目录绝对路径 |
| `domain` | | 领域，默认 `code` |
| `max_rounds` | | 默认 `3` |
| `threshold` | | 默认 `85` |

**SSE 事件**：除 1.1 所有事件外，另有：

| type | 说明 | 关键字段 |
|------|------|---------|
| `tool` | 文件/验证工具调用过程 | `subtype`（`tool_call`/`tool_result`）, `round`, `tool`, `arguments`, `result` |

### 1.3 `GET /api/browse_dir` — 目录浏览

供前端文件夹选择器使用。

| 查询参数 | 说明 |
|---------|------|
| `path` | 目录绝对路径；为空时返回盘符列表（Windows）或根目录 |

**响应**：`{ "path", "parent", "exists", "dirs": [...] }`

### 1.4 `POST /api/stop` — 停止运行中的迭代

| 查询参数 | 说明 |
|---------|------|
| `run_id` | 由 `/api/stream` 或 `/api/stream_files` 返回的运行 ID |

**响应**：`{ "ok": true/false, "message": "..." }`

---

## 2. 任务管理接口（`/api/tasks`）

长时间运行任务的全生命周期管理。

### 2.1 `POST /api/tasks` — 创建任务

**请求体（JSON）**：

```json
{
  "requirement": "需求描述",
  "workspace_dir": "/absolute/path",
  "domain": "code"
}
```

**响应**：`{ "task_id", "title" }`

### 2.2 `GET /api/tasks` — 任务列表

| 查询参数 | 说明 |
|---------|------|
| `status` | 状态筛选：`pending`/`running`/`paused`/`completed`/`failed`/`cancelled` |
| `limit` | 返回条数，默认 `50` |

**响应**：任务项数组，含 `id`, `title`, `status`, `progress_percent`, `subtask_count`, `completed_subtasks`, `created_at`, `error`。

### 2.3 `GET /api/tasks/{task_id}` — 任务详情

**响应**：任务完整信息，含 `subtasks`（每个子任务的 `id`/`title`/`status`/`dependencies`/`score`/`iterations`/`error`）。

### 2.4 任务控制接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/tasks/{task_id}/start` | POST | 启动任务 |
| `/api/tasks/{task_id}/pause` | POST | 暂停任务 |
| `/api/tasks/{task_id}/resume` | POST | 恢复任务 |
| `/api/tasks/{task_id}/cancel` | POST | 取消任务 |

均为简单响应 `{ "message": "..." }`；非法状态返回 400。

### 2.5 `GET /api/tasks/{task_id}/progress` — 任务进度

**响应**：进度对象（含 `progress_percent`, `message` 等）。

### 2.6 `GET /api/tasks/{task_id}/subtasks/{subtask_id}/rounds` — 子任务迭代记录

返回该子任务每一轮迭代的详细记录（生成草稿 + Critic 审查），数据来源为执行时保存的 Checkpoint。

**响应**：数组，每项含 `round`, `draft`, `score`, `acceptable`, `issues`, `suggestions`, `summary`, `tokens_used`, `created_at`。

### 2.7 `GET /api/tasks/{task_id}/events` — 任务实时事件（SSE）

实时推送任务执行进度。事件 type 含 `task_started`、`subtask_*`、`task_completed`、`task_failed`、`task_cancelled` 等；连接空闲每 30s 发送心跳 `: heartbeat`。

---

## 3. SSE 通用约定

- `Content-Type: text/event-stream`
- 每帧格式：`data: <json>\n\n`
- 客户端断开连接时，后端自动中断对应后台迭代（`orchestrator.stop()`）
- 工具结果等长文本默认截断 2000 字符，避免撑爆流

## 4. 错误处理

- 参数校验失败：SSE 接口返回 `error` 事件；REST 接口返回 400/404 + `detail`
- 任务不存在：404
- 状态非法（如启动已启动的任务）：400
