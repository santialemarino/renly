import importlib
import pkgutil
import typing
from datetime import date
from decimal import Decimal
from typing import get_args, get_origin

import pytest
from pydantic import AfterValidator, ValidationError

import app.schemas
from app.models.investment import Currency
from app.models.transaction import TransactionType
from app.schemas.auth import _within_bcrypt_limit
from app.schemas.base import RequestBase
from app.schemas.notification import PUSH_ENDPOINT_MAX_LENGTH, PushSubscriptionCreate, PushSubscriptionDelete
from app.schemas.snapshot import SnapshotCreate
from app.schemas.transaction import TransactionCreate, TransactionUpdate

# Every free-text field a request body can carry is length-bounded, DERIVED from the schemas rather
# than listed.
#
# ▸ WHY DERIVED. This file used to hold a hand-written list of twelve schemas whose `notes` had been
# capped, and that list is exactly why the next five were missed: a field added after it was written
# joined no list and so was checked by nothing. Measured before this unit: one 600 KB note wrote 1.2 MB
# and produced a 1,200,917-byte read, and `PUT /settings` accepted 100,000 characters in
# `primary_currency` — which `update_settings` writes straight into the settings JSONB with no
# validation at all, since the sanitising happens on the way OUT.
#
# ▸ WHAT COUNTS AS FREE TEXT. Only a plain `str` (or a list of them). An enum, a date and a Decimal all
# render as strings in JSON Schema but are bounded by their own parsers — a `maxLength` on a date field
# would be noise, and demanding one would train people to add noise.
#
# ▸ WHAT COUNTS AS BOUNDED, and the one exception. `maxLength` on the COMPILED schema, which is
# generated from the validator that actually runs, so this cannot pass while the runtime disagrees —
# the failure mode of reading the annotation instead. The exception is a password: `PlainPassword` caps
# BYTES, because bcrypt's limit is 72 bytes and `max_length` counts CHARACTERS (`á` is two bytes, an
# emoji four), so a character cap there would be the wrong rule rather than a stricter one.
#
# ▸ AND A BEHAVIOURAL TIE. `TestTheCapsAreRealAtRuntime` below builds actual bodies, because every
# assertion above reads a schema, and a schema-only guard proves nothing about what a request does.
# It is what caught this unit's own defect: an edit meant for `GroupSettlementPlanCreate.notes` landed
# on `GroupSettlementResponse.notes` instead — same field name, different description text, a response
# schema — so the scan read as capped while the endpoint still took 100,000 characters.

for _module in pkgutil.iter_modules(app.schemas.__path__):
    importlib.import_module(f"app.schemas.{_module.name}")

NOTES_MAX_LENGTH = 500


# Every request-body schema in the app: RequestBase's subclasses, transitively.
def _request_schemas():
    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    return sorted(set(walk(RequestBase)), key=lambda c: (c.__module__, c.__name__))


def _plain_str(annotation) -> bool:
    if annotation is str:
        return True
    if get_origin(annotation) is typing.Annotated:
        return _plain_str(get_args(annotation)[0])
    return False


# "str" | "container" | None for a field's annotation. PLAIN str only, unwrapping Optional and
# Annotated — an enum, a date or a Decimal is bounded by its own parser and needs no length cap. A
# CONTAINER is free text when any of its type arguments is a plain str, whatever the container: a
# `dict[str, str]`, a `set[str]` or a `tuple[str, ...]` carries a payload exactly as a `list[str]` does,
# and an earlier version of this that only recognised `list` passed all three uncapped.
def _free_text_kind(annotation):
    branches = [a for a in get_args(annotation) if a is not type(None)] or [annotation]
    for branch in branches:
        if _plain_str(branch):
            return "str"
        if get_origin(branch) is not None and any(_plain_str(arg) for arg in get_args(branch)):
            return "container"
    return None


# Whether an annotation is (or unions in) a mapping keyed by plain str — whose KEYS are payload too.
def _has_str_keys(annotation) -> bool:
    branches = [a for a in get_args(annotation) if a is not type(None)] or [annotation]
    return any(get_origin(b) in (dict, typing.Mapping) and get_args(b) and _plain_str(get_args(b)[0]) for b in branches)


# Every string-typed leaf of a compiled property schema, following $ref, the anyOf that `str | None`
# becomes, into array items (a `list[str]`'s ITEM cap is what gets checked rather than the list's),
# into a tuple's `prefixItems`, and into a mapping's values. With `str_keys`, a mapping's KEYS are a
# leaf as well: its `propertyNames` when the schema carries one, and an uncapped string when it does not.
def _string_leaves(prop, defs, depth=0, str_keys=False):
    if depth > 6 or not isinstance(prop, dict):
        return
    if "$ref" in prop:
        yield from _string_leaves(defs.get(prop["$ref"].rsplit("/", 1)[-1], {}), defs, depth + 1, str_keys)
        return
    if prop.get("type") == "string":
        yield prop
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in prop.get(key, []):
            yield from _string_leaves(sub, defs, depth + 1, str_keys)
    if prop.get("type") == "array":
        if isinstance(prop.get("items"), dict):
            yield from _string_leaves(prop["items"], defs, depth + 1)
        for item in prop.get("prefixItems", []):
            yield from _string_leaves(item, defs, depth + 1)
    if prop.get("type") == "object":
        if isinstance(prop.get("additionalProperties"), dict):
            yield from _string_leaves(prop["additionalProperties"], defs, depth + 1)
        if str_keys:
            yield prop.get("propertyNames", {"type": "string"})


# Whether a field carries the bcrypt BYTE ceiling instead of a character one.
def _carries_the_password_cap(field) -> bool:
    def deep(annotation) -> bool:
        for meta in get_args(annotation):
            if isinstance(meta, AfterValidator) and meta.func is _within_bcrypt_limit:
                return True
            if get_args(meta) and deep(meta):
                return True
        return False

    return any(isinstance(m, AfterValidator) and m.func is _within_bcrypt_limit for m in field.metadata) or deep(field.annotation)


# [(dotted name, is_capped)] for every free-text request field in the app.
def _free_text_fields():
    found = []
    for schema in _request_schemas():
        compiled = schema.model_json_schema()
        defs = compiled.get("$defs", {})
        for name, field in schema.model_fields.items():
            if _free_text_kind(field.annotation) is None:
                continue
            dotted = f"{schema.__module__.removeprefix('app.schemas.')}.{schema.__name__}.{name}"
            if _carries_the_password_cap(field):
                found.append((dotted, True))
                continue
            leaves = _string_leaves(compiled["properties"][name], defs, str_keys=_has_str_keys(field.annotation))
            found.append((dotted, _all_capped(leaves)))
    return found


# Whether every string leaf carries a length cap. An enum or a const leaf is bounded by its members.
def _all_capped(leaves) -> bool:
    leaves = [leaf for leaf in leaves if "enum" not in leaf and "const" not in leaf]
    return bool(leaves) and all("maxLength" in leaf for leaf in leaves)


# [(route parameter, is_capped)] for every free-text parameter a ROUTER declares outside a JSON body —
# path, query, header, cookie and form fields — selected by the parameter's own annotation (the same
# plain-str rule as a body field, so a Decimal query parameter or an uploaded file is not free text) and
# checked against `app.openapi()`, the compiled contract, rather than against the annotation.
def _router_parameters():
    from fastapi.dependencies.utils import get_flat_dependant
    from fastapi.routing import APIRoute

    from app.main import app

    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})
    found = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        flat = get_flat_dependant(route.dependant, skip_repeats=True)
        for method in sorted(route.methods):
            operation = spec["paths"][route.path_format][method.lower()]
            compiled = {(p["in"], p["name"]): p.get("schema", {}) for p in operation.get("parameters", [])}
            form = operation.get("requestBody", {}).get("content", {}).get("multipart/form-data", {}).get("schema", {})
            if "$ref" in form:
                form = components.get(form["$ref"].rsplit("/", 1)[-1], {})
            groups = [
                ("path", flat.path_params),
                ("query", flat.query_params),
                ("header", flat.header_params),
                ("cookie", flat.cookie_params),
                ("form", flat.body_params),
            ]
            for location, params in groups:
                for param in params:
                    annotation = param.field_info.annotation
                    if _free_text_kind(annotation) is None:
                        continue
                    where = f"{method} {route.path_format} {location}:{param.alias}"
                    schema = form.get("properties", {}).get(param.alias, {}) if location == "form" else compiled.get((location, param.alias), {})
                    found.append((where, _all_capped(_string_leaves(schema, components, str_keys=_has_str_keys(annotation)))))
    return found


class TestEveryFreeTextRequestFieldIsBounded:
    def test_no_free_text_request_field_is_uncapped(self):
        uncapped = sorted(name for name, capped in _free_text_fields() if not capped)
        assert uncapped == [], (
            f"these request fields accept unbounded text — add max_length (or, for a password, the bcrypt byte ceiling): {uncapped}"
        )

    def test_the_scan_reaches_every_schema_module_and_finds_a_plausible_population(self):
        # Anti-vacuity, and it needs both halves. An empty result satisfies the assertion above
        # perfectly, so this fails when the walk stops matching; and a population that collapses to a
        # handful means the plain-str filter has started excluding real fields.
        fields = _free_text_fields()
        assert len(fields) > 80, f"the scan found only {len(fields)} free-text fields — it has stopped reaching most of them"
        modules = {name.split(".")[0] for name, _ in fields}
        assert {"auth", "expense", "income", "pot", "settings", "group_settlement"} <= modules

    def test_every_notes_field_is_capped_at_the_same_number(self):
        # Breadth the behavioural cases below cannot reach without a minimal body per schema. The old
        # hand list asserted 500 for twelve schemas; this asserts it for EVERY request `notes` there
        # is, so a new one capped at 50 or at 5000 fails rather than being merely "capped".
        wrong = {}
        for schema in _request_schemas():
            compiled = schema.model_json_schema()
            defs = compiled.get("$defs", {})
            for name in schema.model_fields:
                if name != "notes" or _free_text_kind(schema.model_fields[name].annotation) is None:
                    continue
                for leaf in _string_leaves(compiled["properties"][name], defs):
                    if leaf.get("maxLength") != NOTES_MAX_LENGTH:
                        wrong[f"{schema.__module__.removeprefix('app.schemas.')}.{schema.__name__}"] = leaf.get("maxLength")
        assert wrong == {}, f"notes fields capped at something other than {NOTES_MAX_LENGTH}: {wrong}"

    def test_there_are_more_notes_fields_than_the_hand_list_ever_held(self):
        # The point of the rewrite, stated as a number: the list this file used to carry named twelve
        # schemas, and it was already short by five when it was written.
        notes_fields = [name for name, _ in _free_text_fields() if name.endswith(".notes")]
        assert len(notes_fields) >= 17, f"only {len(notes_fields)} notes fields found — the scan has narrowed"

    def test_it_recognises_the_byte_capped_passwords_rather_than_demanding_a_character_cap(self):
        # The one exception, asserted so it stays deliberate. If this stops holding, the guard above
        # would start demanding `max_length` on passwords — which is the WRONG rule, not a stricter
        # one, and adding it would let a 40-character accented passphrase (80 bytes) through to bcrypt.
        capped = {name for name, is_capped in _free_text_fields() if is_capped}
        assert {"auth.LoginRequest.password", "auth.RegisterRequest.password", "user_account.ChangePasswordRequest.new_password"} <= capped


class TestEveryFreeTextRouterParameterIsBounded:
    # A body is not the only way text reaches a handler. A router's path segments, query parameters and
    # multipart form fields are parsed by FastAPI from the URL and the form, carry no schema class, and
    # so were invisible to every check above: the import's `mapping` form field accepted 949 KB and
    # 40,000 keys, and a group invite's `{token}` and signup's `?invite=` took any length at all.
    #
    # ▸ The population is EVERY such parameter, not a selection. Walked, it was 82 uncapped strings —
    # searches, sort keys, currency codes, tickers, tokens — and each has a natural ceiling
    # (`app/schemas/params.py`), so the principled rule turned out to be the simplest one: any plain-str
    # parameter must carry a `maxLength` in the compiled contract. What is NOT free text is decided the
    # same way as for a body field, by the annotation: a Decimal query parameter is bounded by its
    # parser, an enum by its members, a date by its format, an uploaded file by the request-size limit.

    def test_no_free_text_router_parameter_is_uncapped(self):
        uncapped = sorted(where for where, capped in _router_parameters() if not capped)
        assert uncapped == [], f"these router parameters accept unbounded text — add max_length to their Query/Path/Form: {uncapped}"

    def test_the_walk_reaches_every_kind_of_parameter(self):
        # Anti-vacuity per location, since each is read from a different corner of the dependant and the
        # contract: a walk that silently stopped reading one would pass on every parameter there.
        params = [where for where, _ in _router_parameters()]
        assert len(params) > 60, f"the walk found only {len(params)} free-text router parameters"
        for expected in ("path:ticker", "path:token", "query:search", "query:invite", "query:currency", "form:mapping"):
            assert any(where.endswith(expected) for where in params), f"the walk no longer reaches a `{expected}` parameter"

    def test_the_mapping_cap_fits_every_honest_mapping_with_room(self):
        # The premise of IMPORT_MAPPING_MAX_LENGTH, derived from the specs rather than restated: the
        # widest spec's fields, each mapped to a 512-character header, fit in half of it.
        import json

        from app.domain import import_specs
        from app.schemas.params import IMPORT_MAPPING_MAX_LENGTH

        specs = [value for name, value in vars(import_specs).items() if name.endswith("_SPEC")]
        widest = max(specs, key=lambda spec: len(spec.fields))
        honest = json.dumps({field.key: "h" * 512 for field in widest.fields})
        assert len(honest) * 2 <= IMPORT_MAPPING_MAX_LENGTH


class TestEveryContainerOfStrIsFreeText:
    # The selection rule itself, on annotations built for the purpose. A container was once recognised
    # only when it was a `list`, so `dict[str, str]`, `set[str]` and `tuple[str, ...]` passed uncapped.

    @pytest.mark.parametrize(
        "annotation",
        [str, str | None, list[str], set[str], frozenset[str], tuple[str, ...], dict[str, str], dict[str, int], dict[int, str] | None],
    )
    def test_is_free_text(self, annotation):
        assert _free_text_kind(annotation) is not None

    @pytest.mark.parametrize("annotation", [int, Decimal, date, Currency, list[int], dict[int, Decimal], bool | None])
    def test_is_not_free_text(self, annotation):
        assert _free_text_kind(annotation) is None

    def test_an_uncapped_container_of_str_in_a_request_body_is_caught(self):
        # Built rather than found, so the guard is proved against each container shape it claims. Compiled
        # through a TypeAdapter rather than a RequestBase subclass: a subclass would join
        # `_request_schemas()` for the rest of the session and fail the real scan with a probe.
        from pydantic import StringConstraints, TypeAdapter

        capped = typing.Annotated[str, StringConstraints(max_length=10)]
        cases = {
            "dict[str, str]": (dict[str, str], False),
            "set[str]": (set[str], False),
            "tuple[str, ...]": (tuple[str, ...], False),
            "dict[str, int]": (dict[str, int], False),
            "dict[capped, capped]": (dict[capped, capped], True),
            "set[capped]": (set[capped], True),
        }
        for label, (annotation, expected) in cases.items():
            compiled = TypeAdapter(annotation).json_schema()
            leaves = _string_leaves(compiled, compiled.get("$defs", {}), str_keys=_has_str_keys(annotation))
            assert _free_text_kind(annotation) is not None, label
            assert _all_capped(leaves) is expected, label


class TestTheCapsAreRealAtRuntime:
    # The scan reads compiled schemas. These build actual bodies, so "the schema says maxLength" and
    # "the request is refused" are tied together rather than assumed to mean the same thing.

    @pytest.mark.parametrize(
        ("schema_path", "field", "body"),
        [
            (
                "app.schemas.group_settlement:GroupSettlementPlanCreate",
                "notes",
                {"from_member_id": 1, "to_member_id": 2, "date": date(2026, 1, 1), "amount": Decimal("1"), "currency": "ARS"},
            ),
            (
                "app.schemas.pot:PotMovementCreate",
                "notes",
                {"pot_id": 1, "member_id": 1, "type": "contribution", "date": date(2026, 1, 1), "amount": Decimal("1"), "currency": "ARS"},
            ),
            ("app.schemas.auth:RegisterRequest", "name", {"email": "a@b.com", "password": "P4ssw0rd1234"}),
            ("app.schemas.settings:SettingsUpdate", "primary_currency", {}),
            ("app.schemas.settings:SettingsUpdate", "dollar_rate_preference", {}),
        ],
    )
    def test_an_over_long_value_is_refused_by_the_real_body(self, schema_path, field, body):
        module, name = schema_path.split(":")
        schema = getattr(importlib.import_module(module), name)
        with pytest.raises(ValidationError):
            schema(**body, **{field: "x" * 100_000})

    def test_a_list_of_codes_is_bounded_per_item_and_not_only_per_list(self):
        # Both dimensions, because capping only the list length leaves one item carrying the payload.
        from app.schemas.settings import SettingsUpdate

        with pytest.raises(ValidationError):
            SettingsUpdate(preferred_currencies=["x" * 100_000])
        with pytest.raises(ValidationError):
            SettingsUpdate(preferred_currencies=["ARS"] * 100_000)


# A note exactly at the cap is accepted and preserved verbatim; one character over is refused. Driven
# over every capped `notes` the scan finds rather than a list, so a newly-capped one joins by existing.
_NOTES_CASES = [
    ("app.schemas.expense:ExpenseCreate", {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": "USD"}),
    ("app.schemas.expense:ExpenseUpdate", {}),
    ("app.schemas.income:IncomeCreate", {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": "USD"}),
    ("app.schemas.card_settlement:CardSettlementCreate", {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": "USD"}),
    (
        "app.schemas.transaction:TransactionCreate",
        {"date": date(2026, 1, 1), "amount": Decimal("100.00"), "currency": Currency.USD, "type": TransactionType.buy},
    ),
    ("app.schemas.account:AccountCreate", {"name": "A", "type": "bank", "currency": "USD", "opening_date": date(2026, 1, 1)}),
    ("app.schemas.pot:PotOpeningCreate", {"pot_id": 1, "date": date(2026, 1, 1), "value": Decimal("1"), "shares": {}}),
]


@pytest.mark.parametrize(("schema_path", "base"), _NOTES_CASES, ids=[p.split(":")[1] for p, _ in _NOTES_CASES])
def test_notes_at_the_cap_are_kept_and_one_character_over_is_refused(schema_path, base):
    module, name = schema_path.split(":")
    schema = getattr(importlib.import_module(module), name)
    note = "x" * NOTES_MAX_LENGTH
    assert schema(**base, notes=note).notes == note
    with pytest.raises(ValidationError):
        schema(**base, notes="x" * (NOTES_MAX_LENGTH + 1))


# A zero or negative transaction amount is rejected — a negative "deposit" would silently
# flip to a withdrawal in every downstream formula.
@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-5.00")])
def test_transaction_amount_must_be_positive(amount):
    kwargs = {"date": date(2026, 1, 1), "currency": Currency.USD, "type": TransactionType.buy}
    with pytest.raises(ValidationError):
        TransactionCreate(amount=amount, **kwargs)
    with pytest.raises(ValidationError):
        TransactionUpdate(amount=amount)


# Snapshot value zero is legitimate (a fully-withdrawn investment); negative is not.
def test_snapshot_value_zero_accepted_negative_rejected():
    kwargs = {"date": date(2026, 1, 1), "currency": Currency.USD}
    body = SnapshotCreate(value=Decimal("0"), **kwargs)
    assert body.value == Decimal("0")
    with pytest.raises(ValidationError):
        SnapshotCreate(value=Decimal("-1.00"), **kwargs)


# The push endpoint is bounded at the request even though its column is unbounded TEXT, and the reason
# is not tidiness: the column is UNIQUE, and a btree key cannot exceed 2704 bytes, so an over-long
# endpoint would fail inside the index — `index row size N exceeds btree version 4 maximum 2704`, a 500
# rather than a 422. Both bodies carry the bound, since both compare on the endpoint.
@pytest.mark.parametrize("schema", [PushSubscriptionCreate, PushSubscriptionDelete])
def test_a_push_endpoint_is_bounded_below_the_index_key_limit(schema):
    assert PUSH_ENDPOINT_MAX_LENGTH < 2704
    extras = {"p256dh": "k", "auth": "a"} if schema is PushSubscriptionCreate else {}
    at_cap = schema(endpoint="https://push.test/" + "x" * (PUSH_ENDPOINT_MAX_LENGTH - 18), **extras)
    assert len(at_cap.endpoint) == PUSH_ENDPOINT_MAX_LENGTH
    with pytest.raises(ValidationError):
        schema(endpoint="x" * (PUSH_ENDPOINT_MAX_LENGTH + 1), **extras)
