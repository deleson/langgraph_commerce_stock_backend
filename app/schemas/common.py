from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=0, description="业务状态码，0 表示成功")
    message: str = Field(default="success", description="响应说明")
    data: T | None = Field(default=None, description="响应数据")


class ErrorDetail(BaseModel):
    field: str | None = Field(default=None, description="错误字段")
    reason: str = Field(..., description="错误原因")


class ErrorResponse(BaseModel):
    code: int = Field(..., description="业务错误码")
    message: str = Field(..., description="错误说明")
    details: list[ErrorDetail] | None = Field(default=None, description="错误详情列表")
