# Domain errors, raised by services; the HTTP layer maps them to status codes and responses.
#
# Every domain error carries a stable `code` (the machine-readable contract the frontend maps to a
# localized message) and the `status_code` the API returns. `message` is the English dev/fallback —
# the frontend falls back to it for any code it doesn't map. A single handler in app/main.py turns
# any DomainError into `{"detail": message, "code": code, **extra}`, so the whole family shares one
# uniform response shape. The backend stays locale-agnostic — localization happens on the frontend
# via the code (transactional emails are the one backend-localized exception).
#
# Subclasses are listed alphabetically. Each sets `code` + `status_code` (class-level), assigns
# `self.message`, then calls `super().__init__(self.message)`; errors carrying structured data
# override the `extra` property.

from datetime import date as date_type
from decimal import Decimal


# Base for every service-raised error. Subclasses set `code` + `status_code` and assign `self.message`.
class DomainError(Exception):
    code: str = "domain_error"
    status_code: int = 400
    # Default so the app/main.py handler's `exc.message` always resolves, even for a bare DomainError.
    message: str = "Something went wrong."

    # Extra response fields beyond {detail, code}. Override for errors that carry structured data.
    @property
    def extra(self) -> dict:
        return {}


# A credit-card charge also names a cash/bank account: an expense linking one directly, or a recurring
# plan / card naming one as its default. A card charge increases the card liability now and only draws
# cash later at settlement, so it never draws an account directly. Mapped to 400.
class AccountCardExclusivityError(DomainError):
    code = "account_card_exclusivity"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A credit-card charge cannot also be paid from an account."
        super().__init__(self.message)


# An account's currency cannot be changed because a recurring plan names it as its default funding
# account. Deliberately separate from AccountCurrencyChangeBlockedError: no money has moved, so "has
# linked entries" would be false — what stands in the way is a standing default whose charges would
# silently stop being attributed the moment the currencies stopped matching. A CARD's default does not
# raise this: it may name any currency, because a cross-currency settlement records what left the
# account explicitly. Mapped to 409.
class AccountCurrencyChangeBlockedByDefaultError(DomainError):
    code = "account_currency_change_blocked_by_default"
    status_code = 409

    def __init__(self, referencing_count: int) -> None:
        self.referencing_count = referencing_count
        self.message = (
            f"Currency cannot be changed because {referencing_count} recurring plan(s) use this account as their default. Clear those defaults first."
        )
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"referencing_count": self.referencing_count}


# An account's currency cannot be changed because money entries link to it — a cash balance must stay
# exact, and changing the currency would silently mix currencies in the derived balance. Mapped to 409.
class AccountCurrencyChangeBlockedError(DomainError):
    code = "account_currency_change_blocked"
    status_code = 409

    def __init__(self) -> None:
        self.message = "Currency cannot be changed because this account has linked entries."
        super().__init__(self.message)


# A money entry (expense / income / settlement) links to an account whose currency differs from the
# entry's. A cash balance must stay exact, so the link currencies must match. Mapped to 400 by the API.
class AccountCurrencyMismatchError(DomainError):
    code = "account_currency_mismatch"
    status_code = 400

    def __init__(self, entry_currency: str, account_currency: str) -> None:
        self.entry_currency = entry_currency
        self.account_currency = account_currency
        self.message = f"Currency {entry_currency} does not match the account's currency ({account_currency})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"entry_currency": self.entry_currency, "account_currency": self.account_currency}


# An account cannot be moved into a pot because money entries already link to it. Its balance derives
# from expenses, income, settlements and transfers owned by ONE user, so a shared account carrying
# them would report a different balance to every member depending on whose rows they can see — and a
# figure that changes with the reader is worse than one that is merely wrong. A transfer is the
# sharpest case: it would end up with one leg in each scope, which no transfer may have.
# Mapped to 409.
class AccountHasLinkedEntriesError(DomainError):
    code = "account_has_linked_entries"
    status_code = 409

    def __init__(self, account_ids: list[int]) -> None:
        self.account_ids = account_ids
        self.message = "An account with linked entries cannot be shared. Create a new account for the pot instead."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"account_ids": self.account_ids}


# An account's opening_date cannot be changed because money entries link to it. opening_balance is
# defined as "the balance AT opening_date", and every balance sum is bounded below by it — so moving the
# date forward silently drops rows from the balance while opening_balance stays put, and money that left
# one account would arrive nowhere. The pair cannot be recomputed (the app never knew the earlier
# balance), so the date is locked, mirroring the currency lock. Mapped to 409.
class AccountOpeningDateChangeBlockedError(DomainError):
    code = "account_opening_date_change_blocked"
    status_code = 409

    def __init__(self) -> None:
        self.message = "Opening date cannot be changed because this account has linked entries."
        super().__init__(self.message)


# An account reconciliation is dated before the account's most recent one. Reconciliations are
# point-in-time truths applied forward, so an older one entered afterwards would post its adjustment
# *underneath* the newer one — which cannot see it — leaving the newer, authoritative balance wrong.
# Correcting an older date means deleting the newer reconciliation first. Mapped to 400.
class AccountReconciliationBeforeLastError(DomainError):
    code = "account_reconciliation_before_last"
    status_code = 400

    def __init__(self, last_reconciled_date: date_type) -> None:
        self.last_reconciled_date = last_reconciled_date
        self.message = (
            f"This account is already reconciled up to {last_reconciled_date.isoformat()}. "
            "Reconcile on or after that date, or delete the later reconciliation first."
        )
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"last_reconciled_date": self.last_reconciled_date.isoformat()}


# An account reconciliation is dated before the account's opening_date — the account did not exist
# yet, so there is no balance to true up against. Mapped to 400.
class AccountReconciliationBeforeOpeningError(DomainError):
    code = "account_reconciliation_before_opening"
    status_code = 400

    def __init__(self, opening_date: date_type) -> None:
        self.opening_date = opening_date
        self.message = f"Reconciliation date must be on or after the account's opening date ({opening_date.isoformat()})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"opening_date": self.opening_date.isoformat()}


# An account reconciliation is dated in the future. A reconciliation records a balance the user has
# actually read, which can only be today or earlier. Mapped to 400.
class AccountReconciliationFutureDateError(DomainError):
    code = "account_reconciliation_future_date"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Reconciliation date cannot be in the future."
        super().__init__(self.message)


# A reconciliation that is not the account's most recent cannot be deleted. Its adjustment is already
# baked into every later reconciliation's recorded computed_balance, so removing it would silently
# skew those. Delete newest-first. Mapped to 400.
class AccountReconciliationNotLatestError(DomainError):
    code = "account_reconciliation_not_latest"
    status_code = 400

    def __init__(self, last_reconciled_date: date_type) -> None:
        self.last_reconciled_date = last_reconciled_date
        self.message = f"Delete the reconciliation dated {last_reconciled_date.isoformat()} first — later reconciliations build on this one."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"last_reconciled_date": self.last_reconciled_date.isoformat()}


# A card reconciliation's statement period closes in the future. A reconciliation records the balance
# printed on a statement the user has actually received, and a period cannot have closed yet. This is
# the one rule the card and account flows deliberately share — they differ on ordering, not on whether
# a statement can exist before its closing date. Mapped to 400.
class CardReconciliationFuturePeriodError(DomainError):
    code = "card_reconciliation_future_period"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A statement period that has not closed yet cannot be reconciled."
        super().__init__(self.message)


# A settlement is dated before the funding account it draws from existed. Every cash sum is bounded below
# by the account's opening_date (opening_balance already IS the balance at that date), so such a settlement
# would clear the card while its cash leg was silently dropped from the balance — the one asymmetry a
# settlement must never have. Worse across currencies, where the dropped figure is the account-currency
# amount rather than the card's. Mapped to 400 by the API.
class SettlementBeforeAccountOpenedError(DomainError):
    code = "settlement_before_account_opened"
    status_code = 400

    def __init__(self, opening_date: date_type) -> None:
        self.opening_date = opening_date
        self.message = f"A settlement must be dated on or after its funding account's opening date ({opening_date.isoformat()})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"opening_date": self.opening_date.isoformat()}


# A settlement paying a bucket from an account in a DIFFERENT currency did not record what left that
# account. The bank converted internally and only the user knows the blended rate it charged (the
# "dólar tarjeta" already contains the perception), so inventing one would misstate the cash balance —
# the exact reasoning behind TransferAmountRequiredError. Mapped to 400 by the API.
class SettlementAccountAmountRequiredError(DomainError):
    code = "settlement_account_amount_required"
    status_code = 400

    def __init__(self, bucket_currency: str, account_currency: str) -> None:
        self.bucket_currency = bucket_currency
        self.account_currency = account_currency
        self.message = (
            f"Paying a {bucket_currency} bucket from an account in {account_currency} must record the {account_currency} "
            "amount that left it, so the rate the bank charged is preserved."
        )
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"bucket_currency": self.bucket_currency, "account_currency": self.account_currency}


# A same-currency settlement recorded a cash amount different from what it cleared. No conversion
# happened, so the account must be debited exactly what came off the bucket — a bank fee is its own
# expense rather than a silently inflated payment. Mirrors TransferAmountsMustMatchError. Mapped to 400.
class SettlementAmountsMustMatchError(DomainError):
    code = "settlement_amounts_must_match"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Within one currency a settlement must debit exactly what it clears. Record a fee as its own expense."
        super().__init__(self.message)


# A settlement recorded a cash amount without naming the account it came from. There is no currency for
# that amount to be denominated in, and no balance for it to move. The DB CHECK is the backstop; this is
# the message. Mapped to 400 by the API.
class SettlementAccountAmountWithoutAccountError(DomainError):
    code = "settlement_account_amount_without_account"
    status_code = 400

    def __init__(self) -> None:
        self.message = "An amount drawn from an account needs the account it was drawn from."
        super().__init__(self.message)


# Investment currency cannot be changed because snapshots exist. Mapped to 409 by the API.
class CurrencyChangeBlockedError(DomainError):
    code = "currency_change_blocked"
    status_code = 409

    def __init__(self) -> None:
        self.message = "Currency cannot be changed because this investment has snapshots."
        super().__init__(self.message)


# Email address has not been verified yet; login (or a gated action) is blocked. Mapped to 403 by the API.
class EmailNotVerifiedError(DomainError):
    code = "email_not_verified"
    status_code = 403

    def __init__(self, message: str = "Please verify your email address before logging in.") -> None:
        self.message = message
        super().__init__(self.message)


# Currency conversion requested but no exchange rates are available. Mapped to 503 by the API.
class ExchangeRateUnavailableError(DomainError):
    code = "exchange_rate_unavailable"
    status_code = 503

    def __init__(self, currency: str) -> None:
        self.currency = currency
        self.message = f"Exchange rates unavailable. Cannot convert to {currency}."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"currency": self.currency}


# A group operation that only an admin may perform was attempted by a plain member. Group
# administration is management, not access — this gates WRITES to membership, settings and invites, and
# never widens what anyone can read. Mapped to 403 by the API.
class GroupAdminRequiredError(DomainError):
    code = "group_admin_required"
    status_code = 403

    def __init__(self) -> None:
        self.message = "Only a group admin can do this."
        super().__init__(self.message)


# A member still holds an open balance in the group, in at least one currency, and the operation would
# leave it stranded — removing the seat, or deleting the account behind it. The balance is real money
# between real people, so it has to be settled or explicitly written off first; silently discarding it
# would take one side's claim away without either of them agreeing to it. Mapped to 409 by the API.
class GroupBalanceOutstandingError(DomainError):
    code = "group_balance_outstanding"
    status_code = 409

    def __init__(self, group_names: list[str]) -> None:
        self.group_names = sorted(group_names)
        joined = ", ".join(self.group_names)
        self.message = f"There is still an unsettled balance in {joined}. Settle it or write it off first."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"groups": self.group_names}


# Removing, deactivating or demoting the last active admin of a group. Someone must be able to manage
# members and settings, and no other role can promote a replacement — so the group would be permanently
# unadministrable, with no recovery path short of deleting it. Promote someone else first. Mapped to 409
# by the API: the request is well-formed, it conflicts with the group's state.
class GroupLastAdminError(DomainError):
    code = "group_last_admin"
    status_code = 409

    def __init__(self) -> None:
        self.message = "A group must keep at least one admin. Make someone else an admin first."
        super().__init__(self.message)


# An account tried to claim a second seat in a group it already belongs to. One person is one member per
# group, which is what makes a member id a usable counterparty for balances and ownership units — two
# seats for one account would split their history in half. Mapped to 409 by the API.
class GroupMembershipExistsError(DomainError):
    code = "group_membership_exists"
    status_code = 409

    def __init__(self) -> None:
        self.message = "You are already a member of this group."
        super().__init__(self.message)


# An admin invited a group seat that a Renly account already holds. There is nothing to claim, so the
# link could only ever fail. Deliberately distinct from GroupMembershipExistsError, which says "you are
# already a member of this group" — the right sentence for someone redeeming a link, and the wrong one
# entirely for an admin inviting somebody else. Mapped to 409 by the API.
class GroupSeatTakenError(DomainError):
    code = "group_seat_taken"
    status_code = 409

    def __init__(self) -> None:
        self.message = "This person has already joined, so there is nothing to invite."
        super().__init__(self.message)


# A settlement is dated before one of the accounts it moves through existed. Each leg of the balance
# union is bounded by its own account's opening_date — opening_balance already IS the balance at that
# date — so a settlement dated earlier would clear a balance while the account it supposedly moved
# through never changes. Mapped to 400 by the API.
class GroupSettlementBeforeAccountOpenedError(DomainError):
    code = "group_settlement_before_account_opened"
    status_code = 400

    def __init__(self, opening_date: date_type) -> None:
        self.opening_date = opening_date
        self.message = f"A settlement must be dated on or after its account's opening date ({opening_date.isoformat()})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"opening_date": self.opening_date.isoformat()}


# A settlement that has already been confirmed was edited, deleted, or written off. Confirmation is the
# payee's acknowledgement that they received the money, so it is the one state the payer cannot undo
# alone: the payee un-confirms it first, which is a deliberate second act rather than a silent
# overwrite of somebody else's word. Mapped to 409 by the API.
class GroupSettlementConfirmedError(DomainError):
    code = "group_settlement_confirmed"
    status_code = 409

    def __init__(self) -> None:
        self.message = "This settlement is confirmed. The person who received the money has to un-confirm it first."
        super().__init__(self.message)


# A settlement's cash leg names an account belonging to the OTHER party. The two legs belong to two
# different people, and neither can see the other's accounts at all — the row-level policies hide
# them — so a request naming both could only ever come from a client that had guessed an id.
#
# Refused explicitly rather than left to the ownership check, which WOULD also refuse it but as a bare
# "not found" that tells the user nothing about what to do instead: each side records their own leg.
# Mapped to 400 by the API.
class GroupSettlementForeignLegError(DomainError):
    code = "group_settlement_foreign_leg"
    status_code = 400

    def __init__(self) -> None:
        self.message = "You can only record which of your own accounts the money moved through. The other person records theirs."
        super().__init__(self.message)


# A settlement's cash leg crosses currencies but does not say what actually moved through the account.
# The bucket amount is in the balance's currency, so without the account's own figure the balance would
# be reduced by a number that never left anyone's account. Mapped to 400 by the API.
class GroupSettlementLegAmountRequiredError(DomainError):
    code = "group_settlement_leg_amount_required"
    status_code = 400

    def __init__(self, account_currency: str, bucket_currency: str) -> None:
        self.account_currency = account_currency
        self.bucket_currency = bucket_currency
        self.message = (
            # No indefinite article before a currency code: "a USD" and "an ARS" are both wrong for some
            # of the five supported ones, and nothing in the sentence needs one.
            f"This settlement clears {bucket_currency} through an account in {account_currency}, so it must say how much {account_currency} moved."
        )
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"account_currency": self.account_currency, "bucket_currency": self.bucket_currency}


# A same-currency settlement leg recorded a cash amount different from what it cleared. No conversion
# happened, so the account moved exactly what came off the bucket — a bank fee is its own expense
# rather than a silently inflated payment. Distinct from SettlementAmountsMustMatchError, whose wording
# is about DEBITING: a group settlement has two legs, and "debit" would be wrong on the receiving one.
# Mapped to 400 by the API.
class GroupSettlementLegAmountsMustMatchError(DomainError):
    code = "group_settlement_leg_amounts_must_match"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Within one currency a settlement moves exactly what it clears. Record a fee as its own expense."
        super().__init__(self.message)


# A settlement's cash leg names an amount but no account to draw it from (or pay it into). The figure is
# denominated in THAT account's currency, so with no account there is nothing to interpret it against.
# Enforced here rather than as a CHECK for the reason 0016 recorded: account_id is ON DELETE SET NULL,
# so a constraint pairing the two would make any account that ever funded a cross-currency settlement
# permanently undeletable. Mapped to 400 by the API.
class GroupSettlementLegWithoutAccountError(DomainError):
    code = "group_settlement_leg_without_account"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A settlement's cash amount needs the account it moved through."
        super().__init__(self.message)


# A write-off was recorded by someone other than the creditor. Writing off is giving up a claim, and
# only the person holding it can give it up — a debtor writing off their own debt would be deciding on
# somebody else's behalf. Mapped to 403 by the API.
class GroupSettlementNotCreditorError(DomainError):
    code = "group_settlement_not_creditor"
    status_code = 403

    def __init__(self) -> None:
        self.message = "Only the person who is owed can write a balance off."
        super().__init__(self.message)


# Someone other than the payee tried to confirm or un-confirm a settlement. Confirming is the trust
# anchor for real money — it means "I received this" — so only the seat that received it can say so.
# Mapped to 403 by the API.
class GroupSettlementNotPayeeError(DomainError):
    code = "group_settlement_not_payee"
    status_code = 403

    def __init__(self) -> None:
        self.message = "Only the person who received the money can confirm a settlement."
        super().__init__(self.message)


# A cash leg was attached to a written-off balance. Nothing moved — that is what a write-off IS — so an
# account leg would record a payment nobody made, and a DB CHECK refuses the row outright. Refused here
# with something the user can act on: undo the write-off and record a real payment instead.
# Mapped to 409 by the API — the request is well-formed, it conflicts with the row's state.
class GroupSettlementWriteOffHasNoLegError(DomainError):
    code = "group_settlement_write_off_has_no_leg"
    status_code = 409

    def __init__(self) -> None:
        self.message = "A written-off balance moved no money, so no account can be attached to it."
        super().__init__(self.message)


# The payer says less left their account than this payment could possibly have moved through it.
#
# Reachable only through the waterfall, where one payment writes several rows and each has to move
# something. Two ways to fall under it, and the minimum covers both: a row whose bucket is already in
# the account's currency leaves it one for one, so it alone accounts for part of the total; and every
# other row needs at least one minor unit, since a row recording that it moved nothing is refused by
# `group_settlements_positive_legs` — as a 500, on a form somebody filled in wrong.
#
# The figure named is therefore exact rather than indicative: what the same-currency rows move, plus
# one unit for each row that crosses. Mapped to 400.
class GroupSettlementLegTotalTooSmallError(DomainError):
    code = "group_settlement_leg_total_too_small"
    status_code = 400

    def __init__(self, minimum: Decimal, currency: str) -> None:
        self.minimum = minimum
        self.currency = currency
        self.message = f"At least {minimum} {currency} must have left that account for this payment — each balance it clears has to move something."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"minimum": str(self.minimum), "currency": self.currency}


# A write-off is for more than the bucket actually holds.
#
# Refused, unlike an overpaying PAYMENT, which is legal and flips the balance — the two look alike and
# are not. A payment is a real-world act that can genuinely exceed the debt: money changed hands, and
# the payee simply owes some back. A write-off is a creditor giving up a claim, so writing off more
# than the claim would create a debt in the other direction out of nothing — the debtor would end up
# owed money by the person who forgave them. There is no act that does that, so it is a typo every
# time. Mapped to 400.
class GroupWriteOffExceedsBalanceError(DomainError):
    code = "group_write_off_exceeds_balance"
    status_code = 400

    def __init__(self, outstanding: Decimal, currency: str) -> None:
        self.outstanding = outstanding
        self.currency = currency
        # The figure is named because it is the whole of what the user has to do about it, and it is
        # not on screen in every place this can be reached from.
        self.message = f"You can write off at most {outstanding} {currency} — that is the whole balance."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"outstanding": str(self.outstanding), "currency": self.currency}


# A settlement or write-off names a member who is not a real, active seat in the group — or names the
# same seat on both sides, which would move one balance in two directions and clear nothing. Mapped to
# 400 by the API.
class GroupSettlementSameMemberError(DomainError):
    code = "group_settlement_same_member"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A settlement moves money between two different people."
        super().__init__(self.message)


# Operation conflicts with current state (e.g. deleting a card with linked expenses). Mapped to 409 by the API.
class HasLinkedExpensesError(DomainError):
    code = "has_linked_expenses"
    status_code = 409

    def __init__(self, message: str = "Cannot delete a credit card that has linked expenses. Archive it instead.") -> None:
        self.message = message
        super().__init__(self.message)


# Attempt to modify locked contractual fields on an installment after the first installment was charged. Mapped to 400 by the API.
class InstallmentLockedFieldError(DomainError):
    code = "installment_locked_field"
    status_code = 400

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields
        joined = ", ".join(fields)
        self.message = f"Cannot modify locked installment fields ({joined}) after the first installment has been charged."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        # Pre-joined so the scalar `{fields}` placeholder in the frontend apiErrors message renders cleanly.
        return {"fields": ", ".join(self.fields)}


# Re-authentication failed (wrong current password) on a sensitive action. Mapped to 401 by the API.
class InvalidCredentialsError(DomainError):
    code = "invalid_credentials"
    status_code = 401

    def __init__(self, message: str = "The password you entered is incorrect.") -> None:
        self.message = message
        super().__init__(self.message)


# An uploaded import file is unreadable, unsupported, or exceeds limits (ROAD-1). Mapped to 400 by the API.
class InvalidImportFileError(DomainError):
    code = "invalid_import_file"
    status_code = 400

    def __init__(self, message: str = "The file could not be read. Upload a valid .csv, .tsv, or .xlsx file.") -> None:
        self.message = message
        super().__init__(self.message)


# Registration was attempted without a valid invite in invite-only mode (unknown/expired/used token,
# or an email that doesn't match the invite). Mapped to 403 by the API.
class InvalidInviteError(DomainError):
    code = "invalid_invite"
    status_code = 403

    def __init__(self, message: str = "This invite is invalid or has expired. Ask an admin for a new one.") -> None:
        self.message = message
        super().__init__(self.message)


# A refresh token is unknown, expired, revoked, or reused (AUTH-7). Mapped to 401 by the API.
class InvalidRefreshTokenError(DomainError):
    code = "invalid_refresh_token"
    status_code = 401

    def __init__(self, message: str = "Your session has expired. Please log in again.") -> None:
        self.message = message
        super().__init__(self.message)


# A single-use link token is invalid, expired, or already used — the account-lifecycle tokens
# (AUTH-1/2/8) and group-seat invites both raise this, because the condition and the message a user
# needs are identical and the frontend should map the code once. Mapped to 400 by the API.
class InvalidTokenError(DomainError):
    code = "invalid_token"
    status_code = 400

    def __init__(self, message: str = "This link is invalid or has expired. Please request a new one.") -> None:
        self.message = message
        super().__init__(self.message)


# Snapshot/transaction row currency differs from the investment's base currency. Mapped to 400 by the API.
class InvestmentCurrencyMismatchError(DomainError):
    code = "investment_currency_mismatch"
    status_code = 400

    def __init__(self, row_currency: str, base_currency: str) -> None:
        self.row_currency = row_currency
        self.base_currency = base_currency
        self.message = f"Currency {row_currency} does not match the investment's base currency ({base_currency})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"row_currency": self.row_currency, "base_currency": self.base_currency}


# An admin tried to invite an email that already belongs to an account. Mapped to 409 by the API.
class InviteEmailTakenError(DomainError):
    code = "invite_email_taken"
    status_code = 409

    def __init__(self, message: str = "An account with this email already exists.") -> None:
        self.message = message
        super().__init__(self.message)


# Resource not found or not owned by the current user. Mapped to 404 by the API.
class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404

    def __init__(self, message: str = "Not found") -> None:
        self.message = message
        super().__init__(self.message)


# Password appears in a known data breach (HIBP). Mapped to 400 by the API.
class PasswordBreachedError(DomainError):
    code = "password_breached"
    status_code = 400

    def __init__(self) -> None:
        self.message = "This password has appeared in a known data breach. Please choose a different password."
        super().__init__(self.message)


# Payment method / credit card pairing is inconsistent after applying an update (a card id
# kept or set while the effective payment_method is not credit_card). Mapped to 400 by the API.
class PaymentPairingError(DomainError):
    code = "payment_pairing"
    status_code = 400

    def __init__(self) -> None:
        self.message = "credit_card_id requires payment_method to be 'credit_card'."
        super().__init__(self.message)


# The current user's plan does not include this feature; an upgrade is required. Mapped to 402 by the API.
class PlanRequiredError(DomainError):
    code = "plan_required"
    status_code = 402

    def __init__(self, message: str = "This feature requires a Pro plan.") -> None:
        self.message = message
        super().__init__(self.message)


# A pot already has ownership history, so a baseline cannot be recorded under it. The baseline IS the
# division every later percentage derives from and issues units at a nominal 1.00, so it is only ever
# the FIRST entry: retro-fitting one beneath movements already priced at other rates would produce a
# ledger whose units mean two different things. Changing the split after the fact is a re-agreement, a
# different event with a different meaning. Mapped to 409.
#
# The guard is "any event exists", not "an opening exists", and the message says so: deleting a
# baseline keeps the movements that followed it, so a pot can reach this refusal with no opening on
# record at all — and the old wording ("already has an opening baseline") then stated something untrue.
class PotAlreadyOpenedError(DomainError):
    code = "pot_already_opened"
    status_code = 409

    def __init__(self) -> None:
        self.message = "This pot already has ownership history, so a baseline cannot be added under it — a baseline is only ever the first entry."
        super().__init__(self.message)


# A holding cannot simply be taken out of a pot that has already been divided. Removing it drops the
# pot's value by the whole of that holding while nobody's units change — so every co-owner's share
# falls pro-rata and the holding lands wholly in one person's private scope. That is one member
# taking joint assets, and unlike a private expense from a shared account there is no cap on it.
# Before the opening baseline exists nothing has been divided, so nothing can be taken from anyone
# and the move is free — which is also what keeps "undo a mistaken move-in" possible.
# Taking value out of a divided pot is a withdrawal or a buy-out, both of which redeem units.
# Mapped to 409.
class PotAlreadyDividedError(DomainError):
    code = "pot_already_divided"
    status_code = 409

    def __init__(self) -> None:
        self.message = "This pot's ownership is already agreed, so a holding cannot be taken out directly. Record a withdrawal or a buy-out instead."
        super().__init__(self.message)


# A cross-currency ownership movement did not record the amount credited to the pot. `amount` is in
# the private account's currency and the pot's ownership maths runs in its base currency, so with the
# two differing there is no honest way to derive the credited figure — a stored rate is exactly what
# merged constraint (f) forbids. Refused rather than converted at whatever rate happens to be on file,
# the same posture card settlements take (settlement_account_amount_required). Mapped to 400.
class PotBaseAmountRequiredError(DomainError):
    code = "pot_base_amount_required"
    status_code = 400

    def __init__(self, amount_currency: str, base_currency: str) -> None:
        self.amount_currency = amount_currency
        self.base_currency = base_currency
        self.message = f"A movement in {amount_currency} must record the amount credited in the pot's currency ({base_currency})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"amount_currency": self.amount_currency, "base_currency": self.base_currency}


# A pot still holds investments or accounts, so it cannot be deleted. The database refuses it too
# (every pot_id foreign key is ON DELETE RESTRICT); this exists so the refusal arrives as a real
# message instead of an integrity error. Mapped to 409.
class PotHasHoldingsError(DomainError):
    code = "pot_has_holdings"
    status_code = 409

    def __init__(self, holding_count: int) -> None:
        self.holding_count = holding_count
        self.message = f"This pot still holds {holding_count} item(s). Move them out before deleting it."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"holding_count": self.holding_count}


# A withdrawal (or a re-agreement) would move more units than the member actually holds, leaving them
# owning a negative share of the pot. Mapped to 400.
class PotInsufficientUnitsError(DomainError):
    code = "pot_insufficient_units"
    status_code = 400

    def __init__(self, held: Decimal, requested: Decimal) -> None:
        self.held = held
        self.requested = requested
        self.message = f"That is more than this member holds ({requested} requested, {held} available)."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"held": str(self.held), "requested": str(self.requested)}


# An ownership movement names an ARCHIVED account on the pot's side of the boundary. Both NAV queries
# filter on is_active, while the balance union does not — so crediting an archived pot account would
# move that account's balance and NOT the pot's value. Units would then be issued against a NAV that
# never rises, diluting every other owner for nothing: a real transfer of value, from a movement that
# looks ordinary. The private leg has no such coupling (its balance simply moves), so this is the pot
# leg's rule only. Mapped to 400.
class PotMovementAccountInactiveError(DomainError):
    code = "pot_movement_account_inactive"
    status_code = 400

    def __init__(self, account_id: int) -> None:
        self.account_id = account_id
        self.message = "That account is archived, so it is not counted in the pot's value. Restore it before routing money through it."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"account_id": self.account_id}


# An ownership movement is dated before one of the accounts it names existed. Each leg of the balance
# union is bounded by its OWN account's opening_date (opening_balance already IS the balance at that
# date), so a movement dated earlier issues or redeems units while the account it moved the money
# through never changes — value appearing in the pot from nowhere, or leaving it and arriving nowhere.
# The same failure transfer_before_account_opened exists to prevent, and worse here because units are
# issued against it. Mapped to 400.
class PotMovementBeforeAccountOpenedError(DomainError):
    code = "pot_movement_before_account_opened"
    status_code = 400

    def __init__(self, opening_date: date_type) -> None:
        self.opening_date = opening_date
        self.message = f"A movement must be dated on or after its accounts' opening dates (the later one is {opening_date.isoformat()})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"opening_date": self.opening_date.isoformat()}


# A movement was recorded against a pot with no opening baseline yet. Without one there are no units
# outstanding and therefore no unit price, so there is nothing to issue against. Mapped to 400.
class PotNotOpenedError(DomainError):
    code = "pot_not_opened"
    status_code = 400

    def __init__(self) -> None:
        self.message = "This pot has no opening baseline yet, so there is no unit price to record against."
        super().__init__(self.message)


# The opening percentages do not total 100. Refused rather than normalised: quietly rescaling what
# someone typed turns a 90/5 split into a 94.7/5.3 one without telling them. Mapped to 400.
class PotPercentagesError(DomainError):
    code = "pot_percentages_must_total_100"
    status_code = 400

    def __init__(self, total: Decimal) -> None:
        self.total = total
        self.message = f"Ownership percentages must add up to 100 (they add up to {total})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"total": str(self.total)}


# A re-agreement names one member on both sides. It would be a no-op the replay counts twice, which
# the database refuses too. Mapped to 400.
class PotReagreementSameMemberError(DomainError):
    code = "pot_reagreement_same_member"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A re-agreement needs two different members."
        super().__init__(self.message)


# A movement endpoint was given an event type it does not record. An opening and a re-agreement each
# take different inputs and have their own endpoints, so this is a malformed request rather than a
# domain rule being broken. Mapped to 400.
class PotUnsupportedMovementError(DomainError):
    code = "pot_unsupported_movement"
    status_code = 400

    def __init__(self, type: str) -> None:
        self.type = type
        self.message = f"{type} is not a movement; use the opening or re-agreement endpoint."
        super().__init__(self.message)


# A movement needs the pot's value on its date and no valuation is available at or before it, so the
# unit price is undefined. Refused rather than guessed — the same posture as reconciliation refusing
# to invent a figure. Mapped to 400.
class PotValuationRequiredError(DomainError):
    code = "pot_valuation_required"
    status_code = 400

    def __init__(self, as_of_date: date_type) -> None:
        self.as_of_date = as_of_date
        self.message = f"This pot has no known value on {as_of_date.isoformat()}, so units cannot be priced. Record its value on that date first."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"as_of_date": self.as_of_date.isoformat()}


# The caller may see the pot but not change it. Deliberately distinct from a visibility failure,
# which is a 404: this one confirms the pot exists, which is fine to reveal to someone already
# looking at it. Mapped to 403.
class PotWriteRequiredError(DomainError):
    code = "pot_write_required"
    status_code = 403

    def __init__(self) -> None:
        self.message = "You have read-only access to this pot."
        super().__init__(self.message)


# A private expense or income names a funding account that belongs to a pot. The money really leaves
# the shared account, so the pot's value drops and every co-owner's share falls with it — one person
# spending, everyone paying, with nothing recording it. Refused for the same reason a cross-scope
# transfer is: crossing a scope boundary is an ownership event, not a flow. Mapped to 400.
class PrivateEntryFromSharedAccountError(DomainError):
    code = "private_entry_from_shared_account"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A private entry cannot be paid from a shared account. Record a withdrawal from the pot first."
        super().__init__(self.message)


# A direct edit or delete was attempted on an expense / income row a reconciliation created. The row is
# derived, not authored: its amount IS the reconciliation's recorded difference, so mutating it leaves
# the reconciliation intact and lying — the reverse pointer (adjustment_expense_id / adjustment_income_id)
# is ON DELETE SET NULL, so deleting the entry orphans the reconciliation instead of cleaning it up. The
# supported change is to re-run or delete the reconciliation itself, which recomputes or cascade-drops
# its adjustment. Mapped to 409 by the API — the request is well-formed, it conflicts with the row's state.
class ReconciliationOwnedEntryError(DomainError):
    code = "reconciliation_owned_entry"
    status_code = 409

    def __init__(self) -> None:
        self.message = "This entry is a reconciliation's adjustment. Re-run or delete that reconciliation instead of editing the entry."
        super().__init__(self.message)


# Reconciliation period bounds are inconsistent (e.g. period_start > period_end). Mapped to 400 by the API.
class ReconciliationPeriodMismatchError(DomainError):
    code = "reconciliation_period_mismatch"
    status_code = 400

    def __init__(self, message: str = "Reconciliation period is invalid.") -> None:
        self.message = message
        super().__init__(self.message)


# A shared expense is dated before the account funding it existed. Same reason a transfer or a
# settlement cannot be: the balance sums are bounded below by the account's opening_date, so the
# expense would reduce a balance the account never had. Mapped to 400 by the API.
class SharedExpenseBeforeAccountOpenedError(DomainError):
    code = "shared_expense_before_account_opened"
    status_code = 400

    def __init__(self, opening_date: date_type) -> None:
        self.opening_date = opening_date
        self.message = f"A shared expense must be dated on or after its account's opening date ({opening_date.isoformat()})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"opening_date": self.opening_date.isoformat()}


# A shared expense funded from a SHARED account whose pot nobody has divided yet. The money left a pool
# whose owners are not on record, so there is no honest answer to who fronted it — and inventing one
# (splitting it equally, or crediting nobody) would either assert an ownership nobody agreed or leave
# the group's balances not summing to zero. Agree the pot's division first. Mapped to 400 by the API.
class SharedExpenseFundingPotNotDividedError(DomainError):
    code = "shared_expense_funding_pot_not_divided"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Nobody has agreed who owns this shared account's money yet, so there is no way to record who paid. Divide the pot first."
        super().__init__(self.message)


# A shared expense names a funding account that belongs to a pot in a DIFFERENT group. Its owners are
# not members here, so the money they fronted could not be recorded against anyone this group can
# settle with. Mapped to 400 by the API.
class SharedExpenseFundingScopeError(DomainError):
    code = "shared_expense_funding_scope"
    status_code = 400

    def __init__(self) -> None:
        self.message = "That shared account belongs to another group, so this group cannot spend from it."
        super().__init__(self.message)


# A shared expense names both a shared funding account and a payer. Joint money is fronted by the pot's
# owners in their own proportions, so naming one member as the payer would assert something the
# ownership ledger contradicts. Refused rather than ignored: silently dropping a field the user filled
# in is how a form ends up recording something other than what it showed. Mapped to 400 by the API.
class SharedExpenseSharedAccountPayerError(DomainError):
    code = "shared_expense_shared_account_payer"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Money from a shared account is fronted by everyone who owns it, so this expense cannot also name one payer."
        super().__init__(self.message)


# A shared expense names no payer and no shared funding account, so nothing says who fronted the money.
# Without that the group's balances cannot sum to zero: the shares would add up to the total while
# nobody had paid it. Mapped to 400 by the API.
class SharedExpensePayerRequiredError(DomainError):
    code = "shared_expense_payer_required"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Say who paid for this — the balance is what they fronted minus what they used."
        super().__init__(self.message)


# A split names nobody. An expense divided between no one has no share to attribute and no balance to
# create; a self-only expense is a private expense, which is a different table. Mapped to 400.
class SharedExpenseNoParticipantsError(DomainError):
    code = "shared_expense_no_participants"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A shared expense needs at least one person taking part in it."
        super().__init__(self.message)


# A percentage split's figures do not total 100. Never rescaled, for the same reason a pot's opening
# split is not: quietly turning a 90/5 split into 94.7/5.3 is worse than refusing it. Mapped to 400.
class SharedExpensePercentagesError(DomainError):
    code = "shared_expense_percentages"
    status_code = 400

    def __init__(self, stated: Decimal) -> None:
        self.stated = stated
        self.message = f"The split percentages add up to {stated}%, not 100%."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"stated": str(self.stated)}


# A shares split's weights are negative or all zero. Weights are relative parts, so unlike percentages
# they have no total to hit — only the requirement that there is something to divide by, and that no
# part is negative (which would hand one member a share of less than nothing). Mapped to 400.
class SharedExpenseSharesError(DomainError):
    code = "shared_expense_shares"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Shares must not be negative, and at least one person needs a share above zero."
        super().__init__(self.message)


# An exact split's amounts do not add up to the expense's total. There is nothing to round and nothing
# to distribute for this method — the figures are taken as given — so a mismatch is refused rather than
# silently absorbed onto somebody. Mapped to 400 by the API.
class SharedExpenseSplitTotalError(DomainError):
    code = "shared_expense_split_total"
    status_code = 400

    def __init__(self, stated: Decimal, expected: Decimal) -> None:
        self.stated = stated
        self.expected = expected
        self.message = f"The split amounts add up to {stated}, not {expected}."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"stated": str(self.stated), "expected": str(self.expected)}


# A transfer is dated before one of its accounts existed. The balance union bounds each leg by its own
# account's opening_date (opening_balance already IS the balance at that date), so a transfer dated
# before the later-opening account would be counted on one leg and dropped on the other — money would
# leave one account and arrive nowhere, silently changing net worth. Mapped to 400 by the API.
class TransferBeforeAccountOpenedError(DomainError):
    code = "transfer_before_account_opened"
    status_code = 400

    def __init__(self, opening_date: date_type) -> None:
        self.opening_date = opening_date
        self.message = f"A transfer must be dated on or after both accounts' opening dates (the later one is {opening_date.isoformat()})."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"opening_date": self.opening_date.isoformat()}


# A cross-currency transfer did not record the amount credited. Within one currency the credited amount
# mirrors the debited one, but across currencies only the user knows the rate actually used (the blue /
# MEP spread), and inventing one would misstate the destination balance. Mapped to 400 by the API.
class TransferAmountRequiredError(DomainError):
    code = "transfer_amount_required"
    status_code = 400

    def __init__(self, from_currency: str, to_currency: str) -> None:
        self.from_currency = from_currency
        self.to_currency = to_currency
        self.message = f"Moving {from_currency} to {to_currency} must record the amount credited, so the rate used is preserved."
        super().__init__(self.message)

    @property
    def extra(self) -> dict:
        return {"from_currency": self.from_currency, "to_currency": self.to_currency}


# A single-currency transfer credited a different amount than it debited. Money moving between two of
# your own accounts cannot change net worth, so the two sides must match — a bank fee is recorded as its
# own expense rather than silently shrinking the transfer. Mapped to 400 by the API.
class TransferAmountsMustMatchError(DomainError):
    code = "transfer_amounts_must_match"
    status_code = 400

    def __init__(self) -> None:
        self.message = "Within one currency a transfer must credit exactly what it debits. Record a fee as its own expense."
        super().__init__(self.message)


# A transfer names two accounts in different scopes. A transfer is net-worth-neutral BY
# CONSTRUCTION, and that is only true within one scope: moving joint money into a personal account is
# emphatically not neutral for the other owners, it takes value from them. Such a movement is a
# contribution or a withdrawal instead. Mapped to 400.
class TransferCrossScopeError(DomainError):
    code = "transfer_cross_scope"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A transfer must stay within one scope. Moving money in or out of a pot is a contribution or a withdrawal."
        super().__init__(self.message)


# A transfer names the same account on both legs. It would move nothing and the balance union counts each
# leg separately, so the row would be added and subtracted on one account. Mapped to 400 by the API.
class TransferSameAccountError(DomainError):
    code = "transfer_same_account"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A transfer must move money between two different accounts."
        super().__init__(self.message)
