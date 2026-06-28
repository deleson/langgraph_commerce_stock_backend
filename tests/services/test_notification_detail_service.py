from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.notification_service import AsyncNotificationService


def build_notification(**updates):
    values = {
        "id": 11,
        "user_id": 7,
        "title": "Notification",
        "content": "Preview",
        "notification_type": "system",
        "related_record_id": None,
        "is_read": False,
        "read_at": None,
        "created_at": datetime(2026, 6, 28, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 28, tzinfo=UTC),
    }
    values.update(updates)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_analysis_notification_detail_contains_full_record() -> None:
    service = AsyncNotificationService(db=None)  # type: ignore[arg-type]
    service.notification_repo.get_by_id_for_user = AsyncMock(
        return_value=build_notification(
            notification_type="analysis_completed",
            related_record_id=23,
        )
    )
    service.analysis_record_repo.get_by_id_for_user = AsyncMock(
        return_value=SimpleNamespace(
            id=23,
            analysis_thread_id="thread-23",
            symbol="000001",
            market="CN",
            analysis_type="stock_basic",
            status="completed",
            summary="Full summary",
            result_snapshot={"result": {"summary": "Full analysis"}},
            error_message=None,
            created_at=datetime(2026, 6, 28, tzinfo=UTC),
            updated_at=datetime(2026, 6, 28, tzinfo=UTC),
        )
    )

    detail = await service.get_my_notification_detail(
        user=SimpleNamespace(id=7),
        notification_id=11,
    )

    assert detail.analysis_record is not None
    assert detail.analysis_record.id == 23
    assert detail.analysis_record.result_snapshot["result"]["summary"] == "Full analysis"


@pytest.mark.asyncio
async def test_daily_report_notification_detail_supports_legacy_relation() -> None:
    service = AsyncNotificationService(db=None)  # type: ignore[arg-type]
    service.notification_repo.get_by_id_for_user = AsyncMock(
        return_value=build_notification(notification_type="daily_report")
    )
    service.daily_report_repo.get_report_by_notification_id = AsyncMock(
        return_value=SimpleNamespace(
            id=31,
            user_id=7,
            report_date=date(2026, 6, 28),
            status="generated",
            source="api",
            summary="Daily report summary",
            disclaimer="Research only",
            created_at=datetime(2026, 6, 28, tzinfo=UTC),
            updated_at=datetime(2026, 6, 28, tzinfo=UTC),
        )
    )

    detail = await service.get_my_notification_detail(
        user=SimpleNamespace(id=7),
        notification_id=11,
    )

    assert detail.daily_report is not None
    assert detail.daily_report.id == 31
    service.daily_report_repo.get_report_by_notification_id.assert_awaited_once_with(
        notification_id=11,
        user_id=7,
    )
