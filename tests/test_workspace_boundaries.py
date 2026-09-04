"""File workspace security boundaries."""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"),
)

from src.tools.filesystem import FileWorkspace, FileWorkspaceError
from src.tools.verification import CommandRunner


def test_file_workspace_rejects_symlink_escaping_root(tmp_path):
    """A symlink inside the worktree must not provide access to an external file."""
    workspace_root = tmp_path / "workspace"
    external_root = tmp_path / "external"
    workspace_root.mkdir()
    external_root.mkdir()
    (external_root / "secret.txt").write_text("secret", encoding="utf-8")

    try:
        os.symlink(external_root, workspace_root / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("创建目录符号链接需要额外的 Windows 权限")

    workspace = FileWorkspace(str(workspace_root))
    with pytest.raises(FileWorkspaceError, match="路径越界"):
        workspace.read_file("outside/secret.txt")


def test_verification_runner_rejects_parent_directory_path(tmp_path):
    runner = CommandRunner(str(tmp_path))

    with pytest.raises(ValueError, match="验证路径越界"):
        runner.run_python("../outside.py")
