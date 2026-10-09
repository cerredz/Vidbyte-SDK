"""FILE: lint/rules/c006_finite_numeric_guards.py

PURPOSE: Detect construction-time numeric range guards that still accept True, NaN, or an infinity.
ROLE IN CODEBASE: Enforces C006 so settings, config, and record validation cannot silently disable a budget, limit, or timeout.
ARCHITECTURE NOTE: Static AST only. Each range-checked value is re-evaluated with four probe values (True, NaN, +inf, -inf) through every guard that reads it, so the rule proves what slips through instead of pattern-matching fix text.
FUNCTION INVENTORY: ValidationSiteFinder lists sites; SubjectIndex resolves values; GuardCollector finds guards; ProbeEvaluator evaluates one guard; ProbeJudge decides acceptance; FiniteNumericGuardAnalyzer coordinates; FiniteNumericGuardsRule reports.
COMMON MODIFICATION PATTERNS: Add a probe, a subject shape, or a validator name together with its diagnostic wording, then rerun C006 and its scratch fixtures.
WHAT NOT TO DO: Do not import SDK modules, flag runtime accessors, or report a probe the evaluator cannot prove passes every guard.
KNOWN EDGE CASES: Unknown sub-expressions never prove acceptance. A value handed to a validator helper is judged inside that helper. Other inputs in a cross-field guard are assumed valid (finite, or None when optional).
RELATED DOCS: docs/design/lint-sdk-settings-validation.md; tests/features/sdk_loop_settings/FEATURE.md; tests/features/sdk_middleware_limits/FEATURE.md
TESTS: python lint/run.py --rule C006; fixture and mutation results are recorded in the S1 pull request body.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_CONSTRUCTORS = frozenset({"__init__", "__post_init__"})
_VALIDATOR_NAME = re.compile(r"^_?(validate|validated|require|ensure|normalize|coerce|check)(_|$)")
_DELEGATE_NAME = re.compile(r"^_?(validate|validated|require|ensure|normalize|coerce|check|positive|non_?negative|finite)(_|$)|^require$")
_CONSTANT_NAME = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
_ORDERED = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_PREDICATES = frozenset({"isinstance", "isfinite", "isnan", "isinf"})
_INT = "int"
_REAL = "real"
_ANNOTATION_NOISE = frozenset({"None", "Optional", "Union", "typing"})
_REAL_TOKENS = frozenset({"float", "Real", "Number", "numbers"})
_TYPE_NAMES = {"bool": (bool,), "int": (int,), "float": (float,), "Real": (int, float), "Number": (int, float), "complex": (complex,), "str": (str,)}
_UNKNOWN = object()
_REJECTED = object()
_FINITE = object()
_LOCAL_DEPTH = 4
_GUARD_TEXT_LIMIT = 160
_IMPORT_DEPTH = 3


@dataclass(frozen=True, slots=True)
class Probe:
    """One invalid value that a strict numeric guard must reject."""

    label: str
    value: bool | float

    def __post_init__(self) -> None:
        # Probes are the values the #523-#529 fix series proved can slip through a plain range check.
        if not self.label or not isinstance(self.value, (bool, float)):
            raise ValueError(f"Probe needs a label and a bool or float value, got {self.label!r}={self.value!r}.")


PROBES = (Probe("True", True), Probe("float('nan')", math.nan), Probe("float('inf')", math.inf), Probe("float('-inf')", -math.inf))


@dataclass(frozen=True, slots=True)
class NumericSubject:
    """One value a validation site range-checks: a parameter, a self field, or a getattr sweep over fields."""

    key: str
    display: str
    kind: str
    annotation: str

    def __post_init__(self) -> None:
        # The kind decides the repair, so a subject of unknown kind must never be built.
        if self.kind not in {_INT, _REAL}:
            raise ValueError(f"NumericSubject.kind must be {_INT!r} or {_REAL!r}, got {self.kind!r}.")
        if not self.key or not self.display:
            raise ValueError("NumericSubject needs a key and a display name.")


@dataclass(frozen=True, slots=True)
class ValidationSite:
    """One function that validates construction input: a constructor, __post_init__, or a validator-named helper."""

    source: SourceFile
    function: ast.FunctionDef | ast.AsyncFunctionDef
    owner: ast.ClassDef | None

    def symbol(self) -> str:
        # Renders Class.method, or the bare name for a module-level helper.
        return f"{self.owner.name}.{self.function.name}" if self.owner is not None else self.function.name


@dataclass(frozen=True, slots=True)
class Acceptance:
    """A proven gap: probes that pass every guard on one subject, anchored at the subject's first range guard."""

    site: ValidationSite
    subject: NumericSubject
    operand: str
    line: int
    guard: str
    accepted: tuple[str, ...]

    def __post_init__(self) -> None:
        # An acceptance without an accepted probe would render an empty claim.
        if not self.accepted or any(label not in {probe.label for probe in PROBES} for label in self.accepted):
            raise ValueError(f"Acceptance.accepted must name at least one known probe, got {self.accepted!r}.")
        if self.line < 1:
            raise ValueError(f"Acceptance.line must be positive, got {self.line}.")
        if not self.operand:
            raise ValueError("Acceptance.operand must name the expression the guard reads.")


class ValidationSiteFinder:
    """Lists the functions where construction input is validated."""

    def find(self, source: SourceFile) -> list[ValidationSite]:
        # Constructors, __post_init__, and validator-named helpers are the construction-time boundary.
        if source.tree is None:
            return []
        return [ValidationSite(source=source, function=function, owner=owner) for owner, function in self._functions(source.tree) if function.name in _CONSTRUCTORS or _VALIDATOR_NAME.match(function.name)]

    @staticmethod
    def _functions(tree: ast.Module) -> list[tuple[ast.ClassDef | None, ast.FunctionDef | ast.AsyncFunctionDef]]:
        # Pairs every function with its directly enclosing class, or None for module-level and nested functions.
        methods = [(node, item) for node in ast.walk(tree) if isinstance(node, ast.ClassDef) for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
        claimed = {id(function) for _, function in methods}
        loose = [(None, node) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and id(node) not in claimed]
        return [*methods, *loose]


class LiteralReader:
    """Reads the literal values a guard may compare against, without executing anything."""

    @staticmethod
    def number(node: ast.AST) -> float | int | None:
        # Reads numeric literals, negated literals, float("inf"/"nan"), and math.inf/math.nan.
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)) and not isinstance(node.operand.value, bool):
            return -node.operand.value if isinstance(node.op, ast.USub) else node.operand.value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            text = node.args[0].value.strip().lower()
            return float(text) if text in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "nan"} else None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "math" and node.attr in {"inf", "nan"}:
            return math.inf if node.attr == "inf" else math.nan
        return None

    @staticmethod
    def strings(node: ast.AST) -> tuple[str, ...]:
        # Returns the strings of a literal tuple/list of string constants, else an empty tuple.
        if isinstance(node, (ast.Tuple, ast.List)) and node.elts and all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.elts):
            return tuple(item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str))
        return ()

    @staticmethod
    def name(node: ast.AST) -> str:
        # Returns the final identifier of a Name or Attribute, else an empty string.
        return node.attr if isinstance(node, ast.Attribute) else (node.id if isinstance(node, ast.Name) else "")


@dataclass(frozen=True, slots=True)
class ModuleConstants:
    """Module-level literals the rule may read: string tuples for field sweeps and numbers for bounds."""

    field_tuples: dict[str, tuple[str, ...]]
    numbers: dict[str, float | int]

    @classmethod
    def read(cls, tree: ast.Module) -> ModuleConstants:
        # One pass over top-level assignments; nothing is imported or executed.
        field_tuples: dict[str, tuple[str, ...]] = {}
        numbers: dict[str, float | int] = {}
        for node in tree.body:
            target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else (node.target if isinstance(node, ast.AnnAssign) else None)
            value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(target, ast.Name) and value is not None:
                number = LiteralReader.number(value)
                if LiteralReader.strings(value):
                    field_tuples[target.id] = LiteralReader.strings(value)
                elif number is not None:
                    numbers[target.id] = number
        return cls(field_tuples=field_tuples, numbers=numbers)

    def merged(self, imported: ModuleConstants) -> ModuleConstants:
        # A module's own literals shadow the names it imports.
        return ModuleConstants(field_tuples={**imported.field_tuples, **self.field_tuples}, numbers={**imported.numbers, **self.numbers})


class ConstantResolver:
    """Resolves the literal constants a module imports from another tracked SDK module, following re-exports."""

    def __init__(self, sources: tuple[SourceFile, ...]) -> None:
        # Index every parsed production module by dotted name, so an import resolves without executing anything.
        self._trees = {self.dotted(source.rel): source.tree for source in sources if source.tree is not None}
        self._cache: dict[tuple[str, int], ModuleConstants] = {}

    @staticmethod
    def dotted(rel: str) -> str:
        # vidbyte/lib/constants/jev.py -> vidbyte.lib.constants.jev; a package __init__ is the package itself.
        parts = rel.removesuffix(".py").split("/")
        return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)

    def constants(self, module: str, depth: int = _IMPORT_DEPTH) -> ModuleConstants:
        # Own literals plus absolute `from vidbyte... import NAME` literals, re-exports followed at most depth hops.
        if (module, depth) in self._cache:
            return self._cache[(module, depth)]
        tree = self._trees.get(module)
        own = ModuleConstants.read(tree) if tree is not None else ModuleConstants(field_tuples={}, numbers={})
        imported = ModuleConstants(field_tuples={}, numbers={})
        for node in tree.body if tree is not None and depth > 0 else ():
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in self._trees:
                found = self.constants(node.module, depth - 1)
                imported.field_tuples.update({alias.asname or alias.name: found.field_tuples[alias.name] for alias in node.names if alias.name in found.field_tuples})
                imported.numbers.update({alias.asname or alias.name: found.numbers[alias.name] for alias in node.names if alias.name in found.numbers})
        self._cache[(module, depth)] = own.merged(imported)
        return self._cache[(module, depth)]


class SubjectIndex:
    """Resolves the expressions in one validation site to the numeric subjects they read."""

    def __init__(self, site: ValidationSite, constants: ModuleConstants) -> None:
        # Build every lookup table once so guard evaluation is a dictionary read.
        self.site = site
        self.constants = constants
        self._params = self._parameter_table(site.function)
        self._fields, self._stores = self._field_table(site.owner)
        self._sweeps, self._spans = self._sweep_table(site.function, constants)
        self._aliases: dict[str, list[tuple[int, tuple[str, str]]]] = {}
        self._aliases = self._alias_table(site.function)

    def resolve(self, node: ast.AST) -> tuple[str, str] | None:
        # Returns (subject key, cast) for a parameter, self field, field sweep, local alias, or float()/int() of one.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"float", "int"} and len(node.args) == 1 and not node.keywords:
            inner = self.resolve(node.args[0])
            return (inner[0], node.func.id) if inner is not None else None
        if isinstance(node, ast.Name):
            return self._alias_at(node) or ((f"param:{node.id}", "") if node.id in self._params else None)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            return (f"self:{node.attr}", "") if node.attr in self._fields else None
        sweep = self._sweep_key(node)
        return (sweep, "") if sweep else None

    def mentions(self, node: ast.AST, keys: frozenset[str]) -> bool:
        # True when any sub-expression of node reads one of the subject's keys.
        return any((self.resolve(child) or ("", ""))[0] in keys for child in ast.walk(node) if isinstance(child, ast.expr))

    def canonical(self, key: str) -> str:
        # An __init__ parameter stored as self.<field> is the same value as that field everywhere else in the class.
        family, _, name = key.partition(":")
        if family == "param" and self.site.function.name == "__init__" and name in self._stores:
            return f"self:{self._stores[name]}"
        return key

    def keys_for(self, canonical: str) -> frozenset[str]:
        # The keys this site uses for one value: the field itself, plus the __init__ parameter stored into it.
        family, _, name = canonical.partition(":")
        if family != "self" or self.site.function.name != "__init__":
            return frozenset({canonical})
        return frozenset({canonical, *(f"param:{param}" for param, field in self._stores.items() if field == name)})

    def optional(self, key: str) -> bool:
        # A value annotated with None, or defaulting to None, may legitimately be None.
        family, _, name = key.partition(":")
        annotation, none_default = (self._params if family == "param" else self._fields).get(name, ("", False))
        return none_default or "None" in annotation or "Optional" in annotation

    def subject(self, key: str, guards: list[ast.If], casts: set[str]) -> NumericSubject | None:
        # Builds the typed subject; a loose annotation takes its kind from an isinstance check or a float()/int() cast.
        family, _, name = key.partition(":")
        if family == "sweep":
            fields = self._sweeps[name]
            annotations = tuple(self._fields.get(item, ("", False))[0] for item in fields)
            kinds = {self.kind_of(text) for text in annotations}
            kind = _REAL if _REAL in kinds else (_INT if kinds == {_INT} else None)
            return NumericSubject(key=key, display=f"self.{{{', '.join(fields)}}}", kind=kind, annotation=" / ".join(sorted(set(annotations)))) if kind else None
        annotation = (self._params if family == "param" else self._fields)[name][0]
        cast = {"int": _INT, "float": _REAL}.get(next(iter(casts))) if len(casts) == 1 else None
        kind = self.kind_of(annotation) or self._inferred_kind(key, guards) or cast
        display = name if family == "param" else f"self.{name}"
        return NumericSubject(key=key, display=display, kind=kind, annotation=annotation or "unannotated") if kind else None

    @staticmethod
    def kind_of(annotation: str) -> str | None:
        # Maps an annotation to int or real, ignoring None/Optional; object, Any, and unions with str stay unknown.
        tokens = set(re.findall(r"[A-Za-z_]+", annotation)) - _ANNOTATION_NOISE
        if tokens == {"int"}:
            return _INT
        if tokens and tokens <= {"int"} | _REAL_TOKENS:
            return _REAL
        return None

    def _inferred_kind(self, key: str, guards: list[ast.If]) -> str | None:
        # For object/Any/unannotated values, the type an isinstance guard demands is the declared kind.
        for guard in guards:
            for node in ast.walk(guard.test):
                if isinstance(node, ast.Call) and LiteralReader.name(node.func) == "isinstance" and len(node.args) == 2 and (self.resolve(node.args[0]) or ("", ""))[0] == key:
                    names = {LiteralReader.name(item) for item in ast.walk(node.args[1])}
                    if names & _REAL_TOKENS:
                        return _REAL
                    if "int" in names:
                        return _INT
        return None

    def _alias_at(self, node: ast.Name) -> tuple[str, str] | None:
        # Uses the nearest assignment at or before this line, so a reused local name follows each loop.
        candidates = [resolved for line, resolved in self._aliases.get(node.id, []) if line <= getattr(node, "lineno", 0)]
        return candidates[-1] if candidates else None

    def _sweep_key(self, node: ast.AST) -> str | None:
        # Matches getattr(self, name) inside `for name in (<field names>)` and keys it by the innermost such loop.
        if not (isinstance(node, ast.Call) and LiteralReader.name(node.func) == "getattr" and len(node.args) == 2 and isinstance(node.args[0], ast.Name) and node.args[0].id == "self" and isinstance(node.args[1], ast.Name)):
            return None
        loops = [loop for loop, (variable, start, end) in self._spans.items() if variable == node.args[1].id and start <= node.lineno <= end]
        return f"sweep:{loops[-1]}" if loops else None

    @staticmethod
    def _parameter_table(function: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, tuple[str, bool]]:
        # Maps every non-self parameter to (annotation text, defaults to None).
        positional = [*function.args.posonlyargs, *function.args.args]
        defaulted = positional[len(positional) - len(function.args.defaults):] if function.args.defaults else []
        defaults = {item.arg: value for item, value in zip(defaulted, function.args.defaults, strict=True)}
        defaults.update({item.arg: value for item, value in zip(function.args.kwonlyargs, function.args.kw_defaults, strict=True) if value is not None})
        none_default = {name for name, value in defaults.items() if isinstance(value, ast.Constant) and value.value is None}
        return {item.arg: (ast.unparse(item.annotation) if item.annotation else "", item.arg in none_default) for item in [*positional, *function.args.kwonlyargs] if item.arg not in {"self", "cls"}}

    @staticmethod
    def _field_table(owner: ast.ClassDef | None) -> tuple[dict[str, tuple[str, bool]], dict[str, str]]:
        # Reads class-level annotations, then __init__ parameters stored on self (and remembers param -> field).
        if owner is None:
            return {}, {}
        fields = {item.target.id: (ast.unparse(item.annotation), isinstance(item.value, ast.Constant) and item.value.value is None) for item in owner.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)}
        init = next((item for item in owner.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
        params = SubjectIndex._parameter_table(init) if init is not None else {}
        stores: dict[str, str] = {}
        for node in ast.walk(init) if init is not None else ():
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in params:
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                        fields.setdefault(target.attr, params[node.value.id])
                        stores.setdefault(node.value.id, target.attr)
        return fields, stores

    @staticmethod
    def _sweep_table(function: ast.FunctionDef | ast.AsyncFunctionDef, constants: ModuleConstants) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, int, int]]]:
        # Maps each `for name in <field names>` loop (keyed by its line) to its field names and its line span.
        sweeps: dict[str, tuple[str, ...]] = {}
        spans: dict[str, tuple[str, int, int]] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                names = LiteralReader.strings(node.iter) or (constants.field_tuples.get(node.iter.id, ()) if isinstance(node.iter, ast.Name) else ())
                if names:
                    sweeps[str(node.lineno)] = names
                    spans[str(node.lineno)] = (node.target.id, node.lineno, node.end_lineno or node.lineno)
        return sweeps, spans

    def _alias_table(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, list[tuple[int, tuple[str, str]]]]:
        # Follows `value = self.field`, `value = float(param)`, and `value = getattr(self, name)` back to the subject.
        assignments = sorted((node for node in ast.walk(function) if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)), key=lambda item: item.lineno)
        for node in assignments:
            target = node.targets[0]
            resolved = self.resolve(node.value)
            if resolved is not None and isinstance(target, ast.Name):
                self._aliases.setdefault(target.id, []).append((node.lineno, resolved))
        return self._aliases


class GuardCollector:
    """Finds the raise-guards of one validation site and the range guards among them."""

    def raise_guards(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.If]:
        # An `if` whose own body raises is a rejection; nested function bodies belong to other sites.
        guards: list[ast.If] = []
        stack: list[ast.AST] = list(function.body)
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(node, ast.If) and any(isinstance(item, ast.Raise) for item in node.body):
                guards.append(node)
            stack.extend(ast.iter_child_nodes(node))
        return sorted(guards, key=lambda item: item.lineno)

    def range_keys(self, index: SubjectIndex, guard: ast.If) -> list[str]:
        # Subjects compared with <, <=, > or >= against a literal or a named constant, in a guard that only validates.
        if not self._pure(index, guard.test):
            return []
        keys: list[str] = []
        for node in ast.walk(guard.test):
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                for op, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True):
                    if isinstance(op, _ORDERED):
                        keys.extend(key for key in (self._bounded(index, left, right), self._bounded(index, right, left)) if key)
        return list(dict.fromkeys(keys))

    @staticmethod
    def _bounded(index: SubjectIndex, subject: ast.expr, bound: ast.expr) -> str | None:
        # Returns the subject key when the other operand is a literal number or a named constant.
        resolved = index.resolve(subject)
        if resolved is None or index.resolve(bound) is not None:
            return None
        name = LiteralReader.name(bound)
        constant = name in index.constants.numbers or bool(_CONSTANT_NAME.match(name))
        return resolved[0] if LiteralReader.number(bound) is not None or constant else None

    @staticmethod
    def _pure(index: SubjectIndex, test: ast.expr) -> bool:
        # A guard is a validation only when every atom is a comparison or a type/finite predicate on a subject.
        atoms: list[ast.expr] = [test]
        while atoms:
            atom = atoms.pop()
            if isinstance(atom, ast.BoolOp):
                atoms.extend(atom.values)
            elif isinstance(atom, ast.UnaryOp) and isinstance(atom.op, ast.Not):
                atoms.append(atom.operand)
            elif isinstance(atom, ast.Compare):
                if not any(index.resolve(item) is not None for item in [atom.left, *atom.comparators]):
                    return False
            elif not (isinstance(atom, ast.Call) and LiteralReader.name(atom.func) in _PREDICATES and atom.args and index.resolve(atom.args[0]) is not None):
                return False
        return True


class ProbeEvaluator:
    """Evaluates one guard condition, three-valued, with the subject replaced by one probe value."""

    def __init__(self, index: SubjectIndex, keys: frozenset[str], probe: Probe, others_none: bool) -> None:
        # Binds the subject's keys, the probe, and the assumption about other inputs (optional ones None, or all finite).
        self.index = index
        self.keys = keys
        self.probe = probe
        self.others_none = others_none
        self._locals = self.boolean_locals(index.site.function)
        self._depth = 0

    def raises(self, guard: ast.If) -> bool | None:
        # A top-level `or` lists independent rejections, so disjuncts about other inputs are taken as passing.
        test = guard.test
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
            relevant = [item for item in test.values if self.reads_subject(item)]
            return self.truth(ast.BoolOp(op=ast.Or(), values=relevant)) if relevant else False
        return self.truth(test)

    def reads_subject(self, node: ast.AST) -> bool:
        # True when node reads the subject directly or through a single-assignment boolean local.
        if self.index.mentions(node, self.keys):
            return True
        return any(isinstance(item, ast.Name) and item.id in self._locals and self.index.mentions(self._locals[item.id], self.keys) for item in ast.walk(node))

    def truth(self, node: ast.expr) -> bool | None:
        # Three-valued truth: True, False, or None when the outcome depends on something the rule cannot see.
        if isinstance(node, ast.BoolOp):
            values = [self.truth(item) for item in node.values]
            if isinstance(node.op, ast.And):
                return False if False in values else (True if all(item is True for item in values) else None)
            return True if True in values else (False if all(item is False for item in values) else None)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self.truth(node.operand)
            return None if inner is None else not inner
        if isinstance(node, ast.Compare):
            return self._compare(node)
        if isinstance(node, ast.Call):
            return self._predicate(node)
        if isinstance(node, ast.IfExp):
            return self._conditional(node)
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name) and node.id in self._locals and self._depth < _LOCAL_DEPTH:
            self._depth += 1
            verdict = self.truth(self._locals[node.id])
            self._depth -= 1
            return verdict
        return None

    @staticmethod
    def boolean_locals(function: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, ast.expr]:
        # Maps single-assignment locals such as `valid = (...)` to their defining expression.
        assigned: dict[str, list[ast.expr]] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                assigned.setdefault(node.targets[0].id, []).append(node.value)
        return {name: values[0] for name, values in assigned.items() if len(values) == 1}

    def _compare(self, node: ast.Compare) -> bool | None:
        # A comparison chain is the conjunction of its links.
        operands = [node.left, *node.comparators]
        links = [self._link(left, op, right) for op, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True)]
        return False if False in links else (True if all(item is True for item in links) else None)

    def _link(self, left: ast.expr, op: ast.cmpop, right: ast.expr) -> bool | None:
        # NaN makes every ordered or == comparison False whatever the other side is; infinity beats any finite bound.
        if isinstance(op, (ast.Is, ast.IsNot)):
            return self._none_check(left, op, right)
        if isinstance(op, (ast.In, ast.NotIn)):
            return None
        a, b = self._value(left), self._value(right)
        if a is _REJECTED or b is _REJECTED:
            return True
        if any(isinstance(item, float) and math.isnan(item) for item in (a, b)):
            return isinstance(op, ast.NotEq)
        if a is _UNKNOWN or b is _UNKNOWN or a is None or b is None:
            return None
        if a is _FINITE or b is _FINITE:
            other = b if a is _FINITE else a
            if not (isinstance(other, float) and math.isinf(other)):
                return None
            a, b = (0.0, b) if a is _FINITE else (a, 0.0)
        return self._apply(op, a, b)

    def _none_check(self, left: ast.expr, op: ast.cmpop, right: ast.expr) -> bool | None:
        # A probe is never None; another optional input is None in the first assumption and present in the second.
        left_none, right_none = (isinstance(item, ast.Constant) and item.value is None for item in (left, right))
        resolved = self.index.resolve(right if left_none else left) if left_none != right_none else None
        if resolved is None:
            return None
        is_none = resolved[0] not in self.keys and self.others_none and self.index.optional(resolved[0])
        return is_none if isinstance(op, ast.Is) else not is_none

    def _value(self, node: ast.expr) -> object:
        # Returns the probe (after any float()/int() cast), a literal, _FINITE for another input or a constant, or _UNKNOWN.
        resolved = self.index.resolve(node)
        if resolved is not None:
            if resolved[0] in self.keys:
                return self._cast(resolved[1])
            return None if self.others_none and self.index.optional(resolved[0]) else _FINITE
        literal = LiteralReader.number(node)
        if literal is not None:
            return literal
        name = LiteralReader.name(node)
        if isinstance(node, ast.Name) and name in self.index.constants.numbers:
            return self.index.constants.numbers[name]
        return _FINITE if _CONSTANT_NAME.match(name) else _UNKNOWN

    def _cast(self, cast: str) -> object:
        # float(True) is 1.0 and int(True) is 1; int() raises on NaN and infinity, which rejects the probe.
        value = self.probe.value
        if cast == "float":
            return float(value)
        if cast == "int":
            return int(value) if isinstance(value, bool) or math.isfinite(value) else _REJECTED
        return value

    def _predicate(self, node: ast.Call) -> bool | None:
        # Evaluates isinstance(subject, T) and math.isfinite/isnan/isinf(subject); any other call is unknown.
        name = LiteralReader.name(node.func)
        if not node.args or (self.index.resolve(node.args[0]) or ("", ""))[0] not in self.keys:
            return None
        value = self._value(node.args[0])
        if name == "isinstance" and len(node.args) == 2 and value is not _REJECTED:
            return self._isinstance(value, node.args[1])
        if name in {"isfinite", "isnan", "isinf"} and isinstance(value, (int, float)):
            return {"isfinite": math.isfinite, "isnan": math.isnan, "isinf": math.isinf}[name](value)
        return None

    @staticmethod
    def _isinstance(value: object, types: ast.expr) -> bool | None:
        # Matches the probe's runtime type against bool/int/float/Real names; an unknown class name is unknown.
        verdicts = [isinstance(value, _TYPE_NAMES[label]) if (label := LiteralReader.name(item)) in _TYPE_NAMES else None for item in (types.elts if isinstance(types, ast.Tuple) else [types])]
        return True if True in verdicts else (False if all(item is False for item in verdicts) else None)

    def _conditional(self, node: ast.IfExp) -> bool | None:
        # An unknown condition still decides the result when both branches agree.
        test, body, orelse = self.truth(node.test), self.truth(node.body), self.truth(node.orelse)
        if test is None:
            return body if body == orelse else None
        return body if test else orelse

    @staticmethod
    def _apply(op: ast.cmpop, a: object, b: object) -> bool | None:
        # Applies one comparison operator to two concrete numbers.
        operators = {ast.Lt: lambda x, y: x < y, ast.LtE: lambda x, y: x <= y, ast.Gt: lambda x, y: x > y, ast.GtE: lambda x, y: x >= y, ast.Eq: lambda x, y: x == y, ast.NotEq: lambda x, y: x != y}
        apply = operators.get(type(op))
        return None if apply is None else bool(apply(a, b))


@dataclass(frozen=True, slots=True)
class PoolEntry:
    """One raise-guard that reads the subject, with the index and keys that resolve the subject in its function."""

    index: SubjectIndex
    guard: ast.If
    keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class GuardPool:
    """Every guard that reads one subject across the functions that validate it during construction."""

    entries: tuple[PoolEntry, ...]
    functions: tuple[tuple[SubjectIndex, ast.FunctionDef | ast.AsyncFunctionDef, frozenset[str]], ...]


class ProbeJudge:
    """Decides which probes pass every guard in a pool."""

    def delegated(self, pool: GuardPool) -> bool:
        # A call such as positive_real(x, "x") or JevCount.require(x, ...) owns the check, so the helper is judged instead.
        for index, function, keys in pool.functions:
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and _DELEGATE_NAME.match(LiteralReader.name(node.func)):
                    arguments = [*node.args, *(item.value for item in node.keywords)]
                    if any((index.resolve(item) or ("", ""))[0] in keys for item in arguments):
                        return True
        return False

    def accepted(self, pool: GuardPool) -> tuple[str, ...]:
        # A probe is accepted when, under one assumption about the other inputs, no guard can raise for it.
        return tuple(probe.label for probe in PROBES if any(self._passes(pool, probe, others_none) for others_none in (True, False)))

    @staticmethod
    def _passes(pool: GuardPool, probe: Probe, others_none: bool) -> bool:
        # Every guard must be provably False; an unknown verdict never proves acceptance.
        return all(ProbeEvaluator(entry.index, entry.keys, probe, others_none).raises(entry.guard) is False for entry in pool.entries)


class FiniteNumericGuardAnalyzer:
    """Finds every construction-time range guard that provably accepts True, NaN, or an infinity."""

    def analyze(self, catalog: SourceCatalog) -> list[Acceptance]:
        # Visit every production module once; a module's sites are judged together so class fields share guards.
        sources = catalog.python_files()
        resolver = ConstantResolver(sources)
        acceptances: list[Acceptance] = []
        for source in sources:
            if source.tree is not None:
                acceptances.extend(self._module(source, resolver.constants(resolver.dotted(source.rel))))
        return acceptances

    def _module(self, source: SourceFile, constants: ModuleConstants) -> list[Acceptance]:
        # Index each site, then judge every range-checked value once per class (fields) or per function (parameters).
        collector = GuardCollector()
        indexed = [(site, SubjectIndex(site, constants), collector.raise_guards(site.function)) for site in ValidationSiteFinder().find(source)]
        acceptances: list[Acceptance] = []
        seen: set[tuple[int, str]] = set()
        for site, index, guards in indexed:
            for guard in guards:
                for key in collector.range_keys(index, guard):
                    canonical = index.canonical(key)
                    scope = id(site.owner) if canonical.startswith("self:") and site.owner is not None else id(site.function)
                    if (scope, canonical) not in seen:
                        seen.add((scope, canonical))
                        acceptances.extend(self._judge(site, index, guard, key, indexed))
        return acceptances

    @staticmethod
    def _judge(site: ValidationSite, index: SubjectIndex, trigger: ast.If, key: str, indexed: list[tuple[ValidationSite, SubjectIndex, list[ast.If]]]) -> list[Acceptance]:
        # Pool the guards that read the value (class-wide for fields), then keep the probes none of them rejects.
        canonical = index.canonical(key)
        shared = canonical.startswith("self:") and site.owner is not None
        members = [(other_site, other_index, other_index.keys_for(canonical) if shared else frozenset({key}), guards) for other_site, other_index, guards in indexed if other_site is site or (shared and other_site.owner is site.owner)]
        entries = tuple(PoolEntry(index=other_index, guard=guard, keys=keys) for _, other_index, keys, guards in members for guard in guards if ProbeEvaluator(other_index, keys, PROBES[0], True).reads_subject(guard.test))
        pool = GuardPool(entries=entries, functions=tuple((other_index, other_site.function, keys) for other_site, other_index, keys, _ in members))
        judge = ProbeJudge()
        if judge.delegated(pool):
            return []
        casts = {resolved[1] for entry in entries for node in ast.walk(entry.guard.test) if isinstance(node, ast.expr) and (resolved := entry.index.resolve(node)) is not None and resolved[0] in entry.keys and resolved[1]}
        subject = index.subject(key, [entry.guard for entry in entries], casts)
        if subject is None:
            return []
        accepted = judge.accepted(pool)
        operand = next((ast.unparse(node) for node in ast.walk(trigger.test) if isinstance(node, ast.expr) and index.resolve(node) == (key, "")), subject.display)
        return [Acceptance(site=site, subject=subject, operand=operand, line=trigger.lineno, guard=ast.unparse(trigger.test), accepted=accepted)] if accepted else []


class FiniteNumericGuardsRule(Rule):
    """Requires construction-time numeric range checks to reject True, NaN, and both infinities first."""

    id = "C006"
    name = "finite-numeric-guards"
    severity = "blocking"
    summary = "A numeric range check in a constructor, __post_init__, or validator helper must reject bool, NaN, and infinities before it compares. Python's bool is an int, so True passes as 1, and NaN makes every ordered comparison False, so `value <= 0` lets it through. A finding names the value, the guard, and the exact probe values that pass every check on it today."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Convert each proven acceptance into a stable finding anchored at the value's first range guard.
        return [self._finding(item) for item in FiniteNumericGuardAnalyzer().analyze(catalog)]

    def explain(self, finding: Finding) -> Diagnostic:
        # Spell out what passes, why that disables the guardrail, and the exact type-first repair for this kind.
        extra = finding.extra
        accepted = extra["accepted"].split(", ")
        return Diagnostic(
            what_happened=f"{finding.location()} `{finding.symbol}` range-checks `{extra['subject']}` (annotated `{extra['annotation']}`) with `{extra['guard']}`{self._read_as(extra)}, but no guard on that value rejects {self._listing(accepted)}. {self._consequences(accepted, extra['kind'], extra['operand'])}",
            why_blocked="A boolean budget silently becomes 1, and a NaN or infinite limit, timeout, or cost stops limiting anything, so the guardrail a caller configured is never enforced and nothing fails until a run misbehaves. This exact gap needed seven consecutive merged fixes, PRs #523 through #529 (loop budgets, operation costs, middleware limits, model usage, tool-call timeouts, retry backoff, and the fallback switch), each found by a probe rather than by the gate. The contract is written in tests/features/sdk_loop_settings/FEATURE.md ('True is not an integer budget ... NaN and infinities are not finite timeouts') and tests/features/sdk_middleware_limits/FEATURE.md, and AGENTS.md (Use Validated Dataclasses) requires every record to check types and ranges when it is created.",
            how_to_fix=self._repair(finding),
            correct_examples=("vidbyte/agents/settings/loop.py:110 - AgentLoopSettings._validate_timeout_seconds rejects bool, non-numbers, and non-finite values before `<= 0.0` (PR #523).", "vidbyte/middleware/builtins/limit_validation.py:19 and :27 - positive_integer and positive_real put the type and finiteness checks first (PR #525).", "vidbyte/workflows/contracts.py:117 - RetryPolicy.__post_init__ checks isinstance, excludes bool, and calls isfinite on every float field.", "vidbyte/lib/dataclasses/trace.py:216 - TraceOption.__post_init__ proves an int (not bool) before its 1-3 range."),
            will_not_work=("Adding only `math.isfinite(x)`: True is finite, so it still passes as 1. Exclude bool explicitly.", "Checking `isinstance(x, (int, float))` or `isinstance(x, int)` without `not isinstance(x, bool)`: bool is a subclass of int and passes both.", "Casting first with `float(x)` or `int(x)`: float(True) is 1.0, int(2.9) is 2, and float('nan') stays NaN, so the cast hides the bad input instead of rejecting it.", "Moving the check into an `assert`, which disappears under `python -O`.", "Raising C006's baseline in lint/baseline.json: every finding is a guard that accepts input the SDK contract says must fail."),
            verify=f"{self.verify_command()} && python -m pytest tests/features -q",
        )

    @staticmethod
    def _finding(acceptance: Acceptance) -> Finding:
        # Stores every fact the diagnostic quotes, so explain() never re-reads source.
        site = acceptance.site
        return Finding(rule_id=FiniteNumericGuardsRule.id, rel_path=site.source.rel, line=acceptance.line, source_line=site.source.line_at(acceptance.line), symbol=site.symbol(), extra={"subject": acceptance.subject.display, "operand": acceptance.operand, "annotation": acceptance.subject.annotation, "kind": acceptance.subject.kind, "guard": acceptance.guard if len(acceptance.guard) <= _GUARD_TEXT_LIMIT else f"{acceptance.guard[:_GUARD_TEXT_LIMIT]}...", "accepted": ", ".join(acceptance.accepted)})

    @staticmethod
    def _listing(labels: list[str]) -> str:
        # Renders 'True', 'True and float("nan")', or 'True, float("nan"), and float("inf")'.
        quoted = [f"`{label}`" for label in labels]
        return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"

    @staticmethod
    def _read_as(extra: dict[str, str]) -> str:
        # Names the local or expression the guard actually reads when it differs from the subject.
        return f" (read there as `{extra['operand']}`)" if extra["operand"] != extra["subject"] else ""

    @staticmethod
    def _consequences(labels: list[str], kind: str, value: str) -> str:
        # One sentence per accepted probe, in the order the probes are listed.
        sentences = {"True": "`True` is a subclass of int, so it passes as 1.", "float('nan')": "`float('nan')` makes every <, <=, > and >= comparison False, so the range check never fires.", "float('inf')": "`float('inf')` clears a lower bound and turns the limit into no limit at all.", "float('-inf')": "`float('-inf')` clears an upper bound and is accepted as a real number."}
        text = " ".join(sentences[label] for label in labels)
        float_slips = any(label != "True" for label in labels)
        return f"{text} Nothing checks `isinstance({value}, int)`, so a float reaches an int-typed value." if kind == _INT and float_slips else text

    @staticmethod
    def _repair(finding: Finding) -> str:
        # Gives the exact type-first condition for int or real values, then the shared-validator and test steps.
        extra = finding.extra
        value = extra["operand"]
        label = extra["subject"].removeprefix("self.").strip("{}").split(", ")[0]
        if extra["kind"] == _INT:
            condition = f"isinstance({value}, bool) or not isinstance({value}, int) or <the existing range test>"
            outcome = "This rejects True, fractions, NaN, and both infinities, and keeps every valid integer."
            expected = "an integer (not a bool)"
        else:
            condition = f"isinstance({value}, bool) or not isinstance({value}, (int, float)) or not math.isfinite({value}) or <the existing range test>"
            outcome = "This rejects True, strings, NaN, and both infinities, and keeps every valid finite number. Add `import math` if the module lacks it."
            expected = "a finite number"
        return "\n".join((
            f"1. In `{finding.symbol}` ({finding.location()}), put the type check in the same condition as the range check, ahead of it, so it cannot be skipped: `if {condition}: raise ...`. {outcome}",
            f"2. Keep the existing error type and range, and make the message name the field and both requirements, for example \"{label} must be {expected} within the allowed range\".",
            "3. If this check repeats a primitive that exists elsewhere (C008 lists the copies), call the shared validator in vidbyte/lib/dataclasses/validation.py instead of writing the condition inline; until that module exists, vidbyte/middleware/builtins/limit_validation.py shows the strict shape.",
            "4. Add True, float('nan'), and float('inf') to the feature's contract test (for example tests/features/sdk_loop_settings/test_contract.py or tests/features/sdk_middleware_limits/test_middleware_limit_contract.py) and assert each one raises.",
        ))


RULE = FiniteNumericGuardsRule()
