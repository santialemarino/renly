from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    NotFoundError,
    TransferAmountRequiredError,
    TransferAmountsMustMatchError,
    TransferBeforeAccountOpenedError,
    TransferSameAccountError,
)
from app.models.account import Account, AccountType
from app.models.transfer import Transfer
from app.models.user import User
from app.services import account_service, transfer_service

# A transfer is the one movement that is neither income nor an expense: net worth does not change, the
# money leaves one owned pool and arrives in another. Two amounts are stored so a cross-currency move
# records the rate actually used; within one currency they must match, because a same-currency transfer
# that credited less than it debited would silently destroy net worth (a fee is its own expense).
# Persistence is mocked (AsyncMock), matching the other service tests.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)
TODAY = date(2026, 8, 1)


def _account(account_id: int, currency: str = "ARS", **overrides) -> Account:
    data = dict(
        id=account_id,
        user_id=1,
        name=f"Account {account_id}",
        type=AccountType.bank,
        currency=currency,
        opening_balance=Decimal("0"),
        opening_date=date(2026, 1, 1),
        is_active=True,
    )
    data.update(overrides)
    return Account(**data)


# Wires account lookup (by id) plus the write path, so a rejected request can assert nothing was staged.
def _wire(monkeypatch, accounts: dict[int, Account]) -> AsyncMock:
    async def get_account(session, account_id, user):
        account = accounts.get(account_id)
        if account is None:
            raise NotFoundError("Account not found.")
        return account

    monkeypatch.setattr(transfer_service.account_service, "get_account", AsyncMock(side_effect=get_account))
    monkeypatch.setattr(transfer_service.account_service, "get_account_in_scope", AsyncMock(side_effect=get_account))

    # The real create flushes and the DB assigns the id; the response schema requires one.
    async def create_row(session, transfer):
        transfer.id = 500
        return transfer

    create = AsyncMock(side_effect=create_row)
    monkeypatch.setattr(transfer_service.transfer_repository, "create", create)
    monkeypatch.setattr(transfer_service.transfer_repository, "save", AsyncMock())
    monkeypatch.setattr(transfer_service.transfer_repository, "delete", AsyncMock())
    return create


class TestAmountRules:
    @pytest.mark.asyncio
    async def test_one_currency_mirrors_the_debited_amount_when_omitted(self, monkeypatch):
        create = _wire(monkeypatch, {1: _account(1), 2: _account(2)})
        session = AsyncMock()

        await transfer_service.create_transfer(session, USER, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("2500"))

        written = create.await_args.args[1]
        assert written.from_amount == Decimal("2500") and written.to_amount == Decimal("2500")

    @pytest.mark.asyncio
    async def test_one_currency_rejects_a_different_credited_amount(self, monkeypatch):
        # Not silently overwritten: a user who typed a different number meant something by it, and a
        # transfer that credits less than it debits would destroy net worth. A fee is its own expense.
        create = _wire(monkeypatch, {1: _account(1), 2: _account(2)})
        session = AsyncMock()

        with pytest.raises(TransferAmountsMustMatchError):
            await transfer_service.create_transfer(
                session, USER, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("100"), to_amount=Decimal("90")
            )

        create.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_one_currency_accepts_an_equal_credited_amount(self, monkeypatch):
        create = _wire(monkeypatch, {1: _account(1), 2: _account(2)})
        await transfer_service.create_transfer(
            AsyncMock(), USER, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("100"), to_amount=Decimal("100")
        )
        assert create.await_args.args[1].to_amount == Decimal("100")

    @pytest.mark.asyncio
    async def test_cross_currency_requires_the_credited_amount(self, monkeypatch):
        # Only the user knows the rate they actually got (the blue / MEP spread); inventing one would
        # misstate the destination balance.
        create = _wire(monkeypatch, {1: _account(1, "ARS"), 2: _account(2, "USD")})
        session = AsyncMock()

        with pytest.raises(TransferAmountRequiredError) as exc:
            await transfer_service.create_transfer(session, USER, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("1200"))

        assert exc.value.extra == {"from_currency": "ARS", "to_currency": "USD"}
        create.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cross_currency_stores_both_sides_verbatim(self, monkeypatch):
        # Each leg is counted in its own account's currency, so the pair records the implied rate.
        create = _wire(monkeypatch, {1: _account(1, "ARS"), 2: _account(2, "USD")})

        await transfer_service.create_transfer(
            AsyncMock(), USER, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("1200"), to_amount=Decimal("1")
        )

        written = create.await_args.args[1]
        assert written.from_amount == Decimal("1200") and written.to_amount == Decimal("1")


class TestAccountRules:
    @pytest.mark.asyncio
    async def test_the_same_account_on_both_legs_is_refused(self, monkeypatch):
        # The balance union sums each leg independently, so one row would be both added and subtracted
        # on the same account. Refused as a domain error (400 + a mappable code), not a schema 422.
        create = _wire(monkeypatch, {1: _account(1)})
        session = AsyncMock()

        with pytest.raises(TransferSameAccountError):
            await transfer_service.create_transfer(session, USER, from_account_id=1, to_account_id=1, date=TODAY, from_amount=Decimal("10"))

        create.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_account_the_user_does_not_own_is_a_404(self, monkeypatch):
        create = _wire(monkeypatch, {1: _account(1)})

        with pytest.raises(NotFoundError):
            await transfer_service.create_transfer(AsyncMock(), USER, from_account_id=1, to_account_id=99, date=TODAY, from_amount=Decimal("10"))

        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ownership_is_checked_before_anything_is_written(self, monkeypatch):
        # The SOURCE leg, mirroring the destination case above — and asserting on the session actually
        # passed in, so "nothing was committed" is a real claim rather than one about a spare mock.
        create = _wire(monkeypatch, {2: _account(2)})
        session = AsyncMock()

        with pytest.raises(NotFoundError):
            await transfer_service.create_transfer(session, USER, from_account_id=404, to_account_id=2, date=TODAY, from_amount=Decimal("10"))

        create.assert_not_awaited()
        session.commit.assert_not_awaited()


class TestUpdateRevalidatesTheEffectivePair:
    @pytest.mark.asyncio
    async def test_changing_the_debited_amount_re_mirrors_within_one_currency(self, monkeypatch):
        _wire(monkeypatch, {1: _account(1), 2: _account(2)})
        stored = Transfer(id=5, user_id=1, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("2500"), to_amount=Decimal("2500"))
        monkeypatch.setattr(transfer_service.transfer_repository, "get_by_id", AsyncMock(return_value=stored))

        await transfer_service.update_transfer(AsyncMock(), 5, USER, from_amount=Decimal("4000"))

        assert stored.from_amount == Decimal("4000") and stored.to_amount == Decimal("4000")

    @pytest.mark.asyncio
    async def test_moving_a_leg_across_currencies_requires_the_credited_amount(self, monkeypatch):
        # The stored row was single-currency, so it has no rate to reuse — validating the request alone
        # would let a row through whose credited side is meaningless in the new currency.
        _wire(monkeypatch, {1: _account(1, "ARS"), 2: _account(2, "ARS"), 3: _account(3, "USD")})
        stored = Transfer(id=5, user_id=1, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("2500"), to_amount=Decimal("2500"))
        monkeypatch.setattr(transfer_service.transfer_repository, "get_by_id", AsyncMock(return_value=stored))

        with pytest.raises(TransferAmountRequiredError):
            await transfer_service.update_transfer(AsyncMock(), 5, USER, to_account_id=3)

    @pytest.mark.asyncio
    async def test_an_unrelated_edit_keeps_a_cross_currency_rate(self, monkeypatch):
        # Editing only the notes must not force the client to restate the rate it already recorded.
        _wire(monkeypatch, {1: _account(1, "ARS"), 2: _account(2, "USD")})
        stored = Transfer(id=5, user_id=1, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("1200"), to_amount=Decimal("1"))
        monkeypatch.setattr(transfer_service.transfer_repository, "get_by_id", AsyncMock(return_value=stored))

        await transfer_service.update_transfer(AsyncMock(), 5, USER, notes="MEP")

        assert stored.from_amount == Decimal("1200") and stored.to_amount == Decimal("1")

    @pytest.mark.asyncio
    async def test_repointing_the_source_keeps_a_cross_currency_rate(self, monkeypatch):
        # to_amount is denominated in the DESTINATION's currency, so changing the source cannot
        # invalidate it. Keying the hold on both legs forced the client to restate an unchanged rate.
        _wire(monkeypatch, {1: _account(1, "ARS"), 2: _account(2, "USD"), 3: _account(3, "ARS")})
        stored = Transfer(id=5, user_id=1, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("1200"), to_amount=Decimal("1"))
        monkeypatch.setattr(transfer_service.transfer_repository, "get_by_id", AsyncMock(return_value=stored))

        await transfer_service.update_transfer(AsyncMock(), 5, USER, from_account_id=3)

        assert stored.to_amount == Decimal("1")

    @pytest.mark.asyncio
    async def test_changing_only_the_debited_amount_keeps_a_cross_currency_rate(self, monkeypatch):
        # Across currencies the two sides are independent — the credited amount IS the rate, not a
        # mirror, so it must survive a change to the debited side.
        _wire(monkeypatch, {1: _account(1, "ARS"), 2: _account(2, "USD")})
        stored = Transfer(id=5, user_id=1, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("1200"), to_amount=Decimal("1"))
        monkeypatch.setattr(transfer_service.transfer_repository, "get_by_id", AsyncMock(return_value=stored))

        await transfer_service.update_transfer(AsyncMock(), 5, USER, from_amount=Decimal("1300"))

        assert stored.from_amount == Decimal("1300") and stored.to_amount == Decimal("1")

    @pytest.mark.asyncio
    async def test_pointing_both_legs_at_one_account_is_refused(self, monkeypatch):
        _wire(monkeypatch, {1: _account(1), 2: _account(2)})
        stored = Transfer(id=5, user_id=1, from_account_id=1, to_account_id=2, date=TODAY, from_amount=Decimal("10"), to_amount=Decimal("10"))
        monkeypatch.setattr(transfer_service.transfer_repository, "get_by_id", AsyncMock(return_value=stored))

        with pytest.raises(TransferSameAccountError):
            await transfer_service.update_transfer(AsyncMock(), 5, USER, to_account_id=1)


class TestTransfersMoveTheBalance:
    @pytest.mark.asyncio
    async def test_both_legs_are_applied_with_the_right_sign(self, monkeypatch):
        # The whole point of the feature: money leaves one pool and arrives in the other, and the two
        # sides cancel, so total cash is unchanged.
        accounts = [_account(1, opening_balance=Decimal("10000")), _account(2)]
        monkeypatch.setattr(account_service.income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.expense_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value={1: Decimal("2500")}))
        monkeypatch.setattr(account_service.pot_ownership_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.pot_ownership_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value={2: Decimal("2500")}))
        monkeypatch.setattr(account_service.shared_expense_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.shared_income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.group_settlement_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.group_settlement_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))
        for repo in (
            "income_repository",
            "expense_repository",
            "card_settlement_repository",
            "shared_expense_repository",
            "shared_income_repository",
            "group_settlement_repository",
        ):
            monkeypatch.setattr(getattr(account_service, repo), "linked_account_ids", AsyncMock(return_value=set()))
        monkeypatch.setattr(account_service.transfer_repository, "linked_account_ids", AsyncMock(return_value={1, 2}))

        balances, linked = await account_service.get_account_summaries(AsyncMock(), accounts, 1)

        assert balances == {1: Decimal("7500"), 2: Decimal("2500")}
        assert sum(balances.values()) == Decimal("10000")
        # A transfer counts as a link on either leg, so an account that has only ever sent or received
        # money is still currency-locked.
        assert linked == {1, 2}


class TestBothAccountsMustExistOnTheDate:
    # The balance union bounds each leg by its OWN account's opening_date, so a transfer dated before
    # the later-opening account would be counted on one leg and dropped on the other — money leaving one
    # account and arriving nowhere. That is the one thing a transfer must never do.
    @pytest.mark.asyncio
    async def test_a_transfer_before_the_later_opening_is_refused(self, monkeypatch):
        create = _wire(
            monkeypatch,
            {1: _account(1, opening_date=date(2026, 1, 1)), 2: _account(2, opening_date=date(2026, 7, 1))},
        )
        session = AsyncMock()

        with pytest.raises(TransferBeforeAccountOpenedError) as exc:
            await transfer_service.create_transfer(
                session, USER, from_account_id=1, to_account_id=2, date=date(2026, 6, 15), from_amount=Decimal("20000")
            )

        assert exc.value.extra == {"opening_date": "2026-07-01"}
        create.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_later_opening_is_the_bound_whichever_leg_it_is_on(self, monkeypatch):
        create = _wire(
            monkeypatch,
            {1: _account(1, opening_date=date(2026, 7, 1)), 2: _account(2, opening_date=date(2026, 1, 1))},
        )

        with pytest.raises(TransferBeforeAccountOpenedError):
            await transfer_service.create_transfer(
                AsyncMock(), USER, from_account_id=1, to_account_id=2, date=date(2026, 6, 15), from_amount=Decimal("100")
            )

        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_opening_date_itself_is_allowed(self, monkeypatch):
        create = _wire(
            monkeypatch,
            {1: _account(1, opening_date=date(2026, 1, 1)), 2: _account(2, opening_date=date(2026, 7, 1))},
        )

        await transfer_service.create_transfer(
            AsyncMock(), USER, from_account_id=1, to_account_id=2, date=date(2026, 7, 1), from_amount=Decimal("100")
        )

        create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_moving_a_transfer_back_before_an_opening_is_refused(self, monkeypatch):
        _wire(monkeypatch, {1: _account(1, opening_date=date(2026, 1, 1)), 2: _account(2, opening_date=date(2026, 7, 1))})
        stored = Transfer(
            id=5, user_id=1, from_account_id=1, to_account_id=2, date=date(2026, 8, 1), from_amount=Decimal("10"), to_amount=Decimal("10")
        )
        monkeypatch.setattr(transfer_service.transfer_repository, "get_by_id", AsyncMock(return_value=stored))

        with pytest.raises(TransferBeforeAccountOpenedError):
            await transfer_service.update_transfer(AsyncMock(), 5, USER, date=date(2026, 6, 15))
