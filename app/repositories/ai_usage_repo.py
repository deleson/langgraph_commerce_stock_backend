"""AI 用量 Repository。

本文件封装 AI 调用日志、额度账户和周期用量汇总的数据访问。
它支撑成本追踪、额度检查和审计，但不直接调用 LLM。
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_quota_account import AIQuotaAccount
from app.models.ai_usage_log import AIUsageLog
from app.models.ai_usage_summary import AIUsageSummary
from app.schemas.ai_usage import (
    AIQuotaAccountCreate,
    AIQuotaAccountUpdate,
    AIUsageLogCreate,
    AIUsageQuery,
    AIUsageSummaryCreate,
)


class AsyncAIUsageRepository:
    """异步 AI 用量数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_usage_log(
        self,
        payload: AIUsageLogCreate,
    ) -> AIUsageLog:
        usage_log = AIUsageLog(**payload.model_dump())
        self.db.add(usage_log)
        await self.db.commit()
        await self.db.refresh(usage_log)
        return usage_log

    async def list_usage_logs(
        self,
        *,
        user_id: int,
        query: AIUsageQuery,
    ) -> list[AIUsageLog]:
        """按用户和筛选条件查询 AI 调用日志。

        user_id 是审计边界，用户不能查看其他用户的 token 和成本记录。
        """

        stmt = select(AIUsageLog).where(AIUsageLog.user_id == user_id)

        if query.feature is not None:
            stmt = stmt.where(AIUsageLog.feature == query.feature)

        if query.status is not None:
            stmt = stmt.where(AIUsageLog.status == query.status)

        if query.start_date is not None:
            stmt = stmt.where(
                func.date(AIUsageLog.created_at) >= query.start_date
            )

        if query.end_date is not None:
            stmt = stmt.where(
                func.date(AIUsageLog.created_at) <= query.end_date
            )

        stmt = stmt.order_by(AIUsageLog.created_at.desc()).limit(query.limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_usage_logs(
        self,
        *,
        user_id: int,
        query: AIUsageQuery,
    ) -> int:
        stmt = select(func.count(AIUsageLog.id)).where(AIUsageLog.user_id == user_id)

        if query.feature is not None:
            stmt = stmt.where(AIUsageLog.feature == query.feature)

        if query.status is not None:
            stmt = stmt.where(AIUsageLog.status == query.status)

        if query.start_date is not None:
            stmt = stmt.where(
                func.date(AIUsageLog.created_at) >= query.start_date
            )

        if query.end_date is not None:
            stmt = stmt.where(
                func.date(AIUsageLog.created_at) <= query.end_date
            )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def get_quota_account(
        self,
        *,
        user_id: int,
    ) -> AIQuotaAccount | None:
        stmt = select(AIQuotaAccount).where(AIQuotaAccount.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_quota_account(
        self,
        payload: AIQuotaAccountCreate,
    ) -> AIQuotaAccount:
        quota_account = AIQuotaAccount(**payload.model_dump())
        self.db.add(quota_account)
        await self.db.commit()
        await self.db.refresh(quota_account)
        return quota_account

    async def get_or_create_quota_account(
        self,
        *,
        user_id: int,
    ) -> AIQuotaAccount:
        """获取或创建用户额度账户。

        额度账户是后续 stock_analysis、ReAct、日报 AI 等功能的成本控制基础。
        """

        existing = await self.get_quota_account(user_id=user_id)
        if existing is not None:
            return existing

        return await self.create_quota_account(
            AIQuotaAccountCreate(user_id=user_id)
        )

    async def update_quota_account(
        self,
        quota_account: AIQuotaAccount,
        payload: AIQuotaAccountUpdate,
    ) -> AIQuotaAccount:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(quota_account, field, value)

        self.db.add(quota_account)
        await self.db.commit()
        await self.db.refresh(quota_account)
        return quota_account

    async def get_usage_summary(
        self,
        *,
        user_id: int,
        period_type: str,
        period_start: date,
    ) -> AIUsageSummary | None:
        stmt = select(AIUsageSummary).where(
            AIUsageSummary.user_id == user_id,
            AIUsageSummary.period_type == period_type,
            AIUsageSummary.period_start == period_start,
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_usage_summary(
        self,
        payload: AIUsageSummaryCreate,
    ) -> AIUsageSummary:
        summary = AIUsageSummary(**payload.model_dump())
        self.db.add(summary)
        await self.db.commit()
        await self.db.refresh(summary)
        return summary

    async def get_or_create_usage_summary(
        self,
        payload: AIUsageSummaryCreate,
    ) -> AIUsageSummary:
        existing = await self.get_usage_summary(
            user_id=payload.user_id,
            period_type=payload.period_type,
            period_start=payload.period_start,
        )

        if existing is not None:
            return existing

        return await self.create_usage_summary(payload)

    async def increment_usage_summary(
        self,
        *,
        summary: AIUsageSummary,
        status: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost,
    ) -> AIUsageSummary:
        """累加周期用量汇总。

        成功、失败、被阻断都会进入调用次数统计，便于后续评估真实 AI 成本。
        """

        summary.call_count += 1

        if status == "success":
            summary.success_count += 1
        elif status == "failed":
            summary.failed_count += 1
        elif status == "blocked":
            summary.blocked_count += 1

        summary.prompt_tokens += max(0, int(prompt_tokens))
        summary.completion_tokens += max(0, int(completion_tokens))
        summary.total_tokens += max(0, int(total_tokens))
        summary.estimated_cost += estimated_cost or Decimal("0")

        self.db.add(summary)
        await self.db.commit()
        await self.db.refresh(summary)
        return summary
