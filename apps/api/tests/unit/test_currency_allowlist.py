from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain.currency import SUPPORTED_CURRENCIES
from app.models.asset_price import AssetPrice
from app.models.investment import InvestmentCategory
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.income import IncomeCreate
from app.schemas.subscription import SubscriptionCreate
from app.services import asset_price_service, exchange_rate_service
from app.utils.metrics import RateLookup


# The supported set drives pickers and validators from one registry — pin the endpoint payload.
class TestSupportedCurrenciesSource:
    def test_returns_sorted_domain_registry(self):
        resp = exchange_rate_service.get_supported_currencies()
        assert resp.currencies == sorted(SUPPORTED_CURRENCIES)


# 422 allowlist on the three finance-entry schemas (create + update variants).
class TestEntryCurrencyAllowlist:
    def test_expense_create_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            ExpenseCreate(date=date(2026, 1, 1), amount=Decimal("10.00"), currency="CLP")

    def test_expense_create_normalizes_lowercase(self):
        body = ExpenseCreate(date=date(2026, 1, 1), amount=Decimal("10.00"), currency="usd")
        assert body.currency == "USD"

    def test_expense_update_allows_omitted_currency(self):
        assert ExpenseUpdate(amount=Decimal("10.00")).currency is None

    def test_expense_update_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            ExpenseUpdate(currency="CLP")

    def test_income_create_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            IncomeCreate(date=date(2026, 1, 1), amount=Decimal("10.00"), currency="JPY")

    def test_subscription_create_accepts_supported_currency(self):
        body = SubscriptionCreate(
            name="Netflix",
            amount=Decimal("10.00"),
            currency="GBP",
            billing_cycle="monthly",
            next_billing_date=date(2026, 1, 1),
        )
        assert body.currency == "GBP"

    def test_subscription_create_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            SubscriptionCreate(
                name="Netflix",
                amount=Decimal("10.00"),
                currency="CHF",
                billing_cycle="monthly",
                next_billing_date=date(2026, 1, 1),
            )


# Asset-price lookup only reports converted_* when a rate actually existed.
class TestAssetPriceConversionHonesty:
    @pytest.mark.asyncio
    async def test_missing_rate_leaves_converted_null(self, monkeypatch):
        price = AssetPrice(ticker="AL30", date=date(2026, 1, 5), price=Decimal("100.00"), currency="ARS", source="test")
        monkeypatch.setattr(asset_price_service, "get_or_fetch_price", AsyncMock(return_value=price))
        empty_lookup = RateLookup(dollar_preference="mep", rates_by_pair={})
        monkeypatch.setattr(asset_price_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=empty_lookup))

        result = await asset_price_service.lookup_price(
            AsyncMock(), 1, "AL30", InvestmentCategory.government_bonds, date(2026, 1, 5), convert_to="USD"
        )

        assert result is not None
        assert result.price == Decimal("100.00")
        assert result.currency == "ARS"
        assert result.converted_price is None
        assert result.converted_currency is None
