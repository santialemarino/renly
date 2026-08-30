import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.config import settings as default_settings
from app.domain import DomainError
from app.middleware import BodySizeLimitMiddleware
from app.observability import init_sentry
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import (
    accounts,
    admin,
    api_keys,
    asset_prices,
    auth,
    collections,
    credit_cards,
    dashboard,
    exchange_rates,
    expenses,
    feedback,
    finance_metrics,
    group_invites,
    group_settlements,
    groups,
    imports,
    income,
    installments,
    investments,
    me,
    metrics,
    onboarding,
    payment_obligations,
    payments_calendar,
    pots,
    restore,
    shared_expenses,
    snapshot_grid,
    subscriptions,
    transfers,
)
from app.routers import settings as settings_router
from app.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


# Starts the background scheduler on app startup and shuts it down on exit.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


# --- Exception handlers ---


# Maps any DomainError to its status with a uniform {detail, code, **extra} body. The frontend maps
# `code` to a localized message and falls back to `detail` (English) for a code it doesn't map.
async def domain_error_handler(_request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code, **exc.extra})


# Handles every HTTPException uniformly, adding `code` when the exception carries one (CodedHTTPException)
# so router/deps/middleware exceptions join the same contract; a plain HTTPException stays {detail}.
# Faithfully preserves status_code + headers (e.g. the login 401's WWW-Authenticate).
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    content: dict = {"detail": exc.detail}
    code = getattr(exc, "code", None)
    if code is not None:
        content["code"] = code
    return JSONResponse(status_code=exc.status_code, content=content, headers=getattr(exc, "headers", None))


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
            content={"detail": "A charge is already recorded for this subscription on that date.", "code": "duplicate_subscription_charge"},
        )
    if matches("idx_expense_entries_installment_date"):
        return JSONResponse(
            status_code=409,
            content={"detail": "A charge is already recorded for this installment on that date.", "code": "duplicate_installment_charge"},
        )
    return JSONResponse(
        status_code=409,
        content={"detail": "Conflict — a duplicate or constraint violation prevented the change.", "code": "integrity_conflict"},
    )


# Catch-all for any unhandled exception (SEC-8). Logs the trace server-side and returns a
# generic JSON body — never a stack trace — so production leaks nothing. Bypassed when debug
# is on (non-production), where Starlette returns its own traceback for local debugging.
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


_ROUTERS = (
    accounts.router,
    admin.router,
    api_keys.router,
    asset_prices.router,
    auth.router,
    collections.router,
    credit_cards.router,
    dashboard.router,
    exchange_rates.router,
    expenses.router,
    feedback.router,
    finance_metrics.router,
    group_invites.router,
    group_settlements.router,
    groups.router,
    imports.router,
    income.router,
    installments.router,
    investments.router,
    me.router,
    metrics.router,
    onboarding.router,
    payment_obligations.router,
    payments_calendar.router,
    pots.router,
    restore.router,
    settings_router.router,
    shared_expenses.router,
    snapshot_grid.router,
    subscriptions.router,
    transfers.router,
)

_EXCEPTION_HANDLERS = {
    # One handler for the whole DomainError family (Starlette matches subclasses via the MRO).
    DomainError: domain_error_handler,
    # Adds `code` to any CodedHTTPException while leaving plain HTTPExceptions as {detail}.
    StarletteHTTPException: http_exception_handler,
    IntegrityError: integrity_error_handler,
    RateLimitExceeded: rate_limit_exceeded_handler,
    Exception: unhandled_exception_handler,
}


# Builds the FastAPI app. Docs and debug are locked down in production (SEC-7/8); CORS origins
# come from settings (SEC-9); rate limiting and the body-size limit are wired as middleware (SEC-1/12).
def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or default_settings
    # Wire up error tracking before the app is built (no-op unless a Sentry DSN is configured).
    init_sentry(app_settings)
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
