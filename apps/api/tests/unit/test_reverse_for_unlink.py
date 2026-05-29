from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.services import installment_service, payment_obligation_service, subscription_service
from app.utils.dates import BILLING_CYCLE_MONTHLY

# Pure-helper tests for reverse-on-unlink (Phase 3, follow-up Item 10). The reverse
# helpers are async (they read + save the plan record), so each test uses an AsyncMock
# session — `session.commit` is the caller's responsibility, no commit assertion needed.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _sub(*, next_billing_date: date, billing_cycle: str = BILLING_CYCLE_MONTHLY, anchor_day: int | None = None) -> Subscription:
    return Subscription(
        id=1,
        user_id=1,
        name="Netflix",
        amount=Decimal("10"),
        currency="USD",
        billing_cycle=billing_cycle,
        next_billing_date=next_billing_date,
        anchor_day=anchor_day if anchor_day is not None else next_billing_date.day,
    )


def _inst(*, start_date: date, current_installment: int, installments_count: int = 12, is_active: bool = True) -> Installment:
    return Installment(
        id=1,
        user_id=1,
        name="TV Samsung",
        total_amount=Decimal("1200"),
        installment_amount=Decimal("100"),
        currency="USD",
        installments_count=installments_count,
        current_installment=current_installment,
        start_date=start_date,
        is_active=is_active,
    )


def _obligation(*, next_due_date: date, recurrence: str | None, anchor_day: int | None = None, is_active: bool = True) -> PaymentObligation:
    return PaymentObligation(
        id=1,
        user_id=1,
        name="ABL",
        amount=Decimal("50"),
        currency="USD",
        next_due_date=next_due_date,
        recurrence=recurrence,
        anchor_day=anchor_day if anchor_day is not None else next_due_date.day,
        is_active=is_active,
    )


# --- subscription_service.reverse_for_unlink ---


class TestSubscriptionReverseForUnlink:
    @pytest.mark.asyncio
    async def test_monthly_reverse_walks_one_cycle_back(self, monkeypatch):
        sub = _sub(next_billing_date=date(2026, 7, 15))
        session = AsyncMock()
        monkeypatch.setattr(
            subscription_service.subscription_repository,
            "get_by_id",
            AsyncMock(return_value=sub),
        )
        monkeypatch.setattr(subscription_service.subscription_repository, "save", AsyncMock())
        result = await subscription_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.plan_type == "subscription"
        assert result.previous_cursor == "2026-07-15"
        assert result.new_cursor == "2026-06-15"
        assert sub.next_billing_date == date(2026, 6, 15)

    @pytest.mark.asyncio
    async def test_anchor_day_31_walks_back_without_drift(self, monkeypatch):
        # cursor at Mar 31 (advanced from Feb's clamped Feb 28). Walking back must
        # land on Feb 28 (clamped), not Mar 1 — the anchor preserves the user's
        # intended 31st-of-month even after a prior clamp.
        sub = _sub(next_billing_date=date(2026, 3, 31), anchor_day=31)
        session = AsyncMock()
        monkeypatch.setattr(
            subscription_service.subscription_repository,
            "get_by_id",
            AsyncMock(return_value=sub),
        )
        monkeypatch.setattr(subscription_service.subscription_repository, "save", AsyncMock())
        result = await subscription_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.new_cursor == "2026-02-28"
        assert sub.next_billing_date == date(2026, 2, 28)

    @pytest.mark.asyncio
    async def test_missing_subscription_returns_none(self, monkeypatch):
        session = AsyncMock()
        monkeypatch.setattr(
            subscription_service.subscription_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        )
        result = await subscription_service.reverse_for_unlink(session, 999, USER)
        assert result is None


# --- installment_service.reverse_for_unlink ---


class TestInstallmentReverseForUnlink:
    @pytest.mark.asyncio
    async def test_decrement_cursor_on_active_plan(self, monkeypatch):
        inst = _inst(start_date=date(2026, 1, 1), current_installment=5, installments_count=12)
        session = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        monkeypatch.setattr(installment_service.installment_repository, "save", AsyncMock())
        result = await installment_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.plan_type == "installment"
        assert result.previous_cursor == "5"
        assert result.new_cursor == "4"
        assert result.total_count == 12
        assert inst.current_installment == 4
        assert inst.is_active is True

    @pytest.mark.asyncio
    async def test_fully_paid_plan_re_activates_on_reverse(self, monkeypatch):
        # current=13 with count=12 means the plan archived after the final cuota; reversing
        # walks current back to 12 (= count, still valid) and flips is_active back to True.
        # previous_cursor reads empty (archive sentinel) so the toast can announce the re-activation.
        inst = _inst(start_date=date(2026, 1, 1), current_installment=13, installments_count=12, is_active=False)
        session = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        monkeypatch.setattr(installment_service.installment_repository, "save", AsyncMock())
        result = await installment_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.previous_cursor == ""
        assert result.new_cursor == "12"
        assert inst.current_installment == 12
        assert inst.is_active is True

    @pytest.mark.asyncio
    async def test_cursor_at_one_is_noop(self, monkeypatch):
        # No cuota 0 exists. The expense couldn't have been a "most-recent linked" advance
        # from a cursor that's already at the first cuota, so this branch shouldn't fire in
        # practice — but guard against it returning a nonsensical cursor.
        inst = _inst(start_date=date(2026, 1, 1), current_installment=1, installments_count=12)
        session = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        result = await installment_service.reverse_for_unlink(session, 1, USER)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_installment_returns_none(self, monkeypatch):
        session = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=None))
        result = await installment_service.reverse_for_unlink(session, 999, USER)
        assert result is None

    @pytest.mark.asyncio
    async def test_user_archived_mid_plan_keeps_is_active_false(self, monkeypatch):
        # User manually archived an installment mid-plan (current=5, count=12, is_active=False).
        # Reverse walks current back to 4 but MUST NOT re-activate — the advance never archives
        # mid-plan, so is_active=False here reflects an explicit user choice that the reverse
        # has no business overriding. previous_cursor reads "5" (the value pre-decrement), NOT
        # the archive sentinel.
        inst = _inst(start_date=date(2026, 1, 1), current_installment=5, installments_count=12, is_active=False)
        session = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        monkeypatch.setattr(installment_service.installment_repository, "save", AsyncMock())
        result = await installment_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.previous_cursor == "5"
        assert result.new_cursor == "4"
        assert inst.current_installment == 4
        assert inst.is_active is False


# --- payment_obligation_service.reverse_for_unlink ---


class TestObligationReverseForUnlink:
    @pytest.mark.asyncio
    async def test_monthly_recurring_walks_one_cycle_back(self, monkeypatch):
        obl = _obligation(next_due_date=date(2026, 7, 15), recurrence="monthly")
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        result = await payment_obligation_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.plan_type == "obligation"
        assert result.previous_cursor == "2026-07-15"
        assert result.new_cursor == "2026-06-15"
        assert obl.next_due_date == date(2026, 6, 15)

    @pytest.mark.asyncio
    async def test_bimonthly_walks_two_months_back(self, monkeypatch):
        obl = _obligation(next_due_date=date(2026, 9, 1), recurrence="bimonthly")
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        result = await payment_obligation_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.new_cursor == "2026-07-01"

    @pytest.mark.asyncio
    async def test_anchor_day_31_quarterly_preserved_on_reverse(self, monkeypatch):
        # Quarterly anchored on day 31 — reversing from Oct 31 must hand back Jul 31, not
        # drift via June-30 clamping (matches the forward-advance anchor semantics).
        obl = _obligation(next_due_date=date(2026, 10, 31), recurrence="quarterly", anchor_day=31)
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        result = await payment_obligation_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.new_cursor == "2026-07-31"

    @pytest.mark.asyncio
    async def test_one_off_re_activates_without_date_change(self, monkeypatch):
        # One-off obligation: Mark Paid archived it (is_active=False, date unchanged).
        # Reverse re-activates; the date stays where it was. previous_cursor reads empty
        # to signal the archive-to-active transition.
        obl = _obligation(next_due_date=date(2026, 6, 15), recurrence=None, is_active=False)
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        result = await payment_obligation_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.previous_cursor == ""
        assert result.new_cursor == "2026-06-15"
        assert obl.is_active is True
        assert obl.next_due_date == date(2026, 6, 15)

    @pytest.mark.asyncio
    async def test_unknown_recurrence_no_op(self, monkeypatch):
        # Defensive default for corrupt records — mirrors compute_obligation_advance's
        # unknown-recurrence handling.
        obl = _obligation(next_due_date=date(2026, 6, 15), recurrence="weirdly")
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        result = await payment_obligation_service.reverse_for_unlink(session, 1, USER)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_obligation_returns_none(self, monkeypatch):
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        )
        result = await payment_obligation_service.reverse_for_unlink(session, 999, USER)
        assert result is None

    @pytest.mark.asyncio
    async def test_recurring_user_archived_keeps_is_active_false(self, monkeypatch):
        # User manually archived a recurring obligation (is_active=False) after a payment.
        # Reverse walks the date back but MUST NOT re-activate — the forward advance never
        # archives a recurring obligation, so is_active=False here reflects an explicit user
        # choice. previous_cursor reads the prior date (not the archive sentinel).
        obl = _obligation(next_due_date=date(2026, 7, 15), recurrence="monthly", is_active=False)
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        result = await payment_obligation_service.reverse_for_unlink(session, 1, USER)
        assert result is not None
        assert result.previous_cursor == "2026-07-15"
        assert result.new_cursor == "2026-06-15"
        assert obl.is_active is False


# --- AdvanceResult population on the existing advance helpers (Phase 3, follow-up Item 7) ---


class TestAdvanceResultPopulation:
    # Item 7 evolves the three advance entry points to return AdvanceResult | None instead
    # of bool / None. The advance math itself is covered by test_advance_for_manual_entry.py
    # and test_obligation_advance.py — these tests pin the return-type shape and the
    # archive-sentinel rule.

    @pytest.mark.asyncio
    async def test_subscription_advance_returns_result_with_iso_cursors(self, monkeypatch):
        sub = _sub(next_billing_date=date(2026, 6, 15))
        session = AsyncMock()
        monkeypatch.setattr(
            subscription_service.subscription_repository,
            "get_by_id",
            AsyncMock(return_value=sub),
        )
        monkeypatch.setattr(subscription_service.subscription_repository, "save", AsyncMock())
        result = await subscription_service.advance_for_manual_entry(session, 1, USER, date(2026, 6, 15))
        assert result is not None
        assert result.plan_type == "subscription"
        assert result.previous_cursor == "2026-06-15"
        assert result.new_cursor == "2026-07-15"

    @pytest.mark.asyncio
    async def test_installment_advance_archives_on_final_cuota(self, monkeypatch):
        # Final cuota (current=12 on a 12-cuota plan). Advance carries cursor to 13 and
        # archives the plan; new_cursor reads empty so the toast can use the "fully paid"
        # template rather than "moved to cuota 13".
        inst = _inst(start_date=date(2026, 1, 1), current_installment=12, installments_count=12)
        session = AsyncMock()
        monkeypatch.setattr(installment_service.installment_repository, "get_by_id", AsyncMock(return_value=inst))
        monkeypatch.setattr(installment_service.installment_repository, "save", AsyncMock())
        result = await installment_service.advance_for_manual_entry(session, 1, USER, date(2026, 12, 1))
        assert result is not None
        assert result.plan_type == "installment"
        assert result.previous_cursor == "12"
        assert result.new_cursor == ""
        assert result.total_count == 12
        assert inst.is_active is False

    @pytest.mark.asyncio
    async def test_one_off_obligation_advance_archives_with_empty_new_cursor(self, monkeypatch):
        obl = _obligation(next_due_date=date(2026, 6, 15), recurrence=None)
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        result = await payment_obligation_service.advance_or_archive(session, 1, USER)
        assert result is not None
        assert result.plan_type == "obligation"
        assert result.previous_cursor == "2026-06-15"
        assert result.new_cursor == ""
        assert obl.is_active is False

    @pytest.mark.asyncio
    async def test_quarterly_obligation_advance_returns_new_iso_cursor(self, monkeypatch):
        obl = _obligation(next_due_date=date(2026, 5, 1), recurrence="quarterly")
        session = AsyncMock()
        monkeypatch.setattr(
            payment_obligation_service.payment_obligation_repository,
            "get_by_id",
            AsyncMock(return_value=obl),
        )
        monkeypatch.setattr(payment_obligation_service.payment_obligation_repository, "save", AsyncMock())
        result = await payment_obligation_service.advance_or_archive(session, 1, USER)
        assert result is not None
        assert result.previous_cursor == "2026-05-01"
        assert result.new_cursor == "2026-08-01"
        assert obl.is_active is True

    @pytest.mark.asyncio
    async def test_multi_jump_subscription_returns_none(self, monkeypatch):
        # Item 9: multi-jump entries no longer advance. Verify the new contract:
        # advance_for_manual_entry returns None, the cursor is unchanged.
        sub = _sub(next_billing_date=date(2026, 5, 15))
        session = AsyncMock()
        monkeypatch.setattr(
            subscription_service.subscription_repository,
            "get_by_id",
            AsyncMock(return_value=sub),
        )
        save_mock = AsyncMock()
        monkeypatch.setattr(subscription_service.subscription_repository, "save", save_mock)
        result = await subscription_service.advance_for_manual_entry(session, 1, USER, date(2026, 8, 15))
        assert result is None
        assert sub.next_billing_date == date(2026, 5, 15)
        save_mock.assert_not_called()
