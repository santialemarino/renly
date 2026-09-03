# The scope split every list page renders (X2): the rows the caller owns privately, and the rows a pot
# they co-own owns instead. Pure — no database, no HTTP — so the grouping and its ordering are testable
# without either.
#
# THE governing rule, and it is not negotiable: a scope selection FILTERS, it is never a mode. Grouping
# is what the list does by default; asking for one scope narrows which rows are read. A persistent mode
# would let somebody misread every number on screen, because the page would keep showing a subset while
# looking like the whole — grouping cannot, because every section is on screen at once.
#
# A section's total is the sum of what its own rows SHOW, per currency, and a count where the rows show
# no money at all (`/investments` has no value column). Nothing here converts: per-currency totals need
# no rate, cannot be skipped for want of one, and never state a figure the visible rows fail to add up
# to. Balances not netting across currencies is the same rule the group hub's balances already keep.

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal(0)

# The two things a row on a scope-aware list can be. Kept as literals rather than an enum because they
# travel on the wire and the two unioned flow lists already spell them exactly this way.
SCOPE_PRIVATE = "private"
SCOPE_SHARED = "shared"


# What a `scope` query param may ask for. `all` is the grouped default and the only value that shows
# both scopes at once; the other two narrow the read to one of them.
class ListScope(StrEnum):
    all = "all"
    private = "private"
    shared = "shared"


# One currency's contribution to a section total. Never netted against another currency's, and always
# rendered with its code beside it, because a bare 120 next to a bare 90,000 leaves the reader guessing.
@dataclass(frozen=True)
class SectionTotal:
    currency: str
    amount: Decimal


# One labelled section of a scope-grouped list, totalled over the WHOLE filtered set rather than the
# page — a total that changed as the reader paged would be answering a question nobody asked.
#
# `key` is the container the section is grouped by: a POT id on `/investments` and `/accounts` (the pot
# is the unit that has a value and an ownership split, so a per-group total would sum across pots whose
# ownership differs) and a GROUP id on `/expenses` and `/income` (a shared flow row carries a group and
# no pot). `None` is the caller's own rows, and sorts first.
@dataclass(frozen=True)
class ListSection:
    key: int | None
    count: int
    totals: list[SectionTotal]


# Where a section sorts: the caller's own rows first, then each container by id ascending.
#
# Ascending id is creation order, and it is a real choice rather than an accident: the list queries
# order their rows by the same column with NULLS FIRST, so the sections and the rows they label cannot
# disagree about which comes first. Sorting by name instead would need a join the row query does not
# have, and would then have to be kept in step with it.
def _section_order(key: int | None) -> tuple[int, int]:
    return (0, 0) if key is None else (1, key)


# Folds `(key, currency, amount, count)` aggregate rows into ordered sections.
#
# One function for both mechanics: a paginated list feeds it a grouped query's rows, while `/accounts`
# — which is unpaginated, so the response already IS the whole filtered set — feeds it one tuple per
# account. The renderer therefore has one input shape either way.
#
# A null `currency` means the rows carry no money to total (`/investments`), and the section then
# reports its count alone. Counts are summed across a key's currency groups because a row belongs to
# exactly one currency, so the groups partition the key's rows.
def build_sections(rows: Iterable[tuple[int | None, str | None, Decimal | None, int]]) -> list[ListSection]:
    counts: dict[int | None, int] = {}
    totals: dict[int | None, dict[str, Decimal]] = {}
    for key, currency, amount, count in rows:
        counts[key] = counts.get(key, 0) + count
        if currency is not None and amount is not None:
            bucket = totals.setdefault(key, {})
            bucket[currency] = bucket.get(currency, ZERO) + amount
    return [
        ListSection(
            key=key,
            count=counts[key],
            totals=[SectionTotal(currency=code, amount=amount) for code, amount in sorted(totals.get(key, {}).items())],
        )
        for key in sorted(counts, key=_section_order)
    ]
