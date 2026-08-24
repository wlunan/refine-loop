"""
任务执行器
复用 Orchestrator 执行单个子任务，增加上下文传递和检查点保存
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from config.settings import get_config
from src.agents.critic import CriticAgent
from src.agents.generator import GeneratorAgent
from src.models.task import (
    Checkpoint,
    FileChange,
    SubTask,
    TaskStatus,
)
from src.orchestrator import Orchestrator
from src.store.state_store import StateStore
from src.tools.filesystem import FileWorkspace

logger = logging.getLogger(__name__)


class TaskContext:
    """
    任务执行上下文
    包含前序任务的结果和工作区状态
    """
    
    def __init__(
        self,
        workspace: FileWorkspace,
        completed_results: Dict[str, str] = None,
        file_changes: List[FileChange] = None,
    ):
        self.workspace = workspace
        self.completed_results = completed_results or {}
        self.file_changes = file_changes or []
    
    def build_task_prompt(self, subtask: SubTask) -> str:
        """
        构建子任务的执行提示词
        包含前序任务结果作为上下文
        """
        parts = [f"## 当前任务\n{subtask.title}\n\n{subtask.description}"]
        
        # 添加前序任务结果
        if subtask.dependencies:
            parts.append("\n## 前置任务结果")
            for dep_id in subtask.dependencies:
                if dep_id in self.completed_results:
                    result = self.completed_results[dep_id]
                    # 截断过长的结果
                    if len(result) > 1000:
                        result = result[:1000] + "\n... (已截断)"
                    parts.append(f"\n### {dep_id}\n{result}")
        
        # 添加工作区当前状态
        try:
            workspace_listing = self.workspace.list_directory(".")
            parts.append(f"\n## 工作区当前结构\n{workspace_listing}")
        except Exception:
            pass
        
        return "\n".join(parts)


class TaskExecutor:
    """
    子任务执行器
    
    复用 Orchestrator 的 Generator-Critic 迭代流程，
    增加上下文传递和检查点保存
    """
    
    def __init__(
        self,
        workspace: FileWorkspace,
        store: Optional[StateStore] = None,
        generator: Optional[GeneratorAgent] = None,
        critic: Optional[CriticAgent] = None,
        max_rounds: int = 5,
        on_progress: Optional[Callable[[str, dict], None]] = None,
    ):
        """
        初始化执行器
        
        Args:
            workspace: 文件工作区
            store: 状态存储（用于保存检查点）
            generator: 自定义 Generator
            critic: 自定义 Critic
            max_rounds: 单个子任务的最大迭代轮数
            on_progress: 进度回调，签名: (event_type, data)
        """
        self.workspace = workspace
        self.store = store
        self.generator = generator
        self.critic = critic
        self.max_rounds = max_rounds
        self.on_progress = on_progress
        
        # 停止控制
        self._stop_event = threading.Event()
        
        # 当前执行的 Orchestrator
        self._current_orchestrator: Optional[Orchestrator] = None
    
    def stop(self) -> None:
        """请求停止执行"""
        self._stop_event.set()
        if self._current_orchestrator:
            self._current_orchestrator.stop()
    
    def execute(
        self,
        subtask: SubTask,
        context: TaskContext,
        task_id: str,
    ) -> SubTask:
        """
        执行单个子任务
        
        Args:
            subtask: 待执行的子任务
            context: 任务上下文
            task_id: 所属任务 ID
            
        Returns:
            更新状态后的子任务
        """
        logger.info(f"开始执行子任务: {subtask.id} - {subtask.title}")
        subtask.mark_running()
        
        # 发送开始事件
        self._emit_progress("subtask_started", {
            "subtask_id": subtask.id,
            "title": subtask.title,
        })
        
        try:
            # 1. 构建任务提示词
            task_prompt = context.build_task_prompt(subtask)
            
            # 2. 创建 Orchestrator
            orchestrator = Orchestrator(
                domain="code",
                max_rounds=self.max_rounds,
                generator=self.generator,
                critic=self.critic,
                on_round_complete=lambda r, d, c: self._on_round_complete(
                    task_id, subtask.id, r, d, c
                ),
            )
            self._current_orchestrator = orchestrator
            
            # 3. 执行迭代
            result = orchestrator.run(task_prompt)
            
            # 4. 更新子任务状态
            subtask.iterations = result.iterations
            subtask.mark_completed(
                result=result.final_output,
                score=result.state.critique.score if result.state.critique else 0,
            )
            
            # 5. 记录文件变更
            # TODO: 从 FileWorkspace 的操作日志中提取
            
            # 发送完成事件
            self._emit_progress("subtask_completed", {
                "subtask_id": subtask.id,
                "score": subtask.score,
                "iterations": subtask.iterations,
            })
            
            logger.info(
                f"子任务完成: {subtask.id}, "
                f"评分={subtask.score}, 轮数={subtask.iterations}"
            )
            
        except Exception as e:
            logger.error(f"子任务执行失败: {subtask.id}, {e}")
            subtask.mark_failed(str(e))
            
            # 发送失败事件
            self._emit_progress("subtask_failed", {
                "subtask_id": subtask.id,
                "error": str(e),
            })
        
        finally:
            self._current_orchestrator = None
        
        return subtask
    
    def _on_round_complete(
        self,
        task_id: str,
        subtask_id: str,
        round_num: int,
        draft: str,
        critique,
    ) -> None:
        """每轮完成的回调"""
        # 发送进度事件
        self._emit_progress("subtask_progress", {
            "subtask_id": subtask_id,
            "round": round_num,
            "score": critique.score,
            "draft_preview": draft[:200] + "..." if len(draft) > 200 else draft,
        })
        
        # 保存检查点
        if self.store:
            checkpoint = Checkpoint(
                task_id=task_id,
                subtask_id=subtask_id,
                round=round_num,
                draft=draft,
            )
            try:
                self.store.save_checkpoint(checkpoint)
            except Exception as e:
                logger.warning(f"保存检查点失败: {e}")
    
    def _emit_progress(self, event_type: str, data: dict) -> None:
        """发送进度事件"""
        if self.on_progress:
            try:
                self.on_progress(event_type, data)
            except Exception as e:
                logger.warning(f"进度回调失败: {e}")
