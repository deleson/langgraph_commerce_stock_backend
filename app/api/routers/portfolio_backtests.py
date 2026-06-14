"""组合回测 API Router。

该 Router 提供多资产组合回测入口，支持目标权重、调仓频率、资金曲线和绩效指标。
组合回测用于研究历史表现，不代表未来收益，也不构成投资建议。
"""

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
    """执行一次组合历史回测。

    Router 不直接处理调仓和绩效计算。
    多资产对齐、目标权重、调仓交易、组合权益和绩效指标由
    PortfolioBacktestQueryService 及下游服务完成。
    """

    _ = current_user

    result = await PortfolioBacktestQueryService(db).run_portfolio_backtest(payload)
    return success_response(data=result)
