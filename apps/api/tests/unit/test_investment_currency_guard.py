from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import InvestmentCurrencyMismatchError
from app.models.investment import Currency, Investment
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services import investment_service

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


# Builds an owned ARS-based investment returned by the mocked repository.
def _ars_investment() -> Investment:
    return Investment(id=1, user_id=1, name="Bonos", category="government_bonds", base_currency=Currency.ARS)


class TestSnapshotCurrencyGuard:
    @pytest.mark.asyncio
    async def test_mismatched_currency_raises_before_write(self, monkeypatch):
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id", AsyncMock(return_value=_ars_investment()))
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=_ars_investment()))
        create_mock = AsyncMock()
        monkeypatch.setattr(investment_service.snapshot_repository, "get_by_investment_and_date", AsyncMock(return_value=None))
        monkeypatch.setattr(investment_service.snapshot_repository, "create", create_mock)
        with pytest.raises(InvestmentCurrencyMismatchError):
            await investment_service.upsert_snapshot(
                AsyncMock(), 1, USER, snapshot_date=date(2026, 1, 31), value=Decimal("100.00"), currency=Currency.USD
            )
        create_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_matching_currency_passes(self, monkeypatch):
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id", AsyncMock(return_value=_ars_investment()))
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=_ars_investment()))
        monkeypatch.setattr(investment_service.snapshot_repository, "get_by_investment_and_date", AsyncMock(return_value=None))
        create_mock = AsyncMock(side_effect=lambda session, snapshot: snapshot)
        monkeypatch.setattr(investment_service.snapshot_repository, "create", create_mock)
        await investment_service.upsert_snapshot(
            AsyncMock(), 1, USER, snapshot_date=date(2026, 1, 31), value=Decimal("100.00"), currency=Currency.ARS
        )
        create_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_newly_supported_currency_passes(self, monkeypatch):
        # A BRL investment + BRL snapshot must clear the guard now that the Currency enum covers the full set.
        brl_investment = Investment(id=1, user_id=1, name="ETF", category="stocks", base_currency=Currency.BRL)
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id", AsyncMock(return_value=brl_investment))
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=brl_investment))
        monkeypatch.setattr(investment_service.snapshot_repository, "get_by_investment_and_date", AsyncMock(return_value=None))
        create_mock = AsyncMock(side_effect=lambda session, snapshot: snapshot)
        monkeypatch.setattr(investment_service.snapshot_repository, "create", create_mock)
        snapshot = await investment_service.upsert_snapshot(
            AsyncMock(), 1, USER, snapshot_date=date(2026, 1, 31), value=Decimal("100.00"), currency=Currency.BRL
        )
        create_mock.assert_awaited_once()
        assert snapshot.currency == Currency.BRL


class TestTransactionCurrencyGuard:
    @pytest.mark.asyncio
    async def test_create_mismatch_raises_before_write(self, monkeypatch):
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id", AsyncMock(return_value=_ars_investment()))
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=_ars_investment()))
        create_mock = AsyncMock()
        monkeypatch.setattr(investment_service.transaction_repository, "create", create_mock)
        with pytest.raises(InvestmentCurrencyMismatchError):
            await investment_service.create_transaction(
                AsyncMock(),
                1,
                USER,
                transaction_date=date(2026, 1, 5),
                amount=Decimal("100.00"),
                currency=Currency.USD,
                tx_type=TransactionType.buy,
            )
        create_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_currency_change_mismatch_raises(self, monkeypatch):
        existing_tx = Transaction(
            id=9, investment_id=1, user_id=1, date=date(2026, 1, 5), amount=Decimal("100.00"), currency=Currency.ARS, type=TransactionType.buy
        )
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id", AsyncMock(return_value=_ars_investment()))
        monkeypatch.setattr(investment_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=_ars_investment()))
        monkeypatch.setattr(investment_service.transaction_repository, "get_by_id", AsyncMock(return_value=existing_tx))
        save_mock = AsyncMock()
        monkeypatch.setattr(investment_service.transaction_repository, "save", save_mock)
        with pytest.raises(InvestmentCurrencyMismatchError):
            await investment_service.update_transaction(AsyncMock(), 1, 9, USER, currency=Currency.USD)
        save_mock.assert_not_awaited()
