# Base request model with automatic string normalization.
# All request schemas inherit from this to ensure consistent input handling.

from typing import Any

from pydantic import BaseModel, model_validator


# Base class for all request bodies. Strips whitespace from all strings.
# Optional string fields are converted to None when empty after stripping.
class RequestBase(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def clean_strings(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        for key, value in values.items():
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            field_info = cls.model_fields.get(key)
            if field_info and not field_info.is_required() and not stripped:
                values[key] = None
            else:
                values[key] = stripped
        return values
