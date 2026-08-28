from datetime import date as date_type

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import AdminSessionDep, SessionDep
from app.schemas.pot import (
    PotCreate,
    PotHoldingsMove,
    PotHoldingsResponse,
    PotMovementCreate,
    PotOpeningCreate,
    PotOwnershipEventResponse,
    PotPermissionUpdate,
    PotReagreementCreate,
    PotResponse,
    PotUpdate,
)
from app.services import pot_ownership_service, pot_service

router = APIRouter(prefix="/pots", tags=["pots"])


# Lists every pot the user may see, each with its ownership breakdown. Optionally narrowed to one
# group. A pot the user owns 0% of is still listed — membership is not ownership.
@router.get("", response_model=list[PotResponse])
async def list_pots(
    current_user: CurrentUser,
    session: SessionDep,
    group_id: int | None = Query(default=None, description="Only pots in this group."),
) -> list[PotResponse]:
    return await pot_service.list_pots(session, current_user, group_id=group_id)


# Returns one pot with its ownership breakdown, optionally as at a past date. Returns 404 when it
# does not exist or the user may not see it — the same answer for both, so probing ids reveals
# nothing about pots that are merely hidden.
@router.get("/{pot_id}", response_model=PotResponse)
async def get_pot(
    pot_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    as_of_date: date_type | None = Query(default=None, description="Date to value the pot at; defaults to today."),
) -> PotResponse:
    return await pot_service.get_pot(session, pot_id, current_user, as_of_date=as_of_date)


# Creates a pot in a group and seats its creator with full access. Group admin only (403 otherwise).
# Takes the privileged session because the pot's first permission row is the one its own RLS policy
# reads, so the insert cannot satisfy it — the same bootstrap group creation has.
@router.post("", response_model=PotResponse, status_code=status.HTTP_201_CREATED)
async def create_pot(
    body: PotCreate,
    current_user: CurrentUser,
    admin_session: AdminSessionDep,
) -> PotResponse:
    return await pot_service.create_pot(
        admin_session,
        body.group_id,
        current_user,
        base_currency=body.base_currency,
        name=body.name,
        visibility=body.visibility,
    )


# Updates a pot's name or visibility. Group admin only (403 otherwise). Only provided fields change.
@router.put("/{pot_id}", response_model=PotResponse)
async def update_pot(
    pot_id: int,
    body: PotUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> PotResponse:
    return await pot_service.update_pot(session, pot_id, current_user, name=body.name, visibility=body.visibility)


# Deletes a pot. Group admin only; refused with 409 while it still holds anything.
@router.delete("/{pot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pot(pot_id: int, current_user: CurrentUser, session: SessionDep) -> None:
    await pot_service.delete_pot(session, pot_id, current_user)


# Grants or changes one member's access to a pot. Group admin only — and being an admin is what lets
# you SET this, never what lets you read anything.
@router.put("/{pot_id}/permissions/{member_id}", response_model=PotResponse)
async def set_permission(
    pot_id: int,
    member_id: int,
    body: PotPermissionUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> PotResponse:
    return await pot_service.set_permission(session, pot_id, member_id, current_user, can_view=body.can_view, can_write=body.can_write)


# Removes a member's explicit permission row, dropping them back to the pot's visibility default.
# Group admin only.
@router.delete("/{pot_id}/permissions/{member_id}", response_model=PotResponse)
async def clear_permission(
    pot_id: int,
    member_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> PotResponse:
    return await pot_service.clear_permission(session, pot_id, member_id, current_user)


# Lists everything the pot holds, each with its own figure and the same figure in the pot's base
# currency. Readable by whoever may see the pot at all, including a member holding 0% of it — the
# monitoring surface is not gated on owning any of it (V5).
@router.get("/{pot_id}/holdings", response_model=PotHoldingsResponse)
async def list_holdings(pot_id: int, current_user: CurrentUser, session: SessionDep) -> PotHoldingsResponse:
    return await pot_service.list_holdings(session, pot_id, current_user)


# Moves holdings into the pot. Needs pot write access (403), and every named holding must be the
# caller's own private one (404 otherwise — the whole move is refused rather than partly applied).
# An account with linked entries is refused with 409: its balance derives from one user's rows, so a
# shared one would report a different figure to every member.
@router.post("/{pot_id}/holdings", response_model=PotResponse)
async def add_holdings(
    pot_id: int,
    body: PotHoldingsMove,
    current_user: CurrentUser,
    session: SessionDep,
) -> PotResponse:
    return await pot_service.move_holdings(session, pot_id, current_user, investment_ids=body.investment_ids, account_ids=body.account_ids, into=True)


# Moves holdings back out of the pot into the caller's own private scope. Needs pot write access, and
# every named holding must already belong to THIS pot.
@router.post("/{pot_id}/holdings/remove", response_model=PotResponse)
async def remove_holdings(
    pot_id: int,
    body: PotHoldingsMove,
    current_user: CurrentUser,
    session: SessionDep,
) -> PotResponse:
    return await pot_service.move_holdings(
        session, pot_id, current_user, investment_ids=body.investment_ids, account_ids=body.account_ids, into=False
    )


# Lists the pot's ownership ledger in replay order. Visible to whoever may see the pot at all,
# including a member holding 0% of it.
@router.get("/{pot_id}/ownership", response_model=list[PotOwnershipEventResponse])
async def list_ownership_events(pot_id: int, current_user: CurrentUser, session: SessionDep) -> list[PotOwnershipEventResponse]:
    return await pot_ownership_service.list_events(session, pot_id, current_user)


# Records the pot's opening baseline: its value and each owner's percentage on a date. Refused with
# 409 once a baseline exists, and with 400 when the percentages do not total 100.
# Returns one event per owner — the baseline is a division, not a single movement.
@router.post("/{pot_id}/ownership/opening", response_model=list[PotOwnershipEventResponse], status_code=status.HTTP_201_CREATED)
async def record_opening(
    pot_id: int,
    body: PotOpeningCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[PotOwnershipEventResponse]:
    return await pot_ownership_service.record_opening(
        session,
        pot_id,
        current_user,
        date=body.date,
        value=body.value,
        shares=body.shares,
        notes=body.notes,
    )


# Records a contribution or a withdrawal: money crossing the scope boundary, priced at the pot's unit
# price on the date. Needs pot write access (403 otherwise) and a known valuation on that date (400).
@router.post("/{pot_id}/ownership/movements", response_model=PotOwnershipEventResponse, status_code=status.HTTP_201_CREATED)
async def record_movement(
    pot_id: int,
    body: PotMovementCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> PotOwnershipEventResponse:
    return await pot_ownership_service.record_movement(
        session,
        pot_id,
        current_user,
        type=body.type,
        date=body.date,
        member_id=body.member_id,
        amount=body.amount,
        amount_currency=body.amount_currency,
        base_amount=body.base_amount,
        from_account_id=body.from_account_id,
        to_account_id=body.to_account_id,
        notes=body.notes,
    )


# Records a re-agreement: units moving between two members with no money at all. Taken as a
# percentage of the whole pot, because percentages go in and percentages come out.
@router.post("/{pot_id}/ownership/reagreements", response_model=PotOwnershipEventResponse, status_code=status.HTTP_201_CREATED)
async def record_reagreement(
    pot_id: int,
    body: PotReagreementCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> PotOwnershipEventResponse:
    return await pot_ownership_service.record_reagreement(
        session,
        pot_id,
        current_user,
        date=body.date,
        from_member_id=body.from_member_id,
        to_member_id=body.to_member_id,
        percentage=body.percentage,
        notes=body.notes,
    )


# Deletes an ownership event. Balances are derived, so the series simply recomputes without it.
@router.delete("/{pot_id}/ownership/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ownership_event(pot_id: int, event_id: int, current_user: CurrentUser, session: SessionDep) -> None:
    await pot_ownership_service.delete_event(session, pot_id, event_id, current_user)
