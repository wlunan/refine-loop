"""执行历史与恢复快照的持久化测试。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"),
)

from src.models.execution import ConversationMessage, ExecutionRecord, ExecutionSnapshot
from src.store.state_store import StateStore


def test_execution_history_round_trips_and_filters_by_attempt(tmp_path):
    store = StateStore(str(tmp_path / "state"))
    store.append_message(ConversationMessage(
        id="message-1",
        task_id="task-1",
        subtask_id="subtask-1",
        attempt_id="attempt-1",
        sequence=1,
        agent="generator",
        role="ai",
        content="generated",
    ))
    store.append_execution_record(ExecutionRecord(
        id="execution-1",
        task_id="task-1",
        subtask_id="subtask-1",
        attempt_id="attempt-1",
        sequence=2,
        phase="model_response",
        agent="critic",
        summary="reviewed",
    ))
    store.append_message(ConversationMessage(
        id="message-2",
        task_id="task-1",
        subtask_id="subtask-1",
        attempt_id="attempt-2",
        sequence=3,
        agent="generator",
        role="ai",
        content="resumed",
    ))

    assert [item.id for item in store.list_messages("task-1", "subtask-1")] == [
        "message-1",
        "message-2",
    ]
    assert [item.id for item in store.list_messages(
        "task-1", "subtask-1", attempt_id="attempt-1"
    )] == ["message-1"]
    assert store.list_execution_records("task-1", "subtask-1")[0].summary == "reviewed"


def test_execution_history_skips_corrupt_jsonl_line(tmp_path):
    store = StateStore(str(tmp_path / "state"))
    path = store._execution_subtask_dir("task-1", "subtask-1") / "messages.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "not-json\n"
        + ConversationMessage(
            id="message-1",
            task_id="task-1",
            subtask_id="subtask-1",
            attempt_id="attempt-1",
            sequence=1,
            agent="critic",
            role="ai",
            content="review",
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )

    messages = store.list_messages("task-1", "subtask-1")
    assert len(messages) == 1
    assert messages[0].content == "review"


def test_latest_execution_snapshot_is_replaced_atomically(tmp_path):
    store = StateStore(str(tmp_path / "state"))
    snapshot = ExecutionSnapshot(
        task_id="task-1",
        subtask_id="subtask-1",
        attempt_id="attempt-1",
        snapshot_id="snapshot-1",
        phase="round_committed",
        round=2,
        workspace_path="/workspace",
    )
    store.save_execution_snapshot(snapshot)

    loaded = store.load_latest_execution_snapshot("task-1", "subtask-1")
    assert loaded is not None
    assert loaded.snapshot_id == "snapshot-1"
    assert loaded.round == 2
    assert not list((tmp_path / "state").rglob("*.tmp"))
