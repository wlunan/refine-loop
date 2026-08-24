"""
任务管理 Web 服务
基于 FastAPI + SSE，提供长时间运行任务的管理接口

启动方式：
    python web/task_server.py

然后浏览器访问：http://127.0.0.1:8001
"""

import asyncio
import json
import logging
import os
import sys
import threading
import uuid
from typing import Dict, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import get_config, setup_logging
from src.manager.task_manager import TaskManager
from src.models.task import TaskStatus

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Task Manager API")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DIST_DIR = os.path.join(STATIC_DIR, "dist")

# 任务管理器实例
task_manager = TaskManager()

# SSE 事件队列 {task_id: [queue1, queue2, ...]}
_sse_queues: Dict[str, List[asyncio.Queue]] = {}
_sse_lock = threading.Lock()


# ------------------------------------------------------------------
# 请求/响应模型
# ------------------------------------------------------------------

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    requirement: str
    workspace_dir: str
    domain: str = "code"


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    title: str
    status: str
    progress_percent: float
    subtask_count: int = 0
    completed_subtasks: int = 0
    created_at: str
    error: Optional[str] = None


class ProgressResponse(BaseModel):
    """进度响应"""
    task_id: str
    status: str
    progress_percent: float
    current_subtask: Optional[str] = None
    completed_subtasks: int
    total_subtasks: int
    total_tokens: int
    message: str


# ------------------------------------------------------------------
# API 路由
# ------------------------------------------------------------------

@app.get("/")
async def index():
    """返回前端页面"""
    return FileResponse(os.path.join(STATIC_DIR, "tasks.html"))


@app.post("/api/tasks")
async def create_task(request: CreateTaskRequest):
    """
    创建新任务
    
    Args:
        requirement: 需求描述
        workspace_dir: 工作目录
        domain: 任务领域
    """
    try:
        task = task_manager.create_task(
            requirement=request.requirement,
            workspace_dir=request.workspace_dir,
            domain=request.domain,
        )
        return {"task_id": task.id, "title": task.title}
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tasks")
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


@app.get("/api/tasks/{task_id}")
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


@app.post("/api/tasks/{task_id}/start")
async def start_task(task_id: str):
    """启动任务"""
    try:
        task_manager.start_task(task_id)
        return {"message": "任务已启动"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    """暂停任务"""
    try:
        task_manager.pause_task(task_id)
        return {"message": "任务已暂停"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """恢复任务"""
    try:
        task_manager.resume_task(task_id)
        return {"message": "任务已恢复"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务"""
    try:
        task_manager.cancel_task(task_id)
        return {"message": "任务已取消"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tasks/{task_id}/progress")
async def get_progress(task_id: str):
    """获取任务进度"""
    try:
        progress = task_manager.get_progress(task_id)
        return progress
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: str, request: Request):
    """
    SSE 事件流
    
    实时推送任务执行进度
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
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    
                    # 如果是结束事件，停止推送
                    if event.get("type") in ("task_completed", "task_failed", "task_cancelled"):
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
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------------
# 内部方法
# ------------------------------------------------------------------

def _broadcast_event(task_id: str, event: dict):
    """广播事件到指定任务的所有 SSE 连接"""
    loop = asyncio.get_event_loop()
    
    with _sse_lock:
        queues = _sse_queues.get(task_id, [])
    
    for queue in queues:
        loop.call_soon_threadsafe(queue.put_nowait, event)


def _on_task_event(event_type: str, data: dict):
    """任务事件回调"""
    task_id = data.get("task_id")
    if task_id:
        event = {"type": event_type, **data}
        _broadcast_event(task_id, event)


# 初始化任务管理器的事件回调
task_manager.on_task_event = _on_task_event

# 挂载静态文件（Vue 构建产物）
if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """SPA fallback - 所有非 API 路由返回 index.html"""
    # 尝试返回静态文件
    file_path = os.path.join(DIST_DIR, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    # 否则返回 index.html（SPA 路由）
    index_path = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    # 如果没有构建产物，返回旧版 HTML
    return FileResponse(os.path.join(STATIC_DIR, "tasks.html"))


# ------------------------------------------------------------------
# 启动入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 50)
    print("Task Manager API")
    print("=" * 50)
    print("服务地址: http://127.0.0.1:8001")
    print("API 文档: http://127.0.0.1:8001/docs")
    print("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
