"""Repository-aware, deterministic verification-plan detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal


ResolvedProfile = Literal["none", "python_pytest", "python_lint", "node_build"]


def detect_verification_plan(workspace_dir: str) -> dict:
    """Infer one safe built-in verification profile from repository manifests.

    Detection only reads repository metadata. It never installs dependencies or
    executes package scripts; execution remains an explicit, auditable task step.
    """
    root = Path(workspace_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"工作区目录不存在: {root}")

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = package.get("scripts", {})
        except (OSError, json.JSONDecodeError):
            scripts = {}
        if "build" in scripts:
            return {
                "profile": "node_build",
                "summary": "检测到 package.json 的 build 脚本",
                "plan": ["npm run build"],
                "dependency_note": "若隔离工作区没有 node_modules，执行时会明确提示安装依赖。",
            }
        return {
            "profile": "none",
            "summary": "检测到 Node 项目，但没有 build 脚本",
            "plan": [],
            "dependency_note": "可在高级设置中选择验证方式。",
        }

    python_markers = ("pyproject.toml", "requirements.txt", "pytest.ini", "setup.cfg")
    has_python_marker = any((root / marker).is_file() for marker in python_markers)
    has_python_tests = any(root.glob("test_*.py")) or (root / "tests").is_dir()
    if has_python_marker and has_python_tests:
        return {
            "profile": "python_pytest",
            "summary": "检测到 Python 项目和 pytest 测试目录/文件",
            "plan": ["python -m pytest -q"],
            "dependency_note": "使用运行后端的 Python 环境执行测试。",
        }
    if has_python_marker:
        return {
            "profile": "python_lint",
            "summary": "检测到 Python 项目，未发现测试入口",
            "plan": ["python -m ruff check ."],
            "dependency_note": "若未安装 ruff，会回退尝试 flake8。",
        }

    return {
        "profile": "none",
        "summary": "未识别到受支持的验证入口",
        "plan": [],
        "dependency_note": "任务仍可执行；可在高级设置中手动覆盖验证方式。",
    }
