from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import NotFoundError
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.services import installment_service, payment_obligation_service, subscription_service

# SEC-4 for plans: subscription / installment / payment-obligation create + update must reject
# a credit_card_id the user doesn't own (the FK bypasses RLS), exactly like expenses. The card
# ownership lookup is skipped when an update leaves credit_card_id unchanged. All persistence is
# mocked so the tests pin the guard.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


# --- Subscription ---


class TestCreateSubscriptionOwnership:
    @pytest.mark.asyncio
    async def test_foreign_card_raises_before_create(self, monkeypatch):
        monkeypatch.setattr(subscription_service.credit_card_repository, "get_by_id", AsyncMock(return_value=None))
        create_mock = AsyncMock()
        monkeypatch.setattr(subscription_service.subscription_repository, "create", create_mock)
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await subscription_service.create_subscription(
                session,
                USER,
                name="Netflix",
                amount=Decimal("10"),
                currency="USD",
                billing_cycle="monthly",
                next_billing_date=date(2026, 6, 5),
                payment_method="credit_card",
                credit_card_id=42,
            )

        create_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_owned_card_proceeds_to_create(self, monkeypatch):
        monkeypatch.setattr(subscription_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        created = Subscription(
            id=1,
            user_id=1,
            name="Netflix",
            amount=Decimal("10"),
            currency="USD",
            billing_cycle="monthly",
            next_billing_date=date(2026, 6, 5),
            anchor_day=5,
            is_active=True,
        )
        create_mock = AsyncMock(return_value=created)
        monkeypatch.setattr(subscription_service.subscription_repository, "create", create_mock)
        session = AsyncMock()

        await subscription_service.create_subscription(
            session,
            USER,
            name="Netflix",
            amount=Decimal("10"),
            currency="USD",
            billing_cycle="monthly",
            next_billing_date=date(2026, 6, 5),
            payment_method="credit_card",
            credit_card_id=42,
        )

        create_mock.assert_awaited_once()


def _subscription(*, credit_card_id: int | None) -> Subscription:
    return Subscription(
        id=1,
        user_id=1,
        name="Netflix",
        amount=Decimal("10"),
        currency="USD",
        billing_cycle="monthly",
        next_billing_date=date(2026, 6, 5),
        anchor_day=5,
        payment_method="credit_card" if credit_card_id is not None else None,
        credit_card_id=credit_card_id,
        is_active=True,
    )


class TestUpdateSubscriptionOwnership:
    @pytest.mark.asyncio
    async def test_change_to_foreign_card_raises_before_save(self, monkeypatch):
        sub = _subscription(credit_card_id=5)
        monkeypatch.setattr(subscription_service.subscription_repository, "get_by_id", AsyncMock(return_value=sub))
        save_mock = AsyncMock()
        monkeypatch.setattr(subscription_service.subscription_repository, "save", save_mock)
        monkeypatch.setattr(subscription_service.credit_card_repository, "get_by_id", AsyncMock(return_value=None))
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await subscription_service.update_subscription(session, 1, USER, credit_card_id=99)

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_unchanged_card_skips_ownership_lookup(self, monkeypatch):
        sub = _subscription(credit_card_id=42)
        monkeypatch.setattr(subscription_service.subscription_repository, "get_by_id", AsyncMock(return_value=sub))
        monkeypatch.setattr(subscription_service.subscription_repository, "save", AsyncMock())
        card_get = AsyncMock(return_value=None)
        monkeypatch.setattr(subscription_service.credit_card_repository, "get_by_id", card_get)
        session = AsyncMock()

        await subscription_service.update_subscription(session, 1, USER, amount=Decimal("20"))

        card_get.assert_not_called()


# --- Installment ---


class TestCreateInstallmentOwnership:
    @pytest.mark.asyncio
    async def test_foreign_card_raises_before_create(self, monkeypatch):
        monkeypatch.setattr(installment_service.credit_card_repository, "get_by_id", AsyncMock(return_value=None))
        create_mock = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "create", create_mock)
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await installment_service.create_installment(
                session,
                USER,
                name="TV",
                total_amount=Decimal("120"),
                installment_amount=Decimal("10"),
                currency="USD",
                installments_count=12,
                start_date=date(2026, 6, 5),
                payment_method="credit_card",
                credit_card_id=42,
            )

        create_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_owned_card_proceeds_to_create(self, monkeypatch):
        monkeypatch.setattr(installment_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        create_mock = AsyncMock(return_value=object())
        monkeypatch.setattr(installment_service.installment_repository, "create", create_mock)
        session = AsyncMock()

        await installment_service.create_installment(
            session,
            USER,
            name="TV",
            total_amount=Decimal("120"),
            installment_amount=Decimal("10"),
            currency="USD",
            installments_count=12,
            start_date=date(2026, 6, 5),
            payment_method="credit_card",
            credit_card_id=42,
        )

        create_mock.assert_awaited_once()


def _installment(*, credit_card_id: int | None) -> Installment:
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
        payment_method="credit_card" if credit_card_id is not None else None,
        credit_card_id=credit_card_id,
        is_active=True,
    )


class TestUpdateInstallmentOwnership:
    @pytest.mark.asyncio
    async def test_change_to_foreign_card_raises_before_save(self, monkeypatch):
        inst = _installment(credit_card_id=5)
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        save_mock = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "save", save_mock)
        monkeypatch.setattr(installment_service.credit_card_repository, "get_by_id", AsyncMock(return_value=None))
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await installment_service.update_installment(session, 1, USER, credit_card_id=99)

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_unchanged_card_skips_ownership_lookup(self, monkeypatch):
        inst = _installment(credit_card_id=42)
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        monkeypatch.setattr(installment_service.installment_repository, "save", AsyncMock())
        card_get = AsyncMock(return_value=None)
        monkeypatch.setattr(installment_service.credit_card_repository, "get_by_id", card_get)
        session = AsyncMock()

        await installment_service.update_installment(session, 1, USER, name="TV 2")

        card_get.assert_not_called()


# --- Payment obligation ---


class TestCreateObligationOwnership:
    @pytest.mark.asyncio
    async def test_foreign_card_raises_before_create(self, monkeypatch):
        monkeypatch.setattr(payment_obligation_service.credit_card_repository, "get_by_id", AsyncMock(return_value=None))
        create_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "create", create_mock)
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await payment_obligation_service.create_obligation(
                session,
                USER,
                name="ABL",
                amount=Decimal("10"),
                currency="USD",
                next_due_date=date(2026, 6, 5),
                payment_method="credit_card",
                credit_card_id=42,
            )

        create_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_owned_card_proceeds_to_create(self, monkeypatch):
        monkeypatch.setattr(payment_obligation_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        create_mock = AsyncMock(return_value=object())
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "create", create_mock)
        session = AsyncMock()

        await payment_obligation_service.create_obligation(
            session,
            USER,
            name="ABL",
            amount=Decimal("10"),
            currency="USD",
            next_due_date=date(2026, 6, 5),
            payment_method="credit_card",
            credit_card_id=42,
        )

        create_mock.assert_awaited_once()


def _obligation(*, credit_card_id: int | None) -> PaymentObligation:
    return PaymentObligation(
        id=1,
        user_id=1,
        name="ABL",
        amount=Decimal("10"),
        currency="USD",
        next_due_date=date(2026, 6, 5),
        anchor_day=5,
        recurrence="monthly",
        payment_method="credit_card" if credit_card_id is not None else None,
        credit_card_id=credit_card_id,
        is_active=True,
    )


class TestUpdateObligationOwnership:
    @pytest.mark.asyncio
    async def test_change_to_foreign_card_raises_before_save(self, monkeypatch):
        ob = _obligation(credit_card_id=5)
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "get_by_id", AsyncMock(return_value=ob))
        save_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", save_mock)
        monkeypatch.setattr(payment_obligation_service.credit_card_repository, "get_by_id", AsyncMock(return_value=None))
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await payment_obligation_service.update_obligation(session, 1, USER, credit_card_id=99)

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_unchanged_card_skips_ownership_lookup(self, monkeypatch):
        ob = _obligation(credit_card_id=42)
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "get_by_id", AsyncMock(return_value=ob))
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        card_get = AsyncMock(return_value=None)
        monkeypatch.setattr(payment_obligation_service.credit_card_repository, "get_by_id", card_get)
        session = AsyncMock()

        await payment_obligation_service.update_obligation(session, 1, USER, name="ABL 2")

        card_get.assert_not_called()
