# Request/response schemas for metrics endpoints (HTTP contract).

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.investment import InvestmentCategory


# An investment excluded from aggregated metrics because its currency can't be converted.
class SkippedInvestment(BaseModel):
    investment_id: int = Field(description="Investment id.")
    name: str = Field(description="Investment name.")
    base_currency: str = Field(description="Investment currency that could not be converted.")


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
    twr: Decimal | None = Field(default=None, description="Portfolio time-weighted return.")
    irr: Decimal | None = Field(default=None, description="Portfolio money-weighted return (annualised XIRR).")
    month_change: Decimal | None = Field(default=None, description="Absolute change vs previous month.")
    month_change_pct: Decimal | None = Field(default=None, description="Percentage change vs previous month.")
    currency: str | None = Field(
        default=None, description="Display currency (null if no conversion requested and currencies are mixed)."
    )
    skipped_investments: list[SkippedInvestment] = Field(
        default_factory=list, description="Investments excluded because their currency can't be converted."
    )


# Single data point for portfolio value over time.
class EvolutionPoint(BaseModel):
    date: date_type = Field(description="Month date (first day of month).")
    total_value: Decimal = Field(description="Aggregated portfolio value at this date.")


# Monthly portfolio value series for the evolution chart.
class PortfolioEvolutionResponse(BaseModel):
    points: list[EvolutionPoint] = Field(description="Monthly portfolio totals, chronological.")
    currency: str | None = Field(
        default=None, description="Display currency (null if no conversion requested and currencies are mixed)."
    )
    skipped_investments: list[SkippedInvestment] = Field(
        default_factory=list, description="Investments excluded because their currency can't be converted."
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
    skipped_investments: list[SkippedInvestment] = Field(
        default_factory=list, description="Investments excluded because their currency can't be converted."
    )


# One slice of the allocation distribution by group.
class GroupAllocationItem(BaseModel):
    group_name: str = Field(description="Investment group name.")
    value: Decimal = Field(description="Total value for this group.")
    percentage: Decimal = Field(description="Percentage of total portfolio.")


# Distribution of portfolio by investment group.
class GroupAllocationResponse(BaseModel):
    items: list[GroupAllocationItem] = Field(description="Allocation per group.")
    total_value: Decimal = Field(description="Total portfolio value.")
    skipped_investments: list[SkippedInvestment] = Field(
        default_factory=list, description="Investments excluded because their currency can't be converted."
    )


# Lightweight per-investment metrics for the compact dashboard table.
class InvestmentSummaryItem(BaseModel):
    investment_id: int = Field(description="Investment id.")
    name: str = Field(description="Investment name.")
    category: InvestmentCategory = Field(description="Investment category.")
    current_value: Decimal | None = Field(default=None, description="Latest snapshot value.")
    invested_capital: Decimal = Field(description="Net capital invested.")
    absolute_gain: Decimal | None = Field(default=None, description="Current value minus invested capital.")
    month_change_pct: Decimal | None = Field(default=None, description="Percentage change vs previous month.")
    currency: str = Field(description="Currency of the monetary values.")


# Bulk per-investment metrics for the dashboard compact table.
class InvestmentsSummaryResponse(BaseModel):
    items: list[InvestmentSummaryItem] = Field(description="Per-investment summary, sorted by value desc.")
    skipped_investments: list[SkippedInvestment] = Field(
        default_factory=list, description="Investments excluded because their currency can't be converted."
    )
