"""数据质量专项测试。

验证空数据、数量不足、过旧、重复、非法价格和 source 隔离等场景。
数据质量门控是 AI 分析、策略信号和纸面交易的前置安全边界。
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import BadRequestException
from app.schemas.market_data import MarketProviderCandle
from app.services.market_data_quality_report_service import (
    MarketDataQualityReportService,
)
from app.services.market_data_quality_service import MarketDataQualityService
from tests.fixtures.quant_data import (
    build_candle_payload,
    build_duplicate_candle_payloads,
    build_market_symbol_payload,
    build_stale_candles,
    build_uptrend_candles,
    persist_quant_symbol_and_candles,
    quant_decimal,
)


def _provider_candle_from_payload(payload) -> MarketProviderCandle:
    return MarketProviderCandle(
        symbol=payload.symbol,
        market=payload.market,
        timeframe=payload.timeframe,
        candle_time=payload.candle_time,
        open_price=payload.open_price,
        high_price=payload.high_price,
        low_price=payload.low_price,
        close_price=payload.close_price,
        volume=payload.volume,
        amount=payload.amount,
        source=payload.source,
        is_adjusted=payload.is_adjusted,
        adjust_type=payload.adjust_type,
    )


def test_normalize_candle_quantizes_decimal_and_normalizes_time() -> None:
    service = MarketDataQualityService()

    provider_candle = MarketProviderCandle(
        symbol="qtq",
        market="US",
        timeframe="1d",
        candle_time=datetime(2024, 1, 2, 9, 30),
        open_price=Decimal("100.12345"),
        high_price=Decimal("101.98765"),
        low_price=Decimal("99.11111"),
        close_price=Decimal("100.55555"),
        volume=1_000_000,
        amount=Decimal("100555550.55555"),
        source="mock",
        is_adjusted=False,
        adjust_type="none",
    )

    normalized = service.normalize_candle(provider_candle, symbol_id=123)

    assert normalized.symbol == "QTQ"
    assert normalized.symbol_id == 123
    assert normalized.candle_time.tzinfo is not None
    assert normalized.candle_time.utcoffset().total_seconds() == 0
    assert normalized.open_price == Decimal("100.1235")
    assert normalized.high_price == Decimal("101.9877")
    assert normalized.low_price == Decimal("99.1111")
    assert normalized.close_price == Decimal("100.5556")
    assert normalized.amount == Decimal("100555550.5556")


def test_inspect_candles_empty_returns_error_result() -> None:
    service = MarketDataQualityService()

    result = service.inspect_candles(
        [],
        min_required=35,
        stale_after_days=5,
        now=datetime(2024, 2, 20, tzinfo=UTC),
    )

    assert result.candle_count == 0
    assert result.duplicate_count == 0
    assert result.is_empty is True
    assert result.is_enough is False
    assert result.is_stale is False
    assert result.errors == ["market candle data is empty"]
    assert result.warnings == []


def test_inspect_candles_not_enough_returns_warning() -> None:
    service = MarketDataQualityService()
    candles = build_uptrend_candles(symbol="QTNE", count=10)

    result = service.inspect_candles(
        candles,
        min_required=35,
        now=datetime(2024, 2, 20, tzinfo=UTC),
    )

    assert result.candle_count == 10
    assert result.is_empty is False
    assert result.is_enough is False
    assert result.is_stale is False
    assert result.errors == []
    assert result.warnings == [
        "not enough candles: required=35, actual=10",
    ]


def test_inspect_candles_stale_returns_stale_warning() -> None:
    service = MarketDataQualityService()
    candles = build_stale_candles(symbol="QTST", count=40)

    result = service.inspect_candles(
        candles,
        min_required=35,
        stale_after_days=30,
        now=datetime(2024, 2, 20, tzinfo=UTC),
    )

    assert result.candle_count == 40
    assert result.is_enough is True
    assert result.is_stale is True
    assert result.latest_candle_time == candles[-1].candle_time
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("latest candle is stale")


def test_inspect_provider_candles_removes_duplicates_and_reports_count() -> None:
    service = MarketDataQualityService()

    provider_candles = [
        _provider_candle_from_payload(payload)
        for payload in build_duplicate_candle_payloads(symbol="QTDQ")
    ]

    normalized, result = service.inspect_provider_candles(
        provider_candles,
        min_required=1,
        now=datetime(2024, 1, 20, tzinfo=UTC),
    )

    assert len(provider_candles) == 6
    assert len(normalized) == 5
    assert result.candle_count == 5
    assert result.duplicate_count == 1
    assert result.is_empty is False
    assert result.is_enough is True
    assert result.warnings == ["duplicate candles removed: duplicate_count=1"]


@pytest.mark.parametrize(
    ("update", "expected_message"),
    [
        (
            {"open_price": quant_decimal("-1")},
            "market candle price cannot be negative",
        ),
        (
            {
                "high_price": quant_decimal("90"),
                "low_price": quant_decimal("95"),
            },
            "invalid candle price range for QTBAD: high_price < low_price",
        ),
        (
            {
                "open_price": quant_decimal("120"),
                "high_price": quant_decimal("110"),
                "low_price": quant_decimal("90"),
            },
            "invalid candle open price for QTBAD: open_price outside high/low range",
        ),
        (
            {
                "close_price": quant_decimal("80"),
                "high_price": quant_decimal("110"),
                "low_price": quant_decimal("90"),
            },
            "invalid candle close price for QTBAD: close_price outside high/low range",
        ),
        (
            {"volume": -1},
            "invalid candle volume for QTBAD: volume cannot be negative",
        ),
        (
            {"amount": quant_decimal("-1")},
            "market candle amount cannot be negative",
        ),
    ],
)
def test_normalize_candle_rejects_invalid_provider_candle(
    update: dict,
    expected_message: str,
) -> None:
    service = MarketDataQualityService()

    base_payload = build_candle_payload(
        symbol="QTBAD",
        candle_time=datetime(2024, 1, 2, tzinfo=UTC),
        open_price=quant_decimal("100"),
        high_price=quant_decimal("110"),
        low_price=quant_decimal("90"),
        close_price=quant_decimal("105"),
        volume=1_000_000,
        amount=quant_decimal("105000000"),
    )

    provider_payload = base_payload.model_copy(update=update)
    provider_candle = _provider_candle_from_payload(provider_payload)

    with pytest.raises(BadRequestException) as exc_info:
        service.normalize_candle(provider_candle)

    assert exc_info.value.message == expected_message


def test_inspect_candles_rejects_invalid_min_required() -> None:
    service = MarketDataQualityService()

    with pytest.raises(BadRequestException) as exc_info:
        service.inspect_candles([], min_required=0)

    assert exc_info.value.message == "min_required must be greater than 0"


def test_inspect_candles_rejects_invalid_stale_after_days() -> None:
    service = MarketDataQualityService()

    with pytest.raises(BadRequestException) as exc_info:
        service.inspect_candles(
            build_uptrend_candles(symbol="QTST", count=5),
            stale_after_days=0,
        )

    assert exc_info.value.message == "stale_after_days must be greater than 0"


async def test_quality_report_returns_empty_when_no_candles(db_session) -> None:
    service = MarketDataQualityReportService(db_session)

    report = await service.get_quality_report(
        symbol="QTEMPTY",
        market="US",
        timeframe="1d",
        limit=40,
        source="mock",
        adjust_type="none",
        min_required=35,
    )

    assert report.symbol == "QTEMPTY"
    assert report.market == "US"
    assert report.source == "mock"
    assert report.candle_count == 0
    assert report.duplicate_count == 0
    assert report.is_empty is True
    assert report.is_enough is False
    assert report.is_stale is False
    assert report.errors == ["market candles not found for US:QTEMPTY"]
    assert report.warnings == []


async def test_quality_report_returns_enough_for_valid_candles(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTOK"),
        candle_payloads=build_uptrend_candles(symbol="QTOK", count=40),
    )

    service = MarketDataQualityReportService(db_session)

    report = await service.get_quality_report(
        symbol="qtok",
        market="US",
        timeframe="1d",
        limit=40,
        source="mock",
        adjust_type="none",
        min_required=35,
        stale_after_days=3650,
    )

    assert report.symbol == "QTOK"
    assert report.market == "US"
    assert report.source == "mock"
    assert report.adjust_type == "none"
    assert report.candle_count == 40
    assert report.duplicate_count == 0
    assert report.is_empty is False
    assert report.is_enough is True
    assert report.is_stale is False
    assert report.earliest_candle_time is not None
    assert report.latest_candle_time is not None
    assert report.errors == []
    assert report.warnings == []


async def test_quality_report_returns_not_enough_warning(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTNE"),
        candle_payloads=build_uptrend_candles(symbol="QTNE", count=10),
    )

    service = MarketDataQualityReportService(db_session)

    report = await service.get_quality_report(
        symbol="QTNE",
        market="US",
        timeframe="1d",
        limit=40,
        source="mock",
        adjust_type="none",
        min_required=35,
    )

    assert report.candle_count == 10
    assert report.is_empty is False
    assert report.is_enough is False
    assert report.is_stale is False
    assert report.errors == []
    assert report.warnings == [
        "not enough candles: required=35, actual=10",
    ]


async def test_quality_report_returns_stale_warning(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTRST"),
        candle_payloads=build_stale_candles(symbol="QTRST", count=40),
    )

    service = MarketDataQualityReportService(db_session)

    report = await service.get_quality_report(
        symbol="QTRST",
        market="US",
        timeframe="1d",
        limit=40,
        source="mock",
        adjust_type="none",
        min_required=35,
        stale_after_days=30,
    )

    assert report.candle_count == 40
    assert report.is_empty is False
    assert report.is_enough is True
    assert report.is_stale is True
    assert len(report.warnings) == 1
    assert report.warnings[0].startswith("latest candle is stale")


async def test_quality_report_filters_by_source(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTSRC"),
        candle_payloads=build_uptrend_candles(symbol="QTSRC", count=40),
    )

    service = MarketDataQualityReportService(db_session)

    report = await service.get_quality_report(
        symbol="QTSRC",
        market="US",
        timeframe="1d",
        limit=40,
        source="tushare",
        adjust_type="none",
        min_required=35,
    )

    assert report.symbol == "QTSRC"
    assert report.source == "tushare"
    assert report.candle_count == 0
    assert report.is_empty is True
    assert report.is_enough is False
    assert report.errors == ["market candles not found for US:QTSRC"]
