"""早期轻量指标服务。

这个服务用于 Market Overview 的基础价格指标，输入是一条行情快照，不依赖完整
历史 K 线。更完整的 MA、RSI、MACD、波动率、动量等计算在
TechnicalIndicatorService 中完成。
"""

from app.schemas.stock_analysis import IndicatorSnapshot, MarketSnapshot


class IndicatorService:
    """基于单个行情快照计算轻量指标。"""

    def calculate(self, market_snapshot: MarketSnapshot) -> IndicatorSnapshot:
        """计算涨跌幅、模拟均线、波动等级和趋势方向。"""

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
        """在缺少完整历史 K 线时，用当前价和昨收构造演示型均线。"""

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
        """根据价格、短均线、长均线和涨跌幅给出轻量趋势标签。"""

        if latest_price > moving_average_5 > moving_average_20 and price_change_percent > 0:
            return "bullish"
        if latest_price < moving_average_5 < moving_average_20 and price_change_percent < 0:
            return "bearish"
        return "neutral"
