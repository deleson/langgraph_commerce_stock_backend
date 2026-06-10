import json
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_record import AnalysisRecord
from app.models.notification import Notification
from app.models.user import User


API_PREFIX = "/api/v1"


class FakeChatModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[object]] = []

    async def ainvoke(self, messages: list[object]) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(
            content=self.content,
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
                "model_name": "mock-llm",
            },
        )


@pytest.fixture
def mock_stock_analysis_llm(monkeypatch: pytest.MonkeyPatch) -> FakeChatModel:
    llm = FakeChatModel(
        json.dumps(
            {
                "summary": "这是 Mock LLM 生成的 AAPL 测试分析摘要。",
                "risk_level": "medium",
                "trend": "bullish",
                "key_points": [
                    "Mock 行情显示价格相对前收盘上涨。",
                    "技术指标仅用于测试链路，不构成投资建议。",
                ],
                "suggestion": "建议继续观察，结合更多信息谨慎判断。",
                "warnings": [
                    "这是测试环境生成的 Mock 分析。",
                    "本结果不构成投资建议。",
                ],
            },
            ensure_ascii=False,
        )
    )

    async def fake_check_quota(**kwargs):
        return True, None, None, None

    async def fake_record_success(**kwargs):
        return SimpleNamespace(id=10001)

    monkeypatch.setattr("app.graphs.nodes.get_chat_model", lambda: llm)
    monkeypatch.setattr("app.graphs.nodes._check_stock_analysis_ai_quota", fake_check_quota)
    monkeypatch.setattr("app.graphs.nodes._record_stock_analysis_ai_success", fake_record_success)

    return llm


@pytest.fixture
def mock_follow_up_llm(monkeypatch: pytest.MonkeyPatch) -> FakeChatModel:
    llm = FakeChatModel("这是 Mock LLM 生成的追问回答。")

    monkeypatch.setattr("app.services.stock_analysis_service.get_chat_model", lambda: llm)

    return llm


async def _sync_mock_candles_for_analysis(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    symbol: str = "AAPL",
    market: str = "US",
    limit: int = 40,
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/market-sync/stocks/{symbol}/candles",
        params={
            "market": market,
            "timeframe": "1d",
            "limit": limit,
            "adjust_type": "none",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["source"] == "mock"


async def _count_analysis_records(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> int:
    result = await db_session.execute(
        select(AnalysisRecord).where(AnalysisRecord.user_id == user_id)
    )
    return len(result.scalars().all())


async def _list_notifications(
    db_session: AsyncSession,
    *,
    user_id: int,
) -> list[Notification]:
    result = await db_session.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    return list(result.scalars().all())


async def test_analyze_stock_with_mock_llm_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    mock_stock_analysis_llm: FakeChatModel,
) -> None:
    await _sync_mock_candles_for_analysis(
        async_client,
        auth_headers,
        symbol="AAPL",
        market="US",
        limit=40,
    )

    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock",
        json={
            "symbol": "AAPL",
            "market": "US",
            "analysis_type": "stock_basic",
            "thread_id": "test-analysis-thread-aapl",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["record_id"] is not None
    assert data["thread_id"] == "test-analysis-thread-aapl"
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["status"] == "completed"
    assert data["graph_route"] == "normal"
    assert data["market_snapshot"]["symbol"] == "AAPL"
    assert data["indicators"]["trend"] in {"bullish", "bearish", "neutral"}
    assert data["result"]["summary"] == "这是 Mock LLM 生成的 AAPL 测试分析摘要。"
    assert data["result"]["risk_level"] == "medium"
    assert data["result"]["trend"] == "bullish"
    assert len(mock_stock_analysis_llm.calls) == 1

    record_count = await _count_analysis_records(db_session, user_id=test_user.id)
    assert record_count == 1

    notifications = await _list_notifications(db_session, user_id=test_user.id)
    assert len(notifications) == 1
    assert notifications[0].notification_type == "analysis_completed"
    assert notifications[0].related_record_id == data["record_id"]


async def test_analyze_stock_without_candles_returns_unavailable_without_llm(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_stock_analysis_llm: FakeChatModel,
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock",
        json={
            "symbol": "AAPL",
            "market": "US",
            "analysis_type": "stock_basic",
            "thread_id": "test-analysis-thread-no-candles",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201

    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["graph_route"] == "unavailable"
    assert data["result"]["trend"] == "neutral"
    assert "行情数据不足" in data["result"]["summary"] or "不可用" in data["result"]["summary"]
    assert len(mock_stock_analysis_llm.calls) == 0


async def test_follow_up_stock_analysis_with_mock_llm_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_stock_analysis_llm: FakeChatModel,
    mock_follow_up_llm: FakeChatModel,
) -> None:
    await _sync_mock_candles_for_analysis(
        async_client,
        auth_headers,
        symbol="AAPL",
        market="US",
        limit=40,
    )

    analyze_response = await async_client.post(
        f"{API_PREFIX}/analysis/stock",
        json={
            "symbol": "AAPL",
            "market": "US",
            "analysis_type": "stock_basic",
            "thread_id": "test-follow-up-thread-aapl",
        },
        headers=auth_headers,
    )
    assert analyze_response.status_code == 201

    follow_up_response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/follow-up",
        json={
            "thread_id": "test-follow-up-thread-aapl",
            "message": "这次分析里面最需要注意什么？",
        },
        headers=auth_headers,
    )

    assert follow_up_response.status_code == 200

    data = follow_up_response.json()["data"]
    assert data["thread_id"] == "test-follow-up-thread-aapl"
    assert data["answer"] == "这是 Mock LLM 生成的追问回答。"
    assert data["referenced_symbol"] == "AAPL"
    assert data["referenced_market"] == "US"
    assert len(mock_follow_up_llm.calls) == 1


async def test_follow_up_unknown_thread_returns_404(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_follow_up_llm: FakeChatModel,
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/follow-up",
        json={
            "thread_id": "not-exists-thread",
            "message": "这个分析还能继续解释吗？",
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "stock analysis thread not found"
    assert len(mock_follow_up_llm.calls) == 0


async def test_user_cannot_follow_up_other_users_analysis_thread(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    another_test_user: User,
    auth_headers: dict[str, str],
    mock_follow_up_llm: FakeChatModel,
) -> None:
    db_session.add(
        AnalysisRecord(
            user_id=another_test_user.id,
            symbol="AAPL",
            market="US",
            analysis_type="stock_basic",
            status="completed",
            analysis_thread_id="other-user-analysis-thread",
            summary="Other user's analysis",
            result_snapshot={
                "result": {
                    "summary": "Other user's analysis",
                    "risk_level": "medium",
                    "trend": "neutral",
                    "key_points": [],
                    "suggestion": "observe",
                    "warnings": [],
                }
            },
            error_message=None,
        )
    )
    await db_session.commit()

    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/follow-up",
        json={
            "thread_id": "other-user-analysis-thread",
            "message": "我能看这份分析吗？",
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "stock analysis thread not found"
    assert len(mock_follow_up_llm.calls) == 0