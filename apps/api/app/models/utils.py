# Shared utilities for models.

from datetime import UTC, datetime


# Returns the current UTC time as a naive datetime (no tzinfo).
# Naive UTC is required because SQLModel maps `datetime` to TIMESTAMP WITHOUT TIME ZONE,
# and asyncpg rejects timezone-aware datetimes for that column type.
def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
