from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.models.paper_trading_account import PaperTradingAccount
from app.models.user import User
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.paper_trading import (
    PaperTradingAccountCreate,
    PaperTradingAccountDetailResponse,
    PaperTradingAccountListResponse,
    PaperTradingAccountResponse,
    PaperTradingAccountStatus,
    PaperTradingAccountUpdate,
    PaperTradingEquitySnapshotListResponse,
    PaperTradingEquitySnapshotResponse,
    PaperTradingListQuery,
    PaperTradingOrderListResponse,
    PaperTradingOrderResponse,
    PaperTradingPositionListResponse,
    PaperTradingPositionResponse,
    PaperTradingTickInputSnapshot,
    PaperTradingTickItem,
    PaperTradingTickRequest,
    PaperTradingTickResponse,
    PaperTradingTickStatus,
    PaperTradingTradeListResponse,
    PaperTradingTradeResponse,
    PaperTradingUnavailableReason,
)
from app.services.paper_trading_account_service import PaperTradingAccountService
from app.services.paper_trading_equity_service import PaperTradingEquityService
from app.services.paper_trading_order_service import (
    PaperTradingOrderExecutionResult,
    PaperTradingOrderService,
)
from app.services.paper_trading_position_service import PaperTradingPositionService
from app.services.paper_trading_signal_service import PaperTradingSignalContext, PaperTradingSignalService


class PaperTradingQueryService:
    """Unified paper trading business entry for API handlers.

    This service coordinates account queries and paper trading ticks.
    It keeps API routers thin and does not expose repository details to routers.
    """

    DETAIL_POSITION_LIMIT = 100
    WARNING_LIMIT = 20

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
        account_service: PaperTradingAccountService | None = None,
        signal_service: PaperTradingSignalService | None = None,
        order_service: PaperTradingOrderService | None = None,
        position_service: PaperTradingPositionService | None = None,
        equity_service: PaperTradingEquityService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncPaperTradingRepository(db)
        self.account_service = account_service or PaperTradingAccountService(
            db,
            repository=self.repository,
        )
        self.signal_service = signal_service or PaperTradingSignalService(db)
        self.order_service = order_service or PaperTradingOrderService(
            db,
            repository=self.repository,
        )
        self.position_service = position_service or PaperTradingPositionService(
            db,
            repository=self.repository,
        )
        self.equity_service = equity_service or PaperTradingEquityService(
            db,
            repository=self.repository,
        )

    async def create_account(
        self,
        *,
        user_id: int,
        request: PaperTradingAccountCreate,
    ) -> PaperTradingAccountResponse:
        return await self.account_service.create_account(
            user_id=user_id,
            request=request,
        )

    async def list_accounts(
        self,
        *,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingAccountListResponse:
        return await self.account_service.list_accounts(
            user_id=user_id,
            query=query,
        )

    async def get_account(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> PaperTradingAccountResponse:
        return await self.account_service.get_account(
            user_id=user_id,
            account_id=account_id,
        )

    async def update_account(
        self,
        *,
        user_id: int,
        account_id: int,
        request: PaperTradingAccountUpdate,
    ) -> PaperTradingAccountResponse:
        return await self.account_service.update_account(
            user_id=user_id,
            account_id=account_id,
            request=request,
        )

    async def get_account_detail(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> PaperTradingAccountDetailResponse:
        account = await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        positions = await self.repository.list_positions(
            account_id=account.id,
            user_id=user_id,
            query=PaperTradingListQuery(
                limit=self.DETAIL_POSITION_LIMIT,
                offset=0,
            ),
        )
        latest_equity = await self.equity_service.get_latest_snapshot(
            account_id=account.id,
            user_id=user_id,
        )

        return PaperTradingAccountDetailResponse(
            account=self._build_account_response(account),
            positions=[self._build_position_response(item) for item in positions],
            latest_equity=latest_equity,
        )

    async def list_positions(
        self,
        *,
        user_id: int,
        account_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingPositionListResponse:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        total = await self.repository.count_positions(
            account_id=account_id,
            user_id=user_id,
        )
        items = await self.repository.list_positions(
            account_id=account_id,
            user_id=user_id,
            query=query,
        )

        return PaperTradingPositionListResponse(
            total=total,
            items=[self._build_position_response(item) for item in items],
        )

    async def list_orders(
        self,
        *,
        user_id: int,
        account_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingOrderListResponse:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        total = await self.repository.count_orders(
            account_id=account_id,
            user_id=user_id,
        )
        items = await self.repository.list_orders(
            account_id=account_id,
            user_id=user_id,
            query=query,
        )

        return PaperTradingOrderListResponse(
            total=total,
            items=[self._build_order_response(item) for item in items],
        )

    async def list_trades(
        self,
        *,
        user_id: int,
        account_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingTradeListResponse:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        total = await self.repository.count_trades(
            account_id=account_id,
            user_id=user_id,
        )
        items = await self.repository.list_trades(
            account_id=account_id,
            user_id=user_id,
            query=query,
        )

        return PaperTradingTradeListResponse(
            total=total,
            items=[self._build_trade_response(item) for item in items],
        )

    async def list_equity_snapshots(
        self,
        *,
        user_id: int,
        account_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingEquitySnapshotListResponse:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        total = await self.repository.count_equity_snapshots(
            account_id=account_id,
            user_id=user_id,
        )
        items = await self.repository.list_equity_snapshots(
            account_id=account_id,
            user_id=user_id,
            query=query,
        )

        return PaperTradingEquitySnapshotListResponse(
            total=total,
            items=[self._build_equity_response(item) for item in items],
        )

    async def run_tick(
        self,
        *,
        user: User,
        request: PaperTradingTickRequest,
    ) -> PaperTradingTickResponse:
        self._validate_tick_user(
            user=user,
            request=request,
        )

        tick_request = request.model_copy(
            update={
                "target_user_id": user.id,
            }
        )

        account = await self._resolve_tick_account(
            user=user,
            request=tick_request,
        )

        if account.status != PaperTradingAccountStatus.ACTIVE:
            return self._build_tick_response(
                status=PaperTradingTickStatus.SKIPPED,
                unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
                account=account,
                request=tick_request,
                warnings=["纸面交易账户不是 active 状态，本次 tick 已跳过。"],
            )

        try:
            signal_context = await self.signal_service.collect_signal_context(
                user=user,
                request=tick_request,
            )

            if signal_context.unavailable_reason is not None:
                return self._build_tick_response(
                    status=PaperTradingTickStatus.SKIPPED,
                    unavailable_reason=signal_context.unavailable_reason,
                    account=account,
                    request=tick_request,
                    signal_context=signal_context,
                    warnings=[
                        *signal_context.warnings,
                        *signal_context.errors,
                    ],
                )

            execution_result = await self.order_service.execute_signal_orders(
                account=account,
                signal_context=signal_context,
            )

            position_result = await self.position_service.apply_execution_result(
                account=account,
                execution_result=execution_result,
            )

            updated_account = await self.account_service.get_account_model(
                user_id=user.id,
                account_id=account.id,
            )

            equity_result = await self.equity_service.create_or_update_snapshot(
                account=updated_account,
                user_id=user.id,
            )

            warnings = self._deduplicate_messages(
                [
                    *signal_context.warnings,
                    *signal_context.errors,
                    *execution_result.warnings,
                    *position_result.warnings,
                    *equity_result.warnings,
                ]
            )

            if not signal_context.actionable_items:
                warnings.append("本次 tick 没有 buy / sell 信号，仅更新权益快照。")

            return self._build_tick_response(
                status=PaperTradingTickStatus.COMPLETED,
                unavailable_reason=None,
                account=updated_account,
                request=tick_request,
                signal_context=signal_context,
                execution_result=execution_result,
                equity_snapshot=self._build_equity_response(equity_result.snapshot),
                warnings=warnings,
            )
        except Exception as exc:
            await self.db.rollback()
            return self._build_tick_response(
                status=PaperTradingTickStatus.FAILED,
                unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
                account=account,
                request=tick_request,
                warnings=[f"纸面交易 tick 执行失败：{self._safe_error_message(exc)}"],
            )

    async def _resolve_tick_account(
        self,
        *,
        user: User,
        request: PaperTradingTickRequest,
    ) -> PaperTradingAccount:
        if request.account_id is not None:
            return await self.account_service.get_account_model(
                user_id=user.id,
                account_id=request.account_id,
            )

        account_response = await self.account_service.get_or_create_default_account(
            user_id=user.id,
        )

        return await self.account_service.get_account_model(
            user_id=user.id,
            account_id=account_response.id,
        )

    def _validate_tick_user(
        self,
        *,
        user: User,
        request: PaperTradingTickRequest,
    ) -> None:
        if request.target_user_id is not None and request.target_user_id != user.id:
            raise BadRequestException(
                message="paper trading tick target_user_id must match current user"
            )

    def _build_tick_response(
        self,
        *,
        status: PaperTradingTickStatus,
        unavailable_reason: PaperTradingUnavailableReason | None,
        account: PaperTradingAccount,
        request: PaperTradingTickRequest,
        signal_context: PaperTradingSignalContext | None = None,
        execution_result: PaperTradingOrderExecutionResult | None = None,
        equity_snapshot: PaperTradingEquitySnapshotResponse | None = None,
        warnings: list[str] | None = None,
    ) -> PaperTradingTickResponse:
        scanned_count = len(signal_context.items) if signal_context is not None else 0
        order_count = execution_result.order_count if execution_result is not None else 0
        trade_count = execution_result.trade_count if execution_result is not None else 0

        return PaperTradingTickResponse(
            status=status,
            unavailable_reason=unavailable_reason,
            account=self._build_account_response(account),
            items=self._build_tick_items(execution_result),
            equity_snapshot=equity_snapshot,
            input_snapshot=PaperTradingTickInputSnapshot(
                account_id=account.id,
                scanned_count=scanned_count,
                order_count=order_count,
                trade_count=trade_count,
                source=request.source,
                data_source="market_overview",
            ),
            warnings=self._limit_warnings(
                self._deduplicate_messages(warnings or [])
            ),
            generated_at=datetime.now(UTC),
        )

    def _build_tick_items(
        self,
        execution_result: PaperTradingOrderExecutionResult | None,
    ) -> list[PaperTradingTickItem]:
        if execution_result is None:
            return []

        items: list[PaperTradingTickItem] = []
        for item in execution_result.items:
            items.append(
                PaperTradingTickItem(
                    symbol=item.symbol,
                    market=item.market,
                    action=str(item.action),
                    order_id=item.order.id if item.order is not None else None,
                    trade_id=item.trade.id if item.trade is not None else None,
                    message=item.message or "本条纸面交易动作已处理。",
                    warnings=item.warnings[:10],
                )
            )

        return items

    def _build_account_response(
        self,
        account,
    ) -> PaperTradingAccountResponse:
        return PaperTradingAccountResponse.model_validate(account)

    def _build_position_response(
        self,
        position,
    ) -> PaperTradingPositionResponse:
        return PaperTradingPositionResponse.model_validate(position)

    def _build_order_response(
        self,
        order,
    ) -> PaperTradingOrderResponse:
        return PaperTradingOrderResponse.model_validate(order)

    def _build_trade_response(
        self,
        trade,
    ) -> PaperTradingTradeResponse:
        return PaperTradingTradeResponse.model_validate(trade)

    def _build_equity_response(
        self,
        snapshot,
    ) -> PaperTradingEquitySnapshotResponse:
        return PaperTradingEquitySnapshotResponse.model_validate(snapshot)

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

    def _limit_warnings(
        self,
        warnings: list[str],
    ) -> list[str]:
        return warnings[: self.WARNING_LIMIT]

    def _safe_error_message(
        self,
        exc: Exception,
    ) -> str:
        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__

        return message[:300]