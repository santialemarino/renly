from typing import Annotated

from fastapi import Depends, Query

# Human-facing description for the display-currency query param, shared by every read endpoint.
CURRENCY_DESC = "Display currency (e.g. USD, ARS). Omit for original."


# Normalizes the optional display-currency query param to uppercase. The rate maps are
# uppercase-keyed, so a lowercase code (?currency=usd) would otherwise miss every lookup and
# silently skip conversion instead of converting. Display-only: the code is NOT restricted to the
# supported set (the P02 display param stays unrestricted; only finance-entry currencies are
# validated).
#
# ▸ What an UNSUPPORTED code actually does, because "it just leaves rows in their original currency"
# is only half of it and this comment used to say exactly that. A ROW does fall back: its
# `converted_*` field comes back null and the UI renders the original amount labelled with its own
# currency. An AGGREGATE cannot — there is one number and it can only be in one scale — so every row
# is EXCLUDED and the total reads 0, with every source currency named in `skipped_currencies`.
# Measured: two rows worth 1,974.53 USD total 0 under an unsupported display currency. Any surface
# showing a total therefore has to render the skip hint, or it reports a number that is simply wrong.
def _display_currency(currency: str | None = Query(default=None, description=CURRENCY_DESC)) -> str | None:
    return currency.upper() if currency else None


DisplayCurrency = Annotated[str | None, Depends(_display_currency)]
