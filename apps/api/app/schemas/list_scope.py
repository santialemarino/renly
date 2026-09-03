# Response schemas shared by every scope-aware list endpoint (HTTP contract).
#
# One shape for four lists, because the sections they render are the same thing labelled by a different
# container: `/investments` and `/accounts` group by POT (the unit that has a value and an ownership
# split), `/expenses` and `/income` group by GROUP (a shared flow row carries a group and no pot). The
# fields a list does not group by are simply null, so one renderer draws all four.

from decimal import Decimal

from pydantic import BaseModel, Field


# One currency's contribution to a section total. Its own field rather than a formatted string, so the
# frontend formats it in the reader's locale — and never netted against another currency's.
class SectionTotalResponse(BaseModel):
    currency: str = Field(description="Currency code these rows are denominated in (ISO 4217).")
    amount: Decimal = Field(description="Sum of this section's rows in that currency.", max_digits=18, decimal_places=2)


# One labelled section of a scope-grouped list, totalled over the WHOLE filtered set rather than the
# requested page — a header figure that changed as the reader paged would answer a question nobody asked.
#
# `pot_name` is nullable because a group's default pot is deliberately unnamed (A4); the frontend
# supplies the fallback label, exactly as the dashboard's undivided-pot rows do. `group_name` is NOT
# nullable on a shared section: the copy names the group, and a null interpolated into copy fails by
# PRINTING rather than by raising.
#
# `can_write` is a property of the SECTION and not of its rows, and that is the honest place for it:
# write access is granted per (pot, member) and never per holding, so every row in one section carries
# the same answer. Stating it once also keeps the single-entity responses out of it — a row would
# otherwise have to carry a permission the endpoints returning one row never resolve.
class ListSectionResponse(BaseModel):
    scope: str = Field(description="'private' for the caller's own rows, 'shared' for a pot's or a group's.")
    pot_id: int | None = Field(default=None, description="Pot this section groups, on the lists grouped by pot.")
    pot_name: str | None = Field(default=None, description="That pot's name; null for a group's unnamed default pot.")
    group_id: int | None = Field(default=None, description="Group this section belongs to; null on the private section.")
    group_name: str | None = Field(default=None, description="That group's name; null only on the private section.")
    can_write: bool = Field(description="Whether the caller may change this section's rows. Always true on their own.")
    count: int = Field(description="How many rows the section holds across every page.")
    totals: list[SectionTotalResponse] = Field(
        default_factory=list,
        description="Per-currency sums of what the section's rows show. Empty where the rows carry no money column.",
    )
