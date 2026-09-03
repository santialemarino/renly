from sqlalchemy import asc, desc, or_

from app.domain.list_scope import ListScope
from app.models.account import Account


# The dual-scope predicate for a movement table joined to the Account it moves, mirroring the RLS
# policies: the row belongs to the requesting user, OR it belongs to the same pot the account does.
# The pot branch compares against the JOINED account rather than a passed-in id, which is what makes a
# shared account's balance the same figure for every member who can see it — a balance that varied by
# who asked would be worse than one that was simply wrong.
# `model.pot_id == Account.pot_id` is never true when the account is private (NULL = NULL is not
# true in SQL), so a private account reduces to exactly the owner match it had before 0019.
def account_scope_matches(model, user_id: int):
    return or_(model.user_id == user_id, model.pot_id == Account.pot_id)


# The same predicate for a caller that already holds the Account row and so needs no join — the
# ledger, which reads ONE account and binds its `opening_date` for exactly this reason.
#
# `pot_id is None` drops the pot branch rather than comparing against None, and the reason is a real
# trap: SQL's `NULL = NULL` is not true, but SQLAlchemy's `column == None` compiles to `IS NULL`, so
# `model.pot_id == None` would match every PRIVATE row in the table instead of none of them — the
# widest possible predicate, arrived at by writing what looks like the narrowest.
#
# ▸ That widening is NOT observable, and a mutation sweep proved it: every caller has already bounded
# the query to ONE account id, and a movement naming that account can only belong to its owner or to
# the pot that holds it. The extra `IS NULL` branch therefore adds no row that the account filter does
# not already exclude. The guard stays because the next caller may not be account-bounded, and this
# comment stands in for the test that cannot discriminate.
def account_scope_matches_bound(model, user_id: int, pot_id: int | None):
    if pot_id is None:
        return model.user_id == user_id
    return or_(model.user_id == user_id, model.pot_id == pot_id)


# The dual-scope predicate for a LIST over a stock table (`investments`, `accounts`): the caller's own
# private rows, plus the rows held by any of the pots they may see (X2). THE one copy of it, because two
# lists that must agree about what "shared" means are two things that can stop agreeing.
#
# `pot_ids` are resolved by the caller rather than reached for here, which is §21's measured decision at
# a different table: an `IN (ids)` predicate uses the pot_id index, while asking app_can_view_pot per row
# would evaluate the policy helper once per candidate. Empty — a solo user, or a private-only read —
# reduces the statement to exactly the owner match it ran before 0019.
#
# RLS still decides what is reachable at all: this narrows a policy-scoped read to the scope the caller
# asked for and can never widen one. Dropping the owner filter altogether would also be scoped correctly
# by the policy and is still the wrong shape, because the section a row is drawn under has to come from
# the same list of pot ids the sections themselves are built from.
#
# Deliberately NOT folded into apply_listing_filters, whose four other callers are entities with no
# `pot_id` column at all: a scope argument they could pass would describe a column they do not have.
def scope_filter(model, user_id: int, pot_ids: list[int], scope: ListScope):
    private = model.user_id == user_id
    if scope == ListScope.private or not pot_ids:
        return private
    shared = model.pot_id.in_(pot_ids)
    return shared if scope == ListScope.shared else or_(private, shared)


# Resolves a mapped sort request into an ORDER BY clause, or None when it names no mapped column —
# the single place `sort_by` → column → direction lives. An unmapped or absent value falls back to the
# caller's default order: the frontend picks the column from a typed union, so an unknown one is a
# hand-edited URL rather than something worth a 422.
def _resolve_sort(sort_by: str | None, sort_order: str, sort_columns: dict):
    sort_col = sort_columns.get(sort_by)
    if sort_col is None:
        return None
    return (desc if sort_order == "desc" else asc)(sort_col)


# Mapped sorting for an UNPAGINATED list, where a single clause is enough because no row has to stay
# on a stable page.
def apply_sort(stmt, sort_by: str | None, sort_order: str, *, sort_columns: dict, default_order):
    clause = _resolve_sort(sort_by, sort_order, sort_columns)
    return stmt.order_by(clause if clause is not None else default_order)


# Applies the shared list_by_user filtering to a select statement: ownership, the
# active-only filter (optionally widened by include_ids so listed archived rows that
# are still referenced stay visible), name search, and mapped sorting with a
# per-entity fallback order.
def apply_listing_filters(
    stmt,
    model,
    user_id: int,
    *,
    search: str | None,
    sort_by: str | None,
    sort_order: str,
    active_only: bool,
    include_ids: list[int] | None,
    sort_columns: dict,
    default_order,
):
    stmt = stmt.where(model.user_id == user_id)
    if active_only:
        if include_ids:
            stmt = stmt.where(or_(model.is_active.is_(True), model.id.in_(include_ids)))
        else:
            stmt = stmt.where(model.is_active.is_(True))
    if search:
        stmt = stmt.where(model.name.ilike(f"%{search}%"))
    return apply_sort(stmt, sort_by, sort_order, sort_columns=sort_columns, default_order=default_order)


# Mapped sorting for a PAGINATED list (expenses / income / investments), which needs one thing the
# unpaginated version doesn't: a tie-break. A whole page of rows can share one date or one category,
# and without a TOTAL order Postgres may repeat a row across pages or skip it entirely.
#
# `tie_break` is a sequence rather than a single clause because one column is not always enough. A list
# over one table is totally ordered by its id; the unioned expenses list spans two tables whose ids are
# each unique only within themselves, so it needs the scope alongside the id. Passing it explicitly is
# what keeps the rule in one place while letting each list state the key it actually has.
def apply_entry_sort(stmt, sort_by: str | None, sort_order: str, *, sort_columns: dict, default_order, tie_break):
    clause = _resolve_sort(sort_by, sort_order, sort_columns)
    if clause is None:
        return stmt.order_by(*default_order)
    return stmt.order_by(clause, *tie_break)
