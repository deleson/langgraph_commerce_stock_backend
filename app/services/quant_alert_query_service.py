from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.user import User
from app.repositories.quant_alert_repo import AsyncQuantAlertRepository
from app.schemas.quant_alert import (
    QuantAlertEventListQuery,
    QuantAlertEventListResponse,
    QuantAlertEventResponse,
    QuantAlertEventUpdate,
    QuantAlertRuleCreate,
    QuantAlertRuleListQuery,
    QuantAlertRuleListResponse,
    QuantAlertRuleResponse,
    QuantAlertRuleUpdate,
    QuantAlertScanRequest,
    QuantAlertScanResponse,
)
from app.services.quant_alert_scan_service import QuantAlertScanService


class QuantAlertQueryService:
    """Quant alert API orchestration service.

    This service is the unified entry for Quant Alert API handlers. It manages
    alert rules, reads alert events, and delegates manual scans to
    QuantAlertScanService.

    It does not directly read market data and does not create notifications yet.
    Notification creation is handled in a later step.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncQuantAlertRepository | None = None,
        scan_service: QuantAlertScanService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncQuantAlertRepository(db)
        self.scan_service = scan_service or QuantAlertScanService(
            db,
            repository=self.repository,
        )

    async def create_rule(
        self,
        *,
        user_id: int,
        request: QuantAlertRuleCreate,
    ) -> QuantAlertRuleResponse:
        try:
            rule = await self.repository.create_rule(
                user_id=user_id,
                payload=request,
            )
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(
                "quant alert rule already exists for this user, rule type, market and symbol"
            ) from exc

        return self._build_rule_response(rule)

    async def list_rules(
        self,
        *,
        user_id: int,
        query: QuantAlertRuleListQuery,
    ) -> QuantAlertRuleListResponse:
        total = await self.repository.count_rules(
            user_id=user_id,
            query=query,
        )
        items = await self.repository.list_rules(
            user_id=user_id,
            query=query,
        )

        return QuantAlertRuleListResponse(
            total=total,
            items=[self._build_rule_response(item) for item in items],
        )

    async def get_rule(
        self,
        *,
        user_id: int,
        rule_id: int,
    ) -> QuantAlertRuleResponse:
        rule = await self.repository.get_rule(
            user_id=user_id,
            rule_id=rule_id,
        )
        if rule is None:
            raise NotFoundException("quant alert rule not found")

        return self._build_rule_response(rule)

    async def update_rule(
        self,
        *,
        user_id: int,
        rule_id: int,
        request: QuantAlertRuleUpdate,
    ) -> QuantAlertRuleResponse:
        rule = await self.repository.get_rule(
            user_id=user_id,
            rule_id=rule_id,
        )
        if rule is None:
            raise NotFoundException("quant alert rule not found")

        try:
            updated_rule = await self.repository.update_rule(
                rule,
                request,
            )
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(
                "quant alert rule update conflicts with an existing rule"
            ) from exc

        return self._build_rule_response(updated_rule)

    async def deactivate_rule(
        self,
        *,
        user_id: int,
        rule_id: int,
    ) -> QuantAlertRuleResponse:
        rule = await self.repository.get_rule(
            user_id=user_id,
            rule_id=rule_id,
        )
        if rule is None:
            raise NotFoundException("quant alert rule not found")

        deactivated_rule = await self.repository.deactivate_rule(rule)
        return self._build_rule_response(deactivated_rule)

    async def list_events(
        self,
        *,
        user_id: int,
        query: QuantAlertEventListQuery,
    ) -> QuantAlertEventListResponse:
        total = await self.repository.count_events(
            user_id=user_id,
            query=query,
        )
        items = await self.repository.list_events(
            user_id=user_id,
            query=query,
        )

        return QuantAlertEventListResponse(
            total=total,
            items=[self._build_event_response(item) for item in items],
        )

    async def get_event(
        self,
        *,
        user_id: int,
        event_id: int,
    ) -> QuantAlertEventResponse:
        event = await self.repository.get_event(
            user_id=user_id,
            event_id=event_id,
        )
        if event is None:
            raise NotFoundException("quant alert event not found")

        return self._build_event_response(event)

    async def update_event(
        self,
        *,
        user_id: int,
        event_id: int,
        request: QuantAlertEventUpdate,
    ) -> QuantAlertEventResponse:
        event = await self.repository.get_event(
            user_id=user_id,
            event_id=event_id,
        )
        if event is None:
            raise NotFoundException("quant alert event not found")

        updated_event = await self.repository.update_event(
            event,
            request,
        )
        return self._build_event_response(updated_event)

    async def scan_alerts(
        self,
        *,
        user: User,
        request: QuantAlertScanRequest,
    ) -> QuantAlertScanResponse:
        scan_request = request.model_copy(
            update={
                "target_user_id": user.id,
            }
        )

        return await self.scan_service.scan_alerts(
            user=user,
            request=scan_request,
        )

    def _build_rule_response(
        self,
        rule,
    ) -> QuantAlertRuleResponse:
        return QuantAlertRuleResponse.model_validate(rule)

    def _build_event_response(
        self,
        event,
    ) -> QuantAlertEventResponse:
        return QuantAlertEventResponse.model_validate(event)