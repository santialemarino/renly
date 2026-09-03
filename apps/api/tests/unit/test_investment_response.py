# Unit coverage for investment_service.build_response — the single-investment response assembly used by
# GET /investments/{id}, POST /investments and PUT /investments/{id}. Those three previously hardcoded an
# empty collection list in the router, so the documented `collections` field was always [] on them.

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.domain.list_scope import SCOPE_PRIVATE, SCOPE_SHARED, ListScope
from app.models.investment import Currency, Investment, InvestmentCategory
from app.models.pot import PotCadence
from app.models.user import User
from app.services import investment_service

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


# Builds a persisted investment with the timestamps the response schema requires.
def _investment(investment_id: int | None = 7, *, pot_id: int | None = None) -> Investment:
    now = datetime(2026, 8, 21, 12, 0, 0)
    return Investment(
        id=investment_id,
        # A pot-owned holding has user_id NULL and pot_id set — the single-owner CHECK admits exactly
        # one of them, which is what makes `user_id = me` still mean "my private assets" (§3).
        user_id=None if pot_id is not None else 1,
        pot_id=pot_id,
        name="Google",
        category=InvestmentCategory.stocks,
        base_currency=Currency.USD,
        created_at=now,
        updated_at=now,
    )


class TestBuildResponse:
    @pytest.mark.asyncio
    async def test_returns_the_investments_real_collection_membership(self, monkeypatch):
        monkeypatch.setattr(
            investment_service.investment_repository,
            "get_collections_by_investment_ids",
            AsyncMock(return_value={7: [(37, "Tech"), (38, "Hola")]}),
        )
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value=set()))
        response = await investment_service.build_response(AsyncMock(), _investment())
        assert [(c.id, c.name) for c in response.collections] == [(37, "Tech"), (38, "Hola")]

    @pytest.mark.asyncio
    async def test_an_investment_in_no_collection_gets_an_empty_list(self, monkeypatch):
        monkeypatch.setattr(
            investment_service.investment_repository,
            "get_collections_by_investment_ids",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value=set()))
        response = await investment_service.build_response(AsyncMock(), _investment())
        assert response.collections == []

    @pytest.mark.asyncio
    async def test_has_snapshots_reflects_the_snapshot_lookup(self, monkeypatch):
        monkeypatch.setattr(
            investment_service.investment_repository,
            "get_collections_by_investment_ids",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value={7}))
        assert (await investment_service.build_response(AsyncMock(), _investment())).has_snapshots is True

        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value=set()))
        assert (await investment_service.build_response(AsyncMock(), _investment())).has_snapshots is False

    @pytest.mark.asyncio
    async def test_membership_is_looked_up_for_this_investment_only(self, monkeypatch):
        lookup = AsyncMock(return_value={})
        monkeypatch.setattr(investment_service.investment_repository, "get_collections_by_investment_ids", lookup)
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value=set()))
        await investment_service.build_response(AsyncMock(), _investment(7))
        assert lookup.await_count == 1
        assert lookup.await_args.args[1] == [7]

    @pytest.mark.asyncio
    # A model with id None must not be looked up as id 0, which could match another row.
    async def test_an_unpersisted_investment_queries_no_ids_rather_than_id_zero(self, monkeypatch):
        lookup = AsyncMock(return_value={})
        snapshots = AsyncMock(return_value=set())
        monkeypatch.setattr(investment_service.investment_repository, "get_collections_by_investment_ids", lookup)
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", snapshots)
        response = await investment_service.build_response(AsyncMock(), _investment(None))
        assert lookup.await_args.args[1] == []
        assert snapshots.await_args.args[1] == []
        assert response.collections == []


class TestListResponseCarriesCollections:
    # The list path is the one the web consumes; it must stay wired to the shared enrichment load.
    @pytest.mark.asyncio
    async def test_each_listed_investment_carries_its_own_collections(self, monkeypatch):
        a, b = _investment(7), _investment(8)
        monkeypatch.setattr(
            investment_service.investment_repository,
            "list_by_user_filtered",
            AsyncMock(return_value=([a, b], 2)),
        )
        monkeypatch.setattr(
            investment_service.investment_repository,
            "get_collections_by_investment_ids",
            AsyncMock(return_value={7: [(37, "Tech")], 8: [(38, "Hola")]}),
        )
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value={8}))
        result = await investment_service.list_investments(AsyncMock(), USER)
        assert [(i.id, [(c.id, c.name) for c in i.collections]) for i in result.items] == [
            (7, [(37, "Tech")]),
            (8, [(38, "Hola")]),
        ]
        assert [i.has_snapshots for i in result.items] == [False, True]

    @pytest.mark.asyncio
    async def test_membership_is_loaded_once_for_the_whole_page_not_per_row(self, monkeypatch):
        lookup = AsyncMock(return_value={})
        monkeypatch.setattr(
            investment_service.investment_repository,
            "list_by_user_filtered",
            AsyncMock(return_value=([_investment(7), _investment(8), _investment(9)], 3)),
        )
        monkeypatch.setattr(investment_service.investment_repository, "get_collections_by_investment_ids", lookup)
        monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value=set()))
        await investment_service.list_investments(AsyncMock(), USER)
        assert lookup.await_count == 1
        assert lookup.await_args.args[1] == [7, 8, 9]


# X2 on /investments: the list stops being private-only, the rows come back grouped by the pot that owns
# them, and each section says what it is called and how many rows it holds.
#
# A section total here is a COUNT and nothing else, because this list has no value column at all — a
# header stating a figure the visible rows cannot add up to is the thing X2 exists to avoid.
class TestScopeGrouping:
    @pytest.mark.asyncio
    async def test_a_row_says_which_scope_it_is_in_and_which_pot_owns_it(self, monkeypatch):
        # The row carries the pot ID only; the LABEL lives on the section, stated once, because write
        # access is per (pot, member) and a label repeated per row is a label that can drift.
        _wire(monkeypatch, [_investment(7), _investment(8, pot_id=4)])
        items = (await investment_service.list_investments(AsyncMock(), USER, scope=ListScope.all)).items
        assert [(i.scope, i.pot_id) for i in items] == [(SCOPE_PRIVATE, None), (SCOPE_SHARED, 4)]

    @pytest.mark.asyncio
    async def test_the_visible_pots_bound_the_query_and_label_the_sections(self, monkeypatch):
        # ONE catalogue does both, so a row can never arrive under a header that was never drawn.
        rows = _wire(
            monkeypatch,
            [_investment(8, pot_id=4)],
            scopes=[
                investment_service.pot_service.PotScope(
                    pot_id=4, name=None, group_id=2, group_name="Casa", can_write=True, cadence=PotCadence.monthly
                )
            ],
            counts=[(4, None, None, 3), (None, None, None, 1)],
        )
        result = await investment_service.list_investments(AsyncMock(), USER, scope=ListScope.all)
        assert rows.await_args.args[2] == [4]
        assert [(s.scope, s.pot_id, s.pot_name, s.group_name, s.can_write, s.count, s.totals) for s in result.sections] == [
            (SCOPE_PRIVATE, None, None, None, True, 1, []),
            (SCOPE_SHARED, 4, None, "Casa", True, 3, []),
        ]

    @pytest.mark.asyncio
    async def test_the_section_counts_span_every_page_not_the_one_returned(self, monkeypatch):
        # A header figure that changed as the reader paged would answer a question nobody asked, so the
        # aggregate runs over the whole filtered set. One row on the page, three in its section.
        _wire(
            monkeypatch,
            [_investment(8, pot_id=4)],
            scopes=[
                investment_service.pot_service.PotScope(
                    pot_id=4, name="Viaje", group_id=2, group_name="Casa", can_write=False, cadence=PotCadence.monthly
                )
            ],
            counts=[(4, None, None, 3)],
        )
        result = await investment_service.list_investments(AsyncMock(), USER, scope=ListScope.all)
        assert (len(result.items), result.sections[0].count) == (1, 3)

    @pytest.mark.asyncio
    async def test_a_caller_who_can_see_no_pot_gets_no_sections_at_all(self, monkeypatch):
        # Every user at launch. An empty `sections` is what tells the page to draw the flat table it
        # always drew, and no aggregate is issued for it either.
        _wire(monkeypatch, [_investment(7)])
        result = await investment_service.list_investments(AsyncMock(), USER, scope=ListScope.all)
        assert result.sections == []
        investment_service.investment_repository.count_by_scope.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_private_only_read_resolves_no_catalogue_and_issues_no_aggregate(self, monkeypatch):
        # The default, and the path four other pages take as a PICKER of the caller's own holdings.
        # It must cost exactly what it cost before X2: a list with no pot rows has one section whose
        # count IS the total already returned.
        _wire(monkeypatch, [_investment(7)])
        result = await investment_service.list_investments(AsyncMock(), USER)
        investment_service.pot_service.list_visible_scopes.assert_not_awaited()
        investment_service.investment_repository.count_by_scope.assert_not_awaited()
        assert result.sections == []


# Wires the four reads list_investments makes. `scopes` empty is a user who can see no pot, in which
# case the service must not reach for the aggregate at all.
def _wire(monkeypatch, investments: list[Investment], *, scopes=None, counts=None) -> AsyncMock:
    rows = AsyncMock(return_value=(investments, len(investments)))
    monkeypatch.setattr(investment_service.investment_repository, "list_by_user_filtered", rows)
    monkeypatch.setattr(investment_service.investment_repository, "count_by_scope", AsyncMock(return_value=counts or []))
    monkeypatch.setattr(investment_service.pot_service, "list_visible_scopes", AsyncMock(return_value=scopes or []))
    monkeypatch.setattr(investment_service.investment_repository, "get_collections_by_investment_ids", AsyncMock(return_value={}))
    monkeypatch.setattr(investment_service.snapshot_repository, "get_ids_with_snapshots", AsyncMock(return_value=set()))
    return rows
