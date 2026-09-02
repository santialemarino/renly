# Business logic for a group's shared income: dividing money that arrives and recording who holds it.
#
# Four rules govern everything here, and the first three are the expense mirror with the two sides
# swapped.
#
#   * Shared income records TWO things per member — what they are ENTITLED to and what actually
#     REACHED them — and both sum to the income's total. That is the whole reason the group's balances
#     add to zero, so the split rows are always written as a complete set and never patched.
#
#   * Who received it is not always one person. Money that arrives in a SHARED account was received by
#     that pot's owners in their own proportions, read from the ownership ledger AT THE INCOME'S DATE
#     and pinned onto the split rows. Pinned rather than derived on every read, because the ledger is
#     replayed: a back-dated ownership event would otherwise silently rewrite a balance two people had
#     already agreed on.
#
#   * Shared income is group state, so nothing here filters by user_id. Membership is the gate
#     (group_service.require_member) and the RLS policy is what scopes the rows; a caller who is not a
#     member gets the same 404 as a group that does not exist.
#
#   * The DESTINATION (F2) is the request's own field and the discriminator for everything else.
#     `joint` means the money landed in a shared account a pot holds, so the pot is worth more and
#     every owner's share rises in proportion — no units are issued and nobody's percentage moves,
#     because pro-rata growth needs no ownership event at all. `distributed` means it reached one
#     person, who then holds whatever exceeds their own share as a balance. Money arriving from outside
#     the household crosses no scope boundary on the way in, which is why neither destination is an
#     ownership event: only money that was ALREADY in a pot can leave one, and that is a withdrawal.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AccountCurrencyMismatchError,
    NotFoundError,
    SharedIncomeBeforeAccountOpenedError,
    SharedIncomeDestinationPotNotDividedError,
    SharedIncomeDestinationScopeError,
    SharedIncomeDistributedSharedAccountError,
    SharedIncomeJointAccountRequiredError,
    SharedIncomeJointReceiverError,
    SharedIncomeReceiverRequiredError,
    SharedIncomeSourceScopeError,
    SplitEntry,
    compute_shares,
)
from app.models.account import Account
from app.models.group import Group, GroupMember
from app.models.investment import Investment
from app.models.notification import NotificationEvent
from app.models.shared_income import IncomeDestination, SharedIncome, SharedIncomeSplit
from app.models.user import User
from app.repositories import (
    account_repository,
    group_repository,
    investment_repository,
    pot_repository,
    shared_income_repository,
)
from app.schemas.shared_income import SharedIncomeResponse, SharedIncomeSplitInput, SharedIncomeSplitResponse
from app.services import exchange_rate_service, group_service, notification_service, pot_ownership_service
from app.utils.metrics import RateLookup, convert_optional

ZERO = Decimal(0)


# What the destination half of a create/update resolved to: the account the money arrived in, and who
# received it — one member when it was distributed, several when a pot's account took it in.
# A NamedTuple would do, but the two are always produced and consumed together and never separately.
class _Destination:
    def __init__(self, account: Account | None, received_by: dict[int, Decimal]) -> None:
        self.account = account
        self.received_by = received_by


# Builds one shared-income response, naming every member rather than exposing raw seat ids alone: a
# client rendering the group's income needs the names, and a round trip per row would be an N+1 pushed
# onto the frontend.
#
# `received_by_member_id` / `received_by_display_name` are DERIVED here rather than stored — there is no
# receiver column precisely because money arriving in a shared account has no single recipient.
#
# The stored DESTINATION is what decides it, never the shape of the splits. Reading the splits alone
# gets a single-owner pot wrong: its one owner receives the whole amount, which is indistinguishable
# from one person collecting it — and a pot with exactly one owner is a state the design explicitly
# supports (it is where a buy-out ends). Saying "Nico received it" about money that went into the joint
# account reads as Nico taking it personally, which is a different claim about a different pot of money.
def _build_response(
    income: SharedIncome,
    splits: list[SharedIncomeSplit],
    members_by_id: dict[int, GroupMember],
    viewer_member_id: int,
    *,
    account_name: str | None,
    source_name: str | None,
    currency: str | None,
    lookup: RateLookup | None,
) -> SharedIncomeResponse:
    receivers = [split for split in splits if split.received_amount > ZERO]
    sole_receiver = (
        None
        if income.destination == IncomeDestination.joint
        else next((r for r in receivers if len(receivers) == 1 and r.received_amount == income.amount), None)
    )
    my_split = next((split for split in splits if split.member_id == viewer_member_id), None)
    return SharedIncomeResponse(
        id=income.id,
        group_id=income.group_id,
        date=income.date,
        amount=income.amount,
        currency=income.currency,
        converted_amount=convert_optional(income.amount, income.currency, currency, lookup, income.date),
        category=income.category,
        notes=income.notes,
        split_method=income.split_method,
        destination=income.destination,
        source_investment_id=income.source_investment_id,
        source_investment_name=source_name,
        paid_to_account_id=income.paid_to_account_id,
        paid_to_account_name=account_name,
        received_by_member_id=sole_receiver.member_id if sole_receiver else None,
        received_by_display_name=_display_name(members_by_id, sole_receiver.member_id) if sole_receiver else None,
        my_share=my_split.amount if my_split is not None and my_split.amount > ZERO else None,
        splits=[
            SharedIncomeSplitResponse(
                member_id=split.member_id,
                display_name=_display_name(members_by_id, split.member_id),
                amount=split.amount,
                received_amount=split.received_amount,
                is_self=split.member_id == viewer_member_id,
            )
            for split in splits
        ],
        created_at=income.created_at,
        updated_at=income.updated_at,
    )


# A seat's label, falling back rather than raising: a split can only ever name a seat in its own group,
# but a response that failed outright because one roster row was missing would hide the money too.
def _display_name(members_by_id: dict[int, GroupMember], member_id: int) -> str:
    member = members_by_id.get(member_id)
    return member.display_name if member is not None else "—"


# Lists a group's shared income with every member's position in each row. Members, splits, destination
# accounts and source assets are batch-loaded once for the whole list, so the response costs a fixed
# number of queries regardless of how many rows there are.
async def list_income(session: AsyncSession, group_id: int, user: User, *, currency: str | None = None) -> list[SharedIncomeResponse]:
    _, viewer = await group_service.require_member(session, group_id, user)
    rows = await shared_income_repository.list_by_group(session, group_id)
    if not rows:
        return []
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    splits_by_income = await shared_income_repository.list_splits_by_income_ids(session, [row.id for row in rows])
    accounts = await _destination_accounts(session, rows)
    sources = await _source_investments(session, rows)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    return [
        _build_response(
            row,
            splits_by_income.get(row.id, []),
            members_by_id,
            viewer.id,
            account_name=_named(accounts, row.paid_to_account_id),
            source_name=_named(sources, row.source_investment_id),
            currency=currency,
            lookup=lookup,
        )
        for row in rows
    ]


# Every destination account the given rows name, in one query, keyed by id.
#
# The NAME is denormalized onto the response for the reason CardSettlementResponse denormalizes its
# own: a row has to say what it is even when the client's account list fails to load, or when the
# account has been archived.
async def _destination_accounts(session: AsyncSession, rows: list[SharedIncome]) -> dict[int, Account]:
    account_ids = [row.paid_to_account_id for row in rows if row.paid_to_account_id is not None]
    if not account_ids:
        return {}
    return {account.id: account for account in await account_repository.get_by_ids_any_scope(session, account_ids)}


# Every source asset the given rows name, in one query, keyed by id. Same denormalization argument as
# the accounts above; the id is validated on write, so what is resolved here is only the label.
async def _source_investments(session: AsyncSession, rows: list[SharedIncome]) -> dict[int, Investment]:
    investment_ids = [row.source_investment_id for row in rows if row.source_investment_id is not None]
    if not investment_ids:
        return {}
    return {investment.id: investment for investment in await investment_repository.get_by_ids_any_scope(session, investment_ids)}


# The name of a row's account or source asset, or None when it names none — or names one the caller
# cannot see. Both cases are real and neither is an error: a source asset sits in a pot the caller may
# be excluded from (V4), and a destination account may be another member's private one, which the
# row-level policies hide entirely.
def _named(rows_by_id: dict[int, Account] | dict[int, Investment], row_id: int | None) -> str | None:
    if row_id is None:
        return None
    row = rows_by_id.get(row_id)
    return row.name if row is not None else None


# Loads a shared-income row and the caller's seat in its group, or raises NotFoundError. The row's own
# group is what the membership is checked against, so an id from another group answers 404 rather than
# silently attaching this caller to it.
async def _require_income(session: AsyncSession, group_id: int, income_id: int, user: User) -> tuple[SharedIncome, Group, GroupMember]:
    group, viewer = await group_service.require_member(session, group_id, user)
    income = await shared_income_repository.get_by_id(session, income_id)
    if income is None or income.group_id != group_id:
        raise NotFoundError("Shared income not found")
    return (income, group, viewer)


# Records a piece of shared income and every member's position in it, in one transaction.
async def create_income(
    session: AsyncSession,
    group_id: int,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    split_method,
    splits: list[SharedIncomeSplitInput],
    destination: IncomeDestination,
    category=None,
    notes: str | None = None,
    source_investment_id: int | None = None,
    received_by_member_id: int | None = None,
    paid_to_account_id: int | None = None,
) -> SharedIncomeResponse:
    group, viewer = await group_service.require_member(session, group_id, user)
    members_by_id = await _require_active_seats(session, group_id, [split.member_id for split in splits], received_by_member_id)
    shares = compute_shares(amount, split_method, [SplitEntry(member_id=split.member_id, figure=split.figure) for split in splits])
    source = await _resolve_source(session, group_id, source_investment_id)
    landing = await _resolve_destination(
        session,
        group_id,
        members_by_id=members_by_id,
        total=amount,
        currency=currency,
        date=date,
        destination=destination,
        received_by_member_id=received_by_member_id,
        paid_to_account_id=paid_to_account_id,
    )
    income = await shared_income_repository.create(
        session,
        SharedIncome(
            group_id=group_id,
            date=date,
            amount=amount,
            currency=currency,
            category=category,
            split_method=split_method,
            destination=destination,
            source_investment_id=source.id if source else None,
            paid_to_account_id=landing.account.id if landing.account else None,
            notes=notes,
            created_by=user.id,
        ),
    )
    written = await _write_splits(session, income, shares, landing.received_by)
    # Resolved before the commit, so a failure reading the roster fails the whole use case with nothing
    # written rather than 500-ing a request whose income has already landed.
    recipients = await group_service.list_notifiable_user_ids(session, group_id, exclude_user_id=user.id)
    await session.commit()
    await session.refresh(income)

    # The TOTAL received, in its own currency — the expense mirror, and for the same reason: one payload
    # is shared by every recipient, so it can never carry somebody else's share as if it were the
    # reader's. The DESTINATION is deliberately absent from the copy too; whether the money stayed joint
    # or was distributed is what the row's own page says, and it is the fact most likely to be edited.
    # An UPDATE notifies nobody, exactly as an edited expense does not: a correction is not news.
    await notification_service.dispatch(
        NotificationEvent.shared_income_added,
        recipients,
        {"group_id": group_id, "group": group.name, "actor": viewer.display_name, "amount": str(amount), "currency": currency},
    )
    return _build_response(
        income,
        written,
        members_by_id,
        viewer.id,
        account_name=landing.account.name if landing.account else None,
        source_name=source.name if source else None,
        currency=None,
        lookup=None,
    )


# Replaces a piece of shared income and its whole split set.
#
# A FULL replacement rather than a patch, and that is the honest shape: the amount, the method and the
# participants are one interlocking statement, so changing the amount alone would leave exact figures
# that no longer add up to it. The splits are deleted and rewritten for the same reason — a member
# dropped from the split has to lose their row, and a diff that missed one would leave a stale share.
#
# Balances are derived, so they simply recompute; nothing has to be corrected. A settlement that
# already covered the old figure stays exactly as recorded and the balance moves by the difference,
# which is what makes an edit visible rather than silent.
async def update_income(
    session: AsyncSession,
    group_id: int,
    income_id: int,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    split_method,
    splits: list[SharedIncomeSplitInput],
    destination: IncomeDestination,
    category=None,
    notes: str | None = None,
    source_investment_id: int | None = None,
    received_by_member_id: int | None = None,
    paid_to_account_id: int | None = None,
) -> SharedIncomeResponse:
    income, _, viewer = await _require_income(session, group_id, income_id, user)
    members_by_id = await _require_active_seats(session, group_id, [split.member_id for split in splits], received_by_member_id)
    shares = compute_shares(amount, split_method, [SplitEntry(member_id=split.member_id, figure=split.figure) for split in splits])
    source = await _resolve_source(session, group_id, source_investment_id)
    landing = await _resolve_destination(
        session,
        group_id,
        members_by_id=members_by_id,
        total=amount,
        currency=currency,
        date=date,
        destination=destination,
        received_by_member_id=received_by_member_id,
        paid_to_account_id=paid_to_account_id,
    )
    income.date = date
    income.amount = amount
    income.currency = currency
    income.category = category
    income.split_method = split_method
    income.destination = destination
    income.source_investment_id = source.id if source else None
    income.paid_to_account_id = landing.account.id if landing.account else None
    income.notes = notes
    await shared_income_repository.save(session, income)
    await shared_income_repository.delete_splits(session, income.id)
    await session.flush()
    written = await _write_splits(session, income, shares, landing.received_by)
    await session.commit()
    await session.refresh(income)
    return _build_response(
        income,
        written,
        members_by_id,
        viewer.id,
        account_name=landing.account.name if landing.account else None,
        source_name=source.name if source else None,
        currency=None,
        lookup=None,
    )


# Deletes a piece of shared income; its splits go with it by FK cascade, and the balances recompute.
async def delete_income(session: AsyncSession, group_id: int, income_id: int, user: User) -> None:
    income, _, _ = await _require_income(session, group_id, income_id, user)
    await shared_income_repository.delete(session, income)
    await session.commit()


# --- Internal ---


# Resolves every seat a request names — participants and the recipient — and refuses any that is not
# an ACTIVE seat of this group. Every id here comes from a request body, so it is checked against the
# group's own roster rather than trusted: a seat id from another group would otherwise attach that
# group's member to this income, and a deactivated one would put money on somebody who has left.
async def _require_active_seats(
    session: AsyncSession, group_id: int, member_ids: list[int], received_by_member_id: int | None
) -> dict[int, GroupMember]:
    members_by_id = {member.id: member for member in await group_repository.list_members(session, group_id)}
    named = [*member_ids, *([received_by_member_id] if received_by_member_id is not None else [])]
    for member_id in named:
        member = members_by_id.get(member_id)
        if member is None or not member.is_active:
            raise NotFoundError("Group member not found")
    return members_by_id


# Resolves the source asset, which must be a holding of a pot in THIS group.
#
# Restricted rather than left open, and the reason is V1 rather than tidiness: the source is stored on
# a row the whole group reads, and the response carries its NAME, so a private investment of the
# caller's named here would put it in front of people who cannot see it. Income from an asset of your
# own is private income, which is a different table and a different form.
#
# A 404-shaped miss is folded into the same refusal as a foreign one, because the two are
# indistinguishable to a caller by design — an investment they cannot see is invisible rather than
# absent, exactly as elsewhere.
async def _resolve_source(session: AsyncSession, group_id: int, source_investment_id: int | None) -> Investment | None:
    if source_investment_id is None:
        return None
    investment = await investment_repository.get_by_id_any_scope(session, source_investment_id)
    # `pot_id is None` is the private case, and a mutation sweep proved it EQUIVALENT to the pot lookup
    # below: a null pot id finds no pot, so the second refusal catches it too. Kept because it states
    # the rule the reader needs — a private holding is refused — rather than leaving it to emerge from
    # a lookup that happens to return nothing. No test can tell the two apart, and none pretends to.
    if investment is None or investment.pot_id is None:
        raise SharedIncomeSourceScopeError()
    pot = await pot_repository.get_by_id(session, investment.pot_id)
    if pot is None or pot.group_id != group_id:
        raise SharedIncomeSourceScopeError()
    return investment


# Resolves where the money ended up and who holds it — the half of shared income the split figures
# cannot say.
#
# Two branches, and every rule differs between them:
#   * JOINT — the money landed in a shared account this group's pot holds, so the pot's owners received
#     it in their proportions on this date. The request must NOT name a recipient, an account IS
#     required (joint money with nowhere to land would claim every share rose while no figure moved),
#     and an undivided pot is refused because there is no honest answer to whose money it now is.
#   * DISTRIBUTED — one member received it and must be named. An account is optional (income handed
#     over in cash still divides), and when given it has to be that member's own private one: a pot's
#     account would contradict the destination, and another member's would let one person credit
#     somebody else's balance.
async def _resolve_destination(
    session: AsyncSession,
    group_id: int,
    *,
    members_by_id: dict[int, GroupMember],
    total: Decimal,
    currency: str,
    date: date_type,
    destination: IncomeDestination,
    received_by_member_id: int | None,
    paid_to_account_id: int | None,
) -> _Destination:
    account = await _load_account(session, paid_to_account_id)
    if destination == IncomeDestination.joint:
        if received_by_member_id is not None:
            raise SharedIncomeJointReceiverError()
        if account is None or account.pot_id is None:
            raise SharedIncomeJointAccountRequiredError()
        _ensure_account_currency(account, currency)
        _ensure_account_open(account, date)
        received_by = await _pot_owner_shares(session, account.pot_id, group_id, total=total, date=date)
        return _Destination(account=account, received_by=received_by)

    if received_by_member_id is None:
        raise SharedIncomeReceiverRequiredError()
    receiver = members_by_id[received_by_member_id]
    if account is not None:
        # Checked before ownership, because a pot account has no owner at all: the ownership check
        # would refuse it too, but as a bare "not found" that says nothing about what to do instead.
        if account.pot_id is not None:
            raise SharedIncomeDistributedSharedAccountError()
        _ensure_owned_by(account.user_id, receiver)
        _ensure_account_currency(account, currency)
        _ensure_account_open(account, date)
    return _Destination(account=account, received_by={received_by_member_id: total})


# Loads a destination account in EITHER scope, or None when none was named. Reachability is RLS's
# answer: a shared account is returned when the policy returns it, and whether this group's income may
# land in it is settled by comparing the pot's group.
async def _load_account(session: AsyncSession, account_id: int | None) -> Account | None:
    if account_id is None:
        return None
    account = await account_repository.get_by_id_any_scope(session, account_id)
    if account is None:
        raise NotFoundError("Account not found")
    return account


# Refuses an account that is not the recipient's own. Answers 404 rather than 403 for the same reason
# every other cross-tenant check does: confirming the row exists would be the leak.
def _ensure_owned_by(owner_user_id: int | None, receiver: GroupMember) -> None:
    if receiver.user_id is None or owner_user_id != receiver.user_id:
        raise NotFoundError("Account not found")


# Merged constraint (a): an entry's currency must equal its account's. These sums carry ONE amount, so
# a mismatched link would add a foreign-currency figure straight to the balance.
def _ensure_account_currency(account: Account, currency: str) -> None:
    if account.currency != currency:
        raise AccountCurrencyMismatchError(currency, account.currency)


# Each leg of the balance union is bounded below by its own account's opening_date, so income dated
# earlier would never reach that account's balance while still crediting money the group thinks it
# received.
def _ensure_account_open(account: Account, date: date_type) -> None:
    if date < account.opening_date:
        raise SharedIncomeBeforeAccountOpenedError(account.opening_date)


# Splits what a shared account received across the pot's owners, in their proportions ON THE INCOME'S
# DATE.
#
# The arithmetic is pot_ownership_service.owner_shares, shared with the expense mirror so there is one
# proportional division of a shared account's money rather than two that can drift. What stays here is
# the pair of refusals, because each names something an income reader has to fix and the expense
# wording is different: a pot in another group has owners this group could never settle with, and an
# undivided pot has no owners on record at all.
#
# ▸ This path deliberately does NOT apply _require_active_seats, and the asymmetry is the same one the
# expense mirror carries. A seat NAMED in the request is a choice the user is making now, so a departed
# one is refused. A pot owner is a FACT already on the ownership ledger: a member who left while still
# holding units still owns that share of the money, so income arriving really does reach theirs.
# Excluding them would break the identity the whole feature rests on — the received figures would no
# longer sum to the total, and the group's balances would no longer sum to zero.
async def _pot_owner_shares(session: AsyncSession, pot_id: int, group_id: int, *, total: Decimal, date: date_type) -> dict[int, Decimal]:
    pot = await pot_repository.get_by_id(session, pot_id)
    if pot is None or pot.group_id != group_id:
        raise SharedIncomeDestinationScopeError()
    shares = await pot_ownership_service.owner_shares(session, pot, total=total, date=date)
    if not shares:
        raise SharedIncomeDestinationPotNotDividedError()
    return shares


# Writes the complete split set: one row per member entitled to something, holding something, or both.
# The union of the two sides rather than either alone, because a collector entitled to no share still
# holds a position and a participant who has received nothing obviously does.
async def _write_splits(
    session: AsyncSession, income: SharedIncome, shares: dict[int, Decimal], received_by: dict[int, Decimal]
) -> list[SharedIncomeSplit]:
    member_ids = sorted(set(shares) | set(received_by))
    return await shared_income_repository.create_splits(
        session,
        [
            SharedIncomeSplit(
                shared_income_id=income.id,
                group_id=income.group_id,
                member_id=member_id,
                amount=shares.get(member_id, ZERO),
                received_amount=received_by.get(member_id, ZERO),
            )
            for member_id in member_ids
        ],
    )
