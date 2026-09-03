from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import Numeric, String, case, cast, func, literal, null, or_, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import select

from app.domain.account_movement import AccountMovement, MovementKind, MovementRow, MovementSource
from app.models.account import Account
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseEntry
from app.models.group import Group, GroupMember
from app.models.group_settlement import GroupSettlement, GroupSettlementStatus
from app.models.income_entry import IncomeEntry
from app.models.pot import OwnershipEventType, Pot, PotOwnershipEvent
from app.models.shared_expense import SharedExpense
from app.models.shared_income import SharedIncome
from app.models.transfer import Transfer
from app.repositories.card_settlement_repository import settlement_cash_leg
from app.repositories.utils import account_scope_matches_bound

_CATEGORY = "category"
_COUNTERPARTY = "counterparty"
_COUNTERPARTY_AMOUNT = "counterparty_amount"
_COUNTERPARTY_CURRENCY = "counterparty_currency"


# NULL placeholders are CAST rather than bare so that a single-branch union (every filtered view is
# one) still gives Postgres a type for the column instead of leaving it `unknown`.
def _null_counterparty():
    return (
        cast(null(), String).label(_COUNTERPARTY),
        cast(null(), Numeric).label(_COUNTERPARTY_AMOUNT),
        cast(null(), String).label(_COUNTERPARTY_CURRENCY),
    )


# Whether an entry is a reconciliation's adjustment. Both FKs, matching
# domain.reconciliation.ensure_not_reconciliation_owned exactly — keying on only one of them would be
# a third, narrower definition of the same fact, correct today only because the card flow happens not
# to set account_id on its adjustment.
def _is_adjustment(model):
    return or_(model.account_reconciliation_id.isnot(None), model.reconciliation_id.isnot(None))


# One entry branch — income or expense, which are the same query but for the model, the sign, and
# which kind a non-adjustment row reports. `negate` is where "an expense takes money out" is encoded,
# so the ledger reads as one signed column instead of asking every reader to know which kinds
# subtract. A reconciliation's adjustment is an ordinary entry carrying a reconciliation FK, so the
# kind is decided per ROW rather than per branch.
#
# The owner match is the WHOLE predicate here, and that is a property of the two tables rather than an
# omission: expense_entries and income_entries keep `user_id NOT NULL` and have no pot_id at all (§3 —
# a shared flow lives in its own table), so they never name a pot-owned account and the balance sums
# beside them filter on exactly the same column. `transfers` is the one movement table that DOES carry
# a scope, and its branch below matches on it.
#
# `opening_date` is a bound value rather than a join to accounts: the caller already loaded that row
# in this same transaction, and the balance sums only join because they run for MANY accounts at once.
# The bound itself is the same one they apply — opening_balance IS the balance at that date, so an
# earlier row is already inside it, and a ledger listing rows the balance excludes would not add up.
def _entry_branch(
    model,
    account_id: int,
    user_id: int,
    *,
    source: MovementSource,
    base_kind: MovementKind,
    negate: bool,
    opening_date: date_type,
    adjustments: bool | None,
):
    amount = -model.amount if negate else model.amount
    stmt = select(
        model.id.label("source_id"),
        literal(source.value).label("source"),
        case((_is_adjustment(model), literal(MovementKind.adjustment.value)), else_=literal(base_kind.value)).label("kind"),
        model.date.label("date"),
        amount.label("amount"),
        # Cast to text because a UNION cannot reconcile income_category and expense_category, which
        # are two distinct Postgres enum types.
        cast(model.category, String).label(_CATEGORY),
        *_null_counterparty(),
        model.notes.label("notes"),
    ).where(
        model.account_id == account_id,
        model.user_id == user_id,
        model.date >= opening_date,
    )
    if adjustments is not None:
        stmt = stmt.where(_is_adjustment(model) if adjustments else ~_is_adjustment(model))
    return stmt


# Card bills paid from the account: money out. The card is joined for its name so an ARCHIVED card
# still reads by name — the same reason CardSettlementResponse denormalizes account_name rather than
# leaving the client to join against a list that can fail to load. OUTER, so this branch can never be
# stricter than the balance sum it has to agree with: a settlement whose card row became unreachable
# would otherwise drop out of the ledger while still counting in the balance.
#
# The amount is the CASH leg — coalesce(account_amount, amount), the same expression the balance sums use,
# because a settlement may clear a bucket in one currency while drawing another from this account. The
# CARD leg rides along as the counterparty amount/currency, so a cross-currency settlement renders the
# pair exactly like a cross-currency transfer row: the two amounts ARE the record of the rate, and neither
# one alone says what happened.
def _settlement_branch(account_id: int, user_id: int, *, opening_date: date_type):
    return (
        select(
            CardSettlement.id.label("source_id"),
            literal(MovementSource.settlement.value).label("source"),
            literal(MovementKind.settlement.value).label("kind"),
            CardSettlement.date.label("date"),
            (-settlement_cash_leg()).label("amount"),
            cast(null(), String).label(_CATEGORY),
            CreditCard.name.label(_COUNTERPARTY),
            CardSettlement.amount.label(_COUNTERPARTY_AMOUNT),
            CardSettlement.currency.label(_COUNTERPARTY_CURRENCY),
            CardSettlement.notes.label("notes"),
        )
        .outerjoin(CreditCard, CreditCard.id == CardSettlement.credit_card_id)
        .where(
            CardSettlement.account_id == account_id,
            CardSettlement.user_id == user_id,
            CardSettlement.date >= opening_date,
        )
    )


# One leg of a transfer. A transfer can never name the same account twice (a DB CHECK enforces it),
# so an account sees at most one leg of any transfer and the two branches cannot collide — which is
# what lets both share the source 'transfer'. The leg's own amount is what moves THIS account and is
# already in THIS account's currency; the other side rides along so a cross-currency transfer can
# still show the pair that IS its rate record.
def _transfer_branch(account_id: int, user_id: int, *, outgoing: bool, opening_date: date_type, pot_id: int | None):
    counterpart = aliased(Account)
    leg = Transfer.from_account_id if outgoing else Transfer.to_account_id
    other_leg = Transfer.to_account_id if outgoing else Transfer.from_account_id
    amount = -Transfer.from_amount if outgoing else Transfer.to_amount
    counterpart_amount = Transfer.to_amount if outgoing else Transfer.from_amount
    return (
        select(
            Transfer.id.label("source_id"),
            literal(MovementSource.transfer.value).label("source"),
            literal(MovementKind.transfer.value).label("kind"),
            Transfer.date.label("date"),
            amount.label("amount"),
            cast(null(), String).label(_CATEGORY),
            counterpart.name.label(_COUNTERPARTY),
            counterpart_amount.label(_COUNTERPARTY_AMOUNT),
            counterpart.currency.label(_COUNTERPARTY_CURRENCY),
            Transfer.notes.label("notes"),
        )
        .join(counterpart, counterpart.id == other_leg)
        .where(
            leg == account_id,
            account_scope_matches_bound(Transfer, user_id, pot_id),
            Transfer.date >= opening_date,
        )
    )


# A group's shared expense drawn from this account: money out, and the WHOLE amount rather than the
# caller's share. The money really left this account; who owed whom afterwards is the splits' business
# and never the account's — the same reason the balance sum reads the parent's amount.
#
# The group is joined for its name so the row can say what it was, exactly as the settlement branch
# joins the card. INNER rather than outer because a shared expense's group_id is NOT NULL and cascades,
# so the row cannot outlive its group.
#
# No user filter: the row belongs to the group, the membership policy scopes it, and the account leg's
# own read branch keeps it visible to whoever owns the account. A shared account's ledger must not
# depend on who is asking, for the same reason its balance must not.
def _shared_expense_branch(account_id: int, *, opening_date: date_type):
    return (
        select(
            SharedExpense.id.label("source_id"),
            literal(MovementSource.shared_expense.value).label("source"),
            literal(MovementKind.expense.value).label("kind"),
            SharedExpense.date.label("date"),
            (-SharedExpense.amount).label("amount"),
            cast(SharedExpense.category, String).label(_CATEGORY),
            Group.name.label(_COUNTERPARTY),
            cast(null(), Numeric).label(_COUNTERPARTY_AMOUNT),
            cast(null(), String).label(_COUNTERPARTY_CURRENCY),
            SharedExpense.notes.label("notes"),
        )
        .join(Group, Group.id == SharedExpense.group_id)
        .where(
            SharedExpense.paid_from_account_id == account_id,
            SharedExpense.date >= opening_date,
        )
    )


# A group's shared income paid into this account: money in, and the WHOLE amount rather than the
# caller's share. The money really arrived in this account; who owes whom afterwards is the splits'
# business and never the account's — the mirror of the shared-expense branch above, which reads the
# parent's amount for the same reason.
#
# `kind` is 'income' because from the ACCOUNT's point of view that is exactly what it is: money in,
# earned. It is deliberately NOT reported as an adjustment — a reconciliation's true-up is the only
# thing that is, and this is real money.
#
# The group is joined for its name so the row can say what it was. INNER rather than outer because a
# shared-income row's group_id is NOT NULL and cascades, so the row cannot outlive its group.
#
# No user filter: the row belongs to the group, the membership policy scopes it, and the account leg's
# own read branch keeps it visible to whoever owns the account. A shared account's ledger must not
# depend on who is asking, for the same reason its balance must not.
def _shared_income_branch(account_id: int, *, opening_date: date_type):
    return (
        select(
            SharedIncome.id.label("source_id"),
            literal(MovementSource.shared_income.value).label("source"),
            literal(MovementKind.income.value).label("kind"),
            SharedIncome.date.label("date"),
            SharedIncome.amount.label("amount"),
            cast(SharedIncome.category, String).label(_CATEGORY),
            Group.name.label(_COUNTERPARTY),
            cast(null(), Numeric).label(_COUNTERPARTY_AMOUNT),
            cast(null(), String).label(_COUNTERPARTY_CURRENCY),
            SharedIncome.notes.label("notes"),
        )
        .join(Group, Group.id == SharedIncome.group_id)
        .where(
            SharedIncome.paid_to_account_id == account_id,
            SharedIncome.date >= opening_date,
        )
    )


# One leg of a group settlement. It can never name the same account twice (a DB CHECK enforces it), so
# an account sees at most one leg and the two branches cannot collide — which is what lets both share
# the source 'group_settlement', exactly as the two transfer legs share theirs.
#
# The amount is the CASH leg, coalesce(<leg>_amount, amount) — the same expression the balance sums
# use, because a settlement may clear a bucket in one currency while moving another through this
# account. The BUCKET leg rides along as the counterparty amount/currency, so a cross-currency settle
# renders the pair the way a cross-currency transfer does.
#
# A written-off balance never moved money, so it is excluded here for the same reason the balance sums
# exclude it: a ledger row for a payment nobody made would have to be a zero, or a lie.
#
# Like that one, the predicate is unreachable by construction — a write-off cannot carry an account leg
# at all (a CHECK refuses the row), so `leg == account_id` never matches one and no test can tell this
# clause from its absence. Kept for the same reason: it states what these rows mean rather than relying
# on a constraint declared somewhere else.
def _group_settlement_branch(account_id: int, *, outgoing: bool, opening_date: date_type):
    leg = GroupSettlement.from_account_id if outgoing else GroupSettlement.to_account_id
    leg_amount = GroupSettlement.from_amount if outgoing else GroupSettlement.to_amount
    counterpart_seat = GroupSettlement.to_member_id if outgoing else GroupSettlement.from_member_id
    cash = func.coalesce(leg_amount, GroupSettlement.amount)
    return (
        select(
            GroupSettlement.id.label("source_id"),
            literal(MovementSource.group_settlement.value).label("source"),
            literal(MovementKind.group_settlement.value).label("kind"),
            GroupSettlement.date.label("date"),
            (-cash if outgoing else cash).label("amount"),
            cast(null(), String).label(_CATEGORY),
            GroupMember.display_name.label(_COUNTERPARTY),
            GroupSettlement.amount.label(_COUNTERPARTY_AMOUNT),
            GroupSettlement.currency.label(_COUNTERPARTY_CURRENCY),
            GroupSettlement.notes.label("notes"),
        )
        .join(GroupMember, GroupMember.id == counterpart_seat)
        .where(
            leg == account_id,
            GroupSettlement.status != GroupSettlementStatus.written_off,
            GroupSettlement.date >= opening_date,
        )
    )


# One leg of an ownership event — a contribution into a co-owned pot or a withdrawal out of one.
#
# This branch is what makes the ledger and the balance describe the same row set. Without it an
# account that funded a contribution reports a balance no visible row explains, and every
# `balance_after` above that point is wrong by the contribution — measured on a real database before
# this was written: an account with 100,000 opening and one 5,000 contribution read 95,000 from the
# balance and 100,000 from the ledger.
#
# The two legs are denominated differently and the CASE per leg is the same one the balance sums use:
# a contribution runs private -> pot, so its `from` leg moves `amount` (the private account's currency)
# and its `to` leg moves `base_amount` (the pot's); a withdrawal reverses both. Summing one column on
# both legs would credit a cross-currency contribution with the source currency's figure.
#
# The counterparty is the pot, falling back to its group's name — A4 leaves a group's default pot
# unnamed, so the group's name is the only thing there is to call it, and it is what the UI shows too.
def _ownership_branch(account_id: int, *, outgoing: bool, opening_date: date_type):
    leg = PotOwnershipEvent.from_account_id if outgoing else PotOwnershipEvent.to_account_id
    is_contribution = PotOwnershipEvent.type == OwnershipEventType.contribution
    near = case((is_contribution, PotOwnershipEvent.amount), else_=PotOwnershipEvent.base_amount)
    far = case((is_contribution, PotOwnershipEvent.base_amount), else_=PotOwnershipEvent.amount)
    this_leg = near if outgoing else far
    other_leg = far if outgoing else near
    return (
        select(
            PotOwnershipEvent.id.label("source_id"),
            literal(MovementSource.ownership.value).label("source"),
            literal(MovementKind.ownership.value).label("kind"),
            PotOwnershipEvent.date.label("date"),
            (-this_leg if outgoing else this_leg).label("amount"),
            cast(null(), String).label(_CATEGORY),
            func.coalesce(Pot.name, Group.name).label(_COUNTERPARTY),
            other_leg.label(_COUNTERPARTY_AMOUNT),
            func.coalesce(PotOwnershipEvent.amount_currency, Pot.base_currency).label(_COUNTERPARTY_CURRENCY),
            PotOwnershipEvent.notes.label("notes"),
        )
        .join(Pot, Pot.id == PotOwnershipEvent.pot_id)
        .join(Group, Group.id == Pot.group_id)
        .where(
            leg == account_id,
            PotOwnershipEvent.date >= opening_date,
        )
    )


# The branches a kind filter admits. None means the whole ledger. 'income' and 'expense' deliberately
# EXCLUDE adjustments — a true-up is not money the user earned or spent, and filtering to it is what
# the 'adjustment' kind is for.
def _branches(account_id: int, user_id: int, *, kind: MovementKind | None, opening_date: date_type, pot_id: int | None) -> list:
    def entry(spec, adjustments):
        model, source, base_kind, negate = spec
        return _entry_branch(
            model,
            account_id,
            user_id,
            source=source,
            base_kind=base_kind,
            negate=negate,
            opening_date=opening_date,
            adjustments=adjustments,
        )

    income = (IncomeEntry, MovementSource.income, MovementKind.income, False)
    expense = (ExpenseEntry, MovementSource.expense, MovementKind.expense, True)

    if kind == MovementKind.income:
        return [entry(income, adjustments=False), _shared_income_branch(account_id, opening_date=opening_date)]
    if kind == MovementKind.expense:
        return [entry(expense, adjustments=False), _shared_expense_branch(account_id, opening_date=opening_date)]
    if kind == MovementKind.adjustment:
        return [entry(income, adjustments=True), entry(expense, adjustments=True)]
    if kind == MovementKind.settlement:
        return [_settlement_branch(account_id, user_id, opening_date=opening_date)]
    if kind == MovementKind.group_settlement:
        return [
            _group_settlement_branch(account_id, outgoing=True, opening_date=opening_date),
            _group_settlement_branch(account_id, outgoing=False, opening_date=opening_date),
        ]
    if kind == MovementKind.ownership:
        return [
            _ownership_branch(account_id, outgoing=True, opening_date=opening_date),
            _ownership_branch(account_id, outgoing=False, opening_date=opening_date),
        ]
    if kind == MovementKind.transfer:
        return [
            _transfer_branch(account_id, user_id, outgoing=True, opening_date=opening_date, pot_id=pot_id),
            _transfer_branch(account_id, user_id, outgoing=False, opening_date=opening_date, pot_id=pot_id),
        ]
    return [
        entry(income, adjustments=None),
        entry(expense, adjustments=None),
        _shared_expense_branch(account_id, opening_date=opening_date),
        _shared_income_branch(account_id, opening_date=opening_date),
        _settlement_branch(account_id, user_id, opening_date=opening_date),
        _group_settlement_branch(account_id, outgoing=True, opening_date=opening_date),
        _group_settlement_branch(account_id, outgoing=False, opening_date=opening_date),
        _ownership_branch(account_id, outgoing=True, opening_date=opening_date),
        _ownership_branch(account_id, outgoing=False, opening_date=opening_date),
        _transfer_branch(account_id, user_id, outgoing=True, opening_date=opening_date, pot_id=pot_id),
        _transfer_branch(account_id, user_id, outgoing=False, opening_date=opening_date, pot_id=pot_id),
    ]


# The union of every movement the filter admits, as a subquery to order and paginate over.
def _union(account_id: int, user_id: int, *, kind: MovementKind | None, opening_date: date_type, pot_id: int | None):
    return union_all(*_branches(account_id, user_id, kind=kind, opening_date=opening_date, pot_id=pot_id)).subquery()


# Newest first, and a TOTAL order: (date, source, source_id) is unique because `source` names the
# table and `source_id` is its primary key. Without a total order Postgres may return a row on two
# pages, or on none. `source` doubles as the same-date tie-break, so no extra sort column is needed.
def _newest_first(sub):
    return (sub.c.date.desc(), sub.c.source.desc(), sub.c.source_id.desc())


# Maps one row of the union's projection into the domain object — the only place that shape is read,
# so it cannot leak into the service.
def _to_row(row) -> MovementRow:
    return MovementRow(
        movement=AccountMovement(
            source=MovementSource(row.source),
            source_id=row.source_id,
            kind=MovementKind(row.kind),
            date=row.date,
            amount=row.amount,
            category=row.category,
            counterparty=row.counterparty,
            counterparty_amount=row.counterparty_amount,
            counterparty_currency=row.counterparty_currency,
            notes=row.notes,
        ),
        running_total=row.running_total,
    )


# One page of the account's movements, newest first, with the filter's total — all in ONE pass over
# the union. `count(*) OVER ()` carries the unpaginated total on every row, and a running SUM window
# carries Σ amounts from the newest row through each one, which is what the service needs to place the
# page's balances. Computing both here rather than as two more statements matters because no index can
# remove this query's sort — the planner appends the branches and top-N sorts the account's whole
# history, so every extra statement is another full pass over it.
#
# Returns ([], 0) for a page past the end; the caller clamps and re-asks, which keeps the common
# in-range case at a single query.
async def list_movements(
    session: AsyncSession,
    account_id: int,
    user_id: int,
    *,
    opening_date: date_type,
    pot_id: int | None = None,
    kind: MovementKind | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[MovementRow], int]:
    sub = _union(account_id, user_id, kind=kind, opening_date=opening_date, pot_id=pot_id)
    windowed = select(
        sub,
        func.count().over().label("total"),
        func.sum(sub.c.amount).over(order_by=_newest_first(sub), rows=(None, 0)).label("running_total"),
    ).subquery()
    stmt = select(windowed).order_by(*_newest_first(windowed)).offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    rows = result.all()
    if not rows:
        return [], 0
    return [_to_row(r) for r in rows], int(rows[0].total)


# Total movements matching the filter, without fetching any. Only needed to clamp a page past the end
# — list_movements carries the total itself whenever it returns rows.
async def count_movements(
    session: AsyncSession,
    account_id: int,
    user_id: int,
    *,
    opening_date: date_type,
    pot_id: int | None = None,
    kind: MovementKind | None = None,
) -> int:
    sub = _union(account_id, user_id, kind=kind, opening_date=opening_date, pot_id=pot_id)
    result = await session.execute(select(func.count()).select_from(sub))
    return int(result.scalar_one())


# Signed sum of every movement that reaches the account — the ledger's own answer to what the account
# holds. Deliberately NOT used to render anything: the ledger anchors on
# account_service.get_account_balances precisely so it never becomes a second source of truth. It
# exists for the drift guard, which proves the two still describe the same row set.
async def sum_movements(session: AsyncSession, account_id: int, user_id: int, *, opening_date: date_type, pot_id: int | None = None) -> Decimal:
    sub = _union(account_id, user_id, kind=None, opening_date=opening_date, pot_id=pot_id)
    result = await session.execute(select(func.coalesce(func.sum(sub.c.amount), 0)).select_from(sub))
    return Decimal(str(result.scalar_one()))


# Namespace to call repository functions (e.g. account_movement_repository.list_movements).
class AccountMovementRepository:
    list_movements = staticmethod(list_movements)
    count_movements = staticmethod(count_movements)
    sum_movements = staticmethod(sum_movements)


# Singleton used by services to access account-movement persistence.
account_movement_repository = AccountMovementRepository()
