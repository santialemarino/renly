# Every test module that reads the WEB app's source carries `pytestmark = pytest.mark.cross_app`, and
# only those do.
#
# The pre-commit hook scopes the suites to what is staged, and runs the `cross_app` modules of BOTH apps
# on every commit — they are the only API tests a web-only change can break. An untagged parity test
# would silently drop out of that run, so the population is DERIVED here from the test sources rather
# than listed: a module counts as reading the web app when its code (not its comments) builds a path
# into it — `<path> / "web"`, a call taking `"apps", "web"` or `"..", "web"`, or a string naming
# `apps/web/` or `../web/`. The reverse holds too, so the tag never drifts onto a module that would
# only slow every commit down.

import ast
import re
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[1]
_PARENT_SEGMENTS = {"apps", ".."}
_OTHER_APP = "web"
_PATH_STRING = re.compile(r"(^|/)(apps|\.\.)/web(/|$)")


# Whether a module's code builds a path into the web app.
def _reads_web(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            if isinstance(node.right, ast.Constant) and node.right.value == _OTHER_APP:
                return True
        if isinstance(node, ast.Call):
            values = [a.value if isinstance(a, ast.Constant) else None for a in node.args]
            if any(prev in _PARENT_SEGMENTS and cur == _OTHER_APP for prev, cur in zip(values, values[1:], strict=False)):
                return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _PATH_STRING.search(node.value):
            return True
    return False


# Whether a module assigns `pytestmark` a value naming `pytest.mark.cross_app` at its top level.
def _is_tagged(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            marks = node.value.elts if isinstance(node.value, ast.List | ast.Tuple) else [node.value]
            if any(ast.unparse(m) == "pytest.mark.cross_app" for m in marks):
                return True
    return False


# Module path (relative to tests/) -> (reads web, tagged), for every test module.
def _modules() -> dict[str, tuple[bool, bool]]:
    out = {}
    for path in sorted(_TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text())
        out[str(path.relative_to(_TESTS))] = (_reads_web(tree), _is_tagged(tree))
    return out


class TestCrossAppTag:
    # The derivation finds something, so a scanner that matches nothing cannot pass as "all tagged".
    def test_the_derived_population_is_not_empty(self):
        readers = sorted(name for name, (reads, _) in _modules().items() if reads)
        print("cross-app readers:", readers)
        assert readers

    # A module reading the web app's source must carry the tag, or the pre-commit hook skips it on web commits.
    def test_every_module_reading_the_web_app_is_tagged(self):
        untagged = sorted(name for name, (reads, tagged) in _modules().items() if reads and not tagged)
        assert not untagged, f"read apps/web source without `pytestmark = pytest.mark.cross_app`: {untagged}"

    # A tagged module must actually read the web app, so the always-run set stays the parity tests only.
    def test_every_tagged_module_reads_the_web_app(self):
        stray = sorted(name for name, (reads, tagged) in _modules().items() if tagged and not reads)
        assert not stray, f"tagged cross_app but read no apps/web source: {stray}"
