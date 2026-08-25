"""
Generator-Critic 统一 Web 服务
基于 FastAPI + SSE，提供：
1. 工作台流式接口（文本生成 / 文件操作）
2. 长时间运行任务管理 API
3. Vue 前端构建产物托管（SPA）

单一后端、单一端口（默认 8000）。

启动方式：
    python backend/server.py

然后浏览器访问：http://127.0.0.1:8000
"""

import asyncio
import json
import logging
import os
import sys
import threading
import uuid
from typing import Dict, List, Optional

# 添加 backend 目录到路径（src/、config/ 位于其下）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import get_config, setup_logging
from src.manager.task_manager import TaskManager
from src.models.task import TaskStatus
from src.orchestrator import Orchestrator

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Generator-Critic Web")

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

# ------------------------------------------------------------------
# 工作台：活跃运行表 run_id -> Orchestrator，用于 /api/stop 中断迭代
# ------------------------------------------------------------------
_active_runs = {}
_active_runs_lock = threading.Lock()

# ------------------------------------------------------------------
# 任务管理：SSE 事件队列 {task_id: [queue1, queue2, ...]}
# ------------------------------------------------------------------
_sse_queues: Dict[str, List[asyncio.Queue]] = {}
_sse_lock = threading.Lock()


def _event_stream_response(queue: asyncio.Queue, orchestrator: Orchestrator):
    """构造 SSE StreamingResponse；客户端断连时同步中断后台迭代"""
    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") == "end":
                    break
        finally:
            orchestrator.stop()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，保证实时推送
        },
    )


def _truncate(text, limit: int = 2000) -> str:
    """截断长文本（用于工具结果推送，避免撑爆 SSE）"""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [已截断，共 {len(text)} 字符]"


# 任务管理器实例
task_manager = TaskManager()


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
# 前端托管
# ------------------------------------------------------------------

@app.get("/")
async def index():
    """返回前端页面（优先 Vue 构建产物，回退旧版页面）"""
    spa_index = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(spa_index):
        return FileResponse(spa_index)
    return FileResponse(os.path.join(STATIC_DIR, "tasks.html"))


# ------------------------------------------------------------------
# 工作台：流式接口
# ------------------------------------------------------------------

@app.get("/api/stream")
async def stream(request: Request):
    """
    SSE 流式接口

    接收任务参数，在后台线程运行 Generator-Critic 迭代，
    通过 SSE 实时推送每一轮的生成过程与审查结果。

    查询参数：
        task:       任务描述（必填）
        domain:     领域，general/code/writing/design（默认 general）
        max_rounds: 最大迭代轮数（默认 5）
        threshold:  收敛评分阈值（默认 85）
    """
    task = request.query_params.get("task", "").strip()
    domain = request.query_params.get("domain", "general")
    max_rounds = int(request.query_params.get("max_rounds", "5"))
    threshold = int(request.query_params.get("threshold", "85"))

    if not task:
        # 任务为空时直接返回一条错误事件
        async def _empty():
            yield "data: " + json.dumps(
                {"type": "error", "message": "任务描述不能为空"}, ensure_ascii=False
            ) + "\n\n"
            yield "data: " + json.dumps({"type": "end"}) + "\n\n"

        return StreamingResponse(
            _empty(), media_type="text/event-stream"
        )

    run_id = uuid.uuid4().hex

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event: dict):
        """从后台线程安全地把事件放入队列"""
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def on_token(round_num: int, token: str):
        emit({"type": "token", "round": round_num, "token": token})

    def on_round(round_num: int, draft: str, critique):
        emit({
            "type": "critic",
            "round": round_num,
            "score": critique.score,
            "acceptable": critique.acceptable,
            "issues": critique.issues,
            "suggestions": critique.suggestions,
            "summary": critique.summary,
        })

    # 在创建 Orchestrator 之前修改全局配置（get_config 返回单例）
    config = get_config()
    config.orchestrator.convergence_score_threshold = threshold

    orchestrator = Orchestrator(
        domain=domain,
        max_rounds=max_rounds,
        on_generator_token=on_token,
        on_round_complete=on_round,
    )
    with _active_runs_lock:
        _active_runs[run_id] = orchestrator

    def run():
        """在后台线程中执行迭代，避免阻塞事件循环"""
        try:
            emit({"type": "run_id", "run_id": run_id})
            emit({"type": "status", "message": "开始迭代..."})
            result = orchestrator.run(task)
            emit({
                "type": "done",
                "final_output": result.final_output,
                "iterations": result.iterations,
                "converged": result.converged,
                "convergence_reason": result.convergence_reason,
                "score_trend": result.score_trend,
                "total_time": round(result.total_time_seconds, 2),
            })
        except Exception as e:  # noqa: BLE001
            emit({"type": "error", "message": str(e)})
        finally:
            with _active_runs_lock:
                _active_runs.pop(run_id, None)
            emit({"type": "end"})

    threading.Thread(target=run, daemon=True).start()

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") == "end":
                    break
        finally:
            # 客户端断开（主动停止或直接关闭页面）时，同步中断后台迭代
            orchestrator.stop()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，保证实时推送
        },
    )


@app.post("/api/stop")
async def stop(request: Request):
    """
    停止指定 run_id 对应的迭代任务

    查询参数：
        run_id: 由 /api/stream 返回的运行 ID
    """
    run_id = request.query_params.get("run_id", "")
    with _active_runs_lock:
        orchestrator = _active_runs.get(run_id)
    if orchestrator is None:
        return {"ok": False, "message": "未找到运行中的任务"}
    orchestrator.stop()
    return {"ok": True, "message": "已发送停止请求"}


@app.get("/api/browse_dir")
async def browse_dir(path: str = ""):
    """
    浏览目录（供前端文件夹选择器使用）

    查询参数：
        path: 要浏览的目录绝对路径，为空时返回盘符列表（Windows）或根目录
    """
    if not path:
        if os.name == "nt":
            drives = [
                f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if os.path.exists(f"{d}:\\")
            ]
            return {"path": "", "parent": None, "exists": True, "dirs": drives}
        path = "/"

    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return {"path": path, "parent": None, "exists": False, "dirs": []}

    dirs = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full) and not name.startswith("."):
                dirs.append(name)
    except PermissionError:
        pass

    parent = os.path.dirname(path)
    return {
        "path": path,
        "parent": parent if parent != path else None,
        "exists": True,
        "dirs": dirs,
    }


@app.get("/api/stream_files")
async def stream_files(request: Request):
    """
    文件模式 SSE 流式接口

    Generator 在指定工作区目录内操作真实文件（创建/读取/修改/删除），
    Critic 审查文件快照，实时推送工具调用过程与审查结果。

    查询参数：
        task:      任务描述（必填）
        workspace: 工作区目录绝对路径（必填）
        domain:    领域（默认 code）
        max_rounds: 最大迭代轮数（默认 3）
        threshold: 收敛评分阈值（默认 85）
    """
    task = request.query_params.get("task", "").strip()
    workspace = request.query_params.get("workspace", "").strip()
    domain = request.query_params.get("domain", "code")
    max_rounds = int(request.query_params.get("max_rounds", "3"))
    threshold = int(request.query_params.get("threshold", "85"))

    async def _error(message: str):
        yield "data: " + json.dumps({"type": "error", "message": message}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "end"}) + "\n\n"

    if not task:
        return StreamingResponse(_error("任务描述不能为空"), media_type="text/event-stream")
    if not workspace:
        return StreamingResponse(_error("请选择工作区目录"), media_type="text/event-stream")
    if not os.path.isdir(workspace):
        return StreamingResponse(_error(f"工作区目录不存在: {workspace}"), media_type="text/event-stream")

    run_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event: dict):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def on_generator_event(event: dict):
        emit({
            "type": "tool",
            "subtype": event.get("type"),  # "tool_call" 或 "tool_result"
            "round": event.get("round"),
            "tool": event.get("tool"),
            "arguments": event.get("arguments", {}),
            "result": _truncate(event.get("result", "")),
        })

    def on_round(round_num: int, snapshot: str, critique):
        emit({
            "type": "critic",
            "round": round_num,
            "score": critique.score,
            "acceptable": critique.acceptable,
            "issues": critique.issues,
            "suggestions": critique.suggestions,
            "summary": critique.summary,
        })

    config = get_config()
    config.orchestrator.convergence_score_threshold = threshold

    orchestrator = Orchestrator(
        domain=domain,
        max_rounds=max_rounds,
        on_round_complete=on_round,
    )
    with _active_runs_lock:
        _active_runs[run_id] = orchestrator

    def run():
        try:
            emit({"type": "run_id", "run_id": run_id})
            emit({"type": "status", "message": f"开始文件模式迭代，工作区: {workspace}"})
            result = orchestrator.run_with_files(
                task=task,
                workspace_dir=workspace,
                on_generator_event=on_generator_event,
                on_round_complete=on_round,
            )
            emit({
                "type": "done",
                "final_output": _truncate(result.final_output, 20000),
                "iterations": result.iterations,
                "converged": result.converged,
                "convergence_reason": result.convergence_reason,
                "score_trend": result.score_trend,
                "total_time": round(result.total_time_seconds, 2),
            })
        except Exception as e:  # noqa: BLE001
            emit({"type": "error", "message": str(e)})
        finally:
            with _active_runs_lock:
                _active_runs.pop(run_id, None)
            emit({"type": "end"})

    threading.Thread(target=run, daemon=True).start()
    return _event_stream_response(queue, orchestrator)


# ------------------------------------------------------------------
# 任务管理 API
# ------------------------------------------------------------------

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
# 任务事件广播（由 TaskManager 回调触发）
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


# ------------------------------------------------------------------
# 静态托管与 SPA fallback（必须放在所有 API 路由之后）
# ------------------------------------------------------------------

# 挂载静态文件（Vue 构建产物）
if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """SPA fallback - 所有非 API 路由返回前端页面"""
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
    print("Generator-Critic Web")
    print("=" * 50)
    print("服务地址: http://127.0.0.1:8000")
    print("API 文档: http://127.0.0.1:8000/docs")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=8000)
