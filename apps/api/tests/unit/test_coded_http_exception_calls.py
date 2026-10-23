import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


# Every CodedHTTPException construction in app/, as (file:line, call).
def _calls() -> list[tuple[str, ast.Call]]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "CodedHTTPException":
                found.append((f"{path.relative_to(APP)}:{node.lineno}", node))
    return found


# The web's error-code coverage test reads a code only from `code=<literal or module constant>`; a code
# passed by position, or through any other expression, would reach clients untranslated without failing it.
# `code` is keyword-only in the constructor, which only fails at runtime — this fails at test time.
class TestEveryCodedHTTPExceptionNamesItsCode:
    def test_the_population_is_real(self):
        assert len(_calls()) >= 5

    def test_code_is_a_keyword_literal_or_module_constant(self):
        bad = []
        for where, call in _calls():
            code = next((kw.value for kw in call.keywords if kw.arg == "code"), None)
            literal = isinstance(code, ast.Constant) and isinstance(code.value, str)
            constant = isinstance(code, ast.Name) and code.id.isupper()
            if len(call.args) > 2 or not (literal or constant):
                bad.append(where)
        assert bad == []
