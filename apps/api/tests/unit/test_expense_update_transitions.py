from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import AdvanceResult, ReverseResult
from app.models.expense_entry import ExpenseEntry
from app.models.user import User
from app.services import (
    card_reconciliation_service,
    expense_service,
    installment_service,
    payment_obligation_service,
    subscription_service,
)

# Tests for the symmetric FK-transition model in expense_service.update_expense (Phase 3,
# follow-up Items 10 + audit round 2). The service composes per-FK transition detection,
# the most-recent-linked gate, the actual reverse/advance helpers, and the stale-mark
# bookkeeping. We mock everything below the service so the tests pin the orchestration
# layer — the called-helper return values are spoofed; the helpers themselves are tested
# in test_reverse_for_unlink.py and test_advance_for_manual_entry.py.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _entry(
    *,
    expense_id: int = 1,
    date_: date = date(2026, 6, 5),
    payment_obligation_id: int | None = None,
    subscription_id: int | None = None,
    installment_id: int | None = None,
    credit_card_id: int | None = None,
    currency: str = "USD",
) -> ExpenseEntry:
    return ExpenseEntry(
        id=expense_id,
        user_id=1,
        date=date_,
        amount=Decimal("100"),
        currency=currency,
        notes=None,
        payment_method=None,
        credit_card_id=credit_card_id,
        source="manual",
        payment_obligation_id=payment_obligation_id,
        subscription_id=subscription_id,
        installment_id=installment_id,
    )


@pytest.fixture(autouse=True)
def _silence_card_stale(monkeypatch):
    # mark_stale_for_date is fired on every update_expense when credit_card_id is set on
    # the prior or new row. Stubbing it keeps the transition tests focused on FK logic.
    monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", AsyncMock())
    # The SEC-4 ownership guard runs before the transition logic. These tests operate on
    # owned FKs, so stub every ownership lookup as "owned" to keep the focus on orchestration.
    for repo in ("credit_card_repository", "payment_obligation_repository", "subscription_repository", "installment_repository"):
        monkeypatch.setattr(getattr(expense_service, repo), "get_by_id", AsyncMock(return_value=object()))


def _mock_repos(monkeypatch, entry: ExpenseEntry):
    monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
    monkeypatch.setattr(expense_service.expense_repository, "save", AsyncMock())


class TestUpdateExpenseTransitions:
    @pytest.mark.asyncio
    async def test_no_fk_change_fires_neither(self, monkeypatch):
        # Editing amount only with a pre-existing obligation link. The frontend echoes the
        # FK (no real change), but the transition detector spots new == old and skips both
        # advance + reverse paths.
        entry = _entry(payment_obligation_id=5)
        _mock_repos(monkeypatch, entry)
        advance_mock = AsyncMock()
        reverse_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        monkeypatch.setattr(payment_obligation_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, amount=Decimal("200"), payment_obligation_id=5)

        assert advance is None
        assert reverse is None
        advance_mock.assert_not_called()
        reverse_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_fk_fires_advance_only(self, monkeypatch):
        # None -> subscription Y (edit-add): advance Y, no reverse. Closes the Limitation #2
        # gap where adding a FK on edit used to silently leave the cursor where it was.
        entry = _entry()
        _mock_repos(monkeypatch, entry)
        advance_result = AdvanceResult(
            plan_type="subscription",
            plan_id=7,
            plan_name="Netflix",
            previous_cursor="2026-06-05",
            new_cursor="2026-07-05",
        )
        advance_mock = AsyncMock(return_value=advance_result)
        reverse_mock = AsyncMock()
        monkeypatch.setattr(subscription_service, "advance_for_manual_entry", advance_mock)
        monkeypatch.setattr(subscription_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, subscription_id=7)

        assert advance == advance_result
        assert reverse is None
        advance_mock.assert_awaited_once_with(session, 7, USER, entry.date)
        reverse_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_fk_fires_reverse_when_most_recent(self, monkeypatch):
        # obligation X -> None (unlink): reverse on X, no advance. Most-recent check returns
        # True so the reverse path activates.
        entry = _entry(payment_obligation_id=5)
        _mock_repos(monkeypatch, entry)
        monkeypatch.setattr(
            expense_service.expense_repository,
            "is_most_recent_linked_obligation_expense",
            AsyncMock(return_value=True),
        )
        reverse_result = ReverseResult(
            plan_type="obligation",
            plan_id=5,
            plan_name="ABL",
            previous_cursor="2026-07-05",
            new_cursor="2026-06-05",
        )
        advance_mock = AsyncMock()
        reverse_mock = AsyncMock(return_value=reverse_result)
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        monkeypatch.setattr(payment_obligation_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, payment_obligation_id=None)

        assert advance is None
        assert reverse == reverse_result
        advance_mock.assert_not_called()
        reverse_mock.assert_awaited_once_with(session, 5, USER)

    @pytest.mark.asyncio
    async def test_clear_fk_skips_reverse_when_not_most_recent(self, monkeypatch):
        # Same as above but is_most_recent_linked returns False — the row was mid-chain, so
        # the cursor stays put. No advance, no reverse.
        entry = _entry(payment_obligation_id=5)
        _mock_repos(monkeypatch, entry)
        monkeypatch.setattr(
            expense_service.expense_repository,
            "is_most_recent_linked_obligation_expense",
            AsyncMock(return_value=False),
        )
        reverse_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, payment_obligation_id=None)

        assert advance is None
        assert reverse is None
        reverse_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_type_swap_fires_both(self, monkeypatch):
        # obligation 5 -> obligation 8 (the Limitation #1 case). OLD obligation walks back
        # (it was wrongly advanced when E1 was first Mark-Paid against it); NEW obligation
        # advances (it gains a linked expense). Two cursor changes in one update.
        entry = _entry(payment_obligation_id=5)
        _mock_repos(monkeypatch, entry)
        monkeypatch.setattr(
            expense_service.expense_repository,
            "is_most_recent_linked_obligation_expense",
            AsyncMock(return_value=True),
        )
        advance_result = AdvanceResult(
            plan_type="obligation",
            plan_id=8,
            plan_name="ARBA",
            previous_cursor="2026-06-10",
            new_cursor="2026-07-10",
        )
        reverse_result = ReverseResult(
            plan_type="obligation",
            plan_id=5,
            plan_name="ABL",
            previous_cursor="2026-07-05",
            new_cursor="2026-06-05",
        )
        advance_mock = AsyncMock(return_value=advance_result)
        reverse_mock = AsyncMock(return_value=reverse_result)
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        monkeypatch.setattr(payment_obligation_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, payment_obligation_id=8)

        assert advance == advance_result
        assert reverse == reverse_result
        advance_mock.assert_awaited_once_with(session, 8, USER)
        reverse_mock.assert_awaited_once_with(session, 5, USER)

    @pytest.mark.asyncio
    async def test_cross_type_swap_fires_both(self, monkeypatch):
        # obligation X -> subscription Y: the OLD obligation walks back, the NEW subscription
        # advances. The transition detector handles cross-type swaps independently per FK
        # column, so both fire.
        entry = _entry(payment_obligation_id=5)
        _mock_repos(monkeypatch, entry)
        monkeypatch.setattr(
            expense_service.expense_repository,
            "is_most_recent_linked_obligation_expense",
            AsyncMock(return_value=True),
        )
        reverse_result = ReverseResult(
            plan_type="obligation",
            plan_id=5,
            plan_name="ABL",
            previous_cursor="2026-07-05",
            new_cursor="2026-06-05",
        )
        advance_result = AdvanceResult(
            plan_type="subscription",
            plan_id=7,
            plan_name="Netflix",
            previous_cursor="2026-06-05",
            new_cursor="2026-07-05",
        )
        obligation_reverse = AsyncMock(return_value=reverse_result)
        subscription_advance = AsyncMock(return_value=advance_result)
        monkeypatch.setattr(payment_obligation_service, "reverse_for_unlink", obligation_reverse)
        monkeypatch.setattr(subscription_service, "advance_for_manual_entry", subscription_advance)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, payment_obligation_id=None, subscription_id=7)

        assert advance == advance_result
        assert reverse == reverse_result
        obligation_reverse.assert_awaited_once_with(session, 5, USER)
        subscription_advance.assert_awaited_once_with(session, 7, USER, entry.date)

    @pytest.mark.asyncio
    async def test_advance_returns_none_propagates_as_none(self, monkeypatch):
        # When the NEW plan's advance helper itself returns None (multi-jump per Item 9),
        # the outer service surfaces None — not a stale spurious result.
        entry = _entry()
        _mock_repos(monkeypatch, entry)
        advance_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(installment_service, "advance_for_manual_entry", advance_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, installment_id=3)

        assert advance is None
        assert reverse is None
        advance_mock.assert_awaited_once_with(session, 3, USER, entry.date)

    @pytest.mark.asyncio
    async def test_date_edit_same_subscription_recomputes(self, monkeypatch):
        # Subscription link unchanged but the linked expense's date moved (audit round-2
        # follow-up): the cursor is recomputed by reversing the OLD date's advance and
        # re-applying the NEW date's on the SAME subscription. The reverse gets old_date, the
        # advance gets the new date. (Both helpers self-gate; see test_reverse_for_unlink /
        # test_advance_for_manual_entry.)
        old_date = date(2026, 6, 5)
        new_date = date(2026, 5, 20)
        entry = _entry(subscription_id=7, date_=old_date)
        _mock_repos(monkeypatch, entry)
        # Most-recent link (the common single-link case): the reverse is eligible to fire.
        monkeypatch.setattr(
            expense_service.expense_repository,
            "is_most_recent_linked_subscription_expense",
            AsyncMock(return_value=True),
        )
        reverse_result = ReverseResult(
            plan_type="subscription",
            plan_id=7,
            plan_name="Netflix",
            previous_cursor="2026-07-05",
            new_cursor="2026-06-05",
        )
        advance_mock = AsyncMock(return_value=None)
        reverse_mock = AsyncMock(return_value=reverse_result)
        monkeypatch.setattr(subscription_service, "advance_for_manual_entry", advance_mock)
        monkeypatch.setattr(subscription_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, subscription_id=7, date=new_date)

        assert reverse == reverse_result
        assert advance is None
        reverse_mock.assert_awaited_once_with(session, 7, USER, old_date)
        advance_mock.assert_awaited_once_with(session, 7, USER, new_date)

    @pytest.mark.asyncio
    async def test_date_edit_same_installment_recomputes(self, monkeypatch):
        # Installment counterpart of the date-edit recompute: reverse(old_date) + advance(new_date)
        # on the same installment plan.
        old_date = date(2026, 6, 5)
        new_date = date(2026, 7, 20)
        entry = _entry(installment_id=3, date_=old_date)
        _mock_repos(monkeypatch, entry)
        # Most-recent link (the common single-link case): the reverse is eligible to fire.
        monkeypatch.setattr(
            expense_service.expense_repository,
            "is_most_recent_linked_installment_expense",
            AsyncMock(return_value=True),
        )
        advance_result = AdvanceResult(
            plan_type="installment",
            plan_id=3,
            plan_name="TV",
            previous_cursor="2",
            new_cursor="3",
        )
        advance_mock = AsyncMock(return_value=advance_result)
        reverse_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(installment_service, "advance_for_manual_entry", advance_mock)
        monkeypatch.setattr(installment_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, installment_id=3, date=new_date)

        assert advance == advance_result
        assert reverse is None
        reverse_mock.assert_awaited_once_with(session, 3, USER, old_date)
        advance_mock.assert_awaited_once_with(session, 3, USER, new_date)

    @pytest.mark.asyncio
    async def test_date_edit_skips_reverse_when_not_most_recent(self, monkeypatch):
        # A date edit on a subscription-linked expense that is NOT the most-recent link for the
        # plan must NOT reverse the cursor — only the newest link can govern the cursor top, so
        # the reverse is gated by is_most_recent exactly like the FK-swap and delete paths (this
        # keeps the edit consistent with delete+create and avoids stepping the cursor back onto a
        # cycle a newer link still covers). The advance stays ungated (it self-gates on the cursor).
        old_date = date(2026, 6, 5)
        new_date = date(2026, 5, 20)
        entry = _entry(subscription_id=7, date_=old_date)
        _mock_repos(monkeypatch, entry)
        monkeypatch.setattr(
            expense_service.expense_repository,
            "is_most_recent_linked_subscription_expense",
            AsyncMock(return_value=False),
        )
        advance_mock = AsyncMock(return_value=None)
        reverse_mock = AsyncMock()
        monkeypatch.setattr(subscription_service, "advance_for_manual_entry", advance_mock)
        monkeypatch.setattr(subscription_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, subscription_id=7, date=new_date)

        assert reverse is None
        reverse_mock.assert_not_called()
        # The advance still runs (ungated, self-gating), mirroring create-at-new-date.
        advance_mock.assert_awaited_once_with(session, 7, USER, new_date)

    @pytest.mark.asyncio
    async def test_date_edit_obligation_is_exempt(self, monkeypatch):
        # An obligation-linked expense's date edit does NOT recompute — obligations archive
        # once and carry no cursor. Neither advance nor reverse fires.
        entry = _entry(payment_obligation_id=5, date_=date(2026, 6, 5))
        _mock_repos(monkeypatch, entry)
        advance_mock = AsyncMock()
        reverse_mock = AsyncMock()
        monkeypatch.setattr(payment_obligation_service, "advance_or_archive", advance_mock)
        monkeypatch.setattr(payment_obligation_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, payment_obligation_id=5, date=date(2026, 5, 20))

        assert advance is None
        assert reverse is None
        advance_mock.assert_not_called()
        reverse_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_amount_edit_same_date_fires_neither(self, monkeypatch):
        # Editing a subscription-linked expense's amount with the date unchanged must NOT
        # recompute — the date-edit path requires an actual date change.
        entry = _entry(subscription_id=7, date_=date(2026, 6, 5))
        _mock_repos(monkeypatch, entry)
        advance_mock = AsyncMock()
        reverse_mock = AsyncMock()
        monkeypatch.setattr(subscription_service, "advance_for_manual_entry", advance_mock)
        monkeypatch.setattr(subscription_service, "reverse_for_unlink", reverse_mock)
        session = AsyncMock()

        _entry_out, advance, reverse = await expense_service.update_expense(session, 1, USER, subscription_id=7, amount=Decimal("200"))

        assert advance is None
        assert reverse is None
        advance_mock.assert_not_called()
        reverse_mock.assert_not_called()
