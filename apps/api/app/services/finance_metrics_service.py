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
from app.services import credit_card_service, exchange_rate_service
from app.utils.metrics import RateLookup, convert_value

ZERO = Decimal("0")


# Period-summary totals are aggregated at the DB layer (`SUM(amount) GROUP BY currency`) and lose
# the per-row date dimension, so the conversion can't truly be per-row here. We anchor the
# conversion to the period-end (date_to) — better than always-today's rate, but acknowledged as
# coarser than the per-row conversion used everywhere else. If finer historical accuracy is
# needed later, the repository can switch to per-month grouping (already done for the monthly
# evolution chart).
# Returns (total, skipped currency codes).
def _sum_converted(
    totals_by_currency: dict[str, float],
    target_currency: str | None,
    lookup: RateLookup | None,
    anchor_date: date_type,
) -> tuple[Decimal, set[str]]:
    total = ZERO
    skipped: set[str] = set()
    rate_map = lookup.get_rate_map_at(anchor_date) if (target_currency and lookup) else None
    for currency, amount in totals_by_currency.items():
        val = Decimal(str(amount))
        if target_currency and currency != target_currency:
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
    today = date_type.today()
    anchor = date_to or today

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

    total_income, skipped_income = _sum_converted(income_by_currency, currency, lookup, anchor)
    total_expenses, skipped_expenses = _sum_converted(expense_by_currency, currency, lookup, anchor)
    skipped = skipped_income | skipped_expenses

    # Period-over-period change (compare with same-length previous period).
    income_change_pct = None
    expense_change_pct = None
    if date_from and date_to:
        # Same-length previous window with inclusive bounds: prev_to ends the day before the
        # current window starts (no shared day), and prev spans the same number of days.
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - (date_to - date_from)

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

        # Prior period is anchored to ITS own end so the comparison reflects what each period
        # was worth at the time, not at today's rate.
        prev_income, prev_skipped_i = _sum_converted(prev_income_by_currency, currency, lookup, prev_to)
        prev_expenses, prev_skipped_e = _sum_converted(prev_expense_by_currency, currency, lookup, prev_to)
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
        balances = await credit_card_service.get_card_balances(session, card_ids, card_currencies)
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
        val = Decimal(str(amount))
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
        val = Decimal(str(amount))
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
    anchor = date_to or date_type.today()
    rate_map = lookup.get_rate_map_at(anchor) if (currency and lookup) else None

    rows = await expense_repository.sum_by_user_grouped_by_category(
        session,
        user_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Aggregate multi-currency per-category totals — anchor conversion to the period end. The
    # category breakdown loses per-row dates at the DB layer; see _sum_converted comment above.
    skipped: set[str] = set()
    cat_values: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for category, cur, amount in rows:
        val = Decimal(str(amount))
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
    anchor = date_to or date_type.today()
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
        val = Decimal(str(amount))
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
