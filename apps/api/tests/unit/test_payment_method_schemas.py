from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.installment import InstallmentCreate, InstallmentUpdate
from app.schemas.payment_obligation import PaymentObligationCreate, PaymentObligationUpdate
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate

# --- request-boundary payment_method enum + pairing rule (P06) ---
#
# payment_method is a canonical StrEnum at the request boundary (cash/credit_card/debit/
# transfer); non-canonical strings 422. The pairing rule (credit_card_id set => method is
# credit_card) is enforced on every Create schema and, same-request-only, on every Update.


# Builders supplying each Create schema's minimal required fields, extended with kwargs.
def _expense_create(**kwargs) -> ExpenseCreate:
    return ExpenseCreate(date=date(2026, 5, 28), amount=Decimal("10.00"), currency="USD", **kwargs)


def _subscription_create(**kwargs) -> SubscriptionCreate:
    return SubscriptionCreate(
        name="Netflix",
        amount=Decimal("10.00"),
        currency="USD",
        billing_cycle="monthly",
        next_billing_date=date(2026, 5, 28),
        **kwargs,
    )


def _installment_create(**kwargs) -> InstallmentCreate:
    return InstallmentCreate(
        name="TV",
        total_amount=Decimal("120.00"),
        installment_amount=Decimal("10.00"),
        currency="USD",
        installments_count=12,
        start_date=date(2026, 5, 28),
        **kwargs,
    )


def _obligation_create(**kwargs) -> PaymentObligationCreate:
    return PaymentObligationCreate(name="ABL", amount=Decimal("10.00"), currency="USD", next_due_date=date(2026, 5, 28), **kwargs)


CREATE_BUILDERS = [_expense_create, _subscription_create, _installment_create, _obligation_create]


class TestPaymentMethodEnum:
    @pytest.mark.parametrize("builder", CREATE_BUILDERS)
    @pytest.mark.parametrize("value", ["cash", "credit_card", "debit", "transfer"])
    def test_canonical_values_accepted(self, builder, value):
        body = builder(payment_method=value)
        assert body.payment_method == value

    @pytest.mark.parametrize("builder", CREATE_BUILDERS)
    @pytest.mark.parametrize("value", ["VISA", "Débito"])
    def test_non_canonical_values_rejected(self, builder, value):
        with pytest.raises(ValidationError):
            builder(payment_method=value)

    @pytest.mark.parametrize("builder", CREATE_BUILDERS)
    def test_empty_string_coerces_to_none(self, builder):
        # RequestBase.clean_strings runs mode="before", so "" becomes None before enum coercion.
        body = builder(payment_method="")
        assert body.payment_method is None


class TestPaymentPairingCreate:
    @pytest.mark.parametrize("builder", CREATE_BUILDERS)
    def test_card_with_credit_card_method_ok(self, builder):
        body = builder(payment_method="credit_card", credit_card_id=5)
        assert body.credit_card_id == 5

    @pytest.mark.parametrize("builder", CREATE_BUILDERS)
    def test_credit_card_method_without_card_ok(self, builder):
        # Locked decision 4: a card-less credit_card entry is allowed (zero-card users, imports).
        body = builder(payment_method="credit_card")
        assert body.credit_card_id is None

    @pytest.mark.parametrize("builder", CREATE_BUILDERS)
    def test_card_with_non_card_method_raises(self, builder):
        with pytest.raises(ValidationError):
            builder(payment_method="cash", credit_card_id=5)

    @pytest.mark.parametrize("builder", CREATE_BUILDERS)
    def test_card_with_method_omitted_raises(self, builder):
        with pytest.raises(ValidationError):
            builder(credit_card_id=5)


class TestPaymentPairingUpdate:
    def test_expense_update_card_with_cash_raises(self):
        with pytest.raises(ValidationError):
            ExpenseUpdate(payment_method="cash", credit_card_id=5)

    def test_expense_update_card_alone_passes_schema(self):
        # Only credit_card_id set — the merged effective check is the service's job.
        body = ExpenseUpdate(credit_card_id=5)
        assert body.credit_card_id == 5

    def test_expense_update_simultaneous_clear_ok(self):
        body = ExpenseUpdate(payment_method="cash", credit_card_id=None)
        assert body.payment_method == "cash"
        assert body.credit_card_id is None

    def test_subscription_update_card_with_cash_raises(self):
        with pytest.raises(ValidationError):
            SubscriptionUpdate(payment_method="cash", credit_card_id=5)

    def test_installment_update_card_with_cash_raises(self):
        with pytest.raises(ValidationError):
            InstallmentUpdate(payment_method="cash", credit_card_id=5)

    def test_obligation_update_card_with_cash_raises(self):
        with pytest.raises(ValidationError):
            PaymentObligationUpdate(payment_method="cash", credit_card_id=5)
