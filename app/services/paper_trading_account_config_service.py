from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_account_config import PaperTradingAccountConfig
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.paper_trading import (
    PaperTradingAccountConfigCreate,
    PaperTradingAccountConfigResponse,
    PaperTradingAccountConfigUpdate,
    PaperTradingAccountStatus,
)
from app.services.paper_trading_account_service import PaperTradingAccountService


class PaperTradingAccountConfigService:
    """Paper trading account config business service.

    This service manages account-level paper trading rules.
    It does not create orders, trades, positions, equity snapshots, or run records.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
        account_service: PaperTradingAccountService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncPaperTradingRepository(db)
        self.account_service = account_service or PaperTradingAccountService(
            db,
            repository=self.repository,
        )

    async def get_config(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> PaperTradingAccountConfigResponse:
        await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        config = await self.repository.get_or_create_account_config(
            account_id=account_id,
        )
        return self._build_config_response(config)

    async def get_or_create_config_model(
        self,
        *,
        account: PaperTradingAccount,
    ) -> PaperTradingAccountConfig:
        return await self.repository.get_or_create_account_config(
            account_id=account.id,
        )

    async def update_config(
        self,
        *,
        user_id: int,
        account_id: int,
        request: PaperTradingAccountConfigUpdate,
    ) -> PaperTradingAccountConfigResponse:
        account = await self.account_service.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        self._validate_config_update(
            account=account,
            request=request,
        )

        config = await self.repository.get_or_create_account_config(
            account_id=account.id,
        )
        updated_config = await self.repository.update_account_config(
            config=config,
            payload=request,
        )
        return self._build_config_response(updated_config)

    async def create_default_config(
        self,
        *,
        account_id: int,
    ) -> PaperTradingAccountConfigResponse:
        config = await self.repository.create_account_config(
            account_id=account_id,
            payload=PaperTradingAccountConfigCreate(),
        )
        return self._build_config_response(config)

    def build_config_snapshot(
        self,
        config: PaperTradingAccountConfig,
    ) -> dict[str, Any]:
        return {
            "id": config.id,
            "account_id": config.account_id,
            "is_enabled": config.is_enabled,
            "max_symbols_per_tick": config.max_symbols_per_tick,
            "allow_buy": config.allow_buy,
            "allow_sell": config.allow_sell,
            "max_single_order_cash_ratio": self._decimal_to_string(
                config.max_single_order_cash_ratio
            ),
            "max_total_position_ratio": self._decimal_to_string(
                config.max_total_position_ratio
            ),
            "max_position_count": config.max_position_count,
            "min_order_cash_amount": self._decimal_to_string(
                config.min_order_cash_amount
            ),
            "fee_rate": self._decimal_to_string(config.fee_rate),
            "enforce_data_quality": config.enforce_data_quality,
            "data_quality_stale_after_days": config.data_quality_stale_after_days,
            "notes": config.notes,
        }

    def _validate_config_update(
        self,
        *,
        account: PaperTradingAccount,
        request: PaperTradingAccountConfigUpdate,
    ) -> None:
        if account.status == PaperTradingAccountStatus.CLOSED:
            raise BadRequestException(
                message="closed paper trading account config cannot be updated"
            )

        if (
            request.allow_buy is False
            and request.allow_sell is False
            and request.is_enabled is not False
        ):
            raise BadRequestException(
                message=(
                    "paper trading config cannot disable both buy and sell "
                    "while account config remains enabled"
                )
            )

        if (
            request.max_single_order_cash_ratio is not None
            and request.max_total_position_ratio is not None
            and request.max_single_order_cash_ratio
            > request.max_total_position_ratio
        ):
            raise BadRequestException(
                message=(
                    "max_single_order_cash_ratio cannot be greater than "
                    "max_total_position_ratio"
                )
            )

    def _build_config_response(
        self,
        config: PaperTradingAccountConfig,
    ) -> PaperTradingAccountConfigResponse:
        return PaperTradingAccountConfigResponse.model_validate(config)

    def _decimal_to_string(
        self,
        value: Decimal | None,
    ) -> str | None:
        if value is None:
            return None
        return str(value)