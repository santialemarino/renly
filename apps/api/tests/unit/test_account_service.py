from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain import NotFoundError
from app.models.account import Account, AccountType
from app.models.user import User
from app.schemas.account import AccountCreate
from app.services import account_service

# The account service is straight CRUD over a derived-balance entity: get raises NotFoundError on a
# missing row, balances default to opening_balance (PR 1), and create/delete/archive commit once.
# Persistence is mocked (AsyncMock), matching the other service unit tests.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _account(**overrides) -> Account:
    data = dict(
        id=7,
        user_id=1,
        name="Caja de ahorro $",
        type=AccountType.bank,
        currency="ARS",
        opening_balance=Decimal("1500.50"),
        opening_date=date(2026, 1, 1),
        is_active=True,
    )
    data.update(overrides)
    return Account(**data)


class TestGetAccount:
    @pytest.mark.asyncio
    async def test_missing_account_raises_not_found(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await account_service.get_account(AsyncMock(), 7, USER)


class TestBalances:
    @pytest.mark.asyncio
    async def test_balance_falls_back_to_opening_when_no_links(self, monkeypatch):
        monkeypatch.setattr(account_service.income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.expense_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.pot_ownership_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.pot_ownership_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.transfer_repository, "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(account_service.income_repository, "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(account_service.expense_repository, "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(account_service.card_settlement_repository, "linked_account_ids", AsyncMock(return_value=set()))
        accounts = [_account(id=1, opening_balance=Decimal("100")), _account(id=2, opening_balance=Decimal("-40"))]
        balances = await account_service.get_account_balances(AsyncMock(), accounts, 1)
        assert balances == {1: Decimal("100"), 2: Decimal("-40")}

    @pytest.mark.asyncio
    async def test_empty_accounts_yields_empty_map(self):
        assert await account_service.get_account_balances(AsyncMock(), [], 1) == {}


class TestMutations:
    @pytest.mark.asyncio
    async def test_create_commits_and_sets_fields(self, monkeypatch):
        created: dict = {}

        async def fake_create(_session, account):
            account.id = 7
            created["account"] = account
            return account

        monkeypatch.setattr(account_service.account_repository, "create", fake_create)
        session = AsyncMock()

        account = await account_service.create_account(
            session,
            USER,
            name="Efectivo",
            type=AccountType.cash,
            currency="USD",
            opening_balance=Decimal("50"),
            opening_date=date(2026, 2, 1),
            notes=None,
        )

        assert account.name == "Efectivo"
        assert account.type == AccountType.cash
        assert account.user_id == USER.id
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_commits(self, monkeypatch):
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=_account()))
        delete_mock = AsyncMock()
        monkeypatch.setattr(account_service.account_repository, "delete", delete_mock)
        session = AsyncMock()

        await account_service.delete_account(session, 7, USER)

        delete_mock.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_archive_sets_inactive(self, monkeypatch):
        account = _account(is_active=True)
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=account))
        monkeypatch.setattr(account_service.account_repository, "save", AsyncMock())
        session = AsyncMock()

        result = await account_service.archive_account(session, 7, USER)

        assert result.is_active is False
        session.commit.assert_awaited_once()


class TestSchema:
    def test_currency_uppercased(self):
        body = AccountCreate(name="X", type="bank", currency="usd", opening_date=date(2026, 1, 1))
        assert body.currency == "USD"

    def test_unsupported_currency_rejected(self):
        with pytest.raises(ValidationError):
            AccountCreate(name="X", type="bank", currency="JPY", opening_date=date(2026, 1, 1))

    def test_opening_balance_defaults_to_zero(self):
        body = AccountCreate(name="X", type="cash", currency="ARS", opening_date=date(2026, 1, 1))
        assert body.opening_balance == Decimal(0)
