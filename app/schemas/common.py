"""通用 API 响应 Schema。

本文件定义所有 Router 共用的响应包装结构和错误详情结构。
它只规定接口返回的外层格式，不承载具体业务模块的数据含义。
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一成功响应包装。

    data 的真实类型由具体接口决定，Router 会通过泛型把业务响应体放入这里。
    """

    code: int = Field(default=0, description="业务状态码，0 表示成功")
    message: str = Field(default="success", description="响应说明")
    data: T | None = Field(default=None, description="响应数据")


class ErrorDetail(BaseModel):
    """单个字段或业务校验错误的明细。"""

    field: str | None = Field(default=None, description="错误字段")
    reason: str = Field(..., description="错误原因")


class ErrorResponse(BaseModel):
    """统一错误响应包装。

    生产环境只返回可解释的错误信息，不在响应体中暴露异常堆栈。
    """

    code: int = Field(..., description="业务错误码")
    message: str = Field(..., description="错误说明")
    details: list[ErrorDetail] | None = Field(default=None, description="错误详情列表")
