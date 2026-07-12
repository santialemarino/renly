# Generic CSV/XLSX import: parse a file, map columns to entity fields, validate rows, and (on
# confirm) bulk-insert. The parse/map/validate flow is entity-agnostic; per-entity persistence is a
# thin dispatch. The server re-validates on confirm — it never trusts client-supplied row data.

from collections.abc import Callable
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import InvalidImportFileError
from app.domain.import_specs import ImportEntity, ImportSpec, get_spec
from app.models.expense_entry import ExpenseEntry
from app.models.income_entry import IncomeEntry
from app.models.investment import Investment
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories import (
    expense_repository,
    income_repository,
    investment_repository,
    snapshot_repository,
    transaction_repository,
)
from app.schemas.imports import (
    ImportFieldInfo,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportResultResponse,
    ImportSummary,
)
from app.utils.tabular import parse_tabular

# Caps a single import to bound work and stay within the request body-size limit.
MAX_IMPORT_ROWS = 1000

STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_DUPLICATE = "duplicate"


# Human label for a field key, used in "<field> is required" messages.
def _label(key: str) -> str:
    return key.replace("_", " ").capitalize()


# Normalizes one dedup-key component to a comparable string (dates ISO, decimals canonical, else lowercased).
def _key_part(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, date_type):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value).strip().lower()


# Builds the composite dedup key (a tuple of normalized parts) for a coerced row's field values.
def _dedup_key(fields: tuple[str, ...], values: dict[str, object]) -> tuple[str, ...]:
    return tuple(_key_part(values.get(field)) for field in fields)


# Builds the dedup key from an existing DB row whose columns are in the spec's dedup_fields order.
def _row_dedup_key(spec: ImportSpec, row: tuple[object, ...]) -> tuple[str, ...]:
    return _dedup_key(spec.dedup_fields, dict(zip(spec.dedup_fields, row, strict=True)))


# Parses the upload into (columns, rows), translating parse failures and enforcing the row cap.
def _parse(filename: str, content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        columns, rows = parse_tabular(filename, content)
    except ValueError as exc:
        raise InvalidImportFileError(str(exc)) from exc
    if len(rows) > MAX_IMPORT_ROWS:
        raise InvalidImportFileError(f"Too many rows ({len(rows)}). Import at most {MAX_IMPORT_ROWS} rows per file.")
    return columns, rows


# Auto-detects a target-field → column mapping from the header aliases. Each field takes the first
# matching column in file order (not alias order) so the result is deterministic when several of a
# field's aliases appear as columns.
def _auto_detect(spec: ImportSpec, columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for field in spec.fields:
        for column in columns:
            if column.strip().lower() in field.aliases:
                mapping[field.key] = column
                break
    return mapping


# Resolves the mapping to use: the caller's (filtered to real fields/columns) or auto-detected.
def _resolve_mapping(spec: ImportSpec, columns: list[str], mapping: dict[str, str]) -> dict[str, str]:
    if not mapping:
        return _auto_detect(spec, columns)
    field_keys = {field.key for field in spec.fields}
    column_set = set(columns)
    return {key: column for key, column in mapping.items() if key in field_keys and column in column_set}


# Validates every data row against the spec. Returns (preview_rows, coerced_by_index) where coerced
# holds field→value dicts for the non-invalid rows (valid and duplicate), ready to persist. `resolve`
# (nested entities only) turns a reference field into a foreign key or raises ValueError → invalid.
def _validate_rows(
    spec: ImportSpec,
    columns: list[str],
    rows: list[list[str]],
    mapping: dict[str, str],
    existing_keys: set[tuple[str, ...]],
    resolve: Callable[[dict[str, object]], None] | None = None,
) -> tuple[list[ImportPreviewRow], dict[int, dict[str, object]]]:
    col_index: dict[str, int] = {}
    for index, column in enumerate(columns):
        col_index.setdefault(column, index)  # first occurrence wins on duplicate headers
    seen: set[tuple[str, ...]] = set()
    preview_rows: list[ImportPreviewRow] = []
    coerced_by_index: dict[int, dict[str, object]] = {}
    for index, row in enumerate(rows):
        values: dict[str, str] = {}
        errors: list[str] = []
        coerced: dict[str, object] = {}
        for field in spec.fields:
            column = mapping.get(field.key)
            raw = row[col_index[column]].strip() if column is not None and column in col_index else ""
            if column is not None:
                values[field.key] = raw
            if not raw:
                if field.required:
                    errors.append(f"{_label(field.key)} is required.")
                continue
            try:
                coerced[field.key] = field.coerce(raw)
            except ValueError as exc:
                errors.append(str(exc))
        if not errors and resolve is not None:
            try:
                resolve(coerced)
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            status = STATUS_INVALID
        else:
            key = _dedup_key(spec.dedup_fields, coerced)
            if any(key) and (key in existing_keys or key in seen):
                status = STATUS_DUPLICATE
            else:
                status = STATUS_VALID
                if any(key):
                    seen.add(key)
            coerced_by_index[index] = coerced
        preview_rows.append(ImportPreviewRow(row_number=index + 1, values=values, status=status, errors=errors))
    return preview_rows, coerced_by_index


# Summarizes preview rows into counts by outcome.
def _summarize(rows: list[ImportPreviewRow]) -> ImportSummary:
    return ImportSummary(
        total=len(rows),
        valid=sum(1 for row in rows if row.status == STATUS_VALID),
        invalid=sum(1 for row in rows if row.status == STATUS_INVALID),
        duplicate=sum(1 for row in rows if row.status == STATUS_DUPLICATE),
    )


# Returns the existing dedup keys for the entity (same normalization as new rows), to flag duplicates.
async def _existing_keys(session: AsyncSession, user: User, spec: ImportSpec) -> set[tuple[str, ...]]:
    if spec.entity is ImportEntity.investments:
        names = await investment_repository.list_names_by_user(session, user.id)
        return {_dedup_key(spec.dedup_fields, {"name": name}) for name in names}
    if spec.entity is ImportEntity.expenses:
        rows = await expense_repository.list_dedup_keys_by_user(session, user.id)
        return {_row_dedup_key(spec, row) for row in rows}
    if spec.entity is ImportEntity.income:
        rows = await income_repository.list_dedup_keys_by_user(session, user.id)
        return {_row_dedup_key(spec, row) for row in rows}
    if spec.entity is ImportEntity.transactions:
        rows = await transaction_repository.list_dedup_keys_by_user(session, user.id)
        return {_row_dedup_key(spec, row) for row in rows}
    return set()


# Builds a resolver mapping a row's `investment` identifier to `investment_id`, for nested entities.
# Matches ticker first, then name; ambiguous matches resolve to the lowest (oldest) id. Returns None
# for top-level entities. The resolver raises ValueError for an unmatched identifier (→ invalid row).
# Also validates the row's currency against the resolved investment's base currency — a mismatched
# row is invalid, mirroring the API's 400.
async def _build_resolver(session: AsyncSession, user: User, entity: ImportEntity) -> Callable[[dict[str, object]], None] | None:
    if entity not in (ImportEntity.snapshots, ImportEntity.transactions):
        return None
    identifiers = await investment_repository.list_identifiers_by_user(session, user.id)
    by_ticker: dict[str, int] = {}
    by_name: dict[str, int] = {}
    base_by_id: dict[int, str] = {}
    for investment_id, name, ticker, base_currency in identifiers:
        by_name.setdefault(name.strip().lower(), investment_id)
        if ticker:
            by_ticker.setdefault(ticker.strip().upper(), investment_id)
        base_by_id[investment_id] = base_currency

    def resolve(values: dict[str, object]) -> None:
        raw = str(values.get("investment", "")).strip()
        investment_id = by_ticker.get(raw.upper())
        if investment_id is None:
            investment_id = by_name.get(raw.lower())
        if investment_id is None:
            raise ValueError(f"Investment '{raw}' not found.")
        row_currency = str(values["currency"])
        base_currency = base_by_id[investment_id]
        if row_currency != base_currency:
            raise ValueError(f"Currency {row_currency} does not match the investment's base currency ({base_currency}).")
        values["investment_id"] = investment_id

    return resolve


# Persists the coerced importable rows for the entity. Returns the number created.
async def _persist(session: AsyncSession, user: User, entity: ImportEntity, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    if entity is ImportEntity.investments:
        investments = [
            Investment(
                user_id=user.id,
                name=row["name"],
                category=row["category"],
                base_currency=row["base_currency"],
                ticker=row.get("ticker"),
                broker=row.get("broker"),
                notes=row.get("notes"),
            )
            for row in rows
        ]
        created = await investment_repository.bulk_create(session, investments)
        return len(created)
    if entity is ImportEntity.expenses:
        expenses = [
            ExpenseEntry(
                user_id=user.id,
                date=row["date"],
                amount=row["amount"],
                currency=row["currency"],
                category=row.get("category"),
                payment_method=row.get("payment_method"),
                notes=row.get("notes"),
                source="manual",
            )
            for row in rows
        ]
        created = await expense_repository.bulk_create(session, expenses)
        return len(created)
    if entity is ImportEntity.income:
        income_entries = [
            IncomeEntry(
                user_id=user.id,
                date=row["date"],
                amount=row["amount"],
                currency=row["currency"],
                category=row.get("category"),
                notes=row.get("notes"),
                source="manual",
            )
            for row in rows
        ]
        created = await income_repository.bulk_create(session, income_entries)
        return len(created)
    if entity is ImportEntity.snapshots:
        # Collapse within-file duplicates on (investment_id, date) — last row wins — so the upsert's
        # single statement never updates the same conflict target twice.
        collapsed: dict[tuple[object, object], dict[str, object]] = {}
        for row in rows:
            collapsed[(row["investment_id"], row["date"])] = row
        snapshots = [
            InvestmentSnapshot(
                investment_id=row["investment_id"],
                user_id=user.id,
                date=row["date"],
                value=row["value"],
                quantity=row.get("quantity"),
                currency=row["currency"],
                source="manual",
                notes=row.get("notes"),
            )
            for row in collapsed.values()
        ]
        return await snapshot_repository.bulk_upsert(session, snapshots)
    if entity is ImportEntity.transactions:
        transactions = [
            Transaction(
                investment_id=row["investment_id"],
                user_id=user.id,
                date=row["date"],
                amount=row["amount"],
                quantity=row.get("quantity"),
                currency=row["currency"],
                type=row["type"],
                notes=row.get("notes"),
            )
            for row in rows
        ]
        created = await transaction_repository.bulk_create(session, transactions)
        return len(created)
    return 0


# Builds a dry-run preview for an import file: detected columns, applied mapping, per-row validation.
async def preview_import(
    session: AsyncSession,
    user: User,
    entity: ImportEntity,
    filename: str,
    content: bytes,
    mapping: dict[str, str],
) -> ImportPreviewResponse:
    spec = get_spec(entity)
    columns, rows = _parse(filename, content)
    applied = _resolve_mapping(spec, columns, mapping)
    existing_keys = await _existing_keys(session, user, spec)
    resolve = await _build_resolver(session, user, entity)
    preview_rows, _ = _validate_rows(spec, columns, rows, applied, existing_keys, resolve)
    return ImportPreviewResponse(
        columns=columns,
        fields=[ImportFieldInfo(key=field.key, required=field.required) for field in spec.fields],
        mapping=applied,
        rows=preview_rows,
        summary=_summarize(preview_rows),
    )


# Re-validates the file (server is source of truth) and bulk-inserts the importable rows.
async def confirm_import(
    session: AsyncSession,
    user: User,
    entity: ImportEntity,
    filename: str,
    content: bytes,
    mapping: dict[str, str],
    import_duplicates: bool,
) -> ImportResultResponse:
    spec = get_spec(entity)
    columns, rows = _parse(filename, content)
    applied = _resolve_mapping(spec, columns, mapping)
    existing_keys = await _existing_keys(session, user, spec)
    resolve = await _build_resolver(session, user, entity)
    preview_rows, coerced_by_index = _validate_rows(spec, columns, rows, applied, existing_keys, resolve)

    importable: list[dict[str, object]] = []
    skipped_invalid = 0
    skipped_duplicate = 0
    for row in preview_rows:
        if row.status == STATUS_INVALID:
            skipped_invalid += 1
        elif row.status == STATUS_DUPLICATE and not import_duplicates:
            skipped_duplicate += 1
        else:
            importable.append(coerced_by_index[row.row_number - 1])

    created = await _persist(session, user, entity, importable)
    await session.commit()
    return ImportResultResponse(created=created, skipped_invalid=skipped_invalid, skipped_duplicate=skipped_duplicate)
