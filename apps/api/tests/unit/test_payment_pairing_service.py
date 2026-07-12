from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import PaymentPairingError
from app.models.expense_entry import ExpenseEntry
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.services import (
    card_reconciliation_service,
    expense_service,
    installment_service,
    payment_obligation_service,
    subscription_service,
)

# Tests for the merged effective payment-pairing check the four services run on UPDATE (P06).
# The request schema only sees same-request pairs; the service compares the request fields
# merged over the stored row, so a kept-or-set card id with a non-credit_card effective method
# raises PaymentPairingError before any write. Everything below the service is mocked.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


@pytest.fixture(autouse=True)
def _silence_stale(monkeypatch):
    monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", AsyncMock())


def _expense(*, payment_method: str | None, credit_card_id: int | None) -> ExpenseEntry:
    return ExpenseEntry(
        id=1,
        user_id=1,
        date=date(2026, 6, 5),
        amount=Decimal("100"),
        currency="USD",
        notes=None,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
        source="manual",
    )


class TestUpdateExpensePairing:
    @pytest.mark.asyncio
    async def test_method_away_from_card_keeping_card_raises(self, monkeypatch):
        entry = _expense(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        save_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "save", save_mock)
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await expense_service.update_expense(session, 1, USER, payment_method="cash")

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_simultaneous_clear_passes(self, monkeypatch):
        entry = _expense(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        save_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "save", save_mock)
        session = AsyncMock()

        await expense_service.update_expense(session, 1, USER, payment_method="cash", credit_card_id=None)

        save_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_card_set_on_cash_entry_raises(self, monkeypatch):
        entry = _expense(payment_method="cash", credit_card_id=None)
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        save_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "save", save_mock)
        # Ownership would pass; the pairing check must fire first.
        monkeypatch.setattr(expense_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await expense_service.update_expense(session, 1, USER, credit_card_id=5)

        save_mock.assert_not_called()


def _subscription(*, payment_method: str | None, credit_card_id: int | None) -> Subscription:
    return Subscription(
        id=1,
        user_id=1,
        name="Netflix",
        amount=Decimal("10"),
        currency="USD",
        billing_cycle="monthly",
        next_billing_date=date(2026, 6, 5),
        anchor_day=5,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
        is_active=True,
    )


class TestUpdateSubscriptionPairing:
    @pytest.mark.asyncio
    async def test_method_away_from_card_keeping_card_raises(self, monkeypatch):
        sub = _subscription(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(subscription_service.subscription_repository, "get_by_id", AsyncMock(return_value=sub))
        save_mock = AsyncMock()
        monkeypatch.setattr(subscription_service.subscription_repository, "save", save_mock)
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await subscription_service.update_subscription(session, 1, USER, payment_method="cash")

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_simultaneous_clear_passes(self, monkeypatch):
        sub = _subscription(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(subscription_service.subscription_repository, "get_by_id", AsyncMock(return_value=sub))
        save_mock = AsyncMock()
        monkeypatch.setattr(subscription_service.subscription_repository, "save", save_mock)
        session = AsyncMock()

        await subscription_service.update_subscription(session, 1, USER, payment_method="cash", credit_card_id=None)

        save_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_card_set_on_cash_raises(self, monkeypatch):
        sub = _subscription(payment_method="cash", credit_card_id=None)
        monkeypatch.setattr(subscription_service.subscription_repository, "get_by_id", AsyncMock(return_value=sub))
        save_mock = AsyncMock()
        monkeypatch.setattr(subscription_service.subscription_repository, "save", save_mock)
        monkeypatch.setattr(subscription_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await subscription_service.update_subscription(session, 1, USER, credit_card_id=5)

        save_mock.assert_not_called()


def _installment(*, payment_method: str | None, credit_card_id: int | None) -> Installment:
    return Installment(
        id=1,
        user_id=1,
        name="TV",
        total_amount=Decimal("120"),
        installment_amount=Decimal("10"),
        currency="USD",
        installments_count=12,
        start_date=date(2026, 6, 5),
        current_installment=1,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
        is_active=True,
    )


class TestUpdateInstallmentPairing:
    @pytest.mark.asyncio
    async def test_method_away_from_card_keeping_card_raises(self, monkeypatch):
        inst = _installment(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        save_mock = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "save", save_mock)
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await installment_service.update_installment(session, 1, USER, payment_method="cash")

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_simultaneous_clear_passes(self, monkeypatch):
        inst = _installment(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        save_mock = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "save", save_mock)
        session = AsyncMock()

        await installment_service.update_installment(session, 1, USER, payment_method="cash", credit_card_id=None)

        save_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_card_set_on_cash_raises(self, monkeypatch):
        inst = _installment(payment_method="cash", credit_card_id=None)
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        save_mock = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "save", save_mock)
        monkeypatch.setattr(installment_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await installment_service.update_installment(session, 1, USER, credit_card_id=5)

        save_mock.assert_not_called()


def _obligation(*, payment_method: str | None, credit_card_id: int | None) -> PaymentObligation:
    return PaymentObligation(
        id=1,
        user_id=1,
        name="ABL",
        amount=Decimal("10"),
        currency="USD",
        next_due_date=date(2026, 6, 5),
        anchor_day=5,
        recurrence="monthly",
        payment_method=payment_method,
        credit_card_id=credit_card_id,
        is_active=True,
    )


class TestUpdateObligationPairing:
    @pytest.mark.asyncio
    async def test_method_away_from_card_keeping_card_raises(self, monkeypatch):
        ob = _obligation(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "get_by_id", AsyncMock(return_value=ob))
        save_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", save_mock)
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await payment_obligation_service.update_obligation(session, 1, USER, payment_method="cash")

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_simultaneous_clear_passes(self, monkeypatch):
        ob = _obligation(payment_method="credit_card", credit_card_id=5)
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "get_by_id", AsyncMock(return_value=ob))
        save_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", save_mock)
        session = AsyncMock()

        await payment_obligation_service.update_obligation(session, 1, USER, payment_method="cash", credit_card_id=None)

        save_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_card_set_on_cash_raises(self, monkeypatch):
        ob = _obligation(payment_method="cash", credit_card_id=None)
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "get_by_id", AsyncMock(return_value=ob))
        save_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", save_mock)
        monkeypatch.setattr(payment_obligation_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        session = AsyncMock()

        with pytest.raises(PaymentPairingError):
            await payment_obligation_service.update_obligation(session, 1, USER, credit_card_id=5)

        save_mock.assert_not_called()
