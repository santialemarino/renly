from unittest.mock import AsyncMock

import pytest

from app.domain import HasLinkedExpensesError
from app.models.user import User
from app.services import credit_card_service

# The card-delete guard (P06) rejects deletion with a 409 naming every entity kind that still
# references the card — expenses AND the three plan types. The message degrades to the exact
# legacy expenses-only text so the pre-existing behaviour is preserved. Persistence is mocked.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _patch_counts(monkeypatch, *, expenses=0, subscriptions=0, installments=0, obligations=0):
    monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=object()))
    monkeypatch.setattr(credit_card_service.expense_repository, "count_by_credit_card", AsyncMock(return_value=expenses))
    monkeypatch.setattr(credit_card_service.subscription_repository, "count_by_credit_card", AsyncMock(return_value=subscriptions))
    monkeypatch.setattr(credit_card_service.installment_repository, "count_by_credit_card", AsyncMock(return_value=installments))
    monkeypatch.setattr(credit_card_service.payment_obligation_repository, "count_by_credit_card", AsyncMock(return_value=obligations))


class TestCardDeleteGuard:
    @pytest.mark.asyncio
    async def test_only_expenses_uses_legacy_message(self, monkeypatch):
        _patch_counts(monkeypatch, expenses=3)
        delete_mock = AsyncMock()
        monkeypatch.setattr(credit_card_service.credit_card_repository, "delete", delete_mock)
        session = AsyncMock()

        with pytest.raises(HasLinkedExpensesError) as exc:
            await credit_card_service.delete_card(session, 1, USER)

        assert exc.value.message == "Cannot delete a credit card that has linked expenses. Archive it instead."
        delete_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_only_subscriptions_names_subscriptions(self, monkeypatch):
        _patch_counts(monkeypatch, subscriptions=2)
        monkeypatch.setattr(credit_card_service.credit_card_repository, "delete", AsyncMock())
        session = AsyncMock()

        with pytest.raises(HasLinkedExpensesError) as exc:
            await credit_card_service.delete_card(session, 1, USER)

        assert "subscriptions" in exc.value.message

    @pytest.mark.asyncio
    async def test_expenses_and_installments_named_in_order(self, monkeypatch):
        _patch_counts(monkeypatch, expenses=1, installments=1)
        monkeypatch.setattr(credit_card_service.credit_card_repository, "delete", AsyncMock())
        session = AsyncMock()

        with pytest.raises(HasLinkedExpensesError) as exc:
            await credit_card_service.delete_card(session, 1, USER)

        assert "expenses, installment plans" in exc.value.message

    @pytest.mark.asyncio
    async def test_no_references_deletes_and_commits(self, monkeypatch):
        _patch_counts(monkeypatch)
        delete_mock = AsyncMock()
        monkeypatch.setattr(credit_card_service.credit_card_repository, "delete", delete_mock)
        session = AsyncMock()

        await credit_card_service.delete_card(session, 1, USER)

        delete_mock.assert_awaited_once()
        session.commit.assert_awaited_once()
