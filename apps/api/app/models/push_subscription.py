from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# One browser that has agreed to receive web push for one account.
#
# Per BROWSER, not per user: a subscription is minted by the Push API against a particular browser
# profile on a particular device, so somebody with a laptop and a phone holds two rows and revoking one
# must not silence the other. `endpoint` is the push service's own URL for that browser and is globally
# unique, which is what makes re-subscribing an upsert rather than a duplicate.
#
# `p256dh` and `auth` are the SECRETS the payload is encrypted with — anyone holding the three together
# can send a notification to that browser as if they were Renly. They are therefore treated as
# credentials rather than data: never logged, never returned by any endpoint, and deliberately excluded
# from the data export (which is a portable file the user may email to themselves), exactly as
# auth_tokens and refresh_tokens are.
class PushSubscription(SQLModel, table=True):
    __tablename__ = "push_subscriptions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Account this browser is subscribed for.")
    endpoint: str = Field(unique=True, description="The push service URL for this browser; unique, so re-subscribing replaces.")
    p256dh: str = Field(max_length=255, description="Secret: the browser's public key for payload encryption.")
    auth: str = Field(max_length=255, description="Secret: the browser's auth secret for payload encryption.")
    user_agent: str | None = Field(
        default=None, max_length=500, description="What the browser called itself, so a person can tell their devices apart."
    )
    created_at: datetime = Field(default_factory=utcnow)
    last_used_at: datetime | None = Field(default=None, description="Last successful send; NULL until one succeeds.")
