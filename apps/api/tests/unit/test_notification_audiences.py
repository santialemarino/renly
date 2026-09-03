# Who hears about something — the two functions that answer it, tested directly.
#
# Every producer stubs these, which is correct for a test about what an expense records but leaves the
# rules themselves uncovered: a mutation sweep found both could be widened to "everybody" with the
# whole suite still green. And what they decide is a confidentiality boundary, not a preference — a
# pot set to 'owners' visibility must not announce its movements to a member who cannot open it, and a
# former member must not keep hearing about a group whose rows they can no longer read. In both cases
# the notification would be the thing that discloses what the policy hides.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.group import GroupMember, GroupMemberRole
from app.models.pot import Pot, PotMemberPermission, PotVisibility
from app.models.snapshot import InvestmentSnapshot
from app.services import group_service, pot_service


def _member(member_id: int, *, user_id: int | None, is_active: bool = True) -> GroupMember:
    return GroupMember(id=member_id, group_id=10, user_id=user_id, display_name=f"M{member_id}", role=GroupMemberRole.member, is_active=is_active)


def _pot(*, visibility: PotVisibility = PotVisibility.members) -> Pot:
    return Pot(id=5, group_id=10, base_currency="USD", visibility=visibility, is_default=True)


def _permission(member_id: int, *, can_view: bool, can_write: bool = False) -> PotMemberPermission:
    return PotMemberPermission(pot_id=5, member_id=member_id, can_view=can_view, can_write=can_write)


class TestAGroupsAudience:
    # Seat 101 is the actor's, 102 another account, 103 a name-only placeholder, 104 a former member.
    _ROSTER = [
        _member(101, user_id=1),
        _member(102, user_id=2),
        _member(103, user_id=None),
        _member(104, user_id=4, is_active=False),
    ]

    async def _audience(self, monkeypatch, *, exclude=1):
        monkeypatch.setattr(group_service.group_repository, "list_members", AsyncMock(return_value=self._ROSTER))
        return await group_service.list_notifiable_user_ids(AsyncMock(), 10, exclude_user_id=exclude)

    @pytest.mark.asyncio
    async def test_a_former_member_is_never_notified(self, monkeypatch):
        # Their seat is inactive, so the membership policy already hides every row of the group from
        # them. Telling them about one would be the notification leaking what the policy hides.
        assert 4 not in await self._audience(monkeypatch)

    @pytest.mark.asyncio
    async def test_a_name_only_seat_is_never_notified(self, monkeypatch):
        # There is no account to reach — and the list is of ACCOUNTS, so a placeholder would contribute
        # a None that reached the fan-out as a user id.
        assert None not in await self._audience(monkeypatch)

    @pytest.mark.asyncio
    async def test_the_actor_is_not_told_what_they_just_did(self, monkeypatch):
        assert await self._audience(monkeypatch) == [2]

    @pytest.mark.asyncio
    async def test_excluding_nobody_includes_everyone_who_can_be_reached(self, monkeypatch):
        # The positive control: without it, every assertion above would also pass on a function that
        # returned nothing at all.
        assert await self._audience(monkeypatch, exclude=None) == [1, 2]


class TestAPotsAudience:
    _ROSTER = [
        _member(101, user_id=1),
        _member(102, user_id=2),
        _member(103, user_id=3),
    ]

    async def _audience(self, monkeypatch, *, pot, permissions, require_write=False, exclude=None):
        monkeypatch.setattr(pot_service.group_repository, "list_members", AsyncMock(return_value=self._ROSTER))
        monkeypatch.setattr(pot_service.pot_repository, "list_permissions", AsyncMock(return_value=permissions))
        return await pot_service.list_notifiable_user_ids(AsyncMock(), pot, require_write=require_write, exclude_user_id=exclude)

    @pytest.mark.asyncio
    async def test_a_members_pot_reaches_everyone_with_no_permission_row(self, monkeypatch):
        # The COALESCE the SQL helper carries: a member who joined after the pot was created has no
        # permission row at all and must still see a 'members' pot.
        assert await self._audience(monkeypatch, pot=_pot(), permissions=[]) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_an_owners_pot_reaches_nobody_without_an_explicit_row(self, monkeypatch):
        # Fails closed, which is the whole point of the 'owners' default.
        assert await self._audience(monkeypatch, pot=_pot(visibility=PotVisibility.owners), permissions=[]) == []

    @pytest.mark.asyncio
    async def test_an_explicit_denial_wins_over_a_members_default(self, monkeypatch):
        # The other direction of the same COALESCE: a row saying "no" beats the pot's own default, and
        # a movement in something you cannot open must not arrive in your feed.
        permissions = [_permission(102, can_view=False)]
        assert await self._audience(monkeypatch, pot=_pot(), permissions=permissions) == [1, 3]

    @pytest.mark.asyncio
    async def test_an_explicit_grant_opens_an_owners_pot_to_one_seat(self, monkeypatch):
        permissions = [_permission(103, can_view=True)]
        assert await self._audience(monkeypatch, pot=_pot(visibility=PotVisibility.owners), permissions=permissions) == [3]

    @pytest.mark.asyncio
    async def test_the_reminder_asks_for_WRITERS_and_view_alone_is_not_enough(self, monkeypatch):
        # Only a member with write access can snapshot a shared holding, so a nudge to re-value the pot
        # goes to the people who can clear it. Seat 102 can see it and cannot act on it.
        permissions = [_permission(101, can_view=True, can_write=True), _permission(102, can_view=True)]
        assert await self._audience(monkeypatch, pot=_pot(), permissions=permissions, require_write=True) == [1]

    @pytest.mark.asyncio
    async def test_the_actor_is_excluded_from_a_pots_audience_too(self, monkeypatch):
        assert await self._audience(monkeypatch, pot=_pot(), permissions=[], exclude=2) == [1, 3]


class TestTheBatchWriterResolution:
    # The reminder's own path, which resolves writers for many pots from rows loaded once. It has to
    # agree with the per-pot function above; a second opinion about what write access means is exactly
    # what the shared `_may_write` exists to prevent.
    _ROSTER = [_member(101, user_id=1), _member(102, user_id=2), _member(103, user_id=None), _member(104, user_id=4, is_active=False)]

    def test_it_names_only_active_seats_with_an_account_and_write_access(self):
        permissions = [
            _permission(101, can_view=True, can_write=True),
            _permission(102, can_view=True),
            _permission(103, can_view=True, can_write=True),
            _permission(104, can_view=True, can_write=True),
        ]
        assert pot_service.writer_user_ids(_pot(), self._ROSTER, permissions) == [1]

    def test_a_pot_nobody_may_write_names_nobody(self):
        # A pot with no permission rows is readable by its group and writable by nobody — write has no
        # visibility-style default, so there is nothing to fall back to.
        assert pot_service.writer_user_ids(_pot(), self._ROSTER, []) == []

    @pytest.mark.asyncio
    async def test_the_batch_and_the_per_pot_answer_agree(self, monkeypatch):
        # One rule, two call sites. Asserted against each other rather than each against a literal, so
        # the two cannot drift apart while both stay individually green.
        permissions = [_permission(101, can_view=True, can_write=True), _permission(102, can_view=True)]
        monkeypatch.setattr(pot_service.group_repository, "list_members", AsyncMock(return_value=self._ROSTER))
        monkeypatch.setattr(pot_service.pot_repository, "list_permissions", AsyncMock(return_value=permissions))
        one_at_a_time = await pot_service.list_notifiable_user_ids(AsyncMock(), _pot(), require_write=True)
        assert pot_service.writer_user_ids(_pot(), self._ROSTER, permissions) == one_at_a_time


class TestFreshnessSharesOneRule:
    # `get_freshness` exists so the hourly reminder never pays for a NAV, and the risk it introduces is
    # the one §20 named: two ways to compute one figure. These pin the cheap answer to the expensive
    # one over the same fixture, so a change to either shows up as a disagreement rather than as a
    # reminder that quietly stops firing.
    def _wire(self, monkeypatch, *, snapshot_date):
        snapshot = InvestmentSnapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=snapshot_date, value=Decimal("100"), currency="USD")
        monkeypatch.setattr(pot_service.pot_repository, "list_investment_ids", AsyncMock(return_value=[1]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: snapshot}))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        return lookup

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("snapshot_day", "expected_stale"), [(1, True), (25, False)])
    async def test_the_cheap_answer_matches_the_expensive_one(self, monkeypatch, snapshot_day, expected_stale):
        lookup = self._wire(monkeypatch, snapshot_date=date(2026, 6, snapshot_day))
        today = date(2026, 7, 15)
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=today, lookup=lookup)
        valued_as_of, is_stale = await pot_service.get_freshness(AsyncMock(), _pot(), as_of_date=today)
        assert (valued_as_of, is_stale) == (valuation.valued_as_of, valuation.is_stale)
        assert is_stale is expected_stale

    @pytest.mark.asyncio
    async def test_they_agree_about_a_pot_holding_nothing(self, monkeypatch):
        monkeypatch.setattr(pot_service.pot_repository, "list_investment_ids", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        lookup = AsyncMock()
        lookup.get_rate_map_at = lambda _d: {"USD": Decimal(1)}
        today = date(2026, 7, 15)
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=today, lookup=lookup)
        assert await pot_service.get_freshness(AsyncMock(), _pot(), as_of_date=today) == (valuation.valued_as_of, valuation.is_stale)
        # And "holding nothing" is not overdue: nobody can satisfy a demand to value an empty pot.
        assert valuation.is_stale is False

    @pytest.mark.asyncio
    async def test_freshness_needs_no_rate_lookup_at_all(self, monkeypatch):
        # What makes it usable from a background job: freshness is a question about DATES, so the answer
        # cannot depend on whose currency preference the job happened to run under.
        snapshot = InvestmentSnapshot(id=1, investment_id=1, user_id=None, pot_id=5, date=date(2026, 6, 1), value=Decimal("100"), currency="BRL")
        monkeypatch.setattr(pot_service.pot_repository, "list_investment_ids", AsyncMock(return_value=[1]))
        monkeypatch.setattr(pot_service.snapshot_repository, "get_latest_by_investments", AsyncMock(return_value={1: snapshot}))
        monkeypatch.setattr(pot_service.pot_repository, "list_accounts", AsyncMock(return_value=[]))
        # An unconvertible holding: the NAV is unknown, and the freshness is still a real date.
        unconvertible = AsyncMock()
        unconvertible.get_rate_map_at = lambda _d: {}
        today = date(2026, 7, 15)
        valuation = await pot_service.get_valuation(AsyncMock(), _pot(), as_of_date=today, lookup=unconvertible)
        assert valuation.nav is None
        assert await pot_service.get_freshness(AsyncMock(), _pot(), as_of_date=today) == (date(2026, 6, 1), True)
