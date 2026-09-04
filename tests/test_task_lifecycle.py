"""Regression tests for pause/cancel state ownership across worker threads."""

import os
import subprocess
import sys
import threading
import time

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"),
)

from src.manager.task_manager import TaskManager
from src.models.task import SubTask, Task, TaskPlan, TaskStatus
from src.store.state_store import StateStore
from src.tools.git_workspace import GitWorkspace


def git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class BlockingExecutor:
    """A controlled executor that completes only after TaskManager stops it."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def stop(self):
        self.release.set()

    def execute(self, subtask, context, task_id):
        self.started.set()
        assert self.release.wait(timeout=2)
        subtask.mark_completed("should not overwrite pause", 100)
        return subtask


def test_pause_preserves_persisted_checkpoint_state(tmp_path):
    git(["init", "-q"], tmp_path)
    git(["config", "user.email", "test@example.com"], tmp_path)
    git(["config", "user.name", "Test User"], tmp_path)
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(["add", "app.py"], tmp_path)
    git(["commit", "-qm", "initial"], tmp_path)

    store = StateStore(str(tmp_path / "state"))
    manager = TaskManager(store=store)
    task = Task(
        id="pause_task",
        title="pause",
        description="pause",
        workspace_dir=str(tmp_path),
        status=TaskStatus.RUNNING,
        plan=TaskPlan(
            requirement="pause",
            subtasks=[SubTask(id="subtask_1", title="change", description="change")],
        ),
    )
    task.execution_workspace_dir = GitWorkspace(task.id, task.workspace_dir).create()
    store.save_task(task)
    executor = BlockingExecutor()
    manager._executors[task.id] = executor

    thread = threading.Thread(target=manager._execute_task, args=(task.id, executor, None, None))
    thread.start()
    assert executor.started.wait(timeout=2)
    manager.pause_task(task.id)
    thread.join(timeout=3)

    persisted = manager.get_task(task.id)
    assert not thread.is_alive()
    assert persisted.status == TaskStatus.PAUSED
    assert persisted.plan.subtasks[0].status == TaskStatus.PENDING
    assert persisted.execution_workspace_dir


def test_manager_recovers_interrupted_task_to_resumable_state(tmp_path):
    store = StateStore(str(tmp_path / "state"))
    subtask = SubTask(id="subtask_1", title="change", description="change")
    subtask.mark_running()
    task = Task(
        id="recovered_task",
        title="recover",
        description="recover",
        workspace_dir=str(tmp_path),
        status=TaskStatus.RUNNING,
        current_subtask_id=subtask.id,
        plan=TaskPlan(requirement="recover", subtasks=[subtask]),
    )
    store.save_task(task)

    TaskManager(store=store)
    recovered = store.load_task(task.id)

    assert recovered.status == TaskStatus.PAUSED
    assert recovered.current_subtask_id is None
    assert recovered.plan.subtasks[0].status == TaskStatus.PENDING
