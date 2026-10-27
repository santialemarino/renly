from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.installment import InstallmentCreate, InstallmentUpdate
from app.schemas.payment_obligation import PaymentObligationCreate, PaymentObligationUpdate
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate

# A new subscription, installment plan or payment obligation always starts active; `is_active` is an
# Update-only field. A Create body that sends it is refused with a 422 rather than having the field
# silently dropped — a client sending `is_active: false` would otherwise believe it created an
# archived plan and get an active one.

_CREATES = [
    (
        SubscriptionCreate,
        {"name": "Netflix", "amount": Decimal("10"), "currency": "USD", "billing_cycle": "monthly", "next_billing_date": date(2026, 11, 1)},
    ),
    (
        InstallmentCreate,
        {
            "name": "TV",
            "total_amount": Decimal("120"),
            "installment_amount": Decimal("10"),
            "currency": "ARS",
            "installments_count": 12,
            "start_date": date(2026, 11, 1),
        },
    ),
    (PaymentObligationCreate, {"name": "ABL", "amount": Decimal("50"), "currency": "ARS", "next_due_date": date(2026, 11, 10)}),
]


class TestIsActiveIsRefusedOnCreate:
    @pytest.mark.parametrize(("schema", "body"), _CREATES, ids=lambda v: getattr(v, "__name__", ""))
    def test_a_body_without_it_is_accepted(self, schema, body):
        assert schema(**body).name == body["name"]

    @pytest.mark.parametrize("value", [True, False])
    @pytest.mark.parametrize(("schema", "body"), _CREATES, ids=lambda v: getattr(v, "__name__", ""))
    def test_a_body_with_it_is_refused(self, schema, body, value):
        with pytest.raises(ValidationError, match="is_active cannot be set on create"):
            schema(**body, is_active=value)


class TestIsActiveStaysAcceptedOnUpdate:
    @pytest.mark.parametrize("schema", [SubscriptionUpdate, InstallmentUpdate, PaymentObligationUpdate], ids=lambda v: v.__name__)
    def test_archive_and_unarchive_still_work(self, schema):
        assert schema(is_active=False).is_active is False
        assert schema(is_active=True).is_active is True
