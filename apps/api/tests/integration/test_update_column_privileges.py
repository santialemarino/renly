import ast
import os
import pathlib
import re
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import app.models as app_models

# Every UPDATE the application can issue, DERIVED from its source, checked against what the request
# role is actually allowed to update in a real database.
#
# ▸ THE CLASS OF BUG. A table whose UPDATE is granted per COLUMN (a REVOKE plus a column GRANT, the only
# way to say "this column and no other" — RLS filters rows, never columns) refuses any statement whose
# SET list names a column outside the grant. It refuses it as the request role only, and only at
# runtime: moving an account into a pot re-points its reconciliations' `user_id` / `pot_id`, and that
# answered "permission denied for table account_reconciliations" for as long as the grant named only
# the four back-pointers — invisible while local dev connected as the owner, and to every suite here,
# because nothing compared the code's writes with the grant. Postgres checks the privilege for the
# statement, not for the rows it matches, so it failed even for an account with no reconciliation.
#
# ▸ HOW THE WRITES ARE DERIVED (`derive_writes`), per shape the codebase uses to update a row:
#   * Core `update(Model)` / `sa_update(Model)`: the columns of every `.values(...)` in its chain —
#     keywords, a dict literal, or `**name` where `name` is a dict literal in the same function.
#   * Upserts, `insert(Model)…on_conflict_do_update(set_={...})`: the keys of `set_`.
#   * ORM attribute writes, `obj.col = …` / `setattr(obj, "col", …)` / `session.merge(obj)`, where the
#     type of `obj` is inferred inside its function from a parameter or variable annotation, a model
#     constructor, or the return annotation of the function it came from (a repository's `-> Model`).
#     Every ORM write also carries the model's Python-side `onupdate` columns, which the unit of work
#     adds to its SET list unasked.
#   * Raw SQL: any string literal in `app/` shaped `UPDATE <table> SET <col> = …`.
# A site whose columns cannot be read statically (a `setattr` with a computed name, a `.values(x)` of
# something other than a literal, `session.merge`) is recorded with `columns=None`, and a site whose
# object has no inferable type is recorded against EVERY table carrying that column. Both are
# conservative: they can only make the check stricter, and it fails on them only where a table's grant
# is per-column — where "somewhere in this row" is not good enough.
#
# ▸ WHAT IT CANNOT SEE, stated so nobody reads more into a green run: SQL assembled at runtime from
# non-literal fragments; writes reached through `getattr`/`__dict__`/relationship cascades; and which
# SESSION a write runs on — every write is held to `renly_app`, the stricter role, so a write that only
# ever runs on the admin session would show here as a false alarm rather than hide.
#
# The derivation's own behaviour — that each shape is found, and that it fails loudly rather than
# quietly — is pinned without a database in tests/unit/test_update_write_derivation.py. The check
# against the grants needs the catalogue, so it is gated on the same two vars as the other RLS suites.

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

# Every mapped table the application declares, by model class name.
TABLES = {
    cls.__name__: cls.__table__
    for cls in vars(app_models).values()
    if isinstance(cls, type) and issubclass(cls, SQLModel) and getattr(cls, "__table__", None) is not None
}

_COLUMN_OWNERS: dict[str, set[str]] = {}
for _table in TABLES.values():
    for _column in _table.columns:
        _COLUMN_OWNERS.setdefault(_column.name, set()).add(_table.name)

# The methods that read a statement's rows back, so a value built from one is the statement's model.
_RESULT_READS = {"all", "first", "one", "one_or_none", "scalar", "scalar_one", "scalar_one_or_none", "scalars", "unique"}
# The methods that narrow a SELECT without changing what it returns.
_QUERY_REFINEMENTS = {"distinct", "execution_options", "join", "limit", "offset", "options", "order_by", "where", "with_for_update"}

_SQL_UPDATE = re.compile(r"\bUPDATE\s+(?:ONLY\s+)?\"?(\w+)\"?\s+(?:AS\s+\w+\s+)?SET\s+(.+?)(?=\bWHERE\b|\bFROM\b|\bRETURNING\b|$)", re.I | re.S)
_SQL_ASSIGNMENT = re.compile(r"(?:^|,)\s*\"?(\w+)\"?\s*=")


# One statement shape the application can issue that updates rows. `tables` holds more than one name
# only when the object's type could not be inferred; `columns` is None when the SET list could not be.
@dataclass(frozen=True)
class Write:
    site: str
    kind: str
    tables: frozenset[str]
    columns: frozenset[str] | None


# The local names each module binds to SQLAlchemy's `update` and `insert` constructors.
def _constructor_aliases(tree: ast.Module) -> dict[str, str]:
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {"sqlalchemy", "sqlmodel", "sqlalchemy.dialects.postgresql"}:
            for alias in node.names:
                if alias.name in {"update", "insert"}:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


# The model classes an annotation names, bare or quoted.
def _models_in(annotation: ast.AST | None) -> set[str]:
    if annotation is None:
        return set()
    return {n.id for n in ast.walk(annotation) if isinstance(n, ast.Name) and n.id in TABLES} | {
        n.value for n in ast.walk(annotation) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in TABLES
    }


# The return annotation of every function in the given sources, keyed by (module stem, name) and by bare name.
def _return_annotations(sources: dict[pathlib.Path, str]) -> dict[tuple[str | None, str], list[ast.AST]]:
    found: dict[tuple[str | None, str], list[ast.AST]] = {}
    for path, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
                found.setdefault((path.stem, node.name), []).append(node.returns)
                found.setdefault((None, node.name), []).append(node.returns)
    return found


# The i-th element of a fixed-length `tuple[...]` annotation, or None when it is not one.
def _tuple_element(annotation: ast.AST, index: int) -> ast.AST | None:
    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name) and annotation.value.id == "tuple":
        elements = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        if index < len(elements) and not (isinstance(elements[-1], ast.Constant) and elements[-1].value is Ellipsis):
            return elements[index]
    return None


# The dotted text of a column reference (`"col"`, `Model.col`, `Model.__table__.c.col`) as its name.
def _column_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


# The keys of a dict literal, or None when any key is not a plain column reference.
def _dict_keys(node: ast.AST) -> frozenset[str] | None:
    if isinstance(node, ast.Dict) and None not in node.keys:
        keys = [_column_key(k) for k in node.keys]
        if None not in keys:
            return frozenset(keys)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict" and not node.args:
        if all(k.arg for k in node.keywords):
            return frozenset(k.arg for k in node.keywords)
    return None


# One function body's writes: infers the model each local name holds, then reads every UPDATE shape.
class _FunctionScan:
    # Infers the local types up front, since every write read afterwards depends on them.
    def __init__(self, fn: ast.AST, module: str, path: pathlib.Path, aliases: dict[str, str], returns: dict, owner: str | None):
        self.fn = fn
        self.module = module
        self.path = path
        self.aliases = aliases
        self.returns = returns
        self.assignments: dict[str, list[ast.AST]] = {}
        self.types: dict[str, set[str]] = {}
        if owner in TABLES:
            self.types["self"] = {owner}
        self._infer()

    # "app/…/module.py:<line>" for a node, the form every refusal names.
    def _site(self, node: ast.AST) -> str:
        return f"{self.path.relative_to(APP.parent)}:{node.lineno}"

    # Nodes of this function body, not descending into nested functions or classes.
    def _nodes(self):
        stack = list(ast.iter_child_nodes(self.fn))
        while stack:
            node = stack.pop()
            yield node
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                stack.extend(ast.iter_child_nodes(node))

    # The return annotations of the function a call reaches: by module when the call names one, and
    # otherwise every function of that name, which can only widen the answer.
    def _callee_returns(self, func: ast.AST) -> list[ast.AST]:
        if isinstance(func, ast.Name):
            return self.returns.get((self.module, func.id)) or self.returns.get((None, func.id), [])
        if isinstance(func, ast.Attribute):
            base = func.value.id if isinstance(func.value, ast.Name) else None
            return self.returns.get((base, func.attr)) or self.returns.get((None, func.attr), [])
        return []

    # Models a value expression evaluates to, as far as can be told statically. `index` picks one
    # element, for a value unpacked into a tuple of names.
    def _value_types(self, node: ast.AST, index: int | None = None, seen: frozenset[str] = frozenset()) -> set[str]:
        if isinstance(node, ast.Await):
            node = node.value
        if isinstance(node, ast.Name):
            if index is None:
                return set(self.types.get(node.id, set()))
            if node.id in seen:
                return set()
            return {m for value in self.assignments.get(node.id, []) for m in self._value_types(value, index, seen | {node.id})}
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and index is None:
            return {m for element in node.elts for m in self._value_types(element)}
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)) and index is None:
            return self._value_types(node.elt)
        if not isinstance(node, ast.Call):
            return set()
        func = node.func
        if index is None:
            if isinstance(func, ast.Name) and func.id in TABLES:
                return {func.id}
            if isinstance(func, ast.Name) and func.id == "select" and node.args:
                return _models_in(node.args[0]) if isinstance(node.args[0], ast.Name) else set()
            # A result read — `(await session.execute(select(M))).scalars().all()` — is the statement's model.
            if isinstance(func, ast.Attribute) and func.attr in _RESULT_READS | _QUERY_REFINEMENTS:
                return self._value_types(func.value)
            if isinstance(func, ast.Attribute) and func.attr == "execute" and node.args:
                return self._value_types(node.args[0])
            return {m for annotation in self._callee_returns(func) for m in _models_in(annotation)}
        return {m for annotation in self._callee_returns(func) for m in _models_in(_tuple_element(annotation, index))}

    # Types each local name from its parameter annotation and from every assignment or loop binding it.
    def _infer(self) -> None:
        args = getattr(self.fn, "args", None)
        if args is not None:
            for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
                if models := _models_in(arg.annotation):
                    self.types.setdefault(arg.arg, set()).update(models)
        # Two passes, so a name typed from another name resolves whatever the order they appear in.
        for _ in range(2):
            for node in self._nodes():
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    self.types.setdefault(node.target.id, set()).update(_models_in(node.annotation))
                    if node.value is not None:
                        self.types[node.target.id].update(self._value_types(node.value))
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.assignments.setdefault(target.id, [])
                            if node.value not in self.assignments[target.id]:
                                self.assignments[target.id].append(node.value)
                            self.types.setdefault(target.id, set()).update(self._value_types(node.value))
                        elif isinstance(target, ast.Tuple):
                            for index, element in enumerate(target.elts):
                                if isinstance(element, ast.Name):
                                    self.types.setdefault(element.id, set()).update(self._value_types(node.value, index))
                elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
                    self.types.setdefault(node.target.id, set()).update(self._value_types(node.iter))

    # The update/insert constructor call a statement chain starts from, following local names.
    def _chain_root(self, node: ast.AST, seen: frozenset[str] = frozenset()) -> ast.Call | None:
        while True:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.aliases:
                return node
            if isinstance(node, ast.Call):
                node = node.func
            elif isinstance(node, ast.Attribute):
                node = node.value
            elif isinstance(node, ast.Name) and node.id not in seen and len(self.assignments.get(node.id, [])) >= 1:
                for value in self.assignments[node.id]:
                    root = self._chain_root(value, seen | {node.id})
                    if root is not None:
                        return root
                return None
            else:
                return None

    # The columns a `.values(...)` call sets, or None when they cannot be read.
    def _values_columns(self, call: ast.Call) -> frozenset[str] | None:
        columns: set[str] = set()
        for keyword in call.keywords:
            if keyword.arg is not None:
                columns.add(keyword.arg)
                continue
            if not isinstance(keyword.value, ast.Name):
                return None
            sources = self.assignments.get(keyword.value.id, [])
            keys = [_dict_keys(source) for source in sources]
            if not keys or None in keys:
                return None
            for found in keys:
                columns |= found
        for arg in call.args:
            keys = _dict_keys(arg)
            if keys is None:
                return None
            columns |= keys
        return frozenset(columns)

    # The model a constructor call names, when it names one.
    @staticmethod
    def _root_model(root: ast.Call) -> str | None:
        if root.args and isinstance(root.args[0], ast.Name) and root.args[0].id in TABLES:
            return root.args[0].id
        return None

    # An ORM write on `target`: against its inferred model(s), or, untyped, against every table carrying
    # the column. None when the target is typed and the attribute is none of its model's columns.
    def _orm_write(self, node: ast.AST, target: ast.AST, columns: frozenset[str] | None, kind: str) -> Write | None:
        name = target.id if isinstance(target, ast.Name) else None
        models = self.types.get(name, set()) if name else set()
        if models:
            tables = frozenset(TABLES[m].name for m in models)
            if columns is not None:
                known = {c.name for m in models for c in TABLES[m].columns}
                if not columns & known:
                    return None
                onupdate = {c.name for m in models for c in TABLES[m].columns if c.onupdate is not None}
                columns = frozenset(columns | onupdate)
            return Write(self._site(node), kind, tables, columns)
        if columns is None:
            return Write(self._site(node), kind, frozenset(t.name for t in TABLES.values()), None)
        candidates = {t for c in columns for t in _COLUMN_OWNERS.get(c, set())}
        if not candidates or name == "self":
            return None
        return Write(self._site(node), f"{kind} (untyped)", frozenset(candidates), columns)

    # Every UPDATE shape in this body; an `update(M)` whose SET list is never seen counts as unknown.
    def writes(self) -> list[Write]:
        found: list[Write] = []
        update_roots: dict[int, ast.Call] = {}
        consumed: set[int] = set()
        for node in self._nodes():
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and self.aliases.get(node.func.id) == "update":
                update_roots[id(node)] = node
        for node in self._nodes():
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                if attr == "values":
                    root = self._chain_root(node.func.value)
                    if root is not None and self.aliases.get(root.func.id) == "update":
                        consumed.add(id(root))
                        model = self._root_model(root)
                        tables = frozenset({TABLES[model].name}) if model else frozenset(t.name for t in TABLES.values())
                        found.append(Write(self._site(node), "core update", tables, self._values_columns(node)))
                elif attr == "on_conflict_do_update":
                    root = self._chain_root(node.func.value)
                    model = self._root_model(root) if root is not None else None
                    tables = frozenset({TABLES[model].name}) if model else frozenset(t.name for t in TABLES.values())
                    set_ = next((k.value for k in node.keywords if k.arg == "set_"), None)
                    found.append(Write(self._site(node), "upsert", tables, _dict_keys(set_) if set_ is not None else None))
                elif attr == "merge" and node.args:
                    if write := self._orm_write(node, node.args[0], None, "orm merge"):
                        found.append(write)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr" and len(node.args) == 3:
                key = node.args[1]
                columns = frozenset({key.value}) if isinstance(key, ast.Constant) and isinstance(key.value, str) else None
                if write := self._orm_write(node, node.args[0], columns, "orm setattr"):
                    found.append(write)
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    for leaf in ast.walk(target) if isinstance(target, (ast.Tuple, ast.List)) else [target]:
                        if isinstance(leaf, ast.Attribute) and leaf.attr in _COLUMN_OWNERS:
                            if write := self._orm_write(node, leaf.value, frozenset({leaf.attr}), "orm attribute"):
                                found.append(write)
        for key, root in update_roots.items():
            if key not in consumed:
                model = self._root_model(root)
                tables = frozenset({TABLES[model].name}) if model else frozenset(t.name for t in TABLES.values())
                found.append(Write(self._site(root), "core update", tables, None))
        return found


# The SQL fragments of a string or f-string literal, joined, for the raw-SQL scan.
def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else " ? " for v in node.values)
    return None


# Every UPDATE the given sources can issue. `sources` maps a path under app/ to its text and defaults
# to all of app/; return types are read from app/ and from the sources together.
def derive_writes(sources: dict[pathlib.Path, str] | None = None) -> list[Write]:
    application = {path: path.read_text() for path in sorted(APP.rglob("*.py"))}
    if sources is None:
        sources = application
    returns = _return_annotations(application | sources)
    found: list[Write] = []
    for path, source in sources.items():
        tree = ast.parse(source)
        aliases = _constructor_aliases(tree)
        owners = {id(fn): cls.name for cls in ast.walk(tree) if isinstance(cls, ast.ClassDef) for fn in cls.body}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found += _FunctionScan(fn, path.stem, path, aliases, returns, owners.get(id(fn))).writes()
        # An f-string's constant parts are nodes of their own; they are read as part of the whole.
        fragments = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
        for node in ast.walk(tree):
            if id(node) not in fragments and (sql := _literal_text(node)) is not None:
                for match in _SQL_UPDATE.finditer(sql):
                    columns = frozenset(c.lower() for c in _SQL_ASSIGNMENT.findall(match.group(2)))
                    site = f"{path.relative_to(APP.parent)}:{node.lineno}"
                    found.append(Write(site, "raw sql", frozenset({match.group(1).lower()}), columns or None))
    return found


pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)


@pytest_asyncio.fixture
async def admin():
    engine = create_async_engine(ADMIN_URL)
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()
    await engine.dispose()


# Whether renly_app may UPDATE each table as a whole, and, where it may not, which columns it may.
async def _update_grants(admin: AsyncSession) -> tuple[dict[str, bool], dict[str, set[str]]]:
    tables = sorted({t.name for t in TABLES.values()})
    whole = {
        row.table: row.granted
        for row in (
            await admin.execute(
                text("SELECT t AS table, has_table_privilege('renly_app', 'public.' || t, 'UPDATE') AS granted FROM unnest(CAST(:t AS text[])) t"),
                {"t": tables},
            )
        ).all()
    }
    per_column: dict[str, set[str]] = {}
    for row in (
        await admin.execute(
            text(
                "SELECT c.table_name, c.column_name FROM information_schema.columns c"
                " WHERE c.table_schema = 'public' AND c.table_name = ANY(:t)"
                " AND has_column_privilege('renly_app', 'public.' || c.table_name, c.column_name, 'UPDATE')"
            ),
            {"t": tables},
        )
    ).all():
        per_column.setdefault(row.table_name, set()).add(row.column_name)
    return whole, per_column


# Every derived write the request role would be refused, as a readable line per site.
def _refusals(writes: list[Write], whole: dict[str, bool], per_column: dict[str, set[str]]) -> list[str]:
    refused = []
    for write in writes:
        for table in sorted(write.tables):
            if whole.get(table, False):
                continue
            if write.columns is None:
                refused.append(f"{write.site} ({write.kind}): cannot derive which columns it sets, and {table} grants UPDATE per column")
                continue
            missing = sorted(write.columns - per_column.get(table, set()))
            if missing:
                refused.append(f"{write.site} ({write.kind}): {table}.{', '.join(missing)} is not updatable by renly_app")
    return refused


class TestEveryUpdateTheCodeIssuesIsGrantedToTheRequestRole:
    @pytest.mark.asyncio
    async def test_no_derived_write_names_a_column_renly_app_may_not_update(self, admin):
        whole, per_column = await _update_grants(admin)
        assert _refusals(derive_writes(), whole, per_column) == []

    @pytest.mark.asyncio
    async def test_the_catalogue_reads_the_column_grants_it_is_compared_against(self, admin):
        # Anti-vacuity, from the database side: the comparison above only means something where a
        # table's UPDATE is per-column, and a query that stopped reading grants would report every table
        # as fully granted and pass. Pinned to the tables that are per-column today and their grants.
        whole, per_column = await _update_grants(admin)
        restricted = sorted(table for table, granted in whole.items() if not granted)
        assert restricted == ["account_reconciliations", "pot_ownership_events", "shared_audit_log"]
        assert per_column.get("account_reconciliations") == {
            "adjustment_expense_id",
            "adjustment_income_id",
            "adjustment_shared_expense_id",
            "adjustment_shared_income_id",
            "pot_id",
            "user_id",
        }
        assert per_column.get("pot_ownership_events") == {"confirmed_at"}
        assert "shared_audit_log" not in per_column

    @pytest.mark.asyncio
    async def test_the_comparison_refuses_a_write_outside_the_grant(self, admin):
        # Anti-vacuity, from the comparison's side, against the real grants: a write the table does not
        # grant is reported, and the same statement shape inside the grant is not.
        whole, per_column = await _update_grants(admin)
        outside = Write("probe:1", "core update", frozenset({"account_reconciliations"}), frozenset({"statement_balance"}))
        inside = Write("probe:2", "core update", frozenset({"account_reconciliations"}), frozenset({"user_id", "pot_id"}))
        unknown = Write("probe:3", "orm merge", frozenset({"account_reconciliations"}), None)
        assert _refusals([outside, inside, unknown], whole, per_column) == [
            "probe:1 (core update): account_reconciliations.statement_balance is not updatable by renly_app",
            "probe:3 (orm merge): cannot derive which columns it sets, and account_reconciliations grants UPDATE per column",
        ]
