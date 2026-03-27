from datetime import date as date_type

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.asset_price import AssetPriceResponse, RefreshPricesResponse
from app.services import asset_price_service

router = APIRouter(prefix="/asset-prices", tags=["asset-prices"])


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
