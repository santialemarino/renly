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


# Deletes an event. Balances are derived, so removing one simply recomputes the series — there is no
# stored total to correct afterwards.
async def delete(session: AsyncSession, event: PotOwnershipEvent) -> None:
    await session.delete(event)


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


# Whether any ownership event names one of these accounts on either leg. Used before an account is
# moved into (or out of) a pot: a movement already recorded against it would otherwise end up in a
# different scope than the account it belongs to.
async def exists_for_accounts(session: AsyncSession, account_ids: list[int]) -> bool:
    if not account_ids:
        return False
    result = await session.execute(
        select(PotOwnershipEvent.id)
        .where(or_(PotOwnershipEvent.from_account_id.in_(account_ids), PotOwnershipEvent.to_account_id.in_(account_ids)))
        .limit(1)
    )
    return result.scalars().first() is not None


# Namespace to call repository functions (e.g. pot_ownership_repository.list_by_pot).
class PotOwnershipRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    exists_for_accounts = staticmethod(exists_for_accounts)
    get_by_id = staticmethod(get_by_id)
    list_by_pot = staticmethod(list_by_pot)
    list_by_pots = staticmethod(list_by_pots)
    sum_in_by_account_ids = staticmethod(sum_in_by_account_ids)
    sum_out_by_account_ids = staticmethod(sum_out_by_account_ids)


# Singleton used by services to access ownership-ledger persistence.
pot_ownership_repository = PotOwnershipRepository()
