from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.core.exceptions import BadRequestException
from app.schemas.market_data import MarketCandleCreate, MarketProviderCandle


@dataclass
class MarketDataQualityCheckResult:
    candle_count: int
    duplicate_count: int = 0
    earliest_candle_time: datetime | None = None
    latest_candle_time: datetime | None = None
    is_empty: bool = False
    is_enough: bool = True
    is_stale: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
            key = self._build_candle_identity(payload)
            normalized_by_key[key] = payload

        return sorted(
            normalized_by_key.values(),
            key=lambda item: item.candle_time,
        )

    def inspect_candles(
        self,
        candles: Sequence[MarketCandleCreate],
        *,
        original_count: int | None = None,
        min_required: int = 1,
        stale_after_days: int | None = None,
        now: datetime | None = None,
    ) -> MarketDataQualityCheckResult:
        if min_required <= 0:
            raise BadRequestException(message="min_required must be greater than 0")

        if stale_after_days is not None and stale_after_days <= 0:
            raise BadRequestException(message="stale_after_days must be greater than 0")

        sorted_candles = sorted(candles, key=lambda candle: candle.candle_time)
        candle_count = len(sorted_candles)
        duplicate_count = self._calculate_duplicate_count(
            candles=sorted_candles,
            original_count=original_count,
        )

        result = MarketDataQualityCheckResult(
            candle_count=candle_count,
            duplicate_count=duplicate_count,
            is_empty=candle_count == 0,
        )

        if candle_count == 0:
            result.is_enough = False
            result.errors.append("market candle data is empty")
            return result

        result.earliest_candle_time = sorted_candles[0].candle_time
        result.latest_candle_time = sorted_candles[-1].candle_time

        if candle_count < min_required:
            result.is_enough = False
            result.warnings.append(
                f"not enough candles: required={min_required}, actual={candle_count}"
            )

        if duplicate_count > 0:
            result.warnings.append(f"duplicate candles removed: duplicate_count={duplicate_count}")

        stale_now = self._normalize_datetime(now or datetime.now(UTC))

        if stale_after_days is not None and result.latest_candle_time is not None:
            latest_time = self._normalize_datetime(result.latest_candle_time)
            stale_threshold = stale_now - timedelta(days=stale_after_days)

            if latest_time < stale_threshold:
                result.is_stale = True
                result.warnings.append(
                    f"latest candle is stale: latest_candle_time={latest_time.isoformat()}"
                )

        return result

    def inspect_provider_candles(
        self,
        candles: Sequence[MarketProviderCandle],
        *,
        symbol_id: int | None = None,
        min_required: int = 1,
        stale_after_days: int | None = None,
        now: datetime | None = None,
    ) -> tuple[list[MarketCandleCreate], MarketDataQualityCheckResult]:
        normalized_candles = self.normalize_candles(
            candles,
            symbol_id=symbol_id,
        )
        quality_result = self.inspect_candles(
            normalized_candles,
            original_count=len(candles),
            min_required=min_required,
            stale_after_days=stale_after_days,
            now=now,
        )
        return normalized_candles, quality_result

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

    def _build_candle_identity(
        self,
        candle: MarketCandleCreate,
    ) -> tuple[str, str, str, datetime, str, str]:
        return (
            candle.symbol,
            candle.market,
            candle.timeframe,
            candle.candle_time,
            candle.source,
            candle.adjust_type,
        )

    def _calculate_duplicate_count(
        self,
        *,
        candles: Sequence[MarketCandleCreate],
        original_count: int | None,
    ) -> int:
        if original_count is not None:
            return max(original_count - len(candles), 0)

        unique_keys = {self._build_candle_identity(candle) for candle in candles}
        return max(len(candles) - len(unique_keys), 0)