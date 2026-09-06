"""
可观测性（Observability）基础设施

零第三方依赖的进程内可观测性，面向本地单进程代码 Agent 工作台：

1. 链路上下文：contextvars 为日志注入 request_id / task_id / subtask_id / round，
   使一次运行的日志可按 id 自动聚合，排障不再靠肉眼拼时间线。
2. 日志增强：ContextLogFilter 把上下文写入每条 record，EnrichedFormatter 兜底
   缺字段，避免个别 handler 未挂 filter 时因缺 key 抛错。
3. 指标聚合：线程安全的 Counter / Histogram / Gauge，可导出 Prometheus 文本
   （/metrics）或 JSON（/api/system/metrics）双份。

设计边界：
- 事件流（SSE / timeline / trace）是"事实记录"，本模块只做聚合，不重复记账，
  避免指标与事件口径不一致。
- 单进程工具不做分布式 tracing；未来需要多实例再接 OpenTelemetry。
"""

from __future__ import annotations

import contextvars
import logging
import threading
from typing import Callable, Dict, Iterable, Optional

# ---------------------------------------------------------------------------
# 链路上下文
# ---------------------------------------------------------------------------


class RunContext:
    """一次运行/请求的链路 id 集合（线程局部，经 contextvars 注入日志）。"""

    def __init__(self) -> None:
        self.request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
            "request_id", default="-"
        )
        self.task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
            "task_id", default="-"
        )
        self.subtask_id: contextvars.ContextVar[str] = contextvars.ContextVar(
            "subtask_id", default="-"
        )
        self.round: contextvars.ContextVar[int] = contextvars.ContextVar(
            "round", default=0
        )


_ctx = RunContext()


def set_request_id(value: str) -> None:
    """在请求作用域内设置 request_id（HTTP 中间件调用）。"""
    _ctx.request_id.set(value or "-")


def set_task_context(task_id: Optional[str]) -> None:
    """在任务执行线程内设置 task_id。"""
    _ctx.task_id.set(task_id or "-")


def set_subtask_context(subtask_id: Optional[str]) -> None:
    """在子任务执行线程内设置 subtask_id。"""
    _ctx.subtask_id.set(subtask_id or "-")


def set_round_context(round_num: Optional[int]) -> None:
    """在当前作用域内设置轮次（供编排层在每轮开始时调用）。"""
    _ctx.round.set(round_num or 0)


def reset_run_context() -> None:
    """清空当前线程的链路上下文（后台线程结束时调用，防止串场）。"""
    _ctx.request_id.set("-")
    _ctx.task_id.set("-")
    _ctx.subtask_id.set("-")
    _ctx.round.set(0)


class RunContextScope:
    """上下文管理器：批量设置并在退出时还原（供线程/作用域使用）。"""

    def __init__(
        self,
        task_id: Optional[str] = None,
        subtask_id: Optional[str] = None,
        round_num: Optional[int] = None,
    ) -> None:
        self._patch = (task_id, subtask_id, round_num)
        self._tokens: list = []

    def __enter__(self) -> "RunContextScope":
        task_id, subtask_id, round_num = self._patch
        if task_id is not None:
            self._tokens.append(_ctx.task_id.set(task_id))
        if subtask_id is not None:
            self._tokens.append(_ctx.subtask_id.set(subtask_id))
        if round_num is not None:
            self._tokens.append(_ctx.round.set(round_num))
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        for token in reversed(self._tokens):
            try:
                token.var.reset(token)
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# 日志增强：把链路上下文带进每一条日志
# ---------------------------------------------------------------------------

# 日志格式：时间 级别 request|task|subtask|round logger: message
LOG_TRACE_FORMAT = (
    "%(asctime)s [%(levelname)s] %(request_id)s|%(task_id)s|%(subtask_id)s"
    "|%(round)s %(name)s: %(message)s"
)


class ContextLogFilter(logging.Filter):
    """把当前线程的链路上下文写入 record，供 formatter 渲染。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _ctx.request_id.get()
        record.task_id = _ctx.task_id.get()
        record.subtask_id = _ctx.subtask_id.get()
        record.round = _ctx.round.get()
        return True


class EnrichedFormatter(logging.Formatter):
    """兜底 formatter：record 缺上下文字段时填充占位值，避免 handler 抛 KeyError。"""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "task_id"):
            record.task_id = "-"
        if not hasattr(record, "subtask_id"):
            record.subtask_id = "-"
        if not hasattr(record, "round"):
            record.round = 0
        return super().format(record)


# ---------------------------------------------------------------------------
# 指标聚合
# ---------------------------------------------------------------------------


class MetricsRegistry:
    """进程内线程安全指标聚合器。

    支持三类基础指标：
    - Counter：单调累加（llm_calls_total、tasks_finished_total 等）
    - Histogram：分布采样（耗时），导出 bucket/count/sum
    - Gauge：动态取值（active_tasks 等，经注册函数实时读取）
    """

    BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, Dict[frozenset, float]] = {}
        self._counter_labels: Dict[str, Dict[frozenset, Dict[str, str]]] = {}
        # histogram 每个 series 存: labels / buckets(le->count) / sum / count
        self._histograms: Dict[str, Dict[frozenset, Dict]] = {}
        self._gauge_fns: Dict[str, Callable[[], float]] = {}
        self._help: Dict[str, str] = {}

    def set_help(self, name: str, help: str) -> None:  # noqa: A002
        self._help[name] = help

    # -- Counter ----------------------------------------------------------
    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        """计数器累加，支持任意 label 维度。"""
        with self._lock:
            series = self._counters.setdefault(name, {})
            label_store = self._counter_labels.setdefault(name, {})
            key = frozenset(labels.items())
            series[key] = series.get(key, 0.0) + amount
            label_store.setdefault(key, dict(labels))

    # -- Histogram --------------------------------------------------------
    def observe(self, name: str, value: float, **labels: str) -> None:
        """观察一个样本，按 bucket 累计分布。"""
        with self._lock:
            series = self._histograms.setdefault(name, {})
            key = frozenset(labels.items())
            record = series.get(key)
            if record is None:
                record = {
                    "labels": dict(labels),
                    "buckets": {le: 0.0 for le in self.BUCKETS},
                    "sum": 0.0,
                    "count": 0,
                }
                series[key] = record
            record["count"] += 1
            record["sum"] += value
            for le in self.BUCKETS:
                if value <= le:
                    record["buckets"][le] += 1.0

    # -- Gauge ------------------------------------------------------------
    def register_gauge(self, name: str, fn: Callable[[], float], help: str = "") -> None:  # noqa: A002
        """注册一个动态读取的 gauge（渲染/导出时实时求值）。"""
        self._gauge_fns[name] = fn
        if help:
            self._help[name] = help

    def _gauge_value(self, name: str) -> float:
        fn = self._gauge_fns.get(name)
        if fn is None:
            return 0.0
        try:
            return float(fn())
        except Exception:  # noqa: BLE001
            return 0.0

    # -- 导出 --------------------------------------------------------------
    @staticmethod
    def _escape_label(value: str) -> str:
        return (
            value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        )

    @staticmethod
    def _label_str(labels: Dict[str, str]) -> str:
        if not labels:
            return ""
        inner = ",".join(
            f'{k}="{MetricsRegistry._escape_label(str(v))}"'
            for k, v in sorted(labels.items())
        )
        return "{" + inner + "}"

    def _help_type_lines(self, name: str, kind: str) -> list[str]:
        return [
            f"# HELP {name} {self._help.get(name, '')}",
            f"# TYPE {name} {kind}",
        ]

    def render_text(self) -> str:
        """渲染 Prometheus 文本格式（OpenMetrics v0.0.4 子集）。"""
        lines: list[str] = []

        for name in sorted(self._counters):
            lines.extend(self._help_type_lines(name, "counter"))
            for key, value in self._counters[name].items():
                labels = self._counter_labels[name][key]
                lines.append(f"{name}{self._label_str(labels)} {value}")

        for name in sorted(self._histograms):
            lines.extend(self._help_type_lines(name, "histogram"))
            for key, record in self._histograms[name].items():
                labels = self._label_str(record["labels"])
                base = name if not labels else f"{name}{labels}"
                buckets = record["buckets"]
                for le in self.BUCKETS:
                    bucket_labels = self._label_str(
                        {**record["labels"], "le": str(le)}
                    )
                    lines.append(
                        f"{name}_bucket{bucket_labels} {buckets[le]}"
                    )
                lines.append(f"{name}_sum{labels} {record['sum']}")
                lines.append(f"{name}_count{labels} {record['count']}")

        for name in sorted(self._gauge_fns):
            lines.extend(self._help_type_lines(name, "gauge"))
            lines.append(f"{name} {self._gauge_value(name)}")

        return "\n".join(lines) + "\n"

    def snapshot_json(self) -> dict:
        """输出 JSON 快照，供前端统计卡 / 调试页面直接消费。"""
        with self._lock:
            counters = [
                {
                    "name": name,
                    "labels": self._counter_labels[name][key],
                    "value": value,
                }
                for name, series in sorted(self._counters.items())
                for key, value in sorted(
                    series.items(),
                    key=lambda item: sorted(item[0]),
                )
            ]
            histograms = [
                {
                    "name": name,
                    "labels": record["labels"],
                    "count": record["count"],
                    "sum": record["sum"],
                }
                for name, series in sorted(self._histograms.items())
                for record in series.values()
            ]
            gauges = {
                name: self._gauge_value(name)
                for name in sorted(self._gauge_fns)
            }
        return {"counters": counters, "histograms": histograms, "gauges": gauges}


metrics = MetricsRegistry()


# ---------------------------------------------------------------------------
# LLM 调用指标埋点助手（供 BaseAgent 调用）
# ---------------------------------------------------------------------------


def record_llm_call(
    agent: str,
    model: str,
    *,
    ok: bool,
    duration_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """记录一次 LLM 调用：次数/状态/耗时/token。线程安全，可随时调用。"""
    model = model or "unknown"
    metrics.inc("llm_calls_total", agent=agent, model=model, status="ok" if ok else "error")
    metrics.observe("llm_call_duration_seconds", duration_seconds, agent=agent, model=model)
    if ok:
        if prompt_tokens:
            metrics.inc("llm_prompt_tokens_total", prompt_tokens, agent=agent, model=model)
        if completion_tokens:
            metrics.inc("llm_completion_tokens_total", completion_tokens, agent=agent, model=model)


def usage_tokens(usage: Optional[dict]) -> tuple[int, int]:
    """从 OpenAI 兼容的 usage_metadata 解析 (prompt_tokens, completion_tokens)。

    兼容 langchain usage_metadata 的 input_tokens/output_tokens 与
    openai 的 prompt_tokens/completion_tokens 两种命名。
    """
    if not usage:
        return 0, 0
    prompt = int(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or 0
    )
    completion = int(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or 0
    )
    return prompt, completion
