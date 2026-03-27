from datetime import date as date_type

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.investment import InvestmentCategory
from app.repositories import user_settings_repository
from app.schemas.asset_price import AssetPriceResponse, PriceLookupResponse, RefreshPricesResponse
from app.services import asset_price_service
from app.services import metrics_helpers as mh
from app.services.settings_service import DOLLAR_RATE_DEFAULT, SETTINGS_KEY_DOLLAR_RATE_PREFERENCE

router = APIRouter(prefix="/asset-prices", tags=["asset-prices"])


# Returns the price for a ticker on a specific date. Fetches from provider if not in DB.
# When convert_to is provided, converts the price to the target currency using the rate map.
@router.get("/{ticker}/lookup", response_model=PriceLookupResponse | None)
async def lookup_price(
    ticker: str,
    current_user: CurrentUser,
    session: SessionDep,
    date: date_type = Query(description="Price date."),
    category: InvestmentCategory = Query(description="Investment category (determines provider)."),
    convert_to: str | None = Query(default=None, description="Target currency for conversion."),
) -> PriceLookupResponse | None:
    price = await asset_price_service.get_or_fetch_price(session, ticker, category, date)
    if price is None:
        return None

    converted_price = None
    converted_currency = None

    if convert_to and convert_to != price.currency:
        row = await user_settings_repository.get_by_user_id(session, current_user.id)
        dp = DOLLAR_RATE_DEFAULT
        if row and row.settings:
            pref = row.settings.get(SETTINGS_KEY_DOLLAR_RATE_PREFERENCE)
            if isinstance(pref, str) and pref:
                dp = pref
        rate_map = await mh.get_rate_map(session, dp)
        if rate_map and mh.can_convert(price.currency, convert_to):
            converted_price = mh.convert_value(price.price, price.currency, convert_to, rate_map)
            converted_currency = convert_to

    return PriceLookupResponse(
        ticker=price.ticker,
        date=price.date,
        price=price.price,
        currency=price.currency,
        converted_price=converted_price,
        converted_currency=converted_currency,
        source=price.source,
    )


# Returns the latest stored price for a ticker.
@router.get("/{ticker}/latest", response_model=AssetPriceResponse | None)
async def get_latest_price(
    ticker: str,
    current_user: CurrentUser,
    session: SessionDep,
) -> AssetPriceResponse | None:
    price = await asset_price_service.get_latest_price(session, ticker)
    if price is None:
        return None
    return AssetPriceResponse.model_validate(price)


# Returns price history for a ticker with optional date range.
@router.get("/{ticker}", response_model=list[AssetPriceResponse])
async def get_price_history(
    ticker: str,
    current_user: CurrentUser,
    session: SessionDep,
    start_date: date_type | None = Query(default=None, description="Start date filter."),
    end_date: date_type | None = Query(default=None, description="End date filter."),
) -> list[AssetPriceResponse]:
    prices = await asset_price_service.get_price_history(session, ticker, start_date, end_date)
    return [AssetPriceResponse.model_validate(p) for p in prices]


# Triggers an on-demand price refresh for all ticker-linked investments.
@router.post("/refresh", response_model=RefreshPricesResponse, status_code=status.HTTP_202_ACCEPTED)
async def refresh_prices(
    current_user: CurrentUser,
    session: SessionDep,
) -> RefreshPricesResponse:
    count = await asset_price_service.refresh_all_prices(session)
    return RefreshPricesResponse(prices_stored=count)
