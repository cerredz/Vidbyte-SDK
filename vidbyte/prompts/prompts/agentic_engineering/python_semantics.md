# Description
Python ships a large surface of semantic machinery — a static type system, the data model of dunder methods, descriptors, a runtime contract and assertion layer, and framework introspection — and this principle teaches a model to treat that surface as the interface an AI agent perceives and is steered by, not as optional ceremony for library authors. When a human wrote business logic, most of this was skippable: the human held the model in their head and could read the implementation to recover any missing context, so a bare `dict`, a loose signature, and a missing `__repr__` cost almost nothing. Agents flip that economy. An agent perceives code through narrow channels — the signature, the type-checker verdict, the `repr` in a traceback, the fields on an exception, the decorator markers a framework reads — and every one of these capabilities populates exactly one of those channels, machine-read on every edit and run cycle. The core pattern is to fill the channel at definition time so the agent reads a contract instead of reverse-engineering it from a body, and to fill it with the strongest mechanism available: prefer a type the checker rejects wrong code against, fall back to a runtime self-check that fails loud, and let frameworks read declarations rather than hand-wiring. The discipline that keeps this honest is that a capability is only added when it is semantically true — a `__len__` only when the object is a collection, a `Protocol` only for a real capability — because a meaningless channel-fill is a guessable-wrong operation that misleads the agent and is worse than an honest absence. The most common failure mode when this principle is absent is an agent flying blind through under-typed, under-represented code: it opens five files to infer a shape that one signature could have stated, or it ships a change the type checker would have rejected at the keystroke. As agent-authored code converges toward a single self-describing style, this principle specifies that style deliberately, on the most agent-legible Python idioms. This principle is explicitly scoped to Python; the same channel-filling instinct applies to other languages, but the concrete vocabulary here is Python's.

# Intent
The intent of Python-semantics-for-agents is to make every Python file a high-signal interface whose contracts are encoded where an agent can read them cheaply, instead of latent in an implementation the agent must reconstruct. Agents do not fail only because code is wrong; they fail because the contract they need is implicit. A function annotated only as `def process(data):` forces the agent to read the body and every call site to learn what `data` is and what comes back; the same function written `def parse_invoice(raw: dict) -> Invoice:` states its contract in one line and lets the type checker prove the call sites correct. The deeper move is to choose the channel by cost. The cheapest feedback an agent can get is a type error at authoring time, before anything runs — so steer there first. The next cheapest is a runtime failure that is loud, located, and unignorable on the executed path — so enforce there when the checker cannot reach. The last is a framework reading the code's own declarations to wire behavior — so wire there when the work is registration, dispatch, or configuration. Each capability in this principle is mapped to one of those three intervention points and to the perception channel it fills, and the rule is always the same: fill the strongest channel that genuinely applies, and never fill a channel with a lie. A type that says `Any`, a `__repr__` that hides the fields, an exception that carries only a message string, and an `except: pass` that swallows a failure all degrade the very channel they appear to serve, and a degraded channel is worse than an empty one because the agent trusts it.

# The Three Intervention Points
Every capability below belongs to one of three intervention points. Order your effort cheapest-first: steer at authoring time when you can, enforce at runtime when the checker cannot reach, and wire through declarations when the work is registration or dispatch.
* STEER — Authoring-time static analysis. The type checker and IDE reject wrong code before it runs and autocomplete the right code at the keystroke. This is the cheapest possible feedback for an agent and must be preferred above all. It requires a strict checker in the loop (pyright or mypy in strict mode); without one, type annotations degrade to comments that lie when they drift.
* ENFORCE — Runtime self-checks on the executed path. Dunder methods, descriptors, typed exceptions, and guard clauses fire automatically when the code runs and cannot be ignored on the path that executes. Use them to catch what the type checker cannot express and to make the agent's perception channels (tracebacks, logs, the REPL) carry truthful, structured information.
* WIRE — Self-describing declarations a framework reads. Decorators, dispatch registries, and annotation introspection let code report its own shape so a framework attaches behavior without hand-wiring. Use these to collapse "define a thing" and "register the thing" into a single site so an agent never has to remember a second edit.

# Authoring-Time Steering: Type Checker and IDE
This is the STEER layer. Prefer it above all other layers. It only works with a strict checker (pyright strict or mypy strict) running in the loop; with the checker absent these constructs become unenforced comments. Annotate by meaning and with the most precise type available — a precise type is a contract the agent reads instead of the body.
* Type annotations — every parameter, return, and field, with the precise type. The foundation of steering. An unannotated signature is an opaque box the agent must open; an annotated one is a contract it can trust.
* NewType — a branded primitive so `UserId` is not interchangeable with `str`, at zero runtime cost. Use it for every domain id or handle so the checker rejects a transposed `user_id`/`plan_id` instead of letting it run.
* Literal — a closed set of exact values. Use it for small fixed sets, especially at edges, so the checker enforces that only the allowed values flow through.
* Sum types (tagged dataclass unions) — make illegal states unrepresentable. Tag each variant with a `Literal`, then `match` on the tag and close with `assert_never` so adding a variant becomes a type error at every unhandled branch. Use it for correlated flags that must not drift out of sync.
* Protocol (with `@runtime_checkable` when needed) — a structural interface. The checker lists exactly which methods an implementer is missing. Use it for capabilities and ports, where structural matching without inheritance is the honest model.
* Final and `@final` — close an extension point. `Final` stops a name or attribute from being rebound; `@final` stops a class from being subclassed or a method from being overridden. Use them to tell the agent and the checker that an extension point is deliberately closed.
* overload — multiple typed signatures so the return type tracks the call shape. Use it when one function legitimately returns different types for different, statically distinguishable inputs.
* TypedDict — a fixed, typed key schema for a dict that must stay a dict at a boundary. Use it instead of a bare `dict` when the shape is known but the value must remain a mapping.
* NamedTuple — an immutable, typed, positional record. Use it for small fixed records where positional access and immutability are the point.
* Annotated — attaches machine-readable metadata to a type that libraries read for validation and serialization. Treat it as a general extra-metadata channel that DI and validation frameworks consume (see the wiring layer).
* Self — the enclosing-class return type, for fluent and builder methods so chained calls keep their precise type.
* assert_never, assert_type, reveal_type — exhaustiveness checks, inline type assertions, and dev-time type inspection. Use `assert_never` to make a missing case a type error; use `reveal_type` while authoring to confirm what the checker infers.
* Never and NoReturn — declare that a function never returns normally because it always raises or exits. Use them so the checker propagates unreachability correctly.
* Generic[T] and the PEP 695 form `class Box[T]:` — parametric containers and wrappers. Use them so a container preserves the element type through the checker instead of widening to `Any`.
* TypeAlias — one canonical name for a recurring complex shape. Use it so a long union or nested generic has a single readable, greppable name.
* abc.ABC with `@abstractmethod` — nominal "must implement" enforced at both runtime and check time. Use it when subclasses must inherit; prefer `Protocol` when structural matching without inheritance is the truthful relationship.
* if TYPE_CHECKING — import types for the checker without paying the runtime import cost. Use it to keep heavy or cyclic imports out of the runtime path while still typing against them.

# Runtime Enforcement: The Data Model
This is the ENFORCE layer expressed through Python's data model — the dunder methods and descriptors that fire automatically when the path executes. Implement by meaning, by tier. A meaningless dunder is a guessable-wrong operation that misleads the agent and is worse than the honest `TypeError` of its absence. Implement `__repr__` always; implement value dunders for data; implement protocol, container, and numeric dunders only when the type genuinely is that kind of thing; implement machinery dunders deliberately.
* __repr__ — the agent's primary perception window: it is what appears in tracebacks, logs, the REPL, and pytest output. Always implement it, and aim for a round-trippable form where `eval(repr(x))` reconstructs the object. A `@dataclass` generates a good one for free.
* __str__ — the user-facing string. Implement it only when it must differ from `__repr__`.
* __format__ — handles the f-string and `format()` spec. Implement it for types that have meaningful format options.
* __eq__ — value equality, which makes the test loop honest because assertions compare meaning instead of identity. Always implement it for data; `@dataclass` generates it.
* __hash__ — set and dict-key membership; keep it consistent with `__eq__`. Defining `__eq__` alone makes the type unhashable; a frozen dataclass restores a consistent hash.
* __bool__ — truthiness, when "empty" or "absent" has a real domain meaning. Implement it only when the truth value is semantically meaningful, not by reflex.
* __lt__, __le__, __gt__, __ge__ — ordering for sorting, `min`, and `max`. Implement them only for types with a genuine order; use `@total_ordering` or `@dataclass(order=True)` to derive the rest from one.
* __match_args__ — positional fields for `match`/`case` structural patterns; dataclasses set it automatically. It enables clean structural dispatch on your own types.
* Container and iteration dunders — `__len__`, `__getitem__`, `__setitem__`, `__delitem__`, `__contains__`, `__iter__`, `__next__`, `__reversed__`. Implement them only if the object genuinely is a collection. `__missing__` provides a dict-subclass default; `__length_hint__` is an optional optimization.
* Callable, context, and async dunders — `__call__` for function-like objects such as strategies and handlers; `__enter__`/`__exit__` and the async `__aenter__`/`__aexit__` for `with`; `__await__` for a custom awaitable; `__aiter__`/`__anext__` for `async for`. Implement them only when the object is that thing. Consider making a resource obtainable only as a context manager so cleanup cannot be skipped.
* Numeric dunders — arithmetic `__add__` through `__matmul__` with their reflected `__radd__` and in-place `__iadd__` forms, unary `__neg__`/`__abs__`/`__round__`, conversions `__int__`/`__float__`/`__index__`, and bitwise `__and__`/`__or__`/`__xor__`/`__invert__`. Implement them only for actual quantities such as money or vectors; `enum.Flag` already covers bit-flag sets.
* Path and bytes interop — `__fspath__` makes an object usable anywhere a path is expected (`os.PathLike`); `__bytes__` supports `bytes(x)`. Implement them for path-like and binary value types.
* Construction and lifecycle machinery — `__new__` for pre-`__init__` creation (immutables, singletons, caching); keep `__init__` dumb and assignment-only, constructing through named classmethods; `__post_init__` is the dataclass validation hook, so raise there to make objects valid-by-construction.
* __slots__ — a fixed attribute set so a typo'd attribute raises immediately instead of silently creating junk that poisons later reads. Use it on most data classes via `@dataclass(slots=True)`; watch the multiple-inheritance interactions.
* Attribute interception — `__getattr__` (missing-attribute fallback), `__getattribute__` (all access, dangerous, rarely correct), and `__setattr__`/`__delattr__` (intercept write and delete; a frozen dataclass blocks assignment). Implement them deliberately and sparingly.
* __set_name__ and __init_subclass__ — `__set_name__` lets a descriptor learn its attribute name; `__init_subclass__` fires when a subclass is defined and can auto-register a plugin with no separate registry edit, collapsing "define and register" into one site. `__class_getitem__` supports subscription such as `Box[int]` and is usually free via `Generic`.
* Descriptor protocol — `__get__`, `__set__`, `__delete__` — reusable, declarative per-attribute behavior, the machinery behind `property`, `cached_property`, and ORM fields. Use a descriptor to enforce a field invariant on every assignment in one reusable place instead of scattering checks.
* Copy and pickle hooks — `__copy__`, `__deepcopy__`, `__getstate__`, `__setstate__`, `__reduce__`. Implement them only when the default copy or pickle behavior is wrong for the type.
* Metaclass and isinstance hooks — `__instancecheck__`, `__subclasscheck__`, and a metaclass `__call__` customize `isinstance` and creation. These are rare; prefer `Protocol` and `__init_subclass__` first.

# Runtime Enforcement: Contracts and Assertions
This is the ENFORCE layer for invariants the type system cannot express. The code asserts its own contracts and fails loud so the agent's perception is never poisoned by silent-wrong behavior. A swallowed error lies to the agent's perception channel; a loud, located failure tells the truth. Where this section touches structured exceptions, it concerns the Python mechanism only — for the full anatomy of an agent-readable error packet (the description, expected-versus-actual, blast radius, fix approaches, and doc links), apply the error messages principle and do not re-derive it here.
* Custom exception hierarchy — typed, structured exceptions that carry the failed value, the attempted operation, and a suggested fix as fields rather than prose. The agent branches on `err.kind` and reads `err.suggested_fix` programmatically, so recovery becomes dispatch instead of guesswork. This is errors-as-data; see the error messages principle for the complete field anatomy.
* raise ... from ... — chain the cause so the traceback stays legible and the agent sees the originating failure, not just the rethrow.
* Guard clauses and fail-loud boundaries — invalid input crashes with a precise message at the boundary instead of being swallowed into a `None`, `{}`, or `0` that surfaces as a confusing failure three layers away.
* assert for invariants — programmer-error checks that document and enforce an internal expectation. Do not use `assert` for input validation, because `-O` strips assertions; use a guard clause that raises for anything an external caller controls.
* assert_never in match defaults — a missing case becomes both a type-check error and a runtime guard, so an unhandled variant cannot pass silently.
* Spec-carrying stubs — `raise NotImplementedError("return ranked list; tie-break by recency")` states the contract at the exact point where the work belongs, so the next agent reads the spec where it will implement it.
* warnings and deprecation — `DeprecationWarning` and the `@deprecated` decorator (PEP 702: `warnings.deprecated` in 3.13+, `typing_extensions.deprecated` earlier) surface in both the checker and at runtime, steering an agent off a dead path before it builds on it.
* Design-by-contract (icontract, deal) — pre- and post-condition decorators that enforce contracts at runtime and document them as executable code rather than comments.
* contextlib.suppress — an explicit, scoped, greppable "ignore this specific error" that states intent, instead of a bare `except: pass` that hides which error was expected and lies about the rest.

# Framework Wiring: Introspection and Decorators
This is the WIRE layer: code that reads itself at runtime to drive behavior — dependency injection, dispatch, and registration. The aim is to declare "this participates in X" at the definition site so a framework attaches behavior, instead of maintaining a second hand-edited wiring list the agent must remember to update.
* Decorators — the closest cousin to dunders: a marker a framework reads to attach behavior, such as `@app.route`, `@pytest.fixture`, `@dataclass`, or a project's own `@register_handler`. Use a decorator to declare participation instead of hand-wiring; self-registration lives here. Always apply `functools.wraps` inside your own decorators so the wrapped function keeps its name, doc, and signature for the agent's perception channel.
* functools.singledispatch and singledispatchmethod — add an operation across many types through isolated, local registrations so extension is additive and never a growing `isinstance` ladder.
* abc.ABC.register() — declare a virtual subclass so `isinstance` succeeds without inheritance, when the structural relationship is real but the class tree should not change.
* inspect — read signatures, source, and members at runtime so tools and agents can discover structure programmatically.
* typing.get_type_hints() and __annotations__ — annotations as runtime data, the basis for DI containers, serializers, and objects that report their own shape.
* DI and settings frameworks (pydantic, attrs, dependency-injector) — read annotations and `Annotated` metadata to generate validation, wiring, and configuration from the declarations the type layer already states.
* dataclasses.fields() and dataclasses.field(metadata=...) — introspect fields and carry arbitrary per-field framework metadata, so a framework can drive behavior from the dataclass definition itself.

# Cross-Cutting Toolkit
These standard-library helpers generate or wrap the surfaces above and are often the cheapest way to fill several channels at once. Reach for them before hand-writing the machinery.
* dataclasses — `@dataclass(frozen=True, slots=True[, order=True, kw_only=True])` generates `__init__`, `__repr__`, `__eq__`, `__hash__`, `__match_args__`, and `__slots__` in one line, plus `field()`, `__post_init__`, `replace()`, `asdict()`, and `fields()`. This is the default way to fill the data-model channel honestly and for free.
* functools — `@total_ordering`, `@cached_property`, `@cache`/`@lru_cache`, `singledispatch`, `partial`/`partialmethod`, `@wraps` (always on your own decorators), and `reduce` (sparingly).
* enum — `Enum`, `StrEnum`, `IntEnum`, `Flag`, `IntFlag`, and `auto()`. Members can carry methods and data so behavior travels with the member instead of living in a separate lookup.
* contextlib — `@contextmanager`, `AbstractContextManager`, `ExitStack`, `suppress`, and `closing`.
* abc — `ABC`, `@abstractmethod`, and `.register()`.
* typing and typing_extensions — the authoring-time vocabulary above, with `typing_extensions` providing backports of newer items for older runtimes.
* Validation libraries (pydantic, attrs) — read annotations and `Annotated` to parse untyped input into typed models at the boundary and validate invariants at runtime, bridging the steering layer and the enforcement layer.

# Things Not to Do
* Do not annotate with `Any` or a bare `dict`, `list`, or `tuple` when a precise type exists. `Any` switches the checker off for that value and removes the contract the agent would have read.
* Do not implement a dunder the type does not semantically deserve. A `__len__` on a non-collection or an `__add__` on a non-quantity is a guessable-wrong operation that misleads the agent and is worse than the honest `TypeError` of its absence.
* Do not write a `__repr__` that hides the fields or returns a generic `<object>` form. The repr is the agent's primary perception window, and a useless one blinds every traceback, log line, and test failure.
* Do not define `__eq__` without `__hash__` unless the type is intentionally unhashable. The inconsistency breaks set and dict membership in ways that surface far from the definition.
* Do not swallow errors with a bare `except: pass`. Use `contextlib.suppress(SpecificError)` to state exactly which error is expected, so the channel reports the truth instead of hiding every failure.
* Do not use `assert` to validate external input. `-O` strips assertions, so the check vanishes in production; raise a guard-clause exception for anything a caller controls.
* Do not return a sentinel `None`, `{}`, or `0` from a boundary when the operation failed. Fail loud at the boundary so the failure is located, not laundered into a confusing downstream symptom.
* Do not represent a closed set as magic strings. Use `Literal` or `Enum` so the checker enforces the allowed values.
* Do not `match` on a union without an `assert_never` default. Without it, a newly added variant passes silently instead of failing at the unhandled branch.
* Do not maintain a hand-edited registry beside a definition when `__init_subclass__`, a decorator, or `singledispatch` can register at the definition site. The second list is the one an agent forgets to update.
* Do not duplicate the error-message field anatomy here. Carry the failed value, the operation, and the suggested fix as fields, and apply the error messages principle for the full packet.
* Do not write a multi-line function signature. Keep the signature on one line so the contract is a single readable unit; group excess inputs into a typed object, consistent with the function design principle.

# Checklist
* Before annotating a value, choose the most precise type that is true: brand domain ids with `NewType`, close small sets with `Literal` or `Enum`, and reserve `Any` for genuinely dynamic data only.
* Before writing a boundary function, decide where the untyped input is parsed into a typed model, and do it once at the edge so the interior is fully typed.
* When two or more flags are correlated, model them as a tagged union and close every `match` with `assert_never` so adding a variant becomes a type error.
* For every class that holds data, implement `__repr__` and `__eq__` (prefer generating them with `@dataclass`), and add `__slots__` unless a specific reason forbids it.
* Before implementing any other dunder, confirm the type genuinely is that kind of thing — a collection, a callable, a context manager, a quantity — and skip it otherwise; a meaningless dunder is worse than its absence.
* Before adding `__hash__`, verify it is consistent with `__eq__`; before relying on ordering, derive it from one comparison with `@total_ordering` or `@dataclass(order=True)`.
* When a failure can occur, raise a typed exception that carries the failed value, the operation, and a suggested fix as fields, chain the cause with `raise ... from`, and apply the error messages principle for the full packet.
* Before using `assert`, confirm the condition is a programmer-error invariant and not external input; use a raising guard clause for anything a caller controls.
* When you need to ignore an error, replace any bare `except: pass` with `contextlib.suppress` naming the specific error.
* When defining something that must also be registered, register it at the definition site with `__init_subclass__`, a decorator, or `singledispatch` instead of editing a separate list.
* Before finishing, confirm a strict checker (pyright strict or mypy strict) passes with zero new `Any`, no implicit `Optional`, and no unexplained `# type: ignore`; without a strict checker in the loop, the steering layer is only comments.
* On every decorator you write, apply `functools.wraps` so the wrapped callable keeps its name, doc, and signature in the agent's perception channel.

# Code Examples
These examples show the weak form an agent often inherits and the strict form that fills the channel. Each names the intervention point it demonstrates.

## Example 1: Boundary function — STEER (precise types, NewType, parse-don't-validate)

```python
# Weak: nothing here is a contract. The agent must read the body and every call
# site to learn what `user` and `amount` are and what the dict contains.
def charge(user, amount):
    return {"ok": True, "id": user["id"], "amount": amount}


# Strict: branded ids the checker will not let you transpose, a typed result the
# agent reads instead of the body, and the raw boundary dict parsed once into a
# typed model so the interior is fully typed.
from typing import NewType
from dataclasses import dataclass

UserId = NewType("UserId", str)
Cents = NewType("Cents", int)


@dataclass(frozen=True, slots=True)
class ChargeResult:
    charge_id: str
    user_id: UserId
    amount: Cents


def charge(user_id: UserId, amount: Cents) -> ChargeResult:
    # Contract is in the signature: who is charged, how much, and what comes back.
    charge_id = _submit_to_processor(user_id, amount)
    return ChargeResult(charge_id=charge_id, user_id=user_id, amount=amount)
```

## Example 2: Correlated flags as a tagged union — STEER plus ENFORCE (assert_never)

```python
# Weak: three booleans that can drift into illegal combinations (paid and refunded
# at once), and nothing forces a caller to handle every state.
# status = {"is_pending": False, "is_paid": True, "is_refunded": False}

from dataclasses import dataclass
from typing import Literal, assert_never


@dataclass(frozen=True, slots=True)
class Pending:
    kind: Literal["pending"] = "pending"


@dataclass(frozen=True, slots=True)
class Paid:
    charged_cents: int
    kind: Literal["paid"] = "paid"


@dataclass(frozen=True, slots=True)
class Refunded:
    refunded_cents: int
    kind: Literal["refunded"] = "refunded"


PaymentState = Pending | Paid | Refunded


def describe(state: PaymentState) -> str:
    # Adding a fourth variant makes this match a type error at the assert_never line
    # until the new case is handled, so no state is ever silently dropped.
    match state:
        case Pending():
            return "awaiting payment"
        case Paid(charged_cents=c):
            return f"paid {c} cents"
        case Refunded(refunded_cents=r):
            return f"refunded {r} cents"
        case _ as unreachable:
            assert_never(unreachable)
```

## Example 3: A data class implemented by tier — ENFORCE (data model, honestly)

```python
# Strict: one decorator fills __repr__, __eq__, __hash__, __match_args__, and
# __slots__ truthfully. __bool__ is added only because "no lines" is a real domain
# meaning for an invoice. No collection or numeric dunders are added, because an
# Invoice is neither a collection nor a quantity — adding them would be a
# guessable-wrong operation worse than their absence.
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Invoice:
    invoice_id: str
    line_items: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Validate at construction so an Invoice is valid-by-construction.
        if not self.invoice_id:
            raise ValueError("invoice_id must be non-empty")

    def __bool__(self) -> bool:
        # "Empty" has domain meaning here: an invoice with no line items is falsy.
        return bool(self.line_items)
```

## Example 4: Self-registering handler — WIRE (__init_subclass__ collapses define + register)

```python
# Strict: defining a subclass registers it. There is no second registry list for an
# agent to forget to update — "define the handler" and "register the handler" are
# one site.
from __future__ import annotations


class EventHandler:
    registry: dict[str, type[EventHandler]] = {}
    event_type: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        # Fires when a subclass is defined; wires it into the registry automatically.
        super().__init_subclass__(**kwargs)
        if cls.event_type:
            EventHandler.registry[cls.event_type] = cls

    def handle(self, payload: dict) -> None:
        raise NotImplementedError("handle the event payload for this event_type")


class CheckoutHandler(EventHandler):
    event_type = "checkout.completed"

    def handle(self, payload: dict) -> None:
        # EventHandler.registry["checkout.completed"] is already CheckoutHandler.
        ...
```
