# Endpoints for the general dashboard (aggregated investment + finance view).

from datetime import date as date_type

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.dashboard import (
    DashboardCompositionResponse,
    DashboardEvolutionResponse,
    DashboardLiquidityResponse,
    DashboardOverviewResponse,
)
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CURRENCY_DESC = "Display currency (e.g. USD, ARS). Omit for original."
DATE_FROM_DESC = "Start of date range (YYYY-MM-DD, inclusive)."
DATE_TO_DESC = "End of date range (YYYY-MM-DD, inclusive)."


# Returns aggregated net worth, investment KPIs, and finance KPIs.
@router.get("/overview", response_model=DashboardOverviewResponse)
async def get_overview(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    date_from: date_type | None = Query(default=None, description=DATE_FROM_DESC),
    date_to: date_type | None = Query(default=None, description=DATE_TO_DESC),
) -> DashboardOverviewResponse:
    return await dashboard_service.get_overview(
        session,
        current_user.id,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )


# Returns monthly net worth evolution (investment value - cumulative card balance).
@router.get("/evolution", response_model=DashboardEvolutionResponse)
async def get_evolution(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    date_from: date_type | None = Query(default=None, description=DATE_FROM_DESC),
    date_to: date_type | None = Query(default=None, description=DATE_TO_DESC),
) -> DashboardEvolutionResponse:
    return await dashboard_service.get_evolution(
        session,
        current_user.id,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )


# Returns investment allocation by category plus a liabilities segment.
@router.get("/composition", response_model=DashboardCompositionResponse)
async def get_composition(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
) -> DashboardCompositionResponse:
    return await dashboard_service.get_composition(
        session,
        current_user.id,
        currency=currency,
    )


# Returns the liquidity health indicator (fixed commitments / income ratio) for the dashboard footer.
@router.get("/liquidity", response_model=DashboardLiquidityResponse)
async def get_liquidity(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
) -> DashboardLiquidityResponse:
    return await dashboard_service.get_liquidity(
        session,
        current_user.id,
        currency=currency,
    )
