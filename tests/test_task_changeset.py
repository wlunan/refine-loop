"""任务主链路的 worktree 审阅与确认测试。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

from src.manager.task_manager import TaskManager
from src.models.run import RunConfig
from src.models.schemas import CritiqueResult
from src.models.task import SubTask, Task, TaskPlan, TaskStatus
from src.store.state_store import StateStore


def git(args: list[str], cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


class FileGenerator:
    total_tokens_used = 0

    def generate_with_files(self, task, workspace_dir, on_event=None):
        Path(workspace_dir, "app.py").write_text("value = 2\n", encoding="utf-8")


class AcceptingCritic:
    total_tokens_used = 0

    def critique(self, task, draft):
        return CritiqueResult(score=100, issues=[], acceptable=True)


def test_completed_task_waits_for_changeset_approval(tmp_path):
    git(["init", "-q"], tmp_path)
    git(["config", "user.email", "test@example.com"], tmp_path)
    git(["config", "user.name", "Test User"], tmp_path)
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(["add", "app.py"], tmp_path)
    git(["commit", "-qm", "initial"], tmp_path)

    store = StateStore(str(tmp_path / "state"))
    task = Task(
        id="task_changeset",
        title="change app",
        description="change app.py",
        workspace_dir=str(tmp_path),
        plan=TaskPlan(
            requirement="change app.py",
            subtasks=[SubTask(id="subtask_1", title="change", description="update app.py")],
        ),
        run_config=RunConfig(max_rounds=1),
    )
    store.save_task(task)
    manager = TaskManager(store=store)
    manager.start_task(task.id, generator=FileGenerator(), critic=AcceptingCritic())

    for _ in range(100):
        persisted = manager.get_task(task.id)
        if persisted.status != TaskStatus.RUNNING:
            break
        time.sleep(0.05)

    persisted = manager.get_task(task.id)
    assert persisted.status == TaskStatus.AWAITING_APPROVAL
    assert persisted.changeset is not None
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "value = 1\n"

    manager.approve_changeset(task.id)

    assert manager.get_task(task.id).status == TaskStatus.COMPLETED
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "value = 2\n"
