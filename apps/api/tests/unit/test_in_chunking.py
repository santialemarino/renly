import ast
from pathlib import Path

import pytest

from app.repositories.utils import IN_CHUNK_SIZE, chunked
from tests.integration.test_bind_parameter_cliff import COVERED_FUNCTIONS

# U19: asyncpg refuses a statement carrying more than 32,767 bind parameters, and `column.in_(ids)` binds
# one per id. A repository read whose id list is not bounded by one user's own rows — the scheduler's
# reads span every user, and the dashboard's pot fan-out spans every pot a household holds — therefore
# runs its `IN` through `chunked` (app/repositories/utils.py), one statement per chunk.
#
# Which reads those are is DERIVED here rather than remembered, in two passes over the source:
#
#   * every repository function whose `.in_(...)` takes one of its own PARAMETERS is either chunked or
#     named in BOUNDED with the reason its callers' lists are bounded — so a new one fails until somebody
#     decides which it is, and a chunked one that stops chunking fails because BOUNDED does not name it;
#   * every repository function the SCHEDULER can reach (walked from the job wrappers through the service
#     and repository calls they make) that takes such a list is chunked — a job runs over the whole user
#     base, so "bounded by one user" can never be its reason.
#
# The walk follows `<name>_service.f(...)`, `<name>_repository.f(...)` and same-module calls; a call made
# through any other alias, or a list built in a service and queried there (no repository), is invisible
# to it. tests/integration/test_bind_parameter_cliff.py drives every CHUNKED read past the cap on a real
# database, and fails on a CHUNKED name it has no case for.

_API = Path(__file__).resolve().parents[2]
_APP = _API / "app"

# Every chunked function, as `<module>.<function>`. The integration suite holds one case per entry.
CHUNKED = {
    "account_reconciliation_repository.get_latest_dates_across_users",
    "account_repository.get_by_ids_across_users",
    "asset_price_repository.get_latest_by_tickers",
    "card_settlement_repository.sum_by_account_ids",
    "card_settlement_repository.sum_by_account_ids_dated",
    "expense_repository.sum_by_account_ids",
    "expense_repository.sum_by_account_ids_dated",
    "group_repository.get_by_ids",
    "group_repository.list_members_by_groups",
    "group_settlement_repository._sum_leg",
    "group_settlement_repository._sum_leg_dated",
    "income_repository.sum_by_account_ids",
    "income_repository.sum_by_account_ids_dated",
    "notification_repository.clear_digest_pending",
    "notification_repository.list_digest_pending",
    "pot_ownership_repository._sum_leg",
    "pot_ownership_repository._sum_leg_dated",
    "pot_repository.list_accounts_by_pots",
    "pot_repository.list_active_investments_by_pots",
    "pot_repository.list_permissions_by_pots",
    "shared_expense_repository.sum_by_account_ids",
    "shared_expense_repository.sum_by_account_ids_dated",
    "shared_income_repository.sum_by_account_ids",
    "shared_income_repository.sum_by_account_ids_dated",
    "snapshot_repository.get_ids_with_snapshot_on_date",
    "snapshot_repository.get_latest_by_investments",
    "snapshot_repository.list_by_investments",
    "transfer_repository._sum_leg",
    "transfer_repository._sum_leg_dated",
    "user_repository.get_by_ids",
    "user_settings_repository.get_string_by_user_ids",
}

# Why each unchunked `IN` over a caller list is bounded. Every caller reaches these from ONE request (or
# one event), with ids drawn from rows that request's user owns or can see — so the list grows with one
# person's data, never with the user base. None is reachable from the scheduler (asserted below).
_OWN_ROWS = "ids of the caller's own rows (accounts, cards, investments, plans), from one request"
_OWN_GROUPS = "the groups or pots the caller holds a seat in, from one request"
_OWN_SEATS = "the caller's own seats across their groups"
_ONE_REQUEST = "the ids one request's rows reference, from one request"
_ONE_ENTITY = "the children of one card, group or account being changed"
_ONE_EVENT = "the recipients of one notification event: one group's members at most"
BOUNDED = {
    "account_reconciliation_repository.get_latest_dates_by_account_ids": _OWN_ROWS,
    "account_repository.get_by_ids": _OWN_ROWS,
    "account_repository.get_by_ids_any_scope": _ONE_REQUEST,
    "account_repository.list_ids_by_pots_for_update": _ONE_ENTITY,
    "account_repository.move_to_scope": _ONE_ENTITY,
    "card_reconciliation_repository.mark_stale": _ONE_ENTITY,
    "card_reconciliation_repository.sum_expenses_by_bucket_at": _OWN_ROWS,
    "card_reconciliation_repository.sum_settlements_by_bucket_at": _OWN_ROWS,
    "card_settlement_repository.linked_account_ids": _OWN_ROWS,
    "card_settlement_repository.sum_by_account_ids_monthly": _OWN_ROWS,
    "card_settlement_repository.sum_by_card_ids_grouped": _OWN_ROWS,
    "card_settlement_repository.sum_by_card_ids_monthly": _OWN_ROWS,
    "cedear_ratio_repository.get_latest_by_tickers": _OWN_ROWS,
    "collection_repository.get_investment_ids_by_collections": _OWN_ROWS,
    "expense_repository._spending_rows": _OWN_SEATS,
    "expense_repository._union": _OWN_SEATS,
    "expense_repository.count_by_credit_card_ids": _OWN_ROWS,
    "expense_repository.linked_account_ids": _OWN_ROWS,
    "expense_repository.list_linked_installment_expenses": _OWN_ROWS,
    "expense_repository.list_linked_obligation_expenses": _OWN_ROWS,
    "expense_repository.list_linked_subscription_expenses": _OWN_ROWS,
    "expense_repository.max_linked_obligation_dates": _OWN_ROWS,
    "expense_repository.sum_by_account_ids_monthly": _OWN_ROWS,
    "expense_repository.sum_by_credit_card_ids_grouped": _OWN_ROWS,
    "expense_repository.sum_by_credit_card_ids_monthly": _OWN_ROWS,
    "group_invite_repository.list_by_groups": _OWN_GROUPS,
    "group_money_settings_repository.get_by_group_ids": _OWN_GROUPS,
    "group_repository.delete_by_ids": _ONE_ENTITY,
    "group_settlement_repository.group_ids_with_settlements": _OWN_GROUPS,
    "group_settlement_repository.linked_account_ids": _OWN_ROWS,
    "group_settlement_repository.list_movements_by_groups": _OWN_GROUPS,
    "group_settlement_repository.list_movements_by_groups_monthly": _OWN_GROUPS,
    "income_repository._earning_rows": _OWN_SEATS,
    "income_repository._union": _OWN_SEATS,
    "income_repository.linked_account_ids": _OWN_ROWS,
    "income_repository.sum_by_account_ids_monthly": _OWN_ROWS,
    "investment_repository._apply_list_filters": _OWN_ROWS,
    "investment_repository.get_by_ids": _OWN_ROWS,
    "investment_repository.get_by_ids_any_scope": _ONE_REQUEST,
    "investment_repository.get_collections_by_investment_ids": _OWN_ROWS,
    "investment_repository.list_ids_by_pots_for_update": _ONE_ENTITY,
    "investment_repository.move_to_scope": _ONE_ENTITY,
    "metrics_repository.get_latest_snapshots": _OWN_ROWS,
    "metrics_repository.list_snapshots_by_investments": _OWN_ROWS,
    "metrics_repository.list_transactions_by_investments": _OWN_ROWS,
    "notification_repository.preferences_by_user_ids": _ONE_EVENT,
    "pot_ownership_repository.divided_pot_ids": _OWN_GROUPS,
    "pot_ownership_repository.linked_account_ids": _OWN_ROWS,
    "pot_ownership_repository.list_by_pots": _OWN_GROUPS,
    "pot_repository.list_ids_by_groups": _OWN_GROUPS,
    "push_subscription_repository.list_by_user_ids": _ONE_EVENT,
    "shared_expense_repository.linked_account_ids": _OWN_ROWS,
    "shared_expense_repository.list_positions_by_groups": _OWN_GROUPS,
    "shared_expense_repository.list_positions_by_groups_monthly": _OWN_GROUPS,
    "shared_expense_repository.list_splits_by_expense_ids": _ONE_REQUEST,
    "shared_expense_repository.sum_by_credit_card_ids_grouped": _OWN_ROWS,
    "shared_expense_repository.sum_by_credit_card_ids_monthly": _OWN_ROWS,
    "shared_income_repository.linked_account_ids": _OWN_ROWS,
    "shared_income_repository.list_positions_by_groups": _OWN_GROUPS,
    "shared_income_repository.list_positions_by_groups_monthly": _OWN_GROUPS,
    "shared_income_repository.list_splits_by_income_ids": _ONE_REQUEST,
    "snapshot_repository.get_ids_with_snapshots": _OWN_ROWS,
    "transfer_repository._sum_leg_monthly": _OWN_ROWS,
    "transfer_repository.linked_account_ids": _OWN_ROWS,
    "transfer_repository.linked_account_ids_any_scope": _OWN_ROWS,
    "utils.apply_listing_filters": _OWN_ROWS,
    "utils.scope_filter": _OWN_GROUPS,
}

# Scheduler-reachable reads over a caller list that stay unchunked, each with why the list is bounded
# even though a job reaches it. A job spans the user base, so the reason has to be narrower than a user.
SCHEDULER_BOUNDED = {
    "card_reconciliation_repository.mark_stale": "one card's statements, after one charge",
    "notification_repository.preferences_by_user_ids": _ONE_EVENT,
    "push_subscription_repository.list_by_user_ids": _ONE_EVENT,
}


# Every function in `app/<package>/*.py`, keyed `<module>.<function>`, with its module's tree.
def _functions(package: str) -> dict[str, ast.AST]:
    out = {}
    for path in sorted((_APP / package).glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[f"{path.stem}.{node.name}"] = node
    return out


# How a function feeds its `.in_(...)` predicates from its own parameters: {"raw", "chunked"} subset.
def _in_feeds(fn: ast.AST) -> set[str]:
    params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
    chunk_vars = {
        node.target.id
        for node in ast.walk(fn)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and getattr(node.iter.func, "id", None) == "chunked"
        and isinstance(node.target, ast.Name)
        and node.iter.args
        and getattr(node.iter.args[0], "id", None) in params
    }
    feeds = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "in_" and node.args:
            name = getattr(node.args[0], "id", None)
            if name in params:
                feeds.add("raw")
            elif name in chunk_vars:
                feeds.add("chunked")
    return feeds


_REPOSITORIES = _functions("repositories")
_FEEDS = {name: feeds for name, fn in _REPOSITORIES.items() if (feeds := _in_feeds(fn))}


# The functions a call inside `fn` (defined in `module`) can land on: `<x>_service.f`, `<x>_repository.f`
# and a same-module `f` or `_f`.
def _callees(module: str, fn: ast.AST, known: dict[str, ast.AST]) -> set[str]:
    out = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id.endswith(("_service", "_repository")):
            target = f"{func.value.id}.{func.attr}"
        elif isinstance(func, ast.Name):
            target = f"{module}.{func.id}"
        else:
            continue
        if target in known:
            out.add(target)
    return out


# Every repository function reachable from the scheduler's job wrappers.
def _scheduler_reach() -> set[str]:
    known = {**_functions("services"), **_REPOSITORIES}
    scheduler = ast.parse((_APP / "scheduler.py").read_text())
    wrappers = [n for n in scheduler.body if isinstance(n, ast.AsyncFunctionDef)]
    frontier = set().union(*(_callees("scheduler", w, known) for w in wrappers))
    seen: set[str] = set()
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        frontier |= _callees(name.split(".")[0], known[name], known) - seen
    return {name for name in seen if name in _REPOSITORIES}


class TestChunked:
    def test_empty_gives_no_chunks(self):
        assert chunked([]) == []

    # De-duplicated and sorted, so a repeat cannot push a chunk past the cap and the order is fixed.
    def test_dedupes_and_sorts(self):
        assert chunked([3, 1, 3, 2, 1], size=2) == [[1, 2], [3]]
        assert chunked(["b", "a", "b"]) == [["a", "b"]]

    # The boundary itself: exactly one chunk at the size, a second from one past it, none past the size.
    def test_splits_at_the_size(self):
        assert [len(c) for c in chunked(range(IN_CHUNK_SIZE))] == [IN_CHUNK_SIZE]
        assert [len(c) for c in chunked(range(IN_CHUNK_SIZE + 1))] == [IN_CHUNK_SIZE, 1]
        assert [len(c) for c in chunked(range(50_005))] == [IN_CHUNK_SIZE, IN_CHUNK_SIZE, 10_005]

    # Under the cap with room for the statement's other parameters (the cap is 32,767).
    def test_a_chunk_fits_under_the_cap(self):
        assert IN_CHUNK_SIZE <= 30_000


class TestEveryUnboundedInIsChunked:
    # The derived population, printed once (pytest -s) so a reader can see what the guard saw.
    def test_the_population_is_derived_and_not_empty(self):
        print(f"\nIN over a caller list: {len(_FEEDS)} functions, {len(CHUNKED)} chunked, {len(BOUNDED)} bounded")
        assert len(_FEEDS) > 50 and CHUNKED <= set(_FEEDS)

    # A chunked function chunks EVERY parameter-fed `IN` it has; one left raw beside it is the same cliff.
    def test_chunked_functions_chunk_every_in(self):
        assert {name for name, feeds in _FEEDS.items() if "chunked" in feeds} == CHUNKED
        assert {name for name in CHUNKED if "raw" in _FEEDS[name]} == set()

    # Every other parameter-fed `IN` is named with the reason its lists are bounded — no more, no fewer.
    def test_every_raw_in_is_classified(self):
        raw = {name for name, feeds in _FEEDS.items() if feeds == {"raw"}}
        assert raw - set(BOUNDED) == set(), "chunk it (repositories/utils.chunked) or add it to BOUNDED with a reason"
        assert set(BOUNDED) - raw == set(), "stale BOUNDED entry: it no longer takes a raw caller list"

    # Nothing the scheduler reaches leans on "bounded by one user": a job's lists span every user.
    def test_scheduler_reads_are_chunked(self):
        reach = _scheduler_reach()
        print(f"\nscheduler reaches {len(reach)} repository functions")
        raw = {name for name in reach if "raw" in _FEEDS.get(name, set())}
        assert raw - set(SCHEDULER_BOUNDED) == set()
        assert set(SCHEDULER_BOUNDED) - raw == set(), "stale SCHEDULER_BOUNDED entry"
        assert set(SCHEDULER_BOUNDED) <= set(BOUNDED)

    # The walk itself reaches the reads the job that failed made, so an empty or broken walk cannot pass.
    @pytest.mark.parametrize(
        "name",
        [
            "snapshot_repository.get_latest_by_investments",
            "notification_repository.clear_digest_pending",
            "pot_repository.list_permissions_by_pots",
            "account_repository.get_by_ids_across_users",
            "user_settings_repository.get_string_by_user_ids",
        ],
    )
    def test_the_walk_reaches_the_scheduler_reads(self, name):
        assert name in _scheduler_reach()

    # Every chunked read has a case in the integration suite that drives it past the cap, and no case
    # names a read that is not chunked.
    def test_every_chunked_read_has_an_integration_case(self):
        assert COVERED_FUNCTIONS == CHUNKED
