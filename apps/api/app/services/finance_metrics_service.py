# Business logic for financial dashboard metrics (income, expenses, credit cards).

from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.credit_card_repository import credit_card_repository
from app.repositories.expense_repository import expense_repository
from app.repositories.income_repository import income_repository
from app.schemas.finance_metrics import (
    ExpenseBreakdownResponse,
    ExpenseCategoryItem,
    FinanceMonthlyResponse,
    FinanceOverviewResponse,
    IncomeBreakdownResponse,
    IncomeCategoryItem,
    MonthlyPoint,
)
from app.services import credit_card_service
from app.services.metrics_helpers import convert_value, get_rate_map

ZERO = Decimal("0")


# Converts a multi-currency total dict into a single Decimal in the target currency.
# Each entry in totals_by_currency is {currency_code: amount}.
def _sum_converted(
    totals_by_currency: dict[str, float],
    target_currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> Decimal:
    total = ZERO
    for currency, amount in totals_by_currency.items():
        val = Decimal(str(amount))
        if target_currency and rate_map and currency != target_currency:
            val = convert_value(val, currency, target_currency, rate_map)
        total += val
    return total


# Computes overview metrics (total income, expenses, net, card balance, period change).
async def get_overview(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> FinanceOverviewResponse:
    rate_map = await _get_rate_map_if_needed(session, currency, dollar_preference)

    # Current period totals.
    income_by_currency = await income_repository.sum_by_user(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )
    expense_by_currency = await expense_repository.sum_by_user(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )

    total_income = _sum_converted(income_by_currency, currency, rate_map)
    total_expenses = _sum_converted(expense_by_currency, currency, rate_map)

    # Period-over-period change (compare with same-length previous period).
    income_change_pct = None
    expense_change_pct = None
    if date_from and date_to:
        period_days = (date_to - date_from).days
        prev_to = date_from
        prev_from = date_type.fromordinal(prev_to.toordinal() - period_days)

        prev_income_by_currency = await income_repository.sum_by_user(
            session,
            user_id,
            date_from=prev_from,
            date_to=prev_to,
        )
        prev_expense_by_currency = await expense_repository.sum_by_user(
            session,
            user_id,
            date_from=prev_from,
            date_to=prev_to,
        )

        prev_income = _sum_converted(prev_income_by_currency, currency, rate_map)
        prev_expenses = _sum_converted(prev_expense_by_currency, currency, rate_map)

        if prev_income != ZERO:
            income_change_pct = (total_income - prev_income) / prev_income
        if prev_expenses != ZERO:
            expense_change_pct = (total_expenses - prev_expenses) / prev_expenses

    # Credit card balance (all active cards, converted to display currency).
    cards = await credit_card_repository.list_by_user(session, user_id)
    card_ids = [c.id for c in cards if c.id is not None]
    card_balance = ZERO
    if card_ids:
        balances = await credit_card_service.get_card_balances(session, card_ids)
        for card in cards:
            bal = balances.get(card.id, ZERO)
            if bal and currency and rate_map and card.currency != currency:
                bal = convert_value(bal, card.currency, currency, rate_map)
            card_balance += bal

    return FinanceOverviewResponse(
        total_income=total_income,
        total_expenses=total_expenses,
        net=total_income - total_expenses,
        income_change_pct=income_change_pct,
        expense_change_pct=expense_change_pct,
        credit_card_balance=card_balance,
        currency=currency,
    )


# Computes monthly income vs expenses series for the bar chart.
async def get_monthly(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> FinanceMonthlyResponse:
    rate_map = await _get_rate_map_if_needed(session, currency, dollar_preference)

    income_rows = await income_repository.sum_by_user_monthly(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )
    expense_rows = await expense_repository.sum_by_user_monthly(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Aggregate multi-currency monthly totals into a single converted value per month.
    income_by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    for year, month, cur, amount in income_rows:
        val = Decimal(str(amount))
        if currency and rate_map and cur != currency:
            val = convert_value(val, cur, currency, rate_map)
        income_by_month[(year, month)] += val

    expense_by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    for year, month, cur, amount in expense_rows:
        val = Decimal(str(amount))
        if currency and rate_map and cur != currency:
            val = convert_value(val, cur, currency, rate_map)
        expense_by_month[(year, month)] += val

    # Merge into a single timeline.
    all_months = sorted(set(income_by_month.keys()) | set(expense_by_month.keys()))
    points = [
        MonthlyPoint(
            date=date_type(year, month, 1),
            income=income_by_month.get((year, month), ZERO),
            expenses=expense_by_month.get((year, month), ZERO),
        )
        for year, month in all_months
    ]

    return FinanceMonthlyResponse(points=points, currency=currency)


# Computes expense breakdown by category for the donut chart.
async def get_expense_breakdown(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> ExpenseBreakdownResponse:
    rate_map = await _get_rate_map_if_needed(session, currency, dollar_preference)

    rows = await expense_repository.sum_by_user_grouped_by_category(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Aggregate multi-currency per-category totals.
    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for category, cur, amount in rows:
        val = Decimal(str(amount))
        if currency and rate_map and cur != currency:
            val = convert_value(val, cur, currency, rate_map)
        cat_values[category] += val

    total_expenses = sum(cat_values.values(), ZERO)

    items = []
    for category, value in sorted(cat_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / total_expenses * 100) if total_expenses != ZERO else ZERO
        items.append(ExpenseCategoryItem(category=category, value=value, percentage=pct))

    return ExpenseBreakdownResponse(
        items=items,
        total_expenses=total_expenses,
        currency=currency,
    )


# Computes income breakdown by category for the donut chart.
async def get_income_breakdown(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> IncomeBreakdownResponse:
    rate_map = await _get_rate_map_if_needed(session, currency, dollar_preference)

    rows = await income_repository.sum_by_user_grouped_by_category(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Aggregate multi-currency per-category totals.
    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for category, cur, amount in rows:
        val = Decimal(str(amount))
        if currency and rate_map and cur != currency:
            val = convert_value(val, cur, currency, rate_map)
        cat_values[category] += val

    total_income = sum(cat_values.values(), ZERO)

    items = []
    for category, value in sorted(cat_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / total_income * 100) if total_income != ZERO else ZERO
        items.append(IncomeCategoryItem(category=category, value=value, percentage=pct))

    return IncomeBreakdownResponse(
        items=items,
        total_income=total_income,
        currency=currency,
    )


# Returns a rate map when a display currency is requested. None otherwise.
async def _get_rate_map_if_needed(
    session: AsyncSession,
    currency: str | None,
    dollar_preference: str | None,
) -> dict[str, Decimal] | None:
    if not currency:
        return None
    return await get_rate_map(session, dollar_preference)
