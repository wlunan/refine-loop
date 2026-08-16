# Generator-Critic 多 Agent 系统

一个基于**生成-批判迭代模式**的多智能体协作框架。通过 Generator（生成者）和 Critic（批判者）两个 Agent 的对话迭代，不断优化产出质量，直到达到可接受标准。

## 架构设计

```
用户输入 → Orchestrator → Generator → Critic → (判断收敛) → 是 → 输出结果
                                          ↓ 否
                                       Generator（基于反馈修改）
```

### 核心组件

| 组件 | 职责 |
|------|------|
| **GeneratorAgent** | 根据任务和批判反馈生成/优化产出 |
| **CriticAgent** | 审查产出，输出结构化的批判结果（评分、问题、建议） |
| **Orchestrator** | 控制迭代流程，管理状态，判断收敛 |
| **GeneratorCriticGraph** | 基于 LangGraph 的图状态机实现（可选） |

### 收敛机制

三种终止条件，满足任一即收敛：

1. **质量达标**：Critic 评分 ≥ 阈值（默认85）且 `acceptable=true`
2. **无新反馈**：连续 N 轮（默认2轮）审查问题完全相同
3. **最大轮数**：达到配置的最大迭代轮数（默认5轮）

## 项目结构

```
generator-critic-agent/
├── README.md                    # 项目说明
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量示例
├── .gitignore                   # Git 忽略配置
├── config/
│   ├── __init__.py
│   └── settings.py              # 配置管理（LLM、编排器参数）
├── src/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py           # 数据模型（状态、审查结果、迭代记录）
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py              # Agent 基类（LLM 调用、重试、token 统计）
│   │   ├── generator.py         # Generator Agent 实现
│   │   └── critic.py            # Critic Agent 实现
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   └── orchestrator.py      # 编排器（命令式实现）
│   ├── graph/
│   │   ├── __init__.py
│   │   └── workflow.py          # LangGraph 工作流（图状态机实现）
│   └── prompts/
│       ├── __init__.py
│       ├── generator_prompt.py  # Generator Prompt 模板（多领域）
│       └── critic_prompt.py     # Critic Prompt 模板（多领域）
├── examples/
│   ├── __init__.py
│   ├── quick_start.py           # 快速开始示例
│   ├── code_review_example.py   # 代码审查示例
│   ├── writing_example.py       # 文案写作示例
│   ├── from_draft_example.py    # 从初始草稿优化示例
│   └── langgraph_example.py     # LangGraph 版本示例
└── tests/
    ├── __init__.py
    ├── test_schemas.py          # 数据模型测试
    ├── test_orchestrator.py     # 编排器测试（含 Mock LLM）
    ├── test_agents.py           # Agent 测试
    └── test_prompts.py          # Prompt 模板测试
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key
```

### 3. 运行示例

```bash
# 快速开始
python examples/quick_start.py

# 代码审查示例
python examples/code_review_example.py

# 文案写作示例
python examples/writing_example.py
```

## 基本用法

### 命令式 API（推荐）

```python
from src.orchestrator import Orchestrator

# 创建编排器
orchestrator = Orchestrator(
    domain="code",        # 领域: general/code/writing/design
    max_rounds=5,         # 最大迭代轮数
)

# 运行任务
result = orchestrator.run("用 Python 实现一个 LRU 缓存")

# 输出结果
print(result.final_output)
print(result.summary())
```

### 从初始草稿开始优化

```python
result = orchestrator.run(
    task="优化这段代码",
    initial_draft="def foo(): pass"  # 已有草稿
)
```

### 实时回调

```python
def on_iteration(round_num, critique):
    print(f"第 {round_num} 轮: 评分 {critique.score}")

orchestrator = Orchestrator(
    domain="code",
    on_iteration_complete=on_iteration,
)
```

### LangGraph 版本

```python
from src.graph import GeneratorCriticGraph

graph = GeneratorCriticGraph(domain="code", max_rounds=3)
state = graph.run("实现二分查找")
print(state["draft"])
```

## 支持的领域

| 领域 | 适用场景 | Generator 特点 | Critic 审查维度 |
|------|---------|---------------|----------------|
| `general` | 通用任务 | 结构化输出 | 正确性、完整性、可执行性、规范性 |
| `code` | 代码生成/审查 | 完整可运行代码、类型注解 | 正确性、性能、规范、安全性、可维护性 |
| `writing` | 文案/文章写作 | 完整文案结构 | 逻辑说服力、表达质量、结构节奏、受众适配 |
| `design` | 方案/架构设计 | 完整方案文档 | 可行性、完整性、可扩展性、性能、安全性 |

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | API 密钥（必填） | - |
| `OPENAI_API_BASE` | API 基础地址（兼容其他模型） | - |
| `GENERATOR_MODEL` | Generator 使用的模型 | `gpt-4o` |
| `CRITIC_MODEL` | Critic 使用的模型 | `gpt-4o-mini` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `DEBUG` | 调试模式 | `false` |

### 编排器参数

```python
Orchestrator(
    domain="general",           # 任务领域
    max_rounds=5,               # 最大迭代轮数
    generator=None,             # 自定义 Generator（依赖注入）
    critic=None,                # 自定义 Critic（依赖注入）
    on_iteration_complete=None, # 每轮完成回调
)
```

## 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_orchestrator.py -v

# 查看覆盖率
pytest tests/ --cov=src --cov-report=term-missing
```

## 成本控制策略

1. **模型分级**：Generator 用强模型（GPT-4o），Critic 可用弱模型（GPT-4o-mini）
2. **轮数上限**：通过 `max_rounds` 限制最大迭代次数
3. **提前终止**：质量达标立即停止，不浪费 token
4. **无新反馈检测**：连续无改进时自动终止
5. **最优版本返回**：未收敛时返回历史评分最高的版本，而非最后一版

## 扩展方向

- **多 Critic 并行**：多个 Critic 从不同维度审查，取问题并集
- **Critic 分级**：初筛用弱模型，通过后用强模型终审
- **人工介入**：达到最大轮数仍不收敛时推送给人工
- **自定义领域**：通过新增 Prompt 模板支持更多领域
- **Java 版本**：可用 LangChain4j 实现同等逻辑

## 技术栈

- **Python 3.10+**
- **LangChain** - LLM 应用框架
- **LangGraph** - 基于图的 Agent 工作流
- **Pydantic** - 数据验证和结构化输出
- **python-dotenv** - 环境变量管理
- **pytest** - 单元测试

## License

MIT
