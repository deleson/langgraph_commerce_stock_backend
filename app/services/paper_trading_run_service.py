from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_run import PaperTradingRun
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.paper_trading import (
    PaperTradingEquitySnapshotResponse,
    PaperTradingListQuery,
    PaperTradingRunCreate,
    PaperTradingRunDetailResponse,
    PaperTradingRunListResponse,
    PaperTradingRunResponse,
    PaperTradingRunStatus,
    PaperTradingRunUpdate,
    PaperTradingTickRequest,
    PaperTradingUnavailableReason,
)
from app.services.paper_trading_account_service import PaperTradingAccountService
from app.services.paper_trading_equity_service import PaperTradingEquitySnapshotResult
from app.services.paper_trading_order_service import PaperTradingOrderExecutionResult
from app.services.paper_trading_position_service import PaperTradingPositionUpdateResult
from app.services.paper_trading_signal_service import PaperTradingSignalContext


class PaperTradingRunService:
    """Manage paper trading tick run records.

    This service records the lifecycle and snapshots of a paper trading tick.
    It does not collect signals, create orders, update positions, or create
    equity snapshots.
    """

    WARNING_LIMIT = 50
    ERROR_LIMIT = 50
    SNAPSHOT_ITEM_LIMIT = 100

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
        account_service: PaperTradingAccountService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncPaperTradingRepository(db)
        self.account_service = account_service or PaperTradingAccountService(
            db,
            repository=self.repository,
        )

    async def start_run(
        self,
        *,
        account: PaperTradingAccount,
        request: PaperTradingTickRequest,
        account_config_snapshot: dict[str, Any],
    ) -> PaperTradingRun:
        if account.id is None:
            raise BadRequestException(message="paper trading account id is required")

        payload = PaperTradingRunCreate(
            account_id=account.id,
            source=request.source,
            request_snapshot=self.build_request_snapshot(request),
            account_config_snapshot=account_config_snapshot,
        )

        return await self.repository.create_run(payload=payload)

    async def mark_completed(
        self,
        *,
        run: PaperTradingRun,
        signal_context: PaperTradingSignalContext | None = None,
        execution_result: PaperTradingOrderExecutionResult | None = None,
        position_result: PaperTradingPositionUpdateResult | None = None,
        equity_result: PaperTradingEquitySnapshotResult | None = None,
        warnings: list[str] | None = None,
    ) -> PaperTradingRun:
        finished_at = self._now()
        payload = PaperTradingRunUpdate(
            status=PaperTradingRunStatus.COMPLETED,
            unavailable_reason=None,
            scanned_count=self._scanned_count(signal_context),
            actionable_count=self._actionable_count(signal_context),
            order_count=self._order_count(execution_result),
            trade_count=self._trade_count(execution_result),
            skipped_count=self._skipped_count(execution_result),
            equity_snapshot_id=self._equity_snapshot_id(equity_result),
            warnings=self._limit_warnings(
                [
                    *(warnings or []),
                    *self._signal_warnings(signal_context),
                    *self._execution_warnings(execution_result),
                    *self._position_warnings(position_result),
                    *self._equity_warnings(equity_result),
                ]
            ),
            errors=self._limit_errors(self._signal_errors(signal_context)),
            signal_snapshot=self.build_signal_snapshot(signal_context),
            execution_snapshot=self.build_execution_snapshot(execution_result),
            position_snapshot=self.build_position_snapshot(position_result),
            duration_ms=self._duration_ms(run.started_at, finished_at),
        )

        return await self.repository.update_run(
            run=run,
            payload=payload,
            finished_at=finished_at,
        )

    async def mark_skipped(
        self,
        *,
        run: PaperTradingRun,
        unavailable_reason: PaperTradingUnavailableReason,
        signal_context: PaperTradingSignalContext | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> PaperTradingRun:
        finished_at = self._now()
        payload = PaperTradingRunUpdate(
            status=PaperTradingRunStatus.SKIPPED,
            unavailable_reason=unavailable_reason,
            scanned_count=self._scanned_count(signal_context),
            actionable_count=self._actionable_count(signal_context),
            order_count=0,
            trade_count=0,
            skipped_count=self._scanned_count(signal_context),
            warnings=self._limit_warnings(
                [
                    *(warnings or []),
                    *self._signal_warnings(signal_context),
                ]
            ),
            errors=self._limit_errors(
                [
                    *(errors or []),
                    *self._signal_errors(signal_context),
                ]
            ),
            signal_snapshot=self.build_signal_snapshot(signal_context),
            execution_snapshot={},
            position_snapshot={},
            duration_ms=self._duration_ms(run.started_at, finished_at),
        )

        return await self.repository.update_run(
            run=run,
            payload=payload,
            finished_at=finished_at,
        )

    async def mark_failed(
        self,
        *,
        run: PaperTradingRun,
        error_message: str,
        signal_context: PaperTradingSignalContext | None = None,
        warnings: list[str] | None = None,
    ) -> PaperTradingRun:
        finished_at = self._now()
        payload = PaperTradingRunUpdate(
            status=PaperTradingRunStatus.FAILED,
            unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
            scanned_count=self._scanned_count(signal_context),
            actionable_count=self._actionable_count(signal_context),
            order_count=0,
            trade_count=0,
            skipped_count=0,
            warnings=self._limit_warnings(
                [
                    *(warnings or []),
                    *self._signal_warnings(signal_context),
                ]
            ),
            errors=self._limit_errors(
                [
                    error_message,
                    *self._signal_errors(signal_context),
                ]
            ),
            signal_snapshot=self.build_signal_snapshot(signal_context),
            execution_snapshot={},
            position_snapshot={},
            duration_ms=self._duration_ms(run.started_at, finished_at),
        )

        return await self.repository.update_run(
            run=run,
            payload=payload,
            finished_at=finished_at,
        )

    async def get_run(
        self,
        *,
        user_id: int,
        account_id: int,
        run_id: int,
    ) -> PaperTradingRunDetailResponse:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        run = await self.repository.get_run(
            run_id=run_id,
            account_id=account_id,
            user_id=user_id,
        )
        if run is None:
            raise NotFoundException(message="paper trading run not found")

        return self._build_run_detail_response(run)

    async def get_latest_run(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> PaperTradingRunResponse | None:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        run = await self.repository.get_latest_run(
            account_id=account_id,
            user_id=user_id,
        )
        if run is None:
            return None

        return self._build_run_response(run)

    async def list_runs(
        self,
        *,
        user_id: int,
        account_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingRunListResponse:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        total = await self.repository.count_runs(
            account_id=account_id,
            user_id=user_id,
        )
        items = await self.repository.list_runs(
            account_id=account_id,
            user_id=user_id,
            query=query,
        )

        return PaperTradingRunListResponse(
            total=total,
            items=[self._build_run_response(item) for item in items],
        )

    def build_request_snapshot(
        self,
        request: PaperTradingTickRequest,
    ) -> dict[str, Any]:
        return request.model_dump(mode="json")

    def build_signal_snapshot(
        self,
        signal_context: PaperTradingSignalContext | None,
    ) -> dict[str, Any]:
        if signal_context is None:
            return {}

        return {
            "user_id": signal_context.user_id,
            "universe_count": len(signal_context.universe_items),
            "scanned_count": len(signal_context.items),
            "actionable_count": len(signal_context.actionable_items),
            "unavailable_reason": signal_context.unavailable_reason,
            "warnings": self._limit_warnings(signal_context.warnings),
            "errors": self._limit_errors(signal_context.errors),
            "items": [
                self._build_signal_item_snapshot(item)
                for item in signal_context.items[: self.SNAPSHOT_ITEM_LIMIT]
            ],
        }

    def build_execution_snapshot(
        self,
        execution_result: PaperTradingOrderExecutionResult | None,
    ) -> dict[str, Any]:
        if execution_result is None:
            return {}

        return {
            "account_id": execution_result.account_id,
            "signal_count": execution_result.signal_count,
            "order_count": execution_result.order_count,
            "trade_count": execution_result.trade_count,
            "warnings": self._limit_warnings(execution_result.warnings),
            "items": [
                {
                    "symbol": item.symbol,
                    "market": item.market,
                    "action": item.action,
                    "order_id": item.order.id if item.order is not None else None,
                    "trade_id": item.trade.id if item.trade is not None else None,
                    "status": item.status,
                    "message": item.message,
                    "warnings": item.warnings,
                }
                for item in execution_result.items[: self.SNAPSHOT_ITEM_LIMIT]
            ],
        }

    def build_position_snapshot(
        self,
        position_result: PaperTradingPositionUpdateResult | None,
    ) -> dict[str, Any]:
        if position_result is None:
            return {}

        return {
            "account_id": position_result.account_id,
            "cash_before": self._to_json_value(position_result.cash_before),
            "cash_after": self._to_json_value(position_result.cash_after),
            "updated_position_count": position_result.updated_position_count,
            "warnings": self._limit_warnings(position_result.warnings),
            "items": [
                {
                    "symbol": item.symbol,
                    "market": item.market,
                    "side": item.side,
                    "trade_id": item.trade_id,
                    "position_id": (
                        item.position.id if item.position is not None else None
                    ),
                    "cash_before": self._to_json_value(item.cash_before),
                    "cash_after": self._to_json_value(item.cash_after),
                    "message": item.message,
                    "warnings": item.warnings,
                }
                for item in position_result.items[: self.SNAPSHOT_ITEM_LIMIT]
            ],
        }

    def _build_signal_item_snapshot(
        self,
        item,
    ) -> dict[str, Any]:
        quote = item.quote
        data_quality = item.data_quality
        strategy_signal = item.strategy_signal

        return {
            "symbol": item.symbol,
            "market": item.market,
            "name": item.name,
            "can_generate_order": item.can_generate_order,
            "action": item.action,
            "reason": item.reason,
            "latest_price": self._to_json_value(
                getattr(quote, "latest_price", None)
            ),
            "data_quality_status": getattr(data_quality, "status", None),
            "strategy_action": getattr(strategy_signal, "action", None),
            "strategy_confidence": self._to_json_value(
                getattr(strategy_signal, "confidence", None)
            ),
            "warnings": item.warnings,
            "errors": item.errors,
        }

    def _build_run_response(
        self,
        run: PaperTradingRun,
    ) -> PaperTradingRunResponse:
        return PaperTradingRunResponse.model_validate(run)

    def _build_run_detail_response(
        self,
        run: PaperTradingRun,
        *,
        equity_snapshot: PaperTradingEquitySnapshotResponse | None = None,
    ) -> PaperTradingRunDetailResponse:
        response = PaperTradingRunDetailResponse.model_validate(run)
        return response.model_copy(
            update={
                "equity_snapshot": equity_snapshot,
            }
        )

    def _scanned_count(
        self,
        signal_context: PaperTradingSignalContext | None,
    ) -> int:
        return len(signal_context.items) if signal_context is not None else 0

    def _actionable_count(
        self,
        signal_context: PaperTradingSignalContext | None,
    ) -> int:
        if signal_context is None:
            return 0
        return len(signal_context.actionable_items)

    def _order_count(
        self,
        execution_result: PaperTradingOrderExecutionResult | None,
    ) -> int:
        return execution_result.order_count if execution_result is not None else 0

    def _trade_count(
        self,
        execution_result: PaperTradingOrderExecutionResult | None,
    ) -> int:
        return execution_result.trade_count if execution_result is not None else 0

    def _skipped_count(
        self,
        execution_result: PaperTradingOrderExecutionResult | None,
    ) -> int:
        if execution_result is None:
            return 0
        return sum(1 for item in execution_result.items if item.trade is None)

    def _equity_snapshot_id(
        self,
        equity_result: PaperTradingEquitySnapshotResult | None,
    ) -> int | None:
        if equity_result is None:
            return None
        return equity_result.snapshot.id

    def _signal_warnings(
        self,
        signal_context: PaperTradingSignalContext | None,
    ) -> list[str]:
        return signal_context.warnings if signal_context is not None else []

    def _signal_errors(
        self,
        signal_context: PaperTradingSignalContext | None,
    ) -> list[str]:
        return signal_context.errors if signal_context is not None else []

    def _execution_warnings(
        self,
        execution_result: PaperTradingOrderExecutionResult | None,
    ) -> list[str]:
        return execution_result.warnings if execution_result is not None else []

    def _position_warnings(
        self,
        position_result: PaperTradingPositionUpdateResult | None,
    ) -> list[str]:
        return position_result.warnings if position_result is not None else []

    def _equity_warnings(
        self,
        equity_result: PaperTradingEquitySnapshotResult | None,
    ) -> list[str]:
        return equity_result.warnings if equity_result is not None else []

    def _limit_warnings(
        self,
        warnings: list[str],
    ) -> list[str]:
        return self._deduplicate_messages(warnings)[: self.WARNING_LIMIT]

    def _limit_errors(
        self,
        errors: list[str],
    ) -> list[str]:
        return self._deduplicate_messages(errors)[: self.ERROR_LIMIT]

    def _deduplicate_messages(
        self,
        messages: list[str],
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for message in messages:
            normalized = str(message).strip()
            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            result.append(normalized)

        return result

    def _duration_ms(
        self,
        started_at: datetime,
        finished_at: datetime,
    ) -> int:
        normalized_started_at = started_at
        if normalized_started_at.tzinfo is None:
            normalized_started_at = normalized_started_at.replace(tzinfo=UTC)

        return max(
            int((finished_at - normalized_started_at).total_seconds() * 1000),
            0,
        )

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _to_json_value(
        self,
        value,
    ):
        if value is None:
            return None

        if isinstance(value, Decimal):
            return str(value)

        return value