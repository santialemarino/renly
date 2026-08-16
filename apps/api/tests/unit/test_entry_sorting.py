from sqlmodel import select

from app.models.expense_entry import ExpenseEntry
from app.models.income_entry import IncomeEntry
from app.repositories.expense_repository import _SORT_COLUMNS as EXPENSE_SORT_COLUMNS
from app.repositories.income_repository import _SORT_COLUMNS as INCOME_SORT_COLUMNS
from app.repositories.utils import apply_entry_sort

# GET /expenses and GET /income advertised sortable columns in the UI but discarded sort_by, so a
# click updated the URL and the chevron and reordered nothing. These pin the shared ORDER BY helper
# by compiling the statement, which is the only part of a repository query reachable without a
# database — the rest is verified live.


# The ORDER BY clause of a compiled statement, normalised to one line.
def _order_by(stmt) -> str:
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    return " ".join(sql.split("ORDER BY", 1)[1].split())


class TestApplyEntrySort:
    def test_maps_the_requested_column(self):
        stmt = apply_entry_sort(
            select(ExpenseEntry),
            ExpenseEntry,
            "amount",
            "asc",
            sort_columns=EXPENSE_SORT_COLUMNS,
            default_order=(ExpenseEntry.date.desc(), ExpenseEntry.id.desc()),
        )
        assert "expense_entries.amount ASC" in _order_by(stmt)

    def test_desc_is_honoured(self):
        stmt = apply_entry_sort(
            select(ExpenseEntry),
            ExpenseEntry,
            "amount",
            "desc",
            sort_columns=EXPENSE_SORT_COLUMNS,
            default_order=(ExpenseEntry.date.desc(), ExpenseEntry.id.desc()),
        )
        assert "expense_entries.amount DESC" in _order_by(stmt)

    def test_a_sorted_query_still_breaks_ties_on_id(self):
        # Without this, a page of rows sharing one date or one category can repeat across pages or
        # be skipped entirely — the sort key alone is not a total order.
        stmt = apply_entry_sort(
            select(ExpenseEntry),
            ExpenseEntry,
            "category",
            "asc",
            sort_columns=EXPENSE_SORT_COLUMNS,
            default_order=(ExpenseEntry.date.desc(), ExpenseEntry.id.desc()),
        )
        assert _order_by(stmt).endswith("expense_entries.id DESC")

    def test_category_sorts_as_text_not_as_the_enum(self):
        # ORDER BY on a Postgres enum follows its declaration order, which differs between a database
        # built from 01_create_tables.sql and one built by migrations.
        stmt = apply_entry_sort(
            select(ExpenseEntry),
            ExpenseEntry,
            "category",
            "asc",
            sort_columns=EXPENSE_SORT_COLUMNS,
            default_order=(ExpenseEntry.date.desc(), ExpenseEntry.id.desc()),
        )
        assert "CAST(expense_entries.category AS VARCHAR)" in _order_by(stmt)

    def test_no_sort_by_falls_back_to_the_default_order(self):
        stmt = apply_entry_sort(
            select(ExpenseEntry),
            ExpenseEntry,
            None,
            "desc",
            sort_columns=EXPENSE_SORT_COLUMNS,
            default_order=(ExpenseEntry.date.desc(), ExpenseEntry.id.desc()),
        )
        assert _order_by(stmt) == "expense_entries.date DESC, expense_entries.id DESC"

    def test_an_unmapped_column_falls_back_rather_than_raising(self):
        # The frontend picks the column from a typed union, so an unknown value is a hand-edited URL
        # — worth ignoring, not worth a 422.
        stmt = apply_entry_sort(
            select(ExpenseEntry),
            ExpenseEntry,
            "notes; drop table",
            "asc",
            sort_columns=EXPENSE_SORT_COLUMNS,
            default_order=(ExpenseEntry.date.desc(), ExpenseEntry.id.desc()),
        )
        assert _order_by(stmt) == "expense_entries.date DESC, expense_entries.id DESC"


class TestSortableColumns:
    def test_expenses_offer_exactly_what_the_table_renders(self):
        assert set(EXPENSE_SORT_COLUMNS) == {"date", "amount", "category", "payment_method"}

    def test_income_offers_exactly_what_the_table_renders(self):
        assert set(INCOME_SORT_COLUMNS) == {"date", "amount", "category"}

    def test_income_category_also_sorts_as_text(self):
        stmt = apply_entry_sort(
            select(IncomeEntry),
            IncomeEntry,
            "category",
            "asc",
            sort_columns=INCOME_SORT_COLUMNS,
            default_order=(IncomeEntry.date.desc(), IncomeEntry.id.desc()),
        )
        assert "CAST(income_entries.category AS VARCHAR)" in _order_by(stmt)
