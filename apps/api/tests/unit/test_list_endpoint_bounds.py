# SEC-11: every list endpoint this API serves is bounded, and this is the test that says so once
# instead of once per endpoint.
#
# The recurring defect in this codebase is not arithmetic. It is that N places each independently
# enumerate the same set, a member is added, and only some of them learn about it — seven instances so
# far across the shared-money initiative. "Which endpoints return a list" is exactly that shape: a new
# list endpoint is written, nobody thinks about its row count, and it ships unbounded. So the set is
# not restated here, it is READ OFF THE MOUNTED ROUTER, and every comparison is a set difference.
#
# Three properties make this catch the CLASS rather than one instance of it:
#
# * The population comes from `app.routes` — the real FastAPI app with the real routers — and a route
#   counts as a list read if its response model IS a list or CARRIES an `items` field. Neither test
#   reads a name, so a new endpoint cannot avoid the check by being called something else.
# * Every endpoint must land in exactly one of three buckets, and the buckets are compared against the
#   router both ways. An unclassified endpoint fails; a classified endpoint that no longer exists fails
#   too, so the lists cannot rot into a description of a router that has moved on.
# * BOUNDED — the bucket for "neither paginated nor capped" — is a dict of endpoint to REASON, so
#   adding one costs writing down why. That is the bucket a defect would hide in, and the cost of
#   entering it is the only thing standing between it and a dumping ground.

from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import Settings
from app.db import get_admin_session, get_session
from app.deps.auth import get_current_user
from app.main import app, create_app
from app.models.user import User
from app.schemas.pagination import PaginatedResponse
from app.utils.pagination import DEFAULT_PAGE_SIZE, MAX_LIST_ROWS, MAX_PAGE_SIZE

USER = User(id=1, name="Tester", email="t@example.com", password_hash="h", is_admin=True)


# Endpoints that serve a page: the caller asks for one and is told the total, so nothing is unreachable.
# Read as a set of (method, path) so two verbs on one path stay distinguishable.
PAGINATED = {
    ("GET", "/accounts/{account_id}/movements"),
    ("GET", "/accounts/{account_id}/reconciliations"),
    ("GET", "/admin/invites"),
    ("GET", "/asset-prices/{ticker}"),
    ("GET", "/credit-cards/{card_id}/reconciliations"),
    ("GET", "/credit-cards/{card_id}/settlements"),
    ("GET", "/expenses"),
    ("GET", "/feedback"),
    ("GET", "/groups/{group_id}/expenses"),
    ("GET", "/groups/{group_id}/income"),
    ("GET", "/groups/{group_id}/settlements"),
    ("GET", "/income"),
    ("GET", "/investments"),
    ("GET", "/investments/{investment_id}/snapshots"),
    ("GET", "/investments/{investment_id}/transactions"),
    ("GET", "/notifications"),
    ("GET", "/pots/{pot_id}/ownership"),
    ("GET", "/transfers"),
}

# Endpoints capped at MAX_LIST_ROWS instead: their row count grows with what the user chose to create
# rather than with time, so a ceiling far above any plausible holding bounds the query without ever
# being the reason somebody cannot see a row. No contract change, and no pager on a list that will
# never fill one page.
CAPPED = {
    ("GET", "/accounts"),
    ("GET", "/api-keys"),
    ("GET", "/collections"),
    ("GET", "/credit-cards"),
    ("GET", "/groups"),
    ("GET", "/installments"),
    ("GET", "/payment-obligations"),
    ("GET", "/pots"),
    ("GET", "/subscriptions"),
}

# Endpoints that need neither, each with the reason it is already bounded. Entering this bucket costs
# writing the reason down, which is the point: it is where an unbounded read would otherwise hide.
BOUNDED = {
    ("GET", "/credit-cards/{card_id}/statements"): (
        "Computed rather than queried: list_recent_statements walks back RECENT_STATEMENTS_LIMIT closing "
        "dates from today, so the row count is a constant and no query returns a row per statement."
    ),
    ("GET", "/exchange-rates"): "A required `date` query parameter bounds it to one day's rate per supported pair.",
    ("GET", "/groups/{group_id}/activity"): "Already takes a bounded `limit` query parameter of its own (the group hub's activity feed).",
    ("GET", "/payments-calendar"): "Required `year` and `month` parameters bound it to one month.",
    ("GET", "/dashboard/composition"): "Fixed buckets — one row per net-worth component, an enumerated constant.",
    ("GET", "/finance-metrics/expense-breakdown"): "One row per expense category, an enumerated constant.",
    ("GET", "/finance-metrics/income-breakdown"): "One row per income category, an enumerated constant.",
    ("GET", "/metrics/allocation"): "One row per investment category, an enumerated constant.",
    ("GET", "/metrics/allocation/by-collection"): "One row per collection, bounded by CAPPED /collections above.",
    ("GET", "/metrics/investments/summary"): "One row per investment category, an enumerated constant.",
}


# Every mounted GET route that serves a collection: its response model IS a list, or carries `items`.
# Read off the app rather than restated, so an endpoint cannot dodge the check by being named something
# else — and `items` rather than a name suffix, because the envelope is what makes it a collection.
def _list_routes() -> dict[tuple[str, str], type | None]:
    found: dict[tuple[str, str], type | None] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods:
            continue
        model = route.response_model
        if model is None:
            continue
        if getattr(model, "__origin__", None) is list:
            found[("GET", route.path)] = None
        elif isinstance(model, type) and issubclass(model, BaseModel) and "items" in model.model_fields:
            found[("GET", route.path)] = model
    return found


# Every query parameter a route accepts, INCLUDING those a sub-dependency contributes. `page` and
# `page_size` come from the shared PageQuery dependency, so they are not on the route's own dependant —
# reading only that would report an empty set and pass nothing.
def _query_params(route: APIRoute) -> dict[str, object]:
    found: dict[str, object] = {}

    def walk(dependant) -> None:
        for param in dependant.query_params:
            found[param.name] = param
        for sub in dependant.dependencies:
            walk(sub)

    walk(route.dependant)
    return found


# The routes this app mounts, keyed the way the buckets above are.
def _routes_by_key() -> dict[tuple[str, str], APIRoute]:
    return {("GET", route.path): route for route in app.routes if isinstance(route, APIRoute) and "GET" in route.methods}


# The value of one annotated-constraint attribute on a parameter (`le`, `ge`), or None when absent.
# Looked up by attribute rather than by position: the metadata list holds one object per constraint in
# declaration order, so an index would silently read `ge` after a reordering.
def _constraint(param, name: str):
    return next((getattr(m, name) for m in param.field_info.metadata if hasattr(m, name)), None)


def _client() -> TestClient:
    test_app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _fake_session():
        yield AsyncMock()

    test_app.dependency_overrides[get_session] = _fake_session
    test_app.dependency_overrides[get_admin_session] = _fake_session
    test_app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(test_app, raise_server_exceptions=False)


class TestTheWindowItself:
    def test_the_default_and_the_ceiling_are_pinned(self):
        # Pinned to literals on purpose. Every other assertion in this file compares an endpoint against
        # DEFAULT_PAGE_SIZE / MAX_PAGE_SIZE, so all of them move together if the constants move and the
        # suite stays green while every client's page size silently changes. This is the one place that
        # notices — the API contract is the NUMBER, not the agreement between two copies of it.
        assert (DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE) == (25, 100)

    def test_the_row_ceiling_is_pinned(self):
        assert MAX_LIST_ROWS == 500


class TestEveryListEndpointIsClassified:
    def test_no_list_endpoint_is_left_unbounded(self):
        # THE assertion this file exists for. A new list endpoint lands here until somebody decides
        # whether it pages, caps, or is already bounded — which is the decision that was never forced
        # before SEC-11, and is why 21 endpoints returned every matching row.
        assert set(_list_routes()) - PAGINATED - CAPPED - set(BOUNDED) == set()

    def test_no_classification_describes_an_endpoint_that_no_longer_exists(self):
        # The direction the check above cannot see. A stale entry reads as coverage while describing
        # nothing, and would let a renamed endpoint slip into the unbounded set unnoticed.
        assert (PAGINATED | CAPPED | set(BOUNDED)) - set(_list_routes()) == set()

    def test_the_three_buckets_do_not_overlap(self):
        # An endpoint in two buckets is a claim that it both pages and does not, and whichever
        # assertion ran first would pass.
        assert PAGINATED & CAPPED == set()
        assert PAGINATED & set(BOUNDED) == set()
        assert CAPPED & set(BOUNDED) == set()

    def test_every_bounded_endpoint_states_why(self):
        # The cost of entering the bucket where a defect would hide.
        assert [key for key, reason in BOUNDED.items() if not reason.strip()] == []


class TestThePaginatedOnesActuallyPage:
    def test_each_declares_the_shared_page_window(self):
        # Reads the mounted route's own query parameters rather than the source, so an endpoint listed
        # as paginated that forgot the dependency fails here instead of silently serving every row.
        routes = _routes_by_key()
        for key in sorted(PAGINATED):
            assert {"page", "page_size"} <= set(_query_params(routes[key])), key

    def test_each_response_carries_the_page_fields(self):
        # `total` is what lets a client draw a pager at all; without it a page is just a truncation.
        for key, model in _list_routes().items():
            if key not in PAGINATED:
                continue
            assert model is not None and issubclass(model, PaginatedResponse), key

    def test_the_ceiling_and_the_default_are_the_same_everywhere(self):
        # The whole point of the shared dependency. Four endpoints held three different answers before
        # SEC-11 (20/100, 25/100, and the feed's 20/50), which is how a client learns to guess.
        routes = _routes_by_key()
        for key in sorted(PAGINATED):
            params = _query_params(routes[key])
            assert params["page_size"].default == DEFAULT_PAGE_SIZE, key
            assert _constraint(params["page_size"], "le") == MAX_PAGE_SIZE, key
            assert _constraint(params["page_size"], "ge") == 1, key
            # ge=1 on the page number is load-bearing: page 0 computes a NEGATIVE offset, which Postgres
            # rejects at runtime — a 500 on a query string anyone can type.
            assert _constraint(params["page"], "ge") == 1, key


class TestAnOversizedPageIsRefused:
    # Refused rather than clamped, and that is a decision: a clamped response disagrees with the request
    # with no signal, so a client asking for 1000 rows and getting 100 cannot tell it did not get them
    # all. The refusal happens in the dependency, BEFORE the handler runs, which is why no endpoint has
    # to implement it and none can get it wrong.

    @pytest.mark.parametrize("path", ["/expenses", "/income", "/investments", "/transfers", "/notifications"])
    def test_a_page_size_over_the_ceiling_is_a_422(self, path):
        assert _client().get(path, params={"page_size": MAX_PAGE_SIZE + 1}).status_code == 422

    @pytest.mark.parametrize("path", ["/expenses", "/income", "/investments", "/transfers", "/notifications"])
    def test_the_ceiling_itself_is_accepted(self, path):
        # The boundary from the other side: a cap that refuses its own maximum is off by one, and a test
        # that only pushes past it cannot tell the difference.
        assert _client().get(path, params={"page_size": MAX_PAGE_SIZE}).status_code != 422

    @pytest.mark.parametrize("page_size", [0, -1])
    def test_a_page_size_below_one_is_a_422(self, page_size):
        assert _client().get("/expenses", params={"page_size": page_size}).status_code == 422

    @pytest.mark.parametrize("page", [0, -1])
    def test_a_page_number_below_one_is_a_422(self, page):
        # Without ge=1 a page of 0 computes a NEGATIVE offset, which Postgres rejects at runtime — a 500
        # on a query string a client can type.
        assert _client().get("/expenses", params={"page": page}).status_code == 422


class TestTheDecoratorAndTheFunctionAgree:
    # Not a pagination rule, but the defect SEC-11 kept producing: changing an endpoint's shape means
    # changing it TWICE — the `response_model=` on the decorator and the function's return annotation —
    # and FastAPI serializes by the decorator while the type checker reads the annotation. A settlements
    # endpoint shipped in this very change with `response_model=list[CardSettlementResponse]` over a
    # function returning an envelope, and nothing failed: `pnpm check:api` imports the app without
    # calling it, and no test drove that route over HTTP.

    def test_no_route_declares_one_response_model_and_returns_another(self):
        import typing

        mismatched = [
            (sorted(route.methods)[0], route.path)
            for route in app.routes
            if isinstance(route, APIRoute)
            and route.response_model is not None
            and typing.get_type_hints(route.endpoint).get("return") not in (None, route.response_model)
        ]
        assert mismatched == []
