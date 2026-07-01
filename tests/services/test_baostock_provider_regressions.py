from __future__ import annotations

from types import SimpleNamespace

from app.schemas.market_data import MarketCandleQuery
from app.services.market_providers.baostock import BaoStockProvider


class _LoginResult:
    error_code = "0"
    error_msg = ""


class _QueryResult:
    error_code = "0"
    error_msg = ""
    fields = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adjustflag",
        "tradestatus",
    ]

    def __init__(self, rows: list[list[str]]) -> None:
        self.rows = rows
        self.index = -1

    def next(self) -> bool:
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self) -> list[str]:
        return self.rows[self.index]


class _SymbolResult:
    error_code = "0"
    error_msg = ""
    fields = ["code", "code_name", "ipoDate", "outDate", "type", "status"]

    def __init__(self, row: list[str]) -> None:
        self.row = row
        self.consumed = False

    def next(self) -> bool:
        if self.consumed:
            return False
        self.consumed = True
        return True

    def get_row_data(self) -> list[str]:
        return self.row


async def test_baostock_candles_fall_back_to_full_history_when_recent_window_empty(
    monkeypatch,
) -> None:
    calls: list[dict] = []
    history_rows = [
        ["2019-12-30", "sz.000018", "1", "1.1", "0.9", "1.0", "100", "1000", "3", "1"],
        ["2019-12-31", "sz.000018", "1", "1.2", "0.9", "1.1", "110", "1100", "3", "1"],
        ["2020-01-06", "sz.000018", "1.1", "1.3", "1.0", "1.2", "120", "1200", "3", "1"],
    ]

    def query_history_k_data_plus(_code, _fields, **kwargs):
        calls.append(kwargs)
        return _QueryResult([] if len(calls) == 1 else history_rows)

    fake_bs = SimpleNamespace(
        login=lambda: _LoginResult(),
        logout=lambda: None,
        query_history_k_data_plus=query_history_k_data_plus,
    )
    monkeypatch.setitem(__import__("sys").modules, "baostock", fake_bs)

    candles = await BaoStockProvider().get_candles(
        MarketCandleQuery(
            symbol="000018",
            market="CN",
            timeframe="1d",
            limit=2,
            adjust_type="none",
        )
    )

    assert len(calls) == 2
    assert calls[1]["start_date"] == "1990-01-01"
    assert len(candles) == 2
    assert candles[0].candle_time.date().isoformat() == "2019-12-31"
    assert candles[-1].candle_time.date().isoformat() == "2020-01-06"


async def test_baostock_marks_delisted_symbol_inactive(monkeypatch) -> None:
    fake_bs = SimpleNamespace(
        login=lambda: _LoginResult(),
        logout=lambda: None,
        query_stock_basic=lambda code: _SymbolResult(
            [code, "神城A退", "1992-06-16", "2020-01-07", "1", "0"]
        ),
    )
    monkeypatch.setitem(__import__("sys").modules, "baostock", fake_bs)

    symbol = await BaoStockProvider().get_symbol(symbol="000018", market="CN")

    assert symbol.list_status == "0"
    assert symbol.is_active is False
    assert symbol.raw_payload["outDate"] == "2020-01-07"
