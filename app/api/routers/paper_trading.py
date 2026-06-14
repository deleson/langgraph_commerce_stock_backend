"""纸面交易 API Router。

该 Router 定义纸面交易账户、配置、持仓、订单、成交、权益曲线、运行记录
和 tick 推进接口。Router 层只处理当前用户、路径参数、分页参数和响应包装。

注意：纸面交易只做虚拟模拟，不连接券商，也不会真实下单。
"""

from fastapi import APIRouter, Query, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.paper_trading import (
    PaperTradingAccountCreate,
    PaperTradingAccountDetailResponse,
    PaperTradingAccountListResponse,
    PaperTradingAccountResponse,
    PaperTradingAccountUpdate,
    PaperTradingEquitySnapshotListResponse,
    PaperTradingListQuery,
    PaperTradingOrderListResponse,
    PaperTradingPositionListResponse,
    PaperTradingTickRequest,
    PaperTradingTickResponse,
    PaperTradingTickSource,
    PaperTradingTradeListResponse,
    PaperTradingAccountConfigResponse,
    PaperTradingAccountConfigUpdate,
    PaperTradingRunDetailResponse,
    PaperTradingRunListResponse,
)
from app.services.paper_trading_query_service import PaperTradingQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


@router.post(
    "/accounts",
    summary="Create Paper Trading Account",
    description=(
        "Create one virtual paper trading account for the current user. "
        "Paper trading is not real trading and does not place broker orders."
    ),
    response_model=ApiResponse[PaperTradingAccountResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_paper_trading_account(
    payload: PaperTradingAccountCreate,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PaperTradingAccountResponse]:
    """创建当前用户拥有的纸面交易账户。"""

    result = await PaperTradingQueryService(db).create_account(
        user_id=current_user.id,
        request=payload,
    )
    return success_response(data=result)


@router.get(
    "/accounts",
    summary="List Paper Trading Accounts",
    description="List paper trading accounts owned by the current user.",
    response_model=ApiResponse[PaperTradingAccountListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_paper_trading_accounts(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaperTradingAccountListResponse]:
    """查询当前用户的纸面交易账户列表。"""

    query = PaperTradingListQuery(
        limit=limit,
        offset=offset,
    )

    result = await PaperTradingQueryService(db).list_accounts(
        user_id=current_user.id,
        query=query,
    )
    return success_response(data=result)


@router.get(
    "/accounts/{account_id}",
    summary="Get Paper Trading Account Detail",
    description=(
        "Get one paper trading account detail, including current positions "
        "and latest equity snapshot. Users can only access their own accounts."
    ),
    response_model=ApiResponse[PaperTradingAccountDetailResponse],
    status_code=status.HTTP_200_OK,
)
async def get_paper_trading_account_detail(
    account_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PaperTradingAccountDetailResponse]:
    """查询当前用户拥有的一条纸面交易账户详情。"""

    result = await PaperTradingQueryService(db).get_account_detail(
        user_id=current_user.id,
        account_id=account_id,
    )
    return success_response(data=result)


@router.patch(
    "/accounts/{account_id}",
    summary="Update Paper Trading Account",
    description=(
        "Update one paper trading account owned by the current user. "
        "Closed accounts cannot be updated."
    ),
    response_model=ApiResponse[PaperTradingAccountResponse],
    status_code=status.HTTP_200_OK,
)
async def update_paper_trading_account(
    account_id: int,
    payload: PaperTradingAccountUpdate,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PaperTradingAccountResponse]:
    """更新纸面交易账户名称或状态。"""

    result = await PaperTradingQueryService(db).update_account(
        user_id=current_user.id,
        account_id=account_id,
        request=payload,
    )
    return success_response(data=result)

@router.get(
    "/accounts/{account_id}/config",
    summary="Get Paper Trading Account Config",
    description=(
        "Get current paper trading config for one account. "
        "If the account does not have a config yet, a default config is created."
    ),
    response_model=ApiResponse[PaperTradingAccountConfigResponse],
    status_code=status.HTTP_200_OK,
)
async def get_paper_trading_account_config(
    account_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PaperTradingAccountConfigResponse]:
    """查询纸面交易账户配置。"""

    result = await PaperTradingQueryService(db).get_account_config(
        user_id=current_user.id,
        account_id=account_id,
    )
    return success_response(data=result)

@router.patch(
    "/accounts/{account_id}/config",
    summary="Update Paper Trading Account Config",
    description=(
        "Update paper trading account config, including enable flag, "
        "scan limit, buy/sell switches, position ratios, order amount, "
        "fee rate, and data quality rules."
    ),
    response_model=ApiResponse[PaperTradingAccountConfigResponse],
    status_code=status.HTTP_200_OK,
)
async def update_paper_trading_account_config(
    account_id: int,
    payload: PaperTradingAccountConfigUpdate,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PaperTradingAccountConfigResponse]:
    """更新纸面交易账户配置。"""

    result = await PaperTradingQueryService(db).update_account_config(
        user_id=current_user.id,
        account_id=account_id,
        request=payload,
    )
    return success_response(data=result)

@router.get(
    "/accounts/{account_id}/positions",
    summary="List Paper Trading Positions",
    description="List current simulated positions for one paper trading account.",
    response_model=ApiResponse[PaperTradingPositionListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_paper_trading_positions(
    account_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaperTradingPositionListResponse]:
    """查询某个纸面交易账户的当前模拟持仓。"""

    result = await PaperTradingQueryService(db).list_positions(
        user_id=current_user.id,
        account_id=account_id,
        query=PaperTradingListQuery(limit=limit, offset=offset),
    )
    return success_response(data=result)


@router.get(
    "/accounts/{account_id}/orders",
    summary="List Paper Trading Orders",
    description="List simulated orders for one paper trading account.",
    response_model=ApiResponse[PaperTradingOrderListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_paper_trading_orders(
    account_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaperTradingOrderListResponse]:
    """查询某个纸面交易账户的模拟订单列表。"""

    result = await PaperTradingQueryService(db).list_orders(
        user_id=current_user.id,
        account_id=account_id,
        query=PaperTradingListQuery(limit=limit, offset=offset),
    )
    return success_response(data=result)


@router.get(
    "/accounts/{account_id}/trades",
    summary="List Paper Trading Trades",
    description="List simulated trades for one paper trading account.",
    response_model=ApiResponse[PaperTradingTradeListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_paper_trading_trades(
    account_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaperTradingTradeListResponse]:
    """查询某个纸面交易账户的模拟成交列表。"""

    result = await PaperTradingQueryService(db).list_trades(
        user_id=current_user.id,
        account_id=account_id,
        query=PaperTradingListQuery(limit=limit, offset=offset),
    )
    return success_response(data=result)


@router.get(
    "/accounts/{account_id}/equity",
    summary="List Paper Trading Equity Snapshots",
    description="List equity curve snapshots for one paper trading account.",
    response_model=ApiResponse[PaperTradingEquitySnapshotListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_paper_trading_equity_snapshots(
    account_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaperTradingEquitySnapshotListResponse]:
    """查询某个纸面交易账户的权益快照列表。"""

    result = await PaperTradingQueryService(db).list_equity_snapshots(
        user_id=current_user.id,
        account_id=account_id,
        query=PaperTradingListQuery(limit=limit, offset=offset),
    )
    return success_response(data=result)


@router.post(
    "/accounts/{account_id}/tick",
    summary="Run Paper Trading Tick",
    description=(
        "Run one manual paper trading tick for the current user. "
        "The tick reads watchlist stocks, market overview, data quality, "
        "and deterministic strategy signals. It may create simulated orders, "
        "simulated trades, update virtual positions, and create an equity snapshot. "
        "It does not place real broker orders."
    ),
    response_model=ApiResponse[PaperTradingTickResponse],
    status_code=status.HTTP_200_OK,
)
async def run_paper_trading_tick(
    account_id: int,
    payload: PaperTradingTickRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PaperTradingTickResponse]:
    """手动推进一次纸面交易 tick。

    Router 会强制覆盖 account_id、target_user_id 和 source，
    避免调用方伪造用户或来源。具体信号读取、虚拟订单、虚拟成交、
    持仓更新、权益快照和运行记录由 PaperTradingQueryService 编排。
    """

    request = payload.model_copy(
        update={
            "account_id": account_id,
            "target_user_id": current_user.id,
            "source": PaperTradingTickSource.API,
        }
    )

    result = await PaperTradingQueryService(db).run_tick(
        user=current_user,
        request=request,
    )
    return success_response(data=result)


@router.get(
    "/accounts/{account_id}/runs",
    summary="List Paper Trading Runs",
    description=(
        "List paper trading tick run records for one account. "
        "Each run records one paper trading tick lifecycle and summary statistics."
    ),
    response_model=ApiResponse[PaperTradingRunListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_paper_trading_runs(
    account_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaperTradingRunListResponse]:
    """查询某个纸面交易账户的 tick 运行记录列表。"""

    result = await PaperTradingQueryService(db).list_runs(
        user_id=current_user.id,
        account_id=account_id,
        query=PaperTradingListQuery(limit=limit, offset=offset),
    )
    return success_response(data=result)

@router.get(
    "/accounts/{account_id}/runs/{run_id}",
    summary="Get Paper Trading Run Detail",
    description=(
        "Get one paper trading tick run detail, including request snapshot, "
        "account config snapshot, signal snapshot, execution snapshot, "
        "and position snapshot."
    ),
    response_model=ApiResponse[PaperTradingRunDetailResponse],
    status_code=status.HTTP_200_OK,
)
async def get_paper_trading_run_detail(
    account_id: int,
    run_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PaperTradingRunDetailResponse]:
    """查询某次纸面交易 tick 运行详情。"""

    result = await PaperTradingQueryService(db).get_run(
        user_id=current_user.id,
        account_id=account_id,
        run_id=run_id,
    )
    return success_response(data=result)
