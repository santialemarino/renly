from unittest.mock import AsyncMock

import pytest

from app.models.user import User
from app.services import onboarding_service

# Unit coverage for onboarding_service.get_status: each checklist step is derived from real data
# (an existence probe per entity + the stored primary-currency preference), OR-ing income/expense
# into a single "finances" step.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _patch(monkeypatch, *, investments: bool, expenses: bool, income: bool, primary: str | None):
    monkeypatch.setattr(onboarding_service.investment_repository, "exists_by_user", AsyncMock(return_value=investments))
    monkeypatch.setattr(onboarding_service.expense_repository, "exists_by_user", AsyncMock(return_value=expenses))
    monkeypatch.setattr(onboarding_service.income_repository, "exists_by_user", AsyncMock(return_value=income))
    monkeypatch.setattr(onboarding_service.settings_service, "get_settings", AsyncMock(return_value={"primary_currency": primary}))


class TestOnboardingStatus:
    @pytest.mark.asyncio
    async def test_fresh_user_has_nothing_done(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result == {
            "has_investments": False,
            "has_finances": False,
            "primary_currency_set": False,
        }

    @pytest.mark.asyncio
    async def test_investment_step_reflects_existence(self, monkeypatch):
        _patch(monkeypatch, investments=True, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_investments"] is True

    @pytest.mark.asyncio
    async def test_finances_step_done_with_only_an_expense(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=True, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_finances"] is True

    @pytest.mark.asyncio
    async def test_finances_step_done_with_only_income(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=True, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_finances"] is True

    @pytest.mark.asyncio
    async def test_finances_step_not_done_without_income_or_expense(self, monkeypatch):
        _patch(monkeypatch, investments=True, expenses=False, income=False, primary="USD")

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["has_finances"] is False

    @pytest.mark.asyncio
    async def test_currency_step_reflects_stored_primary(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary="USD")

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["primary_currency_set"] is True

    @pytest.mark.asyncio
    async def test_currency_step_not_done_when_primary_unset(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["primary_currency_set"] is False
