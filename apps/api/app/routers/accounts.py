from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


# Builds an AccountResponse, injecting the derived balance (defaults to opening_balance) and the
# has-links flag (whether any money links the account — the frontend locks its currency when set).
def _to_response(account: Account, balance: Decimal | None = None, has_links: bool = False) -> AccountResponse:
    data = account.model_dump()
    return AccountResponse(**{**data, "balance": balance if balance is not None else account.opening_balance, "has_links": has_links})


# List accounts for the current user with optional search, sorting, and balances.
@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter accounts by name (case-insensitive)."),
    sort_by: str | None = Query(default=None, description="Column to sort by (name, type, currency, opening_date)."),
    sort_order: str = Query(default="asc", description="Sort direction (asc or desc)."),
    show_archived: bool = Query(default=False, description="Include archived (inactive) accounts."),
) -> list[AccountResponse]:
    accounts = await account_service.list_accounts(
        session,
        current_user,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=not show_archived,
    )
    balances, linked = await account_service.get_account_summaries(session, accounts, current_user.id)
    return [_to_response(account, balances.get(account.id), account.id in linked) for account in accounts]


# Get a single account with its current balance.
@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountResponse:
    account = await account_service.get_account(session, account_id, current_user)
    balances, linked = await account_service.get_account_summaries(session, [account], current_user.id)
    return _to_response(account, balances.get(account.id), account.id in linked)


# Create a new account.
@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountResponse:
    account = await account_service.create_account(
        session,
        current_user,
        name=body.name,
        type=body.type,
        currency=body.currency,
        opening_balance=body.opening_balance,
        opening_date=body.opening_date,
        notes=body.notes,
    )
    return _to_response(account)


# Update an account.
@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    body: AccountUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountResponse:
    payload = body.model_dump(exclude_unset=True)
    account = await account_service.update_account(session, account_id, current_user, **payload)
    balances, linked = await account_service.get_account_summaries(session, [account], current_user.id)
    return _to_response(account, balances.get(account.id), account.id in linked)


# Delete an account. Linked entries are un-attributed (ON DELETE SET NULL), preserving their history.
@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await account_service.delete_account(session, account_id, current_user)


# Archive an account (set is_active = false). Returns the updated account.
@router.post("/{account_id}/archive", response_model=AccountResponse)
async def archive_account(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountResponse:
    account = await account_service.archive_account(session, account_id, current_user)
    balances, linked = await account_service.get_account_summaries(session, [account], current_user.id)
    return _to_response(account, balances.get(account.id), account.id in linked)


# Unarchive an account (set is_active = true). Returns the updated account.
@router.post("/{account_id}/unarchive", response_model=AccountResponse)
async def unarchive_account(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountResponse:
    account = await account_service.unarchive_account(session, account_id, current_user)
    balances, linked = await account_service.get_account_summaries(session, [account], current_user.id)
    return _to_response(account, balances.get(account.id), account.id in linked)
