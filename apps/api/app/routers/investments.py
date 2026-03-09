from fastapi import APIRouter, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.investment import (
    InvestmentCreate,
    InvestmentResponse,
    InvestmentUpdate,
)
from app.services import investment_service

router = APIRouter(prefix="/investments", tags=["investments"])


# Lists investments for the current user. Returns only active by default.
@router.get("", response_model=list[InvestmentResponse])
async def list_investments(
    current_user: CurrentUser,
    session: SessionDep,
    active_only: bool = True,
) -> list[InvestmentResponse]:
    investments = await investment_service.list_investments(
        session, current_user, active_only=active_only
    )
    return [InvestmentResponse.model_validate(i) for i in investments]


# Returns a single investment by id. Returns 404 if not found or not owned.
@router.get("/{investment_id}", response_model=InvestmentResponse)
async def get_investment(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> InvestmentResponse:
    investment = await investment_service.get_investment(session, investment_id, current_user)
    return InvestmentResponse.model_validate(investment)


# Creates a new investment for the current user.
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
    investment = await investment_service.update_investment(
        session, investment_id, current_user, **payload
    )
    return InvestmentResponse.model_validate(investment)


# Soft-deletes an investment (sets is_active = false). Returns 204.
@router.delete("/{investment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investment(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await investment_service.delete_investment(session, investment_id, current_user)
