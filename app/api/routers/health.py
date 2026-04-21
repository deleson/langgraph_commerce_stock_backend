from fastapi import APIRouter
from app.utils.responses import success_response
from app.schemas.common import ApiResponse
from app.core.exceptions import BadRequestException

router = APIRouter(prefix="/system",tags=["health"])


@router.get("/health", summary="Health Check",response_model=ApiResponse[dict[str,str]])
def health() -> dict[str, str]:
    return success_response(data={"status":"ok"})



@router.get("/error-demo", summary="Error Demo")
def error_demo():
    raise BadRequestException(
        message="demo bad request",
        details=[{"field": "query.demo", "reason": "this is a demo error"}],
    )