from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ConflictException
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserUpdateRequest



class UserService:
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


