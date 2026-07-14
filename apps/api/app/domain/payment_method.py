# Payment method value object shared by expenses, subscriptions, installments, and
# payment obligations. The DB columns stay free-text VARCHAR(20); this enum is the
# request-boundary contract.

from enum import StrEnum


# Canonical payment method values accepted by entry/plan request schemas.
class PaymentMethod(StrEnum):
    cash = "cash"
    credit_card = "credit_card"
    debit = "debit"
    transfer = "transfer"


# Raises ValueError when credit_card_id is set with a non-card payment_method. A card-less
# credit_card entry IS allowed (zero-card users and imports carry no card id). Used by the
# request-schema validators; services raise the PaymentPairingError domain error instead.
def ensure_payment_pairing(payment_method: str | None, credit_card_id: int | None) -> None:
    if credit_card_id is not None and payment_method != PaymentMethod.credit_card:
        raise ValueError("credit_card_id requires payment_method to be 'credit_card'.")
