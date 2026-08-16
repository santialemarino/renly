from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain.currency import SUPPORTED_CURRENCIES
from app.models.asset_price import AssetPrice
from app.models.investment import Currency, InvestmentCategory
from app.models.transaction import TransactionType
from app.schemas.card_settlement import CardSettlementCreate
from app.schemas.credit_card import CreditCardCreate, CreditCardUpdate
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.income import IncomeCreate
from app.schemas.installment import InstallmentCreate, InstallmentUpdate
from app.schemas.investment import InvestmentCreate, InvestmentUpdate
from app.schemas.payment_obligation import PaymentObligationCreate, PaymentObligationUpdate
from app.schemas.snapshot import SnapshotCreate
from app.schemas.subscription import SubscriptionCreate
from app.schemas.transaction import TransactionCreate
from app.services import asset_price_service, exchange_rate_service
from app.utils.metrics import RateLookup


# The supported set drives pickers and validators from one registry — pin the endpoint payload.
class TestSupportedCurrenciesSource:
    def test_returns_sorted_domain_registry(self):
        resp = exchange_rate_service.get_supported_currencies()
        assert resp.currencies == sorted(SUPPORTED_CURRENCIES)

    def test_supported_set_derives_from_currency_enum(self):
        # Single source of truth: the frozenset is derived from the Currency enum, so both agree.
        assert SUPPORTED_CURRENCIES == frozenset(c.value for c in Currency)
        assert set(SUPPORTED_CURRENCIES) == {"USD", "ARS", "BRL", "EUR", "GBP"}


# base_currency on investments uses the same supported-set allowlist as finance entries.
class TestInvestmentBaseCurrency:
    def test_create_accepts_supported_currency(self):
        body = InvestmentCreate(name="ETF", category=InvestmentCategory.stocks, base_currency="BRL")
        assert body.base_currency == "BRL"

    def test_create_normalizes_lowercase(self):
        body = InvestmentCreate(name="ETF", category=InvestmentCategory.stocks, base_currency="eur")
        assert body.base_currency == "EUR"

    def test_create_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            InvestmentCreate(name="ETF", category=InvestmentCategory.stocks, base_currency="JPY")

    def test_create_rejects_too_long_code(self):
        with pytest.raises(ValidationError):
            InvestmentCreate(name="ETF", category=InvestmentCategory.stocks, base_currency="TOOLONG")

    def test_update_allows_omitted_currency(self):
        assert InvestmentUpdate(name="Renamed").base_currency is None

    def test_update_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            InvestmentUpdate(base_currency="CLP")


# Snapshot/transaction rows can now be denominated in any supported currency (the widened Currency enum).
class TestInvestmentDenominationCurrency:
    def test_snapshot_accepts_new_currency(self):
        body = SnapshotCreate(date=date(2026, 1, 31), value=Decimal("100.00"), currency="BRL")
        assert body.currency == Currency.BRL

    def test_transaction_accepts_new_currency(self):
        body = TransactionCreate(date=date(2026, 1, 5), amount=Decimal("100.00"), currency="EUR", type=TransactionType.buy)
        assert body.currency == Currency.EUR

    def test_snapshot_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError):
            SnapshotCreate(date=date(2026, 1, 31), value=Decimal("100.00"), currency="JPY")


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

    def test_installment_create_normalizes_lowercase(self):
        body = InstallmentCreate(
            name="TV",
            total_amount=Decimal("120.00"),
            installment_amount=Decimal("10.00"),
            currency="usd",
            installments_count=12,
            start_date=date(2026, 1, 1),
        )
        assert body.currency == "USD"

    def test_installment_create_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            InstallmentCreate(
                name="TV",
                total_amount=Decimal("120.00"),
                installment_amount=Decimal("10.00"),
                currency="CLP",
                installments_count=12,
                start_date=date(2026, 1, 1),
            )

    def test_installment_update_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            InstallmentUpdate(currency="JPY")

    def test_payment_obligation_create_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            PaymentObligationCreate(
                name="Electricity",
                amount=Decimal("10.00"),
                currency="CHF",
                next_due_date=date(2026, 1, 1),
            )

    def test_payment_obligation_update_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            PaymentObligationUpdate(currency="CLP")

    # Cards and settlements were the last money schemas without the allowlist, which began to matter
    # once a card's currency had to MATCH its funding account's: the validator normalizes case too, so
    # an unnormalized "usd" card could never pair with a "USD" account.
    def test_credit_card_create_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            CreditCardCreate(name="Visa", closing_day=25, due_day=10, currency="CLP")

    def test_credit_card_create_normalizes_case(self):
        body = CreditCardCreate(name="Visa", closing_day=25, due_day=10, currency="usd")
        assert body.currency == "USD"

    def test_credit_card_update_rejects_unsupported_currency(self):
        with pytest.raises(ValidationError, match="Unsupported currency"):
            CreditCardUpdate(currency="CLP")

    def test_settlement_create_normalizes_case(self):
        body = CardSettlementCreate(date=date(2026, 8, 1), amount=Decimal("700"), currency="ars")
        assert body.currency == "ARS"


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
