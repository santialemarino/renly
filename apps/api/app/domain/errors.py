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


# Reconciliation period bounds are inconsistent (e.g. period_start > period_end). Mapped to 400 by the API.
class ReconciliationPeriodMismatchError(DomainError):
    code = "reconciliation_period_mismatch"
    status_code = 400

    def __init__(self, message: str = "Reconciliation period is invalid.") -> None:
        self.message = message
        super().__init__(self.message)
