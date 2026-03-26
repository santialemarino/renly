# Currency code parsing and supported-currency registry.
# USD variants: "USD" = oficial, "USD_MEP" = MEP, "USD_BLUE" = blue.
# All rates are stored against USD; any pair converts via USD as pivot.

from app.models.exchange_rate import ExchangeRatePair

# Maps every supported currency code to its USD-based ExchangeRatePair.
# USD variants map to their specific ARS pair; other currencies map to their USD pair.
_CURRENCY_PAIRS: dict[str, ExchangeRatePair] = {
    "USD": ExchangeRatePair.USD_ARS_OFICIAL,
    "USD_MEP": ExchangeRatePair.USD_ARS_MEP,
    "USD_BLUE": ExchangeRatePair.USD_ARS_BLUE,
    "ARS": ExchangeRatePair.USD_ARS_OFICIAL,
    "BRL": ExchangeRatePair.USD_BRL,
    "EUR": ExchangeRatePair.USD_EUR,
    "GBP": ExchangeRatePair.USD_GBP,
}

# All virtual currency codes that resolve to USD.
USD_VARIANTS = frozenset({"USD", "USD_MEP", "USD_BLUE"})

# All currency codes with exchange rate support (including USD variants).
SUPPORTED_CURRENCIES = frozenset(_CURRENCY_PAIRS.keys())


def parse_currency(code: str) -> tuple[str, ExchangeRatePair | None]:
    """Returns (base_currency, preferred_pair). Unknown codes return (code, None)."""
    pair = _CURRENCY_PAIRS.get(code)
    if code in USD_VARIANTS:
        return "USD", pair
    return code, pair


def base_currency(code: str) -> str:
    """Strips the variant suffix — e.g. 'USD_MEP' -> 'USD', 'ARS' -> 'ARS'."""
    if code in USD_VARIANTS:
        return "USD"
    return code


def is_usd_variant(code: str) -> bool:
    return code in USD_VARIANTS


def is_supported(code: str) -> bool:
    return code in SUPPORTED_CURRENCIES
