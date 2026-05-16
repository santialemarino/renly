# Value objects for credit card domain.

from decimal import Decimal
from typing import NamedTuple


# Per-currency bucket balance on a credit card. Phase 3 Step 1.5 (dual-currency
# buckets, Option B): a card carries one bucket per currency with activity,
# matching how Argentine resúmenes show "Saldo en pesos" and "Saldo en dólares"
# on the same physical card. Single-currency cards return exactly one bucket.
class CardBucketBalance(NamedTuple):
    currency: str
    balance: Decimal
