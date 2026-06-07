# Rate limiting (SEC-1). In-memory slowapi limiter keyed per-user when authenticated,
# per-IP otherwise; a global default plus tighter per-route limits on auth endpoints.
# In-memory storage is fine for a single instance now; swap to Redis when scaling out.

from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

# Global default applied to every route via the middleware.
DEFAULT_LIMIT = "100/minute"
# Tight limits for credential-accepting auth routes (brute-force / account-flood defense).
LOGIN_LIMIT = "5/minute"
REGISTER_LIMIT = "3/hour"


# Rate-limit key: the authenticated user id when a valid bearer token is present, else the client IP.
# Decoding here is best-effort (no session_epoch check) — it only needs a stable identity to throttle by.
def rate_limit_key(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            sub = payload.get("sub")
            if sub is not None:
                return f"user:{sub}"
        except JWTError:
            pass
    return f"ip:{get_remote_address(request)}"


# headers_enabled adds X-RateLimit-* to responses and Retry-After on a 429 so clients can back off.
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[DEFAULT_LIMIT],
    headers_enabled=True,
    retry_after="delta-seconds",
)


# Returns a generic 429 (no internal detail leaked) and injects Retry-After / X-RateLimit headers.
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    response = JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again later."},
    )
    return request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)
