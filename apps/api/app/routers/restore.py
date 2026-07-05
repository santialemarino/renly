from fastapi import APIRouter, File, Request, Response, UploadFile

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.rate_limit import RESTORE_LIMIT, limiter
from app.schemas.restore import RestorePreviewResponse, RestoreResultResponse
from app.services import restore_service

router = APIRouter(prefix="/restore", tags=["restore"])


# NOTE: every @limiter.limit endpoint must declare `request: Request` and `response: Response`
# parameters; SlowAPI reads the request from the signature and injects rate-limit headers.


# Dry-run preview of restoring a Renly export: per-entity counts of what would be inserted vs skipped. No writes.
@router.post("/preview", response_model=RestorePreviewResponse)
@limiter.limit(RESTORE_LIMIT)
async def preview_restore(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(..., description="Renly export .json file to restore."),
) -> RestorePreviewResponse:
    content = await file.read()
    return await restore_service.preview_restore(session, current_user, file.filename or "", content)


# Re-validates the export and inserts the restorable rows (additive, non-destructive) in one transaction.
@router.post("", response_model=RestoreResultResponse)
@limiter.limit(RESTORE_LIMIT)
async def confirm_restore(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(..., description="Renly export .json file to restore."),
) -> RestoreResultResponse:
    content = await file.read()
    return await restore_service.confirm_restore(session, current_user, file.filename or "", content)
