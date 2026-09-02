from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AccountCardExclusivityError,
    AccountCurrencyChangeBlockedByDefaultError,
    AccountCurrencyChangeBlockedError,
    AccountCurrencyMismatchError,
    AccountOpeningDateChangeBlockedError,
    NotFoundError,
    PaymentMethod,
)
from app.domain.pot import ensure_private_funding
from app.models.account import Account, AccountType
from app.models.user import User
from app.repositories import (
    account_repository,
    card_settlement_repository,
    expense_repository,
    group_settlement_repository,
    income_repository,
    installment_repository,
    payment_obligation_repository,
    pot_ownership_repository,
    shared_expense_repository,
    shared_income_repository,
    subscription_repository,
    transfer_repository,
)

ZERO = Decimal(0)


# List accounts for a user with optional search, sorting, and archive filtering.
async def list_accounts(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Account]:
    return await account_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
    )


# Get a single account by id. Raises NotFoundError if not found.
async def get_account(session: AsyncSession, account_id: int, user: User) -> Account:
    account = await account_repository.get_by_id(session, account_id, user.id)
    if account is None:
        raise NotFoundError("Account not found.")
    return account


# Loads an account in EITHER scope: the caller's own private one, or a co-owned one they may reach.
# Distinct from get_account, which is the private-only lookup every existing caller wants — this one
# exists for transfers, the single flow that legitimately operates on shared accounts.
# Reachability is RLS's answer, not this function's: a shared account is returned when the policy
# returns it, and whether the caller may WRITE it is settled by the write policy on the row being
# inserted, which is gated on pot write access.
async def get_account_in_scope(session: AsyncSession, account_id: int, user: User) -> Account:
    account = await account_repository.get_by_id_any_scope(session, account_id)
    if account is None:
        raise NotFoundError("Account not found.")
    if account.pot_id is None and account.user_id != user.id:
        raise NotFoundError("Account not found.")
    return account


# Loads a linked account and verifies ownership (SEC-4), applying NO currency rule. A None account_id is
# a no-op (unlinked rows are allowed and untouched). Returns the account so a caller that needs it (e.g.
# to denormalize its name onto a response) doesn't re-fetch it; None when there was no link.
#
# Separate from validate_account_link because two callers legitimately accept any currency: a card
# SETTLEMENT (which records what left the account explicitly, so nothing has to be inferred from a
# matching currency) and a card's standing DEFAULT funding account (which exists to prefill exactly that
# settlement). Both are cases where the currencies genuinely may differ, not a relaxation of the hard
# rule below — hence a distinct function rather than a flag that would let a caller opt out by accident.
async def load_linked_account(session: AsyncSession, user: User, account_id: int | None) -> Account | None:
    if account_id is None:
        return None
    account = await account_repository.get_by_id_any_scope(session, account_id)
    if account is None:
        raise NotFoundError("Account not found.")
    # A co-owned account is reachable here (RLS shows it to every member) but must not fund a private
    # entry: the money really leaves, so the pot's value drops and every co-owner's share falls with
    # it — one person spending and everyone paying, with nothing recording it. Refused explicitly
    # rather than left to the owner filter, which WOULD also refuse it but as a bare "not found" that
    # tells the user nothing about what to do instead.
    ensure_private_funding(account)
    if account.user_id != user.id:
        raise NotFoundError("Account not found.")
    return account


# Validates that an account link (from an expense / income, or a recurring plan naming its default
# funding account) is legal: ownership, plus the account's currency must match the linking row's — those
# sums have only ONE amount, so a mismatched link would add a foreign-currency figure straight into the
# balance (mirrors the investment base-currency lock). A None account_id is a no-op. Returns the
# validated account, or None when there was no link.
async def validate_account_link(session: AsyncSession, user: User, account_id: int | None, currency: str) -> Account | None:
    account = await load_linked_account(session, user, account_id)
    if account is not None and account.currency != currency:
        raise AccountCurrencyMismatchError(currency, account.currency)
    return account


# Validates the EFFECTIVE default funding account of a RECURRING PLAN on a partial update: the request's
# fields merged over the stored row. The three plan services need exactly this, so it lives here beside
# the validator it wraps rather than being restated in each. A credit card deliberately does NOT use
# this — its default may name any currency, so only ownership is checked and none of the merge logic
# below (which exists to keep a currency pair matching) applies.
#
# `effective_method` is the plan's merged payment method. A card-paid plan never names a funding account
# — its cash leg lands at the card settlement, so linking here as well would count one charge twice.
#
# Re-validated ONLY when the (account, currency) pair actually moves. An unchanged pair was already
# validated when it was attached, and re-checking it would let a stale stored default — its account's
# currency changed while nothing else referenced it — block an unrelated edit such as a rename or an
# archive. `currency` falls back on a falsy value because it is non-nullable: an explicit null is a
# malformed clear, not a request to drop the currency.
async def validate_effective_default_link(
    session: AsyncSession,
    user: User,
    *,
    fields: dict[str, object],
    stored_account_id: int | None,
    stored_currency: str,
    effective_method: str | None = None,
) -> None:
    new_account_id = fields.get("default_account_id", stored_account_id)
    new_currency = fields.get("currency") or stored_currency
    if new_account_id is not None and effective_method == PaymentMethod.credit_card:
        raise AccountCardExclusivityError()
    if (new_account_id, new_currency) != (stored_account_id, stored_currency):
        await validate_account_link(session, user, new_account_id, new_currency)


# Returns ({account_id: balance}, {account_ids with any linked money}) for the given accounts,
# derived at query time (one batch query per source): balance = opening_balance + linked income −
# linked expenses − card settlements paid from the account + transfers in − transfers out + ownership
# movements in − out − shared expenses drawn from it + shared income paid into it + group settlements
# received − paid. Every term is
# already denominated in the account's currency, so the sums need no per-currency conversion — but for
# four different reasons: entries (private and shared alike) are validated to MATCH the account's
# currency, each transfer leg is stored in its own account's, an ownership event stores both sides and
# the repository picks the right one per leg, and a card or group settlement may cross currencies and
# therefore records what left the account separately (those sums read coalesce(leg, amount)). Each sum is bounded below by
# the account's opening_date inside the repository — opening_balance IS the balance at that date, so an
# earlier row is already inside it. The linked set is free from the same sums (a group is present only
# when it has rows) and drives the currency lock in the response; a transfer counts as a link on either
# leg, so an account that has only ever sent or received money is still currency-locked.
async def get_account_summaries(session: AsyncSession, accounts: list[Account], user_id: int) -> tuple[dict[int, Decimal], set[int]]:
    account_ids = [a.id for a in accounts if a.id is not None]
    if not account_ids:
        return {}, set()
    balances = await get_account_balances(session, accounts, user_id)
    # `linked` is computed from its own UNBOUNDED queries, not from the sums above: those are bounded
    # below by opening_date, so an account whose only rows predate its opening would read as unlinked
    # and the UI would offer a currency change the API then refuses. The lock is about denomination.
    linked = (
        await income_repository.linked_account_ids(session, account_ids, user_id)
        | await expense_repository.linked_account_ids(session, account_ids, user_id)
        | await card_settlement_repository.linked_account_ids(session, account_ids, user_id)
        | await transfer_repository.linked_account_ids(session, account_ids, user_id)
        | await shared_expense_repository.linked_account_ids(session, account_ids)
        | await shared_income_repository.linked_account_ids(session, account_ids)
        | await group_settlement_repository.linked_account_ids(session, account_ids)
    )
    return balances, linked


# Returns {account_id: balance} for the given accounts. The money half of get_account_summaries, and
# the one callers reach for when they don't need the currency-lock set — computing `linked` costs
# four more existence queries, so a caller that only wants balances shouldn't pay for them.
async def get_account_balances(session: AsyncSession, accounts: list[Account], user_id: int) -> dict[int, Decimal]:
    account_ids = [a.id for a in accounts if a.id is not None]
    if not account_ids:
        return {}
    income = await income_repository.sum_by_account_ids(session, account_ids, user_id)
    expenses = await expense_repository.sum_by_account_ids(session, account_ids, user_id)
    settlements = await card_settlement_repository.sum_by_account_ids(session, account_ids, user_id)
    transfers_in = await transfer_repository.sum_in_by_account_ids(session, account_ids, user_id)
    transfers_out = await transfer_repository.sum_out_by_account_ids(session, account_ids, user_id)
    # A contribution into a pot really debits the mover's private account and credits one the pot
    # holds, so both legs belong here for exactly the reason a transfer's do. Without them the money
    # would leave nowhere and arrive nowhere.
    ownership_in = await pot_ownership_repository.sum_in_by_account_ids(session, account_ids)
    ownership_out = await pot_ownership_repository.sum_out_by_account_ids(session, account_ids)
    # A group's shared expense drawn from this account takes the WHOLE amount out of it, not anyone's
    # share: the money really left. Who owed whom afterwards is the splits' business, never the
    # account's. A settlement clearing one of those balances moves cash on both sides, so both of its
    # legs are here for exactly the reason a transfer's two are.
    shared_expenses = await shared_expense_repository.sum_by_account_ids(session, account_ids)
    # And the mirror on the way in: a group's shared income paid into this account puts the WHOLE
    # amount in it, not anybody's share. Who owes whom afterwards is the splits' business.
    shared_income = await shared_income_repository.sum_by_account_ids(session, account_ids)
    group_settlements_in = await group_settlement_repository.sum_in_by_account_ids(session, account_ids)
    group_settlements_out = await group_settlement_repository.sum_out_by_account_ids(session, account_ids)
    return {
        a.id: (
            a.opening_balance
            + income.get(a.id, ZERO)
            - expenses.get(a.id, ZERO)
            - settlements.get(a.id, ZERO)
            + transfers_in.get(a.id, ZERO)
            - transfers_out.get(a.id, ZERO)
            + ownership_in.get(a.id, ZERO)
            - ownership_out.get(a.id, ZERO)
            - shared_expenses.get(a.id, ZERO)
            + shared_income.get(a.id, ZERO)
            + group_settlements_in.get(a.id, ZERO)
            - group_settlements_out.get(a.id, ZERO)
        )
        for a in accounts
        if a.id is not None
    }


# Returns {account_id: balance} as of a DATE, for the given accounts. The batch sibling of
# account_reconciliation_service.compute_account_balance_at, added because the pot NAV query needs a
# balance per holding and calling the single-account version in a loop is an N+1 over seven sums.
# Each sum is scoped by the ACCOUNT's owner rather than the caller's, so a shared account reports the
# same balance to every member who can see it.
async def compute_account_balances_at(session: AsyncSession, accounts: list[Account], *, as_of_date: date_type) -> dict[int, Decimal]:
    account_ids = [a.id for a in accounts if a.id is not None]
    if not account_ids:
        return {}
    owners = {a.user_id for a in accounts}
    # A pot's accounts share one scope, so one owner value covers the batch; a mixed batch would need
    # a sum per owner, which no caller produces (holdings are listed per pot, or per user).
    owner_id = next(iter(owners)) if len(owners) == 1 else None
    income = await income_repository.sum_by_account_ids(session, account_ids, owner_id, as_of_date=as_of_date)
    expenses = await expense_repository.sum_by_account_ids(session, account_ids, owner_id, as_of_date=as_of_date)
    settlements = await card_settlement_repository.sum_by_account_ids(session, account_ids, owner_id, as_of_date=as_of_date)
    transfers_in = await transfer_repository.sum_in_by_account_ids(session, account_ids, owner_id, as_of_date=as_of_date)
    transfers_out = await transfer_repository.sum_out_by_account_ids(session, account_ids, owner_id, as_of_date=as_of_date)
    ownership_in = await pot_ownership_repository.sum_in_by_account_ids(session, account_ids, as_of_date=as_of_date)
    ownership_out = await pot_ownership_repository.sum_out_by_account_ids(session, account_ids, as_of_date=as_of_date)
    shared_expenses = await shared_expense_repository.sum_by_account_ids(session, account_ids, as_of_date=as_of_date)
    shared_income = await shared_income_repository.sum_by_account_ids(session, account_ids, as_of_date=as_of_date)
    group_settlements_in = await group_settlement_repository.sum_in_by_account_ids(session, account_ids, as_of_date=as_of_date)
    group_settlements_out = await group_settlement_repository.sum_out_by_account_ids(session, account_ids, as_of_date=as_of_date)
    return {
        a.id: (
            (a.opening_balance if a.opening_date <= as_of_date else ZERO)
            + income.get(a.id, ZERO)
            - expenses.get(a.id, ZERO)
            - settlements.get(a.id, ZERO)
            + transfers_in.get(a.id, ZERO)
            - transfers_out.get(a.id, ZERO)
            + ownership_in.get(a.id, ZERO)
            - ownership_out.get(a.id, ZERO)
            - shared_expenses.get(a.id, ZERO)
            + shared_income.get(a.id, ZERO)
            + group_settlements_in.get(a.id, ZERO)
            - group_settlements_out.get(a.id, ZERO)
        )
        for a in accounts
        if a.id is not None
    }


# Returns {account_id: [balance at each date]}, for the given accounts and an ASCENDING list of dates.
#
# The batch-over-time sibling of compute_account_balances_at, and the reason it exists is arithmetic:
# that function costs one query per SOURCE per date, so a twelve-point series would cost a dozen times
# what one point does. This costs one per source for the whole series, because each sum is grouped by
# (account_id, date) once over the window and accumulated here. §12's O3 is exactly this fan-out.
#
# Every term of the union appears, in the same order and with the same sign as the point-in-time
# version, deliberately: three of them can only ever be empty for a pot's accounts (a shared account
# cannot carry private entries at all), and dropping them for that reason would make this a sum that
# agrees with the balance only for as long as that guard holds. Keeping every term makes
# `series[i] == compute_account_balances_at(dates[i])` true by construction, which is what
# tests/unit/test_account_balance_series.py asserts.
#
# `dates` must be ascending; the caller builds it from a period grid, which is generated that way.
async def compute_account_balance_series(session: AsyncSession, accounts: list[Account], *, dates: list[date_type]) -> dict[int, list[Decimal]]:
    account_ids = [a.id for a in accounts if a.id is not None]
    if not account_ids or not dates:
        return {}
    owners = {a.user_id for a in accounts}
    # One owner value covers the batch, exactly as compute_account_balances_at resolves it.
    owner_id = next(iter(owners)) if len(owners) == 1 else None
    until = dates[-1]
    income = await income_repository.sum_by_account_ids_dated(session, account_ids, owner_id, until=until)
    expenses = await expense_repository.sum_by_account_ids_dated(session, account_ids, owner_id, until=until)
    settlements = await card_settlement_repository.sum_by_account_ids_dated(session, account_ids, owner_id, until=until)
    transfers_in = await transfer_repository.sum_in_by_account_ids_dated(session, account_ids, owner_id, until=until)
    transfers_out = await transfer_repository.sum_out_by_account_ids_dated(session, account_ids, owner_id, until=until)
    ownership_in = await pot_ownership_repository.sum_in_by_account_ids_dated(session, account_ids, until=until)
    ownership_out = await pot_ownership_repository.sum_out_by_account_ids_dated(session, account_ids, until=until)
    shared_expenses = await shared_expense_repository.sum_by_account_ids_dated(session, account_ids, until=until)
    shared_income = await shared_income_repository.sum_by_account_ids_dated(session, account_ids, until=until)
    group_settlements_in = await group_settlement_repository.sum_in_by_account_ids_dated(session, account_ids, until=until)
    group_settlements_out = await group_settlement_repository.sum_out_by_account_ids_dated(session, account_ids, until=until)

    # One signed delta per (account, date), so the accumulation below is a single pass over dates
    # rather than one pass per source.
    deltas: dict[int, dict[date_type, Decimal]] = {account_id: {} for account_id in account_ids}
    for rows, sign in (
        (income, 1),
        (expenses, -1),
        (settlements, -1),
        (transfers_in, 1),
        (transfers_out, -1),
        (ownership_in, 1),
        (ownership_out, -1),
        (shared_expenses, -1),
        (shared_income, 1),
        (group_settlements_in, 1),
        (group_settlements_out, -1),
    ):
        for account_id, movement_date, total in rows:
            per_account = deltas[account_id]
            per_account[movement_date] = per_account.get(movement_date, ZERO) + total * sign

    series: dict[int, list[Decimal]] = {}
    for account in accounts:
        if account.id is None:
            continue
        moved = sorted(deltas[account.id].items())
        running = ZERO
        cursor = 0
        points: list[Decimal] = []
        for point_date in dates:
            while cursor < len(moved) and moved[cursor][0] <= point_date:
                running += moved[cursor][1]
                cursor += 1
            # The opening figure only counts from its own date, the same bound the point-in-time
            # version applies — before it the account did not exist and its balance is zero.
            points.append((account.opening_balance if account.opening_date <= point_date else ZERO) + running)
        series[account.id] = points
    return series


# The current balance of ONE account, for a caller holding the row already (the ledger's anchor).
# Reuses the batch derivation with a single id, the way compute_account_balance_at reuses the sums.
async def get_account_balance(session: AsyncSession, account: Account, user_id: int) -> Decimal:
    balances = await get_account_balances(session, [account], user_id)
    return balances.get(account.id, account.opening_balance)


# Create a new account.
async def create_account(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    type: AccountType,
    currency: str,
    opening_balance: Decimal,
    opening_date: date_type,
    notes: str | None = None,
) -> Account:
    account = Account(
        user_id=user.id,
        created_by=user.id,
        name=name,
        type=type,
        currency=currency,
        opening_balance=opening_balance,
        opening_date=opening_date,
        notes=notes,
    )
    account = await account_repository.create(session, account)
    await session.commit()
    return account


# Returns whether any money entry (expense / income / settlement) links this account. Used to lock the
# account's currency AND its opening_date once linked: the first would silently mix currencies in the
# derived balance, the second would drop rows out of it, since every sum is bounded below by that date.
async def account_has_links(session: AsyncSession, account_id: int, user_id: int) -> bool:
    return (
        await expense_repository.exists_by_account_id(session, account_id, user_id)
        or await income_repository.exists_by_account_id(session, account_id, user_id)
        or await card_settlement_repository.exists_by_account_id(session, account_id, user_id)
        or await transfer_repository.exists_by_account_id(session, account_id, user_id)
        # No user filter on the three group sources: the rows belong to the group, and RLS scopes them.
        # An account a group has spent from, earned into or settled through is denominated just as
        # firmly as one its owner used privately, so it has to lock the currency too. All three are
        # asked here and not only in the batch summary path: this is the one the UPDATE consults, so a
        # source missing from it is a currency the owner can still change under the group's figures.
        or bool(await shared_expense_repository.linked_account_ids(session, [account_id]))
        or bool(await shared_income_repository.linked_account_ids(session, [account_id]))
        or bool(await group_settlement_repository.linked_account_ids(session, [account_id]))
    )


# Counts the recurring PLANS naming this account as their default funding account. A default is not a
# money link — nothing has moved — but a plan's is a standing instruction that constrains the account's
# currency: a plan's charge carries one amount, so the moment the two stop matching every charge that
# default was meant to attribute silently stops being attributed.
#
# CARDS are deliberately NOT counted, unlike plans. A card's default may now name an account in any
# currency, because a cross-currency settlement records what left that account explicitly — so
# re-denominating the account cannot make the default inert, and there is nothing to protect. The
# asymmetry is the same one that lets a card's default cross currencies while a plan's may not.
async def count_default_references(session: AsyncSession, account_id: int, user_id: int) -> int:
    return (
        await subscription_repository.count_by_default_account(session, account_id, user_id)
        + await installment_repository.count_by_default_account(session, account_id, user_id)
        + await payment_obligation_repository.count_by_default_account(session, account_id, user_id)
    )


# Update an existing account. Only provided fields are changed. Changing the currency is blocked once
# money links to the account — it would silently mix currencies in the derived balance (mirrors the
# investment base-currency lock).
async def update_account(
    session: AsyncSession,
    account_id: int,
    user: User,
    **fields: object,
) -> Account:
    account = await get_account(session, account_id, user)
    new_currency = fields.get("currency")
    new_opening_date = fields.get("opening_date")
    currency_moved = new_currency is not None and new_currency != account.currency
    # opening_date is load-bearing for the balance: every sum is bounded below by it, while
    # opening_balance ("the balance AT that date") cannot be recomputed. Moving it would drop rows from
    # the balance with nothing to offset them — for a transfer, money would leave one account and arrive
    # nowhere. Locked once linked, same as the currency.
    opening_date_moved = new_opening_date is not None and new_opening_date != account.opening_date
    if (currency_moved or opening_date_moved) and await account_has_links(session, account_id, user.id):
        if currency_moved:
            raise AccountCurrencyChangeBlockedError()
        raise AccountOpeningDateChangeBlockedError()
    # A standing default constrains the currency too, with its own error: no money has moved, so the
    # "has linked entries" message above would be false, and the user needs to be told what actually
    # stands in the way. Only the currency — opening_date does not affect whether a default applies.
    if currency_moved:
        references = await count_default_references(session, account_id, user.id)
        if references:
            raise AccountCurrencyChangeBlockedByDefaultError(references)
    for key, value in fields.items():
        setattr(account, key, value)
    await account_repository.save(session, account)
    await session.commit()
    await session.refresh(account)
    return account


# Delete an account. Linked expenses/income/settlements are un-attributed via ON DELETE SET NULL
# (their history is preserved).
#
# A cross-currency settlement's recorded cash leg is cleared first, in the same transaction. That figure
# is denominated in THIS account, so once the link is gone nothing can interpret it — and every reader
# treats "account_amount is set" as "this settlement crossed currencies". The card leg survives, so the
# settlement still clears its bucket exactly as before; only the cash side it can no longer attribute
# goes. Deliberately done here rather than as a DB CHECK: the FK's own SET NULL is an UPDATE, so a
# constraint pairing the two columns would make this delete impossible instead of merely tidy.
async def delete_account(session: AsyncSession, account_id: int, user: User) -> None:
    account = await get_account(session, account_id, user)
    await card_settlement_repository.clear_account_amounts(session, account_id, user.id)
    # A group settlement's cash legs are denominated in THIS account, so once the link is gone nothing
    # can interpret them — and every reader treats "a leg amount is set" as "this crossed currencies".
    # The bucket leg survives, so the settlement still clears its balance exactly as before.
    await group_settlement_repository.clear_account_amounts(session, account_id)
    await account_repository.delete(session, account)
    await session.commit()


# Archive an account (set is_active = false).
async def archive_account(session: AsyncSession, account_id: int, user: User) -> Account:
    account = await get_account(session, account_id, user)
    account.is_active = False
    await account_repository.save(session, account)
    await session.commit()
    await session.refresh(account)
    return account


# Unarchive an account (set is_active = true).
async def unarchive_account(session: AsyncSession, account_id: int, user: User) -> Account:
    account = await get_account(session, account_id, user)
    account.is_active = True
    await account_repository.save(session, account)
    await session.commit()
    await session.refresh(account)
    return account
