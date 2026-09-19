import re
from pathlib import Path

from app.main import app

# The first contract sentence `docs/public/api-reference.md` states is where the API lives, and it was
# wrong: it said `Base URL: /api`, while every router is mounted at the root. An integrator following
# the document built `https://host/api/investments` and got a 404 on every single call — total failure,
# no partial success, and the document also describes API-key auth, so third-party integration is an
# intended use rather than a hypothetical one.
#
# Nothing compared the claim to the app, which is why a wrong first line survived. This does: the
# prefix the document promises is derived from the document, the prefix the app actually serves is
# derived from the app, and the two are asserted against each other rather than against a literal.

_DOC = Path(__file__).resolve().parents[4] / "docs" / "public" / "api-reference.md"


# The path prefix the document tells an integrator to put in front of every path, or "" for none.
#
# Parsed rather than restated so the assertion is about the sentence a reader actually gets. The
# match is asserted to exist, so a reworded or deleted line fails loudly here instead of quietly
# comparing two empty strings — which would agree perfectly.
def _documented_prefix() -> str:
    line = re.search(r"^Base URL:.*$", _DOC.read_text(), re.MULTILINE)
    assert line is not None, f"no 'Base URL:' line in {_DOC} — reword the guard with the document"
    # Anchored to a backticked path IMMEDIATELY after "Base URL:", which is the only position that
    # states a prefix. Any backticked path later in the sentence is an EXAMPLE — the current wording
    # ends with one — and reading that as the prefix would fail the guard for a document that is
    # perfectly correct.
    claim = re.match(r"^Base URL:\s*`(/[^`]*)`", line.group(0))
    return claim.group(1).rstrip("/") if claim else ""


# The prefix the app actually serves every route under, from the app rather than from a constant.
def _served_prefix() -> str:
    paths = [route.path for route in app.routes if getattr(route, "path", "").startswith("/")]
    assert len(paths) > 50, f"route scan found only {len(paths)} paths — it is not seeing the app"
    # The API mounts its routers with no prefix, so the common leading segment is nothing. Derived as
    # "what every documented-style path shares" rather than assumed, so a future decision to mount
    # under a prefix is picked up here instead of silently disagreeing with the document.
    if app.root_path:
        return app.root_path.rstrip("/")
    first_segments = {path.split("/")[1] for path in paths if len(path.split("/")) > 1}
    return "" if len(first_segments) > 1 else f"/{first_segments.pop()}"


class TestTheDocumentedBaseUrlIsWhereTheApiActuallyIs:
    def test_the_document_promises_the_prefix_the_app_serves(self):
        documented, served = _documented_prefix(), _served_prefix()
        assert documented == served, (
            f"api-reference.md tells integrators to use {documented!r} but the app serves routes under {served!r} — every documented path would 404"
        )

    def test_a_known_route_is_reachable_at_the_documented_prefix(self):
        # The same fact from the other side, so the pair cannot agree on a prefix that is wrong for
        # both. `/investments` is documented and real; under a `/api` claim this is the call that 404s.
        prefix = _documented_prefix()
        assert f"{prefix}/investments" in {route.path for route in app.routes}
