from datetime import datetime

from pydantic import BaseModel, Field

from app.models.feedback import FeedbackCategory
from app.schemas.base import RequestBase


# Body for POST /feedback.
class FeedbackCreate(RequestBase):
    category: FeedbackCategory = Field(description="What the feedback is about.")
    message: str = Field(min_length=1, max_length=2000, description="Free-text feedback body.")


# Response for POST /feedback (the submitter's own new row).
class FeedbackResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Feedback id.")
    category: FeedbackCategory = Field(description="What the feedback is about.")
    message: str = Field(description="Free-text feedback body.")
    created_at: datetime = Field(description="When the feedback was submitted (UTC).")


# Response for GET /feedback (admin review list); adds the author's email.
class FeedbackAdminResponse(FeedbackResponse):
    email: str = Field(description="Email of the user who submitted the feedback.")
