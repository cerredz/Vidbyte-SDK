"""FILE: lint/rules/s064_retry_overall_deadline.py

PURPOSE: Detect a retry loop that sleeps between attempts but never consults a cumulative deadline, so each attempt's budget restarts and the whole call can run for attempts x (timeout + backoff).
ROLE IN CODEBASE: Enforces S064 (catalog S083, VR-018) so a time budget bounds the operation that declares it (the S012/S045 deadline intent) across retries, not only within one attempt.
ARCHITECTURE NOTE: Pure AST analysis of vidbyte/**, one module at a time. A loop is a retry loop when its AST names retry vocabulary and it sleeps at its own level: directly, or through an in-module helper that sleeps outside any loop of its own (learned to a fixpoint). It complies when the loop, or an in-module function it calls (to a fixpoint), makes an ordered comparison with a clock-derived value; when it sits inside a timeout block of its own function; or when its function is reached through in-module calls from a call inside such a block or from an asyncio.wait_for argument.
FUNCTION INVENTORY: CallGraph resolves in-module calls; ClockFacts decides clock-derived expressions and deadline comparisons; RetryLoopScan finds and judges loops; RetryOverallDeadlineRule reports and explains.
COMMON MODIFICATION PATTERNS: A new clock accessor goes in _CLOCK_CALLS and a new timeout context manager in _TIMEOUT_SCOPES. Keep compliance broad and detection narrow: an unmodeled deadline must hide a finding, never create one.
WHAT NOT TO DO: Do not import vidbyte, treat a per-attempt timeout (wait_for around one attempt) as a cumulative deadline, or report a polling loop that has no retry vocabulary.
KNOWN EDGE CASES: A deadline enforced by another module (a caller elsewhere wrapping the call in asyncio.timeout) is not seen, so the loop is reported; pass the deadline in instead. A function reached from a timeout block on any one in-module path counts as bounded. Sleeps inside a nested loop belong to that loop, so an outer loop is not reported for its inner retry loop.
RELATED DOCS: docs/design/lint-sdk-jev-packaging-async.md; docs/design/lint-rule-catalog-expansion.md (VR-018); field-guide/vidbyte-sdk/runtime-boundaries.md; lint/rules/s045_async_function_with_timeout.py.
TESTS: python lint/run.py --rule S064; fixture and mutation results are recorded in the S3 pull request body.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

SCOPE_PREFIX = "vidbyte/"
_KIND = "retry-without-deadline"
_RETRY_WORDS = re.compile(r"retr(y|ies|ied)|attempt|backoff", re.IGNORECASE)
_DEADLINE_WORDS = re.compile(r"deadline|elapsed", re.IGNORECASE)
_TIMEOUT_WORDS = re.compile(r"timeout", re.IGNORECASE)
# Calls that read a clock: time.monotonic(), loop.time(), middleware.clock(), datetime.now(), and their variants.
_CLOCK_CALLS = frozenset({"monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns", "time", "time_ns", "clock", "now", "utcnow"})
# Context managers that cancel their body at a deadline (asyncio, plus anyio and trio spellings).
_TIMEOUT_SCOPES = frozenset({"timeout", "timeout_at", "fail_after", "fail_at", "move_on_after", "move_on_at"})
_ORDERED = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, slots=True)
class RetryGap:
    """One retry loop with no cumulative deadline."""

    line: int
    symbol: str
    facts: Mapping[str, str]


def callee_name(func: ast.expr) -> str:
    # The final identifier of a call target, or "" for computed callees.
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def own_nodes(root: ast.AST) -> Iterator[ast.AST]:
    # The nodes under root that run at root's own level: nested loops, functions, lambdas, and classes are not entered.
    pending = list(ast.iter_child_nodes(root))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, (*_LOOPS, *_SCOPES)):
            pending.extend(ast.iter_child_nodes(node))


class CallGraph:
    """Resolves calls of one module to its own functions and methods."""

    def __init__(self, tree: ast.Module) -> None:
        # Indexes module functions, class methods, in-module bases, and per-function instance bindings.
        self.functions: dict[str, FunctionNode] = {}
        self.methods: dict[str, dict[str, FunctionNode]] = {}
        self.bases: dict[str, tuple[str, ...]] = {}
        self.owned: list[tuple[str, FunctionNode]] = []
        self.owner_of: dict[ast.AST, str] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
                self.owned.append(("", node))
            elif isinstance(node, ast.ClassDef):
                members = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
                self.methods[node.name] = {item.name: item for item in members}
                self.bases[node.name] = tuple(callee_name(base) for base in node.bases if callee_name(base))
                self.owned.extend((node.name, item) for item in members)
        self.owner_of = {function: owner for owner, function in self.owned}
        self.instances = {function: self._instances(function) for _, function in self.owned}

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

    def resolve(self, call: ast.Call, function: FunctionNode) -> FunctionNode | None:
        # The in-module function a call reaches: a module function, a constructor, `self`/`cls`/Class methods, or `var.m()` with `var = Class(...)`.
        func = call.func
        owner = self.owner_of.get(function, "")
        if isinstance(func, ast.Name):
            return self.functions.get(func.id) or self._method(func.id, "__init__")
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            return None
        holder = func.value.id
        if holder in {"self", "cls"}:
            return self._method(owner, func.attr)
        if holder in self.methods:
            return self._method(holder, func.attr)
        cls = self.instances[function].get(holder)
        return self._method(cls, func.attr) if cls is not None else None

    def callees(self, nodes: Iterable[ast.AST], function: FunctionNode) -> set[FunctionNode]:
        # The in-module functions the calls among the nodes reach.
        found: set[FunctionNode] = set()
        for node in nodes:
            if isinstance(node, ast.Call):
                target = self.resolve(node, function)
                if target is not None:
                    found.add(target)
        return found

    def _method(self, owner: str, name: str) -> FunctionNode | None:
        # The method a call on `owner` reaches, searching in-module bases.
        return next((self.methods[cls][name] for cls in self.lineage(owner) if name in self.methods[cls]), None)

    def _instances(self, function: FunctionNode) -> dict[str, str]:
        # Local names bound to an instance of a module class, so `run.execute()` resolves after `run = _WorkflowRun(...)`.
        found: dict[str, str] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name) and node.value.func.id in self.methods:
                    found[node.targets[0].id] = node.value.func.id
        return found


class ClockFacts:
    """Decides which expressions of one module derive from a clock and which functions compare one with a bound."""

    def __init__(self, graph: CallGraph) -> None:
        # Learns clock-derived locals per function and self attributes per class, then the deadline-checking functions.
        self.graph = graph
        self.attributes: dict[str, set[str]] = {}
        self.names: dict[ast.AST, set[str]] = {function: set() for _, function in graph.owned}
        changed = True
        while changed:
            changed = False
            for owner, function in graph.owned:
                for node in ast.walk(function):
                    changed = self._absorb(owner, function, node) or changed
        self.checkers = self._checkers()

    def derived(self, node: ast.expr, function: FunctionNode) -> bool:
        # True when the expression reads a clock, a clock-derived local or self attribute, or a deadline or elapsed value.
        owner = self.graph.owner_of.get(function, "")
        for part in ast.walk(node):
            if isinstance(part, ast.Call) and callee_name(part.func) in _CLOCK_CALLS:
                return True
            if isinstance(part, ast.Name) and (part.id in self.names[function] or _DEADLINE_WORDS.search(part.id)):
                return True
            if isinstance(part, ast.Attribute) and (_DEADLINE_WORDS.search(part.attr) or (isinstance(part.value, ast.Name) and part.value.id == "self" and any(part.attr in self.attributes.get(cls, set()) for cls in self.graph.lineage(owner)))):
                return True
        return False

    def comparisons(self, root: ast.AST, function: FunctionNode) -> list[ast.Compare]:
        # The ordered comparisons under root that involve a clock-derived value.
        found: list[ast.Compare] = []
        for node in ast.walk(root):
            if isinstance(node, ast.Compare) and any(isinstance(op, _ORDERED) for op in node.ops) and any(self.derived(item, function) for item in (node.left, *node.comparators)):
                found.append(node)
        return found

    def _checkers(self) -> set[FunctionNode]:
        # Functions that compare a clock-derived value with a bound, or call one that does, to a fixpoint.
        checkers = {function for _, function in self.graph.owned if self.comparisons(function, function)}
        changed = True
        while changed:
            changed = False
            for _, function in self.graph.owned:
                if function not in checkers and self.graph.callees(list(ast.walk(function)), function) & checkers:
                    checkers.add(function)
                    changed = True
        return checkers

    def _absorb(self, owner: str, function: FunctionNode, node: ast.AST) -> bool:
        # Marks a local or self attribute assigned from a clock-derived expression.
        if isinstance(node, ast.Assign):
            value, targets = node.value, node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            value, targets = node.value, [node.target]
        else:
            return False
        if not self.derived(value, function):
            return False
        changed = False
        for target in targets:
            for item in ast.walk(target):
                if isinstance(item, ast.Name) and item.id not in self.names[function]:
                    self.names[function].add(item.id)
                    changed = True
                elif isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "self" and owner and item.attr not in self.attributes.setdefault(owner, set()):
                    self.attributes[owner].add(item.attr)
                    changed = True
        return changed


class RetryLoopScan:
    """Finds one module's sleeping retry loops and reports those with no cumulative deadline."""

    def __init__(self, tree: ast.Module) -> None:
        # Learns the call graph, clock facts, sleeping helpers, and timeout-bounded functions once per module.
        self.graph = CallGraph(tree)
        self.clock = ClockFacts(self.graph)
        self.parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        self.time_modules = {alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names if alias.name == "time"}
        self.sleep_names = {alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module in {"time", "asyncio", "anyio", "trio"} for alias in node.names if alias.name == "sleep"}
        self.sleepers = self._sleepers()
        self.bounded = self._bounded()

    def gaps(self) -> list[RetryGap]:
        # One gap per retry loop that neither checks a deadline nor runs under one.
        gaps: list[RetryGap] = []
        for owner, function in self.graph.owned:
            symbol = f"{owner}.{function.name}" if owner else function.name
            for loop in (node for node in ast.walk(function) if isinstance(node, _LOOPS)):
                sleep = self._sleep(loop, function)
                words = self._retry_words(loop)
                if sleep is None or not words or self._complies(loop, function):
                    continue
                gaps.append(RetryGap(line=loop.lineno, symbol=symbol, facts={"loop": "while" if isinstance(loop, ast.While) else "for", "sleep": sleep, "words": ", ".join(words[:4]), "timeouts": ", ".join(self._timeouts(function))}))
        return sorted(gaps, key=lambda item: item.line)

    def _is_sleep(self, call: ast.Call) -> bool:
        # An awaited `*.sleep(...)`, `time.sleep(...)` through any alias, or a `sleep` imported from time, asyncio, anyio, or trio.
        func = call.func
        if isinstance(func, ast.Name):
            return func.id in self.sleep_names
        if not isinstance(func, ast.Attribute) or func.attr != "sleep":
            return False
        return isinstance(self.parents.get(call), ast.Await) or (isinstance(func.value, ast.Name) and func.value.id in self.time_modules)

    def _sleepers(self) -> set[FunctionNode]:
        # Helpers that sleep at their own level (not inside a loop of their own), directly or through another helper.
        sleepers: set[FunctionNode] = set()
        changed = True
        while changed:
            changed = False
            for _, function in self.graph.owned:
                if function in sleepers:
                    continue
                calls = [node for node in own_nodes(function) if isinstance(node, ast.Call)]
                if any(self._is_sleep(call) for call in calls) or self.graph.callees(list(calls), function) & sleepers:
                    sleepers.add(function)
                    changed = True
        return sleepers

    def _sleep(self, loop: ast.AST, function: FunctionNode) -> str | None:
        # The sleeping call at the loop's own level (directly or through a sleeping helper), as source text.
        for node in own_nodes(loop):
            if isinstance(node, ast.Call) and (self._is_sleep(node) or self.graph.resolve(node, function) in self.sleepers):
                return ast.unparse(node)
        return None

    @staticmethod
    def _retry_words(loop: ast.AST) -> list[str]:
        # The distinct identifiers in the loop that name retrying: retry words first, then backoff, then attempt, each in tree order.
        words: list[str] = []
        for node in ast.walk(loop):
            name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else node.arg if isinstance(node, (ast.keyword, ast.arg)) else None
            if name and _RETRY_WORDS.search(name) and name not in words:
                words.append(name)
        return sorted(words, key=lambda word: next(rank for rank, stem in enumerate(("retr", "backoff", "attempt")) if stem in word.lower()))

    def _complies(self, loop: ast.AST, function: FunctionNode) -> bool:
        # A clock comparison in the loop or a function it calls, an enclosing timeout block, or a timeout-bounded caller.
        if self.clock.comparisons(loop, function) or self.graph.callees(list(ast.walk(loop)), function) & self.clock.checkers:
            return True
        return function in self.bounded or self._inside_timeout(loop, function)

    def _inside_timeout(self, node: ast.AST, function: FunctionNode) -> bool:
        # True when a `with`/`async with` timeout block of the same function encloses the node.
        current = self.parents.get(node)
        while current is not None and current is not function:
            if isinstance(current, (ast.With, ast.AsyncWith)) and any(self._is_timeout(item.context_expr, function) for item in current.items):
                return True
            current = self.parents.get(current)
        return False

    def _is_timeout(self, expr: ast.expr, function: FunctionNode) -> bool:
        # `asyncio.timeout(...)`-style calls, or a local name assigned from one (`deadline = asyncio.timeout(t)` then `async with deadline`).
        if isinstance(expr, ast.Call):
            return callee_name(expr.func) in _TIMEOUT_SCOPES
        if isinstance(expr, ast.Name):
            return any(isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and callee_name(node.value.func) in _TIMEOUT_SCOPES and any(isinstance(target, ast.Name) and target.id == expr.id for target in node.targets) for node in ast.walk(function))
        return False

    def _bounded(self) -> set[FunctionNode]:
        # Functions reached through in-module calls from a call inside a timeout block or from a wait_for argument with a timeout.
        bounded: set[FunctionNode] = set()
        for _, function in self.graph.owned:
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and self._inside_timeout(node, function):
                    target = self.graph.resolve(node, function)
                    bounded.update([target] if target is not None else [])
                if isinstance(node, ast.Call) and callee_name(node.func) == "wait_for" and node.args and isinstance(node.args[0], ast.Call) and not self._no_timeout(node):
                    target = self.graph.resolve(node.args[0], function)
                    bounded.update([target] if target is not None else [])
        return self._close(bounded)

    def _close(self, seeds: set[FunctionNode]) -> set[FunctionNode]:
        # Everything a bounded function calls in-module is bounded too.
        bounded = set(seeds)
        pending = list(seeds)
        while pending:
            function = pending.pop()
            for target in self.graph.callees(list(ast.walk(function)), function):
                if target not in bounded:
                    bounded.add(target)
                    pending.append(target)
        return bounded

    @staticmethod
    def _no_timeout(call: ast.Call) -> bool:
        # `wait_for(x, None)` or `wait_for(x, timeout=None)` waits forever.
        value = call.args[1] if len(call.args) > 1 else next((item.value for item in call.keywords if item.arg == "timeout"), None)
        return value is None or (isinstance(value, ast.Constant) and value.value is None)

    @staticmethod
    def _timeouts(function: FunctionNode) -> list[str]:
        # The function's timeout parameters, which apply per attempt inside the loop.
        arguments = function.args
        return [item.arg for item in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs) if _TIMEOUT_WORDS.search(item.arg)]


class RetryOverallDeadlineRule(Rule):
    """Requires every sleeping retry loop to stop at a cumulative deadline."""

    id = "S064"
    name = "retry-overall-deadline"
    severity = "blocking"
    summary = "A loop that retries and sleeps between attempts stops at one cumulative deadline: it compares a clock reading with a deadline (directly or through an in-module helper) or runs under an asyncio.timeout block, so retries and backoff cannot extend past the caller's time budget."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans every production module; unparsable files are S001's to report.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(SCOPE_PREFIX):
                continue
            findings.extend(self._finding(source, gap) for gap in RetryLoopScan(source.tree).gaps())
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # One kind: the consequence names the loop's per-attempt budget when it has one.
        extra = finding.extra
        budget = f" `{extra['timeouts']}` applies to each attempt, so it restarts with every retry." if extra.get("timeouts") else " No time budget is consulted between attempts."
        agent = "vidbyte/agents/" in finding.rel_path
        owner = "AgentLoopSettings.timeout_seconds, which AgentRuntime._budget_stop checks only between iterations, so a retry storm inside one call runs past it" if agent else "the timeout the caller passed in, which today bounds a single attempt rather than the call"
        return Diagnostic(
            what_happened=f"{finding.location()} in {finding.symbol}: this {extra['loop']} loop retries ({extra['words']}) and sleeps between attempts (`{extra['sleep']}`), but nothing in it compares a clock reading with a deadline, it is not inside an `asyncio.timeout(...)` block, and no in-module caller runs it under one.{budget} Total time grows with every retry and backoff.",
            why_blocked=" ".join((
                "VR-018 (docs/design/lint-rule-catalog-expansion.md) requires retry loops to track a cumulative deadline so the time budget does not reset across attempts, and S012/S045 encode the intent that a timeout bounds the operation that declares it.",
                f"Here the owning budget is {owner}.",
                "The field guide (runtime-boundaries.md, PR #349 comment 3868172231) says to \"Reuse the existing general mechanism (`AgentLoopSettings.timeout_seconds`, `CostBudgetMiddleware`) instead of adding a parallel field\", so the repair consults that budget rather than inventing a new ceiling.",
            )),
            how_to_fix="\n".join((
                "1. Before the loop, compute one deadline from the budget the caller already owns: `deadline = loop.time() + budget` (`time.monotonic()` in synchronous code), where budget is the existing timeout, or what remains of AgentLoopSettings.timeout_seconds for the agent runtime.",
                "2. Before each sleep and each new attempt, stop retrying when the remaining time cannot cover the backoff (`if loop.time() + delay >= deadline: ...` raise or return the last failure), and cap each attempt's own timeout at the remaining time.",
                "3. Or run the whole loop under `async with asyncio.timeout(remaining):`, or call this function from inside such a block in this module, so the event loop enforces the cumulative budget.",
                "4. Add a test in which every attempt fails slowly and assert the call stops at the budget, then rerun the verify command.",
            )),
            correct_examples=(
                "vidbyte/workflows/machine.py StateMachine.arun - runs _WorkflowRun._execute_attempts, the stage retry loop, inside `async with asyncio.timeout(self._definition.settings.timeout_seconds)`, so retries and backoff share one run deadline.",
                "vidbyte/agents/runtime.py AgentRuntime._budget_stop - compares `self.middleware.clock() - started_at` with `self.config.timeout_seconds`, the cumulative check a retry loop can consult.",
            ),
            will_not_work=(
                "Lowering the retry count or the backoff: the bound is still attempts x per-attempt timeout, and it grows again whenever a caller raises either setting.",
                "Wrapping each attempt in `asyncio.wait_for(attempt, timeout)`: every attempt restarts that timeout, which is the reset this rule reports.",
                "Adding a separate `overall_deadline` or `max_total_seconds` setting beside the existing timeout: the field guide asks to reuse the general mechanism, because a second ceiling interacts with the first in ways nobody configured.",
                "Raising S064's baseline in lint/baseline.json: each finding is a call whose declared budget does not bound it.",
            ),
            verify=f"{self.verify_command()} && python -m pytest {'tests/test_agent_runtime.py tests/test_agent_middleware.py' if agent else 'tests/test_web_operation_client_retry.py tests/test_sync_runner_default_transport.py'} -q",
        )

    def _finding(self, source: SourceFile, gap: RetryGap) -> Finding:
        # Stores every quoted fact, so explain() never re-reads source.
        return Finding(rule_id=self.id, rel_path=source.rel, line=gap.line, source_line=source.line_at(gap.line), symbol=gap.symbol, extra={"kind": _KIND, **gap.facts})


RULE = RetryOverallDeadlineRule()
