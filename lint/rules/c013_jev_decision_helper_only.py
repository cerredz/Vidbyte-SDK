"""FILE: lint/rules/c013_jev_decision_helper_only.py

PURPOSE: Detect agents-layer code that asks Jev without DecisionModelHelper, decides a Jev answer against a threshold inline, or awaits one Jev request per loop iteration.
ROLE IN CODEBASE: Enforces C013 so Jev request execution and answer scoring keep the one canonical path in vidbyte/lib/jev/decision.py that PR #477 asked for.
ARCHITECTURE NOTE: Pure AST analysis of vidbyte/agents/**. AnswerFlow is a flow-insensitive, class-local taint pass: a value read from `.probabilities`, returned by `score_noul`, or returned by a lib Jev projection method (learned from vidbyte/lib/dataclasses/jev.py) is answer-derived, and derivation follows assignments, loop and comprehension targets, containers, arithmetic, calls, self attributes, and same-class returns. RequestLoopScan learns which same-class methods send a helper request.
FUNCTION INVENTORY: HelperContract checks the helper vocabulary and learns projections; AnswerFlow decides answer-derived expressions; ThresholdScan, RunnerScan, and RequestLoopScan find each kind; JevDecisionHelperOnlyRule reports and explains.
COMMON MODIFICATION PATTERNS: When DecisionModelHelper gains a method that returns a score, add it to _SCORE_SOURCES; one that returns a pass/fail verdict goes in _OPAQUE_CALLS. A new lib Jev record method that projects probabilities is learned automatically.
WHAT NOT TO DO: Do not import vidbyte, report a comparison between two answer-derived values (that ranks answers, it does not threshold them), or report coroutines created in a loop and awaited together.
KNOWN EDGE CASES: Taint does not cross classes or modules, so a score passed in from another class is not traced (an under-report, never a false positive). Tuple unpacking taints every target. The lib layer (vidbyte/lib/jev/) is the helper itself and is out of scope. A missing helper method fails closed.
RELATED DOCS: docs/design/lint-sdk-jev-packaging-async.md; field-guide/vidbyte-sdk/jev-capability-layout.md; skills/asking-jev-questions/SKILL.md (strategies 11 and 24, T15).
TESTS: python lint/run.py --rule C013; fixture and mutation results are recorded in the S3 pull request body.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

SCOPE_PREFIX = "vidbyte/agents/"
PROJECTION_FILE = "vidbyte/lib/dataclasses/jev.py"
HELPER_FILE = "vidbyte/lib/jev/decision.py"
HELPER_CLASS = "DecisionModelHelper"
RUNNER_CLASS = "DecisionModelRunner"
RUNNER_MODULE = "vidbyte.lib.runners.decision"
_HELPER_METHODS = ("arun", "score_noul", "noul_passes")
_DIRECT = "direct-runner"
_INLINE = "inline-threshold"
_PER_ITEM = "per-item-request"
_KINDS = (_DIRECT, _INLINE, _PER_ITEM)
_ANSWER_ATTRIBUTE = "probabilities"
_SCORE_SOURCES = frozenset({"score_noul"})
# These calls return a verdict, a size, a type test, a key view, or text, never the answer value itself.
_OPAQUE_CALLS = frozenset({"noul_passes", "len", "isinstance", "issubclass", "bool", "str", "repr", "format", "id", "type", "hash", "callable", "hasattr", "keys"})
_COLLECTORS = frozenset({"append", "extend", "add", "update", "insert", "setdefault", "appendleft"})
# These calls return a value computed from their positional inputs, so an answer value stays an answer value.
_VALUE_CALLS = frozenset({"max", "min", "sum", "fsum", "fmean", "mean", "median", "float", "round", "abs", "sorted", "list", "tuple", "set", "frozenset", "reversed", "iter", "next", "dict", "zip", "enumerate"})
_ANSWER = "*"
_WHOLE = frozenset({_ANSWER})
_CLEAN: frozenset[str] = frozenset()
_NO_LOCALS: Mapping[str, frozenset[str]] = MappingProxyType({})
_ORDERING = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True, slots=True)
class Origin:
    """Where a name or attribute first became answer-derived, quoted in the diagnostic."""

    source: str
    line: int

    def __post_init__(self) -> None:
        # The diagnostic quotes both fields, so a blank source or bad line would render a broken sentence.
        if not self.source or self.line < 1:
            raise ValueError(f"Origin needs a source expression and a positive line, got {self.source!r} at {self.line}.")


@dataclass(frozen=True, slots=True)
class JevBypass:
    """One place where agents-layer code asks or decides Jev outside DecisionModelHelper."""

    kind: str
    line: int
    symbol: str
    code: str
    facts: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The kind selects the repair text and the code is quoted in every message.
        if self.kind not in _KINDS:
            raise ValueError(f"JevBypass.kind must be one of {_KINDS}, got {self.kind!r}.")
        if self.line < 1 or not self.symbol or not self.code:
            raise ValueError(f"JevBypass needs a positive line, a symbol, and code, got {self.line}/{self.symbol!r}/{self.code!r}.")


class HelperContract:
    """Confirms the helper vocabulary this rule recommends exists and learns lib projections over probabilities."""

    @staticmethod
    def require_helper(files: dict[str, SourceFile]) -> None:
        # Fails closed when DecisionModelHelper or one of its methods moved, so the repair text never names a missing API.
        source = files.get(HELPER_FILE)
        tree = None if source is None else source.tree
        helper = None if tree is None else next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == HELPER_CLASS), None)
        methods = set() if helper is None else {node.name for node in helper.body if isinstance(node, _FUNCTIONS)}
        missing = [name for name in _HELPER_METHODS if name not in methods]
        if missing:
            raise RuntimeError(f"C013 expects {HELPER_CLASS}.{', '.join(missing)} in {HELPER_FILE}; update the rule's helper vocabulary if the helper moved or was renamed.")

    @staticmethod
    def projections(files: dict[str, SourceFile]) -> frozenset[str]:
        # Public record methods in the lib Jev dataclasses whose return value reads `.probabilities`, such as JevPresetResult.yes().
        source = files.get(PROJECTION_FILE)
        if source is None or source.tree is None:
            raise RuntimeError(f"C013 requires the tracked, parsable file {PROJECTION_FILE} to learn which record methods project Jev probabilities.")
        names: set[str] = set()
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for method in (item for item in node.body if isinstance(item, _FUNCTIONS) and not item.name.startswith("_")):
                returns = (item.value for item in ast.walk(method) if isinstance(item, ast.Return) and item.value is not None)
                if any(isinstance(part, ast.Attribute) and part.attr == _ANSWER_ATTRIBUTE for value in returns for part in ast.walk(value)):
                    names.add(method.name)
        if not names:
            raise RuntimeError(f"C013 found no record method in {PROJECTION_FILE} that returns `.probabilities` values (JevPresetResult.yes() was expected); update the rule if the projections moved.")
        return frozenset(names)


class AnswerFlow:
    """Decides which expressions of one module carry a Jev answer probability or score.

    A taint is a frozenset of strings. Empty is clean, {"*"} is an answer value or a container of answer values, and a set of
    field names is a record whose named fields hold answer values, such as a result built with `score=verdict.score`.
    """

    def __init__(self, tree: ast.Module, projections: frozenset[str]) -> None:
        # Learns answer-derived locals, self attributes, and returning methods to a fixpoint before any query.
        self.projections = projections
        self.functions = tuple(owned_functions(tree))
        self.names: dict[ast.AST, dict[str, frozenset[str]]] = {function: {} for _, function in self.functions}
        self.attributes: dict[str, dict[str, frozenset[str]]] = {}
        self.returns: dict[str, dict[str, frozenset[str]]] = {}
        self.origins: dict[tuple[str, str], Origin] = {}
        changed = True
        while changed:
            changed = False
            for owner, function in self.functions:
                for node in ast.walk(function):
                    changed = self._absorb(owner, function, node) or changed

    def derived(self, node: ast.expr | None, owner: str, function: ast.AST, local: Mapping[str, frozenset[str]] = _NO_LOCALS) -> bool:
        # True when the expression's value is a Jev answer probability or score, not merely a record holding one.
        return _ANSWER in self.taint(node, owner, function, local)

    def taint(self, node: ast.expr | None, owner: str, function: ast.AST, local: Mapping[str, frozenset[str]] = _NO_LOCALS) -> frozenset[str]:
        # The taint of one expression, given the function's learned names and any comprehension-local names.
        if node is None or isinstance(node, (ast.Compare, ast.JoinedStr, ast.Constant, ast.Lambda)):
            return _CLEAN
        if isinstance(node, ast.Name):
            return local[node.id] if node.id in local else self.names[function].get(node.id, _CLEAN)
        if isinstance(node, ast.Attribute):
            return self._attribute_taint(node, owner, function, local)
        if isinstance(node, ast.Call):
            return self._call_taint(node, owner, function, local)
        if isinstance(node, _COMPREHENSIONS):
            inner = self.comprehension_names(node, owner, function, local)
            parts = (node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)
            return join(*(self.taint(part, owner, function, inner) for part in parts))
        if isinstance(node, (ast.BinOp, ast.UnaryOp)):
            # Arithmetic yields a number, so only an answer value (not a record) stays an answer value.
            operands = (node.left, node.right) if isinstance(node, ast.BinOp) else (node.operand,)
            return _WHOLE if any(self.derived(item, owner, function, local) for item in operands) else _CLEAN
        if isinstance(node, ast.Dict):
            return join(*(self.taint(value, owner, function, local) for value in node.values))
        if isinstance(node, ast.IfExp):
            return join(self.taint(node.body, owner, function, local), self.taint(node.orelse, owner, function, local))
        if isinstance(node, (ast.Subscript, ast.Await, ast.Starred, ast.NamedExpr)):
            return self.taint(node.value, owner, function, local)
        if isinstance(node, ast.BoolOp):
            return join(*(self.taint(value, owner, function, local) for value in node.values))
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return join(*(self.taint(item, owner, function, local) for item in node.elts))
        return _CLEAN

    def comprehension_names(self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp, owner: str, function: ast.AST, local: Mapping[str, frozenset[str]]) -> dict[str, frozenset[str]]:
        # Comprehension targets take their iterable's taint inside that comprehension only, shadowing outer names.
        inner = dict(local)
        for generator in node.generators:
            taint = self.taint(generator.iter, owner, function, inner)
            inner.update((item.id, taint) for item in ast.walk(generator.target) if isinstance(item, ast.Name))
        return inner

    def origin(self, node: ast.expr, owner: str, function: ast.AST) -> Origin | None:
        # The recorded assignment that made a name or self attribute inside the expression an answer value.
        for part in ast.walk(node):
            if isinstance(part, ast.Name) and (str(id(function)), part.id) in self.origins:
                return self.origins[(str(id(function)), part.id)]
            if isinstance(part, ast.Attribute) and isinstance(part.value, ast.Name) and part.value.id == "self" and (owner, part.attr) in self.origins:
                return self.origins[(owner, part.attr)]
        return None

    def _attribute_taint(self, node: ast.Attribute, owner: str, function: ast.AST, local: Mapping[str, frozenset[str]]) -> frozenset[str]:
        # `.probabilities` is the answer itself; `self.x` uses the class's learned attribute; `record.field` reads a derived field.
        if node.attr == _ANSWER_ATTRIBUTE:
            return _WHOLE
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            return self.attributes.get(owner, {}).get(node.attr, _CLEAN)
        holder = self.taint(node.value, owner, function, local)
        return _WHOLE if _ANSWER in holder or node.attr in holder else _CLEAN

    def _call_taint(self, node: ast.Call, owner: str, function: ast.AST, local: Mapping[str, frozenset[str]]) -> frozenset[str]:
        # Scoring calls and projections are sources, verdicts and sizes are clean, value functions and constructors carry their inputs.
        name = callee_name(node.func)
        if name in _SCORE_SOURCES or (name in self.projections and isinstance(node.func, ast.Attribute)):
            return _WHOLE
        if name in _OPAQUE_CALLS:
            return _CLEAN
        returned = self._returned(node.func, owner)
        if returned is not None:
            return returned
        if isinstance(node.func, ast.Attribute) and self.derived(node.func.value, owner, function, local):
            return _WHOLE
        if name in _VALUE_CALLS:
            return join(*(self.taint(item, owner, function, local) for item in node.args))
        if name[:1].isupper():
            return frozenset(keyword.arg for keyword in node.keywords if keyword.arg and self.derived(keyword.value, owner, function, local))
        return _CLEAN

    def _returned(self, func: ast.expr, owner: str) -> frozenset[str] | None:
        # The learned return taint of `self.method(...)`, `cls.method(...)`, `Owner.method(...)`, or a module function.
        if isinstance(func, ast.Name):
            return self.returns.get("", {}).get(func.id)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in {"self", "cls", owner}:
            return self.returns.get(owner, {}).get(func.attr)
        return None

    def _absorb(self, owner: str, function: ast.AST, node: ast.AST) -> bool:
        # Records one statement's effect: tainted assignment targets, collected containers, and tainted returns.
        if isinstance(node, ast.Assign):
            taint = self.taint(node.value, owner, function)
            return bool(taint) and any([self._mark(owner, function, target, taint, node.value) for target in node.targets])
        if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and node.value is not None:
            taint = self.taint(node.value, owner, function)
            return bool(taint) and self._mark(owner, function, node.target, taint, node.value)
        if isinstance(node, (ast.For, ast.AsyncFor)):
            taint = self.taint(node.iter, owner, function)
            return bool(taint) and self._mark(owner, function, node.target, taint, node.iter)
        if isinstance(node, ast.withitem) and node.optional_vars is not None:
            taint = self.taint(node.context_expr, owner, function)
            return bool(taint) and self._mark(owner, function, node.optional_vars, taint, node.context_expr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _COLLECTORS:
            taint = join(*(self.taint(item, owner, function) for item in node.args))
            return bool(taint) and self._mark(owner, function, node.func.value, taint, node)
        if isinstance(node, ast.Return) and isinstance(function, _FUNCTIONS):
            return self._absorb_return(owner, function, node)
        return False

    def _absorb_return(self, owner: str, function: ast.FunctionDef | ast.AsyncFunctionDef, node: ast.Return) -> bool:
        # Joins one return value's taint into the function's learned return taint.
        taint = self.taint(node.value, owner, function)
        known = self.returns.setdefault(owner, {})
        merged = join(known.get(function.name, _CLEAN), taint)
        if not taint or merged == known.get(function.name):
            return False
        known[function.name] = merged
        return True

    def _mark(self, owner: str, function: ast.AST, target: ast.expr, taint: frozenset[str], value: ast.AST) -> bool:
        # Joins the taint into a name, a self attribute, every element of an unpacking, or the container of a subscript.
        if isinstance(target, (ast.Tuple, ast.List)):
            return any([self._mark(owner, function, item, taint, value) for item in target.elts])
        if isinstance(target, (ast.Starred, ast.Subscript)):
            return self._mark(owner, function, target.value, taint, value)
        if isinstance(target, ast.Name):
            table, key = self.names[function], (str(id(function)), target.id)
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
            table, key = self.attributes.setdefault(owner, {}), (owner, target.attr)
        else:
            return False
        current = table.get(key[1], _CLEAN)
        merged = join(current, taint)
        if merged == current:
            return False
        table[key[1]] = merged
        if _ANSWER in merged and key not in self.origins:
            self.origins[key] = Origin(source=ast.unparse(value), line=getattr(value, "lineno", 1))
        return True


class ThresholdScan:
    """Finds ordered comparisons of an answer value with a value that is not one."""

    def __init__(self, flow: AnswerFlow) -> None:
        # Shares the module's learned answer flow across every function.
        self.flow = flow

    def scan(self) -> Iterator[JevBypass]:
        # One finding per comparison, anchored at its line and named by its owning function.
        for owner, function in self.flow.functions:
            for compare, answer, limit, local, sources in self._comparisons(owner, function, function, _NO_LOCALS, {}):
                facts = {"answer": ast.unparse(answer), "limit": ast.unparse(limit), "origin": self._origin_sentence(answer, owner, function, local, sources)}
                yield JevBypass(kind=_INLINE, line=compare.lineno, symbol=qualified(owner, function), code=ast.unparse(compare), facts=facts)

    def _comparisons(self, owner: str, function: ast.AST, node: ast.AST, local: Mapping[str, frozenset[str]], sources: Mapping[str, ast.expr]) -> Iterator[tuple[ast.Compare, ast.expr, ast.expr, Mapping[str, frozenset[str]], Mapping[str, ast.expr]]]:
        # Walks the function with comprehension-local names in scope and yields the first mixed ordered pair of each comparison.
        if isinstance(node, _COMPREHENSIONS):
            local = self.flow.comprehension_names(node, owner, function, local)
            sources = {**sources, **{item.id: generator.iter for generator in node.generators for item in ast.walk(generator.target) if isinstance(item, ast.Name)}}
        if isinstance(node, ast.Compare):
            operands = (node.left, *node.comparators)
            for operator, left, right in zip(node.ops, operands, operands[1:], strict=False):
                left_derived, right_derived = self.flow.derived(left, owner, function, local), self.flow.derived(right, owner, function, local)
                if isinstance(operator, _ORDERING) and left_derived != right_derived:
                    yield (node, left, right, local, sources) if left_derived else (node, right, left, local, sources)
                    break
        for child in ast.iter_child_nodes(node):
            yield from self._comparisons(owner, function, child, local, sources)

    def _origin_sentence(self, answer: ast.expr, owner: str, function: ast.AST, local: Mapping[str, frozenset[str]], sources: Mapping[str, ast.expr]) -> str:
        # Says where the compared value came from: the answer itself, a comprehension's iterable, or an earlier assignment.
        if any(isinstance(part, ast.Attribute) and part.attr == _ANSWER_ATTRIBUTE for part in ast.walk(answer)) or any(isinstance(part, ast.Call) and callee_name(part.func) in _SCORE_SOURCES for part in ast.walk(answer)):
            return "It reads the Jev answer probability directly."
        for part in (item for item in ast.walk(answer) if isinstance(item, ast.Name)):
            if part.id in sources and _ANSWER in local.get(part.id, _CLEAN):
                iterable = sources[part.id]
                return f"`{part.id}` is drawn from `{ast.unparse(iterable)}` (line {iterable.lineno}), which holds Jev answer probabilities."
            origin = None if part.id in sources else self.flow.origin(part, owner, function)
            if origin is not None:
                return f"`{part.id}` is derived from `{origin.source}` (line {origin.line}), which carries Jev answer probabilities or a score_noul score."
        origin = self.flow.origin(answer, owner, function)
        if origin is None:
            return "It is derived from a Jev answer probability or a score_noul score."
        return f"The value is derived from `{origin.source}` (line {origin.line}), which carries Jev answer probabilities or a score_noul score."


class RunnerScan:
    """Finds direct DecisionModelRunner and provider decision use in the agents layer."""

    @staticmethod
    def scan(tree: ast.Module) -> Iterator[JevBypass]:
        # Imports of the runner and calls that build it or send a decision request without the helper.
        owners = {id(node): qualified(owner, function) for owner, function in owned_functions(tree) for node in ast.walk(function)}
        for node in ast.walk(tree):
            what = RunnerScan._bypass(node)
            if what:
                line = getattr(node, "lineno", 1)
                yield JevBypass(kind=_DIRECT, line=line, symbol=owners.get(id(node), "<module>"), code=ast.unparse(node), facts={"what": what})

    @staticmethod
    def _bypass(node: ast.AST) -> str:
        # A short description of the bypass, or "" when the node is not one.
        if isinstance(node, ast.Import) and any(alias.name == RUNNER_MODULE or alias.name.startswith(f"{RUNNER_MODULE}.") for alias in node.names):
            return f"imports the runner module {RUNNER_MODULE}"
        if isinstance(node, ast.ImportFrom) and (node.module == RUNNER_MODULE or any(alias.name == RUNNER_CLASS for alias in node.names)):
            return f"imports {RUNNER_CLASS} from {node.module}"
        if not isinstance(node, ast.Call):
            return ""
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if name == RUNNER_CLASS:
            return f"constructs {RUNNER_CLASS} directly"
        if name == "run_decision":
            return "calls a provider's run_decision directly"
        if name == "decision" and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "ModelProviders":
            return "builds the decision provider with ModelProviders.decision directly"
        return ""


class RequestLoopScan:
    """Finds a DecisionModelHelper request awaited once per loop iteration or comprehension element."""

    def __init__(self, tree: ast.Module) -> None:
        # Learns helper-bound self attributes per class, then which same-class methods send a request, to a fixpoint.
        self.functions = tuple(owned_functions(tree))
        self.helper_attributes: dict[str, set[str]] = {}
        for owner, function in self.functions:
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and is_helper_construction(node.value):
                    self.helper_attributes.setdefault(owner, set()).update(target.attr for target in node.targets if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self")
        self.senders: dict[str, set[str]] = {}
        changed = True
        while changed:
            changed = False
            for owner, function in self.functions:
                known = self.senders.setdefault(owner, set())
                if function.name not in known and any(self._request(owner, function, node.value) for node in ast.walk(function) if isinstance(node, ast.Await)):
                    known.add(function.name)
                    changed = True

    def scan(self) -> Iterator[JevBypass]:
        # One finding per awaited request (direct or through a same-class sender) inside a loop body or comprehension.
        for owner, function in self.functions:
            for node, loop_line in self._awaits(function, None):
                via = self._request(owner, function, node.value)
                if via and loop_line is not None:
                    facts = {"loop_line": str(loop_line), "via": "" if via == "direct" else via}
                    yield JevBypass(kind=_PER_ITEM, line=node.lineno, symbol=qualified(owner, function), code=ast.unparse(node), facts=facts)

    def _awaits(self, node: ast.AST, loop_line: int | None) -> Iterator[tuple[ast.Await, int | None]]:
        # Yields each await with the line of the innermost enclosing loop or comprehension, stopping at nested scopes.
        for child, inside in self._children(node, loop_line):
            if isinstance(child, _SCOPES):
                continue
            if isinstance(child, ast.Await):
                yield child, inside
            yield from self._awaits(child, inside)

    @staticmethod
    def _children(node: ast.AST, loop_line: int | None) -> list[tuple[ast.AST, int | None]]:
        # Pairs each child with the loop it runs under: a loop body and everything in a comprehension but its first iterable run once per item.
        if isinstance(node, _LOOPS):
            return [(child, node.lineno if child in node.body else loop_line) for child in ast.iter_child_nodes(node)]
        if isinstance(node, _COMPREHENSIONS):
            first = node.generators[0]
            inner = [(child, node.lineno) for child in ast.iter_child_nodes(node) if child is not first]
            return [(first.iter, loop_line), *inner, *((child, node.lineno) for child in ast.iter_child_nodes(first) if child is not first.iter)]
        return [(child, loop_line) for child in ast.iter_child_nodes(node)]

    def _request(self, owner: str, function: ast.AST, value: ast.expr) -> str:
        # "direct" for a helper `.arun(...)`, the method name for a same-class sender, else "".
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
            return ""
        receiver = value.func.value
        if isinstance(receiver, ast.Name) and receiver.id == "self" and value.func.attr in self.senders.get(owner, set()):
            return value.func.attr
        if value.func.attr != "arun":
            return ""
        if is_helper_construction(receiver):
            return "direct"
        if isinstance(receiver, ast.Attribute) and isinstance(receiver.value, ast.Name) and receiver.value.id == "self" and receiver.attr in self.helper_attributes.get(owner, set()):
            return "direct"
        if isinstance(receiver, ast.Name) and any(isinstance(node, ast.Assign) and is_helper_construction(node.value) and any(isinstance(target, ast.Name) and target.id == receiver.id for target in node.targets) for node in ast.walk(function)):
            return "direct"
        return ""


def owned_functions(tree: ast.Module) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    # Module functions (owner "") and the methods of each module-level class; nested functions belong to their parent.
    for node in tree.body:
        if isinstance(node, _FUNCTIONS):
            yield "", node
        if isinstance(node, ast.ClassDef):
            yield from ((node.name, item) for item in node.body if isinstance(item, _FUNCTIONS))


def qualified(owner: str, function: ast.AST) -> str:
    # `Class.method` or the module function name.
    name = function.name if isinstance(function, _FUNCTIONS) else "<module>"
    return f"{owner}.{name}" if owner else name


def join(*taints: frozenset[str]) -> frozenset[str]:
    # The union of several taints; an answer value absorbs any record fields.
    merged = frozenset().union(*taints)
    return _WHOLE if _ANSWER in merged else merged


def callee_name(func: ast.expr) -> str:
    # The final name segment of a call target: `x.y.get` -> "get", `max` -> "max", anything else -> "".
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def is_helper_construction(node: ast.expr | None) -> bool:
    # `DecisionModelHelper(...)`, however it was imported.
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == HELPER_CLASS) or (isinstance(func, ast.Attribute) and func.attr == HELPER_CLASS)


class JevDecisionHelperOnlyRule(Rule):
    """Requires agents-layer code to ask and score Jev only through DecisionModelHelper, one request per decision."""

    id = "C013"
    name = "jev-decision-helper-only"
    severity = "blocking"
    summary = "Code under vidbyte/agents/ asks Jev only through DecisionModelHelper.arun, turns Jev answers into pass or fail only through DecisionModelHelper.score_noul or noul_passes (never by comparing a probability or score with a threshold inline), and never awaits one Jev request per loop iteration: questions that share a state go in one request, and independent per-item requests run concurrently."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Confirm the helper vocabulary, learn the lib projections, then scan every agents-layer module.
        files = {source.rel: source for source in catalog.python_files()}
        HelperContract.require_helper(files)
        projections = HelperContract.projections(files)
        findings: list[Finding] = []
        for source in (item for rel, item in sorted(files.items()) if rel.startswith(SCOPE_PREFIX)):
            if source.tree is None:
                raise RuntimeError(f"C013 cannot parse {source.rel} ({source.parse_error}); fix the syntax error so the Jev helper contract can be checked.")
            # Each kind runs over the same parsed module; the answer flow is learned once per module.
            bypasses = (*RunnerScan.scan(source.tree), *ThresholdScan(AnswerFlow(source.tree, projections)).scan(), *RequestLoopScan(source.tree).scan())
            findings.extend(self._finding(source, item) for item in sorted(bypasses, key=lambda item: (item.line, item.kind)))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Each kind has its own consequence and repair; the shared tail names the helper and the baseline shortcut.
        kind = finding.extra["kind"]
        if kind == _DIRECT:
            return self._explain_direct(finding)
        if kind == _PER_ITEM:
            return self._explain_per_item(finding)
        return self._explain_inline(finding)

    @staticmethod
    def _finding(source: SourceFile, item: JevBypass) -> Finding:
        # Stores every quoted fact, so explain() never re-reads source.
        return Finding(rule_id=JevDecisionHelperOnlyRule.id, rel_path=source.rel, line=item.line, source_line=source.line_at(item.line), symbol=item.symbol, extra={"kind": item.kind, "code": item.code, **item.facts})

    def _explain_inline(self, finding: Finding) -> Diagnostic:
        # An inline threshold is a private second decision rule; the repair moves the comparison into the helper.
        extra = finding.extra
        limit = extra["limit"]
        return Diagnostic(
            what_happened=f"{finding.location()} in {finding.symbol} decides a Jev answer inline: it compares the answer-derived value `{extra['answer']}` with `{limit}` (`{extra['code']}`). {extra['origin']}",
            why_blocked="PR #477 made DecisionModelHelper (vidbyte/lib/jev/decision.py) the one place where Jev answers become pass or fail; the owner's review comment 4130386075 says \"Any logic for thresholds, returning true or false for questions, translating jev model requests to an answer, etc, should be handled by this new file and should be the universarl/canonicaly way\". The field guide records the rule as \"Turn noul answers into pass or fail with `DecisionModelHelper`, never with inline mean-versus-threshold math\" (jev-capability-layout.md). An inline comparison is a second, private decision rule: it skips the helper's inclusive bound, its missing and non-noul answer handling, and its veto, the helper's boundary tests never exercise it, and the next change to how Jev answers are scored silently misses it.",
            how_to_fix="\n".join((
                f"1. For one noul answer, replace the comparison with `DecisionModelHelper.noul_passes(answers, name, {limit})` and act on its three results: True, False, or None when the answer is missing or not noul.",
                f"2. For several noul answers that decide together, call `DecisionModelHelper.score_noul(answers, names, {limit}, veto)` and read `verdict.passed`; when the value is already a score_noul score carried on a result record, carry and read that verdict's `passed` instead of comparing the score again.",
                "3. When the rule is not a mean P(true) over noul answers (a max or min across two questions, a Choice probability sum, a single recall probability), add one static method to DecisionModelHelper in vidbyte/lib/jev/decision.py that takes the answers, the names, and the threshold and returns the verdict, and call it here.",
                "4. Keep the threshold constant in vidbyte/lib/constants/jev.py and pass it in, and keep this caller's fail-open action where it is; only the comparison moves.",
                "5. Cover the boundary (exactly at the threshold, a missing answer, a non-noul answer) in the focused Jev test: tests/test_jev_done.py for done checks, tests/test_jev_preflight.py for gates, tests/test_jev_compute_situations.py for dynamic compute.",
            )),
            correct_examples=(
                "vidbyte/agents/jev/done/run_state.py JevRunState._cumulative_obligations - `DecisionModelHelper.score_noul(answers, identifiers, threshold, threshold)`, then `noul_passes(verdict.answers, identifier, threshold) is False` per item, and stores `verdict.passed` on the result.",
                "vidbyte/agents/jev/gate/gate.py JevPreflightGate._score - passes the preset's threshold and veto to `DecisionModelHelper.score_noul` and stores `verdict.passed`.",
                "vidbyte/lib/jev/decision.py DecisionModelHelper.score_noul - the inclusive mean P(true) bound and the per-answer veto live here once.",
            ),
            will_not_work=(
                "Moving the comparison into a private helper of the same class or module: C013 follows answer values through same-class attributes and returns, and the threshold logic is still outside DecisionModelHelper.",
                "Rewriting the comparison (`not p >= t`, `t > p`, `1 - p > 1 - t`) or reading the probability through another local name: any ordered comparison of an answer-derived value with a value that is not is the same inline decision.",
                "Rounding or casting the probability first (`round(p, 2) < t`, `float(p) < t`): the value is still the answer.",
                "Raising C013's baseline in lint/baseline.json: each finding is a Jev decision that the canonical helper does not make.",
            ),
            verify=f"{self.verify_command()} && python -m pytest tests/test_jev_done.py tests/test_jev_preflight.py tests/test_jev_compute_situations.py -q",
        )

    def _explain_direct(self, finding: Finding) -> Diagnostic:
        # A direct runner or provider call is a second request path beside the helper.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.location()} in {finding.symbol} {extra['what']} (`{extra['code']}`), so this agents-layer code can ask Jev without DecisionModelHelper.",
            why_blocked="DecisionModelHelper is the canonical Jev request path: it composes DecisionModelRunner in the lib layer so every Jev caller shares one request and answer path (PR #477 review comment 4130386075). The field guide's check for every Jev capability is \"Agent code calls Jev through `DecisionModelHelper`, not `DecisionModelRunner`\", verified by `rg \"DecisionModelRunner\" vidbyte/agents/jev` finding no direct runner usage (jev-capability-layout.md). A direct runner or provider call is a second request path that any later change to the helper silently misses.",
            how_to_fix="\n".join((
                "1. Send the request through the helper: `decision = await DecisionModelHelper(self.decision).arun(JevDecisionRequest(state=state, questions=questions))`, then score it with `DecisionModelHelper.score_noul` or `noul_passes`.",
                f"2. Remove the {RUNNER_CLASS} import, construction, `ModelProviders.decision(...)`, or `run_decision(...)` call from this agents-layer module.",
                "3. If this code needs something from the runner that the helper does not expose, add that operation to DecisionModelHelper in vidbyte/lib/jev/decision.py, which owns the runner in the lib layer, and call it from here.",
                "4. Keep this caller's fail-open policy around the helper call: catch VidbyteSdkError and consult JevDecisionFailurePolicy.should_fail_closed, as JevPreflightGate._ask does.",
            )),
            correct_examples=(
                "vidbyte/agents/jev/gate/gate.py JevPreflightGate._ask - `await DecisionModelHelper(self.decision).arun(request)` inside the gate's fail-open policy.",
                "vidbyte/agents/jev/compute/recognizer.py JevComputeRecognizer.recognize - one DecisionModelHelper request for every enabled option.",
            ),
            will_not_work=(
                f"Importing {RUNNER_CLASS} under an alias or through its package: C013 reports the import itself, whatever it is bound to.",
                "Calling the TypeSafe provider's run_decision or ModelProviders.decision instead of the runner: it is the same bypass one layer lower.",
                "Raising C013's baseline in lint/baseline.json: each finding is a Jev request outside the canonical path.",
            ),
            verify=f"{self.verify_command()} && python -m pytest tests/test_jev_done.py tests/test_jev_preflight.py -q",
        )

    def _explain_per_item(self, finding: Finding) -> Diagnostic:
        # Serial per-item requests multiply latency and cost; the repair batches shared-state questions or runs independent requests together.
        extra = finding.extra
        via = f" through `self.{extra['via']}`, which sends a DecisionModelHelper request" if extra["via"] else ""
        return Diagnostic(
            what_happened=f"{finding.location()} in {finding.symbol} awaits a Jev request{via} (`{extra['code']}`) inside the loop or comprehension at line {extra['loop_line']}, so Jev is asked once per iteration, one request after another.",
            why_blocked="The owner rejected one Jev request per item: \"I dont want to run each one seperately\" (PR #470 comment 4117808663, done checks), \"should build all of the questions and then ask them to jev at once\" (PR #513 comment 4191544290, dynamic compute), and asked independent skill candidates to load \"all at the same time for different requests, asynchronously\" (PR #517 comment 4199735123). The field guide records both shapes: done checks send one request whose per-item questions name their item and \"never loop one request per item\", and independent candidates run with asyncio.gather (jev-capability-layout.md). A serial loop multiplies decision latency by the number of items, because each request waits for the one before it.",
            how_to_fix="\n".join((
                "1. If the items share one state, build every item's questions first, each named for its item (`question.name(item)`, as JevRunState.combine does), send them in one `JevDecisionRequest` through `DecisionModelHelper.arun`, and score each item from that one response with `noul_passes` or `score_noul`.",
                "2. If each item needs its own state (one item per request, asking-jev-questions T15), create the requests in the loop without awaiting them and run them together: `await asyncio.gather(*(helper.arun(request) for request in requests), return_exceptions=True)`, then classify every result with `isinstance(result, BaseException)` and fail closed on any failure (S063).",
                "3. Keep the loop for building questions or requests and for reading answers; only the awaited request leaves it.",
            )),
            correct_examples=(
                "vidbyte/agents/jev/done/run_state.py JevRunState.combine and _ask - every enabled done check's per-item questions go to Jev in one request.",
                "vidbyte/agents/jev/compute/recognizer.py JevComputeRecognizer.recognize - all enabled options' questions share one request and one state.",
            ),
            will_not_work=(
                "Moving the awaited request into a same-class method and calling that method in the loop: C013 follows same-class methods that send a request.",
                "Awaiting `asyncio.create_task(...)` or `asyncio.wait_for(...)` around each request inside the loop: the requests still run one after another.",
                "Raising C013's baseline in lint/baseline.json: each finding is a serial Jev round trip per item.",
            ),
            verify=f"{self.verify_command()} && python -m pytest tests/test_jev_done.py tests/test_jev_compute_situations.py -q",
        )


RULE = JevDecisionHelperOnlyRule()
