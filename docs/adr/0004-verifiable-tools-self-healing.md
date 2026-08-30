# ADR-0004: 可验证工具集 + 代码自愈闭环

## 状态
已接受

## 背景
纯文本审查的批评是「意见」（「我觉得这行可能有 bug」），缺乏事实依据；修复也缺乏客观目标。这限制了「审查 Agent 替代人」的可信度。

## 决策
1. 新增**可验证工具集**（`src/tools/verification.py`）：`run_command` / `run_tests` / `run_lint` / `run_python`，通过 `CommandRunner` 在工作区沙箱内执行真实命令，带超时控制与输出截断。
2. 新增**代码自愈闭环**（`src/orchestrator/self_healing.py`）：`SelfHealingOrchestrator` 循环「生成/修复 → 运行验证命令（默认 pytest）→ 失败则把失败日志注入下一轮任务 → 修复 → 复跑」。
3. 文件模式 Generator 可调用验证工具（`enable_verification`），prompt 引导「先验证再交付」。

## 理由
- 批评依据从「意见」升级为「事实」（pytest 第 3 条挂了、报错如下）
- 验证是确定性的（跑测试），修复目标客观可衡量（让验证通过），不依赖主观评分
- 为「审查 Agent 替代人」补上最关键的一块——可验证性（相对 CodeRabbit/Qodo 的差异点）

## 后果
- 需要安全执行任意命令：cwd 固定为工作区、超时、输出截断
- 验证命令的选择（pytest/lint/自定义）需可配置
- 与纯文本迭代互补：文本迭代负责「质量打磨」，自愈闭环负责「客观验证 + 修复」
