"""设备 API Router。

该 Router 管理当前用户的设备注册、列表和停用。
设备能力主要为后续多端登录、推送通知或客户端识别预留。
"""

from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.device import DeviceRegisterRequest, DeviceResponse
from app.services.device_service import AsyncDeviceService
from app.utils.responses import success_response

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post(
    "",
    summary="Register Or Update My Device",
    response_model=ApiResponse[DeviceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register_or_update_my_device(
    payload: DeviceRegisterRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    # Device registration is idempotent: the same platform/token updates the existing row.
    device = await AsyncDeviceService(db).register_or_update_device(
        user=current_user,
        payload=payload,
    )
    return success_response(data=DeviceResponse.model_validate(device))


@router.get(
    "",
    summary="List My Devices",
    response_model=ApiResponse[list[DeviceResponse]],
)
async def list_my_devices(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    devices = await AsyncDeviceService(db).list_my_devices(current_user)
    return success_response(
        data=[DeviceResponse.model_validate(device) for device in devices]
    )


@router.patch(
    "/{device_id}/deactivate",
    summary="Deactivate My Device",
    response_model=ApiResponse[DeviceResponse],
)
async def deactivate_my_device(
    device_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    # Deactivation keeps the device record for audit/history but excludes it from future push.
    device = await AsyncDeviceService(db).deactivate_my_device(
        user=current_user,
        device_id=device_id,
    )
    return success_response(data=DeviceResponse.model_validate(device))
