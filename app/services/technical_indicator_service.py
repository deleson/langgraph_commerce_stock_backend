import pandas as pd

from app.core.exceptions import BadRequestException
from app.schemas.technical_indicator import MovingAverageSnapshot


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