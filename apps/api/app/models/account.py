from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# Account type (cash, bank, wallet, other).
class AccountType(StrEnum):
    bank = "bank"
    cash = "cash"
    other = "other"
    wallet = "wallet"


# User-owned cash / bank account. The running balance is derived at query time (opening_balance plus
# linked income minus linked expenses/settlements plus/minus transfers), never stored. One currency
# per account; opening_date anchors the historical balance series. Soft-deleted via is_active.
class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=255, description="Account label (e.g. Caja de ahorro $, Efectivo).")
    type: AccountType = Field(sa_column=Column(SAEnum(AccountType, name="account_type"), nullable=False))
    currency: str = Field(max_length=3, description="Account currency (ISO 4217).")
    opening_balance: Decimal = Field(default=Decimal(0), max_digits=18, decimal_places=2, description="Balance at opening_date (the series anchor).")
    opening_date: date_type = Field(description="Date the opening_balance is measured at.")
    is_active: bool = Field(default=True, description="Whether the account is active.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
