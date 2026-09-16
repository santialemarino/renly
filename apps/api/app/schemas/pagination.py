# The page fields every paginated list response carries (HTTP contract).
#
# Stated once rather than on each list schema, because they are one contract: a client that can read a
# page of expenses can read a page of anything. Each entity's list response inherits this and declares
# its own `items` (and whatever else that list needs — a display currency, its scope sections), so the
# three page fields cannot drift apart across the endpoints that serve them.

from pydantic import BaseModel, Field


# Page metadata shared by every paginated list endpoint. `total` counts the WHOLE matching set rather
# than the page, which is what lets a client draw a pager at all.
class PaginatedResponse(BaseModel):
    total: int = Field(description="Total matching rows across every page.")
    page: int = Field(description="Current page (1-based).")
    page_size: int = Field(description="Rows per page.")
