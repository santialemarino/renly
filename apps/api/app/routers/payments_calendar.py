from decimal import Decimal

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.domain import CalendarItem
from app.schemas.payments_calendar import PaymentsCalendarItemResponse, PaymentsCalendarResponse
from app.services import payments_calendar_service
from app.utils.metrics import RateLookup, build_rate_lookup, convert_value
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/payments-calendar", tags=["payments-calendar"])


# Maps a service CalendarItem to its response shape, attaching converted_amount when requested.
# Conversion uses the rate as of the item's own event date (Phase 3, Step C). Past months on the
# calendar therefore display historical-rate amounts; future-dated items fall back to today's
# latest rate (the RateLookup's natural behaviour for dates without a stored quote).
def _to_response(
    item: CalendarItem,
    target_currency: str | None,
    lookup: RateLookup | None,
) -> PaymentsCalendarItemResponse:
    converted: Decimal | None = None
    # Past-paid obligations set `conversion_date` to the linked expense's actual date
    # so the rate matches what the expenses list shows; everything else uses the cycle date.
    fx_date = item.conversion_date or item.date
    if target_currency and lookup and item.currency != target_currency:
        rate_map = lookup.get_rate_map_at(fx_date)
        if rate_map:
            converted = convert_value(item.amount, item.currency, target_currency, rate_map)
    elif target_currency and item.currency == target_currency:
        converted = item.amount
    return PaymentsCalendarItemResponse(
        type=item.type,
        date=item.date,
        name=item.name,
        amount=item.amount,
        currency=item.currency,
        converted_amount=converted,
        payment_method=item.payment_method,
        credit_card_id=item.credit_card_id,
        source_id=item.source_id,
        cuota_index=item.cuota_index,
        installments_count=item.installments_count,
        recurrence=item.recurrence,
        is_paid=item.is_paid,
        linked_expense_id=item.linked_expense_id,
    )


# Aggregated read-only timeline for a calendar month. Sources: subscriptions,
# installments, payment obligations, and credit-card due dates.
@router.get("", response_model=PaymentsCalendarResponse)
async def get_payments_calendar(
    current_user: CurrentUser,
    session: SessionDep,
    year: int = Query(..., description="Calendar year (e.g. 2026)."),
    month: int = Query(..., ge=1, le=12, description="Calendar month (1-12)."),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> PaymentsCalendarResponse:
    items = await payments_calendar_service.get_calendar(session, current_user, year=year, month=month)

    lookup: RateLookup | None = None
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        lookup = await build_rate_lookup(session, dp)

    return PaymentsCalendarResponse(
        year=year,
        month=month,
        currency=currency,
        items=[_to_response(item, currency, lookup) for item in items],
    )
