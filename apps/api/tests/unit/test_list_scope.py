# X2's shared machinery: the section fold every scope-aware list feeds, the dual-scope predicate the two
# stock lists share, and the pot catalogue that labels a section and says who may write it.
#
# The rule under all of it is that a scope selection FILTERS and is never a mode — so the sections are
# all on screen at once, and no header can state a figure the rows beneath it fail to add up to.

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlmodel import select

from app.domain.list_scope import SCOPE_PRIVATE, SCOPE_SHARED, ListScope, ListSection, SectionTotal, build_sections
from app.models.account import Account
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.investment import Investment
from app.models.pot import Pot, PotCadence, PotMemberPermission
from app.repositories.utils import scope_filter
from app.services import pot_service
from app.services.utils import group_sections, pot_sections


# The compiled WHERE of a statement, which is the only part of a predicate reachable without a database.
def _where(model, pot_ids: list[int], scope: ListScope) -> str:
    stmt = select(model).where(scope_filter(model, 7, pot_ids, scope))
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).split("WHERE")[1]


class TestBuildSections:
    def test_the_callers_own_rows_sort_first_and_then_each_container_by_id(self):
        # The list queries order their rows by the same column with NULLS FIRST, so the sections and
        # the rows they label cannot disagree about which comes first.
        sections = build_sections([(9, "ARS", Decimal("1"), 1), (None, "ARS", Decimal("2"), 1), (4, "ARS", Decimal("3"), 1)])
        assert [s.key for s in sections] == [None, 4, 9]

    def test_a_keys_count_is_summed_across_its_currency_groups(self):
        # A row belongs to exactly one currency, so the groups partition the key's rows — summing the
        # group counts is the key's own count. Two currencies on ONE key, so a fixture with a single
        # bucket per key could not tell a sum from an overwrite.
        sections = build_sections([(4, "ARS", Decimal("30"), 2), (4, "USD", Decimal("40"), 3)])
        assert (sections[0].count, len(sections[0].totals)) == (5, 2)

    def test_totals_are_ordered_by_currency_code_and_never_netted(self):
        sections = build_sections([(4, "USD", Decimal("40"), 1), (4, "ARS", Decimal("30"), 1)])
        assert [(t.currency, t.amount) for t in sections[0].totals] == [("ARS", Decimal("30")), ("USD", Decimal("40"))]

    def test_repeated_buckets_of_one_currency_accumulate(self):
        sections = build_sections([(4, "ARS", Decimal("30"), 1), (4, "ARS", Decimal("12"), 1)])
        assert sections[0].totals == [SectionTotal(currency="ARS", amount=Decimal("42"))]

    def test_a_null_currency_reports_a_count_and_no_total(self):
        # `/investments` shows no money column, so a section total there can only honestly be a count —
        # a header figure the visible rows cannot add up to is the thing X2 exists to avoid.
        sections = build_sections([(None, None, None, 4), (6, None, None, 2)])
        assert [(s.key, s.count, s.totals) for s in sections] == [(None, 4, []), (6, 2, [])]

    def test_no_rows_is_no_sections(self):
        assert build_sections([]) == []


class TestSectionResponses:
    def test_a_pot_section_carries_its_label_its_group_and_its_write_flag(self):
        scopes = [pot_service.PotScope(pot_id=6, name="Viaje", group_id=2, group_name="Casa", can_write=True, cadence=PotCadence.monthly)]
        section = pot_sections([ListSection(key=6, count=2, totals=[SectionTotal("ARS", Decimal("30"))])], scopes)[0]
        assert (section.scope, section.pot_id, section.pot_name, section.group_id, section.group_name, section.can_write) == (
            SCOPE_SHARED,
            6,
            "Viaje",
            2,
            "Casa",
            True,
        )

    def test_an_unnamed_default_pot_leaves_the_label_null_for_the_frontend_to_fill(self):
        # A4 leaves a group's default pot unnamed on purpose, and a null interpolated into copy fails by
        # PRINTING rather than by raising — so the fallback belongs where the words live.
        scopes = [pot_service.PotScope(pot_id=6, name=None, group_id=2, group_name="Casa", can_write=False, cadence=PotCadence.monthly)]
        assert pot_sections([ListSection(key=6, count=1, totals=[])], scopes)[0].pot_name is None

    def test_a_pot_section_with_no_catalogue_entry_is_dropped_rather_than_left_unlabelled(self):
        # Unreachable, because the row query filters on exactly the catalogue's pot ids. A header nobody
        # can read is still worse than rows that were never returned, so this fails closed.
        sections = pot_sections([ListSection(key=None, count=1, totals=[]), ListSection(key=99, count=1, totals=[])], [])
        assert [s.scope for s in sections] == [SCOPE_PRIVATE]

    def test_the_private_section_is_writable_and_names_nothing(self):
        section = pot_sections([ListSection(key=None, count=3, totals=[])], [])[0]
        assert (section.scope, section.pot_id, section.group_id, section.group_name, section.can_write) == (SCOPE_PRIVATE, None, None, None, True)

    def test_a_group_section_is_never_writable(self):
        # A shared FLOW row's id belongs to shared_expenses / shared_income, so a PUT to /expenses/{id}
        # would land on whatever private row holds that number. 5b settled that as a refusal.
        assert group_sections([ListSection(key=2, count=1, totals=[])], {2: "Casa"})[0].can_write is False

    def test_a_group_section_with_no_resolved_name_is_dropped(self):
        assert group_sections([ListSection(key=2, count=1, totals=[])], {}) == []


class TestScopeFilter:
    @pytest.mark.parametrize("model", [Investment, Account])
    def test_all_reads_the_callers_own_rows_and_the_pots_they_may_see(self, model):
        where = _where(model, [3, 5], ListScope.all)
        assert "user_id = 7" in where
        assert "pot_id IN (3, 5)" in where
        assert " OR " in where

    @pytest.mark.parametrize("model", [Investment, Account])
    def test_private_reads_no_pot_rows_at_all(self, model):
        where = _where(model, [3, 5], ListScope.private)
        assert "user_id = 7" in where
        assert "pot_id" not in where

    @pytest.mark.parametrize("model", [Investment, Account])
    def test_shared_reads_no_private_rows_at_all(self, model):
        where = _where(model, [3, 5], ListScope.shared)
        assert "pot_id IN (3, 5)" in where
        assert "user_id" not in where

    @pytest.mark.parametrize("model", [Investment, Account])
    def test_a_solo_user_gets_exactly_the_owner_match_the_list_ran_before_pots_existed(self, model):
        # Empty pot ids is a solo user, which is every user at launch. An `IN ()` branch would make all
        # of them pay for a predicate that can never match.
        where = _where(model, [], ListScope.all)
        assert "user_id = 7" in where
        assert "pot_id" not in where


# A pot in group 2, named unless the test is about the unnamed default.
def _pot(pot_id: int, *, name: str | None = "Viaje") -> Pot:
    return Pot(id=pot_id, group_id=2, name=name, base_currency="ARS")


def _seat(member_id: int, user_id: int | None = 1) -> GroupMember:
    return GroupMember(id=member_id, group_id=2, user_id=user_id, display_name="S", role=GroupMemberRole.member, is_active=True)


def _wire_catalogue(monkeypatch, pots, members, permissions, groups):
    monkeypatch.setattr(pot_service.pot_repository, "list_visible", AsyncMock(return_value=pots))
    monkeypatch.setattr(pot_service.group_repository, "list_members_by_groups", AsyncMock(return_value=members))
    monkeypatch.setattr(pot_service.pot_repository, "list_permissions_by_pots", AsyncMock(return_value=permissions))
    monkeypatch.setattr(pot_service.group_repository, "get_by_ids", AsyncMock(return_value=groups))


class TestListVisibleScopes:
    @pytest.mark.asyncio
    async def test_each_visible_pot_comes_back_labelled_and_sorted_by_id(
        self,
        monkeypatch,
    ):
        # Ascending pot id is the order the list queries put the rows in, so the catalogue and the rows
        # cannot disagree about which section comes first.
        _wire_catalogue(
            monkeypatch,
            [_pot(9, name="Viaje"), _pot(4, name=None)],
            {2: [_seat(11)]},
            {},
            [Group(id=2, name="Casa", kind=GroupKind.household)],
        )
        scopes = await pot_service.list_visible_scopes(AsyncMock(), 1)
        assert [(s.pot_id, s.name, s.group_name) for s in scopes] == [(4, None, "Casa"), (9, "Viaje", "Casa")]

    @pytest.mark.asyncio
    async def test_write_access_comes_from_the_callers_own_permission_row(self, monkeypatch):
        # Two seats and two permission rows, so a lookup that read the wrong member's row would show up
        # as the wrong answer rather than as the same answer twice.
        _wire_catalogue(
            monkeypatch,
            [_pot(9)],
            {2: [_seat(11), _seat(12, user_id=2)]},
            {9: [PotMemberPermission(pot_id=9, member_id=12, can_view=True, can_write=True)]},
            [Group(id=2, name="Casa", kind=GroupKind.household)],
        )
        assert (await pot_service.list_visible_scopes(AsyncMock(), 1))[0].can_write is False
        assert (await pot_service.list_visible_scopes(AsyncMock(), 2))[0].can_write is True

    @pytest.mark.asyncio
    async def test_a_pot_whose_group_cannot_be_named_is_dropped(self, monkeypatch):
        # The copy reads "{pot} · {group}". Unreachable — app_can_view_pot requires an active seat in
        # the pot's group, which is the same predicate app_is_group_member applies to the group row —
        # but dropping the pot keeps its rows out of the list too, since the caller filters on these ids.
        _wire_catalogue(monkeypatch, [_pot(9)], {2: [_seat(11)]}, {}, [])
        assert await pot_service.list_visible_scopes(AsyncMock(), 1) == []

    @pytest.mark.asyncio
    async def test_a_pot_the_caller_holds_no_active_seat_in_is_skipped(self, monkeypatch):
        # RLS returns only pots the user may see, so a missing seat means the policy and this service
        # disagree. Under-reporting is the fail-closed direction.
        _wire_catalogue(
            monkeypatch,
            [_pot(9)],
            {2: [_seat(11, user_id=1)]},
            {},
            [Group(id=2, name="Casa", kind=GroupKind.household)],
        )
        assert await pot_service.list_visible_scopes(AsyncMock(), 99) == []

    @pytest.mark.asyncio
    async def test_no_visible_pot_pays_for_no_further_query(self, monkeypatch):
        permissions = AsyncMock(return_value={})
        monkeypatch.setattr(pot_service.pot_repository, "list_visible", AsyncMock(return_value=[]))
        monkeypatch.setattr(pot_service.pot_repository, "list_permissions_by_pots", permissions)
        assert await pot_service.list_visible_scopes(AsyncMock(), 1) == []
        permissions.assert_not_awaited()
