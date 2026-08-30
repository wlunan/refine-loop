"""
代码自愈闭环（Self-Healing Loop）

核心价值：让「验证」基于真实执行结果（测试是否通过），让「修复」有明确
目标（消除失败），形成无人值守的「生成 → 验证 → 失败定位 → 修复 → 复跑」
闭环。

这是本项目相对「纯文本挑刺」多 Agent 审查的关键差异点：批评的依据不是
「我觉得这行可能有 bug」，而是「pytest 第 3 条挂了、报错如下」。修复的
目标也因此变得客观可衡量——让验证命令通过。

与 Orchestrator.run_with_files 的关系：
- run_with_files：Generator 改文件 → Critic 审查（文本）→ 反馈 → 迭代
- run：Generator 改文件 → 真实跑验证命令 → 失败日志反馈 → 修复 → 复跑
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from src.agents.generator import GeneratorAgent
from src.tools.verification import CommandResult, CommandRunner

logger = logging.getLogger(__name__)


@dataclass
class SelfHealingResult:
    """自愈闭环运行结果"""

    task: str
    success: bool
    repair_rounds: int
    final_verification: Optional[CommandResult]
    verification_history: List[CommandResult] = field(default_factory=list)
    total_time_seconds: float = 0.0

    def summary(self) -> str:
        """生成运行摘要"""
        lines = [
            "=" * 50,
            "代码自愈闭环运行摘要",
            "=" * 50,
            f"任务: {self.task[:50]}...",
            f"是否通过验证: {'是' if self.success else '否'}",
            f"修复轮数: {self.repair_rounds}",
            f"总耗时: {self.total_time_seconds:.2f}s",
        ]
        if self.final_verification:
            lines.append(f"最终退出码: {self.final_verification.exit_code}")
        lines.append("=" * 50)
        return "\n".join(lines)


class SelfHealingOrchestrator:
    """
    代码自愈编排器

    循环：Generator 生成/修改文件 → 运行验证命令（默认 pytest）→
    失败则把失败日志注入下一轮任务 → 修复 → 复跑，直到验证通过或
    达到最大修复轮数。

    Args:
        generator: Generator Agent（可注入 Mock 用于测试）
        workspace_dir: 工作区根目录（绝对路径），代码生成与验证都发生在此
        verify_command: 验证命令，默认 "pytest"（走 run_tests），
            也可传入任意 shell 命令（走 run_command）
        max_repair_rounds: 最大修复轮数（含首次生成）
        domain: Generator 领域，默认 code
        timeout: 单次验证命令超时（秒）
        on_event: 事件回调，签名 on_event(dict)，用于终端/Web 展示
    """

    def __init__(
        self,
        generator: Optional[GeneratorAgent] = None,
        workspace_dir: str = ".",
        verify_command: str = "pytest",
        max_repair_rounds: int = 5,
        domain: str = "code",
        timeout: int = 120,
        on_event: Optional[Callable[[dict], None]] = None,
    ):
        self.generator = generator or GeneratorAgent(domain=domain)
        self.workspace_dir = os.path.abspath(os.path.expanduser(workspace_dir))
        self.verify_command = verify_command
        self.max_repair_rounds = max_repair_rounds
        self.runner = CommandRunner(self.workspace_dir, timeout=timeout)
        self.on_event = on_event

    # ------------------------------------------------------------------
    # 事件推送
    # ------------------------------------------------------------------
    def _emit(self, event: dict) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"事件回调失败: {e}")

    # ------------------------------------------------------------------
    # 验证
    # ------------------------------------------------------------------
    def _verify(self) -> CommandResult:
        """运行验证命令（pytest 或自定义命令）"""
        if self.verify_command.strip().lower() == "pytest":
            return self.runner.run_tests()
        return self.runner.run(self.verify_command)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def run(self, task: str) -> SelfHealingResult:
        """
        执行代码自愈闭环

        Args:
            task: 任务描述（如「实现一个 LRU 缓存，含单元测试」）

        Returns:
            SelfHealingResult
        """
        start = time.time()
        os.makedirs(self.workspace_dir, exist_ok=True)

        feedback_task = task
        history: List[CommandResult] = []

        for round_idx in range(1, self.max_repair_rounds + 1):
            logger.info(
                f"--- 自愈第 {round_idx}/{self.max_repair_rounds} 轮："
                f"生成/修复代码 ---"
            )
            self._emit(
                {
                    "type": "repair_round",
                    "round": round_idx,
                    "message": f"第 {round_idx} 轮：生成/修复代码",
                }
            )

            # 1. Generator 生成/修复文件（文件持久在工作区，跨轮可见）
            def _on_gen_event(event: dict) -> None:
                event = dict(event)
                event["round"] = round_idx
                self._emit(event)

            self.generator.generate_with_files(
                task=feedback_task,
                workspace_dir=self.workspace_dir,
                on_event=_on_gen_event,
            )

            # 2. 运行验证命令，拿到真实执行结果
            self._emit({"type": "verifying", "round": round_idx})
            result = self._verify()
            history.append(result)

            self._emit(
                {
                    "type": "verification_result",
                    "round": round_idx,
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "detail": result.to_str(),
                }
            )
            logger.info(
                f"自愈第 {round_idx} 轮验证："
                f"{'通过' if result.success else '失败'} "
                f"(exit_code={result.exit_code})"
            )

            # 3. 验证通过 → 成功收敛
            if result.success:
                return SelfHealingResult(
                    task=task,
                    success=True,
                    repair_rounds=round_idx,
                    final_verification=result,
                    verification_history=history,
                    total_time_seconds=time.time() - start,
                )

            # 4. 验证失败 → 把失败日志注入下一轮任务，驱动修复
            feedback_task = self._build_feedback(task, result)

        # 达到最大修复轮数仍未通过
        logger.warning(f"达到最大修复轮数 {self.max_repair_rounds}，验证仍未通过")
        return SelfHealingResult(
            task=task,
            success=False,
            repair_rounds=self.max_repair_rounds,
            final_verification=history[-1] if history else None,
            verification_history=history,
            total_time_seconds=time.time() - start,
        )

    # ------------------------------------------------------------------
    # 反馈构造
    # ------------------------------------------------------------------
    def _build_feedback(self, task: str, result: CommandResult) -> str:
        """把验证失败日志拼进任务，驱动 Generator 定位并修复"""
        return (
            f"{task}\n\n"
            f"【上一轮验证结果】验证未通过，请修复代码：\n"
            f"{result.to_str()}\n\n"
            f"请根据以上失败信息，定位并修复工作区中的相关代码文件。"
            f"修复完成后系统会再次运行验证，目标是让验证命令通过。"
        )
