# Service-wide helpers: small pieces of orchestration that more than one service needs and none of them
# owns. Nothing feature-specific belongs here — that goes in a `<feature>_helpers.py` beside its service.

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.list_scope import SCOPE_PRIVATE, SCOPE_SHARED, ListSection
from app.repositories import group_repository
from app.schemas.list_scope import ListSectionResponse, SectionTotalResponse
from app.services.pot_service import PotScope


# The names of the given groups, keyed by id, in one query. Four list endpoints label a row or a section
# with its group's name, and resolving it in one place is what keeps them from each holding a copy.
async def group_names_by_id(session: AsyncSession, group_ids: set[int]) -> dict[int, str]:
    if not group_ids:
        return {}
    return {group.id: group.name for group in await group_repository.get_by_ids(session, sorted(group_ids))}


# The per-currency totals of one section, as the wire carries them.
def _totals(section: ListSection) -> list[SectionTotalResponse]:
    return [SectionTotalResponse(currency=total.currency, amount=total.amount) for total in section.totals]


# The caller's own rows as a section: no container, so every naming field is null.
def _private_section(section: ListSection) -> ListSectionResponse:
    return ListSectionResponse(scope=SCOPE_PRIVATE, can_write=True, count=section.count, totals=_totals(section))


# The sections of a list grouped by POT (`/investments`, `/accounts`), labelled from the pot catalogue.
#
# A section whose pot is not in the catalogue is DROPPED rather than rendered unlabelled, and it is
# unreachable by construction because the row query filters on exactly the catalogue's pot ids — the
# same reasoning that has list_visible_scopes drop a pot whose group it cannot name. Dropping the
# section rather than inventing a label is the fail-closed direction: a header nobody can read is worse
# than rows that were never returned.
def pot_sections(sections: list[ListSection], scopes: list[PotScope]) -> list[ListSectionResponse]:
    by_pot = {scope.pot_id: scope for scope in scopes}
    responses: list[ListSectionResponse] = []
    for section in sections:
        if section.key is None:
            responses.append(_private_section(section))
            continue
        scope = by_pot.get(section.key)
        if scope is None:
            continue
        responses.append(
            ListSectionResponse(
                scope=SCOPE_SHARED,
                pot_id=scope.pot_id,
                pot_name=scope.name,
                group_id=scope.group_id,
                group_name=scope.group_name,
                can_write=scope.can_write,
                count=section.count,
                totals=_totals(section),
            )
        )
    return responses


# The sections of a list grouped by GROUP (`/expenses`, `/income`), labelled from the group names the
# caller already resolved. Dropped on a missing name for the reason above: the copy names the group.
def group_sections(sections: list[ListSection], names_by_group: dict[int, str]) -> list[ListSectionResponse]:
    responses: list[ListSectionResponse] = []
    for section in sections:
        if section.key is None:
            responses.append(_private_section(section))
            continue
        name = names_by_group.get(section.key)
        if name is None:
            continue
        responses.append(
            ListSectionResponse(
                scope=SCOPE_SHARED,
                group_id=section.key,
                group_name=name,
                # A shared FLOW row is never editable from the private list: its id belongs to
                # shared_expenses / shared_income, so a PUT to /expenses/{id} would land on whatever
                # private row happens to hold that number. 5b settled that as a refusal, and the
                # section says so once rather than each row re-deriving it.
                can_write=False,
                count=section.count,
                totals=_totals(section),
            )
        )
    return responses
