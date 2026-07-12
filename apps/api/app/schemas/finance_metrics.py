# Request/response schemas for finance metrics endpoints (HTTP contract).

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field


# Summary metrics for the finance overview (cards: income, expenses, net, card balance).
class FinanceOverviewResponse(BaseModel):
    total_income: Decimal = Field(description="Total income in the period.")
    total_expenses: Decimal = Field(description="Total expenses in the period.")
    net: Decimal = Field(description="Income minus expenses.")
    income_change_pct: Decimal | None = Field(default=None, description="Income change vs previous period (ratio).")
    expense_change_pct: Decimal | None = Field(default=None, description="Expense change vs previous period (ratio).")
    credit_card_balance: Decimal = Field(description="Total outstanding credit card balance, including archived cards.")
    currency: str | None = Field(default=None, description="Display currency (null if no conversion requested).")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes excluded from converted totals because no exchange rate was stored.",
    )


# Single data point for the income vs expenses monthly chart.
class MonthlyPoint(BaseModel):
    date: date_type = Field(description="First day of the month.")
    income: Decimal = Field(description="Total income for the month.")
    expenses: Decimal = Field(description="Total expenses for the month.")


# Monthly income vs expenses series for the bar chart.
class FinanceMonthlyResponse(BaseModel):
    points: list[MonthlyPoint] = Field(description="Monthly income and expense totals, chronological.")
    currency: str | None = Field(default=None, description="Display currency.")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes excluded from converted totals because no exchange rate was stored.",
    )


# One slice of the expense category breakdown.
class ExpenseCategoryItem(BaseModel):
    category: str = Field(description="Expense category key, or 'uncategorized' for entries without a category.")
    value: Decimal = Field(description="Total value for this category.")
    percentage: Decimal = Field(description="Percentage of total expenses.")


# Expense distribution by category for the donut chart.
class ExpenseBreakdownResponse(BaseModel):
    items: list[ExpenseCategoryItem] = Field(description="Expense breakdown per category.")
    total_expenses: Decimal = Field(description="Total expenses in the period.")
    currency: str | None = Field(default=None, description="Display currency.")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes excluded from converted totals because no exchange rate was stored.",
    )


# One slice of the income category breakdown.
class IncomeCategoryItem(BaseModel):
    category: str = Field(description="Income category key, or 'uncategorized' for entries without a category.")
    value: Decimal = Field(description="Total value for this category.")
    percentage: Decimal = Field(description="Percentage of total income.")


# Income distribution by category for the donut chart.
class IncomeBreakdownResponse(BaseModel):
    items: list[IncomeCategoryItem] = Field(description="Income breakdown per category.")
    total_income: Decimal = Field(description="Total income in the period.")
    currency: str | None = Field(default=None, description="Display currency.")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes excluded from converted totals because no exchange rate was stored.",
    )
