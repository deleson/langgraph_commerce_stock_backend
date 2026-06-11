from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.stock_candidate import (
    StockCandidateItem,
    StockCandidateRequest,
    StockCandidateStrategySignalSnapshot,
    StockCandidateSymbol,
)
from app.services.stock_candidate_data_service import (
    StockCandidateDataItem,
    StockCandidateDataService,
    StockCandidateUniverseItem,
)
from app.services.stock_candidate_query_service import StockCandidateQueryService
from app.services.stock_candidate_scoring_service import StockCandidateScoringService
from tests.fixtures.quant_data import (
    build_downtrend_candles,
    build_flat_candles,
    build_market_symbol_payload,
    build_uptrend_candles,
    persist_quant_symbol_and_candles,
)


def _candidate_request(
    symbols: list[str],
    *,
    top_n: int = 3,
    include_excluded: bool = True,
    include_score_breakdown: bool = True,
    include_strategy_signal: bool = True,
    include_data_quality: bool = True,
) -> StockCandidateRequest:
    return StockCandidateRequest(
        universe_source="manual",
        symbols=[
            StockCandidateSymbol(
                symbol=symbol,
                market="US",
            )
            for symbol in symbols
        ],
        top_n=top_n,
        timeframe="1d",
        limit=40,
        min_required_candles=35,
        adjust_type="none",
        source="mock",
        enforce_data_quality=True,
        data_quality_stale_after_days=None,
        include_excluded=include_excluded,
        include_score_breakdown=include_score_breakdown,
        include_strategy_signal=include_strategy_signal,
        include_data_quality=include_data_quality,
    )


async def _persist_candidate_candles(db_session, symbol: str, candles) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol=symbol),
        candle_payloads=candles,
    )


async def _load_candidate_data_items(
    db_session,
    symbols: list[str],
) -> list[StockCandidateDataItem]:
    candidates = [
        StockCandidateUniverseItem(
            symbol=symbol,
            market="US",
            name=f"{symbol} Candidate",
        )
        for symbol in symbols
    ]

    return await StockCandidateDataService(db_session).get_data_for_candidates(
        candidates=candidates,
        timeframe="1d",
        limit=40,
        min_required_candles=35,
        adjust_type="none",
        source="mock",
        enforce_data_quality=True,
        stale_after_days=None,
        include_strategy_signal=True,
    )


def _manual_candidate(
    *,
    symbol: str,
    score: int,
    grade: str,
    signal: str | None = None,
) -> StockCandidateItem:
    return StockCandidateItem(
        symbol=symbol,
        market="US",
        name=f"{symbol} Manual",
        decision="candidate",
        excluded_reason=None,
        rank=None,
        score=score,
        grade=grade,
        reasons=["manual candidate for ranking test"],
        risks=["manual risk for ranking test"],
        score_breakdown=None,
        data_quality=None,
        strategy_signal=(
            StockCandidateStrategySignalSnapshot(
                status="available",
                signal=signal,
                strength="strong" if signal else None,
                score=90 if signal == "buy" else 50,
                summary="manual strategy signal",
            )
            if signal
            else None
        ),
    )


def test_stock_candidate_request_validates_manual_symbols_and_limits() -> None:
    with pytest.raises(ValidationError):
        StockCandidateRequest(
            universe_source="manual",
            symbols=[],
            top_n=3,
            limit=40,
            min_required_candles=35,
        )

    with pytest.raises(ValidationError):
        StockCandidateRequest(
            universe_source="manual",
            symbols=[
                StockCandidateSymbol(symbol="AAPL", market="US"),
                StockCandidateSymbol(symbol="aapl", market="us"),
            ],
            top_n=3,
            limit=40,
            min_required_candles=35,
        )

    with pytest.raises(ValidationError):
        StockCandidateRequest(
            universe_source="manual",
            symbols=[
                StockCandidateSymbol(symbol="AAPL", market="US"),
            ],
            top_n=3,
            limit=35,
            min_required_candles=40,
        )


async def test_data_service_loads_quality_indicators_and_strategy_signal(db_session) -> None:
    await _persist_candidate_candles(
        db_session,
        "SCUP",
        build_uptrend_candles(symbol="SCUP", count=40),
    )

    items = await _load_candidate_data_items(db_session, ["SCUP"])

    assert len(items) == 1

    item = items[0]
    assert item.symbol == "SCUP"
    assert item.market == "US"
    assert item.data_quality is not None
    assert item.data_quality.is_empty is False
    assert item.data_quality.is_enough is True
    assert item.technical_indicators is not None
    assert item.strategy_signal is not None
    assert item.strategy_signal.status == "available"


async def test_score_candidate_generates_breakdown_snapshots_reasons_and_risks(db_session) -> None:
    await _persist_candidate_candles(
        db_session,
        "SCSCORE",
        build_uptrend_candles(symbol="SCSCORE", count=40),
    )

    data_item = (await _load_candidate_data_items(db_session, ["SCSCORE"]))[0]
    candidate = StockCandidateScoringService().score_candidate(
        data_item,
        risk_preference="balanced",
        include_score_breakdown=True,
        include_strategy_signal=True,
        include_data_quality=True,
    )

    assert candidate.symbol == "SCSCORE"
    assert candidate.decision == "candidate"
    assert candidate.excluded_reason is None
    assert candidate.score >= StockCandidateScoringService.MIN_CANDIDATE_SCORE
    assert candidate.grade in {"A", "B", "C"}

    assert candidate.score_breakdown is not None
    assert candidate.score_breakdown.base_score == 50
    assert candidate.score_breakdown.final_score == candidate.score
    assert candidate.score_breakdown.raw_score is not None

    expected_dimensions = {
        "data_quality",
        "trend",
        "momentum",
        "rsi",
        "macd",
        "volatility",
        "volume",
        "liquidity",
        "strategy_signal",
        "backtest_performance",
        "risk",
        "user_preference",
    }
    actual_dimensions = {
        result.dimension
        for result in candidate.score_breakdown.rule_results
    }
    assert expected_dimensions.issubset(actual_dimensions)

    component_sum = (
        candidate.score_breakdown.base_score
        + candidate.score_breakdown.data_quality_score
        + candidate.score_breakdown.trend_score
        + candidate.score_breakdown.momentum_score
        + candidate.score_breakdown.rsi_score
        + candidate.score_breakdown.macd_score
        + candidate.score_breakdown.volatility_score
        + candidate.score_breakdown.volume_score
        + candidate.score_breakdown.liquidity_score
        + candidate.score_breakdown.strategy_signal_score
        + candidate.score_breakdown.backtest_performance_score
        + candidate.score_breakdown.risk_score
        + candidate.score_breakdown.user_preference_score
    )
    assert candidate.score_breakdown.raw_score == component_sum

    assert candidate.data_quality is not None
    assert candidate.data_quality.status == "available"
    assert candidate.strategy_signal is not None
    assert candidate.strategy_signal.status == "available"
    assert candidate.reasons
    assert candidate.risks


async def test_risk_preference_changes_candidate_score(db_session) -> None:
    await _persist_candidate_candles(
        db_session,
        "SCRISK",
        build_uptrend_candles(symbol="SCRISK", count=40),
    )

    data_item = (await _load_candidate_data_items(db_session, ["SCRISK"]))[0]
    service = StockCandidateScoringService()

    balanced = service.score_candidate(
        data_item,
        risk_preference="balanced",
        include_score_breakdown=True,
    )
    aggressive = service.score_candidate(
        data_item,
        risk_preference="aggressive",
        include_score_breakdown=True,
    )
    conservative = service.score_candidate(
        data_item,
        risk_preference="conservative",
        include_score_breakdown=True,
    )

    assert balanced.score_breakdown is not None
    assert aggressive.score_breakdown is not None
    assert conservative.score_breakdown is not None

    assert balanced.score_breakdown.user_preference_score == 0
    assert aggressive.score_breakdown.user_preference_score != balanced.score_breakdown.user_preference_score
    assert conservative.score_breakdown.user_preference_score != aggressive.score_breakdown.user_preference_score


def test_unscorable_candidate_is_excluded_when_data_is_empty() -> None:
    data_item = StockCandidateDataItem(
        symbol="SCEMPTY",
        market="US",
        name="SCEMPTY Candidate",
        data_quality=MarketDataQualityReport(
            symbol="SCEMPTY",
            market="US",
            timeframe="1d",
            source="mock",
            adjust_type="none",
            candle_count=0,
            is_empty=True,
            is_enough=False,
            is_stale=False,
            errors=[],
            warnings=["empty data"],
        ),
        technical_indicators=None,
        strategy_signal=None,
        warnings=["empty data"],
        errors=[],
    )

    candidate = StockCandidateScoringService().score_candidate(
        data_item,
        include_score_breakdown=True,
        include_strategy_signal=True,
        include_data_quality=True,
    )

    assert candidate.decision == "excluded"
    assert candidate.excluded_reason is not None
    assert candidate.score == 0
    assert candidate.grade == "D"
    assert candidate.score_breakdown is None
    assert candidate.data_quality is not None
    assert candidate.data_quality.status == "unavailable"
    assert candidate.risks


def test_rank_and_filter_candidates_sorts_ranks_and_excludes_low_score_or_overflow() -> None:
    candidates = [
        _manual_candidate(symbol="SCAAA", score=80, grade="A", signal="buy"),
        _manual_candidate(symbol="SCBBB", score=70, grade="C", signal="hold"),
        _manual_candidate(symbol="SCCCC", score=70, grade="B", signal="buy"),
        _manual_candidate(symbol="SCDDD", score=40, grade="D", signal="sell"),
    ]

    ranked, excluded = StockCandidateScoringService().rank_and_filter_candidates(
        candidates,
        top_n=2,
    )

    assert [candidate.symbol for candidate in ranked] == ["SCAAA", "SCCCC"]
    assert [candidate.rank for candidate in ranked] == [1, 2]
    assert all(candidate.decision == "candidate" for candidate in ranked)

    excluded_symbols = {candidate.symbol for candidate in excluded}
    assert excluded_symbols == {"SCBBB", "SCDDD"}

    low_score = next(candidate for candidate in excluded if candidate.symbol == "SCDDD")
    overflow = next(candidate for candidate in excluded if candidate.symbol == "SCBBB")

    assert low_score.decision == "excluded"
    assert low_score.excluded_reason is not None
    assert overflow.decision == "excluded"
    assert overflow.excluded_reason is not None


async def test_scoring_service_can_score_multiple_market_conditions(db_session) -> None:
    await _persist_candidate_candles(
        db_session,
        "SCUP2",
        build_uptrend_candles(symbol="SCUP2", count=40),
    )
    await _persist_candidate_candles(
        db_session,
        "SCDOWN",
        build_downtrend_candles(symbol="SCDOWN", count=40),
    )
    await _persist_candidate_candles(
        db_session,
        "SCFLAT",
        build_flat_candles(symbol="SCFLAT", count=40),
    )

    data_items = await _load_candidate_data_items(
        db_session,
        ["SCUP2", "SCDOWN", "SCFLAT"],
    )
    scored_items = StockCandidateScoringService().score_candidates(
        data_items,
        risk_preference="balanced",
        include_score_breakdown=True,
        include_strategy_signal=True,
        include_data_quality=True,
    )

    assert len(scored_items) == 3
    assert all(item.score_breakdown is not None for item in scored_items)

    by_symbol = {item.symbol: item for item in scored_items}

    assert by_symbol["SCUP2"].score >= by_symbol["SCDOWN"].score
    assert by_symbol["SCUP2"].decision == "candidate"
    assert by_symbol["SCDOWN"].score_breakdown.risk_score <= 0
    assert by_symbol["SCFLAT"].score_breakdown.backtest_performance_score == 0


async def test_query_service_runs_manual_universe_database_chain(
    db_session,
    test_user,
) -> None:
    await _persist_candidate_candles(
        db_session,
        "SCQUP",
        build_uptrend_candles(symbol="SCQUP", count=40),
    )
    await _persist_candidate_candles(
        db_session,
        "SCQDOWN",
        build_downtrend_candles(symbol="SCQDOWN", count=40),
    )

    request = _candidate_request(
        ["SCQUP", "SCQDOWN"],
        top_n=1,
        include_excluded=True,
    )

    result = await StockCandidateQueryService(db_session).run_stock_candidates(
        request=request,
        user=test_user,
    )

    assert result.status == "available"
    assert result.unavailable_reason is None
    assert len(result.candidates) == 1
    assert result.input_snapshot is not None
    assert result.input_snapshot.universe_source == "manual"
    assert result.input_snapshot.requested_symbol_count == 2
    assert result.input_snapshot.evaluated_symbol_count == 2
    assert result.input_snapshot.candidate_count == 1
    assert result.input_snapshot.source == "mock"

    first_candidate = result.candidates[0]
    assert first_candidate.rank == 1
    assert first_candidate.decision == "candidate"
    assert first_candidate.score_breakdown is not None
    assert first_candidate.data_quality is not None
    assert first_candidate.strategy_signal is not None

    assert result.excluded
    assert result.warnings