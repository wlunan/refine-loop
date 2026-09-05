"""
任务管理路由：长时间运行任务的 REST API 与 SSE 事件流

包含：
- POST   /api/tasks                   创建任务
- GET    /api/tasks                   任务列表
- GET    /api/tasks/{task_id}         任务详情
- POST   /api/tasks/{task_id}/start   启动任务
- POST   /api/tasks/{task_id}/pause   暂停任务
- POST   /api/tasks/{task_id}/resume  恢复任务
- POST   /api/tasks/{task_id}/cancel  取消任务
- GET    /api/tasks/{task_id}/progress 任务进度
- GET    /api/tasks/{task_id}/events  任务实时事件（SSE）
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.settings import get_config
from src.manager.task_manager import TaskManager
from src.models.run import RunConfig, VerificationRequestProfile
from src.models.task import TaskStatus
from src.tools.project_detector import detect_verification_plan

from .common import sse_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# 任务管理器实例（单例）
task_manager = TaskManager()

# SSE 事件队列：{task_id: [queue1, queue2, ...]}
_sse_queues: Dict[str, List[asyncio.Queue]] = {}
_sse_lock = threading.Lock()

# 主线程事件循环引用：在 FastAPI 启动时捕获，
# 供后台任务线程通过 call_soon_threadsafe 安全投递事件到 SSE 队列
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """由 server 启动时注入主事件循环引用"""
    global _main_loop
    _main_loop = loop


# ------------------------------------------------------------------
# 请求/响应模型
# ------------------------------------------------------------------

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    requirement: str
    workspace_dir: str
    domain: str = "code"
    max_rounds: int = 3
    threshold: int = 85
    # "auto" is resolved from the selected workspace before task creation.
    verification_profile: VerificationRequestProfile = "auto"


class TaskResponse(BaseModel):
    """任务列表项"""
    id: str
    title: str
    status: str
    progress_percent: float
    subtask_count: int = 0
    completed_subtasks: int = 0
    created_at: str
    error: Optional[str] = None


# ------------------------------------------------------------------
# 事件广播（由 TaskManager 回调触发，从后台线程调用）
# ------------------------------------------------------------------

def _broadcast_event(task_id: str, event: dict) -> None:
    """广播事件到指定任务的所有 SSE 连接"""
    loop = _main_loop
    if loop is None:
        logger.warning("主事件循环未就绪，丢弃事件: %s", event.get("type"))
        return

    with _sse_lock:
        queues = _sse_queues.get(task_id, [])

    for queue in queues:
        loop.call_soon_threadsafe(queue.put_nowait, event)


def _on_task_event(event_type: str, data: dict) -> None:
    """TaskManager 事件回调 → 广播为 SSE 事件"""
    task_id = data.get("task_id")
    if task_id:
        event = {"type": event_type, **data}
        _broadcast_event(task_id, event)


# 初始化任务管理器的事件回调
task_manager.on_task_event = _on_task_event


# ------------------------------------------------------------------
# 任务管理 API
# ------------------------------------------------------------------

@router.post("")
async def create_task(request: CreateTaskRequest):
    """
    创建新任务

    Args:
        requirement: 需求描述
        workspace_dir: 工作目录
        domain: 任务领域
    """
    try:
        settings = get_config().orchestrator
        detection = detect_verification_plan(request.workspace_dir)
        resolved_profile = (
            detection["profile"]
            if request.verification_profile == "auto"
            else request.verification_profile
        )
        run_config = RunConfig.from_profile(
            resolved_profile,
            max_rounds=request.max_rounds,
            score_threshold=request.threshold,
            round_token_budget=settings.round_token_budget,
            total_token_budget=settings.total_token_budget,
        )
        task = task_manager.create_task(
            requirement=request.requirement,
            workspace_dir=request.workspace_dir,
            domain=request.domain,
            run_config=run_config,
        )
        task.metadata["verification_detection"] = {
            **detection,
            "selection": request.verification_profile,
        }
        task_manager.store.save_task(task)
        return {
            "task_id": task.id,
            "title": task.title,
            "verification_detection": task.metadata["verification_detection"],
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"创建任务失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_tasks(status: Optional[str] = None, limit: int = 50):
    """列出任务"""
    task_status = None
    if status:
        try:
            task_status = TaskStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态: {status}")

    tasks = task_manager.list_tasks(status=task_status, limit=limit)

    return [
        TaskResponse(
            id=t.id,
            title=t.title,
            status=t.status.value,
            progress_percent=t.progress_percent,
            subtask_count=len(t.plan.subtasks) if t.plan else 0,
            completed_subtasks=sum(
                1 for st in t.plan.subtasks
                if st.status == TaskStatus.COMPLETED
            ) if t.plan else 0,
            created_at=t.created_at.isoformat(),
            error=t.error,
        )
        for t in tasks
    ]


@router.get("/detect-verification")
async def detect_verification(workspace_dir: str):
    """Preview the safe verification plan inferred from a local workspace."""
    try:
        return detect_verification_plan(workspace_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    try:
        task = task_manager.get_task(task_id)
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "progress_percent": task.progress_percent,
            "workspace_dir": task.workspace_dir,
            "domain": task.domain,
            "run_config": task.run_config.model_dump() if task.run_config else None,
            "metadata": task.metadata,
            "changeset": task.changeset.model_dump() if task.changeset else None,
            "error": task.error,
            "total_tokens": task.total_tokens,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "subtasks": [
                {
                    "id": st.id,
                    "title": st.title,
                    "description": st.description,
                    "status": st.status.value,
                    "dependencies": st.dependencies,
                    "score": st.score,
                    "iterations": st.iterations,
                    "error": st.error,
                }
                for st in (task.plan.subtasks if task.plan else [])
            ],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{task_id}/start")
async def start_task(task_id: str):
    """启动任务"""
    try:
        task_manager.start_task(task_id)
        return {"message": "任务已启动"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    """暂停任务"""
    try:
        task_manager.pause_task(task_id)
        return {"message": "任务已暂停"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    """恢复任务"""
    try:
        task_manager.resume_task(task_id)
        return {"message": "任务已恢复"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务"""
    try:
        task_manager.cancel_task(task_id)
        return {"message": "任务已取消"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{task_id}/changeset")
async def get_changeset(task_id: str):
    """获取等待审阅的 Git diff。"""
    try:
        task = task_manager.get_task(task_id)
        if not task.changeset:
            raise HTTPException(status_code=404, detail="任务没有变更集")
        return task.changeset
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{task_id}/changeset/approve")
async def approve_changeset(task_id: str):
    """确认将隔离 worktree 的变更应用到原始工作区。"""
    try:
        task_manager.approve_changeset(task_id)
        return {"message": "变更已应用"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{task_id}/changeset/discard")
async def discard_changeset(task_id: str):
    """丢弃隔离 worktree 的变更。"""
    try:
        task_manager.discard_changeset(task_id)
        return {"message": "变更已丢弃"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{task_id}/progress")
async def get_progress(task_id: str):
    """获取任务进度"""
    try:
        progress = task_manager.get_progress(task_id)
        return progress
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{task_id}/subtasks/{subtask_id}/rounds")
async def get_subtask_rounds(task_id: str, subtask_id: str):
    """
    获取子任务每一轮迭代的详细记录（生成草稿 + Critic 审查）

    数据来源为执行过程中保存的 Checkpoint。
    """
    # 验证任务存在
    try:
        task_manager.get_task(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 从存储读取该子任务的检查点（每轮一条）
    try:
        checkpoints = task_manager.store.list_checkpoints(
            task_id=task_id,
            subtask_id=subtask_id,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取迭代记录失败: {e}")

    # 按轮次排序
    checkpoints.sort(key=lambda cp: cp.round)

    return [
        {
            "round": cp.round,
            "draft": cp.draft,
            "score": cp.score,
            "acceptable": cp.acceptable,
            "issues": cp.issues,
            "suggestions": cp.suggestions,
            "summary": cp.summary,
            "verification_summary": (
                cp.verification_summary.model_dump()
                if cp.verification_summary else None
            ),
            "tokens_used": cp.tokens_used,
            "created_at": cp.created_at.isoformat(),
        }
        for cp in checkpoints
    ]


@router.get("/{task_id}/timeline")
async def get_timeline(task_id: str, limit: int = 200):
    """Return persisted task evidence in chronological order."""
    try:
        task_manager.get_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return task_manager.store.list_events(task_id, limit=max(1, min(limit, 500)))


@router.get("/{task_id}/events")
async def task_events(task_id: str, request: Request):
    """
    SSE 事件流：实时推送任务执行进度
    """
    # 验证任务存在
    try:
        task_manager.get_task(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 创建事件队列
    queue: asyncio.Queue = asyncio.Queue()

    with _sse_lock:
        if task_id not in _sse_queues:
            _sse_queues[task_id] = []
        _sse_queues[task_id].append(queue)

    async def event_generator():
        try:
            while True:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    break

                try:
                    # 等待事件，超时后发送心跳
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

                    # 如果是结束事件，停止推送
                    if event.get("type") in (
                        "task_completed",
                        "task_failed",
                        "task_cancelled",
                    ):
                        break
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield ": heartbeat\n\n"
        finally:
            # 清理队列
            with _sse_lock:
                if task_id in _sse_queues:
                    _sse_queues[task_id].remove(queue)
                    if not _sse_queues[task_id]:
                        del _sse_queues[task_id]

    return sse_response(event_generator())
