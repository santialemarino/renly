import pytest

from app.config import Settings
from app.deps.currency import _display_currency
from app.main import create_app


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("usd", "USD"),
        ("USD", "USD"),
        ("ars", "ARS"),
        ("Brl", "BRL"),
        (None, None),
        ("", None),
    ],
)
def test_display_currency_uppercases(raw, expected):
    # A lowercase display code must normalize to uppercase so it hits the uppercase-keyed rate maps
    # (a lowercase code would otherwise silently skip conversion); empty/None stay None (= original).
    assert _display_currency(raw) == expected


def test_currency_still_exposed_as_query_param():
    # The dependency must keep `currency` a documented query param on the read endpoints (the dep
    # declares it via Query), not swallow it into the dependency graph.
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost/renly", jwt_secret="x" * 32))
    schema = app.openapi()
    params = schema["paths"]["/dashboard/overview"]["get"]["parameters"]
    names = {p["name"] for p in params}
    assert "currency" in names
