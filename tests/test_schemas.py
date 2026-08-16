"""
数据模型单元测试
测试 schemas.py 中的所有数据结构
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.models.schemas import (
    AgentRole,
    CritiqueResult,
    IterationRecord,
    AgentState,
    Message,
)


class TestCritiqueResult:
    """CritiqueResult 测试"""

    def test_create_valid_result(self):
        """测试创建合法的审查结果"""
        result = CritiqueResult(
            score=85,
            issues=["问题1"],
            suggestions=["建议1"],
            acceptable=True,
        )
        assert result.score == 85
        assert len(result.issues) == 1
        assert result.acceptable is True

    def test_score_range(self):
        """测试评分范围校验"""
        with pytest.raises(ValueError):
            CritiqueResult(score=101)  # 超过上限
        with pytest.raises(ValueError):
            CritiqueResult(score=-1)  # 低于下限

    def test_acceptable_with_low_score(self):
        """测试 acceptable=True 但分数过低时的校验"""
        with pytest.raises(ValueError):
            CritiqueResult(score=50, acceptable=True)

    def test_has_issues(self):
        """测试 has_issues 方法"""
        result_with_issues = CritiqueResult(score=60, issues=["问题1"])
        assert result_with_issues.has_issues() is True

        result_no_issues = CritiqueResult(score=90, issues=[])
        assert result_no_issues.has_issues() is False

    def test_issues_match(self):
        """测试 issues_match 方法"""
        result1 = CritiqueResult(score=70, issues=["问题A", "问题B"])
        result2 = CritiqueResult(score=75, issues=["问题B", "问题A"])
        result3 = CritiqueResult(score=80, issues=["问题A"])

        # 相同问题（顺序不同）应匹配
        assert result1.issues_match(result2) is True
        # 不同问题不应匹配
        assert result1.issues_match(result3) is False

    def test_default_values(self):
        """测试默认值"""
        result = CritiqueResult()
        assert result.score == 0
        assert result.issues == []
        assert result.suggestions == []
        assert result.acceptable is False
        assert result.summary is None


class TestAgentState:
    """AgentState 测试"""

    def test_create_state(self):
        """测试创建状态"""
        state = AgentState(task="测试任务", max_rounds=3)
        assert state.task == "测试任务"
        assert state.current_round == 0
        assert state.converged is False
        assert state.history == []

    def test_max_rounds_range(self):
        """测试最大轮数范围"""
        with pytest.raises(ValueError):
            AgentState(task="测试", max_rounds=0)
        with pytest.raises(ValueError):
            AgentState(task="测试", max_rounds=21)

    def test_add_iteration(self):
        """测试添加迭代记录"""
        state = AgentState(task="测试")
        record = IterationRecord(
            round=1,
            draft="草稿",
            critique=CritiqueResult(score=80),
        )
        state.add_iteration(record)
        assert len(state.history) == 1
        assert state.history[0].round == 1

    def test_get_best_draft(self):
        """测试获取最优版本"""
        state = AgentState(task="测试")
        state.add_iteration(IterationRecord(
            round=1, draft="版本1", critique=CritiqueResult(score=70)
        ))
        state.add_iteration(IterationRecord(
            round=2, draft="版本2", critique=CritiqueResult(score=90)
        ))
        state.add_iteration(IterationRecord(
            round=3, draft="版本3", critique=CritiqueResult(score=85)
        ))

        best = state.get_best_draft()
        assert best == "版本2"  # 评分最高的版本

    def test_get_best_draft_empty_history(self):
        """测试历史为空时获取最优版本"""
        state = AgentState(task="测试", draft="当前草稿")
        assert state.get_best_draft() == "当前草稿"

    def test_get_score_trend(self):
        """测试获取评分趋势"""
        state = AgentState(task="测试")
        state.add_iteration(IterationRecord(
            round=1, draft="v1", critique=CritiqueResult(score=60)
        ))
        state.add_iteration(IterationRecord(
            round=2, draft="v2", critique=CritiqueResult(score=80)
        ))
        assert state.get_score_trend() == [60, 80]


class TestMessage:
    """Message 测试"""

    def test_create_message(self):
        """测试创建消息"""
        msg = Message(role=AgentRole.GENERATOR, content="测试内容", round=1)
        assert msg.role == "generator"
        assert msg.content == "测试内容"
        assert msg.round == 1


class TestIterationRecord:
    """IterationRecord 测试"""

    def test_create_record(self):
        """测试创建迭代记录"""
        record = IterationRecord(
            round=1,
            draft="草稿",
            critique=CritiqueResult(score=80),
            duration_seconds=1.5,
        )
        assert record.round == 1
        assert record.duration_seconds == 1.5

    def test_duration_non_negative(self):
        """测试耗时不能为负"""
        with pytest.raises(ValueError):
            IterationRecord(
                round=1,
                draft="草稿",
                critique=CritiqueResult(score=80),
                duration_seconds=-1,
            )
