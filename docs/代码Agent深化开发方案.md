# 可验证代码 Agent 工作台：深化开发方案

> 状态：P0、P1 与 P2 核心链路已实现；P3 已具备版本化 benchmark 原始结果格式，尚待执行真实对照实验并提交结果。
> 目标：把现有 Generator-Critic 项目收敛为一个可写入秋招简历的代码 Agent 项目，而不是继续扩展文档、方案或多 Critic 分支。
> 依据：2026-09-04 的 `backend/`、`frontend/`、`benchmark/` 实现。

## 1. 项目定位与成功标准

### 1.1 对外定位

**Verifiable Code Agent Workbench**：面向本地 Git 代码仓库的可验证开发工作台。用户提交需求后，系统拆解任务、在隔离工作区修改代码、运行受控验证，并将失败证据回注后续修复；用户能够在应用中审阅变更、确认应用并查看完整运行证据。

主叙事应是“**验证驱动的代码修复闭环**”，而不是“多 Agent 自动写代码”。

### 1.2 完成定义

一项代码任务只有同时满足下列条件才能被标记为 `completed`：

1. 所有必需验证项通过，例如测试、构建或 lint；
2. 变更已由用户确认应用到目标工作区；
3. 运行未被取消，且没有未处理的工具或持久化错误。

Critic 评分、建议和摘要保留为质量信号与修复上下文，**不再单独决定代码任务成功**。

### 1.3 本期非目标

- 不新增文档 Agent、方案 Agent、RAG、多人协作或多 Critic 编排。
- 不将本地工具包装为多租户远程执行平台；本期仍是可信用户的本地开发工具。
- 不宣称通用自动回滚。首期只提供“隔离修改 + diff 审阅 + 明确应用”的可控路径。
- 不在无 benchmark 原始结果前写任何成功率提升结论。

## 2. 当前基线与缺口

| 已有实现 | 可复用价值 | 当前缺口 |
|---|---|---|
| `Orchestrator.run_with_files()` | Generator 可操作文件，Critic 可审查快照 | 停止条件仍由 Critic 收敛决定，验证结果不参与任务成功判定。 |
| `SelfHealingOrchestrator` | 已实现“失败测试日志 → 下一轮修复”的闭环 | 独立于 Web 和长任务主链路。 |
| `CommandRunner` 与文件工具 | 已有测试、lint、脚本和文件操作能力 | 命令使用 `shell=True`，文件变更没有确认，路径校验未解析链接边界。 |
| `TaskManager` / `TaskExecutor` / `StateStore` | 已有任务、子任务、SSE 和 JSON 检查点 | 恢复会重新启动执行器，未恢复运行配置、上下文和中断轮次。 |
| Vue 工作台与任务页 | 已有 SSE、评分、工具事件、任务状态展示 | 没有 diff、验证证据、确认状态或可恢复运行详情。 |
| `benchmark/` | 有 4 个带 ground-truth pytest 的任务和报告模板 | 没有版本化原始运行结果，不能支撑效果指标。 |

## 3. 目标主链路

```text
创建代码任务
  → 选择受控验证配置
  → 在隔离工作区规划、读取和修改
  → 生成变更集与 diff
  → 用户确认应用变更
  → 执行测试 / 构建 / lint
  → 失败：失败证据 + Critic 意见回注修复
  → 通过：持久化证据、生成摘要、完成任务
```

### 3.1 两类运行状态

将“正在生成”与“是否可交付”分开：

| 状态 | 含义 | 主要触发者 |
|---|---|---|
| `planning` | 正在拆解需求或分析工作区 | `TaskPlanner` |
| `running` | Agent 正在读取、修改或准备验证 | 编排器 |
| `awaiting_approval` | 已产生变更集，等待用户确认应用 | 前端确认页 |
| `verifying` | 正在执行必需验证项 | 验证执行器 |
| `repairing` | 验证失败，携带证据进入下一轮修复 | 编排器 |
| `completed` | 已确认应用且所有必需验证通过 | 任务管理器 |
| `failed` / `cancelled` | 不可恢复错误、轮次耗尽或用户停止 | 任务管理器 |

`paused` 可以保留为用户控制状态；恢复时必须能恢复到上述某个可解释状态，而不是笼统地重新开始。

## 4. 设计决策

### D1：运行配置必须是实例级、可持久化的

新增 `RunConfig`（建议位置：`backend/src/models/run.py`），由 API 请求构造后传入编排器和任务执行器。至少包含：

```python
@dataclass(frozen=True)
class RunConfig:
    max_rounds: int
    score_threshold: int
    round_token_budget: int
    total_token_budget: int
    verification_profile: str
    verification_steps: list[VerificationStep]
```

`backend/config/settings.py` 只保存默认值；不得再由 `routers/workbench.py` 写入全局 `convergence_score_threshold`。每次运行把实际配置写入任务和检查点，支持复现和恢复。

### D2：验证结果进入统一反馈和完成判定

新增以下领域契约，替代“只在独立自愈循环中持有 `CommandResult`”的状态：

```python
class VerificationStep(BaseModel):
    id: str
    label: str
    command: list[str]
    required: bool = True
    timeout_seconds: int = 120

class VerificationResult(BaseModel):
    step_id: str
    passed: bool
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float

class VerificationSummary(BaseModel):
    passed: bool
    results: list[VerificationResult]
```

`CommandRunner` 继续负责底层进程执行，但由 `CodeVerifier` 统一调度验证步骤。`TaskExecutor` 每轮保存验证摘要；若任一必需步骤失败，编排器把截断后的失败证据与 Critic 建议共同注入下一轮 Generator。

**完成规则：** 验证通过优先于 Critic 分数；Critic 可指出后续质量问题，但不应令已通过的代码任务无限迭代。

### D3：默认运行在隔离 Git worktree，确认后才应用

为保证“先看 diff、后写入”真实成立，主模式限定为 Git 工作区：

1. 为每个运行创建临时 Git worktree；Agent 只在该 worktree 读写和验证。
2. 收集 `git diff` 作为 `ChangeSet`，按文件展示新增、修改、删除和 patch。
3. 用户在前端选择“应用”后，系统把已确认 patch 应用到原始工作区；选择“丢弃”则清理临时 worktree。
4. 非 Git 目录仅保留为实验模式，不默认提供自动写入。

这比“先改真实目录，再让用户确认”更符合确认语义，也为演示提供清晰的 diff 证据。

### D4：命令执行使用验证配置，而非任意 shell 字符串

首期只支持明确的验证配置，例如：

| Profile | 受控步骤 |
|---|---|
| `python_pytest` | `python -m pytest <path> -q` |
| `python_lint` | `python -m ruff check <path>`，缺失时回退 flake8 |
| `node_build` | `npm run build` |

- 新的内部执行入口接收 `list[str]`，使用 `shell=False`。
- 自定义命令、安装依赖、删除文件等能力不进入首期自动验证；若后续开放，必须显式确认并记录。
- 运行前验证工作区路径，使用真实路径解析并拒绝越界的符号链接/Windows 重解析点。

### D5：检查点保存“可恢复的运行状态”，而不仅是草稿

扩展现有 `Checkpoint` 或新增 `RunCheckpoint`，持久化：运行配置、工作树标识、当前子任务、已完成子任务结果、当前轮次、Critic 结果、验证摘要、变更集状态、token 和停止原因。

恢复规则：

- `awaiting_approval`：重新展示同一 `ChangeSet`，不重新生成。
- `repairing` / `verifying`：从上一个已持久化轮次恢复，重新执行当前步骤；验证步骤应可重复执行。
- 运行配置和模型信息固定为创建时快照；用户若要改变参数，应新建运行，而非篡改旧记录。

## 5. 前后端改动范围

| 层 | 主要改动 | 涉及现有文件 |
|---|---|---|
| 模型 | 增加 `RunConfig`、验证、变更集与恢复契约 | `backend/src/models/`、`task.py` |
| 编排 | 在文件模式内统一执行“生成 → 验证 → 回注”；复用或逐步替代独立自愈循环 | `backend/src/orchestrator/`、`executor/task_executor.py` |
| 工具 | 真实路径校验、Git worktree、无 shell 的验证执行 | `backend/src/tools/filesystem.py`、`verification.py` |
| 状态 | 保存运行快照、变更集和验证记录 | `backend/src/store/state_store.py`、`manager/task_manager.py` |
| API | 传入 `RunConfig`，提供变更集查询、批准/拒绝、恢复与事件流 | `backend/routers/tasks.py`、`workbench.py` |
| 前端 | 创建任务时选择 profile；运行详情展示 diff、验证、批准与恢复 | `frontend/src/views/Workbench.vue`、`TaskDetail.vue`、`api/task.ts`、`stores/task.ts` |

建议不再为文本工作台和长任务维护两套“代码任务”执行逻辑：文件模式应复用同一个任务运行入口；文本模式可保留为轻量文案/方案实验，但不作为本期主 Demo。

## 6. 分阶段实施与验收

### P0：运行配置与确定性验证主链路

**目标：** 用测试/构建结果而非 Critic 分数决定代码任务是否成功。

1. 引入 `RunConfig`、`VerificationStep`、`VerificationResult`。
2. 消除工作台对全局阈值单例的写入。
3. 将 `CommandRunner` 包装为 `CodeVerifier`，并接入 `Orchestrator.run_with_files()` 与 `TaskExecutor`。
4. 把验证事件、结果和失败证据持久化并通过 SSE 发送。
5. 保留 `SelfHealingOrchestrator` 作为兼容包装或 benchmark 入口，避免双份修复逻辑继续演化。

**验收：** 构造一个失败 pytest 场景，页面可见失败退出码和摘要；下一轮任务包含失败证据；所有必需验证通过后任务才进入 `completed`。

### P1：受控变更与路径边界

**目标：** 让 Agent 修改可信、可审阅、可拒绝。

1. 实现 Git worktree 生命周期和 `ChangeSet`。
2. 页面展示按文件归类的 diff，并支持应用/丢弃。
3. 验证命令切换为 `shell=False` 的参数列表和内置 profile。
4. 以真实路径解析加固 `FileWorkspace`，覆盖链接逃逸测试。

**验收：** Agent 在临时 worktree 中修改，原始工作区在用户批准前保持不变；拒绝后原始工作区无文件变更；越界链接和未授权命令被拒绝并记录原因。

### P2：可恢复任务与证据时间线

**目标：** 让长任务可解释、可暂停、可恢复。

1. 持久化运行级快照、上下文、验证摘要与变更集状态。
2. 明确 `awaiting_approval`、`verifying`、`repairing` 状态和 SSE 事件。
3. 在任务详情页按时间线展示计划、修改、验证、修复、停止和恢复。
4. 实现从 `awaiting_approval` 与安全检查点恢复的流程。

**验收：** 刷新页面或重启服务后，任务仍能展示未应用 diff 和最近验证证据；恢复不会覆盖当初的运行配置或重复已确认变更。

### P3：评测、Demo 与交付

**目标：** 形成可复现的项目证据和秋招演示材料。

1. 将 benchmark 扩展到 10–15 个带固定测试的代码任务，覆盖 bug 修复、小功能、构建失败和边界失败。
2. 固定模型、温度、提示词版本、预算、最大轮数与运行日期；保存每题原始日志和汇总报告。
3. 对比单次生成、Generator + Critic、验证驱动三种策略；报告同时展示通过率、轮数、耗时和 token。
4. 制作 60–90 秒固定 Demo：失败测试 → 隔离修改 → diff 确认 → 失败日志回注 → 测试通过。
5. 增加 CI：后端测试、前端构建、文档链接检查。

**验收：** 任一简历指标都能链接到版本化 benchmark 原始结果；新读者可按 README 复现固定 Demo。

## 7. 测试策略

| 范围 | 必测场景 |
|---|---|
| 编排 | 验证通过、验证失败后修复、最大轮数、用户取消、Critic 低分但验证通过。 |
| 路径与工具 | `..`、绝对路径、符号链接/重解析点、受保护目录、未授权命令、超时。 |
| 变更确认 | worktree 生成 diff、批准应用、拒绝丢弃、重复批准、应用冲突。 |
| 持久化 | 运行配置快照、`awaiting_approval` 恢复、验证中断后的恢复、损坏检查点。 |
| API/SSE | 状态转换、事件顺序、断连、错误响应和任务不存在。 |
| 前端 | 创建代码任务、diff 审阅、批准/拒绝、验证失败与成功、恢复入口。 |

现有 Mock LLM 测试应继续承担 Agent 控制流验证；验证和 worktree 测试使用临时 Git 仓库，不依赖真实 API Key。

## 8. 交付口径

完成 P0 后可表述：

> 实现验证驱动的代码 Agent 闭环，将 pytest/build 等确定性验证结果接入任务状态与 SSE 事件，并将失败证据回注后续修复。

完成 P1 后可表述：

> 设计 Git worktree 隔离与 Human-in-the-loop 变更确认机制，支持 diff 审阅、受控验证命令与工作区边界校验。

完成 P3 且产出原始数据后，才可补充具体 benchmark 指标。

## 9. 评审清单

- 是否接受“面向本地 Git 工作区”作为主产品边界？
- 是否接受“验证通过 + 用户应用变更”作为代码任务完成标准？
- 是否优先实现 P0，再做 worktree/diff，而不同时大规模重构前端？
- 验证 profile 是否先只支持 Python pytest、Python lint、Node build？
- 是否将非 Git 目录明确标注为实验模式，而非自动写入目标？

## 来源

`backend/routers/workbench.py`、`backend/routers/tasks.py`、`backend/src/orchestrator/orchestrator.py`、`backend/src/orchestrator/self_healing.py`、`backend/src/executor/task_executor.py`、`backend/src/manager/task_manager.py`、`backend/src/tools/filesystem.py`、`backend/src/tools/verification.py`、`backend/src/store/state_store.py`、`frontend/src/views/Workbench.vue`、`frontend/src/views/TaskDetail.vue`、`benchmark/`。
