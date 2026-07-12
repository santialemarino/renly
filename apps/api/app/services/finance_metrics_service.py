# Business logic for financial dashboard metrics (income, expenses, credit cards).

import calendar as _calendar
from collections import defaultdict
from datetime import date as date_type
from datetime import timedelta
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
from app.services import credit_card_service, exchange_rate_service, settings_service
from app.utils.metrics import RateLookup, convert_value

ZERO = Decimal("0")


# Sums per-month (year, month, currency, amount) buckets into one converted total, converting each
# month's bucket at that month's last day — the same per-month conversion the monthly evolution chart
# uses (get_monthly). Anchoring per-month rather than at a single period-end makes a window's overview
# totals equal the sum of the chart's converted points for that window (same skip semantics).
# Returns (total, skipped currency codes).
def _sum_monthly_converted(
    rows: list[tuple[int, int, str, Decimal]],
    target_currency: str | None,
    lookup: RateLookup | None,
) -> tuple[Decimal, set[str]]:
    total = ZERO
    skipped: set[str] = set()
    for year, month, currency, amount in rows:
        val = amount
        if target_currency and currency != target_currency:
            rate_map = lookup.get_rate_map_at(_month_end(year, month)) if lookup else None
            converted = convert_value(val, currency, target_currency, rate_map) if rate_map else None
            if converted is None:
                skipped.add(currency)
                continue
            val = converted
        total += val
    return total, skipped


# Returns the last day of the month containing month_start, used to convert monthly aggregates
# at the end of their period (matches how monthly snapshots are typically dated).
def _month_end(year: int, month: int) -> date_type:
    return date_type(year, month, _calendar.monthrange(year, month)[1])


# Computes overview metrics (total income, expenses, net, card balance, period change).
async def get_overview(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    lookup: RateLookup | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> FinanceOverviewResponse:
    lookup = await _build_lookup_if_needed(session, user_id, currency, lookup)
    today = await settings_service.get_user_today(session, user_id)

    # Current period totals — summed from per-month buckets converted at each month's end, so a
    # window's total_income/total_expenses equal the sum of the monthly chart's converted points
    # for the same window (same skip semantics).
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

    total_income, skipped_income = _sum_monthly_converted(income_rows, currency, lookup)
    total_expenses, skipped_expenses = _sum_monthly_converted(expense_rows, currency, lookup)
    skipped = skipped_income | skipped_expenses

    # Period-over-period change (compare with same-length previous period).
    income_change_pct = None
    expense_change_pct = None
    if date_from and date_to:
        # Same-length previous window with inclusive bounds: prev_to ends the day before the
        # current window starts (no shared day), and prev spans the same number of days.
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - (date_to - date_from)

        prev_income_rows = await income_repository.sum_by_user_monthly(
            session,
            user_id,
            date_from=prev_from,
            date_to=prev_to,
        )
        prev_expense_rows = await expense_repository.sum_by_user_monthly(
            session,
            user_id,
            date_from=prev_from,
            date_to=prev_to,
        )

        # Prior period converts each of its months at that month's end (same per-month basis as the
        # current period), so the comparison reflects what each period was worth at the time.
        prev_income, prev_skipped_i = _sum_monthly_converted(prev_income_rows, currency, lookup)
        prev_expenses, prev_skipped_e = _sum_monthly_converted(prev_expense_rows, currency, lookup)
        skipped |= prev_skipped_i | prev_skipped_e

        if prev_income != ZERO:
            income_change_pct = (total_income - prev_income) / prev_income
        if prev_expenses != ZERO:
            expense_change_pct = (total_expenses - prev_expenses) / prev_expenses

    # Credit card liability — current outstanding, so convert at today's rate per bucket.
    # Includes archived cards: archive is a UI filter, not an accounting event, so an
    # archived card's outstanding balance stays a liability.
    cards = await credit_card_repository.list_by_user(session, user_id, active_only=False)
    card_ids = [c.id for c in cards if c.id is not None]
    card_balance = ZERO
    if card_ids:
        card_currencies = {c.id: c.currency for c in cards if c.id is not None}
        balances = await credit_card_service.get_card_balances(session, card_ids, card_currencies, user_id)
        today_rate_map = lookup.get_rate_map_at(today) if lookup else None
        for buckets in balances.values():
            for bucket in buckets:
                val = bucket.balance
                if val and currency and bucket.currency != currency:
                    converted = convert_value(val, bucket.currency, currency, today_rate_map) if today_rate_map else None
                    if converted is None:
                        skipped.add(bucket.currency)
                        continue
                    val = converted
                card_balance += val

    return FinanceOverviewResponse(
        total_income=total_income,
        total_expenses=total_expenses,
        net=total_income - total_expenses,
        income_change_pct=income_change_pct,
        expense_change_pct=expense_change_pct,
        credit_card_balance=card_balance,
        currency=currency,
        skipped_currencies=sorted(skipped),
    )


# Computes monthly income vs expenses series for the bar chart.
async def get_monthly(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> FinanceMonthlyResponse:
    lookup = await _build_lookup_if_needed(session, user_id, currency)

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

    # Aggregate multi-currency monthly totals into a single converted value per month, converting
    # at the month's last day so each historical month uses its own period-end FX rate.
    skipped: set[str] = set()
    income_by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    for year, month, cur, amount in income_rows:
        val = amount
        if currency and cur != currency:
            rate_map = lookup.get_rate_map_at(_month_end(year, month)) if lookup else None
            converted = convert_value(val, cur, currency, rate_map) if rate_map else None
            if converted is None:
                skipped.add(cur)
                continue
            val = converted
        income_by_month[(year, month)] += val

    expense_by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    for year, month, cur, amount in expense_rows:
        val = amount
        if currency and cur != currency:
            rate_map = lookup.get_rate_map_at(_month_end(year, month)) if lookup else None
            converted = convert_value(val, cur, currency, rate_map) if rate_map else None
            if converted is None:
                skipped.add(cur)
                continue
            val = converted
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

    return FinanceMonthlyResponse(points=points, currency=currency, skipped_currencies=sorted(skipped))


# Computes expense breakdown by category for the donut chart.
async def get_expense_breakdown(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> ExpenseBreakdownResponse:
    lookup = await _build_lookup_if_needed(session, user_id, currency)
    anchor = date_to or await settings_service.get_user_today(session, user_id)
    rate_map = lookup.get_rate_map_at(anchor) if (currency and lookup) else None

    rows = await expense_repository.sum_by_user_grouped_by_category(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Aggregate multi-currency per-category totals — anchor conversion to the period end. The
    # category breakdown loses per-row dates at the DB layer (grouped by category, not month), so
    # unlike the overview it can't converge on per-month rates; the period-end anchor is the
    # closest available.
    skipped: set[str] = set()
    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for category, cur, amount in rows:
        val = amount
        if currency and cur != currency:
            converted = convert_value(val, cur, currency, rate_map) if rate_map else None
            if converted is None:
                skipped.add(cur)
                continue
            val = converted
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
        skipped_currencies=sorted(skipped),
    )


# Computes income breakdown by category for the donut chart.
async def get_income_breakdown(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> IncomeBreakdownResponse:
    lookup = await _build_lookup_if_needed(session, user_id, currency)
    anchor = date_to or await settings_service.get_user_today(session, user_id)
    rate_map = lookup.get_rate_map_at(anchor) if (currency and lookup) else None

    rows = await income_repository.sum_by_user_grouped_by_category(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Aggregate multi-currency per-category totals — anchor conversion to the period end.
    skipped: set[str] = set()
    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for category, cur, amount in rows:
        val = amount
        if currency and cur != currency:
            converted = convert_value(val, cur, currency, rate_map) if rate_map else None
            if converted is None:
                skipped.add(cur)
                continue
            val = converted
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
        skipped_currencies=sorted(skipped),
    )


# Returns a pre-loaded RateLookup when a display currency is requested. None otherwise.
# Reuses a prebuilt per-request lookup when the caller (dashboard_service) already built one.
async def _build_lookup_if_needed(
    session: AsyncSession,
    user_id: int,
    currency: str | None,
    lookup: RateLookup | None = None,
) -> RateLookup | None:
    if not currency:
        return None
    if lookup is not None:
        return lookup
    return await exchange_rate_service.get_user_rate_lookup(session, user_id)
