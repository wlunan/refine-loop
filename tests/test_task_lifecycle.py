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
from src.models.task import Checkpoint, SubTask, Task, TaskPlan, TaskStatus
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


class FailingExecutor:
    """Returns a failed subtask without involving an LLM or process runner."""

    def execute(self, subtask, context, task_id):
        subtask.mark_failed("verification command is unavailable")
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


def test_failed_subtask_persists_task_failure_before_worker_cleanup(tmp_path):
    git(["init", "-q"], tmp_path)
    git(["config", "user.email", "test@example.com"], tmp_path)
    git(["config", "user.name", "Test User"], tmp_path)
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    git(["add", "app.py"], tmp_path)
    git(["commit", "-qm", "initial"], tmp_path)

    store = StateStore(str(tmp_path / "state"))
    manager = TaskManager(store=store)
    task = Task(
        id="failed_task",
        title="fail",
        description="fail",
        workspace_dir=str(tmp_path),
        status=TaskStatus.RUNNING,
        plan=TaskPlan(
            requirement="fail",
            subtasks=[SubTask(id="subtask_1", title="change", description="change")],
        ),
    )
    task.execution_workspace_dir = GitWorkspace(task.id, task.workspace_dir).create()
    store.save_task(task)
    executor = FailingExecutor()
    manager._executors[task.id] = executor

    manager._execute_task(task.id, executor, None, None)

    persisted = manager.get_task(task.id)
    assert persisted.status == TaskStatus.FAILED
    assert persisted.error == "子任务失败: verification command is unavailable"


def test_round_progress_persists_token_usage_before_subtask_completion(tmp_path):
    store = StateStore(str(tmp_path / "state"))
    manager = TaskManager(store=store)
    task = Task(
        id="token_task",
        title="tokens",
        description="tokens",
        workspace_dir=str(tmp_path),
        status=TaskStatus.RUNNING,
    )
    store.save_task(task)

    manager._on_executor_progress(
        task.id,
        "subtask_progress",
        {"subtask_id": "subtask_1", "round": 1, "tokens_used": 120},
    )
    manager._on_executor_progress(
        task.id,
        "subtask_progress",
        {"subtask_id": "subtask_1", "round": 2, "tokens_used": 80},
    )

    persisted = manager.get_task(task.id)
    assert persisted.total_tokens == 200
    events = store.list_events(task.id)
    assert [event["data"]["tokens_used"] for event in events] == [120, 80]


def test_task_events_survive_a_new_store_instance(tmp_path):
    store = StateStore(str(tmp_path / "state"))
    store.append_event("task_events", "subtask_started", {"task_id": "task_events", "title": "change"})
    store.append_event("task_events", "verification_completed", {"task_id": "task_events", "passed": True})

    recovered_store = StateStore(str(tmp_path / "state"))
    events = recovered_store.list_events("task_events")

    assert [event["type"] for event in events] == ["subtask_started", "verification_completed"]
    assert events[1]["data"]["passed"] is True
    assert events[0]["created_at"]


def test_delete_task_removes_record_checkpoints_and_timeline(tmp_path):
    store = StateStore(str(tmp_path / "state"))
    task = Task(
        id="delete_task",
        title="delete",
        description="delete",
        workspace_dir=str(tmp_path),
        status=TaskStatus.FAILED,
    )
    store.save_task(task)
    store.save_checkpoint(Checkpoint(task_id=task.id, subtask_id="subtask_1", round=1))
    store.append_event(task.id, "task_failed", {"task_id": task.id})
    manager = TaskManager(store=store)

    manager.delete_task(task.id)

    assert store.load_task(task.id) is None
    assert store.list_checkpoints(task.id) == []
    assert store.list_events(task.id) == []
