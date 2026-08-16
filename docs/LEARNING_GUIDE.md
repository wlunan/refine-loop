# Generator-Critic Agent 学习路径指南

> 本文档面向想系统性理解这个项目「核心价值」的读者，按**由浅入深**的方式组织。
>
> 难度标注说明：
> - 🟢 **入门理解**：先建立整体认知，知道"是什么、为什么"
> - 🟡 **进阶掌握**：理解具体实现逻辑，能看懂并复述关键代码
> - 🔴 **深入钻研**：吃透工程细节，能自己改、能迁移到别的项目

---

## 目录

1. [项目定位与核心问题](#一项目定位与核心问题)
2. [技术架构概览](#二技术架构概览)
3. [关键功能模块](#三关键功能模块)
4. [核心业务流程](#四核心业务流程)
5. [建议阅读顺序（文件级路线图）](#五建议阅读顺序文件级路线图)
6. [重点难点提示](#六重点难点提示)
7. [动手练习建议](#七动手练习建议)

---

## 一、项目定位与核心问题

### 1.1 一句话定位 🟢

> 这是一个把「**单次 LLM 问答**」升级为「**可自我迭代的多 Agent 协作系统**」的最小可运行范例。

它通过两个角色互相对弈——**Generator（生成者）负责产出、Critic（批判者）负责挑刺**——让模型在"生成 → 审查 → 按反馈修改 → 再审查"的循环中，持续逼近更高质量的产出。

### 1.2 它解决的核心问题 🟢

| 问题 | 传统做法（单次调用） | 本项目做法 |
|------|---------------------|-----------|
| **质量不可控** | 一次生成，好不好全凭运气 | Critic 打分挑刺，Generator 逐条修改，循环迭代 |
| **输出格式不稳定** | LLM 自由发挥，难解析 | 结构化输出（JSON）+ 三级降级容错解析 |
| **成本不可控** | 无法预估调用次数 | 收敛机制 + 模型分级 + 轮数上限，三重成本控制 |

### 1.3 核心价值（学习重点）🟡

这个项目最有价值的不是"代码"，而是三个可以**直接迁移到任何 LLM 应用**的思想：

1. **对抗式自优化**：让模型自己扮演"作者"和"评审"两个对立角色，用批判驱动改进（对应 Self-Refine / Reflexion 方法）。
2. **收敛即成本控制**：把"什么时候停"抽象成明确的终止条件，而不是无脑循环。
3. **对 LLM 输出的防御性编程**：永远不信任模型输出一定规范，层层降级、类型容错。

---

## 二、技术架构概览

### 2.1 分层架构 🟢

```
┌─────────────────────────────────────────────────────────┐
│                     调用入口层                            │
│   examples/ (终端示例)      web/ (FastAPI + SSE 网页)     │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  编排层 (Orchestrator)                    │
│   命令式：src/orchestrator/orchestrator.py               │
│   图状态机（可选）：src/graph/workflow.py (LangGraph)      │
│   职责：控制迭代循环、状态管理、收敛判断、结果汇总           │
└───────┬──────────────────────────────┬──────────────────┘
        │                              │
┌───────▼──────────┐        ┌──────────▼───────────────┐
│  Generator Agent │        │      Critic Agent        │
│  (生成/优化)      │        │      (审查/打分)          │
│  generator.py    │        │      critic.py           │
└───────┬──────────┘        └──────────┬───────────────┘
        │                              │
┌───────▼──────────────────────────────▼───────────────┐
│                  Agent 基类 (base.py)                  │
│   封装 LLM 调用、流式、重试、token 统计                  │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│                 数据模型层 (models/schemas.py)          │
│   CritiqueResult / AgentState / IterationRecord        │
│   （Pydantic 建模，系统"契约"所在）                      │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│           Prompt 层 (prompts/)  +  配置层 (config/)     │
│   四领域系统提示词 + 消息模板     环境变量/模型/编排参数    │
└──────────────────────────────────────────────────────┘
```

### 2.2 技术栈 🟢

| 技术 | 用途 | 在项目中的位置 |
|------|------|---------------|
| **LangChain** (`ChatOpenAI`) | LLM 统一调用抽象 | `base.py` |
| **LangGraph** (`StateGraph`) | 图状态机版工作流（可选） | `graph/workflow.py` |
| **Pydantic** | 数据建模 + 结构化输出校验 | `models/schemas.py` |
| **python-dotenv** | 环境变量管理 | `config/settings.py` |
| **FastAPI + SSE** | 流式 Web 服务 | `web/server.py` |
| **pytest + Mock** | 离线单元测试 | `tests/` |

---

## 三、关键功能模块

> 每个模块都标注了**职责、对应文件、难度**，可作为查阅索引。

| 模块 | 职责一句话 | 核心文件 | 难度 |
|------|-----------|---------|------|
| **配置管理** | 统一读取环境变量/模型参数，单例模式 | `config/settings.py` | 🟢 |
| **数据模型** | 定义系统"契约"：审查结果、状态、历史 | `src/models/schemas.py` | 🟢 |
| **Agent 基类** | 封装 LLM 调用/流式/重试/token 统计 | `src/agents/base.py` | 🟡 |
| **Generator** | 首轮生成 + 按反馈迭代 + 提取产出 | `src/agents/generator.py` | 🟡 |
| **Critic** | 审查产出 + 结构化输出 + 容错解析 | `src/agents/critic.py` | 🔴 |
| **Orchestrator** | 迭代循环 + 收敛判断 + 回调 | `src/orchestrator/orchestrator.py` | 🟡 |
| **Prompt 模板** | 四领域系统提示词 + 消息模板 | `src/prompts/*.py` | 🟢 |
| **LangGraph 工作流** | 图状态机版的同一套流程（对比学习） | `src/graph/workflow.py` | 🔴 |
| **Web 服务** | 流式 SSE + 可视化界面 | `web/server.py` + `web/static/index.html` | 🟡 |
| **示例** | 不同场景的可运行入口 | `examples/*.py` | 🟢 |
| **测试** | 用 Mock LLM 离线验证核心逻辑 | `tests/*.py` | 🟡 |

### 3.1 各模块简要说明

**配置管理 `config/settings.py`** 🟢
- 用 dataclass 组织 `LLMConfig`（模型/温度/超时）和 `OrchestratorConfig`（轮数/阈值）。
- `get_config()` 返回全局单例，`load_dotenv(override=True)` 让 `.env` 优先于系统环境变量。
- 学习点：**配置集中管理 + 单例**，便于全局统一调整（例如 `multi_round_demo.py` 里改阈值）。

**数据模型 `src/models/schemas.py`** 🟢
- `CritiqueResult`：系统最核心的结构化输出（`score`/`issues`/`suggestions`/`acceptable`/`summary`），带 `field_validator` 做一致性校验（如"acceptable=True 时分数不能低于 60"）。
- `AgentState`：整个迭代过程的状态快照，含 `history` 和 `get_best_draft()`、`get_score_trend()` 两个工具方法。
- 学习点：**用 Pydantic 定义领域契约**，是后续所有逻辑的基础。

**Agent 基类 `src/agents/base.py`** 🟡
- `call_llm`（阻塞）、`call_llm_stream`（流式 yield）、`call_llm_with_retry`（重试）。
- 支持**外部注入 `llm`**，这是测试能用 Mock 跑通的关键设计。
- 学习点：**依赖注入**让 Agent 与具体模型解耦。

**Generator `src/agents/generator.py`** 🟡
- `_build_user_message` 区分"首次生成"和"基于反馈迭代"两种消息。
- `_extract_final_output` 用正则提取 `【最终产出】` 等标记，拿"干净"的产出。
- 学习点：**用固定标记控制模型输出结构**，再切割提取。

**Critic `src/agents/critic.py`** 🔴
- 这是全项目**工程细节最丰富**的文件，值得精读。
- 把 `PydanticOutputParser.get_format_instructions()` 注入 prompt → 三级降级解析（直接解析 → 正则提取 JSON → 类型容错）→ 最终兜底。
- 学习点：**对 LLM 输出的防御性编程**，详见[第六节](#六重点难点提示)。

**Orchestrator `src/orchestrator/orchestrator.py`** 🟡
- `run()` 主循环：生成 → 审查 → 记录 → 回调 → 判断收敛。
- `_check_convergence()`：三种终止条件。
- `_build_result()`：未收敛时返回**历史最优版本**而非最后一版。
- 学习点：**控制流与业务逻辑分离**（回调解耦展示层）。

**Prompt 模板 `src/prompts/*.py`** 🟢
- 四个领域（general/code/writing/design）各有一套 Generator 和 Critic 提示词。
- 学习点：**按领域切换 prompt** 的工程组织方式，以及好的 prompt 怎么写（明确输出格式、评分标准、审查维度）。

**LangGraph 工作流 `src/graph/workflow.py`** 🔴
- 用 `StateGraph` 把同一套流程表达成 `generate → critique → (条件边) → generate / END`。
- 学习点：**同一业务逻辑的两种实现**（命令式 vs 图状态机）对比，理解 LangGraph 的节点/边/条件路由思想。

**Web 服务 `web/`** 🟡
- `server.py`：FastAPI 起服务，`/api/stream` 用 SSE 在后台线程跑 Orchestrator，`loop.call_soon_threadsafe` 安全推事件。
- 学习点：**LLM 流式输出如何通过 SSE 送到浏览器**（打字机效果）。

**测试 `tests/`** 🟡
- `test_orchestrator.py` 用 `MockLLM`（自定义 `invoke` 返回预设内容）+ `MagicMock` 注入，**完全离线**验证收敛逻辑。
- 学习点：**如何给 LLM 应用写单元测试**——核心是不依赖真实模型，用 Mock 固定输入输出。

---

## 四、核心业务流程

### 4.1 主迭代流程 🟡

以命令式 `Orchestrator.run()` 为例：

```
run(task)
  │
  ├─ 初始化 AgentState（task/domain/max_rounds）
  │
  └─ while current_round < max_rounds:
        │
        ├─ ① Generator 生成/修改
        │     - 首轮：只带 task
        │     - 后续：带 task + 上一版 draft + 上一轮 critique
        │     - 流式时逐 token 触发 on_generator_token 回调
        │
        ├─ ② Critic 审查
        │     - 注入 JSON Schema 格式说明
        │     - 解析为 CritiqueResult（score/issues/suggestions/...）
        │
        ├─ ③ 记录 IterationRecord 到 state.history
        │
        ├─ ④ 触发回调 on_round_complete(round, draft, critique)
        │
        └─ ⑤ 判断收敛 → 收敛则 break
  │
  └─ _build_result：未收敛则取 history 中评分最高的版本
```

### 4.2 收敛判断（三种终止条件）🟡

`_check_convergence()` 中，满足**任一**即停止：

1. **质量达标**：`acceptable == True` 且 `score >= 阈值`（默认 85）。
2. **无新反馈**：连续 N 轮（默认 2）`issues` 完全相同（`issues_match` 用集合比较）。
3. **达到最大轮数**：硬上限兜底（默认 5）。

> 设计意图：条件 1 是"已够好，停"；条件 2 是"改不动了，别再浪费钱"；条件 3 是"兜底，防止成本爆炸"。

### 4.3 Critic 结构化输出的解析链路 🔴

```
LLM 原始回复
  │
  ├─ ① parser.parse() 直接按 Pydantic 解析
  │      └─ 成功 → 返回
  │
  ├─ ② _extract_json() 提取 JSON（```json 代码块 / 首个{到末个}）
  │      └─ json.loads 后 _coerce_critique() 类型容错
  │
  └─ ③ 降级：score=50、acceptable=False、issues 带原始回复片段
```

关键点：**② 的 `_coerce_critique`** 是精华——把 `"85"` 字符串转 int、字符串转列表、字符串布尔转 bool，并兜底 `acceptable` 与 `score` 的一致性冲突。

### 4.4 数据流向 🟢

```
用户 task ──▶ Orchestrator ──▶ Generator ──▶ draft（草稿文本）
                                    ▲            │
                                    │            ▼
                                    │         Critic
                                    │            │
                                    │            ▼
                                    └── CritiqueResult（评分/问题/建议）
                                        （下一轮反馈给 Generator）
```

---

## 五、建议阅读顺序（文件级路线图）

按下面顺序读，每一阶段都明确"读什么、看什么、掌握到什么程度"。

### 阶段一：先跑起来，建立直觉 🟢

| 顺序 | 文件 | 重点 | 目标 |
|------|------|------|------|
| 1 | `README.md` | 架构图、收敛机制、快速开始 | 建立整体认知 |
| 2 | `examples/quick_start.py` | 最简用法 + `on_round_complete` 回调 | 看懂"怎么用" |
| 3 | `examples/multi_round_demo.py` | 如何触发多轮（复杂任务 + 提高阈值） | 理解"为什么有时候只跑一轮" |
| 4 | `config/settings.py` | 有哪些配置项 | 知道参数在哪调 |

> **验收标准**：能回答"这个系统输入什么、输出什么、靠什么停下来"。

### 阶段二：理解核心流程 🟡

| 顺序 | 文件 | 重点 | 目标 |
|------|------|------|------|
| 5 | `src/models/schemas.py` | `CritiqueResult`、`AgentState` 的字段与校验 | 先吃透"数据契约" |
| 6 | `src/orchestrator/orchestrator.py` | `run()` 主循环 + `_check_convergence()` | 吃透控制流 |
| 7 | `src/agents/generator.py` | 首轮 vs 迭代消息、产出提取 | 理解 Generator 怎么做 |
| 8 | `src/agents/base.py` | `call_llm` / `call_llm_stream` / 重试 | 理解 LLM 调用封装 |

> **验收标准**：能对着代码画出[4.1 的主迭代流程图](#41-主迭代流程)，并说清三种收敛条件各自在哪个函数、如何判断。

### 阶段三：深入 LLM 工程细节 🔴

| 顺序 | 文件 | 重点 | 目标 |
|------|------|------|------|
| 9 | `src/agents/critic.py` | 三级降级解析 + `_coerce_critique` 容错 | 全项目精华，精读 |
| 10 | `src/prompts/critic_prompt.py` | 审查维度、评分标准、JSON 输出要求 | 理解"好 prompt 长什么样" |
| 11 | `src/prompts/generator_prompt.py` | 输出格式标记（`【最终产出】`等） | 理解标记切割的配合 |
| 12 | `tests/test_orchestrator.py` | `MockLLM` 如何离线测试收敛 | 学会给 LLM 应用写测试 |

> **验收标准**：能说清"Critic 回复解析失败时会经历哪几步、每一步兜什么底"，以及"为什么要把 JSON Schema 注入 prompt"。

### 阶段四：扩展与对比 🔴

| 顺序 | 文件 | 重点 | 目标 |
|------|------|------|------|
| 13 | `src/graph/workflow.py` | 图状态机的节点/边/条件路由 | 对比命令式实现 |
| 14 | `web/server.py` + `web/static/index.html` | SSE 流式推送 + 前端折叠交互 | 理解流式产品化 |
| 15 | `examples/from_draft_example.py` | 传入初始草稿的用法 | 理解"润色/review"场景 |

> **验收标准**：能说出"命令式 Orchestrator 和 LangGraph 图版本各自适用什么场景"。

---

## 六、重点难点提示

> 这些是值得"死磕"的点，理解了就抓住了项目的灵魂。

### 🔴 难点 1：Critic 的鲁棒解析（`critic.py`）

- **为什么难**：真实 LLM（尤其弱模型）的输出经常不符合预期——字段缺失、类型错误、夹带解释文字。
- **解法套路**：`注入格式说明 → 直接解析 → 正则提取 → 类型容错 → 兜底`，层层设防，永不崩溃。
- **迁移价值**：任何"让 LLM 输出结构化数据"的场景都要这么做。

### 🔴 难点 2：收敛机制 = 成本控制（`orchestrator.py`）

- **为什么难**：看似只是几个 if 判断，实则是一个完整的"终止策略"设计。
- **关键细节**：未收敛时返回**历史最优版本**（`get_best_draft`），因为迭代不是单调上升的。
- **迁移价值**：任何"Agent 循环"都必须设计终止条件，否则成本失控。

### 🟡 难点 3：依赖注入（贯穿全项目）

- `BaseAgent` 可注入 `llm`、`Orchestrator` 可注入 `generator`/`critic`。
- **价值**：这是测试能完全离线跑、以及未来替换模型的根基。理解它，才能理解 `tests/` 为什么能 Mock。

### 🟡 难点 4：流式输出的链路（`base.py` → `orchestrator.py` → `web/server.py`）

- `invoke`（一次性）与 `stream`（逐块）的区别 → 回调把 token 传给上层 → SSE 推给浏览器。
- **价值**：理解"打字机效果"背后的完整数据流。

---

## 七、动手练习建议

按难度递增，验证自己是否真的掌握：

1. **🟢 复现与观察**：运行 `python examples/quick_start.py` 和 `examples/multi_round_demo.py`，观察每轮评分变化，回答"为什么前者只跑一轮、后者跑多轮"。

2. **🟡 改参数看效果**：把收敛阈值改成 99、把 `max_rounds` 改成 10，观察迭代行为变化；把 `domain` 从 `general` 换成 `code`，比较 Critic 审查维度的差异。

3. **🟡 读测试写结论**：只读 `tests/test_orchestrator.py`（不跑），写出每个测试用例验证的是哪个收敛条件、断言了什么。

4. **🔴 新增一个领域**：仿照 `prompts/` 里现有四个领域，新增一个领域（例如"翻译"或"测试用例设计"），补上 Generator/Critic 两套提示词，并在映射表注册，然后跑通。

5. **🔴 实现"多 Critic 并行"**：修改/新增一个编排逻辑，让多个不同领域的 Critic 同时审查同一份 draft，取问题并集后交给 Generator 修改（README 里列出的扩展方向之一）。

---

## 附：学习路径速查图

```
阶段一（跑通）    README → quick_start → multi_round_demo → settings
        │
        ▼
阶段二（核心流程） schemas → orchestrator → generator → base
        │
        ▼
阶段三（LLM 细节） critic → critic_prompt → generator_prompt → test_orchestrator
        │
        ▼
阶段四（扩展对比） graph/workflow → web/ → from_draft_example
```

> 建议：**阶段一、二必读**（理解核心价值），**阶段三精读 critic.py**（工程精髓），阶段四按需选读。
