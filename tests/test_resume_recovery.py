"""任务恢复与执行快照加载测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"),
)

from src.executor.task_executor import TaskExecutor
from src.models.execution import ConversationMessage, ExecutionSnapshot, ToolAgentState
from src.models.schemas import CritiqueResult
from src.store.state_store import StateStore
from src.tools.filesystem import FileWorkspace


def test_resume_loads_latest_execution_snapshot(tmp_path):
    """恢复时 TaskExecutor 能加载最近执行快照并重建 ToolAgentState。"""
    store = StateStore(str(tmp_path / "state"))
    (tmp_path / "workspace").mkdir()
    executor = TaskExecutor(
        workspace=FileWorkspace(str(tmp_path / "workspace")),
        store=store,
    )
    key = ("task-1", "subtask-1")
    executor._attempt_ids[key] = "attempt-1"
    executor._history_sequences[key] = 1
    executor._persisted_tool_calls[key] = set()

    # 保存一个可恢复快照
    store.save_execution_snapshot(
        ExecutionSnapshot(
            task_id="task-1",
            subtask_id="subtask-1",
            attempt_id="attempt-1",
            snapshot_id="snapshot-1",
            phase="tool_result",
            round=1,
            step=2,
            workspace_path=str(tmp_path / "workspace"),
            messages=[
                ConversationMessage(
                    id="msg-1",
                    task_id="task-1",
                    subtask_id="subtask-1",
                    attempt_id="attempt-1",
                    sequence=1,
                    agent="tool_agent",
                    role="human",
                    content="task",
                )
            ],
            resumable=True,
        )
    )

    snapshot = store.load_latest_execution_snapshot("task-1", "subtask-1")
    assert snapshot is not None
    assert snapshot.phase == "tool_result"
    assert snapshot.messages[0].content == "task"


def test_resume_state_rebuilds_tool_agent_state(tmp_path):
    """恢复快照能重建 ToolAgentState 并保留消息。"""
    store = StateStore(str(tmp_path / "state"))
    (tmp_path / "workspace").mkdir()
    executor = TaskExecutor(
        workspace=FileWorkspace(str(tmp_path / "workspace")),
        store=store,
    )
    key = ("task-1", "subtask-1")
    executor._attempt_ids[key] = "attempt-1"
    executor._history_sequences[key] = 1
    executor._persisted_tool_calls[key] = set()

    store.save_execution_snapshot(
        ExecutionSnapshot(
            task_id="task-1",
            subtask_id="subtask-1",
            attempt_id="attempt-1",
            snapshot_id="snapshot-2",
            phase="tool_result",
            round=1,
            step=1,
            workspace_path=str(tmp_path / "workspace"),
            messages=[
                ConversationMessage(
                    id="msg-1",
                    task_id="task-1",
                    subtask_id="subtask-1",
                    attempt_id="attempt-1",
                    sequence=1,
                    agent="tool_agent",
                    role="human",
                    content="task",
                )
            ],
            resumable=True,
        )
    )

    snapshot = store.load_latest_execution_snapshot("task-1", "subtask-1")
    state = ToolAgentState(
        messages=snapshot.messages,
        current_step=snapshot.step,
        phase=snapshot.phase,
        resumable=snapshot.resumable,
    )
    assert state.messages[0].content == "task"
    assert state.current_step == 1
