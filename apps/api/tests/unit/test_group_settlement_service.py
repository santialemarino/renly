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
    GroupSettlementLegWithoutAccountError,
    GroupSettlementNotCreditorError,
    GroupSettlementNotPayeeError,
    GroupSettlementSameMemberError,
    GroupSettlementWriteOffHasNoLegError,
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
def _wire(monkeypatch, *, viewer=_MEMBERS[0], account=None, auto_finalise=False, settlement=None, positions=None):
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
    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "list_movements_by_groups", AsyncMock(return_value=[]))
    monkeypatch.setattr(group_settlement_service, "exchange_rate_service", AsyncMock())
    written: dict = {}

    async def _create(_session, row: GroupSettlement) -> GroupSettlement:
        row.id = 8
        written["row"] = row
        return row

    monkeypatch.setattr(group_settlement_service.group_settlement_repository, "create", _create)
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
    @pytest.mark.asyncio
    async def test_the_creditor_writes_it_off(self, monkeypatch):
        written = _wire(monkeypatch, viewer=_MEMBERS[0])
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
        _wire(monkeypatch, viewer=_MEMBERS[1])
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
