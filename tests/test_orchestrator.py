"""
Orchestrator 单元测试
使用 Mock LLM 测试编排器的迭代流程和收敛逻辑
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import pytest

from src.agents.critic import CriticAgent
from src.agents.generator import GeneratorAgent
from src.models.schemas import CritiqueResult
from src.orchestrator import Orchestrator


class MockLLM:
    """模拟 LLM，用于测试"""
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.model_name = "mock-model"

    def invoke(self, messages, **kwargs):
        response = MagicMock()
        response.content = (
            self.responses[self.call_count]
            if self.call_count < len(self.responses)
            else "默认回复"
        )
        response.usage_metadata = {"total_tokens": 100}
        self.call_count += 1
        return response


def create_mock_generator(responses):
    """创建使用 Mock LLM 的 Generator"""
    llm = MockLLM(responses=responses)
    return GeneratorAgent(domain="general", llm=llm)


def create_mock_critic(critique_results):
    """
    创建使用 Mock LLM 的 Critic
    critique_results: 依次返回的 CritiqueResult 列表
    """
    critic = CriticAgent(domain="general")
    # 直接 mock critique 方法
    call_count = [0]

    def mock_critique(task, draft):
        idx = call_count[0]
        result = (
            critique_results[idx]
            if idx < len(critique_results)
            else critique_results[-1]
        )
        call_count[0] += 1
        return result

    critic.critique = mock_critique
    return critic


class TestOrchestrator:
    """Orchestrator 测试"""

    def test_converge_by_score(self):
        """测试通过评分达标收敛"""
        generator = create_mock_generator(["产出1", "产出2"])
        # 第一轮评分低，第二轮评分达标
        critic = create_mock_critic([
            CritiqueResult(score=60, issues=["问题1"], acceptable=False),
            CritiqueResult(score=90, issues=[], acceptable=True),
        ])

        orchestrator = Orchestrator(
            max_rounds=5,
            generator=generator,
            critic=critic,
        )

        result = orchestrator.run("测试任务")

        assert result.converged is True
        assert "质量达标" in result.convergence_reason
        assert result.iterations == 2

    def test_converge_by_max_rounds(self):
        """测试达到最大轮数终止"""
        generator = create_mock_generator(["v1", "v2", "v3"])
        # 始终不达标
        critic = create_mock_critic([
            CritiqueResult(score=50, issues=["问题"], acceptable=False),
            CritiqueResult(score=55, issues=["问题"], acceptable=False),
            CritiqueResult(score=52, issues=["问题"], acceptable=False),
        ])

        orchestrator = Orchestrator(
            max_rounds=3,
            generator=generator,
            critic=critic,
        )

        result = orchestrator.run("测试任务")

        assert result.converged is False
        assert result.iterations == 3
        assert "最大轮数" in result.convergence_reason

    def test_converge_by_no_progress(self):
        """测试无新反馈收敛"""
        generator = create_mock_generator(["v1", "v2", "v3"])
        # 连续相同的问题
        same_critique = CritiqueResult(
            score=70, issues=["相同问题"], acceptable=False
        )
        critic = create_mock_critic([
            same_critique,
            same_critique,
            same_critique,
        ])

        orchestrator = Orchestrator(
            max_rounds=5,
            no_progress_rounds=2,
            generator=generator,
            critic=critic,
        )

        result = orchestrator.run("测试任务")

        assert result.converged is True
        assert "无新反馈" in result.convergence_reason

    def test_initial_draft(self):
        """测试使用初始草稿"""
        generator = create_mock_generator(["优化后版本"])
        critic = create_mock_critic([
            CritiqueResult(score=90, issues=[], acceptable=True),
        ])

        orchestrator = Orchestrator(
            max_rounds=3,
            generator=generator,
            critic=critic,
        )

        result = orchestrator.run("测试任务", initial_draft="初始草稿")

        # 初始草稿已经达标，应该直接收敛
        assert result.converged is True
        assert result.iterations == 1  # 只有初始审查那一轮

    def test_score_trend(self):
        """测试评分趋势记录"""
        generator = create_mock_generator(["v1", "v2", "v3"])
        critic = create_mock_critic([
            CritiqueResult(score=60, issues=["p1"], acceptable=False),
            CritiqueResult(score=75, issues=["p2"], acceptable=False),
            CritiqueResult(score=85, issues=[], acceptable=True),
        ])

        orchestrator = Orchestrator(
            max_rounds=5,
            generator=generator,
            critic=critic,
        )

        result = orchestrator.run("测试任务")

        assert result.score_trend == [60, 75, 85]

    def test_callback_invoked(self):
        """测试迭代完成回调"""
        callback_calls = []

        def on_complete(round_num, critique):
            callback_calls.append((round_num, critique.score))

        generator = create_mock_generator(["v1", "v2"])
        critic = create_mock_critic([
            CritiqueResult(score=70, issues=["p1"], acceptable=False),
            CritiqueResult(score=90, issues=[], acceptable=True),
        ])

        orchestrator = Orchestrator(
            max_rounds=5,
            generator=generator,
            critic=critic,
            on_iteration_complete=on_complete,
        )

        orchestrator.run("测试任务")

        assert len(callback_calls) == 2
        assert callback_calls[0] == (1, 70)
        assert callback_calls[1] == (2, 90)

    def test_best_draft_returned_when_not_converged(self):
        """测试未收敛时返回最优版本"""
        generator = create_mock_generator(["v1", "v2", "v3"])
        critic = create_mock_critic([
            CritiqueResult(score=60, issues=["p1"], acceptable=False),
            CritiqueResult(score=80, issues=["p2"], acceptable=False),  # 最优
            CritiqueResult(score=70, issues=["p3"], acceptable=False),
        ])

        orchestrator = Orchestrator(
            max_rounds=3,
            generator=generator,
            critic=critic,
        )

        result = orchestrator.run("测试任务")

        # 未收敛时应返回评分最高的版本（v2）
        assert result.final_output == "v2"
