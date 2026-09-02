from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    AccountCurrencyMismatchError,
    NotFoundError,
    SharedIncomeBeforeAccountOpenedError,
    SharedIncomeDestinationPotNotDividedError,
    SharedIncomeDestinationScopeError,
    SharedIncomeDistributedSharedAccountError,
    SharedIncomeJointAccountRequiredError,
    SharedIncomeJointReceiverError,
    SharedIncomeReceiverRequiredError,
    SharedIncomeSourceScopeError,
)
from app.models.account import Account, AccountType
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.group_money_settings import SplitMethod
from app.models.investment import Investment, InvestmentCategory
from app.models.pot import OwnershipEventType, Pot, PotOwnershipEvent
from app.models.shared_income import IncomeDestination, SharedIncome
from app.models.user import User
from app.schemas.shared_income import SharedIncomeSplitInput
from app.services import shared_income_service

# Where the money ended up and who holds it — the half of shared income the split figures cannot say,
# and the mirror of what the shared-expense tests drive from the funding side. Persistence is mocked;
# the SQL these drive is proved against a real database in tests/integration.
#
# Every assertion below reads the rows the service BUILT rather than a stubbed response, because a
# create that dropped `received_amount` entirely would return the same response either way.

GROUP_ID = 3
USER = User(id=1, name="S", email="u@test", password_hash="x", session_epoch=0)
TODAY = date(2026, 6, 1)


def _member(member_id: int, *, user_id: int | None = None, is_active: bool = True) -> GroupMember:
    return GroupMember(
        id=member_id, group_id=GROUP_ID, user_id=user_id, display_name=f"M{member_id}", role=GroupMemberRole.member, is_active=is_active
    )


# Santi's seat, plus a second account-holder and a name-only placeholder.
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


def _investment(investment_id: int, *, pot_id: int | None = 9, user_id: int | None = None) -> Investment:
    return Investment(
        id=investment_id,
        user_id=user_id,
        pot_id=pot_id,
        created_by=1,
        name=f"Flat {investment_id}",
        category=InvestmentCategory.real_estate,
        base_currency="ARS",
    )


# Stubs everything create_income reaches for. Each keyword replaces one collaborator, so a test names
# only the thing it is about. `pot` answers pot_repository for BOTH the destination pot and the source
# asset's pot, which is what makes `source_pot` a separate keyword when the two must differ.
def _wire(monkeypatch, *, account=None, pot=None, events=(), members=_MEMBERS, investment=None, source_pot=...):
    monkeypatch.setattr(
        shared_income_service.group_service,
        "require_member",
        AsyncMock(return_value=(Group(id=GROUP_ID, name="Casa", kind=GroupKind.household), members[0])),
    )
    monkeypatch.setattr(shared_income_service.group_repository, "list_members", AsyncMock(return_value=list(members)))
    monkeypatch.setattr(shared_income_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=account))
    monkeypatch.setattr(shared_income_service.investment_repository, "get_by_id_any_scope", AsyncMock(return_value=investment))
    pots = [pot if source_pot is ... else source_pot, pot]
    monkeypatch.setattr(shared_income_service.pot_repository, "get_by_id", AsyncMock(side_effect=lambda *_a, **_k: pots.pop(0) if pots else pot))
    monkeypatch.setattr(shared_income_service.pot_ownership_service.pot_ownership_repository, "list_by_pot", AsyncMock(return_value=list(events)))
    written: dict = {}

    async def _create(_session, income: SharedIncome) -> SharedIncome:
        income.id = 77
        written["income"] = income
        return income

    async def _create_splits(_session, splits):
        written["splits"] = splits
        return splits

    monkeypatch.setattr(shared_income_service.shared_income_repository, "create", _create)
    monkeypatch.setattr(shared_income_service.shared_income_repository, "create_splits", _create_splits)
    return written


async def _create(_written, **overrides):
    body = dict(
        date=TODAY,
        amount=Decimal("90.00"),
        currency="ARS",
        split_method=SplitMethod.equal,
        splits=[SharedIncomeSplitInput(member_id=11), SharedIncomeSplitInput(member_id=12), SharedIncomeSplitInput(member_id=13)],
        destination=IncomeDestination.distributed,
        received_by_member_id=11,
    )
    body.update(overrides)
    return await shared_income_service.create_income(AsyncMock(), GROUP_ID, USER, **body)


def _positions(written) -> dict[int, tuple[Decimal, Decimal]]:
    return {split.member_id: (split.amount, split.received_amount) for split in written["splits"]}


class TestOneMemberCollectsIt:
    @pytest.mark.asyncio
    async def test_the_recipient_holds_the_whole_received_amount(self, monkeypatch):
        written = _wire(monkeypatch)
        await _create(written)
        assert _positions(written) == {
            11: (Decimal("30.00"), Decimal("90.00")),
            12: (Decimal("30.00"), Decimal("0")),
            13: (Decimal("30.00"), Decimal("0")),
        }

    @pytest.mark.asyncio
    async def test_both_columns_sum_to_the_income(self, monkeypatch):
        written = _wire(monkeypatch)
        await _create(written)
        assert sum(split.amount for split in written["splits"]) == Decimal("90.00")
        assert sum(split.received_amount for split in written["splits"]) == Decimal("90.00")

    @pytest.mark.asyncio
    async def test_the_collector_owes_the_others_their_shares(self, monkeypatch):
        # The whole reason `received_amount` exists. Without it member 11 would report 30 of income
        # while their account really gained 90, and members 12 and 13 would report 30 each with
        # nothing backing it.
        written = _wire(monkeypatch)
        await _create(written)
        balances = {member_id: entitled - received for member_id, (entitled, received) in _positions(written).items()}
        assert balances == {11: Decimal("-60.00"), 12: Decimal("30.00"), 13: Decimal("30.00")}
        assert sum(balances.values()) == Decimal("0")

    @pytest.mark.asyncio
    async def test_a_collector_entitled_to_nothing_still_gets_a_row(self, monkeypatch):
        # A custodian who collects the rent and takes no share of it. The mirror of a payer who took no
        # part in an expense (D33), and the row that carries the whole debt.
        written = _wire(monkeypatch)
        await _create(
            written,
            splits=[SharedIncomeSplitInput(member_id=12), SharedIncomeSplitInput(member_id=13)],
            received_by_member_id=11,
        )
        assert _positions(written) == {
            11: (Decimal("0"), Decimal("90.00")),
            12: (Decimal("45.00"), Decimal("0")),
            13: (Decimal("45.00"), Decimal("0")),
        }

    @pytest.mark.asyncio
    async def test_no_recipient_and_no_shared_account_is_refused(self, monkeypatch):
        written = _wire(monkeypatch)
        with pytest.raises(SharedIncomeReceiverRequiredError):
            await _create(written, received_by_member_id=None)

    @pytest.mark.asyncio
    async def test_the_derived_recipient_is_reported(self, monkeypatch):
        written = _wire(monkeypatch)
        response = await _create(written)
        assert (response.received_by_member_id, response.received_by_display_name) == (11, "M11")
        assert response.destination == IncomeDestination.distributed

    @pytest.mark.asyncio
    async def test_my_share_is_the_ENTITLEMENT_not_what_reached_me(self, monkeypatch):
        # The collector's two figures differ — entitled to 30, holding 90 — which is what makes this
        # able to fail. `my_share` is what lands in their own /income list, so reporting the received
        # figure would tell them they earned three times their share.
        written = _wire(monkeypatch)
        response = await _create(written, received_by_member_id=11)
        assert response.my_share == Decimal("30.00")
        assert next(s for s in response.splits if s.member_id == 11).received_amount == Decimal("90.00")


class TestTheDestinationAccount:
    @pytest.mark.asyncio
    async def test_a_private_account_must_belong_to_the_recipient(self, monkeypatch):
        written = _wire(monkeypatch, account=_account(5, user_id=2))
        with pytest.raises(NotFoundError):
            await _create(written, received_by_member_id=11, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_the_recipients_own_account_is_accepted(self, monkeypatch):
        written = _wire(monkeypatch, account=_account(5, user_id=1))
        await _create(written, received_by_member_id=11, paid_to_account_id=5)
        assert written["income"].paid_to_account_id == 5

    @pytest.mark.asyncio
    async def test_the_currency_must_match_the_account(self, monkeypatch):
        written = _wire(monkeypatch, account=_account(5, user_id=1, currency="USD"))
        with pytest.raises(AccountCurrencyMismatchError):
            await _create(written, received_by_member_id=11, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_it_cannot_be_dated_before_the_account_opened(self, monkeypatch):
        written = _wire(monkeypatch, account=_account(5, user_id=1, opening=date(2026, 5, 1)))
        with pytest.raises(SharedIncomeBeforeAccountOpenedError):
            await _create(written, received_by_member_id=11, paid_to_account_id=5, date=date(2026, 4, 30))

    @pytest.mark.asyncio
    async def test_a_placeholder_cannot_name_an_account(self, monkeypatch):
        # A name-only seat has no linked user, so no account can be theirs — refused by the ownership
        # check without a special case.
        written = _wire(monkeypatch, account=_account(5, user_id=1))
        with pytest.raises(NotFoundError):
            await _create(written, received_by_member_id=13, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_naming_a_pot_account_while_distributing_is_refused_by_its_own_name(self, monkeypatch):
        # The ownership check would refuse it too (a pot account has no owner at all), but as a bare
        # "not found" that says nothing about what to do instead.
        written = _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9))
        with pytest.raises(SharedIncomeDistributedSharedAccountError):
            await _create(written, received_by_member_id=11, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_no_account_at_all_is_legal(self, monkeypatch):
        # Rent handed over in cash still divides, exactly as an expense paid outside Renly still does.
        written = _wire(monkeypatch)
        await _create(written, paid_to_account_id=None)
        assert written["income"].paid_to_account_id is None


class TestItStaysJoint:
    _POT = Pot(id=9, group_id=GROUP_ID, base_currency="ARS")

    @pytest.mark.asyncio
    async def test_the_pots_owners_receive_it_in_their_proportions(self, monkeypatch):
        # 60/40, which is what makes this test able to fail: equal owners would produce the same rows
        # as an equal split and prove nothing about whose proportions were read.
        written = _wire(
            monkeypatch,
            account=_account(5, user_id=None, pot_id=9),
            pot=self._POT,
            events=[_event(11, "60"), _event(12, "40")],
        )
        await _create(
            written,
            destination=IncomeDestination.joint,
            received_by_member_id=None,
            paid_to_account_id=5,
            splits=[SharedIncomeSplitInput(member_id=11), SharedIncomeSplitInput(member_id=12)],
        )
        assert _positions(written) == {11: (Decimal("45.00"), Decimal("54.00")), 12: (Decimal("45.00"), Decimal("36.00"))}
        # An equal split of jointly-received money is a real balance: member 11 got 54 of pot value
        # and agreed to 45, so they owe 9 to member 12.
        assert sum(received for _, received in _positions(written).values()) == Decimal("90.00")

    @pytest.mark.asyncio
    async def test_the_pot_proportions_and_the_split_agreeing_leaves_nobody_owing(self, monkeypatch):
        # F1's common case: the split the form pre-fills IS the pot's proportions, so the row balances
        # to zero on every member and no settle-up is needed.
        written = _wire(
            monkeypatch,
            account=_account(5, user_id=None, pot_id=9),
            pot=self._POT,
            events=[_event(11, "60"), _event(12, "40")],
        )
        await _create(
            written,
            destination=IncomeDestination.joint,
            received_by_member_id=None,
            paid_to_account_id=5,
            split_method=SplitMethod.percentage,
            splits=[
                SharedIncomeSplitInput(member_id=11, figure=Decimal("60")),
                SharedIncomeSplitInput(member_id=12, figure=Decimal("40")),
            ],
        )
        assert all(entitled == received for entitled, received in _positions(written).values())

    @pytest.mark.asyncio
    async def test_the_pinned_proportions_are_read_at_the_incomes_own_date(self, monkeypatch):
        # Pinned rather than derived on read: the ownership ledger is REPLAYED, so a back-dated event
        # would otherwise silently rewrite a balance two people had already agreed on.
        written = _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[_event(11, "50"), _event(12, "50")])
        await _create(
            written,
            destination=IncomeDestination.joint,
            received_by_member_id=None,
            paid_to_account_id=5,
            date=date(2026, 3, 15),
            splits=[SharedIncomeSplitInput(member_id=11), SharedIncomeSplitInput(member_id=12)],
        )
        ledger = shared_income_service.pot_ownership_service.pot_ownership_repository
        assert ledger.list_by_pot.await_args.kwargs == {"as_of_date": date(2026, 3, 15)}

    @pytest.mark.asyncio
    async def test_a_pot_with_ONE_owner_still_names_no_recipient(self, monkeypatch):
        # The case that reading the splits alone gets wrong: a single owner receives the whole amount,
        # which is indistinguishable from one person collecting it. A pot with one owner is a supported
        # state — it is where a buy-out ends — so it is the DESTINATION that decides, not the shape.
        written = _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[_event(11, "100")])
        response = await _create(
            written,
            destination=IncomeDestination.joint,
            received_by_member_id=None,
            paid_to_account_id=5,
            splits=[SharedIncomeSplitInput(member_id=11)],
        )
        assert response.received_by_member_id is None
        assert response.received_by_display_name is None

    @pytest.mark.asyncio
    async def test_an_owner_who_has_LEFT_the_group_still_receives_their_share(self, monkeypatch):
        # Their units are genuinely theirs, so income arriving really does reach their share. Excluding
        # them would leave the received figures short of the total and break the zero-sum identity.
        members = [_member(11, user_id=1), _member(12, user_id=2, is_active=False)]
        written = _wire(
            monkeypatch,
            account=_account(5, user_id=None, pot_id=9),
            pot=self._POT,
            events=[_event(11, "50"), _event(12, "50")],
            members=members,
        )
        await _create(
            written,
            destination=IncomeDestination.joint,
            received_by_member_id=None,
            paid_to_account_id=5,
            splits=[SharedIncomeSplitInput(member_id=11)],
        )
        assert _positions(written) == {11: (Decimal("90.00"), Decimal("45.00")), 12: (Decimal("0"), Decimal("45.00"))}

    @pytest.mark.asyncio
    async def test_but_a_departed_seat_still_cannot_be_NAMED(self, monkeypatch):
        # The other half of the same rule: a seat the REQUEST names is a choice being made now.
        members = [_member(11, user_id=1), _member(12, user_id=2, is_active=False)]
        written = _wire(monkeypatch, members=members)
        with pytest.raises(NotFoundError):
            await _create(written, splits=[SharedIncomeSplitInput(member_id=12)], received_by_member_id=11)

    @pytest.mark.asyncio
    async def test_the_currency_must_match_the_shared_account_too(self, monkeypatch):
        # The same rule as on the distributed branch, and it needs its own case: these sums carry one
        # amount, so a mismatched link would add a foreign-currency figure straight to the pot's
        # account. A sweep found this branch's check uncovered.
        written = _wire(
            monkeypatch,
            account=_account(5, user_id=None, pot_id=9, currency="USD"),
            pot=self._POT,
            events=[_event(11, "100")],
        )
        with pytest.raises(AccountCurrencyMismatchError):
            await _create(written, destination=IncomeDestination.joint, received_by_member_id=None, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_naming_a_recipient_as_well_is_refused(self, monkeypatch):
        written = _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[_event(11, "100")])
        with pytest.raises(SharedIncomeJointReceiverError):
            await _create(written, destination=IncomeDestination.joint, received_by_member_id=11, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_joint_with_no_account_is_refused(self, monkeypatch):
        # Joint money is money in a pot, and a pot is worth what its holdings are worth — so joint
        # income with nowhere to land would claim every owner's share rose while no figure moved.
        written = _wire(monkeypatch)
        with pytest.raises(SharedIncomeJointAccountRequiredError):
            await _create(written, destination=IncomeDestination.joint, received_by_member_id=None, paid_to_account_id=None)

    @pytest.mark.asyncio
    async def test_joint_into_a_members_PRIVATE_account_is_refused(self, monkeypatch):
        # Not a pot's account, so it is not joint money — the same refusal, because the instruction is
        # the same: pick one of the group's shared accounts.
        written = _wire(monkeypatch, account=_account(5, user_id=1))
        with pytest.raises(SharedIncomeJointAccountRequiredError):
            await _create(written, destination=IncomeDestination.joint, received_by_member_id=None, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_an_undivided_pot_is_refused(self, monkeypatch):
        # Crediting nobody would leave the received figures at zero against a total of 90, and the
        # identity the whole feature rests on would hold "except when".
        written = _wire(monkeypatch, account=_account(5, user_id=None, pot_id=9), pot=self._POT, events=[])
        with pytest.raises(SharedIncomeDestinationPotNotDividedError):
            await _create(written, destination=IncomeDestination.joint, received_by_member_id=None, paid_to_account_id=5)

    @pytest.mark.asyncio
    async def test_a_pot_in_another_group_is_refused(self, monkeypatch):
        written = _wire(
            monkeypatch,
            account=_account(5, user_id=None, pot_id=9),
            pot=Pot(id=9, group_id=99, base_currency="ARS"),
            events=[_event(11, "100")],
        )
        with pytest.raises(SharedIncomeDestinationScopeError):
            await _create(written, destination=IncomeDestination.joint, received_by_member_id=None, paid_to_account_id=5)


class TestTheSourceAsset:
    @pytest.mark.asyncio
    async def test_a_holding_of_this_groups_pot_is_accepted(self, monkeypatch):
        written = _wire(monkeypatch, pot=Pot(id=9, group_id=GROUP_ID, base_currency="ARS"), investment=_investment(4))
        response = await _create(written, source_investment_id=4)
        assert written["income"].source_investment_id == 4
        assert response.source_investment_name == "Flat 4"

    @pytest.mark.asyncio
    async def test_a_PRIVATE_investment_is_refused(self, monkeypatch):
        # V1: the source is stored on a row the whole group reads and its NAME is on the response, so a
        # private holding named here would put it in front of people who cannot see it.
        written = _wire(monkeypatch, investment=_investment(4, pot_id=None, user_id=1))
        with pytest.raises(SharedIncomeSourceScopeError):
            await _create(written, source_investment_id=4)

    @pytest.mark.asyncio
    async def test_a_holding_of_ANOTHER_groups_pot_is_refused(self, monkeypatch):
        written = _wire(monkeypatch, investment=_investment(4), source_pot=Pot(id=9, group_id=99, base_currency="ARS"))
        with pytest.raises(SharedIncomeSourceScopeError):
            await _create(written, source_investment_id=4)

    @pytest.mark.asyncio
    async def test_an_unreachable_investment_is_refused_the_same_way(self, monkeypatch):
        # Indistinguishable from a foreign one by design: an investment the caller cannot see is
        # invisible rather than absent.
        written = _wire(monkeypatch, investment=None)
        with pytest.raises(SharedIncomeSourceScopeError):
            await _create(written, source_investment_id=4)

    @pytest.mark.asyncio
    async def test_no_source_is_legal(self, monkeypatch):
        written = _wire(monkeypatch)
        response = await _create(written, source_investment_id=None)
        assert written["income"].source_investment_id is None
        assert response.source_investment_name is None


class TestSeatsAreCheckedAgainstThisGroup:
    @pytest.mark.asyncio
    async def test_a_seat_from_another_group_is_refused(self, monkeypatch):
        written = _wire(monkeypatch)
        with pytest.raises(NotFoundError):
            await _create(written, splits=[SharedIncomeSplitInput(member_id=404)])

    @pytest.mark.asyncio
    async def test_a_recipient_from_another_group_is_refused(self, monkeypatch):
        written = _wire(monkeypatch)
        with pytest.raises(NotFoundError):
            await _create(written, received_by_member_id=404)
