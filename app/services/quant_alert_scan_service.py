from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quant_alert_event import QuantAlertEvent
from app.models.user import User
from app.repositories.quant_alert_repo import AsyncQuantAlertRepository
from app.schemas.quant_alert import (
    QuantAlertEventResponse,
    QuantAlertScanInputSnapshot,
    QuantAlertScanItem,
    QuantAlertScanRequest,
    QuantAlertScanResponse,
    QuantAlertScanStatus,
    QuantAlertUnavailableReason,
)
from app.services.market_service import MarketService
from app.services.quant_alert_data_service import QuantAlertDataContext, QuantAlertDataService
from app.services.quant_alert_trigger_service import (
    QuantAlertTriggeredCandidate,
    QuantAlertTriggerEvaluationResult,
    QuantAlertTriggerService,
)
from app.services.watchlist_service import AsyncWatchlistService


class QuantAlertScanService:
    """Orchestrates one quant alert scan.

    This service reads rules, collects market data, evaluates deterministic
    alert rules, writes new QuantAlertEvent rows, and returns a scan response.

    It does not create notifications yet. Notification creation is handled in a
    later step so the scan flow can be tested independently first.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncQuantAlertRepository | None = None,
        data_service: QuantAlertDataService | None = None,
        trigger_service: QuantAlertTriggerService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncQuantAlertRepository(db)
        self.data_service = data_service or QuantAlertDataService(
            watchlist_service=AsyncWatchlistService(db),
            market_service=MarketService(db),
        )
        self.trigger_service = trigger_service or QuantAlertTriggerService()

    async def scan_alerts(
        self,
        *,
        user: User,
        request: QuantAlertScanRequest,
    ) -> QuantAlertScanResponse:
        triggered_at = datetime.now(UTC)
        warnings: list[str] = []

        rules = await self._list_active_rules_for_scan(user=user, request=request)

        if not rules:
            return self._build_skipped_response(
                user=user,
                request=request,
                unavailable_reason=QuantAlertUnavailableReason.NO_ACTIVE_RULES,
                summary="本次提醒扫描跳过：当前用户没有可用的 active 量化提醒规则。",
                symbol_count=len(request.symbols or []),
                rule_count=0,
                warnings=["当前用户没有 active 量化提醒规则。"],
            )

        data_context = await self.data_service.collect_data_for_scan(
            user=user,
            request=request,
        )
        warnings.extend(data_context.warnings)
        warnings.extend(data_context.errors)

        if data_context.unavailable_reason is not None:
            return self._build_data_unavailable_response(
                user=user,
                request=request,
                data_context=data_context,
                rule_count=len(rules),
                warnings=warnings,
            )

        evaluation_result = self.trigger_service.evaluate_context(
            user_id=user.id,
            context=data_context,
            rules=rules,
            triggered_at=triggered_at,
        )
        warnings.extend(evaluation_result.warnings)

        created_events = await self._create_new_events(
            user_id=user.id,
            candidates=evaluation_result.triggered_candidates,
            warnings=warnings,
        )

        items = self._build_scan_items(
            data_context=data_context,
            evaluation_result=evaluation_result,
            created_events=created_events,
        )

        triggered_count = len(created_events)
        scanned_count = len(data_context.items)

        return QuantAlertScanResponse(
            status=QuantAlertScanStatus.COMPLETED,
            unavailable_reason=None,
            summary=self._build_completed_summary(
                scanned_count=scanned_count,
                triggered_count=triggered_count,
            ),
            scanned_count=scanned_count,
            triggered_count=triggered_count,
            notification_count=0,
            items=items,
            input_snapshot=self._build_input_snapshot(
                user=user,
                request=request,
                symbol_count=len(data_context.universe_items),
                rule_count=len(rules),
            ),
            warnings=self._deduplicate_messages(warnings),
        )

    async def _list_active_rules_for_scan(
        self,
        *,
        user: User,
        request: QuantAlertScanRequest,
    ):
        rule_types = [item.value for item in request.rule_types] if request.rule_types else None
        symbol = request.symbols[0] if request.symbols and len(request.symbols) == 1 else None

        return await self.repository.list_active_rules_for_scan(
            user_id=user.id,
            rule_types=rule_types,
            market=request.market,
            symbol=symbol,
        )

    async def _create_new_events(
        self,
        *,
        user_id: int,
        candidates: Iterable[QuantAlertTriggeredCandidate],
        warnings: list[str],
    ) -> list[QuantAlertEvent]:
        created_events: list[QuantAlertEvent] = []

        for candidate in candidates:
            payload = candidate.event_payload
            existing_event = await self.repository.get_event_by_dedup_key(
                user_id=user_id,
                dedup_key=payload.dedup_key,
            )

            if existing_event is not None:
                warnings.append(
                    f"{payload.market}:{payload.symbol} 已存在同日同规则提醒，"
                    "本次扫描跳过重复事件。"
                )
                continue

            try:
                event = await self.repository.create_event(payload)
            except IntegrityError:
                await self.db.rollback()
                warnings.append(
                    f"{payload.market}:{payload.symbol} 提醒事件写入时命中唯一约束，"
                    "已按重复事件跳过。"
                )
                continue

            created_events.append(event)

        return created_events

    def _build_scan_items(
        self,
        *,
        data_context: QuantAlertDataContext,
        evaluation_result: QuantAlertTriggerEvaluationResult,
        created_events: list[QuantAlertEvent],
    ) -> list[QuantAlertScanItem]:
        evaluation_by_symbol = {
            (item.market, item.symbol): item for item in evaluation_result.items
        }

        events_by_symbol: dict[tuple[str, str], list[QuantAlertEvent]] = defaultdict(list)
        for event in created_events:
            events_by_symbol[(event.market, event.symbol)].append(event)

        items: list[QuantAlertScanItem] = []

        for data_item in data_context.items:
            key = (data_item.market, data_item.symbol)
            evaluation_item = evaluation_by_symbol.get(key)
            events = events_by_symbol.get(key, [])

            warnings = []
            skipped_reason = None
            if evaluation_item is not None:
                warnings = evaluation_item.warnings
                skipped_reason = evaluation_item.skipped_reason
            else:
                warnings = data_item.warnings + data_item.errors

            items.append(
                QuantAlertScanItem(
                    symbol=data_item.symbol,
                    market=data_item.market,
                    scanned=data_item.overview is not None,
                    triggered_count=len(events),
                    skipped_reason=skipped_reason,
                    warnings=self._deduplicate_messages(warnings),
                    events=[self._build_event_response(event) for event in events],
                )
            )

        return items

    def _build_event_response(self, event: QuantAlertEvent) -> QuantAlertEventResponse:
        return QuantAlertEventResponse.model_validate(event)

    def _build_data_unavailable_response(
        self,
        *,
        user: User,
        request: QuantAlertScanRequest,
        data_context: QuantAlertDataContext,
        rule_count: int,
        warnings: list[str],
    ) -> QuantAlertScanResponse:
        items = [
            QuantAlertScanItem(
                symbol=item.symbol,
                market=item.market,
                scanned=item.overview is not None,
                triggered_count=0,
                skipped_reason="data_unavailable" if item.overview is None else None,
                warnings=self._deduplicate_messages(item.warnings + item.errors),
                events=[],
            )
            for item in data_context.items
        ]

        return QuantAlertScanResponse(
            status=QuantAlertScanStatus.SKIPPED,
            unavailable_reason=data_context.unavailable_reason,
            summary=f"本次提醒扫描跳过：{data_context.unavailable_reason}。",
            scanned_count=len(data_context.items),
            triggered_count=0,
            notification_count=0,
            items=items,
            input_snapshot=self._build_input_snapshot(
                user=user,
                request=request,
                symbol_count=len(data_context.universe_items),
                rule_count=rule_count,
            ),
            warnings=self._deduplicate_messages(warnings),
        )

    def _build_skipped_response(
        self,
        *,
        user: User,
        request: QuantAlertScanRequest,
        unavailable_reason: QuantAlertUnavailableReason,
        summary: str,
        symbol_count: int,
        rule_count: int,
        warnings: list[str],
    ) -> QuantAlertScanResponse:
        return QuantAlertScanResponse(
            status=QuantAlertScanStatus.SKIPPED,
            unavailable_reason=unavailable_reason,
            summary=summary,
            scanned_count=0,
            triggered_count=0,
            notification_count=0,
            items=[],
            input_snapshot=self._build_input_snapshot(
                user=user,
                request=request,
                symbol_count=symbol_count,
                rule_count=rule_count,
            ),
            warnings=self._deduplicate_messages(warnings),
        )

    def _build_input_snapshot(
        self,
        *,
        user: User,
        request: QuantAlertScanRequest,
        symbol_count: int,
        rule_count: int,
    ) -> QuantAlertScanInputSnapshot:
        return QuantAlertScanInputSnapshot(
            source=request.source,
            target_user_id=user.id,
            symbol_count=symbol_count,
            rule_type_count=rule_count,
            notify=request.notify,
            force=request.force,
            max_watchlist_items=request.max_watchlist_items,
        )

    def _build_completed_summary(
        self,
        *,
        scanned_count: int,
        triggered_count: int,
    ) -> str:
        if triggered_count == 0:
            return f"本次量化提醒扫描完成，共扫描 {scanned_count} 只股票，未生成新的提醒事件。"

        return (
            f"本次量化提醒扫描完成，共扫描 {scanned_count} 只股票，"
            f"生成 {triggered_count} 条新的提醒事件。"
        )

    def _deduplicate_messages(self, messages: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for message in messages:
            normalized = str(message).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)

        return result