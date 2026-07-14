from typing import Annotated

from fastapi import Depends, Query

# Human-facing description for the display-currency query param, shared by every read endpoint.
CURRENCY_DESC = "Display currency (e.g. USD, ARS). Omit for original."


# Normalizes the optional display-currency query param to uppercase. The rate maps are
# uppercase-keyed, so a lowercase code (?currency=usd) would otherwise miss every lookup and
# silently skip conversion instead of converting. Display-only: the code is NOT restricted to the
# supported set — an unsupported code simply leaves rows in their original currency (the P02
# display param stays unrestricted; only finance-entry currencies are validated).
def _display_currency(currency: str | None = Query(default=None, description=CURRENCY_DESC)) -> str | None:
    return currency.upper() if currency else None


DisplayCurrency = Annotated[str | None, Depends(_display_currency)]
