"""业务异常定义。

Service 和 Repository 可以通过这些异常表达可预期的业务失败，
例如资源不存在、请求非法、认证失败或资源冲突。
`exception_handlers.py` 会把这些异常统一转换成 API 响应。
"""

from typing import Any

class AppException(Exception):
    """项目业务异常基类。

    code 用于前端和调用方识别错误类型，status_code 用于 HTTP 状态码，
    details 用于返回字段级错误原因。
    """

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
    """资源不存在异常，通常用于当前用户无法访问或资源确实不存在的场景。"""

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
    """请求非法异常，通常用于业务参数不满足规则的场景。"""

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

class ConflictException(AppException):
    """资源冲突异常，例如邮箱、用户名或唯一业务资源重复。"""

    def __init__(
            self,
            message:str = "resource conflict",
            code:int = 10009,
            details:list[dict[str,Any] | None] = None,
                 ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=409,
            details=details,
        )


class UnauthorizedException(AppException):
    """认证失败异常，例如 token 无效、过期或未登录。"""

    def __init__(
            self,
            message:str = "unauthorized",
            code:int=10010,
            details:list[dict[str,Any] | None] =None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=401,
            details=details,
        )
