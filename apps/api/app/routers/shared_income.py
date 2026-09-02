from fastapi import APIRouter, status

from app.deps.auth import CurrentUser
from app.deps.currency import DisplayCurrency
from app.deps.db import SessionDep
from app.schemas.shared_income import SharedIncomeCreate, SharedIncomeResponse, SharedIncomeUpdate
from app.services import shared_income_service

# Nested under the group because shared income has no meaning outside one: every seat it names, the
# balance it moves and the membership that gates it all belong to that group. Its own prefix rather
# than a block inside /groups keeps the group router about the people entity, which is what lets that
# entity stay money-agnostic.
router = APIRouter(prefix="/groups/{group_id}/income", tags=["shared money"])


# Lists a group's shared income, newest first, each row with every member's position in it. Returns 404
# when the group does not exist or the caller is not an active member — the same answer for both.
@router.get("", response_model=list[SharedIncomeResponse])
async def list_shared_income(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency = None,
) -> list[SharedIncomeResponse]:
    return await shared_income_service.list_income(session, group_id, current_user, currency=currency)


# Records a piece of shared income and divides it. Returns 400 for a split that does not add up, a
# destination that contradicts where the money landed, a shared account in another group's pot or one
# with no agreed division, or a source asset this group's pots do not hold; 404 for a seat or account
# that is not reachable.
@router.post("", response_model=SharedIncomeResponse, status_code=status.HTTP_201_CREATED)
async def create_shared_income(
    group_id: int,
    body: SharedIncomeCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SharedIncomeResponse:
    return await shared_income_service.create_income(
        session,
        group_id,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        split_method=body.split_method,
        splits=body.splits,
        destination=body.destination,
        category=body.category,
        notes=body.notes,
        source_investment_id=body.source_investment_id,
        received_by_member_id=body.received_by_member_id,
        paid_to_account_id=body.paid_to_account_id,
    )


# Replaces a piece of shared income and its whole split set. A full replacement rather than a partial
# update: the amount, the method and the participants are one interlocking statement.
@router.put("/{income_id}", response_model=SharedIncomeResponse)
async def update_shared_income(
    group_id: int,
    income_id: int,
    body: SharedIncomeUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SharedIncomeResponse:
    return await shared_income_service.update_income(
        session,
        group_id,
        income_id,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        split_method=body.split_method,
        splits=body.splits,
        destination=body.destination,
        category=body.category,
        notes=body.notes,
        source_investment_id=body.source_investment_id,
        received_by_member_id=body.received_by_member_id,
        paid_to_account_id=body.paid_to_account_id,
    )


# Deletes a piece of shared income with its splits. Returns 204.
@router.delete("/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shared_income(
    group_id: int,
    income_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await shared_income_service.delete_income(session, group_id, income_id, current_user)
