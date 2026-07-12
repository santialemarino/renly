# Base request model with automatic string normalization.
# All request schemas inherit from this to ensure consistent input handling.

from typing import Any

from pydantic import BaseModel, model_validator

from app.domain.currency import SUPPORTED_CURRENCIES, is_supported


# Base class for all request bodies. Strips whitespace from all strings.
# Optional string fields are converted to None when empty after stripping.
class RequestBase(BaseModel):
    # Strips every string value; empty optional strings become None.
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


# Reusable field validator for finance-entry currencies: normalizes the code and rejects
# anything outside the supported registry (app/domain/currency.py — the single source of
# truth). Attach with `field_validator("currency")(validate_supported_currency)`.
def validate_supported_currency(value: str | None) -> str | None:
    if value is None:
        return None
    code = value.upper()
    if not is_supported(code):
        valid = ", ".join(sorted(SUPPORTED_CURRENCIES))
        raise ValueError(f"Unsupported currency '{value}'. Use one of: {valid}.")
    return code
