from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
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

    def update_user_profile(self,user:User,payload:UserUpdateRequest) -> User:
        user.timezone = payload.timezone
        user.risk_preference=payload.risk_preference
        return self.user_repo.save(user)


