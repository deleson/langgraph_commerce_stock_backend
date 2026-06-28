from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.services.ai_quota_service import AIQuotaService
from app.services.ai_usage_service import AIUsageService


def test_quota_day_uses_account_timezone_across_utc_midnight() -> None:
    service = AIQuotaService(
        repo=None,  # type: ignore[arg-type]
        now_provider=lambda: datetime(2026, 6, 28, 16, 30, tzinfo=UTC),
    )

    assert service._build_today_range("Asia/Shanghai") == (
        date(2026, 6, 29),
        date(2026, 6, 29),
    )
    assert service._build_current_month_range("Asia/Shanghai") == (
        date(2026, 6, 1),
        date(2026, 6, 30),
    )


def test_quota_day_falls_back_to_default_timezone() -> None:
    service = AIQuotaService(
        repo=None,  # type: ignore[arg-type]
        now_provider=lambda: datetime(2026, 6, 28, 16, 30, tzinfo=UTC),
    )

    assert service._build_today_range("Invalid/Timezone") == (
        date(2026, 6, 29),
        date(2026, 6, 29),
    )

@pytest.mark.asyncio
async def test_usage_recording_uses_quota_account_timezone() -> None:
    class FakeRepo:
        async def create_usage_log(self, payload):
            return payload

        async def get_or_create_quota_account(self, *, user_id: int):
            assert user_id == 7
            return SimpleNamespace(timezone="Asia/Shanghai")

    class CapturingUsageService(AIUsageService):
        def __init__(self) -> None:
            super().__init__(FakeRepo())  # type: ignore[arg-type]
            self.periods: list[tuple[str, str]] = []

        async def _increment_period_summary(
            self,
            *,
            payload,
            period_type: str,
            timezone_name: str,
        ) -> None:
            self.periods.append((period_type, timezone_name))

    service = CapturingUsageService()
    payload = SimpleNamespace(user_id=7)

    await service.record_usage(payload)  # type: ignore[arg-type]

    assert service.periods == [
        ("day", "Asia/Shanghai"),
        ("month", "Asia/Shanghai"),
    ]
