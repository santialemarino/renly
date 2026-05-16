from datetime import date
from decimal import Decimal

from app.models.installment import Installment
from app.services.installment_service import LOCKED_FIELDS, diff_locked_fields


def _make_installment(**overrides: object) -> Installment:
    defaults: dict[str, object] = {
        "id": 1,
        "user_id": 1,
        "name": "TV Samsung",
        "total_amount": Decimal("120000"),
        "installment_amount": Decimal("10000"),
        "currency": "ARS",
        "installments_count": 12,
        "current_installment": 4,
        "start_date": date(2026, 1, 15),
        "payment_method": "credit_card",
        "credit_card_id": 1,
        "is_active": True,
    }
    defaults.update(overrides)
    return Installment(**defaults)


# --- LOCKED_FIELDS contract ---


class TestLockedFieldsContract:
    def test_locks_all_contractual_fields(self):
        # Per decision doc: total_amount, installment_amount, installments_count,
        # currency, start_date, payment_method, credit_card_id are locked once charged.
        assert set(LOCKED_FIELDS) == {
            "total_amount",
            "installment_amount",
            "installments_count",
            "currency",
            "start_date",
            "payment_method",
            "credit_card_id",
        }

    def test_does_not_lock_always_editable_fields(self):
        # Always-editable: name, current_installment, is_active.
        for f in ("name", "current_installment", "is_active"):
            assert f not in LOCKED_FIELDS


# --- diff_locked_fields ---


class TestDiffLockedFields:
    def test_no_locked_fields_changed_returns_empty(self):
        existing = _make_installment()
        # Editable fields touched only.
        violated = diff_locked_fields(existing, {"name": "New Name", "current_installment": 5, "is_active": False})
        assert violated == []

    def test_changing_total_amount_is_violation(self):
        existing = _make_installment()
        violated = diff_locked_fields(existing, {"total_amount": Decimal("130000")})
        assert violated == ["total_amount"]

    def test_changing_installment_amount_is_violation(self):
        existing = _make_installment()
        violated = diff_locked_fields(existing, {"installment_amount": Decimal("11000")})
        assert violated == ["installment_amount"]

    def test_changing_installments_count_is_violation(self):
        existing = _make_installment()
        violated = diff_locked_fields(existing, {"installments_count": 18})
        assert violated == ["installments_count"]

    def test_changing_currency_is_violation(self):
        existing = _make_installment()
        violated = diff_locked_fields(existing, {"currency": "USD"})
        assert violated == ["currency"]

    def test_changing_start_date_is_violation(self):
        existing = _make_installment()
        violated = diff_locked_fields(existing, {"start_date": date(2026, 2, 1)})
        assert violated == ["start_date"]

    def test_changing_payment_method_is_violation(self):
        existing = _make_installment()
        violated = diff_locked_fields(existing, {"payment_method": "cash"})
        assert violated == ["payment_method"]

    def test_changing_credit_card_id_is_violation(self):
        existing = _make_installment()
        violated = diff_locked_fields(existing, {"credit_card_id": 2})
        assert violated == ["credit_card_id"]

    def test_multiple_violations_listed(self):
        existing = _make_installment()
        violated = diff_locked_fields(
            existing,
            {"total_amount": Decimal("999"), "currency": "USD", "name": "rename ok"},
        )
        # Order matches LOCKED_FIELDS — total_amount first, currency next; name is editable.
        assert violated == ["total_amount", "currency"]

    def test_noop_write_with_same_values_is_allowed(self):
        # Partial PUTs often echo unchanged fields. Same-value writes should not error.
        existing = _make_installment()
        violated = diff_locked_fields(
            existing,
            {
                "total_amount": Decimal("120000"),
                "installment_amount": Decimal("10000"),
                "currency": "ARS",
                "start_date": date(2026, 1, 15),
                "payment_method": "credit_card",
                "credit_card_id": 1,
                "installments_count": 12,
            },
        )
        assert violated == []

    def test_decimal_equality_with_different_scales(self):
        # Decimal('120000') == Decimal('120000.00') — same numeric value.
        existing = _make_installment(total_amount=Decimal("120000"))
        violated = diff_locked_fields(existing, {"total_amount": Decimal("120000.00")})
        assert violated == []
