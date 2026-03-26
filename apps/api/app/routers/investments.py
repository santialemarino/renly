from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.investment import InvestmentCategory
from app.schemas.investment import (
    InvestmentCreate,
    InvestmentListResponse,
    InvestmentResponse,
    InvestmentSetGroupsBody,
    InvestmentUpdate,
)
from app.schemas.snapshot import SnapshotCreate, SnapshotResponse
from app.schemas.transaction import (
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from app.services import investment_service

router = APIRouter(prefix="/investments", tags=["investments"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# Lists investments for the user with optional search, group, category filters and pagination.
@router.get("", response_model=InvestmentListResponse)
async def list_investments(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter by name (case-insensitive)."),
    group_ids: list[int] | None = Query(default=None, description="Filter by group ids (union)."),
    category: InvestmentCategory | None = Query(default=None, description="Filter by category."),
    active_only: bool = Query(default=True, description="Return only active investments."),
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    sort_by: str | None = Query(default=None, description="Sort field: name, category, base_currency, broker."),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$", description="Sort direction."),
) -> InvestmentListResponse:
    return await investment_service.list_investments(
        session,
        current_user,
        search=search,
        group_ids=group_ids,
        category=category,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# Returns a single investment by id. Returns 404 if not found or not owned.
@router.get("/{investment_id}", response_model=InvestmentResponse)
async def get_investment(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> InvestmentResponse:
    investment = await investment_service.get_investment(session, investment_id, current_user)
    return InvestmentResponse.model_validate(investment)


# Creates a new investment for the user.
@router.post("", response_model=InvestmentResponse, status_code=status.HTTP_201_CREATED)
async def create_investment(
    body: InvestmentCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> InvestmentResponse:
    investment = await investment_service.create_investment(
        session,
        current_user,
        name=body.name,
        category=body.category,
        base_currency=body.base_currency,
        ticker=body.ticker,
        broker=body.broker,
        notes=body.notes,
    )
    return InvestmentResponse.model_validate(investment)


# Updates an investment. Only provided fields are updated. Returns 404 if not found.
@router.put("/{investment_id}", response_model=InvestmentResponse)
async def update_investment(
    investment_id: int,
    body: InvestmentUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> InvestmentResponse:
    payload = body.model_dump(exclude_unset=True)
    investment = await investment_service.update_investment(session, investment_id, current_user, **payload)
    return InvestmentResponse.model_validate(investment)


# Archives an investment (sets is_active = false). Returns 204.
@router.patch("/{investment_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_investment(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await investment_service.archive_investment(session, investment_id, current_user)


# Unarchives an investment (sets is_active = true). Returns 204.
@router.patch("/{investment_id}/unarchive", status_code=status.HTTP_204_NO_CONTENT)
async def unarchive_investment(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await investment_service.unarchive_investment(session, investment_id, current_user)


# Replaces group membership for the investment. Returns 204.
@router.put("/{investment_id}/groups", status_code=status.HTTP_204_NO_CONTENT)
async def set_investment_groups(
    investment_id: int,
    body: InvestmentSetGroupsBody,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await investment_service.set_investment_groups(session, investment_id, current_user, body.group_ids)


# --- Snapshots ---


# Lists snapshots for an investment. Returns 404 if investment not found or not owned.
@router.get("/{investment_id}/snapshots", response_model=list[SnapshotResponse])
async def list_snapshots(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[SnapshotResponse]:
    snapshots = await investment_service.list_snapshots(session, investment_id, current_user)
    return [SnapshotResponse.model_validate(s) for s in snapshots]


# Creates or updates a snapshot for the investment and date. One per (investment, date).
@router.post(
    "/{investment_id}/snapshots",
    response_model=SnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    investment_id: int,
    body: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> SnapshotResponse:
    snapshot = await investment_service.upsert_snapshot(
        session,
        investment_id,
        current_user,
        snapshot_date=body.date,
        value=body.value,
        currency=body.currency,
        notes=body.notes,
    )
    return SnapshotResponse.model_validate(snapshot)


# --- Transactions ---


# Lists transactions for an investment. Returns 404 if investment not found or not owned.
@router.get(
    "/{investment_id}/transactions",
    response_model=list[TransactionResponse],
)
async def list_transactions(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[TransactionResponse]:
    transactions = await investment_service.list_transactions(session, investment_id, current_user)
    return [TransactionResponse.model_validate(t) for t in transactions]


# Returns a single transaction by id. Returns 404 if not found or not owned.
@router.get(
    "/{investment_id}/transactions/{transaction_id}",
    response_model=TransactionResponse,
)
async def get_transaction(
    investment_id: int,
    transaction_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> TransactionResponse:
    transaction = await investment_service.get_transaction(session, investment_id, transaction_id, current_user)
    return TransactionResponse.model_validate(transaction)


# Creates a new transaction for the investment.
@router.post(
    "/{investment_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    investment_id: int,
    body: TransactionCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> TransactionResponse:
    transaction = await investment_service.create_transaction(
        session,
        investment_id,
        current_user,
        transaction_date=body.date,
        amount=body.amount,
        currency=body.currency,
        tx_type=body.type,
        notes=body.notes,
    )
    return TransactionResponse.model_validate(transaction)


# Updates a transaction. Only provided fields are updated. Returns 404 if not found.
@router.put(
    "/{investment_id}/transactions/{transaction_id}",
    response_model=TransactionResponse,
)
async def update_transaction(
    investment_id: int,
    transaction_id: int,
    body: TransactionUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> TransactionResponse:
    payload = body.model_dump(exclude_unset=True)
    payload_rename = {"date": "transaction_date", "type": "tx_type"}
    service_kwargs = {payload_rename.get(k, k): v for k, v in payload.items()}
    transaction = await investment_service.update_transaction(
        session, investment_id, transaction_id, current_user, **service_kwargs
    )
    return TransactionResponse.model_validate(transaction)


# Deletes a transaction. Returns 204.
@router.delete(
    "/{investment_id}/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transaction(
    investment_id: int,
    transaction_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await investment_service.delete_transaction(session, investment_id, transaction_id, current_user)
