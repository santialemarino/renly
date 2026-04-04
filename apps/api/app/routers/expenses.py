from datetime import date as date_type

from fastapi import APIRouter, Query, status

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.expense_entry import ExpenseCategory
from app.schemas.expense import ExpenseCreate, ExpenseListResponse, ExpenseResponse, ExpenseUpdate
from app.services import expense_service

router = APIRouter(prefix="/expenses", tags=["expenses"])


# List expenses with optional filters and pagination.
@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Search notes."),
    category: ExpenseCategory | None = Query(default=None, description="Filter by category."),
    payment_method: str | None = Query(default=None, description="Filter by payment method."),
    date_from: date_type | None = Query(default=None, description="Start date (inclusive)."),
    date_to: date_type | None = Query(default=None, description="End date (inclusive)."),
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
    items = [ExpenseResponse.model_validate(e) for e in entries]
    return ExpenseListResponse(items=items, total=total, page=page, page_size=page_size)


# Get a single expense by id.
@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> ExpenseResponse:
    entry = await expense_service.get_expense(session, expense_id, current_user)
    return ExpenseResponse.model_validate(entry)


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
