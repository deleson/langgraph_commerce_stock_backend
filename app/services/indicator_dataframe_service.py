from collections.abc import Sequence
from decimal import Decimal

import pandas as pd

from app.core.exceptions import BadRequestException
from app.models.market_candle import MarketCandle


class IndicatorDataFrameService:
    required_columns = [
        "candle_time",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
    ]

    def candles_to_dataframe(
        self,
        candles: Sequence[MarketCandle],
    ) -> pd.DataFrame:
        if not candles:
            raise BadRequestException(message="candles cannot be empty")

        rows = [
            self._candle_to_row(candle)
            for candle in candles
        ]

        df = pd.DataFrame(rows)

        return self._normalize_dataframe(df)

    def _candle_to_row(
        self,
        candle: MarketCandle,
    ) -> dict[str, object]:
        return {
            "candle_time": candle.candle_time,
            "open_price": self._to_float(candle.open_price),
            "high_price": self._to_float(candle.high_price),
            "low_price": self._to_float(candle.low_price),
            "close_price": self._to_float(candle.close_price),
            "volume": float(candle.volume),
            "amount": self._to_optional_float(candle.amount),
            "source": candle.source,
            "adjust_type": candle.adjust_type,
        }

    def _normalize_dataframe(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        missing_columns = [
            column
            for column in self.required_columns
            if column not in df.columns
        ]
        if missing_columns:
            raise BadRequestException(
                message=f"market candle dataframe missing columns: {missing_columns}"
            )

        normalized_df = df.copy()

        normalized_df["candle_time"] = pd.to_datetime(
            normalized_df["candle_time"],
            utc=True,
        )

        numeric_columns = [
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "amount",
        ]

        for column in numeric_columns:
            if column in normalized_df.columns:
                normalized_df[column] = pd.to_numeric(
                    normalized_df[column],
                    errors="coerce",
                )

        normalized_df = normalized_df.sort_values("candle_time").reset_index(drop=True)

        self._validate_dataframe(normalized_df)

        return normalized_df

    def _validate_dataframe(
        self,
        df: pd.DataFrame,
    ) -> None:
        if df.empty:
            raise BadRequestException(message="market candle dataframe cannot be empty")

        if df["candle_time"].isna().any():
            raise BadRequestException(message="market candle dataframe contains invalid candle_time")

        price_columns = [
            "open_price",
            "high_price",
            "low_price",
            "close_price",
        ]

        for column in price_columns:
            if df[column].isna().any():
                raise BadRequestException(message=f"market candle dataframe contains invalid {column}")

            if (df[column] < 0).any():
                raise BadRequestException(message=f"market candle dataframe contains negative {column}")

        if (df["high_price"] < df["low_price"]).any():
            raise BadRequestException(message="market candle dataframe contains high_price < low_price")

        if (df["volume"] < 0).any():
            raise BadRequestException(message="market candle dataframe contains negative volume")

    def _to_float(
        self,
        value: Decimal,
    ) -> float:
        return float(value)

    def _to_optional_float(
        self,
        value: Decimal | None,
    ) -> float | None:
        if value is None:
            return None
        return float(value)