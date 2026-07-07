from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.investment import InvestmentCategory
from app.models.user import User
from app.services import income_service, investment_service, settings_service

# Coverage for the per-section first-run sample retire: the atomic helper's contract (one upsert, no
# commit) and the on-create latch that retires the matching section when the user first creates that
# entity. Expense shares the identical pattern and is exercised by the existing create_expense tests.

USER = User(id=7, email="u@test", password_hash="x", session_epoch=0)


class TestRetireHelper:
    @pytest.mark.asyncio
    async def test_issues_one_statement_and_does_not_commit(self):
        session = AsyncMock()

        await settings_service.retire_sample(session, USER.id, "expenses")

        session.execute.assert_awaited_once()  # a single atomic upsert
        session.commit.assert_not_called()  # the caller's transaction persists it


class TestCreateRetiresSample:
    @pytest.mark.asyncio
    async def test_create_investment_retires_investments_sample(self, monkeypatch):
        monkeypatch.setattr(investment_service.investment_repository, "create", AsyncMock(side_effect=lambda _s, inv: inv))
        retire = AsyncMock()
        monkeypatch.setattr(investment_service.settings_service, "retire_sample", retire)
        session = AsyncMock()

        await investment_service.create_investment(session, USER, name="Test", category=InvestmentCategory("stocks"), base_currency="USD")

        retire.assert_awaited_once()
        assert retire.await_args.args[1:] == (USER.id, "investments")

    @pytest.mark.asyncio
    async def test_create_income_retires_income_sample(self, monkeypatch):
        monkeypatch.setattr(income_service.income_repository, "create", AsyncMock(side_effect=lambda _s, entry: entry))
        retire = AsyncMock()
        monkeypatch.setattr(income_service.settings_service, "retire_sample", retire)
        session = AsyncMock()

        await income_service.create_income(session, USER, date=date(2026, 1, 1), amount=Decimal("1"), currency="USD")

        retire.assert_awaited_once()
        assert retire.await_args.args[1:] == (USER.id, "income")
