from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import AdvanceResult
from app.models.expense_entry import ExpenseEntry
from app.models.payment_obligation import PaymentObligation
from app.models.user import User
from app.services import card_reconciliation_service, expense_service, payment_obligation_service

# Tests for the multi-cycle Mark Paid path (Phase 3, follow-up Item 2). The service
# function inserts N rows + walks the obligation cursor N steps before a single commit.
# We mock the row insert + cursor advance + reconciliation-stale + session.commit so the
# tests pin the orchestration: ordering, atomicity, cursor coalesce, and the recurring
# guard.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _obligation(*, recurrence: str | None = "monthly") -> PaymentObligation:
    return PaymentObligation(
        id=7,
        user_id=1,
        name="ABL",
        amount=Decimal("12500"),
        currency="ARS",
        next_due_date=date(2026, 5, 15),
        anchor_day=15,
        recurrence=recurrence,
        is_active=True,
    )


def _entry() -> ExpenseEntry:
    return ExpenseEntry(
        id=99,
        user_id=1,
        date=date(2026, 5, 28),
        amount=Decimal("12500"),
        currency="ARS",
        notes=None,
        payment_method=None,
        credit_card_id=None,
        source="manual",
        payment_obligation_id=7,
    )


@pytest.fixture(autouse=True)
def _silence_stale(monkeypatch):
    monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", AsyncMock())


def _mock_insert(monkeypatch, entry: ExpenseEntry):
    monkeypatch.setattr(expense_service.expense_repository, "create", AsyncMock(return_value=entry))


def _mock_get_obligation(monkeypatch, obligation: PaymentObligation):
    monkeypatch.setattr(
        payment_obligation_service,
        "get_obligation",
        AsyncMock(return_value=obligation),
    )


class TestCreateExpensesForObligationCycles:
    @pytest.mark.asyncio
    async def test_inserts_n_rows_and_walks_cursor_n_steps(self, monkeypatch):
        # cycles=3 monthly: 3 inserts + 3 advances + 1 commit. Returned advance spans
        # the entire walk (first iter's previous_cursor -> last iter's new_cursor).
        entry = _entry()
        _mock_insert(monkeypatch, entry)
        _mock_get_obligation(monkeypatch, _obligation())
        advances = [
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-05-15", new_cursor="2026-06-15"),
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-06-15", new_cursor="2026-07-15"),
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-07-15", new_cursor="2026-08-15"),
        ]
        advance_mock = AsyncMock(side_effect=advances)
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        session = AsyncMock()

        last_entry, advance = await expense_service.create_expenses_for_obligation_cycles(
            session,
            USER,
            cycles=3,
            date=date(2026, 5, 28),
            amount=Decimal("12500"),
            currency="ARS",
            payment_obligation_id=7,
        )

        assert expense_service.expense_repository.create.await_count == 3
        assert advance_mock.await_count == 3
        assert session.commit.await_count == 1
        assert last_entry is entry
        assert advance is not None
        assert advance.previous_cursor == "2026-05-15"
        assert advance.new_cursor == "2026-08-15"

    @pytest.mark.asyncio
    async def test_single_cycle_still_commits_once(self, monkeypatch):
        # cycles=1 is a degenerate but supported path (router only calls this function
        # when cycles > 1, but the contract must handle cycles=1 cleanly).
        entry = _entry()
        _mock_insert(monkeypatch, entry)
        _mock_get_obligation(monkeypatch, _obligation())
        advance = AdvanceResult(
            plan_type="obligation",
            plan_id=7,
            plan_name="ABL",
            previous_cursor="2026-05-15",
            new_cursor="2026-06-15",
        )
        advance_mock = AsyncMock(return_value=advance)
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        session = AsyncMock()

        _, result = await expense_service.create_expenses_for_obligation_cycles(
            session,
            USER,
            cycles=1,
            date=date(2026, 5, 28),
            amount=Decimal("12500"),
            currency="ARS",
            payment_obligation_id=7,
        )

        assert expense_service.expense_repository.create.await_count == 1
        assert advance_mock.await_count == 1
        assert session.commit.await_count == 1
        assert result == advance

    @pytest.mark.asyncio
    async def test_one_off_obligation_raises_before_any_insert(self, monkeypatch):
        # Recurrence is None: the function must refuse before inserting any row and
        # before calling advance_or_archive. The schema validator catches this for the
        # HTTP path, but the service is the load-bearing guard for non-HTTP callers.
        _mock_insert(monkeypatch, _entry())
        _mock_get_obligation(monkeypatch, _obligation(recurrence=None))
        advance_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        session = AsyncMock()

        with pytest.raises(ValueError, match="recurring"):
            await expense_service.create_expenses_for_obligation_cycles(
                session,
                USER,
                cycles=3,
                date=date(2026, 5, 28),
                amount=Decimal("12500"),
                currency="ARS",
                payment_obligation_id=7,
            )

        expense_service.expense_repository.create.assert_not_called()
        advance_mock.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_mid_loop_exception_skips_commit(self, monkeypatch):
        # Atomicity guarantee: if advance_or_archive blows up mid-loop (e.g. obligation
        # deleted by a concurrent transaction), the service must not commit. The session
        # rolls back on exit via the framework's session lifecycle.
        entry = _entry()
        _mock_insert(monkeypatch, entry)
        _mock_get_obligation(monkeypatch, _obligation())
        advances: list[AdvanceResult | RuntimeError] = [
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-05-15", new_cursor="2026-06-15"),
            RuntimeError("simulated mid-loop failure"),
        ]
        advance_mock = AsyncMock(side_effect=advances)
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        session = AsyncMock()

        with pytest.raises(RuntimeError, match="simulated"):
            await expense_service.create_expenses_for_obligation_cycles(
                session,
                USER,
                cycles=3,
                date=date(2026, 5, 28),
                amount=Decimal("12500"),
                currency="ARS",
                payment_obligation_id=7,
            )

        assert expense_service.expense_repository.create.await_count == 2
        assert advance_mock.await_count == 2
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cursor_coalesce_uses_first_previous_and_last_new(self, monkeypatch):
        # Regression pin: an earlier draft returned the last iteration's AdvanceResult as-is,
        # which made the toast read "Jul 15 -> Aug 15" instead of "May 15 -> Aug 15" for a
        # 3-cycle pre-pay. The coalesce step replaces previous_cursor with the first iter's
        # value via dataclasses.replace.
        entry = _entry()
        _mock_insert(monkeypatch, entry)
        _mock_get_obligation(monkeypatch, _obligation())
        advances = [
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-05-15", new_cursor="2026-06-15"),
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-06-15", new_cursor="2026-07-15"),
        ]
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", AsyncMock(side_effect=advances))
        session = AsyncMock()

        _, advance = await expense_service.create_expenses_for_obligation_cycles(
            session,
            USER,
            cycles=2,
            date=date(2026, 5, 28),
            amount=Decimal("12500"),
            currency="ARS",
            payment_obligation_id=7,
        )

        assert advance is not None
        assert advance.previous_cursor == "2026-05-15"
        assert advance.new_cursor == "2026-07-15"
        # The other fields are unchanged from the underlying AdvanceResult.
        assert advance.plan_type == "obligation"
        assert advance.plan_id == 7
        assert advance.plan_name == "ABL"
