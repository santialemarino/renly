# Adding one notification event touches SIX lists across two languages plus the database, and this is
# the test that says they agree once instead of six times.
#
# The recurring defect in this codebase is not arithmetic. It is that N places each independently
# enumerate the same set, a member is added, and only some of them learn about it. It has now shipped
# five times in the shared-money initiative alone. The card-charge readers were closed with a set
# difference in `test_card_charge_sources.py`; this is the same instrument pointed at the notification
# event list, which is the other place the shape lives.
#
# The pair that had NOTHING guarding it is `NotificationEvent` (Python) against `NOTIFICATION_EVENTS`
# (TypeScript). They are two independent transcriptions of one list in two languages, and each existing
# test iterates ONE of them: the API's template test compares copy against the Python enum, the web's
# parity test compares copy against the TypeScript constant. So an event present in one language and
# absent in the other passes both suites while the preferences grid silently omits a row — and next-intl
# answers a missing key by returning its own key path, a non-empty string, so a `toBeTruthy()` style
# assertion passes on exactly that failure too.
#
# Three properties make this catch the CLASS rather than one instance of it:
#
# * Every comparison is a SET DIFFERENCE, both ways, never an assertion per event. A per-item check
#   agrees with itself forever — an event nobody added to the list is an event nobody checks (PR 11).
# * It reads the OTHER language's source rather than restating it. The web constant is parsed out of
#   the TypeScript file and the enum labels out of the SQL script, so nothing here can be "updated to
#   match" without updating the thing it describes.
# * It names what each list DRIVES, because that is what a failure actually costs.

import json
import re
from pathlib import Path

from app.models.notification import NotificationEvent
from app.services import notification_service

_REPO = Path(__file__).resolve().parents[4]
_WEB_CONSTANTS = _REPO / "apps" / "web" / "lib" / "constants" / "notifications.ts"
_WEB_RENDERER = _REPO / "apps" / "web" / "lib" / "notifications.ts"
_WEB_ROUTES = _REPO / "apps" / "web" / "config" / "routes.ts"
_SCHEMA_SQL = _REPO / "apps" / "api" / "database" / "01_create_tables.sql"
_MIGRATIONS = _REPO / "apps" / "api" / "migrations" / "versions"
_TRANSLATIONS = _REPO / "apps" / "web" / "translations"

_LOCALES = ("en", "es")


# The event values the Python enum declares — the source the other three transcribe.
def _python_events() -> set[str]:
    return {event.value for event in NotificationEvent}


# The event values `NOTIFICATION_EVENTS` declares, read out of the TypeScript rather than restated.
#
# A regex over the source rather than a build step, deliberately: the alternative is running `tsc` from
# pytest, and the thing under test is a flat list of string literals whose shape a regex reads exactly.
# The anchor is asserted to match at all, so a rename of the constant fails loudly here instead of
# quietly returning an empty set that agrees with nothing.
def _web_events() -> set[str]:
    source = _WEB_CONSTANTS.read_text()
    block = re.search(r"export const NOTIFICATION_EVENTS = \[(.*?)\] as const;", source, re.DOTALL)
    assert block is not None, f"NOTIFICATION_EVENTS not found in {_WEB_CONSTANTS}"
    return set(re.findall(r"'([a-z_]+)'", block.group(1)))


# The labels the Postgres enum is CREATED with, for a database built from zero by the SQL script.
def _schema_enum_labels() -> list[str]:
    source = _SCHEMA_SQL.read_text()
    block = re.search(r"CREATE TYPE notification_event AS ENUM \((.*?)\);", source, re.DOTALL)
    assert block is not None, f"notification_event enum not found in {_SCHEMA_SQL}"
    return re.findall(r"'([a-z_]+)'", block.group(1))


# Every `ADD VALUE` any migration performs on the enum, in revision order, as (label, before) pairs —
# `before` being the label the new one is inserted ahead of, or None when it is appended.
#
# Revision order is the filename's numeric prefix, which is this repo's convention and is also the order
# `alembic upgrade head` applies them in. A migration that ever branched would break that assumption;
# nothing here ever has, and the `down_revision` chain is linear.
def _migration_add_values() -> list[tuple[str, str | None]]:
    found: list[tuple[str, str, str | None]] = []
    for path in sorted(_MIGRATIONS.glob("0*.py")):
        for label, before in re.findall(
            r"ALTER TYPE notification_event ADD VALUE(?: IF NOT EXISTS)? '([a-z_]+)'(?: BEFORE '([a-z_]+)')?",
            path.read_text(),
        ):
            found.append((path.name, label, before or None))
    return [(label, before) for _name, label, before in found]


# The labels every migration has ever ADDed to the enum, for a database that got there incrementally.
def _migration_added_labels() -> set[str]:
    return {label for label, _before in _migration_add_values()}


# The enum order a database reaches by MIGRATION: `0023`'s CREATE, then each ADD VALUE applied the way
# Postgres applies it — appended, or inserted ahead of the label a BEFORE clause names.
def _migrated_enum_order() -> list[str]:
    created = re.search(r"_EVENTS = \((.*?)\)", (_MIGRATIONS / "0023_notifications.py").read_text(), re.DOTALL)
    assert created is not None, "0023's _EVENTS tuple not found"
    order = re.findall(r'"([a-z_]+)"', created.group(1))
    for label, before in _migration_add_values():
        if label in order:
            continue
        order.insert(order.index(before) if before else len(order), label)
    return order


# The events one of the web's two routing maps names, with the ROUTES member each is pointed at
# resolved to its actual path — so this compares URLs rather than symbol names.
#
# Parsed a line at a time rather than with one sweeping pattern, because the two maps are written
# differently (a Set of quoted strings, and an object whose keys are bare) and a pattern loose enough to
# read both is loose enough to match halves of `ROUTES.paymentObligations` as well. The parse is asserted
# to have found something, so a renamed constant fails here instead of quietly comparing two empty sets,
# which would agree perfectly.
def _web_routed_events(constant: str) -> dict[str, str]:
    block = re.search(rf"const {constant}[^=]*= (?:new Set<NotificationEvent>\(\[|\{{)(.*?)(?:\]\)|\}});", _WEB_RENDERER.read_text(), re.DOTALL)
    assert block is not None, f"{constant} not found in {_WEB_RENDERER}"
    routes = dict(re.findall(r"^  (\w+): '([^']+)',", _WEB_ROUTES.read_text(), re.MULTILINE))
    entries = re.findall(r"^\s*'?([a-z_]+)'?\s*(?::\s*ROUTES\.(\w+))?\s*,\s*$", block.group(1), re.MULTILINE)
    assert entries, f"no events parsed out of {constant}"
    return {event: (routes[member] if member else "") for event, member in entries}


class TestBothSidesRouteTheSameEvents:
    # `_link` (API, for email and push) and `notificationHref` (web, for the feed row) are two
    # independent answers to "where does this notification point". They must agree, and nothing made
    # them: the same two-transcriptions-of-one-list shape as the enum above, one level down.

    def test_the_same_events_are_treated_as_private_and_at_the_same_paths(self):
        # These are the events whose payload carries no group_id at all, so a missing entry is not a
        # worse link — it is "/shared/None" in somebody's inbox.
        api = {event.value: path for event, path in notification_service._PRIVATE_EVENT_PATHS.items()}
        assert api == _web_routed_events("PRIVATE_EVENT_HREFS")

    def test_the_same_events_are_treated_as_pot_linked(self):
        # Paths are not compared here because the two build them differently — the API from a format
        # string, the web from sharedPotPath — but WHICH events take the pot branch is one decision, and
        # a disagreement sends the email to the group and the feed row to the pot for the same event.
        api = {event.value for event in notification_service._POT_LINKED_EVENTS}
        assert api == set(_web_routed_events("POT_LINKED_EVENTS"))


class TestTheListIsTheInvariant:
    def test_python_and_typescript_declare_the_same_events(self):
        # THE unguarded pair, and the one this test exists for. An event in the enum but not in
        # NOTIFICATION_EVENTS has no row in the preferences grid, so nobody can ever turn it off; one in
        # NOTIFICATION_EVENTS but not in the enum renders a grid row for something that can never fire.
        assert _python_events() == _web_events()

    def test_the_schema_script_declares_the_same_events(self):
        # A database built from zero by `pnpm db:init` must accept every value the app can write. A
        # missing label is an INSERT that raises at dispatch — which dispatch swallows, so the only
        # symptom is a notification nobody ever receives.
        assert _python_events() == set(_schema_enum_labels())

    def test_every_event_the_schema_declares_is_reachable_by_migration_too(self):
        # The other way an existing database gets there. `0023` created the type with its own labels and
        # later revisions ADD to it, so the two paths agree only if every label past the original set was
        # added by a migration — otherwise a fresh build and an upgraded one hold different types, and
        # the divergence surfaces as a 500 on one deployment and not the other.
        created_by_0023 = set(re.findall(r'"([a-z_]+)",', (_MIGRATIONS / "0023_notifications.py").read_text()))
        assert _python_events() - created_by_0023 - _migration_added_labels() == set()

    def test_a_migrated_database_reaches_the_same_enum_ORDER_as_a_fresh_one(self):
        # The assertion the `BEFORE 'group_invited'` clauses exist for, and the one nothing else makes.
        # `ALTER TYPE … ADD VALUE` APPENDS unless told otherwise, so a migration written without the
        # clause leaves an upgraded database holding the same labels in a different order from one built
        # by the SQL script — which is real drift between two deployments of the same release, and
        # invisible until somebody diffs two live schemas.
        #
        # Simulated from the migration text rather than run against Postgres so it costs nothing and
        # fails in the unit suite; verified against a real migrated clone as well.
        assert _migrated_enum_order() == _schema_enum_labels()

    def test_the_declared_ORDER_is_the_same_on_both_sides(self):
        # Order is not cosmetic here: the enum's declared order IS the order the preferences grid
        # presents, stated in both files, and it is also what makes a schema built fresh compare
        # byte-identical to one that was migrated. `ALTER TYPE ADD VALUE` appends unless told otherwise,
        # so this is exactly the assertion that catches a migration missing its BEFORE clause.
        source = _WEB_CONSTANTS.read_text()
        block = re.search(r"export const NOTIFICATION_EVENTS = \[(.*?)\] as const;", source, re.DOTALL)
        assert _schema_enum_labels() == re.findall(r"'([a-z_]+)'", block.group(1))

    def test_both_locales_carry_a_grid_label_for_every_event(self):
        # The row's own name in the preferences grid. Absent, next-intl renders the KEY PATH — so the
        # grid shows `notifications.events.plan_charged.label` to the reader, and every assertion that
        # merely checks for a non-empty string passes on it.
        for locale in _LOCALES:
            messages = json.loads((_TRANSLATIONS / f"{locale}.json").read_text())
            labelled = {event for event, block in messages["notifications"]["events"].items() if "label" in block}
            assert _python_events() - labelled == set(), locale

    def test_no_locale_carries_copy_for_an_event_that_does_not_exist(self):
        # The direction the check above cannot see: copy for a removed or renamed event reads as
        # coverage while describing nothing.
        for locale in _LOCALES:
            messages = json.loads((_TRANSLATIONS / f"{locale}.json").read_text())
            assert set(messages["notifications"]["events"]) - _python_events() == set(), locale
