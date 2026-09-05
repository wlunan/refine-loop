"""
状态持久化存储
支持任务状态和检查点的保存/加载，用于断点恢复
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.models.task import (
    Checkpoint,
    SubTask,
    Task,
    TaskPlan,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class StateStore:
    """
    状态持久化存储
    
    使用 JSON 文件存储任务状态，支持：
    - 任务状态保存/加载
    - 检查点保存/加载
    - 任务列表查询
    """

    def __init__(self, storage_dir: str = ".task_store"):
        """
        初始化存储
        
        Args:
            storage_dir: 存储目录路径
        """
        self.storage_dir = Path(storage_dir)
        self.tasks_dir = self.storage_dir / "tasks"
        self.checkpoints_dir = self.storage_dir / "checkpoints"
        self.events_dir = self.storage_dir / "events"
        self.artifacts_dir = self.storage_dir / "artifacts"
        
        # 创建目录
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"StateStore 初始化完成: {self.storage_dir}")

    def _task_path(self, task_id: str) -> Path:
        """获取任务文件路径"""
        return self.tasks_dir / f"{task_id}.json"

    def _checkpoint_dir(self, task_id: str) -> Path:
        """获取检查点目录"""
        return self.checkpoints_dir / task_id

    def _event_path(self, task_id: str) -> Path:
        """Return the append-only event timeline file for one task."""
        return self.events_dir / f"{task_id}.jsonl"

    def _artifact_dir(self, task_id: str) -> Path:
        """Return the directory that holds full trace payloads for one task."""
        return self.artifacts_dir / task_id

    # ------------------------------------------------------------------
    # 任务操作
    # ------------------------------------------------------------------

    def save_task(self, task: Task) -> None:
        """
        保存任务状态
        
        Args:
            task: 任务对象
        """
        task.update_timestamp()
        path = self._task_path(task.id)
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(task.model_dump_json(indent=2))
            logger.debug(f"任务已保存: {task.id}")
        except Exception as e:
            logger.error(f"保存任务失败: {task.id}, {e}")
            raise

    def load_task(self, task_id: str) -> Optional[Task]:
        """
        加载任务状态
        
        Args:
            task_id: 任务 ID
            
        Returns:
            Task 对象，不存在则返回 None
        """
        path = self._task_path(task_id)
        if not path.exists():
            return None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = f.read()
            return Task.model_validate_json(data)
        except Exception as e:
            logger.error(f"加载任务失败: {task_id}, {e}")
            return None

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否删除成功
        """
        task_path = self._task_path(task_id)
        checkpoint_dir = self._checkpoint_dir(task_id)
        event_path = self._event_path(task_id)
        deleted = False

        if task_path.exists():
            task_path.unlink()
            deleted = True
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)
            deleted = True
        if event_path.exists():
            event_path.unlink()
            deleted = True
        artifact_dir = self._artifact_dir(task_id)
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)
            deleted = True
        if deleted:
            logger.info(f"任务及其持久化证据已删除: {task_id}")
        return deleted

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[Task]:
        """
        列出任务
        
        Args:
            status: 按状态过滤
            limit: 返回数量限制
            
        Returns:
            任务列表
        """
        tasks = []
        
        for path in self.tasks_dir.glob("*.json"):
            try:
                task = self.load_task(path.stem)
                if task is None:
                    continue
                if status is None or task.status == status:
                    tasks.append(task)
            except Exception as e:
                logger.warning(f"跳过损坏的任务文件: {path}, {e}")
        
        # 按创建时间倒序排列
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    # ------------------------------------------------------------------
    # 检查点操作
    # ------------------------------------------------------------------

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """
        保存检查点
        
        Args:
            checkpoint: 检查点对象
        """
        checkpoint_dir = self._checkpoint_dir(checkpoint.task_id)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Round number and microseconds avoid overwriting two fast callbacks.
        timestamp = checkpoint.created_at.strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{checkpoint.subtask_id}_round_{checkpoint.round}_{timestamp}.json"
        path = checkpoint_dir / filename
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(checkpoint.model_dump_json(indent=2))
            logger.debug(f"检查点已保存: {checkpoint.task_id}/{filename}")
        except Exception as e:
            logger.error(f"保存检查点失败: {e}")
            raise

    def load_latest_checkpoint(
        self,
        task_id: str,
        subtask_id: Optional[str] = None
    ) -> Optional[Checkpoint]:
        """
        加载最新的检查点
        
        Args:
            task_id: 任务 ID
            subtask_id: 子任务 ID（可选，不指定则返回任意子任务的最新检查点）
            
        Returns:
            Checkpoint 对象，不存在则返回 None
        """
        checkpoint_dir = self._checkpoint_dir(task_id)
        if not checkpoint_dir.exists():
            return None
        
        checkpoints = []
        for path in checkpoint_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read()
                cp = Checkpoint.model_validate_json(data)
                if subtask_id is None or cp.subtask_id == subtask_id:
                    checkpoints.append(cp)
            except Exception as e:
                logger.warning(f"跳过损坏的检查点: {path}, {e}")
        
        if not checkpoints:
            return None
        
        # 返回最新的检查点
        return max(checkpoints, key=lambda cp: cp.created_at)

    def list_checkpoints(
        self,
        task_id: str,
        subtask_id: Optional[str] = None
    ) -> List[Checkpoint]:
        """
        列出检查点
        
        Args:
            task_id: 任务 ID
            subtask_id: 子任务 ID（可选）
            
        Returns:
            检查点列表
        """
        checkpoint_dir = self._checkpoint_dir(task_id)
        if not checkpoint_dir.exists():
            return []
        
        checkpoints = []
        for path in checkpoint_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read()
                cp = Checkpoint.model_validate_json(data)
                if subtask_id is None or cp.subtask_id == subtask_id:
                    checkpoints.append(cp)
            except Exception as e:
                logger.warning(f"跳过损坏的检查点: {path}, {e}")
        
        checkpoints.sort(key=lambda cp: cp.created_at, reverse=True)
        return checkpoints

    def append_event(self, task_id: str, event_type: str, data: dict) -> dict:
        """Persist one canonical trace event and return the SSE-ready envelope."""
        artifacts = data.get("artifacts", [])
        event_data = {key: value for key, value in data.items() if key != "artifacts"}
        event_id = uuid.uuid4().hex
        event = {
            "id": event_id,
            "type": event_type,
            "category": self._event_category(event_type),
            "task_id": task_id,
            "subtask_id": event_data.get("subtask_id"),
            "round": event_data.get("round"),
            "summary": self._event_summary(event_type, event_data),
            "data": event_data,
            "artifacts": self._save_artifacts(task_id, event_id, artifacts),
            "created_at": datetime.now().isoformat(),
        }
        try:
            with open(self._event_path(task_id), "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"保存任务事件失败: {task_id}, {e}")
        return event

    @staticmethod
    def _event_category(event_type: str) -> str:
        if event_type in {"file_operation", "file_result"}:
            return "tool"
        if event_type == "verification_completed":
            return "verification"
        if event_type == "subtask_progress":
            return "llm"
        return "decision"

    @staticmethod
    def _event_summary(event_type: str, data: dict) -> str:
        summaries = {
            "subtask_progress": f"完成第 {data.get('round', '?')} 轮生成与审查",
            "file_operation": f"调用工具 {data.get('operation', 'unknown')}",
            "file_result": f"工具 {data.get('operation', 'unknown')} 返回结果",
            "verification_completed": "完成确定性验证",
            "subtask_started": f"开始子任务 {data.get('title', data.get('subtask_id', ''))}",
            "subtask_completed": "子任务完成",
            "subtask_failed": "子任务失败",
            "task_started": "开始执行任务",
            "task_completed": "任务完成",
            "task_failed": "任务失败",
            "task_cancelled": "任务已取消",
            "task_paused": "任务已暂停",
        }
        return summaries.get(event_type, event_type)

    def _save_artifacts(
        self,
        task_id: str,
        event_id: str,
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Store large trace payloads outside the JSONL event stream."""
        references: list[dict[str, Any]] = []
        for index, artifact in enumerate(artifacts):
            content = artifact.get("content")
            if content is None:
                continue
            artifact_id = f"{event_id}_{index}"
            is_json = not isinstance(content, str)
            suffix = ".json" if is_json else ".txt"
            path = self._artifact_dir(task_id) / f"{artifact_id}{suffix}"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if is_json:
                    serialized = json.dumps(content, ensure_ascii=False, indent=2)
                    path.write_text(serialized, encoding="utf-8")
                    content_type = "application/json"
                else:
                    path.write_text(content, encoding="utf-8")
                    content_type = "text/plain"
                references.append({
                    "id": artifact_id,
                    "kind": artifact.get("kind", "artifact"),
                    "content_type": artifact.get("content_type", content_type),
                    "size": path.stat().st_size,
                })
            except OSError as e:
                logger.warning(f"保存 trace artifact 失败: {task_id}/{artifact_id}, {e}")
        return references

    def read_artifact(self, task_id: str, artifact_id: str) -> Optional[dict[str, Any]]:
        """Load one artifact by its opaque id without exposing filesystem paths."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+", artifact_id):
            return None
        matches = list(self._artifact_dir(task_id).glob(f"{artifact_id}.*"))
        if len(matches) != 1:
            return None
        path = matches[0]
        try:
            content = path.read_text(encoding="utf-8")
            content_type = "application/json" if path.suffix == ".json" else "text/plain"
            return {
                "id": artifact_id,
                "content_type": content_type,
                "content": json.loads(content) if content_type == "application/json" else content,
            }
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"读取 trace artifact 失败: {task_id}/{artifact_id}, {e}")
            return None

    def list_events(self, task_id: str, limit: int = 200) -> List[dict]:
        """Read a bounded chronological event timeline, skipping malformed lines."""
        path = self._event_path(task_id)
        if not path.exists():
            return []

        events: List[dict] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"跳过损坏的任务事件: {task_id}")
        except OSError as e:
            logger.warning(f"读取任务事件失败: {task_id}, {e}")
            return []
        return events[-limit:]

    def clear_checkpoints(self, task_id: str) -> int:
        """
        清除任务的所有检查点
        
        Args:
            task_id: 任务 ID
            
        Returns:
            删除的检查点数量
        """
        checkpoint_dir = self._checkpoint_dir(task_id)
        if not checkpoint_dir.exists():
            return 0
        
        count = 0
        for path in checkpoint_dir.glob("*.json"):
            path.unlink()
            count += 1
        
        checkpoint_dir.rmdir()
        logger.info(f"已清除 {count} 个检查点: {task_id}")
        return count
