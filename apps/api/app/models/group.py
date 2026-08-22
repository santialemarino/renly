from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# What a group is for (household, couple, trip, flat, other). Labelling only — it changes no rule.
class GroupKind(StrEnum):
    couple = "couple"
    flat = "flat"
    household = "household"
    other = "other"
    trip = "trip"


# A set of people who share money, and the only multi-user entity in the schema: every other table is
# owned by one user_id, while a group's rows are reachable by each of its members. Deliberately carries
# who the people are and nothing about what they share, so the membership kernel stays entity-agnostic.
class Group(SQLModel, table=True):
    __tablename__ = "groups"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=255, description="Display name of the group.")
    kind: GroupKind = Field(sa_column=Column(SAEnum(GroupKind, name="group_kind"), nullable=False))
    created_by: int | None = Field(
        default=None,
        foreign_key="users.id",
        description="Who created the group (authorship, not ownership); NULL once that account is deleted.",
    )
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# Group administration only. An admin manages members and settings and gains NO additional visibility
# into any member's data — the membership policies never look at this column.
class GroupMemberRole(StrEnum):
    admin = "admin"
    member = "member"


# One seat in a group. user_id is NULL for a name-only placeholder — someone tracked in the group who
# has no Renly account; accepting an invite fills it in, so the seat's history needs no migration.
# Removing a member deactivates the seat rather than deleting it, keeping a real counterparty for the
# rows that reference it; is_active is part of the RLS predicate, so it also revokes access.
class GroupMember(SQLModel, table=True):
    __tablename__ = "group_members"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", description="Group this seat belongs to.")
    user_id: int | None = Field(default=None, foreign_key="users.id", description="Linked account; NULL for a name-only placeholder.")
    display_name: str = Field(max_length=255, description="How this person is shown in the group.")
    role: GroupMemberRole = Field(
        default=GroupMemberRole.member,
        sa_column=Column(SAEnum(GroupMemberRole, name="group_member_role"), nullable=False, server_default="member"),
    )
    is_active: bool = Field(default=True, description="False once the member is removed; the seat and its history stay.")
    joined_at: datetime | None = Field(default=None, description="When an account claimed this seat; NULL while it is a placeholder.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
