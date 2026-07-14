from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.currency import DisplayCurrency
from app.deps.db import SessionDep
from app.schemas.payments_calendar import PaymentsCalendarResponse
from app.services import payments_calendar_service

router = APIRouter(prefix="/payments-calendar", tags=["payments-calendar"])


# Aggregated read-only timeline for a calendar month. Sources: subscriptions,
# installments, payment obligations, and credit-card due dates.
@router.get("", response_model=PaymentsCalendarResponse)
async def get_payments_calendar(
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency,
    year: int = Query(..., description="Calendar year (e.g. 2026)."),
    month: int = Query(..., ge=1, le=12, description="Calendar month (1-12)."),
) -> PaymentsCalendarResponse:
    return await payments_calendar_service.get_calendar(session, current_user, year=year, month=month, currency=currency)
