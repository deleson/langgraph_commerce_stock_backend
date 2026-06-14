"""设备 Repository。

本文件封装 devices 表的数据访问，用于记录用户的推送设备和设备活跃状态。
设备 token 只能在当前用户范围内查询，避免把推送能力串到其他用户。
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


class DeviceRepository:
    """同步设备数据访问对象。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user_id(self, user_id: int) -> list[Device]:
        stmt = (
            select(Device)
            .where(Device.user_id == user_id)
            .order_by(Device.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id_for_user(
        self,
        *,
        device_id: int,
        user_id: int,
    ) -> Device | None:
        stmt = select(Device).where(
            Device.id == device_id,
            Device.user_id == user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_platform_token_for_user(
        self,
        *,
        user_id: int,
        platform: str,
        push_token: str,
    ) -> Device | None:
        stmt = select(Device).where(
            Device.user_id == user_id,
            Device.platform == platform,
            Device.push_token == push_token,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: int,
        platform: str,
        push_token: str,
        device_name: str | None = None,
    ) -> Device:
        device = Device(
            user_id=user_id,
            platform=platform,
            push_token=push_token,
            device_name=device_name,
            is_active=True,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(device)
        self.db.commit()
        self.db.refresh(device)
        return device

    def save(self, device: Device) -> Device:
        self.db.add(device)
        self.db.commit()
        self.db.refresh(device)
        return device

    def deactivate(self, device: Device) -> Device:
        device.is_active = False
        self.db.add(device)
        self.db.commit()
        self.db.refresh(device)
        return device

class AsyncDeviceRepository:
    """异步设备数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user_id(self, user_id: int) -> list[Device]:
        stmt = (
            select(Device)
            .where(Device.user_id == user_id)
            .order_by(Device.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self,
        *,
        device_id: int,
        user_id: int,
    ) -> Device | None:
        stmt = select(Device).where(
            Device.id == device_id,
            Device.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_platform_token_for_user(
        self,
        *,
        user_id: int,
        platform: str,
        push_token: str,
    ) -> Device | None:
        stmt = select(Device).where(
            Device.user_id == user_id,
            Device.platform == platform,
            Device.push_token == push_token,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        platform: str,
        push_token: str,
        device_name: str | None = None,
    ) -> Device:
        device = Device(
            user_id=user_id,
            platform=platform,
            push_token=push_token,
            device_name=device_name,
            is_active=True,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)
        return device

    async def save(self, device: Device) -> Device:
        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)
        return device

    async def deactivate(self, device: Device) -> Device:
        device.is_active = False
        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)
        return device
