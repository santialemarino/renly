# The audit trail's own layer: what one entry records, what the group's activity read returns, and the
# one structural invariant that keeps the trail from quietly stopping short of the schema.
#
# Most of this is structural, because the failure modes are. An entity type nobody writes and a
# group-scoped table nobody audits look identical from inside the app — the feed simply never mentions
# them — and neither is a type error.

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import SQLModel

from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.shared_audit import AuditAction, AuditEntityType, SharedAuditEntry
from app.models.user import User
from app.services import shared_audit_service as svc

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
SEAT = GroupMember(id=100, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)
OTHER_SEAT = GroupMember(id=101, group_id=10, user_id=2, display_name="Ana", role=GroupMemberRole.member)
PLACEHOLDER = GroupMember(id=102, group_id=10, user_id=None, display_name="Leo", role=GroupMemberRole.member)

# Which entity type covers each group-scoped table. Declared rather than derived, because the mapping is
# a judgement — a split is audited through its parent expense, and a permission row through its pot —
# and the test below is what stops the judgement going stale.
AUDITED_BY = {
    "groups": AuditEntityType.group,
    "group_members": AuditEntityType.group_member,
    "group_invites": AuditEntityType.group_invite,
    "group_money_settings": AuditEntityType.group_money_settings,
    "pots": AuditEntityType.pot,
    "pot_member_permissions": AuditEntityType.pot,
    "pot_ownership_events": AuditEntityType.ownership_event,
    "shared_expenses": AuditEntityType.shared_expense,
    "shared_expense_splits": AuditEntityType.shared_expense,
    "shared_income": AuditEntityType.shared_income,
    "shared_income_splits": AuditEntityType.shared_income,
    "group_settlements": AuditEntityType.settlement,
}

# The three tables a group-scoped one is reachable through. `group_members` is here as an anchor even
# though it carries a user_id, because a seat is group state that happens to name an account.
_GROUP_ANCHORS = {"groups", "pots", "group_members"}


# Every table that belongs to a GROUP rather than to a user, derived from the schema itself.
#
# The derivation is the point: a table is group-scoped when it hangs off one of the three anchors AND
# has no user_id of its own. The second half is what keeps the dual-scope tables out — investments and
# accounts point at a pot too, but they carry an owner, so a private one is nobody's group business.
def _group_scoped_tables() -> set[str]:
    return {
        name
        for name, table in SQLModel.metadata.tables.items()
        if name in _GROUP_ANCHORS
        or ("user_id" not in table.columns and any(fk.column.table.name in _GROUP_ANCHORS for column in table.columns for fk in column.foreign_keys))
    }


class TestCoverage:
    def test_every_group_scoped_table_is_covered_by_an_entity_type(self):
        # The enumerated list IS the invariant: adding a shared table and forgetting to audit it is
        # invisible from inside the app, because the feed simply never mentions it.
        # The trail itself is excluded — auditing the audit is a loop, and its rows are immutable.
        assert _group_scoped_tables() - set(AUDITED_BY) - {"shared_audit_log"} == set()

    def test_the_map_cannot_rot(self):
        # The other direction: a name here that is no longer a table reads as coverage of nothing.
        assert set(AUDITED_BY) <= set(SQLModel.metadata.tables)

    def test_every_entity_type_covers_a_real_table(self):
        # And a third: an entity type nobody writes would pass both tests above while producing a
        # sentence the web has to translate for an act that never happens.
        assert set(AUDITED_BY.values()) == set(AuditEntityType)

    def test_the_derivation_excludes_the_dual_scope_tables(self):
        # Proving the derivation discriminates rather than merely returning what the map already says.
        # These four point at a pot and are NOT group-scoped: they carry an owner, so a private row is
        # nobody's group business. If the user_id half of the rule were dropped they would appear here,
        # and the first test would fail — which is what makes it a test rather than a restatement.
        assert _group_scoped_tables() & {"investments", "accounts", "transfers", "investment_snapshots"} == set()


class TestRecord:
    @pytest.mark.asyncio
    async def test_it_writes_the_act_and_flushes(self, monkeypatch):
        session = AsyncMock()
        created = MagicMock()
        monkeypatch.setattr(svc.shared_audit_repository, "create", created)

        await svc.record(
            session,
            group_id=10,
            actor=USER,
            entity_type=AuditEntityType.pot,
            action=AuditAction.holdings_added,
            entity_id=5,
            pot_id=5,
            payload={"pot": "Depto"},
        )

        entry = created.call_args.args[1]
        assert (entry.group_id, entry.actor_user_id, entry.entity_id, entry.pot_id) == (10, USER.id, 5, 5)
        assert (entry.entity_type, entry.action) == (AuditEntityType.pot, AuditAction.holdings_added)
        assert entry.payload == {"pot": "Depto"}
        # Flushed rather than left to the commit, which is the whole ordering rule: an entry recorded
        # before a self-revocation has to reach the database while the writer is still allowed to write
        # it, or its own policy refuses the record of the act.
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_it_never_commits(self, monkeypatch):
        # The opposite of notification dispatch, and deliberately so: a notification is a side-effect of
        # something that already happened, while an entry is part of the same fact — so it must not
        # survive a write that rolled back, nor go missing from one that did not.
        session = AsyncMock()
        monkeypatch.setattr(svc.shared_audit_repository, "create", MagicMock())
        await svc.record(session, group_id=10, actor=USER, entity_type=AuditEntityType.group, action=AuditAction.created)
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_missing_actor_is_recorded_as_nobody(self, monkeypatch):
        created = MagicMock()
        monkeypatch.setattr(svc.shared_audit_repository, "create", created)
        await svc.record(AsyncMock(), group_id=10, actor=None, entity_type=AuditEntityType.group, action=AuditAction.created)
        assert created.call_args.args[1].actor_user_id is None


def _entry(**over) -> SharedAuditEntry:
    defaults = dict(
        id=1,
        group_id=10,
        actor_user_id=USER.id,
        entity_type=AuditEntityType.pot,
        entity_id=5,
        action=AuditAction.created,
        pot_id=5,
        payload={"pot": "Depto"},
        created_at=datetime(2026, 9, 4, 12, 0, 0),
    )
    return SharedAuditEntry(**{**defaults, **over})


class TestListActivity:
    @pytest.mark.asyncio
    async def test_membership_is_required_before_anything_is_read(self, monkeypatch):
        # Without this a stranger gets an empty list, which is itself an answer: it says a group with
        # that id exists. Every other group read gives the same 404 either way.
        from app.domain import NotFoundError
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_member", AsyncMock(side_effect=NotFoundError("Group not found")))
        listed = AsyncMock()
        monkeypatch.setattr(svc.shared_audit_repository, "list_by_group", listed)
        with pytest.raises(NotFoundError):
            await svc.list_activity(AsyncMock(), 10, USER, limit=20)
        listed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_limit_is_capped_however_much_is_asked_for(self, monkeypatch):
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, SEAT)))
        listed = AsyncMock(return_value=[])
        monkeypatch.setattr(svc.shared_audit_repository, "list_by_group", listed)
        monkeypatch.setattr(svc.group_repository, "list_members", AsyncMock(return_value=[]))
        await svc.list_activity(AsyncMock(), 10, USER, limit=5000)
        assert listed.await_args.kwargs["limit"] == svc.MAX_ACTIVITY_PAGE_SIZE

    @pytest.mark.asyncio
    async def test_actor_names_come_from_the_roster(self, monkeypatch):
        """Not from `users`, and that is not a preference.

        The users policy is an owner match, so a request session can read exactly one row — its own —
        and every other actor would come back nameless. The roster is the right source anyway: it is
        what every other group surface names people by, and it keeps a REMOVED member's seat.
        """
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(
            svc.shared_audit_repository,
            "list_by_group",
            AsyncMock(return_value=[_entry(actor_user_id=OTHER_SEAT.user_id), _entry(id=2, actor_user_id=None)]),
        )
        roster = AsyncMock(return_value=[SEAT, OTHER_SEAT, PLACEHOLDER])
        monkeypatch.setattr(svc.group_repository, "list_members", roster)

        rows = await svc.list_activity(AsyncMock(), 10, USER, limit=20)

        assert [row.actor_name for row in rows] == ["Ana", None]
        # ONE roster read for the whole page, never a lookup per entry.
        roster.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_an_actor_whose_account_is_gone_reads_as_nobody(self, monkeypatch):
        # None rather than "", so the renderer says "someone" in the reader's own language instead of
        # leaving a hole in the middle of a sentence. actor_user_id is SET NULL, never cascaded, so the
        # record of what an account did to money other people share outlives it.
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(svc.shared_audit_repository, "list_by_group", AsyncMock(return_value=[_entry(actor_user_id=None)]))
        monkeypatch.setattr(svc.group_repository, "list_members", AsyncMock(return_value=[SEAT]))
        rows = await svc.list_activity(AsyncMock(), 10, USER, limit=20)
        assert rows[0].actor_name is None

    @pytest.mark.asyncio
    async def test_the_payload_and_the_pot_reach_the_response_untouched(self, monkeypatch):
        # The response carries structure, never prose: the web composes the sentence from
        # entity_type.action and interpolates the payload, so anything narrowed here is copy the reader
        # never gets. pot_id travels for the link.
        from app.services import group_service

        monkeypatch.setattr(group_service, "require_member", AsyncMock(return_value=(GROUP, SEAT)))
        monkeypatch.setattr(svc.shared_audit_repository, "list_by_group", AsyncMock(return_value=[_entry()]))
        monkeypatch.setattr(svc.group_repository, "list_members", AsyncMock(return_value=[SEAT]))
        rows = await svc.list_activity(AsyncMock(), 10, USER, limit=20)
        assert (rows[0].payload, rows[0].pot_id, rows[0].entity_id) == ({"pot": "Depto"}, 5, 5)
