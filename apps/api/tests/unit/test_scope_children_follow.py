import ast

from tests.integration.test_update_column_privileges import APP, TABLES, _constructor_aliases, derive_writes

# Every row carrying a copy of its parent's scope moves WITH its parent, through one function per parent.
#
# ▸ THE CLASS OF BUG. accounts and investments can belong to a user or to a pot, and their history rows
# (reconciliations, transfers, snapshots, transactions) carry their own copy of that `(user_id, pot_id)`
# pair so the RLS policies read it without a join. A path that moves the parent and forgets a child
# leaves that history scoped to the pot the parent left — readable by whoever can view the pot — and the
# pot undeletable, because every `pot_id` foreign key is ON DELETE RESTRICT. Account deletion shipped
# exactly that: it absorbed an orphaned group's pots with a second, parent-only re-point that moved none
# of the four children, and transfers were not in any move at all.
#
# ▸ WHAT IS DERIVED, so a new child table or a new re-point path is caught by existing rather than by
# somebody remembering it:
#   * the children, from the models' metadata: every table carrying the scope pair with a foreign key to
#     another table carrying it. `test_schema_parity` holds the metadata to the SQL schema;
#   * each parent's `move_to_scope`, from app/repositories: the function whose first UPDATE is the parent;
#   * every UPDATE naming `pot_id` on a parent or a child, from `derive_writes` — the same walk the
#     column-grant check uses.
#
# ▸ WHAT IT CANNOT SEE: an ORM attribute write whose columns are computed (`setattr(row, key, value)`
# over a request's fields), which `derive_writes` records with unknown columns. Those are the generic
# edit paths, whose request schemas carry no scope column.

SCOPE = {"user_id", "pot_id"}
REPOSITORIES = APP / "repositories"
POT_SERVICE = APP / "services" / "pot_service.py"


# {parent table: {child table: the child's foreign-key columns to it}}, derived from the metadata.
def _children() -> dict[str, dict[str, frozenset[str]]]:
    scoped = {t.name: t for t in TABLES.values() if SCOPE <= set(t.c.keys())}
    found: dict[str, dict[str, set[str]]] = {}
    for child in scoped.values():
        for column in child.c:
            for fk in column.foreign_keys:
                parent = fk.column.table.name
                if parent in scoped and parent != child.name:
                    found.setdefault(parent, {}).setdefault(child.name, set()).add(column.name)
    return {parent: {child: frozenset(cols) for child, cols in kids.items()} for parent, kids in found.items()}


# One `update(Model)` statement inside a function: its table, line, and the columns its WHERE matches
# with `.in_(...)`.
class _Update:
    def __init__(self, table: str, line: int, filtered_on: frozenset[str]):
        self.table = table
        self.line = line
        self.filtered_on = filtered_on


# The UPDATE statements of one function, in source order.
def _updates(fn: ast.AST, aliases: dict[str, str]) -> list[_Update]:
    found = []
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "where"):
            continue
        target = node.func.value
        if not (isinstance(target, ast.Call) and isinstance(target.func, ast.Name) and aliases.get(target.func.id) == "update"):
            continue
        model = target.args[0].id if target.args and isinstance(target.args[0], ast.Name) else None
        if model not in TABLES:
            continue
        filtered_on = frozenset(
            call.func.value.attr
            for arg in node.args
            for call in ast.walk(arg)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "in_"
            and isinstance(call.func.value, ast.Attribute)
            and isinstance(call.func.value.value, ast.Name)
            and call.func.value.value.id == model
        )
        found.append(_Update(TABLES[model].name, target.lineno, filtered_on))
    return sorted(found, key=lambda u: u.line)


# Every repository's `move_to_scope`, keyed by the parent table it moves, with its module stem.
def _moves(parents: set[str]) -> dict[str, tuple[str, list[_Update]]]:
    moves = {}
    for path in sorted(REPOSITORIES.glob("*.py")):
        tree = ast.parse(path.read_text())
        aliases = _constructor_aliases(tree)
        for fn in tree.body:
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "move_to_scope":
                updates = _updates(fn, aliases)
                moved = {u.table for u in updates} & parents
                assert len(moved) == 1, f"{path.name}: move_to_scope moves {sorted(moved)}, not exactly one parent"
                moves[moved.pop()] = (path.stem, updates)
    return moves


# The name of the top-level function enclosing a line of a file under app/, or None.
def _enclosing_function(relative: str, line: int) -> str | None:
    tree = ast.parse((APP.parent / relative).read_text())
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.lineno <= line <= (fn.end_lineno or fn.lineno):
            return fn.name
    return None


CHILDREN = _children()
MOVES = _moves(set(CHILDREN))


class TestTheChildrenAreDerived:
    def test_the_derivation_finds_exactly_the_known_children(self):
        # Pinned, so the walk breaking reads differently from the schema legitimately gaining a child —
        # which should fail here first and then in the move below.
        print(f"derived scope children: {CHILDREN}")
        assert CHILDREN == {
            "accounts": {"account_reconciliations": frozenset({"account_id"}), "transfers": frozenset({"from_account_id", "to_account_id"})},
            "investments": {"investment_snapshots": frozenset({"investment_id"}), "transactions": frozenset({"investment_id"})},
        }


class TestEveryMoveCarriesEveryChild:
    def test_every_parent_has_one_move(self):
        assert set(MOVES) == set(CHILDREN)

    def test_each_move_updates_every_child_by_its_foreign_key(self):
        missing = []
        for parent, kids in CHILDREN.items():
            module, updates = MOVES[parent]
            by_table = {u.table: u for u in updates}
            for child, fk_columns in kids.items():
                if child not in by_table:
                    missing.append(f"{module}.move_to_scope does not re-point {child}")
                elif by_table[child].filtered_on != fk_columns:
                    missing.append(f"{module}.move_to_scope matches {child} on {sorted(by_table[child].filtered_on)}, not {sorted(fk_columns)}")
        assert missing == []

    def test_each_move_sets_the_scope_pair_on_every_table_it_updates(self):
        writes = {(w.site, next(iter(w.tables))): w.columns for w in derive_writes() if len(w.tables) == 1}
        for module, updates in MOVES.values():
            for update in updates:
                site = f"app/repositories/{module}.py:{update.line}"
                assert writes.get((site, update.table)) == frozenset(SCOPE), f"{site} ({update.table}) does not set exactly {sorted(SCOPE)}"

    def test_the_parent_moves_before_any_child(self):
        # A trigger holds every reconciliation to its account's CURRENT scope, so a child re-pointed
        # before its parent is refused; the rest have no trigger yet, so the order is pinned here too.
        for parent, (module, updates) in MOVES.items():
            assert updates[0].table == parent, f"{module}.move_to_scope updates {updates[0].table} before {parent}"
            assert [u.table for u in updates].count(parent) == 1


class TestThereIsOneRePointPath:
    def test_no_update_outside_move_to_scope_writes_a_scope(self):
        # The bug's shape: a second function moving a parent's (or a child's) pot_id lists its children
        # separately, and the list it holds is the one that misses a table.
        covered = set(CHILDREN) | {child for kids in CHILDREN.values() for child in kids}
        elsewhere = []
        for write in derive_writes():
            if write.tables & covered and write.columns is not None and "pot_id" in write.columns:
                relative, line = write.site.rsplit(":", 1)
                if _enclosing_function(relative, int(line)) != "move_to_scope":
                    elsewhere.append(f"{write.site} ({sorted(write.tables)})")
        assert elsewhere == []

    def test_absorbing_an_orphaned_groups_pots_moves_through_every_move(self):
        tree = ast.parse(POT_SERVICE.read_text())
        absorb = next(fn for fn in tree.body if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "absorb_group_pots")
        called = {
            (call.func.value.id, call.func.attr)
            for call in ast.walk(absorb)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
        }
        for module, _ in MOVES.values():
            assert (module, "move_to_scope") in called, f"absorb_group_pots does not call {module}.move_to_scope"
