from datetime import date

from fastapi import APIRouter, Query, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.market_data import MarketCode
from app.schemas.quant_alert import (
    QuantAlertEventListQuery,
    QuantAlertEventListResponse,
    QuantAlertEventResponse,
    QuantAlertEventStatus,
    QuantAlertEventUpdate,
    QuantAlertRuleCreate,
    QuantAlertRuleListQuery,
    QuantAlertRuleListResponse,
    QuantAlertRuleResponse,
    QuantAlertRuleStatus,
    QuantAlertRuleType,
    QuantAlertRuleUpdate,
    QuantAlertScanRequest,
    QuantAlertScanResponse,
    QuantAlertScanSource,
    QuantAlertSeverity,
)
from app.services.quant_alert_query_service import QuantAlertQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/quant-alerts", tags=["quant-alerts"])


@router.post(
    "/rules",
    summary="Create Quant Alert Rule",
    description=(
        "Create one deterministic quant alert rule for the current user. "
        "Rules are based on strategy signals, price changes, volume spikes, "
        "or data quality conditions. They do not call AI."
    ),
    response_model=ApiResponse[QuantAlertRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_quant_alert_rule(
    payload: QuantAlertRuleCreate,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[QuantAlertRuleResponse]:
    """Create one quant alert rule owned by the current user."""

    result = await QuantAlertQueryService(db).create_rule(
        user_id=current_user.id,
        request=payload,
    )
    return success_response(data=result)


@router.get(
    "/rules",
    summary="List Quant Alert Rules",
    description="List quant alert rules owned by the current user.",
    response_model=ApiResponse[QuantAlertRuleListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_quant_alert_rules(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    rule_type: QuantAlertRuleType | None = Query(default=None),
    rule_status: QuantAlertRuleStatus | None = Query(default=None, alias="status"),
    market: MarketCode | None = Query(default=None),
    symbol: str | None = Query(default=None, min_length=1, max_length=32),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[QuantAlertRuleListResponse]:
    """List current user's quant alert rules."""

    query = QuantAlertRuleListQuery(
        rule_type=rule_type,
        status=rule_status,
        market=market,
        symbol=symbol,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )

    result = await QuantAlertQueryService(db).list_rules(
        user_id=current_user.id,
        query=query,
    )
    return success_response(data=result)


@router.get(
    "/rules/{rule_id}",
    summary="Get Quant Alert Rule",
    description="Get one quant alert rule by id. Users can only access their own rules.",
    response_model=ApiResponse[QuantAlertRuleResponse],
    status_code=status.HTTP_200_OK,
)
async def get_quant_alert_rule(
    rule_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[QuantAlertRuleResponse]:
    """Get one quant alert rule detail."""

    result = await QuantAlertQueryService(db).get_rule(
        user_id=current_user.id,
        rule_id=rule_id,
    )
    return success_response(data=result)


@router.patch(
    "/rules/{rule_id}",
    summary="Update Quant Alert Rule",
    description="Update one quant alert rule owned by the current user.",
    response_model=ApiResponse[QuantAlertRuleResponse],
    status_code=status.HTTP_200_OK,
)
async def update_quant_alert_rule(
    rule_id: int,
    payload: QuantAlertRuleUpdate,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[QuantAlertRuleResponse]:
    """Update one quant alert rule."""

    result = await QuantAlertQueryService(db).update_rule(
        user_id=current_user.id,
        rule_id=rule_id,
        request=payload,
    )
    return success_response(data=result)


@router.post(
    "/rules/{rule_id}/deactivate",
    summary="Deactivate Quant Alert Rule",
    description="Deactivate one quant alert rule. The rule is not physically deleted.",
    response_model=ApiResponse[QuantAlertRuleResponse],
    status_code=status.HTTP_200_OK,
)
async def deactivate_quant_alert_rule(
    rule_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[QuantAlertRuleResponse]:
    """Deactivate one quant alert rule."""

    result = await QuantAlertQueryService(db).deactivate_rule(
        user_id=current_user.id,
        rule_id=rule_id,
    )
    return success_response(data=result)


@router.get(
    "/events",
    summary="List Quant Alert Events",
    description="List triggered quant alert events owned by the current user.",
    response_model=ApiResponse[QuantAlertEventListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_quant_alert_events(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    rule_type: QuantAlertRuleType | None = Query(default=None),
    event_status: QuantAlertEventStatus | None = Query(default=None, alias="status"),
    severity: QuantAlertSeverity | None = Query(default=None),
    market: MarketCode | None = Query(default=None),
    symbol: str | None = Query(default=None, min_length=1, max_length=32),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[QuantAlertEventListResponse]:
    """List current user's quant alert events."""

    query = QuantAlertEventListQuery(
        rule_type=rule_type,
        status=event_status,
        severity=severity,
        market=market,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    result = await QuantAlertQueryService(db).list_events(
        user_id=current_user.id,
        query=query,
    )
    return success_response(data=result)


@router.get(
    "/events/{event_id}",
    summary="Get Quant Alert Event",
    description="Get one quant alert event by id. Users can only access their own events.",
    response_model=ApiResponse[QuantAlertEventResponse],
    status_code=status.HTTP_200_OK,
)
async def get_quant_alert_event(
    event_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[QuantAlertEventResponse]:
    """Get one quant alert event detail."""

    result = await QuantAlertQueryService(db).get_event(
        user_id=current_user.id,
        event_id=event_id,
    )
    return success_response(data=result)


@router.patch(
    "/events/{event_id}",
    summary="Update Quant Alert Event",
    description=(
        "Update one quant alert event owned by the current user. "
        "This is mainly used to acknowledge or ignore triggered events."
    ),
    response_model=ApiResponse[QuantAlertEventResponse],
    status_code=status.HTTP_200_OK,
)
async def update_quant_alert_event(
    event_id: int,
    payload: QuantAlertEventUpdate,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[QuantAlertEventResponse]:
    """Update one quant alert event status."""

    result = await QuantAlertQueryService(db).update_event(
        user_id=current_user.id,
        event_id=event_id,
        request=payload,
    )
    return success_response(data=result)


@router.post(
    "/scan",
    summary="Scan Quant Alerts",
    description=(
        "Run one manual quant alert scan for the current user. "
        "The scan reads current user's watchlist, evaluates active quant alert rules, "
        "and writes new QuantAlertEvent records. "
        "This endpoint does not call AI."
    ),
    response_model=ApiResponse[QuantAlertScanResponse],
    status_code=status.HTTP_200_OK,
)
async def scan_quant_alerts(
    payload: QuantAlertScanRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[QuantAlertScanResponse]:
    """Run one manual quant alert scan for the current user."""

    request = payload.model_copy(
        update={
            "target_user_id": current_user.id,
            "source": QuantAlertScanSource.API,
        }
    )

    result = await QuantAlertQueryService(db).scan_alerts(
        user=current_user,
        request=request,
    )
    return success_response(data=result)