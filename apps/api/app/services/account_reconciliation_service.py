# Account reconciliation business logic (Bucket 3 #1 — Option F, point-in-time).
# Implements:
#   - compute_account_balance_at(): the account's derived balance as of a date (the cash sibling of
#     card_reconciliation_service.compute_bucket_balance_at).
#   - create_reconciliation(): records the real balance the user read and posts the single adjustment
#     entry that closes the gap, so the balance is true from that date forward.
#
# Reconciliation is the keystone of the "approximate cash" model: linking every movement is optional,
# so the derived balance drifts. Entering the real balance snaps it back with one dated true-up
# instead of demanding the user back-fill history. It is also the universal fee/tax catch-all —
# bank fees, interest, FX spread, and perceptions all land in the difference with no per-fee modelling.
#
# A POT's account reconciles through exactly the same flow, and the ONE thing that differs is where the
# adjustment lands. expense_entries / income_entries keep user_id NOT NULL and carry no pot_id at all
# (§3 — a shared flow lives in its own table), so a private adjustment row could not name a pot-owned
# account; worse, the pot account's balance sums filter on that same column, so such a row would leave
# the drift exactly where it was. The shared adjustment is therefore a shared_expenses / shared_income
# row of the pot's group, funded from the account and split across the pot's OWNERS in their ownership
# proportions on both sides at once — consumed and fronted alike — so it nets to zero between them. The
# drift is the pot's own money: correcting it changes what each owner holds, pro-rata and through the
# pot's NAV, and creates no debt between the people who hold it.
#
# Who may run one on a shared account is every member who can SEE the pot, not only a writer. That is
# the gate the equivalent manual act already carries — shared_expenses_scope_write is group membership
# and _resolve_funding asks only that the pot is visible and divided — so a stricter rule here would be
# theatre, and it would leave a co-owner unable to correct drift on their own money (create_pot grants
# can_write to the creator alone).
#
# Reconciliation stays FORWARD-ONLY in both scopes, and the reason is unchanged by any of the above: it
# posts an adjustment row that changes recorded history, unlike the ownership ledger, which is replayed
# from its events and can therefore take a back-dated one (§5.4).

from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AccountReconciliationBeforeLastError,
    AccountReconciliationBeforeOpeningError,
    AccountReconciliationFutureDateError,
    AccountReconciliationNotLatestError,
    NotFoundError,
    reconciliation_refusal,
)
from app.domain.pot import ONE_HUNDRED
from app.models.account import Account
from app.models.account_reconciliation import AccountReconciliation
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.group import Group, GroupMember
from app.models.group_money_settings import SplitMethod
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.notification import NotificationEvent
from app.models.pot import Pot
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.shared_expense import SharedExpense, SharedExpenseSplit
from app.models.shared_income import IncomeDestination, SharedIncome, SharedIncomeSplit
from app.models.user import User
from app.repositories import (
    account_reconciliation_repository,
    account_repository,
    card_settlement_repository,
    expense_repository,
    group_repository,
    group_settlement_repository,
    income_repository,
    pot_ownership_repository,
    pot_repository,
    shared_expense_repository,
    shared_income_repository,
    transfer_repository,
)
from app.schemas.account_reconciliation import AccountReconciliationResponse, ReconciliationBearerResponse
from app.services import (
    account_service,
    notification_service,
    pot_ownership_service,
    pot_service,
    settings_service,
    shared_audit_service,
)

ZERO = Decimal(0)


# --- Pure helpers ---


# Pure computation: the adjustment the account needs to match reality. Positive means the account
# really holds more than Renly computed (post an income); negative means less (post an expense).
def compute_reconciliation_difference(statement_balance: Decimal, computed_balance: Decimal) -> Decimal:
    return statement_balance - computed_balance


# --- Balance ---


# Derived balance of an account at as_of_date: opening_balance (only once the account has opened) plus
# every movement that reaches it dated on or before that date.
#
# It MIRRORS account_service.get_account_balances bounded in time, and the mirror is the invariant, not
# a resemblance. The two enumerate the same ELEVEN sources, and a source present in one and absent from
# the other does not merely under-report — it makes the reconciliation post an adjustment for money the
# account really did move, permanently, in the app's own drift-closer. Four were missing here: a shared
# expense a member fronted from this private account (the money really left), shared income paid into
# it (it really arrived), and both settlement legs of a settle-up. Reconciling an account that had
# fronted a group's dinner computed a balance too HIGH by the whole bill and then wrote the difference
# in as an expense nobody made.
#
# ▸ So: when a source is added to either list, grep the other one's name and add it there too. The list
# IS the invariant.
#
# It is already correct for a POT's account and needs no scope branch, which is worth stating because it
# looks like an omission. Each user-scoped sum is bounded by `account.user_id`, NULL on a pot's account,
# and the four tables those sums read keep `user_id NOT NULL` — so they contribute nothing, which is the
# true answer: `ensure_private_funding` refuses a private entry funded from a co-owned account, and a
# transfer may not cross a scope boundary. Every source that CAN reach a pot's account is either
# scope-free (both ownership legs, shared expenses, shared income, both group-settlement legs) or reads
# `account_scope_matches`, whose pot branch compares against the JOINED account (transfers). The parity
# test drives both derivations over a pot's account for exactly this reason.
async def compute_account_balance_at(
    session: AsyncSession,
    account: Account,
    as_of_date: date_type,
) -> Decimal:
    if account.id is None:
        return ZERO
    account_ids = [account.id]
    income = await income_repository.sum_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    expenses = await expense_repository.sum_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    settlements = await card_settlement_repository.sum_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    transfers_in = await transfer_repository.sum_in_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    transfers_out = await transfer_repository.sum_out_by_account_ids(session, account_ids, account.user_id, as_of_date=as_of_date)
    ownership_in = await pot_ownership_repository.sum_in_by_account_ids(session, account_ids, as_of_date=as_of_date)
    ownership_out = await pot_ownership_repository.sum_out_by_account_ids(session, account_ids, as_of_date=as_of_date)
    shared_expenses = await shared_expense_repository.sum_by_account_ids(session, account_ids, as_of_date=as_of_date)
    shared_income = await shared_income_repository.sum_by_account_ids(session, account_ids, as_of_date=as_of_date)
    group_settlements_in = await group_settlement_repository.sum_in_by_account_ids(session, account_ids, as_of_date=as_of_date)
    group_settlements_out = await group_settlement_repository.sum_out_by_account_ids(session, account_ids, as_of_date=as_of_date)
    opening = account.opening_balance if account.opening_date <= as_of_date else ZERO
    return (
        opening
        + income.get(account.id, ZERO)
        - expenses.get(account.id, ZERO)
        - settlements.get(account.id, ZERO)
        + transfers_in.get(account.id, ZERO)
        - transfers_out.get(account.id, ZERO)
        + ownership_in.get(account.id, ZERO)
        - ownership_out.get(account.id, ZERO)
        - shared_expenses.get(account.id, ZERO)
        + shared_income.get(account.id, ZERO)
        + group_settlements_in.get(account.id, ZERO)
        - group_settlements_out.get(account.id, ZERO)
    )


# --- Scope ---


# What a POT's account reconciliation needs beyond a private one's: the pot it hangs off and that pot's
# group, which together decide the split, the audit entry and the audience. None means a private
# account, which is every solo user's.
@dataclass(frozen=True)
class _Scope:
    pot: Pot
    group: Group | None
    # The CALLER's own seat, kept because every sentence this produces names them the way their group
    # names them — never users.name, which the group may have overridden and a placeholder never had.
    member: GroupMember


# Resolves the account's scope and takes the row lock that serialises the read-then-act window, or None
# for a private account.
#
# The window is real in both scopes: a reconciliation READS a derived balance and then POSTS a row
# against it, so two concurrent runs each see the pre-adjustment balance, each compute the same
# difference and each post it — the account overshoots by the whole drift, and neither ordering guard
# notices because both rows carry the same date. A shared one has a second window on top: the split is
# a decision taken on the ownership ledger, so a contribution committing between the read and the write
# would divide the difference by proportions that no longer hold.
#
# WHICH row is locked differs by scope, and that is not a stylistic choice. A locking read is governed
# by the UPDATE policy rather than the SELECT one, and `accounts_scope_write` requires pot WRITE access
# — which reconciling deliberately does not — so locking the ACCOUNT of a pot would match no row for a
# read-only co-owner and take no lock at all, silently. `pots_scope_write`'s USING admits a read-only
# seat on purpose, so the pot's own row is lockable by everybody who may reconcile, and it serialises
# every account that pot holds rather than only one.
#
# Taken in the pot-then-account order pot_service.move_holdings establishes (it locks the pot, then
# UPDATEs accounts); a private account has no pot, so only one lock is ever held here.
async def _lock_parent(session: AsyncSession, account: Account, user: User) -> _Scope | None:
    if account.pot_id is None:
        await account_repository.lock_private(session, account.id)
        return None
    # The visibility gate, and the one this act is meant to carry: whoever may SEE the pot may reconcile
    # the account it holds. get_account_in_scope has already let the account through on RLS's answer;
    # this is the pot's own predicate, through the same function every other pot read uses.
    pot, member, _permission = await pot_service.require_visible(session, account.pot_id, user)
    await pot_repository.lock(session, pot.id)
    return _Scope(pot=pot, group=await group_repository.get_by_id(session, pot.group_id), member=member)


# Which sentence the group's trail tells, decided by what the difference turned out to be rather than by
# the caller. `matched` is its own reading rather than an absent variant: a reconciliation that found
# nothing wrong is the outcome people most want to see recorded, and "reconciled the account" alone
# leaves a reader wondering what it cost.
def _audit_variant(difference: Decimal) -> str:
    if difference > ZERO:
        return "surplus"
    return "shortfall" if difference < ZERO else "matched"


# Which sentence the NOTIFICATION tells, or None when there is nothing to tell. A difference of zero
# moved nobody's share, so it earns a trail entry and no message.
def _movement_variant(action: AuditAction, difference: Decimal) -> str | None:
    if difference == ZERO:
        return None
    if action == AuditAction.deleted:
        return "reconciliation_removed"
    return "reconciliation_surplus" if difference > ZERO else "reconciliation_shortfall"


# How the difference divides between the pot's owners, or the refusal a pot nobody has divided earns.
#
# ONE rule with the accounts list, which reports it as `can_reconcile` — the surface that offers the
# action and the write that refuses it cannot disagree, because they call the same function. The two ask
# it at different BOUNDS, and that difference is the whole reason the list cannot express all of it: the
# list asks "has this pot ever been divided", which is all it can know before a date is chosen, while
# the write asks "was it divided ON OR BEFORE the date being reconciled" — a pot divided last week
# cannot bear a correction dated a month ago, and only the request knows that date.
#
# So: two conditions, one filterable and one not. The filterable one is reported per row; the
# date-bounded one refuses at write time with the same error, beside the other date guards.
async def _owner_split(session: AsyncSession, scope: _Scope, *, total: Decimal, date: date_type) -> dict[int, Decimal]:
    shares = await pot_ownership_service.owner_shares(session, scope.pot, total=total, date=date)
    refusal = reconciliation_refusal(scope.pot.id, {scope.pot.id} if shares else set())
    if refusal is not None:
        raise refusal
    return shares


# Records a shared reconciliation in the group's trail and tells the pot's members about it.
#
# The AUDIT entry is written every time, including for a difference of zero: "the account was checked
# and it matched" is a fact about joint money worth keeping, and it is the only trace such a run leaves
# — no adjustment row exists to stand for it.
#
# The NOTIFICATION fires only when something actually moved. What justifies notifying at all is that a
# silent adjustment changes what every co-owner holds; a zero difference changes nothing, and a message
# per routine check is how people learn to mute an event. Removing a non-zero reconciliation notifies
# for the same reason it exists: taking the adjustment away moves every share back.
#
# The audience is `pot_service.list_notifiable_user_ids`, which is the pot's own visibility rule — an
# 'owners' pot must not announce itself to a member the policy hides it from.
async def _announce(
    session: AsyncSession,
    account: Account,
    scope: _Scope,
    user: User,
    action: AuditAction,
    *,
    difference: Decimal,
) -> None:
    variant = _movement_variant(action, difference)
    await shared_audit_service.record(
        session,
        group_id=scope.pot.group_id,
        actor=user,
        entity_type=AuditEntityType.account_reconciliation,
        action=action,
        # The ACCOUNT's id, not the reconciliation's: a deletion entry has to stay meaningful once the
        # row it describes is gone, and every other producer here keys on the thing that survives.
        entity_id=account.id,
        pot_id=scope.pot.id,
        payload={
            "account": account.name,
            "variant": _audit_variant(difference),
            "amount": str(abs(difference)),
            "currency": account.currency,
        },
    )
    if variant is None:
        return
    recipients = await pot_service.list_notifiable_user_ids(session, scope.pot, exclude_user_id=user.id)
    await notification_service.dispatch(
        NotificationEvent.pot_movement,
        recipients,
        pot_service.notification_payload(
            scope.pot,
            scope.group,
            {
                "variant": variant,
                "actor": scope.member.display_name,
                "account": account.name,
                "amount": str(abs(difference)),
                "currency": account.currency,
            },
        ),
    )


# Who would bear a difference on this account, and in what proportion — the disclosure that makes the
# shared reconcile dialog honest about dividing money between people. Empty for a private account, whose
# difference is one person's, and for a pot nobody has divided, which has nobody to bear anything.
#
# Built from `owner_shares` with a total of 100 rather than from `ownership_percentages`, and that is
# what makes it a preview rather than a second opinion: it is the SAME function the split itself calls,
# so the set of seats named here is exactly the set the write will divide between. (The two produce the
# same figures anyway — both quantize to two places and assign the remainder to the largest holder — so
# nothing is lost by taking the one that cannot drift.)
#
# Largest share first, so the reader sees who carries most of it without scanning.
async def list_difference_bearers(
    session: AsyncSession, account: Account, user: User, *, as_of_date: date_type
) -> list[ReconciliationBearerResponse]:
    if account.pot_id is None:
        return []
    pot, _member, _permission = await pot_service.require_visible(session, account.pot_id, user)
    shares = await pot_ownership_service.owner_shares(session, pot, total=ONE_HUNDRED, date=as_of_date)
    if not shares:
        return []
    names = {member.id: member.display_name for member in await group_repository.list_members(session, pot.group_id)}
    bearers = [
        ReconciliationBearerResponse(member_id=member_id, display_name=names.get(member_id, ""), percentage=percentage)
        for member_id, percentage in shares.items()
    ]
    return sorted(bearers, key=lambda bearer: (-bearer.percentage, bearer.display_name))


# --- Reconciliation CRUD ---


# Latest reconciled date per account, in one grouped query. Returns {account_id: as_of_date}; accounts
# never reconciled are absent. Surfaces "last reconciled" on the accounts list without an N+1.
async def get_latest_reconciled_dates(session: AsyncSession, accounts: list[Account], user_id: int) -> dict[int, date_type]:
    account_ids = [a.id for a in accounts if a.id is not None]
    return await account_reconciliation_repository.get_latest_dates_by_account_ids(session, account_ids, user_id)


# Latest reconciled date for one account, or None when it has never been reconciled. Reuses the
# batch query with a single id, the same way compute_account_balance_at reuses the batch sums.
async def get_latest_reconciled_date(session: AsyncSession, account_id: int, user_id: int) -> date_type | None:
    latest = await account_reconciliation_repository.get_latest_dates_by_account_ids(session, [account_id], user_id)
    return latest.get(account_id)


# List an account's reconciliations, newest first, in EITHER scope — a pot's account has a history its
# co-owners are meant to read. Reachability is get_account_in_scope's answer plus RLS's.
async def list_reconciliations(session: AsyncSession, account_id: int, user: User) -> list[AccountReconciliation]:
    await account_service.get_account_in_scope(session, account_id, user)
    return await account_reconciliation_repository.list_by_account(session, account_id)


# Who ran each of the given reconciliations, as the group names them — `{user_id: display_name}` for one
# pot's group. Empty for a private account, whose history has exactly one possible author and needs no
# roster query to say so.
#
# Resolved from group_members rather than from users.name for the reason the audit trail resolves its
# actor the same way: a group shows people under the name the group gave them, and a seat whose account
# is gone has no name to show at all.
async def get_reconciler_names(session: AsyncSession, account: Account) -> dict[int, str]:
    if account.pot_id is None:
        return {}
    pot = await pot_repository.get_by_id(session, account.pot_id)
    if pot is None:
        return {}
    members = await group_repository.list_members(session, pot.group_id)
    return {member.user_id: member.display_name for member in members if member.user_id is not None}


# One reconciliation as the API returns it, with its author resolved from the group's roster.
#
# Here rather than in the router because it reads a MODEL, and routers in this app import none — they
# take schemas in and hand schemas out. `reconciled_by` is null on a private account, whose history has
# exactly one possible author, and on a shared row whose author's seat no longer has an account.
def to_response(reconciliation: AccountReconciliation, names: dict[int, str]) -> AccountReconciliationResponse:
    response = AccountReconciliationResponse.model_validate(reconciliation)
    response.reconciled_by = names.get(reconciliation.created_by) if reconciliation.created_by is not None else None
    return response


# Get a single reconciliation by id, in either scope.
async def get_reconciliation(
    session: AsyncSession,
    account_id: int,
    reconciliation_id: int,
    user: User,
) -> AccountReconciliation:
    await account_service.get_account_in_scope(session, account_id, user)
    reconciliation = await account_reconciliation_repository.get_by_id(session, reconciliation_id, account_id)
    if reconciliation is None:
        raise NotFoundError("Reconciliation not found.")
    return reconciliation


# Record a point-in-time true-up of an account against its real balance. Atomic:
#   1. Compute the derived balance at as_of_date.
#   2. Compute the difference; write the reconciliation row.
#   3. Create the matching adjustment entry (dated on as_of_date, linked to the account so it enters
#      the running balance, tagged source='reconciliation' and category account_adjustment so true-ups
#      are identifiable and separable from real spending) when the difference is non-zero, and patch
#      the back-pointer. NOTE: the category labels the row, it does not exclude it — adjustments still
#      count toward income/expense totals and the category breakdown, exactly like the card
#      reconciliation categories. That is deliberate: money the reconciliation accounts for really did
#      move, it just was not itemised.
# Unlike card reconciliation there is no replace step: a later reconciliation of the same account
# simply appends. Re-running the same date is self-correcting — the earlier adjustment is already in
# the computed balance, so the new difference is zero and no second adjustment is posted. That only
# holds forward, which is why an out-of-order (older) date is rejected: its adjustment would land
# underneath the newer reconciliation, whose date bound cannot see it, skewing the newer balance.
async def create_reconciliation(
    session: AsyncSession,
    account_id: int,
    user: User,
    *,
    as_of_date: date_type,
    statement_balance: Decimal,
) -> AccountReconciliation:
    account = await account_service.get_account_in_scope(session, account_id, user)
    scope = await _lock_parent(session, account, user)
    today = await settings_service.get_user_today(session, user.id)
    if as_of_date > today:
        raise AccountReconciliationFutureDateError()
    if as_of_date < account.opening_date:
        raise AccountReconciliationBeforeOpeningError(account.opening_date)
    last_reconciled = await get_latest_reconciled_date(session, account_id, user.id)
    if last_reconciled is not None and as_of_date < last_reconciled:
        raise AccountReconciliationBeforeLastError(last_reconciled)

    computed = await compute_account_balance_at(session, account, as_of_date)
    difference = compute_reconciliation_difference(statement_balance, computed)
    shares = await _owner_split(session, scope, total=abs(difference), date=as_of_date) if scope else {}

    reconciliation = AccountReconciliation(
        # Exactly one of the two is set — the single-owner CHECK enforces it — and which one decides
        # every downstream read: a pot's reconciliation is visible to, and countable by, each co-owner.
        user_id=user.id if account.pot_id is None else None,
        pot_id=account.pot_id,
        created_by=user.id,
        account_id=account_id,
        as_of_date=as_of_date,
        statement_balance=statement_balance,
        computed_balance=computed,
        difference=difference,
    )
    reconciliation = await account_reconciliation_repository.create(session, reconciliation)

    if scope is None:
        await _post_private_adjustment(session, reconciliation, account, user, as_of_date=as_of_date, difference=difference)
    else:
        await _post_shared_adjustment(session, reconciliation, account, scope, shares, as_of_date=as_of_date, difference=difference)
        await _announce(session, account, scope, user, AuditAction.created, difference=difference)

    await session.commit()
    await session.refresh(reconciliation)
    return reconciliation


# The adjustment a PRIVATE account's difference needs: one expense_entries / income_entries row owned by
# the account's owner, dated on as_of_date and linked to the account so it enters the running balance.
async def _post_private_adjustment(
    session: AsyncSession,
    reconciliation: AccountReconciliation,
    account: Account,
    user: User,
    *,
    as_of_date: date_type,
    difference: Decimal,
) -> None:
    if difference > 0:
        adjustment_income = IncomeEntry(
            user_id=user.id,
            date=as_of_date,
            amount=difference,
            currency=account.currency,
            category=IncomeCategory.account_adjustment,
            account_id=account.id,
            source="reconciliation",
            account_reconciliation_id=reconciliation.id,
        )
        adjustment_income = await income_repository.create(session, adjustment_income)
        reconciliation.adjustment_income_id = adjustment_income.id
        await account_reconciliation_repository.save(session, reconciliation)
    elif difference < 0:
        # payment_method stays NULL: a true-up is not a payment, and a card method would collide with
        # the account link (a card expense never draws an account directly).
        adjustment_expense = ExpenseEntry(
            user_id=user.id,
            date=as_of_date,
            amount=-difference,
            currency=account.currency,
            category=ExpenseCategory.account_adjustment,
            account_id=account.id,
            source="reconciliation",
            account_reconciliation_id=reconciliation.id,
        )
        adjustment_expense = await expense_repository.create(session, adjustment_expense)
        reconciliation.adjustment_expense_id = adjustment_expense.id
        await account_reconciliation_repository.save(session, reconciliation)


# The adjustment a SHARED account's difference needs: one shared_expenses / shared_income row of the
# pot's group, funded from the account, with each owner's figure carried on BOTH sides of their split.
#
# Both sides at once is the whole design. A split row's two columns are what a member consumed (or is
# entitled to) and what they fronted (or received), and a member's balance is the difference between
# them — so writing the same figure twice moves nobody's balance at all. That is the honest record: the
# drift is money the pot already held, so correcting it changes what each owner HOLDS, pro-rata and
# through the pot's NAV, and creates no debt between them. A split that charged the group and credited
# the owners would invent one.
#
# `split_method` is `percentage` because that is what the figures are — each owner's ownership
# percentage of the difference — and it is never re-derived from: a reconciliation-owned row refuses
# every edit, so nothing ever recomputes a split from this value.
#
# The rows are built through the repositories directly rather than through shared_expense_service, for
# the reason the private adjustment is: the `account_adjustment` category is reserved for true-ups and
# the request schemas reject it, and this row names no payer and no participants to resolve.
async def _post_shared_adjustment(
    session: AsyncSession,
    reconciliation: AccountReconciliation,
    account: Account,
    scope: _Scope,
    shares: dict[int, Decimal],
    *,
    as_of_date: date_type,
    difference: Decimal,
) -> None:
    if difference == ZERO:
        return
    if difference > 0:
        income = await shared_income_repository.create(
            session,
            SharedIncome(
                group_id=scope.pot.group_id,
                date=as_of_date,
                amount=difference,
                currency=account.currency,
                category=IncomeCategory.account_adjustment,
                split_method=SplitMethod.percentage,
                # The money is sitting in a pot's account, which IS what joint means (F2). Distributed
                # would claim it reached somebody's hands, and nothing here reached anybody.
                destination=IncomeDestination.joint,
                paid_to_account_id=account.id,
                created_by=reconciliation.created_by,
                account_reconciliation_id=reconciliation.id,
            ),
        )
        await shared_income_repository.create_splits(
            session,
            [
                SharedIncomeSplit(
                    shared_income_id=income.id,
                    group_id=scope.pot.group_id,
                    member_id=member_id,
                    amount=amount,
                    received_amount=amount,
                )
                for member_id, amount in sorted(shares.items())
            ],
        )
        reconciliation.adjustment_shared_income_id = income.id
    else:
        expense = await shared_expense_repository.create(
            session,
            SharedExpense(
                group_id=scope.pot.group_id,
                date=as_of_date,
                amount=-difference,
                currency=account.currency,
                category=ExpenseCategory.account_adjustment,
                split_method=SplitMethod.percentage,
                paid_from_account_id=account.id,
                created_by=reconciliation.created_by,
                account_reconciliation_id=reconciliation.id,
            ),
        )
        await shared_expense_repository.create_splits(
            session,
            [
                SharedExpenseSplit(
                    shared_expense_id=expense.id,
                    group_id=scope.pot.group_id,
                    member_id=member_id,
                    amount=amount,
                    paid_amount=amount,
                )
                for member_id, amount in sorted(shares.items())
            ],
        )
        reconciliation.adjustment_shared_expense_id = expense.id
    # ▸ This `save` is REDUNDANT and kept deliberately, which is worth saying because a mutation sweep
    # deleting it kills no test and there is nothing to add one for. The row was flushed by `create`, so
    # it is already persistent in this session and SQLAlchemy's unit of work flushes the assignment
    # above at commit whether or not `session.add()` is called again — verified by constructing exactly
    # that case against a real database, not reasoned. It stays because the PRIVATE branch calls it in
    # the same place for the same reason, and because "repositories stage, services commit" is the
    # convention every service here follows; dropping it only here would make the pair read as different.
    await account_reconciliation_repository.save(session, reconciliation)


# Delete a reconciliation. Its adjustment row is cascade-dropped via the flow table's
# account_reconciliation_id — expense_entries / income_entries on a private account, shared_expenses /
# shared_income on a pot's — so the balance returns to what it was before the true-up, which is the
# escape hatch for a mistyped balance. A shared adjustment takes its splits with it through their own
# cascade, so no member is left holding a position in an expense that no longer exists.
#
# Only the account's most recent reconciliation can be deleted: an older one's adjustment is already
# inside every later reconciliation's recorded computed_balance, so removing it would silently skew
# those. On a shared account that ordering guard is what the pot's lock protects — two members deleting
# concurrently would otherwise each see the other's row as the latest and both succeed.
async def delete_reconciliation(
    session: AsyncSession,
    account_id: int,
    reconciliation_id: int,
    user: User,
) -> None:
    account = await account_service.get_account_in_scope(session, account_id, user)
    scope = await _lock_parent(session, account, user)
    reconciliation = await account_reconciliation_repository.get_by_id(session, reconciliation_id, account_id)
    if reconciliation is None:
        raise NotFoundError("Reconciliation not found.")
    last_reconciled = await get_latest_reconciled_date(session, account_id, user.id)
    if last_reconciled is not None and reconciliation.as_of_date < last_reconciled:
        raise AccountReconciliationNotLatestError(last_reconciled)
    # Recorded BEFORE the delete, because the entry interpolates the difference the row carries and
    # reading it back afterwards would read a detached object.
    if scope is not None:
        await _announce(session, account, scope, user, AuditAction.deleted, difference=reconciliation.difference)
    await account_reconciliation_repository.delete(session, reconciliation)
    await session.commit()
