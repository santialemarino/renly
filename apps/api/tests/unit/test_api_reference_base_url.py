import re
from pathlib import Path

from app.main import app

# The first contract sentence `docs/public/api-reference.md` states is where the API lives, and it was
# wrong: it said `Base URL: /api`, while every router is mounted at the root. An integrator following
# the document built `https://host/api/investments` and got a 404 on every single call — total
# failure, no partial success, and the document also describes API-key auth, so third-party
# integration is an intended use rather than a hypothetical one.
#
# This asserts the document's OWN endpoint table against the app's real routes, with the documented
# prefix applied to each row. That shape is the second attempt, and the first one is worth recording
# because it read as though it compared two sources while one side was a constant: it derived "the
# prefix the app serves" from the common first path segment, which CANNOT work — `/health`, `/docs`,
# `/redoc` and `/openapi.json` sit at the root beside the routers, so the set never collapses to one
# member and the function could only ever return "". It was also inverted: it passed when the app
# moved under a prefix and the document did not, and FAILED on a document correctly updated to match.
#
# Comparing the tables has no heuristic in it and is non-vacuous in both directions. Document says
# `/api` while the app serves at the root: all 191 rows fail. App moves under a prefix while the
# document is stale: all 191 rows fail. Both correct: green. It also survives the two shapes that
# defeated the first version — a `root_path` deployment, and an app that adds a `/` route.

_DOC = Path(__file__).resolve().parents[4] / "docs" / "public" / "api-reference.md"

# A documented endpoint row: | `GET` | `/investments` | description |
_ROW = re.compile(r"^\|\s*`(GET|POST|PUT|PATCH|DELETE)`\s*\|\s*`([^`]+)`", re.MULTILINE)


# A path with every parameter reduced to a placeholder, so `/accounts/{id}` and `/accounts/{account_id}`
# compare equal.
#
# Parameter NAMES are a documentation choice — the reference writes `{id}` and `{rid}` where the
# routers write `{account_id}` and `{reconciliation_id}` — while the SHAPE is the contract an
# integrator builds a URL from. Comparing the names produced 108 false mismatches out of 191 rows and
# would have made this guard unusable; comparing shapes still catches a segment added, removed or
# reordered, which is what actually breaks a caller.
def _shape(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


# The path prefix the document tells an integrator to put in front of every path, or "" for none.
#
# Anchored to a backticked path IMMEDIATELY after "Base URL:", the only position that states a
# prefix — a backticked path later in the sentence is an example, and the current wording ends with
# one. The line is asserted to exist so a reworded heading fails loudly here rather than silently
# yielding "" and agreeing with an app that happens to serve at the root.
def _documented_prefix() -> str:
    line = re.search(r"^Base URL:.*$", _DOC.read_text(), re.MULTILINE)
    assert line is not None, f"no 'Base URL:' line in {_DOC} — reword the guard with the document"
    claim = re.match(r"^Base URL:\s*`(/[^`]*)`", line.group(0))
    return claim.group(1).rstrip("/") if claim else ""


# Every (method, path) pair the document promises, as written.
def _documented_routes() -> set[tuple[str, str]]:
    rows = {(method, _shape(path)) for method, path in _ROW.findall(_DOC.read_text())}
    assert len(rows) > 150, f"only {len(rows)} endpoint rows parsed out of the document — its table shape changed"
    return rows


# Every (method, path) pair the app actually serves, including the prefix a root_path deployment adds.
def _served_routes() -> set[tuple[str, str]]:
    served = {
        (method, _shape(f"{app.root_path.rstrip('/')}{route.path}")) for route in app.routes for method in (getattr(route, "methods", None) or ())
    }
    assert len(served) > 150, f"route scan found only {len(served)} method+path pairs — it is not seeing the app"
    return served


class TestTheDocumentedEndpointsAreWhereTheApiServesThem:
    def test_every_documented_endpoint_exists_at_the_documented_base_url(self):
        prefix = _documented_prefix()
        served = _served_routes()
        missing = sorted((method, path) for method, path in _documented_routes() if (method, _shape(f"{prefix}{path}")) not in served)
        assert missing == [], (
            f"{len(missing)} documented endpoints do not exist at the documented base URL "
            f"{prefix or '(the host root)'!r} — an integrator following the document would get a 404. "
            f"First few: {missing[:5]}"
        )
