from sqlalchemy import String, cast, literal
from sqlmodel import select

from app.models.expense_entry import ExpenseEntry
from app.models.income_entry import IncomeEntry
from app.repositories.expense_repository import sort_columns as expense_sort_columns
from app.repositories.income_repository import sort_columns as income_sort_columns
from app.repositories.utils import apply_entry_sort

# GET /expenses and GET /income advertised sortable columns in the UI but discarded sort_by, so a
# click updated the URL and the chevron and reordered nothing. These pin the shared ORDER BY helper
# by compiling the statement, which is the only part of a repository query reachable without a
# database — the rest is verified live.
#
# The sort map comes from the PRODUCTION function, over a stand-in of the union's own projection, and
# that is what makes these tests mean something. An earlier version imported a module CONSTANT
# instead — which the union stopped reading the moment it landed, leaving every assertion green
# against a dictionary the API did not use. Drift now fails at IMPORT: a sortable column the
# repository offers but its union does not project raises on `rows.c.<name>` while the maps below are
# being built, so it cannot be missed.


# A stand-in for the union's subquery, carrying the labels both branches project. Named so the
# compiled ORDER BY reads `rows.<column>` rather than an anonymous alias.
def _rows(model, *columns):
    projection = [getattr(model, column).label(column) for column in columns]
    return select(literal("private").label("scope"), model.id.label("id"), *projection).subquery("rows")


_EXPENSE_ROWS = _rows(ExpenseEntry, "date", "amount", "category", "payment_method")
_INCOME_ROWS = _rows(IncomeEntry, "date", "amount", "category")

_SORT_COLUMNS = {ExpenseEntry: expense_sort_columns(_EXPENSE_ROWS), IncomeEntry: income_sort_columns(_INCOME_ROWS)}
_ROWS = {ExpenseEntry: _EXPENSE_ROWS, IncomeEntry: _INCOME_ROWS}


# The ORDER BY clause of a compiled statement, normalised to one line.
def _order_by(stmt) -> str:
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    return " ".join(sql.split("ORDER BY", 1)[1].split())


# The ORDER BY a model's paginated list produces for the given sort request. The default order and the
# tie-break are the repository's own, `scope` included: ids are unique per table and the union spans
# two, so without it a private row and a shared row sharing a date and an id have no total order.
def _order(model, sort_by: str | None, sort_order: str = "asc") -> str:
    rows = _ROWS[model]
    return _order_by(
        apply_entry_sort(
            select(rows),
            sort_by,
            sort_order,
            sort_columns=_SORT_COLUMNS[model],
            default_order=(rows.c.date.desc(), rows.c.id.desc(), rows.c.scope),
            tie_break=(rows.c.id.desc(), rows.c.scope),
        )
    )


class TestApplyEntrySort:
    def test_maps_the_requested_column(self):
        assert "rows.amount ASC" in _order(ExpenseEntry, "amount")

    def test_desc_is_honoured(self):
        assert "rows.amount DESC" in _order(ExpenseEntry, "amount", "desc")

    def test_a_sorted_query_still_breaks_ties_on_id_and_scope(self):
        # Without this, a page of rows sharing one date or one category can repeat across pages or be
        # skipped entirely — the sort key alone is not a total order, and neither is the id alone once
        # the list spans two tables.
        assert _order(ExpenseEntry, "category").endswith("rows.id DESC, rows.scope")

    def test_category_sorts_as_text_not_as_the_enum(self):
        # ORDER BY on a Postgres enum follows its declaration order, which differs between a database
        # built from 01_create_tables.sql and one built by migrations.
        assert "CAST(rows.category AS VARCHAR)" in _order(ExpenseEntry, "category")

    def test_amount_is_not_cast(self):
        # Keeps the assertion above honest: a map that cast every column would satisfy it too.
        assert "CAST" not in _order(ExpenseEntry, "amount")

    def test_no_sort_by_falls_back_to_the_default_order(self):
        assert _order(ExpenseEntry, None, "desc") == "rows.date DESC, rows.id DESC, rows.scope"

    def test_an_unmapped_column_falls_back_rather_than_raising(self):
        # The frontend picks the column from a typed union, so an unknown value is a hand-edited URL
        # — worth ignoring, not worth a 422.
        assert _order(ExpenseEntry, "notes; drop table") == "rows.date DESC, rows.id DESC, rows.scope"


class TestSortableColumns:
    def test_expenses_offer_exactly_what_the_table_renders(self):
        assert set(_SORT_COLUMNS[ExpenseEntry]) == {"date", "amount", "category", "payment_method"}

    def test_income_offers_exactly_what_the_table_renders(self):
        assert set(_SORT_COLUMNS[IncomeEntry]) == {"date", "amount", "category"}

    def test_income_category_also_sorts_as_text(self):
        assert "CAST(rows.category AS VARCHAR)" in _order(IncomeEntry, "category")

    def test_the_category_expression_is_the_cast_one(self):
        assert str(_SORT_COLUMNS[ExpenseEntry]["category"]) == str(cast(_EXPENSE_ROWS.c.category, String))
