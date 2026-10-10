"""FILE: lint/rules/c008_shared_validator_owner.py

PURPOSE: Detect primitive validators (positive int, finite number, strict bool, timeout, limit, temperature) defined outside the one shared validator module.
ROLE IN CODEBASE: Enforces C008 so each primitive check has one owner instead of drifting copies in every package.
ARCHITECTURE NOTE: Static AST. A definition is a primitive validator when its name says so and its own body performs the check; delegating wrappers, lenient parsers, bool predicates, tool-call argument normalizers, and the canonical module are not reported. Copies are grouped by the shared validator that should replace them.
FUNCTION INVENTORY: ValidatorNameGrammar parses names; InlineCheckDetector inspects bodies; ToolArgumentBoundary spots tool-call argument normalizers; SharedValidatorCatalog names the replacement; PrimitiveValidatorAnalyzer coordinates; SharedValidatorOwnerRule reports.
COMMON MODIFICATION PATTERNS: Add a primitive token or verb to the grammar together with its shared validator name, then rerun C008 and its scratch fixtures.
WHAT NOT TO DO: Do not import SDK modules, create the shared module from the rule, or exempt a package-private copy because it is strict.
KNOWN EDGE CASES: vidbyte/lib/dataclasses/validation.py does not exist yet; the diagnostic names it as the canonical home. Class validators whose method is a bare verb (JevCount.require) do not match the grammar. A parser that returns None for a wrong type is a lenient reader, not a validator. Tool-call arguments are model-written JSON, so their normalizers accept "5" on purpose and are not config validators.
RELATED DOCS: docs/design/lint-sdk-settings-validation.md; AGENTS.md (Placement Rules: dataclasses go in vidbyte/lib/dataclasses/)
TESTS: python lint/run.py --rule C008; fixture and mutation results are recorded in the S1 pull request body.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

CANONICAL_MODULE = "vidbyte/lib/dataclasses/validation.py"
_VERBS = frozenset({"require", "validate", "validated", "ensure", "normalize", "coerce", "check", "resolve", "is"})
_QUALIFIERS = frozenset({"strict", "optional"})
_PRIMITIVES = {"positive": "positive", "at_least_one": "positive", "non_negative": "non_negative", "nonnegative": "non_negative", "finite": "finite", "bool": "bool", "boolean": "bool", "int": "int", "integer": "int", "number": "number", "numeric": "number", "float": "number", "real": "number", "timeout": "timeout", "latency": "latency", "limit": "limit", "budget": "budget", "temperature": "temperature", "probability": "probability"}
_NOUN_LEADS = frozenset({"positive", "non_negative", "nonnegative", "finite", "strict"})
_NOUN_TAILS = frozenset({"int", "integer", "float", "real", "number", "numeric", "bool", "boolean"})
_TYPE_NAMES = frozenset({"bool", "int", "float", "Real", "Number"})
_FINITE_CALLS = frozenset({"isfinite", "isnan", "isinf"})
_REAL_ANNOTATION = re.compile(r"\b(float|Real|Number)\b")
_ORDERED = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_SHARED_NAMES = {"bool": "StrictBool", "int": "StrictInt", "positive_int": "PositiveInt", "non_negative_int": "NonNegativeInt", "positive_number": "PositiveFinite", "positive_finite": "PositiveFinite", "positive_finite_number": "PositiveFinite", "timeout": "PositiveFinite", "latency": "NonNegativeFinite", "non_negative_number": "NonNegativeFinite", "non_negative_finite": "NonNegativeFinite", "number": "FiniteNumber", "finite": "FiniteNumber", "finite_number": "FiniteNumber", "limit": "BoundedInt", "temperature": "Temperature", "probability": "Probability"}
_UNTYPED_FAMILIES = frozenset({"positive", "non_negative"})
_SHOWN_SITES = 10
_TOOL_BASE = "BaseTool"
_TOOL_PARAMETER = "ToolParameter"
_ARGUMENT_VERBS = frozenset({"coerce", "resolve", "normalize"})
_CONSTRUCTORS = frozenset({"__init__", "__post_init__"})
_BOOLEAN_CALLS = frozenset({"isinstance", "issubclass", "callable", "hasattr", "isfinite", "isnan", "isinf", "all", "any", "bool"})


def _is_zero(node: ast.expr) -> bool:
    # The literal 0 or 0.0 (not False).
    return isinstance(node, ast.Constant) and not isinstance(node.value, bool) and isinstance(node.value, (int, float)) and node.value == 0


@dataclass(frozen=True, slots=True)
class PrimitiveValidator:
    """One function definition that performs a primitive check itself, outside the shared module."""

    source: SourceFile
    function: ast.FunctionDef | ast.AsyncFunctionDef
    owner: str
    family: str
    shared: str
    check: str

    def __post_init__(self) -> None:
        # The shared name groups copies of the same check; an empty one would group unrelated helpers.
        if not self.family or not self.shared or not self.check:
            raise ValueError(f"PrimitiveValidator needs a family, a shared validator name, and the inline check, got {self.family!r}/{self.shared!r}/{self.check!r}.")

    def symbol(self) -> str:
        # Renders Class.method, or the bare function name.
        return f"{self.owner}.{self.function.name}" if self.owner else self.function.name

    def site(self) -> str:
        # Renders path:line (symbol) for the other-sites list.
        return f"{self.source.rel}:{self.function.lineno} ({self.symbol()})"


class ValidatorNameGrammar:
    """Reads a function name as `<verb>_<primitive...>` or `<lead>_<primitive>` and returns its primitive family."""

    def family(self, name: str) -> str:
        # Returns the normalized primitive family, or an empty string when the name does not name a primitive check.
        words = self.words(name)
        if words and words[0] in _VERBS:
            return self._primitive_run(words[1:])
        if len(words) == 2 and words[0] in _NOUN_LEADS and words[1] in _NOUN_TAILS:
            return self._primitive_run(words)
        return ""

    @staticmethod
    def words(name: str) -> list[str]:
        # Splits on underscores and re-joins non_negative and at_least_one so each reads as one primitive word.
        joined: list[str] = []
        for word in (item for item in name.lower().split("_") if item):
            if joined and joined[-1] == "non" and word == "negative":
                joined[-1] = "non_negative"
            elif joined[-2:] == ["at", "least"] and word == "one":
                joined[-2:] = ["at_least_one"]
            else:
                joined.append(word)
        return joined

    @staticmethod
    def _primitive_run(words: list[str]) -> str:
        # The family is every primitive word after optional qualifiers, in order, so `_validate_retry_budget` reads as budget.
        while words and words[0] in _QUALIFIERS:
            words = words[1:]
        return "_".join(dict.fromkeys(_PRIMITIVES[word] for word in words if word in _PRIMITIVES))


class InlineCheckDetector:
    """Finds the primitive check a function body performs itself, ignoring nested functions."""

    def inline_check(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        # Returns the first isinstance/isfinite/ordered-comparison check on an input, or '' for a wrapper, lenient parser, or bool predicate.
        if not self._rejects_or_answers(function) or self._predicate(function):
            return ""
        inputs = self._inputs(function)
        if self._lenient(function, inputs):
            return ""
        for node in self.body_nodes(function):
            if isinstance(node, ast.Call) and self._is_type_check(node, inputs):
                return ast.unparse(node)
            if isinstance(node, ast.Compare) and self._is_range_check(node, inputs):
                return ast.unparse(node)
        return ""

    @staticmethod
    def body_nodes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
        # Walks the function body without descending into nested functions, lambdas, or classes.
        nodes: list[ast.AST] = []
        stack: list[ast.AST] = list(function.body)
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            nodes.append(node)
            stack.extend(ast.iter_child_nodes(node))
        return sorted(nodes, key=lambda item: (getattr(item, "lineno", 0), getattr(item, "col_offset", 0)))

    def _rejects_or_answers(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        # A validator raises on bad input or returns a verdict or value; a function that does neither is not one.
        return any(isinstance(node, (ast.Raise, ast.Return)) for node in self.body_nodes(function))

    def _predicate(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        # `_is_integer_index(value) -> bool` answers a question and never raises; callers branch on it, so it is not a validator.
        nodes = self.body_nodes(function)
        returns = [node for node in nodes if isinstance(node, ast.Return)]
        return bool(returns) and not any(isinstance(node, ast.Raise) for node in nodes) and all(node.value is not None and self._boolean(node.value) for node in returns)

    @classmethod
    def _boolean(cls, node: ast.expr) -> bool:
        # A comparison, `not`, a bool constant, a bool-returning builtin call, or an and/or of those.
        if isinstance(node, ast.BoolOp):
            return all(cls._boolean(value) for value in node.values)
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (node.func.id if isinstance(node.func, ast.Name) else "")
            return name in _BOOLEAN_CALLS
        if isinstance(node, ast.Constant):
            return isinstance(node.value, bool)
        return isinstance(node, ast.Compare) or (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not))

    def _lenient(self, function: ast.FunctionDef | ast.AsyncFunctionDef, inputs: set[str]) -> bool:
        # `if isinstance(value, bool): return None` reads untrusted data leniently; it is a parser, not a validator.
        for node in self.body_nodes(function):
            if isinstance(node, ast.If) and len(node.body) == 1 and isinstance(node.body[0], ast.Return) and (node.body[0].value is None or (isinstance(node.body[0].value, ast.Constant) and node.body[0].value.value is None)):
                test = node.test.operand if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not) else node.test
                if isinstance(test, ast.Call) and self._is_type_check(test, inputs):
                    return True
        return False

    @staticmethod
    def _inputs(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        # Parameters (except self/cls) and locals assigned from a parameter or a self attribute are the validated inputs.
        inputs = {item.arg for item in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs] if item.arg not in {"self", "cls"}}
        for node in sorted((item for item in ast.walk(function) if isinstance(item, ast.Assign)), key=lambda item: item.lineno):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                names = {item.id for item in ast.walk(node.value) if isinstance(item, ast.Name)}
                reads_self = any(isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "self" for item in ast.walk(node.value))
                if names & inputs or reads_self:
                    inputs.add(node.targets[0].id)
        return inputs

    @staticmethod
    def _reads_input(node: ast.AST, inputs: set[str]) -> bool:
        # True for an input name, a self attribute, or float()/int() of one.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"float", "int"} and len(node.args) == 1:
            node = node.args[0]
        if isinstance(node, ast.Name):
            return node.id in inputs
        return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self"

    def _is_type_check(self, node: ast.Call, inputs: set[str]) -> bool:
        # isinstance(x, bool/int/float/Real/Number) or math.isfinite/isnan/isinf(x) on an input.
        name = node.func.attr if isinstance(node.func, ast.Attribute) else (node.func.id if isinstance(node.func, ast.Name) else "")
        if not node.args or not self._reads_input(node.args[0], inputs):
            return False
        if name == "isinstance" and len(node.args) == 2:
            types = {item.attr if isinstance(item, ast.Attribute) else item.id for item in ast.walk(node.args[1]) if isinstance(item, (ast.Name, ast.Attribute))}
            return bool(types & _TYPE_NAMES)
        return name in _FINITE_CALLS

    def _is_range_check(self, node: ast.Compare, inputs: set[str]) -> bool:
        # An ordered comparison with an input on one side.
        operands = [node.left, *node.comparators]
        return any(isinstance(op, _ORDERED) and (self._reads_input(left, inputs) or self._reads_input(right, inputs)) for op, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True))


class ToolArgumentBoundary:
    """Recognizes normalizers of model-written tool-call arguments, which accept JSON such as "5" on purpose and are not config validators.

    A function qualifies when a parameter is annotated with ToolParameter (vidbyte/lib/dataclasses/tools.py, the model-facing declaration of one
    tool argument), or when it is a coerce_/resolve_/normalize_ method of a BaseTool subclass (vidbyte/tools/base.py) that the class's own
    __init__/__post_init__ never calls. A method the constructor calls validates developer configuration and stays in scope.
    """

    def __init__(self, catalog: SourceCatalog) -> None:
        # Maps each class name under vidbyte/ to its base names, then closes over BaseTool's transitive subclasses.
        bases: dict[str, set[str]] = {}
        for source in catalog.python_files():
            for node in ast.walk(source.tree) if source.tree is not None else ():
                if isinstance(node, ast.ClassDef):
                    bases.setdefault(node.name, set()).update(self._name(item) for item in node.bases)
        tools = {_TOOL_BASE}
        grew = True
        while grew:
            added = {name for name, parents in bases.items() if name not in tools and parents & tools}
            tools |= added
            grew = bool(added)
        self._tools = frozenset(tools)

    def exempt(self, owner: ast.ClassDef | None, function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        # True for a ToolParameter-typed normalizer or a tool method that only the tool-call path can reach.
        annotations = [item.annotation for item in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs] if item.annotation is not None]
        if any(re.search(rf"\b{_TOOL_PARAMETER}\b", ast.unparse(item)) for item in annotations):
            return True
        verb = ValidatorNameGrammar.words(function.name)[:1]
        if owner is None or owner.name not in self._tools or not verb or verb[0] not in _ARGUMENT_VERBS:
            return False
        return not any(self._calls(item, function.name) for item in owner.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in _CONSTRUCTORS)

    @staticmethod
    def _calls(constructor: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
        # True when the constructor calls the method as `self.name(...)` or `Class.name(...)`; a bare `name(...)` is a module function.
        return any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name for node in ast.walk(constructor))

    @staticmethod
    def _name(node: ast.expr) -> str:
        # The class name a base expression refers to: `BaseTool`, `tools.BaseTool`, or `Generic[...]`'s `Generic`.
        node = node.value if isinstance(node, ast.Subscript) else node
        return node.attr if isinstance(node, ast.Attribute) else (node.id if isinstance(node, ast.Name) else "")


class SharedValidatorCatalog:
    """Names the shared validator in vidbyte/lib/dataclasses/validation.py that replaces one family of copies."""

    @staticmethod
    def shared_name(family: str, function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        # A budget's sign comes from its own check; an untyped family (positive, non_negative) then takes int or finite-number from the annotations.
        if family == "budget":
            family = SharedValidatorCatalog._budget_sign(function)
        if family in _UNTYPED_FAMILIES:
            annotations = " ".join(ast.unparse(item.annotation) for item in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs] if item.annotation is not None)
            family = f"{family}_number" if _REAL_ANNOTATION.search(annotations) else f"{family}_int"
        return _SHARED_NAMES.get(family, "".join(part.capitalize() for part in family.split("_")))

    @staticmethod
    def _budget_sign(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        # A budget that rejects only negatives (`value < 0`, `0 > value`) is non-negative; one that rejects zero is positive.
        for node in InlineCheckDetector.body_nodes(function):
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                left, right = node.left, node.comparators[0]
                if (isinstance(node.ops[0], ast.Lt) and _is_zero(right) and not _is_zero(left)) or (isinstance(node.ops[0], ast.Gt) and _is_zero(left) and not _is_zero(right)):
                    return "non_negative"
        return "positive"


class PrimitiveValidatorAnalyzer:
    """Finds every primitive-validator definition outside the shared validator module."""

    def analyze(self, catalog: SourceCatalog) -> list[PrimitiveValidator]:
        # Read each production module once, keep validator-named definitions that check inline, and skip the canonical home.
        grammar = ValidatorNameGrammar()
        detector = InlineCheckDetector()
        boundary = ToolArgumentBoundary(catalog)
        found: list[PrimitiveValidator] = []
        for source in catalog.python_files():
            if source.tree is None or source.rel == CANONICAL_MODULE:
                continue
            for owner, function in self._definitions(source.tree):
                family = grammar.family(function.name)
                check = detector.inline_check(function) if family and not boundary.exempt(owner, function) else ""
                if check:
                    found.append(PrimitiveValidator(source=source, function=function, owner=owner.name if owner else "", family=family, shared=SharedValidatorCatalog.shared_name(family, function), check=check))
        return found

    @staticmethod
    def _definitions(tree: ast.Module) -> list[tuple[ast.ClassDef | None, ast.FunctionDef | ast.AsyncFunctionDef]]:
        # Pairs every function with its enclosing class (None for module-level and nested functions).
        methods = [(node, item) for node in ast.walk(tree) if isinstance(node, ast.ClassDef) for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
        claimed = {id(function) for _, function in methods}
        return [*methods, *((None, node) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and id(node) not in claimed)]


class SharedValidatorOwnerRule(Rule):
    """Requires primitive validators to live in vidbyte/lib/dataclasses/validation.py instead of module-local copies."""

    id = "C008"
    name = "shared-validator-owner"
    severity = "blocking"
    summary = "A function whose name says it validates a primitive (positive int, finite number, bool, timeout, limit, temperature) and whose body performs that check belongs in the shared module vidbyte/lib/dataclasses/validation.py, not in a module-local helper. Copies drift: one gains NaN or bool handling while the others keep accepting bad values. The finding names the shared validator to use and every other copy of the same check."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # One finding per copy, each listing the other copies that the same shared validator replaces.
        validators = PrimitiveValidatorAnalyzer().analyze(catalog)
        groups: dict[str, list[PrimitiveValidator]] = {}
        for item in validators:
            groups.setdefault(item.shared, []).append(item)
        return [self._finding(item, [other for other in groups[item.shared] if other is not item]) for item in validators]

    def explain(self, finding: Finding) -> Diagnostic:
        # Name the shared validator, every copy it replaces, and how to migrate without changing a public error type.
        extra = finding.extra
        shared = extra["shared"]
        count = int(extra["other_count"])
        if count:
            others = f" The same check is also defined in {count} other place{'s' if count > 1 else ''}: {extra['other_sites']}."
        else:
            others = " It is the only copy of this check today, so moving it now gives the next caller one owner instead of a second copy."
        return Diagnostic(
            what_happened=f"{finding.location()} defines `{finding.symbol}`, a private {self._family_text(extra['family'])} validator that performs the check itself (starting with `{extra['check']}`). Primitive validators belong in {CANONICAL_MODULE} as `{shared}`.{others}",
            why_blocked="Copies of one primitive check drift apart. The #523-#529 fix series had to visit each module separately because every package carried its own positive-number or timeout helper: when one copy gained bool or NaN handling (#527, #528), the others kept accepting True and float('nan'). Today the five `_validate_positive_int` copies in vidbyte/lib/dataclasses/model_configs.py accept both, while vidbyte/middleware/builtins/limit_validation.py rejects them. AGENTS.md (Use Validated Dataclasses; Placement Rules) puts validated dataclasses in vidbyte/lib/dataclasses/<domain>.py, and the strict-config-dataclasses field guide (PR #352) asks that a primitive validated in more than one place get its own frozen dataclass.",
            how_to_fix="\n".join((
                f"1. If {CANONICAL_MODULE} exists, import `{shared}` from it. If it does not exist yet, create it with `{shared}` as a `@dataclass(frozen=True, slots=True)` whose `__post_init__` {self._contract(shared)} and raises `ConfigurationError` naming the field; model it on `PauseDuration` (vidbyte/lib/dataclasses/agents.py:132) and expose a `require(value, *, field_name)` helper the way `JevCount.require` does (vidbyte/lib/dataclasses/jev.py:3977).",
                f"2. Replace the body of `{finding.symbol}` with a call to `{shared}`, or delete the helper and call `{shared}` at each of its call sites.",
                "3. Keep each public exception type: if this site promised ValueError or a domain error, let the shared validator take the error class to raise, or re-raise that type `from` the ConfigurationError. Do not change a public exception type silently.",
                f"4. Migrate the {count} other cop{'ies' if count > 1 else 'y'} listed above in the same pull request, or in a follow-up that names them, so the check ends with one owner. Then rerun C008, C006, and C002." if count else f"4. Rerun C008, C006, and C002. Any later need for this check imports `{shared}` instead of defining another helper.",
            )),
            correct_examples=("vidbyte/lib/dataclasses/agents.py:132 - PauseDuration is a frozen, slotted dataclass that owns one primitive (a non-negative whole-number delay) and rejects bool first.", "vidbyte/lib/dataclasses/jev.py:3974 - JevCount.require is one shared count validator that every JEV run-brief record calls instead of copying the check.", "vidbyte/middleware/builtins/limit_validation.py:19 and :27 - positive_integer and positive_real replaced per-middleware copies with one strict owner for the middleware package (PR #525); C008 asks for the same consolidation SDK-wide."),
            will_not_work=("Renaming the helper so the grammar no longer matches: the duplicate check is still there and still drifts.", "Moving the copy into another package-local module such as a new `_validators.py`: that is still a second owner outside vidbyte/lib/dataclasses/validation.py.", "Making only this copy strict: every other copy of the check keeps its old behavior, which is the drift this rule exists to stop.", "Raising C008's baseline in lint/baseline.json: each finding is a copy that a future fix will miss."),
            verify=f"{self.verify_command()} && python lint/run.py --rule C006 && python lint/run.py --rule C002",
        )

    @staticmethod
    def _contract(shared: str) -> str:
        # What the shared validator must reject, by kind: exact bool, non-bool int, or finite real number.
        if shared == "StrictBool":
            return "accepts only the exact values True and False (no 0, 1, or strings)"
        if shared.endswith("Int"):
            return "rejects bool and every non-int value before its range check"
        return "rejects bool, non-numbers, NaN, and both infinities before its range check"

    @staticmethod
    def _family_text(family: str) -> str:
        # Renders positive_int as "positive int" for prose.
        return family.replace("_", " ").replace("non negative", "non-negative")

    @staticmethod
    def _finding(item: PrimitiveValidator, others: list[PrimitiveValidator]) -> Finding:
        # Stores every fact the diagnostic quotes, including a bounded list of the other copies.
        sites = [other.site() for other in sorted(others, key=lambda other: (other.source.rel, other.function.lineno))]
        shown = sites[:_SHOWN_SITES]
        remainder = len(sites) - len(shown)
        listing = "; ".join(shown) + (f"; and {remainder} more (run `python lint/run.py --rule C008 --format json` for all)" if remainder else "")
        return Finding(rule_id=SharedValidatorOwnerRule.id, rel_path=item.source.rel, line=item.function.lineno, source_line=item.source.line_at(item.function.lineno), symbol=item.symbol(), extra={"family": item.family, "shared": item.shared, "check": item.check, "other_count": str(len(sites)), "other_sites": listing})


RULE = SharedValidatorOwnerRule()
