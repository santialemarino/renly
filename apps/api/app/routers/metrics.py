# Endpoints for investment and portfolio metrics.

from datetime import date as date_type

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.repositories import user_settings_repository
from app.schemas.metrics import (
    AllocationResponse,
    GroupAllocationResponse,
    InvestmentMetricsResponse,
    InvestmentsSummaryResponse,
    PortfolioEvolutionResponse,
    PortfolioMetricsResponse,
)
from app.services import metrics_service
from app.services.settings_service import DOLLAR_RATE_DEFAULT, SETTINGS_KEY_DOLLAR_RATE_PREFERENCE

router = APIRouter(prefix="/metrics", tags=["metrics"])

CURRENCY_DESC = "Display currency (e.g. USD, ARS). Omit for original."
INVESTMENT_IDS_DESC = "Filter to specific investment IDs."
GROUP_IDS_DESC = "Filter to investments in these groups (union)."
CATEGORY_DESC = "Filter to investments of this category."
SEARCH_DESC = "Filter by investment name (case-insensitive)."
START_DATE_DESC = "Start of date range (YYYY-MM-DD). Affects TWR, IRR, gain."
END_DATE_DESC = "End of date range (YYYY-MM-DD). Affects TWR, IRR, gain."


# Reads the user's dollar rate preference from settings. Returns default if not set.
async def _get_dollar_pref(session, user_id: int) -> str:
    row = await user_settings_repository.get_by_user_id(session, user_id)
    if row and row.settings:
        pref = row.settings.get(SETTINGS_KEY_DOLLAR_RATE_PREFERENCE)
        if isinstance(pref, str) and pref:
            return pref
    return DOLLAR_RATE_DEFAULT


# Returns portfolio-level metrics (total value, invested, gain, month change).
# Supports filtering by investment IDs, group IDs, or category.
@router.get("/portfolio", response_model=PortfolioMetricsResponse)
async def get_portfolio_metrics(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    investment_ids: list[int] | None = Query(default=None, description=INVESTMENT_IDS_DESC),
    group_ids: list[int] | None = Query(default=None, description=GROUP_IDS_DESC),
    category: str | None = Query(default=None, description=CATEGORY_DESC),
    search: str | None = Query(default=None, description=SEARCH_DESC),
    start_date: date_type | None = Query(default=None, description=START_DATE_DESC),
    end_date: date_type | None = Query(default=None, description=END_DATE_DESC),
) -> PortfolioMetricsResponse:
    dp = await _get_dollar_pref(session, current_user.id)
    return await metrics_service.get_portfolio_metrics(
        session,
        current_user.id,
        currency=currency,
        dollar_preference=dp,
        investment_ids=investment_ids,
        group_ids=group_ids,
        category=category,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )


# Returns monthly portfolio value series for the evolution chart.
# Supports filtering by investment IDs, group IDs, or category.
@router.get("/portfolio/evolution", response_model=PortfolioEvolutionResponse)
async def get_portfolio_evolution(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    investment_ids: list[int] | None = Query(default=None, description=INVESTMENT_IDS_DESC),
    group_ids: list[int] | None = Query(default=None, description=GROUP_IDS_DESC),
    category: str | None = Query(default=None, description=CATEGORY_DESC),
    search: str | None = Query(default=None, description=SEARCH_DESC),
    start_date: date_type | None = Query(default=None, description=START_DATE_DESC),
    end_date: date_type | None = Query(default=None, description=END_DATE_DESC),
) -> PortfolioEvolutionResponse:
    dp = await _get_dollar_pref(session, current_user.id)
    return await metrics_service.get_portfolio_evolution(
        session,
        current_user.id,
        currency=currency,
        dollar_preference=dp,
        investment_ids=investment_ids,
        group_ids=group_ids,
        category=category,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )


# Returns metrics for a single investment (TWR, IRR, period returns).
# Pass currency to convert absolute values (e.g. currency=ARS).
@router.get("/investment/{investment_id}", response_model=InvestmentMetricsResponse)
async def get_investment_metrics(
    investment_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
) -> InvestmentMetricsResponse:
    dp = await _get_dollar_pref(session, current_user.id)
    return await metrics_service.get_investment_metrics(
        session,
        investment_id,
        current_user.id,
        currency=currency,
        dollar_preference=dp,
    )


# Returns portfolio allocation by investment category.
# Supports filtering by investment IDs, group IDs, or category.
@router.get("/allocation", response_model=AllocationResponse)
async def get_allocation(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    investment_ids: list[int] | None = Query(default=None, description=INVESTMENT_IDS_DESC),
    group_ids: list[int] | None = Query(default=None, description=GROUP_IDS_DESC),
    category: str | None = Query(default=None, description=CATEGORY_DESC),
    search: str | None = Query(default=None, description=SEARCH_DESC),
) -> AllocationResponse:
    dp = await _get_dollar_pref(session, current_user.id)
    return await metrics_service.get_allocation(
        session,
        current_user.id,
        currency=currency,
        dollar_preference=dp,
        investment_ids=investment_ids,
        group_ids=group_ids,
        category=category,
        search=search,
    )


# Returns portfolio allocation by investment group.
# Supports filtering by investment IDs, group IDs, or category.
@router.get("/allocation/by-group", response_model=GroupAllocationResponse)
async def get_allocation_by_group(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    investment_ids: list[int] | None = Query(default=None, description=INVESTMENT_IDS_DESC),
    group_ids: list[int] | None = Query(default=None, description=GROUP_IDS_DESC),
    category: str | None = Query(default=None, description=CATEGORY_DESC),
    search: str | None = Query(default=None, description=SEARCH_DESC),
) -> GroupAllocationResponse:
    dp = await _get_dollar_pref(session, current_user.id)
    return await metrics_service.get_allocation_by_group(
        session,
        current_user.id,
        currency=currency,
        dollar_preference=dp,
        investment_ids=investment_ids,
        group_ids=group_ids,
        category=category,
        search=search,
    )


# Returns lightweight per-investment metrics for the dashboard compact table.
# Supports filtering by investment IDs, group IDs, or category.
@router.get("/investments/summary", response_model=InvestmentsSummaryResponse)
async def get_investments_summary(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    investment_ids: list[int] | None = Query(default=None, description=INVESTMENT_IDS_DESC),
    group_ids: list[int] | None = Query(default=None, description=GROUP_IDS_DESC),
    category: str | None = Query(default=None, description=CATEGORY_DESC),
    search: str | None = Query(default=None, description=SEARCH_DESC),
    start_date: date_type | None = Query(default=None, description=START_DATE_DESC),
    end_date: date_type | None = Query(default=None, description=END_DATE_DESC),
) -> InvestmentsSummaryResponse:
    dp = await _get_dollar_pref(session, current_user.id)
    return await metrics_service.get_investments_summary(
        session,
        current_user.id,
        currency=currency,
        dollar_preference=dp,
        investment_ids=investment_ids,
        group_ids=group_ids,
        category=category,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )
