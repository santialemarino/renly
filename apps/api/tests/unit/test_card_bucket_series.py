# The card's bucket balances over time, and the one property that makes a second engine safe to exist.
#
# compute_card_bucket_series is a SECOND way to compute a figure compute_card_balances already
# computes. That is the shape this initiative has shipped a defect in three times — an enumerated list
# of sources kept in two places, drifting quietly — and the card side is where it bit last: for two PRs
# the headline merged a group's card charges while the monthly series read only the private table, so
# the dashboard's card figure and its chart's card line described different debts.
#
# So the load-bearing test here is not "does it add up" but "does it agree with the headline, over
# every source". Both engines are driven from ONE fixture of charges below, which is what makes the
# comparison mean anything: derive the grouped shape and the monthly shape from the same rows and the
# only way the two answers can disagree is if the code does.

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.services import credit_card_service

ZERO = Decimal(0)

USER_ID = 7
CARD_IDS = [1, 2]
# Card 2's primary currency has no activity at all, which is the one asymmetry between the two
# engines: compute_card_balances always emits a zero bucket for a card's primary currency, and a
# series has no entry for a month in which nothing moved.
CARD_CURRENCIES = {1: "ARS", 2: "BRL"}

# (card_id, date, currency, amount) per source. Deliberately includes: two sources on the SAME card in
# the SAME month (so a merge that overwrites instead of adding is caught), a foreign bucket on a peso
# card (the case this whole PR exists for), the same currency on two DIFFERENT cards (so folding
# across cards is exercised), a bucket that nets to exactly zero, and rows spread over four months so
# the cumulative fold has somewhere to go wrong.
_CHARGES: dict[str, list[tuple[int, date, str, Decimal]]] = {
    "expenses": [
        (1, date(2026, 3, 4), "ARS", Decimal("120000.00")),
        (1, date(2026, 3, 19), "USD", Decimal("54.00")),
        (1, date(2026, 5, 8), "ARS", Decimal("45000.00")),
        (2, date(2026, 4, 2), "ARS", Decimal("30000.00")),
        (2, date(2026, 4, 2), "EUR", Decimal("40.00")),
    ],
    "shared_expenses": [
        (1, date(2026, 3, 19), "ARS", Decimal("80000.00")),
        (2, date(2026, 6, 11), "USD", Decimal("15.00")),
    ],
    "settlements": [
        (1, date(2026, 4, 10), "ARS", Decimal("120000.00")),
        # Clears card 2's EUR bucket exactly, so it is present in the series as a zero and present in
        # the headline as a zero, and neither is a liability.
        (2, date(2026, 5, 30), "EUR", Decimal("40.00")),
    ],
}


# The grouped shape the headline reads: {card_id: {currency: total}}, every row, no date bound.
def _grouped(source: str, card_ids: list[int]) -> dict[int, dict[str, float]]:
    grouped: dict[int, dict[str, float]] = {}
    for card_id, _row_date, currency, amount in _CHARGES[source]:
        if card_id in card_ids:
            by_currency = grouped.setdefault(card_id, {})
            by_currency[currency] = float(Decimal(str(by_currency.get(currency, 0))) + amount)
    return grouped


# The monthly shape the series reads: the same rows as (card_id, year, month, currency, total).
def _monthly(source: str, card_ids: list[int]) -> list[tuple[int, int, int, str, float]]:
    totals: dict[tuple[int, int, int, str], Decimal] = {}
    for card_id, row_date, currency, amount in _CHARGES[source]:
        if card_id in card_ids:
            key = (card_id, row_date.year, row_date.month, currency)
            totals[key] = totals.get(key, ZERO) + amount
    return sorted((card_id, year, month, currency, float(total)) for (card_id, year, month, currency), total in totals.items())


# Stubs the three grouped sums the headline reads.
def _stub_grouped(monkeypatch) -> None:
    for repo, method, source in (
        (credit_card_service.expense_repository, "sum_by_credit_card_ids_grouped", "expenses"),
        (credit_card_service.shared_expense_repository, "sum_by_credit_card_ids_grouped", "shared_expenses"),
        (credit_card_service.card_settlement_repository, "sum_by_card_ids_grouped", "settlements"),
    ):

        def handler(_session, card_ids, *_args, _source=source, **_kwargs):
            return _grouped(_source, card_ids)

        monkeypatch.setattr(repo, method, AsyncMock(side_effect=handler))


# Stubs the three monthly sums the series reads, from the same fixture.
def _stub_monthly(monkeypatch) -> None:
    for repo, method, source in (
        (credit_card_service.expense_repository, "sum_by_credit_card_ids_monthly", "expenses"),
        (credit_card_service.shared_expense_repository, "sum_by_credit_card_ids_monthly", "shared_expenses"),
        (credit_card_service.card_settlement_repository, "sum_by_card_ids_monthly", "settlements"),
    ):

        def handler(_session, card_ids, *_args, _source=source, **_kwargs):
            return _monthly(_source, card_ids)

        monkeypatch.setattr(repo, method, AsyncMock(side_effect=handler))


# The headline's buckets flattened to the (card_id, currency) key the series uses. Nothing is summed
# on the way — the two are compared bucket for bucket, so a per-card error cannot cancel against
# another card's.
#
# Zeros are dropped from BOTH sides rather than one: a bucket at zero is not a liability — it is what
# compute_monthly_card_balances declines to convert and declines to flag — and dropping it from one side
# only would make the comparison fail on the very case both engines agree about. It is also the one
# asymmetry between them, since compute_card_balances always emits a card's primary bucket.
def _flatten(headline) -> dict[tuple[int, str], Decimal]:
    return {(card_id, bucket.currency): bucket.balance for card_id, buckets in headline.items() for bucket in buckets if bucket.balance}


def _nonzero(buckets: dict[tuple[int, str], Decimal]) -> dict[tuple[int, str], Decimal]:
    return {bucket: balance for bucket, balance in buckets.items() if balance}


class TestAgreementWithTheHeadline:
    @pytest.mark.asyncio
    async def test_the_last_entry_equals_what_the_headline_says_the_buckets_are(self, monkeypatch):
        # THE test. The series' last cumulative entry covers every row there is — the monthly sums are
        # no more date-bounded than the grouped ones — so it must be the headline, bucket for bucket and
        # card for card. One source dropped, one sign flipped, a merge that overwrites instead of
        # adding, or two cards' same-currency buckets run together, and this reddens.
        _stub_grouped(monkeypatch)
        _stub_monthly(monkeypatch)
        headline = await credit_card_service.get_card_balances(AsyncMock(), CARD_IDS, CARD_CURRENCIES, USER_ID)
        series = await credit_card_service.get_card_bucket_series(AsyncMock(), CARD_IDS, USER_ID)
        assert _nonzero(series[max(series)]) == _flatten(headline)

    @pytest.mark.asyncio
    async def test_the_agreement_breaks_when_the_series_loses_a_source(self, monkeypatch):
        # The positive control. The assertion above is only worth having if it can fail, and the way
        # it failed in production was one engine reading a source the other did not — so blind the
        # series to the shared charges and prove the comparison notices.
        _stub_grouped(monkeypatch)
        _stub_monthly(monkeypatch)
        monkeypatch.setattr(
            credit_card_service.shared_expense_repository,
            "sum_by_credit_card_ids_monthly",
            AsyncMock(return_value=[]),
        )
        headline = await credit_card_service.get_card_balances(AsyncMock(), CARD_IDS, CARD_CURRENCIES, USER_ID)
        series = await credit_card_service.get_card_bucket_series(AsyncMock(), CARD_IDS, USER_ID)
        assert _nonzero(series[max(series)]) != _flatten(headline)

    @pytest.mark.asyncio
    async def test_the_agreement_breaks_when_a_settlement_stops_reducing_the_debt(self, monkeypatch):
        # The other half of the control, and it is the SIGN rather than a second missing source: a
        # settlement added instead of subtracted still produces a plausible, monotonic-looking series,
        # so only the comparison catches it. Driven by handing the real function the settlement rows in
        # the slot that ADDS, which is the world a flipped sign would produce.
        _stub_grouped(monkeypatch)
        headline = await credit_card_service.get_card_balances(AsyncMock(), CARD_IDS, CARD_CURRENCIES, USER_ID)
        sign_flipped = credit_card_service.compute_card_bucket_series(
            _monthly("expenses", CARD_IDS) + _monthly("shared_expenses", CARD_IDS) + _monthly("settlements", CARD_IDS),
            [],
        )
        assert _nonzero(sign_flipped[max(sign_flipped)]) != _flatten(headline)


class TestComputeCardBucketSeries:
    def test_each_month_carries_the_running_bucket_not_that_months_movement(self):
        series = credit_card_service.compute_card_bucket_series(
            [(1, 2026, 1, "USD", 100.0), (1, 2026, 3, "USD", 50.0)],
            [],
        )
        assert series == {(2026, 1): {(1, "USD"): Decimal("100")}, (2026, 3): {(1, "USD"): Decimal("150")}}

    def test_rows_arriving_out_of_order_still_accumulate_chronologically(self):
        # Not hypothetical: get_card_bucket_series CONCATENATES the private and shared monthly reads,
        # and each is ordered only within itself — so a shared charge in an earlier month than the last
        # private one arrives after it. Accumulating in arrival order would put the whole of March
        # inside January's entry and leave March holding only its own charge.
        series = credit_card_service.compute_card_bucket_series(
            [(1, 2026, 3, "USD", 50.0), (1, 2026, 1, "USD", 100.0)],
            [],
        )
        assert series == {(2026, 1): {(1, "USD"): Decimal("100")}, (2026, 3): {(1, "USD"): Decimal("150")}}

    def test_a_month_with_no_movement_has_no_entry(self):
        # The caller forward-fills. Emitting a row for every month in between would make this function
        # need a grid it has no business knowing about.
        series = credit_card_service.compute_card_bucket_series([(1, 2026, 1, "USD", 100.0), (1, 2026, 3, "USD", 50.0)], [])
        assert (2026, 2) not in series

    def test_currencies_never_net_against_each_other(self):
        series = credit_card_service.compute_card_bucket_series(
            [(1, 2026, 1, "USD", 100.0), (1, 2026, 1, "ARS", 120000.0)],
            [],
        )
        assert series[(2026, 1)] == {(1, "USD"): Decimal("100"), (1, "ARS"): Decimal("120000")}

    def test_two_cards_in_one_currency_stay_two_buckets(self):
        # They are never added together here, because the conversion layer has to round them the way
        # the headline does — one bucket at a time.
        series = credit_card_service.compute_card_bucket_series(
            [(1, 2026, 1, "USD", 100.0), (2, 2026, 1, "USD", 40.0)],
            [],
        )
        assert series[(2026, 1)] == {(1, "USD"): Decimal("100"), (2, "USD"): Decimal("40")}

    def test_a_settlement_reduces_its_own_bucket_only(self):
        series = credit_card_service.compute_card_bucket_series(
            [(1, 2026, 1, "USD", 100.0), (1, 2026, 1, "ARS", 5000.0)],
            [(1, 2026, 2, "USD", 30.0)],
        )
        assert series[(2026, 2)] == {(1, "USD"): Decimal("70"), (1, "ARS"): Decimal("5000")}

    def test_a_settlement_clears_its_own_cards_bucket_and_not_the_other_cards(self):
        series = credit_card_service.compute_card_bucket_series(
            [(1, 2026, 1, "USD", 100.0), (2, 2026, 1, "USD", 100.0)],
            [(1, 2026, 2, "USD", 100.0)],
        )
        assert series[(2026, 2)] == {(1, "USD"): ZERO, (2, "USD"): Decimal("100")}

    def test_a_bucket_cleared_in_full_stays_present_as_a_zero(self):
        # It is not dropped, because "this currency is settled" and "this currency was never here" are
        # different facts and the conversion layer treats them the same way only by choice.
        series = credit_card_service.compute_card_bucket_series([(1, 2026, 1, "EUR", 40.0)], [(1, 2026, 2, "EUR", 40.0)])
        assert series[(2026, 2)] == {(1, "EUR"): ZERO}

    def test_an_overpayment_is_a_negative_bucket(self):
        series = credit_card_service.compute_card_bucket_series([(1, 2026, 1, "USD", 50.0)], [(1, 2026, 1, "USD", 100.0)])
        assert series[(2026, 1)] == {(1, "USD"): Decimal("-50")}

    def test_each_month_gets_its_own_map(self):
        # The running map is mutated in place; a month that stored a reference to it rather than a copy
        # would report every later month's balance as its own, and the series would be flat.
        series = credit_card_service.compute_card_bucket_series([(1, 2026, 1, "USD", 100.0), (1, 2026, 2, "USD", 50.0)], [])
        assert series[(2026, 1)] is not series[(2026, 2)]
        assert series[(2026, 1)] == {(1, "USD"): Decimal("100")}

    def test_empty_inputs(self):
        assert credit_card_service.compute_card_bucket_series([], []) == {}

    @pytest.mark.asyncio
    async def test_no_cards_reads_nothing_at_all(self, monkeypatch):
        # The three sums cost three queries; a user with no card should pay for none of them.
        calls = AsyncMock(return_value=[])
        monkeypatch.setattr(credit_card_service.expense_repository, "sum_by_credit_card_ids_monthly", calls)
        assert await credit_card_service.get_card_bucket_series(AsyncMock(), [], USER_ID) == {}
        calls.assert_not_awaited()
