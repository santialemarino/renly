import collections.abc
import dataclasses
import gc
import importlib
import pkgutil
import types
import typing
from datetime import date
from decimal import Decimal
from typing import get_args, get_origin

import pytest
from pydantic import AfterValidator, AnyUrl, BaseModel, Field, HttpUrl, SecretBytes, SecretStr, TypeAdapter, ValidationError
from pydantic.networks import _BaseMultiHostUrl, _BaseUrl

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
# ▸ AND A BEHAVIOURAL TIE. `TestTheCapsAreRealAtRuntime` below runs every plain-str field's real
# validator, because every assertion above reads a schema, and a schema-only guard proves nothing about
# what a request does.
# It is what caught this unit's own defect: an edit meant for `GroupSettlementPlanCreate.notes` landed
# on `GroupSettlementResponse.notes` instead — same field name, different description text, a response
# schema — so the scan read as capped while the endpoint still took 100,000 characters.

for _module in pkgutil.iter_modules(app.schemas.__path__):
    importlib.import_module(f"app.schemas.{_module.name}")

NOTES_MAX_LENGTH = 500


# Every model a request body can carry: RequestBase's subclasses, transitively, PLUS every structured type
# reachable from their fields at any depth. The second half is what covers a plain `BaseModel` nested in a
# request (a `list[Item]` field): its own string fields are payload the request accepts, and a scan of
# RequestBase subclasses alone would never read them.
def _request_schemas():
    def subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from subclasses(sub)

    return sorted(_reachable_models(set(subclasses(RequestBase))), key=lambda c: (c.__module__, c.__name__))


# Whether a type is a structure pydantic validates field by field: a pydantic model, a `TypedDict` or a
# dataclass (standard or pydantic). The last two are not models, so a walk keyed on `BaseModel` alone
# passed straight over them — and their string fields are payload exactly as a nested model's are.
def _is_structure(annotation) -> bool:
    if not isinstance(annotation, type):
        return False
    return issubclass(annotation, BaseModel) or typing.is_typeddict(annotation) or dataclasses.is_dataclass(annotation)


# {field name: annotation} for any structure `_is_structure` accepts, `Annotated` metadata kept.
def _structure_fields(structure) -> dict:
    if issubclass(structure, BaseModel):
        return {name: field.annotation for name, field in structure.model_fields.items()}
    return typing.get_type_hints(structure, include_extras=True)


# The given models plus every structure their fields reach, at any depth and through any container.
def _reachable_models(roots: set) -> set:
    def models_in(annotation):
        annotation = _unwrap(annotation)
        if _is_structure(annotation):
            yield annotation
        for arg in get_args(annotation):
            yield from models_in(arg)

    found = set(roots)
    pending = list(found)
    while pending:
        for annotation in _structure_fields(pending.pop()).values():
            for model in models_in(annotation):
                if model not in found:
                    found.add(model)
                    pending.append(model)
    return found


# The compiled JSON Schema of a structure: a model's own, a TypedDict's or dataclass's through a TypeAdapter.
def _compiled(structure) -> dict:
    if issubclass(structure, BaseModel):
        return structure.model_json_schema()
    return TypeAdapter(structure).json_schema()


# Whether a structure keeps keys it does not declare. A model or pydantic dataclass with `extra="allow"`
# stores every unknown key verbatim, and those keys and values are free text no field annotation describes,
# so nothing in this file can bound them.
def _allows_extra(structure) -> bool:
    config = structure.model_config if issubclass(structure, BaseModel) else getattr(structure, "__pydantic_config__", {})
    return config.get("extra") == "allow"


# An annotation with any `Annotated[...]` wrapping removed — its metadata is constraints, not a type.
def _unwrap(annotation):
    while get_origin(annotation) is typing.Annotated:
        annotation = get_args(annotation)[0]
    return annotation


# The non-None members of a union (`X | None`, `Optional[X]`, `Union[...]`), each unwrapped, or the
# unwrapped annotation itself when it is not a union. Only a UNION is split: splitting any generic by
# its arguments reads `dict[str, int]` as the two branches `str` and `int`, which is how the key check
# once never saw a mapping at all.
def _union_branches(annotation) -> list:
    annotation = _unwrap(annotation)
    if get_origin(annotation) in (typing.Union, types.UnionType):
        return [_unwrap(a) for a in get_args(annotation) if a is not type(None)]
    return [annotation]


def _plain_str(annotation) -> bool:
    return _unwrap(annotation) is str


# `Any` and `object` accept a string of any length, so wherever they appear they are free text too. So do
# `bytes`, the secret types and every URL type: each arrives as a JSON string of any length, and none is
# bounded by a parser the way a date or an enum is (`AnyUrl` takes any length; `HttpUrl` carries its own
# 2083 cap, which the compiled schema shows, so it reads as capped rather than being exempted by name).
_STRING_LIKE = (str, typing.Any, object, bytes, SecretStr, SecretBytes)


def _accepts_any_string(annotation) -> bool:
    annotation = _unwrap(annotation)
    if annotation in _STRING_LIKE:
        return True
    return isinstance(annotation, type) and issubclass(annotation, (_BaseUrl, _BaseMultiHostUrl))


# Whether a plain `str` appears ANYWHERE in an annotation's type arguments, at any depth and through
# unions and `Annotated`. One level was not enough: `list[list[str]]` and `dict[int, list[str]]` carry
# the same payload as `list[str]` and passed uncapped when only the outer arguments were inspected.
def _contains_plain_str(annotation) -> bool:
    annotation = _unwrap(annotation)
    if _accepts_any_string(annotation):
        return True
    return any(_contains_plain_str(arg) for arg in get_args(annotation) if arg is not type(None))


# "str" | "container" | None for a field's annotation. PLAIN str only, unwrapping Optional and
# Annotated — an enum, a date or a Decimal is bounded by its own parser and needs no length cap. A
# CONTAINER is free text when a plain str appears anywhere inside it, whatever the container and however
# deep: a `dict[str, str]`, a `set[str]`, a `tuple[str, ...]` or a `list[list[str]]` carries a payload
# exactly as a `list[str]` does.
def _free_text_kind(annotation):
    for branch in _union_branches(annotation):
        if _accepts_any_string(branch):
            return "str"
        if get_origin(branch) is not None and _contains_plain_str(branch):
            return "container"
    return None


# Whether an annotation holds, at any depth, a mapping keyed by plain str — whose KEYS are payload too.
# `collections.abc.Mapping`, not `typing.Mapping`: `get_origin(typing.Mapping[str, X])` answers the ABC,
# so comparing against the typing alias would never match.
def _has_str_keys(annotation) -> bool:
    annotation = _unwrap(annotation)
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    if get_origin(annotation) in (dict, collections.abc.Mapping) and args and _plain_str(args[0]):
        return True
    return any(_has_str_keys(arg) for arg in args)


# The leaf that stands for "any string at all": what an unconstrained schema (`Any`, `object`, a mapping's
# `additionalProperties: true`) accepts, and what a str-keyed mapping with no `propertyNames` accepts as
# a key. It has no maxLength, so any field reaching it reads as uncapped.
_UNCAPPED = {"type": "string"}


# Every string-typed leaf of a compiled property schema, at any depth. It follows `$ref`; the `anyOf` /
# `oneOf` / `allOf` a union becomes; an array's `items` and a tuple's `prefixItems` (so a `list[str]`'s
# ITEM cap is what is checked, not the list's); and a mapping's values. An UNCONSTRAINED schema — `{}` or
# `true`, which is what `Any`, `object` and `dict[str, Any]`'s values compile to — is an uncapped leaf,
# because it accepts a string of any length.
#
# A mapping is an object with no `properties`. With `str_keys`, EVERY mapping reached yields its keys as a
# leaf — its `propertyNames` when the schema carries one, uncapped when it does not — whether its
# `additionalProperties` is a schema or `true`. JSON Schema cannot tell a str-keyed mapping from an
# int-keyed one, so once the annotation holds a str-keyed mapping anywhere, every mapping in the field is
# held to a key cap. That errs in one direction only: an int-keyed mapping sitting beside a capped
# str-keyed one is flagged although it is bounded. It never lets an uncapped key through.
#
# NOT covered here, and covered elsewhere: an object WITH `properties` is a nested structure — a pydantic
# model, a `TypedDict` or a dataclass — whose fields are scanned as a schema of their own (`_request_schemas`
# reaches every one a request can carry), so this does not descend into it. The extra keys a structure with
# `extra="allow"` keeps are refused outright by `test_no_request_structure_keeps_undeclared_keys`, since no
# annotation describes them. Nesting deeper than MAX_DEPTH yields an uncapped leaf rather than stopping
# quietly, so a field too deep to read (or a recursive type alias) fails the scan by name instead of
# passing unread. Still read as UNCAPPED although bounded: a pattern or a custom validator that bounds a
# string without a `maxLength` (the bcrypt byte cap is the one such rule recognised, by name) — an error
# in the safe direction.
MAX_DEPTH = 10


def _string_leaves(prop, defs, depth=0, str_keys=False):
    if depth > MAX_DEPTH:
        yield _UNCAPPED
        return
    if prop is True or prop == {}:
        yield _UNCAPPED
        return
    if not isinstance(prop, dict):
        return
    if "$ref" in prop:
        yield from _string_leaves(defs.get(prop["$ref"].rsplit("/", 1)[-1], {"properties": {}}), defs, depth + 1, str_keys)
        return
    if prop.get("type") == "string":
        yield prop
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in prop.get(key, []):
            yield from _string_leaves(sub, defs, depth + 1, str_keys)
    if prop.get("type") == "array":
        if "items" in prop:
            yield from _string_leaves(prop["items"], defs, depth + 1, str_keys)
        for item in prop.get("prefixItems", []):
            yield from _string_leaves(item, defs, depth + 1, str_keys)
    if prop.get("type") == "object" and "properties" not in prop:
        yield from _string_leaves(prop.get("additionalProperties", True), defs, depth + 1, str_keys)
        if str_keys:
            yield prop.get("propertyNames", _UNCAPPED)


# Whether a field carries the bcrypt BYTE ceiling instead of a character one. A model field keeps its
# validators in `metadata`; a TypedDict or dataclass field keeps them in its `Annotated` annotation.
def _carries_the_password_cap(structure, name) -> bool:
    def deep(annotation) -> bool:
        for meta in get_args(annotation):
            if isinstance(meta, AfterValidator) and meta.func is _within_bcrypt_limit:
                return True
            if get_args(meta) and deep(meta):
                return True
        return False

    metadata = structure.model_fields[name].metadata if issubclass(structure, BaseModel) else []
    return any(isinstance(m, AfterValidator) and m.func is _within_bcrypt_limit for m in metadata) or deep(_structure_fields(structure)[name])


def _dotted(structure, name) -> str:
    return f"{structure.__module__.removeprefix('app.schemas.')}.{structure.__name__}.{name}"


# [(dotted name, is_capped)] for every free-text field of the given structures (every request one by default).
def _free_text_fields(structures=None):
    found = []
    for schema in _request_schemas() if structures is None else structures:
        compiled = _compiled(schema)
        defs = compiled.get("$defs", {})
        for name, annotation in _structure_fields(schema).items():
            if _free_text_kind(annotation) is None:
                continue
            if _carries_the_password_cap(schema, name):
                found.append((_dotted(schema, name), True))
                continue
            leaves = _string_leaves(compiled["properties"][name], defs, str_keys=_has_str_keys(annotation))
            found.append((_dotted(schema, name), _all_capped(leaves)))
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
            compiled = _compiled(schema)
            defs = compiled.get("$defs", {})
            for name, annotation in _structure_fields(schema).items():
                if name != "notes" or _free_text_kind(annotation) is None:
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

    def test_no_request_structure_keeps_undeclared_keys(self):
        # `extra="allow"` stores every unknown key and its value verbatim — free text that no field
        # annotation describes and so nothing above can bound. Refused outright rather than scanned.
        allowing = sorted(_dotted(s, "*") for s in _request_schemas() if _allows_extra(s))
        assert allowing == [], f"these request structures keep undeclared keys (extra='allow'): {allowing}"

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
        [
            str,
            str | None,
            list[str],
            set[str],
            frozenset[str],
            tuple[str, ...],
            dict[str, str],
            dict[str, int],
            dict[int, str] | None,
            list[list[str]],
            dict[int, list[str]],
            list[list[str]] | None,
            dict[int, list[str]] | None,
            typing.Annotated[list[list[str]] | None, "meta"],
            typing.Any,
            object,
            dict[int, typing.Any] | None,
        ],
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
            "Mapping[str, int]": (typing.Mapping[str, int], False),
            "Mapping[capped, int]": (typing.Mapping[capped, int], True),
            "dict[str, capped]": (dict[str, capped], False),
            "list[list[str]]": (list[list[str]], False),
            "dict[int, list[str]]": (dict[int, list[str]], False),
            "list[dict[str, capped]]": (list[dict[str, capped]], False),
            "list[list[capped]]": (list[list[capped]], True),
            "list[dict[capped, capped]]": (list[dict[capped, capped]], True),
            # A mapping whose values are `Any` compiles to `additionalProperties: true` — no value schema at
            # all — and once passed with a capped leaf beside it.
            "capped | dict[str, Any]": (capped | dict[str, typing.Any], False),
            "tuple[capped, dict[str, Any]]": (tuple[capped, dict[str, typing.Any]], False),
            "tuple[capped, dict[str, capped]]": (tuple[capped, dict[str, capped]], False),
            "list[capped | dict[str, Any]]": (list[capped | dict[str, typing.Any]], False),
            "dict[str, object] | capped": (dict[str, object] | capped, False),
            "dict[capped, Any]": (dict[capped, typing.Any], False),
            "capped | Any": (capped | typing.Any, False),
            # The one deliberate false positive, pinned so it stays a choice: JSON Schema cannot tell the
            # int-keyed outer mapping from the str-keyed inner one, so both are held to a key cap.
            "dict[int, dict[capped, capped]]": (dict[int, dict[capped, capped]], False),
            "dict[capped, capped]": (dict[capped, capped], True),
            "set[capped]": (set[capped], True),
        }
        for label, (annotation, expected) in cases.items():
            compiled = TypeAdapter(annotation).json_schema()
            leaves = _string_leaves(compiled, compiled.get("$defs", {}), str_keys=_has_str_keys(annotation))
            assert _free_text_kind(annotation) is not None, label
            assert _all_capped(leaves) is expected, label


class TestNestedModelsAreScanned:
    def test_a_plain_model_nested_in_a_request_is_reached(self):
        # A plain BaseModel carried by a request field is payload the request accepts; the scan reaches it
        # through the field, at any depth, rather than only reading RequestBase subclasses.
        class Leaf(BaseModel):
            label: str

        class Middle(BaseModel):
            leaves: list[Leaf] | None = None

        class Probe(BaseModel):
            by_key: dict[int, Middle]

        assert _reachable_models({Probe}) == {Probe, Middle, Leaf}

    def test_the_real_scan_reads_through_a_request_into_its_models(self):
        # Through `_request_schemas` itself, so the scan cannot quietly go back to RequestBase subclasses
        # only. Every string here is capped, so the probe cannot fail the real guard if it outlives this
        # test in the subclass registry.
        class CappedItem(BaseModel):
            label: str = Field(description="probe", max_length=5)

        class ProbeCarrier(RequestBase):
            items: list[CappedItem] = Field(default_factory=list, description="probe")

        try:
            assert CappedItem in _request_schemas()
        finally:
            del ProbeCarrier
            gc.collect()


class TestWhatTheScanOnceCouldNotSee:
    # Each case below passed the scan while being read by nothing: no request schema used any of them, so
    # the guard was green, and it would have stayed green the day one did. Built from probes rather than
    # found, so each is proved against the shape it claims. Probes are plain models, never RequestBase
    # subclasses, so none can join the real scan for the rest of the session.

    @pytest.mark.parametrize("annotation", [bytes, SecretStr, SecretBytes, AnyUrl, HttpUrl, list[bytes], dict[int, AnyUrl] | None])
    def test_string_like_types_are_free_text(self, annotation):
        assert _free_text_kind(annotation) is not None

    @pytest.mark.parametrize(
        ("annotation", "capped"),
        [
            (bytes, False),
            (typing.Annotated[bytes, Field(max_length=10)], True),
            (SecretStr, False),
            (typing.Annotated[SecretStr, Field(max_length=10)], True),
            (AnyUrl, False),
            # HttpUrl carries pydantic's own 2083-character ceiling in the compiled schema.
            (HttpUrl, True),
        ],
    )
    def test_an_uncapped_string_like_field_reads_as_uncapped(self, annotation, capped):
        class Probe(BaseModel):
            value: annotation

        assert _free_text_fields({Probe}) == [(_dotted(Probe, "value"), capped)]

    def test_a_typeddict_nested_in_a_request_is_reached_and_its_text_checked(self):
        class Labels(typing.TypedDict):
            label: str
            code: typing.Annotated[str, Field(max_length=5)]

        class Probe(BaseModel):
            labels: list[Labels]

        reached = _reachable_models({Probe})
        assert Labels in reached
        assert dict(_free_text_fields({Labels})) == {_dotted(Labels, "label"): False, _dotted(Labels, "code"): True}

    def test_a_dataclass_nested_in_a_request_is_reached_and_its_text_checked(self):
        @dataclasses.dataclass
        class Line:
            text: str
            ref: typing.Annotated[str, Field(max_length=5)]

        class Probe(BaseModel):
            lines: dict[int, Line] | None = None

        reached = _reachable_models({Probe})
        assert Line in reached
        assert dict(_free_text_fields({Line})) == {_dotted(Line, "text"): False, _dotted(Line, "ref"): True}

    def test_a_structure_keeping_undeclared_keys_is_flagged(self):
        from pydantic import ConfigDict

        class Open(BaseModel):
            model_config = ConfigDict(extra="allow")

        class Closed(BaseModel):
            pass

        assert _allows_extra(Open) and not _allows_extra(Closed)
        assert _allows_extra(RequestBase) is False

    def test_nesting_past_the_depth_limit_reads_as_uncapped_rather_than_unread(self):
        from pydantic import StringConstraints

        capped = typing.Annotated[str, StringConstraints(max_length=10)]

        def nested(levels):
            annotation = capped
            for _ in range(levels):
                annotation = list[annotation]
            return annotation

        def reads_capped(annotation):
            compiled = TypeAdapter(annotation).json_schema()
            return _all_capped(_string_leaves(compiled, compiled.get("$defs", {})))

        assert reads_capped(nested(MAX_DEPTH)) is True
        assert reads_capped(nested(MAX_DEPTH + 1)) is False


# Every plain-str request field the scan found, as (dotted name, model, field) — the population the runtime
# checks below are driven over. A pydantic model only: a TypedDict or dataclass has no instance to assign to,
# and none is carried by a request today (the static scan above reads them all the same).
def _runtime_str_fields(name_filter=None):
    found = []
    for schema in _request_schemas():
        if not issubclass(schema, BaseModel):
            continue
        for name, field in schema.model_fields.items():
            if _free_text_kind(field.annotation) != "str" or (name_filter is not None and name != name_filter):
                continue
            found.append(pytest.param(schema, name, id=_dotted(schema, name)))
    return found


# Runs one field's REAL validation — its annotation, its constraints and every field validator the model
# declares — by assigning to an instance built without validation, and returns (the errors located AT that
# field, the stored value or None). That is what lets the check reach every field without a hand-written
# valid body per schema: the body is what made the old list a list. A model-level validator then runs too,
# against an instance missing every other field, so its verdict (an error at no field, or an
# AttributeError reading a field that was never set) says nothing about this one and is set aside — it
# can only run once the field itself has validated.
def _assign(schema, name, value):
    instance = schema.model_construct()
    try:
        schema.__pydantic_validator__.validate_assignment(instance, name, value)
    except ValidationError as error:
        return [e for e in error.errors() if e["loc"][:1] == (name,)], None
    except AttributeError:
        return [], None
    return [], getattr(instance, name)


class TestTheCapsAreRealAtRuntime:
    # The scan reads compiled schemas. These run the real validator, so "the schema says maxLength" and
    # "the request is refused" are tied together rather than assumed to mean the same thing — for EVERY
    # plain-str request field, derived, where this used to name five.

    @pytest.mark.parametrize(("schema", "name"), _runtime_str_fields())
    def test_an_over_long_value_is_refused_by_the_real_validator(self, schema, name):
        errors, _ = _assign(schema, name, "x" * 100_000)
        assert errors, f"{_dotted(schema, name)} took 100,000 characters"

    def test_the_runtime_population_is_the_scan_population(self):
        # Anti-vacuity, and agreement: every plain-str field the static scan reads is driven here too.
        runtime = {param.id for param in _runtime_str_fields()}
        assert len(runtime) > 100, f"only {len(runtime)} plain-str request fields are driven at runtime"
        assert {
            "group_settlement.GroupSettlementPlanCreate.notes",
            "auth.RegisterRequest.name",
            "settings.SettingsUpdate.primary_currency",
        } <= runtime

    def test_a_list_of_codes_is_bounded_per_item_and_not_only_per_list(self):
        # Both dimensions, because capping only the list length leaves one item carrying the payload.
        from app.schemas.settings import SettingsUpdate

        with pytest.raises(ValidationError):
            SettingsUpdate(preferred_currencies=["x" * 100_000])
        with pytest.raises(ValidationError):
            SettingsUpdate(preferred_currencies=["ARS"] * 100_000)


# A note exactly at the cap is accepted and preserved verbatim; one character over is refused. Driven over
# every request `notes` the scan finds rather than a list, so a new one joins by existing.
_NOTES_FIELDS = _runtime_str_fields("notes")


@pytest.mark.parametrize(("schema", "name"), _NOTES_FIELDS)
def test_notes_at_the_cap_are_kept_and_one_character_over_is_refused(schema, name):
    note = "x" * NOTES_MAX_LENGTH
    errors, stored = _assign(schema, name, note)
    assert errors == []
    assert stored in (None, note), "the note was rewritten on the way in"
    errors, _ = _assign(schema, name, "x" * (NOTES_MAX_LENGTH + 1))
    assert errors, "one character over the cap was accepted"


def test_the_notes_population_is_not_a_short_list():
    # The hand list this replaced named seven schemas; the scan finds every request `notes` (27 today).
    assert len(_NOTES_FIELDS) >= 25, f"only {len(_NOTES_FIELDS)} notes fields are driven"


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
