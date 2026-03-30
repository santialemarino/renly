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


# Resource not found or not owned by the current user. Mapped to 404 by the API.
class NotFoundError(Exception):
    def __init__(self, message: str = "Not found") -> None:
        self.message = message
        super().__init__(message)
