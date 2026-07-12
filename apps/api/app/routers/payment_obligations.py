from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.payment_obligation import (
    PaymentObligationCreate,
    PaymentObligationResponse,
    PaymentObligationUpdate,
)
from app.services import payment_obligation_service

router = APIRouter(prefix="/payment-obligations", tags=["payment-obligations"])


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
    include_ids: list[int] | None = Query(
        default=None,
        description=(
            "Archived obligation ids to include alongside the active set. Used by the expense edit "
            "dialog so a row linked to a since-archived obligation can still render the obligation "
            "name in the dropdown. Ignored when show_archived=true (everything is already included)."
        ),
    ),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> list[PaymentObligationResponse]:
    return await payment_obligation_service.list_obligations(
        session,
        current_user,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=not show_archived,
        include_ids=include_ids,
        currency=currency,
    )


# Get a single payment obligation by id (with optional currency conversion).
@router.get("/{obligation_id}", response_model=PaymentObligationResponse)
async def get_obligation(
    obligation_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> PaymentObligationResponse:
    return await payment_obligation_service.get_obligation_response(session, obligation_id, current_user, currency=currency)


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
