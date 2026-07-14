from datetime import date as date_type

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.investment import InvestmentCategory
from app.schemas.asset_price import AssetPriceResponse, PriceLookupResponse, RefreshPricesResponse
from app.services import asset_price_service

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
    # Uppercase-normalize the display target so a lowercase code converts instead of silently
    # skipping (rate maps are uppercase-keyed), matching the DisplayCurrency dep on the read routes.
    convert_to = convert_to.upper() if convert_to else None
    return await asset_price_service.lookup_price(session, current_user.id, ticker, category, date, convert_to)


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


# Triggers an on-demand price refresh for the caller's ticker-linked investments only.
@router.post("/refresh", response_model=RefreshPricesResponse, status_code=status.HTTP_202_ACCEPTED)
async def refresh_prices(
    current_user: CurrentUser,
    session: SessionDep,
) -> RefreshPricesResponse:
    count = await asset_price_service.refresh_user_prices(session, current_user.id)
    return RefreshPricesResponse(prices_stored=count)
