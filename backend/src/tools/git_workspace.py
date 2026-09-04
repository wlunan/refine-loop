"""Git worktree 隔离与变更集收集。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from src.models.changeset import ChangeFile, ChangeSet


class GitWorkspaceError(ValueError):
    """Git 工作区准备、应用或清理失败。"""


class GitWorkspace:
    """为单个任务创建隔离 worktree，并收集可审阅的变更。"""

    def __init__(self, task_id: str, source_workspace: str):
        self.task_id = task_id
        self.source_workspace = self._git_root(source_workspace)
        self.worktree_path: str | None = None

    @staticmethod
    def _run(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    @classmethod
    def _git_root(cls, path: str) -> str:
        result = cls._run(["git", "rev-parse", "--show-toplevel"], cwd=path)
        if result.returncode != 0:
            raise GitWorkspaceError("代码任务必须在 Git 仓库内创建")
        return str(Path(result.stdout.strip()).resolve())

    def create(self) -> str:
        """创建 detached worktree；原始仓库不会被 Agent 写入。"""
        base = Path(tempfile.gettempdir()) / "generator-critic-agent" / "worktrees"
        base.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix=f"{self.task_id}-", dir=base))
        target.rmdir()
        result = self._run(
            ["git", "worktree", "add", "--detach", str(target), "HEAD"],
            cwd=self.source_workspace,
        )
        if result.returncode != 0:
            raise GitWorkspaceError(result.stderr.strip() or "创建 Git worktree 失败")
        self.worktree_path = str(target.resolve())
        return self.worktree_path

    @classmethod
    def collect(cls, source_workspace: str, worktree_path: str) -> ChangeSet:
        """将新增、修改、删除文件整理为可展示且可应用的 patch。"""
        root = cls._git_root(source_workspace)
        worktree = str(Path(worktree_path).resolve())
        # intent-to-add 让未跟踪文本文件也进入 git diff，索引仅属于该 worktree。
        cls._run(["git", "add", "-N", "--", "."], cwd=worktree)
        diff = cls._run(["git", "diff", "--binary", "--", "."], cwd=worktree)
        status = cls._run(["git", "diff", "--name-status", "--", "."], cwd=worktree)
        if diff.returncode != 0 or status.returncode != 0:
            raise GitWorkspaceError("读取 worktree 变更失败")
        files = []
        for line in status.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            code, path = parts[0], parts[-1]
            operation = {"A": "added", "M": "modified", "D": "deleted"}.get(code[:1], "modified")
            files.append(ChangeFile(path=path, operation=operation))
        return ChangeSet(
            source_workspace=root,
            worktree_path=worktree,
            diff=diff.stdout,
            files=files,
        )

    @classmethod
    def apply(cls, changeset: ChangeSet) -> None:
        """将已确认 patch 应用到原始仓库；冲突时拒绝修改。"""
        if not changeset.diff.strip():
            return
        # 通过标准输入传入 patch，始终保持 shell=False。
        result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=changeset.source_workspace,
            input=changeset.diff,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise GitWorkspaceError(result.stderr.strip() or "应用变更失败，原始工作区未修改")

    @classmethod
    def discard(cls, source_workspace: str, worktree_path: str) -> None:
        """删除隔离 worktree，不影响原始工作区。"""
        result = cls._run(["git", "worktree", "remove", "--force", worktree_path], cwd=source_workspace)
        if result.returncode != 0 and Path(worktree_path).exists():
            raise GitWorkspaceError(result.stderr.strip() or "清理 Git worktree 失败")
        if Path(worktree_path).exists():
            shutil.rmtree(worktree_path, ignore_errors=True)
