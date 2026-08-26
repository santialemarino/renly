from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from app.domain import (
    SettlementAccountAmountRequiredError,
    SettlementAccountAmountWithoutAccountError,
    SettlementAmountsMustMatchError,
    SettlementBeforeAccountOpenedError,
)
from app.models.account import Account, AccountType
from app.models.user import User
from app.repositories import account_movement_repository, card_reconciliation_repository, card_settlement_repository
from app.services import account_service, credit_card_service

# Cross-currency card settlement (B4): paying a USD bucket with pesos. The settlement clears the bucket
# in the CARD's currency (the bank converted internally) while its cash leg draws the real blended local
# amount from the funding account. Both amounts are recorded and the pair IS the rate — there is
# deliberately no stored rate, the same conclusion transfers reached.
#
# The whole correctness surface is which leg each query reads: THREE are cash-side and must read
# coalesce(account_amount, amount), SIX are card-side and must NOT. Unit tests mock repositories, so the
# SQL assertions below are what pins that split; test_account_ledger_drift.py proves the cash side against
# a real DB. Every one of the nine is compiled here — the four in card_reconciliation_repository are the
# ones nothing else covers at all, because their own tests mock them and a mock cannot see SQL.

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
async def _create(
    monkeypatch,
    *,
    account: Account | None,
    amount: Decimal,
    currency: str,
    account_amount: Decimal | None,
    on: date = date(2026, 8, 17),
):
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
        date=on,
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
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(currency="ARS")))

        account = await account_service.load_linked_account(AsyncMock(), USER, 7)

        assert account.currency == "ARS"

    @pytest.mark.asyncio
    async def test_an_entry_link_still_requires_a_matching_currency(self, monkeypatch):
        # The hard rule is untouched for expenses and income: their sums have only ONE amount, so a
        # mismatched link would add a foreign-currency figure straight into the balance.
        from app.domain import AccountCurrencyMismatchError

        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(currency="ARS")))

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


class TestTheFundingAccountMustBeOpen:
    @pytest.mark.asyncio
    async def test_a_settlement_before_the_account_opened_is_refused(self, monkeypatch):
        # Every cash sum is bounded below by opening_date, so such a settlement would clear the card while
        # its cash leg was silently dropped — debt reduced, no money moved. Across currencies the dropped
        # figure is the account-denominated one, which is the larger of the two.
        with pytest.raises(SettlementBeforeAccountOpenedError) as exc:
            await _create(
                monkeypatch,
                account=_account(currency="ARS"),
                amount=Decimal("100"),
                currency="USD",
                account_amount=Decimal("130000"),
                on=date(2025, 12, 31),
            )

        assert exc.value.status_code == 400
        assert exc.value.extra == {"opening_date": "2026-01-01"}

    @pytest.mark.asyncio
    async def test_the_opening_date_itself_is_allowed(self, monkeypatch):
        # opening_balance IS the balance AT that date, and the sums bound with >=, so a row dated exactly
        # on it counts. An off-by-one here would refuse a legitimate settlement.
        row, _ = await _create(
            monkeypatch,
            account=_account(currency="ARS"),
            amount=Decimal("100"),
            currency="USD",
            account_amount=Decimal("130000"),
            on=date(2026, 1, 1),
        )

        assert row.date == date(2026, 1, 1)

    @pytest.mark.asyncio
    async def test_an_unlinked_settlement_has_no_date_bound(self, monkeypatch):
        # No funding account means no cash leg to drop, so any date is recordable — the card side is not
        # bounded by an account's opening date.
        row, _ = await _create(monkeypatch, account=None, amount=Decimal("100"), currency="USD", account_amount=None, on=date(2020, 1, 1))

        assert row.date == date(2020, 1, 1)


class TestUnlinkingClearsTheCashLeg:
    @pytest.mark.asyncio
    async def test_deleting_the_funding_account_clears_the_recorded_cash_leg(self, monkeypatch):
        # The FK is ON DELETE SET NULL, and Postgres performs that as an UPDATE — so a DB CHECK pairing
        # account_id with account_amount would make this delete IMPOSSIBLE (measured: a generic integrity
        # 409, with the account permanently undeletable). The rule lives here instead: clear the cash leg
        # in the same transaction, so the row keeps its card leg and loses only what it can't attribute.
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=_account()))
        monkeypatch.setattr(account_service.account_repository, "delete", AsyncMock())
        clear = AsyncMock()
        monkeypatch.setattr(account_service.card_settlement_repository, "clear_account_amounts", clear)
        session = AsyncMock()

        await account_service.delete_account(session, 7, USER)

        clear.assert_awaited_once_with(session, 7, USER.id)
        # One commit for the whole use case, so the clear and the delete are atomic.
        session.commit.assert_awaited_once()


# Which leg each query reads is the entire correctness surface of this feature, and no unit test can see
# it through a mocked repository — so these compile the real statements and assert on the SQL. A cash-side
# query that stopped coalescing would add dollars into a peso balance; a card-side one that STARTED
# coalescing would clear a USD bucket with a peso figure.
class TestTheCashAndCardLegsNeverSwap:
    @staticmethod
    async def _sql(coro_factory) -> str:
        # An empty result set in every shape a repository might read it (rows, a scalar total, ORM
        # objects), so each one's own mapping runs to completion and the statement it actually executed is
        # what gets compiled.
        session = AsyncMock()
        result = Mock(all=Mock(return_value=[]), scalar_one=Mock(return_value=0), first=Mock(return_value=None))
        result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        session.execute = AsyncMock(return_value=result)
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
    async def test_the_ledger_branch_reads_the_account_leg(self):
        # The third cash-side reader, and the one that lives in another module — it imports the shared
        # expression rather than re-spelling it, so this proves the import still resolves to the coalesce.
        sql = await self._sql(lambda s: account_movement_repository.list_movements(s, 7, USER.id, opening_date=date(2026, 1, 1)))

        assert "coalesce(card_settlements.account_amount, card_settlements.amount)" in sql

    # All SIX card-side queries, parametrized so adding a seventh has an obvious home. The four in
    # card_reconciliation_repository are covered nowhere else: their own tests mock them, and switching any
    # one to the cash leg would clear a USD bucket with a peso figure while the whole suite stayed green.
    @pytest.mark.parametrize(
        ("label", "call"),
        [
            ("sum_by_card_ids_grouped", lambda s: card_settlement_repository.sum_by_card_ids_grouped(s, [5])),
            ("sum_by_card_ids_monthly", lambda s: card_settlement_repository.sum_by_card_ids_monthly(s, [5])),
            ("sum_settlements_at", lambda s: card_reconciliation_repository.sum_settlements_at(s, 5, "USD", date(2026, 8, 17))),
            (
                "sum_settlements_between",
                lambda s: card_reconciliation_repository.sum_settlements_between(s, 5, "USD", date(2026, 7, 20), date(2026, 8, 17)),
            ),
            ("list_settlement_daily_sums", lambda s: card_reconciliation_repository.list_settlement_daily_sums(s, 5, "USD", date(2026, 8, 17))),
            ("sum_settlements_by_bucket_at", lambda s: card_reconciliation_repository.sum_settlements_by_bucket_at(s, [5], date(2026, 8, 17))),
        ],
    )
    @pytest.mark.asyncio
    async def test_the_card_side_queries_read_the_card_leg_only(self, label, call):
        sql = await self._sql(call)

        assert "account_amount" not in sql, f"{label}: a bucket is cleared by what the bank applied to it, not by what any account paid"
