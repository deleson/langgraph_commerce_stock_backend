"""异步 HTTP 客户端工具。

该文件集中封装外部 HTTP 请求的超时、错误转换和 JSON 解析。
真实行情源或其他外部服务调用应通过这里设置超时，避免请求无限等待。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import BadRequestException


def build_http_timeout() -> httpx.Timeout:
    """根据配置构建 httpx 超时对象。"""

    settings = get_settings()
    return httpx.Timeout(
        timeout=settings.http_client_timeout_seconds,
        connect=settings.http_client_connect_timeout_seconds,
    )


@asynccontextmanager
async def get_async_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """创建一次性异步 HTTP client。

    使用 async context manager 确保连接资源在请求结束后被正确释放。
    """

    async with httpx.AsyncClient(
        timeout=build_http_timeout(),
        follow_redirects=False,
    ) as client:
        yield client


async def request_json(
    method: str,
    url: str,
    **kwargs: Any,
) -> Any:
    """请求外部服务并解析 JSON 响应。

    外部请求超时、HTTP 非 2xx 和 JSON 解析失败都会转换成 BadRequestException，
    由上层 Service 决定是否 fallback 或直接返回不可用结果。
    """

    async with get_async_http_client() as client:
        try:
            response = await client.request(method=method, url=url, **kwargs)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise BadRequestException(message="external request timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise BadRequestException(
                message=f"external service returned {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise BadRequestException(message="external request failed") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BadRequestException(message="external response is not valid json") from exc
