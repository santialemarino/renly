from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.repositories import expense_repository
from app.schemas.payment_obligation import (
    PaymentObligationCreate,
    PaymentObligationResponse,
    PaymentObligationUpdate,
)
from app.services import payment_obligation_service
from app.utils.metrics import convert_value, get_rate_map
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/payment-obligations", tags=["payment-obligations"])


# Converts an obligation's amount if a target currency and rate map are provided.
def _convert_response(
    resp: PaymentObligationResponse,
    entry_currency: str,
    target_currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> PaymentObligationResponse:
    if target_currency and rate_map and entry_currency != target_currency:
        resp.converted_amount = convert_value(resp.amount, entry_currency, target_currency, rate_map)
    elif target_currency and entry_currency == target_currency:
        resp.converted_amount = resp.amount
    return resp


# List payment obligations for the current user with optional search, sorting, and currency conversion.
@router.get("", response_model=list[PaymentObligationResponse])
async def list_obligations(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter obligations by name (case-insensitive)."),
    sort_by: str | None = Query(
        default=None,
        description="Column to sort by (name, amount, currency, next_due_date, recurrence, category).",
    ),
    sort_order: str = Query(default="asc", description="Sort direction (asc or desc)."),
    show_archived: bool = Query(default=False, description="Include archived (inactive) obligations."),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> list[PaymentObligationResponse]:
    obligations = await payment_obligation_service.list_obligations(
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

    # Batch-load latest-paid date per obligation in one query so archived one-off rows
    # can display "Paid on YYYY-MM-DD" without an N+1 lookup (Phase 3, Step E, 6.i).
    last_paid_dates = await expense_repository.max_linked_obligation_dates(session, current_user.id, [o.id for o in obligations])

    responses: list[PaymentObligationResponse] = []
    for o in obligations:
        resp = PaymentObligationResponse.model_validate(o)
        resp.last_payment_date = last_paid_dates.get(o.id)
        responses.append(_convert_response(resp, o.currency, currency, rate_map))
    return responses


# Get a single payment obligation by id (with optional currency conversion).
@router.get("/{obligation_id}", response_model=PaymentObligationResponse)
async def get_obligation(
    obligation_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> PaymentObligationResponse:
    obligation = await payment_obligation_service.get_obligation(session, obligation_id, current_user)
    resp = PaymentObligationResponse.model_validate(obligation)
    last_paid_dates = await expense_repository.max_linked_obligation_dates(session, current_user.id, [obligation.id])
    resp.last_payment_date = last_paid_dates.get(obligation.id)
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        rate_map = await get_rate_map(session, dp)
        resp = _convert_response(resp, obligation.currency, currency, rate_map)
    return resp


# Create a new payment obligation.
@router.post("", response_model=PaymentObligationResponse, status_code=status.HTTP_201_CREATED)
async def create_obligation(
    body: PaymentObligationCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> PaymentObligationResponse:
    obligation = await payment_obligation_service.create_obligation(
        session,
        current_user,
        name=body.name,
        amount=body.amount,
        currency=body.currency,
        next_due_date=body.next_due_date,
        recurrence=body.recurrence,
        category=body.category,
        expense_category=body.expense_category,
        payment_method=body.payment_method,
        credit_card_id=body.credit_card_id,
        notes=body.notes,
    )
    return PaymentObligationResponse.model_validate(obligation)


# Update an existing payment obligation.
@router.put("/{obligation_id}", response_model=PaymentObligationResponse)
async def update_obligation(
    obligation_id: int,
    body: PaymentObligationUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> PaymentObligationResponse:
    payload = body.model_dump(exclude_unset=True)
    obligation = await payment_obligation_service.update_obligation(session, obligation_id, current_user, **payload)
    return PaymentObligationResponse.model_validate(obligation)


# Delete a payment obligation. Returns 204.
@router.delete("/{obligation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_obligation(
    obligation_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await payment_obligation_service.delete_obligation(session, obligation_id, current_user)
