from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.device import Device


class DeviceRepository:
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