from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.collection import (
    CollectionCreate,
    CollectionResponse,
    CollectionSetInvestmentsBody,
    CollectionUpdate,
)
from app.services import collection_service

router = APIRouter(prefix="/collections", tags=["collections"])


# Builds a CollectionResponse from the model plus its member investment ids.
def _to_response(collection, investment_ids: list[int]) -> CollectionResponse:
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        target_percentage=collection.target_percentage,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        investment_ids=investment_ids,
    )


# Lists collections for the user with optional search and sorting. Each includes its investment ids.
@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter collections by name (case-insensitive substring match)."),
    sort_by: str | None = Query(default=None, description="Column to sort by (name)."),
    sort_order: str = Query(default="asc", description="Sort direction (asc or desc)."),
) -> list[CollectionResponse]:
    pairs = await collection_service.list_collections(session, current_user, search=search, sort_by=sort_by, sort_order=sort_order)
    return [_to_response(c, ids) for c, ids in pairs]


# Returns a single collection by id. Returns 404 if not found or not owned.
@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> CollectionResponse:
    collection, ids = await collection_service.get_collection(session, collection_id, current_user)
    return _to_response(collection, ids)


# Creates a new collection for the user.
@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> CollectionResponse:
    collection = await collection_service.create_collection(
        session,
        current_user,
        name=body.name,
        target_percentage=body.target_percentage,
    )
    return _to_response(collection, [])


# Updates a collection. Only provided fields are updated. Returns 404 if not found.
@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: int,
    body: CollectionUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> CollectionResponse:
    payload = body.model_dump(exclude_unset=True)
    collection, ids = await collection_service.update_collection(session, collection_id, current_user, **payload)
    return _to_response(collection, ids)


# Deletes a collection. Returns 204. Returns 404 if not found or not owned.
@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await collection_service.delete_collection(session, collection_id, current_user)


# Replaces collection membership with the given investment ids. All must belong to the user. Returns 204.
@router.put("/{collection_id}/investments", status_code=status.HTTP_204_NO_CONTENT)
async def set_collection_investments(
    collection_id: int,
    body: CollectionSetInvestmentsBody,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await collection_service.set_collection_investments(session, collection_id, current_user, body.investment_ids)
