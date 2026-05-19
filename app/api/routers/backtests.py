from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.schemas.common import ApiResponse
from app.services.backtest_query_service import BacktestQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post(
    "",
    summary="Run Stock Backtest",
    description=(
        "Run a single-stock historical backtest using stored market candles, "
        "technical indicators, strategy signals, simulated trades, daily equity, "
        "and basic performance metrics. This result is for strategy research only "
        "and does not constitute investment advice."
    ),
    response_model=ApiResponse[BacktestResponse],
    status_code=status.HTTP_200_OK,
)
async def run_stock_backtest(
    payload: BacktestRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[BacktestResponse]:
    """Run one historical backtest for the current user.

    The router only handles HTTP concerns:
    - receive and validate request payload
    - require authenticated user
    - inject AsyncSession
    - call BacktestQueryService
    - return unified API response
    """

    _ = current_user

    result = await BacktestQueryService(db).run_backtest(payload)
    return success_response(data=result)