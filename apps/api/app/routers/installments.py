from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.installment import InstallmentCreate, InstallmentResponse, InstallmentUpdate
from app.services import installment_service
from app.utils.metrics import convert_value, get_rate_map
from app.utils.settings import get_dollar_pref

router = APIRouter(prefix="/installments", tags=["installments"])


# Converts an installment's amounts if a target currency and rate map are provided.
def _convert_response(
    resp: InstallmentResponse,
    entry_currency: str,
    target_currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> InstallmentResponse:
    if target_currency and rate_map and entry_currency != target_currency:
        resp.converted_total_amount = convert_value(resp.total_amount, entry_currency, target_currency, rate_map)
        resp.converted_installment_amount = convert_value(resp.installment_amount, entry_currency, target_currency, rate_map)
    elif target_currency and entry_currency == target_currency:
        resp.converted_total_amount = resp.total_amount
        resp.converted_installment_amount = resp.installment_amount
    return resp


# List installments for the current user with optional search, sorting, and currency conversion.
@router.get("", response_model=list[InstallmentResponse])
async def list_installments(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter installments by name (case-insensitive)."),
    sort_by: str | None = Query(
        default=None,
        description=(
            "Column to sort by (name, total_amount, installment_amount, currency, "
            "installments_count, current_installment, start_date, next_cuota_date)."
        ),
    ),
    sort_order: str = Query(default="asc", description="Sort direction (asc or desc)."),
    show_archived: bool = Query(default=False, description="Include archived (completed) installments."),
    include_ids: list[int] | None = Query(
        default=None,
        description=(
            "Archived plan ids to include alongside the active set. Used by the expense edit dialog "
            "so a row linked to a since-archived plan can still render the plan name in the dropdown. "
            "Ignored when show_archived=true (everything is already included)."
        ),
    ),
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> list[InstallmentResponse]:
    installments = await installment_service.list_installments(
        session,
        current_user,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=not show_archived,
        include_ids=include_ids,
    )

    rate_map = None
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        rate_map = await get_rate_map(session, dp)

    return [_convert_response(InstallmentResponse.model_validate(i), i.currency, currency, rate_map) for i in installments]


# Get a single installment by id (with optional currency conversion).
@router.get("/{installment_id}", response_model=InstallmentResponse)
async def get_installment(
    installment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> InstallmentResponse:
    installment = await installment_service.get_installment(session, installment_id, current_user)
    resp = InstallmentResponse.model_validate(installment)
    if currency:
        dp = await get_dollar_pref(session, current_user.id)
        rate_map = await get_rate_map(session, dp)
        resp = _convert_response(resp, installment.currency, currency, rate_map)
    return resp


# Create a new installment plan. Supports both JWT (web) and API key (iOS Shortcut) auth.
@router.post("", response_model=InstallmentResponse, status_code=status.HTTP_201_CREATED)
async def create_installment(
    body: InstallmentCreate,
    current_user: JwtOrApiKeyUser,
    session: SessionDep,
) -> InstallmentResponse:
    installment = await installment_service.create_installment(
        session,
        current_user,
        name=body.name,
        total_amount=body.total_amount,
        installment_amount=body.installment_amount,
        currency=body.currency,
        installments_count=body.installments_count,
        current_installment=body.current_installment,
        start_date=body.start_date,
        payment_method=body.payment_method,
        credit_card_id=body.credit_card_id,
    )
    return InstallmentResponse.model_validate(installment)


# Update an existing installment plan.
@router.put("/{installment_id}", response_model=InstallmentResponse)
async def update_installment(
    installment_id: int,
    body: InstallmentUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> InstallmentResponse:
    payload = body.model_dump(exclude_unset=True)
    installment = await installment_service.update_installment(session, installment_id, current_user, **payload)
    return InstallmentResponse.model_validate(installment)


# Delete an installment plan. Returns 204.
@router.delete("/{installment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_installment(
    installment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await installment_service.delete_installment(session, installment_id, current_user)
