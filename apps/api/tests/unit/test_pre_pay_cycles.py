from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_admin_session, get_auth_session, get_session
from app.deps.api_key_auth import get_jwt_or_api_key_user
from app.domain import (
    AdvanceResult,
    ExpenseCycleObligationGoneError,
    ExpenseCycleObligationNotRecurringError,
    ExpenseCyclesOutOfRangeError,
)
from app.main import create_app
from app.models.expense_entry import ExpenseEntry
from app.models.payment_obligation import PaymentObligation
from app.models.user import User
from app.rate_limit import limiter
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
    # The SEC-4 ownership guard validates the card FK before the obligation lookup; the
    # obligation itself is validated by the mocked get_obligation. Stub the card lookup owned.
    monkeypatch.setattr(expense_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))


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

        with pytest.raises(ExpenseCycleObligationNotRecurringError) as raised:
            await expense_service.create_expenses_for_obligation_cycles(
                session,
                USER,
                cycles=3,
                date=date(2026, 5, 28),
                amount=Decimal("12500"),
                currency="ARS",
                payment_obligation_id=7,
            )

        assert raised.value.code == "expense_cycle_obligation_not_recurring"
        expense_service.expense_repository.create.assert_not_called()
        advance_mock.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_recurrence_raises_before_any_insert(self, monkeypatch):
        # Recurrence is a string value not in OBLIGATION_MONTH_STEP (e.g. legacy 'fortnightly',
        # DB drift, or a future migration that adds a recurrence before the dict is updated).
        # The schema (PaymentObligation.recurrence is free-form str | None) doesn't enforce the
        # enum, so the service must catch it — otherwise the loop would silently emit N rows
        # while compute_obligation_advance's defensive no-op left the cursor frozen.
        _mock_insert(monkeypatch, _entry())
        _mock_get_obligation(monkeypatch, _obligation(recurrence="fortnightly"))
        advance_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        session = AsyncMock()

        with pytest.raises(ExpenseCycleObligationNotRecurringError) as raised:
            await expense_service.create_expenses_for_obligation_cycles(
                session,
                USER,
                cycles=3,
                date=date(2026, 5, 28),
                amount=Decimal("12500"),
                currency="ARS",
                payment_obligation_id=7,
            )

        assert raised.value.code == "expense_cycle_obligation_not_recurring"
        expense_service.expense_repository.create.assert_not_called()
        advance_mock.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_cycles", [0, -1, 13, 100])
    async def test_cycles_out_of_range_raises_before_any_lookup(self, monkeypatch, bad_cycles):
        # Defensive cycles bound. Schema enforces 1..MAX_CYCLES_PER_MARK_PAID on the HTTP
        # path; this guard catches internal callers and survives `python -O` (assert would
        # not). The check runs BEFORE the obligation lookup, so a bad cycles value never
        # touches the DB.
        _mock_insert(monkeypatch, _entry())
        get_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "get_obligation", get_mock)
        advance_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        session = AsyncMock()

        with pytest.raises(ExpenseCyclesOutOfRangeError) as raised:
            await expense_service.create_expenses_for_obligation_cycles(
                session,
                USER,
                cycles=bad_cycles,
                date=date(2026, 5, 28),
                amount=Decimal("12500"),
                currency="ARS",
                payment_obligation_id=7,
            )

        assert (raised.value.code, raised.value.extra) == ("expense_cycles_out_of_range", {"max_cycles": 12})
        get_mock.assert_not_called()
        expense_service.expense_repository.create.assert_not_called()
        advance_mock.assert_not_called()
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_delete_mid_loop_raises_and_skips_commit(self, monkeypatch):
        # If a concurrent transaction deletes the obligation between iterations, the next
        # advance_or_archive call returns None (obligation not found). Pre-fix the loop
        # silently overwrote last_advance to None and committed N dangling FK rows with no
        # toast; now the loop raises ExpenseCycleObligationGoneError and the framework rolls back. Mid-loop
        # invariant: the session.commit() at the bottom never fires when advance returns
        # None on any iteration.
        entry = _entry()
        _mock_insert(monkeypatch, entry)
        _mock_get_obligation(monkeypatch, _obligation())
        advances: list[AdvanceResult | None] = [
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-05-15", new_cursor="2026-06-15"),
            None,
        ]
        advance_mock = AsyncMock(side_effect=advances)
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        session = AsyncMock()

        with pytest.raises(ExpenseCycleObligationGoneError) as raised:
            await expense_service.create_expenses_for_obligation_cycles(
                session,
                USER,
                cycles=3,
                date=date(2026, 5, 28),
                amount=Decimal("12500"),
                currency="ARS",
                payment_obligation_id=7,
            )

        assert raised.value.code == "expense_cycle_obligation_gone"
        assert advance_mock.await_count == 2
        assert expense_service.expense_repository.create.await_count == 2
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_stale_fires_once_per_batch_not_per_iteration(self, monkeypatch):
        # _insert_expense_row no longer touches card_reconciliation_service (the hoist
        # avoids N redundant indexed lookups for the same card+currency+date). The
        # multi-cycle function fires mark_stale_for_date exactly once after the loop —
        # idempotent regardless of how many rows the batch emitted.
        entry = _entry()
        entry.credit_card_id = 42
        _mock_insert(monkeypatch, entry)
        _mock_get_obligation(monkeypatch, _obligation())
        advances = [
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-05-15", new_cursor="2026-06-15"),
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-06-15", new_cursor="2026-07-15"),
            AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-07-15", new_cursor="2026-08-15"),
        ]
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", AsyncMock(side_effect=advances))
        stale_mock = AsyncMock()
        monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", stale_mock)
        session = AsyncMock()

        await expense_service.create_expenses_for_obligation_cycles(
            session,
            USER,
            cycles=3,
            date=date(2026, 5, 28),
            amount=Decimal("12500"),
            currency="ARS",
            payment_obligation_id=7,
            credit_card_id=42,
        )

        # 3 inserts, 1 stale-mark (was 3 pre-hoist).
        assert expense_service.expense_repository.create.await_count == 3
        assert stale_mock.await_count == 1
        stale_mock.assert_awaited_once_with(session, 42, "ARS", date(2026, 5, 28))

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


# The three refusals above used to leave the router as one `expense_cycle_invalid`, so the user read
# the same "check the dates" message for each. Driven through POST /expenses so the code a client
# receives is the one pinned, with persistence mocked as above.
def _client() -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_admin_session] = _fake_session
    app.dependency_overrides[get_auth_session] = _fake_session
    app.dependency_overrides[get_jwt_or_api_key_user] = lambda: USER
    return TestClient(app, raise_server_exceptions=False)


_MULTI_CYCLE_BODY = {
    "date": "2026-05-28",
    "amount": "12500",
    "currency": "ARS",
    "payment_obligation_id": 7,
    "cycles_to_advance": 3,
}


class TestEachRefusalReachesTheClientWithItsOwnCode:
    @pytest.fixture(autouse=True)
    def _reset_limiter(self):
        limiter.reset()
        yield
        limiter.reset()

    def test_a_one_off_obligation_answers_not_recurring(self, monkeypatch):
        _mock_insert(monkeypatch, _entry())
        _mock_get_obligation(monkeypatch, _obligation(recurrence=None))
        response = _client().post("/expenses", json=_MULTI_CYCLE_BODY)
        assert (response.status_code, response.json()["code"]) == (400, "expense_cycle_obligation_not_recurring")

    def test_an_obligation_deleted_mid_walk_answers_gone(self, monkeypatch):
        _mock_insert(monkeypatch, _entry())
        _mock_get_obligation(monkeypatch, _obligation())
        first = AdvanceResult(plan_type="obligation", plan_id=7, plan_name="ABL", previous_cursor="2026-05-15", new_cursor="2026-06-15")
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", AsyncMock(side_effect=[first, None]))
        response = _client().post("/expenses", json=_MULTI_CYCLE_BODY)
        assert (response.status_code, response.json()["code"]) == (409, "expense_cycle_obligation_gone")

    def test_a_walk_past_year_9999_answers_out_of_range_not_500(self, monkeypatch):
        # next_due_date has no upper bound, so twelve annual cycles from 9995 step the cursor to 10007,
        # which the date math cannot build. The REAL advance_or_archive runs here (only its repository
        # is mocked), so without the service's up-front check this is a ValueError mid-loop: a 500.
        _mock_insert(monkeypatch, _entry())
        obligation = _obligation(recurrence="annual")
        obligation.next_due_date = date(9995, 1, 1)
        _mock_get_obligation(monkeypatch, obligation)
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "get_by_id", AsyncMock(return_value=obligation))
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        response = _client().post("/expenses", json={**_MULTI_CYCLE_BODY, "cycles_to_advance": 12})
        assert (response.status_code, response.json()["code"]) == (400, "expense_cycles_out_of_range")
        expense_service.expense_repository.create.assert_not_called()

    def test_a_walk_ending_in_year_9999_is_still_allowed(self, monkeypatch):
        # The boundary of the check above: two annual cycles from 9997 land in 9999, the last
        # representable year, and must go through.
        _mock_insert(monkeypatch, _entry())
        obligation = _obligation(recurrence="annual")
        obligation.next_due_date = date(9997, 1, 15)
        _mock_get_obligation(monkeypatch, obligation)
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "get_by_id", AsyncMock(return_value=obligation))
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        response = _client().post("/expenses", json={**_MULTI_CYCLE_BODY, "cycles_to_advance": 2})
        assert response.status_code == 201, response.json()
        assert obligation.next_due_date == date(9999, 1, 15)
