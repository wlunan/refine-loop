# 更新日志（Changelog）

本项目的所有重要变更记录，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

## [未发布] - 2026-08-30

### 新增
- **可验证工具集**（`src/tools/verification.py`）：`run_command` / `run_tests` / `run_lint` / `run_python`，带沙箱 cwd、超时控制与输出截断，让审查基于真实执行结果
- **代码自愈闭环**（`src/orchestrator/self_healing.py`）：`SelfHealingOrchestrator` 实现「生成 → 验证 → 失败定位 → 修复 → 复跑」
- 文件模式 Generator 支持 `enable_verification`，写完代码后可主动跑测试验证；文件模式 prompt 增加「先验证再交付」
- **评估框架 / benchmark**（`benchmark/`）：对比「单次生成 vs 自愈闭环」的测试通过率与修复率，输出量化报告
- 架构文档 `docs/ARCHITECTURE.md`、接口文档 `docs/API.md`、项目上下文 `CONTEXT.md`、决策记录 `docs/adr/`

### 修复
- 修正 `test_orchestrator.py` 两个红测试（`no_progress_rounds` 参数已从 `Orchestrator.__init__` 移除；三轮 issues 相同误触发「无新反馈」收敛）

## [1.0.0] - 更早

### 核心能力
- Generator-Critic 多 Agent 框架（生成-批判迭代）
- 收敛机制（质量达标 / 无新反馈 / 最大轮数），未收敛返回历史最优版本
- Critic 结构化输出的三级降级解析 + 类型容错
- 模型分级（Generator 强模型 + Critic 弱模型）+ token 预算控制
- FastAPI + SSE 流式 Web 服务 + Vue3 前端（工作台 / 任务列表 / 任务详情）
- 长时间运行任务管理（TaskManager，含断点恢复）
- 文件安全沙箱（FileWorkspace）+ 混合模式工具调用（ToolAgent）
- LangGraph 图状态机（对比实现）
- Mock LLM 完全离线单元测试
