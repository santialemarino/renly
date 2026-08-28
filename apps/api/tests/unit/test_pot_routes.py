# Route-level contracts that live in the ROUTER rather than in a service, and that therefore no
# service test can protect.
#
# The one that matters most is which SESSION each endpoint is handed. Creating a pot writes the very
# permission row its own RLS policy reads, so it needs the privileged session; rewiring it to
# SessionDep would leave every service test green while the endpoint 500s against a real database.
# The counterweight matters just as much: a plain read must STAY on the request session, or the
# perimeter widens one endpoint at a time and RLS quietly stops being the thing enforcing visibility.

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_admin_session, get_session
from app.deps.auth import get_current_user
from app.main import create_app
from app.models.user import User
from app.schemas.pot import PotCreate, PotUpdate
from app.services import pot_ownership_service, pot_service

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)

_POT_JSON = {
    "id": 5,
    "group_id": 10,
    "name": None,
    "base_currency": "USD",
    "visibility": "members",
    "is_default": True,
    "nav": None,
    "unit_price": None,
    "total_units": "0",
    "my_percentage": "0",
    "can_write": True,
    "shares": [],
    "permissions": [],
    "created_at": "2026-08-25T00:00:00",
    "updated_at": "2026-08-25T00:00:00",
}


# What each stubbed service returns, for the endpoints whose response model is not a single pot.
_STUB_RETURNS = {"list_pots": [], "list_holdings": {"investments": [], "accounts": []}}


# Builds the real app with the DB and auth dependencies faked, so a request exercises the router's
# own wiring. `sessions` records which override each endpoint actually resolved.
def _client(sessions: dict) -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _request_session():
        sessions["kind"] = "request"
        yield AsyncMock()

    async def _admin_session():
        sessions["kind"] = "privileged"
        yield AsyncMock()

    app.dependency_overrides[get_session] = _request_session
    app.dependency_overrides[get_admin_session] = _admin_session
    app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app, raise_server_exceptions=False)


class TestSessionWiring:
    @pytest.mark.asyncio
    async def test_creating_a_pot_is_handed_the_privileged_session(self, monkeypatch):
        # The bootstrap: the pot's first permission row is what app_can_view_pot reads, so the insert
        # cannot satisfy its own predicate.
        sessions: dict = {}
        monkeypatch.setattr(pot_service, "create_pot", AsyncMock(return_value=_POT_JSON))
        response = _client(sessions).post("/pots", json={"group_id": 10, "base_currency": "USD"})
        assert response.status_code == 201
        assert sessions["kind"] == "privileged"

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("get", "/pots", None),
            ("get", "/pots/5", None),
            ("put", "/pots/5", {"name": "Casa"}),
            ("delete", "/pots/5", None),
            ("put", "/pots/5/permissions/100", {"can_view": True, "can_write": False}),
            ("delete", "/pots/5/permissions/100", None),
            ("get", "/pots/5/holdings", None),
            ("post", "/pots/5/holdings", {"investment_ids": [1]}),
            ("post", "/pots/5/holdings/remove", {"investment_ids": [1]}),
        ],
    )
    @pytest.mark.asyncio
    async def test_every_other_pot_endpoint_stays_on_the_request_session(self, monkeypatch, method, path, body):
        # The counterweight to the test above. Without it, "use the privileged session" spreads.
        sessions: dict = {}
        for name in ("list_pots", "get_pot", "list_holdings", "update_pot", "delete_pot", "set_permission", "clear_permission", "move_holdings"):
            monkeypatch.setattr(pot_service, name, AsyncMock(return_value=_STUB_RETURNS.get(name, _POT_JSON)))
        response = getattr(_client(sessions), method)(path, **({"json": body} if body is not None else {}))
        assert response.status_code in (200, 204)
        assert sessions["kind"] == "request"

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/pots/5/ownership/opening", {"date": "2026-01-01", "value": "100.00", "shares": {"100": "100"}}),
            ("/pots/5/ownership/movements", {"type": "contribution", "date": "2026-06-01", "member_id": 100, "amount": "5.00"}),
            ("/pots/5/ownership/reagreements", {"date": "2026-06-01", "from_member_id": 100, "to_member_id": 101, "percentage": "10"}),
        ],
    )
    @pytest.mark.asyncio
    async def test_every_ledger_write_stays_on_the_request_session(self, monkeypatch, path, body):
        # These are gated by app_can_write_pot at the DATABASE, which only happens on the request
        # session. Handing one the privileged session would bypass the policy entirely.
        sessions: dict = {}
        event = {
            "id": 1,
            "pot_id": 5,
            "type": "contribution",
            "date": "2026-06-01",
            "member_id": 100,
            "member_name": "Santi",
            "units": "1",
            "unit_price": "1",
            "created_at": "2026-08-25T00:00:00",
        }
        monkeypatch.setattr(pot_ownership_service, "record_opening", AsyncMock(return_value=[event]))
        monkeypatch.setattr(pot_ownership_service, "record_movement", AsyncMock(return_value=event))
        monkeypatch.setattr(pot_ownership_service, "record_reagreement", AsyncMock(return_value=event))
        response = _client(sessions).post(path, json=body)
        assert response.status_code == 201
        assert sessions["kind"] == "request"


class TestRequestContract:
    @pytest.mark.asyncio
    async def test_a_pot_cannot_be_created_in_an_unsupported_currency(self, monkeypatch):
        monkeypatch.setattr(pot_service, "create_pot", AsyncMock(return_value=_POT_JSON))
        response = _client({}).post("/pots", json={"group_id": 10, "base_currency": "XYZ"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_the_base_currency_cannot_be_changed_after_creation(self, monkeypatch):
        # It is the unit of every figure already in the ledger, so changing it would restate every
        # past event at a rate nobody chose. The guarantee lives in the SCHEMA — the field simply does
        # not exist on the update body — so that is what is asserted. Checking the service call
        # arguments instead would be a tautology: the router names its two keywords explicitly, so
        # base_currency could be added to the schema and the assertion would still pass.
        assert "base_currency" not in PotUpdate.model_fields
        assert "base_currency" in PotCreate.model_fields

        update = AsyncMock(return_value=_POT_JSON)
        monkeypatch.setattr(pot_service, "update_pot", update)
        response = _client({}).put("/pots/5", json={"name": "Casa", "base_currency": "ARS"})
        assert response.status_code == 200
