# Endpoints for investment and portfolio metrics.

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.metrics import (
    AllocationResponse,
    GroupAllocationResponse,
    InvestmentMetricsResponse,
    InvestmentsSummaryResponse,
    PortfolioEvolutionResponse,
    PortfolioMetricsResponse,
)
from app.services import metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])


# Returns portfolio-level metrics (total value, invested, gain, month change).
# Pass currency to convert all values (e.g. currency=ARS).
@router.get("/portfolio", response_model=PortfolioMetricsResponse)
async def get_portfolio_metrics(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> PortfolioMetricsResponse:
    return await metrics_service.get_portfolio_metrics(session, current_user.id, currency=currency)


# Returns monthly portfolio value series for the evolution chart.
# Pass currency to convert all values (e.g. currency=USD).
@router.get("/portfolio/evolution", response_model=PortfolioEvolutionResponse)
async def get_portfolio_evolution(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> PortfolioEvolutionResponse:
    return await metrics_service.get_portfolio_evolution(session, current_user.id, currency=currency)


# Returns metrics for a single investment (TWR, IRR, period returns).
# Pass currency to convert absolute values (e.g. currency=ARS).
@router.get("/investment/{investment_id}", response_model=InvestmentMetricsResponse)
async def get_investment_metrics(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> InvestmentMetricsResponse:
    return await metrics_service.get_investment_metrics(session, investment_id, current_user.id, currency=currency)


# Returns portfolio allocation by investment category.
# Pass currency to convert values to a common currency (e.g. currency=USD).
@router.get("/allocation", response_model=AllocationResponse)
async def get_allocation(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> AllocationResponse:
    return await metrics_service.get_allocation(session, current_user.id, currency=currency)


# Returns portfolio allocation by investment group.
# Pass currency to convert values to a common currency (e.g. currency=USD).
@router.get("/allocation/by-group", response_model=GroupAllocationResponse)
async def get_allocation_by_group(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> GroupAllocationResponse:
    return await metrics_service.get_allocation_by_group(session, current_user.id, currency=currency)


# Returns lightweight per-investment metrics for the dashboard compact table.
# Pass currency to convert values (e.g. currency=USD).
@router.get("/investments/summary", response_model=InvestmentsSummaryResponse)
async def get_investments_summary(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Display currency (e.g. USD, ARS). Omit for original."),
) -> InvestmentsSummaryResponse:
    return await metrics_service.get_investments_summary(session, current_user.id, currency=currency)
