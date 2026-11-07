#!/usr/bin/env python3
"""The API test files a set of changed paths can affect, for the pre-commit hook.

Usage: api-related-tests.py <path relative to the repo root>...

Prints one test file per line (relative to apps/api), or the single line `ALL` when the whole suite has to
run. It is the API's answer to `vitest related`: a test is related to a changed module when it imports it,
directly or through any chain of imports — conftest files included, since every test below one depends
on it. Built from the source with `ast`, so it needs no environment and runs in well under a second.

`ALL` when a path is not a Python module of `app/` or `tests/`: the schema and migrations, `pyproject.toml`
and `uv.lock`, the API reference the suite reads, a deleted file (whatever imported it may now break).
What this cannot see is a test that reads source by PATH rather than importing it (the structural guards
that walk `app/`); those and every other test run in CI, whose checks are required before a merge.
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path

API = Path(__file__).resolve().parent.parent / "apps" / "api"


# The dotted module name of a file under apps/api (`app/services/x.py` -> `app.services.x`).
def module_name(path: Path) -> str:
    parts = list(path.relative_to(API).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


# Every module a file imports, with each package on the way (importing `a.b.c` runs `a` and `a.b` too).
def imports_of(path: Path, name: str, modules: set[str]) -> set[str]:
    is_package = path.name == "__init__.py"
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                package = name.split(".") if is_package else name.split(".")[:-1]
                package = package[: len(package) - (node.level - 1)]
                base = ".".join(package + ([base] if base else []))
            targets = [base] + [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
        for target in targets:
            parts = target.split(".")
            found.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return found & modules


def main(changed: list[str]) -> None:
    files = {module_name(p): p for root in ("app", "tests") for p in (API / root).rglob("*.py") if ".venv" not in p.parts}
    modules = set(files)

    importers: dict[str, set[str]] = defaultdict(set)
    for name, path in files.items():
        for imported in imports_of(path, name, modules):
            importers[imported].add(name)
        # A test module depends on every conftest above it, which pytest loads first.
        if path.name.startswith("test_"):
            for conftest in (d / "conftest.py" for d in path.parents if API in d.parents or d == API):
                if conftest.exists():
                    importers[module_name(conftest)].add(name)

    start: set[str] = set()
    for raw in changed:
        path = (API.parent.parent / raw).resolve()
        if path.suffix != ".py" or not path.exists() or API not in path.parents or path.parts[len(API.parts)] not in ("app", "tests"):
            print("ALL")
            return
        start.add(module_name(path))

    # A package's `__init__` re-exports its whole package (`app.services` imports every service), so a
    # path through one would relate every change to every test. It is not followed unless it is the
    # change itself: whether the package still imports is what `check:api` (`from app.main import app`)
    # proves, and the hook runs it beside these tests.
    affected, queue = set(start), list(start)
    while queue:
        name = queue.pop()
        if files[name].name == "__init__.py" and name not in start:
            continue
        for importer in importers[name]:
            if importer not in affected:
                affected.add(importer)
                queue.append(importer)

    for name in sorted(affected):
        path = files[name]
        if path.name.startswith("test_"):
            print(path.relative_to(API))


if __name__ == "__main__":
    main(sys.argv[1:])
