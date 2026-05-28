from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.expense_entry import ExpenseCategory
from app.schemas.expense import (
    AutoChargeMatch,
    AutoChargeMatchResponse,
    AutoChargeMatchSourcePlan,
    CycleAdvancePreviewResponse,
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseResponse,
    ExpenseUpdate,
)
from app.services import expense_service
from app.utils.metrics import RateLookup, build_rate_lookup, convert_value
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/expenses", tags=["expenses"])


# Converts an entry's amount at the entry's historical date (Phase 3, Step C).
# Expenses are records of past events — display value reflects the rate that was in effect
# when the expense actually happened, so re-opening the page on a different day shows the
# same number.
def _convert_entry(
    resp: ExpenseResponse,
    entry_currency: str,
    entry_date: date_type,
    target_currency: str | None,
    lookup: RateLookup | None,
) -> ExpenseResponse:
    if target_currency and lookup and entry_currency != target_currency:
        rate_map = lookup.get_rate_map_at(entry_date)
        if rate_map:
            resp.converted_amount = convert_value(resp.amount, entry_currency, target_currency, rate_map)
    elif target_currency and entry_currency == target_currency:
        resp.converted_amount = resp.amount
    return resp


# List expenses with optional filters, pagination, and currency conversion.
@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Search notes."),
    category: ExpenseCategory | None = Query(default=None, description="Filter by category."),
    payment_method: str | None = Query(default=None, description="Filter by payment method."),
    date_from: date_type | None = Query(default=None, description="Start date (inclusive)."),
    date_to: date_type | None = Query(default=None, description="End date (inclusive)."),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page."),
) -> ExpenseListResponse:
    entries, total = await expense_service.list_expenses(
        session,
        current_user,
        search=search,
        category=category,
        payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    lookup: RateLookup | None = None
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        lookup = await build_rate_lookup(session, dp)

    items = [_convert_entry(ExpenseResponse.model_validate(e), e.currency, e.date, currency, lookup) for e in entries]
    return ExpenseListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        display_currency=currency,
    )


# Look up a likely-duplicate auto-generated expense for a manual entry being drafted
# (Phase 3, Step D). Returns at most one match (newest first) — the form uses it to
# trigger a soft confirmation dialog before saving. Declared above GET /{id} so the
# static slug isn't shadowed by the parametrised route.
@router.get("/auto-charge-match", response_model=AutoChargeMatchResponse)
async def auto_charge_match(
    current_user: CurrentUser,
    session: SessionDep,
    credit_card_id: int = Query(description="Credit card id of the candidate manual entry."),
    currency: str = Query(description="Currency of the candidate manual entry (ISO 4217).", max_length=3),
    amount: Decimal = Query(description="Amount of the candidate manual entry.", gt=0),
    date: date_type = Query(description="Date of the candidate manual entry."),
    exclude_expense_id: int | None = Query(
        default=None,
        description="Expense id to exclude (set on the edit flow so a row doesn't match itself).",
    ),
) -> AutoChargeMatchResponse:
    result = await expense_service.find_auto_charge_match(
        session,
        current_user,
        credit_card_id=credit_card_id,
        currency=currency,
        amount=amount,
        target_date=date,
        exclude_expense_id=exclude_expense_id,
    )
    if result is None:
        return AutoChargeMatchResponse(match=None)
    return AutoChargeMatchResponse(
        match=AutoChargeMatch(
            expense_id=result.expense_id,
            date=result.date,
            source=result.source,
            source_plan=AutoChargeMatchSourcePlan(id=result.source_plan_id, name=result.source_plan_name),
        )
    )


# Preview the effect of saving a manual expense linked to a subscription or installment
# (Phase 3, follow-up 3b). Returns would_advance + distance + matched cycle so the
# expense form can show a soft-confirm dialog when the entry is out of tolerance / back-
# dated. Mirrors the auto-charge-match lookup pattern. Declared above GET /{id} so the
# static slug isn't shadowed by the parametrised route. Exactly one of subscription_id
# / installment_id must be set.
@router.get("/cycle-advance-preview", response_model=CycleAdvancePreviewResponse)
async def cycle_advance_preview(
    current_user: CurrentUser,
    session: SessionDep,
    entry_date: date_type = Query(description="Date of the candidate manual entry."),
    subscription_id: int | None = Query(default=None, description="Subscription id (mutually exclusive with installment_id)."),
    installment_id: int | None = Query(default=None, description="Installment id (mutually exclusive with subscription_id)."),
) -> CycleAdvancePreviewResponse:
    if (subscription_id is None) == (installment_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of subscription_id or installment_id must be set.",
        )
    decision = await expense_service.find_cycle_advance_decision(
        session,
        current_user,
        subscription_id=subscription_id,
        installment_id=installment_id,
        entry_date=entry_date,
    )
    return CycleAdvancePreviewResponse(
        would_advance=decision.would_advance,
        distance_days=decision.distance_days,
        next_expected_date=decision.next_expected_date,
    )


# Get a single expense by id (with optional currency conversion).
@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> ExpenseResponse:
    entry = await expense_service.get_expense(session, expense_id, current_user)
    resp = ExpenseResponse.model_validate(entry)
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        lookup = await build_rate_lookup(session, dp)
        resp = _convert_entry(resp, entry.currency, entry.date, currency, lookup)
    return resp


# Create a new expense. Supports both JWT (web) and API key (iOS Shortcut) auth.
@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: ExpenseCreate,
    current_user: JwtOrApiKeyUser,
    session: SessionDep,
) -> ExpenseResponse:
    entry = await expense_service.create_expense(
        session,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        category=body.category,
        notes=body.notes,
        payment_method=body.payment_method,
        credit_card_id=body.credit_card_id,
        source=body.source,
        payment_obligation_id=body.payment_obligation_id,
        subscription_id=body.subscription_id,
        installment_id=body.installment_id,
    )
    return ExpenseResponse.model_validate(entry)


# Update an existing expense.
@router.put("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    body: ExpenseUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> ExpenseResponse:
    payload = body.model_dump(exclude_unset=True)
    entry = await expense_service.update_expense(session, expense_id, current_user, **payload)
    return ExpenseResponse.model_validate(entry)


# Delete an expense. Returns 204.
@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await expense_service.delete_expense(session, expense_id, current_user)
