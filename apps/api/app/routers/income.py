from datetime import date as date_type

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.income_entry import IncomeCategory
from app.schemas.income import IncomeCreate, IncomeListResponse, IncomeResponse, IncomeUpdate
from app.services import income_service
from app.utils.metrics import RateLookup, build_rate_lookup, convert_value
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/income", tags=["income"])


# Converts an entry's amount at the entry's historical date (Phase 3, Step C).
# Income entries are records of past events — display value reflects the rate that was in
# effect when the income was received.
def _convert_entry(
    resp: IncomeResponse,
    entry_currency: str,
    entry_date: date_type,
    target_currency: str | None,
    lookup: RateLookup | None,
) -> IncomeResponse:
    if target_currency and lookup and entry_currency != target_currency:
        rate_map = lookup.get_rate_map_at(entry_date)
        if rate_map:
            resp.converted_amount = convert_value(resp.amount, entry_currency, target_currency, rate_map)
    elif target_currency and entry_currency == target_currency:
        resp.converted_amount = resp.amount
    return resp


# List income entries with optional filters, pagination, and currency conversion.
@router.get("", response_model=IncomeListResponse)
async def list_income(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Search notes."),
    category: IncomeCategory | None = Query(default=None, description="Filter by category."),
    date_from: date_type | None = Query(default=None, description="Start date (inclusive)."),
    date_to: date_type | None = Query(default=None, description="End date (inclusive)."),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page."),
) -> IncomeListResponse:
    entries, total = await income_service.list_income(
        session,
        current_user,
        search=search,
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    lookup: RateLookup | None = None
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        lookup = await build_rate_lookup(session, dp)

    items = [_convert_entry(IncomeResponse.model_validate(e), e.currency, e.date, currency, lookup) for e in entries]
    return IncomeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        display_currency=currency,
    )


# Get a single income entry by id (with optional currency conversion).
@router.get("/{income_id}", response_model=IncomeResponse)
async def get_income(
    income_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> IncomeResponse:
    entry = await income_service.get_income(session, income_id, current_user)
    resp = IncomeResponse.model_validate(entry)
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        lookup = await build_rate_lookup(session, dp)
        resp = _convert_entry(resp, entry.currency, entry.date, currency, lookup)
    return resp


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
