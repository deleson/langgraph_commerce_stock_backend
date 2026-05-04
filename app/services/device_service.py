from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.device import Device
from app.models.user import User
from app.repositories.device_repo import DeviceRepository,AsyncDeviceRepository
from app.schemas.device import DeviceRegisterRequest


class DeviceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.device_repo = DeviceRepository(db)

    def list_my_devices(self, user: User) -> list[Device]:
        return self.device_repo.list_by_user_id(user.id)

    def register_or_update_device(
        self,
        *,
        user: User,
        payload: DeviceRegisterRequest,
    ) -> Device:
        device = self.device_repo.get_by_platform_token_for_user(
            user_id=user.id,
            platform=payload.platform,
            push_token=payload.push_token,
        )

        if device is not None:
            device.device_name = payload.device_name
            device.is_active = True
            device.last_seen_at = datetime.now(timezone.utc)
            return self.device_repo.save(device)

        return self.device_repo.create(
            user_id=user.id,
            platform=payload.platform,
            push_token=payload.push_token,
            device_name=payload.device_name,
        )

    def deactivate_my_device(
        self,
        *,
        user: User,
        device_id: int,
    ) -> Device:
        device = self.device_repo.get_by_id_for_user(
            device_id=device_id,
            user_id=user.id,
        )
        if device is None:
            raise NotFoundException(
                message="device not found",
                details=[
                    {
                        "field": "device_id",
                        "reason": "device does not exist",
                    }
                ],
            )

        if not device.is_active:
            return device

        return self.device_repo.deactivate(device)


class AsyncDeviceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.device_repo = AsyncDeviceRepository(db)

    async def list_my_devices(self, user: User) -> list[Device]:
        return await self.device_repo.list_by_user_id(user.id)

    async def register_or_update_device(
        self,
        *,
        user: User,
        payload: DeviceRegisterRequest,
    ) -> Device:
        device = await self.device_repo.get_by_platform_token_for_user(
            user_id=user.id,
            platform=payload.platform,
            push_token=payload.push_token,
        )

        if device is not None:
            device.device_name = payload.device_name
            device.is_active = True
            device.last_seen_at = datetime.now(timezone.utc)
            return await self.device_repo.save(device)

        return await self.device_repo.create(
            user_id=user.id,
            platform=payload.platform,
            push_token=payload.push_token,
            device_name=payload.device_name,
        )

    async def deactivate_my_device(
        self,
        *,
        user: User,
        device_id: int,
    ) -> Device:
        device = await self.device_repo.get_by_id_for_user(
            device_id=device_id,
            user_id=user.id,
        )
        if device is None:
            raise NotFoundException(
                message="device not found",
                details=[
                    {
                        "field": "device_id",
                        "reason": "device does not exist",
                    }
                ],
            )

        if not device.is_active:
            return device

        return await self.device_repo.deactivate(device)