from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage

from app.repositories.ai_usage_repo import AsyncAIUsageRepository
from app.schemas.ai_usage import (
    AIUsageFeature,
    AIUsageLogCreate,
    AIUsageProvider,
    AIUsageStatus,
    AIUsageSummaryCreate,
)
from app.services.ai_usage_token_service import AIUsageTokenService


class AIUsageService:
    """Record AI usage logs and update daily/monthly summaries.

    This service records usage after an AI call succeeds, fails, or is blocked.
    It does not decide whether a call is allowed. Quota checking belongs to
    the next AIQuotaService step.
    """

    DEFAULT_PROVIDER: AIUsageProvider = "deepseek"
    DEFAULT_CURRENCY = "CNY"
    DEFAULT_TIMEZONE = "Asia/Shanghai"

    def __init__(
        self,
        repo: AsyncAIUsageRepository,
        token_service: AIUsageTokenService | None = None,
    ) -> None:
        self.repo = repo
        self.token_service = token_service or AIUsageTokenService()

    async def record_success(
        self,
        *,
        user_id: int,
        feature: AIUsageFeature,
        model_name: str,
        response: Any | None,
        prompt_messages: list[BaseMessage] | list[dict[str, Any]] | list[Any] | None = None,
        completion_text: str | None = None,
        provider: AIUsageProvider = DEFAULT_PROVIDER,
        request_id: str | None = None,
        analysis_thread_id: str | None = None,
        trace_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        extra: dict[str, Any] | None = None,
    ):
        finished_at = finished_at or datetime.now(UTC)
        started_at = started_at or finished_at

        token_usage = self.token_service.build_token_usage(
            response=response,
            prompt_messages=prompt_messages,
            completion_text=completion_text,
        )
        cost = self.token_service.estimate_cost(
            model_name=model_name,
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens,
            currency=self.DEFAULT_CURRENCY,
        )

        payload = AIUsageLogCreate(
            user_id=user_id,
            feature=feature,
            provider=provider,
            model_name=model_name,
            status="success",
            token_source=token_usage.token_source,
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens,
            total_tokens=token_usage.total_tokens,
            estimated_cost=cost.estimated_cost,
            currency=cost.currency,
            request_id=request_id,
            analysis_thread_id=analysis_thread_id,
            trace_id=trace_id,
            extra=extra or {},
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=self._calculate_duration_ms(started_at, finished_at),
        )

        return await self.record_usage(payload)

    async def record_failed(
        self,
        *,
        user_id: int,
        feature: AIUsageFeature,
        model_name: str,
        error_message: str,
        response: Any | None = None,
        prompt_messages: list[BaseMessage] | list[dict[str, Any]] | list[Any] | None = None,
        completion_text: str | None = None,
        provider: AIUsageProvider = DEFAULT_PROVIDER,
        request_id: str | None = None,
        analysis_thread_id: str | None = None,
        trace_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        extra: dict[str, Any] | None = None,
    ):
        finished_at = finished_at or datetime.now(UTC)
        started_at = started_at or finished_at

        token_usage = self.token_service.build_token_usage(
            response=response,
            prompt_messages=prompt_messages,
            completion_text=completion_text,
        )
        cost = self.token_service.estimate_cost(
            model_name=model_name,
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens,
            currency=self.DEFAULT_CURRENCY,
        )

        payload = AIUsageLogCreate(
            user_id=user_id,
            feature=feature,
            provider=provider,
            model_name=model_name,
            status="failed",
            token_source=token_usage.token_source,
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens,
            total_tokens=token_usage.total_tokens,
            estimated_cost=cost.estimated_cost,
            currency=cost.currency,
            request_id=request_id,
            analysis_thread_id=analysis_thread_id,
            trace_id=trace_id,
            error_message=self._safe_error_message(error_message),
            extra=extra or {},
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=self._calculate_duration_ms(started_at, finished_at),
        )

        return await self.record_usage(payload)

    async def record_blocked(
        self,
        *,
        user_id: int,
        feature: AIUsageFeature,
        model_name: str,
        reason: str,
        estimated_prompt_tokens: int = 0,
        estimated_completion_tokens: int = 0,
        estimated_cost: Decimal = Decimal("0"),
        provider: AIUsageProvider = DEFAULT_PROVIDER,
        request_id: str | None = None,
        analysis_thread_id: str | None = None,
        trace_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        extra: dict[str, Any] | None = None,
    ):
        finished_at = finished_at or datetime.now(UTC)
        started_at = started_at or finished_at
        total_tokens = max(0, int(estimated_prompt_tokens)) + max(0, int(estimated_completion_tokens))

        payload = AIUsageLogCreate(
            user_id=user_id,
            feature=feature,
            provider=provider,
            model_name=model_name,
            status="blocked",
            token_source="estimated" if total_tokens > 0 else "none",
            prompt_tokens=max(0, int(estimated_prompt_tokens)),
            completion_tokens=max(0, int(estimated_completion_tokens)),
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            currency=self.DEFAULT_CURRENCY,
            request_id=request_id,
            analysis_thread_id=analysis_thread_id,
            trace_id=trace_id,
            error_message=self._safe_error_message(reason),
            extra=extra or {},
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=self._calculate_duration_ms(started_at, finished_at),
        )

        return await self.record_usage(payload)

    async def record_usage(self, payload: AIUsageLogCreate):
        usage_log = await self.repo.create_usage_log(payload)
        account = await self.repo.get_or_create_quota_account(user_id=payload.user_id)
        timezone_name = account.timezone or self.DEFAULT_TIMEZONE

        await self._increment_period_summary(
            payload=payload,
            period_type="day",
            timezone_name=timezone_name,
        )
        await self._increment_period_summary(
            payload=payload,
            period_type="month",
            timezone_name=timezone_name,
        )

        return usage_log

    async def _increment_period_summary(
        self,
        *,
        payload: AIUsageLogCreate,
        period_type: str,
        timezone_name: str,
    ) -> None:
        period_start, period_end = self._build_period_range(
            timestamp=payload.started_at,
            period_type=period_type,
            timezone_name=timezone_name,
        )

        summary = await self.repo.get_or_create_usage_summary(
            AIUsageSummaryCreate(
                user_id=payload.user_id,
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                currency=payload.currency,
            )
        )

        await self.repo.increment_usage_summary(
            summary=summary,
            status=payload.status,
            prompt_tokens=payload.prompt_tokens,
            completion_tokens=payload.completion_tokens,
            total_tokens=payload.total_tokens,
            estimated_cost=payload.estimated_cost,
        )

    def _build_period_range(
        self,
        *,
        timestamp: datetime,
        period_type: str,
        timezone_name: str,
    ) -> tuple[date, date]:
        local_datetime = self._to_local_datetime(timestamp, timezone_name)

        if period_type == "day":
            day = local_datetime.date()
            return day, day

        if period_type == "month":
            month_start = date(local_datetime.year, local_datetime.month, 1)
            if local_datetime.month == 12:
                next_month_start = date(local_datetime.year + 1, 1, 1)
            else:
                next_month_start = date(local_datetime.year, local_datetime.month + 1, 1)
            month_end = next_month_start - timedelta(days=1)
            return month_start, month_end

        raise ValueError(f"unsupported usage summary period_type: {period_type}")

    def _to_local_datetime(
        self,
        timestamp: datetime,
        timezone_name: str,
    ) -> datetime:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return timestamp.astimezone(ZoneInfo(timezone_name))

    def _calculate_duration_ms(
        self,
        started_at: datetime,
        finished_at: datetime,
    ) -> int:
        duration = finished_at - started_at
        return max(0, int(duration.total_seconds() * 1000))

    def _safe_error_message(self, message: str | None) -> str | None:
        if message is None:
            return None

        normalized = str(message).strip()
        if not normalized:
            return None

        return normalized[:1000]