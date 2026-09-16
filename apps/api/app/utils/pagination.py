# Bounds on how many rows one request may read (SEC-11).
#
# Every list this API serves was written for a single user's data and returned every matching row. At
# one user that is correct and cheap; at a thousand it is a denial of service that any authenticated
# caller can trigger by owning a lot of history. Two instruments close it, and which one a list gets
# depends on whether its row count grows with TIME or only with what the user chose to create:
#
#   * A list that grows without bound — a ledger, a history, an admin list spanning every user — is
#     PAGINATED. The caller asks for a page and is told the total, so nothing becomes unreachable.
#   * A list bounded by the user's own behaviour — their accounts, cards, collections, pots — is
#     CAPPED at MAX_LIST_ROWS. No contract change, no pager for a list that will never fill one page,
#     and a ceiling far above any plausible holding so the truncation never happens in practice.
#
# `tests/unit/test_list_endpoint_bounds.py` is what keeps that a closed set rather than a good
# intention: it reads the routers and fails on any list endpoint classified as neither.

import logging

from sqlalchemy import Select

logger = logging.getLogger(__name__)

# Rows per page when the caller does not ask. The number /expenses, /income and the account ledger
# already served, so three of the four lists paginated before SEC-11 keep their behaviour exactly;
# /investments moved 20 -> 25 to join them, which is the whole point of there being one number.
DEFAULT_PAGE_SIZE = 25

# The largest page any endpoint will serve. A caller asking for more gets a 422 from the Query
# constraint rather than a silently smaller page — an honest refusal beats a response that disagrees
# with the request with no signal.
MAX_PAGE_SIZE = 100

# The ceiling on a capped (unpaginated) list. Chosen to sit far above any plausible holding — the
# busiest dev account has 13 investments and 3 cards — so it bounds the query without ever being the
# reason a user cannot see a row.
MAX_LIST_ROWS = 500


# Applies a page window to a statement. The caller owns the ORDER, which must be total (add an id
# tiebreak to any low-cardinality sort): without one Postgres may repeat a row across pages or skip it.
def apply_page(stmt: Select, page: int, page_size: int) -> Select:
    return stmt.offset((page - 1) * page_size).limit(page_size)


# Applies an optional row ceiling to a statement. `None` means unbounded, and that is the shape every
# read feeding a COMPUTATION has to keep: six of the nine capped lists share their query with the
# dashboard or the payments calendar, which SUM it, and a truncated sum is a wrong number rather than a
# short list. So the ceiling is opt-in per call site, passed by the list endpoint and by nothing else.
def apply_limit(stmt: Select, limit: int | None) -> Select:
    return stmt if limit is None else stmt.limit(limit)


# Returns the rows, warning when the ceiling actually bit. Capping is silent by construction, so this
# is the only signal that a list the app assumes is small has stopped being small — which is the point
# at which it needs pagination rather than a bigger number here.
#
# Takes the limit rather than comparing against MAX_LIST_ROWS, so the UNBOUNDED read of the same query
# — the one the dashboard sums — cannot trip the warning by legitimately holding 500 rows.
def capped[T](rows: list[T], limit: int | None, what: str) -> list[T]:
    if limit is not None and len(rows) >= limit:
        logger.warning("Capped list %s returned %d rows, its ceiling — it may be truncated.", what, len(rows))
    return rows
