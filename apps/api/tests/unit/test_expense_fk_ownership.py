from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import NotFoundError
from app.models.expense_entry import ExpenseEntry
from app.models.user import User
from app.services import (
    card_reconciliation_service,
    expense_service,
    payment_obligation_service,
)

# Tests for the cross-tenant FK ownership guard in expense_service (SEC-4). An expense must not
# reference another user's credit_card_id / payment_obligation_id / subscription_id /
# installment_id — doing so would attach the row (and, for cards, stale-mark a foreign
# reconciliation) across tenants. _validate_owned_fks raises NotFoundError before any write.
# Everything below the service is mocked so the tests pin the guard, not the persistence.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _entry(*, credit_card_id: int | None = None) -> ExpenseEntry:
    return ExpenseEntry(
        id=1,
        user_id=1,
        date=date(2026, 6, 5),
        amount=Decimal("100"),
        currency="USD",
        notes=None,
        payment_method=None,
        credit_card_id=credit_card_id,
        source="manual",
    )


@pytest.fixture(autouse=True)
def _silence_stale(monkeypatch):
    monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", AsyncMock())


# Patch a repository's get_by_id to model ownership: None = not owned (foreign / missing),
# an object = owned.
def _owns(monkeypatch, repo_name: str, owned: bool):
    repo = getattr(expense_service, repo_name)
    monkeypatch.setattr(repo, "get_by_id", AsyncMock(return_value=object() if owned else None))


class TestCreateExpenseOwnership:
    @pytest.mark.asyncio
    async def test_foreign_credit_card_raises_before_insert(self, monkeypatch):
        _owns(monkeypatch, "credit_card_repository", owned=False)
        create_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "create", create_mock)
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await expense_service.create_expense(session, USER, date=date(2026, 6, 5), amount=Decimal("100"), currency="USD", credit_card_id=42)

        create_mock.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_foreign_payment_obligation_raises(self, monkeypatch):
        _owns(monkeypatch, "payment_obligation_repository", owned=False)
        monkeypatch.setattr(expense_service.expense_repository, "create", AsyncMock())
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Payment obligation not found"):
            await expense_service.create_expense(session, USER, date=date(2026, 6, 5), amount=Decimal("100"), currency="USD", payment_obligation_id=7)

    @pytest.mark.asyncio
    async def test_foreign_subscription_raises(self, monkeypatch):
        _owns(monkeypatch, "subscription_repository", owned=False)
        monkeypatch.setattr(expense_service.expense_repository, "create", AsyncMock())
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Subscription not found"):
            await expense_service.create_expense(session, USER, date=date(2026, 6, 5), amount=Decimal("100"), currency="USD", subscription_id=9)

    @pytest.mark.asyncio
    async def test_foreign_installment_raises(self, monkeypatch):
        _owns(monkeypatch, "installment_repository", owned=False)
        monkeypatch.setattr(expense_service.expense_repository, "create", AsyncMock())
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Installment not found"):
            await expense_service.create_expense(session, USER, date=date(2026, 6, 5), amount=Decimal("100"), currency="USD", installment_id=3)

    @pytest.mark.asyncio
    async def test_owned_credit_card_proceeds_to_insert(self, monkeypatch):
        _owns(monkeypatch, "credit_card_repository", owned=True)
        entry = _entry(credit_card_id=42)
        create_mock = AsyncMock(return_value=entry)
        monkeypatch.setattr(expense_service.expense_repository, "create", create_mock)
        session = AsyncMock()

        out, advance = await expense_service.create_expense(
            session, USER, date=date(2026, 6, 5), amount=Decimal("100"), currency="USD", credit_card_id=42
        )

        assert out is entry
        assert advance is None
        create_mock.assert_awaited_once()
        session.commit.assert_awaited_once()


class TestCreateCyclesOwnership:
    @pytest.mark.asyncio
    async def test_foreign_credit_card_raises_before_obligation_lookup(self, monkeypatch):
        _owns(monkeypatch, "credit_card_repository", owned=False)
        get_obligation_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "get_obligation", get_obligation_mock)
        create_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "create", create_mock)
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await expense_service.create_expenses_for_obligation_cycles(
                session,
                USER,
                cycles=2,
                date=date(2026, 6, 5),
                amount=Decimal("100"),
                currency="USD",
                payment_obligation_id=7,
                credit_card_id=42,
            )

        get_obligation_mock.assert_not_called()
        create_mock.assert_not_called()


class TestUpdateExpenseOwnership:
    @pytest.mark.asyncio
    async def test_change_to_foreign_card_raises_before_save(self, monkeypatch):
        entry = _entry(credit_card_id=None)
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        save_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "save", save_mock)
        _owns(monkeypatch, "credit_card_repository", owned=False)
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Credit card not found"):
            await expense_service.update_expense(session, 1, USER, credit_card_id=99)

        save_mock.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_change_to_foreign_subscription_raises(self, monkeypatch):
        entry = _entry()
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        monkeypatch.setattr(expense_service.expense_repository, "save", AsyncMock())
        _owns(monkeypatch, "subscription_repository", owned=False)
        session = AsyncMock()

        with pytest.raises(NotFoundError, match="Subscription not found"):
            await expense_service.update_expense(session, 1, USER, subscription_id=7)

    @pytest.mark.asyncio
    async def test_unchanged_fks_skip_ownership_check(self, monkeypatch):
        # Editing only the amount on a card-linked expense must not re-validate the unchanged
        # card FK (the guard runs only for newly-set / changed FKs).
        entry = _entry(credit_card_id=42)
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        monkeypatch.setattr(expense_service.expense_repository, "save", AsyncMock())
        card_get = AsyncMock(return_value=None)
        monkeypatch.setattr(expense_service.credit_card_repository, "get_by_id", card_get)
        session = AsyncMock()

        out, _advance, _reverse = await expense_service.update_expense(session, 1, USER, amount=Decimal("200"))

        card_get.assert_not_called()
        assert out is entry
        session.commit.assert_awaited_once()
