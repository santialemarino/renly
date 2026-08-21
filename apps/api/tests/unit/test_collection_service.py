# Unit coverage for the investment-collection service: the six CRUD flows, the cross-user ownership
# guard on membership writes, and the batch-load that keeps list_collections off an N+1.

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import NotFoundError
from app.models.investment import Investment
from app.models.investment_collection import InvestmentCollection
from app.models.user import User
from app.services import collection_service

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)
OTHER = User(id=2, email="other@test", password_hash="x", session_epoch=0)


# Builds a collection owned by USER.
def _collection(collection_id: int = 10, name: str = "Retirement") -> InvestmentCollection:
    return InvestmentCollection(id=collection_id, user_id=USER.id, name=name, target_percentage=Decimal("40.00"))


# Points the collection repository at the given return values; unset methods stay AsyncMock() no-ops.
def _patch_repo(monkeypatch, **methods):
    for name in (
        "create",
        "delete",
        "get_by_id",
        "get_investment_ids_by_collection",
        "get_investment_ids_by_collections",
        "list_by_user",
        "save",
        "set_members",
    ):
        monkeypatch.setattr(collection_service.collection_repository, name, methods.get(name, AsyncMock()))


class TestListCollections:
    @pytest.mark.asyncio
    async def test_returns_each_collection_with_its_investment_ids(self, monkeypatch):
        a, b = _collection(10, "Retirement"), _collection(11, "Trading")
        _patch_repo(
            monkeypatch,
            list_by_user=AsyncMock(return_value=[a, b]),
            get_investment_ids_by_collections=AsyncMock(return_value={10: [5, 6], 11: [7]}),
        )
        pairs = await collection_service.list_collections(AsyncMock(), USER)
        assert pairs == [(a, [5, 6]), (b, [7])]

    @pytest.mark.asyncio
    async def test_membership_is_one_batch_query_not_one_per_collection(self, monkeypatch):
        batch = AsyncMock(return_value={})
        per_one = AsyncMock(return_value=[])
        _patch_repo(
            monkeypatch,
            list_by_user=AsyncMock(return_value=[_collection(10), _collection(11), _collection(12)]),
            get_investment_ids_by_collections=batch,
            get_investment_ids_by_collection=per_one,
        )
        await collection_service.list_collections(AsyncMock(), USER)
        # One batch call carrying all three ids, and the single-id variant never used in the loop.
        assert batch.await_count == 1
        assert batch.await_args.args[1] == [10, 11, 12]
        per_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_collection_with_no_members_gets_an_empty_list(self, monkeypatch):
        solo = _collection(10)
        _patch_repo(
            monkeypatch,
            list_by_user=AsyncMock(return_value=[solo]),
            get_investment_ids_by_collections=AsyncMock(return_value={}),
        )
        assert await collection_service.list_collections(AsyncMock(), USER) == [(solo, [])]


class TestGetCollection:
    @pytest.mark.asyncio
    async def test_returns_the_collection_and_its_members(self, monkeypatch):
        found = _collection()
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=found),
            get_investment_ids_by_collection=AsyncMock(return_value=[5, 6]),
        )
        assert await collection_service.get_collection(AsyncMock(), 10, USER) == (found, [5, 6])

    @pytest.mark.asyncio
    async def test_another_users_collection_is_not_found(self, monkeypatch):
        # The repository scopes by user_id, so a foreign id comes back as None.
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await collection_service.get_collection(AsyncMock(), 10, OTHER)


class TestCreateCollection:
    @pytest.mark.asyncio
    async def test_persists_with_the_callers_user_id_and_commits_once(self, monkeypatch):
        created = {}

        async def _create(session, collection):
            created["value"] = collection
            return collection

        _patch_repo(monkeypatch, create=AsyncMock(side_effect=_create))
        session = AsyncMock()
        result = await collection_service.create_collection(session, USER, "Kids", target_percentage=Decimal("15.00"))
        assert result.user_id == USER.id
        assert result.name == "Kids"
        assert result.target_percentage == Decimal("15.00")
        session.commit.assert_awaited_once()


class TestUpdateCollection:
    @pytest.mark.asyncio
    async def test_updates_name_and_target_then_returns_members(self, monkeypatch):
        existing = _collection(name="Old")
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=existing),
            get_investment_ids_by_collection=AsyncMock(return_value=[5]),
        )
        session = AsyncMock()
        collection, ids = await collection_service.update_collection(session, 10, USER, name="New", target_percentage=Decimal("25.00"))
        assert (collection.name, collection.target_percentage, ids) == ("New", Decimal("25.00"), [5])
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_omitting_name_keeps_it_while_omitting_target_clears_it(self, monkeypatch):
        # target_percentage is unconditionally assigned, so a partial update without it means "clear".
        existing = _collection(name="Keep")
        _patch_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=existing),
            get_investment_ids_by_collection=AsyncMock(return_value=[]),
        )
        collection, _ = await collection_service.update_collection(AsyncMock(), 10, USER)
        assert collection.name == "Keep"
        assert collection.target_percentage is None

    @pytest.mark.asyncio
    async def test_missing_collection_raises_before_any_write(self, monkeypatch):
        save = AsyncMock()
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=None), save=save)
        session = AsyncMock()
        with pytest.raises(NotFoundError):
            await collection_service.update_collection(AsyncMock(), 10, USER, name="New")
        save.assert_not_awaited()
        session.commit.assert_not_awaited()


class TestDeleteCollection:
    @pytest.mark.asyncio
    async def test_deletes_and_commits(self, monkeypatch):
        delete = AsyncMock()
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=_collection()), delete=delete)
        session = AsyncMock()
        await collection_service.delete_collection(session, 10, USER)
        delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_collection_raises_before_deleting(self, monkeypatch):
        delete = AsyncMock()
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=None), delete=delete)
        with pytest.raises(NotFoundError):
            await collection_service.delete_collection(AsyncMock(), 10, USER)
        delete.assert_not_awaited()


class TestSetCollectionInvestments:
    @pytest.mark.asyncio
    async def test_replaces_membership_with_the_given_ids(self, monkeypatch):
        set_members = AsyncMock()
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=_collection()), set_members=set_members)
        monkeypatch.setattr(
            collection_service.investment_repository,
            "get_by_ids",
            AsyncMock(return_value=[Investment(id=5, user_id=1, name="A", category="stocks", base_currency="USD")]),
        )
        session = AsyncMock()
        await collection_service.set_collection_investments(session, 10, USER, [5])
        assert set_members.await_count == 1
        assert set_members.await_args.args[1:] == (10, [5])
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    # The ownership guard: get_by_ids is user-scoped, so a foreign id simply does not come back.
    async def test_an_investment_the_caller_does_not_own_is_rejected_and_nothing_is_written(self, monkeypatch):
        set_members = AsyncMock()
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=_collection()), set_members=set_members)
        # Asked for 5 and 99; only 5 belongs to the caller.
        monkeypatch.setattr(
            collection_service.investment_repository,
            "get_by_ids",
            AsyncMock(return_value=[Investment(id=5, user_id=1, name="A", category="stocks", base_currency="USD")]),
        )
        session = AsyncMock()
        with pytest.raises(NotFoundError) as exc:
            await collection_service.set_collection_investments(session, 10, USER, [5, 99])
        assert "99" in str(exc.value)
        set_members.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_empty_list_clears_membership_without_an_ownership_query(self, monkeypatch):
        set_members = AsyncMock()
        get_by_ids = AsyncMock(return_value=[])
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=_collection()), set_members=set_members)
        monkeypatch.setattr(collection_service.investment_repository, "get_by_ids", get_by_ids)
        await collection_service.set_collection_investments(AsyncMock(), 10, USER, [])
        get_by_ids.assert_not_awaited()
        set_members.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_collection_the_caller_does_not_own_is_not_found(self, monkeypatch):
        set_members = AsyncMock()
        _patch_repo(monkeypatch, get_by_id=AsyncMock(return_value=None), set_members=set_members)
        with pytest.raises(NotFoundError):
            await collection_service.set_collection_investments(AsyncMock(), 10, OTHER, [5])
        set_members.assert_not_awaited()
