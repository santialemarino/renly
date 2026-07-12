from sqlalchemy import asc, desc, or_


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
    sort_col = sort_columns.get(sort_by or "") if sort_by else None
    order_fn = desc if sort_order == "desc" else asc
    order_clause = order_fn(sort_col) if sort_col is not None else default_order
    return stmt.order_by(order_clause)
