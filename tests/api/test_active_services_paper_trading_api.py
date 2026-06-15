"""主动服务与纸面交易 API 测试。

覆盖每日简报、量化提醒和纸面交易接口。
测试只验证虚拟账户和模拟数据流，不连接券商、不真实下单。
"""

from httpx import AsyncClient


API_PREFIX = "/api/v1"


async def _create_paper_trading_account(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    name: str = "测试纸面交易账户",
) -> dict:
    response = await async_client.post(
        f"{API_PREFIX}/paper-trading/accounts",
        json={
            "name": name,
            "initial_cash": "100000",
            "currency": "CNY",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    return response.json()["data"]


async def _create_quant_alert_rule(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> dict:
    response = await async_client.post(
        f"{API_PREFIX}/quant-alerts/rules",
        json={
            "name": "AAPL 策略信号提醒",
            "rule_type": "strategy_signal",
            "market": "US",
            "symbol": "AAPL",
            "severity": "warning",
            "cooldown_minutes": 0,
            "enabled_notification": False,
            "description": "测试用量化提醒规则",
            "rule_config": {},
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    return response.json()["data"]


async def test_generate_daily_report_empty_watchlist_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/daily-reports/generate",
        json={
            "use_ai": False,
            "force_rebuild": True,
            "notify": False,
            "include_candidates": False,
            "include_user_profile": False,
            "include_relevant_memories": False,
            "max_watchlist_items": 5,
            "max_candidate_items": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    data = body["data"]
    report = data["report"]

    assert body["code"] == 0
    assert data["created"] is True
    assert data["notification_created"] is False
    assert data["ai_used"] is False
    assert report["status"] == "failed"
    assert report["source"] == "api"
    assert report["unavailable_reason"] == "empty_watchlist"
    assert report["input_snapshot"]["watchlist_count"] == 0
    assert report["input_snapshot"]["use_ai"] is False
    assert report["summary"] == "当前用户没有自选股，暂时无法生成每日简报。"
    assert report["disclaimer"]


async def test_get_today_daily_report_after_generation(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    generate_response = await async_client.post(
        f"{API_PREFIX}/daily-reports/generate",
        json={
            "use_ai": False,
            "force_rebuild": True,
            "notify": False,
            "include_candidates": False,
            "include_user_profile": False,
            "include_relevant_memories": False,
        },
        headers=auth_headers,
    )
    assert generate_response.status_code == 200

    response = await async_client.get(
        f"{API_PREFIX}/daily-reports/today",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["exists"] is True
    assert data["report"]["status"] == "failed"
    assert data["report"]["unavailable_reason"] == "empty_watchlist"


async def test_list_and_get_daily_report_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    generate_response = await async_client.post(
        f"{API_PREFIX}/daily-reports/generate",
        json={
            "use_ai": False,
            "force_rebuild": True,
            "notify": False,
            "include_candidates": False,
            "include_user_profile": False,
            "include_relevant_memories": False,
        },
        headers=auth_headers,
    )
    assert generate_response.status_code == 200

    report_id = generate_response.json()["data"]["report"]["id"]

    list_response = await async_client.get(
        f"{API_PREFIX}/daily-reports",
        params={
            "status": "failed",
            "source": "api",
            "limit": 20,
            "offset": 0,
        },
        headers=auth_headers,
    )

    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == report_id

    detail_response = await async_client.get(
        f"{API_PREFIX}/daily-reports/{report_id}",
        headers=auth_headers,
    )

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["id"] == report_id
    assert detail["status"] == "failed"
    assert detail["unavailable_reason"] == "empty_watchlist"


async def test_create_list_update_and_deactivate_quant_alert_rule(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    rule = await _create_quant_alert_rule(async_client, auth_headers)
    rule_id = rule["id"]

    assert rule["name"] == "AAPL 策略信号提醒"
    assert rule["rule_type"] == "strategy_signal"
    assert rule["status"] == "active"
    assert rule["market"] == "US"
    assert rule["symbol"] == "AAPL"

    list_response = await async_client.get(
        f"{API_PREFIX}/quant-alerts/rules",
        params={
            "rule_type": "strategy_signal",
            "status": "active",
            "market": "US",
            "symbol": "AAPL",
        },
        headers=auth_headers,
    )

    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == rule_id

    get_response = await async_client.get(
        f"{API_PREFIX}/quant-alerts/rules/{rule_id}",
        headers=auth_headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["data"]["id"] == rule_id

    update_response = await async_client.patch(
        f"{API_PREFIX}/quant-alerts/rules/{rule_id}",
        json={
            "name": "AAPL 策略信号提醒-更新",
            "severity": "critical",
            "enabled_notification": False,
            "description": "更新后的测试规则",
        },
        headers=auth_headers,
    )

    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["name"] == "AAPL 策略信号提醒-更新"
    assert updated["severity"] == "critical"
    assert updated["description"] == "更新后的测试规则"

    deactivate_response = await async_client.post(
        f"{API_PREFIX}/quant-alerts/rules/{rule_id}/deactivate",
        headers=auth_headers,
    )

    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["data"]["status"] == "inactive"


async def test_create_quant_alert_threshold_rule_without_threshold_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/quant-alerts/rules",
        json={
            "name": "非法价格提醒",
            "rule_type": "price_change",
            "market": "US",
            "symbol": "AAPL",
            "severity": "warning",
            "cooldown_minutes": 0,
            "enabled_notification": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_scan_quant_alerts_without_active_rules_returns_skipped(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/quant-alerts/scan",
        json={
            "symbols": ["AAPL"],
            "market": "US",
            "rule_types": ["strategy_signal"],
            "notify": False,
            "force": True,
            "max_watchlist_items": 10,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["status"] == "skipped"
    assert data["unavailable_reason"] == "no_active_rules"
    assert data["scanned_count"] == 0
    assert data["triggered_count"] == 0
    assert data["notification_count"] == 0
    assert data["input_snapshot"]["source"] == "api"
    assert data["input_snapshot"]["rule_type_count"] == 0
    assert data["disclaimer"]


async def test_list_quant_alert_events_empty_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/quant-alerts/events",
        params={
            "status": "triggered",
            "limit": 20,
            "offset": 0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


async def test_create_list_and_get_paper_trading_account_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    account = await _create_paper_trading_account(async_client, auth_headers)
    account_id = account["id"]

    assert account["name"] == "测试纸面交易账户"
    assert account["initial_cash"] == "100000.0000"
    assert account["cash_balance"] == "100000.0000"
    assert account["currency"] == "CNY"
    assert account["status"] == "active"
    assert account["disclaimer"]

    list_response = await async_client.get(
        f"{API_PREFIX}/paper-trading/accounts",
        params={
            "limit": 20,
            "offset": 0,
        },
        headers=auth_headers,
    )

    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == account_id

    detail_response = await async_client.get(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}",
        headers=auth_headers,
    )

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["account"]["id"] == account_id
    assert detail["account"]["status"] == "active"
    assert detail["config"] is not None
    assert detail["positions"] == []


async def test_update_paper_trading_account_and_config_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    account = await _create_paper_trading_account(async_client, auth_headers)
    account_id = account["id"]

    update_account_response = await async_client.patch(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}",
        json={
            "name": "更新后的纸面交易账户",
            "status": "paused",
        },
        headers=auth_headers,
    )

    assert update_account_response.status_code == 200
    updated_account = update_account_response.json()["data"]
    assert updated_account["name"] == "更新后的纸面交易账户"
    assert updated_account["status"] == "paused"

    config_response = await async_client.get(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/config",
        headers=auth_headers,
    )

    assert config_response.status_code == 200
    config = config_response.json()["data"]
    assert config["account_id"] == account_id
    assert config["is_enabled"] is True

    update_config_response = await async_client.patch(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/config",
        json={
            "is_enabled": False,
            "max_symbols_per_tick": 10,
            "allow_buy": True,
            "allow_sell": True,
            "notes": "测试关闭配置",
        },
        headers=auth_headers,
    )

    assert update_config_response.status_code == 200
    updated_config = update_config_response.json()["data"]
    assert updated_config["account_id"] == account_id
    assert updated_config["is_enabled"] is False
    assert updated_config["max_symbols_per_tick"] == 10
    assert updated_config["notes"] == "测试关闭配置"
    assert updated_config["disclaimer"]


async def test_paper_trading_tick_skipped_when_config_disabled(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    account = await _create_paper_trading_account(async_client, auth_headers)
    account_id = account["id"]

    update_config_response = await async_client.patch(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/config",
        json={
            "is_enabled": False,
            "max_symbols_per_tick": 10,
            "allow_buy": True,
            "allow_sell": True,
        },
        headers=auth_headers,
    )
    assert update_config_response.status_code == 200

    tick_response = await async_client.post(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/tick",
        json={
            "force": True,
            "max_symbols": 10,
            "notify": False,
        },
        headers=auth_headers,
    )

    assert tick_response.status_code == 200

    tick = tick_response.json()["data"]
    assert tick["status"] == "skipped"
    assert tick["unavailable_reason"] == "tick_failed"
    assert tick["account"]["id"] == account_id
    assert tick["run_id"] is not None
    assert tick["equity_snapshot"] is None
    assert tick["input_snapshot"]["source"] == "api"
    assert tick["warnings"]
    assert tick["disclaimer"]

    runs_response = await async_client.get(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/runs",
        headers=auth_headers,
    )

    assert runs_response.status_code == 200
    runs = runs_response.json()["data"]
    assert runs["total"] == 1
    assert runs["items"][0]["id"] == tick["run_id"]
    assert runs["items"][0]["status"] == "skipped"

    run_detail_response = await async_client.get(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/runs/{tick['run_id']}",
        headers=auth_headers,
    )

    assert run_detail_response.status_code == 200
    run_detail = run_detail_response.json()["data"]
    assert run_detail["id"] == tick["run_id"]
    assert run_detail["status"] == "skipped"
    assert run_detail["account_config_snapshot"]["is_enabled"] is False
    assert run_detail["request_snapshot"]["source"] == "api"


async def test_paper_trading_resource_lists_are_empty_for_new_account(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    account = await _create_paper_trading_account(async_client, auth_headers)
    account_id = account["id"]

    endpoints = [
        "positions",
        "orders",
        "trades",
        "equity",
    ]

    for endpoint in endpoints:
        response = await async_client.get(
            f"{API_PREFIX}/paper-trading/accounts/{account_id}/{endpoint}",
            params={
                "limit": 20,
                "offset": 0,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200

        data = response.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []


async def test_paper_trading_invalid_account_update_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    account = await _create_paper_trading_account(async_client, auth_headers)
    account_id = account["id"]

    response = await async_client.patch(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}",
        json={
            "status": "unknown",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
