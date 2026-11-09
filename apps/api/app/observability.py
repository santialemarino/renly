import logging
import sys

import sentry_sdk
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
from uvicorn.logging import DefaultFormatter

from app.config import Settings
from app.rate_limit import CLIENT_IP_HEADER, INTERNAL_SECRET_HEADER

logger = logging.getLogger(__name__)

# The logger every module under app/ hangs from (each takes logging.getLogger(__name__)).
APP_LOGGER_NAME = "app"
# Uvicorn's own line shape ("INFO:     message"), with the logger name so a line says where it came from.
LOG_FORMAT = "%(levelprefix)s %(name)s: %(message)s"


# Writes to whatever sys.stderr is at the moment of each record rather than the stream that existed when
# the handler was built, the way logging's own last-resort handler does; a test runner that swaps stderr
# out and closes it then never leaves the handler writing to a closed file.
class _StderrHandler(logging.StreamHandler):
    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


# Gives the app's own loggers a handler and the configured level.
#
# Nothing else does: uvicorn configures only its own loggers, and without a handler Python's fallback
# prints WARNING and up, so every INFO line (the scheduler runs, and the console provider's emails with
# their verification, reset and invite links) used to vanish. Only the `app` logger is configured, never
# the root: the root would also turn on third-party INFO lines such as httpx's request log, whose URLs can
# carry a provider's API key. Records still propagate to the root, so pytest's caplog keeps seeing them.
# Idempotent: create_app runs once per test app and once per reload, and each call replaces the
# handler rather than stacking a second one that would print every line twice.
def configure_logging(app_settings: Settings) -> None:
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    for handler in [handler for handler in app_logger.handlers if isinstance(handler, _StderrHandler)]:
        app_logger.removeHandler(handler)
    handler = _StderrHandler()
    handler.setFormatter(DefaultFormatter(LOG_FORMAT))
    app_logger.addHandler(handler)
    app_logger.setLevel(app_settings.log_level)


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
        # Sentry keeps request headers it does not know to be sensitive, so the web server's shared
        # secret and the client IP it forwards are named here; the default lists still apply.
        event_scrubber=EventScrubber(denylist=[*DEFAULT_DENYLIST, CLIENT_IP_HEADER, INTERNAL_SECRET_HEADER]),
        # Errors only by default; performance tracing stays off to keep the free tier light.
        traces_sample_rate=0.0,
    )
    logger.info("Sentry initialized (environment=%s).", app_settings.environment.value)
