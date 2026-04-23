from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        email: str,
        username: str,
        hashed_password: str,
        timezone: str | None = None,
        risk_preference: str | None = None,
        is_active: bool = True,
        is_superuser: bool = False,
        status: str = "active",
    ) -> User:
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            timezone=timezone,
            risk_preference=risk_preference,
            is_active=is_active,
            is_superuser=is_superuser,
            status=status,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user