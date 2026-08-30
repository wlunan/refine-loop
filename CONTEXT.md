# 项目上下文（CONTEXT）

> 给 AI 助手和新人看的「第一入口」。开工前先读本文件建立上下文，避免反复摸索。
> 更细的设计决策见 `docs/ARCHITECTURE.md` 与 `docs/adr/`。

## 一句话定位

把「单次 LLM 问答」工程化为「可自我纠错、可收敛、可控成本、可流式交互」的多 Agent 系统：
Generator（生成者）与 Critic（批判者）对抗式迭代，用批判驱动改进，直到收敛。

核心命题：**审查 Agent 替代人**——把「AI 输出 → 人肉审查 → 再喂提示词」的人机循环，迁移为无人值守的自动闭环。

## 技术栈

- 后端：Python 3.10+ / LangChain / LangGraph / Pydantic / FastAPI(SSE) / uvicorn
- 前端：Vue 3 + TypeScript + Vite / Ant Design Vue / Pinia / ECharts
- 测试：pytest + Mock LLM（完全离线）

## 如何运行

- 运行环境必须用（base 环境的 pydantic_core 已损坏，不可用）：
  `D:\software\ProgramTool\Miniconda3\envs\agentchat\python.exe`
- 后端：`python backend/server.py` → http://127.0.0.1:8000
- 前端开发：`cd frontend && npm run dev` → http://127.0.0.1:5173
- 测试：`<exe> -m pytest tests/`（52 个用例，无需 API Key）
- 终端示例：`python examples/quick_start.py`、`examples/self_healing_example.py` 等

## 目录结构（关键部分）

```
backend/
├── server.py                 # FastAPI 入口（CORS、路由挂载、前端托管）
├── routers/                  # workbench（SSE 流式）/ tasks（任务管理）
├── config/settings.py        # 配置（LLM、编排器参数、日志）
└── src/
    ├── convergence.py        # 共享收敛判定纯函数
    ├── models/schemas.py     # 数据契约（CritiqueResult / AgentState）
    ├── agents/               # Generator / Critic / ToolAgent / base
    ├── orchestrator/         # Orchestrator / SelfHealingOrchestrator
    ├── graph/workflow.py     # LangGraph 图状态机（对比实现）
    ├── prompts/              # 四领域提示词
    └── tools/                # filesystem（沙箱）/ verification（可验证）
frontend/                     # Vue3 前端源码
benchmark/                    # 评估框架（任务集 + 评测执行器 + 报告）
tests/                        # 单元测试（Mock LLM 离线）
```

## 核心概念

1. **收敛三条件**：质量达标（score≥阈值且 acceptable）/ 无新反馈（连续 N 轮 issues 相同）/ 最大轮数；未收敛时返回「历史最优版本」而非最后一版
2. **模型分级**：Generator 用强模型，Critic 用弱模型（挑刺比创作对能力要求低）
3. **三级降级解析**：Critic 结构化输出的防御性解析（直接解析 → 正则提取 JSON → 类型容错）
4. **可验证工具集 + 代码自愈**：`run_tests`/`run_lint`/`run_command`/`run_python` 让审查基于真实执行结果；`SelfHealingOrchestrator` 实现「生成 → 验证 → 失败定位 → 修复 → 复跑」

## 当前状态（2026-08-30）

- 已实现：文本/文件迭代、收敛机制、成本控制（token 预算）、可验证工具集、代码自愈闭环、Web 前端、长任务管理、评估框架/benchmark、Mock LLM 离线测试
- 下一步：审查标准外置化、CLI 入口

## 约定

- Git 提交信息用中文，通过 `git commit -F <utf8文件>`（PowerShell 下 `-m "中文"` 会乱码）
- `git add` 显式列出文件，勿用 `-A`
- 跑测试/运行必须用 agentchat 环境的 python
- 前端构建产物目标为 `backend/static/dist`（`frontend/vite.config.ts` 的 outDir 需与之保持一致，当前存在潜在不一致，待修）
