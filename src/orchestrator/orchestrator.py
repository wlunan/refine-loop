"""
Orchestrator 编排器模块
负责控制 Generator-Critic 的整个迭代流程，
包括状态管理、收敛判断、结果汇总等
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from config.settings import get_config
from src.agents.critic import CriticAgent
from src.agents.generator import GeneratorAgent
from src.models.schemas import (
    AgentState,
    CritiqueResult,
    IterationRecord,
)

logger = logging.getLogger(__name__)


class OrchestratorStopped(Exception):
    """编排器被外部请求停止时抛出的内部异常，用于中断流式生成"""
    pass


@dataclass
class RunResult:
    """运行结果封装"""
    final_output: str
    state: AgentState
    iterations: int
    converged: bool
    convergence_reason: str
    score_trend: list
    total_time_seconds: float

    def summary(self) -> str:
        """生成运行摘要"""
        lines = [
            "=" * 50,
            "Generator-Critic 运行摘要",
            "=" * 50,
            f"任务: {self.state.task[:50]}...",
            f"迭代轮数: {self.iterations}",
            f"是否收敛: {'是' if self.converged else '否'}",
            f"收敛原因: {self.convergence_reason}",
            f"评分趋势: {' → '.join(map(str, self.score_trend))}",
            f"总耗时: {self.total_time_seconds:.2f}s",
            f"累计 Token: {self.state.total_tokens}",
            f"最终评分: {self.state.critique.score if self.state.critique else 'N/A'}",
            "=" * 50,
        ]
        return "\n".join(lines)


class Orchestrator:
    """
    编排器
    控制 Generator 和 Critic 的迭代对话流程，
    实现生成-批判-修改的循环，直到收敛或达到最大轮数
    """

    def __init__(
        self,
        domain: str = "general",
        max_rounds: Optional[int] = None,
        generator: Optional[GeneratorAgent] = None,
        critic: Optional[CriticAgent] = None,
        on_iteration_complete: Optional[Callable[[int, CritiqueResult], None]] = None,
        on_round_complete: Optional[Callable[[int, str, CritiqueResult], None]] = None,
        on_generator_token: Optional[Callable[[int, str], None]] = None,
    ):
        """
        初始化编排器
        
        Args:
            domain: 任务领域
            max_rounds: 最大迭代轮数，为 None 时使用配置默认值
            generator: 外部注入的 Generator（用于自定义或测试）
            critic: 外部注入的 Critic（用于自定义或测试）
            on_iteration_complete: 每轮完成后的回调函数（仅评分结果）
            on_round_complete: 每轮完成后的回调函数（含完整草稿与审查结果），
                签名: (round_num, draft, critique)，用于实时观察对话内容
            on_generator_token: Generator 流式生成时的 token 回调，
                签名: (round_num, token)，传入后 Generator 会走流式生成
        """
        config = get_config()
        self.domain = domain
        self.max_rounds = max_rounds or config.orchestrator.default_max_rounds
        self.score_threshold = config.orchestrator.convergence_score_threshold
        self.no_progress_rounds = config.orchestrator.no_progress_rounds
        # Token 预算：<= 0 表示不限制
        self.round_token_budget = config.orchestrator.round_token_budget
        self.total_token_budget = config.orchestrator.total_token_budget
        # 停止标志：线程安全的终止信号
        self._stop_event = threading.Event()

        # 初始化 Agent（支持外部注入）
        self.generator = generator or GeneratorAgent(domain=domain)
        self.critic = critic or CriticAgent(domain=domain)

        # 回调函数
        self.on_iteration_complete = on_iteration_complete
        self.on_round_complete = on_round_complete
        self.on_generator_token = on_generator_token

        logger.info(
            f"Orchestrator 初始化完成: domain={domain}, "
            f"max_rounds={self.max_rounds}, "
            f"score_threshold={self.score_threshold}"
        )

    def stop(self) -> None:
        """
        请求停止迭代（线程安全）

        调用后，编排器会在「当前 token 生成后」或「下一轮开始前」尽快停止，
        并返回当前历史最优版本。适用于 Web 等需要用户主动中断长任务的场景。
        """
        self._stop_event.set()
        logger.info("收到停止请求，将在当前步骤结束后停止")

    def _is_stopped(self) -> bool:
        """是否已收到停止请求"""
        return self._stop_event.is_set()

    def _current_total_tokens(self) -> int:
        """当前累计 token 消耗（Generator + Critic）"""
        return self.generator.total_tokens_used + self.critic.total_tokens_used

    def _exceeds_total_budget(self) -> bool:
        """是否已超过总 token 预算"""
        if self.total_token_budget <= 0:
            return False
        return self._current_total_tokens() >= self.total_token_budget

    def _exceeds_round_budget(self, round_tokens: int) -> bool:
        """单轮 token 消耗是否超过预算"""
        if self.round_token_budget <= 0:
            return False
        return round_tokens > self.round_token_budget

    def run(self, task: str, initial_draft: str = "") -> RunResult:
        """
        执行完整的 Generator-Critic 迭代流程
        
        Args:
            task: 任务描述
            initial_draft: 初始草稿（可选，提供后跳过首次生成）
        
        Returns:
            RunResult 运行结果
        """
        start_time = time.time()
        logger.info(f"开始执行任务: {task[:80]}...")

        # 初始化状态
        state = AgentState(
            task=task,
            domain=self.domain,
            draft=initial_draft,
            max_rounds=self.max_rounds,
        )

        # 如果有初始草稿，先进行一次审查
        if initial_draft:
            logger.info("使用用户提供的初始草稿，直接进入审查阶段")
            critique = self.critic.critique(task, initial_draft)
            state.critique = critique
            state.current_round = 1
            state.add_iteration(IterationRecord(
                round=0,
                draft=initial_draft,
                critique=critique,
                duration_seconds=0,
            ))

            # 检查初始草稿是否已经达标
            if self._check_convergence(state):
                return self._build_result(state, start_time)

        # 主循环：生成 → 审查 → 判断收敛
        while state.current_round < self.max_rounds:
            # 0. 检查外部停止请求
            if self._is_stopped():
                state.convergence_reason = "用户主动停止"
                break

            # 0.1 检查总 token 预算
            if self._exceeds_total_budget():
                state.convergence_reason = (
                    f"达到总 token 预算 {self.total_token_budget}"
                )
                break

            iteration_start = time.time()
            round_num = state.current_round + 1
            round_start_tokens = self._current_total_tokens()

            logger.info(f"--- 第 {round_num} 轮迭代开始 ---")

            # 1. Generator 生成/修改
            # 传入 on_generator_token 时走流式生成，实时推送 token
            if self.on_generator_token:
                stop_event = self._stop_event

                def _on_token(token: str) -> None:
                    if stop_event.is_set():
                        raise OrchestratorStopped("用户主动停止")
                    self.on_generator_token(round_num, token)

                try:
                    draft = self.generator.generate_stream(
                        task=task,
                        draft=state.draft,
                        critique=state.critique,
                        on_token=_on_token,
                    )
                except OrchestratorStopped:
                    state.convergence_reason = "用户主动停止"
                    break
            else:
                draft = self.generator.generate(
                    task=task,
                    draft=state.draft,
                    critique=state.critique,
                )
            state.draft = draft

            # 1.1 生成后再次检查停止（Critic 审查是阻塞调用，尽量在此之前停）
            if self._is_stopped():
                state.convergence_reason = "用户主动停止"
                break

            # 2. Critic 审查
            critique = self.critic.critique(task, draft)
            state.critique = critique
            state.current_round = round_num

            # 3. 记录迭代
            iteration_duration = time.time() - iteration_start
            record = IterationRecord(
                round=round_num,
                draft=draft,
                critique=critique,
                duration_seconds=iteration_duration,
            )
            state.add_iteration(record)

            # 4. 触发回调
            if self.on_iteration_complete:
                try:
                    self.on_iteration_complete(round_num, critique)
                except Exception as e:
                    logger.warning(f"回调执行失败: {e}")

            # 4.5 触发完整轮次回调（含草稿全文，用于实时观察对话内容）
            if self.on_round_complete:
                try:
                    self.on_round_complete(round_num, draft, critique)
                except Exception as e:
                    logger.warning(f"轮次回调执行失败: {e}")

            logger.info(
                f"第 {round_num} 轮完成: 评分={critique.score}, "
                f"问题数={len(critique.issues)}, "
                f"耗时={iteration_duration:.2f}s"
            )

            # 4.6 检查单轮 token 预算
            round_tokens = self._current_total_tokens() - round_start_tokens
            if self._exceeds_round_budget(round_tokens):
                state.convergence_reason = (
                    f"本轮 token 超预算（{round_tokens} > "
                    f"{self.round_token_budget}）"
                )
                break

            # 5. 检查收敛
            if self._check_convergence(state):
                break

        # 构建结果
        result = self._build_result(state, start_time)
        logger.info(result.summary())
        return result

    def _check_convergence(self, state: AgentState) -> bool:
        """
        检查是否满足收敛条件
        三种收敛条件，满足任一即收敛：
        1. 质量达标：score >= threshold 且 acceptable=True
        2. 无新反馈：连续 N 轮 issues 完全相同
        3. 达到最大轮数（在循环条件中处理）
        
        Args:
            state: 当前系统状态
        
        Returns:
            是否已收敛
        """
        critique = state.critique
        if critique is None:
            return False

        # 条件1：质量达标
        if critique.acceptable and critique.score >= self.score_threshold:
            state.converged = True
            state.convergence_reason = (
                f"质量达标：评分 {critique.score} >= 阈值 {self.score_threshold}"
            )
            logger.info(f"收敛：{state.convergence_reason}")
            return True

        # 条件2：无新反馈（连续 N 轮 issues 相同）
        if len(state.history) >= self.no_progress_rounds + 1:
            recent = state.history[-(self.no_progress_rounds + 1):]
            all_same = all(
                recent[i].critique.issues_match(recent[i + 1].critique)
                for i in range(len(recent) - 1)
            )
            if all_same:
                state.converged = True
                state.convergence_reason = (
                    f"连续 {self.no_progress_rounds} 轮无新反馈，"
                    f"无法继续优化"
                )
                logger.info(f"收敛：{state.convergence_reason}")
                return True

        return False

    def _build_result(self, state: AgentState, start_time: float) -> RunResult:
        """
        构建运行结果
        
        Args:
            state: 最终状态
            start_time: 开始时间戳
        
        Returns:
            RunResult
        """
        total_time = time.time() - start_time

        # 记录累计 token 消耗
        state.total_tokens = self._current_total_tokens()

        # 如果未收敛，取历史中评分最高的版本。
        # 注意：因 token 预算 / 用户停止而提前退出时，convergence_reason
        # 已在主循环中设置，这里不覆盖。
        if not state.converged:
            if not state.convergence_reason:
                state.convergence_reason = (
                    f"达到最大轮数 {self.max_rounds}，未完全收敛，"
                    f"返回历史最优版本"
                )
            final_output = state.get_best_draft()
        else:
            final_output = state.draft

        return RunResult(
            final_output=final_output,
            state=state,
            iterations=state.current_round,
            converged=state.converged,
            convergence_reason=state.convergence_reason or "未知",
            score_trend=state.get_score_trend(),
            total_time_seconds=total_time,
        )
