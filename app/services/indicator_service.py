from app.schemas.stock_analysis import IndicatorSnapshot, MarketSnapshot


class IndicatorService:
    """Calculate simple stage-five indicators from a market snapshot."""

    def calculate(self, market_snapshot: MarketSnapshot) -> IndicatorSnapshot:
        price_change = round(
            market_snapshot.latest_price - market_snapshot.previous_close,
            4,
        )
        price_change_percent = self._safe_percent(
            numerator=price_change,
            denominator=market_snapshot.previous_close,
        )

        moving_average_5 = self._mock_moving_average(
            latest_price=market_snapshot.latest_price,
            previous_close=market_snapshot.previous_close,
            weight=0.6,
        )
        moving_average_20 = self._mock_moving_average(
            latest_price=market_snapshot.latest_price,
            previous_close=market_snapshot.previous_close,
            weight=0.35,
        )

        volatility_ratio = self._safe_percent(
            numerator=market_snapshot.high_price - market_snapshot.low_price,
            denominator=market_snapshot.previous_close,
        )

        volatility_level = self._classify_volatility(volatility_ratio)
        trend = self._classify_trend(
            latest_price=market_snapshot.latest_price,
            moving_average_5=moving_average_5,
            moving_average_20=moving_average_20,
            price_change_percent=price_change_percent,
        )

        return IndicatorSnapshot(
            price_change=price_change,
            price_change_percent=price_change_percent,
            moving_average_5=moving_average_5,
            moving_average_20=moving_average_20,
            volatility_level=volatility_level,
            trend=trend,
        )

    def _mock_moving_average(
        self,
        latest_price: float,
        previous_close: float,
        weight: float,
    ) -> float:
        return round(latest_price * weight + previous_close * (1 - weight), 4)

    def _safe_percent(self, numerator: float, denominator: float) -> float:
        if denominator == 0:
            return 0.0
        return round(numerator / denominator * 100, 4)

    def _classify_volatility(self, volatility_ratio: float) -> str:
        if volatility_ratio >= 5:
            return "high"
        if volatility_ratio >= 2:
            return "medium"
        return "low"

    def _classify_trend(
        self,
        latest_price: float,
        moving_average_5: float,
        moving_average_20: float,
        price_change_percent: float,
    ) -> str:
        if latest_price > moving_average_5 > moving_average_20 and price_change_percent > 0:
            return "bullish"
        if latest_price < moving_average_5 < moving_average_20 and price_change_percent < 0:
            return "bearish"
        return "neutral"