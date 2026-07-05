# Response schemas for the restore-from-export flow (preview + confirm).

from pydantic import BaseModel, Field


# Per-entity outcome in a restore preview (counts that will happen) or result (counts that happened).
class RestoreEntityStat(BaseModel):
    entity: str = Field(description="Export entity name (e.g. investments).")
    restore: int = Field(description="Rows that will be (preview) or were (confirm) inserted.")
    skipped_unresolved: int = Field(description="Rows skipped because a required parent row could not be resolved or the row was invalid.")


# Response for POST /restore/preview. A dry run; nothing is written.
class RestorePreviewResponse(BaseModel):
    recognized: bool = Field(description="Whether the file is a recognized Renly export.")
    exported_at: str | None = Field(default=None, description="When the source export was produced, if the file records it.")
    entities: list[RestoreEntityStat] = Field(description="Per-entity restore plan (in insertion order).")
    skipped_entities: list[str] = Field(description="Exported sections this flow does not restore (reported for transparency).")


# Response for POST /restore. Reports what was written.
class RestoreResultResponse(BaseModel):
    restored: int = Field(description="Total rows inserted across all entities.")
    skipped_unresolved: int = Field(description="Total rows skipped due to an unresolved parent or invalid data.")
    entities: list[RestoreEntityStat] = Field(description="Per-entity result (in insertion order).")
