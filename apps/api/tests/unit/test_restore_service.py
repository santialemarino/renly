import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.db import get_admin_session, get_session
from app.deps.auth import get_current_user
from app.domain import InvalidImportFileError
from app.domain.restore_specs import RESTORE_SPECS, SKIPPED_ENTITIES
from app.main import create_app
from app.models.account import Account
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.income_entry import IncomeEntry
from app.models.investment import Currency, Investment
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.restore import RestoreResultResponse
from app.services import restore_service

# Unit coverage for the restore-from-export engine (ROAD-1 JSON round-trip): shape validation, type
# coercion, FK remapping, per-entity dedup (idempotency), and the preview/confirm orchestration. The
# DB layer is mocked (AsyncMock) so the tests pin the restore logic, not persistence.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _export(**sections) -> bytes:
    return json.dumps({"exported_at": "2026-07-05T00:00:00", "user": {"id": 9}, **sections}).encode()


# Mocks the repository insert so it assigns sequential ids in insertion order (to check FK remapping).
def _mock_repo(monkeypatch):
    counter = {"next": 1000}

    async def bulk_insert(session, rows):
        for row in rows:
            if hasattr(row, "id"):
                row.id = counter["next"]
                counter["next"] += 1

    monkeypatch.setattr(restore_service.restore_repository, "bulk_insert", AsyncMock(side_effect=bulk_insert))
    return restore_service.restore_repository.bulk_insert


class TestParseExport:
    def test_rejects_non_json_extension(self):
        with pytest.raises(InvalidImportFileError, match="\\.json"):
            restore_service._parse_export("x.csv", b"{}")

    def test_rejects_invalid_json(self):
        with pytest.raises(InvalidImportFileError, match="valid JSON"):
            restore_service._parse_export("x.json", b"not json")

    def test_rejects_non_object(self):
        with pytest.raises(InvalidImportFileError, match="not a Renly export"):
            restore_service._parse_export("x.json", b"[1, 2, 3]")

    def test_rejects_unrecognized_object(self):
        with pytest.raises(InvalidImportFileError, match="not a Renly export"):
            restore_service._parse_export("x.json", b'{"foo": 1}')

    def test_accepts_export_and_keeps_decimal_precision(self):
        data = restore_service._parse_export("x.json", b'{"investments": [{"amount": 1234.56}]}')
        assert data["investments"][0]["amount"] == Decimal("1234.56")
        assert isinstance(data["investments"][0]["amount"], Decimal)


# Wraps the mocked bulk_insert so a test can assert on the model instances that were written.
# Call after _mock_repo, which installs the id-assigning side effect this chains onto.
def _capture_inserts(monkeypatch) -> list:
    captured: list = []
    original = restore_service.restore_repository.bulk_insert.side_effect

    async def capture(session, rows):
        await original(session, rows)
        captured.extend(rows)

    monkeypatch.setattr(restore_service.restore_repository, "bulk_insert", AsyncMock(side_effect=capture))
    return captured


class TestBuildModel:
    def test_coerces_scalars(self):
        row = {"user_id": 1, "date": "2026-01-31", "value": 5200, "currency": "USD", "quantity": "20", "investment_id": 3}
        model = restore_service._build_model(InvestmentSnapshot, row)
        assert model.date == date(2026, 1, 31)
        assert model.value == Decimal("5200")
        assert model.currency == Currency.USD
        assert model.id is None  # a fresh insert

    def test_missing_required_column_raises(self):
        # InvestmentSnapshot.value is NOT NULL with no default → a truncated row is rejected.
        with pytest.raises(ValueError, match="Missing required field"):
            restore_service._build_model(InvestmentSnapshot, {"user_id": 1, "date": "2026-01-31", "currency": "USD", "investment_id": 3})

    # Every real export carries a UTC offset on its timestamps (they are read from timestamptz
    # columns), while the models declare a naive datetime. asyncpg binds strictly to the declared type
    # and refused the tz-aware value, so restoring any real export died on the first entity.
    def test_strips_the_utc_offset_the_export_writes(self):
        row = {"user_id": 1, "name": "Apple", "category": "stocks", "base_currency": "USD", "created_at": "2026-03-28T03:59:02.625635Z"}
        model = restore_service._build_model(Investment, row)
        assert model.created_at.tzinfo is None
        assert model.created_at == datetime(2026, 3, 28, 3, 59, 2, 625635)

    def test_converts_a_non_utc_offset_rather_than_dropping_it(self):
        # 00:30 at -03:00 is 03:30 UTC — discarding the offset instead of converting would shift the
        # instant by three hours and silently move the row to the previous day.
        row = {"user_id": 1, "name": "Apple", "category": "stocks", "base_currency": "USD", "created_at": "2026-03-28T00:30:00-03:00"}
        model = restore_service._build_model(Investment, row)
        assert model.created_at == datetime(2026, 3, 28, 3, 30, 0)

    def test_leaves_an_already_naive_timestamp_untouched(self):
        row = {"user_id": 1, "name": "Apple", "category": "stocks", "base_currency": "USD", "created_at": "2026-03-28T03:59:02.625635"}
        model = restore_service._build_model(Investment, row)
        assert model.created_at == datetime(2026, 3, 28, 3, 59, 2, 625635)

    # A tampered file can put a JSON number or object where a timestamp belongs. The tz check
    # dereferences .tzinfo, so such a value has to fail as an invalid value like every other bad
    # scalar — not as an AttributeError, which no caller catches.
    @pytest.mark.parametrize("bad", [12345, 1.5, True, {"at": 1}, ["2026-03-28"]])
    def test_a_non_timestamp_value_is_an_invalid_value(self, bad):
        row = {"user_id": 1, "name": "Apple", "category": "stocks", "base_currency": "USD", "created_at": bad}
        with pytest.raises(ValueError, match="Invalid value for 'created_at'"):
            restore_service._build_model(Investment, row)


class TestPreviewRestore:
    @pytest.mark.asyncio
    async def test_reports_counts_and_skipped_entities(self, monkeypatch):
        _mock_repo(monkeypatch)
        content = _export(
            investments=[
                {"id": 10, "name": "Apple", "category": "stocks", "base_currency": "USD"},
                {"id": 11, "name": "Bitcoin", "category": "crypto", "base_currency": "USD"},
            ],
            investment_snapshots=[
                {"id": 20, "investment_id": 10, "date": "2026-01-31", "value": 100, "currency": "USD"},
                {"id": 21, "investment_id": 999, "date": "2026-01-31", "value": 50, "currency": "USD"},  # unresolved parent
            ],
            api_keys=[{"id": 1, "name": "k"}],
            card_reconciliations=[{"id": 1}],
        )
        result = await restore_service.preview_restore(AsyncMock(), USER, "renly-export.json", content)
        assert result.recognized is True
        assert result.exported_at == "2026-07-05T00:00:00"
        assert result.skipped_entities == ["api_keys", "card_reconciliations"]
        by_entity = {stat.entity: stat for stat in result.entities}
        assert by_entity["investments"].restore == 2
        assert (by_entity["investment_snapshots"].restore, by_entity["investment_snapshots"].skipped_unresolved) == (1, 1)

    # The preview is a read-only dry run, so a row the file gets wrong must be reported as unresolved
    # rather than crashing the whole request — including a timestamp that isn't one.
    @pytest.mark.asyncio
    async def test_counts_a_malformed_timestamp_as_unresolved(self, monkeypatch):
        _mock_repo(monkeypatch)
        content = _export(
            investments=[
                {"id": 10, "name": "Apple", "category": "stocks", "base_currency": "USD"},
                {"id": 11, "name": "Bitcoin", "category": "crypto", "base_currency": "USD", "created_at": 12345},
            ]
        )
        result = await restore_service.preview_restore(AsyncMock(), USER, "renly-export.json", content)
        by_entity = {stat.entity: stat for stat in result.entities}
        assert (by_entity["investments"].restore, by_entity["investments"].skipped_unresolved) == (1, 1)

    @pytest.mark.asyncio
    async def test_preview_does_not_write(self, monkeypatch):
        bulk = _mock_repo(monkeypatch)
        content = _export(investments=[{"id": 10, "name": "Apple", "category": "stocks", "base_currency": "USD"}])
        await restore_service.preview_restore(AsyncMock(), USER, "x.json", content)
        bulk.assert_not_awaited()


class TestConfirmRestore:
    @pytest.mark.asyncio
    async def test_inserts_and_remaps_child_fks(self, monkeypatch):
        _mock_repo(monkeypatch)
        session = AsyncMock()
        content = _export(
            investments=[{"id": 10, "name": "Apple", "category": "stocks", "base_currency": "USD"}],
            investment_snapshots=[{"id": 20, "investment_id": 10, "date": "2026-01-31", "value": 5200.00, "currency": "USD", "quantity": 20}],
            transactions=[{"id": 30, "investment_id": 10, "date": "2026-01-05", "amount": 2600, "currency": "USD", "type": "buy", "quantity": 10}],
        )
        captured: list = []
        original = restore_service.restore_repository.bulk_insert.side_effect

        async def capture(sess, rows):
            await original(sess, rows)
            captured.extend(rows)

        monkeypatch.setattr(restore_service.restore_repository, "bulk_insert", AsyncMock(side_effect=capture))

        result = await restore_service.confirm_restore(session, USER, "renly-export.json", content)
        assert isinstance(result, RestoreResultResponse)
        assert result.restored == 3
        snapshot = next(r for r in captured if isinstance(r, InvestmentSnapshot))
        transaction = next(r for r in captured if isinstance(r, Transaction))
        investment = next(r for r in captured if isinstance(r, Investment))
        # Both children point at the investment's NEW id, not the exported id 10.
        assert snapshot.investment_id == investment.id
        assert transaction.investment_id == investment.id
        assert snapshot.user_id == USER.id
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nulls_scheduler_and_reconciliation_links_on_expense(self, monkeypatch):
        _mock_repo(monkeypatch)
        captured: list = []
        original = restore_service.restore_repository.bulk_insert.side_effect

        async def capture(sess, rows):
            await original(sess, rows)
            captured.extend(rows)

        monkeypatch.setattr(restore_service.restore_repository, "bulk_insert", AsyncMock(side_effect=capture))
        content = _export(
            expense_entries=[
                {
                    "id": 40,
                    "date": "2026-01-05",
                    "amount": 1250.50,
                    "currency": "ARS",
                    "category": "food",
                    "notes": "x",
                    "source": "manual",
                    "subscription_id": 500,
                    "installment_id": 501,
                    "reconciliation_id": 700,
                }
            ]
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)
        expense = next(r for r in captured if isinstance(r, ExpenseEntry))
        assert (expense.subscription_id, expense.installment_id, expense.reconciliation_id) == (None, None, None)
        assert expense.amount == Decimal("1250.50")
        assert expense.category == ExpenseCategory.food

    @pytest.mark.asyncio
    async def test_optional_fk_to_skipped_parent_is_nulled(self, monkeypatch):
        # A subscription references a credit card that is NOT in the export → the optional FK nulls out.
        _mock_repo(monkeypatch)
        captured: list = []
        original = restore_service.restore_repository.bulk_insert.side_effect

        async def capture(sess, rows):
            await original(sess, rows)
            captured.extend(rows)

        monkeypatch.setattr(restore_service.restore_repository, "bulk_insert", AsyncMock(side_effect=capture))
        content = _export(
            subscriptions=[
                {
                    "id": 60,
                    "name": "Netflix",
                    "amount": 15,
                    "currency": "USD",
                    "billing_cycle": "monthly",
                    "next_billing_date": "2026-02-01",
                    "anchor_day": 1,
                    "credit_card_id": 900,
                }
            ]
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)
        subscription = captured[0]
        assert subscription.credit_card_id is None

    @pytest.mark.asyncio
    async def test_distinct_same_content_rows_are_all_restored(self, monkeypatch):
        # Two legitimately-distinct expenses with identical content must BOTH be restored — restore never
        # content-dedups (that would silently drop real data).
        _mock_repo(monkeypatch)
        captured: list = []
        original = restore_service.restore_repository.bulk_insert.side_effect

        async def capture(sess, rows):
            await original(sess, rows)
            captured.extend(rows)

        monkeypatch.setattr(restore_service.restore_repository, "bulk_insert", AsyncMock(side_effect=capture))
        content = _export(
            expense_entries=[
                {"id": 40, "date": "2026-01-05", "amount": 500, "currency": "ARS", "category": "food", "source": "manual"},
                {"id": 41, "date": "2026-01-05", "amount": 500, "currency": "ARS", "category": "food", "source": "manual"},
            ]
        )
        result = await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)
        assert result.restored == 2
        assert len([r for r in captured if isinstance(r, ExpenseEntry)]) == 2

    @pytest.mark.asyncio
    async def test_same_name_investments_keep_their_own_children(self, monkeypatch):
        # Two investments sharing a name (differing currency) are both restored, and each snapshot stays
        # attached to its OWN investment — no merge, no child misattribution.
        _mock_repo(monkeypatch)
        captured: list = []
        original = restore_service.restore_repository.bulk_insert.side_effect

        async def capture(sess, rows):
            await original(sess, rows)
            captured.extend(rows)

        monkeypatch.setattr(restore_service.restore_repository, "bulk_insert", AsyncMock(side_effect=capture))
        content = _export(
            investments=[
                {"id": 10, "name": "Cash", "category": "dollars", "base_currency": "USD"},
                {"id": 11, "name": "Cash", "category": "other", "base_currency": "ARS"},
            ],
            investment_snapshots=[
                {"id": 20, "investment_id": 10, "date": "2026-01-31", "value": 100, "currency": "USD"},
                {"id": 21, "investment_id": 11, "date": "2026-01-31", "value": 200, "currency": "ARS"},
            ],
        )
        result = await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)
        assert result.restored == 4
        investments = [r for r in captured if isinstance(r, Investment)]
        snapshots = [r for r in captured if isinstance(r, InvestmentSnapshot)]
        assert len(investments) == 2 and investments[0].id != investments[1].id
        # Each snapshot points at the distinct investment it was exported under (no merge).
        assert {s.investment_id for s in snapshots} == {inv.id for inv in investments}
        assert snapshots[0].investment_id != snapshots[1].investment_id


# A cash balance is derived from an account's opening_balance plus the rows linked to it, so an
# account that does not come back — or comes back with its entries unattached — reads as zero cash.
# These pin the whole account cluster: the parent restores, both entry types keep their link, and a
# transfer's two NOT NULL legs are remapped together or the row is dropped.
class TestAccountClusterRoundTrip:
    @pytest.mark.asyncio
    async def test_entries_keep_their_account_link(self, monkeypatch):
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            accounts=[{"id": 80, "name": "Caja de ahorro", "type": "bank", "currency": "ARS", "opening_balance": 1000, "opening_date": "2026-01-01"}],
            expense_entries=[
                {"id": 40, "date": "2026-01-05", "amount": 500, "currency": "ARS", "category": "food", "source": "manual", "account_id": 80}
            ],
            income_entries=[
                {"id": 50, "date": "2026-01-06", "amount": 900, "currency": "ARS", "category": "salary", "source": "manual", "account_id": 80}
            ],
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        account = next(r for r in captured if isinstance(r, Account))
        expense = next(r for r in captured if isinstance(r, ExpenseEntry))
        income = next(r for r in captured if isinstance(r, IncomeEntry))
        # The NEW id, never the exported 80 — the whole point of the remap.
        assert expense.account_id == account.id
        assert income.account_id == account.id
        assert account.id != 80
        assert account.opening_balance == Decimal("1000")

    @pytest.mark.asyncio
    async def test_both_transfer_legs_are_remapped(self, monkeypatch):
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            accounts=[
                {"id": 80, "name": "Pesos", "type": "bank", "currency": "ARS", "opening_date": "2026-01-01"},
                {"id": 81, "name": "Dólares", "type": "bank", "currency": "USD", "opening_date": "2026-01-01"},
            ],
            transfers=[{"id": 90, "from_account_id": 80, "to_account_id": 81, "date": "2026-02-01", "from_amount": 12000, "to_amount": 10}],
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        source, destination = (r for r in captured if isinstance(r, Account))
        transfer = next(r for r in captured if isinstance(r, Transfer))
        assert (transfer.from_account_id, transfer.to_account_id) == (source.id, destination.id)
        # Distinct after the remap too — collapsing them would trip the DB's distinct-accounts CHECK.
        assert transfer.from_account_id != transfer.to_account_id
        assert (transfer.from_amount, transfer.to_amount) == (Decimal("12000"), Decimal("10"))

    @pytest.mark.asyncio
    async def test_a_transfer_missing_an_account_is_dropped_whole(self, monkeypatch):
        # Both legs are required FKs: restoring the half that resolves would debit an account and
        # credit nothing, which is the shape that destroyed net worth in the transfers review round.
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            accounts=[{"id": 80, "name": "Pesos", "type": "bank", "currency": "ARS", "opening_date": "2026-01-01"}],
            transfers=[{"id": 90, "from_account_id": 80, "to_account_id": 999, "date": "2026-02-01", "from_amount": 100, "to_amount": 100}],
        )
        result = await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        assert not [r for r in captured if isinstance(r, Transfer)]
        assert next(s for s in result.entities if s.entity == "transfers").skipped_unresolved == 1
        assert result.restored == 1  # the account only

    @pytest.mark.asyncio
    async def test_reconciliation_links_still_null_while_the_account_link_survives(self, monkeypatch):
        # account_reconciliations stay in SKIPPED_ENTITIES, so their back-links must keep nulling even
        # though the sibling account_id no longer does. A restored adjustment is a plain entry.
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            accounts=[{"id": 80, "name": "Pesos", "type": "bank", "currency": "ARS", "opening_date": "2026-01-01"}],
            expense_entries=[
                {
                    "id": 40,
                    "date": "2026-01-05",
                    "amount": 500,
                    "currency": "ARS",
                    "category": "account_adjustment",
                    "source": "reconciliation",
                    "account_id": 80,
                    "account_reconciliation_id": 700,
                }
            ],
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        account = next(r for r in captured if isinstance(r, Account))
        expense = next(r for r in captured if isinstance(r, ExpenseEntry))
        assert expense.account_reconciliation_id is None
        assert expense.account_id == account.id

    @pytest.mark.asyncio
    async def test_a_settlement_keeps_its_card_and_its_funding_account(self, monkeypatch):
        # A card balance is sum(expenses) - sum(settlements). Dropping the settlements returned a
        # restored card at full historical debt, understating net worth by every payment ever made.
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            credit_cards=[{"id": 70, "name": "Visa", "closing_day": 25, "due_day": 5, "currency": "ARS"}],
            accounts=[{"id": 80, "name": "Pesos", "type": "bank", "currency": "ARS", "opening_date": "2026-01-01"}],
            card_settlements=[{"id": 95, "credit_card_id": 70, "account_id": 80, "date": "2026-02-28", "amount": 7000, "currency": "ARS"}],
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        card = next(r for r in captured if isinstance(r, CreditCard))
        account = next(r for r in captured if isinstance(r, Account))
        settlement = next(r for r in captured if isinstance(r, CardSettlement))
        assert settlement.credit_card_id == card.id
        assert settlement.account_id == account.id
        assert settlement.amount == Decimal("7000")

    @pytest.mark.asyncio
    async def test_a_settlement_without_a_card_is_dropped_but_one_without_an_account_is_not(self, monkeypatch):
        # credit_card_id is NOT NULL and a settlement is meaningless without the card it paid;
        # account_id is optional, so an unresolved funding account only costs the attribution.
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            credit_cards=[{"id": 70, "name": "Visa", "closing_day": 25, "due_day": 5, "currency": "ARS"}],
            card_settlements=[
                {"id": 95, "credit_card_id": 70, "account_id": 999, "date": "2026-02-28", "amount": 7000, "currency": "ARS"},
                {"id": 96, "credit_card_id": 999, "date": "2026-02-28", "amount": 500, "currency": "ARS"},
            ],
        )
        result = await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        settlements = [r for r in captured if isinstance(r, CardSettlement)]
        assert len(settlements) == 1
        assert settlements[0].account_id is None
        assert next(s for s in result.entities if s.entity == "card_settlements").skipped_unresolved == 1

    @pytest.mark.asyncio
    async def test_a_dropped_funding_account_takes_its_cash_amount_with_it(self, monkeypatch):
        # account_amount is denominated in the funding ACCOUNT's currency, so once that link is dropped
        # there is nothing left to interpret it — and a DB CHECK forbids the pairing outright, so keeping
        # it would fail the insert rather than merely mislead. The CARD leg survives, so the restored
        # settlement still clears its bucket correctly; only the cash side it can't attribute is lost.
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            credit_cards=[{"id": 70, "name": "Visa", "closing_day": 25, "due_day": 5, "currency": "USD"}],
            card_settlements=[
                {
                    "id": 95,
                    "credit_card_id": 70,
                    "account_id": 999,
                    "date": "2026-02-28",
                    "amount": 100,
                    "currency": "USD",
                    "account_amount": 130000,
                }
            ],
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        settlement = next(r for r in captured if isinstance(r, CardSettlement))
        assert (settlement.account_id, settlement.account_amount) == (None, None)
        assert (settlement.amount, settlement.currency) == (Decimal("100"), "USD")

    @pytest.mark.asyncio
    async def test_a_resolved_funding_account_keeps_its_cash_amount(self, monkeypatch):
        # The dependent-null rule must fire only when the link actually drops, never on a healthy remap —
        # otherwise every cross-currency settlement would come back having moved no cash.
        _mock_repo(monkeypatch)
        captured = _capture_inserts(monkeypatch)
        content = _export(
            credit_cards=[{"id": 70, "name": "Visa", "closing_day": 25, "due_day": 5, "currency": "USD"}],
            accounts=[{"id": 80, "name": "Pesos", "type": "bank", "currency": "ARS", "opening_date": "2026-01-01"}],
            card_settlements=[
                {
                    "id": 95,
                    "credit_card_id": 70,
                    "account_id": 80,
                    "date": "2026-02-28",
                    "amount": 100,
                    "currency": "USD",
                    "account_amount": 130000,
                }
            ],
        )
        await restore_service.confirm_restore(AsyncMock(), USER, "x.json", content)

        account = next(r for r in captured if isinstance(r, Account))
        settlement = next(r for r in captured if isinstance(r, CardSettlement))
        assert settlement.account_id == account.id
        assert settlement.account_amount == Decimal("130000")

    @pytest.mark.asyncio
    async def test_transfers_and_settlements_are_no_longer_reported_as_skipped(self, monkeypatch):
        _mock_repo(monkeypatch)
        content = _export(accounts=[], transfers=[], card_settlements=[], card_reconciliations=[{"id": 1}])
        result = await restore_service.preview_restore(AsyncMock(), USER, "renly-export.json", content)
        assert "transfers" not in result.skipped_entities
        assert "accounts" not in result.skipped_entities
        assert "card_settlements" not in result.skipped_entities
        # The reconciliation cluster stays skipped on purpose — an old true-up against a freshly
        # re-derived balance would post an adjustment for drift that no longer exists.
        assert "account_reconciliations" in SKIPPED_ENTITIES and "card_reconciliations" in result.skipped_entities


# Router wiring over a TestClient.
def _restore_client() -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_admin_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app, raise_server_exceptions=False)


class TestDatabaseRejectionIsABadFileNotACrash:
    # The documented contract is that a file whose contents the database refuses returns 400. Only
    # IntegrityError was caught, so anything asyncpg reports as a plain DataError (an over-length
    # string, a non-numeric int) escaped as a 500 — the shape that made a real restore look like a
    # server crash. _build_model already rejects what it can coerce, so this net only sees values
    # Postgres alone can refuse.
    @pytest.mark.asyncio
    async def test_a_dbapi_error_becomes_a_domain_error(self, monkeypatch):
        monkeypatch.setattr(
            restore_service.restore_repository,
            "bulk_insert",
            AsyncMock(side_effect=DBAPIError("INSERT", {}, Exception("value too long for type character varying(255)"))),
        )
        content = _export(investments=[{"id": 10, "name": "X" * 500, "category": "stocks", "base_currency": "USD"}])
        with pytest.raises(InvalidImportFileError):
            await restore_service.confirm_restore(AsyncMock(), USER, "renly-export.json", content)

    def test_the_endpoint_reports_it_as_400(self, monkeypatch):
        monkeypatch.setattr(
            restore_service.restore_repository,
            "bulk_insert",
            AsyncMock(side_effect=DBAPIError("INSERT", {}, Exception("value too long"))),
        )
        content = _export(investments=[{"id": 10, "name": "X" * 500, "category": "stocks", "base_currency": "USD"}])
        response = _restore_client().post("/restore", files={"file": ("renly-export.json", content, "application/json")})
        assert response.status_code == 400
        assert "stack" not in response.text.lower() and "Traceback" not in response.text


class TestRestoreEndpoints:
    @pytest.fixture(autouse=True)
    def _reset_limiter(self):
        limiter.reset()
        yield
        limiter.reset()

    def test_preview_endpoint_returns_200(self, monkeypatch):
        _mock_repo(monkeypatch)
        content = _export(investments=[{"id": 10, "name": "Apple", "category": "stocks", "base_currency": "USD"}])
        response = _restore_client().post("/restore/preview", files={"file": ("renly-export.json", content, "application/json")})
        assert response.status_code == 200
        body = response.json()
        assert body["recognized"] is True
        assert any(e["entity"] == "investments" and e["restore"] == 1 for e in body["entities"])

    def test_confirm_endpoint_returns_200(self, monkeypatch):
        _mock_repo(monkeypatch)
        content = _export(investments=[{"id": 10, "name": "Apple", "category": "stocks", "base_currency": "USD"}])
        response = _restore_client().post("/restore", files={"file": ("renly-export.json", content, "application/json")})
        assert response.status_code == 200
        assert response.json()["restored"] == 1

    def test_non_export_file_returns_400(self, monkeypatch):
        _mock_repo(monkeypatch)
        response = _restore_client().post("/restore/preview", files={"file": ("x.json", b'{"foo": 1}', "application/json")})
        assert response.status_code == 400


def test_all_specs_have_unique_keys():
    keys = [spec.key for spec in RESTORE_SPECS]
    assert len(keys) == len(set(keys))


class TestRestoreSpecsCoverEveryForeignKey:
    # Structural guards, in the spirit of the export guard #171 added: three tables had reached the
    # export late, and a FK left off a RestoreSpec is the same failure one layer down — the engine
    # copies unlisted columns VERBATIM, so an un-remapped account id doesn't merely dangle, it resolves
    # to whatever row holds that id in the restoring account (a cross-tenant pointer).
    def test_every_fk_to_a_restored_entity_is_remapped_or_nulled(self):
        table_to_key = {spec.model.__tablename__: spec.key for spec in RESTORE_SPECS}
        missing: list[str] = []
        for spec in RESTORE_SPECS:
            handled = {fk.field for fk in spec.fks} | set(spec.null_fields) | {"user_id"}
            for column in spec.model.__table__.columns:
                for fk in column.foreign_keys:
                    target = fk.column.table.name
                    if target in table_to_key and column.name not in handled:
                        missing.append(f"{spec.key}.{column.name} -> {target}")
        assert missing == []

    def test_every_fk_to_a_skipped_entity_is_nulled(self):
        for spec in RESTORE_SPECS:
            for column in spec.model.__table__.columns:
                for fk in column.foreign_keys:
                    if fk.column.table.name in SKIPPED_ENTITIES:
                        assert column.name in spec.null_fields, f"{spec.key}.{column.name} points at a skipped entity"

    def test_every_parent_is_restored_before_its_children(self):
        # Would have caught `accounts` sitting after `credit_cards` once a card started naming one.
        position = {spec.key: index for index, spec in enumerate(RESTORE_SPECS)}
        for index, spec in enumerate(RESTORE_SPECS):
            for fk in spec.fks:
                assert position[fk.parent] < index, f"{spec.key} is restored before its parent {fk.parent}"
