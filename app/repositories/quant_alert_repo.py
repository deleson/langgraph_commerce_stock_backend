from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quant_alert_event import QuantAlertEvent
from app.models.quant_alert_rule import QuantAlertRule
from app.schemas.quant_alert import (
    QuantAlertEventCreate,
    QuantAlertEventListQuery,
    QuantAlertEventUpdate,
    QuantAlertRuleCreate,
    QuantAlertRuleListQuery,
    QuantAlertRuleStatus,
    QuantAlertRuleUpdate,
)


class AsyncQuantAlertRepository:
    """Database access for quant alert rules and triggered alert events.

    Repository only reads and writes database rows. It does not decide whether
    an alert should trigger, and it does not create notifications.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_rule(
        self,
        *,
        user_id: int,
        payload: QuantAlertRuleCreate,
    ) -> QuantAlertRule:
        rule = QuantAlertRule(
            user_id=user_id,
            name=payload.name,
            rule_type=payload.rule_type,
            status=QuantAlertRuleStatus.ACTIVE,
            market=payload.market,
            symbol=payload.symbol,
            severity=payload.severity,
            trigger_direction=payload.trigger_direction,
            threshold_value=payload.threshold_value,
            cooldown_minutes=payload.cooldown_minutes,
            enabled_notification=payload.enabled_notification,
            description=payload.description,
            rule_config=payload.rule_config,
        )

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def get_rule(
        self,
        *,
        rule_id: int,
        user_id: int,
    ) -> QuantAlertRule | None:
        stmt = select(QuantAlertRule).where(
            QuantAlertRule.id == rule_id,
            QuantAlertRule.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_rules(
        self,
        *,
        user_id: int,
        query: QuantAlertRuleListQuery,
    ) -> list[QuantAlertRule]:
        stmt = self._apply_rule_filters(
            select(QuantAlertRule),
            user_id=user_id,
            query=query,
        )

        stmt = (
            stmt.order_by(QuantAlertRule.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_rules(
        self,
        *,
        user_id: int,
        query: QuantAlertRuleListQuery,
    ) -> int:
        stmt = self._apply_rule_filters(
            select(func.count(QuantAlertRule.id)),
            user_id=user_id,
            query=query,
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def list_active_rules_for_scan(
        self,
        *,
        user_id: int,
        rule_types: list[str] | None = None,
        market: str | None = None,
        symbol: str | None = None,
    ) -> list[QuantAlertRule]:
        stmt = select(QuantAlertRule).where(
            QuantAlertRule.user_id == user_id,
            QuantAlertRule.status == QuantAlertRuleStatus.ACTIVE,
        )

        if rule_types:
            stmt = stmt.where(QuantAlertRule.rule_type.in_(rule_types))

        if market is not None:
            stmt = stmt.where(
                (QuantAlertRule.market.is_(None)) | (QuantAlertRule.market == market)
            )

        if symbol is not None:
            stmt = stmt.where(
                (QuantAlertRule.symbol.is_(None)) | (QuantAlertRule.symbol == symbol)
            )

        stmt = stmt.order_by(QuantAlertRule.created_at.asc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_rule(
        self,
        rule: QuantAlertRule,
        payload: QuantAlertRuleUpdate,
    ) -> QuantAlertRule:
        update_data = payload.model_dump(
            mode="json",
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(rule, field, value)

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def deactivate_rule(
        self,
        rule: QuantAlertRule,
    ) -> QuantAlertRule:
        rule.status = QuantAlertRuleStatus.INACTIVE

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def create_event(
        self,
        payload: QuantAlertEventCreate,
    ) -> QuantAlertEvent:
        event_data = payload.model_dump(mode="json")
        event_data["event_date"] = payload.event_date
        event_data["triggered_at"] = payload.triggered_at

        event = QuantAlertEvent(**event_data)

        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def get_event(
        self,
        *,
        event_id: int,
        user_id: int,
    ) -> QuantAlertEvent | None:
        stmt = select(QuantAlertEvent).where(
            QuantAlertEvent.id == event_id,
            QuantAlertEvent.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_event_by_dedup_key(
        self,
        *,
        user_id: int,
        dedup_key: str,
    ) -> QuantAlertEvent | None:
        stmt = select(QuantAlertEvent).where(
            QuantAlertEvent.user_id == user_id,
            QuantAlertEvent.dedup_key == dedup_key,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_events(
        self,
        *,
        user_id: int,
        query: QuantAlertEventListQuery,
    ) -> list[QuantAlertEvent]:
        stmt = self._apply_event_filters(
            select(QuantAlertEvent),
            user_id=user_id,
            query=query,
        )

        stmt = (
            stmt.order_by(
                QuantAlertEvent.triggered_at.desc(),
                QuantAlertEvent.created_at.desc(),
            )
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_events(
        self,
        *,
        user_id: int,
        query: QuantAlertEventListQuery,
    ) -> int:
        stmt = self._apply_event_filters(
            select(func.count(QuantAlertEvent.id)),
            user_id=user_id,
            query=query,
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def update_event(
        self,
        event: QuantAlertEvent,
        payload: QuantAlertEventUpdate,
    ) -> QuantAlertEvent:
        update_data = payload.model_dump(
            mode="json",
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(event, field, value)

        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def set_event_notification(
        self,
        *,
        event: QuantAlertEvent,
        notification_id: int,
    ) -> QuantAlertEvent:
        event.notification_id = notification_id

        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    def _apply_rule_filters(
        self,
        stmt,
        *,
        user_id: int,
        query: QuantAlertRuleListQuery,
    ):
        stmt = stmt.where(QuantAlertRule.user_id == user_id)

        if not query.include_inactive:
            stmt = stmt.where(QuantAlertRule.status == QuantAlertRuleStatus.ACTIVE)

        if query.rule_type is not None:
            stmt = stmt.where(QuantAlertRule.rule_type == query.rule_type)

        if query.status is not None:
            stmt = stmt.where(QuantAlertRule.status == query.status)

        if query.market is not None:
            stmt = stmt.where(QuantAlertRule.market == query.market)

        if query.symbol is not None:
            stmt = stmt.where(QuantAlertRule.symbol == query.symbol)

        return stmt

    def _apply_event_filters(
        self,
        stmt,
        *,
        user_id: int,
        query: QuantAlertEventListQuery,
    ):
        stmt = stmt.where(QuantAlertEvent.user_id == user_id)

        if query.rule_type is not None:
            stmt = stmt.where(QuantAlertEvent.rule_type == query.rule_type)

        if query.status is not None:
            stmt = stmt.where(QuantAlertEvent.status == query.status)

        if query.severity is not None:
            stmt = stmt.where(QuantAlertEvent.severity == query.severity)

        if query.market is not None:
            stmt = stmt.where(QuantAlertEvent.market == query.market)

        if query.symbol is not None:
            stmt = stmt.where(QuantAlertEvent.symbol == query.symbol)

        if query.start_date is not None:
            stmt = stmt.where(QuantAlertEvent.event_date >= query.start_date)

        if query.end_date is not None:
            stmt = stmt.where(QuantAlertEvent.event_date <= query.end_date)

        return stmt