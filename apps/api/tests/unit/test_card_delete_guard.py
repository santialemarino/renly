from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import HasLinkedExpensesError
from app.models.user import User
from app.services import credit_card_service

# The card-delete guard (P06) rejects deletion with a 409 naming every entity kind that still
# references the card — expenses AND the three plan types. The message degrades to the exact
# legacy expenses-only text so the pre-existing behaviour is preserved. Persistence is mocked.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _patch_counts(monkeypatch, *, expenses=0, shared_expenses=0, subscriptions=0, installments=0, obligations=0):
    monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=object()))
    monkeypatch.setattr(credit_card_service.expense_repository, "count_by_credit_card", AsyncMock(return_value=expenses))
    monkeypatch.setattr(credit_card_service.shared_expense_repository, "count_by_credit_card", AsyncMock(return_value=shared_expenses))
    monkeypatch.setattr(credit_card_service.subscription_repository, "count_by_credit_card", AsyncMock(return_value=subscriptions))
    monkeypatch.setattr(credit_card_service.installment_repository, "count_by_credit_card", AsyncMock(return_value=installments))
    monkeypatch.setattr(credit_card_service.payment_obligation_repository, "count_by_credit_card", AsyncMock(return_value=obligations))


class TestCardBalancesIncludeAGroupsCharges:
    # A shared expense charged to this card raises the same liability a private one does: the whole
    # amount hit the card, whoever ends up owing whom for it. Without this the card would understate
    # what is owed to the issuer by exactly the group's charges — and the statement balance, which
    # reads its own queries, would then disagree with the card page.
    @pytest.mark.asyncio
    async def test_a_groups_charge_is_added_into_the_same_bucket(self, monkeypatch):
        monkeypatch.setattr(
            credit_card_service.expense_repository,
            "sum_by_credit_card_ids_grouped",
            AsyncMock(return_value={1: {"ARS": Decimal("1000")}}),
        )
        monkeypatch.setattr(
            credit_card_service.shared_expense_repository,
            "sum_by_credit_card_ids_grouped",
            AsyncMock(return_value={1: {"ARS": Decimal("400"), "USD": Decimal("60")}}),
        )
        monkeypatch.setattr(credit_card_service.card_settlement_repository, "sum_by_card_ids_grouped", AsyncMock(return_value={}))

        balances = await credit_card_service.get_card_balances(AsyncMock(), [1], {1: "ARS"}, USER.id)

        by_currency = {bucket.currency: bucket.balance for bucket in balances[1]}
        # 1000 private + 400 shared in the card's own bucket, and a second bucket the group opened.
        assert by_currency == {"ARS": Decimal("1400"), "USD": Decimal("60")}

    @pytest.mark.asyncio
    async def test_a_card_with_only_group_charges_still_has_a_balance(self, monkeypatch):
        # The additional-cardholder case: every charge on this card is the group's.
        monkeypatch.setattr(credit_card_service.expense_repository, "sum_by_credit_card_ids_grouped", AsyncMock(return_value={}))
        monkeypatch.setattr(
            credit_card_service.shared_expense_repository,
            "sum_by_credit_card_ids_grouped",
            AsyncMock(return_value={1: {"ARS": Decimal("750")}}),
        )
        monkeypatch.setattr(credit_card_service.card_settlement_repository, "sum_by_card_ids_grouped", AsyncMock(return_value={}))

        balances = await credit_card_service.get_card_balances(AsyncMock(), [1], {1: "ARS"}, USER.id)

        assert [(b.currency, b.balance) for b in balances[1]] == [("ARS", Decimal("750"))]


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
    async def test_a_group_expense_on_the_card_also_blocks_deletion(self, monkeypatch):
        # A shared expense charged to this card raises the same liability a private one does, so it
        # holds the card open the same way. Named apart from "expenses" because the fix is different:
        # the user has to go to the group, not to their own list.
        _patch_counts(monkeypatch, shared_expenses=1)
        monkeypatch.setattr(credit_card_service.credit_card_repository, "delete", AsyncMock())

        with pytest.raises(HasLinkedExpensesError) as exc:
            await credit_card_service.delete_card(AsyncMock(), 1, USER)

        assert "shared expenses" in exc.value.message

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
