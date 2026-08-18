# Business logic for the general dashboard (aggregates investments + finance).

import calendar as _calendar
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.account_repository import account_repository
from app.repositories.card_settlement_repository import card_settlement_repository
from app.repositories.credit_card_repository import credit_card_repository
from app.repositories.expense_repository import expense_repository
from app.repositories.income_repository import income_repository
from app.repositories.installment_repository import installment_repository
from app.repositories.investment_repository import investment_repository
from app.repositories.payment_obligation_repository import payment_obligation_repository
from app.repositories.subscription_repository import subscription_repository
from app.repositories.transfer_repository import transfer_repository
from app.schemas.dashboard import (
    CompositionItem,
    DashboardCompositionResponse,
    DashboardEvolutionResponse,
    DashboardLiquidityResponse,
    DashboardOverviewResponse,
    NetWorthEvolutionPoint,
    SkippedLiquidityEntity,
)
from app.services import (
    account_service,
    credit_card_service,
    exchange_rate_service,
    finance_metrics_service,
    metrics_service,
    settings_service,
)
from app.utils.dates import OBLIGATION_MONTH_STEP
from app.utils.liquidity import (
    LIQUIDITY_INCOME_MIN_HISTORY_DAYS,
    LIQUIDITY_INCOME_WINDOW_DAYS,
    STATE_UNKNOWN,
    classify_liquidity,
    compute_fixed_monthly_commitments,
    compute_monthly_income,
)
from app.utils.metrics import RateLookup, convert_value, month_over_month

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
# Returns ({(year, month): cumulative_balance} in the target currency, skipped currency codes).
def compute_monthly_card_balances(
    expense_monthly: list[tuple[int, int, int, str, float]],
    settlement_monthly: list[tuple[int, int, int, str, float]],
    card_currencies: dict[int, str],
    target_currency: str | None,
    lookup: RateLookup | None,
) -> tuple[dict[tuple[int, int], Decimal], list[str]]:
    def _convert_at_month(val: Decimal, currency: str, year: int, month: int) -> Decimal | None:
        if not (target_currency and lookup) or currency == target_currency:
            return val
        rate_map = lookup.get_rate_map_at(_month_end(year, month))
        if rate_map is None:
            return None
        return convert_value(val, currency, target_currency, rate_map)

    skipped: set[str] = set()

    # Aggregate expenses per (year, month), converting each row at its OWN month-end rate.
    month_expenses: dict[tuple[int, int], Decimal] = {}
    for _card_id, year, month, currency, total in expense_monthly:
        val = _convert_at_month(Decimal(str(total)), currency, year, month)
        if val is None:
            skipped.add(currency)
            continue
        key = (year, month)
        month_expenses[key] = month_expenses.get(key, ZERO) + val

    # Aggregate settlements per (year, month), converting each row at its OWN month-end rate.
    month_settlements: dict[tuple[int, int], Decimal] = {}
    for _card_id, year, month, currency, total in settlement_monthly:
        val = _convert_at_month(Decimal(str(total)), currency, year, month)
        if val is None:
            skipped.add(currency)
            continue
        key = (year, month)
        month_settlements[key] = month_settlements.get(key, ZERO) + val

    # Collect and sort all months, then accumulate running balance.
    all_months = sorted(set(month_expenses) | set(month_settlements))
    running = ZERO
    result: dict[tuple[int, int], Decimal] = {}
    for ym in all_months:
        running += month_expenses.get(ym, ZERO) - month_settlements.get(ym, ZERO)
        result[ym] = running
    return result, sorted(skipped)


# Pure computation: forward-fills the cumulative card balance onto each requested month.
# `card_balance_by_month` holds cumulative balances only at months WITH card activity; each
# requested month takes the latest cumulative entry at-or-before it, so gap months (and
# months after the last activity) keep the prior balance instead of reading zero. Months
# before any activity read zero. `months` must be ascending. Returns one balance per
# requested month, same order.
def forward_fill_card_balances(
    months: list[tuple[int, int]],
    card_balance_by_month: dict[tuple[int, int], Decimal],
) -> list[Decimal]:
    balance_months = sorted(card_balance_by_month)
    result: list[Decimal] = []
    last_balance = ZERO
    next_idx = 0
    for ym in months:
        while next_idx < len(balance_months) and balance_months[next_idx] <= ym:
            last_balance = card_balance_by_month[balance_months[next_idx]]
            next_idx += 1
        result.append(last_balance)
    return result


# Pure computation: cumulative cash balance (in the display currency) at each month with activity.
# Mirrors compute_monthly_card_balances: each signed movement converts at its OWN month-end rate,
# then accumulates. Movements = each account's opening balance (a positive delta in its opening
# month) + linked income (+) − linked expenses (−) − settlements (−), all in the account's own
# currency. An unconvertible currency is skipped and reported. Returns ({(year, month): cumulative
# balance in target currency}, sorted skipped currency codes).
def compute_monthly_cash_balances(
    accounts: list,
    income_monthly: list[tuple[int, int, int, Decimal]],
    expense_monthly: list[tuple[int, int, int, Decimal]],
    settlement_monthly: list[tuple[int, int, int, Decimal]],
    transfer_in_monthly: list[tuple[int, int, int, Decimal]],
    transfer_out_monthly: list[tuple[int, int, int, Decimal]],
    target_currency: str | None,
    lookup: RateLookup | None,
) -> tuple[dict[tuple[int, int], Decimal], list[str]]:
    def _convert_at_month(val: Decimal, currency: str, year: int, month: int) -> Decimal | None:
        if not (target_currency and lookup) or currency == target_currency:
            return val
        rate_map = lookup.get_rate_map_at(_month_end(year, month))
        if rate_map is None:
            return None
        return convert_value(val, currency, target_currency, rate_map)

    currency_by_account = {a.id: a.currency for a in accounts}
    skipped: set[str] = set()
    month_delta: dict[tuple[int, int], Decimal] = {}

    def _add(account_id: int, year: int, month: int, amount: Decimal) -> None:
        currency = currency_by_account.get(account_id)
        if currency is None or amount == ZERO:
            return
        val = _convert_at_month(amount, currency, year, month)
        if val is None:
            skipped.add(currency)
            return
        month_delta[(year, month)] = month_delta.get((year, month), ZERO) + val

    # Opening balances enter as a positive delta in each account's opening month.
    for account in accounts:
        _add(account.id, account.opening_date.year, account.opening_date.month, account.opening_balance)
    for account_id, year, month, total in income_monthly:
        _add(account_id, year, month, Decimal(str(total)))
    for account_id, year, month, total in expense_monthly:
        _add(account_id, year, month, -Decimal(str(total)))
    for account_id, year, month, total in settlement_monthly:
        _add(account_id, year, month, -Decimal(str(total)))
    # Each transfer leg is added under its own account, in that account's currency, so a cross-currency
    # move converts each side at its own month-end rate — the same way the headline balance does.
    for account_id, year, month, total in transfer_in_monthly:
        _add(account_id, year, month, Decimal(str(total)))
    for account_id, year, month, total in transfer_out_monthly:
        _add(account_id, year, month, -Decimal(str(total)))

    running = ZERO
    result: dict[tuple[int, int], Decimal] = {}
    for ym in sorted(month_delta):
        running += month_delta[ym]
        result[ym] = running
    return result, sorted(skipped)


# Pure computation: total cash across accounts in the display currency. Each account's balance (in
# its own currency) converts at the given rate map (today's rate); a zero balance contributes
# nothing (so its currency is never flagged skipped); an unconvertible currency is skipped and
# reported. When target_currency is None nothing converts (balances sum raw, "original" mode).
# Mirrors the per-bucket card-balance conversion. Returns (total, skipped currency codes).
def compute_cash_total(
    accounts: list,
    account_balances: dict[int, Decimal],
    target_currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> tuple[Decimal, set[str]]:
    total = ZERO
    skipped: set[str] = set()
    for account in accounts:
        val = account_balances.get(account.id, ZERO)
        if val and target_currency and account.currency != target_currency:
            converted = convert_value(val, account.currency, target_currency, rate_map) if rate_map else None
            if converted is None:
                skipped.add(account.currency)
                continue
            val = converted
        total += val
    return total, skipped


# Loads accounts (including archived — like cards, they stay in net worth) plus their current
# derived balances, then converts to the display currency. Returns (total, skipped, whether the user
# has any account at all — the caller needs existence, not the list).
async def _load_cash_total(
    session: AsyncSession,
    user_id: int,
    currency: str | None,
    rate_map: dict[str, Decimal] | None,
) -> tuple[Decimal, set[str], bool]:
    accounts = await account_repository.list_by_user(session, user_id, active_only=False)
    account_balances = await account_service.get_account_balances(session, accounts, user_id)
    total, skipped = compute_cash_total(accounts, account_balances, currency, rate_map)
    return total, skipped, bool(accounts)


# Whether the net-worth headline is derived from anything at all — NOT whether it is non-zero.
# Offsetting holdings can net to exactly zero, and a new account's opening balance defaults to zero,
# so a value test would report "nothing here" for users who hold plenty. The investment probe is the
# ACTIVE-only one: an archived investment contributes nothing to portfolio value, unlike an archived
# account or card, whose balance stays in net worth. `has_accounts` rides the list _load_cash_total
# already fetched, and the two probes are indexed LIMIT 1 reads reached only when it is False — so a
# user holding an account pays nothing extra and an empty account pays two cheap reads.
async def _has_holdings(session: AsyncSession, user_id: int, *, has_accounts: bool) -> bool:
    if has_accounts:
        return True
    if await investment_repository.exists_active_by_user(session, user_id):
        return True
    return await credit_card_repository.exists_by_user(session, user_id)


# Aggregates investment portfolio metrics and finance overview into a single dashboard response.
async def get_overview(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> DashboardOverviewResponse:
    # One user_settings read + one rate lookup per request, shared by the investment and finance
    # halves. get_request_settings folds the dollar preference (which builds the lookup) and the
    # timezone (the finance card-balance rate anchor) into a single row read; only needed when a
    # display currency is requested — otherwise nothing converts.
    rs = await settings_service.get_request_settings(session, user_id) if currency else None
    lookup = await exchange_rate_service.build_rate_lookup(session, rs.dollar_preference) if rs else None
    today = settings_service.today_for_timezone(rs.timezone) if rs else None
    # Sequential calls — AsyncSession is not safe for concurrent use.
    portfolio = await metrics_service.get_portfolio_metrics(
        session,
        user_id,
        currency=currency,
        lookup=lookup,
    )
    finance = await finance_metrics_service.get_overview(
        session,
        user_id,
        currency=currency,
        lookup=lookup,
        today=today,
        date_from=date_from,
        date_to=date_to,
    )

    # Cash across all accounts, converted to the display currency at today's rate (fail-loud).
    rate_map_today = lookup.get_rate_map_at(today) if (lookup and today) else None
    cash_total, cash_skipped, has_accounts = await _load_cash_total(session, user_id, currency, rate_map_today)

    net_worth = portfolio.total_value + cash_total - finance.credit_card_balance
    has_holdings = await _has_holdings(session, user_id, has_accounts=has_accounts)

    # Net worth month-over-month: the latest vs prior month of the SAME monthly net-worth series the
    # evolution chart uses (investment + cash − card per month), so the delta reflects cash and card
    # movements, not investments alone — e.g. funding a new account this month now shows up. Full
    # history (unwindowed): net worth is a point-in-time snapshot, unlike the period-scoped income
    # /expense totals. (investment_month_change below stays investment-only for the Investment card.)
    nw_points, _ = await compute_net_worth_evolution(session, user_id, currency=currency, lookup=lookup, today=today)
    net_worth_change: Decimal | None = None
    net_worth_change_pct: Decimal | None = None
    nw_mom = month_over_month([(p.date, p.net_worth) for p in nw_points])
    if nw_mom is not None:
        prev_nw, curr_nw = nw_mom
        net_worth_change = curr_nw - prev_nw
        if prev_nw != ZERO:
            net_worth_change_pct = net_worth_change / prev_nw

    savings_rate: Decimal | None = None
    if finance.total_income != ZERO:
        savings_rate = (finance.total_income - finance.total_expenses) / finance.total_income

    income_expense_ratio: Decimal | None = None
    if finance.total_expenses != ZERO:
        income_expense_ratio = finance.total_income / finance.total_expenses

    return DashboardOverviewResponse(
        net_worth=net_worth,
        cash_total=cash_total,
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
        has_holdings=has_holdings,
        # Fail-loud: surface every side's inconvertible currencies (finance/liability skips, any
        # investment base currency that couldn't reach the display currency, plus any account
        # currency the cash total had to exclude), so the summary flags everything its totals dropped.
        skipped_currencies=sorted(set(finance.skipped_currencies) | {s.base_currency for s in portfolio.skipped_investments} | cash_skipped),
    )


# Builds the monthly net-worth series (investment value + cumulative cash − cumulative card per month,
# forward-filled), shared by the evolution chart and the overview's month-over-month delta. Cash and
# card include archived rows (their balances stay in net worth; archive is a UI filter). Returns
# (points, sorted skipped-currency codes).
async def compute_net_worth_evolution(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None,
    lookup: RateLookup | None,
    today: date_type | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> tuple[list[NetWorthEvolutionPoint], list[str]]:
    portfolio_evo = await metrics_service.get_portfolio_evolution(
        session,
        user_id,
        currency=currency,
        lookup=lookup,
        start_date=date_from,
        end_date=date_to,
    )
    if not portfolio_evo.points:
        return [], []

    # Build monthly card balance series. Includes archived cards — their history and any
    # outstanding balance remain part of net worth (archive is a UI filter).
    cards = await credit_card_repository.list_by_user(session, user_id, active_only=False)
    card_ids = [c.id for c in cards if c.id is not None]
    card_currencies = {c.id: c.currency for c in cards if c.id is not None}

    card_balance_by_month: dict[tuple[int, int], Decimal] = {}
    skipped: set[str] = set()
    if card_ids:
        expense_monthly = await expense_repository.sum_by_credit_card_ids_monthly(session, card_ids, user_id)
        settlement_monthly = await card_settlement_repository.sum_by_card_ids_monthly(session, card_ids)
        card_balance_by_month, card_skipped = compute_monthly_card_balances(
            expense_monthly,
            settlement_monthly,
            card_currencies,
            currency,
            lookup,
        )
        skipped.update(card_skipped)

    # Build the monthly cash series the same way (opening balances + linked income/expenses/
    # settlements + both transfer legs accumulated, each converted at its own month-end). Includes archived accounts —
    # their balance stays in net worth (archive is a UI filter, like cards).
    accounts = await account_repository.list_by_user(session, user_id, active_only=False)
    account_ids = [a.id for a in accounts if a.id is not None]
    cash_balance_by_month: dict[tuple[int, int], Decimal] = {}
    if account_ids:
        cash_income = await income_repository.sum_by_account_ids_monthly(session, account_ids, user_id)
        cash_expense = await expense_repository.sum_by_account_ids_monthly(session, account_ids, user_id)
        cash_settlement = await card_settlement_repository.sum_by_account_ids_monthly(session, account_ids, user_id)
        cash_transfer_in = await transfer_repository.sum_in_by_account_ids_monthly(session, account_ids, user_id)
        cash_transfer_out = await transfer_repository.sum_out_by_account_ids_monthly(session, account_ids, user_id)
        cash_balance_by_month, cash_skipped = compute_monthly_cash_balances(
            accounts,
            cash_income,
            cash_expense,
            cash_settlement,
            cash_transfer_in,
            cash_transfer_out,
            currency,
            lookup,
        )
        skipped.update(cash_skipped)

    # Merge onto a month grid = the portfolio points' months plus the CURRENT month when it's beyond
    # the last snapshot, so cash/card movements that post-date the latest investment snapshot still
    # advance net worth (e.g. funding an account this month). Every series forward-fills at-or-before
    # each month: investments carry the latest snapshot value into the trailing current month; card
    # and cash carry their cumulative balances (including any built up before the window starts).
    investment_by_month = {(p.date.year, p.date.month): p.total_value for p in portfolio_evo.points}
    months = [(p.date.year, p.date.month) for p in portfolio_evo.points]
    if today is not None and (today.year, today.month) > months[-1]:
        months.append((today.year, today.month))
    investment_balances = forward_fill_card_balances(months, investment_by_month)
    card_balances = forward_fill_card_balances(months, card_balance_by_month)
    cash_balances = forward_fill_card_balances(months, cash_balance_by_month)
    points = [
        NetWorthEvolutionPoint(
            date=date_type(year, month, 1),
            investment_value=investment,
            cash_balance=cash,
            card_balance=card,
            net_worth=investment + cash - card,
        )
        for (year, month), investment, card, cash in zip(months, investment_balances, card_balances, cash_balances)
    ]
    return points, sorted(skipped)


# Computes the monthly net worth series (investment + cash − card per point) for the evolution chart.
async def get_evolution(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
) -> DashboardEvolutionResponse:
    # One settings read + rate lookup per request (matches get_overview): the dollar preference builds
    # the lookup, and the timezone anchors "today" so the series extends to the current month.
    rs = await settings_service.get_request_settings(session, user_id) if currency else None
    lookup = await exchange_rate_service.build_rate_lookup(session, rs.dollar_preference) if rs else None
    today = settings_service.today_for_timezone(rs.timezone) if rs else None
    points, skipped = await compute_net_worth_evolution(
        session, user_id, currency=currency, lookup=lookup, today=today, date_from=date_from, date_to=date_to
    )
    return DashboardEvolutionResponse(points=points, currency=currency, skipped_currencies=skipped)


# Computes investment allocation by category plus a liabilities segment.
async def get_composition(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
) -> DashboardCompositionResponse:
    # One user_settings read + one rate lookup per request (only when converting): the dollar
    # preference builds the lookup and the timezone anchors the card-liability conversion to today.
    rs = await settings_service.get_request_settings(session, user_id) if currency else None
    lookup = await exchange_rate_service.build_rate_lookup(session, rs.dollar_preference) if rs else None
    allocation = await metrics_service.get_allocation(
        session,
        user_id,
        currency=currency,
        lookup=lookup,
    )

    # Compute total card liability, converting each bucket's balance to display currency at TODAY's
    # rate (the composition view is a snapshot of the current state, not a historical one).
    # Includes archived cards — their outstanding balance stays a liability (UI filter only).
    rate_map = lookup.get_rate_map_at(settings_service.today_for_timezone(rs.timezone)) if lookup else None
    cards = await credit_card_repository.list_by_user(session, user_id, active_only=False)
    card_ids = [c.id for c in cards if c.id is not None]
    card_balance = ZERO
    skipped: set[str] = set()
    if card_ids:
        card_currencies = {c.id: c.currency for c in cards if c.id is not None}
        balances = await credit_card_service.get_card_balances(session, card_ids, card_currencies, user_id)
        for buckets in balances.values():
            for bucket in buckets:
                val = bucket.balance
                # `val and` mirrors get_overview: a zero-balance bucket (always emitted for a
                # card's primary currency) contributes nothing, so never flag its currency as
                # skipped just because no rate exists — that would disagree with the overview.
                if val and currency and bucket.currency != currency:
                    converted = convert_value(val, bucket.currency, currency, rate_map) if rate_map else None
                    if converted is None:
                        skipped.add(bucket.currency)
                        continue
                    val = converted
                card_balance += val

    # Cash across accounts (asset side), converted at today's rate. A net-negative cash total
    # (overdrafts) can't be a donut slice, so it's excluded from the items/base like a net-credit
    # card balance is — the overview net-worth still reflects the true (signed) cash total.
    cash_total, cash_skipped, _ = await _load_cash_total(session, user_id, currency, rate_map)
    cash_asset = cash_total if cash_total > ZERO else ZERO

    total_assets = allocation.total_value + cash_asset
    # Percentage base = sum of the item values actually returned (asset categories + cash + the
    # liabilities item when shown). Keeps legend percentages consistent with the donut's
    # value-proportional slices; net-negative aggregates are excluded so asset percentages sum to 100.
    items_total = total_assets + (card_balance if card_balance > ZERO else ZERO)

    items: list[CompositionItem] = []
    for item in allocation.items:
        pct = (item.value / items_total * 100) if items_total != ZERO else ZERO
        items.append(CompositionItem(label=item.category, value=item.value, percentage=pct))

    if cash_asset > ZERO:
        pct = (cash_asset / items_total * 100) if items_total != ZERO else ZERO
        items.append(CompositionItem(label="cash", value=cash_asset, percentage=pct))

    if card_balance > ZERO:
        pct = (card_balance / items_total * 100) if items_total != ZERO else ZERO
        items.append(CompositionItem(label="liabilities", value=card_balance, percentage=pct))

    return DashboardCompositionResponse(
        items=items,
        total_assets=total_assets,
        total_liabilities=card_balance,
        currency=currency,
        # Fail-loud: include the liability-bucket skips, any investment base currency the allocation
        # couldn't convert, and any account currency the cash total dropped.
        skipped_currencies=sorted(skipped | {s.base_currency for s in allocation.skipped_investments} | cash_skipped),
    )


# Computes the liquidity health indicator: ratio of fixed monthly commitments to normalised
# monthly income, classified against the user's threshold. Phase 3 Step 6.
async def get_liquidity(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None = None,
) -> DashboardLiquidityResponse:
    # One user_settings read for the threshold, timezone (today), and dollar preference this
    # endpoint needs, instead of three separate indexed reads.
    rs = await settings_service.get_request_settings(session, user_id)
    threshold = rs.liquidity_threshold_pct
    today = settings_service.today_for_timezone(rs.timezone)

    # Build the rate lookup once — reused for commitments + income conversions.
    lookup = await exchange_rate_service.build_rate_lookup(session, rs.dollar_preference) if currency else None
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
        if currency and cur != currency:
            converted = convert_value(val, cur, currency, rate_map_today) if rate_map_today else None
            if converted is None:
                # Fail-loud: flag the currency so the diagnostic lists affected entities and
                # the ratio excludes what it can't convert.
                unsupported_currencies.add(cur)
                continue
            val = converted
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
    monthly_income, skipped_income_currencies = compute_monthly_income(
        income_by_currency,
        days=actual_window_days,
        target_currency=currency,
        lookup=lookup,
        anchor_date=today,
    )
    # Income buckets are per-currency aggregates (no entity name) — report the code itself.
    for cur in sorted(skipped_income_currencies):
        skipped_entities.append(SkippedLiquidityEntity(type="income", name=cur, currency=cur))

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
