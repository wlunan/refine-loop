"""
工作台路由：文本生成 / 文件操作 的 SSE 流式接口

包含：
- GET /api/stream          文本模式 SSE 流式迭代
- GET /api/stream_files    文件操作模式 SSE 流式迭代
- GET /api/browse_dir      目录浏览（文件夹选择器）
- POST /api/stop           停止运行中的迭代
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from config.settings import get_config
from src.models.run import RunConfig
from src.orchestrator import Orchestrator

from .common import sse_event, sse_response, truncate

router = APIRouter(tags=["workbench"])

# 活跃运行表：run_id -> Orchestrator，用于 /api/stop 中断后台迭代
_active_runs = {}
_active_runs_lock = threading.Lock()


def _emit(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, event: dict):
    """从后台线程安全地把事件放入队列"""
    loop.call_soon_threadsafe(queue.put_nowait, event)


def _build_run_config(max_rounds: int, threshold: int, profile: str = "none") -> RunConfig:
    """从请求参数创建运行实例配置，绝不修改全局 settings 单例。"""
    settings = get_config().orchestrator
    return RunConfig.from_profile(
        profile,  # type: ignore[arg-type]
        max_rounds=max_rounds,
        score_threshold=threshold,
        round_token_budget=settings.round_token_budget,
        total_token_budget=settings.total_token_budget,
    )


@router.get("/api/stream")
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
        async def _empty():
            yield sse_event({"type": "error", "message": "任务描述不能为空"})
            yield sse_event({"type": "end"})

        return sse_response(_empty())

    try:
        run_config = _build_run_config(max_rounds, threshold)
    except (KeyError, ValueError) as e:
        async def _invalid_config():
            yield sse_event({"type": "error", "message": f"运行配置无效: {e}"})
            yield sse_event({"type": "end"})
        return sse_response(_invalid_config())

    run_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_token(round_num: int, token: str):
        _emit(queue, loop, {"type": "token", "round": round_num, "token": token})

    def on_round(round_num: int, draft: str, critique):
        _emit(queue, loop, {
            "type": "critic",
            "round": round_num,
            "score": critique.score,
            "acceptable": critique.acceptable,
            "issues": critique.issues,
            "suggestions": critique.suggestions,
            "summary": critique.summary,
        })

    orchestrator = Orchestrator(
        domain=domain,
        run_config=run_config,
        on_generator_token=on_token,
        on_round_complete=on_round,
    )
    with _active_runs_lock:
        _active_runs[run_id] = orchestrator

    def run():
        """在后台线程中执行迭代，避免阻塞事件循环"""
        try:
            _emit(queue, loop, {"type": "run_id", "run_id": run_id})
            _emit(queue, loop, {"type": "status", "message": "开始迭代..."})
            result = orchestrator.run(task)
            _emit(queue, loop, {
                "type": "done",
                "final_output": result.final_output,
                "iterations": result.iterations,
                "converged": result.converged,
                "convergence_reason": result.convergence_reason,
                "score_trend": result.score_trend,
                "total_time": round(result.total_time_seconds, 2),
            })
        except Exception as e:  # noqa: BLE001
            _emit(queue, loop, {"type": "error", "message": str(e)})
        finally:
            with _active_runs_lock:
                _active_runs.pop(run_id, None)
            _emit(queue, loop, {"type": "end"})

    threading.Thread(target=run, daemon=True).start()

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield sse_event(event)
                if event.get("type") == "end":
                    break
        finally:
            # 客户端断开（主动停止或直接关闭页面）时，同步中断后台迭代
            orchestrator.stop()

    return sse_response(event_generator())


@router.post("/api/stop")
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


@router.get("/api/browse_dir")
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


@router.get("/api/stream_files")
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
    verification_profile = request.query_params.get("verification_profile", "none")

    async def _error(message: str):
        yield sse_event({"type": "error", "message": message})
        yield sse_event({"type": "end"})

    if not task:
        return sse_response(_error("任务描述不能为空"))
    if not workspace:
        return sse_response(_error("请选择工作区目录"))
    if not os.path.isdir(workspace):
        return sse_response(_error(f"工作区目录不存在: {workspace}"))

    try:
        run_config = _build_run_config(
            max_rounds,
            threshold,
            verification_profile,
        )
    except (KeyError, ValueError) as e:
        return sse_response(_error(f"运行配置无效: {e}"))

    run_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_generator_event(event: dict):
        _emit(queue, loop, {
            "type": "tool",
            "subtype": event.get("type"),  # "tool_call" 或 "tool_result"
            "round": event.get("round"),
            "tool": event.get("tool"),
            "arguments": event.get("arguments", {}),
            "result": truncate(event.get("result", "")),
        })

    def on_round(round_num: int, snapshot: str, critique):
        _emit(queue, loop, {
            "type": "critic",
            "round": round_num,
            "score": critique.score,
            "acceptable": critique.acceptable,
            "issues": critique.issues,
            "suggestions": critique.suggestions,
            "summary": critique.summary,
        })

    def on_verification(round_num: int, summary):
        _emit(queue, loop, {
            "type": "verification",
            "round": round_num,
            "profile": summary.profile,
            "passed": summary.passed,
            "results": [result.model_dump() for result in summary.results],
        })

    orchestrator = Orchestrator(
        domain=domain,
        run_config=run_config,
        on_round_complete=on_round,
        on_verification_complete=on_verification,
    )
    with _active_runs_lock:
        _active_runs[run_id] = orchestrator

    def run():
        try:
            _emit(queue, loop, {"type": "run_id", "run_id": run_id})
            _emit(queue, loop, {
                "type": "status",
                "message": f"开始文件模式迭代，工作区: {workspace}",
            })
            result = orchestrator.run_with_files(
                task=task,
                workspace_dir=workspace,
                on_generator_event=on_generator_event,
                on_round_complete=on_round,
            )
            _emit(queue, loop, {
                "type": "done",
                "final_output": truncate(result.final_output, 20000),
                "iterations": result.iterations,
                "converged": result.converged,
                "convergence_reason": result.convergence_reason,
                "score_trend": result.score_trend,
                "total_time": round(result.total_time_seconds, 2),
                "verification": (
                    result.verification_summary.model_dump()
                    if result.verification_summary else None
                ),
            })
        except Exception as e:  # noqa: BLE001
            _emit(queue, loop, {"type": "error", "message": str(e)})
        finally:
            with _active_runs_lock:
                _active_runs.pop(run_id, None)
            _emit(queue, loop, {"type": "end"})

    threading.Thread(target=run, daemon=True).start()

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield sse_event(event)
                if event.get("type") == "end":
                    break
        finally:
            # 客户端断开时同步中断后台迭代
            orchestrator.stop()

    return sse_response(event_generator())
