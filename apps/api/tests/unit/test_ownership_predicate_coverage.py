import ast
import pathlib
import re

from tests.integration.test_ownership_predicates import COVERED_FUNCTIONS

# The population of owner-scoped repository functions is DERIVED from the repositories on disk, not
# listed here — so a new one joins the behavioural suite by existing rather than by somebody remembering.
#
# This is the half that runs on every `pnpm test:api`. The behaviour itself lives in
# `tests/integration/test_ownership_predicates.py` and needs a real database, because a repository
# predicate cannot be tested through a mocked session at all: the mock returns whatever it was told, so
# the assertion reads identically whether the predicate is there or not.
#
# ▸ The population: every repository function that ADDRESSES rows — a keyed read named `get_by_*` or
# `find_by_*`, or a `delete_*` — and whose signature takes `user_id` ALONGSIDE something else. That second
# half is what makes `user_id` a scope rather than the key: `user_repository.get_by_id(session, user_id)`
# and `user_settings_repository.get_by_user_id(session, user_id)` take it as the thing looked up, so they
# fall out of the rule mechanically — there are no exclusions here at all. The keyed-read half used to
# match only functions literally named `get_by_id`, and `account_repository.get_by_ids` and
# `investment_repository.get_by_ids` (the same predicate, batched) had it deleted with the whole suite
# green. The delete half is there because a `DELETE … WHERE user_id = …` decides what is destroyed, and
# the two that exist run on the admin session, where RLS cannot backstop the predicate at all.
#
# What stays out, and why by the same rule: a `list_*` or aggregate taking `user_id` is RLS-backstopped
# on the request session and is not "addressing" a row, so the predicate is not the only guard.

REPOSITORIES = pathlib.Path(__file__).resolve().parents[2] / "app" / "repositories"
ADDRESSING = re.compile(r"^(get_by_|find_by_|delete_)")


# Every repository function that scopes the rows it addresses to an owner, as "<module>.<function>".
def _owner_scoped_functions() -> set[str]:
    found = set()
    for path in sorted(REPOSITORIES.glob("*_repository.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef) or not ADDRESSING.match(node.name):
                continue
            args = [a.arg for a in node.args.args if a.arg != "session"] + [a.arg for a in node.args.kwonlyargs]
            if "user_id" in args and len(args) > 1:
                found.add(f"{path.stem}.{node.name}")
    return found


class TestTheBehaviouralSuiteCoversEveryOwnerScopedFunction:
    def test_no_owner_scoped_function_is_left_unpinned(self):
        missing = sorted(_owner_scoped_functions() - COVERED_FUNCTIONS)
        assert missing == [], f"these repository functions scope rows by user_id with no case in test_ownership_predicates.py: {missing}"

    def test_it_does_not_name_functions_that_no_longer_scope_by_owner(self):
        # The other direction, so a case left behind after a signature changes is caught rather than
        # quietly asserting about a function that stopped being owner-scoped.
        stale = sorted(COVERED_FUNCTIONS - _owner_scoped_functions())
        assert stale == [], f"cases exist for functions that no longer take a scoping user_id: {stale}"

    def test_the_derivation_actually_finds_things(self):
        # Without this the two assertions above pass vacuously the moment the AST walk stops matching —
        # an empty set is a subset of everything. Named functions rather than a count, one per branch of
        # the rule, so it fails on the walk breaking rather than on the population legitimately growing.
        found = _owner_scoped_functions()
        assert {
            "account_repository.get_by_id",
            "account_repository.get_by_ids",
            "investment_repository.get_by_ids",
            "notification_repository.get_by_id",
            "auth_token_repository.delete_unconsumed_by_user_type",
            "refresh_token_repository.delete_expired_by_user",
        } <= found

    def test_a_lookup_by_the_user_itself_is_excluded_by_the_rule_and_not_by_a_list(self):
        # `user_id` as the thing looked up, not as a scope. Out because the rule says "user_id alongside
        # something else", and asserting that here is what stops somebody from later 'fixing' the rule
        # into one that needs an exclusion list.
        found = _owner_scoped_functions()
        assert "user_repository.get_by_id" not in found
        assert "user_settings_repository.get_by_user_id" not in found
