"""Versioned, machine-readable benchmark run artifacts."""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .runner import TaskResult

BENCHMARK_VERSION = "2026.09.06.v2"
ARTIFACT_SCHEMA_VERSION = 1


def build_run_artifact(
    results: Iterable[TaskResult],
    *,
    max_repair_rounds: int,
) -> dict:
    """Create the raw evidence record used by reports and resume claims."""
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "max_repair_rounds": max_repair_rounds,
        },
        "results": [
            {
                "task_name": result.task_name,
                "baseline": result.baseline.__dict__,
                "self_healing": result.self_healing.__dict__,
                "repaired": result.repaired,
            }
            for result in results
        ],
    }


def write_artifact(output_dir: str | Path, artifact: dict) -> Path:
    """Write one immutable raw artifact file and return its path."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "results.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
