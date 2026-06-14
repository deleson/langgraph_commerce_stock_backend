"""单股回测 API Router。

该 Router 提供基于历史 K 线和策略信号的单股回测入口。
回测只用于研究和学习，历史结果不代表未来收益，也不构成投资建议。
"""

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
    """执行一次单股历史回测。

    Router 只负责接收请求和鉴权，K 线读取、策略信号、模拟成交、
    资金曲线和绩效指标由 BacktestQueryService 及下游服务处理。
    回测结果只用于研究，不能代表未来收益。
    """

    _ = current_user

    result = await BacktestQueryService(db).run_backtest(payload)
    return success_response(data=result)
