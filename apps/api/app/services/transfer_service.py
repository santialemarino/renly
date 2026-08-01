# Transfers: moving money between two accounts the user owns.
#
# A transfer is the one movement that is neither income nor an expense — net worth does not change,
# the money just leaves one pool and arrives in another. That makes it the missing primitive for an
# ATM withdrawal (bank −X, cash +X) and for buying or selling dollars, both of which would otherwise
# have to be faked as an expense plus an income and would wrongly inflate both flow totals.
#
# Two amounts are stored rather than one. Within a single currency they must match: money moving
# between your own accounts cannot change net worth, so a bank fee is recorded as its own expense
# instead of silently shrinking the transfer. Across currencies the pair IS the record of the rate the
# user actually got (the blue / MEP spread), which no stored rate could reconstruct.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    NotFoundError,
    TransferAmountRequiredError,
    TransferAmountsMustMatchError,
    TransferSameAccountError,
)
from app.models.account import Account
from app.models.transfer import Transfer
from app.models.user import User
from app.repositories import account_repository, transfer_repository
from app.schemas.transfer import TransferListResponse, TransferResponse
from app.services import account_service


# Maps a transfer to its response, denormalizing both account names and currencies so a client renders
# the row without a second lookup.
def _to_response(transfer: Transfer, accounts: dict[int, Account]) -> TransferResponse:
    source = accounts[transfer.from_account_id]
    destination = accounts[transfer.to_account_id]
    return TransferResponse(
        id=transfer.id,
        from_account_id=transfer.from_account_id,
        to_account_id=transfer.to_account_id,
        from_account_name=source.name,
        to_account_name=destination.name,
        from_currency=source.currency,
        to_currency=destination.currency,
        date=transfer.date,
        from_amount=transfer.from_amount,
        to_amount=transfer.to_amount,
        notes=transfer.notes,
        created_at=transfer.created_at,
        updated_at=transfer.updated_at,
    )


# Resolves the credited amount against the two accounts' currencies, raising the domain error that
# names the specific problem. Within one currency the credited amount mirrors the debited one, so it
# may be omitted — but a value that disagrees is rejected rather than silently overwritten, since a
# user who typed it meant something by it. Across currencies it is required.
def _resolve_to_amount(source: Account, destination: Account, from_amount: Decimal, to_amount: Decimal | None) -> Decimal:
    if source.currency == destination.currency:
        if to_amount is not None and to_amount != from_amount:
            raise TransferAmountsMustMatchError()
        return from_amount
    if to_amount is None:
        raise TransferAmountRequiredError(source.currency, destination.currency)
    return to_amount


# Loads both accounts, verifying ownership (NotFoundError → 404) and that they differ. Returns
# (source, destination).
async def _load_pair(session: AsyncSession, user: User, from_account_id: int, to_account_id: int) -> tuple[Account, Account]:
    if from_account_id == to_account_id:
        raise TransferSameAccountError()
    source = await account_service.get_account(session, from_account_id, user)
    destination = await account_service.get_account(session, to_account_id, user)
    return source, destination


# List a user's transfers, newest first, optionally narrowed to one account (either leg). Accounts are
# batch-loaded once for the whole page rather than per row.
async def list_transfers(session: AsyncSession, user: User, *, account_id: int | None = None) -> TransferListResponse:
    transfers = await transfer_repository.list_by_user(session, user.id, account_id=account_id)
    referenced = {t.from_account_id for t in transfers} | {t.to_account_id for t in transfers}
    accounts = {a.id: a for a in await account_repository.get_by_ids(session, sorted(referenced), user.id) if a.id is not None}
    items = [_to_response(t, accounts) for t in transfers if t.from_account_id in accounts and t.to_account_id in accounts]
    return TransferListResponse(items=items, total=len(items))


# Get a single transfer by id. Raises NotFoundError if it doesn't exist or isn't the user's.
async def get_transfer(session: AsyncSession, transfer_id: int, user: User) -> Transfer:
    transfer = await transfer_repository.get_by_id(session, transfer_id, user.id)
    if transfer is None:
        raise NotFoundError("Transfer not found.")
    return transfer


# Get a single transfer as its response schema.
async def get_transfer_response(session: AsyncSession, transfer_id: int, user: User) -> TransferResponse:
    transfer = await get_transfer(session, transfer_id, user)
    source, destination = await _load_pair(session, user, transfer.from_account_id, transfer.to_account_id)
    return _to_response(transfer, {source.id: source, destination.id: destination})


# Create a transfer between two owned accounts.
async def create_transfer(
    session: AsyncSession,
    user: User,
    *,
    from_account_id: int,
    to_account_id: int,
    date: date_type,
    from_amount: Decimal,
    to_amount: Decimal | None = None,
    notes: str | None = None,
) -> TransferResponse:
    source, destination = await _load_pair(session, user, from_account_id, to_account_id)
    resolved = _resolve_to_amount(source, destination, from_amount, to_amount)
    transfer = Transfer(
        user_id=user.id,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        date=date,
        from_amount=from_amount,
        to_amount=resolved,
        notes=notes,
    )
    transfer = await transfer_repository.create(session, transfer)
    await session.commit()
    await session.refresh(transfer)
    return _to_response(transfer, {source.id: source, destination.id: destination})


# Update a transfer. Only provided fields change, and the currency rules are re-checked against the
# EFFECTIVE pair (request fields over the stored row) — moving one leg to an account in another currency
# changes which rule applies, so validating the request alone would let an inconsistent row through.
async def update_transfer(
    session: AsyncSession,
    transfer_id: int,
    user: User,
    **fields: object,
) -> TransferResponse:
    transfer = await get_transfer(session, transfer_id, user)
    new_from_id = fields["from_account_id"] if "from_account_id" in fields else transfer.from_account_id
    new_to_id = fields["to_account_id"] if "to_account_id" in fields else transfer.to_account_id
    source, destination = await _load_pair(session, user, new_from_id, new_to_id)

    new_from_amount = fields["from_amount"] if "from_amount" in fields else transfer.from_amount
    # An omitted to_amount re-derives rather than holding the stored value: within one currency it must
    # mirror a changed from_amount, and a leg moved across currencies must state the rate explicitly.
    new_to_amount = fields["to_amount"] if "to_amount" in fields else None
    if (
        new_to_amount is None
        and source.currency != destination.currency
        and transfer.from_account_id == new_from_id
        and transfer.to_account_id == new_to_id
    ):
        # Currencies unchanged and the client didn't restate the credited amount — keep what was stored.
        new_to_amount = transfer.to_amount
    resolved = _resolve_to_amount(source, destination, new_from_amount, new_to_amount)

    for key, value in fields.items():
        setattr(transfer, key, value)
    transfer.to_amount = resolved
    await transfer_repository.save(session, transfer)
    await session.commit()
    await session.refresh(transfer)
    return _to_response(transfer, {source.id: source, destination.id: destination})


# Delete a transfer. Both accounts' balances recompute from the remaining rows — nothing is stored.
async def delete_transfer(session: AsyncSession, transfer_id: int, user: User) -> None:
    transfer = await get_transfer(session, transfer_id, user)
    await transfer_repository.delete(session, transfer)
    await session.commit()
