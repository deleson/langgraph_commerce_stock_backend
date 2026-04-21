import time
from collections.abc import Awaitable,Callable

from fastapi import FastAPI,Request,Response

from app.core.logging import get_logger


def register_middlewares(app:FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(
            request:Request,
            call_next:Callable[[Request],Awaitable[Response]],
    ) -> Response:
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
