from app.schemas.auth import (
    AuthenticatedUser,
    RefreshTokenRequest,
    TokenPairResponse,
    TokenPayload,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.schemas.common import ApiResponse, ErrorDetail, ErrorResponse
from app.schemas.preference import UserPreferenceResponse, UserPreferenceUpdateRequest
from app.schemas.user import UserResponse, UserUpdateRequest
from app.schemas.watchlist import (
    WatchlistCreateRequest,
    WatchlistResponse,
    WatchlistUpdateRequest,
)

__all__ = [
    "ApiResponse",
    "ErrorDetail",
    "ErrorResponse",
    "UserRegisterRequest",
    "UserLoginRequest",
    "TokenPayload",
    "TokenResponse",
    "AuthenticatedUser",
    "UserResponse",
    "UserUpdateRequest",
    "RefreshTokenRequest",
    "TokenPairResponse",
    "WatchlistCreateRequest",
    "WatchlistUpdateRequest",
    "WatchlistResponse",
    "UserPreferenceUpdateRequest",
    "UserPreferenceResponse",
]
