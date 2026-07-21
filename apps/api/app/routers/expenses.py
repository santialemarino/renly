from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.currency import DisplayCurrency
from app.deps.db import SessionDep
from app.domain import AdvanceResult, ReverseResult
from app.http_errors import CodedHTTPException
from app.models.expense_entry import ExpenseCategory
from app.schemas.expense import (
    AutoChargeMatch,
    AutoChargeMatchResponse,
    AutoChargeMatchSourcePlan,
    CycleAdvancePreviewResponse,
    ExpenseCreate,
    ExpenseDeleteResponse,
    ExpenseListResponse,
    ExpenseResponse,
    ExpenseUpdate,
    PlanCursorChange,
)
from app.services import expense_service

router = APIRouter(prefix="/expenses", tags=["expenses"])


# Maps an AdvanceResult / ReverseResult to the PlanCursorChange response field.
def _cursor_change(result: AdvanceResult | ReverseResult | None) -> PlanCursorChange | None:
    if result is None:
        return None
    return PlanCursorChange(
        plan_type=result.plan_type,
        plan_id=result.plan_id,
        plan_name=result.plan_name,
        previous_cursor=result.previous_cursor,
        new_cursor=result.new_cursor,
        total_count=result.total_count,
    )


# List expenses with optional filters, pagination, and currency conversion.
@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency,
    search: str | None = Query(default=None, description="Search notes."),
    category: ExpenseCategory | None = Query(default=None, description="Filter by category."),
    payment_method: str | None = Query(default=None, description="Filter by payment method."),
    date_from: date_type | None = Query(default=None, description="Start date (inclusive)."),
    date_to: date_type | None = Query(default=None, description="End date (inclusive)."),
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page."),
) -> ExpenseListResponse:
    return await expense_service.list_expenses(
        session,
        current_user,
        search=search,
        category=category,
        payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
        page=page,
        page_size=page_size,
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
# (Phase 3, follow-up 3b). Returns would_advance + distance + matched cycle + multi_jump
# so the expense form can show a soft-confirm dialog when the cursor won't advance —
# multi-jump (matched cycle ahead of cursor) vs back-dated (matched behind) gets different
# copy. Mirrors the auto-charge-match lookup pattern. Declared above GET /{id} so the
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
        raise CodedHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of subscription_id or installment_id must be set.",
            code="mutually_exclusive_link",
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
        multi_jump=decision.multi_jump,
    )


# Get a single expense by id (with optional currency conversion).
@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency,
) -> ExpenseResponse:
    return await expense_service.get_expense_response(session, expense_id, current_user, currency=currency)


# Create a new expense. Supports both JWT (web) and API key (iOS Shortcut) auth.
# advance_change on the response (when populated) carries the advance emitted by a
# linked obligation / subscription / installment (Phase 3, follow-up Item 7). When
# body.cycles_to_advance > 1 (Phase 3, follow-up Item 2), the request inserts N rows
# atomically and walks the obligation cursor N steps in a single transaction; the
# response carries the last-inserted entry and an advance spanning the whole walk.
@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: ExpenseCreate,
    current_user: JwtOrApiKeyUser,
    session: SessionDep,
) -> ExpenseResponse:
    if body.cycles_to_advance > 1:
        try:
            entry, advance_result = await expense_service.create_expenses_for_obligation_cycles(
                session,
                current_user,
                cycles=body.cycles_to_advance,
                date=body.date,
                amount=body.amount,
                currency=body.currency,
                category=body.category,
                notes=body.notes,
                payment_method=body.payment_method,
                credit_card_id=body.credit_card_id,
                source=body.source,
                payment_obligation_id=body.payment_obligation_id,  # type: ignore[arg-type]
            )
        except ValueError as exc:
            raise CodedHTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc), code="expense_cycle_invalid") from exc
    else:
        entry, advance_result = await expense_service.create_expense(
            session,
            current_user,
            date=body.date,
            amount=body.amount,
            currency=body.currency,
            category=body.category,
            notes=body.notes,
            payment_method=body.payment_method,
            credit_card_id=body.credit_card_id,
            account_id=body.account_id,
            source=body.source,
            payment_obligation_id=body.payment_obligation_id,
            subscription_id=body.subscription_id,
            installment_id=body.installment_id,
        )
    resp = ExpenseResponse.model_validate(entry)
    resp.advance_change = _cursor_change(advance_result)
    return resp


# Update an existing expense. advance_change + reverse_change on the response carry the
# cursor deltas emitted by the symmetric FK-transition model (Phase 3, follow-up Items 10
# + audit round 2): edit can fire reverse on the OLD plan (clear / swap) AND advance on
# the NEW plan (add / swap). Both can be populated simultaneously on a swap.
@router.put("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    body: ExpenseUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> ExpenseResponse:
    payload = body.model_dump(exclude_unset=True)
    entry, advance_result, reverse_result = await expense_service.update_expense(session, expense_id, current_user, **payload)
    resp = ExpenseResponse.model_validate(entry)
    resp.advance_change = _cursor_change(advance_result)
    resp.reverse_change = _cursor_change(reverse_result)
    return resp


# Delete an expense. Returns 200 with an optional reverse_change (Phase 3, follow-up
# Item 10) emitted when the deleted row was the most-recent linked expense for a commitment.
# Was 204 in Step D+E; switched to 200 + body so the delete confirmation toast can
# announce the schedule walk-back symmetric to create / update.
@router.delete("/{expense_id}", response_model=ExpenseDeleteResponse)
async def delete_expense(
    expense_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> ExpenseDeleteResponse:
    reverse_result = await expense_service.delete_expense(session, expense_id, current_user)
    return ExpenseDeleteResponse(reverse_change=_cursor_change(reverse_result))
