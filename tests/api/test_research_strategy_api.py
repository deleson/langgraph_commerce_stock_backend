"""回测、候选股票和策略研究类 API 测试。

覆盖策略信号、单股回测、组合回测和候选评分。
这些测试验证历史研究链路可用，不证明策略未来收益。
"""

from httpx import AsyncClient


API_PREFIX = "/api/v1"


async def _sync_mock_candles(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    symbol: str = "AAPL",
    market: str = "US",
    limit: int = 80,
) -> dict:
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

    data = response.json()["data"]
    assert data["synced"] is True
    assert data["synced_count"] == limit
    assert data["source"] == "mock"
    assert data["first_candle_time"] is not None
    assert data["last_candle_time"] is not None

    return data


def _date_range_from_sync(sync_data: dict) -> tuple[str, str]:
    return sync_data["first_candle_time"][:10], sync_data["last_candle_time"][:10]


async def test_get_strategy_signal_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(
        async_client,
        auth_headers,
        symbol="AAPL",
        market="US",
        limit=80,
    )

    response = await async_client.get(
        f"{API_PREFIX}/strategy-signals/stocks/AAPL",
        params={
            "market": "US",
            "timeframe": "1d",
            "limit": 80,
            "adjust_type": "none",
            "source": "mock",
            "include_detail": True,
            "min_required": 60,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["timeframe"] == "1d"
    assert data["source"] == "mock"
    assert data["status"] == "available"
    assert data["signal"] in {"buy", "sell", "hold", "observe"}
    assert data["strength"] in {"weak", "medium", "strong"}
    assert 0 <= data["score"] <= 100
    assert data["summary"]
    assert data["reasons"]
    assert data["input_snapshot"] is not None
    assert data["disclaimer"]


async def test_run_single_stock_backtest_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    sync_data = await _sync_mock_candles(
        async_client,
        auth_headers,
        symbol="AAPL",
        market="US",
        limit=80,
    )
    start_date, end_date = _date_range_from_sync(sync_data)

    response = await async_client.post(
        f"{API_PREFIX}/backtests",
        json={
            "symbol": "AAPL",
            "market": "US",
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": "1d",
            "initial_cash": "100000",
            "position_size_ratio": 1,
            "adjust_type": "none",
            "source": "mock",
            "min_required_candles": 60,
            "enforce_data_quality": True,
            "include_trades": True,
            "include_daily_equity": True,
            "include_signal_snapshots": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["start_date"] == start_date
    assert data["end_date"] == end_date
    assert data["status"] == "available"
    assert data["summary"]
    assert data["metrics"] is not None
    assert float(data["metrics"]["initial_cash"]) > 0
    assert float(data["metrics"]["final_equity"]) >= 0
    assert data["input_snapshot"] is not None
    assert data["input_snapshot"]["source"] == "mock"
    assert data["daily_equity"]
    assert data["disclaimer"]


async def test_run_single_stock_backtest_without_data_returns_unavailable(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/backtests",
        json={
            "symbol": "AAPL",
            "market": "US",
            "start_date": "2024-01-01",
            "end_date": "2024-03-31",
            "timeframe": "1d",
            "initial_cash": "100000",
            "position_size_ratio": 1,
            "adjust_type": "none",
            "source": "mock",
            "min_required_candles": 60,
            "enforce_data_quality": True,
            "include_trades": True,
            "include_daily_equity": True,
            "include_signal_snapshots": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["status"] == "unavailable"
    assert data["unavailable_reason"] in {"no_data", "insufficient_data", "data_error"}
    assert data["metrics"] is None
    assert data["trades"] == []
    assert data["daily_equity"] == []
    assert data["disclaimer"]


async def test_run_single_stock_backtest_invalid_date_range_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/backtests",
        json={
            "symbol": "AAPL",
            "market": "US",
            "start_date": "2024-03-31",
            "end_date": "2024-01-01",
            "timeframe": "1d",
            "initial_cash": "100000",
            "position_size_ratio": 1,
            "adjust_type": "none",
            "source": "mock",
            "min_required_candles": 60,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_run_portfolio_backtest_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    aapl_sync = await _sync_mock_candles(
        async_client,
        auth_headers,
        symbol="AAPL",
        market="US",
        limit=80,
    )
    await _sync_mock_candles(
        async_client,
        auth_headers,
        symbol="TSLA",
        market="US",
        limit=80,
    )
    start_date, end_date = _date_range_from_sync(aapl_sync)

    response = await async_client.post(
        f"{API_PREFIX}/portfolio-backtests",
        json={
            "assets": [
                {
                    "symbol": "AAPL",
                    "market": "US",
                    "target_weight": "0.5",
                },
                {
                    "symbol": "TSLA",
                    "market": "US",
                    "target_weight": "0.5",
                },
            ],
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": "1d",
            "initial_cash": "100000",
            "cash_deploy_ratio": 1,
            "rebalance_frequency": "monthly",
            "adjust_type": "none",
            "source": "mock",
            "min_required_candles": 60,
            "enforce_data_quality": True,
            "include_trades": True,
            "include_daily_equity": True,
            "include_position_snapshots": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["status"] == "available"
    assert len(data["assets"]) == 2
    assert data["summary"]
    assert data["metrics"] is not None
    assert float(data["metrics"]["initial_cash"]) > 0
    assert float(data["metrics"]["final_equity"]) >= 0
    assert data["input_snapshot"] is not None
    assert data["input_snapshot"]["source"] == "mock"
    assert data["daily_equity"]
    assert data["disclaimer"]


async def test_run_portfolio_backtest_invalid_weights_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/portfolio-backtests",
        json={
            "assets": [
                {
                    "symbol": "AAPL",
                    "market": "US",
                    "target_weight": "0.7",
                },
                {
                    "symbol": "MSFT",
                    "market": "US",
                    "target_weight": "0.7",
                },
            ],
            "start_date": "2024-01-01",
            "end_date": "2024-03-31",
            "timeframe": "1d",
            "initial_cash": "100000",
            "cash_deploy_ratio": 1,
            "rebalance_frequency": "monthly",
            "adjust_type": "none",
            "source": "mock",
            "min_required_candles": 60,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_run_stock_candidates_manual_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(
        async_client,
        auth_headers,
        symbol="AAPL",
        market="US",
        limit=80,
    )
    await _sync_mock_candles(
        async_client,
        auth_headers,
        symbol="TSLA",
        market="US",
        limit=80,
    )

    response = await async_client.post(
        f"{API_PREFIX}/stock-candidates",
        json={
            "universe_source": "manual",
            "symbols": [
                {
                    "symbol": "AAPL",
                    "market": "US",
                },
                {
                    "symbol": "TSLA",
                    "market": "US",
                },
            ],
            "top_n": 2,
            "timeframe": "1d",
            "limit": 80,
            "min_required_candles": 60,
            "adjust_type": "none",
            "source": "mock",
            "enforce_data_quality": True,
            "include_excluded": True,
            "include_score_breakdown": True,
            "include_strategy_signal": True,
            "include_data_quality": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["status"] == "available"
    assert data["summary"]
    assert len(data["candidates"]) >= 1
    assert data["input_snapshot"] is not None
    assert data["input_snapshot"]["universe_source"] == "manual"
    assert data["input_snapshot"]["requested_symbol_count"] == 2
    assert data["input_snapshot"]["source"] == "mock"
    assert data["disclaimer"]

    first_candidate = data["candidates"][0]
    assert first_candidate["symbol"] in {"AAPL", "TSLA"}
    assert first_candidate["market"] == "US"
    assert first_candidate["decision"] == "candidate"
    assert 0 <= first_candidate["score"] <= 100
    assert first_candidate["grade"] in {"A", "B", "C", "D"}
    assert first_candidate["score_breakdown"] is not None
    assert first_candidate["strategy_signal"] is not None
    assert first_candidate["data_quality"] is not None


async def test_run_stock_candidates_manual_empty_symbols_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/stock-candidates",
        json={
            "universe_source": "manual",
            "symbols": [],
            "top_n": 2,
            "timeframe": "1d",
            "limit": 80,
            "min_required_candles": 60,
            "adjust_type": "none",
            "source": "mock",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_run_stock_candidates_duplicate_symbols_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/stock-candidates",
        json={
            "universe_source": "manual",
            "symbols": [
                {
                    "symbol": "AAPL",
                    "market": "US",
                },
                {
                    "symbol": "aapl",
                    "market": "us",
                },
            ],
            "top_n": 2,
            "timeframe": "1d",
            "limit": 80,
            "min_required_candles": 60,
            "adjust_type": "none",
            "source": "mock",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
