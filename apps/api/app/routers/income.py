from datetime import date as date_type

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.currency import DisplayCurrency
from app.deps.db import SessionDep
from app.models.income_entry import IncomeCategory
from app.schemas.income import IncomeCreate, IncomeListResponse, IncomeResponse, IncomeUpdate
from app.services import income_service

router = APIRouter(prefix="/income", tags=["income"])


# List income entries with optional filters, pagination, and currency conversion.
@router.get("", response_model=IncomeListResponse)
async def list_income(
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency,
    search: str | None = Query(default=None, description="Search notes."),
    category: IncomeCategory | None = Query(default=None, description="Filter by category."),
    date_from: date_type | None = Query(default=None, description="Start date (inclusive)."),
    date_to: date_type | None = Query(default=None, description="End date (inclusive)."),
    sort_by: str | None = Query(default=None, description="Column to sort by (date, amount, category)."),
    sort_order: str = Query(default="desc", description="Sort direction (asc or desc)."),
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page."),
) -> IncomeListResponse:
    return await income_service.list_income(
        session,
        current_user,
        search=search,
        category=category,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        currency=currency,
        page=page,
        page_size=page_size,
    )


# Get a single income entry by id (with optional currency conversion).
@router.get("/{income_id}", response_model=IncomeResponse)
async def get_income(
    income_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency,
) -> IncomeResponse:
    return await income_service.get_income_response(session, income_id, current_user, currency=currency)


# Create a new income entry.
@router.post("", response_model=IncomeResponse, status_code=status.HTTP_201_CREATED)
async def create_income(
    body: IncomeCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> IncomeResponse:
    entry = await income_service.create_income(
        session,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        category=body.category,
        notes=body.notes,
        account_id=body.account_id,
    )
    return IncomeResponse.model_validate(entry)


# Update an existing income entry.
@router.put("/{income_id}", response_model=IncomeResponse)
async def update_income(
    income_id: int,
    body: IncomeUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> IncomeResponse:
    payload = body.model_dump(exclude_unset=True)
    entry = await income_service.update_income(session, income_id, current_user, **payload)
    return IncomeResponse.model_validate(entry)


# Delete an income entry. Returns 204.
@router.delete("/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_income(
    income_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await income_service.delete_income(session, income_id, current_user)
