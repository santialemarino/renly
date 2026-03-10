from fastapi import APIRouter, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.group import (
    GroupCreate,
    GroupResponse,
    GroupSetInvestmentsBody,
    GroupUpdate,
)
from app.services import group_service

router = APIRouter(prefix="/groups", tags=["groups"])


def _to_response(group, investment_ids: list[int]) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.name,
        created_at=group.created_at,
        updated_at=group.updated_at,
        investment_ids=investment_ids,
    )


# Lists groups for the current user. Each group includes its investment ids.
@router.get("", response_model=list[GroupResponse])
async def list_groups(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[GroupResponse]:
    pairs = await group_service.list_groups(session, current_user)
    return [_to_response(g, ids) for g, ids in pairs]


# Returns a single group by id. Returns 404 if not found or not owned.
@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupResponse:
    group, ids = await group_service.get_group(session, group_id, current_user)
    return _to_response(group, ids)


# Creates a new group for the current user.
@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupResponse:
    group = await group_service.create_group(session, current_user, name=body.name)
    return _to_response(group, [])


# Updates a group. Only provided fields are updated. Returns 404 if not found.
@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    body: GroupUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupResponse:
    payload = body.model_dump(exclude_unset=True)
    group, ids = await group_service.update_group(session, group_id, current_user, **payload)
    return _to_response(group, ids)


# Deletes a group. Returns 204. Returns 404 if not found or not owned.
@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await group_service.delete_group(session, group_id, current_user)


# Replaces group membership with the given investment ids. All must belong to the user. Returns 204.
@router.put("/{group_id}/investments", status_code=status.HTTP_204_NO_CONTENT)
async def set_group_investments(
    group_id: int,
    body: GroupSetInvestmentsBody,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await group_service.set_group_investments(session, group_id, current_user, body.investment_ids)
