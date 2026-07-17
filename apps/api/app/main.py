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
    EmailNotVerifiedError,
    ExchangeRateUnavailableError,
    HasLinkedExpensesError,
    InstallmentLockedFieldError,
    InvalidCredentialsError,
    InvalidImportFileError,
    InvalidInviteError,
    InvalidRefreshTokenError,
    InvalidTokenError,
    InvestmentCurrencyMismatchError,
    InviteEmailTakenError,
    NotFoundError,
    PasswordBreachedError,
    PaymentPairingError,
    PlanRequiredError,
    ReconciliationPeriodMismatchError,
)
from app.middleware import BodySizeLimitMiddleware
from app.observability import init_sentry
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import (
    admin,
    api_keys,
    asset_prices,
    auth,
    credit_cards,
    dashboard,
    exchange_rates,
    expenses,
    feedback,
    finance_metrics,
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
    restore,
    snapshot_grid,
    subscriptions,
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


# Maps CurrencyChangeBlockedError to 409.
async def currency_change_blocked_handler(_request: Request, exc: CurrencyChangeBlockedError):
    return JSONResponse(status_code=409, content={"detail": exc.message})


# Maps HasLinkedExpensesError to 409.
async def has_linked_expenses_handler(_request: Request, exc: HasLinkedExpensesError):
    return JSONResponse(status_code=409, content={"detail": exc.message})


# Maps InstallmentLockedFieldError to 400 with the offending fields.
async def installment_locked_field_handler(_request: Request, exc: InstallmentLockedFieldError):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "code": exc.code, "fields": exc.fields},
    )


# Maps EmailNotVerifiedError to 403.
async def email_not_verified_handler(_request: Request, exc: EmailNotVerifiedError):
    return JSONResponse(status_code=403, content={"detail": exc.message})


# Maps InvalidCredentialsError to 401.
async def invalid_credentials_handler(_request: Request, exc: InvalidCredentialsError):
    return JSONResponse(status_code=401, content={"detail": exc.message})


# Maps InvalidImportFileError to 400.
async def invalid_import_file_handler(_request: Request, exc: InvalidImportFileError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Maps InvalidRefreshTokenError to 401.
async def invalid_refresh_token_handler(_request: Request, exc: InvalidRefreshTokenError):
    return JSONResponse(status_code=401, content={"detail": exc.message})


# Maps InvalidTokenError to 400.
async def invalid_token_handler(_request: Request, exc: InvalidTokenError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Maps InvalidInviteError to 403.
async def invalid_invite_handler(_request: Request, exc: InvalidInviteError):
    return JSONResponse(status_code=403, content={"detail": exc.message})


# Maps InvestmentCurrencyMismatchError to 400.
async def investment_currency_mismatch_handler(_request: Request, exc: InvestmentCurrencyMismatchError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Maps InviteEmailTakenError to 409.
async def invite_email_taken_handler(_request: Request, exc: InviteEmailTakenError):
    return JSONResponse(status_code=409, content={"detail": exc.message})


# Maps NotFoundError to 404.
async def not_found_exception_handler(_request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.message})


# Maps PasswordBreachedError to 400.
async def password_breached_handler(_request: Request, exc: PasswordBreachedError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Maps PaymentPairingError to 400.
async def payment_pairing_handler(_request: Request, exc: PaymentPairingError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Maps PlanRequiredError to 402.
async def plan_required_handler(_request: Request, exc: PlanRequiredError):
    return JSONResponse(status_code=402, content={"detail": exc.message})


# Maps ExchangeRateUnavailableError to 503.
async def exchange_rate_unavailable_handler(_request: Request, exc: ExchangeRateUnavailableError):
    return JSONResponse(status_code=503, content={"detail": exc.message})


# Maps ReconciliationPeriodMismatchError to 400.
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
    admin.router,
    api_keys.router,
    asset_prices.router,
    auth.router,
    credit_cards.router,
    dashboard.router,
    exchange_rates.router,
    expenses.router,
    feedback.router,
    finance_metrics.router,
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
    restore.router,
    settings_router.router,
    snapshot_grid.router,
    subscriptions.router,
)

_EXCEPTION_HANDLERS = {
    CurrencyChangeBlockedError: currency_change_blocked_handler,
    EmailNotVerifiedError: email_not_verified_handler,
    HasLinkedExpensesError: has_linked_expenses_handler,
    InstallmentLockedFieldError: installment_locked_field_handler,
    InvalidCredentialsError: invalid_credentials_handler,
    InvalidImportFileError: invalid_import_file_handler,
    InvalidInviteError: invalid_invite_handler,
    InvalidRefreshTokenError: invalid_refresh_token_handler,
    InvalidTokenError: invalid_token_handler,
    InvestmentCurrencyMismatchError: investment_currency_mismatch_handler,
    InviteEmailTakenError: invite_email_taken_handler,
    NotFoundError: not_found_exception_handler,
    PasswordBreachedError: password_breached_handler,
    PaymentPairingError: payment_pairing_handler,
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
