"""定时每日简报任务提交测试。"""

from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.user_preference_service import AsyncUserPreferenceService
from app.tasks import background_tasks


async def test_scheduled_daily_reports_only_submits_enabled_users(
    db_session: AsyncSession,
    test_user: User,
    another_test_user: User,
    monkeypatch,
) -> None:
    await AsyncUserPreferenceService(db_session).update_daily_report_mode(
        test_user,
        enabled=True,
    )
    await AsyncUserPreferenceService(db_session).update_daily_report_mode(
        another_test_user,
        enabled=False,
    )

    sent_task_args: list[list[int]] = []

    def fake_send_task(
        name: str,
        args: list[int],
    ) -> SimpleNamespace:
        assert name == "background_tasks.dispatch_background_task"
        sent_task_args.append(args)
        return SimpleNamespace(id=f"fake-celery-task-{len(sent_task_args)}")

    monkeypatch.setattr(background_tasks.celery_app, "send_task", fake_send_task)

    result = await background_tasks._submit_scheduled_daily_reports_async()

    assert result["status"] == "success"
    assert result["reason"] == "scheduled_daily_reports_submitted"
    assert result["submitted_count"] == 1
    assert result["failed_count"] == 0
    assert len(sent_task_args) == 1


async def test_scheduled_daily_reports_skips_when_no_user_enabled(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch,
) -> None:
    await AsyncUserPreferenceService(db_session).update_daily_report_mode(
        test_user,
        enabled=False,
    )

    def fake_send_task(
        name: str,
        args: list[int],
    ) -> SimpleNamespace:
        raise AssertionError("send_task should not be called when no user enabled daily reports")

    monkeypatch.setattr(background_tasks.celery_app, "send_task", fake_send_task)

    result = await background_tasks._submit_scheduled_daily_reports_async()

    assert result["status"] == "skipped"
    assert result["reason"] == "no_daily_report_enabled_users"
    assert result["submitted_count"] == 0
    assert result["failed_count"] == 0
