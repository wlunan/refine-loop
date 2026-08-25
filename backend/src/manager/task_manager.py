"""
任务管理器
协调 TaskPlanner 和 TaskExecutor，管理任务生命周期
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional

from config.settings import get_config
from src.agents.critic import CriticAgent
from src.agents.generator import GeneratorAgent
from src.executor.task_executor import TaskContext, TaskExecutor
from src.models.task import (
    Checkpoint,
    SubTask,
    Task,
    TaskPlan,
    TaskProgress,
    TaskStatus,
)
from src.planner.task_planner import TaskPlanner
from src.store.state_store import StateStore
from src.tools.filesystem import FileWorkspace

logger = logging.getLogger(__name__)


class TaskManager:
    """
    任务管理器
    
    职责：
    - 任务创建与分解
    - 任务执行调度
    - 任务暂停/恢复/取消
    - 进度追踪与通知
    """
    
    def __init__(
        self,
        store: Optional[StateStore] = None,
        on_task_event: Optional[Callable[[str, dict], None]] = None,
    ):
        """
        初始化任务管理器
        
        Args:
            store: 状态存储（默认使用 .task_store 目录）
            on_task_event: 任务事件回调，签名: (event_type, data)
        """
        self.store = store or StateStore()
        self.on_task_event = on_task_event
        
        # 运行中的任务 {task_id: thread}
        self._running_tasks: Dict[str, threading.Thread] = {}
        # 任务执行器 {task_id: TaskExecutor}
        self._executors: Dict[str, TaskExecutor] = {}
        # 任务锁 {task_id: threading.Lock}
        self._task_locks: Dict[str, threading.Lock] = {}
        
        logger.info("TaskManager 初始化完成")
    
    # ------------------------------------------------------------------
    # 任务生命周期
    # ------------------------------------------------------------------
    
    def create_task(
        self,
        requirement: str,
        workspace_dir: str,
        domain: str = "code",
        llm=None,
    ) -> Task:
        """
        创建新任务
        
        Args:
            requirement: 用户需求描述
            workspace_dir: 工作目录
            domain: 任务领域
            llm: 用于任务分解的 LLM
            
        Returns:
            创建的任务对象
        """
        # 生成任务 ID
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        # 创建任务对象
        task = Task(
            id=task_id,
            title=requirement[:50] + ("..." if len(requirement) > 50 else ""),
            description=requirement,
            workspace_dir=workspace_dir,
            domain=domain,
            status=TaskStatus.PENDING,
        )
        
        # 保存任务
        self.store.save_task(task)
        
        # 发送事件
        self._emit_event("task_created", {
            "task_id": task_id,
            "title": task.title,
        })
        
        logger.info(f"任务已创建: {task_id}")
        return task
    
    def plan_task(
        self,
        task_id: str,
        llm=None,
    ) -> Task:
        """
        分解任务
        
        Args:
            task_id: 任务 ID
            llm: 用于分解的 LLM
            
        Returns:
            更新后的任务对象
        """
        task = self._load_task(task_id)
        
        # 更新状态
        task.status = TaskStatus.PLANNING
        self.store.save_task(task)
        
        # 发送事件
        self._emit_event("task_planning", {"task_id": task_id})
        
        try:
            # 创建工作区
            workspace = FileWorkspace(task.workspace_dir)
            
            # 创建分解器
            planner = TaskPlanner(
                llm=llm or self._create_llm(),
                workspace=workspace,
            )
            
            # 执行分解
            plan = planner.plan(task.description)
            
            # 更新任务
            task.plan = plan
            task.status = TaskStatus.PENDING
            self.store.save_task(task)
            
            # 发送事件
            self._emit_event("task_planned", {
                "task_id": task_id,
                "subtask_count": len(plan.subtasks),
            })
            
            logger.info(
                f"任务分解完成: {task_id}, "
                f"{len(plan.subtasks)} 个子任务"
            )
            
        except Exception as e:
            logger.error(f"任务分解失败: {task_id}, {e}")
            task.status = TaskStatus.FAILED
            task.error = f"任务分解失败: {e}"
            self.store.save_task(task)
            raise
        
        return task
    
    def start_task(
        self,
        task_id: str,
        llm=None,
        generator: Optional[GeneratorAgent] = None,
        critic: Optional[CriticAgent] = None,
    ) -> None:
        """
        启动任务执行（异步）
        
        Args:
            task_id: 任务 ID
            llm: 用于任务分解的 LLM（如果尚未分解）
            generator: 自定义 Generator
            critic: 自定义 Critic
        """
        task = self._load_task(task_id)
        
        # 如果尚未分解，先执行分解
        if task.plan is None:
            task = self.plan_task(task_id, llm=llm)
        
        # 检查状态
        if task.status not in (TaskStatus.PENDING, TaskStatus.PAUSED):
            raise ValueError(f"任务状态不允许启动: {task.status}")
        
        # 更新状态
        task.status = TaskStatus.RUNNING
        task.error = None
        self.store.save_task(task)
        
        # 创建执行器（默认使用文件模式，直接操作工作区文件）
        workspace = FileWorkspace(task.workspace_dir)
        executor = TaskExecutor(
            workspace=workspace,
            store=self.store,
            generator=generator,
            critic=critic,
            use_file_mode=True,  # 启用文件模式，代码会写入实际文件
            on_progress=lambda et, d: self._on_executor_progress(task_id, et, d),
        )
        self._executors[task_id] = executor
        
        # 创建锁
        self._task_locks[task_id] = threading.Lock()
        
        # 启动执行线程
        thread = threading.Thread(
            target=self._execute_task,
            args=(task_id, executor, generator, critic),
            daemon=True,
            name=f"task-{task_id}",
        )
        self._running_tasks[task_id] = thread
        thread.start()
        
        # 发送事件
        self._emit_event("task_started", {"task_id": task_id})
        
        logger.info(f"任务已启动: {task_id}")
    
    def pause_task(self, task_id: str) -> None:
        """
        暂停任务
        
        Args:
            task_id: 任务 ID
        """
        task = self._load_task(task_id)
        
        if task.status != TaskStatus.RUNNING:
            raise ValueError(f"任务不在运行状态: {task.status}")
        
        # 通知执行器停止
        if task_id in self._executors:
            self._executors[task_id].stop()
        
        # 更新状态
        task.status = TaskStatus.PAUSED
        self.store.save_task(task)
        
        # 发送事件
        self._emit_event("task_paused", {"task_id": task_id})
        
        logger.info(f"任务已暂停: {task_id}")
    
    def resume_task(self, task_id: str, **kwargs) -> None:
        """
        恢复任务
        
        Args:
            task_id: 任务 ID
        """
        task = self._load_task(task_id)
        
        if task.status != TaskStatus.PAUSED:
            raise ValueError(f"任务不在暂停状态: {task.status}")
        
        # 重新启动
        self.start_task(task_id, **kwargs)
        
        logger.info(f"任务已恢复: {task_id}")
    
    def cancel_task(self, task_id: str) -> None:
        """
        取消任务
        
        Args:
            task_id: 任务 ID
        """
        task = self._load_task(task_id)
        
        if task.is_finished:
            raise ValueError(f"任务已结束: {task.status}")
        
        # 通知执行器停止
        if task_id in self._executors:
            self._executors[task_id].stop()
        
        # 更新状态
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        self.store.save_task(task)
        
        # 清理
        self._cleanup_task(task_id)
        
        # 发送事件
        self._emit_event("task_cancelled", {"task_id": task_id})
        
        logger.info(f"任务已取消: {task_id}")
    
    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------
    
    def get_task(self, task_id: str) -> Task:
        """获取任务详情"""
        return self._load_task(task_id)
    
    def get_progress(self, task_id: str) -> TaskProgress:
        """获取任务进度"""
        task = self._load_task(task_id)
        
        completed = 0
        total = 0
        current_subtask = None
        
        if task.plan:
            total = len(task.plan.subtasks)
            completed = sum(
                1 for st in task.plan.subtasks
                if st.status == TaskStatus.COMPLETED
            )
            if task.current_subtask_id:
                current = task.plan.get_subtask_by_id(task.current_subtask_id)
                if current:
                    current_subtask = current.title
        
        return TaskProgress(
            task_id=task_id,
            status=task.status,
            progress_percent=task.progress_percent,
            current_subtask=current_subtask,
            completed_subtasks=completed,
            total_subtasks=total,
            total_tokens=task.total_tokens,
            message=self._get_status_message(task),
        )
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        """列出任务"""
        return self.store.list_tasks(status=status, limit=limit)
    
    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    
    def _execute_task(
        self,
        task_id: str,
        executor: TaskExecutor,
        generator: Optional[GeneratorAgent],
        critic: Optional[CriticAgent],
    ) -> None:
        """执行任务（在线程中运行）"""
        task = self._load_task(task_id)
        
        try:
            # 创建上下文
            workspace = FileWorkspace(task.workspace_dir)
            context = TaskContext(workspace=workspace)
            
            # 按依赖顺序执行子任务
            while True:
                # 检查是否被取消
                if task.status == TaskStatus.CANCELLED:
                    break
                
                # 获取可执行的子任务
                executable = task.plan.get_executable_subtasks()
                if not executable:
                    # 没有可执行的任务，检查是否全部完成
                    all_completed = all(
                        st.status == TaskStatus.COMPLETED
                        for st in task.plan.subtasks
                    )
                    if all_completed:
                        break
                    else:
                        # 有任务失败或循环依赖
                        task.status = TaskStatus.FAILED
                        task.error = "存在无法执行的子任务"
                        break
                
                # 执行第一个可执行的子任务
                subtask = executable[0]
                task.current_subtask_id = subtask.id
                self.store.save_task(task)
                
                # 执行子任务
                completed_subtask = executor.execute(
                    subtask=subtask,
                    context=context,
                    task_id=task_id,
                )
                
                # 更新子任务状态
                for i, st in enumerate(task.plan.subtasks):
                    if st.id == completed_subtask.id:
                        task.plan.subtasks[i] = completed_subtask
                        break
                
                # 记录结果到上下文
                if completed_subtask.status == TaskStatus.COMPLETED:
                    context.completed_results[completed_subtask.id] = (
                        completed_subtask.result or ""
                    )
                else:
                    # 子任务失败，整个任务失败
                    task.status = TaskStatus.FAILED
                    task.error = f"子任务失败: {completed_subtask.error}"
                    break
                
                # 保存进度
                self.store.save_task(task)
            
            # 检查最终状态
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
            
        except Exception as e:
            logger.error(f"任务执行异常: {task_id}, {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
        
        finally:
            # 保存最终状态
            self.store.save_task(task)
            
            # 发送完成事件
            self._emit_event("task_completed" if task.status == TaskStatus.COMPLETED else "task_failed", {
                "task_id": task_id,
                "status": task.status.value,
                "error": task.error,
            })
            
            # 清理
            self._cleanup_task(task_id)
    
    def _load_task(self, task_id: str) -> Task:
        """加载任务"""
        task = self.store.load_task(task_id)
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")
        return task
    
    def _cleanup_task(self, task_id: str) -> None:
        """清理任务资源"""
        self._running_tasks.pop(task_id, None)
        self._executors.pop(task_id, None)
        self._task_locks.pop(task_id, None)
    
    def _on_executor_progress(
        self,
        task_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """执行器进度回调"""
        data["task_id"] = task_id
        self._emit_event(event_type, data)
    
    def _emit_event(self, event_type: str, data: dict) -> None:
        """发送事件"""
        if self.on_task_event:
            try:
                self.on_task_event(event_type, data)
            except Exception as e:
                logger.warning(f"事件回调失败: {e}")
    
    def _get_status_message(self, task: Task) -> str:
        """获取状态描述消息"""
        if task.status == TaskStatus.PENDING:
            return "等待执行"
        elif task.status == TaskStatus.PLANNING:
            return "正在分析需求..."
        elif task.status == TaskStatus.RUNNING:
            if task.current_subtask:
                return f"正在执行: {task.current_subtask.title}"
            return "执行中..."
        elif task.status == TaskStatus.PAUSED:
            return "已暂停"
        elif task.status == TaskStatus.COMPLETED:
            return "已完成"
        elif task.status == TaskStatus.FAILED:
            return f"失败: {task.error}"
        elif task.status == TaskStatus.CANCELLED:
            return "已取消"
        return ""
    
    def _create_llm(self):
        """创建默认 LLM 实例"""
        from langchain_openai import ChatOpenAI
        config = get_config()
        return ChatOpenAI(
            model=config.llm.generator_model,
            api_key=config.llm.api_key,
            base_url=config.llm.api_base,
            temperature=0.7,
        )
