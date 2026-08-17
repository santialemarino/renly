from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from app.domain import (
    SettlementAccountAmountRequiredError,
    SettlementAccountAmountWithoutAccountError,
    SettlementAmountsMustMatchError,
)
from app.models.account import Account, AccountType
from app.models.user import User
from app.repositories import card_settlement_repository
from app.services import account_service, credit_card_service

# Cross-currency card settlement (B4): paying a USD bucket with pesos. The settlement clears the bucket
# in the CARD's currency (the bank converted internally) while its cash leg draws the real blended local
# amount from the funding account. Both amounts are recorded and the pair IS the rate — there is
# deliberately no stored rate, the same conclusion transfers reached.
#
# The whole correctness surface is which leg each sum reads: three sums are cash-side and must read
# coalesce(account_amount, amount), four are card-side and must NOT. Unit tests mock repositories, so the
# SQL assertions below are what pins that split; test_account_ledger_drift.py proves it against a real DB.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _account(**overrides) -> Account:
    data = dict(
        id=7,
        user_id=1,
        name="Caja de ahorro $",
        type=AccountType.bank,
        currency="ARS",
        opening_balance=Decimal("500000"),
        opening_date=date(2026, 1, 1),
    )
    data.update(overrides)
    return Account(**data)


# Drives create_settlement with persistence mocked, returning the CardSettlement row it built.
async def _create(monkeypatch, *, account: Account | None, amount: Decimal, currency: str, account_amount: Decimal | None):
    monkeypatch.setattr(credit_card_service, "get_card", AsyncMock())
    monkeypatch.setattr(credit_card_service.account_service, "load_linked_account", AsyncMock(return_value=account))
    monkeypatch.setattr(credit_card_service.card_reconciliation_service, "mark_stale_for_date", AsyncMock())
    created = {}

    async def capture(_session, row):
        created["row"] = row
        return row.model_copy(update={"id": 9})

    monkeypatch.setattr(credit_card_service.card_settlement_repository, "create", capture)
    response = await credit_card_service.create_settlement(
        AsyncMock(),
        5,
        USER,
        date=date(2026, 8, 17),
        amount=amount,
        currency=currency,
        account_id=account.id if account is not None else None,
        account_amount=account_amount,
    )
    return created["row"], response


class TestTheCashLegIsRecorded:
    @pytest.mark.asyncio
    async def test_paying_a_usd_bucket_from_a_peso_account_stores_both_amounts(self, monkeypatch):
        row, response = await _create(
            monkeypatch,
            account=_account(currency="ARS"),
            amount=Decimal("100.00"),
            currency="USD",
            account_amount=Decimal("130000.00"),
        )

        # The bucket is cleared in USD; the account is debited in ARS. Neither figure is derived from
        # the other, and no rate is stored — the pair is the record.
        assert (row.amount, row.currency) == (Decimal("100.00"), "USD")
        assert row.account_amount == Decimal("130000.00")
        assert (response.account_currency, response.account_amount) == ("ARS", Decimal("130000.00"))

    @pytest.mark.asyncio
    async def test_a_same_currency_settlement_stores_no_cash_amount(self, monkeypatch):
        # Normalized to NULL rather than storing the same number twice, so "account_amount IS NOT NULL"
        # always means "these two currencies differ" for every reader.
        row, response = await _create(
            monkeypatch,
            account=_account(currency="ARS"),
            amount=Decimal("700.00"),
            currency="ARS",
            account_amount=None,
        )

        assert row.account_amount is None
        assert response.account_amount is None

    @pytest.mark.asyncio
    async def test_a_redundant_but_equal_cash_amount_normalizes_to_null(self, monkeypatch):
        row, _ = await _create(
            monkeypatch,
            account=_account(currency="ARS"),
            amount=Decimal("700.00"),
            currency="ARS",
            account_amount=Decimal("700.00"),
        )

        assert row.account_amount is None

    @pytest.mark.asyncio
    async def test_an_unlinked_settlement_stores_no_cash_amount(self, monkeypatch):
        row, response = await _create(monkeypatch, account=None, amount=Decimal("700.00"), currency="ARS", account_amount=None)

        assert (row.account_id, row.account_amount) == (None, None)
        assert (response.account_name, response.account_currency) == (None, None)


class TestTheThreeRefusals:
    @pytest.mark.asyncio
    async def test_crossing_currencies_without_the_cash_amount_is_refused(self, monkeypatch):
        # Only the user knows the blended rate the bank charged, so inventing one would misstate the
        # cash balance — the same reasoning as TransferAmountRequiredError.
        with pytest.raises(SettlementAccountAmountRequiredError) as exc:
            await _create(monkeypatch, account=_account(currency="ARS"), amount=Decimal("100"), currency="USD", account_amount=None)

        assert exc.value.status_code == 400
        assert exc.value.extra == {"bucket_currency": "USD", "account_currency": "ARS"}

    @pytest.mark.asyncio
    async def test_a_same_currency_settlement_must_debit_what_it_clears(self, monkeypatch):
        # No conversion happened, so a difference is a fee — and a fee is its own expense rather than a
        # silently inflated payment. Mirrors TransferAmountsMustMatchError.
        with pytest.raises(SettlementAmountsMustMatchError) as exc:
            await _create(monkeypatch, account=_account(currency="ARS"), amount=Decimal("700"), currency="ARS", account_amount=Decimal("715"))

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_a_cash_amount_without_an_account_is_refused(self, monkeypatch):
        # There is no currency for the amount to be denominated in and no balance for it to move. The
        # DB CHECK is the backstop; this is the localizable message.
        with pytest.raises(SettlementAccountAmountWithoutAccountError) as exc:
            await _create(monkeypatch, account=None, amount=Decimal("700"), currency="ARS", account_amount=Decimal("130000"))

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_every_refusal_carries_a_code_the_frontend_can_localize(self):
        # Deliberately service-layer rather than Pydantic validators: a ValueError in a validator becomes
        # a 422 with no `code`, which the frontend cannot map to a localized string.
        codes = {
            SettlementAccountAmountRequiredError("USD", "ARS").code,
            SettlementAmountsMustMatchError().code,
            SettlementAccountAmountWithoutAccountError().code,
        }

        assert codes == {
            "settlement_account_amount_required",
            "settlement_amounts_must_match",
            "settlement_account_amount_without_account",
        }


class TestTheCurrencyRuleIsAsymmetric:
    @pytest.mark.asyncio
    async def test_a_settlement_accepts_a_foreign_currency_account(self, monkeypatch):
        # load_linked_account verifies ownership and applies no currency rule; the settlement's own
        # resolver owns the amount rules instead.
        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))

        account = await account_service.load_linked_account(AsyncMock(), USER, 7)

        assert account.currency == "ARS"

    @pytest.mark.asyncio
    async def test_an_entry_link_still_requires_a_matching_currency(self, monkeypatch):
        # The hard rule is untouched for expenses and income: their sums have only ONE amount, so a
        # mismatched link would add a foreign-currency figure straight into the balance.
        from app.domain import AccountCurrencyMismatchError

        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))

        with pytest.raises(AccountCurrencyMismatchError):
            await account_service.validate_account_link(AsyncMock(), USER, 7, "USD")

    @pytest.mark.asyncio
    async def test_a_card_default_no_longer_locks_the_accounts_currency(self, monkeypatch):
        # Reversing #173 decision 3 removes the reason the account-side lock counted cards: a card's
        # default cannot be made inert by re-denominating the account. PLAN defaults still count.
        for repo in ("subscription_repository", "installment_repository", "payment_obligation_repository"):
            monkeypatch.setattr(getattr(account_service, repo), "count_by_default_account", AsyncMock(return_value=0))

        assert await account_service.count_default_references(AsyncMock(), 7, USER.id) == 0

    @pytest.mark.asyncio
    async def test_a_plan_default_still_locks_the_accounts_currency(self, monkeypatch):
        monkeypatch.setattr(account_service.subscription_repository, "count_by_default_account", AsyncMock(return_value=2))
        for repo in ("installment_repository", "payment_obligation_repository"):
            monkeypatch.setattr(getattr(account_service, repo), "count_by_default_account", AsyncMock(return_value=0))

        assert await account_service.count_default_references(AsyncMock(), 7, USER.id) == 2


# Which leg each sum reads is the entire correctness surface of this feature, and no unit test can see it
# through a mocked repository — so these compile the real statements and assert on the SQL. A cash-side
# sum that stopped coalescing would add dollars into a peso balance; a card-side sum that STARTED
# coalescing would leave a USD bucket cleared by a peso figure.
class TestTheCashAndCardLegsNeverSwap:
    @staticmethod
    async def _sql(coro_factory) -> str:
        # An empty result set, so each repository's own row-mapping runs to completion and the statement
        # it actually executed is what gets compiled.
        session = AsyncMock()
        session.execute = AsyncMock(return_value=Mock(all=Mock(return_value=[])))
        await coro_factory(session)
        return str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect())).lower()

    @pytest.mark.asyncio
    async def test_the_three_cash_side_sums_read_the_account_leg(self):
        live = await self._sql(lambda s: card_settlement_repository.sum_by_account_ids(s, [7], USER.id))
        monthly = await self._sql(lambda s: card_settlement_repository.sum_by_account_ids_monthly(s, [7], USER.id))

        for sql in (live, monthly):
            assert "coalesce(card_settlements.account_amount, card_settlements.amount)" in sql

    @pytest.mark.asyncio
    async def test_the_point_in_time_balance_shares_the_live_sums_query(self):
        # sum_by_account_ids serves both the live balance and reconciliation's point-in-time balance, so
        # the as_of_date variant must carry the same coalesce rather than being a second spelling.
        sql = await self._sql(lambda s: card_settlement_repository.sum_by_account_ids(s, [7], USER.id, as_of_date=date(2026, 8, 17)))

        assert "coalesce(card_settlements.account_amount, card_settlements.amount)" in sql

    @pytest.mark.asyncio
    async def test_the_card_side_sums_read_the_card_leg_only(self):
        grouped = await self._sql(lambda s: card_settlement_repository.sum_by_card_ids_grouped(s, [5]))
        monthly = await self._sql(lambda s: card_settlement_repository.sum_by_card_ids_monthly(s, [5]))

        for sql in (grouped, monthly):
            assert "account_amount" not in sql, "a bucket is cleared by what the bank applied to it, not by what any account paid"
