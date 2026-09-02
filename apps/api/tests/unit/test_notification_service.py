# The notification layer's own rules: what the shipped defaults are, how an override changes them,
# who a dispatch actually reaches, and what the feed shows.
#
# The fan-out is the part worth testing hardest, because every one of its failure modes is silent by
# design — it swallows exceptions so a push outage cannot roll back a money write, which means a
# dispatch that reaches nobody looks exactly like one that reaches everybody.

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.domain import NotFoundError, PushNotConfiguredError
from app.domain.notification import is_enabled_by_default
from app.models.notification import Notification, NotificationChannel, NotificationEvent, NotificationPreference
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.repositories import notification_repository
from app.services import notification_service as svc

USER = User(id=1, name="Santi", email="santi@test.local", password_hash="x", session_epoch=0)
OTHER = User(id=2, name="Ana", email="ana@test.local", password_hash="x", session_epoch=0)

# The five events that reach a person outside the app out of the box, per §7's decision. Restated here
# as a literal rather than imported from the domain, so a change to the shipped behaviour has to be
# made twice on purpose instead of once by accident.
_OUTSIDE_APP = {
    NotificationEvent.balance_written_off,
    NotificationEvent.ownership_changed,
    NotificationEvent.settle_confirmed,
    NotificationEvent.settle_marked_paid,
    NotificationEvent.snapshot_due,
}


def _preference(user_id: int, event: NotificationEvent, channel: NotificationChannel, *, enabled: bool) -> NotificationPreference:
    return NotificationPreference(id=1, user_id=user_id, event=event, channel=channel, enabled=enabled)


def _subscription(id: int, user_id: int, endpoint: str) -> PushSubscription:
    return PushSubscription(id=id, user_id=user_id, endpoint=endpoint, p256dh="p", auth="a")


# Stands in for a template render that a payload cannot satisfy.
def _raises(*_args, **_kwargs):
    raise KeyError("member")


# Captured at import, BEFORE any test replaces them: `_arrange_dispatch` swaps both for mocks, so
# reading them back off the module inside a test would restore the mock to itself and silently exercise
# nothing — which is exactly what the first version of the test below did.
_REAL_SEND_EMAIL = svc._send_email
_REAL_SEND_PUSH = svc._send_push


# Wires a dispatch: one admin session, the preference read, the insert, and the two out-of-app senders.
# Returns the mocks the tests assert on.
def _arrange_dispatch(monkeypatch, *, overrides=None, written=None, subscriptions=None, push_configured=False):
    session = AsyncMock()

    @asynccontextmanager
    async def _admin_session():
        yield session

    monkeypatch.setattr(svc, "AdminSessionLocal", lambda: _admin_session())
    monkeypatch.setattr(svc.notification_repository, "preferences_by_user_ids", AsyncMock(return_value=overrides or {}))
    created = AsyncMock(side_effect=lambda _s, rows: [row.user_id for row in rows] if written is None else written)
    monkeypatch.setattr(svc.notification_repository, "create_many", created)
    monkeypatch.setattr(svc.user_repository, "get_by_ids", AsyncMock(return_value={USER.id: USER, OTHER.id: OTHER}))
    monkeypatch.setattr(svc.settings_service, "get_languages_by_user_ids", AsyncMock(side_effect=lambda _s, ids: dict.fromkeys(ids, "en")))
    monkeypatch.setattr(svc.push_subscription_repository, "list_by_user_ids", AsyncMock(return_value=subscriptions or {}))
    monkeypatch.setattr(svc.push_subscription_repository, "delete_by_endpoint", AsyncMock())
    monkeypatch.setattr(svc.push_subscription_repository, "touch", AsyncMock())
    monkeypatch.setattr(svc.web_push, "is_configured", lambda: push_configured)
    emails = AsyncMock()
    monkeypatch.setattr(svc, "_send_email", emails)
    pushes = AsyncMock(side_effect=lambda _c, sub, *_a: (sub, True, False))
    monkeypatch.setattr(svc, "_send_push", pushes)
    return {"created": created, "emails": emails, "pushes": pushes}


class TestShippedDefaults:
    def test_the_feed_is_on_for_every_event(self):
        # A row costs nothing and interrupts nobody, and it is also what stops a repeating notification
        # repeating — so there is no event it is off for by default.
        for event in NotificationEvent:
            assert is_enabled_by_default(event, NotificationChannel.in_app) is True

    def test_email_and_push_are_on_for_exactly_the_material_events(self):
        for event in NotificationEvent:
            expected = event in _OUTSIDE_APP
            assert is_enabled_by_default(event, NotificationChannel.email) is expected, event
            assert is_enabled_by_default(event, NotificationChannel.push) is expected, event

    def test_a_contribution_stays_quiet_where_a_re_agreement_does_not(self):
        # The distinction units exist for: a contribution dilutes everyone's PERCENTAGE and moves
        # nobody's VALUE, while a re-agreement moves value between people.
        assert is_enabled_by_default(NotificationEvent.pot_movement, NotificationChannel.email) is False
        assert is_enabled_by_default(NotificationEvent.ownership_changed, NotificationChannel.email) is True


class TestDispatch:
    @pytest.mark.asyncio
    async def test_a_recipient_with_every_channel_off_costs_no_row(self, monkeypatch):
        overrides = {
            OTHER.id: {
                (NotificationEvent.member_joined, NotificationChannel.in_app): False,
                (NotificationEvent.member_joined, NotificationChannel.email): False,
                (NotificationEvent.member_joined, NotificationChannel.push): False,
            }
        }
        mocks = _arrange_dispatch(monkeypatch, overrides=overrides)
        await svc.dispatch(NotificationEvent.member_joined, [OTHER.id], {"group_id": 1, "group": "Casa", "member": "Ana"})
        mocks["created"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_row_is_still_written_when_only_the_FEED_is_off(self, monkeypatch):
        # The row is the record of dispatch, not just the feed entry: it is what the dedupe index binds
        # on, so suppressing it would leave a repeating reminder with nothing to deduplicate against.
        overrides = {OTHER.id: {(NotificationEvent.snapshot_due, NotificationChannel.in_app): False}}
        mocks = _arrange_dispatch(monkeypatch, overrides=overrides)
        await svc.dispatch(NotificationEvent.snapshot_due, [OTHER.id], {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"})
        assert [row.user_id for row in mocks["created"].await_args.args[1]] == [OTHER.id]

    @pytest.mark.asyncio
    async def test_the_dedupe_key_reaches_the_row(self, monkeypatch):
        mocks = _arrange_dispatch(monkeypatch)
        await svc.dispatch(
            NotificationEvent.snapshot_due,
            [OTHER.id],
            {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"},
            dedupe_key="pot:5:2026-09",
        )
        assert mocks["created"].await_args.args[1][0].dedupe_key == "pot:5:2026-09"

    @pytest.mark.asyncio
    async def test_only_the_recipients_who_GAINED_a_row_are_emailed(self, monkeypatch):
        # The whole point of create_many returning ids: an hourly reminder re-offers the same
        # notification all period, and the second attempt must email nobody rather than everybody.
        mocks = _arrange_dispatch(monkeypatch, written=[])
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id, OTHER.id], {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"})
        mocks["emails"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_email_goes_to_the_recipients_whose_preference_allows_it(self, monkeypatch):
        overrides = {OTHER.id: {(NotificationEvent.snapshot_due, NotificationChannel.email): False}}
        mocks = _arrange_dispatch(monkeypatch, overrides=overrides)
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id, OTHER.id], {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"})
        assert [call.args[0].id for call in mocks["emails"].await_args_list] == [USER.id]

    @pytest.mark.asyncio
    async def test_nothing_is_pushed_on_a_deployment_with_no_key(self, monkeypatch):
        mocks = _arrange_dispatch(monkeypatch, subscriptions={USER.id: [_subscription(1, USER.id, "https://p/1")]}, push_configured=False)
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id], {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"})
        mocks["pushes"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_every_subscribed_browser_of_a_recipient_is_pushed_to(self, monkeypatch):
        # A laptop and a phone are two rows; reaching one of them is a notification the person may
        # never see.
        subs = {USER.id: [_subscription(1, USER.id, "https://p/1"), _subscription(2, USER.id, "https://p/2")]}
        mocks = _arrange_dispatch(monkeypatch, subscriptions=subs, push_configured=True)
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id], {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"})
        assert {call.args[1].endpoint for call in mocks["pushes"].await_args_list} == {"https://p/1", "https://p/2"}

    @pytest.mark.asyncio
    async def test_a_browser_the_push_service_says_is_gone_is_deleted(self, monkeypatch):
        deleted = AsyncMock()
        mocks = _arrange_dispatch(monkeypatch, subscriptions={USER.id: [_subscription(1, USER.id, "https://p/dead")]}, push_configured=True)
        monkeypatch.setattr(svc.push_subscription_repository, "delete_by_endpoint", deleted)
        monkeypatch.setattr(svc, "_send_push", AsyncMock(side_effect=lambda _c, sub, *_a: (sub, False, True)))
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id], {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"})
        assert deleted.await_args.args[1] == "https://p/dead"
        assert mocks["created"].await_count == 1

    @pytest.mark.asyncio
    async def test_a_successful_push_stamps_the_browser_so_devices_can_be_told_apart(self, monkeypatch):
        touched = AsyncMock()
        _arrange_dispatch(monkeypatch, subscriptions={USER.id: [_subscription(7, USER.id, "https://p/1")]}, push_configured=True)
        monkeypatch.setattr(svc.push_subscription_repository, "touch", touched)
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id], {"group_id": 1, "group": "Casa", "pot_id": 5, "pot": "P"})
        assert touched.await_args.args[1] == 7

    @pytest.mark.asyncio
    async def test_an_empty_recipient_list_does_nothing_at_all(self, monkeypatch):
        mocks = _arrange_dispatch(monkeypatch)
        await svc.dispatch(NotificationEvent.member_joined, [], {"group_id": 1})
        mocks["created"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_same_recipient_named_twice_gets_one_row(self, monkeypatch):
        # A caller can legitimately hand over a list with a repeat (two seats, one account); two rows
        # for one event would be two entries in one feed.
        mocks = _arrange_dispatch(monkeypatch)
        await svc.dispatch(NotificationEvent.member_joined, [OTHER.id, OTHER.id], {"group_id": 1, "group": "Casa", "member": "Ana"})
        assert [row.user_id for row in mocks["created"].await_args.args[1]] == [OTHER.id]

    @pytest.mark.asyncio
    async def test_an_unrenderable_EMAIL_does_not_abandon_the_push_bookkeeping(self, monkeypatch):
        # A producer that forgets a field the copy interpolates raises a KeyError in the RENDER, not in
        # the send. These run inside an asyncio.gather, so without the render being inside the sender's
        # own try, that KeyError abandons the loop that deletes dead push subscriptions and stamps live
        # ones — and the layer quietly stops maintaining them.
        _arrange_dispatch(monkeypatch, subscriptions={USER.id: [_subscription(7, USER.id, "https://p/1")]}, push_configured=True)
        monkeypatch.setattr(svc, "_send_email", _REAL_SEND_EMAIL)
        monkeypatch.setattr(svc.notification_templates, "notification_email", _raises)
        monkeypatch.setattr(svc, "get_email_service", lambda: AsyncMock(send=AsyncMock()))
        touched = AsyncMock()
        monkeypatch.setattr(svc.push_subscription_repository, "touch", touched)
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id], {"group_id": 1, "group": "Casa"})
        assert touched.await_args.args[1] == 7

    @pytest.mark.asyncio
    async def test_an_unrenderable_PUSH_costs_only_that_browser(self, monkeypatch):
        # Two recipients, and the copy raises for one of them. The other's push still goes, and the
        # bookkeeping still runs for it — without the guard the gather raises and neither happens.
        subscriptions = {USER.id: [_subscription(7, USER.id, "https://p/1")], OTHER.id: [_subscription(8, OTHER.id, "https://p/2")]}
        _arrange_dispatch(monkeypatch, subscriptions=subscriptions, push_configured=True)
        monkeypatch.setattr(svc, "_send_push", _REAL_SEND_PUSH)
        monkeypatch.setattr(svc.settings_service, "get_languages_by_user_ids", AsyncMock(return_value={USER.id: "es", OTHER.id: "en"}))
        monkeypatch.setattr(svc.notification_templates, "push_body", lambda _e, _p, locale: _raises() if locale == "es" else "ok")
        monkeypatch.setattr(svc.web_push, "send", AsyncMock(return_value=(True, False)))
        touched = AsyncMock()
        monkeypatch.setattr(svc.push_subscription_repository, "touch", touched)
        await svc.dispatch(NotificationEvent.snapshot_due, [USER.id, OTHER.id], {"group_id": 1, "group": "Casa"})
        # Only the renderable one was sent, and only it was stamped.
        assert [call.args[1] for call in touched.await_args_list] == [8]

    @pytest.mark.asyncio
    async def test_a_failure_anywhere_in_the_fan_out_is_swallowed(self, monkeypatch):
        # The rule the whole layer rests on: the event has already been committed, so a notification
        # failure must never reach the caller. Asserted by making the very first read raise.
        _arrange_dispatch(monkeypatch)
        monkeypatch.setattr(svc.notification_repository, "preferences_by_user_ids", AsyncMock(side_effect=RuntimeError("db gone")))
        await svc.dispatch(NotificationEvent.member_joined, [OTHER.id], {"group_id": 1, "group": "Casa", "member": "Ana"})

    @pytest.mark.asyncio
    async def test_the_created_at_can_be_pinned(self, monkeypatch):
        mocks = _arrange_dispatch(monkeypatch)
        moment = datetime(2026, 9, 2, 12, 0, 0)
        await svc.dispatch(NotificationEvent.member_joined, [OTHER.id], {"group_id": 1, "group": "Casa", "member": "Ana"}, now=moment)
        assert mocks["created"].await_args.args[1][0].created_at == moment


class TestLinks:
    def test_a_pot_event_points_at_the_pot(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "web_base_url", "https://renly.test")
        assert svc._link(NotificationEvent.pot_movement, {"group_id": 3, "pot_id": 5}) == "https://renly.test/shared/pots/5"

    def test_a_group_event_points_at_the_group(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "web_base_url", "https://renly.test")
        assert svc._link(NotificationEvent.shared_expense_added, {"group_id": 3}) == "https://renly.test/shared/3"

    def test_a_pot_event_with_no_pot_named_falls_back_to_the_group(self, monkeypatch):
        # A link is not worth a 500, so this is a fallback rather than a guard.
        monkeypatch.setattr(svc.settings, "web_base_url", "https://renly.test")
        assert svc._link(NotificationEvent.snapshot_due, {"group_id": 3}) == "https://renly.test/shared/3"


class TestFeed:
    def _arrange(self, monkeypatch, *, overrides=None, items=None, total=3, unread=2):
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=overrides or []))
        listed = AsyncMock(return_value=items if items is not None else [])
        monkeypatch.setattr(svc.notification_repository, "list_by_user", listed)
        counted = AsyncMock(return_value=total)
        monkeypatch.setattr(svc.notification_repository, "count_by_user", counted)
        unread_mock = AsyncMock(return_value=unread)
        monkeypatch.setattr(svc.notification_repository, "count_unread", unread_mock)
        return {"list": listed, "count": counted, "unread": unread_mock}

    @pytest.mark.asyncio
    async def test_the_list_the_total_and_the_badge_all_exclude_the_same_events(self, monkeypatch):
        # A badge counting rows the list does not show is the defect this shape exists to prevent, so
        # the exclusion is asserted on all three calls rather than on the response alone.
        overrides = [_preference(USER.id, NotificationEvent.pot_movement, NotificationChannel.in_app, enabled=False)]
        mocks = self._arrange(monkeypatch, overrides=overrides)
        await svc.get_feed(AsyncMock(), USER, limit=10)
        for name in ("list", "count", "unread"):
            assert mocks[name].await_args.kwargs["exclude_events"] == [NotificationEvent.pot_movement]

    @pytest.mark.asyncio
    async def test_nothing_is_excluded_when_the_user_has_expressed_no_preference(self, monkeypatch):
        mocks = self._arrange(monkeypatch)
        await svc.get_feed(AsyncMock(), USER, limit=10)
        assert mocks["list"].await_args.kwargs["exclude_events"] == []

    @pytest.mark.asyncio
    async def test_a_page_larger_than_the_cap_is_clamped(self, monkeypatch):
        mocks = self._arrange(monkeypatch)
        await svc.get_feed(AsyncMock(), USER, limit=10_000)
        assert mocks["list"].await_args.kwargs["limit"] == svc.MAX_FEED_PAGE_SIZE

    @pytest.mark.asyncio
    async def test_the_response_carries_the_rows_and_both_counts(self, monkeypatch):
        row = Notification(id=9, user_id=USER.id, event=NotificationEvent.member_joined, payload={"group": "Casa"})
        self._arrange(monkeypatch, items=[row], total=5, unread=1)
        feed = await svc.get_feed(AsyncMock(), USER, limit=10)
        assert (feed.total, feed.unread, [item.id for item in feed.items]) == (5, 1, [9])
        assert feed.items[0].payload == {"group": "Casa"}


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_another_persons_notification_is_a_404(self, monkeypatch):
        # Indistinguishable from one that does not exist, so an id from somebody else's feed reveals
        # nothing about whether it is real.
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.notification_repository, "get_by_id", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await svc.mark_read(AsyncMock(), 99, USER)

    @pytest.mark.asyncio
    async def test_marking_one_already_read_changes_nothing_and_says_so(self, monkeypatch):
        row = Notification(id=9, user_id=USER.id, event=NotificationEvent.member_joined, payload={}, read_at=datetime(2026, 9, 1))
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.notification_repository, "get_by_id", AsyncMock(return_value=row))
        monkeypatch.setattr(svc.notification_repository, "mark_read", AsyncMock(return_value=row))
        monkeypatch.setattr(svc.notification_repository, "count_unread", AsyncMock(return_value=0))
        assert (await svc.mark_read(AsyncMock(), 9, USER)).updated == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_clears_exactly_what_the_list_was_showing(self, monkeypatch):
        overrides = [_preference(USER.id, NotificationEvent.pot_movement, NotificationChannel.in_app, enabled=False)]
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=overrides))
        marked = AsyncMock(return_value=4)
        monkeypatch.setattr(svc.notification_repository, "mark_all_read", marked)
        monkeypatch.setattr(svc.notification_repository, "count_unread", AsyncMock(return_value=0))
        result = await svc.mark_all_read(AsyncMock(), USER)
        assert result.updated == 4
        assert marked.await_args.kwargs["exclude_events"] == [NotificationEvent.pot_movement]


class TestTheRepositoryMarkRead:
    # Driven through the repository rather than through the service, which stubs it: the guard being
    # tested lives inside the repository, and a service test cannot see it at all — a mutation sweep
    # found it survived the whole suite.

    class _Session:
        def add(self, _row):
            pass

        async def flush(self):
            pass

    @pytest.mark.asyncio
    async def test_marking_an_already_read_row_leaves_its_timestamp_alone(self):
        # Idempotent on purpose. A second click — or the "mark all" beside it — must not move the moment
        # the person actually read it.
        first_read = datetime(2026, 9, 1, 10, 0, 0)
        row = Notification(id=9, user_id=USER.id, event=NotificationEvent.member_joined, payload={}, read_at=first_read)
        await notification_repository.mark_read(self._Session(), row, now=datetime(2026, 9, 2, 10, 0, 0))
        assert row.read_at == first_read

    @pytest.mark.asyncio
    async def test_an_unread_row_gets_the_timestamp_it_is_given(self):
        # The positive control: without it the test above would pass on a function that never writes.
        row = Notification(id=9, user_id=USER.id, event=NotificationEvent.member_joined, payload={})
        moment = datetime(2026, 9, 2, 10, 0, 0)
        await notification_repository.mark_read(self._Session(), row, now=moment)
        assert row.read_at == moment


class TestPreferences:
    @pytest.mark.asyncio
    async def test_the_grid_is_complete_and_says_which_cells_are_defaults(self, monkeypatch):
        overrides = [_preference(USER.id, NotificationEvent.pot_movement, NotificationChannel.email, enabled=True)]
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=overrides))
        monkeypatch.setattr(svc.push_subscription_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.web_push, "is_configured", lambda: False)
        monkeypatch.setattr(svc.web_push, "public_key", lambda: None)

        response = await svc.get_preferences(AsyncMock(), USER)
        assert len(response.preferences) == len(NotificationEvent) * len(NotificationChannel)
        cell = next(p for p in response.preferences if p.event == NotificationEvent.pot_movement and p.channel == NotificationChannel.email)
        assert (cell.enabled, cell.is_default) == (True, False)
        untouched = next(p for p in response.preferences if p.event == NotificationEvent.pot_movement and p.channel == NotificationChannel.push)
        assert (untouched.enabled, untouched.is_default) == (False, True)

    @pytest.mark.asyncio
    async def test_an_unconfigured_deployment_reports_push_as_unavailable(self, monkeypatch):
        # So the surface can say so rather than offering a switch that silently does nothing.
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.push_subscription_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.web_push, "is_configured", lambda: False)
        monkeypatch.setattr(svc.web_push, "public_key", lambda: None)
        response = await svc.get_preferences(AsyncMock(), USER)
        assert (response.push_available, response.push_public_key) == (False, None)

    @pytest.mark.asyncio
    async def test_subscribing_is_refused_when_nothing_could_ever_be_sent(self, monkeypatch):
        # A stored subscription nothing will send to is worse than none, because the switch then reads
        # as on.
        monkeypatch.setattr(svc.web_push, "is_configured", lambda: False)
        with pytest.raises(PushNotConfiguredError):
            await svc.subscribe_push(AsyncMock(), USER, endpoint="https://p/1", p256dh="p", auth="a")

    @pytest.mark.asyncio
    async def test_subscribing_takes_the_browser_off_whoever_held_it_before(self, monkeypatch):
        # A shared computer, which a shared-money app invites: Ana signs in on Santi's browser and turns
        # push on. The browser has ONE subscription, so the endpoint she presents is the one Santi is
        # registered under — and his row has to go, or his group activity keeps arriving on a machine
        # she is now signed in on. It also cannot be moved through her own connection (the owner-match
        # policy refuses an update it cannot see), which is why the release runs on the PRIVILEGED
        # session and why this asserts the session it ran on, not just that it ran.
        admin_session = AsyncMock()

        @asynccontextmanager
        async def _admin():
            yield admin_session

        request_session = AsyncMock()
        monkeypatch.setattr(svc, "AdminSessionLocal", lambda: _admin())
        release = AsyncMock()
        monkeypatch.setattr(svc.push_subscription_repository, "release_endpoint", release)
        monkeypatch.setattr(svc.push_subscription_repository, "upsert", AsyncMock())
        monkeypatch.setattr(
            svc.push_subscription_repository, "list_by_user", AsyncMock(return_value=[_subscription(1, OTHER.id, "https://p/shared")])
        )
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.web_push, "is_configured", lambda: True)
        monkeypatch.setattr(svc.web_push, "public_key", lambda: "pub")

        await svc.subscribe_push(request_session, OTHER, endpoint="https://p/shared", p256dh="p", auth="a")

        release.assert_awaited_once_with(admin_session, "https://p/shared", keep_user_id=OTHER.id)
        # And the row she is claiming is spared: releasing everything would delete the subscription the
        # very next statement re-creates, turning every re-subscribe into a fresh row.
        assert release.await_args.kwargs["keep_user_id"] == OTHER.id

    @pytest.mark.asyncio
    async def test_unsubscribing_something_already_gone_is_not_an_error(self, monkeypatch):
        # The caller's intent — "this browser must not be pushed to" — is satisfied either way.
        monkeypatch.setattr(svc.notification_repository, "list_preferences", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.push_subscription_repository, "delete_by_endpoint", AsyncMock())
        monkeypatch.setattr(svc.push_subscription_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.web_push, "is_configured", lambda: False)
        monkeypatch.setattr(svc.web_push, "public_key", lambda: None)
        assert (await svc.unsubscribe_push(AsyncMock(), USER, endpoint="https://p/gone")).push_subscriptions == 0
