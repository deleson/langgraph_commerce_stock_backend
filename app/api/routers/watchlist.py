from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.common import ApiResponse
from app.schemas.watchlist import (
    WatchlistCreateRequest,
    WatchlistResponse,
    WatchlistUpdateRequest,
)
from app.services.watchlist_service import WatchlistService
from app.utils.responses import success_response

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.post(
    "",
    summary="Create Watchlist Item",
    response_model=ApiResponse[WatchlistResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_watchlist_item(
    payload: WatchlistCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    item = WatchlistService(db).create_watchlist_item(
        user=current_user,
        payload=payload,
    )
    return success_response(data=WatchlistResponse.model_validate(item))


@router.get(
    "",
    summary="List My Watchlist Items",
    response_model=ApiResponse[list[WatchlistResponse]],
)
def list_my_watchlist_items(
    current_user: CurrentUser,
    db: DBSession,
):
    items = WatchlistService(db).list_my_watchlist(current_user)
    return success_response(
        data=[WatchlistResponse.model_validate(item) for item in items]
    )


@router.get(
    "/{item_id}",
    summary="Get My Watchlist Item",
    response_model=ApiResponse[WatchlistResponse],
)
def get_my_watchlist_item(
    item_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    item = WatchlistService(db).get_my_watchlist_item(
        user=current_user,
        item_id=item_id,
    )
    return success_response(data=WatchlistResponse.model_validate(item))


@router.patch(
    "/{item_id}",
    summary="Update My Watchlist Item",
    response_model=ApiResponse[WatchlistResponse],
)
def update_my_watchlist_item(
    item_id: int,
    payload: WatchlistUpdateRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    item = WatchlistService(db).update_watchlist_item(
        user=current_user,
        item_id=item_id,
        payload=payload,
    )
    return success_response(data=WatchlistResponse.model_validate(item))


@router.delete(
    "/{item_id}",
    summary="Delete My Watchlist Item",
    response_model=ApiResponse[dict[str, str]],
)
def delete_my_watchlist_item(
    item_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    WatchlistService(db).delete_watchlist_item(
        user=current_user,
        item_id=item_id,
    )
    return success_response(data={"message": "watchlist item deleted"})