# Business logic for financial dashboard metrics (income, expenses, credit cards).

from collections import defaultdict
from collections.abc import Callable
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.credit_card_repository import credit_card_repository
from app.repositories.expense_repository import expense_repository
from app.repositories.group_repository import group_repository
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


# Converts each daily (date, category, currency, amount) bucket into the display currency at the rate of
# its OWN day and hands back the converted amounts in the same order — None where the bucket could not
# convert, with its currency added to `skipped`. Every period aggregate here (the overview totals and
# their previous-period comparison, the monthly bars, the category donuts) sums these SAME buckets, so
# the three agree exactly, and each equals the sum of the converted rows the /expenses and /income lists
# show for the same window (each list row converts at its own date too), up to the cent a bucket of
# several rows rounds to once rather than per row.
def _convert_daily(
    buckets: list[tuple[date_type, str, str, Decimal]],
    target_currency: str | None,
    lookup: RateLookup | None,
    skipped: set[str],
) -> list[Decimal | None]:
    converted: list[Decimal | None] = []
    for day, _category, currency, amount in buckets:
        if not target_currency or currency == target_currency:
            converted.append(amount)
            continue
        rate_map = lookup.get_rate_map_at(day) if lookup else None
        value = convert_value(amount, currency, target_currency, rate_map) if rate_map else None
        if value is None:
            skipped.add(currency)
        converted.append(value)
    return converted


# Sums daily buckets into one converted total, each bucket at its own day's rate.
# Returns (total, skipped currency codes).
def _sum_daily_converted(
    buckets: list[tuple[date_type, str, str, Decimal]],
    target_currency: str | None,
    lookup: RateLookup | None,
) -> tuple[Decimal, set[str]]:
    skipped: set[str] = set()
    total = sum((v for v in _convert_daily(buckets, target_currency, lookup, skipped) if v is not None), ZERO)
    return total, skipped


# Sums converted daily buckets by a key derived from each bucket (its month, its category). A bucket that
# could not convert (None) contributes nothing — its currency is already in the skipped set.
def _sum_converted_by[K](
    buckets: list[tuple[date_type, str, str, Decimal]],
    converted: list[Decimal | None],
    key: Callable[[date_type, str], K],
) -> dict[K, Decimal]:
    totals: dict[K, Decimal] = defaultdict(lambda: ZERO)
    for (day, category, _currency, _amount), value in zip(buckets, converted):
        if value is not None:
            totals[key(day, category)] += value
    return totals


# The month a daily bucket falls in, as (year, month).
def _month_key(day: date_type, _category: str) -> tuple[int, int]:
    return (day.year, day.month)


# The category a daily bucket belongs to.
def _category_key(_day: date_type, category: str) -> str:
    return category


# Computes overview metrics (total income, expenses, net, card balance, period change).
async def get_overview(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    lookup: RateLookup | None = None,
    member_ids: list[int] | None = None,
    today: date_type | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> FinanceOverviewResponse:
    lookup = await _build_lookup_if_needed(session, user_id, currency, lookup)
    member_ids = await _resolve_member_ids(session, user_id, member_ids)
    # The caller (dashboard overview) passes today from its merged settings read; standalone callers
    # (the finance-metrics router) omit it and resolve it here.
    if today is None:
        today = await settings_service.get_user_today(session, user_id)

    # Current period totals — summed from daily buckets, each converted at its own day's rate, so a
    # window's total_income/total_expenses equal both the sum of the converted rows the lists show and
    # the sum of the monthly chart's bars for the same window (same skip semantics).
    income_rows = await income_repository.sum_by_user_daily(
        session,
        user_id,
        member_ids,
        date_from=date_from,
        date_to=date_to,
    )
    expense_rows = await expense_repository.sum_by_user_daily(
        session,
        user_id,
        member_ids,
        date_from=date_from,
        date_to=date_to,
    )

    total_income, skipped_income = _sum_daily_converted(income_rows, currency, lookup)
    total_expenses, skipped_expenses = _sum_daily_converted(expense_rows, currency, lookup)
    skipped = skipped_income | skipped_expenses

    # Period-over-period change (compare with same-length previous period).
    income_change_pct = None
    expense_change_pct = None
    if date_from and date_to:
        # Same-length previous window with inclusive bounds: prev_to ends the day before the
        # current window starts (no shared day), and prev spans the same number of days.
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - (date_to - date_from)

        prev_income_rows = await income_repository.sum_by_user_daily(
            session,
            user_id,
            member_ids,
            date_from=prev_from,
            date_to=prev_to,
        )
        prev_expense_rows = await expense_repository.sum_by_user_daily(
            session,
            user_id,
            member_ids,
            date_from=prev_from,
            date_to=prev_to,
        )

        # Prior period converts each of its days at that day's rate (the same basis as the current
        # period), so the comparison reflects what each period was worth at the time.
        prev_income, prev_skipped_i = _sum_daily_converted(prev_income_rows, currency, lookup)
        prev_expenses, prev_skipped_e = _sum_daily_converted(prev_expense_rows, currency, lookup)
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
    member_ids = await _resolve_member_ids(session, user_id, None)

    income_rows = await income_repository.sum_by_user_daily(
        session,
        user_id,
        member_ids,
        date_from=date_from,
        date_to=date_to,
    )
    expense_rows = await expense_repository.sum_by_user_daily(
        session,
        user_id,
        member_ids,
        date_from=date_from,
        date_to=date_to,
    )

    # Each month's bar is the sum of its days, each converted at its own day's rate — the same
    # conversion the overview totals and the lists use, so the bars of a window add up to its totals.
    skipped: set[str] = set()
    income_by_month = _sum_converted_by(income_rows, _convert_daily(income_rows, currency, lookup, skipped), _month_key)
    expense_by_month = _sum_converted_by(expense_rows, _convert_daily(expense_rows, currency, lookup, skipped), _month_key)

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
    member_ids = await _resolve_member_ids(session, user_id, None)

    rows = await expense_repository.sum_by_user_daily(
        session,
        user_id,
        member_ids,
        date_from=date_from,
        date_to=date_to,
    )

    # The same daily buckets the period total sums, each at its own day's rate, so the slices add up to
    # the overview's total for the same window exactly.
    skipped: set[str] = set()
    cat_values = _sum_converted_by(rows, _convert_daily(rows, currency, lookup, skipped), _category_key)

    total_expenses = sum(cat_values.values(), ZERO)

    # A category can total NEGATIVE — a card credit posts a negative reconciliation adjustment, which
    # correctly reduces spending. The headline total keeps it (net spending is the honest figure), but
    # percentages are computed against the positive categories only: a share of a mixed-sign total is
    # meaningless, and the donut this feeds cannot render a negative slice. Same clamp the general
    # dashboard's composition already applies to a negative cash total / a net-credit card.
    positive_total = sum((v for v in cat_values.values() if v > ZERO), ZERO)

    items = []
    for category, value in sorted(cat_values.items(), key=lambda x: x[1], reverse=True):
        pct = (value / positive_total * 100) if (value > ZERO and positive_total != ZERO) else ZERO
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
    member_ids = await _resolve_member_ids(session, user_id, None)

    rows = await income_repository.sum_by_user_daily(
        session,
        user_id,
        member_ids,
        date_from=date_from,
        date_to=date_to,
    )

    # The same daily buckets the period total sums, each at its own day's rate, so the slices add up to
    # the overview's total for the same window exactly.
    skipped: set[str] = set()
    cat_values = _sum_converted_by(rows, _convert_daily(rows, currency, lookup, skipped), _category_key)

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


# The caller's own active group seats, which is what turns every aggregate here into "their spending
# and their earnings" rather than "the rows in their own two tables".
#
# Resolved once per request and threaded down, because a member's SHARE of a shared expense is their
# expense (D2) and their entitlement out of shared income is their income — the same rule /expenses and
# /income already apply row by row. Without it the finance dashboard states a different total from the
# list it summarises.
#
# The dashboard overview pre-resolves them (it needs the same seats for the shared half of net worth)
# and passes them in; the standalone finance-metrics endpoints resolve them here. An empty list is a
# real answer, not a missing one — every solo user has one, and it is what makes the shared branch of
# each aggregate not be built at all.
async def _resolve_member_ids(session: AsyncSession, user_id: int, member_ids: list[int] | None) -> list[int]:
    if member_ids is not None:
        return member_ids
    return await group_repository.list_active_member_ids(session, user_id)


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
