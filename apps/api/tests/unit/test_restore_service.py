import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_admin_session, get_session
from app.deps.auth import get_current_user
from app.domain import InvalidImportFileError
from app.domain.restore_specs import RESTORE_SPECS
from app.main import create_app
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.investment import Currency, Investment
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction
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


# Router wiring over a TestClient.
def _restore_client() -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_admin_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app, raise_server_exceptions=False)


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
