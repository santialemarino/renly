# Request/response schemas for metrics endpoints (HTTP contract).

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.investment import InvestmentCategory


# Period return for a single snapshot.
class PeriodReturnItem(BaseModel):
    date: date_type = Field(description="Snapshot date.")
    value: Decimal = Field(description="Snapshot value.")
    return_pct: Decimal | None = Field(default=None, description="Period return (null for first snapshot).")


# Full metrics for a single investment.
class InvestmentMetricsResponse(BaseModel):
    investment_id: int = Field(description="Investment id.")
    name: str = Field(description="Investment name.")
    category: InvestmentCategory = Field(description="Investment category.")
    base_currency: str = Field(description="Investment currency.")
    current_value: Decimal | None = Field(default=None, description="Latest snapshot value.")
    invested_capital: Decimal = Field(description="Net capital invested (deposits - withdrawals).")
    absolute_gain: Decimal | None = Field(default=None, description="Current value minus invested capital.")
    simple_return: Decimal | None = Field(default=None, description="(current_value / invested_capital) - 1.")
    twr: Decimal | None = Field(default=None, description="Time-weighted return since inception.")
    irr: Decimal | None = Field(default=None, description="Money-weighted return (annualised XIRR).")
    period_returns: list[PeriodReturnItem] = Field(default_factory=list, description="Return per snapshot period.")
    currency: str = Field(description="Currency of the monetary values.")


# Summary metrics for the entire portfolio.
class PortfolioMetricsResponse(BaseModel):
    total_value: Decimal = Field(description="Sum of latest snapshot values.")
    total_invested: Decimal = Field(description="Sum of net invested capital across all investments.")
    absolute_gain: Decimal = Field(description="Total value minus total invested.")
    total_return_pct: Decimal | None = Field(
        default=None, description="Simple return: (total_value / total_invested) - 1."
    )
    month_change: Decimal | None = Field(default=None, description="Absolute change vs previous month.")
    month_change_pct: Decimal | None = Field(default=None, description="Percentage change vs previous month.")
    currency: str | None = Field(
        default=None, description="Display currency (null if no conversion requested and currencies are mixed)."
    )


# One slice of the allocation distribution.
class AllocationItem(BaseModel):
    category: InvestmentCategory = Field(description="Investment category.")
    value: Decimal = Field(description="Total value for this category.")
    percentage: Decimal = Field(description="Percentage of total portfolio.")


# Distribution of portfolio by investment category.
class AllocationResponse(BaseModel):
    items: list[AllocationItem] = Field(description="Allocation per category.")
    total_value: Decimal = Field(description="Total portfolio value.")
