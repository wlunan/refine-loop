# 架构与技术设计

> 本文档回答「**为什么这么设计、难点在哪、如何权衡**」，与 `README.md`（怎么用）互补。
> 目标读者：面试官、技术评审、后续接手者。

## 1. 一句话定位

把「单次 LLM 问答」工程化为「**可自我纠错、可收敛、可控成本、可流式交互**」的多 Agent 系统：
Generator（生成者）与 Critic（批判者）对抗式迭代，用「批判」驱动「改进」，直到满足收敛条件。
本质是把人工的「AI 输出 → 人肉审查 → 再喂提示词」循环，迁移为无人值守的自动闭环。

---

## 2. 总体架构

```
┌──────────────────────────────────────────────────────────┐
│  接入层                                                  │
│  examples/*.py (终端)        backend/server.py (FastAPI) │
│                              + SSE 流式                   │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│  编排层 Orchestrator（迭代循环 + 收敛判定 + 结果汇总）     │
│  · 命令式：src/orchestrator/orchestrator.py               │
│  · 图状态机（可选）：src/graph/workflow.py (LangGraph)     │
│  · 共享收敛纯函数：src/convergence.py                     │
└───────────────┬──────────────────────┬───────────────────┘
                │                      │
     ┌──────────▼─────────┐  ┌─────────▼─────────┐
     │  GeneratorAgent     │  │  CriticAgent      │
     │  生成 / 按反馈修改   │  │  审查 / 结构化打分  │
     └──────────┬─────────┘  └─────────┬─────────┘
                │                      │
     ┌──────────▼──────────────────────▼─────────────────┐
     │  Agent 基类 base.py（LLM 调用/流式/重试/token 统计） │
     └──────────────────────┬────────────────────────────┘
                            │
     ┌──────────────────────▼────────────────────────────┐
     │  数据契约 models/schemas.py                        │
     │  CritiqueResult / AgentState / IterationRecord     │
     └──────────────────────┬────────────────────────────┘
                            │
     ┌──────────────────────▼────────────────────────────┐
     │  Prompt 层 (prompts/) + 配置层 (config/) + 工具层    │
     │  四领域提示词        环境变量/参数     文件沙箱        │
     └────────────────────────────────────────────────────┘
```

**分层要点**：编排层不直接依赖具体模型，通过依赖注入拿到 Generator/Critic；展示层（终端打印、SSE 推送）通过回调与核心流程解耦。

---

## 3. 核心设计决策

### 3.1 为什么是「生成-批判」对抗式迭代，而非单次调用

- **背景**：单次 LLM 输出质量不可控，好坏全凭运气；且「改哪里、为什么改」缺乏依据。
- **决策**：让同一（或两个）模型分别扮演「作者」与「评审」两个对立角色，用结构化的批判驱动修改。
- **权衡**：代价是调用次数与 token 成倍增加 → 因此「收敛机制」和「成本控制」成为这个范式的**必选项**，而非可选项。这正是本项目区别于「玩具 demo」的关键：把「什么时候停」显式化了。

### 3.2 收敛机制 = 成本控制

三种终止条件，满足任一即停（统一收敛顺序：质量达标 → 无新反馈 → 最大轮数）：

1. **质量达标**：`acceptable=True` 且 `score >= 阈值`（默认 85）→ 成功收敛
2. **无新反馈**：连续 N 轮（默认 2）`issues` 完全相同 → 成功收敛（避免空转烧钱）
3. **达到最大轮数**：硬上限兜底 → 未收敛，返回**历史最优版本**

关键细节：**未收敛时返回「历史评分最高的版本」而非最后一版**（`AgentState.get_best_draft()`），因为 LLM 迭代不是单调上升的，最后一轮可能反而更差。这是踩过坑才会有的设计。

实现上把收敛判定抽成纯函数 `convergence.py::evaluate_convergence`，供命令式 `Orchestrator` 与 LangGraph 版共用，**避免两份实现逻辑漂移**。

### 3.3 模型分级：Generator 强模型 + Critic 弱模型

- **决策**：Generator 负责创作（对能力要求高）用强模型；Critic 负责挑刺（对能力要求低）用弱模型。
- **收益**：显著降低迭代总成本。真实场景下（如小米 mimo-pro vs mimo）弱模型挑刺足够，创作才需要强模型。
- **代价**：弱模型输出格式不稳定 → 引出 3.4 的防御性解析。

### 3.4 Critic 结构化输出的防御性解析（三级降级 + 类型容错）

这是全项目工程细节最丰富的一环。LLM（尤其弱模型）输出经常不规范：字段缺失、类型错误、夹带解释文字。

解析链路：

```
LLM 原始回复
  ├─ ① parser.parse() 直接按 Pydantic 解析         → 成功则返回
  ├─ ② _extract_json() 提取 JSON（```json 块 / 首个{到末个}）
  │      → json.loads → _coerce_critique() 类型容错   → 成功则返回
  └─ ③ 降级兜底：score=50, acceptable=False，带回原始片段
```

两个关键工程点：
- **把 `get_format_instructions()` 的 JSON Schema 注入 Prompt**：否则弱模型根本不知道字段结构（「解析降级」的根因）。
- **`_coerce_critique` 类型容错**：`"85"` 字符串转 int、字符串转列表、字符串布尔转 bool，并处理 `acceptable` 与 `score` 的一致性冲突（`acceptable=True` 时 `score` 不得低于 60，否则强制兜底）。

**迁移价值**：任何「让 LLM 输出结构化数据」的场景都要做这层防御，这是从「demo」到「系统」的分水岭。

### 3.5 依赖注入与可测试性

`BaseAgent`、`Orchestrator` 均支持注入 `llm` / `generator` / `critic`。这使测试能用 **Mock LLM 完全离线运行**（`tests/test_orchestrator.py`），不消耗 token、不依赖真实 API，同时覆盖三种收敛条件的验证。

**价值**：这是「LLM 应用如何写单测」的标准答案——核心逻辑用 Mock 固定输入输出，而非依赖真实模型。

### 3.6 流式输出与 SSE 架构

- `call_llm`（阻塞一次性）与 `call_llm_stream`（逐块 yield）双通道；传入 `on_generator_token` 回调即自动切换流式。
- Web 端：后台线程跑 Orchestrator，通过 `loop.call_soon_threadsafe` 安全地把事件投递到 FastAPI 主事件循环，再由 SSE 推送到浏览器实现打字机效果。
- 支持线程安全的 `stop()`（`threading.Event`），在「当前 token 生成后 / 下一轮开始前」尽快中断长任务。

### 3.7 文件安全沙箱

`FileWorkspace` 把 Agent 的所有文件操作限制在指定工作目录内，文件模式下 Generator 在沙箱内创建/修改真实文件。

### 3.8 可验证工具集 + 代码自愈闭环（核心差异化）

这是本项目区别于「纯文本挑刺」多 Agent 审查的关键：批评的依据从「我觉得这行可能有 bug」升级为「pytest 第 3 条挂了、报错如下」的**事实**。

- **可验证工具集**（`src/tools/verification.py`）：`run_command` / `run_tests` / `run_lint` / `run_python`，通过 `CommandRunner` 在工作区沙箱内执行真实命令，带超时控制与输出截断。文件模式的 Generator 可直接调用这些工具（写完代码后自己跑测试验证）。
- **代码自愈闭环**（`src/orchestrator/self_healing.py`）：`SelfHealingOrchestrator` 循环「Generator 生成/修复 → 运行验证命令（默认 pytest）→ 失败则把失败日志注入下一轮任务 → 修复 → 复跑」，直到验证通过或达到最大修复轮数。

**为什么有效**：验证是确定性的（跑测试），修复目标客观可衡量（让验证通过），不依赖 Critic 的主观评分。这为「审查 Agent 替代人」补上了最关键的一块——可验证性。

---

## 4. 关键数据流

```
用户 task
  → Orchestrator.run()
    → ① Generator.generate()         产出 draft
    → ② Critic.critique(task, draft) 产出 CritiqueResult
    → ③ 记录 IterationRecord → state.history
    → ④ 回调 on_round_complete / on_iteration_complete
    → ⑤ evaluate_convergence() 判断
         ├─ 收敛 → break
         └─ 否则 → 下一轮（feedback 注入 Generator）
  → _build_result()：收敛取当前 draft；未收敛取 get_best_draft()
```

---

## 5. 工程权衡与已知方向

| 已做 | 权衡 / 局限 | 规划方向 |
|------|-----------|---------|
| 模型分级控制成本 | Critic 弱模型易「解析降级」 | Critic 分级（弱初筛 + 强终审） |
| 结构化输出三级降级 | 本质是「祈祷模型输出干净 JSON」 | 改用 JSON mode / function calling 根治 |
| 收敛三条件 | 纯文本审查，无事实依据 | 已补可验证性（见下行） |
| 可验证工具集 + 代码自愈闭环 | 验证命令需在沙箱内安全执行（超时/截断已控） | 审查标准外置化（YAML/JSON 可配置评审规范） |
| Mock LLM 离线测试 | 只覆盖收敛逻辑 | 补评估框架，量化「迭代前 vs 后」质量提升 |
| 单 Critic | 维度单一 | 多 Critic 并行，取问题并集 |
| 每轮只看上一版 | 无全局记忆，可能重复犯错 | Generator 全局记忆，注入历史否定点 |

---

## 附：文件级导航

- `src/convergence.py` — 共享收敛判定纯函数
- `src/orchestrator/orchestrator.py` — 迭代主循环（命令式）
- `src/orchestrator/self_healing.py` — 代码自愈闭环
- `src/tools/verification.py` — 可验证工具集（真实执行结果）
- `src/graph/workflow.py` — LangGraph 图状态机（对比实现）
- `src/agents/critic.py` — 三级降级解析（工程精华）
- `src/agents/generator.py` — 首轮生成 + 反馈迭代 + 产出提取
- `src/models/schemas.py` — 数据契约
- `backend/server.py` + `backend/routers/` — FastAPI + SSE
