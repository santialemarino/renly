# Every repository function is reachable through its namespace singleton, and this is the test that
# says so — because the registry is a hand-written transcription of the module's own functions.
#
# A repository module is a set of module-level `async def`s plus a class that re-exports each as a
# staticmethod, and a singleton of that class is what services import. Adding a function means adding
# it in two places, and the second is easy to miss: the module imports fine, `pnpm check:api` passes
# (it only imports the app), ruff is happy, and the failure is an AttributeError the first time a
# service actually calls it. SEC-11 added two such functions and forgot the registry for both.
#
# The comparison is a set difference in one direction only, deliberately. A registry entry for a
# function that no longer exists cannot happen: `list_x = staticmethod(list_x)` fails at import.

import ast
import pathlib

REPOSITORIES = sorted(pathlib.Path("app/repositories").glob("*_repository.py"))


# The module-level async functions a repository file defines, excluding private helpers.
#
# Async only, and that is the whole selector: a repository's callable surface is its queries, while the
# synchronous names in these files are SQL-expression builders (`settlement_cash_leg`, `sort_columns`)
# that callers import directly rather than reaching through the singleton.
def _module_functions(tree: ast.Module) -> set[str]:
    return {node.name for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_")}


# The names the file's `*Repository` namespace class re-exports. Selected by class NAME suffix rather
# than by position, because several of these files declare a NamedTuple row type first.
def _registered(tree: ast.Module) -> set[str] | None:
    cls = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Repository")), None)
    if cls is None:
        return None
    return {target.id for node in cls.body if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name)}


class TestEveryRepositoryFunctionIsReachable:
    def test_every_repository_file_has_a_namespace_class(self):
        # Asserted first so the check below cannot pass by finding nothing: a file whose class was
        # renamed would otherwise contribute an empty comparison that agrees with everything.
        assert [path.name for path in REPOSITORIES if _registered(ast.parse(path.read_text())) is None] == []

    def test_no_query_is_missing_from_its_namespace(self):
        missing = {
            path.name: sorted(_module_functions(tree) - (_registered(tree) or set()))
            for path in REPOSITORIES
            if (tree := ast.parse(path.read_text())) and _module_functions(tree) - (_registered(tree) or set())
        }
        assert missing == {}

    def test_the_scan_actually_finds_functions(self):
        # The guard on the guard. Both assertions above are set differences that pass trivially against
        # an empty left side, so a selector that stopped matching (a rename, a move to sync defs) would
        # read as every repository being clean.
        assert sum(len(_module_functions(ast.parse(path.read_text()))) for path in REPOSITORIES) > 100


class TestEveryCappedReadReportsWhenTheCeilingBites:
    # Capping is silent by construction — a query with a LIMIT returns a short list and says nothing —
    # so `capped()` is the only signal that a list the app assumes is small has stopped being small.
    # It is also trivially forgettable: the cap still works without it, so nothing fails, and the
    # warning simply never arrives. It shipped that way once in this very change.

    def test_every_read_that_takes_a_limit_routes_its_rows_through_capped(self):
        # Matched on the PARAMETER rather than a list of function names: "which reads are capped" is
        # the thing that changes, so naming them here would need updating by exactly the person who
        # already forgot the call.
        offenders = []
        for path in REPOSITORIES:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.AsyncFunctionDef):
                    continue
                takes_limit = any(arg.arg == "limit" for arg in node.args.kwonlyargs + node.args.args)
                if not takes_limit:
                    continue
                body = ast.unparse(node)
                # A paged read takes `limit` only as part of `page_size`; the capped ones apply it directly.
                if "apply_limit" in body and "capped(" not in body:
                    offenders.append(f"{path.name}:{node.name}")
        assert offenders == []

    def test_the_scan_finds_the_capped_reads(self):
        # The guard on the guard: the assertion above is a filter, so a selector that stopped matching
        # would report every repository clean rather than none checked. Nine endpoints are capped.
        found = sum(
            1
            for path in REPOSITORIES
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.AsyncFunctionDef) and "apply_limit" in ast.unparse(node)
        )
        assert found >= 9
