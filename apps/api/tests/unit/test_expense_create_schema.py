from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.expense import ExpenseCreate

# --- ExpenseCreate.validate_commitment_link_exclusivity ---

# Mutual exclusivity rule (Phase 3, follow-up 3a): at most one of payment_obligation_id /
# subscription_id / installment_id may be set on the same insert. An expense pays exactly
# one commitment-type; allowing two FKs would let the same row appear as both a
# subscription charge and an installment charge and cause divergent advance semantics.

BASE_FIELDS = {
    "date": date(2026, 5, 28),
    "amount": Decimal("10.00"),
    "currency": "USD",
}


class TestExpenseCreateCommitmentLinkExclusivity:
    def test_no_links_is_valid(self):
        body = ExpenseCreate(**BASE_FIELDS)
        assert body.payment_obligation_id is None
        assert body.subscription_id is None
        assert body.installment_id is None

    def test_only_payment_obligation_id_is_valid(self):
        body = ExpenseCreate(**BASE_FIELDS, payment_obligation_id=7)
        assert body.payment_obligation_id == 7
        assert body.subscription_id is None
        assert body.installment_id is None

    def test_only_subscription_id_is_valid(self):
        body = ExpenseCreate(**BASE_FIELDS, subscription_id=3)
        assert body.subscription_id == 3
        assert body.payment_obligation_id is None
        assert body.installment_id is None

    def test_only_installment_id_is_valid(self):
        body = ExpenseCreate(**BASE_FIELDS, installment_id=11)
        assert body.installment_id == 11
        assert body.payment_obligation_id is None
        assert body.subscription_id is None

    def test_obligation_and_subscription_together_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, payment_obligation_id=7, subscription_id=3)

    def test_obligation_and_installment_together_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, payment_obligation_id=7, installment_id=11)

    def test_subscription_and_installment_together_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, subscription_id=3, installment_id=11)

    def test_all_three_links_together_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(
                **BASE_FIELDS,
                payment_obligation_id=7,
                subscription_id=3,
                installment_id=11,
            )
