from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.stock_analysis import StockAnalysisRequest, StockAnalysisResponse
from app.services.stock_analysis_service import AsyncStockAnalysisService
from app.utils.responses import success_response

router = APIRouter(prefix="/analysis", tags=["stock-analysis"])


@router.post(
    "/stock",
    summary="Analyze Stock",
    response_model=ApiResponse[StockAnalysisResponse],
    status_code=status.HTTP_201_CREATED,
)
async def analyze_stock(
    payload: StockAnalysisRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    # Stock analysis is user-scoped: records and notifications belong to CurrentUser.
    result = await AsyncStockAnalysisService(db).analyze_stock(
        user=current_user,
        payload=payload,
    )
    return success_response(data=result)