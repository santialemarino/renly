# Unit coverage for investment_service.build_response — the single-investment response assembly used by
# GET /investments/{id}, POST /investments and PUT /investments/{id}. Those three previously hardcoded an
# empty collection list in the router, so the documented `collections` field was always [] on them.

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.models.investment import Currency, Investment, InvestmentCategory
from app.models.user import User
from app.services import investment_service

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


# Builds a persisted investment with the timestamps the response schema requires.
def _investment(investment_id: int | None = 7) -> Investment:
    now = datetime(2026, 8, 21, 12, 0, 0)
    return Investment(
        id=investment_id,
        user_id=1,
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
