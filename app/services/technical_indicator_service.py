import pandas as pd

from app.core.exceptions import BadRequestException
from app.schemas.technical_indicator import (
    MacdSnapshot,
    MomentumSnapshot,
    MovingAverageSnapshot,
    RsiSnapshot,
    VolatilitySnapshot,
    VolumeFactorSnapshot,
)


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

    def calculate_macd(
        self,
        df: pd.DataFrame,
    ) -> MacdSnapshot:
        self._validate_price_dataframe(df)

        close = df["close_price"]

        macd_values = self._latest_macd(
            close,
            fast_span=12,
            slow_span=26,
            signal_span=9,
        )

        dif = macd_values["dif"]
        dea = macd_values["dea"]
        histogram = macd_values["histogram"]

        return MacdSnapshot(
            dif=dif,
            dea=dea,
            histogram=histogram,
            signal=self._classify_macd_signal(
                dif=dif,
                dea=dea,
                histogram=histogram,
            ),
        )

    def calculate_volatility(
        self,
        df: pd.DataFrame,
    ) -> VolatilitySnapshot:
        self._validate_price_dataframe(df)

        close = df["close_price"]
        daily_returns = close.pct_change().dropna()

        if len(daily_returns) < 2:
            return VolatilitySnapshot(
                daily_return_std=None,
                annualized_volatility=None,
                level="low",
            )

        daily_return_std = round(float(daily_returns.std()), 6)
        annualized_volatility = round(float(daily_return_std * (252 ** 0.5)), 6)

        return VolatilitySnapshot(
            daily_return_std=daily_return_std,
            annualized_volatility=annualized_volatility,
            level=self._classify_volatility_level(annualized_volatility),
        )

    def calculate_momentum(
        self,
        df: pd.DataFrame,
    ) -> MomentumSnapshot:
        self._validate_price_dataframe(df)

        close = df["close_price"]

        momentum_5 = self._latest_momentum(close, window=5)
        momentum_10 = self._latest_momentum(close, window=10)
        momentum_20 = self._latest_momentum(close, window=20)

        return MomentumSnapshot(
            momentum_5=momentum_5,
            momentum_10=momentum_10,
            momentum_20=momentum_20,
            direction=self._classify_momentum_direction(
                momentum_5=momentum_5,
                momentum_10=momentum_10,
                momentum_20=momentum_20,
            ),
        )

    def calculate_volume_factor(
        self,
        df: pd.DataFrame,
    ) -> VolumeFactorSnapshot:
        self._validate_volume_dataframe(df)

        volume = df["volume"]

        volume_ma5 = self._latest_rolling_mean(volume, window=5)
        volume_ma20 = self._latest_rolling_mean(volume, window=20)
        volume_ratio = self._calculate_volume_ratio(
            latest_volume=self._latest_value(volume),
            volume_ma20=volume_ma20,
        )

        return VolumeFactorSnapshot(
            volume_ma5=volume_ma5,
            volume_ma20=volume_ma20,
            volume_ratio=volume_ratio,
            status=self._classify_volume_status(volume_ratio),
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

    def _classify_volatility_level(
        self,
        annualized_volatility: float | None,
    ) -> str:
        if annualized_volatility is None:
            return "low"

        if annualized_volatility >= 0.4:
            return "high"

        if annualized_volatility >= 0.2:
            return "medium"

        return "low"

    def _latest_momentum(
        self,
        series: pd.Series,
        *,
        window: int,
    ) -> float | None:
        if len(series) <= window:
            return None

        value = series.iloc[-1] - series.iloc[-window - 1]
        return round(float(value), 4)

    def _classify_momentum_direction(
        self,
        *,
        momentum_5: float | None,
        momentum_10: float | None,
        momentum_20: float | None,
    ) -> str:
        primary_momentum = self._select_primary_momentum(
            momentum_20=momentum_20,
            momentum_10=momentum_10,
            momentum_5=momentum_5,
        )

        if primary_momentum is None:
            return "neutral"

        if primary_momentum > 0:
            return "bullish"

        if primary_momentum < 0:
            return "bearish"

        return "neutral"

    def _select_primary_momentum(
        self,
        *,
        momentum_20: float | None,
        momentum_10: float | None,
        momentum_5: float | None,
    ) -> float | None:
        for value in (momentum_20, momentum_10, momentum_5):
            if value is not None:
                return value

        return None

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

        if (df["close_price"] <= 0).any():
            raise BadRequestException(message="indicator dataframe contains non-positive close_price")


    def _validate_volume_dataframe(
        self,
        df: pd.DataFrame,
    ) -> None:
        if df.empty:
            raise BadRequestException(message="indicator dataframe cannot be empty")

        if "volume" not in df.columns:
            raise BadRequestException(message="indicator dataframe missing volume column")

        if df["volume"].isna().any():
            raise BadRequestException(message="indicator dataframe contains invalid volume")

        if (df["volume"] < 0).any():
            raise BadRequestException(message="indicator dataframe contains negative volume")

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

    def _latest_macd(
        self,
        series: pd.Series,
        *,
        fast_span: int,
        slow_span: int,
        signal_span: int,
    ) -> dict[str, float | None]:
        min_required = slow_span + signal_span

        if len(series) < min_required:
            return {
                "dif": None,
                "dea": None,
                "histogram": None,
            }

        ema_fast = series.ewm(span=fast_span, adjust=False).mean()
        ema_slow = series.ewm(span=slow_span, adjust=False).mean()

        dif_series = ema_fast - ema_slow
        dea_series = dif_series.ewm(span=signal_span, adjust=False).mean()
        histogram_series = 2 * (dif_series - dea_series)

        return {
            "dif": self._round_optional(dif_series.iloc[-1]),
            "dea": self._round_optional(dea_series.iloc[-1]),
            "histogram": self._round_optional(histogram_series.iloc[-1]),
        }

    def _classify_macd_signal(
        self,
        *,
        dif: float | None,
        dea: float | None,
        histogram: float | None,
    ) -> str:
        if dif is None or dea is None or histogram is None:
            return "neutral"

        if dif > dea and histogram > 0:
            return "bullish"

        if dif < dea and histogram < 0:
            return "bearish"

        return "neutral"

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


    def _calculate_volume_ratio(
        self,
        *,
        latest_volume: float,
        volume_ma20: float | None,
    ) -> float | None:
        if volume_ma20 is None or volume_ma20 == 0:
            return None

        return round(latest_volume / volume_ma20, 4)

    def _classify_volume_status(
        self,
        volume_ratio: float | None,
    ) -> str:
        if volume_ratio is None:
            return "normal"

        if volume_ratio >= 1.5:
            return "expanding"

        if volume_ratio <= 0.5:
            return "shrinking"

        return "normal"