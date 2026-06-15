from __future__ import annotations

"""量化提醒扫描编排服务。

一次扫描的完整链路是：
1. 读取当前用户 active 规则；
2. 收集自选股行情、质量、指标和策略信号；
3. 用 QuantAlertTriggerService 做确定性触发判断；
4. 去重后写入 QuantAlertEvent；
5. 可选创建 Notification；
6. 返回本次扫描摘要。

本服务不接券商、不下单，只做提醒事件记录。
"""

from collections import defaultdict
from dataclasses import dataclass
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
from app.schemas.notification import NotificationCreateRequest
from app.services.market_service import MarketService
from app.services.quant_alert_data_service import QuantAlertDataContext, QuantAlertDataService
from app.services.notification_service import AsyncNotificationService
from app.services.quant_alert_trigger_service import (
    QuantAlertTriggeredCandidate,
    QuantAlertTriggerEvaluationResult,
    QuantAlertTriggerService,
)
from app.services.watchlist_service import AsyncWatchlistService


@dataclass(slots=True)
class QuantAlertCreatedEvent:
    """已成功创建或更新通知后的提醒事件包装。"""

    event: QuantAlertEvent
    candidate: QuantAlertTriggeredCandidate

class QuantAlertScanService:
    """编排一次量化提醒扫描。

    这个 Service 连接规则、行情、触发判定、事件落库和通知创建。
    它仍然是确定性逻辑，不调用 LLM，也不生成投资建议。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncQuantAlertRepository | None = None,
        data_service: QuantAlertDataService | None = None,
        trigger_service: QuantAlertTriggerService | None = None,
        notification_service: AsyncNotificationService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncQuantAlertRepository(db)
        self.data_service = data_service or QuantAlertDataService(
            watchlist_service=AsyncWatchlistService(db),
            market_service=MarketService(db),
        )
        self.trigger_service = trigger_service or QuantAlertTriggerService()
        self.notification_service = notification_service or AsyncNotificationService(db)

    async def scan_alerts(
        self,
        *,
        user: User,
        request: QuantAlertScanRequest,
    ) -> QuantAlertScanResponse:
        """执行一次提醒扫描。

        无 active 规则、无可用股票池或行情不可用时，会返回 skipped / unavailable，
        而不是制造空提醒。真正触发的事件会先做 dedup_key 去重，避免同一天重复提醒。
        """

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

        created_event_items = await self._create_new_events(
            user_id=user.id,
            candidates=evaluation_result.triggered_candidates,
            warnings=warnings,
        )

        created_event_items = await self._create_notifications_for_events(
            user=user,
            request=request,
            created_event_items=created_event_items,
            warnings=warnings,
        )

        items = self._build_scan_items(
            data_context=data_context,
            evaluation_result=evaluation_result,
            created_event_items=created_event_items,
        )

        triggered_count = len(created_event_items)
        notification_count = self._count_created_notifications(created_event_items)
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
            notification_count=notification_count,
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
    ) -> list[QuantAlertCreatedEvent]:
        """将触发候选写入提醒事件表。

        dedup_key 用于避免同一用户、同一股票、同一规则在同一周期重复创建事件。
        数据库唯一约束命中时也按重复事件处理，保证并发下仍然安全。
        """

        created_events: list[QuantAlertCreatedEvent] = []

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

            created_events.append(
                QuantAlertCreatedEvent(
                    event=event,
                    candidate=candidate,
                )
            )

        return created_events

    async def _create_notifications_for_events(
            self,
            *,
            user: User,
            request: QuantAlertScanRequest,
            created_event_items: list[QuantAlertCreatedEvent],
            warnings: list[str],
    ) -> list[QuantAlertCreatedEvent]:
        """为提醒事件创建通知。

        通知创建是提醒事件的附加能力。通知失败只写入 warnings，
        不会回滚已经创建的 QuantAlertEvent。
        """

        if not request.notify:
            return created_event_items

        result: list[QuantAlertCreatedEvent] = []

        for item in created_event_items:
            event = item.event
            rule = item.candidate.rule

            if not bool(getattr(rule, "enabled_notification", False)):
                result.append(item)
                continue

            if event.notification_id is not None:
                result.append(item)
                continue

            try:
                notification = await self.notification_service.create_notification(
                    user=user,
                    payload=NotificationCreateRequest(
                        title=self._build_notification_title(event),
                        content=self._build_notification_content(event),
                        notification_type="abnormal_alert",
                        related_record_id=None,
                    ),
                )

                updated_event = await self.repository.set_event_notification(
                    event=event,
                    notification_id=notification.id,
                )

                result.append(
                    QuantAlertCreatedEvent(
                        event=updated_event,
                        candidate=item.candidate,
                    )
                )
            except Exception as exc:
                warnings.append(
                    f"{event.market}:{event.symbol} 提醒事件已生成，但通知创建失败："
                    f"{self._safe_exception_message(exc)}"
                )
                result.append(item)

        return result

    def _build_scan_items(
        self,
        *,
        data_context: QuantAlertDataContext,
        evaluation_result: QuantAlertTriggerEvaluationResult,
        created_event_items: list[QuantAlertCreatedEvent],
    ) -> list[QuantAlertScanItem]:
        evaluation_by_symbol = {
            (item.market, item.symbol): item for item in evaluation_result.items
        }

        events_by_symbol: dict[tuple[str, str], list[QuantAlertEvent]] = defaultdict(list)
        for item in created_event_items:
            event = item.event
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

    def _build_notification_title(self, event: QuantAlertEvent) -> str:
        severity_label = {
            "info": "量化提醒",
            "warning": "量化提醒",
            "critical": "重要量化提醒",
        }.get(str(event.severity), "量化提醒")

        return self._truncate(
            f"{severity_label}：{event.market}:{event.symbol} 触发提醒",
            120,
        )

    def _build_notification_content(self, event: QuantAlertEvent) -> str:
        return "\n".join(
            [
                event.message,
                "",
                f"提醒类型：{event.rule_type}",
                f"严重程度：{event.severity}",
                f"触发时间：{event.triggered_at}",
                "",
                "本提醒基于历史行情、技术指标、策略信号和数据质量规则生成，只作为研究线索，不构成投资建议。",
            ]
        )

    def _count_created_notifications(
            self,
            created_event_items: list[QuantAlertCreatedEvent],
    ) -> int:
        return sum(
            1
            for item in created_event_items
            if item.event.notification_id is not None
        )

    def _safe_exception_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__
        return self._truncate(message, 200)

    def _truncate(self, text: str, max_length: int) -> str:
        normalized = str(text).strip()
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 3] + "..."

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
