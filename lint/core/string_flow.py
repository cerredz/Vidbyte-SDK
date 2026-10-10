"""FILE: lint/core/string_flow.py

PURPOSE: Evaluates a Python expression in vidbyte source to every string value it can hold, as pieces of literal text (with their rel:line origins) and holes for values known only at run time; also infers receiver classes, resolves call targets, binds call arguments to parameters, and decides whether a headers expression carries an Authorization header.
ROLE IN CODEBASE: The evaluator lint/core/url_flow.py uses to trace request URLs, methods, and headers for rules C017 and C018. It reads source facts from lint/core/python_index.py.
ARCHITECTURE NOTE: It follows literals, f-strings, `+`, `or`/`and`/conditional expressions, module and imported constants, upper-case or ClassVar class constants, parameter and local bindings, `str.format`, `removeprefix`/`removesuffix`, `strip` variants, `str()`, `os.environ.get`/`os.getenv` defaults, properties, and the returns of called functions and methods. A method is followed only when its receiver's class is known (self/cls, a class name, an annotated parameter or attribute, or a local built by a constructor or an annotated call), so a same-named method of an unrelated class is never borrowed. Everything else becomes a hole, so an approximation loses information but never invents a value.
FUNCTION INVENTORY: TraceLimitExceeded; Piece, StringValue, TypeRef, Binding, Frame, CallTarget records; StringFlowEvaluator (values, types, targets, parameters, bind, argument, credentials).
COMMON MODIFICATION PATTERNS: Support a new string idiom with one branch in StringFlowEvaluator._values or _string_method and a C017 scratch fixture.
WHAT NOT TO DO: Do not resolve a method by name alone, import vidbyte, or truncate a value set that grows past MAX_VALUES; TraceLimitExceeded makes the rule ERRORED instead of silently tracing less.
KNOWN EDGE CASES: Local bindings are flow-insensitive: every assignment to a name is a possible value. A re-entered name or a recursive call becomes a hole. Lower-case class attributes, dataclass fields, and enum members are runtime state, so they are holes.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md (C017 URL tracing).
TESTS: python lint/run.py --rule C017 and --rule C018; scratch fixtures and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

import ast
import re
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lint.core.python_index import BodyFacts, ClassFacts, ConstSymbol, FunctionFacts, ImportRef, ModuleFacts, ModuleIndex

MAX_CALL_DEPTH = 8
MAX_VALUES = 64
AUTHORIZATION = "authorization"
API_KEY = "api_key"
NO_CREDENTIAL = "none"
UNKNOWN_CREDENTIAL = "unknown"
_STRIP_METHODS = frozenset({"strip", "rstrip", "lstrip"})
_AFFIX_METHODS = frozenset({"removeprefix", "removesuffix"})
_STRING_METHODS = _STRIP_METHODS | _AFFIX_METHODS | {"format"}


class TraceLimitExceeded(RuntimeError):
    """An expression has more possible values than MAX_VALUES; the rule must stop rather than trace a subset."""


@dataclass(frozen=True, slots=True)
class Piece:
    """Literal text with its rel:line origin, or (text None) a hole for a value only known at run time."""

    text: str | None
    origin: str
    label: str = ""
    param: str = ""
    function: int = 0


@dataclass(frozen=True, slots=True)
class StringValue:
    """One possible string: its pieces in order, and the rel:line steps (constants, returns) it flowed through."""

    pieces: tuple[Piece, ...]
    trail: tuple[str, ...] = ()

    @staticmethod
    def literal(text: str, origin: str) -> StringValue:
        return StringValue((Piece(text, origin),))

    @staticmethod
    def hole(origin: str, label: str, param: str = "", function: int = 0) -> StringValue:
        return StringValue((Piece(None, origin, label, param, function),))

    def concat(self, other: StringValue) -> StringValue:
        # Joins two values; the trail keeps each step once, in first-seen order.
        return StringValue(self.pieces + other.pieces, tuple(dict.fromkeys(self.trail + other.trail)))

    def with_step(self, step: str) -> StringValue:
        return StringValue(self.pieces, tuple(dict.fromkeys((*self.trail, step))))

    @property
    def is_literal(self) -> bool:
        return all(piece.text is not None for piece in self.pieces)

    @property
    def text(self) -> str:
        # The full text of a literal value; holes render as their {label}.
        return "".join(piece.text if piece.text is not None else "{" + (piece.label or "?") + "}" for piece in self.pieces)

    def literal_prefix(self) -> str:
        # The literal text before the first hole.
        prefix: list[str] = []
        for piece in self.pieces:
            if piece.text is None:
                break
            prefix.append(piece.text)
        return "".join(prefix)

    def depends_on(self, function: int) -> bool:
        # Whether any hole stands for a parameter of the given function node.
        return any(piece.text is None and piece.function == function and piece.param for piece in self.pieces)

    def literal_origins(self) -> frozenset[str]:
        return frozenset(piece.origin for piece in self.pieces if piece.text is not None)


@dataclass(frozen=True, slots=True, eq=False)
class TypeRef:
    """A known receiver: an instance of a vidbyte class, or (is_class) the class object itself."""

    cls: ClassFacts
    is_class: bool


@dataclass(frozen=True, slots=True, eq=False)
class Binding:
    """The argument expression a caller passed for one parameter and the frame to evaluate it in; expr None is unknown."""

    expr: ast.expr | None
    frame: Frame | None


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    """Where an expression is evaluated: its module, function (with caller bindings), class body, and receiver."""

    module: ModuleFacts
    function: FunctionFacts | None = None
    class_body: ClassFacts | None = None
    args: Mapping[str, Binding] | None = None
    receiver: TypeRef | None = None
    depth: int = 0


@dataclass(frozen=True, slots=True, eq=False)
class CallTarget:
    """A resolved callee: a function or method (with its bound receiver), or a class constructor."""

    function: FunctionFacts | None
    cls: ClassFacts | None
    receiver: TypeRef | None
    implicit_first: bool


class StringFlowEvaluator:
    """Evaluates expressions to possible string values, receiver types, call targets, and header credentials."""

    def __init__(self, index: ModuleIndex) -> None:
        # Starts with empty recursion guards; every cycle becomes a hole.
        self.index = index
        self._active_calls: list[int] = []
        self._active_names: set[tuple[int, str]] = set()
        self._attribute_types: dict[tuple[int, str], list[TypeRef]] = {}

    # ---- string values -------------------------------------------------------------------------------------------

    def values(self, expr: ast.expr, frame: Frame) -> tuple[StringValue, ...]:
        # Every possible string value of an expression; never empty, and never more than MAX_VALUES.
        found = tuple(dict.fromkeys(self._values(expr, frame)))
        if not found:
            return (self._hole(expr, frame),)
        if len(found) > MAX_VALUES:
            raise TraceLimitExceeded(f"{frame.module.location(expr)} `{_snippet(expr)}` has more than {MAX_VALUES} possible string values; simplify it or raise MAX_VALUES in lint/core/string_flow.py with a fixture.")
        return found

    def _hole(self, expr: ast.expr, frame: Frame, label: str = "") -> StringValue:
        return StringValue.hole(frame.module.location(expr), label or _label(expr))

    def _values(self, expr: ast.expr, frame: Frame) -> list[StringValue]:
        # Dispatches on the expression shape; anything unlisted is a hole.
        if isinstance(expr, ast.Constant):
            return [StringValue.literal(expr.value, frame.module.location(expr))] if isinstance(expr.value, str) else [self._hole(expr, frame)]
        if isinstance(expr, ast.JoinedStr):
            return self._product([self._fstring_part(part, frame) for part in expr.values], expr, frame)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            return self._product([list(self.values(expr.left, frame)), list(self.values(expr.right, frame))], expr, frame)
        if isinstance(expr, ast.BoolOp):
            return [value for operand in expr.values for value in self.values(operand, frame)]
        if isinstance(expr, ast.IfExp):
            return [*self.values(expr.body, frame), *self.values(expr.orelse, frame)]
        if isinstance(expr, ast.NamedExpr):
            return list(self.values(expr.value, frame))
        if isinstance(expr, ast.Name):
            return self._name_values(expr, frame)
        if isinstance(expr, ast.Attribute):
            return self._attribute_values(expr, frame)
        if isinstance(expr, ast.Call):
            return self._call_values(expr, frame)
        return [self._hole(expr, frame)]

    def _fstring_part(self, part: ast.expr, frame: Frame) -> list[StringValue]:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            return [StringValue.literal(part.value, frame.module.location(part))]
        if isinstance(part, ast.FormattedValue):
            if part.format_spec is not None or part.conversion not in (-1, ord("s")):
                return [self._hole(part.value, frame)]
            inner = part.value
            if isinstance(inner, ast.Constant) and isinstance(inner.value, int) and not isinstance(inner.value, bool):
                return [StringValue.literal(str(inner.value), frame.module.location(inner))]
            return list(self.values(inner, frame))
        return [self._hole(part, frame)]

    def _product(self, parts: Sequence[Sequence[StringValue]], expr: ast.expr, frame: Frame) -> list[StringValue]:
        # Every concatenation of one value per part, failing loudly instead of truncating.
        results: list[StringValue] = [StringValue(())]
        for options in parts:
            if len(results) * len(options) > MAX_VALUES:
                raise TraceLimitExceeded(f"{frame.module.location(expr)} `{_snippet(expr)}` has more than {MAX_VALUES} possible string values; simplify it or raise MAX_VALUES in lint/core/string_flow.py with a fixture.")
            results = [left.concat(right) for left in results for right in options]
        return results

    def _name_values(self, node: ast.Name, frame: Frame) -> list[StringValue]:
        # Class-body names, then parameters and locals, then module scope and imports.
        name = node.id
        if frame.class_body is not None and name in frame.class_body.constants:
            cls = frame.class_body
            return self._constant(ConstSymbol(cls.module, cls, name, tuple(cls.constants[name])), node, frame)
        function = frame.function
        if function is not None:
            body = self.index.body(function)
            is_param = name in function.param_names()
            if name not in body.globals and (is_param or name in body.assigned or name in body.imports):
                return self._local_values(node, frame, function, body, is_param)
        symbol = self.index.resolve(frame.module, name)
        if isinstance(symbol, ConstSymbol):
            return self._constant(symbol, node, frame)
        return [self._hole(node, frame)]

    def _local_values(self, node: ast.Name, frame: Frame, function: FunctionFacts, body: BodyFacts, is_param: bool) -> list[StringValue]:
        # A parameter's bound value plus every local assignment; a re-entered name contributes only its parameter value.
        name = node.id
        key = (id(frame), name)
        results: list[StringValue] = list(self._param_values(name, node, frame, function)) if is_param else []
        if key in self._active_names:
            return results or [self._hole(node, frame)]
        self._active_names.add(key)
        try:
            for value in body.assigned.get(name, []):
                results.extend(self.values(value, frame) if value is not None else [self._hole(node, frame)])
            if name in body.imports:
                symbol = self.index.resolve_import(body.imports[name])
                results.extend(self._constant(symbol, node, frame) if isinstance(symbol, ConstSymbol) else [self._hole(node, frame)])
        finally:
            self._active_names.discard(key)
        return results

    def _param_values(self, name: str, node: ast.Name, frame: Frame, function: FunctionFacts) -> tuple[StringValue, ...]:
        # A caller-bound parameter evaluates in the caller's frame; an unbound one is a hole tagged with its function.
        if frame.args is None:
            return (StringValue.hole(function.location, name, param=name, function=id(function.node)),)
        binding = frame.args.get(name)
        if binding is None or binding.expr is None or binding.frame is None:
            return (self._hole(node, frame, name),)
        return self.values(binding.expr, binding.frame)

    def _constant(self, symbol: ConstSymbol, node: ast.expr, frame: Frame) -> list[StringValue]:
        # Every assignment of a constant, evaluated where it was defined, with the definition recorded in the trail.
        owner = symbol.owner
        where = Frame(module=symbol.module, class_body=owner, depth=frame.depth)
        label = f"{owner.name}.{symbol.name}" if owner is not None else symbol.name
        results: list[StringValue] = []
        key = (id(symbol.module), f"{label}")
        if key in self._active_names:
            return [self._hole(node, frame, label)]
        self._active_names.add(key)
        try:
            for value in symbol.values:
                if value is None:
                    results.append(self._hole(node, frame, label))
                    continue
                step = f"{symbol.module.rel}:{value.lineno} {label}"
                results.extend(item.with_step(step) for item in self.values(value, where))
        finally:
            self._active_names.discard(key)
        return results

    def _attribute_values(self, node: ast.Attribute, frame: Frame) -> list[StringValue]:
        # module.NAME, then class constants and properties on a receiver of known class.
        owner = self._module_of(node.value, frame)
        if owner is not None:
            symbol = self.index.resolve(owner, node.attr)
            return self._constant(symbol, node, frame) if isinstance(symbol, ConstSymbol) else [self._hole(node, frame)]
        results: list[StringValue] = []
        for receiver in self.types(node.value, frame):
            results.extend(self._member_values(receiver, node, frame))
        return results or [self._hole(node, frame)]

    def _member_values(self, receiver: TypeRef, node: ast.Attribute, frame: Frame) -> list[StringValue]:
        # An upper-case or ClassVar class constant, or a property's return values; instance state is a hole.
        attr = node.attr
        for cls in self.index.bases(receiver.cls):
            if attr in cls.methods:
                method = self.index.function(cls.module, cls.methods[attr], cls)
                if method.kind == "property":
                    return self._returns(CallTarget(method, None, receiver, True), None, frame)
                return [self._hole(node, frame)]
            if attr in cls.constants:
                if self.index.is_enum(cls) or not (attr.isupper() or attr in cls.classvars):
                    return [self._hole(node, frame)]
                return self._constant(ConstSymbol(cls.module, cls, attr, tuple(cls.constants[attr])), node, frame)
        return [self._hole(node, frame)]

    def _call_values(self, node: ast.Call, frame: Frame) -> list[StringValue]:
        # Environment defaults, str(), resolved callees, then string methods on string receivers.
        func = node.func
        if self._is_environment_get(func, frame):
            default = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == "default"), None)
            return [self._hole(node, frame), *(self.values(default, frame) if default is not None else ())]
        if isinstance(func, ast.Name) and func.id == "str" and self.index.resolve(frame.module, "str") is None and len(node.args) == 1 and not node.keywords:
            return list(self.values(node.args[0], frame))
        targets = self.targets(func, frame)
        if targets:
            return [value for target in targets for value in self._returns(target, node, frame)]
        if isinstance(func, ast.Attribute) and func.attr in _STRING_METHODS:
            return self._string_method(func, node, frame)
        return [self._hole(node, frame)]

    def _returns(self, target: CallTarget, call: ast.Call | None, frame: Frame) -> list[StringValue]:
        # A callee's return values with its parameters bound to this call's arguments; constructors build objects, not strings.
        function = target.function
        if function is None:
            return [StringValue.hole(frame.module.location(call) if call is not None else "", target.cls.name if target.cls else "?")]
        where = frame.module.location(call) if call is not None else function.location
        if frame.depth >= MAX_CALL_DEPTH or id(function.node) in self._active_calls:
            return [StringValue.hole(where, f"{function.qualname}(...)")]
        body = self.index.body(function)
        if body.yields or not body.returns:
            return [StringValue.hole(where, f"{function.qualname}(...)")]
        callee = Frame(module=function.module, function=function, args=self.bind(target, call, frame), receiver=target.receiver, depth=frame.depth + 1)
        results: list[StringValue] = []
        self._active_calls.append(id(function.node))
        try:
            for statement in body.returns:
                if statement.value is None:
                    continue
                step = f"{function.module.rel}:{statement.lineno} return in {function.qualname}"
                results.extend(value.with_step(step) for value in self.values(statement.value, callee))
        finally:
            self._active_calls.pop()
        return results or [StringValue.hole(where, f"{function.qualname}(...)")]

    def _string_method(self, func: ast.Attribute, call: ast.Call, frame: Frame) -> list[StringValue]:
        # str.format, removeprefix/removesuffix, and strip variants applied to each receiver value.
        receivers = self.values(func.value, frame)
        if func.attr == "format":
            return [value for receiver in receivers for value in self._format(receiver, call, frame)]
        if any(isinstance(arg, ast.Starred) for arg in call.args) or call.keywords or len(call.args) > 1:
            return [self._hole(call, frame)]
        if func.attr in _AFFIX_METHODS:
            if len(call.args) != 1:
                return [self._hole(call, frame)]
            affixes = self.values(call.args[0], frame)
            return [self._affix(receiver, affix, func.attr, call, frame) for receiver in receivers for affix in affixes]
        chars_values: tuple[StringValue | None, ...] = self.values(call.args[0], frame) if call.args else (None,)
        return [self._strip(receiver, chars, func.attr, call, frame) for receiver in receivers for chars in chars_values]

    def _affix(self, receiver: StringValue, affix: StringValue, method: str, call: ast.Call, frame: Frame) -> StringValue:
        # Removes a literal prefix or suffix from the literal end of a value; an unknown affix makes the result unknown.
        if not affix.is_literal:
            return self._hole(call, frame)
        text = affix.text
        if not text:
            return receiver
        at_end = method == "removesuffix"
        run, rest = _literal_run(receiver.pieces, at_end)
        joined = "".join(piece.text or "" for piece in run)
        if not run or not (joined.endswith(text) if at_end else joined.startswith(text)):
            # Either the literal end lacks the affix, or the end is a hole that may carry it; the literal part is unchanged.
            return receiver
        trimmed = joined[: len(joined) - len(text)] if at_end else joined[len(text):]
        return StringValue(_rejoin(run, trimmed, rest, at_end), receiver.trail)

    def _strip(self, receiver: StringValue, chars: StringValue | None, method: str, call: ast.Call, frame: Frame) -> StringValue:
        # Strips characters from the literal end(s) a strip variant touches; an end that is a hole stays as it is.
        if chars is not None and not chars.is_literal:
            return self._hole(call, frame)
        strip_chars = chars.text if chars is not None else None
        value = receiver
        for at_end in (False, True):
            if (at_end and method == "lstrip") or (not at_end and method == "rstrip"):
                continue
            run, rest = _literal_run(value.pieces, at_end)
            if not run:
                continue
            joined = "".join(piece.text or "" for piece in run)
            stripped = joined.rstrip(strip_chars) if at_end else joined.lstrip(strip_chars)
            whole = len(run) == len(value.pieces)
            if whole:
                stripped = joined.strip(strip_chars) if method == "strip" else stripped
            value = StringValue(_rejoin(run, stripped, rest, at_end), value.trail)
            if whole:
                break
        return value

    def _format(self, receiver: StringValue, call: ast.Call, frame: Frame) -> list[StringValue]:
        # str.format on a literal template: literal arguments are substituted, any other argument is a hole named after its field.
        if not receiver.is_literal or any(isinstance(arg, ast.Starred) for arg in call.args) or any(kw.arg is None for kw in call.keywords):
            return [self._hole(call, frame)]
        try:
            parsed = list(string.Formatter().parse(receiver.text))
        except ValueError:
            return [self._hole(call, frame)]
        origin = receiver.pieces[0].origin if receiver.pieces else frame.module.location(call)
        carried = [Piece("", piece.origin) for piece in receiver.pieces[1:]]
        keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
        parts: list[list[StringValue]] = [[StringValue((Piece("", origin), *carried), receiver.trail)]]
        automatic = 0
        for literal_text, field_name, format_spec, conversion in parsed:
            if literal_text:
                parts.append([StringValue.literal(literal_text, origin)])
            if field_name is None:
                continue
            argument: ast.expr | None
            if field_name == "":
                argument = call.args[automatic] if automatic < len(call.args) else None
                automatic += 1
            elif field_name.isdigit():
                argument = call.args[int(field_name)] if int(field_name) < len(call.args) else None
            else:
                argument = keywords.get(field_name)
            if argument is None or format_spec or conversion not in (None, "s") or not re.fullmatch(r"\w*", field_name):
                parts.append([StringValue.hole(frame.module.location(call), field_name or "?")])
                continue
            parts.append(list(self.values(argument, frame)))
        return self._product(parts, call, frame)

    def _is_environment_get(self, func: ast.expr, frame: Frame) -> bool:
        # os.environ.get(...), environ.get(...) imported from os, os.getenv(...), or getenv(...) imported from os.
        if isinstance(func, ast.Attribute) and func.attr == "get":
            target = func.value
            if isinstance(target, ast.Attribute) and target.attr == "environ" and self._imported_module(target.value, frame) == "os":
                return True
            return isinstance(target, ast.Name) and self._imported(target.id, frame) == ImportRef("os", "environ")
        if isinstance(func, ast.Attribute) and func.attr == "getenv":
            return self._imported_module(func.value, frame) == "os"
        return isinstance(func, ast.Name) and self._imported(func.id, frame) == ImportRef("os", "getenv")

    def _imported(self, name: str, frame: Frame) -> ImportRef | None:
        if frame.function is not None:
            local = self.index.body(frame.function).imports.get(name)
            if local is not None:
                return local
        return frame.module.imports.get(name)

    def _imported_module(self, node: ast.expr, frame: Frame) -> str | None:
        if isinstance(node, ast.Name):
            ref = self._imported(node.id, frame)
            return ref.module if ref is not None and ref.name is None else None
        return None

    def _module_of(self, node: ast.expr, frame: Frame) -> ModuleFacts | None:
        # The vidbyte module an expression names (an imported module alias or a dotted path of them).
        if isinstance(node, ast.Name):
            if frame.function is not None and node.id in frame.function.param_names():
                return None
            local = self.index.body(frame.function).imports.get(node.id) if frame.function is not None else None
            symbol = self.index.resolve_import(local) if local is not None else self.index.resolve(frame.module, node.id)
            return symbol if isinstance(symbol, ModuleFacts) else None
        if isinstance(node, ast.Attribute):
            parent = self._module_of(node.value, frame)
            if parent is not None:
                symbol = self.index.resolve(parent, node.attr)
                return symbol if isinstance(symbol, ModuleFacts) else None
        return None

    # ---- receiver types and call targets -------------------------------------------------------------------------

    def types(self, expr: ast.expr, frame: Frame) -> list[TypeRef]:
        # The vidbyte classes an expression is known to be an instance of (or, for a class name, the class itself).
        if isinstance(expr, ast.Name):
            return self._name_types(expr, frame)
        if isinstance(expr, ast.Attribute):
            owner = self._module_of(expr.value, frame)
            if owner is not None:
                symbol = self.index.resolve(owner, expr.attr)
                return [TypeRef(symbol, True)] if isinstance(symbol, ClassFacts) else []
            return [found for receiver in self.types(expr.value, frame) for found in self._attribute_types_of(receiver, expr.attr)]
        if isinstance(expr, ast.Call):
            found: list[TypeRef] = []
            for target in self.targets(expr.func, frame):
                if target.cls is not None:
                    found.append(TypeRef(target.cls, False))
                elif target.function is not None:
                    found.extend(TypeRef(cls, False) for cls in self.index.annotation_classes(target.function.node.returns, target.function.module))
            return found
        if isinstance(expr, ast.IfExp):
            return [*self.types(expr.body, frame), *self.types(expr.orelse, frame)]
        if isinstance(expr, ast.BoolOp):
            return [found for operand in expr.values for found in self.types(operand, frame)]
        return []

    def _name_types(self, node: ast.Name, frame: Frame) -> list[TypeRef]:
        name = node.id
        function = frame.function
        if function is not None:
            if name == function.receiver_name() and function.owner is not None:
                return [frame.receiver or TypeRef(function.owner, function.kind == "classmethod")]
            body = self.index.body(function)
            if name in function.param_names():
                annotated = [TypeRef(cls, False) for cls in self.index.annotation_classes(function.annotation(name), function.module)]
                if annotated:
                    return annotated
                binding = frame.args.get(name) if frame.args is not None else None
                if binding is not None and binding.expr is not None and binding.frame is not None:
                    return self.types(binding.expr, binding.frame)
                return []
            if name in body.assigned and name not in body.globals:
                key = (id(frame), f"type:{name}")
                if key in self._active_names:
                    return []
                self._active_names.add(key)
                try:
                    return [found for value in body.assigned[name] if value is not None for found in self.types(value, frame)]
                finally:
                    self._active_names.discard(key)
            if name in body.imports:
                symbol = self.index.resolve_import(body.imports[name])
                return [TypeRef(symbol, True)] if isinstance(symbol, ClassFacts) else []
        symbol = self.index.resolve(frame.module, name)
        if isinstance(symbol, ClassFacts):
            return [TypeRef(symbol, True)]
        if isinstance(symbol, ConstSymbol):
            where = Frame(module=symbol.module)
            return [found for value in symbol.values if value is not None for found in self.types(value, where)]
        return []

    def _attribute_types_of(self, receiver: TypeRef, attr: str) -> list[TypeRef]:
        # An attribute's class from its class-level annotation, its assignments in methods, or a property's return annotation.
        key = (id(receiver.cls.node), attr)
        cached = self._attribute_types.get(key)
        if cached is not None:
            return cached
        self._attribute_types[key] = []
        found: list[TypeRef] = []
        for cls in self.index.bases(receiver.cls):
            if attr in cls.methods:
                method = self.index.function(cls.module, cls.methods[attr], cls)
                if method.kind == "property":
                    found.extend(TypeRef(item, False) for item in self.index.annotation_classes(method.node.returns, cls.module))
                break
            if attr in cls.annotations:
                found.extend(TypeRef(item, False) for item in self.index.annotation_classes(cls.annotations[attr], cls.module))
            if attr in cls.constants:
                where = Frame(module=cls.module, class_body=cls)
                found.extend(item for value in cls.constants[attr] if value is not None for item in self.types(value, where))
            for method_node in cls.methods.values():
                method = self.index.function(cls.module, method_node, cls)
                receiver_name = method.receiver_name()
                if not receiver_name:
                    continue
                for target, annotation, value in self.index.body(method).attribute_stores:
                    if target.attr != attr or not (isinstance(target.value, ast.Name) and target.value.id == receiver_name):
                        continue
                    if annotation is not None:
                        found.extend(TypeRef(item, False) for item in self.index.annotation_classes(annotation, cls.module))
                    if value is not None:
                        found.extend(self.types(value, Frame(module=cls.module, function=method)))
            if found:
                break
        unique = list({id(item.cls.node): item for item in found}.values())
        self._attribute_types[key] = unique
        return unique

    def targets(self, func: ast.expr, frame: Frame) -> list[CallTarget]:
        # Functions, methods on known receivers, and constructors a call expression can invoke.
        if isinstance(func, ast.Name):
            if frame.function is not None:
                body = self.index.body(frame.function)
                if func.id in frame.function.param_names() or (func.id in body.assigned and func.id not in body.globals):
                    return []
                if func.id in body.imports:
                    return self._symbol_targets(self.index.resolve_import(body.imports[func.id]))
            return self._symbol_targets(self.index.resolve(frame.module, func.id))
        if not isinstance(func, ast.Attribute):
            return []
        owner = self._module_of(func.value, frame)
        if owner is not None:
            return self._symbol_targets(self.index.resolve(owner, func.attr))
        found: list[CallTarget] = []
        for receiver in self.types(func.value, frame):
            method = self._method(receiver.cls, func.attr)
            if method is None:
                continue
            if method.kind == "staticmethod":
                found.append(CallTarget(method, None, None, False))
            elif method.kind == "classmethod":
                found.append(CallTarget(method, None, TypeRef(receiver.cls, True), True))
            elif method.kind == "method":
                found.append(CallTarget(method, None, receiver, not receiver.is_class))
        return found

    def _symbol_targets(self, symbol: object | None) -> list[CallTarget]:
        if isinstance(symbol, FunctionFacts):
            return [CallTarget(symbol, None, None, False)]
        if isinstance(symbol, ClassFacts):
            return [CallTarget(None, symbol, None, False)]
        return []

    def _method(self, cls: ClassFacts, name: str) -> FunctionFacts | None:
        for current in self.index.bases(cls):
            if name in current.methods:
                return self.index.function(current.module, current.methods[name], current)
        return None

    def parameters(self, target: CallTarget) -> tuple[list[str], set[str], FunctionFacts | None]:
        # The positional parameter names a call binds in order, all parameter names, and the function that declares them.
        if target.function is not None:
            names = [arg.arg for arg in target.function.positional()]
            return (names[1:] if target.implicit_first else names), target.function.param_names(), target.function
        if target.cls is None:
            return [], set(), None
        init = self._method(target.cls, "__init__")
        if init is not None:
            names = [arg.arg for arg in init.positional()][1:]
            return names, init.param_names(), init
        if target.cls.is_dataclass:
            fields: list[str] = []
            for cls in reversed(self.index.bases(target.cls)):
                fields.extend(name for name in cls.fields if name not in fields)
            return fields, set(fields), None
        return [], set(), None

    def bind(self, target: CallTarget, call: ast.Call | None, frame: Frame) -> dict[str, Binding]:
        # Maps each parameter to the caller's argument, its default, or an unknown binding.
        function = target.function
        if function is None:
            return {}
        positional, names, _ = self.parameters(target)
        bindings: dict[str, Binding] = {}
        unknown_rest = False
        if call is not None:
            for index, arg in enumerate(call.args):
                if isinstance(arg, ast.Starred):
                    unknown_rest = True
                    break
                if index < len(positional):
                    bindings[positional[index]] = Binding(arg, frame)
            for keyword in call.keywords:
                if keyword.arg is None:
                    unknown_rest = True
                elif keyword.arg in names:
                    bindings[keyword.arg] = Binding(keyword.value, frame)
        defaults_frame = Frame(module=function.module, class_body=function.owner, depth=frame.depth + 1)
        for name in names:
            if name in bindings:
                continue
            default = None if unknown_rest else function.default(name)
            bindings[name] = Binding(default, defaults_frame if default is not None else None)
        return bindings

    def argument(self, call: ast.Call, name: str, frame: Frame) -> tuple[bool, ast.expr | None, list[CallTarget]]:
        # Whether a call passes the named parameter (by keyword, or by position to a callee whose signature is known).
        for keyword in call.keywords:
            if keyword.arg == name:
                return True, keyword.value, []
        targets = self.targets(call.func, frame)
        for target in targets:
            positional, _, _ = self.parameters(target)
            if name in positional:
                index = positional.index(name)
                if index < len(call.args) and not any(isinstance(arg, ast.Starred) for arg in call.args[: index + 1]):
                    return True, call.args[index], targets
        return False, None, targets

    # ---- credentials ---------------------------------------------------------------------------------------------

    def credentials(self, expr: ast.expr | None, frame: Frame, depth: int = 0) -> frozenset[str]:
        # Whether headers carry an Authorization header (the caller's API key), none at all, or cannot be told.
        if expr is None or depth > MAX_CALL_DEPTH:
            return frozenset({UNKNOWN_CREDENTIAL})
        if isinstance(expr, ast.Dict):
            return self._dict_credentials(expr, frame, depth)
        if isinstance(expr, (ast.IfExp, ast.BoolOp)):
            operands = [expr.body, expr.orelse] if isinstance(expr, ast.IfExp) else list(expr.values)
            return frozenset().union(*(self.credentials(operand, frame, depth + 1) for operand in operands))
        if isinstance(expr, ast.Name):
            return self._name_credentials(expr, frame, depth)
        if isinstance(expr, ast.Call):
            return self._call_credentials(expr, frame, depth)
        return frozenset({UNKNOWN_CREDENTIAL})

    def _dict_credentials(self, expr: ast.Dict, frame: Frame, depth: int) -> frozenset[str]:
        unknown = False
        spreads: list[frozenset[str]] = []
        for key, value in zip(expr.keys, expr.values, strict=True):
            if key is None:
                spreads.append(self.credentials(value, frame, depth + 1))
                continue
            names = self.values(key, frame)
            if any(name.is_literal and name.text.lower() == AUTHORIZATION for name in names):
                return frozenset({API_KEY})
            unknown = unknown or not all(name.is_literal for name in names)
        if any(API_KEY in spread for spread in spreads):
            return frozenset({API_KEY})
        if unknown or any(UNKNOWN_CREDENTIAL in spread for spread in spreads):
            return frozenset({UNKNOWN_CREDENTIAL})
        return frozenset({NO_CREDENTIAL})

    def _name_credentials(self, node: ast.Name, frame: Frame, depth: int) -> frozenset[str]:
        function = frame.function
        if function is None:
            symbol = self.index.resolve(frame.module, node.id)
            if isinstance(symbol, ConstSymbol) and all(value is not None for value in symbol.values):
                where = Frame(module=symbol.module)
                return frozenset().union(*(self.credentials(value, where, depth + 1) for value in symbol.values))
            return frozenset({UNKNOWN_CREDENTIAL})
        name = node.id
        body = self.index.body(function)
        found: set[str] = set()
        if name in function.param_names():
            binding = frame.args.get(name) if frame.args is not None else None
            found |= self.credentials(binding.expr, binding.frame, depth + 1) if binding is not None and binding.frame is not None else {UNKNOWN_CREDENTIAL}
        key = (id(frame), f"credential:{name}")
        if key in self._active_names:
            return frozenset(found or {UNKNOWN_CREDENTIAL})
        self._active_names.add(key)
        try:
            for value in body.assigned.get(name, []):
                found |= self.credentials(value, frame, depth + 1) if value is not None else {UNKNOWN_CREDENTIAL}
        finally:
            self._active_names.discard(key)
        if not found:
            return self._name_credentials(node, Frame(module=frame.module), depth + 1)
        for store_key in body.item_stores.get(name, []):
            names = self.values(store_key, frame) if store_key is not None else ()
            if any(item.is_literal and item.text.lower() == AUTHORIZATION for item in names):
                found = (found - {NO_CREDENTIAL}) | {API_KEY}
            elif not names or not all(item.is_literal for item in names):
                found.add(UNKNOWN_CREDENTIAL)
        if name in body.mutated:
            found.add(UNKNOWN_CREDENTIAL)
        return frozenset(found)

    def _call_credentials(self, call: ast.Call, frame: Frame, depth: int) -> frozenset[str]:
        if isinstance(call.func, ast.Name) and call.func.id == "dict" and self.index.resolve(frame.module, "dict") is None:
            if any(keyword.arg is not None and keyword.arg.lower() == AUTHORIZATION for keyword in call.keywords):
                return frozenset({API_KEY})
            inner = [self.credentials(arg, frame, depth + 1) for arg in call.args]
            inner += [self.credentials(keyword.value, frame, depth + 1) for keyword in call.keywords if keyword.arg is None]
            if any(API_KEY in item for item in inner):
                return frozenset({API_KEY})
            return frozenset({UNKNOWN_CREDENTIAL}) if any(UNKNOWN_CREDENTIAL in item for item in inner) else frozenset({NO_CREDENTIAL})
        found: set[str] = set()
        for target in self.targets(call.func, frame):
            function = target.function
            if function is None or id(function.node) in self._active_calls:
                found.add(UNKNOWN_CREDENTIAL)
                continue
            body = self.index.body(function)
            callee = Frame(module=function.module, function=function, args=self.bind(target, call, frame), receiver=target.receiver, depth=frame.depth + 1)
            self._active_calls.append(id(function.node))
            try:
                for statement in body.returns:
                    found |= self.credentials(statement.value, callee, depth + 1)
            finally:
                self._active_calls.pop()
            if not body.returns:
                found.add(UNKNOWN_CREDENTIAL)
        return frozenset(found or {UNKNOWN_CREDENTIAL})


def _literal_run(pieces: tuple[Piece, ...], at_end: bool) -> tuple[list[Piece], list[Piece]]:
    # The maximal run of literal pieces at one end of a value, and the remaining pieces.
    ordered = list(reversed(pieces)) if at_end else list(pieces)
    run: list[Piece] = []
    for piece in ordered:
        if piece.text is None:
            break
        run.append(piece)
    rest = ordered[len(run):]
    if at_end:
        return list(reversed(run)), list(reversed(rest))
    return run, rest


def _rejoin(run: list[Piece], text: str, rest: list[Piece], at_end: bool) -> tuple[Piece, ...]:
    # Rebuilds a value after its literal end run became `text`; the run's other origins stay as empty pieces.
    head = run[-1] if at_end else run[0]
    kept = [Piece("", piece.origin) for piece in run if piece is not head]
    new_run = [*kept, Piece(text, head.origin)] if at_end else [Piece(text, head.origin), *kept]
    return tuple([*rest, *new_run] if at_end else [*new_run, *rest])


def _label(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    if isinstance(expr, ast.Call):
        return f"{_label(expr.func)}(...)"
    return type(expr).__name__.lower()


def _snippet(expr: ast.expr) -> str:
    text = ast.unparse(expr)
    return text if len(text) <= 80 else f"{text[:77]}..."
