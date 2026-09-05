"""Tests for deterministic, repository-aware verification detection."""

import json
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"),
)

from src.tools.project_detector import detect_verification_plan


def test_detects_node_build_script(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"build": "vite build"}}), encoding="utf-8"
    )

    plan = detect_verification_plan(str(tmp_path))

    assert plan["profile"] == "node_build"
    assert plan["plan"] == ["npm run build"]


def test_detects_python_pytest_from_project_and_tests(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    plan = detect_verification_plan(str(tmp_path))

    assert plan["profile"] == "python_pytest"
    assert plan["plan"] == ["python -m pytest -q"]


def test_falls_back_to_none_for_unknown_workspace(tmp_path):
    plan = detect_verification_plan(str(tmp_path))

    assert plan["profile"] == "none"
    assert plan["plan"] == []
