"""
数据模型定义模块
包含 Generator-Critic 系统中所有核心数据结构
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class AgentRole(str, Enum):
    """Agent 角色枚举"""
    GENERATOR = "generator"
    CRITIC = "critic"
    ORCHESTRATOR = "orchestrator"
    USER = "user"


class Message(BaseModel):
    """对话消息"""
    role: AgentRole
    content: str
    round: int = Field(default=0, ge=0, description="当前迭代轮次")
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class CritiqueResult(BaseModel):
    """
    Critic 的审查结果
    这是系统中最核心的结构化输出，用于驱动迭代收敛
    """
    score: int = Field(
        default=0,
        ge=0,
        le=100,
        description="质量评分，0-100 分"
    )
    issues: List[str] = Field(
        default_factory=list,
        description="发现的问题列表，每条问题应具体可定位"
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="针对问题的修改建议，每条建议应可操作"
    )
    acceptable: bool = Field(
        default=False,
        description="是否达到可接受标准，达到则终止迭代"
    )
    summary: Optional[str] = Field(
        default=None,
        description="审查总结（可选）"
    )

    @field_validator("acceptable")
    @classmethod
    def check_acceptable_consistency(cls, v: bool, info) -> bool:
        """校验 acceptable 与 score 的一致性"""
        score = info.data.get("score", 0)
        if v and score < 60:
            raise ValueError("acceptable=True 时 score 不应低于 60")
        return v

    def has_issues(self) -> bool:
        """是否存在问题"""
        return len(self.issues) > 0

    def issues_match(self, other: "CritiqueResult") -> bool:
        """
        判断与另一轮审查的问题是否完全相同
        用于检测"无新反馈"的收敛条件
        """
        return set(self.issues) == set(other.issues)


class IterationRecord(BaseModel):
    """单轮迭代记录，用于历史追溯"""
    round: int
    draft: str
    critique: CritiqueResult
    duration_seconds: float = Field(default=0.0, ge=0)


class AgentState(BaseModel):
    """
    Agent 系统全局状态
    在 LangGraph 中作为共享状态在节点间传递
    """
    task: str = Field(description="用户原始任务描述")
    domain: str = Field(
        default="general",
        description="任务领域，如 code/writing/design，用于选择 prompt"
    )
    draft: str = Field(default="", description="当前最新的生成产出")
    critique: Optional[CritiqueResult] = Field(
        default=None,
        description="当前最新的审查结果"
    )
    current_round: int = Field(default=0, ge=0, description="当前迭代轮次")
    max_rounds: int = Field(
        default=5,
        ge=1,
        le=20,
        description="最大迭代轮数，防止成本爆炸"
    )
    history: List[IterationRecord] = Field(
        default_factory=list,
        description="完整迭代历史记录"
    )
    converged: bool = Field(
        default=False,
        description="是否已收敛（达到终止条件）"
    )
    convergence_reason: Optional[str] = Field(
        default=None,
        description="收敛原因说明"
    )
    total_tokens: int = Field(default=0, ge=0, description="累计 token 消耗")

    def add_iteration(self, record: IterationRecord) -> None:
        """添加一轮迭代记录"""
        self.history.append(record)

    def get_best_draft(self) -> str:
        """
        获取历史中评分最高的版本
        当最终未收敛时，返回最优版本而非最后一版
        """
        if not self.history:
            return self.draft
        best = max(self.history, key=lambda r: r.critique.score)
        return best.draft

    def get_score_trend(self) -> List[int]:
        """获取评分趋势，用于分析迭代效果"""
        return [r.critique.score for r in self.history]
