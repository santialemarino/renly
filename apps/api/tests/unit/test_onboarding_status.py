from unittest.mock import AsyncMock

import pytest

from app.models.user import User
from app.services import onboarding_service

# Unit coverage for onboarding_service: the checklist derived from real data (an existence probe per
# entity + the stored primary-currency preference, OR-ing income/expense into one "finances" step),
# the PER-SECTION first-run sample flags (a section samples only until the user creates that entity
# or clears it), the backstop that retires samples for data created outside the create paths, and
# the explicit dismiss.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)

_NONE_RETIRED = {"investments": False, "expenses": False, "income": False}


def _patch(monkeypatch, *, investments, expenses, income, primary, retired=None):
    monkeypatch.setattr(onboarding_service.investment_repository, "exists_by_user", AsyncMock(return_value=investments))
    monkeypatch.setattr(onboarding_service.expense_repository, "exists_by_user", AsyncMock(return_value=expenses))
    monkeypatch.setattr(onboarding_service.income_repository, "exists_by_user", AsyncMock(return_value=income))
    settings = {"primary_currency": primary, "samples_retired": retired or dict(_NONE_RETIRED)}
    monkeypatch.setattr(onboarding_service.settings_service, "get_settings", AsyncMock(return_value=settings))
    retire_mock = AsyncMock()
    monkeypatch.setattr(onboarding_service.settings_service, "retire_sample", retire_mock)
    return retire_mock


class TestChecklist:
    @pytest.mark.asyncio
    async def test_fresh_user(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result == {
            "has_investments": False,
            "has_finances": False,
            "primary_currency_set": False,
            "sample_investments": True,
            "sample_expenses": True,
            "sample_income": True,
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


class TestPerSectionSamples:
    @pytest.mark.asyncio
    async def test_pristine_account_samples_every_section(self, monkeypatch):
        _patch(monkeypatch, investments=False, expenses=False, income=False, primary=None)

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["sample_investments"] is True
        assert result["sample_expenses"] is True
        assert result["sample_income"] is True

    @pytest.mark.asyncio
    async def test_creating_one_entity_retires_only_that_section(self, monkeypatch):
        # An investment (only) retires the investments sample — but income & expenses still sample.
        # That independence is the whole point of per-section.
        retire_mock = _patch(monkeypatch, investments=True, expenses=False, income=False, primary=None)
        session = AsyncMock()

        result = await onboarding_service.get_status(session, USER)

        assert result["sample_investments"] is False
        assert result["sample_expenses"] is True
        assert result["sample_income"] is True
        retire_mock.assert_awaited_once()
        assert retire_mock.await_args.args[1:] == (USER.id, "investments")
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retired_section_does_not_resample_after_delete(self, monkeypatch):
        # No investments now, but that section was retired (created once, then emptied) → no sample;
        # expenses were never touched → still samples.
        _patch(
            monkeypatch,
            investments=False,
            expenses=False,
            income=False,
            primary=None,
            retired={"investments": True, "expenses": False, "income": False},
        )

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["sample_investments"] is False
        assert result["sample_expenses"] is True

    @pytest.mark.asyncio
    async def test_dismissed_section_has_no_sample(self, monkeypatch):
        _patch(
            monkeypatch,
            investments=False,
            expenses=False,
            income=False,
            primary=None,
            retired={"investments": False, "expenses": True, "income": False},
        )

        result = await onboarding_service.get_status(AsyncMock(), USER)

        assert result["sample_expenses"] is False
        assert result["sample_investments"] is True


class TestBackstop:
    @pytest.mark.asyncio
    async def test_retires_each_entity_that_has_data(self, monkeypatch):
        retire_mock = _patch(monkeypatch, investments=True, expenses=True, income=False, primary=None)
        session = AsyncMock()

        await onboarding_service.get_status(session, USER)

        retired_entities = {call.args[2] for call in retire_mock.await_args_list}
        assert retired_entities == {"investments", "expenses"}
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_entities_already_retired(self, monkeypatch):
        retire_mock = _patch(
            monkeypatch,
            investments=True,
            expenses=False,
            income=False,
            primary=None,
            retired={"investments": True, "expenses": False, "income": False},
        )
        session = AsyncMock()

        await onboarding_service.get_status(session, USER)

        retire_mock.assert_not_awaited()
        session.commit.assert_not_awaited()  # nothing to retire → no write, no commit

    @pytest.mark.asyncio
    async def test_backstop_write_failure_degrades_to_a_correct_read(self, monkeypatch):
        # A backstop write hiccup must never fail the read: the section is still correctly hidden (it
        # has data), the transaction is rolled back, and the retire re-attempts on the next request.
        retire_mock = _patch(monkeypatch, investments=True, expenses=False, income=False, primary=None)
        retire_mock.side_effect = RuntimeError("db unavailable")
        session = AsyncMock()

        result = await onboarding_service.get_status(session, USER)

        assert result["sample_investments"] is False  # has data → hidden regardless of the write
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()


class TestDismiss:
    @pytest.mark.asyncio
    async def test_dismiss_retires_the_section_and_commits(self, monkeypatch):
        retire_mock = AsyncMock()
        monkeypatch.setattr(onboarding_service.settings_service, "retire_sample", retire_mock)
        session = AsyncMock()

        await onboarding_service.dismiss_sample(session, USER, "expenses")

        retire_mock.assert_awaited_once()
        assert retire_mock.await_args.args[1:] == (USER.id, "expenses")
        session.commit.assert_awaited_once()
