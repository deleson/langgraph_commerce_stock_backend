from __future__ import annotations

"""量化提醒 API 编排服务。

本文件负责规则管理、事件查询和手动扫描入口。
Router 层不直接访问 Repository，也不直接执行扫描细节；
所有用户隔离和业务编排都收口在这里。
"""

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
    """量化提醒 API 业务编排服务。

    这个 Service 管理提醒规则、读取提醒事件，并把手动扫描委托给 QuantAlertScanService。
    它不直接读取行情，也不直接判断规则触发。
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
        """执行当前用户的手动提醒扫描。

        target_user_id 会被强制替换为当前用户 id，
        防止调用方通过请求体扫描其他用户的规则或自选股。
        """

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
