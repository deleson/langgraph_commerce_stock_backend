from __future__ import annotations

"""纸面交易 API 与 tick 编排服务。

本文件是纸面交易模块的统一业务入口：
账户查询、配置查询、持仓/订单/成交/权益/运行记录查询，以及 run_tick 主链路都在这里编排。

run_tick 只推进虚拟账户，不连接券商、不真实下单、不构成投资建议。
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.models.paper_trading_account import PaperTradingAccount
from app.models.user import User
from app.models.paper_trading_run import PaperTradingRun
from app.services.paper_trading_account_config_service import (
    PaperTradingAccountConfigService,
)
from app.services.paper_trading_run_service import PaperTradingRunService
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
    PaperTradingAccountConfigResponse,
    PaperTradingAccountConfigUpdate,
    PaperTradingRunDetailResponse,
    PaperTradingRunListResponse,
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
    """纸面交易 API 的统一业务入口。

    Router 层只处理 HTTP、认证和分页参数；
    本 Service 负责账户归属校验、配置读取、tick 运行记录和多个子 Service 串联。
    """

    DETAIL_POSITION_LIMIT = 100
    WARNING_LIMIT = 20

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
        account_service: PaperTradingAccountService | None = None,
        account_config_service: PaperTradingAccountConfigService | None = None,
        run_service: PaperTradingRunService | None = None,
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
        self.account_config_service = (
                account_config_service
                or PaperTradingAccountConfigService(
            db,
            repository=self.repository,
            account_service=self.account_service,
        )
        )
        self.run_service = run_service or PaperTradingRunService(
            db,
            repository=self.repository,
            account_service=self.account_service,
        )
        self.signal_service = signal_service or PaperTradingSignalService(
            db,
            repository=self.repository,
        )
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

    async def delete_account(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> None:
        await self.account_service.delete_account(
            user_id=user_id,
            account_id=account_id,
        )

    async def get_account_config(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> PaperTradingAccountConfigResponse:
        return await self.account_config_service.get_config(
            user_id=user_id,
            account_id=account_id,
        )

    async def update_account_config(
        self,
        *,
        user_id: int,
        account_id: int,
        request: PaperTradingAccountConfigUpdate,
    ) -> PaperTradingAccountConfigResponse:
        return await self.account_config_service.update_config(
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

        config_model = await self.account_config_service.get_or_create_config_model(
            account=account,
        )
        latest_run = await self.run_service.get_latest_run(
            user_id=user_id,
            account_id=account.id,
        )

        return PaperTradingAccountDetailResponse(
            account=self._build_account_response(account),
            config=self.account_config_service._build_config_response(config_model),
            positions=[self._build_position_response(item) for item in positions],
            latest_equity=latest_equity,
            latest_run=latest_run,
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

    async def list_runs(
        self,
        *,
        user_id: int,
        account_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingRunListResponse:
        return await self.run_service.list_runs(
            user_id=user_id,
            account_id=account_id,
            query=query,
        )

    async def get_run(
        self,
        *,
        user_id: int,
        account_id: int,
        run_id: int,
    ) -> PaperTradingRunDetailResponse:
        return await self.run_service.get_run(
            user_id=user_id,
            account_id=account_id,
            run_id=run_id,
        )

    async def run_tick(
        self,
        *,
        user: User,
        request: PaperTradingTickRequest,
    ) -> PaperTradingTickResponse:
        """推进一次纸面交易 tick。

        主流程：
        1. 校验 target_user_id 必须等于当前用户；
        2. 解析账户并读取账户配置；
        3. 创建 PaperTradingRun 运行记录；
        4. 收集策略信号；
        5. 创建模拟订单和成交；
        6. 更新现金与持仓；
        7. 创建或更新权益快照；
        8. 把快照和统计写回运行记录。
        """

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

        config = await self.account_config_service.get_or_create_config_model(
            account=account,
        )
        config_snapshot = self.account_config_service.build_config_snapshot(config)

        tick_request = tick_request.model_copy(
            update={
                # 调度任务可能不携带 account_id；解析后写回请求，保证持仓退出扫描绑定正确账户。
                "account_id": account.id,
                "max_symbols": min(
                    tick_request.max_symbols,
                    config.max_symbols_per_tick,
                ),
            }
        )

        run = await self.run_service.start_run(
            account=account,
            request=tick_request,
            account_config_snapshot=config_snapshot,
        )

        if account.status != PaperTradingAccountStatus.ACTIVE:
            warnings = ["纸面交易账户不是 active 状态，本次 tick 已跳过。"]
            await self.run_service.mark_skipped(
                run=run,
                unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
                warnings=warnings,
            )
            return self._build_tick_response(
                status=PaperTradingTickStatus.SKIPPED,
                unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
                account=account,
                request=tick_request,
                run=run,
                warnings=warnings,
            )

        if not config.is_enabled:
            warnings = ["纸面交易账户配置未启用，本次 tick 已跳过。"]
            await self.run_service.mark_skipped(
                run=run,
                unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
                warnings=warnings,
            )
            return self._build_tick_response(
                status=PaperTradingTickStatus.SKIPPED,
                unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
                account=account,
                request=tick_request,
                run=run,
                warnings=warnings,
            )

        signal_context: PaperTradingSignalContext | None = None

        try:
            signal_context = await self.signal_service.collect_signal_context(
                user=user,
                request=tick_request,
            )

            if signal_context.unavailable_reason is not None:
                warnings = [
                    *signal_context.warnings,
                    *signal_context.errors,
                ]
                await self.run_service.mark_skipped(
                    run=run,
                    unavailable_reason=signal_context.unavailable_reason,
                    signal_context=signal_context,
                    warnings=warnings,
                    errors=signal_context.errors,
                )
                return self._build_tick_response(
                    status=PaperTradingTickStatus.SKIPPED,
                    unavailable_reason=signal_context.unavailable_reason,
                    account=account,
                    request=tick_request,
                    run=run,
                    signal_context=signal_context,
                    warnings=warnings,
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
                warnings.append(
                    "本次 tick 未生成模拟成交：当前信号均不满足下单条件，"
                    "每只股票的具体原因见 items。"
                )

            completed_run = await self.run_service.mark_completed(
                run=run,
                signal_context=signal_context,
                execution_result=execution_result,
                position_result=position_result,
                equity_result=equity_result,
                warnings=warnings,
            )

            return self._build_tick_response(
                status=PaperTradingTickStatus.COMPLETED,
                unavailable_reason=None,
                account=updated_account,
                request=tick_request,
                run=completed_run,
                signal_context=signal_context,
                execution_result=execution_result,
                equity_snapshot=self._build_equity_response(equity_result.snapshot),
                warnings=warnings,
            )
        except Exception as exc:
            await self.db.rollback()
            error_message = f"纸面交易 tick 执行失败：{self._safe_error_message(exc)}"

            failed_run = await self.run_service.mark_failed(
                run=run,
                error_message=error_message,
                signal_context=signal_context,
                warnings=[error_message],
            )

            return self._build_tick_response(
                status=PaperTradingTickStatus.FAILED,
                unavailable_reason=PaperTradingUnavailableReason.TICK_FAILED,
                account=account,
                request=tick_request,
                run=failed_run,
                signal_context=signal_context,
                warnings=[error_message],
            )

    async def _resolve_tick_account(
        self,
        *,
        user: User,
        request: PaperTradingTickRequest,
    ) -> PaperTradingAccount:
        """解析本次 tick 使用的纸面交易账户。

        如果请求没有传 account_id，则获取或创建当前用户默认账户。
        账户查询始终带 user_id，避免跨用户推进别人的虚拟账户。
        """

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
        """校验 tick 的目标用户不能被请求体伪造。"""

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
        run: PaperTradingRun | None = None,
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
            run_id=run.id if run is not None else None,
            items=self._build_tick_items(
                signal_context=signal_context,
                execution_result=execution_result,
            ),
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
        *,
        signal_context: PaperTradingSignalContext | None,
        execution_result: PaperTradingOrderExecutionResult | None,
    ) -> list[PaperTradingTickItem]:
        """返回全部扫描项，让“未成交”也有明确、可审计的原因。"""

        execution_by_key = {
            (item.market, item.symbol): item
            for item in (execution_result.items if execution_result else [])
        }
        items: list[PaperTradingTickItem] = []

        for signal_item in signal_context.items if signal_context else []:
            execution_item = execution_by_key.get(
                (signal_item.market, signal_item.symbol)
            )
            if execution_item is not None:
                items.append(
                    PaperTradingTickItem(
                        symbol=execution_item.symbol,
                        market=execution_item.market,
                        action=str(execution_item.action),
                        order_id=(
                            execution_item.order.id
                            if execution_item.order is not None
                            else None
                        ),
                        trade_id=(
                            execution_item.trade.id
                            if execution_item.trade is not None
                            else None
                        ),
                        message=execution_item.message or "本条纸面交易动作已处理。",
                        warnings=execution_item.warnings[:10],
                    )
                )
                continue

            items.append(
                PaperTradingTickItem(
                    symbol=signal_item.symbol,
                    market=signal_item.market,
                    action=signal_item.action or "skip",
                    message=signal_item.reason or "当前信号不满足模拟下单条件。",
                    warnings=[
                        *signal_item.warnings,
                        *signal_item.errors,
                    ][:10],
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
