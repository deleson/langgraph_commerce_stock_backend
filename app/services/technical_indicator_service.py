import pandas as pd

from app.core.exceptions import BadRequestException
from app.schemas.technical_indicator import MovingAverageSnapshot, RsiSnapshot


class TechnicalIndicatorService:
    def calculate_moving_average(
        self,
        df: pd.DataFrame,
    ) -> MovingAverageSnapshot:
        self._validate_price_dataframe(df)

        close = df["close_price"]

        ma5 = self._latest_rolling_mean(close, window=5)
        ma10 = self._latest_rolling_mean(close, window=10)
        ma20 = self._latest_rolling_mean(close, window=20)
        ma60 = self._latest_rolling_mean(close, window=60)

        ema12 = self._latest_ema(close, span=12)
        ema26 = self._latest_ema(close, span=26)

        trend = self._classify_ma_trend(
            latest_close=self._latest_value(close),
            ma5=ma5,
            ma20=ma20,
            ma60=ma60,
        )

        return MovingAverageSnapshot(
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            ma60=ma60,
            ema12=ema12,
            ema26=ema26,
            trend=trend,
        )

    def calculate_rsi(self, df: pd.DataFrame) -> RsiSnapshot:
        self._validate_price_dataframe(df)

        close = df["close_price"]

        rsi6 = self._latest_rsi(close, period=6)
        rsi12 = self._latest_rsi(close, period=12)
        rsi24 = self._latest_rsi(close, period=24)

        return RsiSnapshot(
            rsi6=rsi6,
            rsi12=rsi12,
            rsi24=rsi24,
            status=self._classify_rsi_status(
                self._select_primary_rsi(rsi12=rsi12, rsi6=rsi6, rsi24=rsi24)
            ),
        )

    def _validate_price_dataframe(
        self,
        df: pd.DataFrame,
    ) -> None:
        if df.empty:
            raise BadRequestException(message="indicator dataframe cannot be empty")

        if "close_price" not in df.columns:
            raise BadRequestException(message="indicator dataframe missing close_price column")

        if df["close_price"].isna().any():
            raise BadRequestException(message="indicator dataframe contains invalid close_price")

        if (df["close_price"] < 0).any():
            raise BadRequestException(message="indicator dataframe contains negative close_price")

    def _latest_rolling_mean(
        self,
        series: pd.Series,
        *,
        window: int,
    ) -> float | None:
        if len(series) < window:
            return None

        value = series.rolling(window=window).mean().iloc[-1]
        return self._round_optional(value)

    def _latest_rsi(self, series: pd.Series, *, period: int) -> float | None:
        if len(series) <= period:
            return None

        delta = series.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        average_gain = gain.rolling(window=period).mean().iloc[-1]
        average_loss = loss.rolling(window=period).mean().iloc[-1]

        if pd.isna(average_gain) or pd.isna(average_loss):
            return None

        if average_loss == 0:
            if average_gain == 0:
                return 50.0
            return 100.0

        if average_gain == 0:
            return 0.0

        relative_strength = average_gain / average_loss
        rsi = 100 - (100 / (1 + relative_strength))

        return round(float(rsi), 4)

    def _classify_rsi_status(self, rsi: float | None) -> str:
        if rsi is None:
            return "neutral"

        if rsi >= 70:
            return "overbought"

        if rsi <= 30:
            return "oversold"

        return "neutral"

    def _select_primary_rsi(
        self,
        *,
        rsi12: float | None,
        rsi6: float | None,
        rsi24: float | None,
    ) -> float | None:
        for value in (rsi12, rsi6, rsi24):
            if value is not None:
                return value

        return None


    def _latest_ema(
        self,
        series: pd.Series,
        *,
        span: int,
    ) -> float | None:
        if len(series) < span:
            return None

        value = series.ewm(span=span, adjust=False).mean().iloc[-1]
        return self._round_optional(value)

    def _latest_value(
        self,
        series: pd.Series,
    ) -> float:
        return round(float(series.iloc[-1]), 4)

    def _round_optional(
        self,
        value,
    ) -> float | None:
        if pd.isna(value):
            return None

        return round(float(value), 4)

    def _classify_ma_trend(
        self,
        *,
        latest_close: float,
        ma5: float | None,
        ma20: float | None,
        ma60: float | None,
    ) -> str:
        if ma5 is not None and ma20 is not None:
            if latest_close > ma5 > ma20:
                return "bullish"

            if latest_close < ma5 < ma20:
                return "bearish"

        if ma20 is not None and ma60 is not None:
            if latest_close > ma20 > ma60:
                return "bullish"

            if latest_close < ma20 < ma60:
                return "bearish"

        return "neutral"

