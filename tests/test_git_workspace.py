"""Git worktree 隔离与变更确认的回归测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

from src.tools.git_workspace import GitWorkspace


def git(args: list[str], cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def init_repository(path: Path) -> None:
    git(["init", "-q"], path)
    git(["config", "user.email", "test@example.com"], path)
    git(["config", "user.name", "Test User"], path)
    (path / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(["add", "app.py"], path)
    git(["commit", "-qm", "initial"], path)


def test_worktree_keeps_source_unchanged_until_changeset_is_applied(tmp_path):
    init_repository(tmp_path)
    workspace = GitWorkspace("task_apply", str(tmp_path))
    worktree = Path(workspace.create())
    (worktree / "app.py").write_text("value = 2\n", encoding="utf-8")
    (worktree / "new.py").write_text("created = True\n", encoding="utf-8")

    changeset = GitWorkspace.collect(str(tmp_path), str(worktree))

    assert {item.path for item in changeset.files} == {"app.py", "new.py"}
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert not (tmp_path / "new.py").exists()

    GitWorkspace.apply(changeset)

    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "created = True\n"
    GitWorkspace.discard(str(tmp_path), str(worktree))


def test_discard_leaves_source_unchanged(tmp_path):
    init_repository(tmp_path)
    workspace = GitWorkspace("task_discard", str(tmp_path))
    worktree = Path(workspace.create())
    (worktree / "app.py").write_text("value = 3\n", encoding="utf-8")

    changeset = GitWorkspace.collect(str(tmp_path), str(worktree))
    GitWorkspace.discard(str(tmp_path), str(worktree))

    assert changeset.files[0].path == "app.py"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert not worktree.exists()
