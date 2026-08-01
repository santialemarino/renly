from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.transfer import TransferCreate, TransferListResponse, TransferResponse, TransferUpdate
from app.services import transfer_service

router = APIRouter(prefix="/transfers", tags=["transfers"])


# List the user's transfers, newest first. Optionally narrowed to one account, matching either leg.
@router.get("", response_model=TransferListResponse)
async def list_transfers(
    current_user: CurrentUser,
    session: SessionDep,
    account_id: int | None = Query(default=None, description="Only transfers touching this account, on either leg."),
) -> TransferListResponse:
    return await transfer_service.list_transfers(session, current_user, account_id=account_id)


# Get a single transfer by id. Returns 404 when it isn't the user's.
@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(transfer_id: int, current_user: CurrentUser, session: SessionDep) -> TransferResponse:
    return await transfer_service.get_transfer_response(session, transfer_id, current_user)


# Create a transfer between two owned accounts. Returns 400 when the two accounts are the same, when a
# single-currency transfer credits a different amount than it debits, or when a cross-currency transfer
# omits the credited amount; 404 when either account isn't the user's.
@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
async def create_transfer(body: TransferCreate, current_user: CurrentUser, session: SessionDep) -> TransferResponse:
    return await transfer_service.create_transfer(
        session,
        current_user,
        from_account_id=body.from_account_id,
        to_account_id=body.to_account_id,
        date=body.date,
        from_amount=body.from_amount,
        to_amount=body.to_amount,
        notes=body.notes,
    )


# Update a transfer. Only provided fields change; the currency rules are re-checked against the
# effective account pair, so moving a leg to another currency is validated as the new shape.
@router.put("/{transfer_id}", response_model=TransferResponse)
async def update_transfer(
    transfer_id: int,
    body: TransferUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> TransferResponse:
    payload = body.model_dump(exclude_unset=True)
    return await transfer_service.update_transfer(session, transfer_id, current_user, **payload)


# Delete a transfer. Both accounts' balances recompute from the remaining rows.
@router.delete("/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transfer(transfer_id: int, current_user: CurrentUser, session: SessionDep) -> None:
    await transfer_service.delete_transfer(session, transfer_id, current_user)
