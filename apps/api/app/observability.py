import logging

import sentry_sdk

from app.config import Settings

logger = logging.getLogger(__name__)


# Initializes Sentry error tracking when a DSN is configured (INFRA-5). A no-op when
# settings.sentry_dsn is unset, so local dev, tests, and CI send nothing. The FastAPI/Starlette
# integrations auto-enable, so unhandled request errors are captured without per-route wiring.
def init_sentry(app_settings: Settings) -> None:
    if not app_settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=app_settings.sentry_dsn,
        environment=app_settings.environment.value,
        # Don't attach request bodies / headers — this app handles financial data.
        send_default_pii=False,
        # Errors only by default; performance tracing stays off to keep the free tier light.
        traces_sample_rate=0.0,
    )
    logger.info("Sentry initialized (environment=%s).", app_settings.environment.value)
