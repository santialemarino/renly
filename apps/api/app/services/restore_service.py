# Restore-from-export: re-import a Renly JSON export (the inverse of GET /me/export). Additive and
# non-destructive — it only inserts, never deletes or overwrites. Rows are inserted in spec order
# (parents first); each child FK is remapped from the exported id to the freshly inserted id, and a row
# whose required parent can't be resolved is skipped. It does NOT dedup (see restore_specs), so it is not
# idempotent — re-restoring adds everything again; it targets a fresh account. The confirm path re-runs
# the whole plan server-side — it never trusts client-supplied counts.

import json
import logging
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Date, DateTime, Enum, Numeric
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.domain import InvalidImportFileError
from app.domain.restore_specs import RESTORE_SPECS, SKIPPED_ENTITIES, RestoreSpec
from app.models.user import User
from app.repositories import restore_repository
from app.schemas.restore import RestoreEntityStat, RestorePreviewResponse, RestoreResultResponse

logger = logging.getLogger(__name__)


# Parses the upload into the export object: a Renly export is a JSON object with known top-level keys.
# parse_float=Decimal keeps monetary precision (JSON has no fixed scale, so amounts round-trip exact).
def _parse_export(filename: str, content: bytes) -> dict[str, Any]:
    if not filename.lower().endswith(".json"):
        raise InvalidImportFileError("Restore requires a Renly export .json file.")
    try:
        data = json.loads(content.decode("utf-8"), parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidImportFileError("The file is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise InvalidImportFileError("The file is not a Renly export.")
    known = {"user", *(spec.key for spec in RESTORE_SPECS)}
    if not known.intersection(data):
        raise InvalidImportFileError("The file is not a Renly export.")
    return data


# Rebuilds a model instance from an exported row, coercing JSON scalars to the column types (SQLModel
# table models don't validate on construction) and requiring every non-nullable, defaultless column.
def _build_model(model_cls: type[SQLModel], values: dict[str, Any]) -> SQLModel:
    kwargs: dict[str, Any] = {}
    for column in model_cls.__table__.columns:  # type: ignore[attr-defined]
        name = column.name
        required = not column.nullable and column.default is None and column.server_default is None and not column.primary_key
        if name not in values or values[name] is None:
            if required:
                raise ValueError(f"Missing required field '{name}'.")
            continue
        value = values[name]
        column_type = column.type
        try:
            if isinstance(column_type, Enum) and getattr(column_type, "enum_class", None) is not None:
                enum_cls = column_type.enum_class
                value = value if isinstance(value, enum_cls) else enum_cls(value)
            elif isinstance(column_type, DateTime):
                value = datetime.fromisoformat(value) if isinstance(value, str) else value
                # The export serializes timestamps from timestamptz columns, so they carry a UTC
                # offset, while the models declare a naive datetime (they default to utcnow(), which
                # returns naive UTC). asyncpg binds strictly to the declared type and rejects a
                # tz-aware value for a naive column, which failed every real export on the first
                # entity. Convert to UTC, then drop the tzinfo so the instant is preserved.
                if value.tzinfo is not None and not column_type.timezone:
                    value = value.astimezone(UTC).replace(tzinfo=None)
            elif isinstance(column_type, Date):
                value = date_type.fromisoformat(value) if isinstance(value, str) else value
            elif isinstance(column_type, Numeric):
                value = value if isinstance(value, Decimal) else Decimal(str(value))
        # AttributeError joins the coercion failures because the tz check above dereferences .tzinfo on
        # whatever the file supplied — a JSON number or object for a timestamp column reaches it as an
        # int/Decimal/dict. Without it the row escapes as a 500 from both /restore and its read-only
        # preview, instead of being counted unresolved like every other value the file gets wrong.
        except (AttributeError, ValueError, InvalidOperation) as exc:
            raise ValueError(f"Invalid value for '{name}'.") from exc
        kwargs[name] = value
    return model_cls(**kwargs)


# Runs the restore plan for one entity: remap FKs, build models, and (when apply) insert every valid
# row. Mutates id_maps[spec.key] with old-id → new-id so later specs can remap their children. No dedup —
# a row whose required parent can't be resolved (or whose data is invalid) is counted as unresolved.
async def _restore_entity(
    session: AsyncSession,
    user: User,
    spec: RestoreSpec,
    rows: list[Any],
    id_maps: dict[str, dict[int, int]],
    placeholder: list[int],
    apply: bool,
) -> RestoreEntityStat:
    id_map: dict[int, int] = {}
    to_insert: list[SQLModel] = []
    insert_old_ids: list[int | None] = []
    restore_count = skipped_unresolved = 0

    for raw in rows:
        if not isinstance(raw, dict):
            skipped_unresolved += 1
            continue
        old_id = raw.get("id") if spec.has_id else None
        prepared = dict(raw)
        prepared.pop("id", None)
        if spec.has_user_id:
            prepared["user_id"] = user.id
        for null_field in spec.null_fields:
            prepared[null_field] = None

        unresolved = False
        for fk in spec.fks:
            old_fk = raw.get(fk.field)
            resolved = None if old_fk is None else id_maps.get(fk.parent, {}).get(old_fk)
            if resolved is None:
                # A required FK that is null in the file, or points at a parent that wasn't restored,
                # can't be rebuilt at all; an optional one is dropped along with anything that only
                # made sense while it pointed somewhere.
                if fk.required:
                    unresolved = True
                    break
                prepared[fk.field] = None
                for dependent in fk.dependents:
                    prepared[dependent] = None
            else:
                prepared[fk.field] = resolved
        if unresolved:
            skipped_unresolved += 1
            continue

        try:
            model = _build_model(spec.model, prepared)
        except ValueError:
            skipped_unresolved += 1
            continue

        restore_count += 1
        to_insert.append(model)
        insert_old_ids.append(old_id)

    if apply and to_insert:
        await restore_repository.bulk_insert(session, to_insert)

    for old_id, model in zip(insert_old_ids, to_insert, strict=True):
        new_id = getattr(model, "id", None) if apply else placeholder[0]
        if not apply:
            placeholder[0] -= 1
        if spec.has_id and old_id is not None and new_id is not None:
            id_map[old_id] = new_id

    id_maps[spec.key] = id_map
    return RestoreEntityStat(entity=spec.key, restore=restore_count, skipped_unresolved=skipped_unresolved)


# Runs the plan across every entity in order. apply=False is a dry run (placeholder ids, no writes).
async def _run(session: AsyncSession, user: User, data: dict[str, Any], apply: bool) -> list[RestoreEntityStat]:
    id_maps: dict[str, dict[int, int]] = {}
    placeholder = [-1]
    stats: list[RestoreEntityStat] = []
    for spec in RESTORE_SPECS:
        rows = data.get(spec.key)
        rows = rows if isinstance(rows, list) else []
        stats.append(await _restore_entity(session, user, spec, rows, id_maps, placeholder, apply))
    return stats


# Builds a dry-run plan for a restore file: per-entity counts of what would be inserted vs skipped.
async def preview_restore(session: AsyncSession, user: User, filename: str, content: bytes) -> RestorePreviewResponse:
    data = _parse_export(filename, content)
    exported_at = data.get("exported_at")
    stats = await _run(session, user, data, apply=False)
    return RestorePreviewResponse(
        recognized=True,
        exported_at=exported_at if isinstance(exported_at, str) else None,
        entities=stats,
        skipped_entities=[name for name in SKIPPED_ENTITIES if name in data],
    )


# Re-runs the plan server-side and inserts the restorable rows in one transaction. Any database-level
# rejection from a malformed/tampered export rolls the whole transaction back (nothing is written) and
# surfaces as a 400 rather than a 500 — the documented contract for a bad file. DBAPIError is the
# widest wrapper on purpose: _build_model already rejects a value it can coerce (that row is counted
# unresolved instead), so what still reaches the driver is a value only Postgres can refuse — an
# over-length string, a non-numeric int — and asyncpg reports several of those as a plain DataError
# that SQLAlchemy does not map to a more specific class. The trace is logged server-side so a genuine
# infrastructure failure caught by the same net stays diagnosable.
async def confirm_restore(session: AsyncSession, user: User, filename: str, content: bytes) -> RestoreResultResponse:
    data = _parse_export(filename, content)
    try:
        stats = await _run(session, user, data, apply=True)
        await session.commit()
    except DBAPIError as exc:
        logger.exception("Restore failed at the database layer", exc_info=exc)
        raise InvalidImportFileError("The export could not be restored; it may be incomplete or from an incompatible version.") from exc
    return RestoreResultResponse(
        restored=sum(stat.restore for stat in stats),
        skipped_unresolved=sum(stat.skipped_unresolved for stat in stats),
        entities=stats,
    )
