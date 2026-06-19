from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedException
from app.core.security import generate_refresh_token
from app.models.user import User
from app.services.session_service import AsyncSessionService


async def test_session_service_resolves_device_category() -> None:
    service = AsyncSessionService  # 只测试纯函数，不需要数据库连接。

    assert service.resolve_device_category("android") == "mobile"
    assert service.resolve_device_category("ios") == "mobile"
    assert service.resolve_device_category("web") == "web"
    assert service.resolve_device_category("desktop") == "unknown"


async def test_revoke_same_category_sessions_only_revokes_matching_category(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    service = AsyncSessionService(db_session)
    old_mobile = await service.create_refresh_session(
        user_id=test_user.id,
        refresh_token=generate_refresh_token(),
        device_platform="android",
        device_category="mobile",
    )
    web_session = await service.create_refresh_session(
        user_id=test_user.id,
        refresh_token=generate_refresh_token(),
        device_platform="web",
        device_category="web",
    )
    new_mobile = await service.create_refresh_session(
        user_id=test_user.id,
        refresh_token=generate_refresh_token(),
        device_platform="ios",
        device_category="mobile",
    )

    revoked = await service.revoke_same_category_sessions(
        user_id=test_user.id,
        device_category="mobile",
        replaced_by_session_id=new_mobile.id,
    )

    assert [session.id for session in revoked] == [old_mobile.id]
    await db_session.refresh(old_mobile)
    await db_session.refresh(web_session)
    await db_session.refresh(new_mobile)
    assert old_mobile.is_revoked is True
    assert old_mobile.revoked_reason == "replaced_by_same_category_login"
    assert old_mobile.replaced_by_session_id == new_mobile.id
    assert web_session.is_revoked is False
    assert new_mobile.is_revoked is False


async def test_validate_access_session_rejects_revoked_session(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    service = AsyncSessionService(db_session)
    session = await service.create_refresh_session(
        user_id=test_user.id,
        refresh_token=generate_refresh_token(),
        device_platform="android",
        device_category="mobile",
    )
    await service.session_repo.revoke(
        session,
        reason="replaced_by_same_category_login",
    )

    try:
        await service.validate_access_session(
            session_id=session.id,
            user_id=test_user.id,
        )
    except UnauthorizedException as exc:
        assert exc.details[0]["reason"] == "replaced_by_same_category_login"
    else:
        raise AssertionError("revoked session should be rejected")