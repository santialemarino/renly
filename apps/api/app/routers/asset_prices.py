from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.deps.pagination import PageQuery
from app.models.investment import InvestmentCategory
from app.schemas.asset_price import AssetPriceListResponse, AssetPriceResponse, PriceLookupResponse, RefreshPricesResponse
from app.schemas.params import CURRENCY_CODE_MAX_LENGTH, TICKER_MAX_LENGTH
from app.services import asset_price_service

router = APIRouter(prefix="/asset-prices", tags=["asset-prices"])


# Returns the price for a ticker on a specific date. Fetches from provider if not in DB.
# When convert_to is provided, converts the price to the target currency using the rate map.
@router.get("/{ticker}/lookup", response_model=PriceLookupResponse | None)
async def lookup_price(
    ticker: Annotated[str, Path(max_length=TICKER_MAX_LENGTH, description="Asset symbol (e.g. AAPL, AAPL.BA).")],
    current_user: CurrentUser,
    session: SessionDep,
    date: date_type = Query(description="Price date."),
    category: InvestmentCategory = Query(description="Investment category (determines provider)."),
    convert_to: str | None = Query(default=None, max_length=CURRENCY_CODE_MAX_LENGTH, description="Target currency for conversion."),
) -> PriceLookupResponse | None:
    # Uppercase-normalize the display target so a lowercase code converts instead of silently
    # skipping (rate maps are uppercase-keyed), matching the DisplayCurrency dep on the read routes.
    convert_to = convert_to.upper() if convert_to else None
    return await asset_price_service.lookup_price(session, current_user.id, ticker, category, date, convert_to)


# Returns the latest stored price for a ticker.
@router.get("/{ticker}/latest", response_model=AssetPriceResponse | None)
async def get_latest_price(
    ticker: Annotated[str, Path(max_length=TICKER_MAX_LENGTH, description="Asset symbol (e.g. AAPL, AAPL.BA).")],
    current_user: CurrentUser,
    session: SessionDep,
) -> AssetPriceResponse | None:
    price = await asset_price_service.get_latest_price(session, ticker)
    if price is None:
        return None
    return AssetPriceResponse.model_validate(price)


# Returns one page of a ticker's price history, newest first, with optional date range.
@router.get("/{ticker}", response_model=AssetPriceListResponse)
async def get_price_history(
    ticker: Annotated[str, Path(max_length=TICKER_MAX_LENGTH, description="Asset symbol (e.g. AAPL, AAPL.BA).")],
    current_user: CurrentUser,
    session: SessionDep,
    page_query: PageQuery,
    start_date: date_type | None = Query(default=None, description="Start date filter."),
    end_date: date_type | None = Query(default=None, description="End date filter."),
) -> AssetPriceListResponse:
    return await asset_price_service.get_price_history(session, ticker, start_date, end_date, page=page_query.page, page_size=page_query.page_size)


# Triggers an on-demand price refresh for the caller's ticker-linked investments only.
@router.post("/refresh", response_model=RefreshPricesResponse, status_code=status.HTTP_202_ACCEPTED)
async def refresh_prices(
    current_user: CurrentUser,
    session: SessionDep,
) -> RefreshPricesResponse:
    count = await asset_price_service.refresh_user_prices(session, current_user.id)
    return RefreshPricesResponse(prices_stored=count)
