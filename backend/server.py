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
import os
import sys

# 添加 backend 目录到路径（src/、config/、routers/ 位于其下）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.settings import setup_logging

from routers import tasks as tasks_router
from routers import workbench as workbench_router

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """捕获主线程事件循环，供后台任务线程通过 call_soon_threadsafe 投递事件"""
    tasks_router.set_main_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="Generator-Critic Web", lifespan=lifespan)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    print("Generator-Critic Web")
    print("=" * 50)
    print("服务地址: http://127.0.0.1:8000")
    print("API 文档: http://127.0.0.1:8000/docs")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=8000)
