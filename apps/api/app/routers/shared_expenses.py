from fastapi import APIRouter, status

from app.deps.auth import CurrentUser
from app.deps.currency import DisplayCurrency
from app.deps.db import SessionDep
from app.schemas.shared_expense import SharedExpenseCreate, SharedExpenseResponse, SharedExpenseUpdate
from app.services import shared_expense_service

# Nested under the group because a shared expense has no meaning outside one: every seat it names, the
# balance it moves and the membership that gates it all belong to that group. Its own prefix rather
# than a block inside /groups keeps the group router about the people entity, which is what lets that
# entity stay money-agnostic.
router = APIRouter(prefix="/groups/{group_id}/expenses", tags=["shared money"])


# Lists a group's shared expenses, newest first, each with every member's position in it. Returns 404
# when the group does not exist or the caller is not an active member — the same answer for both.
@router.get("", response_model=list[SharedExpenseResponse])
async def list_shared_expenses(
    group_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: DisplayCurrency = None,
) -> list[SharedExpenseResponse]:
    return await shared_expense_service.list_expenses(session, group_id, current_user, currency=currency)


# Records a shared expense and divides it. Returns 400 for a split that does not add up, a funding
# account in another group's pot, or joint money with no agreed division; 404 for a seat, account or
# card that is not reachable.
@router.post("", response_model=SharedExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_shared_expense(
    group_id: int,
    body: SharedExpenseCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SharedExpenseResponse:
    return await shared_expense_service.create_expense(
        session,
        group_id,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        split_method=body.split_method,
        splits=body.splits,
        category=body.category,
        notes=body.notes,
        payer_member_id=body.payer_member_id,
        paid_from_account_id=body.paid_from_account_id,
        payment_method=body.payment_method,
        credit_card_id=body.credit_card_id,
    )


# Replaces a shared expense and its whole split set. A full replacement rather than a partial update:
# the amount, the method and the participants are one interlocking statement.
@router.put("/{expense_id}", response_model=SharedExpenseResponse)
async def update_shared_expense(
    group_id: int,
    expense_id: int,
    body: SharedExpenseUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SharedExpenseResponse:
    return await shared_expense_service.update_expense(
        session,
        group_id,
        expense_id,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        split_method=body.split_method,
        splits=body.splits,
        category=body.category,
        notes=body.notes,
        payer_member_id=body.payer_member_id,
        paid_from_account_id=body.paid_from_account_id,
        payment_method=body.payment_method,
        credit_card_id=body.credit_card_id,
    )


# Deletes a shared expense with its splits. Returns 204.
@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shared_expense(
    group_id: int,
    expense_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await shared_expense_service.delete_expense(session, group_id, expense_id, current_user)
