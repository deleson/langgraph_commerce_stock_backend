"""FastAPI 中间件注册。

当前中间件主要负责记录 HTTP 请求耗时，是生产第一版最基础的可观测能力。
后续如需限流、请求 ID、链路追踪，也适合在这里继续扩展。
"""

import time
from collections.abc import Awaitable,Callable

from fastapi import FastAPI,Request,Response

from app.core.logging import get_logger


def register_middlewares(app:FastAPI) -> None:
    """注册全局 HTTP 中间件。"""

    @app.middleware("http")
    async def log_requests(
            request:Request,
            call_next:Callable[[Request],Awaitable[Response]],
    ) -> Response:
        """记录每次 HTTP 请求的路径、状态码和耗时。

        如果请求处理过程中抛出异常，这里会记录 500 日志后继续抛出，
        再交给统一异常处理器转换为 API 响应。
        """

        logger = get_logger("app.request")
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "HTTP %s %s -> 500 (%.2f ms)",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "HTTP %s %s -> %s (%.2f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms
        )
        return response
