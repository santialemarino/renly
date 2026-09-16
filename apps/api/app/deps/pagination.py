from typing import Annotated, NamedTuple

from fastapi import Depends, Query

from app.utils.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


# One page request: which page, and how many rows on it.
class PageParams(NamedTuple):
    page: int
    page_size: int


# Reads the page window every paginated list endpoint accepts (SEC-11).
#
# One dependency rather than the same two Query declarations on each router, so the default and the
# ceiling are stated once and cannot drift apart across endpoints. `le=MAX_PAGE_SIZE` is what refuses
# an oversized request: FastAPI rejects it with a 422 BEFORE the handler runs, so no endpoint has to
# decide what to do about it and none can silently serve a different page than the one asked for.
def _page_params(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Rows per page."),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


PageQuery = Annotated[PageParams, Depends(_page_params)]
