"""上下文管理（消息滑窗 / 焦点快照 / 失败证据摘要）单元测试。"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"),
)

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agents.tool_agent import ToolAgent
from src.models.run import VerificationResult, VerificationSummary
from src.tools.filesystem import FileWorkspace
from src.tools.verification import CommandResult


def _make_agent(**kwargs):
    return ToolAgent(
        llm=MagicMock(),
        tools=[],
        system_prompt="sys",
        **kwargs,
    )


class TestToolAgentSlidingWindow:
    def test_long_tool_result_truncated(self):
        agent = _make_agent(keep_recent_rounds=0, max_tool_result_chars=50)
        messages = [
            SystemMessage(content="sys"),
            HumanMessage(content="task"),
            AIMessage(content="do it", tool_calls=[{"name": "read_file", "args": {"path": "a.py"}, "id": "c1"}]),
            ToolMessage(content="x" * 300, tool_call_id="c1"),
        ]
        agent._trim_messages(messages)
        assert len(messages) == 4  # 只截断单条内容，不删消息
        assert "已截断" in messages[-1].content
        assert len(messages[-1].content) < 200

    def test_oldest_turns_dropped_but_system_and_task_kept(self):
        agent = _make_agent(keep_recent_rounds=2, max_tool_result_chars=0)
        messages = [
            SystemMessage(content="sys"),
            HumanMessage(content="task: fix bug"),
            AIMessage(content="call1", tool_calls=[{"name": "write_file", "args": {}, "id": "c1"}]),
            ToolMessage(content="r1", tool_call_id="c1"),
            AIMessage(content="call2", tool_calls=[{"name": "write_file", "args": {}, "id": "c2"}]),
            ToolMessage(content="r2", tool_call_id="c2"),
            AIMessage(content="call3", tool_calls=[{"name": "run_tests", "args": {}, "id": "c3"}]),
            ToolMessage(content="r3", tool_call_id="c3"),
            AIMessage(content="final answer"),
        ]
        agent._trim_messages(messages)
        roles = [type(m).__name__ for m in messages]
        # 最早一轮 (call1/r1) 被剔除
        assert "r1" not in [m.content for m in messages]
        # 身份与任务保留
        assert messages[0].content == "sys"
        assert any(isinstance(m, HumanMessage) and "task" in m.content for m in messages)
        # 最近两个 AI 回合 + 最终消息仍在
        assert any(m.content == "r3" for m in messages)
        assert any(m.content == "final answer" for m in messages)
        assert roles[-1] == "AIMessage"

    def test_no_trim_when_under_window(self):
        agent = _make_agent(keep_recent_rounds=10, max_tool_result_chars=0)
        messages = [
            SystemMessage(content="sys"),
            HumanMessage(content="task"),
            AIMessage(content="call1"),
            ToolMessage(content="r1", tool_call_id="c1"),
        ]
        original = list(messages)
        agent._trim_messages(messages)
        assert len(messages) == len(original)


class TestFailureEvidenceSummaries:
    def test_verification_result_failure_summary_concise(self):
        result = VerificationResult(
            step_id="pytest",
            label="pytest",
            required=True,
            passed=False,
            exit_code=1,
            stdout=(
                "===== short test summary =====\n"
                "1 passed, 1 failed\n"
                "collecting ... done\n"
                ">       assert 1 == 2\n"
                + "noise" * 200
            ),
            stderr="Traceback (most recent call last):\nE   assert 1 == 2",
        )
        summary = result.failure_summary()
        assert "退出码: 1" in summary
        assert "assert" in summary
        # 长噪音与"短汇总"类整段输出被丢弃
        assert "noise" * 200 not in summary

    def test_verification_summary_evidence_uses_summary_not_full_stdout(self):
        result = VerificationResult(
            step_id="pytest",
            label="pytest",
            required=True,
            passed=False,
            exit_code=1,
            stdout="full stdout payload here " + "z" * 5000,
        )
        summary = VerificationSummary(profile="python_pytest", results=[result])
        evidence = summary.evidence()
        assert "失败要点" in evidence
        assert "z" * 5000 not in evidence

    def test_command_result_failure_summary(self):
        result = CommandResult(
            command="pytest -q",
            exit_code=1,
            stdout="1 passed, 1 failed\nFAILED tests/test_x.py::test_boom\n"
            ">       assert 0 == 1\nnormal line\n",
        )
        compact = result.failure_summary()
        assert "FAILED tests/test_x.py::test_boom" in compact
        assert "normal line" not in compact


class TestFocusedSnapshot:
    def test_focus_files_come_first(self, tmp_path):
        ws = FileWorkspace(str(tmp_path))
        for name in ("a.py", "b.py", "c.py"):
            (tmp_path / name).write_text(f"content of {name}\n", encoding="utf-8")
        snap = ws.snapshot_focused(["b.py"], budget_chars=200_000)
        assert snap.index("===== 文件: b.py =====") < snap.index("===== 文件: a.py =====")
        assert "文件清单" in snap
        assert "3 个文本文件" in snap

    def test_budget_bounds_content(self, tmp_path):
        ws = FileWorkspace(str(tmp_path))
        for name in ("a.py", "b.py", "c.py"):
            (tmp_path / name).write_text("content line\n" * 200, encoding="utf-8")
        snap = ws.snapshot_focused(["b.py"], budget_chars=300)
        assert "已展示" in snap  # 超预算时明确标注省略
