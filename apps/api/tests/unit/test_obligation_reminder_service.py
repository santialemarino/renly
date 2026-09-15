# The upcoming-bill reminder: which bills it announces, to whom, when, and how it avoids nagging.
#
# Every property here is one the job cannot be observed to have from outside. It runs hourly with
# nobody watching, and the two ways of getting it wrong look identical from a distance: a reminder that
# never fires and one that fires every day both read as "nothing seems broken" — the first because
# nothing arrives, the second because the dedupe index silently refuses the duplicates.

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.notification import NotificationEvent
from app.models.payment_obligation import PaymentObligation
from app.services import obligation_reminder_service as svc

# 12:00 UTC, which is 09:00 in Buenos Aires (UTC-3) — the reminder hour.
NOON_UTC = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
BUENOS_AIRES = "America/Argentina/Buenos_Aires"
# Buenos Aires' local date at NOON_UTC, so a "three days away" bill is the 18th.
LOCAL_TODAY = date(2026, 9, 15)


def _obligation(*, id: int = 1, user_id: int = 1, due: date = date(2026, 9, 18), name: str = "Edenor") -> PaymentObligation:
    return PaymentObligation(
        id=id,
        user_id=user_id,
        name=name,
        amount=Decimal("45000.00"),
        currency="ARS",
        next_due_date=due,
        anchor_day=due.day,
        recurrence="monthly",
    )


# Wires one owner with one bill due in three days, at their own local reminder hour.
def _arrange(monkeypatch, *, obligations=None, timezones=None, told=None):
    monkeypatch.setattr(
        svc.payment_obligation_repository,
        "list_active_due",
        AsyncMock(return_value=[_obligation()] if obligations is None else obligations),
    )
    monkeypatch.setattr(
        svc.user_settings_repository,
        "get_all_timezones",
        AsyncMock(return_value={1: BUENOS_AIRES} if timezones is None else timezones),
    )
    # dispatch answers with how many people it actually WROTE a row for, which is what the job counts.
    dispatched = AsyncMock(side_effect=(lambda _e, ids, _p, **_kw: len(ids)) if told is None else (lambda *_a, **_kw: told))
    monkeypatch.setattr(svc.notification_service, "dispatch", dispatched)
    return dispatched


class TestWhenItFires:
    @pytest.mark.asyncio
    async def test_a_bill_inside_the_lead_time_is_announced(self, monkeypatch):
        dispatched = _arrange(monkeypatch)
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 1
        assert dispatched.await_args.args[0] == NotificationEvent.obligation_due
        assert dispatched.await_args.args[1] == [1]

    @pytest.mark.asyncio
    async def test_a_bill_one_day_past_the_lead_time_is_not(self, monkeypatch):
        # The boundary from the other side, which is what makes the test above about the lead time
        # rather than about "a row exists". The SQL scan deliberately reaches a day further than the
        # lead (every user's local today can lead UTC by up to 14 hours), so this row IS loaded and the
        # per-user comparison is the only thing that leaves it alone.
        dispatched = _arrange(monkeypatch, obligations=[_obligation(due=date(2026, 9, 19))])
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_bill_due_exactly_at_the_lead_boundary_is_announced(self, monkeypatch):
        # Inclusive, and pinned: three days ahead is the intended day, so an off-by-one here would move
        # every reminder in the product by a day without changing any count.
        _arrange(monkeypatch, obligations=[_obligation(due=LOCAL_TODAY + timedelta(days=svc.OBLIGATION_REMINDER_LEAD_DAYS))])
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 1

    @pytest.mark.asyncio
    async def test_a_bill_already_overdue_is_still_offered(self, monkeypatch):
        # Deliberate, and the reason the window has no lower bound: an overdue bill's key is the key its
        # own cycle already used, so the dedupe index — not a date filter — is what stops the nagging.
        # Filtering it out here would instead mean a bill that first became visible late is never
        # announced at all.
        _arrange(monkeypatch, obligations=[_obligation(due=date(2026, 8, 1))])
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 1

    @pytest.mark.asyncio
    async def test_nobody_is_reached_outside_their_own_local_hour(self, monkeypatch):
        # The whole reason the job is hourly. At 12:00 UTC a user in UTC is at 12:00 local, not 09:00.
        dispatched = _arrange(monkeypatch, timezones={1: "UTC"})
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_user_with_no_stored_timezone_is_treated_as_UTC(self, monkeypatch):
        # Day-zero behaviour for an un-filled account, matching the auto-expense job. 09:00 UTC is
        # therefore their hour, and 12:00 is not.
        _arrange(monkeypatch, timezones={})
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        assert await svc.send_due_reminders(AsyncMock(), datetime(2026, 9, 15, 9, 0, tzinfo=UTC)) == 1

    @pytest.mark.asyncio
    async def test_the_horizon_is_the_OWNERS_calendar_day_and_not_the_servers(self, monkeypatch):
        # The two dates are the same in every other fixture here, which is what let a server-date
        # horizon pass unnoticed. Auckland is UTC+12, so its local 09:00 on the 16th is 21:00 UTC on
        # the 15th: the owner's today is the 16th while the server's is still the 15th. A bill due on
        # the 19th is inside the owner's three-day window and outside the server's.
        _arrange(
            monkeypatch,
            obligations=[_obligation(due=date(2026, 9, 19))],
            timezones={1: "Pacific/Auckland"},
        )
        assert await svc.send_due_reminders(AsyncMock(), datetime(2026, 9, 15, 21, 0, tzinfo=UTC)) == 1

    @pytest.mark.asyncio
    async def test_the_sql_scan_is_bounded_by_the_lead_time(self, monkeypatch):
        # The bound only prunes — the per-user comparison decides — but an unbounded scan loads every
        # active obligation in the database on every hourly tick, which nothing else here would notice
        # because the repository is mocked. One day PAST the lead, because a user's local today can run
        # up to 14 hours ahead of the UTC date.
        scan = AsyncMock(return_value=[])
        monkeypatch.setattr(svc.payment_obligation_repository, "list_active_due", scan)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        assert scan.await_args.args[1] == NOON_UTC.date() + timedelta(days=svc.OBLIGATION_REMINDER_LEAD_DAYS + 1)

    @pytest.mark.asyncio
    async def test_no_obligations_at_all_costs_nothing_further(self, monkeypatch):
        # Prune before you measure: an empty scan must not go on to load every timezone in the database.
        timezones = AsyncMock(return_value={})
        monkeypatch.setattr(svc.payment_obligation_repository, "list_active_due", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.user_settings_repository, "get_all_timezones", timezones)
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        timezones.assert_not_awaited()


class TestWhatItSays:
    @pytest.mark.asyncio
    async def test_the_payload_carries_everything_the_copy_interpolates(self, monkeypatch):
        # The email, the push and the feed row all render from this one dict, so a field missing here is
        # a literal `{name}` on somebody's lock screen.
        dispatched = _arrange(monkeypatch)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        payload = dispatched.await_args.args[2]
        assert payload == {
            "obligation_id": 1,
            "name": "Edenor",
            "amount": "45000.00",
            "currency": "ARS",
            "date": "2026-09-18",
        }

    @pytest.mark.asyncio
    async def test_the_dedupe_key_names_the_cycle_rather_than_the_day(self, monkeypatch):
        # Keyed on the DUE DATE, which is what makes one reminder per cycle rather than one per tick: a
        # bill sits inside the window for the whole lead period, so the job re-offers it every day and
        # the partial unique index refuses all but the first. Paying advances next_due_date, which is
        # what makes the following cycle a different key rather than a repeat.
        dispatched = _arrange(monkeypatch)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        assert dispatched.await_args.kwargs["dedupe_key"] == "obligation:1:2026-09-18"

    @pytest.mark.asyncio
    async def test_two_bills_for_one_person_are_two_separate_messages(self, monkeypatch):
        # One notification per BILL, because each names its own amount and date. Grouping them would
        # need a count variant and would say less.
        dispatched = _arrange(monkeypatch, obligations=[_obligation(id=1), _obligation(id=2, name="Aysa")])
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 2
        assert {call.kwargs["dedupe_key"] for call in dispatched.await_args_list} == {
            "obligation:1:2026-09-18",
            "obligation:2:2026-09-18",
        }

    @pytest.mark.asyncio
    async def test_it_counts_who_was_told_rather_than_who_was_offered(self, monkeypatch):
        # A bill stays inside the window for the whole lead period, so the offer is made every day and
        # the dedupe index refuses all but the first. Counting the offer would make the scheduler's log
        # claim a daily reminder nobody received — the same correction PR 7 made to the pot reminder.
        dispatched = _arrange(monkeypatch, told=0)
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_awaited_once()


class TestWhoIsReached:
    @pytest.mark.asyncio
    async def test_each_bill_reaches_only_its_own_owner(self, monkeypatch):
        # The scan is cluster-wide (the job has no user context), so the owner filter is the only thing
        # standing between one person's bill and another person's inbox.
        dispatched = _arrange(
            monkeypatch,
            obligations=[_obligation(id=1, user_id=1), _obligation(id=2, user_id=2, name="Aysa")],
            timezones={1: BUENOS_AIRES, 2: BUENOS_AIRES},
        )
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        reached = {call.kwargs["dedupe_key"]: call.args[1] for call in dispatched.await_args_list}
        assert reached == {"obligation:1:2026-09-18": [1], "obligation:2:2026-09-18": [2]}

    @pytest.mark.asyncio
    async def test_one_owner_at_their_hour_does_not_drag_another_along(self, monkeypatch):
        # Two owners, two timezones, one tick. The hour test is per PERSON, so a shared tick must not
        # announce the bill of somebody for whom it is the middle of the night.
        dispatched = _arrange(
            monkeypatch,
            obligations=[_obligation(id=1, user_id=1), _obligation(id=2, user_id=2, name="Aysa")],
            timezones={1: BUENOS_AIRES, 2: "UTC"},
        )
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 1
        assert dispatched.await_args.args[1] == [1]
