# Request/response schemas for the general dashboard endpoints.

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field


# One pot holding value that nobody's net worth can claim yet, because its owners have not agreed a
# division. Named on the dashboard's Shared breakdown so a holding that used to be in the headline does
# not simply vanish from it. `name` is null for a group's default pot (A4 leaves it unnamed); the
# frontend supplies the fallback label, so no renderer here can print "None".
class UndividedPotItem(BaseModel):
    pot_id: int = Field(description="Pot id, for the link to its page.")
    name: str | None = Field(default=None, description="Pot name; null for a group's default pot.")
    group_id: int = Field(description="Group the pot belongs to.")
    group_name: str | None = Field(default=None, description="Group name, for the label beside the pot's.")


# Net worth and aggregated KPIs for the dashboard overview cards.
class DashboardOverviewResponse(BaseModel):
    net_worth: Decimal = Field(description="Everything the user is worth: their private holdings plus their share of everything shared.")
    private_net_worth: Decimal = Field(
        default=Decimal(0), description="The 'Yours' half: private investments plus private cash minus the credit-card balance."
    )
    shared_net_worth: Decimal = Field(
        default=Decimal(0), description="The 'Shared' half: the user's share of every visible pot, plus receivables, less payables."
    )
    shared_pot_value: Decimal = Field(default=Decimal(0), description="The user's share of every pot they can see, in the display currency.")
    shared_receivable: Decimal = Field(default=Decimal(0), description="What the user's groups owe them, summed across currency buckets.")
    shared_payable: Decimal = Field(default=Decimal(0), description="What the user owes their groups, summed across currency buckets.")
    has_shared: bool = Field(
        default=False,
        description=(
            "Whether the user has a shared side at all — a visible pot or a group seat. Existence, not value, so a household "
            "whose balances net to zero still gets the breakdown."
        ),
    )
    undivided_pots: list[UndividedPotItem] = Field(
        default_factory=list,
        description="Visible pots holding value that no ownership baseline divides yet, so they contribute exactly zero to net worth.",
    )
    cash_total: Decimal = Field(
        default=Decimal(0), description="Cash/bank balances in the display currency: the user's own accounts plus their share of pot-held ones."
    )
    net_worth_change: Decimal | None = Field(default=None, description="Absolute net worth change vs previous month.")
    net_worth_change_pct: Decimal | None = Field(default=None, description="Percentage net worth change vs previous month.")
    investment_total: Decimal = Field(description="Latest investment values: the user's own holdings plus their share of pot-held ones.")
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
    has_holdings: bool = Field(
        default=False,
        description=(
            "Whether the user holds any investment, account, or card — i.e. whether the net-worth "
            "figure is derived from anything at all. True even when the figures net to zero."
        ),
    )
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes excluded from converted totals because no exchange rate was stored.",
    )


# Single data point for the net-worth evolution line chart.
class NetWorthEvolutionPoint(BaseModel):
    date: date_type = Field(description="First day of the month.")
    investment_value: Decimal = Field(description="Aggregated private investment portfolio value at this month.")
    cash_balance: Decimal = Field(default=Decimal(0), description="Private cash/bank balance at this month end.")
    card_balance: Decimal = Field(description="Cumulative credit card balance at this month.")
    shared_value: Decimal = Field(
        default=Decimal(0), description="The user's share of every visible pot at this month, plus their net position in every group."
    )
    private_net_worth: Decimal = Field(default=Decimal(0), description="investment_value plus cash_balance minus card_balance — the 'Yours' line.")
    net_worth: Decimal = Field(description="private_net_worth plus shared_value.")


# Monthly net worth series for the evolution chart.
class DashboardEvolutionResponse(BaseModel):
    points: list[NetWorthEvolutionPoint] = Field(description="Monthly net worth points, chronological.")
    currency: str | None = Field(default=None, description="Display currency (null if no conversion requested).")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes excluded from converted totals because no exchange rate was stored.",
    )


# One slice of the composition donut (investment category, 'cash', 'receivable', or 'liabilities').
class CompositionItem(BaseModel):
    label: str = Field(description="Segment label (investment category name, 'cash', 'receivable', or 'liabilities').")
    value: Decimal = Field(description="Absolute value for this segment.")
    percentage: Decimal = Field(description="Percentage of the summed item values (asset categories plus the liabilities item when present).")


# Investment allocation by category plus a cash segment and a liabilities segment.
class DashboardCompositionResponse(BaseModel):
    items: list[CompositionItem] = Field(description="Composition segments (investment categories + cash + receivable + liabilities).")
    total_assets: Decimal = Field(description="Investment value plus cash plus what the user's groups owe them, each including their shared share.")
    total_liabilities: Decimal = Field(description="Credit-card balance (archived cards included) plus what the user owes their groups.")
    currency: str | None = Field(default=None, description="Display currency (null if no conversion requested).")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes excluded from converted totals because no exchange rate was stored.",
    )


# Single skipped commitment whose currency couldn't be converted to the display currency.
class SkippedLiquidityEntity(BaseModel):
    type: str = Field(description="Entity type (subscription, installment, obligation, credit_card, income).")
    name: str = Field(
        description="User-facing name of the skipped entity; for income entries this is the currency code (income is aggregated per currency).",
    )
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
