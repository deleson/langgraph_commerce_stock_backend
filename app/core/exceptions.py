from typing import Any

class AppException(Exception):
    def __init__(
            self,
            message:str,
            code:int=10000,
            status_code:int=400,
            details:list[dict[str,Any]] | None =None,
    ) -> None:
        self.message =message
        self.code = code
        self.status_code = status_code
        self.details = details
        super().__init__(message)



class NotFoundException(AppException):
    def __init__(
        self,
        message: str = "resource not found",
        code: int = 10004,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=404,
            details=details,
        )


class BadRequestException(AppException):
    def __init__(
        self,
        message: str = "bad request",
        code: int = 10001,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=400,
            details=details,
        )