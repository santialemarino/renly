# HTTP-layer exception carrying a stable `code`, so the router/deps/middleware exceptions that don't
# map to a domain error (login, admin gate, request-too-large, param validation) still join the same
# `{detail, code}` contract the frontend resolves to localized copy. The app/main.py HTTPException
# handler emits the code when present; a plain HTTPException stays `{detail}` (frontend falls back to it).

from fastapi import HTTPException


class CodedHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
