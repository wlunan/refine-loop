"""
路由层共享工具：SSE 响应构造、长文本截断
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.responses import StreamingResponse


def sse_response(
    event_generator,
    *,
    extra_headers: dict | None = None,
) -> StreamingResponse:
    """
    构造标准 SSE StreamingResponse

    Args:
        event_generator: 异步事件生成器，逐条 yield 事件 dict
        extra_headers: 额外响应头

    Returns:
        StreamingResponse
    """
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，保证实时推送
    }
    if extra_headers:
        headers.update(extra_headers)

    return StreamingResponse(
        event_generator,
        media_type="text/event-stream",
        headers=headers,
    )


def sse_event(event: dict) -> str:
    """把事件 dict 序列化为 SSE data 帧"""
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def truncate(text: Any, limit: int = 2000) -> str:
    """截断长文本（用于工具结果推送，避免撑爆 SSE）"""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [已截断，共 {len(text)} 字符]"
