from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException
from app.schemas.common import ErrorResponse,ErrorDetail


def register_exception_handlers(app:FastAPI) ->None:
    @app.exception_handler(AppException)
    async def handle_app_exception(
            request:Request,
            exc:AppException,
    ) -> JSONResponse:
        details = None
        if exc.details:
            details = [ErrorDetail(**detail).model_dump() for detail in exc.details]

        response = ErrorResponse(
            code = exc.code,
            message=exc.message,
            details=details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
            request:Request,
            exc:RequestValidationError,
    ) -> JSONResponse:
        details = [
            ErrorDetail(
                field=".".join(str(item) for item in error["loc"]),
                reason= error["msg"]
            ).model_dump()
            for error in exc.errors()
        ]

        response = ErrorResponse(
            code = 10002,
            message="request validation failed",
            details=details,
        )

        return JSONResponse(
            status_code=422,
            content=response.model_dump()
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        response = ErrorResponse(
            code=10005,
            message="internal server error",
            details=None,
        )
        return JSONResponse(
            status_code=500,
            content=response.model_dump(),
        )