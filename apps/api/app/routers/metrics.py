# Endpoints for investment and portfolio metrics.

from fastapi import APIRouter

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.metrics import (
    AllocationResponse,
    InvestmentMetricsResponse,
    PortfolioMetricsResponse,
)
from app.services import metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])


# Returns portfolio-level metrics (total value, invested, gain, month change).
@router.get("/portfolio", response_model=PortfolioMetricsResponse)
async def get_portfolio_metrics(
    current_user: CurrentUser,
    session: SessionDep,
) -> PortfolioMetricsResponse:
    return await metrics_service.get_portfolio_metrics(session, current_user.id)


# Returns metrics for a single investment (TWR, IRR, period returns).
@router.get("/investment/{investment_id}", response_model=InvestmentMetricsResponse)
async def get_investment_metrics(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> InvestmentMetricsResponse:
    return await metrics_service.get_investment_metrics(session, investment_id, current_user.id)


# Returns portfolio allocation by investment category.
@router.get("/allocation", response_model=AllocationResponse)
async def get_allocation(
    current_user: CurrentUser,
    session: SessionDep,
) -> AllocationResponse:
    return await metrics_service.get_allocation(session, current_user.id)
