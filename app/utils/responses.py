from typing import Any

from app.schemas.common import ApiResponse

def success_response(
        data:Any = None,
        message:str="success",
        code:int=0,
) -> ApiResponse[Any]:
    return ApiResponse(code=code,message=message,data=data)

