"""行情、数据质量、技术指标和策略信号 API 测试。

测试环境使用 mock provider，重点验证 API 链路和响应结构，
不依赖真实行情实时波动。
"""

from httpx import AsyncClient


API_PREFIX = "/api/v1"


async def _sync_mock_candles(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    symbol: str = "AAPL",
    market: str = "US",
    limit: int = 40,
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
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["synced"] is True
    assert body["data"]["synced_count"] == limit
    assert body["data"]["source"] == "mock"

    return body["data"]


async def test_search_stocks_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/market/stocks/search",
        params={"keyword": "AAPL", "market": "US"},
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert len(body["data"]) >= 1
    assert body["data"][0]["symbol"] == "AAPL"
    assert body["data"][0]["market"] == "US"


async def test_get_stock_quote_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/market/stocks/aapl/quote",
        params={"market": "US"},
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["currency"] == "USD"
    assert data["latest_price"] > 0
    assert data["source"] == "mock"


async def test_get_stock_quote_unknown_symbol_returns_404(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/market/stocks/UNKNOWN/quote",
        params={"market": "US"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == 10004


async def test_get_stock_candles_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/market/stocks/AAPL/candles",
        params={"market": "US", "timeframe": "1d", "limit": 5},
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["timeframe"] == "1d"
    assert data["limit"] == 5
    assert len(data["candles"]) == 5
    assert data["source"] == "mock"


async def test_get_market_indicators_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/market/stocks/AAPL/indicators",
        params={"market": "US"},
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["price_change"] != 0
    assert data["volatility_level"] in {"low", "medium", "high"}
    assert data["trend"] in {"bullish", "bearish", "neutral"}


async def test_get_market_overview_basic_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/market/stocks/AAPL/overview",
        params={"market": "US", "timeframe": "1d", "limit": 5},
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["quote"]["symbol"] == "AAPL"
    assert data["indicators"]["symbol"] == "AAPL"
    assert len(data["candles"]) == 5
    assert data["technical_indicators"] is None
    assert data["data_quality"] is None
    assert data["sync_status"] is None
    assert data["strategy_signal"] is None


async def test_sync_market_symbol_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/market-sync/symbols/AAPL",
        params={"market": "US"},
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["source"] == "mock"
    assert data["synced"] is True


async def test_sync_market_symbol_pool_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/market-sync/symbol-pool",
        params={
            "market": "US",
            "provider": "mock",
            "limit": 2,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["status"] == "success"
    assert data["provider"] == "mock"
    assert data["market"] == "US"
    assert data["fetched_count"] == 2
    assert data["source_inserted"] == 2
    assert data["canonical_inserted"] == 2


async def test_sync_stock_candles_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    data = await _sync_mock_candles(
        async_client,
        auth_headers,
        symbol="AAPL",
        market="US",
        limit=40,
    )

    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["timeframe"] == "1d"
    assert data["adjust_type"] == "none"
    assert data["first_candle_time"] is not None
    assert data["last_candle_time"] is not None


async def test_get_market_data_quality_report_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(async_client, auth_headers, limit=40)

    response = await async_client.get(
        f"{API_PREFIX}/market-data-quality/stocks/AAPL/report",
        params={
            "market": "US",
            "timeframe": "1d",
            "limit": 40,
            "adjust_type": "none",
            "source": "mock",
            "min_required": 35,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["source"] == "mock"
    assert data["candle_count"] == 40
    assert data["is_empty"] is False
    assert data["is_enough"] is True


async def test_list_market_data_sync_statuses_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(async_client, auth_headers, limit=40)

    response = await async_client.get(
        f"{API_PREFIX}/market-data-quality/sync-statuses",
        params={
            "symbol": "AAPL",
            "market": "US",
            "timeframe": "1d",
            "source": "mock",
            "adjust_type": "none",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["source"] == "mock"
    assert data[0]["candle_count"] == 40
    assert data[0]["status"] in {"success", "partial"}


async def test_list_market_data_sync_logs_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(async_client, auth_headers, limit=40)

    response = await async_client.get(
        f"{API_PREFIX}/market-data-quality/sync-logs",
        params={
            "symbol": "AAPL",
            "market": "US",
            "timeframe": "1d",
            "source": "mock",
            "adjust_type": "none",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["source"] == "mock"
    assert data[0]["fetched_count"] == 40
    assert data[0]["saved_count"] == 40
    assert data[0]["status"] in {"success", "partial"}


async def test_get_technical_indicator_summary_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(async_client, auth_headers, limit=40)

    response = await async_client.get(
        f"{API_PREFIX}/technical-indicators/stocks/AAPL/summary",
        params={
            "market": "US",
            "timeframe": "1d",
            "limit": 40,
            "adjust_type": "none",
            "source": "mock",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["source"] == "mock"
    assert data["candle_count"] == 40
    assert data["summary"]["moving_average"]
    assert data["summary"]["rsi"]
    assert data["summary"]["macd"]
    assert data["summary"]["volatility"]
    assert data["summary"]["momentum"]
    assert data["summary"]["volume_factor"]


async def test_get_technical_indicator_ma_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(async_client, auth_headers, limit=40)

    response = await async_client.get(
        f"{API_PREFIX}/technical-indicators/stocks/AAPL/ma",
        params={
            "market": "US",
            "timeframe": "1d",
            "limit": 40,
            "source": "mock",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["ma5"] is not None
    assert data["ma20"] is not None
    assert data["trend"] in {"bullish", "bearish", "neutral"}


async def test_get_strategy_signal_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(async_client, auth_headers, limit=40)

    response = await async_client.get(
        f"{API_PREFIX}/strategy-signals/stocks/AAPL",
        params={
            "market": "US",
            "timeframe": "1d",
            "limit": 40,
            "adjust_type": "none",
            "source": "mock",
            "include_detail": True,
            "min_required": 35,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert data["status"] == "available"
    assert data["signal"] in {"buy", "sell", "hold", "observe"}
    assert 0 <= data["score"] <= 100
    assert data["disclaimer"]
    assert data["input_snapshot"] is not None


async def test_get_market_overview_with_quality_indicators_and_signal_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _sync_mock_candles(async_client, auth_headers, limit=40)

    response = await async_client.get(
        f"{API_PREFIX}/market/stocks/AAPL/overview",
        params={
            "market": "US",
            "timeframe": "1d",
            "limit": 5,
            "include_technical_indicators": True,
            "technical_indicator_limit": 40,
            "technical_indicator_source": "mock",
            "include_data_quality": True,
            "include_sync_status": True,
            "data_quality_source": "mock",
            "data_quality_min_required": 35,
            "include_strategy_signal": True,
            "strategy_signal_limit": 40,
            "strategy_signal_source": "mock",
            "strategy_signal_min_required": 35,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["quote"]["symbol"] == "AAPL"
    assert len(data["candles"]) == 5
    assert data["technical_indicators"]["symbol"] == "AAPL"
    assert data["data_quality"]["symbol"] == "AAPL"
    assert data["sync_status"]["symbol"] == "AAPL"
    assert data["strategy_signal"]["symbol"] == "AAPL"
