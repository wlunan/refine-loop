"""ToolAgent 工具生命周期持久化测试。"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"),
)

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from src.agents.tool_agent import ToolAgent
from src.models.execution import ToolAgentState
from src.store.state_store import StateStore


def echo(value: str) -> str:
    """Echo a value."""
    return value


class ToolCallLLM:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "echo",
                    "args": {"value": "ok"},
                    "id": "call-1",
                    "type": "tool_call",
                }],
            )
        return AIMessage(content="done")


def test_tool_agent_state_contains_completed_tool_call():
    states = []
    agent = ToolAgent(
        ToolCallLLM(),
        [StructuredTool.from_function(echo)],
        "system",
        checkpoint_callback=states.append,
    )

    assert agent.run("task") == "done"
    completed = states[-1].completed_tools
    assert len(completed) == 1
    assert completed[0].call_id == "call-1"
    assert completed[0].status == "completed"
    assert completed[0].idempotency_key.startswith("echo:")


def test_task_executor_persists_tool_records_without_duplicates(tmp_path):
    from src.executor.task_executor import TaskExecutor
    from src.models.schemas import CritiqueResult
    from src.tools.filesystem import FileWorkspace

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

    agent = ToolAgent(
        ToolCallLLM(),
        [StructuredTool.from_function(echo)],
        "system",
    )
    states = []
    agent.checkpoint_callback = states.append
    agent.run("task")
    state = states[-1]
    executor._on_tool_checkpoint("task-1", "subtask-1", state)
    executor._on_tool_checkpoint("task-1", "subtask-1", state)

    records = store.list_tool_records("task-1", "subtask-1")
    assert len(records) == 1
    snapshot = store.load_latest_execution_snapshot("task-1", "subtask-1")
    assert snapshot is not None
    assert snapshot.messages[-1].role == "ai"
    assert ToolAgentState(messages=snapshot.messages).messages[-1].content == "done"
