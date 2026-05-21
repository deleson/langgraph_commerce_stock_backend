from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.portfolio_backtest import (
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
)
from app.services.portfolio_backtest_query_service import (
    PortfolioBacktestQueryService,
)
from app.utils.responses import success_response


router = APIRouter(prefix="/portfolio-backtests", tags=["portfolio-backtests"])


@router.post(
    "",
    summary="Run Portfolio Backtest",
    description=(
        "Run a multi-asset portfolio historical backtest using stored market "
        "candles, target weights, shared cash, simulated rebalancing trades, "
        "transaction costs, daily portfolio equity, position snapshots, and "
        "portfolio performance metrics. This result is for strategy research "
        "only and does not constitute investment advice."
    ),
    response_model=ApiResponse[PortfolioBacktestResponse],
    status_code=status.HTTP_200_OK,
)
async def run_portfolio_backtest(
    payload: PortfolioBacktestRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[PortfolioBacktestResponse]:
    """Run one historical portfolio backtest for the current user.

    The router only handles HTTP concerns:
    - receive and validate request payload
    - require authenticated user
    - inject AsyncSession
    - call PortfolioBacktestQueryService
    - return unified API response
    """

    _ = current_user

    result = await PortfolioBacktestQueryService(db).run_portfolio_backtest(payload)
    return success_response(data=result)