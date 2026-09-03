from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain import NotFoundError
from app.domain.list_scope import SCOPE_PRIVATE, SCOPE_SHARED, ListScope
from app.models.account import Account, AccountType
from app.models.pot import PotCadence
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
        monkeypatch.setattr(account_service.shared_expense_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.shared_income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.group_settlement_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.group_settlement_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))
        for repo in ("transfer_repository", "income_repository", "expense_repository", "card_settlement_repository"):
            monkeypatch.setattr(getattr(account_service, repo), "linked_account_ids", AsyncMock(return_value=set()))
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
        monkeypatch.setattr(account_service.group_settlement_repository, "clear_account_amounts", AsyncMock())
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


# X2 on /accounts: the list stops being private-only, the rows come back grouped by the pot that owns
# them, and each section totals its rows' BALANCES per currency.
#
# The totals are folded from the rows rather than from an aggregate query, and that is not a shortcut:
# this list is unpaginated, so the response already IS the whole filtered set, and each balance is
# DERIVED from eleven movement sources rather than stored — an aggregate would have to re-derive all of
# them to restate a figure already in hand.
class TestListAccountsGrouped:
    @pytest.mark.asyncio
    async def test_a_row_says_which_scope_it_is_in_and_which_pot_owns_it(self, monkeypatch):
        _wire(monkeypatch, [_account(id=7), _account(id=8, user_id=None, pot_id=4)])
        items = (await account_service.list_accounts_grouped(AsyncMock(), USER, scope=ListScope.all)).items
        assert [(i.scope, i.pot_id) for i in items] == [(SCOPE_PRIVATE, None), (SCOPE_SHARED, 4)]

    @pytest.mark.asyncio
    async def test_each_section_totals_its_own_rows_balances_per_currency(self, monkeypatch):
        # Two currencies inside ONE section, so a fixture with a single bucket per section could not
        # tell a per-currency total from a blended one. Currencies never net, exactly as the group hub's
        # balances do not.
        _wire(
            monkeypatch,
            [
                _account(id=8, user_id=None, pot_id=4, currency="ARS"),
                _account(id=9, user_id=None, pot_id=4, currency="USD"),
                _account(id=7),
            ],
            balances={8: Decimal("3000.00"), 9: Decimal("400.00"), 7: Decimal("120.00")},
            scopes=[
                account_service.pot_service.PotScope(pot_id=4, name=None, group_id=2, group_name="Casa", can_write=True, cadence=PotCadence.monthly)
            ],
        )
        sections = (await account_service.list_accounts_grouped(AsyncMock(), USER, scope=ListScope.all)).sections
        assert [(s.scope, s.pot_id, s.group_name, s.can_write, s.count) for s in sections] == [
            (SCOPE_PRIVATE, None, None, True, 1),
            (SCOPE_SHARED, 4, "Casa", True, 2),
        ]
        assert [(t.currency, t.amount) for t in sections[0].totals] == [("ARS", Decimal("120.00"))]
        assert [(t.currency, t.amount) for t in sections[1].totals] == [("ARS", Decimal("3000.00")), ("USD", Decimal("400.00"))]

    @pytest.mark.asyncio
    async def test_the_total_is_the_derived_balance_and_not_the_opening_figure(self, monkeypatch):
        # The opening figure and the derived balance are the same number on an account nothing has
        # moved, so a fixture where they agree could not tell which one the header is summing.
        _wire(
            monkeypatch,
            [_account(id=7, opening_balance=Decimal("1500.50"))],
            balances={7: Decimal("42.00")},
            scopes=[
                account_service.pot_service.PotScope(pot_id=4, name=None, group_id=2, group_name="Casa", can_write=True, cadence=PotCadence.monthly)
            ],
        )
        sections = (await account_service.list_accounts_grouped(AsyncMock(), USER, scope=ListScope.all)).sections
        assert sections[0].totals[0].amount == Decimal("42.00")

    @pytest.mark.asyncio
    async def test_a_caller_who_can_see_no_pot_gets_no_sections_at_all(self, monkeypatch):
        # Every user at launch. An empty `sections` is what tells the page to draw the flat table it
        # always drew, so a solo user's accounts page is unchanged by X2.
        _wire(monkeypatch, [_account(id=7)])
        assert (await account_service.list_accounts_grouped(AsyncMock(), USER, scope=ListScope.all)).sections == []

    @pytest.mark.asyncio
    async def test_a_private_only_read_resolves_no_catalogue(self, monkeypatch):
        # The default, and the path seven other pages take as a picker of the caller's own accounts.
        _wire(monkeypatch, [_account(id=7)])
        await account_service.list_accounts_grouped(AsyncMock(), USER)
        account_service.pot_service.list_visible_scopes.assert_not_awaited()


# Wires the four reads list_accounts_grouped makes.
def _wire(monkeypatch, accounts: list[Account], *, balances=None, scopes=None) -> None:
    monkeypatch.setattr(account_service.account_repository, "list_by_user", AsyncMock(return_value=accounts))
    resolved = balances if balances is not None else {a.id: a.opening_balance for a in accounts}
    monkeypatch.setattr(account_service, "get_account_summaries", AsyncMock(return_value=(resolved, set())))
    monkeypatch.setattr(account_service.account_reconciliation_repository, "get_latest_dates_by_account_ids", AsyncMock(return_value={}))
    monkeypatch.setattr(account_service.pot_service, "list_visible_scopes", AsyncMock(return_value=scopes or []))
