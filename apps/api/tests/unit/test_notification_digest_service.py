# The daily email digest: who gets one, when, what is in it, and what happens to the queue afterwards.
#
# The failure modes here are all quiet. A digest that never fires and one that fires twice both look
# like nothing from outside — the first because no email arrives, the second because the second copy is
# indistinguishable from the first. And the queue is the only record of what is owed, so clearing it
# without sending, or sending without clearing, are each one line away from each other.

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.notification import Notification, NotificationEvent
from app.models.user import User
from app.services import notification_digest_service as svc

# 23:00 UTC, which is 20:00 in Buenos Aires (UTC-3) — the digest hour.
EVENING_UTC = datetime(2026, 9, 15, 23, 0, tzinfo=UTC)
BUENOS_AIRES = "America/Argentina/Buenos_Aires"

# Captured at import, BEFORE _arrange replaces it: a test that wants the REAL sender has to put this
# back, and reading it off the module inside the test would restore the mock to itself.
_REAL_SEND = svc._send

USER = User(id=1, name="Santi", email="santi@test.local", password_hash="x", session_epoch=0)
OTHER = User(id=2, name="Ana", email="ana@test.local", password_hash="x", session_epoch=0)


def _row(id: int, user_id: int = 1, event: NotificationEvent = NotificationEvent.plan_charged, **payload) -> Notification:
    base = {"variant": "subscription", "name": "Netflix", "amount": "15.00", "currency": "USD", "date": "2026-09-15"}
    return Notification(id=id, user_id=user_id, event=event, payload={**base, **payload}, digest_pending=True)


# Wires one person owed one summary, at their own local digest hour. Returns the mocks the tests assert
# on: what was sent, and which rows were taken out of the queue.
def _arrange(monkeypatch, *, pending=None, timezones=None, users=None):
    pending = {1: [_row(10)]} if pending is None else pending
    monkeypatch.setattr(svc.notification_repository, "list_digest_pending_user_ids", AsyncMock(return_value=sorted(pending)))
    monkeypatch.setattr(svc.notification_repository, "list_digest_pending", AsyncMock(return_value=pending))
    cleared = AsyncMock(return_value=0)
    monkeypatch.setattr(svc.notification_repository, "clear_digest_pending", cleared)
    monkeypatch.setattr(
        svc.user_settings_repository,
        "get_all_timezones",
        AsyncMock(return_value={1: BUENOS_AIRES, 2: BUENOS_AIRES} if timezones is None else timezones),
    )
    monkeypatch.setattr(svc.user_repository, "get_by_ids", AsyncMock(return_value={USER.id: USER, OTHER.id: OTHER} if users is None else users))
    monkeypatch.setattr(svc.settings_service, "get_languages_by_user_ids", AsyncMock(side_effect=lambda _s, ids: dict.fromkeys(ids, "en")))
    sent = AsyncMock()
    monkeypatch.setattr(svc, "_send", sent)
    return {"sent": sent, "cleared": cleared}


class TestWhenItFires:
    @pytest.mark.asyncio
    async def test_somebody_owed_a_summary_at_their_own_evening_hour_gets_one(self, monkeypatch):
        mocks = _arrange(monkeypatch)
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 1
        mocks["sent"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nobody_is_reached_outside_their_own_local_hour(self, monkeypatch):
        # The whole reason the job is hourly rather than daily. At 23:00 UTC a user in UTC is at 23:00
        # local, not 20:00 — a daily cron would pick one global hour and be wrong for everybody outside
        # it.
        mocks = _arrange(monkeypatch, timezones={1: "UTC"})
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 0
        mocks["sent"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_empty_queue_costs_one_index_probe_and_nothing_else(self, monkeypatch):
        # Prune before you measure. The queue is the FIRST read precisely so an hour with nothing owed
        # never loads a timezone, a user or a notification — and this job runs every hour forever.
        timezones = AsyncMock(return_value={})
        monkeypatch.setattr(svc.notification_repository, "list_digest_pending_user_ids", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.user_settings_repository, "get_all_timezones", timezones)
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 0
        timezones.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nobody_due_this_hour_loads_no_notifications(self, monkeypatch):
        # The second prune: the queue names people across every timezone, and only the ones at their own
        # evening hour are worth reading rows for.
        rows = AsyncMock(return_value={})
        _arrange(monkeypatch, timezones={1: "UTC"})
        monkeypatch.setattr(svc.notification_repository, "list_digest_pending", rows)
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 0
        rows.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_it_counts_SUMMARIES_rather_than_the_rows_in_them(self, monkeypatch):
        # One person with a busy day is one email, and the scheduler's log says so. Every other fixture
        # here has a single pending row per person, which makes the two figures the same number — so
        # without a multi-row person nothing distinguishes "summaries sent" from "things summarised".
        mocks = _arrange(monkeypatch, pending={1: [_row(10), _row(11), _row(12)]})
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 1
        mocks["sent"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_persons_evening_does_not_drag_another_along(self, monkeypatch):
        # Two people owed a summary, two timezones, one tick.
        mocks = _arrange(monkeypatch, pending={1: [_row(10)], 2: [_row(11, user_id=2)]}, timezones={1: BUENOS_AIRES, 2: "UTC"})
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 1
        assert mocks["sent"].await_args.args[0].to == USER.email


class TestWhatIsInIt:
    @pytest.mark.asyncio
    async def test_each_line_is_the_events_own_email_subject(self, monkeypatch):
        # The property the whole design rests on: a digest needs no per-event copy, because every event
        # already has a one-line form. So an event added later is digestible the day it exists.
        mocks = _arrange(monkeypatch, pending={1: [_row(10), _row(11, event=NotificationEvent.obligation_due, variant=None, name="Edenor")]})
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        text = mocks["sent"].await_args.args[0].text
        assert "Netflix — 15 USD recorded on September 15, 2026" in text
        assert "Edenor is due on September 15, 2026" in text

    @pytest.mark.asyncio
    async def test_the_subject_counts_what_the_email_covers(self, monkeypatch):
        mocks = _arrange(monkeypatch, pending={1: [_row(10), _row(11)]})
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        assert mocks["sent"].await_args.args[0].subject == "Your Renly summary — 2 updates"

    @pytest.mark.asyncio
    async def test_a_single_update_reads_in_the_singular(self, monkeypatch):
        # Two strings rather than one with a count, because "1 updates" is the kind of thing people
        # notice and nothing else would catch.
        mocks = _arrange(monkeypatch)
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        assert mocks["sent"].await_args.args[0].subject == "Your Renly summary — 1 update"

    @pytest.mark.asyncio
    async def test_it_is_written_in_the_recipients_own_language(self, monkeypatch):
        mocks = _arrange(monkeypatch)
        monkeypatch.setattr(svc.settings_service, "get_languages_by_user_ids", AsyncMock(return_value={1: "es"}))
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        assert mocks["sent"].await_args.args[0].subject == "Tu resumen de Renly — 1 novedad"

    @pytest.mark.asyncio
    async def test_a_long_day_is_capped_and_the_remainder_is_named(self, monkeypatch):
        # A heavy day must produce a readable email rather than a five-hundred-line one. Capping is only
        # safe because every row is in the feed the email links to — so the count is stated rather than
        # the remainder silently dropped.
        rows = [_row(index) for index in range(svc.DIGEST_MAX_ITEMS + 5)]
        mocks = _arrange(monkeypatch, pending={1: rows})
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        message = mocks["sent"].await_args.args[0]
        assert message.text.count("•") == svc.DIGEST_MAX_ITEMS
        assert "…and 5 more." in message.text
        # The subject counts the whole day, not the part that fitted: a summary that says 40 when 45
        # happened is a summary that is wrong about its own subject.
        assert message.subject == f"Your Renly summary — {svc.DIGEST_MAX_ITEMS + 5} updates"

    @pytest.mark.asyncio
    async def test_one_unrenderable_row_costs_its_own_line_and_nothing_else(self, monkeypatch):
        # A payload missing a field its copy interpolates. Inside a single-event send that costs one
        # message; here it would cost the whole day's summary, which is why the line render is guarded
        # per item rather than per email.
        broken = Notification(id=99, user_id=1, event=NotificationEvent.plan_charged, payload={"variant": "subscription"}, digest_pending=True)
        mocks = _arrange(monkeypatch, pending={1: [_row(10), broken]})
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        message = mocks["sent"].await_args.args[0]
        assert message.text.count("•") == 1
        assert "Netflix" in message.text

    @pytest.mark.asyncio
    async def test_it_points_at_the_notifications_page(self, monkeypatch):
        # Both links in a digest go there, and deliberately: it is where the full history lives AND
        # where the cadence is changed, so "see them all" and "turn this off" are one destination.
        monkeypatch.setattr(svc.settings, "web_base_url", "https://renly.test")
        mocks = _arrange(monkeypatch)
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        assert "https://renly.test/notifications" in mocks["sent"].await_args.args[0].text


class TestTheQueue:
    @pytest.mark.asyncio
    async def test_every_row_it_sent_is_taken_out_of_the_queue(self, monkeypatch):
        mocks = _arrange(monkeypatch, pending={1: [_row(10), _row(11)]})
        await svc.send_due_digests(AsyncMock(), EVENING_UTC)
        assert mocks["cleared"].await_args.args[1] == [10, 11]

    @pytest.mark.asyncio
    async def test_a_deleted_recipients_rows_are_cleared_even_though_nothing_was_sent(self, monkeypatch):
        # Otherwise the queue — and so this job's first read, every hour forever — keeps describing
        # somebody who can never be emailed.
        mocks = _arrange(monkeypatch, pending={2: [_row(12, user_id=2)]}, users={})
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 0
        mocks["sent"].assert_not_awaited()
        assert mocks["cleared"].await_args.args[1] == [12]

    @pytest.mark.asyncio
    async def test_a_send_that_fails_still_clears(self, monkeypatch):
        # The same posture every other send in this layer takes: the notifications are already in the
        # recipient's feed, so a provider outage must not leave a queue that re-sends the same summary
        # every day until it recovers.
        #
        # The REAL `_send` is put back for this one, and that is the whole test: with the mock in place
        # nothing could raise, so it would pass on a job that has no swallowing at all. The provider is
        # what fails here — which is the thing that actually fails in production.
        mocks = _arrange(monkeypatch)
        monkeypatch.setattr(svc, "_send", _REAL_SEND)
        monkeypatch.setattr(svc, "get_email_service", Mock(return_value=Mock(send=AsyncMock(side_effect=RuntimeError("down")))))
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 1
        assert mocks["cleared"].await_args.args[1] == [10]

    @pytest.mark.asyncio
    async def test_one_failing_send_does_not_abandon_the_rest_of_the_batch(self, monkeypatch):
        # They run inside an asyncio.gather, which propagates the first exception and cancels nothing
        # else usefully — so a single bad address would cost every other person's summary on that tick.
        mocks = _arrange(monkeypatch, pending={1: [_row(10)], 2: [_row(12, user_id=2)]})
        monkeypatch.setattr(svc, "_send", _REAL_SEND)
        send = AsyncMock(side_effect=[RuntimeError("down"), None])
        monkeypatch.setattr(svc, "get_email_service", Mock(return_value=Mock(send=send)))
        assert await svc.send_due_digests(AsyncMock(), EVENING_UTC) == 2
        assert send.await_count == 2
        assert mocks["cleared"].await_args.args[1] == [10, 12]

    @pytest.mark.asyncio
    async def test_the_queue_is_cleared_in_the_same_transaction_the_tick_commits(self, monkeypatch):
        # So a crash between sending and clearing cannot lose a summary silently: the rows stay pending
        # and the next tick rebuilds them.
        session = AsyncMock()
        _arrange(monkeypatch)
        await svc.send_due_digests(session, EVENING_UTC)
        session.commit.assert_awaited_once()
