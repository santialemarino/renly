from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.asset_price import AssetPrice
from app.models.investment import Investment, InvestmentCategory
from app.models.snapshot import InvestmentSnapshot
from app.services import auto_snapshot_service

CATEGORY = list(InvestmentCategory)[0]


def _inv(*, inv_id: int, ticker: str, base_currency: str) -> Investment:
    return Investment(id=inv_id, user_id=1, name=ticker, category=CATEGORY, base_currency=base_currency, ticker=ticker)


def _price(*, ticker: str, price: Decimal, currency: str) -> AssetPrice:
    return AssetPrice(ticker=ticker, date=date(2026, 7, 10), price=price, currency=currency)


def _snap(*, inv_id: int, quantity: Decimal | None) -> InvestmentSnapshot:
    return InvestmentSnapshot(
        investment_id=inv_id, user_id=1, date=date(2026, 7, 1), value=Decimal("50000"), quantity=quantity, currency="USD", source="manual"
    )


class TestAutoSnapshotSkips:
    @pytest.mark.asyncio
    async def test_skips_missing_quantity_and_currency_mismatch(self, monkeypatch):
        # inv 1: quantity 10 x price 200 -> snapshot 2000 (created).
        # inv 2: latest snapshot has no quantity -> skipped (old code wrote 200 as the value).
        # inv 3: price in USD but base ARS -> skipped (no conversion attempt).
        investments = [
            _inv(inv_id=1, ticker="AAPL", base_currency="USD"),
            _inv(inv_id=2, ticker="MSFT", base_currency="USD"),
            _inv(inv_id=3, ticker="GOOG", base_currency="ARS"),
        ]
        monkeypatch.setattr(auto_snapshot_service.investment_repository, "list_with_ticker", AsyncMock(return_value=investments))
        monkeypatch.setattr(auto_snapshot_service.snapshot_repository, "get_ids_with_snapshot_on_date", AsyncMock(return_value=set()))
        monkeypatch.setattr(
            auto_snapshot_service.asset_price_repository,
            "get_latest_by_tickers",
            AsyncMock(
                return_value={
                    "AAPL": _price(ticker="AAPL", price=Decimal("200"), currency="USD"),
                    "MSFT": _price(ticker="MSFT", price=Decimal("300"), currency="USD"),
                    "GOOG": _price(ticker="GOOG", price=Decimal("150"), currency="USD"),
                }
            ),
        )
        monkeypatch.setattr(
            auto_snapshot_service.snapshot_repository,
            "get_latest_by_investments",
            AsyncMock(
                return_value={
                    1: _snap(inv_id=1, quantity=Decimal("10")),
                    2: _snap(inv_id=2, quantity=None),
                    3: _snap(inv_id=3, quantity=Decimal("5")),
                }
            ),
        )
        session = AsyncMock()
        session.add_all = Mock()
        created = await auto_snapshot_service.generate_auto_snapshots(session)
        assert created == 1
        added = session.add_all.call_args.args[0]
        assert len(added) == 1
        assert added[0].investment_id == 1
        assert added[0].value == Decimal("2000")
        assert added[0].quantity == Decimal("10")
        assert added[0].currency == "USD"

    @pytest.mark.asyncio
    async def test_zero_quantity_skipped(self, monkeypatch):
        investments = [_inv(inv_id=1, ticker="AAPL", base_currency="USD")]
        monkeypatch.setattr(auto_snapshot_service.investment_repository, "list_with_ticker", AsyncMock(return_value=investments))
        monkeypatch.setattr(auto_snapshot_service.snapshot_repository, "get_ids_with_snapshot_on_date", AsyncMock(return_value=set()))
        monkeypatch.setattr(
            auto_snapshot_service.asset_price_repository,
            "get_latest_by_tickers",
            AsyncMock(return_value={"AAPL": _price(ticker="AAPL", price=Decimal("200"), currency="USD")}),
        )
        monkeypatch.setattr(
            auto_snapshot_service.snapshot_repository,
            "get_latest_by_investments",
            AsyncMock(return_value={1: _snap(inv_id=1, quantity=Decimal("0"))}),
        )
        session = AsyncMock()
        session.add_all = Mock()
        assert await auto_snapshot_service.generate_auto_snapshots(session) == 0
        session.add_all.assert_not_called()


class TestScopeInheritance:
    @pytest.mark.asyncio
    async def test_a_co_owned_investments_snapshot_inherits_the_pots_scope(self, monkeypatch):
        # list_with_ticker is a GLOBAL query — the scheduler runs as the table owner, across every
        # user — so it picks up co-owned investments as readily as private ones. Taking user_id from
        # the parent without also taking pot_id leaves a row with NEITHER owner, which violates the
        # single-owner CHECK and fails the whole batch: one shared ticker-tracked holding would stop
        # auto-snapshots for every user in the database, not just its own group.
        shared = Investment(id=9, user_id=None, pot_id=77, name="SHRD", category=CATEGORY, base_currency="USD", ticker="SHRD")
        private = _inv(inv_id=1, ticker="AAPL", base_currency="USD")
        monkeypatch.setattr(auto_snapshot_service.investment_repository, "list_with_ticker", AsyncMock(return_value=[shared, private]))
        monkeypatch.setattr(auto_snapshot_service.snapshot_repository, "get_ids_with_snapshot_on_date", AsyncMock(return_value=set()))
        monkeypatch.setattr(
            auto_snapshot_service.asset_price_repository,
            "get_latest_by_tickers",
            AsyncMock(
                return_value={
                    "SHRD": _price(ticker="SHRD", price=Decimal("10"), currency="USD"),
                    "AAPL": _price(ticker="AAPL", price=Decimal("200"), currency="USD"),
                }
            ),
        )
        monkeypatch.setattr(
            auto_snapshot_service.snapshot_repository,
            "get_latest_by_investments",
            AsyncMock(return_value={9: _snap(inv_id=9, quantity=Decimal("3")), 1: _snap(inv_id=1, quantity=Decimal("10"))}),
        )
        session = AsyncMock()
        session.add_all = Mock()
        await auto_snapshot_service.generate_auto_snapshots(session)

        written = {s.investment_id: s for s in session.add_all.call_args.args[0]}
        assert (written[9].user_id, written[9].pot_id) == (None, 77)
        assert (written[1].user_id, written[1].pot_id) == (1, None)
        # Every row satisfies the single-owner CHECK the database will apply.
        assert all((s.user_id is None) != (s.pot_id is None) for s in written.values())
