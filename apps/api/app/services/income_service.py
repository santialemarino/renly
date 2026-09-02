from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError, ensure_not_reconciliation_owned
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.user import User
from app.repositories import group_repository, income_repository
from app.repositories.income_repository import IncomeListRow
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


# Maps one row of the UNIONED list to its response. Built field by field rather than by validating the
# row, because the two branches are different tables and only this projection knows which of its
# fields mean what: `amount` is the caller's own figure either way, `full_amount` is the whole of a
# shared row, and `scope` is what a client must gate its row actions on — ids are unique per table and
# not across them, so a PUT to /income/{id} on a shared row would land on an unrelated private entry.
#
# `group_name` is filled in by the caller, which resolves the names for the whole page in one query.
def _list_row_to_response(row: IncomeListRow, currency: str | None, lookup: RateLookup | None) -> IncomeResponse:
    return IncomeResponse(
        id=row.id,
        date=row.date,
        amount=row.amount,
        currency=row.currency,
        converted_amount=convert_optional(row.amount, row.currency, currency, lookup, row.date),
        category=row.category,
        notes=row.notes,
        account_id=row.account_id,
        source=row.source,
        reconciliation_id=row.reconciliation_id,
        account_reconciliation_id=row.account_reconciliation_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        scope=row.scope,
        group_id=row.group_id,
        group_name=None,
        full_amount=row.full_amount,
    )


# The names of the groups behind the shared rows on this page, in ONE query. A row has to say which
# group it belongs to — a 40,000 share of 100,000 rent renders identically to a solo 40,000 entry
# without it — and resolving that per row would be an N+1 over a list the user paginates through.
async def _group_names(session: AsyncSession, rows: list[IncomeListRow]) -> dict[int, str]:
    group_ids = {row.group_id for row in rows if row.group_id is not None}
    if not group_ids:
        return {}
    return {group.id: group.name for group in await group_repository.get_by_ids(session, sorted(group_ids))}


# List income for a user with optional filters, pagination, and display-currency conversion: their own
# private entries, plus their SHARE of every piece of income their group seats take a share of.
async def list_income(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    category: IncomeCategory | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    currency: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> IncomeListResponse:
    # The caller's own active seats, resolved before the union rather than joined inside it: an
    # `IN (seat ids)` predicate uses the splits' member index, while the join makes Postgres scan every
    # split in the database. An empty list also means the shared branch is not built at all, so a user
    # in no group pays nothing for it.
    member_ids = await group_repository.list_active_member_ids(session, user.id)
    rows, total = await income_repository.list_by_user_filtered(
        session,
        user.id,
        member_ids,
        search=search,
        category=category,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    group_names = await _group_names(session, rows)
    items: list[IncomeResponse] = []
    skipped: set[str] = set()
    for row in rows:
        resp = _list_row_to_response(row, currency, lookup)
        resp.group_name = group_names.get(row.group_id)
        # A requested conversion that yielded null means the rate was missing — flag the row's currency.
        if currency and row.currency != currency and resp.converted_amount is None:
            skipped.add(row.currency)
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


# Update an existing income entry. Only provided fields are changed. Rejects a reconciliation's
# adjustment row with ReconciliationOwnedEntryError (409) — change it via its reconciliation.
async def update_income(
    session: AsyncSession,
    income_id: int,
    user: User,
    **fields: object,
) -> IncomeEntry:
    entry = await get_income(session, income_id, user)
    # A reconciliation's adjustment is derived — its amount IS the recorded difference. Refuse before
    # anything is read or mutated, so a rejected request writes nothing.
    ensure_not_reconciliation_owned(entry.reconciliation_id, entry.account_reconciliation_id)
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


# Delete an income entry. Rejects a reconciliation's adjustment row with
# ReconciliationOwnedEntryError (409) — delete the reconciliation to drop its adjustment.
async def delete_income(session: AsyncSession, income_id: int, user: User) -> None:
    entry = await get_income(session, income_id, user)
    # Deleting the adjustment would orphan its reconciliation: the reverse pointer is ON DELETE SET
    # NULL, so the reconciliation survives still claiming a difference it no longer applies while the
    # balance snaps back. Only deleting the reconciliation cascades cleanly.
    ensure_not_reconciliation_owned(entry.reconciliation_id, entry.account_reconciliation_id)
    await income_repository.delete(session, entry)
    await session.commit()
