import io
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.config import Settings
from app.db import get_admin_session, get_session
from app.deps.auth import get_current_user
from app.domain import InvalidImportFileError, import_specs
from app.domain.import_specs import (
    EXPENSES_SPEC,
    INCOME_SPEC,
    INVESTMENTS_SPEC,
    SNAPSHOTS_SPEC,
    TRANSACTIONS_SPEC,
    ImportEntity,
)
from app.main import create_app
from app.models.expense_entry import ExpenseCategory
from app.models.income_entry import IncomeCategory
from app.models.investment import Currency, InvestmentCategory
from app.models.transaction import TransactionType
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.imports import ImportPreviewResponse, ImportSummary
from app.services import import_service
from app.utils.tabular import parse_tabular

# Unit coverage for the generic CSV/XLSX import engine (ROAD-1): tabular parsing, header
# auto-detection, per-row validation + dedup, and the preview/confirm orchestration. The DB layer
# is mocked (AsyncMock) so the tests pin the import logic, not persistence.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestParseTabular:
    def test_parses_csv_with_header_and_rows(self):
        headers, rows = parse_tabular("x.csv", _csv("Name,Category,Currency\nApple,stocks,USD\n"))
        assert headers == ["Name", "Category", "Currency"]
        assert rows == [["Apple", "stocks", "USD"]]

    def test_tolerates_utf8_bom(self):
        headers, _ = parse_tabular("x.csv", "﻿Name,Category\nApple,stocks\n".encode())
        assert headers == ["Name", "Category"]

    def test_sniffs_semicolon_delimiter(self):
        headers, rows = parse_tabular("x.csv", _csv("Name;Category;Currency\nApple;stocks;USD\n"))
        assert headers == ["Name", "Category", "Currency"]
        assert rows == [["Apple", "stocks", "USD"]]

    def test_parses_tsv_file(self):
        headers, rows = parse_tabular("x.tsv", _csv("Name\tCategory\tCurrency\nApple\tstocks\tUSD\n"))
        assert headers == ["Name", "Category", "Currency"]
        assert rows == [["Apple", "stocks", "USD"]]

    def test_skips_blank_rows_and_pads_short_rows(self):
        headers, rows = parse_tabular("x.csv", _csv("Name,Category,Currency\n\nApple,stocks\n"))
        assert headers == ["Name", "Category", "Currency"]
        assert rows == [["Apple", "stocks", ""]]

    def test_parses_xlsx(self):
        content = _xlsx([["Name", "Category", "Currency"], ["Apple", "stocks", "USD"]])
        headers, rows = parse_tabular("x.xlsx", content)
        assert headers == ["Name", "Category", "Currency"]
        assert rows == [["Apple", "stocks", "USD"]]

    def test_rejects_unsupported_extension(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_tabular("x.pdf", b"whatever")

    def test_rejects_empty_file(self):
        with pytest.raises(ValueError, match="empty"):
            parse_tabular("x.csv", _csv("\n\n"))


class TestAutoDetect:
    def test_detects_english_and_spanish_headers(self):
        columns = ["Nombre", "Tipo", "Moneda", "Símbolo"]
        mapping = import_service._auto_detect(INVESTMENTS_SPEC, columns)
        assert mapping == {
            "name": "Nombre",
            "category": "Tipo",
            "base_currency": "Moneda",
            "ticker": "Símbolo",
        }

    def test_is_case_insensitive(self):
        mapping = import_service._auto_detect(INVESTMENTS_SPEC, ["NAME", "CATEGORY", "CURRENCY"])
        assert mapping["name"] == "NAME"
        assert mapping["base_currency"] == "CURRENCY"

    def test_first_matching_column_in_file_order_wins(self):
        # "Investment" and "Name" both alias `name`; the first column in file order is chosen
        # deterministically (the mapping no longer depends on the alias frozenset's iteration order).
        mapping = import_service._auto_detect(INVESTMENTS_SPEC, ["Investment", "Name", "Currency"])
        assert mapping["name"] == "Investment"

    def test_resolve_falls_back_to_auto_detect_when_empty(self):
        columns = ["Name", "Category", "Currency"]
        assert import_service._resolve_mapping(INVESTMENTS_SPEC, columns, {}) == import_service._auto_detect(INVESTMENTS_SPEC, columns)

    def test_resolve_drops_unknown_fields_and_columns(self):
        columns = ["Name", "Category"]
        mapping = {"name": "Name", "bogus": "Name", "category": "Missing"}
        assert import_service._resolve_mapping(INVESTMENTS_SPEC, columns, mapping) == {"name": "Name"}


class TestValidateRows:
    def _validate(self, rows, *, mapping=None, existing=None):
        columns = ["name", "category", "base_currency", "ticker", "broker", "notes"]
        mapping = mapping or {field.key: field.key for field in INVESTMENTS_SPEC.fields}
        return import_service._validate_rows(INVESTMENTS_SPEC, columns, rows, mapping, existing or set())

    def test_valid_row(self):
        rows = [["Apple", "stocks", "usd", "aapl", "IBKR", "note"]]
        preview, coerced = self._validate(rows)
        assert preview[0].status == "valid"
        assert preview[0].errors == []
        assert coerced[0]["category"] == InvestmentCategory.stocks
        # Currency uppercased, ticker uppercased by the coercers.
        assert coerced[0]["base_currency"] == "USD"
        assert coerced[0]["ticker"] == "AAPL"

    def test_missing_required_name_is_invalid(self):
        preview, _ = self._validate([["", "stocks", "USD", "", "", ""]])
        assert preview[0].status == "invalid"
        assert any("Name is required" in error for error in preview[0].errors)

    def test_unknown_category_is_invalid(self):
        preview, _ = self._validate([["Apple", "wat", "USD", "", "", ""]])
        assert preview[0].status == "invalid"
        assert any("Unknown category" in error for error in preview[0].errors)

    def test_unsupported_currency_is_invalid(self):
        preview, _ = self._validate([["Apple", "stocks", "JPY", "", "", ""]])
        assert preview[0].status == "invalid"
        assert any("Unsupported currency" in error for error in preview[0].errors)

    def test_overlong_name_is_invalid(self):
        preview, _ = self._validate([["A" * 256, "stocks", "USD", "", "", ""]])
        assert preview[0].status == "invalid"
        assert any("too long" in error for error in preview[0].errors)

    def test_duplicate_against_existing(self):
        # Dedup keys are composite tuples now; investments dedup on a 1-tuple of the lowercased name.
        preview, _ = self._validate([["Apple", "stocks", "USD", "", "", ""]], existing={("apple",)})
        assert preview[0].status == "duplicate"

    def test_within_file_duplicate(self):
        rows = [["Apple", "stocks", "USD", "", "", ""], ["apple", "fci", "ARS", "", "", ""]]
        preview, _ = self._validate(rows)
        assert preview[0].status == "valid"
        assert preview[1].status == "duplicate"


class TestPreviewImport:
    @pytest.mark.asyncio
    async def test_preview_reports_columns_mapping_and_summary(self, monkeypatch):
        monkeypatch.setattr(import_service.investment_repository, "list_names_by_user", AsyncMock(return_value=["Apple"]))
        content = _csv("Name,Category,Currency\nApple,stocks,USD\nTesla,stocks,USD\nBad,wat,USD\n")
        result = await import_service.preview_import(AsyncMock(), USER, ImportEntity.investments, "x.csv", content, {})
        assert result.columns == ["Name", "Category", "Currency"]
        assert result.mapping == {"name": "Name", "category": "Category", "base_currency": "Currency"}
        # Apple = existing duplicate, Tesla = valid, Bad = invalid category.
        assert (result.summary.valid, result.summary.duplicate, result.summary.invalid) == (1, 1, 1)


class TestConfirmImport:
    @pytest.mark.asyncio
    async def test_confirm_inserts_valid_skips_invalid_and_duplicate(self, monkeypatch):
        monkeypatch.setattr(import_service.investment_repository, "list_names_by_user", AsyncMock(return_value=["Apple"]))
        bulk = AsyncMock(side_effect=lambda session, investments: investments)
        monkeypatch.setattr(import_service.investment_repository, "bulk_create", bulk)
        session = AsyncMock()
        content = _csv("Name,Category,Currency\nApple,stocks,USD\nTesla,stocks,USD\nBad,wat,USD\n")
        mapping = {"name": "Name", "category": "Category", "base_currency": "Currency"}

        result = await import_service.confirm_import(session, USER, ImportEntity.investments, "x.csv", content, mapping, False)

        assert (result.created, result.skipped_duplicate, result.skipped_invalid) == (1, 1, 1)
        inserted = bulk.call_args.args[1]
        assert [inv.name for inv in inserted] == ["Tesla"]
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirm_imports_duplicates_when_flagged(self, monkeypatch):
        monkeypatch.setattr(import_service.investment_repository, "list_names_by_user", AsyncMock(return_value=["Apple"]))
        bulk = AsyncMock(side_effect=lambda session, investments: investments)
        monkeypatch.setattr(import_service.investment_repository, "bulk_create", bulk)
        content = _csv("Name,Category,Currency\nApple,stocks,USD\nTesla,stocks,USD\n")
        mapping = {"name": "Name", "category": "Category", "base_currency": "Currency"}

        result = await import_service.confirm_import(AsyncMock(), USER, ImportEntity.investments, "x.csv", content, mapping, True)

        assert (result.created, result.skipped_duplicate) == (2, 0)


class TestRowCap:
    @pytest.mark.asyncio
    async def test_rejects_file_over_row_cap(self, monkeypatch):
        monkeypatch.setattr(import_service, "MAX_IMPORT_ROWS", 2)
        content = _csv("Name,Category,Currency\nA,stocks,USD\nB,stocks,USD\nC,stocks,USD\n")
        with pytest.raises(InvalidImportFileError, match="Too many rows"):
            await import_service.preview_import(AsyncMock(), USER, ImportEntity.investments, "x.csv", content, {})


class TestAmountCoercer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("100", Decimal("100.00")),
            ("100.5", Decimal("100.50")),
            ("1,234.56", Decimal("1234.56")),  # US grouping + decimal
            ("1.234,56", Decimal("1234.56")),  # AR/ES grouping + decimal
            ("1.234.567,89", Decimal("1234567.89")),
            ("1.000", Decimal("1000.00")),  # lone separator, exactly 3 digits → thousands group
            ("1,000", Decimal("1000.00")),
            ("100.005", Decimal("100005.00")),  # same thousands rule (consistent with 1.000 → 1000)
            ("10,50", Decimal("10.50")),  # lone comma, 2 digits → decimal
            ("100.5678", Decimal("100.57")),  # 4-digit fraction stays decimal, rounds half-up
            ("1234,5", Decimal("1234.50")),
        ],
    )
    def test_parses_amount(self, raw, expected):
        assert import_specs._coerce_amount(raw) == expected

    @pytest.mark.parametrize("raw", ["0", "-5", "abc", "", "1e400"])
    def test_rejects_bad_amount(self, raw):
        with pytest.raises(ValueError):
            import_specs._coerce_amount(raw)

    def test_rejects_too_large(self):
        with pytest.raises(ValueError, match="too large"):
            import_specs._coerce_amount("1" * 17)


class TestDateCoercer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-01-15", date(2026, 1, 15)),
            ("2026-01-15T10:30:00", date(2026, 1, 15)),
            ("2026-01-15 00:00:00", date(2026, 1, 15)),
            ("2026/01/15", date(2026, 1, 15)),
            ("15/01/2026", date(2026, 1, 15)),  # day-first
            ("15-01-2026", date(2026, 1, 15)),
            ("01/02/2026", date(2026, 2, 1)),  # ambiguous → day-first wins
            ("01/15/2026", date(2026, 1, 15)),  # unambiguous US → month-first fallback
        ],
    )
    def test_parses_date(self, raw, expected):
        assert import_specs._coerce_date(raw) == expected

    @pytest.mark.parametrize("raw", ["not a date", "2026-13-01", "32/01/2026"])
    def test_rejects_bad_date(self, raw):
        with pytest.raises(ValueError, match="date"):
            import_specs._coerce_date(raw)


class TestExpenseSpec:
    def _validate(self, rows, *, mapping=None, existing=None):
        columns = [field.key for field in EXPENSES_SPEC.fields]
        mapping = mapping or {field.key: field.key for field in EXPENSES_SPEC.fields}
        return import_service._validate_rows(EXPENSES_SPEC, columns, rows, mapping, existing or set())

    def test_auto_detects_spanish_headers(self):
        columns = ["Fecha", "Monto", "Moneda", "Categoría", "Medio de pago", "Notas"]
        mapping = import_service._auto_detect(EXPENSES_SPEC, columns)
        assert mapping == {
            "date": "Fecha",
            "amount": "Monto",
            "currency": "Moneda",
            "category": "Categoría",
            "payment_method": "Medio de pago",
            "notes": "Notas",
        }

    def test_valid_row_coerces_fields(self):
        preview, coerced = self._validate([["2026-01-05", "1.234,56", "ars", "comida", "debit", "lunch"]])
        assert preview[0].status == "valid"
        assert coerced[0]["date"] == date(2026, 1, 5)
        assert coerced[0]["amount"] == Decimal("1234.56")
        assert coerced[0]["currency"] == "ARS"
        assert coerced[0]["category"] == ExpenseCategory.food

    def test_category_is_optional(self):
        preview, coerced = self._validate([["2026-01-05", "100", "USD", "", "", ""]])
        assert preview[0].status == "valid"
        assert "category" not in coerced[0]

    def test_missing_required_date_is_invalid(self):
        preview, _ = self._validate([["", "100", "USD", "food", "", ""]])
        assert preview[0].status == "invalid"
        assert any("Date is required" in error for error in preview[0].errors)

    def test_bad_amount_is_invalid(self):
        preview, _ = self._validate([["2026-01-05", "abc", "USD", "food", "", ""]])
        assert preview[0].status == "invalid"

    def test_unsupported_currency_is_invalid(self):
        preview, _ = self._validate([["2026-01-05", "100", "JPY", "food", "", ""]])
        assert preview[0].status == "invalid"

    def test_unknown_category_is_invalid(self):
        preview, _ = self._validate([["2026-01-05", "100", "USD", "wat", "", ""]])
        assert preview[0].status == "invalid"

    def test_overlong_payment_method_is_invalid(self):
        preview, _ = self._validate([["2026-01-05", "100", "USD", "food", "x" * 21, ""]])
        assert preview[0].status == "invalid"

    def test_composite_dedup_within_file(self):
        rows = [
            ["2026-01-05", "100", "USD", "food", "", "Cafe"],
            ["2026-01-05", "100", "USD", "food", "", "Cafe"],  # identical → duplicate
        ]
        preview, _ = self._validate(rows)
        assert preview[0].status == "valid"
        assert preview[1].status == "duplicate"

    def test_differing_notes_are_not_duplicates(self):
        rows = [
            ["2026-01-05", "100", "USD", "food", "", "Coffee"],
            ["2026-01-05", "100", "USD", "food", "", "Bus fare"],  # notes differ → distinct
        ]
        preview, _ = self._validate(rows)
        assert preview[0].status == "valid"
        assert preview[1].status == "valid"

    def test_differing_category_is_not_duplicate(self):
        rows = [
            ["2026-01-05", "100", "USD", "food", "", ""],
            ["2026-01-05", "100", "USD", "rent", "", ""],
        ]
        preview, _ = self._validate(rows)
        assert preview[1].status == "valid"

    def test_duplicate_against_existing(self):
        existing = {("2026-01-05", "100.00", "usd", "food", "lunch")}
        preview, _ = self._validate([["2026-01-05", "100", "USD", "food", "", "lunch"]], existing=existing)
        assert preview[0].status == "duplicate"


class TestIncomeSpec:
    def _validate(self, rows, *, existing=None):
        columns = [field.key for field in INCOME_SPEC.fields]
        mapping = {field.key: field.key for field in INCOME_SPEC.fields}
        return import_service._validate_rows(INCOME_SPEC, columns, rows, mapping, existing or set())

    def test_valid_row(self):
        preview, coerced = self._validate([["2026-01-01", "3500", "USD", "salary", "paycheck"]])
        assert preview[0].status == "valid"
        assert coerced[0]["category"] == IncomeCategory.salary

    def test_unknown_category_is_invalid(self):
        preview, _ = self._validate([["2026-01-01", "3500", "USD", "wat", ""]])
        assert preview[0].status == "invalid"

    def test_composite_dedup_within_file(self):
        rows = [
            ["2026-01-01", "3500", "USD", "salary", ""],
            ["2026-01-01", "3500", "USD", "salary", ""],
        ]
        preview, _ = self._validate(rows)
        assert preview[1].status == "duplicate"


class TestExpenseImport:
    @pytest.mark.asyncio
    async def test_preview_reports_summary(self, monkeypatch):
        existing = [(date(2026, 1, 5), Decimal("100.00"), "USD", ExpenseCategory.food, "lunch")]
        monkeypatch.setattr(import_service.expense_repository, "list_dedup_keys_by_user", AsyncMock(return_value=existing))
        content = _csv(
            "Date,Amount,Currency,Category,Notes\n2026-01-05,100,USD,food,lunch\n2026-01-06,50,USD,transport,bus\n2026-01-07,bad,USD,food,x\n"
        )
        result = await import_service.preview_import(AsyncMock(), USER, ImportEntity.expenses, "x.csv", content, {})
        # row1 = existing duplicate, row2 = valid, row3 = invalid amount.
        assert (result.summary.valid, result.summary.duplicate, result.summary.invalid) == (1, 1, 1)

    @pytest.mark.asyncio
    async def test_confirm_inserts_valid_skips_rest(self, monkeypatch):
        monkeypatch.setattr(import_service.expense_repository, "list_dedup_keys_by_user", AsyncMock(return_value=[]))
        bulk = AsyncMock(side_effect=lambda session, entries: entries)
        monkeypatch.setattr(import_service.expense_repository, "bulk_create", bulk)
        session = AsyncMock()
        content = _csv(
            "Date,Amount,Currency,Category,Notes\n2026-01-05,100,USD,food,lunch\n2026-01-05,100,USD,food,lunch\n2026-01-07,bad,USD,food,x\n"
        )
        mapping = {"date": "Date", "amount": "Amount", "currency": "Currency", "category": "Category", "notes": "Notes"}

        result = await import_service.confirm_import(session, USER, ImportEntity.expenses, "x.csv", content, mapping, False)

        # row1 valid, row2 within-file duplicate, row3 invalid.
        assert (result.created, result.skipped_duplicate, result.skipped_invalid) == (1, 1, 1)
        inserted = bulk.call_args.args[1]
        assert len(inserted) == 1
        assert inserted[0].amount == Decimal("100.00")
        assert inserted[0].source == "manual"
        session.commit.assert_awaited_once()


class TestIncomeImport:
    @pytest.mark.asyncio
    async def test_confirm_inserts_income(self, monkeypatch):
        monkeypatch.setattr(import_service.income_repository, "list_dedup_keys_by_user", AsyncMock(return_value=[]))
        bulk = AsyncMock(side_effect=lambda session, entries: entries)
        monkeypatch.setattr(import_service.income_repository, "bulk_create", bulk)
        content = _csv("Date,Amount,Currency,Category,Notes\n2026-01-01,3500,USD,salary,paycheck\n")
        mapping = {"date": "Date", "amount": "Amount", "currency": "Currency", "category": "Category", "notes": "Notes"}

        result = await import_service.confirm_import(AsyncMock(), USER, ImportEntity.income, "x.csv", content, mapping, False)

        assert result.created == 1
        inserted = bulk.call_args.args[1]
        assert inserted[0].category == IncomeCategory.salary
        assert inserted[0].source == "manual"


# Router wiring over a TestClient: multipart parsing, mapping-JSON parsing, and entity validation.
def _import_client() -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_admin_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app, raise_server_exceptions=False)


class TestImportEndpoints:
    @pytest.fixture(autouse=True)
    def _reset_limiter(self):
        limiter.reset()
        yield
        limiter.reset()

    def test_preview_endpoint_returns_200(self, monkeypatch):
        preview = ImportPreviewResponse(
            columns=["Name"], fields=[], mapping={}, rows=[], summary=ImportSummary(total=0, valid=0, invalid=0, duplicate=0)
        )
        monkeypatch.setattr(import_service, "preview_import", AsyncMock(return_value=preview))
        response = _import_client().post("/imports/investments/preview", files={"file": ("x.csv", b"Name\nApple\n", "text/csv")})
        assert response.status_code == 200
        assert response.json()["columns"] == ["Name"]

    def test_invalid_mapping_json_returns_400(self):
        response = _import_client().post(
            "/imports/investments/preview",
            files={"file": ("x.csv", b"Name\nApple\n", "text/csv")},
            data={"mapping": "not-json"},
        )
        assert response.status_code == 400

    def test_unknown_entity_returns_422(self):
        response = _import_client().post("/imports/bogus/preview", files={"file": ("x.csv", b"Name\nApple\n", "text/csv")})
        assert response.status_code == 422

    @pytest.mark.parametrize("entity", ["expenses", "income"])
    def test_new_entity_preview_endpoint_returns_200(self, entity, monkeypatch):
        # Exercises the full route → service → spec wiring for the entities added in this PR.
        monkeypatch.setattr(import_service.expense_repository, "list_dedup_keys_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(import_service.income_repository, "list_dedup_keys_by_user", AsyncMock(return_value=[]))
        content = b"Date,Amount,Currency,Category\n2026-01-05,100,USD,other\n"
        response = _import_client().post(f"/imports/{entity}/preview", files={"file": ("x.csv", content, "text/csv")})
        assert response.status_code == 200
        body = response.json()
        assert body["mapping"]["amount"] == "Amount"
        assert body["summary"]["valid"] == 1

    @pytest.mark.parametrize("entity", ["snapshots", "transactions"])
    def test_nested_entity_preview_endpoint_returns_200(self, entity, monkeypatch):
        # Exercises route → service → spec + investment resolution for the nested entities.
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=[(1, "Apple", "AAPL", "USD")]))
        monkeypatch.setattr(import_service.transaction_repository, "list_dedup_keys_by_user", AsyncMock(return_value=[]))
        content = {
            "snapshots": b"Investment,Date,Value,Currency\nApple,2026-01-31,100,USD\n",
            "transactions": b"Investment,Date,Amount,Currency,Type\nApple,2026-01-05,100,USD,buy\n",
        }[entity]
        response = _import_client().post(f"/imports/{entity}/preview", files={"file": ("x.csv", content, "text/csv")})
        assert response.status_code == 200
        assert response.json()["summary"]["valid"] == 1


class TestValueCoercer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0", Decimal("0.00")),  # a closed position is a valid data point
            ("1000", Decimal("1000.00")),
            ("1.234,56", Decimal("1234.56")),
            ("1,234.56", Decimal("1234.56")),
        ],
    )
    def test_parses_value(self, raw, expected):
        assert import_specs._coerce_value(raw) == expected

    @pytest.mark.parametrize("raw", ["-1", "abc", ""])
    def test_rejects_bad_value(self, raw):
        with pytest.raises(ValueError):
            import_specs._coerce_value(raw)


class TestQuantityCoercer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0", Decimal("0.000000")),
            ("1.5", Decimal("1.5")),
            ("0.00012345", Decimal("0.000123")),  # 6-decimal precision
        ],
    )
    def test_parses_quantity(self, raw, expected):
        assert import_specs._coerce_quantity(raw) == expected

    @pytest.mark.parametrize("raw", ["-1", "abc"])
    def test_rejects_bad_quantity(self, raw):
        with pytest.raises(ValueError):
            import_specs._coerce_quantity(raw)


class TestTransactionTypeCoercer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("buy", TransactionType.buy),
            ("Compra", TransactionType.buy),
            ("sell", TransactionType.sell),
            ("venta", TransactionType.sell),
            ("deposit", TransactionType.deposit),
            ("aporte", TransactionType.deposit),
            ("withdrawal", TransactionType.withdrawal),
            ("retiro", TransactionType.withdrawal),
        ],
    )
    def test_parses_type(self, raw, expected):
        assert import_specs._coerce_transaction_type(raw) == expected

    def test_rejects_unknown_type(self):
        with pytest.raises(ValueError, match="transaction type"):
            import_specs._coerce_transaction_type("teleport")


class TestInvestmentCurrencyCoercer:
    @pytest.mark.parametrize(("raw", "expected"), [("usd", Currency.USD), ("ARS", Currency.ARS)])
    def test_parses_currency(self, raw, expected):
        assert import_specs._coerce_investment_currency(raw) == expected

    @pytest.mark.parametrize("raw", ["BRL", "EUR", "JPY"])
    def test_rejects_non_ars_usd(self, raw):
        with pytest.raises(ValueError, match="Unsupported currency"):
            import_specs._coerce_investment_currency(raw)


class TestInvestmentResolver:
    @pytest.mark.asyncio
    async def test_resolves_ticker_first_then_name_lowest_id(self, monkeypatch):
        # Two investments named "Apple" (ids 3, 7); a third with ticker "AAPL" (id 5).
        identifiers = [(3, "Apple", None, "USD"), (5, "Apple Inc", "AAPL", "USD"), (7, "Apple", None, "USD")]
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=identifiers))
        resolve = await import_service._build_resolver(AsyncMock(), USER, ImportEntity.transactions)

        ticker_row: dict[str, object] = {"investment": "aapl", "currency": "USD"}
        resolve(ticker_row)
        assert ticker_row["investment_id"] == 5  # ticker match wins

        name_row: dict[str, object] = {"investment": "apple", "currency": "USD"}
        resolve(name_row)
        assert name_row["investment_id"] == 3  # ambiguous name → lowest (oldest) id

    @pytest.mark.asyncio
    async def test_unmatched_identifier_raises(self, monkeypatch):
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=[(1, "Apple", None, "USD")]))
        resolve = await import_service._build_resolver(AsyncMock(), USER, ImportEntity.snapshots)
        with pytest.raises(ValueError, match="not found"):
            resolve({"investment": "Tesla", "currency": "USD"})

    @pytest.mark.asyncio
    async def test_row_currency_must_match_base(self, monkeypatch):
        # ARS row for a USD-based investment is invalid — mirrors the API's 400.
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=[(1, "Apple", "AAPL", "USD")]))
        resolve = await import_service._build_resolver(AsyncMock(), USER, ImportEntity.transactions)
        with pytest.raises(ValueError, match="does not match the investment's base currency"):
            resolve({"investment": "AAPL", "currency": "ARS"})

    @pytest.mark.asyncio
    async def test_matching_currency_resolves(self, monkeypatch):
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=[(1, "Apple", "AAPL", "USD")]))
        resolve = await import_service._build_resolver(AsyncMock(), USER, ImportEntity.transactions)
        row: dict[str, object] = {"investment": "AAPL", "currency": "USD"}
        resolve(row)
        assert row["investment_id"] == 1

    @pytest.mark.asyncio
    async def test_top_level_entity_has_no_resolver(self):
        assert await import_service._build_resolver(AsyncMock(), USER, ImportEntity.investments) is None


# Minimal investment resolver for the spec-level validation tests (the real one is covered above).
def _make_resolver(by_name: dict[str, int], by_ticker: dict[str, int] | None = None):
    by_ticker = by_ticker or {}

    def resolve(values: dict[str, object]) -> None:
        raw = str(values.get("investment", "")).strip()
        investment_id = by_ticker.get(raw.upper()) or by_name.get(raw.lower())
        if investment_id is None:
            raise ValueError(f"Investment '{raw}' not found.")
        values["investment_id"] = investment_id

    return resolve


class TestSnapshotSpec:
    def _validate(self, rows, *, resolver=None):
        columns = [field.key for field in SNAPSHOTS_SPEC.fields]
        mapping = {field.key: field.key for field in SNAPSHOTS_SPEC.fields}
        return import_service._validate_rows(SNAPSHOTS_SPEC, columns, rows, mapping, set(), resolver or _make_resolver({"apple": 1}))

    def test_valid_row_coerces_fields(self):
        preview, coerced = self._validate([["Apple", "2026-01-31", "1.000,50", "usd", "10", "note"]])
        assert preview[0].status == "valid"
        assert coerced[0]["investment_id"] == 1
        assert coerced[0]["value"] == Decimal("1000.50")
        assert coerced[0]["currency"] == Currency.USD
        assert coerced[0]["quantity"] == Decimal("10")

    def test_zero_value_is_valid(self):
        preview, coerced = self._validate([["Apple", "2026-01-31", "0", "USD", "", ""]])
        assert preview[0].status == "valid"
        assert coerced[0]["value"] == Decimal("0.00")

    def test_unmatched_investment_is_invalid(self):
        preview, _ = self._validate([["Tesla", "2026-01-31", "100", "USD", "", ""]])
        assert preview[0].status == "invalid"
        assert any("not found" in error for error in preview[0].errors)

    def test_missing_investment_is_invalid(self):
        preview, _ = self._validate([["", "2026-01-31", "100", "USD", "", ""]])
        assert preview[0].status == "invalid"
        assert any("Investment is required" in error for error in preview[0].errors)

    def test_non_ars_usd_currency_is_invalid(self):
        preview, _ = self._validate([["Apple", "2026-01-31", "100", "BRL", "", ""]])
        assert preview[0].status == "invalid"

    def test_no_soft_dedup_repeated_dates_stay_valid(self):
        # Snapshots upsert natively, so two rows for the same (investment, date) are both valid in
        # preview; the confirm path collapses them before the upsert.
        rows = [["Apple", "2026-01-31", "100", "USD", "", ""], ["Apple", "2026-01-31", "200", "USD", "", ""]]
        preview, _ = self._validate(rows)
        assert [row.status for row in preview] == ["valid", "valid"]


class TestTransactionSpec:
    def _validate(self, rows, *, existing=None):
        columns = [field.key for field in TRANSACTIONS_SPEC.fields]
        mapping = {field.key: field.key for field in TRANSACTIONS_SPEC.fields}
        return import_service._validate_rows(TRANSACTIONS_SPEC, columns, rows, mapping, existing or set(), _make_resolver({"apple": 1}))

    def test_valid_row_coerces_fields(self):
        preview, coerced = self._validate([["Apple", "2026-01-05", "100", "USD", "compra", "5", ""]])
        assert preview[0].status == "valid"
        assert coerced[0]["investment_id"] == 1
        assert coerced[0]["type"] == TransactionType.buy
        assert coerced[0]["amount"] == Decimal("100.00")

    def test_unknown_type_is_invalid(self):
        preview, _ = self._validate([["Apple", "2026-01-05", "100", "USD", "teleport", "", ""]])
        assert preview[0].status == "invalid"

    def test_missing_type_is_invalid(self):
        preview, _ = self._validate([["Apple", "2026-01-05", "100", "USD", "", "", ""]])
        assert preview[0].status == "invalid"
        assert any("Type is required" in error for error in preview[0].errors)

    def test_composite_dedup_within_file(self):
        rows = [
            ["Apple", "2026-01-05", "100", "USD", "buy", "5", ""],
            ["Apple", "2026-01-05", "100", "USD", "buy", "5", ""],  # identical → duplicate
        ]
        preview, _ = self._validate(rows)
        assert [row.status for row in preview] == ["valid", "duplicate"]

    def test_differing_type_is_not_duplicate(self):
        rows = [
            ["Apple", "2026-01-05", "100", "USD", "buy", "5", ""],
            ["Apple", "2026-01-05", "100", "USD", "sell", "5", ""],
        ]
        preview, _ = self._validate(rows)
        assert [row.status for row in preview] == ["valid", "valid"]

    def test_differing_currency_is_not_duplicate(self):
        rows = [
            ["Apple", "2026-01-05", "100", "USD", "buy", "5", ""],
            ["Apple", "2026-01-05", "100", "ARS", "buy", "5", ""],  # same but currency differs → distinct
        ]
        preview, _ = self._validate(rows)
        assert [row.status for row in preview] == ["valid", "valid"]

    def test_duplicate_against_existing(self):
        existing = {("1", "2026-01-05", "buy", "100.00", "usd", "5.000000")}
        preview, _ = self._validate([["Apple", "2026-01-05", "100", "USD", "buy", "5", ""]], existing=existing)
        assert preview[0].status == "duplicate"


class TestSnapshotImport:
    @pytest.mark.asyncio
    async def test_confirm_upserts_and_collapses_within_file(self, monkeypatch):
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=[(1, "Apple", "AAPL", "USD")]))
        upsert = AsyncMock(side_effect=lambda session, snapshots: len(snapshots))
        monkeypatch.setattr(import_service.snapshot_repository, "bulk_upsert", upsert)
        session = AsyncMock()
        # Apple + AAPL both resolve to id 1 for the same date → collapse to one upsert (last wins);
        # Tesla is unmatched → invalid.
        content = _csv("Investment,Date,Value,Currency\nApple,2026-01-31,100,USD\nAAPL,2026-01-31,200,USD\nTesla,2026-01-31,50,USD\n")
        mapping = {"investment": "Investment", "date": "Date", "value": "Value", "currency": "Currency"}

        result = await import_service.confirm_import(session, USER, ImportEntity.snapshots, "x.csv", content, mapping, False)

        assert (result.created, result.skipped_invalid) == (1, 1)
        upserted = upsert.call_args.args[1]
        assert len(upserted) == 1
        assert upserted[0].value == Decimal("200.00")  # last row wins
        assert upserted[0].source == "manual"  # set by the service, not the repo
        assert upserted[0].user_id == USER.id
        session.commit.assert_awaited_once()


class TestTransactionImport:
    @pytest.mark.asyncio
    async def test_confirm_inserts_matched_skips_unmatched(self, monkeypatch):
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=[(1, "Apple", "AAPL", "USD")]))
        monkeypatch.setattr(import_service.transaction_repository, "list_dedup_keys_by_user", AsyncMock(return_value=[]))
        bulk = AsyncMock(side_effect=lambda session, txns: txns)
        monkeypatch.setattr(import_service.transaction_repository, "bulk_create", bulk)
        session = AsyncMock()
        content = _csv("Investment,Date,Amount,Currency,Type\nApple,2026-01-05,100,USD,buy\nTesla,2026-01-06,50,USD,sell\n")
        mapping = {"investment": "Investment", "date": "Date", "amount": "Amount", "currency": "Currency", "type": "Type"}

        result = await import_service.confirm_import(session, USER, ImportEntity.transactions, "x.csv", content, mapping, False)

        assert (result.created, result.skipped_invalid) == (1, 1)
        inserted = bulk.call_args.args[1]
        assert len(inserted) == 1
        assert inserted[0].investment_id == 1
        assert inserted[0].type == TransactionType.buy
        assert inserted[0].user_id == USER.id

    @pytest.mark.asyncio
    async def test_confirm_dedups_against_existing_db_row(self, monkeypatch):
        # Existing keys arrive as DB-shaped tuples (int, date, TransactionType, Decimal, Currency,
        # Decimal); confirm they normalize to the same key as the coerced import row so it skips.
        monkeypatch.setattr(import_service.investment_repository, "list_identifiers_by_user", AsyncMock(return_value=[(1, "Apple", "AAPL", "USD")]))
        existing = [(1, date(2026, 1, 5), TransactionType.buy, Decimal("100.00"), Currency.USD, Decimal("5.000000"))]
        monkeypatch.setattr(import_service.transaction_repository, "list_dedup_keys_by_user", AsyncMock(return_value=existing))
        bulk = AsyncMock(side_effect=lambda session, txns: txns)
        monkeypatch.setattr(import_service.transaction_repository, "bulk_create", bulk)
        content = _csv("Investment,Date,Amount,Currency,Type,Quantity\nApple,2026-01-05,100,USD,buy,5\n")
        mapping = {"investment": "Investment", "date": "Date", "amount": "Amount", "currency": "Currency", "type": "Type", "quantity": "Quantity"}

        result = await import_service.confirm_import(AsyncMock(), USER, ImportEntity.transactions, "x.csv", content, mapping, False)

        assert (result.created, result.skipped_duplicate) == (0, 1)
