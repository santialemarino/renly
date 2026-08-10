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


# An account-lifecycle token is invalid, expired, or already used (AUTH-1/2/8). Mapped to 400 by the API.
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


# A transfer names the same account on both legs. It would move nothing and the balance union counts each
# leg separately, so the row would be added and subtracted on one account. Mapped to 400 by the API.
class TransferSameAccountError(DomainError):
    code = "transfer_same_account"
    status_code = 400

    def __init__(self) -> None:
        self.message = "A transfer must move money between two different accounts."
        super().__init__(self.message)
