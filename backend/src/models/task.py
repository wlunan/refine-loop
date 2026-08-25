"""
长时间运行任务的数据模型
支持任务分解、状态持久化、断点恢复
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"          # 等待执行
    PLANNING = "planning"        # 正在分解任务
    RUNNING = "running"          # 执行中
    PAUSED = "paused"            # 已暂停
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消


class FileChange(BaseModel):
    """文件变更记录"""
    path: str = Field(description="文件相对路径")
    operation: str = Field(description="操作类型: create/modify/delete")
    content_before: Optional[str] = Field(default=None, description="变更前内容")
    content_after: Optional[str] = Field(default=None, description="变更后内容")
    timestamp: datetime = Field(default_factory=datetime.now)


class SubTask(BaseModel):
    """子任务模型"""
    id: str = Field(description="唯一标识")
    title: str = Field(description="任务标题")
    description: str = Field(description="详细描述")
    dependencies: List[str] = Field(
        default_factory=list,
        description="依赖的子任务 ID 列表"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="当前状态"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="执行上下文（文件路径、变量等）"
    )
    result: Optional[str] = Field(
        default=None,
        description="执行结果摘要"
    )
    error: Optional[str] = Field(
        default=None,
        description="错误信息（失败时）"
    )
    iterations: int = Field(
        default=0,
        ge=0,
        description="实际迭代轮数"
    )
    score: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="最终评分"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    def mark_running(self) -> None:
        """标记为运行中"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, result: str, score: int) -> None:
        """标记为完成"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.score = score
        self.completed_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """标记为失败"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    @property
    def duration_seconds(self) -> Optional[float]:
        """执行时长（秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class TaskPlan(BaseModel):
    """任务执行计划"""
    requirement: str = Field(description="原始需求描述")
    analysis: str = Field(default="", description="需求分析")
    subtasks: List[SubTask] = Field(
        default_factory=list,
        description="子任务列表"
    )
    estimated_rounds: int = Field(
        default=0,
        ge=0,
        description="预估总迭代轮数"
    )
    created_at: datetime = Field(default_factory=datetime.now)

    def get_executable_subtasks(self) -> List[SubTask]:
        """获取当前可执行的子任务（依赖已完成）"""
        completed_ids = {
            st.id for st in self.subtasks
            if st.status == TaskStatus.COMPLETED
        }
        return [
            st for st in self.subtasks
            if st.status == TaskStatus.PENDING
            and all(dep in completed_ids for dep in st.dependencies)
        ]

    def get_subtask_by_id(self, subtask_id: str) -> Optional[SubTask]:
        """根据 ID 获取子任务"""
        for st in self.subtasks:
            if st.id == subtask_id:
                return st
        return None


class Checkpoint(BaseModel):
    """检查点 - 用于断点恢复"""
    task_id: str = Field(description="任务 ID")
    subtask_id: str = Field(description="子任务 ID")
    round: int = Field(ge=0, description="当前迭代轮次")
    draft: str = Field(default="", description="当前草稿")
    file_changes: List[FileChange] = Field(
        default_factory=list,
        description="文件变更记录"
    )
    tokens_used: int = Field(default=0, ge=0, description="已消耗 token 数")
    created_at: datetime = Field(default_factory=datetime.now)


class Task(BaseModel):
    """完整任务模型"""
    id: str = Field(description="唯一标识")
    title: str = Field(description="任务标题")
    description: str = Field(description="原始需求描述")
    workspace_dir: str = Field(description="工作目录")
    domain: str = Field(
        default="code",
        description="任务领域: code/writing/design"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="当前状态"
    )
    plan: Optional[TaskPlan] = Field(
        default=None,
        description="执行计划"
    )
    current_subtask_id: Optional[str] = Field(
        default=None,
        description="当前执行的子任务 ID"
    )
    error: Optional[str] = Field(
        default=None,
        description="任务级错误信息"
    )
    total_tokens: int = Field(
        default=0,
        ge=0,
        description="累计 token 消耗"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = Field(default=None)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="扩展字段"
    )

    def update_timestamp(self) -> None:
        """更新修改时间"""
        self.updated_at = datetime.now()

    @property
    def progress_percent(self) -> float:
        """进度百分比"""
        if not self.plan or not self.plan.subtasks:
            return 0.0
        completed = sum(
            1 for st in self.plan.subtasks
            if st.status == TaskStatus.COMPLETED
        )
        return (completed / len(self.plan.subtasks)) * 100

    @property
    def current_subtask(self) -> Optional[SubTask]:
        """当前执行的子任务"""
        if self.current_subtask_id and self.plan:
            return self.plan.get_subtask_by_id(self.current_subtask_id)
        return None

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.status == TaskStatus.RUNNING

    @property
    def is_finished(self) -> bool:
        """是否已结束（完成/失败/取消）"""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED
        )


class TaskProgress(BaseModel):
    """任务进度信息"""
    task_id: str
    status: TaskStatus
    progress_percent: float = Field(ge=0, le=100)
    current_subtask: Optional[str] = None
    completed_subtasks: int = 0
    total_subtasks: int = 0
    total_tokens: int = 0
    message: str = ""
