import ast
import pathlib

from tests.integration.test_ownership_predicates import COVERED_REPOSITORIES

# The population of owner-scoped reads is DERIVED from the repositories on disk, not listed here — so a
# new one joins the behavioural suite by existing rather than by somebody remembering.
#
# This is the half that runs on every `pnpm test:api`. The behaviour itself lives in
# `tests/integration/test_ownership_predicates.py` and needs a real database, because a repository
# predicate cannot be tested through a mocked session at all: the mock returns whatever it was told, so
# the assertion reads identically whether the predicate is there or not. Four of these were found
# unpinned by the pre-launch audit and eight more had the same shape — a hand-written list is what let
# that happen, which is why there is no hand-written list.
#
# ▸ The rule: a `get_by_id` whose signature takes `user_id` ALONGSIDE something else is scoping rows to
# an owner. `user_repository.get_by_id(session, user_id)` takes it as the PRIMARY KEY, so it falls out
# of the rule mechanically rather than sitting in an exclusion list somebody has to maintain — there are
# no exclusions here at all. Every other `get_by_id` (reconciliations by account, settlements by group,
# pots by id) takes no `user_id` and is scoped by its parent or by RLS, so it is out of scope by the
# same rule.

REPOSITORIES = pathlib.Path(__file__).resolve().parents[2] / "app" / "repositories"


# Every repository whose get_by_id scopes rows to an owner, by module name.
def _owner_scoped_repositories() -> set[str]:
    found = set()
    for path in sorted(REPOSITORIES.glob("*_repository.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef) or node.name != "get_by_id":
                continue
            args = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
            if "user_id" in args and len(args) > 2:
                found.add(path.stem)
    return found


class TestTheBehaviouralSuiteCoversEveryOwnerScopedRead:
    def test_no_owner_scoped_get_by_id_is_left_unpinned(self):
        missing = sorted(_owner_scoped_repositories() - COVERED_REPOSITORIES)
        assert missing == [], (
            f"these repositories scope get_by_id by user_id with no case in tests/integration/test_ownership_predicates.py: {missing}"
        )

    def test_it_does_not_name_repositories_that_no_longer_scope_by_owner(self):
        # The other direction, so a case left behind after a signature changes is caught rather than
        # quietly asserting about a function that stopped being owner-scoped.
        stale = sorted(COVERED_REPOSITORIES - _owner_scoped_repositories())
        assert stale == [], f"cases exist for repositories whose get_by_id no longer takes a user_id: {stale}"

    def test_the_derivation_actually_finds_things(self):
        # Without this the two assertions above pass vacuously the moment the AST walk stops matching —
        # an empty set is a subset of everything, and a guard that is green because it is looking at
        # nothing is the failure this repo keeps re-learning. Named repositories rather than a count, so
        # it fails on the walk breaking rather than on the population legitimately growing.
        found = _owner_scoped_repositories()
        assert {"account_repository", "credit_card_repository", "investment_repository", "collection_repository"} <= found

    def test_the_users_own_lookup_is_excluded_by_the_rule_and_not_by_a_list(self):
        # `user_repository.get_by_id(session, user_id)` takes user_id as the primary key, not as a
        # scope. It is out because the rule says "user_id alongside something else", and asserting that
        # here is what stops somebody from later 'fixing' the rule into one that needs an exclusion list.
        assert "user_repository" not in _owner_scoped_repositories()
