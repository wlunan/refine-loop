"""代码任务的可审阅变更集。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChangeFile(BaseModel):
    path: str
    operation: Literal["added", "modified", "deleted"]


class ChangeSet(BaseModel):
    source_workspace: str
    worktree_path: str
    diff: str = ""
    files: list[ChangeFile] = Field(default_factory=list)
    status: Literal["pending", "applied", "discarded"] = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    decided_at: datetime | None = None
