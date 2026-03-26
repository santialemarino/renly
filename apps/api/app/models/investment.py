from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


# Investment category (CEDEARs, FCI, dollars, bonds, etc.).
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


# Currency code.
class Currency(StrEnum):
    ARS = "ARS"
    USD = "USD"


# User-owned investment (account, asset, or position).
class Investment(SQLModel, table=True):
    __tablename__ = "investments"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner.")
    name: str = Field(max_length=255, description="Display name.")
    category: InvestmentCategory = Field(
        sa_column=Column(SAEnum(InvestmentCategory, name="investment_category"), nullable=False)
    )
    base_currency: str = Field(max_length=10, description="Reporting currency (ISO 4217 code).")
    ticker: str | None = Field(default=None, max_length=20, description="Symbol for auto-price-fetching (e.g. AAPL).")
    broker: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None)
    is_active: bool = Field(default=True, description="Whether to include in portfolio.")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
