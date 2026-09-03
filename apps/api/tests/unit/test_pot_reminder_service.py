# The overdue-valuation reminder: who it reaches, when, and how it avoids saying the same thing twice.
#
# Every one of these is a property the job cannot be observed to have from outside. It runs hourly with
# no user watching, its notifications are best-effort, and a reminder that never fires and one that
# fires every hour both look like silence from the outside — the first because nothing arrives, the
# second because the dedupe index quietly refuses the duplicates.

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.pot import Pot, PotCadence, PotMemberPermission
from app.services import pot_reminder_service as svc

GROUP = Group(id=10, name="Casa", kind=GroupKind.household)
# The custodian (write access) and a plain co-owner who can see the pot but cannot value anything in it.
WRITER = GroupMember(id=100, group_id=10, user_id=1, display_name="Santi", role=GroupMemberRole.admin)
VIEWER = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.member)
PLACEHOLDER = GroupMember(id=102, group_id=10, display_name="Nico", role=GroupMemberRole.member)

# 12:00 UTC, which is 09:00 in Buenos Aires (UTC-3) — the reminder hour.
NOON_UTC = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
BUENOS_AIRES = "America/Argentina/Buenos_Aires"


def _pot(*, cadence: PotCadence = PotCadence.monthly, name: str | None = "Depto") -> Pot:
    return Pot(id=5, group_id=10, name=name, base_currency="USD", snapshot_cadence=cadence, is_default=False)


def _permission(member_id: int, *, can_write: bool) -> PotMemberPermission:
    return PotMemberPermission(pot_id=5, member_id=member_id, can_view=True, can_write=can_write)


# Wires one pot in one group: the custodian may write, the co-owner may only view, and the pot is
# behind on its cadence unless told otherwise.
def _arrange(monkeypatch, *, pots=None, timezones=None, permissions=None, freshness=(date(2026, 7, 12), True), told=None):
    monkeypatch.setattr(svc.pot_repository, "list_all", AsyncMock(return_value=pots if pots is not None else [_pot()]))
    monkeypatch.setattr(
        svc.pot_repository,
        "list_permissions_by_pots",
        AsyncMock(
            return_value={5: permissions if permissions is not None else [_permission(100, can_write=True), _permission(101, can_write=False)]}
        ),
    )
    monkeypatch.setattr(svc.group_repository, "list_members_by_groups", AsyncMock(return_value={10: [WRITER, VIEWER, PLACEHOLDER]}))
    monkeypatch.setattr(svc.group_repository, "get_by_ids", AsyncMock(return_value=[GROUP]))
    monkeypatch.setattr(
        svc.user_settings_repository,
        "get_all_timezones",
        AsyncMock(return_value=timezones if timezones is not None else {1: BUENOS_AIRES, 2: BUENOS_AIRES}),
    )
    monkeypatch.setattr(svc.pot_service, "get_freshness", AsyncMock(return_value=freshness))
    # dispatch answers with how many people it actually WROTE a row for, which is what the job counts.
    # Defaults to "everybody it was asked about", so a test that does not care reads naturally.
    dispatched = AsyncMock(side_effect=(lambda _e, ids, _p, **_kw: len(ids)) if told is None else (lambda *_a, **_kw: told))
    monkeypatch.setattr(svc.notification_service, "dispatch", dispatched)
    return dispatched


class TestWhoIsReminded:
    @pytest.mark.asyncio
    async def test_only_the_members_who_can_actually_value_the_pot(self, monkeypatch):
        # The co-owner sees the staleness on the pot page already; only a writer can clear it, and a
        # nudge to somebody who cannot act is a nudge they learn to ignore.
        dispatched = _arrange(monkeypatch)
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 1
        assert dispatched.await_args.args[1] == [WRITER.user_id]

    @pytest.mark.asyncio
    async def test_a_pot_with_no_write_permissions_at_all_reminds_nobody(self, monkeypatch):
        # A pot whose group has read-only access everywhere: there is no standard anybody can meet, so
        # a reminder would be a message with no possible response.
        dispatched = _arrange(monkeypatch, permissions=[_permission(100, can_write=False)])
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_name_only_seat_is_never_reminded(self, monkeypatch):
        # There is no account to reach. Asserted through a permission row on the placeholder, which is
        # a state D34 supports.
        dispatched = _arrange(monkeypatch, permissions=[_permission(102, can_write=True)])
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_former_member_is_never_reminded(self, monkeypatch):
        # Their seat is inactive, so the group's rows are already invisible to them; a reminder about a
        # pot they can no longer open would be the notification leaking what the policy hides.
        departed = GroupMember(id=100, group_id=10, user_id=1, display_name="Santi", role=GroupMemberRole.admin, is_active=False)
        dispatched = _arrange(monkeypatch, permissions=[_permission(100, can_write=True)])
        monkeypatch.setattr(svc.group_repository, "list_members_by_groups", AsyncMock(return_value={10: [departed]}))
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_not_awaited()


class TestWhen:
    @pytest.mark.asyncio
    async def test_nothing_fires_outside_the_recipients_own_local_hour(self, monkeypatch):
        # 12:00 UTC is 09:00 in Buenos Aires but 14:00 in Madrid. The job ticks hourly; the filter is
        # what stops it waking somebody in the middle of their afternoon — or their night.
        dispatched = _arrange(monkeypatch, timezones={1: "Europe/Madrid"})
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_user_with_no_stored_timezone_is_treated_as_utc(self, monkeypatch):
        # The same fallback every other per-user-hour job uses. At 09:00 UTC they are due.
        dispatched = _arrange(monkeypatch, timezones={})
        assert await svc.send_due_reminders(AsyncMock(), datetime(2026, 9, 2, 9, 0, tzinfo=UTC)) == 1
        assert dispatched.await_args.args[1] == [WRITER.user_id]

    @pytest.mark.asyncio
    async def test_two_writers_in_different_zones_are_reached_on_their_own_ticks(self, monkeypatch):
        # Not on one: the pot is one thing but the reminder is a message to a person, and each person's
        # morning is a different UTC hour. The dedupe key is what makes reaching them separately safe.
        dispatched = _arrange(
            monkeypatch,
            permissions=[_permission(100, can_write=True), _permission(101, can_write=True)],
            timezones={1: BUENOS_AIRES, 2: "Europe/Madrid"},
        )
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 1
        assert dispatched.await_args.args[1] == [WRITER.user_id]
        dispatched.reset_mock()
        # 07:00 UTC is 09:00 in Madrid.
        assert await svc.send_due_reminders(AsyncMock(), datetime(2026, 9, 2, 7, 0, tzinfo=UTC)) == 1
        assert dispatched.await_args.args[1] == [VIEWER.user_id]


class TestWhatIsSaid:
    @pytest.mark.asyncio
    async def test_a_pot_that_is_up_to_date_says_nothing(self, monkeypatch):
        dispatched = _arrange(monkeypatch, freshness=(date(2026, 9, 1), False))
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        dispatched.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_freshness_is_asked_about_the_recipients_own_today(self, monkeypatch):
        # Not the server's, and the fixture is chosen so the two ANSWERS DIFFER: at 19:00 UTC on the
        # 1st it is already 09:00 on the 2nd in Kiritimati (UTC+14). Asked about the server's date, a
        # pot one day past its period reads as up to date for a whole day — and a Buenos Aires fixture
        # cannot show that, because there both dates are the same.
        _arrange(monkeypatch, timezones={1: "Pacific/Kiritimati"})
        freshness = AsyncMock(return_value=(date(2026, 7, 12), True))
        monkeypatch.setattr(svc.pot_service, "get_freshness", freshness)
        now = datetime(2026, 9, 1, 19, 0, tzinfo=UTC)
        assert await svc.send_due_reminders(AsyncMock(), now) == 1
        assert now.date() == date(2026, 9, 1)
        assert freshness.await_args.kwargs["as_of_date"] == date(2026, 9, 2)

    @pytest.mark.asyncio
    async def test_the_payload_names_the_pot_the_group_and_when_it_was_last_valued(self, monkeypatch):
        dispatched = _arrange(monkeypatch)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        payload = dispatched.await_args.args[2]
        assert payload == {"group_id": 10, "group": "Casa", "pot_id": 5, "pot": "Depto", "valued_as_of": "2026-07-12"}

    @pytest.mark.asyncio
    async def test_a_pot_nobody_has_ever_valued_says_so_rather_than_naming_a_date(self, monkeypatch):
        # Two different sentences, and the null is what separates them: "Last valued 12 Jul" against
        # "It has never been valued".
        dispatched = _arrange(monkeypatch, freshness=(None, True))
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        assert dispatched.await_args.args[2]["valued_as_of"] is None

    @pytest.mark.asyncio
    async def test_a_nameless_default_pot_carries_a_null_name_for_the_renderer_to_label(self, monkeypatch):
        # The label a nameless pot reads under is LOCALIZED, and the payload is shared by every
        # recipient whatever language each of them uses — so the fallback belongs to each renderer.
        dispatched = _arrange(monkeypatch, pots=[_pot(name=None)])
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        assert dispatched.await_args.args[2]["pot"] is None


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_the_key_names_the_pot_and_the_calendar_month(self, monkeypatch):
        dispatched = _arrange(monkeypatch)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        assert dispatched.await_args.kwargs["dedupe_key"] == "pot:5:2026-09"

    @pytest.mark.asyncio
    async def test_a_weekly_pot_keys_on_the_iso_week_instead(self, monkeypatch):
        # Otherwise a weekly pot would be reminded once a MONTH — the cadence would decide the
        # freshness rule and not the nudge, which is the two halves disagreeing.
        dispatched = _arrange(monkeypatch, pots=[_pot(cadence=PotCadence.weekly)])
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        assert dispatched.await_args.kwargs["dedupe_key"] == "pot:5:2026-W36"

    @pytest.mark.asyncio
    async def test_the_key_changes_when_the_period_rolls_over_so_it_nudges_again(self, monkeypatch):
        # The reminder is once per period, not once ever: a pot still overdue next month must be raised
        # again, and the key is the only thing that decides that.
        dispatched = _arrange(monkeypatch)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        first = dispatched.await_args.kwargs["dedupe_key"]
        await svc.send_due_reminders(AsyncMock(), datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
        assert dispatched.await_args.kwargs["dedupe_key"] != first


class TestCost:
    @pytest.mark.asyncio
    async def test_no_pot_is_valued_when_nobody_is_due(self, monkeypatch):
        # The job runs 24 times a day over every pot in the database. Valuing them all on every tick
        # would be the expensive read multiplied by the pot count, 23 times out of 24 for nothing.
        _arrange(monkeypatch, timezones={1: "Europe/Madrid"})
        freshness = AsyncMock(return_value=(date(2026, 7, 12), True))
        monkeypatch.setattr(svc.pot_service, "get_freshness", freshness)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        freshness.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_roster_and_the_permissions_load_once_for_every_pot(self, monkeypatch):
        # Two pots must not cost two roster reads: the batch variants are what keep the job flat in the
        # number of pots.
        second = Pot(id=6, group_id=10, name="Otro", base_currency="USD", snapshot_cadence=PotCadence.monthly, is_default=False)
        monkeypatch.setattr(svc.pot_repository, "list_all", AsyncMock(return_value=[_pot(), second]))
        _arrange(monkeypatch, pots=[_pot(), second])
        members = AsyncMock(return_value={10: [WRITER]})
        permissions = AsyncMock(return_value={5: [_permission(100, can_write=True)], 6: [_permission(100, can_write=True)]})
        monkeypatch.setattr(svc.group_repository, "list_members_by_groups", members)
        monkeypatch.setattr(svc.pot_repository, "list_permissions_by_pots", permissions)
        await svc.send_due_reminders(AsyncMock(), NOON_UTC)
        assert (members.await_count, permissions.await_count) == (1, 1)

    @pytest.mark.asyncio
    async def test_an_empty_database_costs_one_query(self, monkeypatch):
        timezones = AsyncMock(return_value={})
        monkeypatch.setattr(svc.pot_repository, "list_all", AsyncMock(return_value=[]))
        monkeypatch.setattr(svc.user_settings_repository, "get_all_timezones", timezones)
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        timezones.assert_not_awaited()


class TestWhatTheJobReports:
    # The count the scheduler logs. A pot stays stale for the rest of its period, so the job offers the
    # same reminder to the same people every day and the dedupe index refuses all but the first — a
    # count of who was ASKED would therefore claim a daily reminder nobody received, every day for a
    # month. Counting what dispatch actually wrote is the only figure an operator can act on.
    @pytest.mark.asyncio
    async def test_a_deduped_repeat_is_reported_as_nobody_told(self, monkeypatch):
        dispatched = _arrange(monkeypatch, told=0)
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 0
        # And it still made the offer — the silence is the index's decision, not the job's.
        dispatched.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_it_reports_the_people_actually_told(self, monkeypatch):
        # The positive control: without it, the assertion above would also pass on a job that always
        # reported zero.
        _arrange(monkeypatch)
        assert await svc.send_due_reminders(AsyncMock(), NOON_UTC) == 1


def test_the_reminder_hour_is_a_waking_one():
    # Not an assertion about the number so much as about the reason for it: this is a message asking
    # somebody to do something, unlike the 01:00 auto-expense job, which is a silent write nobody reads.
    assert 7 <= svc.SNAPSHOT_REMINDER_HOUR_LOCAL <= 20
