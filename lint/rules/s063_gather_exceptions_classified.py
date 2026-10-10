"""FILE: lint/rules/s063_gather_exceptions_classified.py

PURPOSE: Detect `asyncio.gather(..., return_exceptions=True)` whose results are never tested against BaseException, so a child's CancelledError or error is used as a value or dropped unseen.
ROLE IN CODEBASE: Enforces S063 (catalog S082, VR-001) so concurrent fan-out keeps the cancellation contract that S019 enforces for except handlers and fails closed on a failed or incomplete batch.
ARCHITECTURE NOTE: Pure AST analysis of vidbyte/**, one module at a time. ResultFlow is a flow-insensitive, module-local pass that follows each gather's results as shapes (a sequence of results, one result, a tuple position, a mapping of results) through names, unpacking, loops, comprehensions, list()/tuple()/zip()/enumerate()/dict(), subscripts, appends, self attributes, arguments into in-module functions, and returns to in-module callers, to a fixpoint. GatherClassification then reads every isinstance() test and match class pattern applied to one result.
FUNCTION INVENTORY: ModuleIndex resolves in-module calls and imports; GatherSite records one call; ResultFlow propagates results; GatherClassification decides each site's kind; GatherExceptionsClassifiedRule reports and explains.
COMMON MODIFICATION PATTERNS: A new pass-through builtin goes in _PASSTHROUGH and a new collector method in _APPENDERS or _EXTENDERS. Keep the approximation one-sided: extra flow may only hide a finding, so missing flow is the only way to create a false one.
WHAT NOT TO DO: Do not import vidbyte, count a test against Exception (or narrower) as cancellation-aware, or report a gather that drains tasks the same function cancelled just before it.
KNOWN EDGE CASES: Flow does not cross modules, so results classified by another module's helper are reported as unclassified (state that contract with `# @intent`). A test against a class name that does not look like an exception is a positive success check and counts as classified. A `return_exceptions` value other than the literal False counts as True; `**kwargs` hides it and the call is skipped.
RELATED DOCS: docs/design/lint-sdk-jev-packaging-async.md; docs/design/lint-rule-catalog-expansion.md (VR-001); field-guide/vidbyte-sdk/jev-capability-layout.md; lint/rules/s019_cancellation_propagation.py.
TESTS: python lint/run.py --rule S063; fixture and mutation results are recorded in the S3 pull request body.
"""

from __future__ import annotations

import ast
import builtins
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

SCOPE_PREFIX = "vidbyte/"
_DISCARDED = "results-discarded"
_PARTIAL = "cancellation-unclassified"
_UNCLASSIFIED = "results-unclassified"
# Shape steps, outermost first: a sequence of items, a mapping whose values are items, or a tuple position. () is one result.
_SEQ = "seq"
_MAP = "map"
_MAX_DEPTH = 4
_CANCELLATION_AWARE = frozenset({"BaseException", "CancelledError"})
_BUILTIN_EXCEPTIONS = frozenset(name for name, value in vars(builtins).items() if isinstance(value, type) and issubclass(value, BaseException))
_EXCEPTION_SUFFIXES = ("Error", "Exception", "Exit", "Interrupt", "Warning", "Group")
# These calls return their first argument's items unchanged (as a sequence) or the awaitable's eventual results.
_PASSTHROUGH = frozenset({"list", "tuple", "sorted", "reversed", "set", "frozenset", "iter"})
_AWAIT_WRAPPERS = frozenset({"wait_for", "shield", "ensure_future", "create_task"})
_APPENDERS = frozenset({"append", "add", "appendleft", "insert"})
_EXTENDERS = frozenset({"extend", "extendleft", "update"})
_ITEM_READERS = frozenset({"get", "pop", "setdefault"})
_INTENT = re.compile(r"#\s*@intent\s+\S+")
_NONE: frozenset[Flow] = frozenset()

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
Shape = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class Flow:
    """One way an expression holds the results of one gather site: `shape` leads from the value to a single result."""

    site: int
    shape: Shape


@dataclass(frozen=True, slots=True)
class GatherSite:
    """One `gather(..., return_exceptions=<not False>)` call and the statement that holds it."""

    call: ast.Call
    owner: str
    function: FunctionNode
    statement: ast.stmt
    discarded: bool


@dataclass(frozen=True, slots=True)
class Check:
    """One isinstance() test or match class pattern applied to a single result of a site."""

    site: int
    aware: bool
    line: int
    code: str
    function: str


@dataclass(frozen=True, slots=True)
class GatherGap:
    """One site whose results are not classified against BaseException."""

    kind: str
    line: int
    symbol: str
    facts: Mapping[str, str]


def wrap(step: str | int, flows: Iterable[Flow]) -> frozenset[Flow]:
    # Puts each flow one step deeper (inside a sequence, a mapping, or a tuple position), capped so the fixpoint ends.
    return frozenset(Flow(item.site, (step, *item.shape)) for item in flows if len(item.shape) < _MAX_DEPTH)


def headed(flows: Iterable[Flow], *heads: str | int) -> frozenset[Flow]:
    # Keeps the flows whose outermost step is one of the heads.
    return frozenset(item for item in flows if item.shape[:1] and item.shape[0] in heads)


def iterate(flows: Iterable[Flow]) -> frozenset[Flow]:
    # Iterating a sequence yields its items; iterating a tuple yields its positions (one of which holds the result); a mapping yields keys.
    return frozenset(Flow(item.site, item.shape[1:]) for item in flows if item.shape[:1] and item.shape[0] != _MAP)


def callee_name(func: ast.expr) -> str:
    # The final identifier of a call target, or "" for computed callees.
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


class ModuleIndex:
    """The functions, classes, module constants, and asyncio imports of one module, for in-module call resolution."""

    def __init__(self, tree: ast.Module) -> None:
        # Indexes module functions and class methods (the analyzed owners) and the names that mean asyncio.gather.
        self.functions: dict[str, FunctionNode] = {}
        self.methods: dict[str, dict[str, FunctionNode]] = {}
        self.bases: dict[str, tuple[str, ...]] = {}
        self.constants: dict[str, ast.expr] = {}
        self.owned: list[tuple[str, FunctionNode]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
                self.owned.append(("", node))
            elif isinstance(node, ast.ClassDef):
                members = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
                self.methods[node.name] = {item.name: item for item in members}
                self.bases[node.name] = tuple(callee_name(base) for base in node.bases if callee_name(base))
                self.owned.extend((node.name, item) for item in members)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self.constants[node.targets[0].id] = node.value
        self.asyncio_modules = {alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names if alias.name == "asyncio"}
        self.gather_names = {alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "asyncio" for alias in node.names if alias.name == "gather"}

    def is_gather(self, call: ast.Call) -> bool:
        # `asyncio.gather(...)` through any module alias, or a name imported from asyncio as gather.
        func = call.func
        if isinstance(func, ast.Attribute):
            return func.attr == "gather" and isinstance(func.value, ast.Name) and func.value.id in self.asyncio_modules
        return isinstance(func, ast.Name) and func.id in self.gather_names

    def lineage(self, owner: str) -> tuple[str, ...]:
        # The class and its in-module bases, breadth first, each once.
        order: list[str] = []
        pending = [owner] if owner in self.methods else []
        while pending:
            current = pending.pop(0)
            if current not in order:
                order.append(current)
                pending.extend(base for base in self.bases.get(current, ()) if base in self.methods)
        return tuple(order)

    def method(self, owner: str, name: str) -> FunctionNode | None:
        # The method a call on an instance of `owner` reaches, searching in-module bases.
        return next((self.methods[cls][name] for cls in self.lineage(owner) if name in self.methods[cls]), None)

    def resolve(self, call: ast.Call, owner: str, instances: Mapping[str, str]) -> tuple[FunctionNode, int] | None:
        # The in-module function a call reaches and how many leading parameters (self or cls) it binds implicitly.
        func = call.func
        if isinstance(func, ast.Name):
            if func.id in self.functions:
                return self.functions[func.id], 0
            constructor = self.method(func.id, "__init__")
            return (constructor, 1) if constructor is not None else None
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            return None
        holder = func.value.id
        if holder in {"self", "cls"} and owner:
            cls, bound = owner, True
        elif holder in self.methods:
            cls, bound = holder, False
        elif holder in instances:
            cls, bound = instances[holder], True
        else:
            return None
        target = self.method(cls, func.attr)
        if target is None:
            return None
        decorators = {callee_name(item) for item in target.decorator_list}
        if "staticmethod" in decorators:
            return target, 0
        return target, int(bound or "classmethod" in decorators)

    def exception_like(self, name: str, seen: frozenset[str] = frozenset()) -> bool:
        # A builtin exception, a name shaped like one, or an in-module class whose bases are.
        if name in _BUILTIN_EXCEPTIONS or name.endswith(_EXCEPTION_SUFFIXES):
            return True
        return name in self.bases and name not in seen and any(self.exception_like(base, seen | {name}) for base in self.bases[name])

    @staticmethod
    def qualified(owner: str, function: FunctionNode) -> str:
        # `Class.method` or `function`, as findings name their symbol.
        return f"{owner}.{function.name}" if owner else function.name


class ResultFlow:
    """Learns, to a fixpoint, which names, attributes, parameters, and returns of one module hold each site's results."""

    def __init__(self, index: ModuleIndex, sites: Mapping[ast.Call, int]) -> None:
        # Absorbs every statement and call of every owned function until no binding grows.
        self.index = index
        self.sites = sites
        self.names: dict[ast.AST, dict[str, frozenset[Flow]]] = {function: {} for _, function in index.owned}
        self.attributes: dict[str, dict[str, frozenset[Flow]]] = {}
        self.returns: dict[ast.AST, frozenset[Flow]] = {}
        self.instances: dict[ast.AST, dict[str, str]] = {function: self._instances(function) for _, function in index.owned}
        changed = True
        while changed:
            changed = False
            for owner, function in index.owned:
                for node in ast.walk(function):
                    changed = self._absorb(owner, function, node) or changed

    def flows(self, node: ast.expr | None, owner: str, function: ast.AST) -> frozenset[Flow]:
        # The ways one expression holds gather results, given the learned bindings.
        if node is None:
            return _NONE
        if isinstance(node, ast.Call):
            return self._call(node, owner, function)
        if isinstance(node, ast.Name):
            return self.names[function].get(node.id, _NONE)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                return frozenset().union(*(self.attributes.get(cls, {}).get(node.attr, _NONE) for cls in self.index.lineage(owner)))
            return _NONE
        if isinstance(node, (ast.Await, ast.NamedExpr)):
            return self.flows(node.value, owner, function)
        if isinstance(node, ast.IfExp):
            return self.flows(node.body, owner, function) | self.flows(node.orelse, owner, function)
        if isinstance(node, ast.BoolOp):
            return frozenset().union(*(self.flows(item, owner, function) for item in node.values))
        if isinstance(node, ast.Subscript):
            return self._subscript(node, owner, function)
        return self._display(node, owner, function)

    def _display(self, node: ast.expr, owner: str, function: ast.AST) -> frozenset[Flow]:
        # Tuples keep positions; lists, sets, comprehensions, and dicts hold their elements as items.
        if isinstance(node, ast.Tuple):
            positional = []
            for position, item in enumerate(node.elts):
                if isinstance(item, ast.Starred):
                    break
                positional.append(wrap(position, self.flows(item, owner, function)))
            return frozenset().union(*positional)
        if isinstance(node, (ast.List, ast.Set)):
            spread = (headed(self.flows(item.value, owner, function), _SEQ) for item in node.elts if isinstance(item, ast.Starred))
            return frozenset().union(*(wrap(_SEQ, self.flows(item, owner, function)) for item in node.elts if not isinstance(item, ast.Starred)), *spread)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return wrap(_SEQ, self.flows(node.elt, owner, function))
        if isinstance(node, ast.DictComp):
            return wrap(_MAP, self.flows(node.value, owner, function))
        if isinstance(node, ast.Dict):
            spread = (headed(self.flows(value, owner, function), _MAP) for key, value in zip(node.keys, node.values, strict=True) if key is None)
            return frozenset().union(*(wrap(_MAP, self.flows(value, owner, function)) for key, value in zip(node.keys, node.values, strict=True) if key is not None), *spread)
        return _NONE

    def _subscript(self, node: ast.Subscript, owner: str, function: ast.AST) -> frozenset[Flow]:
        # A slice keeps the sequence; an index reads one item, or one tuple position when the index is a matching constant.
        held = self.flows(node.value, owner, function)
        if isinstance(node.slice, ast.Slice):
            return frozenset(item for item in held if item.shape[:1] and item.shape[0] != _MAP)
        index = node.slice.value if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int) and node.slice.value >= 0 else None
        return frozenset(Flow(item.site, item.shape[1:]) for item in held if item.shape[:1] and (item.shape[0] in (_SEQ, _MAP) or index is None or item.shape[0] == index))

    def _call(self, node: ast.Call, owner: str, function: ast.AST) -> frozenset[Flow]:
        # A site yields a sequence of results; builtins and container methods reshape it; in-module calls return what they learned.
        if node in self.sites:
            return frozenset({Flow(self.sites[node], (_SEQ,))})
        name = callee_name(node.func)
        first = self.flows(node.args[0], owner, function) if node.args and not isinstance(node.args[0], ast.Starred) else _NONE
        if name in _AWAIT_WRAPPERS:
            return first
        if isinstance(node.func, ast.Name):
            if name in _PASSTHROUGH:
                return headed(first, _SEQ)
            if name == "zip":
                return self._zip(node, owner, function)
            if name == "enumerate":
                return wrap(_SEQ, (Flow(item.site, (1, *item.shape[1:])) for item in headed(first, _SEQ)))
            if name == "dict":
                return frozenset(Flow(item.site, (_MAP, *item.shape[2:])) for item in first if item.shape[:2] == (_SEQ, 1)) | headed(first, _MAP)
            if name == "next":
                return iterate(first)
        if isinstance(node.func, ast.Attribute):
            held = self.flows(node.func.value, owner, function)
            if name == "values":
                return frozenset(Flow(item.site, (_SEQ, *item.shape[1:])) for item in headed(held, _MAP))
            if name == "items":
                return frozenset(Flow(item.site, (_SEQ, 1, *item.shape[1:])) for item in headed(held, _MAP))
            if name in _ITEM_READERS:
                return frozenset(Flow(item.site, item.shape[1:]) for item in headed(held, _SEQ, _MAP))
            if name == "copy":
                return held
        resolved = self.index.resolve(node, owner, self.instances[function])
        return self.returns.get(resolved[0], _NONE) if resolved is not None else _NONE

    def _zip(self, node: ast.Call, owner: str, function: ast.AST) -> frozenset[Flow]:
        # zip(a, results) yields tuples whose position matches the argument that held the results.
        parts = []
        for position, item in enumerate(node.args):
            if isinstance(item, ast.Starred):
                break
            parts.append(frozenset(Flow(flow.site, (_SEQ, position, *flow.shape[1:])) for flow in headed(self.flows(item, owner, function), _SEQ) if len(flow.shape) < _MAX_DEPTH))
        return frozenset().union(*parts)

    def _absorb(self, owner: str, function: FunctionNode, node: ast.AST) -> bool:
        # Records one binding, collection, argument pass, or return; True when anything learned grows.
        if isinstance(node, ast.Assign):
            value = self.flows(node.value, owner, function)
            return any([self._bind(owner, function, target, value) for target in node.targets])
        if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and node.value is not None:
            return self._bind(owner, function, node.target, self.flows(node.value, owner, function))
        if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            return self._bind(owner, function, node.target, iterate(self.flows(node.iter, owner, function)))
        if isinstance(node, ast.withitem) and node.optional_vars is not None:
            return self._bind(owner, function, node.optional_vars, self.flows(node.context_expr, owner, function))
        if isinstance(node, ast.Return) and node.value is not None:
            learned = self.returns.get(function, _NONE)
            merged = learned | self.flows(node.value, owner, function)
            self.returns[function] = merged
            return merged != learned
        if isinstance(node, ast.Call):
            return self._collect(owner, function, node) | self._pass_arguments(owner, function, node)
        return False

    def _bind(self, owner: str, function: FunctionNode, target: ast.expr, flows: frozenset[Flow]) -> bool:
        # Joins flows into a name, a self attribute, a container written by subscript, or each element of an unpacking.
        if not flows:
            return False
        if isinstance(target, ast.Name):
            return self._merge(self.names[function], target.id, flows)
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self" and owner:
            return self._merge(self.attributes.setdefault(owner, {}), target.attr, flows)
        if isinstance(target, ast.Subscript):
            return self._bind(owner, function, target.value, wrap(_SEQ, flows) | wrap(_MAP, flows))
        if isinstance(target, (ast.Tuple, ast.List)):
            starred = any(isinstance(item, ast.Starred) for item in target.elts)
            changed = False
            for position, item in enumerate(target.elts):
                if isinstance(item, ast.Starred):
                    changed = self._bind(owner, function, item.value, headed(flows, _SEQ)) or changed
                    continue
                part = frozenset(Flow(flow.site, flow.shape[1:]) for flow in flows if flow.shape[:1] and (flow.shape[0] == _SEQ or (isinstance(flow.shape[0], int) and (starred or flow.shape[0] == position))))
                changed = self._bind(owner, function, item, part) or changed
            return changed
        return False

    def _collect(self, owner: str, function: FunctionNode, node: ast.Call) -> bool:
        # `x.append(result)` makes x a sequence of results; `x.extend(results)` copies the sequence.
        func = node.func
        if not isinstance(func, ast.Attribute) or not node.args or isinstance(node.args[-1], ast.Starred):
            return False
        if func.attr in _APPENDERS:
            return self._bind(owner, function, func.value, wrap(_SEQ, self.flows(node.args[-1], owner, function)))
        if func.attr in _EXTENDERS:
            return self._bind(owner, function, func.value, headed(self.flows(node.args[0], owner, function), _SEQ, _MAP))
        return False

    def _pass_arguments(self, owner: str, function: FunctionNode, node: ast.Call) -> bool:
        # An argument that holds results binds the matching parameter of the in-module function the call reaches.
        resolved = self.index.resolve(node, owner, self.instances[function])
        if resolved is None:
            return False
        target, skip = resolved
        positional = [*target.args.posonlyargs, *target.args.args]
        named = {item.arg for item in (*positional, *target.args.kwonlyargs)}
        changed = False
        for position, item in enumerate(node.args):
            if isinstance(item, ast.Starred):
                break
            if position + skip < len(positional):
                changed = self._merge(self.names[target], positional[position + skip].arg, self.flows(item, owner, function)) or changed
        for keyword in node.keywords:
            if keyword.arg in named:
                changed = self._merge(self.names[target], keyword.arg, self.flows(keyword.value, owner, function)) or changed
        return changed

    def _instances(self, function: FunctionNode) -> dict[str, str]:
        # Local names bound to an instance of a module class (`runner = Runner(...)`), so `runner.m(...)` resolves.
        found: dict[str, str] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call):
                name = callee_name(node.value.func)
                if isinstance(node.value.func, ast.Name) and name in self.index.methods:
                    found[node.targets[0].id] = name
        return found

    @staticmethod
    def _merge(table: dict[str, frozenset[Flow]], key: str, flows: frozenset[Flow]) -> bool:
        # Joins flows into one binding; True when it grew.
        if not flows:
            return False
        current = table.get(key, _NONE)
        merged = current | flows
        table[key] = merged
        return merged != current


class GatherClassification:
    """Finds one module's gather sites, follows their results, and reports each site that does not classify them."""

    def __init__(self, source: SourceFile, tree: ast.Module) -> None:
        # Indexes the module, finds the sites, and learns the result flow once.
        self.source = source
        self.lines = source.text.splitlines()
        self.index = ModuleIndex(tree)
        self.parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        self.sites = self._sites()
        self.flow = ResultFlow(self.index, {site.call: number for number, site in enumerate(self.sites)})

    def gaps(self) -> list[GatherGap]:
        # One gap per site with no cancellation-aware test, unless the drain or an @intent marker states the suppression.
        if not self.sites:
            return []
        checks = self._checks()
        gaps: list[GatherGap] = []
        for number, site in enumerate(self.sites):
            mine = [item for item in checks if item.site == number]
            if any(item.aware for item in mine) or self._has_intent(site):
                continue
            if mine:
                gaps.append(self._gap(_PARTIAL, number, site, mine))
            elif site.discarded and not self._drains_cancelled(site):
                gaps.append(self._gap(_DISCARDED, number, site, mine))
            elif not site.discarded:
                gaps.append(self._gap(_UNCLASSIFIED, number, site, mine))
        return gaps

    def _sites(self) -> list[GatherSite]:
        # Every gather in an owned function whose return_exceptions keyword is present and not the literal False.
        sites: list[GatherSite] = []
        for owner, function in self.index.owned:
            for node in ast.walk(function):
                if not isinstance(node, ast.Call) or not self.index.is_gather(node):
                    continue
                flag = next((item.value for item in node.keywords if item.arg == "return_exceptions"), None)
                if flag is None or (isinstance(flag, ast.Constant) and flag.value is False):
                    continue
                sites.append(GatherSite(call=node, owner=owner, function=function, statement=self._statement(node), discarded=self._discarded(node)))
        return sorted(sites, key=lambda item: (item.call.lineno, item.call.col_offset))

    def _statement(self, node: ast.AST) -> ast.stmt:
        # The innermost statement holding the call.
        current = node
        while not isinstance(current, ast.stmt):
            current = self.parents[current]
        return current

    def _discarded(self, node: ast.Call) -> bool:
        # True when the gather (awaited, or passed through wait_for/shield) is the whole expression statement.
        current: ast.AST = node
        parent = self.parents[current]
        while isinstance(parent, ast.Await) or (isinstance(parent, ast.Call) and callee_name(parent.func) in _AWAIT_WRAPPERS and parent.args[:1] == [current]):
            current, parent = parent, self.parents[parent]
        return isinstance(parent, ast.Expr)

    def _checks(self) -> list[Check]:
        # Every isinstance() test and match class pattern whose subject is one result of a site.
        checks: list[Check] = []
        for owner, function in self.index.owned:
            symbol = ModuleIndex.qualified(owner, function)
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "isinstance" and len(node.args) == 2:
                    for site in self._single_results(node.args[0], owner, function):
                        checks.append(Check(site=site, aware=self._aware(node.args[1]), line=node.lineno, code=ast.unparse(node), function=symbol))
                if isinstance(node, ast.Match):
                    for site in self._single_results(node.subject, owner, function):
                        for case in node.cases:
                            checks.extend(Check(site=site, aware=self._aware(item.cls), line=item.lineno, code=f"case {ast.unparse(item)}", function=symbol) for item in ast.walk(case.pattern) if isinstance(item, ast.MatchClass))
        return checks

    def _single_results(self, node: ast.expr, owner: str, function: FunctionNode) -> set[int]:
        # The sites of which this expression is one result (not a sequence or a tuple holding one).
        return {item.site for item in self.flow.flows(node, owner, function) if not item.shape}

    def _aware(self, classes: ast.expr) -> bool:
        # A test is cancellation-aware when it names BaseException or CancelledError, or positively checks a non-exception type.
        names = self._class_names(classes, 0)
        return not names or any(name in _CANCELLATION_AWARE or not self.index.exception_like(name) for name in names)

    def _class_names(self, node: ast.expr, depth: int) -> list[str]:
        # The class identifiers a type argument names, following tuples, `A | B` unions, and module-level tuple constants.
        if isinstance(node, ast.Tuple):
            return [name for item in node.elts for name in self._class_names(item, depth)]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._class_names(node.left, depth) + self._class_names(node.right, depth)
        if isinstance(node, ast.Name) and node.id in self.index.constants and depth < 3:
            return self._class_names(self.index.constants[node.id], depth + 1)
        if isinstance(node, ast.Name):
            return [node.id]
        return [node.attr] if isinstance(node, ast.Attribute) else []

    def _drains_cancelled(self, site: GatherSite) -> bool:
        # A discarded gather drains only tasks the same function cancelled earlier: `for t in tasks: t.cancel()` then `gather(*tasks)`.
        line = site.call.lineno
        cancelled = {ast.unparse(node.func.value) for node in ast.walk(site.function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "cancel" and not node.args and node.lineno < line}
        loops = {node.iter.id for node in ast.walk(site.function) if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.iter, ast.Name) and isinstance(node.target, ast.Name) and node.lineno < line and node.target.id in {ast.unparse(item.func.value) for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == "cancel"}}
        if not site.call.args:
            return False
        return all((isinstance(item.value, ast.Name) and item.value.id in loops) if isinstance(item, ast.Starred) else ast.unparse(item) in cancelled for item in site.call.args)

    def _has_intent(self, site: GatherSite) -> bool:
        # An `# @intent <slug>` marker from the statement's first line to the gather's last line, or in the comment block directly above.
        statement = site.statement
        end = site.call.end_lineno or site.call.lineno
        if any(_INTENT.search(text) for text in self.lines[statement.lineno - 1:end]):
            return True
        row = statement.lineno - 2
        while row >= 0 and self.lines[row].strip().startswith("#"):
            if _INTENT.search(self.lines[row]):
                return True
            row -= 1
        return False

    def _gap(self, kind: str, number: int, site: GatherSite, checks: list[Check]) -> GatherGap:
        # Records every fact the diagnostic quotes, so explain() never re-reads source.
        symbol = ModuleIndex.qualified(site.owner, site.function)
        reached = sorted({ModuleIndex.qualified(owner, function) for owner, function in self.index.owned if any(item.site == number for flows in self.flow.names[function].values() for item in flows)} - {symbol})
        tests = "; ".join(f"line {item.line} `{item.code}` in {item.function}" for item in sorted(checks, key=lambda item: item.line))
        return GatherGap(kind=kind, line=site.call.lineno, symbol=symbol, facts={"code": ast.unparse(site.call), "statement": ast.unparse(site.statement).splitlines()[0], "checks": tests, "reached": ", ".join(reached)})


class GatherExceptionsClassifiedRule(Rule):
    """Requires every gather(return_exceptions=True) result to be tested against BaseException before it is used or dropped."""

    id = "S063"
    name = "gather-exceptions-classified"
    severity = "blocking"
    summary = "Results of asyncio.gather(..., return_exceptions=True) are each tested with isinstance(result, BaseException) (or a positive success-type check) before use, never only against Exception and never discarded unseen, unless an `# @intent` comment states the suppression."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans every production module; unparsable files are S001's to report.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(SCOPE_PREFIX):
                continue
            gaps = GatherClassification(source, source.tree).gaps()
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=gap.line, source_line=source.line_at(gap.line), symbol=gap.symbol, extra={"kind": gap.kind, **gap.facts}) for gap in gaps)
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Each kind has its own consequence; all share the classification repair and the verification.
        kind = finding.extra["kind"]
        if kind == _PARTIAL:
            return self._explain_partial(finding)
        if kind == _DISCARDED:
            return self._explain_discarded(finding)
        return self._explain_unclassified(finding)

    @staticmethod
    def _why(consequence: str) -> str:
        # The shared standard: what return_exceptions=True does with a CancelledError, and where the repository states the contract.
        return " ".join((
            consequence,
            "The asyncio documentation states that with return_exceptions=True \"exceptions are treated the same as successful results, and aggregated in the result list\", and that a cancelled child \"is treated as if it raised CancelledError\" without cancelling the gather. Since Python 3.8 CancelledError subclasses BaseException, not Exception.",
            "The repository requires cancellation to propagate (SS-156, the contract S019 enforces for except handlers; field guide provider-api-contracts.md: \"Never catch `BaseException`, so cancellation propagates\"), and the field guide's concurrent Jev pattern (jev-capability-layout.md, PR #517) runs requests \"with `asyncio.gather(return_exceptions=True)`, preserve order, fail closed on any failed or incomplete batch\".",
        ))

    def _explain_partial(self, finding: Finding) -> Diagnostic:
        # An Exception-only test lets a CancelledError result through as a successful value.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.location()} in {finding.symbol} gathers with return_exceptions=True (`{extra['code']}`), and its results are classified only against Exception or narrower: {extra['checks']}. A child that is cancelled returns a CancelledError, which fails that test, so the code takes it for a successful result.",
            why_blocked=self._why("A CancelledError treated as a value is either used as if it were the child's result (an AttributeError far from the cause) or silently counted as success, so a cancelled branch never fails the batch and the cancellation itself is lost."),
            how_to_fix="\n".join((
                "1. Change each test to `isinstance(result, BaseException)` so every returned exception, CancelledError included, is classified before the result is used.",
                "2. Re-raise a cancellation instead of recording it as an ordinary failure: `if isinstance(result, asyncio.CancelledError): raise result`, then handle the remaining exceptions as this batch requires (fail closed, or record them as failures).",
                "3. Alternatively test the success type positively (`isinstance(result, AgentResult)`) and treat everything else as a failure.",
                "4. Cover a child that raises asyncio.CancelledError in the focused test, then rerun the verify command.",
            )),
            correct_examples=(
                "vidbyte/agents/multi/cleanup.py MultiAgentCleanup.close_run - records `type(outcome).__name__ for outcome in outcomes if isinstance(outcome, BaseException)`.",
                "vidbyte/agents/aggregation.py MultiProviderAggregator._collect_candidates - `\"\" if isinstance(result, BaseException) else self._reply_text(result)` before any result is read.",
            ),
            will_not_work=(
                "Wrapping the gather in `try/except asyncio.CancelledError`: with return_exceptions=True a cancelled child never raises out of the gather; its CancelledError arrives as a result.",
                "Adding `Exception` subclasses to the tuple (`(Exception, TimeoutError)`): CancelledError is not an Exception, so it still passes as a value.",
                "Raising S063's baseline in lint/baseline.json: each finding is a fan-out where a cancelled child is mistaken for a success.",
            ),
            verify=f"{self.verify_command()} && python -m pytest tests/test_mcp_attachment.py tests/test_multi_provider_agentic_grader.py tests/test_aggregate_agent.py -q",
        )

    def _explain_discarded(self, finding: Finding) -> Diagnostic:
        # A bare awaited gather drops every child error and cancellation unseen.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.location()} in {finding.symbol} awaits `{extra['code']}` as a bare statement, so every exception and CancelledError its children return is dropped without being looked at, and the code continues as if all of them succeeded.",
            why_blocked=self._why("return_exceptions=True turns each child failure into a return value; discarding the list leaves a failed close or a cancelled child with no trace, no log, and no effect on the caller."),
            how_to_fix="\n".join((
                "1. Bind the results and test each one with `isinstance(result, BaseException)`: re-raise a CancelledError, and record or raise the other exceptions, as vidbyte/agents/multi/cleanup.py records `cleanup_error_types`.",
                "2. If dropping them is the contract (best-effort cleanup that must not mask the error already being raised), state it with an `# @intent <slug>` comment directly above the statement that names the invariant and why the errors are safe to drop.",
                "3. Rerun the verify command.",
            )),
            correct_examples=(
                "vidbyte/agents/multi/cleanup.py MultiAgentCleanup.close_run - gathers every closer, then stores the type of each BaseException result on the run state.",
                "vidbyte/tools/mcp/transport.py McpStdioTransport._stop_reader_tasks - cancels each reader task first, so the drained results are the cancellations it requested; S063 accepts that drain.",
            ),
            will_not_work=(
                "Removing return_exceptions=True: the first child error then propagates while the other children keep running unobserved, so cleanup stops halfway.",
                "Assigning the results to `_` or an unused name: they are still never classified, and S063 reports the site as unclassified.",
                "Raising S063's baseline in lint/baseline.json: each finding is a fan-out whose failures and cancellations disappear.",
            ),
            verify=f"{self.verify_command()} && python -m pytest tests/test_mcp_attachment.py tests/test_mcp_stdio_transport.py -q",
        )

    def _explain_unclassified(self, finding: Finding) -> Diagnostic:
        # Results used or handed on with no test at all treat every exception as a value.
        extra = finding.extra
        reach = f" They reach {extra['reached']} in this module, and none of them tests a single result." if extra.get("reached") else " No function in this module tests a single result."
        return Diagnostic(
            what_happened=f"{finding.location()} in {finding.symbol} gathers with return_exceptions=True (`{extra['code']}`) and binds, returns, or passes on the results without any isinstance() test.{reach} An exception or CancelledError a child returns is therefore used as that child's value.",
            why_blocked=self._why("Unclassified results let a failed or cancelled child flow on as data, so the batch neither fails closed nor propagates the cancellation."),
            how_to_fix="\n".join((
                "1. Before any result is used, test each one with `isinstance(result, BaseException)`: re-raise a CancelledError and fail the batch (or record the failure) for any other exception.",
                "2. If the results leave this module, classify them before returning, or return only the successful values together with the failures, so callers elsewhere cannot mistake an exception for a value.",
                "3. If another module's helper classifies them by contract, say so with an `# @intent <slug>` comment directly above the gather statement.",
                "4. Rerun the verify command.",
            )),
            correct_examples=(
                "vidbyte/agents/aggregation.py MultiProviderAggregator._run_proposers - returns `(label, result)` pairs that _collect_candidates tests with `isinstance(result, BaseException)` before reading.",
                "vidbyte/agents/multi/cleanup.py MultiAgentCleanup.close_run - classifies every closer outcome against BaseException in the same statement that reads them.",
            ),
            will_not_work=(
                "Testing the results with `isinstance(result, Exception)`: CancelledError still passes as a value, and S063 reports the site as cancellation-unclassified.",
                "Removing return_exceptions=True to avoid the rule: the first child error then propagates while the other children keep running unobserved.",
                "Raising S063's baseline in lint/baseline.json: each finding is a batch whose exceptions are read as results.",
            ),
            verify=self.verify_command(),
        )


RULE = GatherExceptionsClassifiedRule()
