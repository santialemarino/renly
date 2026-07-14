# Response schemas for the generic import flow (preview + confirm).

from pydantic import BaseModel, Field


# A target field columns can map to, with whether a value is required for a valid row.
class ImportFieldInfo(BaseModel):
    key: str = Field(description="Target field key (e.g. name, category).")
    required: bool = Field(description="Whether a value is required for the row to be valid.")


# One parsed data row in the preview, with its validation outcome.
class ImportPreviewRow(BaseModel):
    row_number: int = Field(description="1-based data row number (excludes the header row).")
    values: dict[str, str] = Field(description="Mapped source values keyed by target field.")
    status: str = Field(description="Row outcome: valid, invalid, or duplicate.")
    errors: list[str] = Field(default_factory=list, description="Validation errors for this row.")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings; the row still imports but the flagged value is dropped.")


# Row counts across the whole preview.
class ImportSummary(BaseModel):
    total: int = Field(description="Total data rows.")
    valid: int = Field(description="Rows that will be imported.")
    invalid: int = Field(description="Rows skipped due to validation errors.")
    duplicate: int = Field(description="Rows matching an existing or earlier row.")


# Response for POST /imports/{entity}/preview. A dry run; nothing is written.
class ImportPreviewResponse(BaseModel):
    columns: list[str] = Field(description="Detected header columns from the file.")
    fields: list[ImportFieldInfo] = Field(description="Target fields the columns can map to.")
    mapping: dict[str, str] = Field(description="Applied mapping: target field key → source column.")
    rows: list[ImportPreviewRow] = Field(description="Per-row preview with validation outcomes.")
    summary: ImportSummary = Field(description="Row counts by outcome.")


# Response for POST /imports/{entity}. Reports what was written.
class ImportResultResponse(BaseModel):
    created: int = Field(description="Rows inserted.")
    skipped_invalid: int = Field(description="Rows skipped due to validation errors.")
    skipped_duplicate: int = Field(description="Rows skipped as duplicates.")
