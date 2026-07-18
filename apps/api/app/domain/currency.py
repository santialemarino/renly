# Currency support registry and dollar rate preference resolution.
# All rates are stored against USD; any pair converts via USD as pivot.
# The dollar rate preference (oficial/mep/blue) determines which USD/ARS rate to use.

from app.models.exchange_rate import ExchangeRatePair
from app.models.investment import Currency

# All currencies Renly supports, derived from the Currency enum (the single source of truth) so the
# two never drift. Every member has exchange-rate support (USD is the pivot; the rest have a USD pair).
SUPPORTED_CURRENCIES = frozenset(c.value for c in Currency)

# Maps dollar rate preference string to the ExchangeRatePair for USD/ARS.
_DOLLAR_RATE_PAIRS: dict[str, ExchangeRatePair] = {
    "oficial": ExchangeRatePair.USD_ARS_OFICIAL,
    "mep": ExchangeRatePair.USD_ARS_MEP,
    "blue": ExchangeRatePair.USD_ARS_BLUE,
}

DOLLAR_RATE_DEFAULT = "mep"


# Returns the ExchangeRatePair for USD/ARS based on the dollar preference. A falsy or unknown
# preference both resolve to the DOLLAR_RATE_DEFAULT pair (single default, no drift).
def get_ars_pair(preference: str | None = None) -> ExchangeRatePair:
    return _DOLLAR_RATE_PAIRS.get(preference or DOLLAR_RATE_DEFAULT, _DOLLAR_RATE_PAIRS[DOLLAR_RATE_DEFAULT])


# Returns True when the currency code has exchange-rate support.
def is_supported(code: str) -> bool:
    return code in SUPPORTED_CURRENCIES
