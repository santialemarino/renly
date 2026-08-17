from sqlalchemy import asc, desc, or_


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
# unpaginated version doesn't: an id tie-break. A whole page of rows can share one date or one
# category, and without a total order Postgres may repeat a row across pages or skip it entirely. The
# tie-break is derived from the model rather than passed in, so a caller cannot forget it.
def apply_entry_sort(stmt, model, sort_by: str | None, sort_order: str, *, sort_columns: dict, default_order):
    clause = _resolve_sort(sort_by, sort_order, sort_columns)
    if clause is None:
        return stmt.order_by(*default_order)
    return stmt.order_by(clause, model.id.desc())
