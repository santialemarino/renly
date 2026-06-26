import json

from fastapi import APIRouter, File, Form, Request, Response, UploadFile

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.domain import InvalidImportFileError
from app.domain.import_specs import ImportEntity
from app.rate_limit import IMPORT_LIMIT, limiter
from app.schemas.imports import ImportPreviewResponse, ImportResultResponse
from app.services import import_service

router = APIRouter(prefix="/imports", tags=["imports"])


# Parses the multipart `mapping` form field (a JSON object of field→column). Empty when omitted.
def _parse_mapping(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidImportFileError("The column mapping is not valid.") from exc
    if not isinstance(parsed, dict):
        raise InvalidImportFileError("The column mapping is not valid.")
    return {str(key): str(value) for key, value in parsed.items()}


# NOTE: every @limiter.limit endpoint must declare `request: Request` and `response: Response`
# parameters; SlowAPI reads the request from the signature and injects rate-limit headers.


# Dry-run preview of an import file: detected columns, suggested mapping, per-row validation. No writes.
@router.post("/{entity}/preview", response_model=ImportPreviewResponse)
@limiter.limit(IMPORT_LIMIT)
async def preview_import(
    entity: ImportEntity,
    request: Request,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(..., description="CSV or XLSX file to import."),
    mapping: str | None = Form(default=None, description="Optional JSON mapping of field → source column."),
) -> ImportPreviewResponse:
    content = await file.read()
    return await import_service.preview_import(session, current_user, entity, file.filename or "", content, _parse_mapping(mapping))


# Re-validates the file and bulk-inserts the importable rows. Returns created/skipped counts.
@router.post("/{entity}", response_model=ImportResultResponse)
@limiter.limit(IMPORT_LIMIT)
async def confirm_import(
    entity: ImportEntity,
    request: Request,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(..., description="CSV or XLSX file to import."),
    mapping: str = Form(..., description="JSON mapping of field → source column."),
    import_duplicates: bool = Form(default=False, description="Import rows flagged as duplicates too."),
) -> ImportResultResponse:
    content = await file.read()
    return await import_service.confirm_import(
        session, current_user, entity, file.filename or "", content, _parse_mapping(mapping), import_duplicates
    )
