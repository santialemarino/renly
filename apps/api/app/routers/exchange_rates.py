# Endpoints for exchange rates (latest and historical).

from datetime import date as date_type

from fastapi import APIRouter, Query

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.exchange_rate import ExchangeRateResponse, LatestRatesResponse, SupportedCurrenciesResponse
from app.services import exchange_rate_service

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])


# Returns the latest rate for each pair.
@router.get("/latest", response_model=LatestRatesResponse)
async def get_latest_rates(
    current_user: CurrentUser,
    session: SessionDep,
) -> LatestRatesResponse:
    return await exchange_rate_service.get_latest_rates(session)


# Returns rates for a specific date. Pass date as YYYY-MM-DD.
@router.get("", response_model=list[ExchangeRateResponse])
async def get_rates_by_date(
    current_user: CurrentUser,
    session: SessionDep,
    date: date_type = Query(description="Date to fetch rates for (YYYY-MM-DD)."),
) -> list[ExchangeRateResponse]:
    return await exchange_rate_service.get_rates_by_date(session, date)


# Returns the currency codes with exchange-rate support. Drives the entry-form currency pickers.
@router.get("/currencies", response_model=SupportedCurrenciesResponse)
async def get_supported_currencies(
    current_user: CurrentUser,
) -> SupportedCurrenciesResponse:
    return exchange_rate_service.get_supported_currencies()
