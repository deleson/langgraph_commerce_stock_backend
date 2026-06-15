"""用户资料 Service。

本文件负责当前用户资料查询和更新。当前用户身份来自 JWT 解析结果，
不能通过请求体传入 user_id 来修改其他用户资料。
"""

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ConflictException
from app.models.user import User
from app.repositories.user_repo import UserRepository,AsyncUserRepository
from app.schemas.user import UserUpdateRequest



class UserService:
    """同步用户资料业务服务。"""

    def __init__(self,db:Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)

    def get_user_by_id(self,user_id:int) -> User:
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundException(
                message="user not found",
                details=[{"field":"user_id","reason":"iser does exist"}]
            )

        return user

    def update_user_profile(self, user: User, payload: UserUpdateRequest) -> User:
        """更新当前用户资料。

        用户名更新需要检查唯一性，避免和其他账号冲突。
        """

        update_data = payload.model_dump(exclude_unset=True)

        if "username" in update_data:
            username = update_data["username"].strip()
            existing_user = self.user_repo.get_by_username(username)
            if existing_user is not None and existing_user.id != user.id:
                raise ConflictException(
                    message="username already exists",
                    details=[{"field": "username", "reason": "username already exists"}],
                )
            user.username = username

        return self.user_repo.save(user)



class AsyncUserService:
    """异步用户资料业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = AsyncUserRepository(db)

    async def get_user_by_id(self, user_id: int) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundException(
                message="user not found",
                details=[{"field": "user_id", "reason": "user does not exist"}],
            )

        return user

    async def update_user_profile(
        self,
        user: User,
        payload: UserUpdateRequest,
    ) -> User:
        """更新当前用户资料。"""

        update_data = payload.model_dump(exclude_unset=True)

        if "username" in update_data:
            username = update_data["username"].strip()
            existing_user = await self.user_repo.get_by_username(username)
            if existing_user is not None and existing_user.id != user.id:
                raise ConflictException(
                    message="username already exists",
                    details=[
                        {
                            "field": "username",
                            "reason": "username already exists",
                        }
                    ],
                )
            user.username = username

        return await self.user_repo.save(user)
