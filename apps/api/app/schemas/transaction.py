# Request/response schemas for transaction endpoints (HTTP contract).

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.investment import Currency
from app.models.transaction import TransactionType


# Body for POST /investments/{id}/transactions.
class TransactionCreate(BaseModel):
    date: date_type = Field(description="Transaction date.")
    amount: Decimal = Field(description="Amount (positive).", max_digits=18, decimal_places=2)
    currency: Currency = Field(description="Amount currency.")
    type: TransactionType = Field(description="Transaction kind (buy, sell, deposit, withdrawal).")
    notes: str | None = Field(default=None, description="Optional notes.")


# Body for PUT /investments/{id}/transactions/{tx_id}. Partial update; only updates provided fields.
class TransactionUpdate(BaseModel):
    date: date_type | None = Field(default=None, description="Transaction date.")
    amount: Decimal | None = Field(default=None, description="Amount (positive).", max_digits=18, decimal_places=2)
    currency: Currency | None = Field(default=None, description="Amount currency.")
    type: TransactionType | None = Field(default=None, description="Transaction kind.")
    notes: str | None = Field(default=None, description="Optional notes.")


# Response for GET list, GET one, POST and PUT.
class TransactionResponse(BaseModel):
    id: int = Field(description="Transaction id.")
    investment_id: int = Field(description="Parent investment id.")
    date: date_type = Field(description="Transaction date.")
    amount: Decimal = Field(description="Amount.")
    currency: Currency = Field(description="Amount currency.")
    type: TransactionType = Field(description="Transaction kind.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")

    model_config = {"from_attributes": True}
