from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.user import User
from app.repositories import income_repository
from app.schemas.income import IncomeListResponse, IncomeResponse
from app.services import account_service, exchange_rate_service, settings_service
from app.utils.metrics import RateLookup, convert_optional


# Maps an entry to its response, converting at the entry's historical date (Phase 3, Step C).
# Income entries are records of past events — the display value reflects the rate in effect when
# the income was received.
def _to_response(entry: IncomeEntry, currency: str | None, lookup: RateLookup | None) -> IncomeResponse:
    resp = IncomeResponse.model_validate(entry)
    resp.converted_amount = convert_optional(entry.amount, entry.currency, currency, lookup, entry.date)
    return resp


# List income entries for a user with optional filters, pagination, and display-currency conversion.
async def list_income(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    category: IncomeCategory | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    currency: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> IncomeListResponse:
    entries, total = await income_repository.list_by_user_filtered(
        session,
        user.id,
        search=search,
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    items: list[IncomeResponse] = []
    skipped: set[str] = set()
    for e in entries:
        resp = _to_response(e, currency, lookup)
        # A requested conversion that yielded null means the rate was missing — flag the row's currency.
        if currency and e.currency != currency and resp.converted_amount is None:
            skipped.add(e.currency)
        items.append(resp)
    return IncomeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        display_currency=currency,
        skipped_currencies=sorted(skipped),
    )


# Get a single income entry by id. Raises NotFoundError if not found.
async def get_income(session: AsyncSession, income_id: int, user: User) -> IncomeEntry:
    entry = await income_repository.get_by_id(session, income_id, user.id)
    if entry is None:
        raise NotFoundError("Income entry not found.")
    return entry


# Get a single income entry as its response schema, converted when a display currency is requested.
async def get_income_response(
    session: AsyncSession,
    income_id: int,
    user: User,
    *,
    currency: str | None = None,
) -> IncomeResponse:
    entry = await get_income(session, income_id, user)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    return _to_response(entry, currency, lookup)


# Create a new income entry.
async def create_income(
    session: AsyncSession,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    category: IncomeCategory | None = None,
    notes: str | None = None,
    account_id: int | None = None,
    source: str = "manual",
) -> IncomeEntry:
    await account_service.validate_account_link(session, user, account_id, currency)
    entry = IncomeEntry(
        user_id=user.id,
        date=date,
        amount=amount,
        currency=currency,
        category=category,
        notes=notes,
        account_id=account_id,
        source=source,
    )
    entry = await income_repository.create(session, entry)
    # Retire the income first-run sample once the user has their first income entry.
    await settings_service.retire_sample(session, user.id, "income")
    await session.commit()
    return entry


# Update an existing income entry. Only provided fields are changed.
async def update_income(
    session: AsyncSession,
    income_id: int,
    user: User,
    **fields: object,
) -> IncomeEntry:
    entry = await get_income(session, income_id, user)
    # Effective account link (request field over stored) must be owned + currency-matched.
    new_account_id = fields["account_id"] if "account_id" in fields else entry.account_id
    new_currency = fields["currency"] if "currency" in fields else entry.currency
    await account_service.validate_account_link(session, user, new_account_id, new_currency)
    for key, value in fields.items():
        setattr(entry, key, value)
    await income_repository.save(session, entry)
    await session.commit()
    await session.refresh(entry)
    return entry


# Delete an income entry.
async def delete_income(session: AsyncSession, income_id: int, user: User) -> None:
    entry = await get_income(session, income_id, user)
    await income_repository.delete(session, entry)
    await session.commit()
