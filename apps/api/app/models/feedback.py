from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# What a piece of feedback is about: a bug report, a feature idea, a question, or anything else.
class FeedbackCategory(StrEnum):
    bug = "bug"
    idea = "idea"
    question = "question"
    other = "other"


# A message sent from the in-app feedback form (SHELL-7). Stored for review in the admin area; an
# email notification to every admin is sent best-effort on submission (not persisted here). Owned by
# user_id (RLS); the admin list reads across users on the privileged session.
class Feedback(SQLModel, table=True):
    __tablename__ = "feedback"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, description="Author of the feedback.")
    category: FeedbackCategory = Field(sa_column=Column(SAEnum(FeedbackCategory, name="feedback_category"), nullable=False))
    message: str = Field(max_length=2000, description="Free-text feedback body.")
    created_at: datetime = Field(default_factory=utcnow)
