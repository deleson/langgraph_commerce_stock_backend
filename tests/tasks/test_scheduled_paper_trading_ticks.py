"""纸面交易定时任务按活跃账户提交测试。"""

from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.models.user import User
from app.repositories.watchlist_repo import AsyncWatchlistRepository
from app.schemas.paper_trading import PaperTradingAccountCreate
from app.services.paper_trading_account_service import PaperTradingAccountService
from app.tasks import background_tasks


async def test_scheduled_paper_trading_submits_each_active_account(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch,
) -> None:
    watchlist_item = await AsyncWatchlistRepository(db_session).create(
        user_id=test_user.id,
        symbol="000001",
        market="CN",
        name="平安银行",
    )
    account_service = PaperTradingAccountService(db_session)
    account_ids: list[int] = []
    for name in ("组合一", "组合二"):
        account = await account_service.create_account(
            user_id=test_user.id,
            request=PaperTradingAccountCreate(
                name=name,
                initial_cash="100000",
                currency="CNY",
                watchlist_item_ids=[watchlist_item.id],
            ),
        )
        account_ids.append(account.id)

    sent_task_args: list[list[int]] = []

    def fake_send_task(name: str, args: list[int]) -> SimpleNamespace:
        assert name == "background_tasks.dispatch_background_task"
        sent_task_args.append(args)
        return SimpleNamespace(id=f"fake-paper-task-{len(sent_task_args)}")

    monkeypatch.setattr(background_tasks.celery_app, "send_task", fake_send_task)

    result = await background_tasks._submit_scheduled_paper_trading_ticks_async()

    assert result["status"] == "success"
    assert result["submitted_count"] == 2
    assert result["duplicate_count"] == 0
    assert len(sent_task_args) == 2
    duplicate_result = await background_tasks._submit_scheduled_paper_trading_ticks_async()
    assert duplicate_result["status"] == "skipped"
    assert duplicate_result["reason"] == "paper_trading_ticks_already_submitted"
    assert duplicate_result["submitted_count"] == 0
    assert duplicate_result["duplicate_count"] == 2
    assert len(sent_task_args) == 2


    rows = await db_session.execute(
        select(BackgroundTask).where(BackgroundTask.task_type == "paper_trading_tick")
    )
    tasks = list(rows.scalars().all())
    assert {task.payload["account_id"] for task in tasks} == set(account_ids)
    assert all(task.payload["target_user_id"] == test_user.id for task in tasks)
    assert len(tasks) == 2

    assert all(task.idempotency_key for task in tasks)
