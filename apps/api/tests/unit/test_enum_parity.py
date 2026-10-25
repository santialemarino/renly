# Every Python `StrEnum` the API declares against every TypeScript list the web keeps of the same values.
#
# `test_notification_event_surface.py` built the instrument — a set difference both ways, the other
# language's source read rather than restated — and pointed it at one list. This is the same instrument
# pointed at all of them. The defect it closes is the one that list was guarding: a value is added to,
# renamed in or dropped from the enum, the web's copy does not learn about it, and both suites stay green
# because each only ever iterates its own side.
#
# What makes it catch the CLASS rather than the pairs someone remembered:
#
# * The Python side is DERIVED: every `StrEnum` under `app/` must be either paired below or declared
#   server-only with a reason, so a new enum fails here until somebody decides which it is.
# * The web side is SCANNED: any `as const` literal array or literal union whose values EQUAL an enum's must be a
#   registered twin, so a new transcription on the web fails here too.
# * A picker offering FEWER values than its enum is not tolerated silently — the values it omits (or, for
#   a derived status, adds) are DECLARED, and the declaration is asserted exactly: a subset that heals or
#   grows fails as loudly as one that drifts.
#
# Which pairs are twins cannot be derived (the two sides name them differently: `AuditEntityType` is
# `ACTIVITY_ENTITY_TYPES`, `GroupMemberRole` is `GROUP_ROLES`), so `_TWINS` is a hand list — and it is
# the invariant, its size pinned.

import ast
import importlib
import re
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import NamedTuple

import pytest

from app.domain.reconciliation import SYSTEM_EXPENSE_CATEGORIES, SYSTEM_INCOME_CATEGORIES
from app.models.investment import InvestmentCategory
from app.services import asset_price_service

# Reads the web app's source, so it runs on every commit whichever app is staged (see the testing skill).
pytestmark = pytest.mark.cross_app

_REPO = Path(__file__).resolve().parents[4]
_API_APP = _REPO / "apps" / "api" / "app"
_WEB = _REPO / "apps" / "web"
_WEB_SKIP = {"node_modules", ".next", "tests"}


# One web transcription of a Python enum: where it lives, and what it deliberately differs by.
class Twin(NamedTuple):
    enum: str
    web_file: str
    web_symbol: str
    web_omits: frozenset[str] = frozenset()
    web_adds: frozenset[str] = frozenset()


_CATEGORIES = "lib/constants/categories.ts"
_POTS = "lib/constants/pots.ts"
_TRANSACTION_FORM = "app/(protected)/snapshots/snapshots-form-schema.ts"

# Every (enum, web list) pair. A subset or superset names exactly what it leaves out or adds, and why.
_TWINS: tuple[Twin, ...] = (
    Twin("AccountType", "lib/constants/accounts.ts", "ACCOUNT_TYPES"),
    Twin("AuditAction", "lib/constants/shared-activity.ts", "ACTIVITY_ACTIONS"),
    Twin("AuditEntityType", "lib/constants/shared-activity.ts", "ACTIVITY_ENTITY_TYPES"),
    # The confirm endpoint answers only the two email flows; a password reset has its own route.
    Twin("AuthTokenType", "lib/auth-api.ts", "ConfirmEmailKind", web_omits=frozenset({"password_reset"})),
    Twin("EmailCadence", "lib/constants/notifications.ts", "NOTIFICATION_EMAIL_CADENCES"),
    # The picker's set: the system categories are written by a reconciliation, never chosen by a person.
    Twin("ExpenseCategory", _CATEGORIES, "EXPENSE_CATEGORIES", web_omits=frozenset(c.value for c in SYSTEM_EXPENSE_CATEGORIES)),
    Twin("FeedbackCategory", "lib/constants/feedback.ts", "FEEDBACK_CATEGORIES"),
    Twin("GroupKind", "lib/constants/groups.ts", "GROUP_KINDS"),
    Twin("GroupMemberRole", "lib/constants/groups.ts", "GROUP_ROLES"),
    Twin("GroupSettlementStatus", "lib/api/group-settlements.ts", "SettlementStatus"),
    Twin("ImportEntity", "app/(protected)/data/_components/import-section.tsx", "DATA_TYPES"),
    # As for expenses: system-written categories are not offered by the picker.
    Twin("IncomeCategory", _CATEGORIES, "INCOME_CATEGORIES", web_omits=frozenset(c.value for c in SYSTEM_INCOME_CATEGORIES)),
    Twin("IncomeDestination", "lib/constants/shared-income.ts", "INCOME_DESTINATIONS"),
    Twin("InvestmentCategory", _CATEGORIES, "INVESTMENT_CATEGORIES"),
    # `expired` is derived on read (invite_service.effective_status), never stored.
    Twin("InviteStatus", "lib/api/invites.ts", "InviteStatus", web_adds=frozenset({"expired"})),
    Twin("ListScope", "lib/api/types.ts", "ListScope"),
    Twin("MovementKind", "lib/constants/accounts.ts", "MOVEMENT_KINDS"),
    Twin("MovementSource", "lib/constants/accounts.ts", "MovementSource"),
    Twin("NotificationChannel", "lib/constants/notifications.ts", "NOTIFICATION_CHANNELS"),
    # The fuller check of this pair, across every list an event touches, is test_notification_event_surface.py.
    Twin("NotificationEvent", "lib/constants/notifications.ts", "NOTIFICATION_EVENTS"),
    Twin("OwnershipEventType", _POTS, "OWNERSHIP_EVENT_TYPES"),
    # The movements endpoint takes these two; an opening and a re-agreement have endpoints of their own.
    Twin("OwnershipEventType", _POTS, "POT_MOVEMENT_TYPES", web_omits=frozenset({"opening", "reagreement"})),
    Twin("PaymentMethod", _CATEGORIES, "PAYMENT_METHODS"),
    Twin("PotCadence", _POTS, "POT_CADENCES"),
    Twin("PotCadence", "lib/api/snapshots.ts", "SnapshotCadence"),
    Twin("PotSeriesInterval", _POTS, "PotSeriesInterval"),
    Twin("PotSeriesInterval", "lib/api/snapshots.ts", "SnapshotGridInterval"),
    Twin("PotVisibility", _POTS, "POT_VISIBILITIES"),
    Twin("SampleEntity", "components/sample/sample-actions.ts", "SampleEntity"),
    Twin("SignupMode", "lib/auth-api.ts", "SignupMode"),
    Twin("SplitMethod", "lib/constants/shared-expenses.ts", "SPLIT_METHODS"),
    # The methods that carry a per-member figure; an equal split has none to enter.
    Twin("SplitMethod", "app/(protected)/shared/split-rules.ts", "SplitFigureKind", web_omits=frozenset({"equal"})),
    Twin("TransactionType", _TRANSACTION_FORM, "TRANSACTION_TYPES"),
    # The types that take units OUT of a holding, which the form checks against what is held.
    Twin("TransactionType", _TRANSACTION_FORM, "TRANSACTION_TYPES_OUTGOING", web_omits=frozenset({"buy", "deposit"})),
)

# Enums with no web transcription at all, and why none is needed.
_SERVER_ONLY: dict[str, str] = {
    "Currency": "the web takes currency codes from the API's responses and settings; it never enumerates them",
    "EmailProvider": "server configuration",
    "Environment": "server configuration",
    "ExchangeRatePair": "the web names one pair by literal when it reads the rates the API returns",
    "UserPlan": "billing is not exposed to the web yet",
}

_TWIN_COUNT = 34


# Every `StrEnum` class defined under `app/`, by name — found by parsing the source, then imported.
@cache
def _python_enums() -> dict[str, type[StrEnum]]:
    found: dict[str, type[StrEnum]] = {}
    for path in sorted(_API_APP.rglob("*.py")):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id == "StrEnum" for b in node.bases):
                module = ".".join(("app", *path.relative_to(_API_APP).with_suffix("").parts))
                assert node.name not in found, f"two StrEnums named {node.name}"
                found[node.name] = getattr(importlib.import_module(module), node.name)
    return found


# The string literals one web declaration holds: a `const X = [...] as const`, a `const X = {...} as const`
# (the object's VALUES — its keys are bare), or a `type X = 'a' | 'b'` union. Asserted to be found and
# to be literals only, so a rename or a switch to `(typeof …)[number]` fails here rather than reading
# as an empty or partial set.
def _web_values(twin: Twin) -> set[str]:
    path = _WEB / twin.web_file
    source = path.read_text()
    const = re.search(rf"\bconst {twin.web_symbol}\b[^=]*= ([\[{{].*?[\]}}]) as const", source, re.DOTALL)
    if const is not None:
        values = re.findall(r"'([^']*)'", const.group(1))
    else:
        union = re.search(rf"\btype {twin.web_symbol} =(.*?);", source, re.DOTALL)
        assert union is not None, f"{twin.web_symbol} not found in {path}"
        assert re.fullmatch(r"(\s*\|?\s*'[^']*')+\s*", union.group(1)), f"{twin.web_symbol} is not a union of string literals"
        values = re.findall(r"'([^']*)'", union.group(1))
    assert values, f"no values parsed out of {twin.web_symbol}"
    return set(values)


_ARRAY = re.compile(r"\bconst (\w+)\b[^=;]*= \[([^\]]*)\] as const", re.DOTALL)
_UNION = re.compile(r"\btype (\w+) =((?:\s*\|?\s*'[^']*')+)\s*;")


# Every literal list and literal union in the web app's source, as (file, symbol) -> values.
def _web_literal_lists() -> dict[tuple[str, str], set[str]]:
    found: dict[tuple[str, str], set[str]] = {}
    for path in _WEB.rglob("*.ts*"):
        if _WEB_SKIP & set(path.relative_to(_WEB).parts):
            continue
        source = path.read_text()
        for pattern in (_ARRAY, _UNION):
            for symbol, body in pattern.findall(source):
                values = set(re.findall(r"'([^']*)'", body))
                if values:
                    found[(str(path.relative_to(_WEB)), symbol)] = values
    return found


class TestEveryEnumIsClassified:
    def test_the_derived_population_is_not_empty(self):
        enums = sorted(_python_enums())
        print("StrEnums under app/:", enums)
        assert len(enums) > 20

    def test_every_enum_is_paired_or_declared_server_only(self):
        # A new enum fails here until somebody decides whether the web transcribes it.
        twinned = {twin.enum for twin in _TWINS}
        unclassified = set(_python_enums()) - twinned - set(_SERVER_ONLY)
        assert not unclassified, f"StrEnums neither in _TWINS nor in _SERVER_ONLY: {sorted(unclassified)}"

    def test_no_entry_names_an_enum_that_does_not_exist(self):
        stale = ({twin.enum for twin in _TWINS} | set(_SERVER_ONLY)) - set(_python_enums())
        assert not stale, f"entries naming no StrEnum: {sorted(stale)}"

    def test_no_enum_is_both_twinned_and_server_only(self):
        assert not {twin.enum for twin in _TWINS} & set(_SERVER_ONLY)

    def test_the_pair_list_is_the_size_it_was_reviewed_at(self):
        # Dropping a pair loses its guard silently; this makes removing one a deliberate edit.
        assert len(_TWINS) == _TWIN_COUNT
        assert len({(twin.web_file, twin.web_symbol) for twin in _TWINS}) == _TWIN_COUNT


class TestEveryTwinAgrees:
    @pytest.mark.parametrize("twin", _TWINS, ids=lambda twin: f"{twin.enum}-{twin.web_symbol}")
    def test_the_web_list_differs_from_the_enum_by_exactly_what_it_declares(self, twin: Twin):
        python = {member.value for member in _python_enums()[twin.enum]}
        web = _web_values(twin)
        assert python - web == twin.web_omits, f"{twin.enum} values missing from {twin.web_symbol} ({twin.web_file})"
        assert web - python == twin.web_adds, f"{twin.web_symbol} ({twin.web_file}) values that {twin.enum} lacks"

    def test_every_web_list_equal_to_an_enum_is_a_registered_twin(self):
        # The web-side half of the derivation: a new transcription whose values match an enum today is
        # the one that drifts tomorrow, so it has to be registered before it can.
        by_values = {frozenset(member.value for member in enum): name for name, enum in _python_enums().items()}
        registered = {(twin.web_file, twin.web_symbol) for twin in _TWINS}
        lists = _web_literal_lists()
        assert lists, "the web scan found no literal lists"
        unregistered = sorted(
            f"{symbol} ({file}) == {by_values[frozenset(values)]}"
            for (file, symbol), values in lists.items()
            if frozenset(values) in by_values and (file, symbol) not in registered
        )
        assert not unregistered, f"web lists equal to a StrEnum but not in _TWINS: {unregistered}"


class TestPricedCategoriesAgree:
    # `_CATEGORY_PROVIDERS` decides which categories get a price at all; the web's `hasTicker` decides
    # which forms ask for a ticker. A category in one and not the other either asks for a ticker nothing
    # will ever price, or is priced from a ticker nobody could enter.

    @staticmethod
    def _web_has_ticker() -> dict[str, bool]:
        source = (_WEB / _CATEGORIES).read_text()
        block = re.search(r"export const CATEGORY_CAPABILITIES\b[^=]*= \{(.*?)\n\};", source, re.DOTALL)
        assert block is not None, "CATEGORY_CAPABILITIES not found"
        rows = re.findall(r"^\s*(\w+): \{ hasTicker: (true|false)\b", block.group(1), re.MULTILINE)
        parsed = {category: ticker == "true" for category, ticker in rows}
        assert set(parsed) == {category.value for category in InvestmentCategory}, "CATEGORY_CAPABILITIES rows not all parsed"
        return parsed

    def test_the_priced_categories_are_the_ones_the_web_asks_a_ticker_for(self):
        priced = {category.value for category in asset_price_service._CATEGORY_PROVIDERS}
        assert priced, "_CATEGORY_PROVIDERS is empty"
        ticker = {category for category, has_ticker in self._web_has_ticker().items() if has_ticker}
        assert priced == ticker
