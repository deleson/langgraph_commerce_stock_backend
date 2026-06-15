"""access token 黑名单 Service。

JWT 本身是无状态 token，签发后在过期前默认无法主动失效。
本服务使用 Redis 保存 token jti，让退出登录后的 access token 可以提前失效。
"""

from datetime import UTC,datetime

from app.core.redis import get_redis_client
from app.core.security import decode_access_token


ACCESS_TOKEN_BLACKLIST_PRFEIX = "auth:blacklist:access"

class TokenBlacklistService:
    """基于 Redis 的 access token 黑名单服务。"""

    def __init__(self) -> None:
        self.redis = get_redis_client()


    def _build_key(self,jti:str) -> str:
        return f"{ACCESS_TOKEN_BLACKLIST_PRFEIX}:{jti}"

    def blacklist_access_token(self,token:str) -> None:
        """把 access token 加入黑名单。

        Redis TTL 使用 token 剩余有效期，过期后自动清理，不需要永久保存。
        """

        payload = decode_access_token(token)
        now_ts = int(datetime.now(UTC).timestamp())
        ttl_seconds = max(payload.exp - now_ts,1)

        self.redis.set(
            self._build_key(payload.jti),
            "1",
            ex=ttl_seconds,
        )

    def is_access_token_blacklisted(self,jti:str) -> bool:
        """检查某个 JWT jti 是否已经被加入黑名单。"""

        return bool(self.redis.exists(self._build_key(jti)))
