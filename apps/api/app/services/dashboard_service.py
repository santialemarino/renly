# Business logic for the general dashboard (aggregates investments + finance).

import calendar as _calendar
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.card_settlement_repository import card_settlement_repository
from app.repositories.credit_card_repository import credit_card_repository
from app.repositories.expense_repository import expense_repository
from app.repositories.income_repository import income_repository
from app.repositories.installment_repository import installment_repository
from app.repositories.payment_obligation_repository import payment_obligation_repository
from app.repositories.subscription_repository import subscription_repository
from app.schemas.dashboard import (
    CompositionItem,
    DashboardCompositionResponse,
    DashboardEvolutionResponse,
    DashboardLiquidityResponse,
    DashboardOverviewResponse,
    NetWorthEvolutionPoint,
    SkippedLiquidityEntity,
)
from app.services import credit_card_service, finance_metrics_service, metrics_service
from app.utils.dates import OBLIGATION_MONTH_STEP
from app.utils.liquidity import (
    LIQUIDITY_INCOME_MIN_HISTORY_DAYS,
    LIQUIDITY_INCOME_WINDOW_DAYS,
    STATE_UNKNOWN,
    classify_liquidity,
    compute_fixed_monthly_commitments,
    compute_monthly_income,
)
from app.utils.metrics import RateLookup, build_rate_lookup, convert_value
from app.utils.settings import get_liquidity_threshold

ZERO = Decimal("0")


# Returns the last day of the given (year, month). Used to convert monthly aggregates at month-end.
def _month_end(year: int, month: int) -> date_type:
    return date_type(year, month, _calendar.monthrange(year, month)[1])


# Pure computation: builds cumulative monthly card balance from expense and
# settlement totals. Phase 3 dual-currency model: settlements carry their own
# currency (bucket they settle), so both inputs are 5-tuples and each tuple's
# currency converts directly to `target_currency` — each row at its OWN month-end rate
# (Phase 3 Step C — historical exchange rate conversion). `card_currencies` is no
# longer load-bearing here (each row knows its own currency) but stays in the
# signature so callers don't need to rewire — defensive fallback only.
# Returns {(year, month): cumulative_balance} in the target currency.
def compute_monthly_card_balances(
    expense_monthly: list[tuple[int, int, int, str, float]],
    settlement_monthly: list[tuple[int, int, int, str, float]],
    card_currencies: dict[int, str],
    target_currency: str | None,
    lookup: RateLookup | None,
) -> dict[tuple[int, int], Decimal]:
    def _convert_at_month(val: Decimal, currency: str, year: int, month: int) -> Decimal:
        if not (target_currency and lookup) or currency == target_currency:
            return val
        rate_map = lookup.get_rate_map_at(_month_end(year, month))
        if rate_map is None:
            return val
        return convert_value(val, currency, target_currency, rate_map)

    # Aggregate expenses per (year, month), converting each row at its OWN month-end rate.
    month_expenses: dict[tuple[int, int], Decimal] = {}
    for _card_id, year, month, currency, total in expense_monthly:
        val = _convert_at_month(Decimal(str(total)), currency, year, month)
        key = (year, month)
        month_expenses[key] = month_expenses.get(key, ZERO) + val

    # Aggregate settlements per (year, month), converting each row at its OWN month-end rate.
    month_settlements: dict[tuple[int, int], Decimal] = {}
    for _card_id, year, month, currency, total in settlement_monthly:
        val = _convert_at_month(Decimal(str(total)), currency, year, month)
        key = (year, month)
        month_settlements[key] = month_settlements.get(key, ZERO) + val

    # Collect and sort all months, then accumulate running balance.
    all_months = sorted(set(month_expenses) | set(month_settlements))
    running = ZERO
    result: dict[tuple[int, int], Decimal] = {}
    for ym in all_months:
        running += month_expenses.get(ym, ZERO) - month_settlements.get(ym, ZERO)
        result[ym] = running
    return result


# Aggregates investment portfolio metrics and finance overview into a single dashboard response.
async def get_overview(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> DashboardOverviewResponse:
    # Sequential calls — AsyncSession is not safe for concurrent use.
    portfolio = await metrics_service.get_portfolio_metrics(
        session,
        user_id,
        currency=currency,
        dollar_preference=dollar_preference,
    )
    finance = await finance_metrics_service.get_overview(
        session,
        user_id,
        currency=currency,
        dollar_preference=dollar_preference,
        date_from=date_from,
        date_to=date_to,
    )

    net_worth = portfolio.total_value - finance.credit_card_balance

    # Net worth month-over-month change (approximated from portfolio change).
    net_worth_change = portfolio.month_change
    net_worth_change_pct: Decimal | None = None
    if net_worth_change is not None:
        prev = net_worth - net_worth_change
        if prev != ZERO:
            net_worth_change_pct = net_worth_change / prev

    savings_rate: Decimal | None = None
    if finance.total_income != ZERO:
        savings_rate = (finance.total_income - finance.total_expenses) / finance.total_income

    income_expense_ratio: Decimal | None = None
    if finance.total_expenses != ZERO:
        income_expense_ratio = finance.total_income / finance.total_expenses

    return DashboardOverviewResponse(
        net_worth=net_worth,
        net_worth_change=net_worth_change,
        net_worth_change_pct=net_worth_change_pct,
        investment_total=portfolio.total_value,
        investment_gain=portfolio.absolute_gain,
        investment_gain_pct=portfolio.total_return_pct,
        investment_month_change=portfolio.month_change,
        investment_month_change_pct=portfolio.month_change_pct,
        credit_card_balance=finance.credit_card_balance,
        total_income=finance.total_income,
        total_expenses=finance.total_expenses,
        savings_rate=savings_rate,
        income_expense_ratio=income_expense_ratio,
        currency=currency,
    )


# Computes monthly net worth series (investment value - cumulative card balance).
async def get_evolution(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> DashboardEvolutionResponse:
    portfolio_evo = await metrics_service.get_portfolio_evolution(
        session,
        user_id,
        currency=currency,
        dollar_preference=dollar_preference,
        start_date=date_from,
        end_date=date_to,
    )

    if not portfolio_evo.points:
        return DashboardEvolutionResponse(points=[], currency=currency)

    # Build monthly card balance series.
    cards = await credit_card_repository.list_by_user(session, user_id)
    card_ids = [c.id for c in cards if c.id is not None]
    card_currencies = {c.id: c.currency for c in cards if c.id is not None}

    card_balance_by_month: dict[tuple[int, int], Decimal] = {}
    if card_ids:
        expense_monthly = await expense_repository.sum_by_credit_card_ids_monthly(session, card_ids)
        settlement_monthly = await card_settlement_repository.sum_by_card_ids_monthly(session, card_ids)
        lookup = await build_rate_lookup(session, dollar_preference) if currency else None
        card_balance_by_month = compute_monthly_card_balances(
            expense_monthly,
            settlement_monthly,
            card_currencies,
            currency,
            lookup,
        )

    # Merge: for each portfolio evolution point, look up cumulative card balance.
    points: list[NetWorthEvolutionPoint] = []
    last_balance = ZERO
    for p in portfolio_evo.points:
        ym = (p.date.year, p.date.month)
        if ym in card_balance_by_month:
            last_balance = card_balance_by_month[ym]
        points.append(
            NetWorthEvolutionPoint(
                date=p.date,
                investment_value=p.total_value,
                card_balance=last_balance,
                net_worth=p.total_value - last_balance,
            )
        )

    return DashboardEvolutionResponse(points=points, currency=currency)


# Computes investment allocation by category plus a liabilities segment.
async def get_composition(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
) -> DashboardCompositionResponse:
    allocation = await metrics_service.get_allocation(
        session,
        user_id,
        currency=currency,
        dollar_preference=dollar_preference,
    )

    # Compute total card liability, converting each bucket's balance to display currency at TODAY's
    # rate (the composition view is a snapshot of the current state, not a historical one).
    cards = await credit_card_repository.list_by_user(session, user_id)
    card_ids = [c.id for c in cards if c.id is not None]
    card_balance = ZERO
    if card_ids:
        card_currencies = {c.id: c.currency for c in cards if c.id is not None}
        balances = await credit_card_service.get_card_balances(session, card_ids, card_currencies)
        lookup = await build_rate_lookup(session, dollar_preference) if currency else None
        rate_map = lookup.get_rate_map_at(date_type.today()) if lookup else None
        for buckets in balances.values():
            for bucket in buckets:
                val = bucket.balance
                if currency and bucket.currency != currency and rate_map:
                    val = convert_value(val, bucket.currency, currency, rate_map)
                card_balance += val

    total_assets = allocation.total_value
    total_gross = total_assets + card_balance

    items: list[CompositionItem] = []
    for item in allocation.items:
        pct = (item.value / total_gross * 100) if total_gross != ZERO else ZERO
        items.append(CompositionItem(label=item.category, value=item.value, percentage=pct))

    if card_balance > ZERO:
        pct = (card_balance / total_gross * 100) if total_gross != ZERO else ZERO
        items.append(CompositionItem(label="liabilities", value=card_balance, percentage=pct))

    return DashboardCompositionResponse(
        items=items,
        total_assets=total_assets,
        total_liabilities=card_balance,
        currency=currency,
    )


# Computes the liquidity health indicator: ratio of fixed monthly commitments to normalised
# monthly income, classified against the user's threshold. Phase 3 Step 6.
async def get_liquidity(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    dollar_preference: str | None = None,
) -> DashboardLiquidityResponse:
    threshold = await get_liquidity_threshold(session, user_id)
    today = date_type.today()

    # Build the rate lookup once — reused for commitments + income conversions.
    lookup = await build_rate_lookup(session, dollar_preference) if currency else None
    rate_map_today = lookup.get_rate_map_at(today) if lookup else None

    # Commitments: load active rows from the four sources, amortise to monthly-equivalent
    # per currency via the pure helper, then sum-convert to display currency at today's rate.
    subscriptions = await subscription_repository.list_by_user(session, user_id, active_only=True)
    installments = await installment_repository.list_by_user(session, user_id, active_only=True)
    obligations = await payment_obligation_repository.list_by_user(session, user_id, active_only=True)
    cards = await credit_card_repository.list_by_user(session, user_id, active_only=True)
    commitments_by_currency = compute_fixed_monthly_commitments(subscriptions, installments, obligations, cards)

    commitments_total = ZERO
    unsupported_currencies: set[str] = set()
    for cur, val in commitments_by_currency.items():
        if currency and rate_map_today and cur != currency:
            if cur not in rate_map_today:
                # Conversion would no-op silently; flag the currency so the diagnostic can list
                # affected entities and exclude their amount from the displayed ratio.
                unsupported_currencies.add(cur)
                continue
            val = convert_value(val, cur, currency, rate_map_today)
        commitments_total += val

    skipped_entities: list[SkippedLiquidityEntity] = []
    if unsupported_currencies:
        for sub in subscriptions:
            if sub.currency in unsupported_currencies:
                skipped_entities.append(SkippedLiquidityEntity(type="subscription", name=sub.name, currency=sub.currency))
        for inst in installments:
            if inst.currency in unsupported_currencies and inst.current_installment <= inst.installments_count:
                skipped_entities.append(SkippedLiquidityEntity(type="installment", name=inst.name, currency=inst.currency))
        for obl in obligations:
            if obl.currency in unsupported_currencies and (obl.recurrence or "") in OBLIGATION_MONTH_STEP:
                skipped_entities.append(SkippedLiquidityEntity(type="obligation", name=obl.name, currency=obl.currency))
        for card in cards:
            if card.currency in unsupported_currencies and card.monthly_payment is not None:
                skipped_entities.append(SkippedLiquidityEntity(type="credit_card", name=card.name, currency=card.currency))

    # Income window sizing follows the user's actual income history. Below the minimum
    # history threshold (or zero history) the card renders 'unknown' — one paycheck
    # doesn't make a baseline.
    first_income_date = await income_repository.get_first_income_date(session, user_id)
    if first_income_date is None:
        return DashboardLiquidityResponse(
            ratio=None,
            state=STATE_UNKNOWN,
            fixed_monthly_commitments=commitments_total,
            monthly_income=ZERO,
            threshold=threshold,
            income_window_days=LIQUIDITY_INCOME_WINDOW_DAYS,
            actual_window_days=0,
            currency=currency,
            skipped_entities=skipped_entities,
        )

    elapsed_days = (today - first_income_date).days + 1
    if elapsed_days < LIQUIDITY_INCOME_MIN_HISTORY_DAYS:
        return DashboardLiquidityResponse(
            ratio=None,
            state=STATE_UNKNOWN,
            fixed_monthly_commitments=commitments_total,
            monthly_income=ZERO,
            threshold=threshold,
            income_window_days=LIQUIDITY_INCOME_WINDOW_DAYS,
            actual_window_days=elapsed_days,
            currency=currency,
            skipped_entities=skipped_entities,
        )

    actual_window_days = min(LIQUIDITY_INCOME_WINDOW_DAYS, elapsed_days)
    window_start = today - timedelta(days=actual_window_days - 1)
    income_by_currency = await income_repository.sum_by_user(
        session,
        user_id,
        date_from=window_start,
        date_to=today,
    )
    monthly_income = compute_monthly_income(
        income_by_currency,
        days=actual_window_days,
        target_currency=currency,
        lookup=lookup,
        anchor_date=today,
    )

    if monthly_income == ZERO:
        return DashboardLiquidityResponse(
            ratio=None,
            state=STATE_UNKNOWN,
            fixed_monthly_commitments=commitments_total,
            monthly_income=ZERO,
            threshold=threshold,
            income_window_days=LIQUIDITY_INCOME_WINDOW_DAYS,
            actual_window_days=actual_window_days,
            currency=currency,
            skipped_entities=skipped_entities,
        )

    ratio = commitments_total / monthly_income
    state = classify_liquidity(ratio, threshold)

    return DashboardLiquidityResponse(
        ratio=ratio,
        state=state,
        fixed_monthly_commitments=commitments_total,
        monthly_income=monthly_income,
        threshold=threshold,
        income_window_days=LIQUIDITY_INCOME_WINDOW_DAYS,
        actual_window_days=actual_window_days,
        currency=currency,
        skipped_entities=skipped_entities,
    )
