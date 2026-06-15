"""ReAct 工具追问 API 测试。

本文件使用 FakeReactChatModel 验证工具选择、Observation、Trace 和会话消息落库。
测试重点是工具白名单和用户隔离，不调用真实 DeepSeek。
"""

import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_conversation_message import AnalysisConversationMessage
from app.models.analysis_react_trace import AnalysisReactTrace
from app.models.analysis_record import AnalysisRecord
from app.models.user import User


API_PREFIX = "/api/v1"


class FakeReactChatModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[list[object]] = []

    async def ainvoke(self, messages: list[object]) -> SimpleNamespace:
        self.calls.append(messages)

        if not self.responses:
            content = json.dumps(
                {
                    "next_action": "final_answer",
                    "final_answer": "这是默认的 Mock ReAct 最终回答。",
                },
                ensure_ascii=False,
            )
        else:
            content = self.responses.pop(0)

        return SimpleNamespace(
            content=content,
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
                "model_name": "mock-react-llm",
            },
        )


@pytest.fixture
def mock_react_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_check_quota(**kwargs):
        return True, None, SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            token_source="estimated",
        ), SimpleNamespace(
            estimated_cost="0.0001",
            currency="USD",
        )

    async def fake_record_success(**kwargs):
        return SimpleNamespace(id=20001)

    monkeypatch.setattr("app.graphs.react_nodes._check_react_ai_quota", fake_check_quota)
    monkeypatch.setattr("app.graphs.react_nodes._record_react_ai_success", fake_record_success)


@pytest.fixture
def mock_react_llm_with_analysis_record_tool(
    monkeypatch: pytest.MonkeyPatch,
    mock_react_quota: None,
) -> FakeReactChatModel:
    llm = FakeReactChatModel(
        responses=[
            json.dumps(
                {
                    "next_action": "tool_call",
                    "tool_call": {
                        "tool_name": "get_analysis_record",
                        "tool_input": {
                            "analysis_thread_id": "react-thread-aapl",
                        },
                        "reason": "需要先读取原始分析记录。",
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "next_action": "final_answer",
                    "final_answer": "我已经查看原始分析记录，AAPL 当前更适合继续观察，不构成投资建议。",
                },
                ensure_ascii=False,
            ),
        ]
    )

    monkeypatch.setattr("app.graphs.react_nodes.get_chat_model", lambda: llm)

    return llm


@pytest.fixture
def mock_react_llm_with_watchlist_tool(
    monkeypatch: pytest.MonkeyPatch,
    mock_react_quota: None,
) -> FakeReactChatModel:
    llm = FakeReactChatModel(
        responses=[
            json.dumps(
                {
                    "next_action": "tool_call",
                    "tool_call": {
                        "tool_name": "get_watchlist",
                        "tool_input": {
                            "limit": 10,
                        },
                        "reason": "用户询问自选股，需要读取当前用户自选股。",
                    },
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "next_action": "final_answer",
                    "final_answer": "我已经查看你的自选股列表，可以围绕其中股票继续做研究比较。",
                },
                ensure_ascii=False,
            ),
        ]
    )

    monkeypatch.setattr("app.graphs.react_nodes.get_chat_model", lambda: llm)

    return llm


@pytest.fixture
def mock_react_llm_direct_final_answer(
    monkeypatch: pytest.MonkeyPatch,
    mock_react_quota: None,
) -> FakeReactChatModel:
    llm = FakeReactChatModel(
        responses=[
            json.dumps(
                {
                    "next_action": "final_answer",
                    "final_answer": "这个问题可以直接基于已有分析回答，不需要调用工具。",
                },
                ensure_ascii=False,
            ),
        ]
    )

    monkeypatch.setattr("app.graphs.react_nodes.get_chat_model", lambda: llm)

    return llm


async def _create_analysis_record(
    db_session: AsyncSession,
    *,
    user_id: int,
    thread_id: str = "react-thread-aapl",
    symbol: str = "AAPL",
    market: str = "US",
) -> AnalysisRecord:
    record = AnalysisRecord(
        user_id=user_id,
        symbol=symbol,
        market=market,
        analysis_type="stock_basic",
        status="completed",
        analysis_thread_id=thread_id,
        summary="AAPL mock analysis summary",
        result_snapshot={
            "graph_route": "normal",
            "result": {
                "summary": "AAPL mock analysis summary",
                "risk_level": "medium",
                "trend": "bullish",
                "key_points": [
                    "测试用分析记录。",
                    "不构成投资建议。",
                ],
                "suggestion": "observe",
                "warnings": [
                    "测试环境 Mock 数据。",
                ],
            },
            "context_snapshot": {
                "symbol": symbol,
                "market": market,
            },
            "quality_context": {
                "route": "normal",
            },
        },
        error_message=None,
    )

    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    return record


async def _list_conversation_messages(
    db_session: AsyncSession,
    *,
    user_id: int,
    thread_id: str,
) -> list[AnalysisConversationMessage]:
    result = await db_session.execute(
        select(AnalysisConversationMessage)
        .where(AnalysisConversationMessage.user_id == user_id)
        .where(AnalysisConversationMessage.analysis_thread_id == thread_id)
        .order_by(AnalysisConversationMessage.sequence_no.asc())
    )
    return list(result.scalars().all())


async def _list_react_traces(
    db_session: AsyncSession,
    *,
    user_id: int,
    thread_id: str,
) -> list[AnalysisReactTrace]:
    result = await db_session.execute(
        select(AnalysisReactTrace)
        .where(AnalysisReactTrace.user_id == user_id)
        .where(AnalysisReactTrace.analysis_thread_id == thread_id)
        .order_by(AnalysisReactTrace.step.asc())
    )
    return list(result.scalars().all())


async def test_react_follow_up_calls_analysis_record_tool_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    mock_react_llm_with_analysis_record_tool: FakeReactChatModel,
) -> None:
    record = await _create_analysis_record(
        db_session,
        user_id=test_user.id,
        thread_id="react-thread-aapl",
    )

    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/react-follow-up",
        json={
            "analysis_thread_id": "react-thread-aapl",
            "message": "帮我结合原始分析再解释一下风险。",
            "max_iterations": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["analysis_thread_id"] == "react-thread-aapl"
    assert data["referenced_analysis_record_id"] == record.id
    assert data["referenced_symbol"] == "AAPL"
    assert data["referenced_market"] == "US"
    assert data["react_graph_checkpoint_id"].startswith("react:react-thread-aapl:")
    assert data["answer"] == "我已经查看原始分析记录，AAPL 当前更适合继续观察，不构成投资建议。"
    assert data["used_tools"] == ["get_analysis_record"]

    assert len(data["observations"]) == 1
    assert data["observations"][0]["tool_name"] == "get_analysis_record"
    assert data["observations"][0]["success"] is True
    assert data["observations"][0]["tool_output"]["analysis_thread_id"] == "react-thread-aapl"

    assert len(data["trace"]) == 1
    assert data["trace"][0]["action"] == "tool_call"
    assert data["trace"][0]["tool_name"] == "get_analysis_record"
    assert data["trace"][0]["success"] is True

    assert len(mock_react_llm_with_analysis_record_tool.calls) == 2

    messages = await _list_conversation_messages(
        db_session,
        user_id=test_user.id,
        thread_id="react-thread-aapl",
    )
    assert [message.role for message in messages] == ["user", "tool", "assistant"]
    assert messages[0].message_type == "react_follow_up"
    assert messages[1].message_type == "tool_observation"
    assert messages[2].message_type == "react_follow_up"

    traces = await _list_react_traces(
        db_session,
        user_id=test_user.id,
        thread_id="react-thread-aapl",
    )
    assert len(traces) == 1
    assert traces[0].tool_name == "get_analysis_record"
    assert traces[0].success is True


async def test_react_follow_up_calls_watchlist_tool_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    mock_react_llm_with_watchlist_tool: FakeReactChatModel,
) -> None:
    await _create_analysis_record(
        db_session,
        user_id=test_user.id,
        thread_id="react-thread-watchlist",
    )

    watchlist_response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json={
            "symbol": "MSFT",
            "market": "US",
            "name": "Microsoft",
            "notes": "测试自选股",
        },
        headers=auth_headers,
    )
    assert watchlist_response.status_code == 201

    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/react-follow-up",
        json={
            "analysis_thread_id": "react-thread-watchlist",
            "message": "结合我的自选股看一下后续还可以研究什么。",
            "max_iterations": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["used_tools"] == ["get_watchlist"]
    assert data["observations"][0]["tool_name"] == "get_watchlist"
    assert data["observations"][0]["success"] is True
    assert data["observations"][0]["tool_output"]["count"] == 1
    assert data["observations"][0]["tool_output"]["items"][0]["symbol"] == "MSFT"
    assert data["answer"] == "我已经查看你的自选股列表，可以围绕其中股票继续做研究比较。"

    assert len(mock_react_llm_with_watchlist_tool.calls) == 2


async def test_react_follow_up_direct_final_answer_without_tool(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    mock_react_llm_direct_final_answer: FakeReactChatModel,
) -> None:
    await _create_analysis_record(
        db_session,
        user_id=test_user.id,
        thread_id="react-thread-direct",
    )

    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/react-follow-up",
        json={
            "analysis_thread_id": "react-thread-direct",
            "message": "用一句话总结一下。",
            "max_iterations": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["answer"] == "这个问题可以直接基于已有分析回答，不需要调用工具。"
    assert data["used_tools"] == []
    assert data["observations"] == []
    assert data["trace"] == []

    assert len(mock_react_llm_direct_final_answer.calls) == 1

    messages = await _list_conversation_messages(
        db_session,
        user_id=test_user.id,
        thread_id="react-thread-direct",
    )
    assert [message.role for message in messages] == ["user", "assistant"]


async def test_react_follow_up_unknown_thread_returns_404(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_react_llm_direct_final_answer: FakeReactChatModel,
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/react-follow-up",
        json={
            "analysis_thread_id": "not-exists-react-thread",
            "message": "这份分析还能继续解释吗？",
            "max_iterations": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "stock analysis thread not found"
    assert len(mock_react_llm_direct_final_answer.calls) == 0


async def test_user_cannot_react_follow_up_other_users_thread(
    async_client: AsyncClient,
    db_session: AsyncSession,
    another_test_user: User,
    auth_headers: dict[str, str],
    mock_react_llm_direct_final_answer: FakeReactChatModel,
) -> None:
    await _create_analysis_record(
        db_session,
        user_id=another_test_user.id,
        thread_id="other-user-react-thread",
    )

    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/react-follow-up",
        json={
            "analysis_thread_id": "other-user-react-thread",
            "message": "我能看别人的分析吗？",
            "max_iterations": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "stock analysis thread not found"
    assert len(mock_react_llm_direct_final_answer.calls) == 0


async def test_react_follow_up_invalid_max_iterations_returns_422(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    await _create_analysis_record(
        db_session,
        user_id=test_user.id,
        thread_id="react-thread-invalid-max-iterations",
    )

    response = await async_client.post(
        f"{API_PREFIX}/analysis/stock/react-follow-up",
        json={
            "analysis_thread_id": "react-thread-invalid-max-iterations",
            "message": "测试非法 max_iterations。",
            "max_iterations": 0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
