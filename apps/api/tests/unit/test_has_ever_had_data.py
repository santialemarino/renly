from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.investment import InvestmentCategory
from app.models.user import User
from app.services import income_service, investment_service, settings_service

# Coverage for the first-run sample-data marker: the atomic helper's contract (one upsert, no
# commit) and the on-create latch in the primary create paths. Expense shares the identical pattern
# and is exercised by the existing create_expense tests (which still pass with the latch in place).

USER = User(id=7, email="u@test", password_hash="x", session_epoch=0)


class TestMarkHelper:
    @pytest.mark.asyncio
    async def test_issues_one_statement_and_does_not_commit(self):
        session = AsyncMock()

        await settings_service.mark_has_ever_had_data(session, USER.id)

        session.execute.assert_awaited_once()  # a single atomic upsert
        session.commit.assert_not_called()  # the caller's transaction persists it


class TestCreateLatchesMarker:
    @pytest.mark.asyncio
    async def test_create_investment_latches_marker(self, monkeypatch):
        monkeypatch.setattr(investment_service.investment_repository, "create", AsyncMock(side_effect=lambda _s, inv: inv))
        mark = AsyncMock()
        monkeypatch.setattr(investment_service.settings_service, "mark_has_ever_had_data", mark)
        session = AsyncMock()

        await investment_service.create_investment(session, USER, name="Test", category=InvestmentCategory("stocks"), base_currency="USD")

        mark.assert_awaited_once()
        assert mark.await_args.args[1] == USER.id

    @pytest.mark.asyncio
    async def test_create_income_latches_marker(self, monkeypatch):
        monkeypatch.setattr(income_service.income_repository, "create", AsyncMock(side_effect=lambda _s, entry: entry))
        mark = AsyncMock()
        monkeypatch.setattr(income_service.settings_service, "mark_has_ever_had_data", mark)
        session = AsyncMock()

        await income_service.create_income(session, USER, date=date(2026, 1, 1), amount=Decimal("1"), currency="USD")

        mark.assert_awaited_once()
        assert mark.await_args.args[1] == USER.id
