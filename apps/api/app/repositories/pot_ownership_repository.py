# Data access for a pot's ownership ledger.
#
# Every read here is ordered by (date, id) and every balance is derived by replaying what it returns.
# That ordering is not presentational — it IS the semantics, because replaying the same events in a
# different order produces different unit balances. It lives in the repository so no caller can
# accidentally omit it, and so a back-dated event slots into the right place with no other change.
#
# Scoped by the pot's RLS policies, not by user_id: reading needs app_can_view_pot, writing needs
# app_can_write_pot, so a read-only custodian is stopped by the database and not only by the service.

from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import case, or_
from sqlalchemy import delete as delete_stmt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlmodel import func, select

from app.models.account import Account
from app.models.pot import OwnershipEventType, PotOwnershipEvent


# Every event for a pot in replay order, optionally bounded to those on or before a date so a
# historical balance can be derived without loading the whole ledger.
async def list_by_pot(session: AsyncSession, pot_id: int, *, as_of_date: date_type | None = None) -> list[PotOwnershipEvent]:
    stmt = select(PotOwnershipEvent).where(PotOwnershipEvent.pot_id == pot_id)
    if as_of_date is not None:
        stmt = stmt.where(PotOwnershipEvent.date <= as_of_date)
    result = await session.execute(stmt.order_by(PotOwnershipEvent.date, PotOwnershipEvent.id))
    return list(result.scalars().all())


# Events for several pots at once in replay order, keyed by pot id, so a list page showing each pot's
# ownership breakdown costs one query rather than one per pot.
async def list_by_pots(session: AsyncSession, pot_ids: list[int]) -> dict[int, list[PotOwnershipEvent]]:
    if not pot_ids:
        return {}
    result = await session.execute(
        select(PotOwnershipEvent).where(PotOwnershipEvent.pot_id.in_(pot_ids)).order_by(PotOwnershipEvent.date, PotOwnershipEvent.id)
    )
    grouped: dict[int, list[PotOwnershipEvent]] = defaultdict(list)
    for event in result.scalars().all():
        grouped[event.pot_id].append(event)
    return dict(grouped)


# Fetches one event by id, scoped to its pot so an id from another pot cannot be reached by guessing.
async def get_by_id(session: AsyncSession, pot_id: int, event_id: int) -> PotOwnershipEvent | None:
    result = await session.execute(select(PotOwnershipEvent).where(PotOwnershipEvent.id == event_id, PotOwnershipEvent.pot_id == pot_id))
    return result.scalars().first()


# Persists a new event and flushes to get the id.
async def create(session: AsyncSession, event: PotOwnershipEvent) -> PotOwnershipEvent:
    session.add(event)
    await session.flush()
    return event


# Persists several events and flushes ONCE to get their ids. The batch sibling of create, for the
# opening baseline: it writes one row per owner, and flushing per row is a round trip per owner.
async def create_many(session: AsyncSession, events: list[PotOwnershipEvent]) -> list[PotOwnershipEvent]:
    if not events:
        return []
    session.add_all(events)
    await session.flush()
    return events


# Persists a change to an existing event.
#
# The ONLY column any caller ever changes is `confirmed_at` (plus the `updated_at` the trigger keeps),
# which is why the grants narrow UPDATE on this table to exactly those two: the ledger is otherwise
# append-and-delete, and a row whose units could be rewritten after the fact would make every derived
# balance a claim about the present rather than a replay of what happened.
async def save(session: AsyncSession, event: PotOwnershipEvent) -> PotOwnershipEvent:
    session.add(event)
    await session.flush()
    return event


# Deletes an event. Balances are derived, so removing one simply recomputes the series — there is no
# stored total to correct afterwards.
async def delete(session: AsyncSession, event: PotOwnershipEvent) -> None:
    await session.delete(event)


# Deletes EVERY opening event of a pot, in one statement, and returns how many went.
#
# The baseline is one act written as one row per owner (see create_many), so it can only be undone as
# one act: deleting a single row of it leaves a division that sums to less than the value it recorded
# and hands the remaining owners a share nobody agreed to. Returned count so the service can tell an
# opening apart from a no-op without a second query.
async def delete_openings(session: AsyncSession, pot_id: int) -> int:
    result = await session.execute(
        delete_stmt(PotOwnershipEvent).where(PotOwnershipEvent.pot_id == pot_id, PotOwnershipEvent.type == OwnershipEventType.opening)
    )
    return int(result.rowcount or 0)


# Which stored figure a leg is denominated in, and it is NOT the same column on both sides.
# `amount` is the money in the PRIVATE account's currency; `base_amount` is the same movement in the
# pot's base currency, which is the currency of the account the pot holds. A contribution runs
# private -> pot, so its `from` leg is `amount` and its `to` leg is `base_amount`; a withdrawal runs
# the other way and so does the pairing. Summing one column on both legs would credit a
# cross-currency contribution with the source currency's figure — the same class of error the
# transfers table avoids by storing from_amount and to_amount separately.
_FROM_AMOUNT = case((PotOwnershipEvent.type == OwnershipEventType.contribution, PotOwnershipEvent.amount), else_=PotOwnershipEvent.base_amount)
_TO_AMOUNT = case((PotOwnershipEvent.type == OwnershipEventType.contribution, PotOwnershipEvent.base_amount), else_=PotOwnershipEvent.amount)


# Totals for one leg of the money side, mirroring transfer_repository._sum_leg exactly — including
# the `date >= Account.opening_date` bound, without which a movement dated before the account's
# opening balance was measured would be counted twice (once inside the opening figure, once here).
async def _sum_leg(
    session: AsyncSession,
    leg: InstrumentedAttribute,
    amount,
    account_ids: list[int],
    *,
    as_of_date: date_type | None = None,
) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    stmt = (
        select(leg, func.coalesce(func.sum(amount), 0))
        .join(Account, Account.id == leg)
        .where(leg.in_(account_ids), PotOwnershipEvent.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(PotOwnershipEvent.date <= as_of_date)
    result = await session.execute(stmt.group_by(leg))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# Total moved OUT of each account by an ownership event (debits the balance): the private side of a
# contribution, or the pot side of a withdrawal.
# Deliberately NOT filtered by user_id, unlike its transfer sibling. A shared account's balance must
# be the same figure for every member who can see it, so it cannot depend on who is asking; RLS and
# the account_id join are what scope it. `amount` is the source currency's figure, which is the
# account being debited here.
async def sum_out_by_account_ids(session: AsyncSession, account_ids: list[int], *, as_of_date: date_type | None = None) -> dict[int, Decimal]:
    return await _sum_leg(session, PotOwnershipEvent.from_account_id, _FROM_AMOUNT, account_ids, as_of_date=as_of_date)


# Total moved INTO each account by an ownership event (credits the balance).
async def sum_in_by_account_ids(session: AsyncSession, account_ids: list[int], *, as_of_date: date_type | None = None) -> dict[int, Decimal]:
    return await _sum_leg(session, PotOwnershipEvent.to_account_id, _TO_AMOUNT, account_ids, as_of_date=as_of_date)


# Totals for one leg, grouped by (account_id, date), for a caller deriving those accounts' balances at
# MANY dates in one pass. Mirrors _sum_leg above — the same CASE per leg and the same opening_date lower
# bound, plus an `until` upper bound — so the series and the point-in-time balance cannot disagree.
async def _sum_leg_dated(
    session: AsyncSession,
    leg: InstrumentedAttribute,
    amount,
    account_ids: list[int],
    *,
    until: date_type,
) -> list[tuple[int, date_type, Decimal]]:
    if not account_ids:
        return []
    result = await session.execute(
        select(leg, PotOwnershipEvent.date, func.coalesce(func.sum(amount), 0))
        .join(Account, Account.id == leg)
        .where(
            leg.in_(account_ids),
            PotOwnershipEvent.date >= Account.opening_date,
            PotOwnershipEvent.date <= until,
        )
        .group_by(leg, PotOwnershipEvent.date)
    )
    return [(row[0], row[1], Decimal(str(row[2]))) for row in result.all()]


# Dated totals moved OUT of each account by an ownership event.
async def sum_out_by_account_ids_dated(session: AsyncSession, account_ids: list[int], *, until: date_type) -> list[tuple[int, date_type, Decimal]]:
    return await _sum_leg_dated(session, PotOwnershipEvent.from_account_id, _FROM_AMOUNT, account_ids, until=until)


# Dated totals moved INTO each account by an ownership event.
async def sum_in_by_account_ids_dated(session: AsyncSession, account_ids: list[int], *, until: date_type) -> list[tuple[int, date_type, Decimal]]:
    return await _sum_leg_dated(session, PotOwnershipEvent.to_account_id, _TO_AMOUNT, account_ids, until=until)


# WHICH of these accounts an ownership event names on either leg. Asked before an account is moved
# into (or out of) a pot: a movement already recorded against it would otherwise end up in a different
# scope than the account it belongs to.
#
# Scope-free by nature, so it has no user-filtered sibling — an ownership event's two legs sit on
# OPPOSITE sides of the scope boundary by construction, so filtering by user_id would hide exactly the
# leg the question is about. Returns ids rather than a boolean for the same reason its transfer
# counterpart does: one caller names the offending accounts, the other keeps the rest.
async def linked_account_ids(session: AsyncSession, account_ids: list[int]) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(
        select(PotOwnershipEvent.from_account_id, PotOwnershipEvent.to_account_id).where(
            or_(PotOwnershipEvent.from_account_id.in_(account_ids), PotOwnershipEvent.to_account_id.in_(account_ids))
        )
    )
    wanted = set(account_ids)
    return {account_id for row in result.all() for account_id in row if account_id in wanted}


# Namespace to call repository functions (e.g. pot_ownership_repository.list_by_pot).
class PotOwnershipRepository:
    create = staticmethod(create)
    create_many = staticmethod(create_many)
    delete = staticmethod(delete)
    delete_openings = staticmethod(delete_openings)
    get_by_id = staticmethod(get_by_id)
    linked_account_ids = staticmethod(linked_account_ids)
    list_by_pot = staticmethod(list_by_pot)
    list_by_pots = staticmethod(list_by_pots)
    save = staticmethod(save)
    sum_in_by_account_ids = staticmethod(sum_in_by_account_ids)
    sum_in_by_account_ids_dated = staticmethod(sum_in_by_account_ids_dated)
    sum_out_by_account_ids = staticmethod(sum_out_by_account_ids)
    sum_out_by_account_ids_dated = staticmethod(sum_out_by_account_ids_dated)


# Singleton used by services to access ownership-ledger persistence.
pot_ownership_repository = PotOwnershipRepository()
