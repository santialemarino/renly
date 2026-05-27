# Request/response schemas for the general dashboard endpoints.

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field


# Net worth and aggregated KPIs for the dashboard overview cards.
class DashboardOverviewResponse(BaseModel):
    net_worth: Decimal = Field(description="Investment total value minus credit card balance.")
    net_worth_change: Decimal | None = Field(default=None, description="Absolute net worth change vs previous month.")
    net_worth_change_pct: Decimal | None = Field(default=None, description="Percentage net worth change vs previous month.")
    investment_total: Decimal = Field(description="Sum of latest investment snapshot values.")
    investment_gain: Decimal = Field(description="Investment total value minus total invested capital.")
    investment_gain_pct: Decimal | None = Field(default=None, description="Simple return: (total_value / total_invested) - 1.")
    investment_month_change: Decimal | None = Field(default=None, description="Investment value absolute change vs previous month.")
    investment_month_change_pct: Decimal | None = Field(default=None, description="Investment value percentage change vs previous month.")
    credit_card_balance: Decimal = Field(description="Total outstanding credit card balance.")
    total_income: Decimal = Field(description="Total income in the selected period.")
    total_expenses: Decimal = Field(description="Total expenses in the selected period.")
    savings_rate: Decimal | None = Field(default=None, description="(income - expenses) / income. Null when income is zero.")
    income_expense_ratio: Decimal | None = Field(default=None, description="income / expenses. Null when expenses are zero.")
    currency: str | None = Field(default=None, description="Display currency (null if no conversion requested).")


# Single data point for the net-worth evolution line chart.
class NetWorthEvolutionPoint(BaseModel):
    date: date_type = Field(description="First day of the month.")
    investment_value: Decimal = Field(description="Aggregated investment portfolio value.")
    card_balance: Decimal = Field(description="Cumulative credit card balance at this month.")
    net_worth: Decimal = Field(description="investment_value minus card_balance.")


# Monthly net worth series for the evolution chart.
class DashboardEvolutionResponse(BaseModel):
    points: list[NetWorthEvolutionPoint] = Field(description="Monthly net worth points, chronological.")
    currency: str | None = Field(default=None, description="Display currency (null if no conversion requested).")


# One slice of the composition donut (investment category or liabilities).
class CompositionItem(BaseModel):
    label: str = Field(description="Segment label (investment category name or 'liabilities').")
    value: Decimal = Field(description="Absolute value for this segment.")
    percentage: Decimal = Field(description="Percentage of total gross value.")


# Investment allocation by category plus a liabilities segment.
class DashboardCompositionResponse(BaseModel):
    items: list[CompositionItem] = Field(description="Composition segments (investment categories + liabilities).")
    total_assets: Decimal = Field(description="Total investment portfolio value.")
    total_liabilities: Decimal = Field(description="Total credit card balance.")
    currency: str | None = Field(default=None, description="Display currency (null if no conversion requested).")


# Single skipped commitment whose currency couldn't be converted to the display currency.
class SkippedLiquidityEntity(BaseModel):
    type: str = Field(description="Entity type: subscription, installment, obligation, or credit_card.")
    name: str = Field(description="User-facing name of the skipped entity.")
    currency: str = Field(description="The unsupported currency of the entity.")


# Liquidity health indicator (fixed monthly commitments vs monthly income) for the dashboard footer.
class DashboardLiquidityResponse(BaseModel):
    ratio: Decimal | None = Field(default=None, description="Commitments / income. Null when income is zero or history is insufficient.")
    state: str = Field(description="One of: healthy, caution, at_risk, unknown.")
    fixed_monthly_commitments: Decimal = Field(description="Monthly-equivalent commitments in display currency.")
    monthly_income: Decimal = Field(description="Normalised monthly income over the income window.")
    threshold: int = Field(description="User-configured threshold (integer percentage, e.g. 40 = 40%).")
    income_window_days: int = Field(description="Target window length (90 days when fully populated).")
    actual_window_days: int = Field(description="Actual window used for normalisation. Smaller than income_window_days during early app life.")
    currency: str | None = Field(default=None, description="Display currency (null when 'Original' is selected).")
    skipped_entities: list[SkippedLiquidityEntity] = Field(
        default_factory=list,
        description="Commitments excluded because their currency couldn't be converted to display currency. Empty in normal operation.",
    )
