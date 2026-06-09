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
    """Create one paper trading account owned by the current user."""

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
    """List current user's paper trading accounts."""

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
    """Get one paper trading account detail."""

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
    """Update paper trading account name or status."""

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
    """Get paper trading account config."""

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
    """Update paper trading account config."""

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
    """List current positions for one account."""

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
    """List simulated orders for one account."""

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
    """List simulated trades for one account."""

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
    """List equity snapshots for one account."""

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
    """Run one manual paper trading tick for one account."""

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
    """List paper trading run records for one account."""

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
    """Get one paper trading run detail."""

    result = await PaperTradingQueryService(db).get_run(
        user_id=current_user.id,
        account_id=account_id,
        run_id=run_id,
    )
    return success_response(data=result)