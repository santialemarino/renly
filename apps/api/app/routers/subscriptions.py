from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate
from app.services import subscription_service
from app.utils.metrics import convert_value, get_rate_map
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# Converts a subscription's amount if a target currency and rate map are provided.
def _convert_response(
    resp: SubscriptionResponse,
    entry_currency: str,
    target_currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> SubscriptionResponse:
    if target_currency and rate_map and entry_currency != target_currency:
        resp.converted_amount = convert_value(resp.amount, entry_currency, target_currency, rate_map)
    elif target_currency and entry_currency == target_currency:
        resp.converted_amount = resp.amount
    return resp


# List subscriptions for the current user with optional search, sorting, and currency conversion.
@router.get("", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter subscriptions by name (case-insensitive)."),
    sort_by: str | None = Query(
        default=None,
        description="Column to sort by (name, amount, currency, billing_cycle, next_billing_date).",
    ),
    sort_order: str = Query(default="asc", description="Sort direction (asc or desc)."),
    show_archived: bool = Query(default=False, description="Include archived (inactive) subscriptions."),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> list[SubscriptionResponse]:
    subscriptions = await subscription_service.list_subscriptions(
        session,
        current_user,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=not show_archived,
    )

    rate_map = None
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        rate_map = await get_rate_map(session, dp)

    return [_convert_response(SubscriptionResponse.model_validate(s), s.currency, currency, rate_map) for s in subscriptions]


# Get a single subscription by id (with optional currency conversion).
@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> SubscriptionResponse:
    subscription = await subscription_service.get_subscription(session, subscription_id, current_user)
    resp = SubscriptionResponse.model_validate(subscription)
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        rate_map = await get_rate_map(session, dp)
        resp = _convert_response(resp, subscription.currency, currency, rate_map)
    return resp


# Create a new subscription. Supports both JWT (web) and API key (iOS Shortcut) auth.
@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionCreate,
    current_user: JwtOrApiKeyUser,
    session: SessionDep,
) -> SubscriptionResponse:
    subscription = await subscription_service.create_subscription(
        session,
        current_user,
        name=body.name,
        amount=body.amount,
        currency=body.currency,
        billing_cycle=body.billing_cycle,
        next_billing_date=body.next_billing_date,
        payment_method=body.payment_method,
        credit_card_id=body.credit_card_id,
    )
    return SubscriptionResponse.model_validate(subscription)


# Update an existing subscription.
@router.put("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    body: SubscriptionUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SubscriptionResponse:
    payload = body.model_dump(exclude_unset=True)
    subscription = await subscription_service.update_subscription(session, subscription_id, current_user, **payload)
    return SubscriptionResponse.model_validate(subscription)


# Delete a subscription. Returns 204.
@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await subscription_service.delete_subscription(session, subscription_id, current_user)
