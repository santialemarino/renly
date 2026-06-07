# App/server request hardening middleware (SEC-12 — the body-size half).

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Max accepted request body. The API only takes small JSON bodies (no uploads), so 1 MiB is generous.
MAX_REQUEST_BODY_BYTES = 1 * 1024 * 1024


# Rejects oversized request bodies with 413. A declared Content-Length over the cap is refused up
# front; bodies without a Content-Length (e.g. chunked transfer-encoding) are counted as they stream
# in and refused once they exceed the cap, so the limit can't be bypassed by omitting the header.
# Pure-ASGI (not BaseHTTPMiddleware) and mounted innermost so the streaming HTTPException is re-raised
# by FastAPI's body parsing straight into the 413 handler, with no middleware in between to wrap it.
class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: refuse an oversized declared Content-Length before reading any body.
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                declared: int | None = int(content_length)
            except ValueError:
                declared = None
            if declared is not None and declared > self.max_body_bytes:
                response = JSONResponse(status_code=413, content={"detail": "Request body too large."})
                await response(scope, receive, send)
                return

        received = 0

        # Counts bytes as the body streams in; raises once the cap is crossed. FastAPI re-raises this
        # HTTPException out of its body parsing, so it lands in the standard 413 response.
        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise HTTPException(status_code=413, detail="Request body too large.")
            return message

        await self.app(scope, limited_receive, send)
