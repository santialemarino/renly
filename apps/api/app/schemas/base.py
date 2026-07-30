# Base request model with automatic string normalization.
# All request schemas inherit from this to ensure consistent input handling.

from typing import Any

from pydantic import BaseModel, model_validator

from app.domain.currency import SUPPORTED_CURRENCIES, is_supported
from app.domain.reconciliation import SYSTEM_EXPENSE_CATEGORIES, SYSTEM_INCOME_CATEGORIES
from app.models.expense_entry import ExpenseCategory
from app.models.income_entry import IncomeCategory


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


# Reusable field validator rejecting a reserved, system-generated expense category on a request
# (app/domain/reconciliation.py owns the set). Only a reconciliation writes those values, and it does
# so through the repositories, never through a request schema — so accepting one here would let a user
# author a row that is indistinguishable from a computed true-up. Attach with
# `field_validator("category")(validate_user_pickable_expense_category)`.
def validate_user_pickable_expense_category(value: ExpenseCategory | None) -> ExpenseCategory | None:
    if value is not None and value in SYSTEM_EXPENSE_CATEGORIES:
        valid = ", ".join(sorted(c.value for c in ExpenseCategory if c not in SYSTEM_EXPENSE_CATEGORIES))
        raise ValueError(f"Category '{value.value}' is system-generated and cannot be set directly. Use one of: {valid}.")
    return value


# The income counterpart of validate_user_pickable_expense_category.
def validate_user_pickable_income_category(value: IncomeCategory | None) -> IncomeCategory | None:
    if value is not None and value in SYSTEM_INCOME_CATEGORIES:
        valid = ", ".join(sorted(c.value for c in IncomeCategory if c not in SYSTEM_INCOME_CATEGORIES))
        raise ValueError(f"Category '{value.value}' is system-generated and cannot be set directly. Use one of: {valid}.")
    return value
