import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.config import settings as default_settings
from app.domain import (
    CurrencyChangeBlockedError,
    ExchangeRateUnavailableError,
    HasLinkedExpensesError,
    InstallmentLockedFieldError,
    NotFoundError,
    PasswordBreachedError,
    PlanRequiredError,
    ReconciliationPeriodMismatchError,
)
from app.middleware import BodySizeLimitMiddleware
from app.rate_limit import limiter, rate_limit_exceeded_handler
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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


# --- Exception handlers ---


async def currency_change_blocked_handler(_request: Request, exc: CurrencyChangeBlockedError):
    return JSONResponse(status_code=409, content={"detail": exc.message})


async def has_linked_expenses_handler(_request: Request, exc: HasLinkedExpensesError):
    return JSONResponse(status_code=409, content={"detail": exc.message})


async def installment_locked_field_handler(_request: Request, exc: InstallmentLockedFieldError):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "code": exc.code, "fields": exc.fields},
    )


async def not_found_exception_handler(_request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.message})


async def password_breached_handler(_request: Request, exc: PasswordBreachedError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


async def plan_required_handler(_request: Request, exc: PlanRequiredError):
    return JSONResponse(status_code=402, content={"detail": exc.message})


async def exchange_rate_unavailable_handler(_request: Request, exc: ExchangeRateUnavailableError):
    return JSONResponse(status_code=503, content={"detail": exc.message})


async def reconciliation_period_mismatch_handler(_request: Request, exc: ReconciliationPeriodMismatchError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Maps SQLAlchemy IntegrityError to a clean 409 (Phase 3, follow-up Item 8.2). The most
# common case in this codebase: a manual expense whose date exactly matches a scheduler-
# emitted row on the same plan, hitting the partial UNIQUE INDEX on (subscription_id, date)
# / (installment_id, date). The asyncpg layer surfaces `constraint_name` on the wrapped
# exception when available — falls back to substring matching on the message text so the
# handler still fires across driver / version variations.
async def integrity_error_handler(_request: Request, exc: IntegrityError):
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


# Catch-all for any unhandled exception (SEC-8). Logs the trace server-side and returns a
# generic JSON body — never a stack trace — so production leaks nothing. Bypassed when debug
# is on (non-production), where Starlette returns its own traceback for local debugging.
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


_ROUTERS = (
    api_keys.router,
    asset_prices.router,
    auth.router,
    credit_cards.router,
    dashboard.router,
    exchange_rates.router,
    expenses.router,
    finance_metrics.router,
    groups.router,
    income.router,
    installments.router,
    investments.router,
    metrics.router,
    payment_obligations.router,
    payments_calendar.router,
    settings_router.router,
    snapshot_grid.router,
    subscriptions.router,
)

_EXCEPTION_HANDLERS = {
    CurrencyChangeBlockedError: currency_change_blocked_handler,
    HasLinkedExpensesError: has_linked_expenses_handler,
    InstallmentLockedFieldError: installment_locked_field_handler,
    NotFoundError: not_found_exception_handler,
    PasswordBreachedError: password_breached_handler,
    PlanRequiredError: plan_required_handler,
    ExchangeRateUnavailableError: exchange_rate_unavailable_handler,
    ReconciliationPeriodMismatchError: reconciliation_period_mismatch_handler,
    IntegrityError: integrity_error_handler,
    RateLimitExceeded: rate_limit_exceeded_handler,
    Exception: unhandled_exception_handler,
}


# Builds the FastAPI app. Docs and debug are locked down in production (SEC-7/8); CORS origins
# come from settings (SEC-9); rate limiting and the body-size limit are wired as middleware (SEC-1/12).
def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or default_settings
    docs_enabled = not app_settings.is_production

    app = FastAPI(
        title="Renly API",
        description="Renly backend — personal finance (investments, metrics, exchange rates)",
        version="0.1.0",
        lifespan=lifespan,
        debug=app_settings.debug,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.state.limiter = limiter

    for exc_type, handler in _EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exc_type, handler)

    for router in _ROUTERS:
        app.include_router(router)

    # Middleware added last is outermost: CORS wraps everything (so 4xx/5xx still get CORS headers
    # and preflight is handled before rate limiting), then rate limit, then the body-size limit
    # innermost. Body-size goes last/innermost on purpose: its streaming guard raises an
    # HTTPException that FastAPI's body parsing re-raises into the 413 handler, and keeping it next
    # to the route avoids any outer BaseHTTPMiddleware (e.g. SlowAPI) wrapping that exception.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Liveness probe; exempt from rate limiting so uptime checks never trip the limiter.
    @app.get("/health")
    @limiter.exempt
    def health():
        return {"status": "ok"}

    return app


app = create_app()
