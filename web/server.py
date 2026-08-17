"""
Generator-Critic Web 服务
基于 FastAPI + SSE，提供流式、可交互的多轮对话界面

启动方式：
    python web/server.py

然后浏览器访问：http://127.0.0.1:8000
"""

import asyncio
import json
import os
import sys
import threading
import uuid

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

from config.settings import get_config, setup_logging
from src.orchestrator import Orchestrator

setup_logging()

app = FastAPI(title="Generator-Critic Web")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# 活跃运行表：run_id -> Orchestrator，用于支持 /api/stop 中断后台迭代
_active_runs = {}
_active_runs_lock = threading.Lock()


@app.get("/")
async def index():
    """返回前端页面"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
