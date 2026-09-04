"""
Orchestrator 单元测试
使用 Mock LLM 测试编排器的迭代流程和收敛逻辑
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from unittest.mock import MagicMock

import pytest

from src.agents.critic import CriticAgent
from src.agents.generator import GeneratorAgent
from src.models.schemas import CritiqueResult
from src.models.run import RunConfig, VerificationStep
from src.models.task import SubTask, TaskStatus
from src.orchestrator import Orchestrator
from src.executor.task_executor import TaskContext, TaskExecutor
from src.store.state_store import StateStore
from src.tools.filesystem import FileWorkspace


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
        # 始终不达标，且每轮问题不同（避免触发「无新反馈」收敛）
        critic = create_mock_critic([
            CritiqueResult(score=50, issues=["问题1"], acceptable=False),
            CritiqueResult(score=55, issues=["问题2"], acceptable=False),
            CritiqueResult(score=52, issues=["问题3"], acceptable=False),
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

    def test_file_mode_requires_verification_even_with_high_critic_score(self, tmp_path):
        """配置验证后，Critic 高分不能绕过真实命令失败。"""
        class FileGenerator:
            total_tokens_used = 0

            def generate_with_files(self, task, workspace_dir, on_event=None):
                Path(workspace_dir, "generated.py").write_text("value = 1\n", encoding="utf-8")

        critic = create_mock_critic([
            CritiqueResult(score=100, issues=[], acceptable=True),
            CritiqueResult(score=100, issues=[], acceptable=True),
        ])
        config = RunConfig(
            max_rounds=2,
            score_threshold=85,
            verification_profile="none",
            verification_steps=[VerificationStep(
                id="always_fail",
                label="always fail",
                command=f'"{sys.executable}" -c "import sys; sys.exit(1)"',
            )],
        )
        verification_events = []
        orchestrator = Orchestrator(
            generator=FileGenerator(),
            critic=critic,
            run_config=config,
            on_verification_complete=lambda round_num, summary: verification_events.append(
                (round_num, summary.passed)
            ),
        )

        result = orchestrator.run_with_files("create a file", str(tmp_path))

        assert result.converged is False
        assert result.iterations == 2
        assert result.verification_summary is not None
        assert result.verification_summary.passed is False
        assert verification_events == [(1, False), (2, False)]

    def test_task_executor_persists_failed_verification_and_marks_subtask_failed(self, tmp_path):
        """长任务主链路保存验证检查点，验证耗尽后不能标记完成。"""
        class FileGenerator:
            total_tokens_used = 0

            def generate_with_files(self, task, workspace_dir, on_event=None):
                Path(workspace_dir, "generated.py").write_text("value = 1\n", encoding="utf-8")

        config = RunConfig(
            max_rounds=1,
            score_threshold=85,
            verification_steps=[VerificationStep(
                id="always_fail",
                label="always fail",
                command=f'"{sys.executable}" -c "import sys; sys.exit(1)"',
            )],
        )
        workspace = FileWorkspace(str(tmp_path))
        store = StateStore(str(tmp_path / "state"))
        executor = TaskExecutor(
            workspace=workspace,
            store=store,
            generator=FileGenerator(),
            critic=create_mock_critic([CritiqueResult(score=100, issues=[], acceptable=True)]),
            run_config=config,
        )
        subtask = SubTask(id="subtask_1", title="write file", description="write generated.py")

        result = executor.execute(
            subtask,
            TaskContext(workspace),
            task_id="task_verification",
        )
        checkpoints = store.list_checkpoints("task_verification", "subtask_1")

        assert result.status == TaskStatus.FAILED
        assert len(checkpoints) == 1
        assert checkpoints[0].verification_summary is not None
        assert checkpoints[0].verification_summary.passed is False
