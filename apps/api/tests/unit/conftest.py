# One autouse guard, and the reason it exists is specific enough to be worth stating.
#
# Every service in this app receives its session from the caller, which is what makes the unit suite
# DB-free by construction: hand it a mock and nothing can reach Postgres. `notification_service` is the
# one exception — two of its functions open their OWN privileged session, because both do something no
# request connection is allowed to: `dispatch` writes a row per RECIPIENT into a table with no INSERT
# policy, and `subscribe_push` detaches a browser from whichever account held it before.
#
# A unit test that reached it would therefore connect to whatever DATABASE_ADMIN_URL names, which on a
# developer's machine is their real data — and it would do so INVISIBLY, because dispatch swallows every
# exception so that a push outage can never roll back the money write that produced the event. The
# failure would be a unit run quietly inserting notifications into a live database.
#
# So the factory is replaced with a recorder and the assertion is made at TEARDOWN. Raising from the
# factory would not do: a raise inside dispatch is precisely what dispatch is built to ignore.
#
# Reaching this guard almost always means a test drove a real producer without stubbing the fan-out. The
# fix is to stub `notification_service.dispatch` in that test — which is also what lets it assert WHAT
# was announced, rather than leaving the announcement untested. A test of `subscribe_push` instead
# replaces the factory itself, and then asserts which session each write ran on.

import pytest

from app.services import notification_service


# Records whether a privileged session was ever opened, so the assertion can happen after the test.
class _SessionFactoryRecorder:
    def __init__(self) -> None:
        self.opened = False

    def __call__(self):
        self.opened = True
        raise AssertionError("unit tests must not open a database session")


@pytest.fixture(autouse=True)
def no_real_session_from_a_unit_test(monkeypatch):
    recorder = _SessionFactoryRecorder()
    monkeypatch.setattr(notification_service, "AdminSessionLocal", recorder)
    yield
    assert not recorder.opened, (
        "This test reached a notification_service function that opens a real privileged session "
        "(dispatch, or subscribe_push). Stub notification_service.dispatch on the service under test, "
        "or replace notification_service.AdminSessionLocal for a test of the push subscribe itself."
    )
