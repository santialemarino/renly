# The dashboard's pot reads cost one read per SOURCE, never one per pot (U17).
#
# The statement count itself is pinned against a real database by
# tests/integration/test_pot_fanout_query_count.py, which also holds every batch read to the per-pot
# read it replaces. That suite needs a Postgres and is skipped without one, so this file is the half
# that runs everywhere: at twenty pots, every read under the headline and the evolution chart is
# awaited ONCE, and the per-pot reads are not awaited at all.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.account import Account, AccountType
from app.models.group import GroupMember, GroupMemberRole
from app.models.investment import Investment, InvestmentCategory
from app.models.pot import Pot, PotVisibility
from app.models.snapshot import InvestmentSnapshot
from app.services import pot_service, shared_worth_service
from app.utils.metrics import RateLookup

POTS = 20
AS_OF = date(2026, 6, 30)
_LOOKUP = RateLookup(dollar_preference=None, rates_by_pair={})


def _seats() -> list[pot_service.PotSeat]:
    return [
        pot_service.PotSeat(
            pot=Pot(id=pot_id, group_id=10, name=None, base_currency="USD", visibility=PotVisibility.members, is_default=False),
            member_id=100,
            events=[],
        )
        for pot_id in range(1, POTS + 1)
    ]


# Every pot holds one investment and one account, so every conditional read (the snapshots, the
# balance union) is reached and a per-pot one would be awaited twenty times.
def _wire(monkeypatch) -> dict[str, AsyncMock]:
    investments = {
        pot_id: [Investment(id=pot_id, pot_id=pot_id, name="I", category=InvestmentCategory.fci, base_currency="USD")]
        for pot_id in range(1, POTS + 1)
    }
    accounts = {
        pot_id: [
            Account(
                id=1000 + pot_id,
                pot_id=pot_id,
                name="A",
                type=AccountType.bank,
                currency="USD",
                opening_balance=Decimal("10"),
                opening_date=date(2026, 1, 1),
            )
        ]
        for pot_id in range(1, POTS + 1)
    }
    snapshot = {
        pot_id: InvestmentSnapshot(investment_id=pot_id, date=date(2026, 1, 15), value=Decimal("100"), currency="USD") for pot_id in investments
    }
    mocks = {
        "list_active_investments_by_pots": AsyncMock(return_value=investments),
        "list_accounts_by_pots": AsyncMock(return_value=accounts),
        "list_active_investments": AsyncMock(),
        "list_accounts": AsyncMock(),
        "get_latest_by_investments": AsyncMock(return_value=snapshot),
        "list_by_investments": AsyncMock(return_value=list(snapshot.values())),
        "compute_account_balances_at": AsyncMock(return_value={1000 + pot_id: Decimal("10") for pot_id in investments}),
        "compute_account_balance_series": AsyncMock(return_value={1000 + pot_id: [Decimal("10")] for pot_id in investments}),
    }
    for name in ("list_active_investments_by_pots", "list_accounts_by_pots", "list_active_investments", "list_accounts"):
        monkeypatch.setattr(pot_service.pot_repository, name, mocks[name])
    for name in ("get_latest_by_investments", "list_by_investments"):
        monkeypatch.setattr(pot_service.snapshot_repository, name, mocks[name])
    for name in ("compute_account_balances_at", "compute_account_balance_series"):
        monkeypatch.setattr(pot_service.account_service, name, mocks[name])
    return mocks


class TestTheHeadlineReadsEveryPotOnce:
    @pytest.mark.asyncio
    async def test_each_source_is_read_once_for_twenty_pots(self, monkeypatch):
        mocks = _wire(monkeypatch)
        shares = await pot_service.get_member_shares(AsyncMock(), _seats(), as_of_date=AS_OF, lookup=_LOOKUP)
        assert [share.nav for share in shares] == [Decimal("110")] * POTS
        for name in ("list_active_investments_by_pots", "list_accounts_by_pots", "get_latest_by_investments", "compute_account_balances_at"):
            assert mocks[name].await_count == 1, name
        mocks["list_active_investments"].assert_not_awaited()
        mocks["list_accounts"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_shared_worth_asks_for_every_pot_in_one_call(self, monkeypatch):
        mocks = _wire(monkeypatch)
        single = AsyncMock()
        monkeypatch.setattr(pot_service, "get_member_share", single)
        context = shared_worth_service.SharedContext(
            seats=[GroupMember(id=100, group_id=10, user_id=1, display_name="Santi", role=GroupMemberRole.member)], pots=_seats(), positions=[]
        )
        await shared_worth_service.get_shared_worth(AsyncMock(), 1, context, currency="USD", lookup=_LOOKUP, as_of_date=AS_OF)
        single.assert_not_awaited()
        assert mocks["compute_account_balances_at"].await_count == 1


class TestTheEvolutionReadsEveryPotOnce:
    @pytest.mark.asyncio
    async def test_each_source_is_read_once_for_twenty_pots(self, monkeypatch):
        mocks = _wire(monkeypatch)
        series = await pot_service.compute_share_series_many(AsyncMock(), _seats(), dates=[AS_OF], lookup=_LOOKUP)
        assert [points[0].nav for points in series] == [Decimal("110")] * POTS
        for name in ("list_active_investments_by_pots", "list_accounts_by_pots", "list_by_investments", "compute_account_balance_series"):
            assert mocks[name].await_count == 1, name
        mocks["list_active_investments"].assert_not_awaited()
        mocks["list_accounts"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_shared_series_asks_for_every_pot_in_one_call(self, monkeypatch):
        mocks = _wire(monkeypatch)
        single = AsyncMock()
        monkeypatch.setattr(pot_service, "compute_share_series", single)
        context = shared_worth_service.SharedContext(seats=[], pots=_seats(), positions=[])
        await shared_worth_service.get_shared_series(AsyncMock(), 1, context, months=[(2026, 6)], month_ends=[AS_OF], currency="USD", lookup=_LOOKUP)
        single.assert_not_awaited()
        assert mocks["compute_account_balance_series"].await_count == 1
