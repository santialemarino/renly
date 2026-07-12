# Domain errors, raised by services; the HTTP layer maps them to status codes and responses.


# Investment currency cannot be changed because snapshots exist. Mapped to 409 by the API.
class CurrencyChangeBlockedError(Exception):
    def __init__(self) -> None:
        self.message = "Currency cannot be changed because this investment has snapshots."
        super().__init__(self.message)


# Currency conversion requested but no exchange rates are available. Mapped to 503 by the API.
class ExchangeRateUnavailableError(Exception):
    def __init__(self, currency: str) -> None:
        self.message = f"Exchange rates unavailable. Cannot convert to {currency}."
        self.currency = currency
        super().__init__(self.message)


# Operation conflicts with current state (e.g. deleting a card with linked expenses). Mapped to 409 by the API.
class HasLinkedExpensesError(Exception):
    def __init__(self) -> None:
        self.message = "Cannot delete a credit card that has linked expenses. Archive it instead."
        super().__init__(self.message)


# Attempt to modify locked contractual fields on an installment after the first installment was charged. Mapped to 400 by the API.
class InstallmentLockedFieldError(Exception):
    code = "installment_locked_field"

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields
        joined = ", ".join(fields)
        self.message = f"Cannot modify locked installment fields ({joined}) after the first installment has been charged."
        super().__init__(self.message)


# Email address has not been verified yet; login (or a gated action) is blocked. Mapped to 403 by the API.
class EmailNotVerifiedError(Exception):
    def __init__(self, message: str = "Please verify your email address before logging in.") -> None:
        self.message = message
        super().__init__(message)


# Re-authentication failed (wrong current password) on a sensitive action. Mapped to 401 by the API.
class InvalidCredentialsError(Exception):
    def __init__(self, message: str = "The password you entered is incorrect.") -> None:
        self.message = message
        super().__init__(message)


# An uploaded import file is unreadable, unsupported, or exceeds limits (ROAD-1). Mapped to 400 by the API.
class InvalidImportFileError(Exception):
    def __init__(self, message: str = "The file could not be read. Upload a valid .csv, .tsv, or .xlsx file.") -> None:
        self.message = message
        super().__init__(message)


# A refresh token is unknown, expired, revoked, or reused (AUTH-7). Mapped to 401 by the API.
class InvalidRefreshTokenError(Exception):
    def __init__(self, message: str = "Your session has expired. Please log in again.") -> None:
        self.message = message
        super().__init__(message)


# An account-lifecycle token is invalid, expired, or already used (AUTH-1/2/8). Mapped to 400 by the API.
class InvalidTokenError(Exception):
    def __init__(self, message: str = "This link is invalid or has expired. Please request a new one.") -> None:
        self.message = message
        super().__init__(message)


# Registration was attempted without a valid invite in invite-only mode (unknown/expired/used token,
# or an email that doesn't match the invite). Mapped to 403 by the API.
class InvalidInviteError(Exception):
    def __init__(self, message: str = "This invite is invalid or has expired. Ask an admin for a new one.") -> None:
        self.message = message
        super().__init__(message)


# Snapshot/transaction row currency differs from the investment's base currency. Mapped to 400 by the API.
class InvestmentCurrencyMismatchError(Exception):
    def __init__(self, row_currency: str, base_currency: str) -> None:
        self.message = f"Currency {row_currency} does not match the investment's base currency ({base_currency})."
        super().__init__(self.message)


# An admin tried to invite an email that already belongs to an account. Mapped to 409 by the API.
class InviteEmailTakenError(Exception):
    def __init__(self, message: str = "An account with this email already exists.") -> None:
        self.message = message
        super().__init__(message)


# Resource not found or not owned by the current user. Mapped to 404 by the API.
class NotFoundError(Exception):
    def __init__(self, message: str = "Not found") -> None:
        self.message = message
        super().__init__(message)


# Password appears in a known data breach (HIBP). Mapped to 400 by the API.
class PasswordBreachedError(Exception):
    def __init__(self) -> None:
        self.message = "This password has appeared in a known data breach. Please choose a different password."
        super().__init__(self.message)


# The current user's plan does not include this feature; an upgrade is required. Mapped to 402 by the API.
class PlanRequiredError(Exception):
    def __init__(self, message: str = "This feature requires a Pro plan.") -> None:
        self.message = message
        super().__init__(message)


# Reconciliation period bounds are inconsistent (e.g. period_start > period_end). Mapped to 400 by the API.
class ReconciliationPeriodMismatchError(Exception):
    def __init__(self, message: str = "Reconciliation period is invalid.") -> None:
        self.message = message
        super().__init__(message)
