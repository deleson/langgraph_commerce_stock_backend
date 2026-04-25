from datetime import UTC,datetime

from app.core.redis import get_redis_client
from app.core.security import decode_access_token


ACCESS_TOKEN_BLACKLIST_PRFEIX = "auth:balcklist:access"

class TokenBlacklistService:
    def __init__(self) -> None:
        self.redis = get_redis_client()


    def _build_key(self,jti:str) -> str:
        return f"{ACCESS_TOKEN_BLACKLIST_PRFEIX}:{jti}"

    def blacklist_access_token(self,token:str) -> None:
        payload = decode_access_token(token)
        now_ts = int(datetime.now(UTC).timestamp())
        ttl_seconds = max(payload.exp - now_ts,1)

        self.redis.set(
            self._build_key(payload.jti),
            "1",
            ex=ttl_seconds,
        )

    def is_access_token_blacklisted(self,jti:str) -> bool:
        return bool(self.redis.exists(self._build_key(jti)))