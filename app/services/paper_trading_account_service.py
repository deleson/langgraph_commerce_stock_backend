from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.paper_trading_account import PaperTradingAccount
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.paper_trading import (
    PaperTradingAccountCreate,
    PaperTradingAccountListResponse,
    PaperTradingAccountResponse,
    PaperTradingAccountStatus,
    PaperTradingAccountUpdate,
    PaperTradingListQuery,
)


class PaperTradingAccountService:
    """Paper trading account business service.

    This service manages virtual paper trading accounts.
    It does not create orders, trades, positions, or equity snapshots.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncPaperTradingRepository(db)

    async def create_account(
        self,
        *,
        user_id: int,
        request: PaperTradingAccountCreate,
    ) -> PaperTradingAccountResponse:
        account = await self.repository.create_account(
            user_id=user_id,
            payload=request,
        )
        return self._build_account_response(account)

    async def get_account(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> PaperTradingAccountResponse:
        account = await self.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )
        return self._build_account_response(account)

    async def list_accounts(
        self,
        *,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> PaperTradingAccountListResponse:
        total = await self.repository.count_accounts(user_id=user_id)
        items = await self.repository.list_accounts(
            user_id=user_id,
            query=query,
        )

        return PaperTradingAccountListResponse(
            total=total,
            items=[self._build_account_response(item) for item in items],
        )

    async def update_account(
        self,
        *,
        user_id: int,
        account_id: int,
        request: PaperTradingAccountUpdate,
    ) -> PaperTradingAccountResponse:
        account = await self.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )

        self._validate_account_update(
            account=account,
            request=request,
        )

        updated_account = await self.repository.update_account(
            account,
            request,
        )
        return self._build_account_response(updated_account)

    async def delete_account(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> None:
        account = await self.get_account_model(
            user_id=user_id,
            account_id=account_id,
        )
        await self.repository.delete_account_tree(account)

    async def get_or_create_default_account(
        self,
        *,
        user_id: int,
    ) -> PaperTradingAccountResponse:
        query = PaperTradingListQuery(limit=1, offset=0)
        accounts = await self.repository.list_accounts(
            user_id=user_id,
            query=query,
        )

        if accounts:
            return self._build_account_response(accounts[0])

        account = await self.repository.create_account(
            user_id=user_id,
            payload=PaperTradingAccountCreate(),
        )
        return self._build_account_response(account)

    async def get_account_model(
        self,
        *,
        user_id: int,
        account_id: int,
    ) -> PaperTradingAccount:
        account = await self.repository.get_account(
            user_id=user_id,
            account_id=account_id,
        )
        if account is None:
            raise NotFoundException(message="paper trading account not found")

        return account

    def _validate_account_update(
        self,
        *,
        account: PaperTradingAccount,
        request: PaperTradingAccountUpdate,
    ) -> None:
        if account.status == PaperTradingAccountStatus.CLOSED:
            raise BadRequestException(
                message="closed paper trading account cannot be updated"
            )

        if request.status == PaperTradingAccountStatus.ACTIVE and account.status == PaperTradingAccountStatus.CLOSED:
            raise BadRequestException(
                message="closed paper trading account cannot be reactivated"
            )

    def _build_account_response(
        self,
        account: PaperTradingAccount,
    ) -> PaperTradingAccountResponse:
        return PaperTradingAccountResponse.model_validate(account)