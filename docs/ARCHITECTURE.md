# 架构与技术设计

> 本文记录当前代码已经具备的结构与边界，不把路线图当成既有能力。更新于 2026-09-04。

## 1. 定位

Generator-Critic 是一个本地运行的 LLM 迭代工作台：Generator 产出或修改内容，Critic 输出结构化审查，再把反馈用于下一轮改进。项目同时提供文本迭代、文件工作区迭代、可持久化的长任务，以及独立的代码自愈和 benchmark 能力。

## 2. 运行结构

```text
Vue 3 工作台 / 任务管理页
        │ HTTP + SSE
        ▼
FastAPI（backend/server.py）
  ├─ workbench router：文本、文件、目录选择、停止
  └─ tasks router：任务控制、进度、事件流
        │
        ├─ Orchestrator：Generator → Critic → 收敛
        ├─ TaskManager：规划 → 依赖顺序执行子任务 → JSON 持久化
        └─ SelfHealingOrchestrator：生成/修复 → 验证命令 → 失败日志回注
                │
                ▼
    GeneratorAgent / CriticAgent / ToolAgent
      ├─ LLM 与 Prompt
      ├─ FileWorkspace 文件工具
      └─ CommandRunner 验证工具
```

前端源码位于 `frontend/`，生产构建输出由 Vite 配置到 `backend/static/dist`，随后由 FastAPI 在同一端口托管。开发时 Vite 使用 5173 端口并代理 `/api` 到后端。

## 3. 核心模块

| 模块 | 责任 | 关键实现 |
|---|---|---|
| Agent | 统一模型调用、重试、流式 token 与 token 累计 | `backend/src/agents/base.py`、`backend/src/agents/generator.py`、`backend/src/agents/critic.py` |
| 编排器 | 管理文本/文件模式迭代、回调、停止、token 预算和结果汇总 | `backend/src/orchestrator/orchestrator.py` |
| 收敛判定 | 供命令式编排器与 LangGraph 工作流复用的纯函数 | `backend/src/convergence.py` |
| 文件工作区 | 文件读写、精准编辑、删除、搜索和工作区快照 | `backend/src/tools/filesystem.py` |
| 验证工具 | 在工作区执行测试、lint、Python 脚本和一般命令 | `backend/src/tools/verification.py` |
| 长任务 | LLM 规划子任务，按依赖顺序串行执行，写入检查点 | `backend/src/planner/`、`backend/src/manager/`、`backend/src/executor/`、`backend/src/store/` |
| Web | SSE 适配、运行中断、目录浏览、SPA 托管 | `routers/`、`server.py` |

## 4. 两条主要数据流

### 文本模式

1. `/api/stream` 创建 `Orchestrator`，在后台线程运行。
2. Generator 流式输出 token，路由经线程安全队列推送 SSE。
3. Critic 为完整草稿生成 `CritiqueResult`：评分、问题、建议、摘要。
4. 编排器记录 `IterationRecord`，执行收敛和预算检查。
5. `done` 事件返回最终文本、评分趋势、停止原因和耗时。

### 文件模式与长任务

1. 文件模式的 Generator 通过 `ToolAgent` 使用文件和验证工具，最大 20 个工具步骤。
2. `FileWorkspace.snapshot()` 将最多 50 个文本文件组成快照，交给 Critic 审查。若任务配置了必需验证，随后由 `CodeVerifier` 执行 pytest/lint/build，失败证据与 Critic 反馈共同追加到下一轮任务。
3. 文件模式配置必需验证时，验证通过而非 Critic 分数决定收敛；未配置验证时保留原有 Critic 收敛策略。
4. 长任务从 `TaskManager.start_task()` 开始：无计划时先用 `TaskPlanner` 生成最多 10 个子任务，再按已完成依赖顺序串行执行，并把每轮验证摘要写入检查点。
4. `TaskExecutor` 每轮写入 `Checkpoint`，`StateStore` 将任务和检查点保存到 `.task_store/`，任务事件经 `/api/tasks/{task_id}/events` 推送。

## 5. 收敛与预算

`evaluate_convergence()` 按以下顺序停止：

1. `acceptable=True` 且 `score >= score_threshold`：成功收敛。
2. 连续 `no_progress_rounds` 轮的 `issues` 集合完全相同：成功收敛，避免空转。
3. 达到 `max_rounds`：停止但标记为未收敛。

文本模式还在轮次开始前检查总 token 预算，并在每轮后检查单轮预算。未收敛的文本模式返回评分最高的历史草稿；文件模式的最终输出是结束时的工作区快照。用户停止也会中断后续步骤，但不能取消已经进入的阻塞模型调用。

## 6. 结构化审查与工具调用

Critic 使用 Pydantic 模型 `CritiqueResult` 表示审查结论，并对模型不稳定输出做分层处理：直接解析、提取 JSON 后做类型容错、最终降级为不可接受的结果。`acceptable=True` 且评分低于 60 会被模型校验拒绝。

文件 Agent 的工具调用采用两级策略：优先调用模型原生 Function Calling；若模型不支持，则降级到 JSON 文本命令协议。工具执行结果会回填对话，使 Agent 能读取文件、修改文件、执行命令后继续决策。

## 7. 自愈与评估

`SelfHealingOrchestrator` 是独立的代码自愈循环：

```text
生成或修复文件 → 执行验证命令（默认 pytest）
       │ 失败
       └─ 将退出码、stdout、stderr 回注下一轮任务
```

它已被 `examples/self_healing_example.py` 和 `benchmark/` 调用。benchmark 提供 4 个带 ground-truth pytest 的小型 Python 任务，对比单次生成和自愈循环，并生成 Markdown 报告；仓库未提交任何正式运行结果，因此文档不声明效果指标。

## 8. 安全边界与已知限制

- FastAPI 未接入鉴权，且 CORS 为 `*`；服务器默认仅绑定 `127.0.0.1`。
- `FileWorkspace` 防止 `..` 和绝对路径的字面量逃逸，但未解析符号链接/Windows 重解析点；它不是强隔离沙箱。
- 文件模式允许 `run_command`，其底层使用 `shell=True`。仅应对可信任务、可信本地工作区使用。
- `write_file`、`edit_file` 可以覆盖工作区中未列为受保护的文件；没有变更预览、确认或回滚 API。
- 工作台请求把 `threshold` 写入全局配置单例，多个并发运行可能串扰。`max_rounds` 是编排器实例字段，不受该问题影响。
- `TaskManager.resume_task()` 重新启动执行流程，未从检查点恢复执行上下文；检查点当前主要用于展示每轮记录。

## 9. 代码导航

| 想了解的问题 | 首选文件 |
|---|---|
| 文本或文件迭代如何运行 | `backend/src/orchestrator/orchestrator.py` |
| 何时停止、何时算收敛 | `backend/src/convergence.py` |
| Agent 怎样操作文件和命令 | `backend/src/agents/generator.py`、`backend/src/agents/tool_agent.py` |
| 文件/命令边界 | `backend/src/tools/filesystem.py`、`backend/src/tools/verification.py` |
| 长任务规划、执行和持久化 | `backend/src/manager/task_manager.py`、`backend/src/executor/task_executor.py`、`backend/src/store/state_store.py` |
| HTTP/SSE 协议 | `backend/routers/workbench.py`、`backend/routers/tasks.py`、[API.md](./API.md) |
| 前端入口与页面 | `frontend/src/router/index.ts`、`frontend/src/views/` |

相关设计决策保留在 [ADR](./adr/) 中；功能与工程演进见 [功能开发计划](./功能开发计划.md) 和 [开发计划](./开发计划.md)。
