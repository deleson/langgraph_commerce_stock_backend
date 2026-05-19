from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.services.backtest_service import BacktestService


class BacktestQueryService:
    """Orchestrate backtest queries for API and future tools.

    This service keeps routers thin and gives later steps a stable place to add
    data-quality gates, persistence, user isolation, and AI explanation hooks.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        backtest_service: BacktestService | None = None,
    ) -> None:
        self.db = db
        self.backtest_service = backtest_service or BacktestService(db)

    async def run_backtest(
        self,
        request: BacktestRequest,
    ) -> BacktestResponse:
        return await self.backtest_service.run_backtest(request)