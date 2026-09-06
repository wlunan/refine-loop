"""可观测性基础设施单元测试（离线、无 LLM 依赖）。"""

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"),
)

import logging

from src.observability import (
    ContextLogFilter,
    EnrichedFormatter,
    MetricsRegistry,
    RunContextScope,
    LOG_TRACE_FORMAT,
    set_request_id,
    set_round_context,
    set_task_context,
    usage_tokens,
    _ctx,  # noqa: PLC2701 —— 测试读取 contextvar 当前值
)


class TestMetricsRegistry:
    def test_counter_inc_and_labels(self):
        m = MetricsRegistry()
        m.inc("calls", agent="generator", model="m1")
        m.inc("calls", agent="generator", model="m1")
        m.inc("calls", agent="critic", model="m2")
        snap = m.snapshot_json()
        counters = {
            (s["name"], s["labels"]["agent"]): s["value"]
            for s in snap["counters"]
        }
        assert counters[("calls", "generator")] == 2
        assert counters[("calls", "critic")] == 1

    def test_histogram_observe(self):
        m = MetricsRegistry()
        m.observe("latency", 0.2, agent="generator")
        m.observe("latency", 1.5, agent="generator")
        snap = m.snapshot_json()
        hist = [h for h in snap["histograms"] if h["name"] == "latency"][0]
        assert hist["count"] == 2
        assert hist["sum"] == 1.7

    def test_gauge_dynamic(self):
        m = MetricsRegistry()
        m.register_gauge("active_tasks", lambda: 3)
        assert m.snapshot_json()["gauges"]["active_tasks"] == 3

    def test_render_text_has_type_lines(self):
        m = MetricsRegistry()
        m.inc("calls", agent="generator", model="m1")
        text = m.render_text()
        assert "# TYPE calls counter" in text
        assert 'calls{agent="generator",model="m1"} 1.0' in text


class TestLogEnrichment:
    @staticmethod
    def _make_record(message="hello"):
        return logging.LogRecord(
            name="x", level=logging.INFO, pathname=__file__, lineno=1,
            msg=message, args=(), exc_info=None,
        )

    def test_formatter_survives_missing_attributes(self):
        formatter = EnrichedFormatter(fmt=LOG_TRACE_FORMAT)
        line = formatter.format(self._make_record())
        assert "hello" in line
        assert "|" in line  # request|task|subtask|round 段存在

    def test_context_filter_injects_current_ids(self):
        f = ContextLogFilter()
        record = self._make_record()
        set_request_id("req_1")
        set_task_context("task_9")
        set_round_context(3)
        assert f.filter(record) is True
        assert record.request_id == "req_1"
        assert record.task_id == "task_9"
        assert record.round == 3

    def test_scope_restores_previous_value(self):
        set_task_context("old")
        with RunContextScope(task_id="new"):
            assert _ctx.task_id.get() == "new"
        assert _ctx.task_id.get() == "old"


def test_usage_tokens_supports_both_namings():
    assert usage_tokens({"input_tokens": 10, "output_tokens": 20}) == (10, 20)
    assert usage_tokens({"prompt_tokens": 3, "completion_tokens": 4}) == (3, 4)
    assert usage_tokens(None) == (0, 0)
