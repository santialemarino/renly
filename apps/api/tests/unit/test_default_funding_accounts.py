from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.domain import AccountCardExclusivityError, AccountCurrencyMismatchError
from app.models.account import Account, AccountType
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseEntry
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.installment import InstallmentCreate, InstallmentUpdate
from app.schemas.payment_obligation import PaymentObligationCreate, PaymentObligationUpdate
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate
from app.services import (
    auto_expense_service,
    credit_card_service,
    installment_service,
    payment_obligation_service,
    subscription_service,
)

# Conveniences batch: an optional default funding account on a credit card (pre-fills the settlement's
# "Paid from") and on each recurring plan (the scheduler links it onto every charge it emits, so an
# auto-generated expense decrements the balance it really came from). Two rules everywhere: the account
# must be denominated in the card's / plan's own currency, and a CARD-paid plan never names one — its
# cash leg lands at the card settlement instead. Persistence is mocked.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _account(**overrides) -> Account:
    data = dict(
        id=7,
        user_id=1,
        name="Caja $",
        type=AccountType.bank,
        currency="ARS",
        opening_balance=Decimal("1000"),
        opening_date=date(2026, 1, 1),
    )
    data.update(overrides)
    return Account(**data)


def _card(**overrides) -> CreditCard:
    data = dict(id=5, user_id=1, name="Visa", closing_day=25, due_day=10, currency="ARS")
    data.update(overrides)
    return CreditCard(**data)


def _subscription(**overrides) -> Subscription:
    data = dict(
        id=3,
        user_id=1,
        name="Netflix",
        amount=Decimal("100"),
        currency="ARS",
        billing_cycle="monthly",
        next_billing_date=date(2026, 8, 1),
        anchor_day=1,
        payment_method="debit",
    )
    data.update(overrides)
    return Subscription(**data)


def _installment(**overrides) -> Installment:
    data = dict(
        id=4,
        user_id=1,
        name="TV",
        total_amount=Decimal("1200"),
        installment_amount=Decimal("100"),
        currency="ARS",
        installments_count=12,
        start_date=date(2026, 1, 10),
        payment_method="debit",
    )
    data.update(overrides)
    return Installment(**data)


def _obligation(**overrides) -> PaymentObligation:
    data = dict(
        id=6,
        user_id=1,
        name="Electricity",
        amount=Decimal("500"),
        currency="ARS",
        next_due_date=date(2026, 8, 15),
        anchor_day=15,
        payment_method="transfer",
    )
    data.update(overrides)
    return PaymentObligation(**data)


class TestPlanSchemaAccountPairing:
    # A card-paid plan cannot also name a funding account — same rule the expense form already enforces.
    def test_subscription_create_rejects_account_on_card_plan(self):
        with pytest.raises(ValidationError):
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("100"),
                currency="ARS",
                billing_cycle="monthly",
                next_billing_date=date(2026, 8, 1),
                payment_method="credit_card",
                default_account_id=7,
            )

    def test_subscription_create_allows_account_on_non_card_plan(self):
        body = SubscriptionCreate(
            name="Netflix",
            amount=Decimal("100"),
            currency="ARS",
            billing_cycle="monthly",
            next_billing_date=date(2026, 8, 1),
            payment_method="debit",
            default_account_id=7,
        )
        assert body.default_account_id == 7

    def test_installment_create_rejects_account_on_card_plan(self):
        with pytest.raises(ValidationError):
            InstallmentCreate(
                name="TV",
                total_amount=Decimal("1200"),
                installment_amount=Decimal("100"),
                currency="ARS",
                installments_count=12,
                start_date=date(2026, 1, 10),
                payment_method="credit_card",
                default_account_id=7,
            )

    def test_obligation_create_rejects_account_on_card_plan(self):
        with pytest.raises(ValidationError):
            PaymentObligationCreate(
                name="Electricity",
                amount=Decimal("500"),
                currency="ARS",
                next_due_date=date(2026, 8, 15),
                payment_method="credit_card",
                default_account_id=7,
            )

    @pytest.mark.parametrize("schema", [SubscriptionUpdate, InstallmentUpdate, PaymentObligationUpdate])
    def test_update_rejects_the_pair_when_both_provided(self, schema):
        with pytest.raises(ValidationError):
            schema(payment_method="credit_card", default_account_id=7)

    @pytest.mark.parametrize("schema", [SubscriptionUpdate, InstallmentUpdate, PaymentObligationUpdate])
    def test_update_accepts_the_account_alone(self, schema):
        # Only one key provided, so the schema can't see the effective pair — the service enforces it.
        assert schema(default_account_id=7).default_account_id == 7


class TestCardDefaultAccount:
    @pytest.mark.asyncio
    async def test_create_rejects_an_account_in_another_currency(self, monkeypatch):
        monkeypatch.setattr(credit_card_service.account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="USD")))
        create_mock = AsyncMock()
        monkeypatch.setattr(credit_card_service.credit_card_repository, "create", create_mock)

        with pytest.raises(AccountCurrencyMismatchError):
            await credit_card_service.create_card(AsyncMock(), USER, name="Visa", closing_day=25, due_day=10, currency="ARS", default_account_id=7)

        create_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_accepts_a_matching_account(self, monkeypatch):
        monkeypatch.setattr(credit_card_service.account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(credit_card_service.credit_card_repository, "create", AsyncMock(side_effect=lambda _s, card: card))

        card = await credit_card_service.create_card(AsyncMock(), USER, name="Visa", closing_day=25, due_day=10, currency="ARS", default_account_id=7)

        assert card.default_account_id == 7

    @pytest.mark.asyncio
    async def test_changing_the_card_currency_with_a_stored_default_is_refused(self, monkeypatch):
        # The effective pair is (new currency, stored default) — validating the request alone would let
        # an ARS default survive on a USD card, i.e. a link the settlement dialog could never offer.
        monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=_card(currency="ARS", default_account_id=7)))
        monkeypatch.setattr(credit_card_service.account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        save_mock = AsyncMock()
        monkeypatch.setattr(credit_card_service.credit_card_repository, "save", save_mock)

        with pytest.raises(AccountCurrencyMismatchError):
            await credit_card_service.update_card(AsyncMock(), 5, USER, currency="USD")

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unrelated_edit_does_not_revalidate_the_stored_pair(self, monkeypatch):
        # A stale stored default (its account's currency changed while nothing else referenced it) must
        # not block a rename: the pair didn't move, so there is nothing new to validate.
        monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=_card(currency="ARS", default_account_id=7)))
        get_by_id = AsyncMock(return_value=_account(currency="USD"))
        monkeypatch.setattr(credit_card_service.account_service.account_repository, "get_by_id", get_by_id)
        save_mock = AsyncMock()
        monkeypatch.setattr(credit_card_service.credit_card_repository, "save", save_mock)

        card = await credit_card_service.update_card(AsyncMock(), 5, USER, name="Visa Signature")

        assert card.name == "Visa Signature"
        get_by_id.assert_not_awaited()
        save_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clearing_the_default_alongside_a_currency_change_is_allowed(self, monkeypatch):
        monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=_card(currency="ARS", default_account_id=7)))
        get_by_id = AsyncMock()
        monkeypatch.setattr(credit_card_service.account_service.account_repository, "get_by_id", get_by_id)
        monkeypatch.setattr(credit_card_service.credit_card_repository, "save", AsyncMock())

        card = await credit_card_service.update_card(AsyncMock(), 5, USER, currency="USD", default_account_id=None)

        assert card.default_account_id is None
        get_by_id.assert_not_awaited()  # nothing to validate once the link is cleared


class TestPlanDefaultAccountService:
    # The schema validator only sees same-request pairs, so each plan service enforces the EFFECTIVE
    # rules after merging the request over the stored row.
    @pytest.mark.parametrize(
        ("service", "plan", "get_name", "repo_name"),
        [
            (subscription_service, _subscription(default_account_id=7), "get_subscription", "subscription_repository"),
            (installment_service, _installment(default_account_id=7), "get_installment", "installment_repository"),
            (payment_obligation_service, _obligation(default_account_id=7), "get_obligation", "payment_obligation_repository"),
        ],
    )
    @pytest.mark.asyncio
    async def test_switching_a_plan_to_a_card_while_a_default_is_stored_raises(self, monkeypatch, service, plan, get_name, repo_name):
        monkeypatch.setattr(service, get_name, AsyncMock(return_value=plan))
        monkeypatch.setattr(service.credit_card_repository, "get_by_id", AsyncMock(return_value=_card()))
        save_mock = AsyncMock()
        monkeypatch.setattr(getattr(service, repo_name), "save", save_mock)

        with pytest.raises(AccountCardExclusivityError):
            await _update(service, USER, payment_method="credit_card", credit_card_id=5)

        save_mock.assert_not_called()

    @pytest.mark.parametrize(
        ("service", "plan", "get_name", "repo_name"),
        [
            (subscription_service, _subscription(payment_method="credit_card", credit_card_id=5), "get_subscription", "subscription_repository"),
            (installment_service, _installment(payment_method="credit_card", credit_card_id=5), "get_installment", "installment_repository"),
            (
                payment_obligation_service,
                _obligation(payment_method="credit_card", credit_card_id=5),
                "get_obligation",
                "payment_obligation_repository",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_setting_a_default_on_a_stored_card_plan_raises(self, monkeypatch, service, plan, get_name, repo_name):
        monkeypatch.setattr(service, get_name, AsyncMock(return_value=plan))
        monkeypatch.setattr(service.credit_card_repository, "get_by_id", AsyncMock(return_value=_card()))
        save_mock = AsyncMock()
        monkeypatch.setattr(getattr(service, repo_name), "save", save_mock)

        with pytest.raises(AccountCardExclusivityError):
            await _update(service, USER, default_account_id=7)

        save_mock.assert_not_called()

    @pytest.mark.parametrize(
        ("service", "plan", "get_name", "repo_name"),
        [
            (subscription_service, _subscription(default_account_id=7), "get_subscription", "subscription_repository"),
            (installment_service, _installment(default_account_id=7), "get_installment", "installment_repository"),
            (payment_obligation_service, _obligation(default_account_id=7), "get_obligation", "payment_obligation_repository"),
        ],
    )
    @pytest.mark.asyncio
    async def test_changing_the_plan_currency_with_a_stored_default_is_refused(self, monkeypatch, service, plan, get_name, repo_name):
        monkeypatch.setattr(service, get_name, AsyncMock(return_value=plan))
        monkeypatch.setattr(service.account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        save_mock = AsyncMock()
        monkeypatch.setattr(getattr(service, repo_name), "save", save_mock)

        with pytest.raises(AccountCurrencyMismatchError):
            await _update(service, USER, currency="USD")

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_archiving_a_plan_does_not_revalidate_the_stored_pair(self, monkeypatch):
        # Same rule on the plan side: `is_active: false` must not be refused because a stored default
        # went stale — otherwise a user could not even archive the plan without editing it first.
        plan = _subscription(default_account_id=7)
        monkeypatch.setattr(subscription_service, "get_subscription", AsyncMock(return_value=plan))
        get_by_id = AsyncMock(return_value=_account(currency="USD"))
        monkeypatch.setattr(subscription_service.account_service.account_repository, "get_by_id", get_by_id)
        save_mock = AsyncMock()
        monkeypatch.setattr(subscription_service.subscription_repository, "save", save_mock)

        updated = await subscription_service.update_subscription(AsyncMock(), 3, USER, is_active=False)

        assert updated.is_active is False
        get_by_id.assert_not_awaited()
        save_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_default_is_not_a_locked_installment_field(self, monkeypatch):
        # Forward-looking convenience, not a contractual term: editable after charging has started,
        # unlike currency / amounts / payment_method.
        plan = _installment(current_installment=4)
        monkeypatch.setattr(installment_service, "get_installment", AsyncMock(return_value=plan))
        monkeypatch.setattr(installment_service.account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(installment_service.installment_repository, "save", AsyncMock())

        updated = await installment_service.update_installment(AsyncMock(), 4, USER, default_account_id=7)

        assert updated.default_account_id == 7


# Calls the right update function for whichever plan service the parametrisation supplied.
async def _update(service, user: User, **fields):
    updater = {
        subscription_service: "update_subscription",
        installment_service: "update_installment",
        payment_obligation_service: "update_obligation",
    }[service]
    return await getattr(service, updater)(AsyncMock(), 1, user, **fields)


class TestSchedulerHonoursTheDefault:
    @pytest.mark.asyncio
    async def test_no_query_when_no_plan_carries_a_default(self, monkeypatch):
        get_mock = AsyncMock()
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", get_mock)

        assert await auto_expense_service._resolve_default_accounts(AsyncMock(), [_subscription()]) == {}
        get_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_matching_account_resolves(self, monkeypatch):
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account(currency="ARS")]))

        resolved = await auto_expense_service._resolve_default_accounts(AsyncMock(), [_subscription(default_account_id=7)])

        assert {plan_id: account.id for plan_id, account in resolved.items()} == {3: 7}

    @pytest.mark.asyncio
    async def test_a_currency_mismatch_is_skipped_not_written(self, monkeypatch):
        # Reachable: an account referenced ONLY as a default has no money links, so its currency is not
        # locked and can be changed out from under the plan. A mismatched link would corrupt the
        # account's balance, which sums linked rows without conversion.
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account(currency="USD")]))

        resolved = await auto_expense_service._resolve_default_accounts(AsyncMock(), [_subscription(currency="ARS", default_account_id=7)])

        assert resolved == {}

    @pytest.mark.asyncio
    async def test_another_users_account_is_skipped(self, monkeypatch):
        # The loader is unscoped by design (one query for every user in the tick), so ownership is
        # re-checked per row here.
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account(user_id=99)]))

        resolved = await auto_expense_service._resolve_default_accounts(AsyncMock(), [_subscription(default_account_id=7)])

        assert resolved == {}

    @pytest.mark.asyncio
    async def test_an_archived_account_is_skipped(self, monkeypatch):
        # Archiving means the user stopped using the account; no picker in the app will link money to
        # one, so the nightly job must not keep depositing charges into it either.
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account(is_active=False)]))

        resolved = await auto_expense_service._resolve_default_accounts(AsyncMock(), [_subscription(default_account_id=7)])

        assert resolved == {}

    @pytest.mark.asyncio
    async def test_a_card_paid_plan_is_skipped(self, monkeypatch):
        # Reachable through restore, which copies payment_method verbatim and remaps the default with
        # no cross-field validation. Linking here as well would raise the card liability AND drop cash
        # for one charge — the double-count the whole feature exists to avoid.
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account()]))
        plan = _subscription(default_account_id=7, payment_method="credit_card", credit_card_id=5)

        resolved = await auto_expense_service._resolve_default_accounts(AsyncMock(), [plan])

        assert resolved == {}

    def test_a_charge_dated_before_the_account_opened_is_not_linked(self):
        # Every balance sum is bounded below by opening_date, so such a link would render as
        # "Paid from X" while never moving X's balance. The scheduler picks these dates itself.
        account = _account(opening_date=date(2026, 7, 1))

        assert auto_expense_service._link_for_date(account, date(2026, 6, 30)) is None
        assert auto_expense_service._link_for_date(account, date(2026, 7, 1)) == 7
        assert auto_expense_service._link_for_date(None, date(2026, 7, 1)) is None

    @pytest.mark.asyncio
    async def test_a_back_filled_charge_before_the_opening_date_stays_unattributed(self, monkeypatch):
        # End to end: the plan qualifies, but the back-fill reaches back past the account's opening.
        sub = _subscription(default_account_id=7, next_billing_date=date(2026, 6, 1))
        session = _scheduler_session([sub], [])
        monkeypatch.setattr(
            auto_expense_service.account_repository,
            "get_by_ids_across_users",
            AsyncMock(return_value=[_account(currency="ARS", opening_date=date(2026, 8, 1))]),
        )

        created, _ = await auto_expense_service._generate_subscription_expenses(session, _tick(), {1: "UTC"})

        entries = _added_entries(session)
        assert created == 3  # June, July and August cycles
        assert [(e.date, e.account_id) for e in entries] == [
            (date(2026, 6, 1), None),
            (date(2026, 7, 1), None),
            (date(2026, 8, 1), 7),
        ]

    @pytest.mark.asyncio
    async def test_an_emitted_subscription_charge_carries_the_account(self, monkeypatch):
        # End to end through the emit loop, not just the resolver: the link has to reach the row.
        sub = _subscription(default_account_id=7, next_billing_date=date(2026, 8, 1))
        session = _scheduler_session([sub], [])
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account(currency="ARS")]))

        created, _ = await auto_expense_service._generate_subscription_expenses(session, _tick(), {1: "UTC"})

        assert created == 1
        assert [e.account_id for e in _added_entries(session)] == [7]

    @pytest.mark.asyncio
    async def test_an_emitted_charge_is_unattributed_when_the_default_no_longer_qualifies(self, monkeypatch):
        sub = _subscription(default_account_id=7, next_billing_date=date(2026, 8, 1))
        session = _scheduler_session([sub], [])
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account(currency="USD")]))

        created, _ = await auto_expense_service._generate_subscription_expenses(session, _tick(), {1: "UTC"})

        # The charge still lands — a stale default must never block a scheduled expense.
        assert created == 1
        assert [e.account_id for e in _added_entries(session)] == [None]

    @pytest.mark.asyncio
    async def test_an_emitted_installment_cuota_carries_the_account(self, monkeypatch):
        plan = _installment(default_account_id=7, start_date=date(2026, 8, 1), installments_count=1)
        session = _scheduler_session([plan], [])
        monkeypatch.setattr(auto_expense_service.account_repository, "get_by_ids_across_users", AsyncMock(return_value=[_account(currency="ARS")]))

        created, _ = await auto_expense_service._generate_installment_expenses(session, _tick(), {1: "UTC"})

        assert created == 1
        assert [e.account_id for e in _added_entries(session)] == [7]


# A UTC tick at the hour the scheduler emits at, for a UTC user — on a day both fixtures are due.
def _tick() -> datetime:
    return datetime(2026, 8, 2, auto_expense_service.AUTO_EXPENSES_HOUR_LOCAL, tzinfo=UTC)


# Mirrors the two queries an emit pass runs: the due plans, then their linked expense dates.
# (The account load is monkeypatched at the repository, so it consumes no execute() call.)
def _scheduler_session(plans: list, linked_rows: list):
    plans_result = Mock()
    plans_result.scalars.return_value.all.return_value = plans
    linked_result = Mock()
    linked_result.all.return_value = linked_rows
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[plans_result, linked_result])
    session.add = Mock()
    session.flush = AsyncMock()
    return session


# The ExpenseEntry rows an emit pass staged on the session.
def _added_entries(session) -> list[ExpenseEntry]:
    return [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ExpenseEntry)]


class TestSettlementResponseNamesTheAccount:
    @pytest.mark.asyncio
    async def test_the_funding_account_is_named_and_batched(self, monkeypatch):
        settlements = [
            CardSettlement(id=1, credit_card_id=5, user_id=1, date=date(2026, 8, 1), amount=Decimal("700"), currency="ARS", account_id=7),
            CardSettlement(id=2, credit_card_id=5, user_id=1, date=date(2026, 7, 1), amount=Decimal("300"), currency="ARS", account_id=None),
        ]
        monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=_card()))
        monkeypatch.setattr(credit_card_service.card_settlement_repository, "list_by_card", AsyncMock(return_value=settlements))
        get_by_ids = AsyncMock(return_value=[_account(id=7, name="Caja de ahorro $")])
        monkeypatch.setattr(credit_card_service.account_repository, "get_by_ids", get_by_ids)

        result = await credit_card_service.list_settlements(AsyncMock(), 5, USER)

        assert [(r.id, r.account_name) for r in result] == [(1, "Caja de ahorro $"), (2, None)]
        get_by_ids.assert_awaited_once()  # one batch query for the whole list, never one per row

    @pytest.mark.asyncio
    async def test_an_archived_account_still_reads_by_name(self, monkeypatch):
        # The name is denormalized server-side precisely so this works — a client-side join against its
        # own active-accounts list would render a blank cell here.
        settlements = [CardSettlement(id=1, credit_card_id=5, user_id=1, date=date(2026, 8, 1), amount=Decimal("700"), currency="ARS", account_id=7)]
        monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=_card()))
        monkeypatch.setattr(credit_card_service.card_settlement_repository, "list_by_card", AsyncMock(return_value=settlements))
        monkeypatch.setattr(
            credit_card_service.account_repository, "get_by_ids", AsyncMock(return_value=[_account(id=7, name="Old savings", is_active=False)])
        )

        result = await credit_card_service.list_settlements(AsyncMock(), 5, USER)

        assert result[0].account_name == "Old savings"

    @pytest.mark.asyncio
    async def test_create_names_the_account_without_a_second_fetch(self, monkeypatch):
        monkeypatch.setattr(credit_card_service, "get_card", AsyncMock(return_value=_card()))
        monkeypatch.setattr(credit_card_service.account_service, "validate_account_link", AsyncMock(return_value=_account(name="Caja $")))
        monkeypatch.setattr(
            credit_card_service.card_settlement_repository,
            "create",
            AsyncMock(side_effect=lambda _s, row: row.model_copy(update={"id": 9})),
        )
        monkeypatch.setattr(credit_card_service.card_reconciliation_service, "mark_stale_for_date", AsyncMock())
        get_by_ids = AsyncMock()
        monkeypatch.setattr(credit_card_service.account_repository, "get_by_ids", get_by_ids)

        result = await credit_card_service.create_settlement(
            AsyncMock(), 5, USER, date=date(2026, 8, 1), amount=Decimal("700"), currency="ARS", account_id=7
        )

        assert result.account_name == "Caja $"
        get_by_ids.assert_not_awaited()  # validate_account_link already returned the account
