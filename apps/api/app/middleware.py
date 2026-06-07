# App/server request hardening middleware (SEC-12 — the body-size half).

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Max accepted request body. The API only takes small JSON bodies (no uploads), so 1 MiB is generous.
MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024


# Rejects oversized request bodies with 413 based on the declared Content-Length, before any handler runs.
class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            if declared is not None and declared > self.max_body_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request body too large."})
        return await call_next(request)
