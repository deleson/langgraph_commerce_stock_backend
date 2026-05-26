from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.repositories.ai_usage_repo import AsyncAIUsageRepository
from app.schemas.ai_usage import (
    AIQuotaCheckRequest,
    AIQuotaCheckResult,
    AIQuotaRemaining,
    AIQuotaSummaryResponse,
    AIUsageSummaryCreate,
)


class AIQuotaService:
    """Check whether a user can make an AI call.

    This service only checks quota. It does not call the LLM and does not
    record blocked logs. Blocked logs are recorded by AIUsageService.
    """

    def __init__(self, repo: AsyncAIUsageRepository) -> None:
        self.repo = repo

    async def check_quota(
        self,
        request: AIQuotaCheckRequest,
    ) -> AIQuotaCheckResult:
        account = await self.repo.get_or_create_quota_account(
            user_id=request.user_id
        )

        today_start, today_end = self._build_today_range()
        month_start, month_end = self._build_current_month_range()

        today = await self.repo.get_or_create_usage_summary(
            AIUsageSummaryCreate(
                user_id=request.user_id,
                period_type="day",
                period_start=today_start,
                period_end=today_end,
                currency=request.currency,
            )
        )
        current_month = await self.repo.get_or_create_usage_summary(
            AIUsageSummaryCreate(
                user_id=request.user_id,
                period_type="month",
                period_start=month_start,
                period_end=month_end,
                currency=request.currency,
            )
        )

        remaining = self._build_remaining(
            account=account,
            today=today,
            current_month=current_month,
        )

        if not account.is_active:
            return AIQuotaCheckResult(
                allowed=False,
                reason="AI 额度账户已停用，暂时不能调用 AI 分析。",
                account=account,
                today=today,
                current_month=current_month,
                remaining=remaining,
            )

        exceeded_reason = self._get_exceeded_reason(
            request=request,
            account=account,
            today=today,
            current_month=current_month,
        )

        if exceeded_reason is not None:
            return AIQuotaCheckResult(
                allowed=False,
                reason=exceeded_reason,
                account=account,
                today=today,
                current_month=current_month,
                remaining=remaining,
            )

        return AIQuotaCheckResult(
            allowed=True,
            reason=None,
            account=account,
            today=today,
            current_month=current_month,
            remaining=remaining,
        )

    async def get_quota_summary(
        self,
        *,
        user_id: int,
        currency: str = "CNY",
    ) -> AIQuotaSummaryResponse:
        account = await self.repo.get_or_create_quota_account(user_id=user_id)

        today_start, today_end = self._build_today_range()
        month_start, month_end = self._build_current_month_range()

        today = await self.repo.get_or_create_usage_summary(
            AIUsageSummaryCreate(
                user_id=user_id,
                period_type="day",
                period_start=today_start,
                period_end=today_end,
                currency=currency,
            )
        )
        current_month = await self.repo.get_or_create_usage_summary(
            AIUsageSummaryCreate(
                user_id=user_id,
                period_type="month",
                period_start=month_start,
                period_end=month_end,
                currency=currency,
            )
        )

        return AIQuotaSummaryResponse(
            account=account,
            today=today,
            current_month=current_month,
            remaining=self._build_remaining(
                account=account,
                today=today,
                current_month=current_month,
            ),
        )

    def _get_exceeded_reason(
        self,
        *,
        request: AIQuotaCheckRequest,
        account,
        today,
        current_month,
    ) -> str | None:
        if self._would_exceed_limit(
            used=today.call_count,
            incoming=1,
            limit=account.daily_call_limit,
        ):
            return "今日 AI 调用次数额度已用完。"

        if self._would_exceed_limit(
            used=current_month.call_count,
            incoming=1,
            limit=account.monthly_call_limit,
        ):
            return "本月 AI 调用次数额度已用完。"

        if self._would_exceed_limit(
            used=today.total_tokens,
            incoming=request.estimated_total_tokens,
            limit=account.daily_token_limit,
        ):
            return "今日 AI Token 额度不足。"

        if self._would_exceed_limit(
            used=current_month.total_tokens,
            incoming=request.estimated_total_tokens,
            limit=account.monthly_token_limit,
        ):
            return "本月 AI Token 额度不足。"

        if account.daily_cost_limit is not None and self._would_exceed_decimal_limit(
            used=today.estimated_cost,
            incoming=request.estimated_cost,
            limit=account.daily_cost_limit,
        ):
            return "今日 AI 成本额度不足。"

        if account.monthly_cost_limit is not None and self._would_exceed_decimal_limit(
            used=current_month.estimated_cost,
            incoming=request.estimated_cost,
            limit=account.monthly_cost_limit,
        ):
            return "本月 AI 成本额度不足。"

        return None

    def _build_remaining(
        self,
        *,
        account,
        today,
        current_month,
    ) -> AIQuotaRemaining:
        return AIQuotaRemaining(
            daily_calls_remaining=self._remaining_int(
                limit=account.daily_call_limit,
                used=today.call_count,
            ),
            monthly_calls_remaining=self._remaining_int(
                limit=account.monthly_call_limit,
                used=current_month.call_count,
            ),
            daily_tokens_remaining=self._remaining_int(
                limit=account.daily_token_limit,
                used=today.total_tokens,
            ),
            monthly_tokens_remaining=self._remaining_int(
                limit=account.monthly_token_limit,
                used=current_month.total_tokens,
            ),
            daily_cost_remaining=self._remaining_decimal(
                limit=account.daily_cost_limit,
                used=today.estimated_cost,
            ),
            monthly_cost_remaining=self._remaining_decimal(
                limit=account.monthly_cost_limit,
                used=current_month.estimated_cost,
            ),
        )

    def _would_exceed_limit(
        self,
        *,
        used: int,
        incoming: int,
        limit: int,
    ) -> bool:
        if limit <= 0:
            return True

        return max(0, used) + max(0, incoming) > limit

    def _would_exceed_decimal_limit(
        self,
        *,
        used: Decimal,
        incoming: Decimal,
        limit: Decimal,
    ) -> bool:
        if limit <= 0:
            return True

        return max(Decimal("0"), used) + max(Decimal("0"), incoming) > limit

    def _remaining_int(
        self,
        *,
        limit: int,
        used: int,
    ) -> int:
        return max(0, int(limit) - int(used))

    def _remaining_decimal(
        self,
        *,
        limit: Decimal | None,
        used: Decimal,
    ) -> Decimal | None:
        if limit is None:
            return None

        return max(Decimal("0"), limit - used)

    def _build_today_range(self) -> tuple[date, date]:
        today = date.today()
        return today, today

    def _build_current_month_range(self) -> tuple[date, date]:
        today = date.today()
        month_start = date(today.year, today.month, 1)

        if today.month == 12:
            next_month_start = date(today.year + 1, 1, 1)
        else:
            next_month_start = date(today.year, today.month + 1, 1)

        month_end = date.fromordinal(next_month_start.toordinal() - 1)
        return month_start, month_end