# Currency code parsing for USD variants (USD, USD_MEP, USD_BLUE).
# "USD" = oficial rate (default), "USD_MEP" = MEP/bolsa rate, "USD_BLUE" = blue/parallel rate.
# Non-USD codes pass through unchanged.

from app.models.exchange_rate import ExchangeRatePair

# Maps virtual currency suffix to the exchange rate pair used for ARS conversion.
_USD_VARIANT_PAIRS: dict[str, ExchangeRatePair] = {
    "USD": ExchangeRatePair.USD_ARS_OFICIAL,
    "USD_MEP": ExchangeRatePair.USD_ARS_MEP,
    "USD_BLUE": ExchangeRatePair.USD_ARS_BLUE,
}

# All virtual currency codes that resolve to USD.
USD_VARIANTS = frozenset(_USD_VARIANT_PAIRS.keys())


def parse_currency(code: str) -> tuple[str, ExchangeRatePair | None]:
    """Returns (base_currency, preferred_pair). Non-USD codes return (code, None)."""
    if code in _USD_VARIANT_PAIRS:
        return "USD", _USD_VARIANT_PAIRS[code]
    return code, None


def base_currency(code: str) -> str:
    """Strips the variant suffix — e.g. 'USD_MEP' -> 'USD', 'ARS' -> 'ARS'."""
    if code in USD_VARIANTS:
        return "USD"
    return code


def is_usd_variant(code: str) -> bool:
    return code in USD_VARIANTS
