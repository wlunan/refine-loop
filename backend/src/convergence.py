"""
收敛判定共享模块

提供 Generator-Critic 迭代的收敛判定纯函数，供命令式 Orchestrator 与
LangGraph 工作流（GeneratorCriticGraph）共用，避免两份实现逻辑漂移。

统一收敛顺序：质量达标 → 无新反馈 → 达到最大轮数
（"无新反馈"排在"最大轮数"之前，便于在轮数耗尽前提前收敛，节省成本）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.models.schemas import CritiqueResult, IterationRecord


@dataclass(frozen=True)
class ConvergenceDecision:
    """收敛判定结果"""
    should_stop: bool = False   # 是否应停止迭代（三种终止条件任一命中）
    converged: bool = False     # 是否"成功收敛"（质量达标/无新反馈为 True，达到最大轮数为 False）
    reason: str = ""            # 停止 / 收敛原因


def evaluate_convergence(
    critique: Optional[CritiqueResult],
    current_round: int,
    max_rounds: int,
    score_threshold: int,
    no_progress_rounds: int,
    history: List[IterationRecord],
) -> ConvergenceDecision:
    """
    统一的收敛判定（三种终止条件，满足任一即停止）

    判定顺序：质量达标 → 无新反馈 → 达到最大轮数

    Args:
        critique: 当前审查结果（可能为 None，表示尚未审查）
        current_round: 当前轮数
        max_rounds: 最大迭代轮数
        score_threshold: 收敛评分阈值
        no_progress_rounds: 连续无新反馈轮数阈值
        history: 迭代历史记录列表

    Returns:
        ConvergenceDecision：should_stop 表示是否停止，
        converged 表示是否"成功收敛"（达到最大轮数时为 False）
    """
    if critique is None:
        return ConvergenceDecision()

    # 条件1：质量达标
    if critique.acceptable and critique.score >= score_threshold:
        return ConvergenceDecision(
            should_stop=True,
            converged=True,
            reason=f"质量达标：评分 {critique.score} >= 阈值 {score_threshold}",
        )

    # 条件2：无新反馈（连续 N 轮 issues 完全相同）
    if len(history) >= no_progress_rounds + 1:
        recent = history[-(no_progress_rounds + 1):]
        all_same = all(
            recent[i].critique.issues_match(recent[i + 1].critique)
            for i in range(len(recent) - 1)
        )
        if all_same:
            return ConvergenceDecision(
                should_stop=True,
                converged=True,
                reason=f"连续 {no_progress_rounds} 轮无新反馈，无法继续优化",
            )

    # 条件3：达到最大轮数（未真正收敛，仅停止）
    if current_round >= max_rounds:
        return ConvergenceDecision(
            should_stop=True,
            converged=False,
            reason=f"达到最大轮数 {max_rounds}",
        )

    return ConvergenceDecision()
