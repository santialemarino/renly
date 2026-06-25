# Generic CSV/XLSX import: parse a file, map columns to entity fields, validate rows, and (on
# confirm) bulk-insert. The parse/map/validate flow is entity-agnostic; per-entity persistence is a
# thin dispatch. The server re-validates on confirm — it never trusts client-supplied row data.

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import InvalidImportFileError
from app.domain.import_specs import ImportEntity, ImportSpec, get_spec
from app.models.investment import Investment
from app.models.user import User
from app.repositories import investment_repository
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


# Parses the upload into (columns, rows), translating parse failures and enforcing the row cap.
def _parse(filename: str, content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        columns, rows = parse_tabular(filename, content)
    except ValueError as exc:
        raise InvalidImportFileError(str(exc)) from exc
    if len(rows) > MAX_IMPORT_ROWS:
        raise InvalidImportFileError(f"Too many rows ({len(rows)}). Import at most {MAX_IMPORT_ROWS} rows per file.")
    return columns, rows


# Auto-detects a target-field → column mapping from the header aliases.
def _auto_detect(spec: ImportSpec, columns: list[str]) -> dict[str, str]:
    by_normalized = {column.strip().lower(): column for column in columns}
    mapping: dict[str, str] = {}
    for field in spec.fields:
        for alias in field.aliases:
            if alias in by_normalized:
                mapping[field.key] = by_normalized[alias]
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
# holds field→value dicts for the non-invalid rows (valid and duplicate), ready to persist.
def _validate_rows(
    spec: ImportSpec,
    columns: list[str],
    rows: list[list[str]],
    mapping: dict[str, str],
    existing_keys: set[str],
) -> tuple[list[ImportPreviewRow], dict[int, dict[str, object]]]:
    col_index: dict[str, int] = {}
    for index, column in enumerate(columns):
        col_index.setdefault(column, index)  # first occurrence wins on duplicate headers
    seen: set[str] = set()
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
        if errors:
            status = STATUS_INVALID
        else:
            key = str(coerced.get(spec.dedup_field, "")).strip().lower()
            if key and (key in existing_keys or key in seen):
                status = STATUS_DUPLICATE
            else:
                status = STATUS_VALID
                if key:
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


# Returns the existing dedup keys (lowercased) for the entity, used to flag duplicates.
async def _existing_keys(session: AsyncSession, user: User, entity: ImportEntity) -> set[str]:
    if entity is ImportEntity.investments:
        names = await investment_repository.list_names_by_user(session, user.id)
        return {name.strip().lower() for name in names}
    return set()


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
    existing_keys = await _existing_keys(session, user, entity)
    preview_rows, _ = _validate_rows(spec, columns, rows, applied, existing_keys)
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
    existing_keys = await _existing_keys(session, user, entity)
    preview_rows, coerced_by_index = _validate_rows(spec, columns, rows, applied, existing_keys)

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
