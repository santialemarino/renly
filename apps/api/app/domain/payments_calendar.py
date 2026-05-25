# Value objects for the Payments Calendar service.

from datetime import date as date_type
from decimal import Decimal
from typing import NamedTuple


# A single event on the Payments Calendar timeline. `type` discriminates the
# source entity: 'subscription' | 'installment' | 'obligation' | 'card_due'.
# Type-specific fields (cuota_index, installments_count, recurrence, is_paid,
# conversion_date) are populated only by their respective sources and remain
# None / False elsewhere.
class CalendarItem(NamedTuple):
    type: str
    date: date_type
    name: str
    amount: Decimal
    currency: str
    source_id: int
    payment_method: str | None = None
    credit_card_id: int | None = None
    cuota_index: int | None = None
    installments_count: int | None = None
    recurrence: str | None = None
    is_paid: bool = False
    conversion_date: date_type | None = None  # FX-conversion anchor; overrides `date` when set (paid obligations use linked expense date)
