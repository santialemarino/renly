# Currency support registry and dollar rate preference resolution.
# All rates are stored against USD; any pair converts via USD as pivot.
# The dollar rate preference (oficial/mep/blue) determines which USD/ARS rate to use.

from app.models.exchange_rate import ExchangeRatePair

# All currencies with exchange rate support.
SUPPORTED_CURRENCIES = frozenset({"USD", "ARS", "BRL", "EUR", "GBP"})

# Maps dollar rate preference string to the ExchangeRatePair for USD/ARS.
_DOLLAR_RATE_PAIRS: dict[str, ExchangeRatePair] = {
    "oficial": ExchangeRatePair.USD_ARS_OFICIAL,
    "mep": ExchangeRatePair.USD_ARS_MEP,
    "blue": ExchangeRatePair.USD_ARS_BLUE,
}

DOLLAR_RATE_DEFAULT = "mep"


def get_ars_pair(preference: str | None = None) -> ExchangeRatePair:
    """Returns the ExchangeRatePair for USD/ARS based on the dollar preference."""
    return _DOLLAR_RATE_PAIRS.get(preference or DOLLAR_RATE_DEFAULT, ExchangeRatePair.USD_ARS_MEP)


def is_supported(code: str) -> bool:
    return code in SUPPORTED_CURRENCIES
