import ast
import importlib
import pathlib
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.domain.money import MONEY_PLACES, quantize

# Money rounds HALF-UP everywhere, and nothing is allowed to inherit Decimal's default quietly.
#
# `Decimal.quantize()` with no `rounding` argument takes ROUND_HALF_EVEN — banker's rounding — which
# sends half of all exactly-half values the opposite way from `domain.money.quantize`. That is not a
# rounding preference: it is two different products' answers to "what does 2.345 cost", living in one
# codebase. `convert_value` sat behind every `converted_*` field the API returns and did exactly that.
#
# ▸ DERIVED, not listed. A test naming `convert_value` would have caught the one instance somebody
# already knew about. This walks `app/` for every `.quantize(` call and fails any that omits the mode,
# so the next one cannot arrive silently — the same reframe the ownership predicates and the input
# caps got, for the same reason: the hand-written list is what let the first one through.
#
# It checks the CALL rather than the result because there is nothing to observe otherwise: a function
# that rounds the wrong way is only visibly wrong on inputs that land exactly on a half, which most
# tests never construct.

#
# ▸ The builtin `round(x, n)` is the same trap by another name: on a Decimal it is ROUND_HALF_EVEN too,
# and on a float it rounds the binary approximation. The auto-snapshot job stored every position as
# `round(quantity * price, 2)` for exactly that reason. The line it is drawn on is the SCALE, derived
# from `MONEY_PLACES` rather than written as `2`: a two-argument `round()` to the money scale is a
# second money rule and fails, and so does one whose `ndigits` is not a literal, since nothing can
# prove it is not the money scale. A literal at any OTHER scale passes — the six-place `round()` on a
# provider's quoted price and on the IRR solver's rate are not money figures and have no half-up rule
# to disagree with.

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

# The number of decimal places a money figure carries, read off the rule rather than restated.
MONEY_DIGITS = -MONEY_PLACES.as_tuple().exponent


# A stand-in for the SQLAlchemy result a grouped sum iterates.
def _rows(rows):
    result = Mock()
    result.all.return_value = rows
    return result


# Every `.quantize(...)` call in the app, as (file:line, names_the_mode).
def _quantize_calls() -> list[tuple[str, bool]]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "quantize"):
                continue
            names_mode = any(kw.arg == "rounding" for kw in node.keywords) or len(node.args) > 1
            found.append((f"{path.relative_to(APP.parent)}:{node.lineno}", names_mode))
    return found


# Every two-argument builtin `round(...)` call in the app, as (file:line, ndigits) where ndigits is the
# literal int, or None when the argument is an expression.
def _round_calls() -> list[tuple[str, int | None]]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "round"):
                continue
            ndigits = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == "ndigits"), None)
            if ndigits is None:
                continue
            literal = ndigits.value if isinstance(ndigits, ast.Constant) and isinstance(ndigits.value, int) else None
            found.append((f"{path.relative_to(APP.parent)}:{node.lineno}", literal))
    return found


class TestNothingInheritsBankersRounding:
    def test_every_quantize_call_names_its_rounding_mode(self):
        silent = sorted(where for where, names_mode in _quantize_calls() if not names_mode)
        assert silent == [], (
            "these calls take Decimal's ROUND_HALF_EVEN default, which disagrees with "
            f"domain.money.quantize on every exactly-half value — pass `rounding=` or use it: {silent}"
        )

    def test_the_walk_actually_finds_the_calls(self):
        # Anti-vacuity: an empty list satisfies the assertion above perfectly, and a walk that stopped
        # matching would produce exactly that. `domain/money.py` is the one call that is certain to
        # exist, since it IS the rule.
        calls = _quantize_calls()
        assert len(calls) >= 3, f"the walk found only {len(calls)} quantize calls — it has stopped matching"
        assert any(where.startswith("app/domain/money.py") for where, _ in calls)

    def test_the_two_modes_really_do_disagree(self):
        # The premise, asserted rather than assumed. If these ever agreed, the guard above would be
        # policing nothing and should be deleted rather than left looking useful.
        value = Decimal("2.345")
        assert value.quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN) == Decimal("2.34")
        assert value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP) == Decimal("2.35")
        assert quantize(value, MONEY_PLACES) == Decimal("2.35")

    def test_no_builtin_round_to_the_money_scale(self):
        offending = sorted(where for where, ndigits in _round_calls() if ndigits is None or ndigits == MONEY_DIGITS)
        assert offending == [], (
            f"these round() to {MONEY_DIGITS} places (or to a scale nothing can prove is not it), which is banker's "
            f"rounding on a Decimal — use domain.money.quantize(value, MONEY_PLACES): {offending}"
        )

    def test_the_round_walk_actually_finds_the_calls(self):
        # Anti-vacuity, for the same reason as the quantize walk: the six-place price and IRR roundings
        # are certain to exist, and a walk that stopped matching would find none of them.
        calls = _round_calls()
        assert len(calls) >= 3, f"the walk found only {len(calls)} round() calls — it has stopped matching"
        assert any(where.startswith("app/utils/metrics.py") for where, _ in calls)

    def test_builtin_round_really_is_bankers_rounding(self):
        # The premise of the round() guard. Python's round() on a Decimal delegates to
        # Decimal.__round__, which uses the context's rounding — ROUND_HALF_EVEN by default.
        assert MONEY_DIGITS == 2
        assert round(Decimal("2.345"), MONEY_DIGITS) == Decimal("2.34")
        assert quantize(Decimal("2.345"), MONEY_PLACES) == Decimal("2.35")


class TestMoneyNeverRoundTripsThroughFloat:
    # The card-balance path used to return `float` from three repositories and rebuild a Decimal from
    # `str(total)` in the service. Harmless at ordinary magnitudes and wrong at large ones, since a
    # float carries ~15-16 significant digits — and ARS reaches them: at roughly 90 trillion, a cent
    # is past the last digit a float can hold.
    #
    # Pinned as the property rather than as "no `float(` appears", because the point is the cent
    # surviving, not the spelling.

    # Driven through the REPOSITORIES with a mocked session rather than by handing the service a
    # Decimal, because a test that builds its own Decimal cannot see a cast that happens upstream of
    # it — the first version of this did exactly that and passed with `float(total)` put back.
    @pytest.mark.parametrize(
        ("module", "function", "extra"),
        [
            ("app.repositories.expense_repository", "sum_by_credit_card_ids_grouped", (1,)),
            ("app.repositories.card_settlement_repository", "sum_by_card_ids_grouped", ()),
            ("app.repositories.shared_expense_repository", "sum_by_credit_card_ids_grouped", ()),
        ],
    )
    @pytest.mark.asyncio
    async def test_a_grouped_sum_hands_back_the_cent_a_float_would_lose(self, module, function, extra):
        exact = Decimal("90000000000000.01")
        assert Decimal(str(float(exact))) != exact, "pick a larger figure — this one still fits in a float"

        session = AsyncMock()
        session.execute.return_value = _rows([(1, "ARS", exact)])
        grouped = await getattr(importlib.import_module(module), function)(session, [1], *extra)

        assert grouped[1]["ARS"] == exact

    @pytest.mark.parametrize(
        ("module", "function", "extra"),
        [
            ("app.repositories.expense_repository", "sum_by_credit_card_ids_monthly", (1,)),
            ("app.repositories.card_settlement_repository", "sum_by_card_ids_monthly", ()),
            ("app.repositories.shared_expense_repository", "sum_by_credit_card_ids_monthly", ()),
        ],
    )
    @pytest.mark.asyncio
    async def test_a_monthly_sum_hands_back_the_cent_too(self, module, function, extra):
        exact = Decimal("90000000000000.01")
        session = AsyncMock()
        session.execute.return_value = _rows([(1, 2026, 1, "ARS", exact)])
        rows = await getattr(importlib.import_module(module), function)(session, [1], *extra)

        assert rows[0][4] == exact
