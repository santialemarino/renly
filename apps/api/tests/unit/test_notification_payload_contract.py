import ast
import functools
import importlib
import re
from pathlib import Path

from app.models.notification import NotificationEvent
from app.services import notification_templates as templates

# The payload <-> template contract, held at EVERY place the app announces something.
#
# A notification's email and push are rendered from the payload its producer built, by
# `template.format(**payload)`. A template naming a field that producer does not put in its payload raises
# a KeyError at render time, and the render runs inside `_send_email` / `_send_push`, which catch and log
# it so one bad message cannot cost the rest of a fan-out — on the request path AND on a scheduled job's,
# which otherwise raises into the scheduler. The feed row is still written (the web renders it from its own
# copy), so the only trace is a warning in the log while every co-owner silently stops getting the email
# and the push about money moving. test_notification_templates renders every template against ONE payload
# holding every field any producer uses, which cannot see a field missing from one producer's payload.
#
# So the population is DERIVED from the source: every `notification_service.dispatch(...)` call and every
# `NotificationDispatch(...)` handed to `dispatch_many`, wherever it is. For each, the payload's keys are
# read statically — a dict literal, its `**` spreads, the helpers that build it (`pot_service.
# notification_payload`, `_settlement_payload`) and the variables it passes through — and so is the set of
# `variant` values it can carry, which picks the template. Each (site, variant) is then held, in every
# locale, to: every placeholder in the subject, body and push is a payload key or one the renderer itself
# supplies. A site whose payload or variant the reader cannot resolve fails rather than being skipped.

_APP = Path(__file__).resolve().parents[2] / "app"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
# What each renderer supplies itself (notification_templates.notification_email / push_body).
_BUILDER_FIELDS = {"subject": {"product"}, "body": {"product", "link"}, "push": {"product"}}

# The one site whose variant set is a guard rather than an expression the reader can follow:
# record_movement refuses any `type` other than these two before it writes or announces anything.
_VARIANT_DOMAINS = {
    ("pot_ownership_service", "record_movement"): {"contribution", "withdrawal"},
}


# Raised when the reader cannot follow an expression; the site then fails, never skips.
class _Unresolved(Exception):
    pass


# One parsed app module: its top-level functions, classes and app imports.
class _Module:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.stem
        self.dotted = ".".join(path.relative_to(_APP.parent).with_suffix("").parts)
        self.tree = ast.parse(path.read_text())
        self.functions = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
        self.classes = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef)}
        # Imported names: alias -> dotted module (for `from app.services import pot_service`) or
        # (dotted module, name) for `from app.services.x import f`.
        self.imports: dict[str, object] = {}
        for node in self.tree.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
                for alias in node.names:
                    local = alias.asname or alias.name
                    candidate = _APP.parent / Path(*node.module.split("."), alias.name).with_suffix(".py")
                    self.imports[local] = f"{node.module}.{alias.name}" if candidate.exists() else (node.module, alias.name)


_MODULES: dict[str, _Module] = {}


# Each module parsed once, by dotted name.
def _module(dotted: str) -> _Module:
    if dotted not in _MODULES:
        _MODULES[dotted] = _Module(_APP.parent / Path(*dotted.split(".")).with_suffix(".py"))
    return _MODULES[dotted]


# Where an expression is read: the module, the function it sits in, and any parameters bound by a caller.
class _Ctx:
    def __init__(self, module: _Module, fn: ast.AST, bindings: dict | None = None) -> None:
        self.module = module
        self.fn = fn
        self.bindings = bindings or {}


# A function's parameter names, positional then keyword-only.
def _params(fn) -> list[str]:
    a = fn.args
    return [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]


# The arguments a call passes, by parameter name of the function it calls.
def _bind(fn, call: ast.Call, caller: _Ctx) -> dict:
    names = [p.arg for p in (*fn.args.posonlyargs, *fn.args.args)]
    bound = {name: (arg, caller) for name, arg in zip(names, call.args)}
    bound.update({kw.arg: (kw.value, caller) for kw in call.keywords if kw.arg})
    return bound


# The single assignment to a local name inside a function: (value, tuple index or None).
def _assignment(fn, name: str):
    found = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    found.append((node.value, None))
                elif isinstance(target, ast.Tuple):
                    for index, element in enumerate(target.elts):
                        if isinstance(element, ast.Name) and element.id == name:
                            found.append((node.value, index))
    if len(found) != 1:
        raise _Unresolved(f"{name} is assigned {len(found)} times")
    return found[0]


# The function a call reaches: a module-level function here, or one in an imported app module.
def _callee(call: ast.Call, ctx: _Ctx) -> tuple[_Module, ast.AST]:
    func = call.func
    if isinstance(func, ast.Name) and func.id in ctx.module.functions:
        return ctx.module, ctx.module.functions[func.id]
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        target = ctx.module.imports.get(func.value.id)
        if isinstance(target, str):
            module = _module(target)
            if func.attr in module.functions:
                return module, module.functions[func.attr]
    if isinstance(func, ast.Name) and isinstance(ctx.module.imports.get(func.id), tuple):
        dotted, name = ctx.module.imports[func.id]
        module = _module(dotted)
        if name in module.functions:
            return module, module.functions[name]
    raise _Unresolved(f"cannot follow the call {ast.unparse(call.func)}")


# Every value a function returns.
def _returns(fn) -> list[ast.expr]:
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            out.append(node.value)
    return out


# The payload an expression builds: {key: (value expression, its context)}.
def _payload(expr: ast.expr, ctx: _Ctx) -> dict:
    if isinstance(expr, ast.Dict):
        keys: dict = {}
        for key, value in zip(expr.keys, expr.values):
            if key is None:
                keys.update(_payload(value, ctx))
            elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys[key.value] = (value, ctx)
            else:
                raise _Unresolved(f"a computed payload key: {ast.unparse(key)}")
        return keys
    if isinstance(expr, ast.Name):
        if expr.id in ctx.bindings:
            value, caller = ctx.bindings[expr.id]
            return _payload(value, caller)
        value, index = _assignment(ctx.fn, expr.id)
        if index is not None:
            raise _Unresolved(f"a payload unpacked from a tuple: {expr.id}")
        return _payload(value, ctx)
    if isinstance(expr, ast.Call):
        module, fn = _callee(expr, ctx)
        returns = _returns(fn)
        if len(returns) != 1:
            raise _Unresolved(f"{fn.name} has {len(returns)} returns")
        return _payload(returns[0], _Ctx(module, fn, _bind(fn, expr, ctx)))
    raise _Unresolved(f"cannot read a payload from {ast.unparse(expr)}")


# Every string value an expression can take.
def _values(expr: ast.expr, ctx: _Ctx) -> set[str]:
    if isinstance(expr, ast.Constant):
        if isinstance(expr.value, str):
            return {expr.value}
        raise _Unresolved(f"a non-string variant {expr.value!r}")
    if isinstance(expr, ast.IfExp):
        return _values(expr.body, ctx) | _values(expr.orelse, ctx)
    if isinstance(expr, ast.Name) and expr.id in ctx.bindings:
        value, caller = ctx.bindings[expr.id]
        return _values(value, caller)
    if isinstance(expr, ast.Name) and expr.id in _params(ctx.fn):
        # A parameter of a module-private function: whatever every caller in its module passes.
        position = _params(ctx.fn).index(expr.id)
        out: set[str] = set()
        callers = 0
        for caller in ctx.module.functions.values():
            for node in ast.walk(caller):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == ctx.fn.name:
                    args = {kw.arg: kw.value for kw in node.keywords}
                    arg = args.get(expr.id, node.args[position] if position < len(node.args) else None)
                    if arg is None:
                        raise _Unresolved(f"{ctx.fn.name} called without {expr.id}")
                    out |= _values(arg, _Ctx(ctx.module, caller))
                    callers += 1
        if not callers:
            raise _Unresolved(f"{expr.id} is a parameter of {ctx.fn.name}, which nothing in its module calls")
        return out
    if (isinstance(expr, ast.Name) and expr.id in ctx.module.imports) or (isinstance(expr, ast.Attribute) and _root(expr) in ctx.module.imports):
        value = eval(ast.unparse(expr), vars(importlib.import_module(ctx.module.dotted)))  # noqa: S307 — our own module's constants
        if isinstance(value, str):
            return {value}
    if isinstance(expr, ast.Name):
        module_constant = next(
            (
                n.value
                for n in ctx.module.tree.body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == expr.id for t in n.targets)
            ),
            None,
        )
        if module_constant is not None:
            return _values(module_constant, ctx)
        value, index = _assignment(ctx.fn, expr.id)
        if index is None:
            return _values(value, ctx)
        if not isinstance(value, ast.Call):
            raise _Unresolved(f"{expr.id} unpacked from {ast.unparse(value)}")
        module, fn = _callee(value, ctx)
        inner = _Ctx(module, fn, _bind(fn, value, ctx))
        out = set()
        for returned in _returns(fn):
            if not isinstance(returned, ast.Tuple):
                raise _Unresolved(f"{fn.name} does not return a tuple")
            out |= _values(returned.elts[index], inner)
        return out
    if isinstance(expr, ast.Call):
        module, fn = _callee(expr, ctx)
        inner = _Ctx(module, fn, _bind(fn, expr, ctx))
        out = set()
        # A `return None` is the producer's own "nothing to announce", which its caller checks before it
        # dispatches (account_reconciliation_service._notify); only the strings reach a template.
        for returned in _returns(fn):
            if not (isinstance(returned, ast.Constant) and returned.value is None):
                out |= _values(returned, inner)
        return out
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        # A field of a NamedTuple built in this module: whatever every construction puts there.
        for cls in ctx.module.classes.values():
            fields = [n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
            if expr.attr not in fields:
                continue
            index = fields.index(expr.attr)
            out = set()
            for fn in ctx.module.functions.values():
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == cls.name:
                        kwargs = {kw.arg: kw.value for kw in node.keywords}
                        out |= _values(kwargs.get(expr.attr, node.args[index] if index < len(node.args) else None), _Ctx(ctx.module, fn))
            if out:
                return out
    raise _Unresolved(f"cannot read the values of {ast.unparse(expr)}")


# The name an attribute chain starts from.
def _root(expr: ast.expr) -> str | None:
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None


# The NotificationEvent member a dispatch names; anything else is unreadable.
def _event(expr: ast.expr) -> NotificationEvent:
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name) and expr.value.id == "NotificationEvent":
        return NotificationEvent[expr.attr]
    raise _Unresolved(f"an event that is not a NotificationEvent member: {ast.unparse(expr)}")


# A call's argument by keyword, else by position.
def _arg(call: ast.Call, position: int, name: str) -> ast.expr:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return call.args[position]


# Every announcement in the app: (where, event, payload keys, variants or {None}).
@functools.cache
def _sites() -> list[tuple[str, NotificationEvent, set[str], set[str | None]]]:
    sites = []
    for path in sorted(_APP.rglob("*.py")):
        if path.name == "notification_service.py":
            continue
        dotted = ".".join(path.relative_to(_APP.parent).with_suffix("").parts)
        module = _module(dotted)
        for fn in ast.walk(module.tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
            many = [c for c in calls if ast.unparse(c.func) == "notification_service.dispatch_many"]
            for call in calls:
                func = ast.unparse(call.func)
                if func == "notification_service.dispatch":
                    event, payload = _event(_arg(call, 0, "event")), _arg(call, 2, "payload")
                elif func == "NotificationDispatch":
                    assert len(many) == 1, f"{dotted}.{fn.name}: a NotificationDispatch needs exactly one dispatch_many beside it"
                    event, payload = _event(_arg(many[0], 0, "event")), _arg(call, 1, "payload")
                else:
                    continue
                where = f"{module.name}.{fn.name}:{call.lineno}"
                ctx = _Ctx(module, fn)
                try:
                    keys = _payload(payload, ctx)
                    if "variant" not in keys:
                        variants: set[str | None] = {None}
                    elif (module.name, fn.name) in _VARIANT_DOMAINS:
                        variants = set(_VARIANT_DOMAINS[(module.name, fn.name)])
                    else:
                        value, value_ctx = keys["variant"]
                        variants = set(_values(value, value_ctx))
                except _Unresolved as error:
                    raise AssertionError(f"{where}: {error}") from None
                sites.append((where, event, set(keys), variants))
    return sites


# The catalogue key an (event, variant) renders from, as notification_templates.template_key builds it.
def _template_key(event: NotificationEvent, variant: str | None) -> str:
    return f"{event.value}.{variant}" if variant else event.value


class TestEveryAnnouncementCanBeRendered:
    def test_the_population_is_every_dispatch_in_the_app(self):
        print(f"\n{len(_sites())} dispatch sites:")
        for where, event, keys, variants in _sites():
            print(f"  {where} {event.value} variants={sorted(v or '-' for v in variants)} keys={sorted(keys)}")
        # Every textual dispatch reaches the derivation: a producer calling it through another name
        # would be invisible to it.
        source = "".join(p.read_text() for p in _APP.rglob("*.py") if p.name != "notification_service.py")
        direct = source.count("notification_service.dispatch(")
        batched = source.count("NotificationDispatch(")
        assert direct + batched == len(_sites()) and direct > 10 and batched >= 2
        assert "import dispatch" not in source and "dispatch_many as" not in source

    def test_every_variant_a_site_sends_has_a_template_and_every_template_is_sent(self):
        sent = {_template_key(event, variant) for _, event, _, variants in _sites() for variant in variants}
        catalogue = {key for key in templates._STRINGS["en"] if not key.startswith("_")}
        assert sent - catalogue == set(), "a site sends a variant with no template (a KeyError on every render)"
        assert catalogue - sent == set(), "a template no site sends: dead copy, or a site whose variants were misread"

    def test_the_variant_table_names_only_sites_that_exist(self):
        functions = {where.split(":")[0] for where, *_ in _sites()}
        assert {f"{module}.{fn}" for module, fn in _VARIANT_DOMAINS} <= functions
        # And the guard the one entry stands for still says what the table says.
        fn = _module("app.services.pot_ownership_service").functions["record_movement"]
        guards = [
            {element.attr for element in node.test.comparators[0].elts}
            for node in ast.walk(fn)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.ops[0], ast.NotIn)
            and ast.unparse(node.test.left) == "type"
            and isinstance(node.body[0], ast.Raise)
        ]
        assert guards == [_VARIANT_DOMAINS[("pot_ownership_service", "record_movement")]]

    def test_every_placeholder_is_a_field_its_producer_supplies_in_every_locale(self):
        missing = []
        for where, event, keys, variants in _sites():
            for variant in variants:
                key = _template_key(event, variant)
                for locale, catalogue in templates._STRINGS.items():
                    if key not in catalogue:
                        missing.append(f"{where} {key} {locale}: no template at all")
                        continue
                    for field, text in catalogue[key].items():
                        needed = set(_PLACEHOLDER.findall(text)) - _BUILDER_FIELDS[field]
                        if not needed <= keys:
                            missing.append(f"{where} {key} {locale}/{field}: {sorted(needed - keys)}")
        assert missing == []
