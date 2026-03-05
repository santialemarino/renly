from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class InvestmentCategory(StrEnum):
    cedears = "cedears"
    fci = "fci"
    dollars = "dollars"
    bonds = "bonds"
    stocks = "stocks"
    crypto = "crypto"
    real_estate = "real_estate"
    term_deposit = "term_deposit"
    other = "other"


class Currency(StrEnum):
    ARS = "ARS"
    USD = "USD"


class Investment(SQLModel, table=True):
    __tablename__ = "investments"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    name: str = Field(max_length=255)
    category: InvestmentCategory
    base_currency: Currency
    broker: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
