from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.domain.account_movement import MovementKind
from app.models.account import Account
from app.models.user import User
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.schemas.account_movement import AccountMovementListResponse
from app.schemas.account_reconciliation import (
    AccountComputedBalanceResponse,
    AccountReconciliationCreate,
    AccountReconciliationResponse,
)
from app.services import account_movement_service, account_reconciliation_service, account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


# Builds an AccountResponse, injecting the derived balance (defaults to opening_balance), the
# has-links flag (whether any money — including a transfer on either leg — links the account — the frontend locks its currency when set),
# and the date of the account's most recent reconciliation.
def _to_response(
    account: Account,
    balance: Decimal | None = None,
    has_links: bool = False,
    last_reconciled_date: date_type | None = None,
) -> AccountResponse:
    data = account.model_dump()
    return AccountResponse(
        **{
            **data,
            "balance": balance if balance is not None else account.opening_balance,
            "has_links": has_links,
            "last_reconciled_date": last_reconciled_date,
        }
    )


# Builds responses for a set of accounts, batching every derived field: the balance union, the
# has-links flag, and the last-reconciled date are grouped queries, so cost is independent of count.
async def _to_responses(session: AsyncSession, accounts: list[Account], user: User) -> list[AccountResponse]:
    balances, linked = await account_service.get_account_summaries(session, accounts, user.id)
    last_reconciled = await account_reconciliation_service.get_latest_reconciled_dates(session, accounts, user.id)
    return [_to_response(a, balances.get(a.id), a.id in linked, last_reconciled.get(a.id)) for a in accounts]


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
    return await _to_responses(session, accounts, current_user)


# Get a single account with its current balance.
@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountResponse:
    account = await account_service.get_account(session, account_id, current_user)
    return (await _to_responses(session, [account], current_user))[0]


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
    return (await _to_responses(session, [account], current_user))[0]


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
    return (await _to_responses(session, [account], current_user))[0]


# Unarchive an account (set is_active = true). Returns the updated account.
@router.post("/{account_id}/unarchive", response_model=AccountResponse)
async def unarchive_account(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountResponse:
    account = await account_service.unarchive_account(session, account_id, current_user)
    return (await _to_responses(session, [account], current_user))[0]


# The account's ledger: every movement that reaches it, newest first, paginated. `balance_after` is
# populated only on the unfiltered view — see account_movement_service for why.
@router.get("/{account_id}/movements", response_model=AccountMovementListResponse)
async def list_movements(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    kind: MovementKind | None = Query(default=None, description="Filter by movement kind."),
    page: int = Query(default=1, ge=1, description="Page number; clamped to the last page that has rows."),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page."),
) -> AccountMovementListResponse:
    return await account_movement_service.list_account_movements(
        session,
        account_id,
        current_user,
        kind=kind,
        page=page,
        page_size=page_size,
    )


# The account's derived balance at a date. Drives the reconcile dialog's difference preview, which
# has to follow the date the user picks rather than assume today.
@router.get("/{account_id}/computed-balance", response_model=AccountComputedBalanceResponse)
async def get_computed_balance(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    as_of_date: date_type = Query(description="Date to compute the balance at."),
) -> AccountComputedBalanceResponse:
    account = await account_service.get_account(session, account_id, current_user)
    balance = await account_reconciliation_service.compute_account_balance_at(session, account, as_of_date)
    return AccountComputedBalanceResponse(account_id=account_id, as_of_date=as_of_date, balance=balance)


# List an account's reconciliations, newest first.
@router.get("/{account_id}/reconciliations", response_model=list[AccountReconciliationResponse])
async def list_reconciliations(
    account_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[AccountReconciliationResponse]:
    rows = await account_reconciliation_service.list_reconciliations(session, account_id, current_user)
    return [AccountReconciliationResponse.model_validate(row) for row in rows]


# Reconcile an account: record the real balance as of a date and post the adjustment that closes the gap.
@router.post("/{account_id}/reconciliations", response_model=AccountReconciliationResponse, status_code=status.HTTP_201_CREATED)
async def create_reconciliation(
    account_id: int,
    body: AccountReconciliationCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> AccountReconciliationResponse:
    reconciliation = await account_reconciliation_service.create_reconciliation(
        session,
        account_id,
        current_user,
        as_of_date=body.as_of_date,
        statement_balance=body.statement_balance,
    )
    return AccountReconciliationResponse.model_validate(reconciliation)


# Delete a reconciliation. Cascades to its adjustment expense or income, undoing the true-up.
@router.delete("/{account_id}/reconciliations/{reconciliation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reconciliation(
    account_id: int,
    reconciliation_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await account_reconciliation_service.delete_reconciliation(session, account_id, reconciliation_id, current_user)
