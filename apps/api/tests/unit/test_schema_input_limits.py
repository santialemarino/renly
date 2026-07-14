from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.investment import Currency, InvestmentCategory
from app.models.transaction import TransactionType
from app.schemas.card_settlement import CardSettlementCreate
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.income import IncomeCreate, IncomeUpdate
from app.schemas.investment import InvestmentCreate, InvestmentUpdate
from app.schemas.payment_obligation import PaymentObligationCreate, PaymentObligationUpdate
from app.schemas.snapshot import SnapshotCreate
from app.schemas.transaction import TransactionCreate, TransactionUpdate

# Input-length coverage for SEC-12 (schema-field caps): every uncapped free-text
# `notes` field on the finance request schemas now carries max_length, so an
# over-length note is rejected at the request boundary rather than reaching storage.

NOTES_MAX_LENGTH = 500

# Each entry is (id, request_schema, minimal_valid_kwargs) for a schema whose `notes`
# field was capped. Create bodies carry their required fields; partial-update bodies
# accept notes alone. Currency is the plain ISO string for expense/income/settlement/
# obligation and the Currency enum for transaction/snapshot.
_CAPPED_NOTES_SCHEMAS = [
    ("ExpenseCreate", ExpenseCreate, {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": "USD"}),
    ("ExpenseUpdate", ExpenseUpdate, {}),
    ("IncomeCreate", IncomeCreate, {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": "USD"}),
    ("IncomeUpdate", IncomeUpdate, {}),
    ("CardSettlementCreate", CardSettlementCreate, {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": "USD"}),
    (
        "TransactionCreate",
        TransactionCreate,
        {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": Currency.USD, "type": TransactionType.buy},
    ),
    ("TransactionUpdate", TransactionUpdate, {}),
    ("SnapshotCreate", SnapshotCreate, {"date": date(2026, 1, 1), "value": Decimal("100.00"), "currency": Currency.USD}),
    ("InvestmentCreate", InvestmentCreate, {"name": "Apple", "category": InvestmentCategory.stocks, "base_currency": "USD"}),
    ("InvestmentUpdate", InvestmentUpdate, {}),
    (
        "PaymentObligationCreate",
        PaymentObligationCreate,
        {"name": "Electricity", "amount": Decimal("100.00"), "currency": "USD", "next_due_date": date(2026, 1, 1)},
    ),
    ("PaymentObligationUpdate", PaymentObligationUpdate, {}),
]


# A note exactly at the cap is accepted and preserved verbatim.
@pytest.mark.parametrize("schema", [s for _, s, _ in _CAPPED_NOTES_SCHEMAS], ids=[i for i, _, _ in _CAPPED_NOTES_SCHEMAS])
def test_notes_at_max_length_accepted(schema):
    base = next(kwargs for _, s, kwargs in _CAPPED_NOTES_SCHEMAS if s is schema)
    note = "x" * NOTES_MAX_LENGTH
    body = schema(**base, notes=note)
    assert body.notes == note


# A note one character over the cap is rejected at construction.
@pytest.mark.parametrize("schema", [s for _, s, _ in _CAPPED_NOTES_SCHEMAS], ids=[i for i, _, _ in _CAPPED_NOTES_SCHEMAS])
def test_notes_over_max_length_rejected(schema):
    base = next(kwargs for _, s, kwargs in _CAPPED_NOTES_SCHEMAS if s is schema)
    with pytest.raises(ValidationError):
        schema(**base, notes="x" * (NOTES_MAX_LENGTH + 1))


# A zero or negative transaction amount is rejected — a negative "deposit" would silently
# flip to a withdrawal in every downstream formula.
@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-5.00")])
def test_transaction_amount_must_be_positive(amount):
    kwargs = {"date": date(2026, 1, 1), "currency": Currency.USD, "type": TransactionType.buy}
    with pytest.raises(ValidationError):
        TransactionCreate(amount=amount, **kwargs)
    with pytest.raises(ValidationError):
        TransactionUpdate(amount=amount)


# Snapshot value zero is legitimate (a fully-withdrawn investment); negative is not.
def test_snapshot_value_zero_accepted_negative_rejected():
    kwargs = {"date": date(2026, 1, 1), "currency": Currency.USD}
    body = SnapshotCreate(value=Decimal("0"), **kwargs)
    assert body.value == Decimal("0")
    with pytest.raises(ValidationError):
        SnapshotCreate(value=Decimal("-1.00"), **kwargs)
