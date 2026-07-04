# Description
Python ships a large surface of semantic machinery — a static type system, the data model of dunder methods, descriptors, a runtime contract and assertion layer, and framework introspection — and this principle teaches a model to treat that surface as the interface an AI agent perceives and is steered by, not as optional ceremony for library authors. When a human wrote business logic, most of this was skippable: the human held the model in their head and could read the implementation to recover any missing context, so a bare `dict`, a loose signature, and a missing `__repr__` cost almost nothing. Agents flip that economy. An agent perceives code through narrow channels — the signature, the type-checker verdict, the `repr` in a traceback, the fields on an exception, the decorator markers a framework reads — and every one of these capabilities populates exactly one of those channels, machine-read on every edit and run cycle. The core pattern is to fill the channel at definition time so the agent reads a contract instead of reverse-engineering it from a body, and to fill it with the strongest mechanism available: prefer a type the checker rejects wrong code against, fall back to a runtime self-check that fails loud, and let frameworks read declarations rather than hand-wiring. The discipline that keeps this honest is that a capability is only added when it is semantically true — a `__len__` only when the object is a collection, a `Protocol` only for a real capability — because a meaningless channel-fill is a guessable-wrong operation that misleads the agent and is worse than an honest absence. The most common failure mode when this principle is absent is an agent flying blind through under-typed, under-represented code: it opens five files to infer a shape that one signature could have stated, or it ships a change the type checker would have rejected at the keystroke. As agent-authored code converges toward a single self-describing style, this principle specifies that style deliberately, on the most agent-legible Python idioms. This principle is explicitly scoped to Python; the same channel-filling instinct applies to other languages, but the concrete vocabulary here is Python's.

# Intent
The intent of Python-semantics-for-agents is to make every Python file a high-signal interface whose contracts are encoded where an agent can read them cheaply, instead of latent in an implementation the agent must reconstruct. Agents do not fail only because code is wrong; they fail because the contract they need is implicit. A function annotated only as `def process(data):` forces the agent to read the body and every call site to learn what `data` is and what comes back; the same function written `def parse_invoice(raw: dict) -> Invoice:` states its contract in one line and lets the type checker prove the call sites correct. The deeper move is to choose the channel by cost. The cheapest feedback an agent can get is a type error at authoring time, before anything runs — so steer there first. The next cheapest is a runtime failure that is loud, located, and unignorable on the executed path — so enforce there when the checker cannot reach. The last is a framework reading the code's own declarations to wire behavior — so wire there when the work is registration, dispatch, or configuration. Each capability in this principle maps to one of those three intervention points and to the perception channel it fills, and the rule is always the same: fill the strongest channel that genuinely applies, and never fill a channel with a lie. A type that says `Any`, a `__repr__` that hides the fields, an exception that carries only a message string, and an `except: pass` that swallows a failure all degrade the very channel they appear to serve, and a degraded channel is worse than an empty one because the agent trusts it.

# 1. Authoring-Time Steering: Type Checker and IDE (STEER)
This is the STEER layer: authoring-time static analysis where the type checker and IDE reject wrong code before it runs and autocomplete the right code at the keystroke. This is the cheapest possible feedback for an agent and must be preferred above all. It only works with a strict checker (pyright strict or mypy strict) running in the loop; with the checker absent these constructs become unenforced comments. Annotate by meaning and with the most precise type available — a precise type is a contract the agent reads instead of the body.
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
* TypeVar with bound and constraints — names the relationship between input and output positions before reaching for `Generic[T]` or the PEP 695 form. Use a bound to restrict the variable to a capability (`TypeVar("T", bound=Comparable)`) and constraints to a closed set of exact types, so the checker enforces the relationship instead of widening to `Any`.
* ParamSpec and Concatenate — capture an arbitrary call signature so a decorator-returning function preserves the wrapped callable's exact parameter list instead of collapsing it to `(*args, **kwargs) -> Any`. Pair with `functools.wraps` (see the wiring layer) so the decorator is both runtime- and check-time-honest.
* TypeVarTuple and Unpack — variadic generics for a container or function whose arity itself varies, such as a multi-dimensional array shape. Use them so the checker tracks the exact number and order of type parameters instead of erasing them to `tuple[Any, ...]`.
* TypeGuard and TypeIs — a function that narrows a type for the caller by returning a bool the checker trusts. Prefer `TypeIs` (PEP 742) over `TypeGuard` when the narrowing should also apply in the negative branch, so an `if not is_valid(x):` branch is narrowed too.
* override — `typing.override` (PEP 698) marks a method as overriding a parent's, and the checker flags it if the parent signature ever changes or the method does not exist there. Use it on every subclass method meant to override, so a renamed base method is caught at the override site instead of silently creating an unrelated method.
* ClassVar — marks an attribute as class-level, not per-instance, so the checker rejects an instance trying to shadow it and a dataclass does not mistake it for a field. Use it on shared registries, defaults, and configuration that live on the class itself.
* Required and NotRequired — per-key optionality inside a `TypedDict` (PEP 655), so a boundary dict can mix mandatory and optional keys precisely instead of making the whole shape optional or none of it.
* cast() — an explicit, narrow escape hatch that tells the checker to trust a type it cannot infer on its own. Use it sparingly and only when you, not the checker, hold the proof of correctness; a `cast` that turns out wrong is a silent lie with no runtime check behind it, so prefer a runtime-validating boundary (TypedDict, pydantic) over `cast` whenever the input is not already provably correct.
* Mapping, Sequence, Iterable over dict, list — accept the most abstract structural type a parameter genuinely needs and return the most concrete type a caller can rely on. Accepting `Mapping` instead of `dict` widens what a caller may pass; returning `dict` instead of `Mapping` tells the caller exactly what they got.

# 2. Runtime Enforcement: The Data Model (ENFORCE)
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
* __dir__ — customizes what `dir()` reports for an object with dynamically generated attributes, so an agent or REPL introspecting the object sees the real attribute surface instead of an incomplete default listing.
* __del__ — a finalizer that runs at garbage collection, with no guaranteed timing. Implement it only for advisory cleanup logging, never for resource release that correctness depends on; use a context manager (`__enter__`/`__exit__`) for anything that must run deterministically.
* __sizeof__ — reports the object's memory footprint to `sys.getsizeof`. Implement it only for types whose memory profile is part of their contract, such as a custom buffer or cache.
* __subclasshook__ — paired with `abc.ABC.register()`, customizes `isinstance`/`issubclass` with a structural check instead of a registry lookup. Prefer `Protocol` first; reach for this only when the relationship must be expressed on an existing `ABC`.
* Enum hooks (_missing_, _generate_next_value_) — `_missing_` supplies a fallback when a raw value does not match any member (for example, normalize casing before failing); `_generate_next_value_` controls what `auto()` produces. Use them so an `Enum` self-describes its own coercion and numbering rules instead of forcing callers to pre-normalize input.

# 3. Runtime Enforcement: Contracts and Assertions (ENFORCE)
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
* Exception notes — `BaseException.add_note()` (PEP 678, 3.11+) appends extra context to an already-raised exception without re-wrapping it, so a catch-and-annotate path enriches the traceback the agent reads instead of losing the original type.
* ExceptionGroup and except* — `ExceptionGroup` (PEP 654, 3.11+) carries multiple concurrent failures as one raisable object, and `except*` handles each contained exception by type. Use them for fan-out operations (concurrent tasks, batch validation) so the agent sees every failure that occurred, not just the first one a single `except` would catch.
* __cause__ and __context__ — the attributes `raise ... from ...` and implicit exception chaining populate. Read them explicitly when re-raising or logging so the chain stays attached to the object, not just to the printed traceback.
* warnings.warn(..., stacklevel=...) — set `stacklevel` so the warning is attributed to the caller's line, not the line inside your own wrapper function; an agent fixing a deprecation warning needs the warning pointed at the call site it can actually edit.
* Sentinel objects for "not provided" — a private `_UNSET = object()` default distinguishes "caller passed nothing" from "caller passed None" when `None` is itself a valid value, so the function does not silently misinterpret an intentional `None`.

# 4. Framework Wiring: Introspection and Decorators (WIRE)
This is the WIRE layer: code that reads itself at runtime to drive behavior — dependency injection, dispatch, and registration. The aim is to declare "this participates in X" at the definition site so a framework attaches behavior, instead of maintaining a second hand-edited wiring list the agent must remember to update.
* Decorators — the closest cousin to dunders: a marker a framework reads to attach behavior, such as `@app.route`, `@pytest.fixture`, `@dataclass`, or a project's own `@register_handler`. Use a decorator to declare participation instead of hand-wiring; self-registration lives here. Always apply `functools.wraps` inside your own decorators so the wrapped function keeps its name, doc, and signature for the agent's perception channel.
* functools.singledispatch and singledispatchmethod — add an operation across many types through isolated, local registrations so extension is additive and never a growing `isinstance` ladder.
* abc.ABC.register() — declare a virtual subclass so `isinstance` succeeds without inheritance, when the structural relationship is real but the class tree should not change.
* inspect — read signatures, source, and members at runtime so tools and agents can discover structure programmatically.
* typing.get_type_hints() and __annotations__ — annotations as runtime data, the basis for DI containers, serializers, and objects that report their own shape.
* DI and settings frameworks (pydantic, attrs, dependency-injector) — read annotations and `Annotated` metadata to generate validation, wiring, and configuration from the declarations the type layer already states.
* dataclasses.fields() and dataclasses.field(metadata=...) — introspect fields and carry arbitrary per-field framework metadata, so a framework can drive behavior from the dataclass definition itself.

# 5. Cross-Cutting Toolkit
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
* Do not write a `__repr__` that hides the fields or falls back to Python's default object form. The repr is the agent's primary perception window, and a useless one blinds every traceback, log line, and test failure.
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
* Look for opportunities to replace a loose or default type with the most precise type that is still true, wherever a value crosses a function boundary.
* Think about which layer — STEER, ENFORCE, or WIRE — is the cheapest channel that can carry a given contract, and fill that layer before falling back to a weaker one.
* Look for state that is implicitly correlated (booleans, flags, optional fields that only make sense together) and consider whether a tagged union would make the illegal combinations unrepresentable.
* Think about what a class's data model is silently telling an agent — its repr, its equality, its hashability — and whether that story is true and complete for what the class represents.
* Before implementing any capability — a dunder, a Protocol, an ABC — ask whether the object genuinely is that kind of thing; treat a meaningless capability as worse than its absence.
* Look for places where a failure can occur and ask whether the resulting exception will tell the next reader what happened, what was expected, and how to recover, as data rather than prose.
* Think about whether an internal invariant (programmer error) is being conflated with an external precondition (caller error), since they call for different enforcement mechanisms.
* Look for hand-maintained registries, lookup tables, or wiring lists sitting beside a definition, and consider whether the definition itself could declare its own participation instead.
* Think about which standard-library helper (dataclasses, functools, enum, contextlib, abc) already generates the channel you are about to hand-write.
* Before finishing a file, consider whether a strict type checker run over it would surface anything this principle would have caught earlier and more cheaply.
* Look for any place a channel is filled with something untrue — a vague type, a hollow repr, a swallowed error — and treat repairing or removing it as higher priority than adding a new one.
* Think about whether the next agent to touch this code would need to open another file to recover a contract that could have lived in this one.

# Code Examples
These examples show the weak form an agent often inherits and the strict form that fills the channel, paired so the failure mode and the fix sit side by side. Each names the intervention point it demonstrates, and together they span boundary parsing, correlated state, the data model, contracts, and framework wiring across a range of software-engineering scenarios.

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
# Weak: three independent booleans can drift into illegal combinations (paid and
# refunded at once), and nothing forces a caller to handle every state — a new
# state silently falls through to the wrong branch.
class PaymentState:
    def __init__(self, is_pending: bool, is_paid: bool, is_refunded: bool, amount_cents: int = 0):
        self.is_pending = is_pending
        self.is_paid = is_paid
        self.is_refunded = is_refunded
        self.amount_cents = amount_cents


def describe(state: PaymentState) -> str:
    if state.is_pending:
        return "awaiting payment"
    if state.is_paid:
        return f"paid {state.amount_cents} cents"
    if state.is_refunded:
        return f"refunded {state.amount_cents} cents"
    return "unknown"  # silently reached if a new state is added and forgotten here


# Strict: a tagged union makes the illegal combinations unrepresentable, and
# assert_never turns a missing case into a type error instead of a silent branch.
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
# Weak: a plain class with no data-model methods. Equality falls back to
# identity, so two invoices with identical data compare unequal; the default
# repr (<Invoice object at 0x7f...>) tells an agent nothing in a traceback or
# test failure; nothing stops a typo'd attribute from silently creating a new
# one instead of raising.
class Invoice:
    def __init__(self, invoice_id, line_items=None):
        self.invoice_id = invoice_id
        self.line_items = line_items or []


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
# Weak: defining a new handler and registering it are two separate edits in two
# different places. An agent that adds CheckoutHandler but forgets the matching
# line in HANDLER_REGISTRY ships a handler that is never dispatched to, with no
# error to signal the omission.
class CheckoutHandler:
    def handle(self, payload: dict) -> None:
        ...


HANDLER_REGISTRY = {
    # "checkout.completed": CheckoutHandler,  # easy to forget this line
}


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

## Example 5: A structural capability check — STEER (Protocol over isinstance/hasattr chains)

```python
# Weak: duck-typing via hasattr leaves the contract implicit and untyped; the
# checker cannot verify a caller's object actually has a working close() method
# with the right signature, so a typo or wrong shape only surfaces at runtime,
# deep inside the call.
def shutdown(resource) -> None:
    if hasattr(resource, "close"):
        resource.close()


# Strict: a Protocol states the exact capability required. The checker lists
# precisely which methods an implementer is missing, and runtime_checkable lets
# the same contract be checked with isinstance at runtime when needed.
from typing import Protocol, runtime_checkable


@runtime_checkable
class Closeable(Protocol):
    def close(self) -> None: ...


def shutdown(resource: Closeable) -> None:
    resource.close()
```

## Example 6: Parsing an external payload at the boundary — STEER (TypedDict, parse-don't-validate)

```python
# Weak: the raw webhook dict flows untyped through the whole call graph. Every
# function that touches it must independently guess the key names and trust
# that other call sites are using the same ones; a renamed key surfaces as a
# runtime KeyError far from where the payload was received.
def handle_webhook(payload: dict) -> None:
    customer_id = payload["data"]["customer_id"]
    amount = payload["data"]["amount_cents"]
    _charge(customer_id, amount)


# Strict: a TypedDict pins the boundary shape so the checker catches a renamed
# or missing key at every call site that touches the payload, not just at the
# one that happens to run first.
from typing import TypedDict


class WebhookData(TypedDict):
    customer_id: str
    amount_cents: int


class WebhookPayload(TypedDict):
    data: WebhookData


def handle_webhook(payload: WebhookPayload) -> None:
    customer_id = payload["data"]["customer_id"]
    amount = payload["data"]["amount_cents"]
    _charge(customer_id, amount)
```

## Example 7: Reporting a failed operation — ENFORCE (typed exception, chained cause)

```python
# Weak: a generic exception with only a message string. The agent cannot branch
# on the failure mode programmatically, and re-raising as a bare Exception
# discards the original exception type even though the traceback chain survives.
def load_plan(plan_id: str) -> dict:
    try:
        return _db_lookup(plan_id)
    except KeyError:
        raise Exception("plan lookup failed")


# Strict: a typed exception carries the failed value and the operation as
# fields, and raise ... from preserves the original cause so the traceback
# shows both the database failure and the lookup that triggered it.
class PlanLookupError(Exception):
    def __init__(self, *, plan_id: str, operation: str) -> None:
        self.plan_id = plan_id
        self.operation = operation
        super().__init__(f"{operation} failed for plan_id={plan_id}")


def load_plan(plan_id: str) -> dict:
    try:
        return _db_lookup(plan_id)
    except KeyError as exc:
        raise PlanLookupError(plan_id=plan_id, operation="load_plan") from exc
```

## Example 8: Ignoring an expected failure — ENFORCE (contextlib.suppress over bare except)

```python
# Weak: a bare except hides which error was anticipated and silently swallows
# every other failure too, including ones that indicate a real bug elsewhere
# in this function.
def remove_cache_entry(key: str) -> None:
    try:
        del _cache[key]
    except:
        pass


# Strict: contextlib.suppress names the exact exception expected, so the intent
# is greppable and any other failure still surfaces instead of being hidden.
from contextlib import suppress


def remove_cache_entry(key: str) -> None:
    with suppress(KeyError):
        del _cache[key]
```

## Example 9: A field invariant enforced on every assignment — ENFORCE (descriptor protocol)

```python
# Weak: the non-negative check is duplicated at every assignment site. A new
# assignment path that forgets to repeat the check — or a future field added
# the same way — silently lets an invalid value through.
class Account:
    def __init__(self, balance: int) -> None:
        if balance < 0:
            raise ValueError("balance must be non-negative")
        self.balance = balance

    def deposit(self, amount: int) -> None:
        new_balance = self.balance + amount
        if new_balance < 0:
            raise ValueError("balance must be non-negative")
        self.balance = new_balance


# Strict: a descriptor enforces the invariant once, in one reusable place, on
# every assignment to balance regardless of which method performs it.
class NonNegative:
    def __set_name__(self, owner: type, name: str) -> None:
        self._name = f"_{name}"

    def __get__(self, obj: object, objtype: type | None = None) -> int:
        return getattr(obj, self._name)

    def __set__(self, obj: object, value: int) -> None:
        if value < 0:
            raise ValueError(f"{self._name[1:]} must be non-negative")
        setattr(obj, self._name, value)


class Account:
    balance = NonNegative()

    def __init__(self, balance: int) -> None:
        self.balance = balance

    def deposit(self, amount: int) -> None:
        self.balance = self.balance + amount
```

## Example 10: Catching a typo'd attribute — ENFORCE (__slots__)

```python
# Weak: assigning to a misspelled attribute silently creates a new one instead
# of raising. order.staus is now a real attribute that nothing reads, and the
# bug surfaces later as a wrong or missing status with no clue why.
class Order:
    def __init__(self, status: str) -> None:
        self.status = status


order = Order(status="pending")
order.staus = "shipped"  # typo creates a new attribute; no error


# Strict: __slots__ fixes the attribute set, so the same typo raises
# AttributeError immediately at the line that made the mistake.
class Order:
    __slots__ = ("status",)

    def __init__(self, status: str) -> None:
        self.status = status


order = Order(status="pending")
order.staus = "shipped"  # AttributeError: 'Order' object has no attribute 'staus'
```

## Example 11: Adding an operation across types — WIRE (singledispatch over an isinstance ladder)

```python
# Weak: every new type that needs serializing requires editing this one growing
# function, and the branches are easy to mis-order, duplicate, or forget when a
# new type is added far from this file.
def serialize(value):
    if isinstance(value, Invoice):
        return {"invoice_id": value.invoice_id}
    elif isinstance(value, Refund):
        return {"refund_id": value.refund_id}
    else:
        raise TypeError(f"no serializer for {type(value)}")


# Strict: each type registers its own serializer at its own definition site.
# Adding a type is additive — no existing function is edited or reordered.
from functools import singledispatch


@singledispatch
def serialize(value: object) -> dict:
    raise TypeError(f"no serializer for {type(value)}")


@serialize.register
def _(value: Invoice) -> dict:
    return {"invoice_id": value.invoice_id}


@serialize.register
def _(value: Refund) -> dict:
    return {"refund_id": value.refund_id}
```

## Example 12: Driving serialization from field declarations — WIRE (dataclasses.fields() introspection)

```python
# Weak: the list of which fields are sensitive lives in a separate function,
# disconnected from the dataclass definition. Adding a new sensitive field to
# the model means remembering to also edit this unrelated, hand-maintained set.
@dataclass
class User:
    user_id: str
    email: str
    password_hash: str


SENSITIVE_FIELDS = {"password_hash"}  # a second list an agent can forget


def to_public_dict(user: User) -> dict:
    return {k: v for k, v in vars(user).items() if k not in SENSITIVE_FIELDS}


# Strict: each field declares its own sensitivity as metadata. A generic
# function reads that metadata from the dataclass definition itself, so a new
# sensitive field is correct by construction with no second list to update.
from dataclasses import dataclass, field, fields


@dataclass
class User:
    user_id: str
    email: str
    password_hash: str = field(metadata={"sensitive": True})


def to_public_dict(user: User) -> dict:
    return {
        f.name: getattr(user, f.name)
        for f in fields(user)
        if not f.metadata.get("sensitive")
    }
```

## Example 13: A container that preserves its element type — STEER (Generic[T])

```python
# Weak: the cache widens every value to object. The checker cannot catch a
# caller storing a User and reading it back as an Invoice; the mistake surfaces
# only at runtime, wherever the wrong attribute is accessed.
class Cache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def put(self, key: str, value) -> None:
        self._store[key] = value

    def get(self, key: str):
        return self._store[key]


# Strict: Generic[T] threads the element type through put and get, so the
# checker rejects a mismatched read at the call site instead of at runtime.
from typing import Generic, TypeVar

T = TypeVar("T")


class Cache(Generic[T]):
    def __init__(self) -> None:
        self._store: dict[str, T] = {}

    def put(self, key: str, value: T) -> None:
        self._store[key] = value

    def get(self, key: str) -> T:
        return self._store[key]


user_cache: Cache[User] = Cache()
```

## Example 14: A closed set of values that carries behavior — STEER (Enum over magic strings)

```python
# Weak: the status is a bare string. Nothing stops a typo like "actve" from
# being assigned, and the routing logic for each status lives in a separate
# if/elif chain that must be kept in sync with every place a status string is
# written.
def route_subscription(status: str) -> str:
    if status == "active":
        return "billing_queue"
    elif status == "past_due":
        return "dunning_queue"
    elif status == "canceled":
        return "archive_queue"
    else:
        return "unknown_queue"  # a typo'd status silently lands here


# Strict: Enum closes the set of valid values so the checker rejects a typo'd
# status at the call site, and each member carries its own routing behavior so
# there is one place to look, not a separate chain to keep in sync.
from enum import Enum


class SubscriptionStatus(Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"

    @property
    def queue(self) -> str:
        return {
            SubscriptionStatus.ACTIVE: "billing_queue",
            SubscriptionStatus.PAST_DUE: "dunning_queue",
            SubscriptionStatus.CANCELED: "archive_queue",
        }[self]


def route_subscription(status: SubscriptionStatus) -> str:
    return status.queue
```

## Example 15: An unfinished implementation — ENFORCE (spec-carrying stub over a silent pass)

```python
# Weak: a silent stub returns None and does nothing. Any caller that depends on
# this function appears to succeed while actually doing nothing, and the gap is
# discovered far from where it was introduced, with no signal pointing back here.
def rank_search_results(results: list) -> list:
    pass


# Strict: the stub states its contract at the exact point the work belongs and
# fails loud if anyone calls it before it is implemented, instead of pretending
# to succeed.
def rank_search_results(results: list[SearchResult]) -> list[SearchResult]:
    raise NotImplementedError(
        "return results ranked by relevance score descending; "
        "tie-break by recency (most recent first)"
    )
```
