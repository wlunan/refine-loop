"""
任务执行器
复用 Orchestrator 执行单个子任务，支持文件写入模式
"""

from __future__ import annotations

import logging
import json
import threading
import time
import uuid
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
from src.models.execution import ConversationMessage, ExecutionRecord, ExecutionSnapshot
from src.models.execution import ToolAgentState
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
        self._attempt_ids: Dict[tuple[str, str], str] = {}
        self._history_sequences: Dict[tuple[str, str], int] = {}
    
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
        history_key = (task_id, subtask.id)
        attempt_id = uuid.uuid4().hex
        self._attempt_ids[history_key] = attempt_id
        self._history_sequences[history_key] = self._next_history_sequence(
            task_id, subtask.id
        )
        
        # 发送开始事件
        self._emit_progress("subtask_started", {
            "subtask_id": subtask.id,
            "title": subtask.title,
        })
        
        try:
            # 1. 构建任务提示词
            task_prompt = context.build_task_prompt(subtask)
            execution_snapshot = (
                self.store.load_latest_execution_snapshot(task_id, subtask.id)
                if self.store else None
            )
            tool_execution_state = None
            resumable_phases = {
                "model_call",
                "tool_result",
                "tool_call",
                "checkpoint",
            }
            if (
                execution_snapshot
                and execution_snapshot.resumable
                and execution_snapshot.phase in resumable_phases
                and execution_snapshot.messages
            ):
                tool_execution_state = ToolAgentState(
                    messages=execution_snapshot.messages,
                    current_step=execution_snapshot.step,
                    phase=execution_snapshot.phase,
                    resumable=execution_snapshot.resumable,
                )
            
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
                on_tool_checkpoint=lambda state: self._on_tool_checkpoint(
                    task_id, subtask.id, state
                ),
                tool_execution_state=tool_execution_state,
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
            self._attempt_ids.pop(history_key, None)
            self._history_sequences.pop(history_key, None)
        
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

        attempt_id = self._attempt_ids.get(key)
        if self.store and attempt_id:
            generator_message = self._append_history_message(
                task_id=task_id,
                subtask_id=subtask_id,
                attempt_id=attempt_id,
                agent="generator",
                role="ai",
                content=draft,
                round_num=round_num,
            )
            critic_content = {
                "score": critique.score,
                "acceptable": critique.acceptable,
                "issues": list(critique.issues),
                "suggestions": list(critique.suggestions),
                "summary": critique.summary,
            }
            critic_message = self._append_history_message(
                task_id=task_id,
                subtask_id=subtask_id,
                attempt_id=attempt_id,
                agent="critic",
                role="ai",
                content=json.dumps(critic_content, ensure_ascii=False),
                round_num=round_num,
            )
            self._append_execution_record(
                task_id,
                subtask_id,
                attempt_id,
                phase="model_response",
                agent="generator",
                round_num=round_num,
                summary="Generator 完成本轮产出",
                message_ids=[generator_message.id],
                metadata={"tokens_used": round_tokens},
            )
            self._append_execution_record(
                task_id,
                subtask_id,
                attempt_id,
                phase="model_response",
                agent="critic",
                round_num=round_num,
                summary="Critic 完成本轮审阅",
                message_ids=[critic_message.id],
                metadata={"score": critique.score, "acceptable": critique.acceptable},
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

            if attempt_id:
                self._save_history_snapshot(
                    task_id=task_id,
                    subtask_id=subtask_id,
                    attempt_id=attempt_id,
                    round_num=round_num,
                    phase="round_committed",
                )

        # 发送进度事件
        self._emit_progress("subtask_progress", {
            "subtask_id": subtask_id,
            "round": round_num,
            "score": critique.score,
            "tokens_used": round_tokens,
            "draft_preview": draft[:200] + "..." if len(draft) > 200 else draft,
            # Full model content is kept as trace artifacts rather than added
            # to the append-only event stream or the SSE payload.
            "artifacts": [
                {
                    "kind": "generator_output",
                    "content": draft,
                },
                {
                    "kind": "critic_review",
                    "content": {
                        "score": critique.score,
                        "acceptable": critique.acceptable,
                        "issues": list(critique.issues),
                        "suggestions": list(critique.suggestions),
                        "summary": critique.summary,
                    },
                },
            ],
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
            "result_count": len(summary.results),
            "artifacts": [
                {
                    "kind": "verification_results",
                    "content": [result.model_dump() for result in summary.results],
                },
            ],
        })

    def _on_tool_checkpoint(
        self,
        task_id: str,
        subtask_id: str,
        state: ToolAgentState,
    ) -> None:
        """Persist the latest ToolAgent messages at every safe loop boundary."""
        attempt_id = self._attempt_ids.get((task_id, subtask_id))
        if not self.store or not attempt_id:
            return
        self.store.save_execution_snapshot(
            ExecutionSnapshot(
                task_id=task_id,
                subtask_id=subtask_id,
                attempt_id=attempt_id,
                snapshot_id=f"snapshot_{uuid.uuid4().hex}",
                phase=state.phase,
                round=0,
                step=state.current_step,
                workspace_path=self.workspace.root,
                message_sequence=len(state.messages),
                execution_sequence=self._history_sequences.get(
                    (task_id, subtask_id), 0
                ),
                messages=state.messages,
                resumable=state.resumable,
            )
        )
    
    def _on_generator_event(
        self,
        task_id: str,
        subtask_id: str,
        event: dict,
    ) -> None:
        """Generator 工具调用事件回调（文件模式）"""
        event_type = event.get("type", "unknown")
        
        if event_type == "tool_call":
            tool_name = event.get("tool", event.get("tool_name", ""))
            tool_input = event.get("arguments", event.get("input", {})) or {}
            self._emit_progress("file_operation", {
                "subtask_id": subtask_id,
                "operation": tool_name,
                "path": tool_input.get("path", ""),
                "round": event.get("round", 0),
                "artifacts": [{
                    "kind": "tool_arguments",
                    "content": tool_input,
                }],
            })
        elif event_type == "tool_result":
            tool_name = event.get("tool", event.get("tool_name", ""))
            result = event.get("result", "")
            self._emit_progress("file_result", {
                "subtask_id": subtask_id,
                "operation": tool_name,
                "result_preview": result[:200],
                "round": event.get("round", 0),
                "artifacts": [{
                    "kind": "tool_result",
                    "content": result,
                }],
            })
    
    def _emit_progress(self, event_type: str, data: dict) -> None:
        """发送进度事件"""
        if self.on_progress:
            try:
                self.on_progress(event_type, data)
            except Exception as e:
                logger.warning(f"进度回调失败: {e}")

    def _next_history_sequence(self, task_id: str, subtask_id: str) -> int:
        """Continue sequence numbers after a backend restart."""
        if not self.store:
            return 1
        records = self.store.list_execution_records(task_id, subtask_id, limit=1)
        messages = self.store.list_messages(task_id, subtask_id, limit=1)
        last_record = records[-1].sequence if records else 0
        last_message = messages[-1].sequence if messages else 0
        return max(last_record, last_message) + 1

    def _next_history_id(self, key: tuple[str, str]) -> int:
        sequence = self._history_sequences.get(key, 0)
        self._history_sequences[key] = sequence + 1
        return sequence

    def _append_history_message(
        self,
        task_id: str,
        subtask_id: str,
        attempt_id: str,
        agent: str,
        role: str,
        content,
        round_num: int,
    ) -> ConversationMessage:
        key = (task_id, subtask_id)
        message = ConversationMessage(
            id=f"msg_{uuid.uuid4().hex}",
            task_id=task_id,
            subtask_id=subtask_id,
            attempt_id=attempt_id,
            sequence=self._next_history_id(key),
            agent=agent,
            role=role,
            content=content,
            round=round_num,
        )
        self.store.append_message(message)
        return message

    def _append_execution_record(
        self,
        task_id: str,
        subtask_id: str,
        attempt_id: str,
        phase: str,
        agent: str,
        round_num: int,
        summary: str,
        message_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> ExecutionRecord:
        key = (task_id, subtask_id)
        record = ExecutionRecord(
            id=f"exec_{uuid.uuid4().hex}",
            task_id=task_id,
            subtask_id=subtask_id,
            attempt_id=attempt_id,
            sequence=self._next_history_id(key),
            phase=phase,
            agent=agent,
            round=round_num,
            summary=summary,
            message_ids=message_ids or [],
            metadata=metadata or {},
        )
        self.store.append_execution_record(record)
        return record

    def _save_history_snapshot(
        self,
        task_id: str,
        subtask_id: str,
        attempt_id: str,
        round_num: int,
        phase: str,
    ) -> None:
        key = (task_id, subtask_id)
        sequence = self._history_sequences.get(key, 0)
        self.store.save_execution_snapshot(
            ExecutionSnapshot(
                task_id=task_id,
                subtask_id=subtask_id,
                attempt_id=attempt_id,
                snapshot_id=f"snapshot_{uuid.uuid4().hex}",
                phase=phase,
                round=round_num,
                step=0,
                workspace_path=self.workspace.root,
                message_sequence=sequence,
                execution_sequence=sequence,
            )
        )
