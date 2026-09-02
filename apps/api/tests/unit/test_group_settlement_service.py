from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    GroupBalanceOutstandingError,
    GroupSettlementBeforeAccountOpenedError,
    GroupSettlementConfirmedError,
    GroupSettlementForeignLegError,
    GroupSettlementLegAmountRequiredError,
    GroupSettlementLegAmountsMustMatchError,
    GroupSettlementLegTotalTooSmallError,
    GroupSettlementLegWithoutAccountError,
    GroupSettlementNotCreditorError,
    GroupSettlementNotPayeeError,
    GroupSettlementSameMemberError,
    GroupSettlementWriteOffHasNoLegError,
    GroupWriteOffExceedsBalanceError,
    NotFoundError,
)
from app.models.account import Account, AccountType
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.group_money_settings import GroupMoneySettings
from app.models.group_settlement import GroupSettlement, GroupSettlementStatus
from app.models.user import User
from app.services import group_settlement_service
from app.utils.metrics import RateLookup

# Recording, confirming and reversing a settlement, and the balances it clears. Who may do what is the
# surface here: each rule names a different person, and collapsing any two would let one member act on
# another's word.

GROUP_ID = 3
USER = User(id=1, name="S", email="u@test", password_hash="x", session_epoch=0)
TODAY = date(2026, 6, 1)


def _member(member_id: int, *, user_id: int | None = None, is_active: bool = True) -> GroupMember:
    return GroupMember(
        id=member_id, group_id=GROUP_ID, user_id=user_id, display_name=f"M{member_id}", role=GroupMemberRole.member, is_active=is_active
    )


_MEMBERS = [_member(11, user_id=1), _member(12, user_id=2), _member(13)]


def _account(account_id: int, *, user_id: int = 1, currency: str = "ARS", opening=date(2026, 1, 1)) -> Account:
    return Account(
        id=account_id,
        user_id=user_id,
        created_by=1,
        name=f"A{account_id}",
        type=AccountType.bank,
        currency=currency,
        opening_balance=Decimal("0"),
        opening_date=opening,
    )


def _settlement(**overrides) -> GroupSettlement:
    data = dict(
        id=8,
        group_id=GROUP_ID,
        from_member_id=12,
        to_member_id=11,
        date=TODAY,
        amount=Decimal("30.00"),
        currency="ARS",
        status=GroupSettlementStatus.pending,
    )
    data.update(overrides)
    return GroupSettlement(**data)


# Stubs everything the settlement service reaches for. `viewer` is which seat the caller holds, which
# is what every permission rule below turns on.
#
# `positions` are the EXPENSE splits' aggregate and `income_positions` the income one, as
# (currency, member_id, two figures) — the two are separate parameters rather than one pre-netted map
# because the service reads them from two repositories and nets them itself, and a test that handed it
# one combined figure could not tell a dropped flow from a summed one.
def _wire(
    monkeypatch,
    *,
    viewer=_MEMBERS[0],
    account=None,
    auto_finalise=False,
    settlement=None,
    positions=None,
    income_positions=None,
):
    monkeypatch.setattr(
        group_settlement_service.group_service,
        "require_member",
        AsyncMock(return_value=(Group(id=GROUP_ID, name="Casa", kind=GroupKind.household), viewer)),
    )
    monkeypatch.setattr(group_settlement_service.group_repository, "list_members", AsyncMock(return_value=list(_MEMBERS)))
    monkeypatch.setattr(
        group_settlement_service.group_repository,
        "get_by_ids",
        AsyncMock(return_value=[Group(id=GROUP_ID, name="Casa", kind=GroupKind.household)]),
    )
    monkeypatch.setattr(group_settlement_service.account_repository, "get_by_id", AsyncMock(return_value=account))
    monkeypatch.setattr(
        group_settlement_service.group_money_settings_repository,
        "get_by_group_id",
        AsyncMock(return_value=GroupMoneySettings(group_id=GROUP_ID, auto_finalise_settlements=auto_finalise)),
    )
    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "get_by_id", AsyncMock(return_value=settlement))
    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "save", AsyncMock())
    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "delete", AsyncMock())
    # The batched reads, which the single-group form delegates to. `positions` is given in the
    # single-group shape below and lifted here, so a test stays about balances rather than about ids.
    monkeypatch.setattr(
        group_settlement_service.shared_expense_repository,
        "list_positions_by_groups",
        AsyncMock(return_value=[(GROUP_ID, *row) for row in (positions or [])]),
    )
    monkeypatch.setattr(
        group_settlement_service.shared_income_repository,
        "list_positions_by_groups",
        AsyncMock(return_value=[(GROUP_ID, *row) for row in (income_positions or [])]),
    )
    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "list_movements_by_groups", AsyncMock(return_value=[]))
    monkeypatch.setattr(group_settlement_service, "exchange_rate_service", AsyncMock())
    written: dict = {}

    # `row` is the last one written and `rows` every one, in order. The waterfall writes several from
    # one request, and a helper that only ever remembered the last would report a plan's final step as
    # though it were the whole payment.
    written["rows"] = []

    async def _create(_session, row: GroupSettlement) -> GroupSettlement:
        row.id = 8 + len(written["rows"])
        written["row"] = row
        written["rows"].append(row)
        return row

    async def _create_many(_session, batch: list[GroupSettlement]) -> list[GroupSettlement]:
        for row in batch:
            await _create(_session, row)
        return batch

    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "create", _create)
    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "create_many", _create_many)
    return written


async def _record(**overrides):
    body = dict(from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal("30.00"), currency="ARS")
    body.update(overrides)
    return await group_settlement_service.record_settlement(AsyncMock(), GROUP_ID, USER, **body)


class TestRecording:
    @pytest.mark.asyncio
    async def test_a_settlement_lands_pending_by_default(self, monkeypatch):
        written = _wire(monkeypatch)
        await _record()
        assert written["row"].status == GroupSettlementStatus.pending
        assert written["row"].confirmed_at is None

    @pytest.mark.asyncio
    async def test_auto_finalise_confirms_it_on_the_spot(self, monkeypatch):
        # D28's near-zero-friction path for a couple: the confirmation step is skipped, not faked, so
        # the row is genuinely confirmed and carries a timestamp the CHECK constraint requires.
        written = _wire(monkeypatch, auto_finalise=True)
        await _record()
        assert written["row"].status == GroupSettlementStatus.confirmed
        assert written["row"].confirmed_at is not None

    @pytest.mark.asyncio
    async def test_paying_yourself_is_refused(self, monkeypatch):
        _wire(monkeypatch)
        with pytest.raises(GroupSettlementSameMemberError):
            await _record(from_member_id=11, to_member_id=11)

    @pytest.mark.asyncio
    async def test_a_seat_outside_the_group_is_refused(self, monkeypatch):
        _wire(monkeypatch)
        with pytest.raises(NotFoundError):
            await _record(from_member_id=999)

    @pytest.mark.asyncio
    async def test_any_member_may_record_one(self, monkeypatch):
        # Either side of a payment can be the one who remembers to write it down — only CONFIRMING is
        # the payee's alone.
        written = _wire(monkeypatch, viewer=_MEMBERS[1])
        await _record()
        assert written["row"].id == 8


class TestTheCashLegs:
    """Each side records their OWN account, and only when it says something the bucket does not.

    The two legs belong to two different people, and the row-level policies hide each member's
    accounts from the other — so a request naming both could only have guessed an id. Every test here
    therefore records as the member whose leg it names.
    """

    @pytest.mark.asyncio
    async def test_no_account_means_no_leg_amount(self, monkeypatch):
        # Mark-as-paid with nothing named is the v1 default, and the only thing a placeholder's side
        # can ever be.
        written = _wire(monkeypatch)
        await _record()
        assert (written["row"].from_amount, written["row"].to_amount) == (None, None)

    @pytest.mark.asyncio
    async def test_a_leg_amount_without_an_account_is_refused(self, monkeypatch):
        # There is no currency for that figure to be denominated in and no balance for it to move.
        _wire(monkeypatch, viewer=_MEMBERS[1])
        with pytest.raises(GroupSettlementLegWithoutAccountError):
            await _record(from_amount=Decimal("30.00"))

    @pytest.mark.asyncio
    async def test_naming_the_other_partys_account_is_refused(self, monkeypatch):
        # The caller cannot even SEE the other side's accounts, so this could only have guessed an id.
        # Refused explicitly rather than left to the ownership check, which would also refuse it but as
        # a bare "not found" that says nothing about what to do instead.
        _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=1))
        with pytest.raises(GroupSettlementForeignLegError):
            await _record(to_account_id=5)

    @pytest.mark.asyncio
    async def test_the_payer_may_name_their_own(self, monkeypatch):
        written = _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=2))
        await _record(from_account_id=5)
        assert written["row"].from_account_id == 5

    @pytest.mark.asyncio
    async def test_a_same_currency_leg_stores_nothing(self, monkeypatch):
        # Every reader treats "a leg amount is set" as "this crossed currencies", and the sums read
        # coalesce(leg, amount) — so a second copy of the same figure is a second thing to keep in step.
        written = _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=2))
        await _record(from_account_id=5)
        assert written["row"].from_amount is None

    @pytest.mark.asyncio
    async def test_a_same_currency_leg_that_disagrees_is_refused(self, monkeypatch):
        # No conversion happened, so the account moved exactly what came off the bucket. A bank fee is
        # its own expense rather than a silently inflated payment.
        _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=2))
        with pytest.raises(GroupSettlementLegAmountsMustMatchError):
            await _record(from_account_id=5, from_amount=Decimal("31.00"))

    @pytest.mark.asyncio
    async def test_a_cross_currency_leg_must_say_what_moved(self, monkeypatch):
        # Without it the balance would be reduced by a number that never left anyone's account.
        _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=2, currency="USD"))
        with pytest.raises(GroupSettlementLegAmountRequiredError):
            await _record(from_account_id=5)

    @pytest.mark.asyncio
    async def test_a_cross_currency_leg_stores_what_actually_moved(self, monkeypatch):
        written = _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=2, currency="USD"))
        await _record(from_account_id=5, from_amount=Decimal("0.03"))
        assert written["row"].from_amount == Decimal("0.03")

    @pytest.mark.asyncio
    async def test_a_leg_must_name_the_members_own_account(self, monkeypatch):
        # Their OWN, not merely one on their side: naming an account they do not hold would move money
        # through somebody else's.
        _wire(monkeypatch, viewer=_MEMBERS[1], account=None)
        with pytest.raises(NotFoundError):
            await _record(from_account_id=5)

    @pytest.mark.asyncio
    async def test_it_cannot_be_dated_before_the_account_opened(self, monkeypatch):
        _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=2, opening=date(2026, 9, 1)))
        with pytest.raises(GroupSettlementBeforeAccountOpenedError):
            await _record(from_account_id=5)


class TestAttachingYourOwnLegAfterwards:
    """The other side attaches theirs later — usually at the moment they confirm receiving it.

    This exists because the two legs cannot be set in one request: neither party can see the other's
    accounts. Without it the payee's balance would stay wrong for a payment they actually received,
    with no way to fix it.
    """

    @pytest.mark.asyncio
    async def test_the_payee_attaches_theirs_to_the_receiving_leg(self, monkeypatch):
        row = _settlement()
        _wire(monkeypatch, viewer=_MEMBERS[0], account=_account(5, user_id=1), settlement=row)
        result = await group_settlement_service.set_leg(AsyncMock(), GROUP_ID, 8, USER, account_id=5)
        # The RECEIVING leg, decided by which seat the caller holds rather than by anything in the body.
        assert (result.to_account_id, result.from_account_id) == (5, None)

    @pytest.mark.asyncio
    async def test_the_payer_attaches_theirs_to_the_paying_leg(self, monkeypatch):
        row = _settlement()
        _wire(monkeypatch, viewer=_MEMBERS[1], account=_account(5, user_id=2), settlement=row)
        result = await group_settlement_service.set_leg(AsyncMock(), GROUP_ID, 8, USER, account_id=5)
        assert (result.from_account_id, result.to_account_id) == (5, None)

    @pytest.mark.asyncio
    async def test_a_third_member_has_no_leg_to_attach(self, monkeypatch):
        _wire(monkeypatch, viewer=_MEMBERS[2], account=_account(5, user_id=1), settlement=_settlement())
        with pytest.raises(GroupSettlementForeignLegError):
            await group_settlement_service.set_leg(AsyncMock(), GROUP_ID, 8, USER, account_id=5)

    @pytest.mark.asyncio
    async def test_a_confirmed_settlement_still_accepts_it(self, monkeypatch):
        # Deliberately not locked the way deletion is: confirmation vouches for the amount and the fact
        # of the payment, and neither changes here — only which of the caller's own accounts it passed
        # through, which affects nobody else's balance.
        row = _settlement(status=GroupSettlementStatus.confirmed, confirmed_at=TODAY)
        _wire(monkeypatch, viewer=_MEMBERS[0], account=_account(5, user_id=1), settlement=row)
        result = await group_settlement_service.set_leg(AsyncMock(), GROUP_ID, 8, USER, account_id=5)
        assert result.to_account_id == 5

    @pytest.mark.asyncio
    async def test_a_write_off_has_no_leg_to_attach(self, monkeypatch):
        # It moved no money — that is what a write-off IS — so an account would record a payment
        # nobody made, and a DB CHECK refuses the row outright.
        _wire(monkeypatch, viewer=_MEMBERS[0], account=_account(5, user_id=1), settlement=_settlement(status=GroupSettlementStatus.written_off))
        with pytest.raises(GroupSettlementWriteOffHasNoLegError):
            await group_settlement_service.set_leg(AsyncMock(), GROUP_ID, 8, USER, account_id=5)

    @pytest.mark.asyncio
    async def test_passing_nothing_clears_it(self, monkeypatch):
        row = _settlement(to_account_id=5, to_amount=Decimal("2.00"))
        _wire(monkeypatch, viewer=_MEMBERS[0], settlement=row)
        result = await group_settlement_service.set_leg(AsyncMock(), GROUP_ID, 8, USER, account_id=None)
        assert (result.to_account_id, result.to_amount) == (None, None)


class TestConfirming:
    @pytest.mark.asyncio
    async def test_the_payee_confirms(self, monkeypatch):
        row = _settlement()
        _wire(monkeypatch, viewer=_MEMBERS[0], settlement=row)
        result = await group_settlement_service.confirm_settlement(AsyncMock(), GROUP_ID, 8, USER)
        assert result.status == GroupSettlementStatus.confirmed
        assert row.confirmed_at is not None

    @pytest.mark.asyncio
    async def test_the_payer_cannot_confirm_their_own_payment(self, monkeypatch):
        # Confirming means "I received this" — it is the trust anchor for real money, so it can only
        # be said by the person who received it.
        _wire(monkeypatch, viewer=_MEMBERS[1], settlement=_settlement())
        with pytest.raises(GroupSettlementNotPayeeError):
            await group_settlement_service.confirm_settlement(AsyncMock(), GROUP_ID, 8, USER)

    @pytest.mark.asyncio
    async def test_confirming_twice_is_refused(self, monkeypatch):
        _wire(monkeypatch, settlement=_settlement(status=GroupSettlementStatus.confirmed, confirmed_at=TODAY))
        with pytest.raises(GroupSettlementConfirmedError):
            await group_settlement_service.confirm_settlement(AsyncMock(), GROUP_ID, 8, USER)

    @pytest.mark.asyncio
    async def test_un_confirming_returns_it_to_pending_and_clears_the_stamp(self, monkeypatch):
        # The stamp exists in exactly one status — a CHECK constraint enforces the pair, so leaving it
        # behind would make the row unwritable rather than merely untidy.
        row = _settlement(status=GroupSettlementStatus.confirmed, confirmed_at=TODAY)
        _wire(monkeypatch, settlement=row)
        result = await group_settlement_service.unconfirm_settlement(AsyncMock(), GROUP_ID, 8, USER)
        assert (result.status, row.confirmed_at) == (GroupSettlementStatus.pending, None)

    @pytest.mark.asyncio
    async def test_only_the_payee_may_un_confirm(self, monkeypatch):
        _wire(monkeypatch, viewer=_MEMBERS[1], settlement=_settlement(status=GroupSettlementStatus.confirmed, confirmed_at=TODAY))
        with pytest.raises(GroupSettlementNotPayeeError):
            await group_settlement_service.unconfirm_settlement(AsyncMock(), GROUP_ID, 8, USER)


class TestReversing:
    @pytest.mark.asyncio
    async def test_either_party_may_delete_a_pending_settlement(self, monkeypatch):
        for viewer in (_MEMBERS[0], _MEMBERS[1]):
            _wire(monkeypatch, viewer=viewer, settlement=_settlement())
            await group_settlement_service.delete_settlement(AsyncMock(), GROUP_ID, 8, USER)
            group_settlement_service.group_settlement_repository.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_third_member_may_not(self, monkeypatch):
        _wire(monkeypatch, viewer=_MEMBERS[2], settlement=_settlement())
        with pytest.raises(GroupSettlementNotPayeeError):
            await group_settlement_service.delete_settlement(AsyncMock(), GROUP_ID, 8, USER)

    @pytest.mark.asyncio
    async def test_a_confirmed_settlement_cannot_be_deleted_by_anyone(self, monkeypatch):
        # The payee said they received the money; undoing that silently would overwrite their word.
        # They un-confirm it first, which is a deliberate second act.
        for viewer in _MEMBERS:
            _wire(monkeypatch, viewer=viewer, settlement=_settlement(status=GroupSettlementStatus.confirmed, confirmed_at=TODAY))
            with pytest.raises(GroupSettlementConfirmedError):
                await group_settlement_service.delete_settlement(AsyncMock(), GROUP_ID, 8, USER)


class TestWriteOff:
    # Seat 12 owes seat 11 thirty pesos — a write-off is capped at the balance, so these need one.
    _OWES_30 = [("ARS", 11, Decimal("0"), Decimal("30")), ("ARS", 12, Decimal("30"), Decimal("0"))]

    @pytest.mark.asyncio
    async def test_the_creditor_writes_it_off(self, monkeypatch):
        written = _wire(monkeypatch, viewer=_MEMBERS[0], positions=self._OWES_30)
        await group_settlement_service.record_write_off(
            AsyncMock(), GROUP_ID, USER, from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal("30.00"), currency="ARS"
        )
        assert written["row"].status == GroupSettlementStatus.written_off
        # No cash moved, so no account leg — a DB CHECK backs this, and a row with one would record a
        # movement that never happened.
        assert (written["row"].from_account_id, written["row"].to_account_id) == (None, None)

    @pytest.mark.asyncio
    async def test_the_debtor_cannot_write_off_their_own_debt(self, monkeypatch):
        # Giving up a claim is the creditor's to give up; the other way round is one person deciding
        # on somebody else's behalf.
        _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._OWES_30)
        with pytest.raises(GroupSettlementNotCreditorError):
            await group_settlement_service.record_write_off(
                AsyncMock(), GROUP_ID, USER, from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal("30.00"), currency="ARS"
            )

    @pytest.mark.asyncio
    async def test_only_the_creditor_may_take_a_write_off_back(self, monkeypatch):
        # Symmetric with recording it: taking back a forgiveness is theirs too.
        _wire(monkeypatch, viewer=_MEMBERS[1], settlement=_settlement(status=GroupSettlementStatus.written_off))
        with pytest.raises(GroupSettlementNotCreditorError):
            await group_settlement_service.delete_settlement(AsyncMock(), GROUP_ID, 8, USER)


class TestBalances:
    _POSITIONS = [
        ("ARS", 11, Decimal("30"), Decimal("90")),
        ("ARS", 12, Decimal("30"), Decimal("0")),
        ("ARS", 13, Decimal("30"), Decimal("0")),
        ("USD", 12, Decimal("0"), Decimal("10")),
        ("USD", 11, Decimal("10"), Decimal("0")),
    ]

    @pytest.mark.asyncio
    async def test_each_currency_is_its_own_bucket(self, monkeypatch):
        # D27: owing dollars while being owed pesos is a real state, and netting them would invent a
        # rate nobody agreed to. Member 11 is owed 60 ARS and owes 10 USD at the same time.
        _wire(monkeypatch, positions=self._POSITIONS)
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER)
        by_currency = {bucket.currency: bucket.my_balance for bucket in result.buckets}
        assert by_currency == {"ARS": Decimal("60"), "USD": Decimal("-10")}

    @pytest.mark.asyncio
    async def test_each_bucket_sums_to_zero(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER)
        for bucket in result.buckets:
            assert sum(row.amount for row in bucket.balances) == Decimal(0), bucket.currency

    @pytest.mark.asyncio
    async def test_income_alone_produces_a_balance(self, monkeypatch):
        """The service reading the INCOME aggregate at all, which a sweep found nothing exercised.

        A member who collected 90 of shared income while entitled to 30 owes the other two their
        shares — the mirror of fronting a bill. Dropping the income read from the derivation left every
        expense test green and this figure at zero, which is money nobody could see they were owed.
        """
        _wire(
            monkeypatch,
            income_positions=[
                ("ARS", 11, Decimal("30"), Decimal("90")),
                ("ARS", 12, Decimal("30"), Decimal("0")),
                ("ARS", 13, Decimal("30"), Decimal("0")),
            ],
        )
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER)
        ars = next(bucket for bucket in result.buckets if bucket.currency == "ARS")
        # Entitled 30 minus received 90 — the OPPOSITE direction from an expense, where fronting 90
        # against a 30 share leaves you owed 60. Reading the income columns the expense way would put
        # +60 here.
        assert ars.my_balance == Decimal("-60")
        assert {row.member_id: row.amount for row in ars.balances} == {11: Decimal("-60"), 12: Decimal("30"), 13: Decimal("30")}
        assert sum(row.amount for row in ars.balances) == Decimal(0)

    @pytest.mark.asyncio
    async def test_the_two_flows_net_in_one_bucket(self, monkeypatch):
        # One settle-up clears whatever the two add up to. Member 11 fronted a 90 expense (owed 60) and
        # collected 90 of income they were entitled to 30 of (owes 60), so they are square — and the
        # bucket disappears entirely, which is the state a group that has done both ends in.
        _wire(
            monkeypatch,
            positions=[("ARS", 11, Decimal("30"), Decimal("90")), ("ARS", 12, Decimal("60"), Decimal("0"))],
            income_positions=[("ARS", 11, Decimal("30"), Decimal("90")), ("ARS", 12, Decimal("60"), Decimal("0"))],
        )
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER)
        assert result.buckets == []

    @pytest.mark.asyncio
    async def test_a_bucket_only_income_opened_still_appears(self, monkeypatch):
        # The key set the derivation iterates has to be the UNION of both flows' keys: a currency only
        # income has been recorded in would otherwise vanish, taking its balance with it.
        _wire(
            monkeypatch,
            positions=[("ARS", 11, Decimal("30"), Decimal("30"))],
            income_positions=[("USD", 11, Decimal("0"), Decimal("40")), ("USD", 12, Decimal("40"), Decimal("0"))],
        )
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER)
        assert [bucket.currency for bucket in result.buckets] == ["USD"]

    @pytest.mark.asyncio
    async def test_the_suggestions_clear_the_bucket(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER)
        ars = next(bucket for bucket in result.buckets if bucket.currency == "ARS")
        assert [(s.from_member_id, s.to_member_id, s.amount) for s in ars.suggestions] == [(12, 11, Decimal("30")), (13, 11, Decimal("30"))]

    @pytest.mark.asyncio
    async def test_a_display_currency_converts_each_bucket_at_todays_rate(self, monkeypatch):
        """The path that 500s if the conversion is handed no date.

        A balance is a live position — the expenses behind it are already reduced to one figure per
        bucket, with no single date to convert at — so it converts at TODAY. Passing None instead
        reaches `bisect` inside the rate lookup and raises TypeError, which is a 500 on every request
        that asks for a display currency. Nothing else exercises it: the browser walk read the
        balances without one, and the buckets themselves need no rate at all.
        """
        _wire(monkeypatch, positions=self._POSITIONS)
        rates = {ExchangeRatePair.USD_ARS_MEP: [ExchangeRate(pair=ExchangeRatePair.USD_ARS_MEP, date=date(2026, 1, 1), rate=Decimal("1500"))]}
        monkeypatch.setattr(
            group_settlement_service.exchange_rate_service,
            "get_user_rate_lookup",
            AsyncMock(return_value=RateLookup("mep", rates)),
        )

        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER, currency="ARS")

        by_currency = {bucket.currency: (bucket.my_balance, bucket.my_converted_balance) for bucket in result.buckets}
        # The ARS bucket needs no conversion; the USD one is marked at the stored rate.
        assert by_currency["ARS"] == (Decimal("60"), Decimal("60"))
        assert by_currency["USD"] == (Decimal("-10"), Decimal("-15000.00"))
        assert result.skipped_currencies == []

    @pytest.mark.asyncio
    async def test_a_bucket_with_no_usable_rate_is_flagged_rather_than_guessed(self, monkeypatch):
        # Same contract the expenses list has: a row that cannot be converted reports null and names
        # its currency, instead of the response quietly omitting it or inventing a figure.
        _wire(monkeypatch, positions=self._POSITIONS)
        monkeypatch.setattr(
            group_settlement_service.exchange_rate_service,
            "get_user_rate_lookup",
            AsyncMock(return_value=RateLookup("mep", {})),
        )

        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER, currency="ARS")

        assert result.skipped_currencies == ["USD"]
        assert next(b.my_converted_balance for b in result.buckets if b.currency == "USD") is None

    @pytest.mark.asyncio
    async def test_a_group_that_is_square_has_no_buckets_at_all(self, monkeypatch):
        _wire(monkeypatch, positions=[("ARS", 11, Decimal("30"), Decimal("30"))])
        result = await group_settlement_service.get_balances(AsyncMock(), GROUP_ID, USER)
        assert result.buckets == []


class TestTheRemovalGuard:
    @pytest.mark.asyncio
    async def test_an_open_balance_refuses_the_removal(self, monkeypatch):
        _wire(monkeypatch, positions=[("ARS", 11, Decimal("0"), Decimal("30")), ("ARS", 12, Decimal("30"), Decimal("0"))])
        with pytest.raises(GroupBalanceOutstandingError) as exc:
            await group_settlement_service.ensure_no_outstanding_balance(AsyncMock(), [_MEMBERS[0]])
        # The message names the group, because a user in several needs to know which one to settle.
        assert exc.value.group_names == ["Casa"]

    @pytest.mark.asyncio
    async def test_a_square_seat_passes(self, monkeypatch):
        _wire(monkeypatch, positions=[("ARS", 11, Decimal("30"), Decimal("30"))])
        await group_settlement_service.ensure_no_outstanding_balance(AsyncMock(), [_MEMBERS[0]])

    @pytest.mark.asyncio
    async def test_somebody_elses_open_balance_does_not_block_this_seat(self, monkeypatch):
        # The guard is about the seat going away, not about the group being tidy — refusing on another
        # member's balance would make one person's debt everybody's problem.
        _wire(monkeypatch, positions=[("ARS", 12, Decimal("0"), Decimal("30")), ("ARS", 13, Decimal("30"), Decimal("0"))])
        await group_settlement_service.ensure_no_outstanding_balance(AsyncMock(), [_MEMBERS[0]])


class TestTheWriteOffCap:
    # Seat 12 owes seat 11 thirty pesos and ten dollars.
    _POSITIONS = [
        ("ARS", 11, Decimal("0"), Decimal("30")),
        ("ARS", 12, Decimal("30"), Decimal("0")),
        ("USD", 11, Decimal("0"), Decimal("10")),
        ("USD", 12, Decimal("10"), Decimal("0")),
    ]

    async def _write_off(self, amount: str, currency: str = "ARS"):
        return await group_settlement_service.record_write_off(
            AsyncMock(), GROUP_ID, USER, from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal(amount), currency=currency
        )

    @pytest.mark.asyncio
    async def test_writing_off_the_whole_balance_is_allowed(self, monkeypatch):
        written = _wire(monkeypatch, positions=self._POSITIONS)
        await self._write_off("30.00")
        assert written["row"].amount == Decimal("30.00")

    @pytest.mark.asyncio
    async def test_writing_off_part_of_it_is_allowed(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        await self._write_off("10.00")

    @pytest.mark.asyncio
    async def test_writing_off_more_than_the_balance_is_refused(self, monkeypatch):
        """The asymmetry with a payment, which is the whole point of the rule.

        An overpaying payment is legal and flips the bucket — real money moved. Forgiving more than you
        are owed would leave the person you forgave owed money BY you, out of nothing, which no act
        produces. One cent over is refused, because the boundary is the balance and not "roughly it".
        """
        _wire(monkeypatch, positions=self._POSITIONS)
        with pytest.raises(GroupWriteOffExceedsBalanceError) as caught:
            await self._write_off("30.01")
        assert caught.value.extra == {"outstanding": "30", "currency": "ARS"}

    @pytest.mark.asyncio
    async def test_the_cap_is_the_bucket_being_written_off_not_another(self, monkeypatch):
        # Balances never net across currencies, so the ten dollars owed is no licence to write off
        # more pesos. Reading the wrong bucket here would pass every same-currency test.
        _wire(monkeypatch, positions=self._POSITIONS)
        with pytest.raises(GroupWriteOffExceedsBalanceError):
            await self._write_off("40.00")
        await self._write_off("10.00", currency="USD")

    @pytest.mark.asyncio
    async def test_a_bucket_with_nothing_owed_refuses_any_write_off(self, monkeypatch):
        # Nobody owes anybody in euros, so there is no claim to give up.
        _wire(monkeypatch, positions=self._POSITIONS)
        with pytest.raises(GroupWriteOffExceedsBalanceError):
            await self._write_off("1.00", currency="EUR")

    @pytest.mark.asyncio
    async def test_the_cap_follows_the_DIRECTION_of_the_debt(self, monkeypatch):
        """Seat 11 owes seat 12 nothing, so 11 cannot forgive 12 anything.

        `_owed_between` is directional, and taking the bucket's magnitude instead would let the debtor
        write off their own debt by naming themselves as the creditor — which the permission check
        already refuses, so this is the guard behind it rather than a duplicate of it.
        """
        _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS)
        with pytest.raises(GroupWriteOffExceedsBalanceError):
            await group_settlement_service.record_write_off(
                AsyncMock(), GROUP_ID, USER, from_member_id=11, to_member_id=12, date=TODAY, amount=Decimal("5.00"), currency="ARS"
            )


class TestTheOverpayWaterfall:
    """One payment that clears more than the bucket it names.

    Seat 12 owes seat 11 thirty THOUSAND pesos and ten dollars. The rate is 1,037.50 rather than a
    round 1,000 on purpose: a round rate cannot tell a correct allocation from an incorrect one,
    because every rounding path agrees when the arithmetic comes out whole.
    """

    _POSITIONS = [
        ("ARS", 11, Decimal("0"), Decimal("30000")),
        ("ARS", 12, Decimal("30000"), Decimal("0")),
        ("USD", 11, Decimal("0"), Decimal("10")),
        ("USD", 12, Decimal("10"), Decimal("0")),
    ]
    # Clearing the dollar bucket costs 10 × 1037.50 = 10,375.00 pesos.
    _USD_COST = Decimal("10375.00")

    def _rates(self, monkeypatch, *, available: bool = True):
        rates = (
            {ExchangeRatePair.USD_ARS_MEP: [ExchangeRate(pair=ExchangeRatePair.USD_ARS_MEP, date=date(2026, 1, 1), rate=Decimal("1037.50"))]}
            if available
            else {}
        )
        monkeypatch.setattr(group_settlement_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=RateLookup("mep", rates)))

    async def _preview(self, **overrides):
        body = dict(from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal("30000.00"), currency="ARS")
        body.update(overrides)
        return await group_settlement_service.preview_waterfall(AsyncMock(), GROUP_ID, USER, **body)

    async def _record(self, **overrides):
        body = dict(from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal("30000.00"), currency="ARS")
        body.update(overrides)
        return await group_settlement_service.record_waterfall(AsyncMock(), GROUP_ID, USER, **body)


class TestThePreview(TestTheOverpayWaterfall):
    @pytest.mark.asyncio
    async def test_a_payment_that_does_not_exceed_the_bucket_has_no_plan(self, monkeypatch):
        # The ordinary case, and the signal the client uses to take the plain create path instead.
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("20000.00"))
        assert (plan.excess, plan.buckets, plan.leftover) == (Decimal("0"), [], Decimal("0"))

    @pytest.mark.asyncio
    async def test_paying_exactly_the_balance_has_no_plan_either(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("30000.00"))
        assert plan.excess == Decimal("0")

    @pytest.mark.asyncio
    async def test_an_overpayment_is_priced_against_the_other_bucket(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("45000.00"))
        assert plan.primary_outstanding == Decimal("30000")
        assert plan.excess == Decimal("15000.00")
        bucket = plan.buckets[0]
        # Two currencies in one row, and confusing them is what this asserts against: `outstanding`
        # and `amount` are dollars, `cost` and `applied_cost` pesos.
        assert (bucket.currency, bucket.outstanding, bucket.cost) == ("USD", Decimal("10"), self._USD_COST)
        assert (bucket.amount, bucket.applied_cost) == (Decimal("10"), self._USD_COST)
        # 15,000 covered the 10,375 the dollars cost; the rest is a credit in the currency paid.
        assert plan.leftover == Decimal("4625.00")

    @pytest.mark.asyncio
    async def test_an_excess_smaller_than_the_bucket_buys_part_of_it(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("35000.00"))
        bucket = plan.buckets[0]
        # 5,000 pesos buys 5000/1037.50 = 4.8192... dollars of the ten owed.
        assert bucket.amount == Decimal("4.82")
        assert bucket.applied_cost == Decimal("5000.00")
        assert plan.leftover == Decimal("0")

    @pytest.mark.asyncio
    async def test_unticking_a_bucket_leaves_it_listed_but_unapplied(self, monkeypatch):
        """The reason every reachable bucket comes back rather than only the applied ones.

        The client renders one list of checkboxes from one field. If unticking removed the bucket from
        the response the checkbox would vanish along with it, and there would be no way to tick it back.
        """
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("45000.00"), spillover_currencies=[])
        assert len(plan.buckets) == 1
        bucket = plan.buckets[0]
        assert (bucket.currency, bucket.selected) == ("USD", False)
        # Still priced, so the row can say what ticking it would cost.
        assert bucket.cost == self._USD_COST
        assert (bucket.amount, bucket.applied_cost) == (Decimal("0"), Decimal("0"))
        # Nothing absorbed it, so the whole excess is a credit.
        assert plan.leftover == Decimal("15000.00")

    @pytest.mark.asyncio
    async def test_a_bucket_with_no_rate_is_named_rather_than_guessed(self, monkeypatch):
        # Same posture as every other conversion in Renly: a missing rate is reported, never invented.
        # Moving real money at a made-up number is the one outcome this whole flow must not produce.
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch, available=False)
        plan = await self._preview(amount=Decimal("45000.00"))
        assert plan.skipped_currencies == ["USD"]
        assert plan.buckets == []
        assert plan.leftover == Decimal("15000.00")

    @pytest.mark.asyncio
    async def test_a_bucket_the_payer_is_OWED_in_is_not_a_candidate(self, monkeypatch):
        """Direction, which sums alone cannot see.

        Here seat 12 owes pesos but is OWED dollars. Applying a peso overpayment to the dollar bucket
        would increase what the payee owes them — money flowing the wrong way — so that bucket must not
        appear at all. `_owed_between` reads the settle-up plan, which is directional.
        """
        _wire(
            monkeypatch,
            positions=[
                ("ARS", 11, Decimal("0"), Decimal("30000")),
                ("ARS", 12, Decimal("30000"), Decimal("0")),
                ("USD", 12, Decimal("0"), Decimal("10")),
                ("USD", 11, Decimal("10"), Decimal("0")),
            ],
        )
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("45000.00"))
        assert plan.buckets == []
        assert plan.leftover == Decimal("15000.00")

    @pytest.mark.asyncio
    async def test_the_preview_writes_nothing(self, monkeypatch):
        written = _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        await self._preview(amount=Decimal("45000.00"))
        assert written["rows"] == []


class TestRecordingTheWaterfall(TestTheOverpayWaterfall):
    @pytest.mark.asyncio
    async def test_one_settlement_per_bucket_in_the_bucket_s_own_currency(self, monkeypatch):
        written = _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"))
        assert [(row.currency, row.amount) for row in written["rows"]] == [
            # The paid bucket carries its own balance PLUS the leftover, so it flips by 4,625.
            ("ARS", Decimal("34625.00")),
            ("USD", Decimal("10")),
        ]

    @pytest.mark.asyncio
    async def test_the_rows_account_for_exactly_what_was_paid(self, monkeypatch):
        """The invariant the whole feature rests on, asserted end to end rather than on the allocator.

        Each row's cost in the payment's currency must sum to the payment. The dollar row's cost is not
        its `amount` — that is dollars — so this reads the peso figure back off the cash leg, which is
        the only place the two meet.
        """
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="ARS"))
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"), from_account_id=5)
        rows = written["rows"]
        # A same-currency leg stores None, meaning "the account moved exactly what cleared the bucket".
        paid = [row.from_amount if row.from_amount is not None else row.amount for row in rows]
        assert sum(paid) == Decimal("45000.00")

    @pytest.mark.asyncio
    async def test_unticking_everything_is_a_single_overpaying_settlement(self, monkeypatch):
        # Which is exactly the behaviour before this PR existed: the bucket flips and nothing spills.
        written = _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"), spillover_currencies=[])
        assert [(row.currency, row.amount) for row in written["rows"]] == [("ARS", Decimal("45000.00"))]

    @pytest.mark.asyncio
    async def test_a_partial_payment_records_what_was_paid_not_the_balance(self, monkeypatch):
        # The `min` in `primary_amount`. Without it this path credits the payer with the whole 30,000
        # for a 12,000 payment — every overpay test stays green while partial payments silently
        # over-clear, which is the worst possible direction for this bug.
        written = _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        await self._record(amount=Decimal("12000.00"))
        assert [(row.currency, row.amount) for row in written["rows"]] == [("ARS", Decimal("12000.00"))]

    @pytest.mark.asyncio
    async def test_paying_only_to_clear_another_currency_writes_no_empty_row(self, monkeypatch):
        """Nothing owed in the currency being paid, and all of it spills.

        A zero-amount settlement is refused by the schema and means nothing anyway. The row is skipped
        rather than written at zero.
        """
        written = _wire(
            monkeypatch,
            positions=[("USD", 11, Decimal("0"), Decimal("10")), ("USD", 12, Decimal("10"), Decimal("0"))],
        )
        self._rates(monkeypatch)
        await self._record(amount=self._USD_COST)
        assert [(row.currency, row.amount) for row in written["rows"]] == [("USD", Decimal("10"))]

    @pytest.mark.asyncio
    async def test_auto_finalise_confirms_every_row_not_just_the_first(self, monkeypatch):
        written = _wire(monkeypatch, positions=self._POSITIONS, auto_finalise=True)
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"))
        assert all(row.status == GroupSettlementStatus.confirmed and row.confirmed_at is not None for row in written["rows"])

    @pytest.mark.asyncio
    async def test_notes_reach_every_row(self, monkeypatch):
        written = _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"), notes="Alquiler")
        assert {row.notes for row in written["rows"]} == {"Alquiler"}

    @pytest.mark.asyncio
    async def test_naming_the_other_party_s_account_is_refused(self, monkeypatch):
        # The same rule the plain create enforces: the two legs belong to two different people, and
        # neither can even see the other's accounts.
        _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="ARS"))
        self._rates(monkeypatch)
        with pytest.raises(GroupSettlementForeignLegError):
            await self._record(amount=Decimal("45000.00"), to_account_id=5)


class TestSplittingTheCashLeg(TestTheOverpayWaterfall):
    """One real payment out of ONE account, recorded across several rows.

    The payer states what left their account once. It is decomposed across the rows in proportion to
    what each consumed of the payment — never re-converted at a market rate, because a payment made at
    the rate their bank actually gave them must stay recorded at that rate.
    """

    @pytest.mark.asyncio
    async def test_a_foreign_account_s_total_is_split_across_the_rows_exactly(self, monkeypatch):
        # Paying the peso balance from a DOLLAR account: 45,000 pesos left it as $43.37, all told.
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="USD"))
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"), from_account_id=5, from_amount=Decimal("43.37"))
        rows = written["rows"]
        # The dollar row's bucket currency MATCHES the account's, so its leg normalises to None — the
        # account moved exactly what cleared that bucket. Its share is therefore read off the row.
        assert rows[0].currency == "ARS" and rows[0].from_amount == Decimal("33.37")
        assert rows[1].currency == "USD" and rows[1].from_amount is None and rows[1].amount == Decimal("10")
        # 33.37 + 10.00 = 43.37. Not a cent more or less than the payer said left their account.
        assert rows[0].from_amount + rows[1].amount == Decimal("43.37")

    @pytest.mark.asyncio
    async def test_the_payee_s_own_leg_is_split_the_same_way(self, monkeypatch):
        # Symmetric: either side may record the payment, and each states only their own account.
        written = _wire(monkeypatch, viewer=_MEMBERS[0], positions=self._POSITIONS, account=_account(6, currency="USD"))
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"), to_account_id=6, to_amount=Decimal("43.37"))
        rows = written["rows"]
        assert rows[0].to_amount == Decimal("33.37")
        assert rows[1].to_amount is None

    @pytest.mark.asyncio
    async def test_a_same_currency_account_stores_no_leg_amount_on_any_row(self, monkeypatch):
        """Every reader treats "a leg amount is set" as "this row crossed currencies".

        A second copy of the same figure would be a second thing to keep in step, and would make the
        peso row look like a conversion it never was.
        """
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="ARS"))
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"), from_account_id=5)
        rows = written["rows"]
        assert rows[0].from_amount is None
        # The dollar row DID cross, so it carries what those pesos were.
        assert rows[1].from_amount == Decimal("10375.00")
        assert all(row.from_account_id == 5 for row in rows)


class TestTwoBucketsAtOnce:
    """Three rows from one payment, which is what several assertions above cannot reach.

    Seat 12 owes seat 11 30,000 pesos, ten dollars AND forty reais. Two spillover buckets rather than
    one is the only way to see the ORDER the excess fills them in, and three rows is what makes the
    cash leg's proportional split leave a remainder to spread — with two rows the arithmetic happened
    to come out exact, so a sweep survived on removing the spread entirely.
    """

    _POSITIONS = [
        ("ARS", 11, Decimal("0"), Decimal("30000")),
        ("ARS", 12, Decimal("30000"), Decimal("0")),
        ("USD", 11, Decimal("0"), Decimal("10")),
        ("USD", 12, Decimal("10"), Decimal("0")),
        ("BRL", 11, Decimal("0"), Decimal("40")),
        ("BRL", 12, Decimal("40"), Decimal("0")),
    ]
    # 10 USD = 10,375.00 ARS at 1,037.50; 40 BRL = 7,642.73 ARS via USD at 5.43.
    _USD_COST = Decimal("10375.00")
    _BRL_COST = Decimal("7642.73")
    # Clears all three and leaves 500 pesos over.
    _AMOUNT = Decimal("48517.73")

    def _rates(self, monkeypatch):
        rates = {
            ExchangeRatePair.USD_ARS_MEP: [ExchangeRate(pair=ExchangeRatePair.USD_ARS_MEP, date=date(2026, 1, 1), rate=Decimal("1037.50"))],
            ExchangeRatePair.USD_BRL: [ExchangeRate(pair=ExchangeRatePair.USD_BRL, date=date(2026, 1, 1), rate=Decimal("5.43"))],
        }
        monkeypatch.setattr(group_settlement_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=RateLookup("mep", rates)))

    @pytest.mark.asyncio
    async def test_the_costliest_bucket_is_listed_and_filled_first(self, monkeypatch):
        # Ordering, which one bucket cannot show. Dollars cost more than reais, so they come first in
        # the response AND take the excess first — the list reads top to bottom as the money flows.
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await group_settlement_service.preview_waterfall(
            AsyncMock(), GROUP_ID, USER, from_member_id=12, to_member_id=11, date=TODAY, amount=self._AMOUNT, currency="ARS"
        )
        assert [(b.currency, b.cost) for b in plan.buckets] == [("USD", self._USD_COST), ("BRL", self._BRL_COST)]
        assert plan.leftover == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_a_partial_excess_fills_the_costliest_and_leaves_the_rest_untouched(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await group_settlement_service.preview_waterfall(
            AsyncMock(), GROUP_ID, USER, from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal("40375.00"), currency="ARS"
        )
        by_currency = {b.currency: (b.amount, b.applied_cost) for b in plan.buckets}
        assert by_currency["USD"] == (Decimal("10"), self._USD_COST)
        assert by_currency["BRL"] == (Decimal("0"), Decimal("0"))

    @pytest.mark.asyncio
    async def test_a_row_already_in_the_account_s_currency_moves_exactly_what_it_clears(self, monkeypatch):
        """Paying a dollar debt out of a dollar account crosses nothing, so no rate may be implied.

        Giving that row a proportional share of the payer's stated total instead would claim the
        account paid 8.58 dollars to clear a 10-dollar bucket — a contradiction the leg rule refuses
        outright, and rightly: within one currency a settlement moves exactly what it clears. So the
        dollar row takes its own amount, and the rows that DID cross split what is left.
        """
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="USD"))
        self._rates(monkeypatch)
        await group_settlement_service.record_waterfall(
            AsyncMock(),
            GROUP_ID,
            USER,
            from_member_id=12,
            to_member_id=11,
            date=TODAY,
            amount=self._AMOUNT,
            currency="ARS",
            from_account_id=5,
            from_amount=Decimal("40.14"),
        )
        rows = written["rows"]
        assert [row.currency for row in rows] == ["ARS", "USD", "BRL"]
        # None on the dollar row IS the statement that it crossed nothing; the other two carry what
        # those pesos and reais actually cost in dollars, and they split 40.14 − 10.00 between them.
        assert rows[1].from_amount is None
        assert rows[0].from_amount + rows[2].from_amount == Decimal("30.14")

    @pytest.mark.asyncio
    async def test_the_cash_leg_s_rounding_remainder_is_spread_so_the_parts_sum_exactly(self, monkeypatch):
        """The gap a mutation sweep found: with two parts the split came out exact on its own.

        Two complementary ratios round to the total almost always, so removing `spread_remainder`
        stayed green. THREE crossing rows is what shows it — here 30.04 euros splits into parts that
        naively sum to 30.03, and the missing cent has to land on the largest of them. Without the
        spread the payer's account would show a cent less leaving it than they said did: small, and
        wrong in the one place a person checks by hand.
        """
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="EUR"))
        self._rates(monkeypatch)
        await group_settlement_service.record_waterfall(
            AsyncMock(),
            GROUP_ID,
            USER,
            from_member_id=12,
            to_member_id=11,
            date=TODAY,
            amount=self._AMOUNT,
            currency="ARS",
            from_account_id=5,
            from_amount=Decimal("30.04"),
        )
        legs = [row.from_amount for row in written["rows"]]
        # 18.88 + 6.42 + 4.73 = 30.03. The cent goes to the largest part, making it 18.89.
        assert legs == [Decimal("18.89"), Decimal("6.42"), Decimal("4.73")]
        assert sum(legs) == Decimal("30.04")

    @pytest.mark.asyncio
    async def test_the_lifted_unit_comes_off_the_LARGEST_part(self, monkeypatch):
        """Which part pays for the lift, not merely that one does.

        With two rows the question cannot arise — lifting the only zero leaves exactly one other row to
        take it from, so a sweep survived on `max` → `min`. THREE rows separate them: 0.03 euros splits
        naively into 0.02 / 0.01 / 0.00, and taking the unit off the SMALLEST non-zero part would push
        that one to zero instead, recreating the very 500 the lift exists to prevent.
        """
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="EUR"))
        self._rates(monkeypatch)
        await group_settlement_service.record_waterfall(
            AsyncMock(),
            GROUP_ID,
            USER,
            from_member_id=12,
            to_member_id=11,
            date=TODAY,
            amount=self._AMOUNT,
            currency="ARS",
            from_account_id=5,
            from_amount=Decimal("0.03"),
        )
        legs = [row.from_amount for row in written["rows"]]
        assert legs == [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
        assert sum(legs) == Decimal("0.03")


class TestTheRateFollowsThePaymentDate:
    _POSITIONS = [
        ("ARS", 11, Decimal("0"), Decimal("30000")),
        ("ARS", 12, Decimal("30000"), Decimal("0")),
        ("USD", 11, Decimal("0"), Decimal("10")),
        ("USD", 12, Decimal("10"), Decimal("0")),
    ]

    def _rates(self, monkeypatch):
        # The peso moved a long way between January and May, which is the point: which rate applies is
        # a real difference in what the payer gets for their money, not a rounding detail.
        rates = {
            ExchangeRatePair.USD_ARS_MEP: [
                ExchangeRate(pair=ExchangeRatePair.USD_ARS_MEP, date=date(2026, 1, 1), rate=Decimal("900.00")),
                ExchangeRate(pair=ExchangeRatePair.USD_ARS_MEP, date=date(2026, 5, 1), rate=Decimal("1500.00")),
            ]
        }
        monkeypatch.setattr(group_settlement_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=RateLookup("mep", rates)))

    async def _preview(self, when: date):
        return await group_settlement_service.preview_waterfall(
            AsyncMock(), GROUP_ID, USER, from_member_id=12, to_member_id=11, date=when, amount=Decimal("50000.00"), currency="ARS"
        )

    @pytest.mark.asyncio
    async def test_a_back_dated_payment_converts_at_the_rate_in_force_then(self, monkeypatch):
        """Not today's rate, which is what `get_balances` deliberately uses.

        The two are different questions and the difference is principled: a displayed BALANCE is a live
        position with no single date behind it, whereas a payment happened on a day, and the rate that
        matters is the one in force when the money actually moved — which is how every other
        cross-currency figure in Renly is recorded.
        """
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(date(2026, 2, 15))
        assert plan.buckets[0].cost == Decimal("9000.00")

    @pytest.mark.asyncio
    async def test_a_payment_made_later_converts_at_the_later_rate(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(date(2026, 6, 1))
        assert plan.buckets[0].cost == Decimal("15000.00")


class TestThePreviewMatchesTheWrite(TestTheOverpayWaterfall):
    """The number the payer confirms is the number that gets recorded.

    `primary_amount` exists so the confirm step can name the settlement against the paid bucket without
    re-deriving it — one function answers it for both paths, because two derivations of a figure
    somebody agrees to and then has recorded are two things that can disagree about what was agreed.
    """

    @pytest.mark.parametrize(
        ("amount", "spillover"),
        [
            ("45000.00", None),  # overpays, everything ticked
            ("45000.00", []),  # overpays, nothing ticked
            ("40375.00", None),  # overpays by exactly the dollar bucket
            ("30000.00", None),  # pays it off exactly
            ("12000.00", None),  # a partial payment
        ],
    )
    @pytest.mark.asyncio
    async def test_the_planned_primary_amount_is_what_gets_written(self, monkeypatch, amount, spillover):
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal(amount), spillover_currencies=spillover)

        written = _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        await self._record(amount=Decimal(amount), spillover_currencies=spillover)

        rows_in_paid_currency = [row.amount for row in written["rows"] if row.currency == "ARS"]
        assert rows_in_paid_currency == ([plan.primary_amount] if plan.primary_amount > Decimal("0") else [])

    @pytest.mark.asyncio
    async def test_a_payment_purely_for_another_currency_plans_no_row_in_the_one_paid(self, monkeypatch):
        _wire(monkeypatch, positions=[("USD", 11, Decimal("0"), Decimal("10")), ("USD", 12, Decimal("10"), Decimal("0"))])
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("10375.00"))
        assert plan.primary_amount == Decimal("0")

    @pytest.mark.asyncio
    async def test_every_planned_bucket_amount_is_what_gets_written(self, monkeypatch):
        _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        plan = await self._preview(amount=Decimal("35000.00"))

        written = _wire(monkeypatch, positions=self._POSITIONS)
        self._rates(monkeypatch)
        await self._record(amount=Decimal("35000.00"))

        planned = {bucket.currency: bucket.amount for bucket in plan.buckets if bucket.amount > Decimal("0")}
        assert {row.currency: row.amount for row in written["rows"] if row.currency != "ARS"} == planned


class TestALegTotalSmallerThanThePaymentItself(TestTheOverpayWaterfall):
    """A stated cash total that the payment's own same-currency rows already exceed.

    Paying from a USD account while the excess spills into the USD bucket means part of the payment
    leaves that account in dollars, one for one — 9.74 of them here. Saying only 5.00 left in total is
    not a smaller payment, it is an impossible statement, and the arithmetic that follows hands the
    remaining rows a NEGATIVE leg.

    Reachable, and it lands on a DB CHECK (`group_settlements_positive_legs`) rather than a message —
    a 500 on a form somebody filled in wrong.
    """

    @pytest.mark.parametrize("stated", ["5.00", "9.74", "9.75"])
    @pytest.mark.asyncio
    async def test_it_is_refused_rather_than_left_to_the_database(self, monkeypatch, stated):
        _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="USD"))
        self._rates(monkeypatch)
        with pytest.raises(GroupSettlementLegTotalTooSmallError):
            await self._record(amount=Decimal("45000.00"), from_account_id=5, from_amount=Decimal(stated))

    @pytest.mark.asyncio
    async def test_a_total_that_covers_them_is_allowed(self, monkeypatch):
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="USD"))
        self._rates(monkeypatch)
        await self._record(amount=Decimal("45000.00"), from_account_id=5, from_amount=Decimal("29.50"))
        # 19.50 on the peso row + the 10.00 the dollar row moves on its own = 29.50, to the cent.
        assert written["rows"][0].from_amount == Decimal("19.50")
        assert written["rows"][1].from_amount is None
        assert written["rows"][1].amount == Decimal("10")

    @pytest.mark.asyncio
    async def test_a_payment_wholly_in_the_account_s_own_currency_needs_no_remainder(self, monkeypatch):
        # Every row is same-currency, so there is nothing left to divide and nothing to refuse.
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="ARS"))
        self._rates(monkeypatch)
        await self._record(amount=Decimal("30000.00"), from_account_id=5)
        assert [row.from_amount for row in written["rows"]] == [None]


class TestEveryRowMovesSomething:
    """A part of the payment too small to reach the account's smallest unit.

    NOT only an absurd figure: a fifteen-peso row paid from a dollar account really is worth less than
    a cent, so refusing outright would block a legitimate small payment. One minor unit is the honest
    floor for money that did move — taken off the largest part, never added, so the total the payer
    stated survives to the cent.

    The alternative is a row recording that it moved nothing, which `group_settlements_positive_legs`
    refuses as a 500.
    """

    _POSITIONS = [
        ("ARS", 11, Decimal("0"), Decimal("30000")),
        ("ARS", 12, Decimal("30000"), Decimal("0")),
        ("USD", 11, Decimal("0"), Decimal("10")),
        ("USD", 12, Decimal("10"), Decimal("0")),
    ]

    def _rates(self, monkeypatch):
        rates = {ExchangeRatePair.USD_ARS_MEP: [ExchangeRate(pair=ExchangeRatePair.USD_ARS_MEP, date=date(2026, 1, 1), rate=Decimal("1037.50"))]}
        monkeypatch.setattr(group_settlement_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=RateLookup("mep", rates)))

    async def _record(self, **overrides):
        body = dict(from_member_id=12, to_member_id=11, date=TODAY, amount=Decimal("45000.00"), currency="ARS")
        body.update(overrides)
        return await group_settlement_service.record_waterfall(AsyncMock(), GROUP_ID, USER, **body)

    @pytest.mark.asyncio
    async def test_a_share_below_one_minor_unit_is_lifted_rather_than_recorded_as_nothing(self, monkeypatch):
        # A EUR account, so BOTH rows cross. Two cents over two rows whose costs are 30,000 and 10,375
        # would naively be 0.02 and 0.00 — the smaller row rounds away entirely.
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="EUR"))
        self._rates(monkeypatch)
        await self._record(from_account_id=5, from_amount=Decimal("0.02"))
        legs = [row.from_amount for row in written["rows"]]
        assert legs == [Decimal("0.01"), Decimal("0.01")]
        # The stated total survives exactly: the lifted unit came OFF the largest part, not out of thin air.
        assert sum(legs) == Decimal("0.02")

    @pytest.mark.asyncio
    async def test_a_total_that_cannot_give_every_row_a_unit_is_refused(self, monkeypatch):
        # One cent over two rows: there is no split, so this is refused rather than lifted. The minimum
        # the error names is exactly right — two rows, one unit each.
        _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="EUR"))
        self._rates(monkeypatch)
        with pytest.raises(GroupSettlementLegTotalTooSmallError) as caught:
            await self._record(from_account_id=5, from_amount=Decimal("0.01"))
        assert caught.value.extra == {"minimum": "0.02", "currency": "EUR"}

    @pytest.mark.asyncio
    async def test_an_extreme_cost_ratio_is_lifted_too_not_only_a_tiny_total(self, monkeypatch):
        """The case the threshold alone does not catch, which is why the floor exists as well.

        At exactly the minimum, a lopsided pair of costs still rounds the smaller row to nothing: the
        naive split of two cents across 30,000 and 10,375 gives 0.02 and 0.00. Passing the threshold is
        not the same as every row getting something.
        """
        written = _wire(monkeypatch, viewer=_MEMBERS[1], positions=self._POSITIONS, account=_account(5, user_id=2, currency="EUR"))
        self._rates(monkeypatch)
        await self._record(from_account_id=5, from_amount=Decimal("0.02"))
        assert all(row.from_amount > Decimal("0") for row in written["rows"])
