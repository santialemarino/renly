from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings  # noqa: F401 — ensures settings are validated on startup
from app.domain import (
    CurrencyChangeBlockedError,
    ExchangeRateUnavailableError,
    HasLinkedExpensesError,
    InstallmentLockedFieldError,
    NotFoundError,
    ReconciliationPeriodMismatchError,
)
from app.routers import (
    api_keys,
    asset_prices,
    auth,
    credit_cards,
    dashboard,
    exchange_rates,
    expenses,
    finance_metrics,
    groups,
    income,
    installments,
    investments,
    metrics,
    payment_obligations,
    payments_calendar,
    snapshot_grid,
    subscriptions,
)
from app.routers import settings as settings_router
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Renly API",
    description="Renly backend — personal finance (investments, metrics, exchange rates)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_keys.router)
app.include_router(asset_prices.router)
app.include_router(auth.router)
app.include_router(credit_cards.router)
app.include_router(dashboard.router)
app.include_router(exchange_rates.router)
app.include_router(expenses.router)
app.include_router(finance_metrics.router)
app.include_router(groups.router)
app.include_router(income.router)
app.include_router(installments.router)
app.include_router(investments.router)
app.include_router(metrics.router)
app.include_router(payment_obligations.router)
app.include_router(payments_calendar.router)
app.include_router(settings_router.router)
app.include_router(snapshot_grid.router)
app.include_router(subscriptions.router)


@app.exception_handler(CurrencyChangeBlockedError)
async def currency_change_blocked_handler(_request, exc: CurrencyChangeBlockedError):
    return JSONResponse(
        status_code=409,
        content={"detail": exc.message},
    )


@app.exception_handler(HasLinkedExpensesError)
async def has_linked_expenses_handler(_request, exc: HasLinkedExpensesError):
    return JSONResponse(
        status_code=409,
        content={"detail": exc.message},
    )


@app.exception_handler(InstallmentLockedFieldError)
async def installment_locked_field_handler(_request, exc: InstallmentLockedFieldError):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "code": exc.code, "fields": exc.fields},
    )


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(_request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message},
    )


@app.exception_handler(ExchangeRateUnavailableError)
async def exchange_rate_unavailable_handler(_request, exc: ExchangeRateUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": exc.message},
    )


@app.exception_handler(ReconciliationPeriodMismatchError)
async def reconciliation_period_mismatch_handler(_request, exc: ReconciliationPeriodMismatchError):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message},
    )


# Maps SQLAlchemy IntegrityError to a clean 409 (Phase 3, follow-up Item 8.2). The most
# common case in this codebase: a manual expense whose date exactly matches a scheduler-
# emitted row on the same plan, hitting the partial UNIQUE INDEX on (subscription_id, date)
# / (installment_id, date). The asyncpg layer surfaces `constraint_name` on the wrapped
# exception when available — falls back to substring matching on the message text so the
# handler still fires across driver / version variations.
@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request, exc: IntegrityError):
    orig = exc.orig
    constraint_name = getattr(orig, "constraint_name", None)
    msg_text = str(orig) if orig is not None else str(exc)

    def matches(name: str) -> bool:
        return constraint_name == name or name in msg_text

    if matches("idx_expense_entries_subscription_date"):
        return JSONResponse(
            status_code=409,
            content={"detail": "A charge is already recorded for this subscription on that date."},
        )
    if matches("idx_expense_entries_installment_date"):
        return JSONResponse(
            status_code=409,
            content={"detail": "A charge is already recorded for this installment on that date."},
        )
    return JSONResponse(
        status_code=409,
        content={"detail": "Conflict — a duplicate or constraint violation prevented the change."},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
