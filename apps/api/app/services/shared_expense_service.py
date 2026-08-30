# Business logic for a group's shared expenses: dividing one bill and recording who fronted it.
#
# Three rules govern everything here.
#
#   * A shared expense records TWO things per member — what they consumed and what they fronted — and
#     both sum to the expense's total. That is the whole reason the group's balances add to zero, so
#     the split rows are always written as a complete set and never patched.
#
#   * Who fronted it is not always one person. Money drawn from a SHARED account was fronted by that
#     pot's owners in their own proportions, and those proportions are read from the ownership ledger
#     AT THE EXPENSE'S DATE and pinned onto the split rows. Pinned rather than derived on every read,
#     because the ledger is replayed: a back-dated ownership event would otherwise silently rewrite a
#     balance two people had already agreed on.
#
#   * A shared expense is group state, so nothing here filters by user_id. Membership is the gate
#     (group_service.require_member) and the RLS policy is what scopes the rows; a caller who is not a
#     member gets the same 404 as a group that does not exist.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AccountCurrencyMismatchError,
    NotFoundError,
    SharedExpenseBeforeAccountOpenedError,
    SharedExpenseFundingPotNotDividedError,
    SharedExpenseFundingScopeError,
    SharedExpensePayerRequiredError,
    SharedExpenseSharedAccountPayerError,
    SplitEntry,
    compute_shares,
)
from app.domain.pot import OwnershipEntry, replay_units, share_values
from app.models.account import Account
from app.models.group import Group, GroupMember
from app.models.shared_expense import SharedExpense, SharedExpenseSplit
from app.models.user import User
from app.repositories import (
    account_repository,
    credit_card_repository,
    group_repository,
    pot_ownership_repository,
    pot_repository,
    shared_expense_repository,
)
from app.schemas.shared_expense import SharedExpenseResponse, SharedExpenseSplitInput, SharedExpenseSplitResponse
from app.services import card_reconciliation_service, exchange_rate_service, group_service
from app.utils.metrics import RateLookup, convert_optional

ZERO = Decimal(0)


# What the funding half of a create/update resolved to: the account or card the money came from, and
# who fronted it — one member for a private source, several for a shared one.
# A NamedTuple would do, but the two are always produced and consumed together and never separately.
class _Funding:
    def __init__(self, account: Account | None, credit_card_id: int | None, paid_by: dict[int, Decimal]) -> None:
        self.account = account
        self.credit_card_id = credit_card_id
        self.paid_by = paid_by


# Builds one shared-expense response, naming every member rather than exposing raw seat ids alone: a
# client rendering the group's expenses needs the names, and a round trip per row would be an N+1
# pushed onto the frontend.
#
# `payer_member_id` / `payer_display_name` are DERIVED here from the splits — the one member who
# fronted the whole amount, or nobody when several did, which is exactly the shared-account case. There
# is no payer column precisely because that case exists.
def _build_response(
    expense: SharedExpense,
    splits: list[SharedExpenseSplit],
    members_by_id: dict[int, GroupMember],
    viewer_member_id: int,
    *,
    account_name: str | None,
    currency: str | None,
    lookup: RateLookup | None,
) -> SharedExpenseResponse:
    payers = [split for split in splits if split.paid_amount > ZERO]
    sole_payer = payers[0] if len(payers) == 1 and payers[0].paid_amount == expense.amount else None
    my_split = next((split for split in splits if split.member_id == viewer_member_id), None)
    return SharedExpenseResponse(
        id=expense.id,
        group_id=expense.group_id,
        date=expense.date,
        amount=expense.amount,
        currency=expense.currency,
        converted_amount=convert_optional(expense.amount, expense.currency, currency, lookup, expense.date),
        category=expense.category,
        notes=expense.notes,
        split_method=expense.split_method,
        paid_from_account_id=expense.paid_from_account_id,
        paid_from_account_name=account_name,
        payment_method=expense.payment_method,
        credit_card_id=expense.credit_card_id,
        payer_member_id=sole_payer.member_id if sole_payer else None,
        payer_display_name=_display_name(members_by_id, sole_payer.member_id) if sole_payer else None,
        my_share=my_split.amount if my_split is not None and my_split.amount > ZERO else None,
        splits=[
            SharedExpenseSplitResponse(
                member_id=split.member_id,
                display_name=_display_name(members_by_id, split.member_id),
                amount=split.amount,
                paid_amount=split.paid_amount,
                is_self=split.member_id == viewer_member_id,
            )
            for split in splits
        ],
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


# A seat's label, falling back rather than raising: a split can only ever name a seat in its own group,
# but a response that failed outright because one roster row was missing would hide the money too.
def _display_name(members_by_id: dict[int, GroupMember], member_id: int) -> str:
    member = members_by_id.get(member_id)
    return member.display_name if member is not None else "—"


# Lists a group's shared expenses with every member's position in each. Members and splits are
# batch-loaded once for the whole list, so the response costs a fixed number of queries regardless of
# how many expenses there are.
async def list_expenses(session: AsyncSession, group_id: int, user: User, *, currency: str | None = None) -> list[SharedExpenseResponse]:
    _, viewer = await group_service.require_member(session, group_id, user)
    expenses = await shared_expense_repository.list_by_group(session, group_id)
    if not expenses:
        return []
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    splits_by_expense = await shared_expense_repository.list_splits_by_expense_ids(session, [expense.id for expense in expenses])
    account_names = await _account_names(session, expenses)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    return [
        _build_response(
            expense,
            splits_by_expense.get(expense.id, []),
            members_by_id,
            viewer.id,
            account_name=account_names.get(expense.paid_from_account_id),
            currency=currency,
            lookup=lookup,
        )
        for expense in expenses
    ]


# The names of every funding account the given expenses draw from, in one query. Denormalized onto the
# response for the reason CardSettlementResponse denormalizes its account name: a row has to say what
# it is even when the client's own account list fails to load, or when the account has been archived.
async def _account_names(session: AsyncSession, expenses: list[SharedExpense]) -> dict[int, str]:
    account_ids = [expense.paid_from_account_id for expense in expenses if expense.paid_from_account_id is not None]
    if not account_ids:
        return {}
    accounts = await account_repository.get_by_ids_any_scope(session, account_ids)
    return {account.id: account.name for account in accounts}


# Loads a shared expense and the caller's seat in its group, or raises NotFoundError. The expense's own
# group is what the membership is checked against, so an id from another group answers 404 rather than
# silently attaching this caller to it.
async def _require_expense(session: AsyncSession, group_id: int, expense_id: int, user: User) -> tuple[SharedExpense, Group, GroupMember]:
    group, viewer = await group_service.require_member(session, group_id, user)
    expense = await shared_expense_repository.get_by_id(session, expense_id)
    if expense is None or expense.group_id != group_id:
        raise NotFoundError("Shared expense not found")
    return (expense, group, viewer)


# Records a shared expense and every member's position in it, in one transaction.
async def create_expense(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    split_method,
    splits: list[SharedExpenseSplitInput],
    category=None,
    notes: str | None = None,
    payer_member_id: int | None = None,
    paid_from_account_id: int | None = None,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
) -> SharedExpenseResponse:
    group, viewer = await group_service.require_member(session, group_id, user)
    members_by_id = await _require_active_seats(session, group_id, [split.member_id for split in splits], payer_member_id)
    shares = compute_shares(amount, split_method, [SplitEntry(member_id=split.member_id, figure=split.figure) for split in splits])
    funding = await _resolve_funding(
        session,
        group_id,
        user,
        members_by_id=members_by_id,
        total=amount,
        currency=currency,
        date=date,
        payer_member_id=payer_member_id,
        paid_from_account_id=paid_from_account_id,
        credit_card_id=credit_card_id,
    )
    expense = await shared_expense_repository.create(
        session,
        SharedExpense(
            group_id=group_id,
            date=date,
            amount=amount,
            currency=currency,
            category=category,
            split_method=split_method,
            paid_from_account_id=funding.account.id if funding.account else None,
            payment_method=payment_method,
            credit_card_id=funding.credit_card_id,
            notes=notes,
            created_by=user.id,
        ),
    )
    written = await _write_splits(session, expense, shares, funding.paid_by)
    if funding.credit_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, funding.credit_card_id, currency, date)
    await session.commit()
    await session.refresh(expense)
    return _build_response(
        expense,
        written,
        members_by_id,
        viewer.id,
        account_name=funding.account.name if funding.account else None,
        currency=None,
        lookup=None,
    )


# Replaces a shared expense and its whole split set.
#
# A FULL replacement rather than a patch, and that is the honest shape: the amount, the method and the
# participants are one interlocking statement, so changing the amount alone would leave exact figures
# that no longer add up to it. The splits are deleted and rewritten for the same reason — a member
# dropped from the split has to lose their row, and a diff that missed one would leave a stale share.
#
# Balances are derived, so they simply recompute; nothing has to be corrected. A settlement that
# already covered the old figure stays exactly as recorded and the balance moves by the difference,
# which is what makes an edit visible rather than silent.
async def update_expense(
    session: AsyncSession,
    group_id: int,
    expense_id: int,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    split_method,
    splits: list[SharedExpenseSplitInput],
    category=None,
    notes: str | None = None,
    payer_member_id: int | None = None,
    paid_from_account_id: int | None = None,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
) -> SharedExpenseResponse:
    expense, _, viewer = await _require_expense(session, group_id, expense_id, user)
    old_card_id, old_currency, old_date = expense.credit_card_id, expense.currency, expense.date
    members_by_id = await _require_active_seats(session, group_id, [split.member_id for split in splits], payer_member_id)
    shares = compute_shares(amount, split_method, [SplitEntry(member_id=split.member_id, figure=split.figure) for split in splits])
    funding = await _resolve_funding(
        session,
        group_id,
        user,
        members_by_id=members_by_id,
        total=amount,
        currency=currency,
        date=date,
        payer_member_id=payer_member_id,
        paid_from_account_id=paid_from_account_id,
        credit_card_id=credit_card_id,
    )
    expense.date = date
    expense.amount = amount
    expense.currency = currency
    expense.category = category
    expense.split_method = split_method
    expense.paid_from_account_id = funding.account.id if funding.account else None
    expense.payment_method = payment_method
    expense.credit_card_id = funding.credit_card_id
    expense.notes = notes
    await shared_expense_repository.save(session, expense)
    await shared_expense_repository.delete_splits(session, expense.id)
    await session.flush()
    written = await _write_splits(session, expense, shares, funding.paid_by)
    # Both the card the charge LEFT and the one it landed on have to be re-flagged: a statement
    # reconciled over either date now covers a different set of charges.
    if old_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, old_card_id, old_currency, old_date)
    if funding.credit_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, funding.credit_card_id, currency, date)
    await session.commit()
    await session.refresh(expense)
    return _build_response(
        expense,
        written,
        members_by_id,
        viewer.id,
        account_name=funding.account.name if funding.account else None,
        currency=None,
        lookup=None,
    )


# Deletes a shared expense; its splits go with it by FK cascade, and the balances recompute.
async def delete_expense(session: AsyncSession, group_id: int, expense_id: int, user: User) -> None:
    expense, _, _ = await _require_expense(session, group_id, expense_id, user)
    card_id, currency, date = expense.credit_card_id, expense.currency, expense.date
    await shared_expense_repository.delete(session, expense)
    if card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, card_id, currency, date)
    await session.commit()


# --- Internal ---


# Resolves every seat a request names — participants and the payer — and refuses any that is not an
# ACTIVE seat of this group. Every id here comes from a request body, so it is checked against the
# group's own roster rather than trusted: a seat id from another group would otherwise attach that
# group's member to this expense, and a deactivated one would put money on somebody who has left.
async def _require_active_seats(session: AsyncSession, group_id: int, member_ids: list[int], payer_member_id: int | None) -> dict[int, GroupMember]:
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    named = [*member_ids, *([payer_member_id] if payer_member_id is not None else [])]
    for member_id in named:
        member = members_by_id.get(member_id)
        if member is None or not member.is_active:
            raise NotFoundError("Group member not found")
    return members_by_id


# Resolves where the money came from and who fronted it — the half of a shared expense the split
# figures cannot say.
#
# Four shapes, and the payer rule differs between them:
#   * a SHARED account (one a pot holds) — the pot's owners fronted it in their proportions on this
#     date, so the request must NOT name a payer, and an undivided pot is refused because there is no
#     honest answer to whose money it was;
#   * a private account, a card, or nothing at all — one member fronted the whole amount and must be
#     named. When an account or card is named it has to be that member's own, or one person could
#     spend from another's.
async def _resolve_funding(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    members_by_id: dict[int, GroupMember],
    total: Decimal,
    currency: str,
    date: date_type,
    payer_member_id: int | None,
    paid_from_account_id: int | None,
    credit_card_id: int | None,
) -> _Funding:
    account = await _load_account(session, paid_from_account_id)
    if account is not None and account.pot_id is not None:
        if payer_member_id is not None:
            raise SharedExpenseSharedAccountPayerError()
        _ensure_account_open(account, date)
        _ensure_account_currency(account, currency)
        paid_by = await _pot_owner_shares(session, account.pot_id, group_id, total=total, date=date)
        return _Funding(account=account, credit_card_id=None, paid_by=paid_by)

    if payer_member_id is None:
        raise SharedExpensePayerRequiredError()
    payer = members_by_id[payer_member_id]
    if account is not None:
        _ensure_owned_by(account.user_id, payer)
        _ensure_account_open(account, date)
        _ensure_account_currency(account, currency)
    card_id = await _load_card_id(session, credit_card_id, payer)
    return _Funding(account=account, credit_card_id=card_id, paid_by={payer_member_id: total})


# Loads a funding account in EITHER scope, or None when none was named. Reachability is RLS's answer:
# a shared account is returned when the policy returns it, and whether this group may spend from it is
# settled below by comparing the pot's group.
async def _load_account(session: AsyncSession, account_id: int | None) -> Account | None:
    if account_id is None:
        return None
    account = await account_repository.get_by_id_any_scope(session, account_id)
    if account is None:
        raise NotFoundError("Account not found")
    return account


# Verifies the named card belongs to the payer's own account, and returns its id. A name-only seat has
# no linked account, so it can never name a card — the ownership check refuses it without a special case.
async def _load_card_id(session: AsyncSession, credit_card_id: int | None, payer: GroupMember) -> int | None:
    if credit_card_id is None:
        return None
    card = await credit_card_repository.get_by_id(session, credit_card_id, payer.user_id) if payer.user_id is not None else None
    if card is None:
        raise NotFoundError("Credit card not found")
    return card.id


# Refuses an instrument that is not the payer's own. Answers 404 rather than 403 for the same reason
# every other cross-tenant check does: confirming the row exists would be the leak.
def _ensure_owned_by(owner_user_id: int | None, payer: GroupMember) -> None:
    if payer.user_id is None or owner_user_id != payer.user_id:
        raise NotFoundError("Account not found")


# Merged constraint (a): an entry's currency must equal its account's. These sums carry ONE amount, so
# a mismatched link would subtract a foreign-currency figure straight from the balance.
def _ensure_account_currency(account: Account, currency: str) -> None:
    if account.currency != currency:
        raise AccountCurrencyMismatchError(currency, account.currency)


# Each leg of the balance union is bounded below by its own account's opening_date, so an expense dated
# earlier would never reach that account's balance while still clearing money the group thinks it spent.
def _ensure_account_open(account: Account, date: date_type) -> None:
    if date < account.opening_date:
        raise SharedExpenseBeforeAccountOpenedError(account.opening_date)


# Splits what a shared account fronted across the pot's owners, in their proportions ON THE EXPENSE'S
# DATE. share_values is the same function the pot page divides a NAV with, so the parts sum to the
# total exactly and the rounding rule cannot differ between the two surfaces.
#
# Two refusals rather than one, because they are different problems: a pot in another group has owners
# this group could never settle with, and an undivided pot has no owners on record at all.
async def _pot_owner_shares(session: AsyncSession, pot_id: int, group_id: int, *, total: Decimal, date: date_type) -> dict[int, Decimal]:
    pot = await pot_repository.get_by_id(session, pot_id)
    if pot is None or pot.group_id != group_id:
        raise SharedExpenseFundingScopeError()
    events = await pot_ownership_repository.list_by_pot(session, pot_id, as_of_date=date)
    balances = replay_units([OwnershipEntry(member_id=e.member_id, units=e.units, counterparty_member_id=e.counterparty_member_id) for e in events])
    shares = share_values(balances, total)
    if not shares:
        raise SharedExpenseFundingPotNotDividedError()
    return shares


# Writes the complete split set: one row per member who consumed something, fronted something, or both.
# The union of the two sides rather than either alone, because a payer who took no part still holds a
# position (D33) and a participant who paid nothing obviously does.
async def _write_splits(
    session: AsyncSession, expense: SharedExpense, shares: dict[int, Decimal], paid_by: dict[int, Decimal]
) -> list[SharedExpenseSplit]:
    member_ids = sorted(set(shares) | set(paid_by))
    return await shared_expense_repository.create_splits(
        session,
        [
            SharedExpenseSplit(
                shared_expense_id=expense.id,
                group_id=expense.group_id,
                member_id=member_id,
                amount=shares.get(member_id, ZERO),
                paid_amount=paid_by.get(member_id, ZERO),
            )
            for member_id in member_ids
        ],
    )
