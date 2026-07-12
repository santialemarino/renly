# Endpoints for financial dashboard metrics (income, expenses, credit cards).

from datetime import date as date_type

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.finance_metrics import (
    ExpenseBreakdownResponse,
    FinanceMonthlyResponse,
    FinanceOverviewResponse,
    IncomeBreakdownResponse,
)
from app.services import finance_metrics_service

router = APIRouter(prefix="/finance-metrics", tags=["finance-metrics"])

CURRENCY_DESC = "Display currency (e.g. USD, ARS). Omit for original."
DATE_FROM_DESC = "Start of date range (YYYY-MM-DD, inclusive)."
DATE_TO_DESC = "End of date range (YYYY-MM-DD, inclusive)."


# Returns finance overview metrics (total income, expenses, net, card balance, period change).
@router.get("/overview", response_model=FinanceOverviewResponse)
async def get_overview(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    date_from: date_type | None = Query(default=None, description=DATE_FROM_DESC),
    date_to: date_type | None = Query(default=None, description=DATE_TO_DESC),
) -> FinanceOverviewResponse:
    return await finance_metrics_service.get_overview(
        session,
        current_user.id,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )


# Returns monthly income vs expenses series for the bar chart.
@router.get("/monthly", response_model=FinanceMonthlyResponse)
async def get_monthly(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    date_from: date_type | None = Query(default=None, description=DATE_FROM_DESC),
    date_to: date_type | None = Query(default=None, description=DATE_TO_DESC),
) -> FinanceMonthlyResponse:
    return await finance_metrics_service.get_monthly(
        session,
        current_user.id,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )


# Returns expense breakdown by category for the donut chart.
@router.get("/expense-breakdown", response_model=ExpenseBreakdownResponse)
async def get_expense_breakdown(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    date_from: date_type | None = Query(default=None, description=DATE_FROM_DESC),
    date_to: date_type | None = Query(default=None, description=DATE_TO_DESC),
) -> ExpenseBreakdownResponse:
    return await finance_metrics_service.get_expense_breakdown(
        session,
        current_user.id,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )


# Returns income breakdown by category for the donut chart.
@router.get("/income-breakdown", response_model=IncomeBreakdownResponse)
async def get_income_breakdown(
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description=CURRENCY_DESC),
    date_from: date_type | None = Query(default=None, description=DATE_FROM_DESC),
    date_to: date_type | None = Query(default=None, description=DATE_TO_DESC),
) -> IncomeBreakdownResponse:
    return await finance_metrics_service.get_income_breakdown(
        session,
        current_user.id,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )
