from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    AccountCurrencyMismatchError,
    NotFoundError,
    SharedExpenseBeforeAccountOpenedError,
    SharedExpenseFundingPotNotDividedError,
    SharedExpenseFundingScopeError,
    SharedExpensePayerRequiredError,
    SharedExpenseSharedAccountPayerError,
)
from app.models.account import Account, AccountType
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.group_money_settings import SplitMethod
from app.models.pot import OwnershipEventType, Pot, PotOwnershipEvent
from app.models.shared_expense import SharedExpense
from app.models.user import User
from app.schemas.shared_expense import SharedExpenseSplitInput
from app.services import shared_expense_service

# Where the money came from and who fronted it — the half of a shared expense the split figures cannot
# say, and the half every case in §4.2 turns on. Persistence is mocked; the SQL these drive is proved
# against a real database in tests/integration.

GROUP_ID = 3
USER = User(id=1, name="S", email="u@test", password_hash="x", session_epoch=0)
TODAY = date(2026, 6, 1)


def _member(member_id: int, *, user_id: int | None = None, is_active: bool = True) -> GroupMember:
    return GroupMember(
        id=member_id, group_id=GROUP_ID, user_id=user_id, display_name=f"M{member_id}", role=GroupMemberRole.member, is_active=is_active
    )


# Santi's seat, plus a name-only placeholder and a second account-holder.
_MEMBERS = [_member(11, user_id=1), _member(12, user_id=2), _member(13)]


def _account(account_id: int, *, user_id: int | None = 1, pot_id: int | None = None, currency: str = "ARS", opening=date(2026, 1, 1)) -> Account:
    return Account(
        id=account_id,
        user_id=user_id,
        pot_id=pot_id,
        created_by=1,
        name=f"A{account_id}",
        type=AccountType.bank,
        currency=currency,
        opening_balance=Decimal("0"),
        opening_date=opening,
    )


def _event(member_id: int, units: str, *, type=OwnershipEventType.opening) -> PotOwnershipEvent:
    return PotOwnershipEvent(id=1, pot_id=9, type=type, date=date(2026, 1, 2), member_id=member_id, units=Decimal(units), unit_price=Decimal("1"))


# Stubs everything create_expense reaches for. Each keyword replaces one collaborator, so a test names
# only the thing it is about.
def _wire(monkeypatch, *, account=None, pot=None, events=(), card=None, members=_MEMBERS):
    monkeypatch.setattr(
        shared_expense_service.group_service,
        "require_member",
        AsyncMock(return_value=(Group(id=GROUP_ID, name="Casa", kind=GroupKind.household), members[0])),
    )
    monkeypatch.setattr(shared_expense_service.group_repository, "list_members", AsyncMock(return_value=list(members)))
    monkeypatch.setattr(shared_expense_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=account))
    monkeypatch.setattr(shared_expense_service.credit_card_repository, "get_by_id", AsyncMock(return_value=card))
    monkeypatch.setattr(shared_expense_service.pot_repository, "get_by_id", AsyncMock(return_value=pot))
    monkeypatch.setattr(shared_expense_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=list(events)))
    monkeypatch.setattr(shared_expense_service.card_reconciliation_service, "mark_stale_for_date", AsyncMock())
    written: dict = {}

    async def _create(_session, expense: SharedExpense) -> SharedExpense:
        expense.id = 77
        written["expense"] = expense
        return expense

    async def _create_splits(_session, splits):
        written["splits"] = splits
        return splits

    monkeypatch.setattr(shared_expense_service.shared_expense_repository, "create", _create)
    monkeypatch.setattr(shared_expense_service.shared_expense_repository, "create_splits", _create_splits)
    return written


async def _create(monkeypatch_written, **overrides):
    body = dict(
        date=TODAY,
        amount=Decimal("90.00"),
        currency="ARS",
        split_method=SplitMethod.equal,
        splits=[SharedExpenseSplitInput(member_id=11), SharedExpenseSplitInput(member_id=12), SharedExpenseSplitInput(member_id=13)],
        payer_member_id=11,
    )
    body.update(overrides)
    return await shared_expense_service.create_expense(AsyncMock(), GROUP_ID, USER, **body)


class TestOneMemberFrontsIt:
    @pytest.mark.asyncio
    async def test_the_payer_holds_the_whole_fronted_amount(self, monkeypatch):
        written = _wire(monkeypatch)
        await _create(written)
        # Asserted on the rows the service BUILT, not on what a stub handed back: a create that
        # dropped paid_amount would return the same response either way.
        positions = {s.member_id: (s.amount, s.paid_amount) for s in written["splits"]}
        assert positions == {
            11: (Decimal("30.00"), Decimal("90.00")),
            12: (Decimal("30.00"), Decimal("0")),
            13: (Decimal("30.00"), Decimal("0")),
        }

    @pytest.mark.asyncio
    async def test_both_columns_sum_to_the_expense(self, monkeypatch):
        written = _wire(monkeypatch)
        await _create(written)
        assert sum(s.amount for s in written["splits"]) == Decimal("90.00")
        assert sum(s.paid_amount for s in written["splits"]) == Decimal("90.00")

    @pytest.mark.asyncio
    async def test_a_payer_who_took_no_part_still_gets_a_row(self, monkeypatch):
        # D33: you can front a bill you are not in on. Their share is zero and the whole amount is a
        # receivable — without the row the fronted total would not sum to the expense.
        written = _wire(monkeypatch)
        await _create(
            written,
            amount=Decimal("60.00"),
            splits=[SharedExpenseSplitInput(member_id=12), SharedExpenseSplitInput(member_id=13)],
            payer_member_id=11,
        )
        rows = {s.member_id: (s.amount, s.paid_amount) for s in written["splits"]}
        assert rows[11] == (Decimal("0"), Decimal("60.00"))
        assert sum(s.paid_amount for s in written["splits"]) == Decimal("60.00")

    @pytest.mark.asyncio
    async def test_no_payer_and_no_shared_account_is_refused(self, monkeypatch):
        # Nothing would say who fronted it, so the balances could not sum to zero — the shares would
        # add up to the total while nobody had paid it.
        _wire(monkeypatch)
        with pytest.raises(SharedExpensePayerRequiredError):
            await _create({}, payer_member_id=None)


class TestTheFundingAccount:
    @pytest.mark.asyncio
    async def test_a_private_account_must_belong_to_the_payer(self, monkeypatch):
        # Otherwise one member could spend from another's account by naming its id.
        _wire(monkeypatch, account=_account(5, user_id=2))
        with pytest.raises(NotFoundError):
            await _create({}, paid_from_account_id=5, payer_member_id=11)

    @pytest.mark.asyncio
    async def test_the_payers_own_account_is_accepted(self, monkeypatch):
        written = _wire(monkeypatch, account=_account(5, user_id=1))
        await _create(written, paid_from_account_id=5, payer_member_id=11)
        assert written["expense"].paid_from_account_id == 5

    @pytest.mark.asyncio
    async def test_the_currency_must_match_the_account(self, monkeypatch):
        # Merged constraint (a): the balance sums carry ONE amount, so a mismatched link would
        # subtract a foreign-currency figure straight from the account.
        _wire(monkeypatch, account=_account(5, currency="USD"))
        with pytest.raises(AccountCurrencyMismatchError):
            await _create({}, paid_from_account_id=5, payer_member_id=11)

    @pytest.mark.asyncio
    async def test_it_cannot_be_dated_before_the_account_opened(self, monkeypatch):
        # The balance sum is bounded below by opening_date, so an earlier expense would clear money
        # the account never shows leaving.
        _wire(monkeypatch, account=_account(5, opening=date(2026, 7, 1)))
        with pytest.raises(SharedExpenseBeforeAccountOpenedError):
            await _create({}, paid_from_account_id=5, payer_member_id=11)

    @pytest.mark.asyncio
    async def test_a_placeholder_cannot_name_an_account(self, monkeypatch):
        # A name-only seat has no linked user, so no account can be theirs — refused by the ownership
        # check without a special case for placeholders.
        _wire(monkeypatch, account=_account(5, user_id=1))
        with pytest.raises(NotFoundError):
            await _create({}, paid_from_account_id=5, payer_member_id=13)


class TestASharedAccountFrontsIt:
    _POT = Pot(id=9, group_id=GROUP_ID, base_currency="ARS")

    @pytest.mark.asyncio
    async def test_the_pots_owners_front_it_in_their_proportions(self, monkeypatch):
        # §4.2's fourth row and O1's answer, in one shape: joint money paid for one member's own
        # purchase, so the others are owed their ownership share of it.
        written = _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[_event(11, "20"), _event(12, "80")])
        await _create(
            written,
            amount=Decimal("100.00"),
            splits=[SharedExpenseSplitInput(member_id=11)],
            payer_member_id=None,
            paid_from_account_id=5,
        )
        rows = {s.member_id: (s.amount, s.paid_amount) for s in written["splits"]}
        assert rows == {11: (Decimal("100.00"), Decimal("20.00")), 12: (Decimal("0"), Decimal("80.00"))}
        # Member 11 consumed 100 and fronted 20, so they owe 80 — exactly member 12's share of the
        # joint money that was spent on them.
        assert rows[11][1] - rows[11][0] == Decimal("-80.00")

    @pytest.mark.asyncio
    async def test_the_pinned_proportions_are_read_at_the_expenses_own_date(self, monkeypatch):
        # Pinned rather than derived on read: the ownership ledger is REPLAYED, so a back-dated event
        # would otherwise silently rewrite a balance two people had already agreed on.
        written = _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[_event(11, "50"), _event(12, "50")])
        await _create(written, payer_member_id=None, paid_from_account_id=5, date=date(2026, 3, 15))
        assert shared_expense_service.pot_ownership_repository.list_by_pot.await_args.kwargs == {"as_of_date": date(2026, 3, 15)}

    @pytest.mark.asyncio
    async def test_naming_a_payer_as_well_is_refused(self, monkeypatch):
        # Joint money is fronted by everyone who owns it, so one named payer would assert something
        # the ownership ledger contradicts. Refused rather than ignored: silently dropping a field the
        # user filled in is how a form records something other than what it showed.
        _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[_event(11, "100")])
        with pytest.raises(SharedExpenseSharedAccountPayerError):
            await _create({}, payer_member_id=11, paid_from_account_id=5)

    @pytest.mark.asyncio
    async def test_an_undivided_pot_is_refused(self, monkeypatch):
        # With no ownership on record there is no honest answer to whose money it was, and inventing
        # one would either assert a division nobody agreed or leave the balances not summing to zero.
        _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[])
        with pytest.raises(SharedExpenseFundingPotNotDividedError):
            await _create({}, payer_member_id=None, paid_from_account_id=5)

    @pytest.mark.asyncio
    async def test_a_pot_in_another_group_is_refused(self, monkeypatch):
        # Its owners are not members here, so what they fronted could not be recorded against anyone
        # this group can settle with.
        _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=Pot(id=9, group_id=99, base_currency="ARS"))
        with pytest.raises(SharedExpenseFundingScopeError):
            await _create({}, payer_member_id=None, paid_from_account_id=5)


class TestSeatsAreCheckedAgainstThisGroup:
    @pytest.mark.asyncio
    async def test_a_seat_from_another_group_is_refused(self, monkeypatch):
        _wire(monkeypatch)
        with pytest.raises(NotFoundError):
            await _create({}, splits=[SharedExpenseSplitInput(member_id=999)], payer_member_id=11)

    @pytest.mark.asyncio
    async def test_a_deactivated_seat_is_refused(self, monkeypatch):
        # A former member cannot be given a share: the membership policy has already taken the group's
        # rows away from them, so they would owe money they could never see.
        _wire(monkeypatch, members=[_member(11, user_id=1), _member(12, user_id=2, is_active=False)])
        with pytest.raises(NotFoundError):
            await _create({}, splits=[SharedExpenseSplitInput(member_id=12)], payer_member_id=11)

    @pytest.mark.asyncio
    async def test_a_payer_from_another_group_is_refused(self, monkeypatch):
        _wire(monkeypatch)
        with pytest.raises(NotFoundError):
            await _create({}, payer_member_id=999)


class TestTheCardLeg:
    @pytest.mark.asyncio
    async def test_a_card_charge_flags_the_covering_statement_as_stale(self, monkeypatch):
        # A reconciled statement over this date now covers a different set of charges. Asserted on the
        # arguments the service PASSED, which is the only thing that proves the right bucket was flagged.
        written = _wire(monkeypatch, card=type("Card", (), {"id": 4})())
        await _create(written, credit_card_id=4, payment_method="credit_card", payer_member_id=11)
        assert shared_expense_service.card_reconciliation_service.mark_stale_for_date.await_args.args[1:] == (4, "ARS", TODAY)

    @pytest.mark.asyncio
    async def test_a_card_that_is_not_the_payers_is_refused(self, monkeypatch):
        _wire(monkeypatch, card=None)
        with pytest.raises(NotFoundError):
            await _create({}, credit_card_id=4, payment_method="credit_card", payer_member_id=11)

    @pytest.mark.asyncio
    async def test_no_card_flags_nothing(self, monkeypatch):
        written = _wire(monkeypatch)
        await _create(written)
        shared_expense_service.card_reconciliation_service.mark_stale_for_date.assert_not_awaited()
