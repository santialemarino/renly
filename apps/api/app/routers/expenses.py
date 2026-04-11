from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.expense_entry import ExpenseCategory
from app.schemas.expense import ExpenseCreate, ExpenseListResponse, ExpenseResponse, ExpenseUpdate
from app.services import expense_service
from app.utils.metrics import convert_value, get_rate_map
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/expenses", tags=["expenses"])


# Converts an entry's amount if a target currency and rate map are provided.
def _convert_entry(
    resp: ExpenseResponse,
    entry_currency: str,
    target_currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> ExpenseResponse:
    if target_currency and rate_map and entry_currency != target_currency:
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

    rate_map = None
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        rate_map = await get_rate_map(session, dp)

    items = [_convert_entry(ExpenseResponse.model_validate(e), e.currency, currency, rate_map) for e in entries]
    return ExpenseListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        display_currency=currency,
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
        rate_map = await get_rate_map(session, dp)
        resp = _convert_entry(resp, entry.currency, currency, rate_map)
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
