from decimal import Decimal

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.domain import CalendarItem
from app.schemas.payments_calendar import PaymentsCalendarItemResponse, PaymentsCalendarResponse
from app.services import payments_calendar_service
from app.utils.metrics import convert_value, get_rate_map
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/payments-calendar", tags=["payments-calendar"])


# Maps a service CalendarItem to its response shape, attaching converted_amount when requested.
def _to_response(
    item: CalendarItem,
    target_currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> PaymentsCalendarItemResponse:
    converted: Decimal | None = None
    if target_currency and rate_map and item.currency != target_currency:
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
    )


# Aggregated read-only timeline for a calendar month. Sources: subscriptions,
# installment cuotas, payment obligations, and credit-card due dates.
@router.get("", response_model=PaymentsCalendarResponse)
async def get_payments_calendar(
    current_user: CurrentUser,
    session: SessionDep,
    year: int = Query(..., description="Calendar year (e.g. 2026)."),
    month: int = Query(..., ge=1, le=12, description="Calendar month (1-12)."),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> PaymentsCalendarResponse:
    items = await payments_calendar_service.get_calendar(session, current_user, year=year, month=month)

    rate_map: dict[str, Decimal] | None = None
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        rate_map = await get_rate_map(session, dp)

    return PaymentsCalendarResponse(
        year=year,
        month=month,
        currency=currency,
        items=[_to_response(item, currency, rate_map) for item in items],
    )
