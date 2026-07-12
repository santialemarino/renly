from datetime import date as date_type
from decimal import Decimal

from app.models.credit_card import CreditCard
from app.models.installment import Installment
from app.models.payment_obligation import PaymentObligation
from app.models.subscription import Subscription
from app.utils.liquidity import (
    STATE_AT_RISK,
    STATE_CAUTION,
    STATE_HEALTHY,
    STATE_UNKNOWN,
    classify_liquidity,
    compute_fixed_monthly_commitments,
    compute_monthly_income,
)

# Rate map: 1 USD = 1200 ARS. Used by the multi-currency income test.
RATE_MAP = {
    "USD": Decimal("1"),
    "ARS": Decimal("1200"),
}


# Stub RateLookup that returns the same rate map for any date — same pattern as test_dashboard.
class _FixedLookup:
    def __init__(self, rate_map: dict[str, Decimal] | None) -> None:
        self._rate_map = rate_map

    def get_rate_map_at(self, _as_of_date: date_type) -> dict[str, Decimal] | None:
        return self._rate_map


FIXED_LOOKUP = _FixedLookup(RATE_MAP)


def _subscription(*, amount: Decimal, currency: str, billing_cycle: str) -> Subscription:
    # Minimal in-memory Subscription. The helper only reads amount / currency / billing_cycle.
    return Subscription(
        id=1,
        user_id=1,
        name="Test sub",
        amount=amount,
        currency=currency,
        billing_cycle=billing_cycle,
        next_billing_date=date_type(2026, 6, 1),
        anchor_day=1,
        is_active=True,
    )


def _installment(
    *,
    installment_amount: Decimal,
    currency: str,
    current_installment: int,
    installments_count: int,
) -> Installment:
    # Minimal in-memory Installment. The helper reads installment_amount, currency,
    # current_installment, installments_count.
    return Installment(
        id=1,
        user_id=1,
        name="Test installment",
        total_amount=installment_amount * Decimal(installments_count),
        installment_amount=installment_amount,
        currency=currency,
        installments_count=installments_count,
        start_date=date_type(2026, 1, 1),
        current_installment=current_installment,
        is_active=True,
    )


def _credit_card(*, currency: str, monthly_payment: Decimal | None) -> CreditCard:
    # Minimal in-memory CreditCard. The helper only reads currency + monthly_payment.
    return CreditCard(
        id=1,
        user_id=1,
        name="Test card",
        closing_day=15,
        due_day=25,
        currency=currency,
        is_active=True,
        monthly_payment=monthly_payment,
    )


def _obligation(*, amount: Decimal, currency: str, recurrence: str | None) -> PaymentObligation:
    # Minimal in-memory PaymentObligation. The helper reads amount / currency / recurrence.
    return PaymentObligation(
        id=1,
        user_id=1,
        name="Test obligation",
        amount=amount,
        currency=currency,
        next_due_date=date_type(2026, 6, 1),
        anchor_day=1,
        recurrence=recurrence,
        is_active=True,
    )


# --- compute_fixed_monthly_commitments ---


class TestComputeFixedMonthlyCommitments:
    def test_empty_inputs_return_empty_dict(self):
        result = compute_fixed_monthly_commitments([], [], [], [])
        assert result == {}

    def test_monthly_subscription_contributes_amount_once(self):
        sub = _subscription(amount=Decimal("10"), currency="USD", billing_cycle="monthly")
        result = compute_fixed_monthly_commitments([sub], [], [], [])
        assert result == {"USD": Decimal("10")}

    def test_annual_subscription_divides_by_twelve(self):
        # $120/year = $10/month.
        sub = _subscription(amount=Decimal("120"), currency="USD", billing_cycle="annual")
        result = compute_fixed_monthly_commitments([sub], [], [], [])
        assert result["USD"] == Decimal("120") * (Decimal("1") / Decimal("12"))

    def test_biweekly_subscription_multiplies_by_twentysix_over_twelve(self):
        # Biweekly = 26 cycles per year / 12 months.
        sub = _subscription(amount=Decimal("12"), currency="USD", billing_cycle="biweekly")
        result = compute_fixed_monthly_commitments([sub], [], [], [])
        assert result["USD"] == Decimal("12") * (Decimal("26") / Decimal("12"))

    def test_unknown_billing_cycle_contributes_zero(self):
        # Defensive default — corrupt billing_cycle string is silently skipped.
        sub = _subscription(amount=Decimal("10"), currency="USD", billing_cycle="fortnightly")
        result = compute_fixed_monthly_commitments([sub], [], [], [])
        assert result == {}

    def test_active_installment_contributes_one_cuota_amount(self):
        inst = _installment(
            installment_amount=Decimal("500"),
            currency="USD",
            current_installment=4,
            installments_count=12,
        )
        result = compute_fixed_monthly_commitments([], [inst], [], [])
        assert result == {"USD": Decimal("500")}

    def test_fully_paid_installment_is_excluded(self):
        # Defensive — should already be is_active=False after Step 3 scheduler completes
        # the plan, but the helper guards against current_installment > installments_count.
        inst = _installment(
            installment_amount=Decimal("500"),
            currency="USD",
            current_installment=13,
            installments_count=12,
        )
        result = compute_fixed_monthly_commitments([], [inst], [], [])
        assert result == {}

    def test_monthly_obligation_contributes_full_amount(self):
        obl = _obligation(amount=Decimal("200"), currency="ARS", recurrence="monthly")
        result = compute_fixed_monthly_commitments([], [], [obl], [])
        assert result == {"ARS": Decimal("200")}

    def test_bimonthly_obligation_divides_by_two(self):
        # ABL bimonthly $200 -> $100/month equivalent.
        obl = _obligation(amount=Decimal("200"), currency="ARS", recurrence="bimonthly")
        result = compute_fixed_monthly_commitments([], [], [obl], [])
        assert result == {"ARS": Decimal("100")}

    def test_quarterly_obligation_divides_by_three(self):
        obl = _obligation(amount=Decimal("300"), currency="ARS", recurrence="quarterly")
        result = compute_fixed_monthly_commitments([], [], [obl], [])
        assert result == {"ARS": Decimal("100")}

    def test_annual_obligation_divides_by_twelve(self):
        # Patente $1200/year -> $100/month.
        obl = _obligation(amount=Decimal("1200"), currency="ARS", recurrence="annual")
        result = compute_fixed_monthly_commitments([], [], [obl], [])
        assert result == {"ARS": Decimal("100")}

    def test_one_off_obligation_is_excluded(self):
        # recurrence=None means single future event, not a fixed monthly commitment.
        obl = _obligation(amount=Decimal("500"), currency="ARS", recurrence=None)
        result = compute_fixed_monthly_commitments([], [], [obl], [])
        assert result == {}

    def test_mixed_currencies_return_separate_entries(self):
        # No cross-currency conversion at this layer — service does the pivot.
        sub_usd = _subscription(amount=Decimal("10"), currency="USD", billing_cycle="monthly")
        sub_ars = _subscription(amount=Decimal("12000"), currency="ARS", billing_cycle="monthly")
        result = compute_fixed_monthly_commitments([sub_usd, sub_ars], [], [], [])
        assert result == {"USD": Decimal("10"), "ARS": Decimal("12000")}

    def test_all_sources_accumulate_per_currency(self):
        # Subscriptions + active installment + monthly obligation + card revolving payment,
        # all in USD: sum directly.
        sub = _subscription(amount=Decimal("10"), currency="USD", billing_cycle="monthly")
        inst = _installment(
            installment_amount=Decimal("500"),
            currency="USD",
            current_installment=4,
            installments_count=12,
        )
        obl = _obligation(amount=Decimal("100"), currency="USD", recurrence="monthly")
        card = _credit_card(currency="USD", monthly_payment=Decimal("200"))
        result = compute_fixed_monthly_commitments([sub], [inst], [obl], [card])
        assert result == {"USD": Decimal("810")}

    def test_credit_card_with_monthly_payment_contributes(self):
        # Revolving-debt user states a monthly payment — counts as a fixed commitment.
        card = _credit_card(currency="USD", monthly_payment=Decimal("250"))
        result = compute_fixed_monthly_commitments([], [], [], [card])
        assert result == {"USD": Decimal("250")}

    def test_credit_card_without_monthly_payment_is_excluded(self):
        # Pay-in-full user (monthly_payment is null) doesn't add anything to commitments.
        card = _credit_card(currency="USD", monthly_payment=None)
        result = compute_fixed_monthly_commitments([], [], [], [card])
        assert result == {}

    def test_mixed_currency_cards_keep_separate_entries(self):
        # Two cards with different currencies sum independently per currency.
        card_usd = _credit_card(currency="USD", monthly_payment=Decimal("100"))
        card_ars = _credit_card(currency="ARS", monthly_payment=Decimal("30000"))
        result = compute_fixed_monthly_commitments([], [], [], [card_usd, card_ars])
        assert result == {"USD": Decimal("100"), "ARS": Decimal("30000")}


# --- compute_monthly_income ---


ANCHOR = date_type(2026, 5, 15)


class TestComputeMonthlyIncome:
    def test_empty_dict_returns_zero(self):
        total, skipped = compute_monthly_income(
            {},
            days=30,
            target_currency=None,
            lookup=None,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("0")
        assert skipped == set()

    def test_zero_days_returns_zero_defensively(self):
        # Guard against pathological inputs — division by zero protection.
        total, skipped = compute_monthly_income(
            {"USD": Decimal("300")},
            days=0,
            target_currency=None,
            lookup=None,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("0")
        assert skipped == set()

    def test_thirty_day_window_is_identity(self):
        # 30 days of $300 income, 30-day window: monthly equivalent = $300.
        total, skipped = compute_monthly_income(
            {"USD": Decimal("300")},
            days=30,
            target_currency=None,
            lookup=None,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("300")
        assert skipped == set()

    def test_sixty_day_window_halves(self):
        # 60 days of $600 income, normalised to 30 days = $300/month.
        total, skipped = compute_monthly_income(
            {"USD": Decimal("600")},
            days=60,
            target_currency=None,
            lookup=None,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("300")
        assert skipped == set()

    def test_seventeen_day_window_scales_up(self):
        # Early app life: 17 days of $170 income, normalised to 30 days = $300/month.
        total, skipped = compute_monthly_income(
            {"USD": Decimal("170")},
            days=17,
            target_currency=None,
            lookup=None,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("170") * Decimal("30") / Decimal("17")
        assert skipped == set()

    def test_ninety_day_window_thirds(self):
        # 90-day window of $900 -> $300/month (normalised).
        total, skipped = compute_monthly_income(
            {"USD": Decimal("900")},
            days=90,
            target_currency=None,
            lookup=None,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("300")
        assert skipped == set()

    def test_multi_currency_converted_to_target(self):
        # 1 USD = 1200 ARS. $100 USD + 120000 ARS over 30 days = $100 + $100 = $200/month.
        total, skipped = compute_monthly_income(
            {"USD": Decimal("100"), "ARS": Decimal("120000")},
            days=30,
            target_currency="USD",
            lookup=FIXED_LOOKUP,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("200")
        assert skipped == set()

    def test_no_target_currency_skips_conversion(self):
        # target_currency=None means no conversion — totals sum raw across currencies.
        total, skipped = compute_monthly_income(
            {"USD": Decimal("100"), "ARS": Decimal("200")},
            days=30,
            target_currency=None,
            lookup=FIXED_LOOKUP,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("300")
        assert skipped == set()

    def test_missing_rate_bucket_is_skipped_and_reported(self):
        # FIXED_LOOKUP only maps USD/ARS — the CLP bucket has no rate, so it's excluded and reported.
        total, skipped = compute_monthly_income(
            {"USD": Decimal("300"), "CLP": Decimal("900000")},
            days=30,
            target_currency="USD",
            lookup=FIXED_LOOKUP,
            anchor_date=ANCHOR,
        )
        assert total == Decimal("300")
        assert skipped == {"CLP"}


# --- classify_liquidity ---


class TestClassifyLiquidity:
    def test_none_ratio_returns_unknown(self):
        # Zero-income state: ratio is undefined.
        assert classify_liquidity(None, 40) == STATE_UNKNOWN

    def test_below_threshold_returns_healthy(self):
        # 30% ratio, 40% threshold -> healthy.
        assert classify_liquidity(Decimal("0.30"), 40) == STATE_HEALTHY

    def test_exactly_at_threshold_returns_caution(self):
        # At-boundary: ratio == threshold -> caution (inclusive lower bound).
        assert classify_liquidity(Decimal("0.40"), 40) == STATE_CAUTION

    def test_inside_caution_band_returns_caution(self):
        # 45% with 40% threshold -> 5pp into the 10pp caution band -> caution.
        assert classify_liquidity(Decimal("0.45"), 40) == STATE_CAUTION

    def test_just_below_caution_ceiling_returns_caution(self):
        # 49.99% with 40% threshold + 10pp band = ceiling at 50% (exclusive) -> caution.
        assert classify_liquidity(Decimal("0.4999"), 40) == STATE_CAUTION

    def test_at_caution_ceiling_returns_at_risk(self):
        # 50% with 40% threshold -> caution ceiling reached -> at_risk.
        assert classify_liquidity(Decimal("0.50"), 40) == STATE_AT_RISK

    def test_above_caution_ceiling_returns_at_risk(self):
        # 70% with 40% threshold -> well above ceiling -> at_risk.
        assert classify_liquidity(Decimal("0.70"), 40) == STATE_AT_RISK
