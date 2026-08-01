from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.db import get_admin_session, get_session
from app.deps.auth import get_current_user
from app.domain import ReconciliationOwnedEntryError
from app.domain.import_specs import _EXPENSE_CATEGORY_ALIASES, _INCOME_CATEGORY_ALIASES
from app.domain.reconciliation import SYSTEM_EXPENSE_CATEGORIES, SYSTEM_INCOME_CATEGORIES, ensure_not_reconciliation_owned
from app.domain.restore_specs import RESTORE_SPECS
from app.main import create_app
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.income import IncomeCreate, IncomeUpdate
from app.schemas.payment_obligation import PaymentObligationCreate, PaymentObligationUpdate
from app.services import expense_service, income_service

# Both reconciliation features post their difference as an ordinary expense / income row linked back
# to the reconciliation that created it: the card flow via reconciliation_id, the account flow via
# account_reconciliation_id. Such a row is derived — its amount IS the recorded difference — so a
# direct PUT / DELETE must be refused. Delete is not an escape hatch: the reverse pointer
# (adjustment_expense_id / adjustment_income_id) is ON DELETE SET NULL, so removing the entry leaves
# the reconciliation alive with a null pointer and a difference it no longer applies, while the
# balance snaps back. Persistence is mocked (AsyncMock), matching the other service tests.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)
ENTRY_DATE = date(2026, 7, 29)


def _expense(**overrides) -> ExpenseEntry:
    data = dict(
        id=5,
        user_id=1,
        date=ENTRY_DATE,
        amount=Decimal("200"),
        currency="ARS",
        category=ExpenseCategory.card_fees_and_taxes,
        source="reconciliation",
    )
    data.update(overrides)
    return ExpenseEntry(**data)


def _income(**overrides) -> IncomeEntry:
    data = dict(
        id=9,
        user_id=1,
        date=ENTRY_DATE,
        amount=Decimal("700"),
        currency="ARS",
        category=IncomeCategory.account_adjustment,
        source="reconciliation",
    )
    data.update(overrides)
    return IncomeEntry(**data)


# Stubs everything expense_service.update_expense / delete_expense touch after the guard, so a test
# that expects a rejection can assert those were never reached. Returns the write mocks.
def _wire_expense(monkeypatch, entry: ExpenseEntry) -> tuple[AsyncMock, AsyncMock]:
    monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
    monkeypatch.setattr(expense_service.account_service, "validate_account_link", AsyncMock())
    monkeypatch.setattr(expense_service.card_reconciliation_service, "mark_stale_for_date", AsyncMock())
    save = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(expense_service.expense_repository, "save", save)
    monkeypatch.setattr(expense_service.expense_repository, "delete", delete)
    return save, delete


# The income counterpart of _wire_expense.
def _wire_income(monkeypatch, entry: IncomeEntry) -> tuple[AsyncMock, AsyncMock]:
    monkeypatch.setattr(income_service.income_repository, "get_by_id", AsyncMock(return_value=entry))
    monkeypatch.setattr(income_service.account_service, "validate_account_link", AsyncMock())
    save = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(income_service.income_repository, "save", save)
    monkeypatch.setattr(income_service.income_repository, "delete", delete)
    return save, delete


class TestGuardRule:
    def test_passes_when_neither_link_is_set(self):
        ensure_not_reconciliation_owned(None, None)

    def test_raises_on_the_card_link(self):
        with pytest.raises(ReconciliationOwnedEntryError):
            ensure_not_reconciliation_owned(3, None)

    def test_raises_on_the_account_link(self):
        with pytest.raises(ReconciliationOwnedEntryError):
            ensure_not_reconciliation_owned(None, 4)

    def test_carries_the_stable_code_and_a_conflict_status(self):
        exc = ReconciliationOwnedEntryError()
        assert exc.code == "reconciliation_owned_entry"
        assert exc.status_code == 409
        # No structured extras — the frontend message needs no interpolation.
        assert exc.extra == {}


class TestExpenseUpdateIsRefused:
    @pytest.mark.asyncio
    async def test_card_adjustment_cannot_be_updated(self, monkeypatch):
        save, _ = _wire_expense(monkeypatch, _expense(reconciliation_id=3))
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await expense_service.update_expense(session, 5, USER, amount=Decimal("9999"))

        save.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_account_adjustment_cannot_be_updated(self, monkeypatch):
        save, _ = _wire_expense(monkeypatch, _expense(account_reconciliation_id=4, category=ExpenseCategory.account_adjustment))
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await expense_service.update_expense(session, 5, USER, amount=Decimal("9999"))

        save.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_guard_runs_before_the_account_link_is_validated(self, monkeypatch):
        # The guard sits immediately after the row fetch, so a rejected request performs no further
        # reads and stages no writes at all.
        _wire_expense(monkeypatch, _expense(reconciliation_id=3))
        validate = AsyncMock()
        monkeypatch.setattr(expense_service.account_service, "validate_account_link", validate)

        with pytest.raises(ReconciliationOwnedEntryError):
            await expense_service.update_expense(AsyncMock(), 5, USER, notes="tampered")

        validate.assert_not_awaited()


class TestExpenseDeleteIsRefused:
    @pytest.mark.asyncio
    async def test_card_adjustment_cannot_be_deleted(self, monkeypatch):
        _, delete = _wire_expense(monkeypatch, _expense(reconciliation_id=3, credit_card_id=2, payment_method="credit_card"))
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await expense_service.delete_expense(session, 5, USER)

        delete.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_account_adjustment_cannot_be_deleted(self, monkeypatch):
        _, delete = _wire_expense(
            monkeypatch,
            _expense(account_reconciliation_id=4, account_id=7, category=ExpenseCategory.account_adjustment),
        )
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await expense_service.delete_expense(session, 5, USER)

        delete.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_reconciliation_is_marked_stale_when_the_delete_is_refused(self, monkeypatch):
        # mark_stale_for_date is not a write to the entry, but it would still mutate reconciliation
        # state on a request that ultimately fails.
        _wire_expense(monkeypatch, _expense(reconciliation_id=3, credit_card_id=2, payment_method="credit_card"))
        mark_stale = AsyncMock()
        monkeypatch.setattr(expense_service.card_reconciliation_service, "mark_stale_for_date", mark_stale)

        with pytest.raises(ReconciliationOwnedEntryError):
            await expense_service.delete_expense(AsyncMock(), 5, USER)

        mark_stale.assert_not_awaited()


class TestIncomeUpdateIsRefused:
    @pytest.mark.asyncio
    async def test_account_adjustment_cannot_be_updated(self, monkeypatch):
        save, _ = _wire_income(monkeypatch, _income(account_reconciliation_id=4, account_id=7))
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await income_service.update_income(session, 9, USER, amount=Decimal("9999"))

        save.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_legacy_card_link_is_covered_too(self, monkeypatch):
        # income_entries.reconciliation_id is legacy (card credits are signed expenses since the
        # card-credit fix), but rows written before that change still carry it.
        save, _ = _wire_income(monkeypatch, _income(reconciliation_id=3, category=IncomeCategory.card_credits_and_refunds))
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await income_service.update_income(session, 9, USER, amount=Decimal("9999"))

        save.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_guard_runs_before_the_account_link_is_validated(self, monkeypatch):
        _wire_income(monkeypatch, _income(account_reconciliation_id=4))
        validate = AsyncMock()
        monkeypatch.setattr(income_service.account_service, "validate_account_link", validate)

        with pytest.raises(ReconciliationOwnedEntryError):
            await income_service.update_income(AsyncMock(), 9, USER, notes="tampered")

        validate.assert_not_awaited()


class TestIncomeDeleteIsRefused:
    @pytest.mark.asyncio
    async def test_account_adjustment_cannot_be_deleted(self, monkeypatch):
        _, delete = _wire_income(monkeypatch, _income(account_reconciliation_id=4, account_id=7))
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await income_service.delete_income(session, 9, USER)

        delete.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_legacy_card_link_is_covered_too(self, monkeypatch):
        _, delete = _wire_income(monkeypatch, _income(reconciliation_id=3, category=IncomeCategory.card_credits_and_refunds))
        session = AsyncMock()

        with pytest.raises(ReconciliationOwnedEntryError):
            await income_service.delete_income(session, 9, USER)

        delete.assert_not_awaited()
        session.commit.assert_not_awaited()


class TestTheGuardDoesNotOverReach:
    @pytest.mark.asyncio
    async def test_a_plain_expense_still_updates(self, monkeypatch):
        save, _ = _wire_expense(monkeypatch, _expense(category=ExpenseCategory.food, source="manual"))
        session = AsyncMock()

        entry, _advance, _reverse = await expense_service.update_expense(session, 5, USER, amount=Decimal("300"))

        assert entry.amount == Decimal("300")
        save.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_plain_expense_still_deletes(self, monkeypatch):
        _, delete = _wire_expense(monkeypatch, _expense(category=ExpenseCategory.food, source="manual"))
        session = AsyncMock()

        await expense_service.delete_expense(session, 5, USER)

        delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_plain_income_entry_still_updates(self, monkeypatch):
        save, _ = _wire_income(monkeypatch, _income(category=IncomeCategory.salary, source="manual"))
        session = AsyncMock()

        entry = await income_service.update_income(session, 9, USER, amount=Decimal("300"))

        assert entry.amount == Decimal("300")
        save.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_plain_income_entry_still_deletes(self, monkeypatch):
        _, delete = _wire_income(monkeypatch, _income(category=IncomeCategory.salary, source="manual"))
        session = AsyncMock()

        await income_service.delete_income(session, 9, USER)

        delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_scheduler_generated_expense_is_not_gated(self, monkeypatch):
        # The guard keys off the reconciliation links, never off `source` — the scheduler, the iOS
        # shortcut and the importers all stamp `source` and their rows must stay editable.
        save, _ = _wire_expense(monkeypatch, _expense(category=ExpenseCategory.subscriptions, source="subscription"))
        session = AsyncMock()

        await expense_service.update_expense(session, 5, USER, notes="edited")

        save.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_restored_adjustment_stays_mutable(self, monkeypatch):
        # restore_specs nulls both reconciliation links (the reconciliations themselves are in
        # SKIPPED_ENTITIES), so a restored adjustment is a plain historical entry nothing owns. Its
        # `source` survives the restore, which is exactly why the guard must not read `source`.
        save, _ = _wire_expense(monkeypatch, _expense(source="reconciliation", reconciliation_id=None, account_reconciliation_id=None))
        session = AsyncMock()

        await expense_service.update_expense(session, 5, USER, notes="edited")

        save.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_restored_adjustment_income_stays_deletable(self, monkeypatch):
        _, delete = _wire_income(monkeypatch, _income(source="reconciliation", reconciliation_id=None, account_reconciliation_id=None))
        session = AsyncMock()

        await income_service.delete_income(session, 9, USER)

        delete.assert_awaited_once()
        session.commit.assert_awaited_once()


# Router wiring over a TestClient — the deliverable is an HTTP contract (409 + a stable code), and
# only an in-process request exercises router -> domain_error_handler end to end.
def _client() -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_admin_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app, raise_server_exceptions=False)


class TestTheEndpointsReturn409:
    @pytest.fixture(autouse=True)
    def _reset_limiter(self):
        limiter.reset()
        yield
        limiter.reset()

    def test_put_expenses_returns_409_with_the_stable_code(self, monkeypatch):
        _wire_expense(monkeypatch, _expense(reconciliation_id=3))
        response = _client().put("/expenses/5", json={"amount": "9999.00"})
        assert response.status_code == 409
        assert response.json()["code"] == "reconciliation_owned_entry"

    def test_delete_expenses_returns_409_with_the_stable_code(self, monkeypatch):
        _wire_expense(monkeypatch, _expense(reconciliation_id=3))
        response = _client().delete("/expenses/5")
        assert response.status_code == 409
        assert response.json()["code"] == "reconciliation_owned_entry"

    def test_put_income_returns_409_with_the_stable_code(self, monkeypatch):
        _wire_income(monkeypatch, _income(account_reconciliation_id=4))
        response = _client().put("/income/9", json={"amount": "9999.00"})
        assert response.status_code == 409
        assert response.json()["code"] == "reconciliation_owned_entry"

    def test_delete_income_returns_409_with_the_stable_code(self, monkeypatch):
        _wire_income(monkeypatch, _income(account_reconciliation_id=4))
        response = _client().delete("/income/9")
        assert response.status_code == 409
        assert response.json()["code"] == "reconciliation_owned_entry"

    def test_the_response_carries_an_english_detail_for_api_consumers(self, monkeypatch):
        # The backend stays locale-agnostic: the frontend maps `code`, a direct API consumer reads `detail`.
        _wire_expense(monkeypatch, _expense(account_reconciliation_id=4))
        body = _client().delete("/expenses/5").json()
        assert body["detail"] == ReconciliationOwnedEntryError().message

    def test_a_plain_expense_delete_still_returns_200(self, monkeypatch):
        # Guards the contract in the other direction — the 409 must not leak onto ordinary entries.
        _wire_expense(monkeypatch, _expense(category=ExpenseCategory.food, source="manual"))
        response = _client().delete("/expenses/5")
        assert response.status_code == 200

    def test_a_plain_income_delete_still_returns_204(self, monkeypatch):
        _wire_income(monkeypatch, _income(category=IncomeCategory.salary, source="manual"))
        response = _client().delete("/income/9")
        assert response.status_code == 204


class TestSystemCategoriesAreNotUserWritable:
    # The reconciliation categories LABEL a true-up, which is what lets the app tell a balance
    # correction apart from real spending. A user-supplied value would be a fake true-up, and it would
    # also produce a row the entry form cannot round-trip (no picker option) with nothing owning it.
    @pytest.mark.parametrize("category", sorted(c.value for c in SYSTEM_EXPENSE_CATEGORIES))
    def test_expense_create_rejects_a_system_category(self, category):
        with pytest.raises(ValidationError) as exc:
            ExpenseCreate(date=ENTRY_DATE, amount=Decimal("10"), currency="ARS", category=category)
        assert "system-generated" in str(exc.value)

    @pytest.mark.parametrize("category", sorted(c.value for c in SYSTEM_EXPENSE_CATEGORIES))
    def test_expense_update_rejects_a_system_category(self, category):
        with pytest.raises(ValidationError):
            ExpenseUpdate(category=category)

    @pytest.mark.parametrize("category", sorted(c.value for c in SYSTEM_INCOME_CATEGORIES))
    def test_income_create_rejects_a_system_category(self, category):
        with pytest.raises(ValidationError):
            IncomeCreate(date=ENTRY_DATE, amount=Decimal("10"), currency="ARS", category=category)

    @pytest.mark.parametrize("category", sorted(c.value for c in SYSTEM_INCOME_CATEGORIES))
    def test_income_update_rejects_a_system_category(self, category):
        with pytest.raises(ValidationError):
            IncomeUpdate(category=category)

    def test_obligation_schemas_reject_a_system_expense_category(self):
        # Mark Paid copies expense_category onto the expense it creates, so an unguarded obligation
        # would author the same fake true-up one step later.
        with pytest.raises(ValidationError):
            PaymentObligationCreate(
                name="Rent",
                amount=Decimal("10"),
                currency="ARS",
                next_due_date=ENTRY_DATE,
                expense_category=ExpenseCategory.account_adjustment.value,
            )
        with pytest.raises(ValidationError):
            PaymentObligationUpdate(expense_category=ExpenseCategory.account_adjustment.value)

    def test_ordinary_categories_are_still_accepted(self):
        assert ExpenseCreate(date=ENTRY_DATE, amount=Decimal("10"), currency="ARS", category="food").category == ExpenseCategory.food
        assert ExpenseUpdate(category="other").category == ExpenseCategory.other
        assert IncomeCreate(date=ENTRY_DATE, amount=Decimal("10"), currency="ARS", category="salary").category == IncomeCategory.salary
        assert IncomeUpdate(category="other").category == IncomeCategory.other

    def test_omitting_the_category_is_still_allowed(self):
        assert ExpenseCreate(date=ENTRY_DATE, amount=Decimal("10"), currency="ARS").category is None
        assert IncomeUpdate().category is None

    def test_the_rejection_message_never_advertises_a_reserved_value(self):
        # A message listing the whole enum would tell the user to retry with a value that also fails.
        with pytest.raises(ValidationError) as exc:
            ExpenseCreate(date=ENTRY_DATE, amount=Decimal("10"), currency="ARS", category="account_adjustment")
        message = str(exc.value)
        assert "food" in message
        for reserved in SYSTEM_EXPENSE_CATEGORIES:
            assert f" {reserved.value}," not in message and not message.endswith(f" {reserved.value}.")

    def test_the_importers_no_longer_alias_a_system_category(self):
        # A bank statement never says "account adjustment"; aliasing these let a CSV author a row that
        # looked like a computed true-up.
        for aliases, reserved in ((_EXPENSE_CATEGORY_ALIASES, SYSTEM_EXPENSE_CATEGORIES), (_INCOME_CATEGORY_ALIASES, SYSTEM_INCOME_CATEGORIES)):
            assert not (set(aliases.values()) & set(reserved))

    def test_the_reconciliation_services_can_still_write_them(self):
        # The guard is at the request boundary only. Both services build their adjustment rows as models
        # straight through the repositories, so they are unaffected — this is the whole reason the rule
        # can be this strict.
        assert ExpenseEntry(user_id=1, date=ENTRY_DATE, amount=Decimal("-200"), currency="ARS", category=ExpenseCategory.card_credits_and_refunds)
        assert IncomeEntry(user_id=1, date=ENTRY_DATE, amount=Decimal("700"), currency="ARS", category=IncomeCategory.account_adjustment)


class TestRestoreKeepsAdjustmentsMutable:
    def test_both_reconciliation_links_are_nulled_on_restore(self):
        # The frontend gate and the backend guard both read these links, so restore nulling them is
        # what makes a restored adjustment a plain entry rather than a permanently frozen row.
        specs = {spec.key: spec for spec in RESTORE_SPECS}
        for key in ("expense_entries", "income_entries"):
            assert "reconciliation_id" in specs[key].null_fields, key
            assert "account_reconciliation_id" in specs[key].null_fields, key
