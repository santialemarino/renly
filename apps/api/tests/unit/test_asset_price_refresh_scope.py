from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.investment import Investment, InvestmentCategory
from app.models.user import User
from app.repositories.investment_repository import investment_repository
from app.routers.asset_prices import refresh_prices
from app.services import asset_price_service, price_providers
from app.services.price_providers import PriceProviderInfo

# Tests for the on-demand price refresh scope (SEC-2). A user-triggered refresh
# (POST /asset-prices/refresh) must fetch prices only for the caller's own tickers, never the
# whole DB. The system-wide refresh stays reserved for the scheduler. Everything below the
# service is faked so the tests pin the scoping, not the persistence or the external providers.

USER_1 = User(id=1, email="one@test", password_hash="x", session_epoch=0)


def _inv(id: int, user_id: int, ticker: str | None, *, is_active: bool = True) -> Investment:
    return Investment(
        id=id,
        user_id=user_id,
        name=ticker or f"inv-{id}",
        category=InvestmentCategory.stocks,
        base_currency="USD",
        ticker=ticker,
        is_active=is_active,
    )


# Fake DB: user 1 owns AAPL + BTC (plus an inactive and a ticker-less position that must be
# excluded); user 2 owns MSFT + ETH.
ALL_INVESTMENTS = [
    _inv(1, user_id=1, ticker="AAPL"),
    _inv(2, user_id=1, ticker="BTC"),
    _inv(3, user_id=1, ticker="TSLA", is_active=False),
    _inv(4, user_id=1, ticker=None),
    _inv(5, user_id=2, ticker="MSFT"),
    _inv(6, user_id=2, ticker="ETH"),
]


# Mirrors the repository query: the user's active, ticker-bearing investments.
def _list_with_ticker_by_user(_session, user_id: int) -> list[Investment]:
    return [i for i in ALL_INVESTMENTS if i.user_id == user_id and i.is_active and i.ticker]


# Mirrors the system-wide repository query: every active, ticker-bearing investment.
def _list_with_ticker(_session) -> list[Investment]:
    return [i for i in ALL_INVESTMENTS if i.is_active and i.ticker]


@pytest.fixture
def wiring(monkeypatch):
    # Record which tickers the providers were asked to fetch and which were stored.
    fetched: list[str] = []
    stored: list[str] = []

    async def _fetch(ticker, _start=None, _end=None):
        fetched.append(ticker)
        return [(date(2026, 6, 1), Decimal("100"), "USD")]

    async def _bulk_upsert(_session, prices):
        stored.extend(p.ticker for p in prices)
        return len(prices)

    provider = PriceProviderInfo(source="fake", fetch=_fetch, supports_history=True)
    monkeypatch.setattr(asset_price_service, "_CATEGORY_PROVIDERS", {InvestmentCategory.stocks: provider})
    monkeypatch.setattr(asset_price_service.asset_price_repository, "bulk_upsert", _bulk_upsert)
    monkeypatch.setattr(price_providers, "clear_fci_cache", MagicMock())

    list_all = AsyncMock(side_effect=_list_with_ticker)
    list_by_user = AsyncMock(side_effect=_list_with_ticker_by_user)
    monkeypatch.setattr(investment_repository, "list_with_ticker", list_all)
    monkeypatch.setattr(investment_repository, "list_with_ticker_by_user", list_by_user)

    return {"fetched": fetched, "stored": stored, "list_all": list_all, "list_by_user": list_by_user}


class TestRefreshEndpointScope:
    @pytest.mark.asyncio
    async def test_endpoint_refreshes_only_callers_tickers(self, wiring):
        session = AsyncMock()

        result = await refresh_prices(current_user=USER_1, session=session)

        # Only user 1's active, ticker-bearing investments are fetched and stored.
        assert set(wiring["fetched"]) == {"AAPL", "BTC"}
        assert set(wiring["stored"]) == {"AAPL", "BTC"}
        # User 2's tickers are never touched.
        assert "MSFT" not in wiring["fetched"]
        assert "ETH" not in wiring["fetched"]
        assert result.prices_stored == 2
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_endpoint_scopes_the_query_to_the_caller(self, wiring):
        await refresh_prices(current_user=USER_1, session=AsyncMock())

        # The user-scoped query runs with the caller's id; the system-wide query never runs.
        wiring["list_by_user"].assert_awaited_once()
        assert wiring["list_by_user"].await_args.args[1] == USER_1.id
        wiring["list_all"].assert_not_called()


class TestSchedulerRefreshStaysSystemWide:
    @pytest.mark.asyncio
    async def test_system_wide_refresh_covers_every_users_tickers(self, wiring):
        session = AsyncMock()

        await asset_price_service.refresh_all_prices(session)

        # The scheduler path still fetches every user's tickers via the system-wide query.
        assert set(wiring["fetched"]) == {"AAPL", "BTC", "MSFT", "ETH"}
        wiring["list_all"].assert_awaited_once()
        wiring["list_by_user"].assert_not_called()
