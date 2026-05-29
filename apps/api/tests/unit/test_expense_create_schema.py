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


# --- ExpenseCreate.cycles_to_advance ---

# Multi-cycle Mark Paid (Phase 3, follow-up Item 2): N >= 1, capped at 12. cycles > 1
# requires payment_obligation_id (multi-cycle is meaningful only for a recurring
# obligation; the obligation-recurrence DB check lives in the service). sub/installment
# IDs are forbidden alongside cycles > 1 — caught by the mutual-exclusivity rule above
# since cycles > 1 requires obligation set.


class TestExpenseCreateCyclesToAdvance:
    def test_default_is_one(self):
        body = ExpenseCreate(**BASE_FIELDS)
        assert body.cycles_to_advance == 1

    def test_minimum_value_is_one(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, cycles_to_advance=0)

    def test_maximum_value_is_twelve(self):
        body = ExpenseCreate(**BASE_FIELDS, payment_obligation_id=7, cycles_to_advance=12)
        assert body.cycles_to_advance == 12

    def test_above_twelve_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, payment_obligation_id=7, cycles_to_advance=13)

    def test_cycles_one_without_obligation_is_valid(self):
        # cycles=1 path is the standard single-row create — no obligation requirement.
        body = ExpenseCreate(**BASE_FIELDS, cycles_to_advance=1)
        assert body.cycles_to_advance == 1
        assert body.payment_obligation_id is None

    def test_cycles_above_one_without_obligation_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, cycles_to_advance=3)

    def test_cycles_above_one_with_subscription_rejected(self):
        # cycles>1 + subscription_id violates the mutex-with-obligation rule indirectly:
        # cycles>1 requires obligation set, but obligation + subscription is mutually
        # exclusive. ValidationError is raised for the missing-obligation reason.
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, subscription_id=3, cycles_to_advance=3)

    def test_cycles_above_one_with_installment_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(**BASE_FIELDS, installment_id=11, cycles_to_advance=3)

    def test_cycles_above_one_with_obligation_is_valid(self):
        body = ExpenseCreate(**BASE_FIELDS, payment_obligation_id=7, cycles_to_advance=4)
        assert body.cycles_to_advance == 4
        assert body.payment_obligation_id == 7
