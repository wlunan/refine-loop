"""
状态持久化存储
支持任务状态和检查点的保存/加载，用于断点恢复
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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
        
        # 创建目录
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"StateStore 初始化完成: {self.storage_dir}")

    def _task_path(self, task_id: str) -> Path:
        """获取任务文件路径"""
        return self.tasks_dir / f"{task_id}.json"

    def _checkpoint_dir(self, task_id: str) -> Path:
        """获取检查点目录"""
        return self.checkpoints_dir / task_id

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
        path = self._task_path(task_id)
        if path.exists():
            path.unlink()
            logger.info(f"任务已删除: {task_id}")
            return True
        return False

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
        
        # 使用时间戳命名，保留历史检查点
        timestamp = checkpoint.created_at.strftime("%Y%m%d_%H%M%S")
        filename = f"{checkpoint.subtask_id}_{timestamp}.json"
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
