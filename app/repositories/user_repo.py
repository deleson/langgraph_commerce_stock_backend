"""用户 Repository。

本文件封装 users 表的数据访问：按 id、邮箱、用户名查询用户，创建用户，
以及保存用户基础信息。密码校验、JWT 签发、注册冲突处理等业务规则由 Service 层负责。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """同步用户数据访问对象。

    早期同步链路保留该类，当前主业务更多使用 AsyncUserRepository。
    """

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
        is_active: bool = True,
        is_superuser: bool = False,
        status: str = "active",
    ) -> User:
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
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


class AsyncUserRepository:
    """异步用户数据访问对象。

    只负责 users 表查询和写入，不处理密码安全、登录状态或权限判断。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_users(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[User]:
        """分页查询活跃用户。

        生产定时任务会用它批量扫描需要执行日报、提醒或纸面交易的用户。
        """

        stmt = (
            select(User)
            .where(User.is_active.is_(True), User.status == "active")
            .order_by(User.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        email: str,
        username: str,
        hashed_password: str,
        is_active: bool = True,
        is_superuser: bool = False,
        status: str = "active",
    ) -> User:
        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            is_active=is_active,
            is_superuser=is_superuser,
            status=status,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def save(self, user: User) -> User:
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
