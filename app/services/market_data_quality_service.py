from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from app.core.exceptions import BadRequestException
from app.schemas.market_data import MarketCandleCreate, MarketProviderCandle


class MarketDataQualityService:
    price_quant = Decimal("0.0001")
    amount_quant = Decimal("0.0001")

    def normalize_candle(
        self,
        candle: MarketProviderCandle,
        *,
        symbol_id: int | None = None,
    ) -> MarketCandleCreate:
        candle_time = self._normalize_datetime(candle.candle_time)

        open_price = self._normalize_price(candle.open_price)
        high_price = self._normalize_price(candle.high_price)
        low_price = self._normalize_price(candle.low_price)
        close_price = self._normalize_price(candle.close_price)
        amount = self._normalize_amount(candle.amount)

        self._validate_prices(
            symbol=candle.symbol,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
        )
        self._validate_volume(
            symbol=candle.symbol,
            volume=candle.volume,
        )

        return MarketCandleCreate(
            symbol_id=symbol_id,
            symbol=candle.symbol,
            market=candle.market,
            timeframe=candle.timeframe,
            candle_time=candle_time,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=candle.volume,
            amount=amount,
            source=candle.source,
            is_adjusted=candle.is_adjusted,
            adjust_type=candle.adjust_type,
        )

    def normalize_candles(
        self,
        candles: Sequence[MarketProviderCandle],
        *,
        symbol_id: int | None = None,
    ) -> list[MarketCandleCreate]:
        normalized_by_key: dict[
            tuple[str, str, str, datetime, str, str],
            MarketCandleCreate,
        ] = {}

        for candle in candles:
            payload = self.normalize_candle(
                candle,
                symbol_id=symbol_id,
            )
            key = (
                payload.symbol,
                payload.market,
                payload.timeframe,
                payload.candle_time,
                payload.source,
                payload.adjust_type,
            )
            normalized_by_key[key] = payload

        return sorted(
            normalized_by_key.values(),
            key=lambda item: item.candle_time,
        )

    def _normalize_datetime(
        self,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)

    def _normalize_price(
        self,
        value: Decimal,
    ) -> Decimal:
        if value < 0:
            raise BadRequestException(message="market candle price cannot be negative")

        return value.quantize(self.price_quant, rounding=ROUND_HALF_UP)

    def _normalize_amount(
        self,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is None:
            return None

        if value < 0:
            raise BadRequestException(message="market candle amount cannot be negative")

        return value.quantize(self.amount_quant, rounding=ROUND_HALF_UP)

    def _validate_prices(
        self,
        *,
        symbol: str,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
    ) -> None:
        if high_price < low_price:
            raise BadRequestException(
                message=f"invalid candle price range for {symbol}: high_price < low_price"
            )

        if open_price < low_price or open_price > high_price:
            raise BadRequestException(
                message=f"invalid candle open price for {symbol}: open_price outside high/low range"
            )

        if close_price < low_price or close_price > high_price:
            raise BadRequestException(
                message=f"invalid candle close price for {symbol}: close_price outside high/low range"
            )

    def _validate_volume(
        self,
        *,
        symbol: str,
        volume: int,
    ) -> None:
        if volume < 0:
            raise BadRequestException(
                message=f"invalid candle volume for {symbol}: volume cannot be negative"
            )