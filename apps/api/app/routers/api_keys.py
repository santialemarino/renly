from fastapi import APIRouter, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreateResponse, ApiKeyResponse
from app.services import api_key_service

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# List all active API keys for the current user.
@router.get("", response_model=list[ApiKeyResponse])
async def list_keys(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[ApiKeyResponse]:
    keys = await api_key_service.list_keys(session, current_user)
    return [ApiKeyResponse.model_validate(k) for k in keys]


# Generate a new API key. Returns the raw key once.
@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> ApiKeyCreateResponse:
    key, raw_key = await api_key_service.create_key(session, current_user, name=body.name)
    return ApiKeyCreateResponse(
        id=key.id,
        name=key.name,
        raw_key=raw_key,
        created_at=key.created_at,
        is_active=key.is_active,
    )


# Revoke an API key (soft-delete). Returns 204.
@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await api_key_service.revoke_key(session, key_id, current_user)
