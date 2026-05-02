from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import BadRequestException


def build_http_timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        timeout=settings.http_client_timeout_seconds,
        connect=settings.http_client_connect_timeout_seconds,
    )


@asynccontextmanager
async def get_async_http_client() -> AsyncIterator[httpx.AsyncClient]:
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