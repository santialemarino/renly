from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import ReconciliationOwnedEntryError
from app.domain.reconciliation import ensure_not_reconciliation_owned
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.user import User
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


class TestRestoreKeepsAdjustmentsMutable:
    def test_both_reconciliation_links_are_nulled_on_restore(self):
        # The frontend gate and the backend guard both read these links, so restore nulling them is
        # what makes a restored adjustment a plain entry rather than a permanently frozen row.
        from app.domain.restore_specs import RESTORE_SPECS

        specs = {spec.key: spec for spec in RESTORE_SPECS}
        for key in ("expense_entries", "income_entries"):
            assert "reconciliation_id" in specs[key].null_fields, key
            assert "account_reconciliation_id" in specs[key].null_fields, key
