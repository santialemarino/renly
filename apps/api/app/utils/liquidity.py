# Pure helpers for the liquidity alert (fixed monthly commitments / monthly income ratio).
# Phase 3 Step 6. The service layer (dashboard_service.get_liquidity) orchestrates these
# pure functions with the per-request RateLookup and the user's stored threshold.

from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from app.models.credit_card import CreditCard
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.utils.dates import OBLIGATION_MONTH_STEP
from app.utils.metrics import RateLookup, convert_value

ZERO = Decimal("0")

# Threshold default. JSONB key 'liquidity_threshold_pct' overrides at runtime when set.
# Mirrors the frontend default in apps/web/lib/constants/liquidity.ts.
DEFAULT_LIQUIDITY_THRESHOLD_PCT = 40

# Percentage-points above the user's threshold where state flips from caution to at_risk.
LIQUIDITY_CAUTION_BAND_PCT = 10

# Target window for the income rolling average. Smooths typical pay cycles so the alert
# state doesn't flicker day-to-day.
LIQUIDITY_INCOME_WINDOW_DAYS = 90

# Below this many days of recorded income history the card renders "unknown" — one data
# point isn't a trend and a single paycheck would dominate the ratio.
LIQUIDITY_INCOME_MIN_HISTORY_DAYS = 7

# Subscription billing cycle -> monthly-equivalent multiplier. Cycles not in the map
# (corrupt rows) contribute zero — defensive default.
MONTHLY_FACTOR: dict[str, Decimal] = {
    "monthly": Decimal("1"),
    "biweekly": Decimal("26") / Decimal("12"),
    "weekly": Decimal("52") / Decimal("12"),
    "quarterly": Decimal("1") / Decimal("3"),
    "annual": Decimal("1") / Decimal("12"),
}

# Liquidity classification states. Frontend maps these 1:1 to colours.
STATE_HEALTHY = "healthy"
STATE_CAUTION = "caution"
STATE_AT_RISK = "at_risk"
STATE_UNKNOWN = "unknown"


# Sums fixed monthly commitments across active subscriptions, installments, recurring
# obligations, and credit cards with a stated monthly_payment (for revolving-debt users).
# Amortised to a monthly base. Returns per-currency totals; the service layer pivots via
# display currency.
def compute_fixed_monthly_commitments(
    subscriptions: list[Subscription],
    installments: list[Installment],
    obligations: list[PaymentObligation],
    credit_cards: list[CreditCard],
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)

    for sub in subscriptions:
        factor = MONTHLY_FACTOR.get(sub.billing_cycle)
        if factor is None:
            continue
        totals[sub.currency] += sub.amount * factor

    for inst in installments:
        # Fully-paid plans (current_installment past the final installment) aren't commitments.
        if inst.current_installment > inst.installments_count:
            continue
        totals[inst.currency] += inst.installment_amount

    for obl in obligations:
        # One-off obligations (recurrence is null) aren't fixed monthly commitments —
        # they're single future events and don't belong in the recurring-cost picture.
        months_step = OBLIGATION_MONTH_STEP.get(obl.recurrence or "")
        if months_step is None:
            continue
        totals[obl.currency] += obl.amount / Decimal(months_step)

    for card in credit_cards:
        # Only revolving-debt users (those who fill monthly_payment) contribute here.
        # Pay-in-full users leave monthly_payment NULL — their card-funded subs/installments
        # are already in the count via their own rows.
        if card.monthly_payment is None:
            continue
        totals[card.currency] += card.monthly_payment

    return dict(totals)


# Normalises a multi-currency income window to a monthly-equivalent in target currency.
# `days` is the actual width of the window; scales by 30/days so a 17-day window still
# returns a monthly figure. Conversion anchors on anchor_date (typically window end).
def compute_monthly_income(
    income_by_currency: dict[str, float],
    *,
    days: int,
    target_currency: str | None,
    lookup: RateLookup | None,
    anchor_date: date_type,
) -> Decimal:
    if days <= 0:
        return ZERO

    rate_map = lookup.get_rate_map_at(anchor_date) if (target_currency and lookup) else None

    total = ZERO
    for currency, amount in income_by_currency.items():
        val = Decimal(str(amount))
        if target_currency and rate_map and currency != target_currency:
            val = convert_value(val, currency, target_currency, rate_map)
        total += val

    return total * Decimal(30) / Decimal(days)


# Classifies a ratio against the user's threshold and the +caution-band ceiling.
# `ratio` is the raw decimal (0.32 = 32%); `threshold_pct` is the integer percent (40 = 40%).
def classify_liquidity(ratio: Decimal | None, threshold_pct: int) -> str:
    if ratio is None:
        return STATE_UNKNOWN
    ratio_pct = ratio * Decimal(100)
    threshold = Decimal(threshold_pct)
    caution_ceiling = threshold + Decimal(LIQUIDITY_CAUTION_BAND_PCT)
    if ratio_pct < threshold:
        return STATE_HEALTHY
    if ratio_pct < caution_ceiling:
        return STATE_CAUTION
    return STATE_AT_RISK
