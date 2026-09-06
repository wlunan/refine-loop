"""Agent 执行历史与恢复状态模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MessageRole = Literal["system", "human", "ai", "tool"]
ExecutionAgent = Literal["generator", "critic", "tool_agent", "orchestrator"]
ExecutionPhase = Literal[
    "model_call",
    "model_response",
    "tool_call",
    "tool_result",
    "verification",
    "checkpoint",
    "state_change",
]


class ConversationMessage(BaseModel):
    """可跨 LangChain 版本持久化的消息记录。"""

    id: str
    task_id: str = ""
    subtask_id: str = ""
    attempt_id: str = ""
    sequence: int = Field(ge=0)
    agent: ExecutionAgent
    role: MessageRole
    content: str | list[dict[str, Any]]
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    name: str | None = None
    round: int = Field(default=0, ge=0)
    step: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.now)


class ExecutionRecord(BaseModel):
    """一次模型、工具、验证或状态动作的追加式记录。"""

    id: str
    task_id: str
    subtask_id: str
    attempt_id: str
    sequence: int = Field(ge=0)
    phase: ExecutionPhase
    agent: ExecutionAgent
    round: int = Field(default=0, ge=0)
    step: int = Field(default=0, ge=0)
    summary: str = ""
    message_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class ExecutionSnapshot(BaseModel):
    """恢复入口使用的轻量执行快照。"""

    task_id: str
    subtask_id: str
    attempt_id: str
    snapshot_id: str
    phase: str
    round: int = Field(default=0, ge=0)
    step: int = Field(default=0, ge=0)
    workspace_path: str
    message_sequence: int = Field(default=0, ge=0)
    execution_sequence: int = Field(default=0, ge=0)
    messages: list[ConversationMessage] = Field(default_factory=list)
    resumable: bool = True
    recovery_note: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class ToolAgentState(BaseModel):
    """可序列化的 ToolAgent 中间状态，用于暂停后恢复模型上下文。"""

    messages: list[ConversationMessage] = Field(default_factory=list)
    current_step: int = Field(default=0, ge=0)
    phase: str = "generating"
    resumable: bool = True
