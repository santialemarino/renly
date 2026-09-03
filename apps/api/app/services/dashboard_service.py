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
from app.repositories.group_repository import group_repository
from app.repositories.income_repository import income_repository
from app.repositories.installment_repository import installment_repository
from app.repositories.investment_repository import investment_repository
from app.repositories.payment_obligation_repository import payment_obligation_repository
from app.repositories.shared_expense_repository import shared_expense_repository
from app.repositories.subscription_repository import subscription_repository
from app.schemas.dashboard import (
    CompositionItem,
    DashboardCompositionResponse,
    DashboardEvolutionResponse,
    DashboardLiquidityResponse,
    DashboardOverviewResponse,
    NetWorthEvolutionPoint,
    SkippedLiquidityEntity,
    UndividedPotItem,
)
from app.services import (
    account_service,
    credit_card_service,
    exchange_rate_service,
    finance_metrics_service,
    metrics_service,
    pot_service,
    settings_service,
    shared_worth_service,
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


# Every month from `start` to `end` inclusive, as (year, month) pairs. The grid every series on the
# evolution chart is drawn on.
def month_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start
    while (year, month) <= end:
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


# Pure computation: each account's balance at each month end, converted and summed into one cash figure
# per month.
#
# The balances arrive already derived by account_service.compute_account_balance_series — the SAME
# eleven-source union the headline `cash_total` reads, which is the whole point of this function taking
# balances rather than movements. The monthly series used to accumulate its own six sources and had
# silently stopped agreeing with the headline about what an account balance contains: it counted no pot
# contribution, no shared expense drawn from the account, no shared income paid into it and neither leg
# of a settlement. A list of sources in two places is two lists that drift, so there is now one.
#
# Each month's balance converts at THAT month's rate, so a foreign-currency account tracks its own
# currency over time instead of staying frozen at the rate of the month its money arrived. A zero
# balance contributes nothing and never flags its currency as skipped, mirroring compute_cash_total.
# Returns (one total per month, sorted skipped currency codes).
def compute_monthly_cash_balances(
    accounts: list,
    balances_by_account: dict[int, list[Decimal]],
    month_ends: list[date_type],
    target_currency: str | None,
    lookup: RateLookup | None,
) -> tuple[list[Decimal], list[str]]:
    skipped: set[str] = set()
    totals = [ZERO for _ in month_ends]
    for index, month_end in enumerate(month_ends):
        rate_map = lookup.get_rate_map_at(month_end) if lookup else None
        for account in accounts:
            series = balances_by_account.get(account.id)
            if series is None:
                continue
            val = series[index]
            if val and target_currency and account.currency != target_currency:
                converted = convert_value(val, account.currency, target_currency, rate_map) if rate_map else None
                if converted is None:
                    skipped.add(account.currency)
                    continue
                val = converted
            totals[index] += val
    return totals, sorted(skipped)


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
# account or card, whose balance stays in net worth. The account side rides the list _load_cash_total
# already fetched rather than calling `account_repository.exists_by_user` (which the onboarding
# checklist does use): the rows are in hand here, and both answers must stay archived-inclusive to
# agree. The other two are indexed LIMIT 1 reads reached only when the account side is False — so a
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
    # Loaded up front because the finance half needs the caller's group seats to union each member's
    # own share into their spending and earnings, and the shared half of net worth needs the same
    # seats plus the pots — one read set for the whole request rather than two that could disagree
    # about which seats are active.
    context = await shared_worth_service.load_context(session, user_id)
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
        member_ids=[seat.id for seat in context.seats],
        today=today,
        date_from=date_from,
        date_to=date_to,
    )

    # Cash across all accounts, converted to the display currency at today's rate (fail-loud).
    rate_map_today = lookup.get_rate_map_at(today) if (lookup and today) else None
    private_cash, cash_skipped, has_accounts = await _load_cash_total(session, user_id, currency, rate_map_today)

    # The shared half: this member's share of every pot they can see, plus what their groups owe them
    # and what they owe back. `as_of_date` falls back to the server's date on the one path that reads no
    # settings at all (no display currency requested), which is the same fallback the pot pages use.
    shared = await shared_worth_service.get_shared_worth(
        session,
        user_id,
        context,
        currency=currency,
        lookup=lookup,
        as_of_date=today or date_type.today(),
    )

    # Every asset headline counts the same universe — your own holdings PLUS your share of the shared
    # ones — so the composition donut's slices and the cards above it cannot describe different money.
    # The gain figure below stays private, because a pot share has no "invested" of its own that is not
    # the pot's ledger, and the card copy says so.
    shared_cash = shared.buckets.get(pot_service.CASH_BUCKET, ZERO)
    cash_total = private_cash + shared_cash
    investment_total = portfolio.total_value + (shared.pot_value - shared_cash)
    # "Yours" is the private side alone; the card liability sits wholly here because a card's whole
    # charge is its owner's debt whoever consumed what it bought — what the group owes them back for it
    # is the receivable on the shared side, and the two net out exactly as they should.
    private_net_worth = portfolio.total_value + private_cash - finance.credit_card_balance
    net_worth = private_net_worth + shared.total
    has_holdings = shared.has_shared or await _has_holdings(session, user_id, has_accounts=has_accounts)
    # Named only when there is something to name, so the common case pays no read at all.
    group_names = (
        {group.id: group.name for group in await group_repository.get_by_ids(session, sorted({p.group_id for p in shared.undivided_pots}))}
        if shared.undivided_pots
        else {}
    )

    # Net worth month-over-month: the latest vs prior month of the SAME monthly net-worth series the
    # evolution chart uses (investment + cash − card per month), so the delta reflects cash and card
    # movements, not investments alone — e.g. funding a new account this month now shows up. Full
    # history (unwindowed): net worth is a point-in-time snapshot, unlike the period-scoped income
    # /expense totals. (investment_month_change below stays investment-only for the Investment card.)
    nw_points, _ = await compute_net_worth_evolution(session, user_id, currency=currency, lookup=lookup, today=today, context=context)
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
        private_net_worth=private_net_worth,
        shared_net_worth=shared.total,
        shared_pot_value=shared.pot_value,
        shared_receivable=shared.receivable,
        shared_payable=shared.payable,
        has_shared=shared.has_shared,
        undivided_pots=[
            UndividedPotItem(pot_id=pot.pot_id, name=pot.name, group_id=pot.group_id, group_name=group_names.get(pot.group_id))
            for pot in shared.undivided_pots
        ],
        cash_total=cash_total,
        net_worth_change=net_worth_change,
        net_worth_change_pct=net_worth_change_pct,
        investment_total=investment_total,
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
        skipped_currencies=sorted(
            set(finance.skipped_currencies) | {s.base_currency for s in portfolio.skipped_investments} | cash_skipped | shared.skipped_currencies
        ),
    )


# Builds the monthly net-worth series — investment value, cash, card liability and the caller's share
# of everything shared, per month — used by both the evolution chart and the overview's
# month-over-month delta. Cash and card include archived rows (their balances stay in net worth;
# archive is a UI filter). Returns (points, sorted skipped-currency codes).
#
# THE GRID is the union of every term's own history rather than the investment side's alone, which is
# what it used to be. A user holding only cash got no chart at all, and a user whose only holdings are
# co-owned would have got the same — the months existed for one term and the chart asked a different
# one. It now runs from the earliest month ANY term begins to the current month, clipped to the
# requested window at both ends. Clipping the end is also what stops a window that closed in June from
# gaining a September point, which appending "today" unconditionally used to do.
async def compute_net_worth_evolution(
    session: AsyncSession,
    user_id: int,
    *,
    currency: str | None,
    lookup: RateLookup | None,
    today: date_type | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    context: shared_worth_service.SharedContext | None = None,
) -> tuple[list[NetWorthEvolutionPoint], list[str]]:
    context = context if context is not None else await shared_worth_service.load_context(session, user_id)
    portfolio_evo = await metrics_service.get_portfolio_evolution(
        session,
        user_id,
        currency=currency,
        lookup=lookup,
        start_date=date_from,
        end_date=date_to,
    )
    skipped: set[str] = set()

    # Card and cash inputs, loaded before the grid because their earliest activity helps define it.
    # Both include archived rows — their history and any outstanding balance remain part of net worth.
    cards = await credit_card_repository.list_by_user(session, user_id, active_only=False)
    card_ids = [c.id for c in cards if c.id is not None]
    card_currencies = {c.id: c.currency for c in cards if c.id is not None}
    card_balance_by_month: dict[tuple[int, int], Decimal] = {}
    if card_ids:
        expense_monthly = await expense_repository.sum_by_credit_card_ids_monthly(session, card_ids, user_id)
        # A group's shared charge raises the same liability a private one does, and get_card_balances
        # already merges the two for the CURRENT figure — so the monthly series merges them too, or the
        # headline card balance and this line describe different sets of charges.
        expense_monthly = expense_monthly + await shared_expense_repository.sum_by_credit_card_ids_monthly(session, card_ids)
        settlement_monthly = await card_settlement_repository.sum_by_card_ids_monthly(session, card_ids)
        card_balance_by_month, card_skipped = compute_monthly_card_balances(
            expense_monthly,
            settlement_monthly,
            card_currencies,
            currency,
            lookup,
        )
        skipped.update(card_skipped)

    accounts = await account_repository.list_by_user(session, user_id, active_only=False)

    months = _evolution_grid(
        portfolio_months=[(p.date.year, p.date.month) for p in portfolio_evo.points],
        card_months=sorted(card_balance_by_month),
        accounts=accounts,
        shared_start=shared_worth_service.earliest_month(context),
        today=today,
        date_from=date_from,
        date_to=date_to,
    )
    if not months:
        return [], []
    month_ends = [_month_end(year, month) for year, month in months]

    # Cash, from the same eleven-source balance engine the headline reads — see
    # compute_monthly_cash_balances for why it is no longer a second list of sources.
    cash_balances = [ZERO for _ in months]
    if accounts:
        balances_by_account = await account_service.compute_account_balance_series(session, accounts, dates=month_ends)
        cash_balances, cash_skipped = compute_monthly_cash_balances(accounts, balances_by_account, month_ends, currency, lookup)
        skipped.update(cash_skipped)

    shared_values, shared_skipped = await shared_worth_service.get_shared_series(
        session,
        user_id,
        context,
        months=months,
        month_ends=month_ends,
        currency=currency,
        lookup=lookup,
    )
    skipped.update(shared_skipped)

    # Investments and cards forward-fill onto the grid: each carries its latest known figure into a
    # month that has none, and reads zero before its first. Cash and the shared side are already one
    # figure per month by construction, because both are derived AT each date rather than accumulated
    # from the movements that happened in it.
    investment_by_month = {(p.date.year, p.date.month): p.total_value for p in portfolio_evo.points}
    investment_balances = forward_fill_card_balances(months, investment_by_month)
    card_balances = forward_fill_card_balances(months, card_balance_by_month)
    points = [
        NetWorthEvolutionPoint(
            date=date_type(year, month, 1),
            investment_value=investment,
            cash_balance=cash,
            card_balance=card,
            shared_value=shared,
            private_net_worth=investment + cash - card,
            net_worth=investment + cash - card + shared,
        )
        for (year, month), investment, card, cash, shared in zip(months, investment_balances, card_balances, cash_balances, shared_values)
    ]
    return points, sorted(skipped)


# The months the chart is drawn on: from the earliest month any term begins to the current month,
# clipped to the requested window.
#
# `today` is null only when no display currency was requested, which is the one path that skips the
# settings read the user's timezone comes from; the grid then ends at the last month a term has, which
# is what it did before this function existed.
def _evolution_grid(
    *,
    portfolio_months: list[tuple[int, int]],
    card_months: list[tuple[int, int]],
    accounts: list,
    shared_start: tuple[int, int] | None,
    today: date_type | None,
    date_from: date_type | None,
    date_to: date_type | None,
) -> list[tuple[int, int]]:
    starts = [months[0] for months in (portfolio_months, card_months) if months]
    starts += [(a.opening_date.year, a.opening_date.month) for a in accounts]
    if shared_start is not None:
        starts.append(shared_start)
    if not starts:
        return []
    ends = [months[-1] for months in (portfolio_months, card_months) if months]
    if today is not None:
        ends.append((today.year, today.month))
    start = min(starts)
    end = max(ends) if ends else start
    if date_from is not None:
        start = max(start, (date_from.year, date_from.month))
    if date_to is not None:
        end = min(end, (date_to.year, date_to.month))
    return month_range(start, end) if start <= end else []


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
    private_cash, cash_skipped, _ = await _load_cash_total(session, user_id, currency, rate_map)

    # The shared half enters the SAME segments a private holding does: your share of a co-owned CEDEAR
    # adds to `cedears`, your share of a jointly-held bank account to `cash`. The donut answers "what is
    # my money in", and scope is not an asset class — the Yours/Shared split is the headline's job. It
    # is also what keeps these slices agreeing with the cards above them, which count the same universe.
    context = await shared_worth_service.load_context(session, user_id)
    shared = await shared_worth_service.get_shared_worth(
        session,
        user_id,
        context,
        currency=currency,
        lookup=lookup,
        as_of_date=settings_service.today_for_timezone(rs.timezone) if rs else date_type.today(),
    )
    by_label: dict[str, Decimal] = {item.category: item.value for item in allocation.items}
    for label, value in shared.buckets.items():
        by_label[label] = by_label.get(label, ZERO) + value
    cash_total = private_cash + by_label.pop(pot_service.CASH_BUCKET, ZERO)
    cash_asset = cash_total if cash_total > ZERO else ZERO

    # A receivable is an asset on its own line and a payable a liability on its own (D3) — never blended
    # into cash, which is what "its own line" means. So one becomes a slice and the other joins the
    # liabilities segment the card balance already forms.
    card_balance += shared.payable
    receivable = shared.receivable

    total_assets = sum(by_label.values(), ZERO) + cash_asset + receivable
    # Percentage base = sum of the item values actually returned (asset categories + cash + the
    # liabilities item when shown). Keeps legend percentages consistent with the donut's
    # value-proportional slices; net-negative aggregates are excluded so asset percentages sum to 100.
    items_total = total_assets + (card_balance if card_balance > ZERO else ZERO)

    def _pct(value: Decimal) -> Decimal:
        return (value / items_total * 100) if items_total != ZERO else ZERO

    # Ordered by the allocation's own categories first so a private-only user's donut is unchanged, then
    # any category that exists ONLY because something shared sits in it.
    labels = [item.category for item in allocation.items]
    labels += sorted(label for label in by_label if label not in set(labels))
    items = [
        CompositionItem(label=label, value=by_label[label], percentage=_pct(by_label[label])) for label in labels if by_label.get(label, ZERO) != ZERO
    ]

    if cash_asset > ZERO:
        items.append(CompositionItem(label="cash", value=cash_asset, percentage=_pct(cash_asset)))

    if receivable > ZERO:
        items.append(CompositionItem(label="receivable", value=receivable, percentage=_pct(receivable)))

    if card_balance > ZERO:
        items.append(CompositionItem(label="liabilities", value=card_balance, percentage=_pct(card_balance)))

    return DashboardCompositionResponse(
        items=items,
        total_assets=total_assets,
        total_liabilities=card_balance,
        currency=currency,
        # Fail-loud: include the liability-bucket skips, any investment base currency the allocation
        # couldn't convert, any account currency the cash total dropped, and any pot or balance bucket
        # the shared side could not restate.
        skipped_currencies=sorted(skipped | {s.base_currency for s in allocation.skipped_investments} | cash_skipped | shared.skipped_currencies),
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
    # doesn't make a baseline. Both reads union the caller's SHARE of their groups' income, because
    # their part of the rent really is income they can meet a commitment out of — the same rule the
    # /income list and the finance dashboard apply.
    member_ids = await group_repository.list_active_member_ids(session, user_id)
    first_income_date = await income_repository.get_first_income_date(session, user_id, member_ids)
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
        member_ids,
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
