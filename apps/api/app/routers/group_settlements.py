from fastapi import APIRouter, status

from app.deps.auth import CurrentUser
from app.deps.currency import DisplayCurrency
from app.deps.db import SessionDep
from app.schemas.group_settlement import (
    GroupBalancesResponse,
    GroupMoneySettingsResponse,
    GroupMoneySettingsUpdate,
    GroupSettlementCreate,
    GroupSettlementLegUpdate,
    GroupSettlementResponse,
    GroupWriteOffCreate,
)
from app.services import group_money_service, group_settlement_service

# The balances half of a group's money, on its own prefix for the same reason the expenses half is:
# the group router stays about the people entity, which is what keeps that entity money-agnostic.
router = APIRouter(prefix="/groups/{group_id}", tags=["shared money"])


# Returns every member's balance per currency, plus the fewest payments that clear each bucket.
# Balances never net across currencies — each is its own settle line — so a member can appear as a
# creditor in one bucket and a debtor in another.
@router.get("/balances", response_model=GroupBalancesResponse)
async def get_group_balances(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency = None,
) -> GroupBalancesResponse:
    return await group_settlement_service.get_balances(session, group_id, current_user, currency=currency)


# Lists the group's recorded settlements and write-offs, newest first.
@router.get("/settlements", response_model=list[GroupSettlementResponse])
async def list_group_settlements(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[GroupSettlementResponse]:
    return await group_settlement_service.list_settlements(session, group_id, current_user)


# Records a payment one member made to another. Lands pending unless the group has opted into
# auto-finalise. Returns 400 for a leg that names an amount without an account, or crosses currencies
# without saying what moved; 404 for a seat or account that is not reachable.
@router.post("/settlements", response_model=GroupSettlementResponse, status_code=status.HTTP_201_CREATED)
async def create_group_settlement(
    group_id: int,
    body: GroupSettlementCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupSettlementResponse:
    return await group_settlement_service.record_settlement(
        session,
        group_id,
        current_user,
        from_member_id=body.from_member_id,
        to_member_id=body.to_member_id,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        from_account_id=body.from_account_id,
        from_amount=body.from_amount,
        to_account_id=body.to_account_id,
        to_amount=body.to_amount,
        notes=body.notes,
    )


# Records a debt the creditor gives up on. Clears the same bucket a payment would and moves no money.
# Returns 403 when the caller is not the seat being owed.
@router.post("/settlements/write-off", response_model=GroupSettlementResponse, status_code=status.HTTP_201_CREATED)
async def create_group_write_off(
    group_id: int,
    body: GroupWriteOffCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupSettlementResponse:
    return await group_settlement_service.record_write_off(
        session,
        group_id,
        current_user,
        from_member_id=body.from_member_id,
        to_member_id=body.to_member_id,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        notes=body.notes,
    )


# Acknowledges receipt of a pending settlement. Only the payee may (403 otherwise); returns 409 when
# it is already confirmed.
@router.post("/settlements/{settlement_id}/confirm", response_model=GroupSettlementResponse)
async def confirm_group_settlement(
    group_id: int,
    settlement_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupSettlementResponse:
    return await group_settlement_service.confirm_settlement(session, group_id, settlement_id, current_user)


# Takes a confirmation back, returning the settlement to pending so it can be corrected or removed.
# Only the payee may (403 otherwise).
@router.delete("/settlements/{settlement_id}/confirm", response_model=GroupSettlementResponse)
async def unconfirm_group_settlement(
    group_id: int,
    settlement_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupSettlementResponse:
    return await group_settlement_service.unconfirm_settlement(session, group_id, settlement_id, current_user)


# Attaches or clears the caller's OWN cash leg. Which side it lands on follows from which seat they
# hold, so nothing in the body names a side. Returns 400 when the caller is on neither side, and 409
# for a write-off, which moved no money to attach an account to.
@router.put("/settlements/{settlement_id}/account", response_model=GroupSettlementResponse)
async def set_group_settlement_leg(
    group_id: int,
    settlement_id: int,
    body: GroupSettlementLegUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupSettlementResponse:
    return await group_settlement_service.set_leg(
        session,
        group_id,
        settlement_id,
        current_user,
        account_id=body.account_id,
        leg_amount=body.amount,
    )


# Removes a settlement — which is what reversing one is. Either named member may while it is pending;
# a write-off only its creditor. A confirmed settlement is refused with 409 until it is un-confirmed.
@router.delete("/settlements/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_settlement(
    group_id: int,
    settlement_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await group_settlement_service.delete_settlement(session, group_id, settlement_id, current_user)


# Returns the group's shared money settings.
@router.get("/money-settings", response_model=GroupMoneySettingsResponse)
async def get_group_money_settings(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupMoneySettingsResponse:
    return await group_money_service.get_settings(session, group_id, current_user)


# Updates the group's shared money settings. Admin only (403 otherwise) — setting the standard the
# group holds itself to is management, not money movement.
@router.put("/money-settings", response_model=GroupMoneySettingsResponse)
async def update_group_money_settings(
    group_id: int,
    body: GroupMoneySettingsUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> GroupMoneySettingsResponse:
    return await group_money_service.update_settings(
        session,
        group_id,
        current_user,
        default_split_method=body.default_split_method,
        auto_finalise_settlements=body.auto_finalise_settlements,
    )
