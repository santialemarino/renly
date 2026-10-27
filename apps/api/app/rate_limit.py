# Rate limiting (SEC-1). In-memory slowapi limiter keyed per-user when authenticated,
# per-IP otherwise; a global default plus tighter per-route limits on auth endpoints.
# In-memory storage is fine for a single instance now; swap to Redis when scaling out.

import hmac
import ipaddress

import jwt
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
# Tight limits on email-dispatching account routes (anti-abuse: each call can send an email).
VERIFY_EMAIL_LIMIT = "5/hour"
FORGOT_PASSWORD_LIMIT = "5/hour"
RESET_PASSWORD_LIMIT = "10/hour"
CHANGE_EMAIL_LIMIT = "5/hour"
# Admin invite create/resend (each sends an email; bounded per admin to cap outbound volume).
INVITE_LIMIT = "30/hour"
# Import endpoints (file upload + parse + bulk insert); bounded per user.
IMPORT_LIMIT = "20/hour"
# Restore endpoints (re-import a full export; heavier than a single-entity import); tighter per user.
RESTORE_LIMIT = "10/hour"
# Data export (reads every row the user owns, one full-table read per exported table); the read-side
# twin of restore, bounded per user at the same rate.
EXPORT_LIMIT = "10/hour"
# Feedback submissions (each can email the admins); bounded per user to cap outbound volume.
FEEDBACK_LIMIT = "10/hour"


# Headers the web server sends on its own API calls: the real client's IP, and the shared secret that
# proves the web server sent it. Both names are also scrubbed from Sentry events (app/observability.py).
CLIENT_IP_HEADER = "X-Renly-Client-IP"
INTERNAL_SECRET_HEADER = "X-Renly-Internal-Secret"


# Returns the client IP the web server forwarded, or None when the request does not prove it came
# from the web server. Honoured only when INTERNAL_API_SECRET is set and the request carries the same
# secret, compared in constant time so the secret cannot be recovered by timing; a value that is not
# an IP address is ignored rather than becoming a rate-limit key.
def forwarded_client_ip(request: Request) -> str | None:
    secret = settings.internal_api_secret
    if not secret:
        return None
    presented = request.headers.get(INTERNAL_SECRET_HEADER)
    if presented is None or not hmac.compare_digest(presented.encode(), secret.encode()):
        return None
    try:
        return str(ipaddress.ip_address(request.headers.get(CLIENT_IP_HEADER, "").strip()))
    except ValueError:
        return None


# Resolves the client IP to throttle by. A call from the web server that proves itself (see
# forwarded_client_ip) is keyed by the client it names. Otherwise, when trusted_proxy_count is 0 the
# app is reached directly, so the connection peer (get_remote_address) is the client. When proxies are
# in front, the peer is the nearest proxy and the real client sits in X-Forwarded-For; we count
# trusted_proxy_count hops in from the proxy-appended (right) end. Counting from the right is
# spoof-resistant: a client can prepend fake entries but can't control the ones appended by the
# trusted proxies after it.
def client_ip(request: Request) -> str:
    web_client = forwarded_client_ip(request)
    if web_client is not None:
        return web_client
    count = settings.trusted_proxy_count
    if count > 0:
        forwarded = request.headers.get("X-Forwarded-For", "")
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[max(0, len(parts) - count)]
    return get_remote_address(request)


# Rate-limit key: the authenticated user id when a valid bearer token is present, else the client IP.
# Decoding here is best-effort (no session_epoch check) — it only needs a stable identity to throttle by.
def rate_limit_key(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["exp"]})
            sub = payload.get("sub")
            if sub is not None:
                return f"user:{sub}"
        except jwt.InvalidTokenError:
            pass
    return f"ip:{client_ip(request)}"


# headers_enabled adds X-RateLimit-* to responses and Retry-After on a 429 so clients can back off.
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[DEFAULT_LIMIT],
    headers_enabled=True,
    retry_after="delta-seconds",
)


# Returns a generic 429 (no internal detail leaked) with the stable `rate_limited` code, and injects
# Retry-After / X-RateLimit headers; a client reads how long to wait from Retry-After.
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    response = JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again later.", "code": "rate_limited"},
    )
    return request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)
