"""系统健康检查 API Router。

该 Router 提供生产部署、CI/CD 和运维检查使用的健康接口。
健康检查只验证应用入口可访问，不代表外部行情源、LLM 或后台任务全部可用。
"""

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
