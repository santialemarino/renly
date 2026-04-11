# Value objects for credit card domain.

from decimal import Decimal
from typing import NamedTuple


class CardBalance(NamedTuple):
    balance: Decimal
    has_mixed_currencies: bool
