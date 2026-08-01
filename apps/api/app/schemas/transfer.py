# Request/response schemas for transfer endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import RequestBase


# Body for POST /transfers.
class TransferCreate(RequestBase):
    from_account_id: int = Field(description="Account the money leaves.")
    to_account_id: int = Field(description="Account the money arrives in.")
    date: date_type = Field(description="Date the movement happened.")
    from_amount: Decimal = Field(description="Amount debited, in the source account's currency.", gt=0, max_digits=18, decimal_places=2)
    to_amount: Decimal | None = Field(
        default=None,
        description=(
            "Amount credited, in the destination account's currency. Omit within one currency (it mirrors "
            "from_amount); required when the two accounts differ in currency, where it records the rate actually used."
        ),
        gt=0,
        max_digits=18,
        decimal_places=2,
    )
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)


# Body for PUT /transfers/{id}. Partial update; only provided fields are changed.
class TransferUpdate(RequestBase):
    from_account_id: int | None = Field(default=None, description="Account the money leaves.")
    to_account_id: int | None = Field(default=None, description="Account the money arrives in.")
    date: date_type | None = Field(default=None, description="Date the movement happened.")
    from_amount: Decimal | None = Field(default=None, description="Amount debited.", gt=0, max_digits=18, decimal_places=2)
    to_amount: Decimal | None = Field(default=None, description="Amount credited.", gt=0, max_digits=18, decimal_places=2)
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)


# Response for a single transfer. from_currency / to_currency are denormalized from the two accounts so
# a client can render both sides without a second lookup.
#
# Deliberately no implied_rate field: the two amounts ARE the record of the rate, and any single derived
# number has to pick a direction that is only readable for one of them — buying dollars with pesos wants
# "1200 ARS per USD", selling them wants the reciprocal, and the same field cannot be both. Rendering the
# pair ("ARS 1,200.00 → USD 1.00") is unambiguous, and a client that wants a rate can divide with the
# direction it is presenting.
class TransferResponse(BaseModel):
    id: int = Field(description="Transfer id.")
    from_account_id: int = Field(description="Account the money left.")
    to_account_id: int = Field(description="Account the money arrived in.")
    from_account_name: str = Field(description="Source account name, for display.")
    to_account_name: str = Field(description="Destination account name, for display.")
    from_currency: str = Field(description="Source account currency (ISO 4217).")
    to_currency: str = Field(description="Destination account currency (ISO 4217).")
    date: date_type = Field(description="Date the movement happened.")
    from_amount: Decimal = Field(description="Amount debited, in the source currency.", max_digits=18, decimal_places=2)
    to_amount: Decimal = Field(description="Amount credited, in the destination currency.", max_digits=18, decimal_places=2)
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}


# Response for GET /transfers.
class TransferListResponse(BaseModel):
    items: list[TransferResponse] = Field(description="Transfers, newest first.")
    total: int = Field(description="Total transfers returned.")
