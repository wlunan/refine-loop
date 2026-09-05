"""
任务执行器
复用 Orchestrator 执行单个子任务，支持文件写入模式
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
from src.models.run import RunConfig, VerificationSummary
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
    
    支持两种模式：
    1. 文本模式：生成文本内容（默认）
    2. 文件模式：直接操作工作区文件（use_file_mode=True）
    """
    
    def __init__(
        self,
        workspace: FileWorkspace,
        store: Optional[StateStore] = None,
        generator: Optional[GeneratorAgent] = None,
        critic: Optional[CriticAgent] = None,
        max_rounds: int = 5,
        use_file_mode: bool = True,
        on_progress: Optional[Callable[[str, dict], None]] = None,
        run_config: Optional[RunConfig] = None,
    ):
        """
        初始化执行器
        
        Args:
            workspace: 文件工作区
            store: 状态存储（用于保存检查点）
            generator: 自定义 Generator
            critic: 自定义 Critic
            max_rounds: 单个子任务的最大迭代轮数
            use_file_mode: 是否使用文件模式（直接操作文件）
            on_progress: 进度回调，签名: (event_type, data)
        """
        self.workspace = workspace
        self.store = store
        self.generator = generator
        self.critic = critic
        self.run_config = run_config
        self.max_rounds = run_config.max_rounds if run_config else max_rounds
        self.use_file_mode = use_file_mode
        self.on_progress = on_progress
        
        # 停止控制
        self._stop_event = threading.Event()
        
        # 当前执行的 Orchestrator
        self._current_orchestrator: Optional[Orchestrator] = None
        self._round_verifications: Dict[tuple[str, str, int], VerificationSummary] = {}
        # The agents can be shared by injected test/custom executors, so use a
        # per-subtask baseline to persist each round's delta accurately.
        self._round_token_totals: Dict[tuple[str, str], int] = {}
        self._subtask_token_totals: Dict[tuple[str, str], int] = {}
    
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
                run_config=self.run_config,
                on_round_complete=lambda r, d, c: self._on_round_complete(
                    task_id, subtask.id, r, d, c
                ),
                on_verification_complete=lambda r, summary: self._on_verification_complete(
                    task_id, subtask.id, r, summary
                ),
            )
            self._current_orchestrator = orchestrator
            self._round_token_totals[(task_id, subtask.id)] = orchestrator.total_tokens_used
            self._subtask_token_totals[(task_id, subtask.id)] = 0
            
            # 3. 根据模式执行
            if self.use_file_mode:
                # 文件模式：直接操作工作区文件
                result = orchestrator.run_with_files(
                    task=task_prompt,
                    workspace_dir=self.workspace.root,
                    on_generator_event=lambda e: self._on_generator_event(
                        task_id, subtask.id, e
                    ),
                )
            else:
                # 文本模式：生成文本内容
                result = orchestrator.run(task_prompt)
            
            # 4. 更新子任务状态
            subtask.iterations = result.iterations
            if (
                self.use_file_mode
                and self.run_config
                and any(step.required for step in self.run_config.verification_steps)
                and not (result.verification_summary and result.verification_summary.passed)
            ):
                raise RuntimeError(result.convergence_reason)
            subtask.mark_completed(
                result=result.final_output,
                score=result.state.critique.score if result.state.critique else 0,
            )

            # 轮次回调已将增量持久化；这里仅用于子任务完成事件展示。
            tokens_used = self._subtask_token_totals[(task_id, subtask.id)]
            
            # 发送完成事件（附带 token 消耗）
            self._emit_progress("subtask_completed", {
                "subtask_id": subtask.id,
                "score": subtask.score,
                "iterations": subtask.iterations,
                "tokens_used": tokens_used,
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
            self._round_token_totals.pop((task_id, subtask.id), None)
            self._subtask_token_totals.pop((task_id, subtask.id), None)
        
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
        key = (task_id, subtask_id)
        current_total = (
            self._current_orchestrator.total_tokens_used
            if self._current_orchestrator else 0
        )
        previous_total = self._round_token_totals.get(key, 0)
        round_tokens = max(0, current_total - previous_total)
        self._round_token_totals[key] = current_total
        self._subtask_token_totals[key] = self._subtask_token_totals.get(key, 0) + round_tokens

        verification_summary = self._round_verifications.pop(
            (task_id, subtask_id, round_num),
            None,
        )

        # Checkpoints are the durable source for per-round token usage.
        if self.store:
            checkpoint = Checkpoint(
                task_id=task_id,
                subtask_id=subtask_id,
                round=round_num,
                draft=draft,
                tokens_used=round_tokens,
                score=critique.score if critique else None,
                acceptable=critique.acceptable if critique else None,
                issues=list(critique.issues) if critique else [],
                suggestions=list(critique.suggestions) if critique else [],
                summary=critique.summary if critique else None,
                verification_summary=verification_summary,
            )
            try:
                self.store.save_checkpoint(checkpoint)
            except Exception as e:
                logger.warning(f"保存检查点失败: {e}")

        # 发送进度事件
        self._emit_progress("subtask_progress", {
            "subtask_id": subtask_id,
            "round": round_num,
            "score": critique.score,
            "tokens_used": round_tokens,
            "draft_preview": draft[:200] + "..." if len(draft) > 200 else draft,
        })

    def _on_verification_complete(
        self,
        task_id: str,
        subtask_id: str,
        round_num: int,
        summary: VerificationSummary,
    ) -> None:
        """保存验证结果，并让同一轮检查点在轮次回调时一并持久化。"""
        self._round_verifications[(task_id, subtask_id, round_num)] = summary
        self._emit_progress("verification_completed", {
            "subtask_id": subtask_id,
            "round": round_num,
            "passed": summary.passed,
            "profile": summary.profile,
            "results": [result.model_dump() for result in summary.results],
        })
    
    def _on_generator_event(
        self,
        task_id: str,
        subtask_id: str,
        event: dict,
    ) -> None:
        """Generator 工具调用事件回调（文件模式）"""
        event_type = event.get("type", "unknown")
        
        if event_type == "tool_call":
            tool_name = event.get("tool_name", "")
            tool_input = event.get("input", {})
            self._emit_progress("file_operation", {
                "subtask_id": subtask_id,
                "operation": tool_name,
                "path": tool_input.get("path", ""),
                "round": event.get("round", 0),
            })
        elif event_type == "tool_result":
            self._emit_progress("file_result", {
                "subtask_id": subtask_id,
                "result": event.get("result", "")[:200],
                "round": event.get("round", 0),
            })
    
    def _emit_progress(self, event_type: str, data: dict) -> None:
        """发送进度事件"""
        if self.on_progress:
            try:
                self.on_progress(event_type, data)
            except Exception as e:
                logger.warning(f"进度回调失败: {e}")
