from decimal import Decimal

from sqlalchemy import Numeric, String, case, cast, func, literal, null, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import select

from app.domain.account_movement import MovementKind, MovementSource
from app.models.account import Account
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseEntry
from app.models.income_entry import IncomeEntry
from app.models.transfer import Transfer

# Tie-break rank, one per SOURCE TABLE rather than per MovementKind: two adjustments dated the same
# day share the kind 'adjustment' but come from different tables whose id sequences are independent,
# so (date, kind, id) is not unique while (date, sort_rank, id) is. A total order is what makes
# pagination safe — without one, Postgres may return a row on two pages, or on none.
_RANK_INCOME = 1
_RANK_EXPENSE = 2
_RANK_SETTLEMENT = 3
_RANK_TRANSFER_OUT = 4
_RANK_TRANSFER_IN = 5

_CATEGORY = "category"
_COUNTERPARTY = "counterparty"
_COUNTERPARTY_AMOUNT = "counterparty_amount"
_COUNTERPARTY_CURRENCY = "counterparty_currency"


# NULL placeholders are CAST rather than bare so that a single-branch union (every filtered view is
# one) still gives Postgres a type for the column instead of leaving it `unknown`.
def _null_category():
    return cast(null(), String).label(_CATEGORY)


# The three counterparty columns as NULLs, for the branches that have no other side.
def _null_counterparty():
    return (
        cast(null(), String).label(_COUNTERPARTY),
        cast(null(), Numeric).label(_COUNTERPARTY_AMOUNT),
        cast(null(), String).label(_COUNTERPARTY_CURRENCY),
    )


# An entry's kind, decided per ROW: a reconciliation's adjustment is stored as an ordinary income or
# expense carrying account_reconciliation_id, so only that FK separates a true-up from real money.
def _entry_kind(fk_column, base_kind: MovementKind):
    return case(
        (fk_column.isnot(None), literal(MovementKind.adjustment.value)),
        else_=literal(base_kind.value),
    ).label("kind")


# Restricts a branch to adjustments (True), to everything else (False), or leaves it whole (None).
def _filter_adjustments(stmt, fk_column, adjustments: bool | None):
    if adjustments is None:
        return stmt
    return stmt.where(fk_column.isnot(None) if adjustments else fk_column.is_(None))


# Income linked to the account: money in, so the amount stays positive. The join to accounts bounds
# the branch BELOW by opening_date exactly as income_repository.sum_by_account_ids does —
# opening_balance IS the balance at that date, so an earlier row is already inside it. A ledger that
# listed rows the balance excludes would not add up to the balance it is shown beneath.
def _income_branch(account_id: int, user_id: int, *, adjustments: bool | None):
    stmt = (
        select(
            IncomeEntry.id.label("source_id"),
            literal(MovementSource.income.value).label("source"),
            literal(_RANK_INCOME).label("sort_rank"),
            _entry_kind(IncomeEntry.account_reconciliation_id, MovementKind.income),
            IncomeEntry.date.label("date"),
            IncomeEntry.amount.label("amount"),
            cast(IncomeEntry.category, String).label(_CATEGORY),
            *_null_counterparty(),
            IncomeEntry.notes.label("notes"),
        )
        .join(Account, Account.id == IncomeEntry.account_id)
        .where(
            IncomeEntry.account_id == account_id,
            IncomeEntry.user_id == user_id,
            IncomeEntry.date >= Account.opening_date,
        )
    )
    return _filter_adjustments(stmt, IncomeEntry.account_reconciliation_id, adjustments)


# Expenses linked to the account: money out, so the amount is negated here rather than at the client
# — the ledger reads as one signed column instead of asking every reader to know which kinds subtract.
# The category is cast to text because a UNION cannot reconcile the income_category and
# expense_category Postgres enums.
def _expense_branch(account_id: int, user_id: int, *, adjustments: bool | None):
    stmt = (
        select(
            ExpenseEntry.id.label("source_id"),
            literal(MovementSource.expense.value).label("source"),
            literal(_RANK_EXPENSE).label("sort_rank"),
            _entry_kind(ExpenseEntry.account_reconciliation_id, MovementKind.expense),
            ExpenseEntry.date.label("date"),
            (-ExpenseEntry.amount).label("amount"),
            cast(ExpenseEntry.category, String).label(_CATEGORY),
            *_null_counterparty(),
            ExpenseEntry.notes.label("notes"),
        )
        .join(Account, Account.id == ExpenseEntry.account_id)
        .where(
            ExpenseEntry.account_id == account_id,
            ExpenseEntry.user_id == user_id,
            ExpenseEntry.date >= Account.opening_date,
        )
    )
    return _filter_adjustments(stmt, ExpenseEntry.account_reconciliation_id, adjustments)


# Card bills paid from the account: money out. The card is joined for its name so an ARCHIVED card
# still reads by name — the same reason CardSettlementResponse denormalizes account_name rather than
# leaving the client to join against a list that can fail to load.
def _settlement_branch(account_id: int, user_id: int):
    return (
        select(
            CardSettlement.id.label("source_id"),
            literal(MovementSource.settlement.value).label("source"),
            literal(_RANK_SETTLEMENT).label("sort_rank"),
            literal(MovementKind.settlement.value).label("kind"),
            CardSettlement.date.label("date"),
            (-CardSettlement.amount).label("amount"),
            _null_category(),
            CreditCard.name.label(_COUNTERPARTY),
            cast(null(), Numeric).label(_COUNTERPARTY_AMOUNT),
            cast(null(), String).label(_COUNTERPARTY_CURRENCY),
            CardSettlement.notes.label("notes"),
        )
        .join(Account, Account.id == CardSettlement.account_id)
        .join(CreditCard, CreditCard.id == CardSettlement.credit_card_id)
        .where(
            CardSettlement.account_id == account_id,
            CardSettlement.user_id == user_id,
            CardSettlement.date >= Account.opening_date,
        )
    )


# One leg of a transfer. A transfer can never name the same account twice (a DB CHECK enforces it),
# so an account sees at most one leg of any transfer and the two branches cannot collide. The leg's
# own amount is what moves THIS account and is already in THIS account's currency; the other side
# rides along so a cross-currency transfer can still show the pair that IS its rate record.
def _transfer_branch(account_id: int, user_id: int, *, outgoing: bool):
    counterpart = aliased(Account)
    leg = Transfer.from_account_id if outgoing else Transfer.to_account_id
    other_leg = Transfer.to_account_id if outgoing else Transfer.from_account_id
    amount = -Transfer.from_amount if outgoing else Transfer.to_amount
    counterpart_amount = Transfer.to_amount if outgoing else Transfer.from_amount
    return (
        select(
            Transfer.id.label("source_id"),
            literal(MovementSource.transfer.value).label("source"),
            literal(_RANK_TRANSFER_OUT if outgoing else _RANK_TRANSFER_IN).label("sort_rank"),
            literal(MovementKind.transfer.value).label("kind"),
            Transfer.date.label("date"),
            amount.label("amount"),
            _null_category(),
            counterpart.name.label(_COUNTERPARTY),
            counterpart_amount.label(_COUNTERPARTY_AMOUNT),
            counterpart.currency.label(_COUNTERPARTY_CURRENCY),
            Transfer.notes.label("notes"),
        )
        .join(Account, Account.id == leg)
        .join(counterpart, counterpart.id == other_leg)
        .where(
            leg == account_id,
            Transfer.user_id == user_id,
            Transfer.date >= Account.opening_date,
        )
    )


# The branches a kind filter admits. None means the whole ledger. 'income' and 'expense' deliberately
# EXCLUDE adjustments — a true-up is not money the user earned or spent, and filtering to it is what
# the 'adjustment' kind is for.
def _branches(account_id: int, user_id: int, *, kind: MovementKind | None) -> list:
    if kind is MovementKind.income:
        return [_income_branch(account_id, user_id, adjustments=False)]
    if kind is MovementKind.expense:
        return [_expense_branch(account_id, user_id, adjustments=False)]
    if kind is MovementKind.adjustment:
        return [
            _income_branch(account_id, user_id, adjustments=True),
            _expense_branch(account_id, user_id, adjustments=True),
        ]
    if kind is MovementKind.settlement:
        return [_settlement_branch(account_id, user_id)]
    if kind is MovementKind.transfer:
        return [
            _transfer_branch(account_id, user_id, outgoing=True),
            _transfer_branch(account_id, user_id, outgoing=False),
        ]
    return [
        _income_branch(account_id, user_id, adjustments=None),
        _expense_branch(account_id, user_id, adjustments=None),
        _settlement_branch(account_id, user_id),
        _transfer_branch(account_id, user_id, outgoing=True),
        _transfer_branch(account_id, user_id, outgoing=False),
    ]


# The union of every movement that reaches the account, as a subquery to order and paginate over.
def _union(account_id: int, user_id: int, *, kind: MovementKind | None):
    return union_all(*_branches(account_id, user_id, kind=kind)).subquery()


# The deterministic newest-first total order (see the rank constants).
def _newest_first(sub):
    return (sub.c.date.desc(), sub.c.sort_rank.desc(), sub.c.source_id.desc())


# One page of the account's movements, newest first. Rows are returned as-is; the service turns them
# into AccountMovement and assigns the running balance.
async def list_movements(
    session: AsyncSession,
    account_id: int,
    user_id: int,
    *,
    kind: MovementKind | None = None,
    page: int = 1,
    page_size: int = 25,
) -> list:
    sub = _union(account_id, user_id, kind=kind)
    stmt = select(sub).order_by(*_newest_first(sub)).offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    return list(result.all())


# Total movements matching the filter, for pagination.
async def count_movements(session: AsyncSession, account_id: int, user_id: int, *, kind: MovementKind | None = None) -> int:
    sub = _union(account_id, user_id, kind=kind)
    result = await session.execute(select(func.count()).select_from(sub))
    return result.scalar_one()


# Signed sum of the movements NEWER than the page starting at `offset` — i.e. the first `offset` rows
# of the same newest-first order. The service subtracts it from the account's current balance to get
# the running balance the page opens on, so page 9 is anchored just as exactly as page 1.
#
# Deliberately unfiltered: the running balance is withheld while a kind filter is active, so this is
# only ever asked about the whole ledger.
async def sum_of_newer_movements(session: AsyncSession, account_id: int, user_id: int, *, offset: int) -> Decimal:
    if offset <= 0:
        return Decimal(0)
    sub = _union(account_id, user_id, kind=None)
    newer = select(sub.c.amount).order_by(*_newest_first(sub)).limit(offset).subquery()
    result = await session.execute(select(func.coalesce(func.sum(newer.c.amount), 0)).select_from(newer))
    return Decimal(str(result.scalar_one()))


# Namespace to call repository functions (e.g. account_movement_repository.list_movements).
class AccountMovementRepository:
    list_movements = staticmethod(list_movements)
    count_movements = staticmethod(count_movements)
    sum_of_newer_movements = staticmethod(sum_of_newer_movements)


# Singleton used by services to access account-movement persistence.
account_movement_repository = AccountMovementRepository()
