import json

import pytest
from fastapi import HTTPException

from app.deps.api_key_auth import get_jwt_or_api_key_user
from app.domain import InstallmentLockedFieldError, InvestmentCurrencyMismatchError
from app.domain.errors import DomainError
from app.http_errors import CodedHTTPException
from app.main import domain_error_handler, http_exception_handler

# F4: every domain error carries a stable code, and the handlers surface {detail, code, **extra}
# uniformly so the frontend can map code → localized message (falling back to raw detail).


# All concrete DomainError subclasses (importing app.domain loads the whole errors module).
def _all_domain_errors() -> list[type[DomainError]]:
    seen: set[type[DomainError]] = set()
    stack = list(DomainError.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls not in seen:
            seen.add(cls)
            stack.extend(cls.__subclasses__())
    return sorted(seen, key=lambda c: c.__name__)


class TestDomainErrorCodes:
    def test_every_domain_error_defines_a_nonempty_code_and_valid_status(self):
        for cls in _all_domain_errors():
            assert isinstance(cls.code, str) and cls.code, f"{cls.__name__} has no code"
            assert cls.code != DomainError.code, f"{cls.__name__} did not override the base code"
            assert isinstance(cls.status_code, int) and 400 <= cls.status_code < 600, cls.__name__

    def test_codes_are_unique_across_domain_errors(self):
        codes = [cls.code for cls in _all_domain_errors()]
        assert len(codes) == len(set(codes)), f"duplicate domain-error codes: {codes}"

    def test_base_defines_a_message_so_the_handler_never_attributeerrors(self):
        # The app/main.py handler reads exc.message; the base must always expose one.
        assert isinstance(DomainError.message, str) and DomainError.message

    def test_installment_locked_field_prejoins_fields_for_scalar_placeholder(self):
        # extra["fields"] is a display-ready string so the frontend's scalar {fields} renders cleanly.
        exc = InstallmentLockedFieldError(["amount", "interest_rate"])
        assert exc.extra == {"fields": "amount, interest_rate"}


class TestErrorHandlers:
    @pytest.mark.asyncio
    async def test_domain_handler_emits_detail_code_and_extra(self):
        exc = InvestmentCurrencyMismatchError("USD", "ARS")
        response = await domain_error_handler(None, exc)
        body = json.loads(response.body)
        assert response.status_code == 400
        assert body["detail"] == exc.message
        assert body["code"] == "investment_currency_mismatch"
        # `extra` fields ride along so the frontend can interpolate the localized message.
        assert body["row_currency"] == "USD" and body["base_currency"] == "ARS"

    @pytest.mark.asyncio
    async def test_http_handler_adds_code_only_when_present(self):
        coded = await http_exception_handler(None, CodedHTTPException(status_code=403, detail="Admin access required", code="admin_required"))
        assert json.loads(coded.body) == {"detail": "Admin access required", "code": "admin_required"}

        # A plain HTTPException keeps the bare {detail} shape (frontend falls back to it).
        plain = await http_exception_handler(None, HTTPException(status_code=404, detail="Nope"))
        assert json.loads(plain.body) == {"detail": "Nope"}


class TestDualAuthErrorCode:
    # The dual-auth dependency carries the same invalid_auth_token code as the JWT-only dependency,
    # so a session-expiry on a dual-auth endpoint localizes instead of showing raw English.
    @pytest.mark.asyncio
    async def test_missing_credentials_raise_coded_invalid_auth_token(self):
        with pytest.raises(CodedHTTPException) as exc_info:
            await get_jwt_or_api_key_user(session=None, admin_session=None, credentials=None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "invalid_auth_token"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
