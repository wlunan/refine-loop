"""
Generator-Critic 统一 Web 服务入口
===================================

分层架构：
- server.py          应用入口：FastAPI app、CORS、路由挂载、前端托管
- routers/           路由层：按业务模块拆分的 APIRouter
  - workbench.py      工作台接口（SSE 流式、目录浏览、停止）
  - tasks.py          任务管理接口（REST + SSE）
- src/               核心业务层：Agent、Orchestrator、TaskManager 等

单一后端、单一端口（默认 8000）。

启动方式：
    python backend/server.py

然后浏览器访问：http://127.0.0.1:8000
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import uuid

# 添加 backend 目录到路径（src/、config/、routers/ 位于其下）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from config.settings import get_config, setup_logging
from src.observability import metrics, set_request_id

from routers import tasks as tasks_router
from routers import workbench as workbench_router

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """捕获主线程事件循环，供后台任务线程通过 call_soon_threadsafe 投递事件"""
    tasks_router.set_main_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="RefineLoop API",
    description="可验证、可恢复、可人工审批的本地代码 Agent 工作台",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# 可观测性中间件：请求日志 + HTTP 指标 + request_id
# ------------------------------------------------------------------

@app.middleware("http")
async def _observability_http(request: Request, call_next):
    """记录每个 HTTP 请求的状态码/耗时，并在响应头注入 X-Request-ID。

    后台任务线程不继承请求上下文，任务级链路 id 由 TaskManager 在
    _execute_task 线程入口显式设置（见 task_manager.py）。
    """
    request_id = uuid.uuid4().hex[:12]
    set_request_id(request_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        status = 500
        raise
    finally:
        duration = time.perf_counter() - started_at
        route = request.scope.get("route")
        path = getattr(route, "path", None) or request.url.path
        metrics.inc(
            "http_requests_total",
            method=request.method,
            path=path,
            status=str(status),
        )
        metrics.observe("http_request_duration_seconds", duration)
        logger.info(
            "HTTP %s %s -> %s (%.0fms)",
            request.method,
            request.url.path,
            status,
            duration * 1000,
        )


# 指标口径帮助文本与动态 gauge（active_tasks 实时读取任务管理器运行线程数）
metrics.register_gauge(
    "active_tasks",
    lambda: len(tasks_router.task_manager._running_tasks),
    help="当前正在运行的任务数",
)
for _name, _help in {
    "tasks_created_total": "创建的任务总数",
    "tasks_started_total": "启动执行的任务总数",
    "tasks_finished_total": "已结束的任务总数（按 status 维度）",
    "llm_calls_total": "LLM 调用总次数（按 agent/model/status 维度）",
    "llm_prompt_tokens_total": "LLM 输入 token 累计",
    "llm_completion_tokens_total": "LLM 输出 token 累计",
    "llm_call_duration_seconds": "LLM 单次调用耗时分布",
    "http_requests_total": "HTTP 请求总数（按 method/path/status 维度）",
    "http_request_duration_seconds": "HTTP 请求耗时分布",
}.items():
    metrics.set_help(_name, _help)


# ------------------------------------------------------------------
# 可观测性端点：健康探针 / 指标（必须注册在 SPA catch-all 之前）
# ------------------------------------------------------------------

@app.get("/healthz")
async def healthz():
    """存活探针：进程活着即返回 200。"""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """就绪探针：LLM 配置已提供、状态存储目录可写。"""
    checks: dict[str, str] = {}
    ok = True
    try:
        get_config()
        checks["llm"] = "ok"
    except Exception as e:  # noqa: BLE001
        ok = False
        checks["llm"] = str(e)
    try:
        os.makedirs(".task_store", exist_ok=True)
        checks["store"] = "ok"
    except Exception as e:  # noqa: BLE001
        ok = False
        checks["store"] = str(e)
    if not ok:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "checks": checks},
        )
    return {"status": "ok", "checks": checks}


@app.get("/metrics")
async def metrics_text():
    """Prometheus 文本格式指标（OpenMetrics v0.0.4 子集）。"""
    return Response(
        content=metrics.render_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/api/system/metrics")
async def system_metrics():
    """JSON 指标快照，供前端统计卡 / 调试页面消费。"""
    return metrics.snapshot_json()


# 路由挂载
app.include_router(workbench_router.router)
app.include_router(tasks_router.router)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DIST_DIR = os.path.join(STATIC_DIR, "dist")


# ------------------------------------------------------------------
# 前端托管（必须放在所有 API 路由之后）
# ------------------------------------------------------------------

@app.get("/")
async def index():
    """返回前端页面（Vue 构建产物，需先执行 npm run build）"""
    spa_index = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(spa_index):
        return FileResponse(spa_index)
    raise HTTPException(
        status_code=404,
        detail="前端尚未构建，请先在 frontend 目录执行 npm run build",
    )


# 挂载静态文件（Vue 构建产物）
if os.path.isdir(DIST_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(DIST_DIR, "assets")),
        name="assets",
    )


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
    raise HTTPException(status_code=404, detail="页面不存在")


# ------------------------------------------------------------------
# 启动入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("RefineLoop Code Agent")
    print("=" * 50)
    print("服务地址: http://127.0.0.1:8000")
    print("API 文档: http://127.0.0.1:8000/docs")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=8000)
