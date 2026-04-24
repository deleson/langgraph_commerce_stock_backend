from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repo import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

DBSession = Annotated[Session, Depends(get_db_session)]


def get_current_user(
    db: DBSession,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    payload = decode_access_token(token)
    user = UserRepository(db).get_by_id(payload.user_id)

    if user is None:
        raise UnauthorizedException(
            message="user not found for token",
            details=[{"field": "authorization", "reason": "user does not exist"}],
        )

    if not user.is_active or user.status != "active":
        raise UnauthorizedException(
            message="user is inactive or suspended",
            details=[{"field": "authorization", "reason": "user is not allowed to access"}],
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]