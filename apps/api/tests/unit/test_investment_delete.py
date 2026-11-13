from unittest.mock import AsyncMock

import pytest

from app.domain import InvestmentHasHistoryError
from app.models.investment import Currency, Investment, InvestmentCategory
from app.models.user import User
from app.services import investment_service

# An investment can be deleted only while it has no history. A snapshot or a transaction feeds the
# returns, the net-worth series and the dashboards, so either one leaves archiving as the only way out.
# Persistence is mocked; what is asserted is which path the service takes and that it commits once.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _patch(monkeypatch, *, snapshots: bool, transactions: bool) -> tuple[AsyncMock, AsyncMock]:
    investment = Investment(id=7, user_id=1, name="Google", category=InvestmentCategory.stocks, base_currency=Currency.USD)
    monkeypatch.setattr(investment_service, "get_investment", AsyncMock(return_value=investment))
    monkeypatch.setattr(investment_service.snapshot_repository, "has_snapshots", AsyncMock(return_value=snapshots))
    monkeypatch.setattr(
        investment_service.transaction_repository,
        "get_ids_with_transactions",
        AsyncMock(return_value={7} if transactions else set()),
    )
    delete = AsyncMock()
    monkeypatch.setattr(investment_service.investment_repository, "delete", delete)
    session = AsyncMock()
    return delete, session


class TestDeleteInvestment:
    @pytest.mark.asyncio
    async def test_an_investment_with_no_history_is_deleted(self, monkeypatch):
        delete, session = _patch(monkeypatch, snapshots=False, transactions=False)
        await investment_service.delete_investment(session, 7, USER)
        delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("snapshots", "transactions"), [(True, False), (False, True), (True, True)])
    async def test_an_investment_with_history_is_refused(self, monkeypatch, snapshots, transactions):
        delete, session = _patch(monkeypatch, snapshots=snapshots, transactions=transactions)
        with pytest.raises(InvestmentHasHistoryError) as raised:
            await investment_service.delete_investment(session, 7, USER)
        assert raised.value.status_code == 409
        assert raised.value.code == "investment_has_history"
        delete.assert_not_awaited()
        session.commit.assert_not_awaited()


class TestTheResponseSaysWhetherThereIsHistory:
    @pytest.mark.asyncio
    async def test_has_transactions_reflects_the_transaction_lookup(self, monkeypatch):
        monkeypatch.setattr(investment_service.investment_repository, "get_collections_by_investment_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value=set()))
        monkeypatch.setattr(investment_service.transaction_repository, "get_ids_with_transactions", AsyncMock(return_value={7}))
        from datetime import datetime

        now = datetime(2026, 11, 12)
        investment = Investment(
            id=7, user_id=1, name="Google", category=InvestmentCategory.stocks, base_currency=Currency.USD, created_at=now, updated_at=now
        )
        response = await investment_service.build_response(AsyncMock(), investment)
        assert response.has_transactions is True
        assert response.has_snapshots is False
