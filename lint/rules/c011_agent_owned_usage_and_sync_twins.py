"""FILE: lint/rules/c011_agent_owned_usage_and_sync_twins.py

PURPOSE: Detect agent-layer model calls whose usage never reaches the agent's UsageTracker, and public entry classes whose async arun() has no matching synchronous run().
ROLE IN CODEBASE: Enforces C011, the two halves of the agent-owned run contract: the agent owns one usage tracker that every model call made on its behalf records into, and every public entry class is callable as run() or arun() (AGENTS.md).
ARCHITECTURE NOTE: Static AST analysis over tracked vidbyte/ modules with a shared in-repo class index. The usage half has three sub-checks (unrecorded model call, child runtime built without the tracker, orphan tracker); the sync-twin half has two (missing twin, signature drift). Every finding stores its sub-check in extra["kind"], so one C011 count covers both families.
FUNCTION INVENTORY: ClassIndex resolves in-repo inheritance; ModelCallScanner finds model calls and what happens to their responses; UnrecordedCallAnalyzer, ChildRuntimeAnalyzer, OrphanTrackerAnalyzer, and SyncTwinAnalyzer each own one sub-check family; AgentOwnedUsageAndSyncTwinsRule reports and explains.
COMMON MODIFICATION PATTERNS: Add a recording method to _RECORD_METHODS only when it really records into a UsageTracker; add an entry-class suffix to _ENTRY_SUFFIXES only when every existing public class with that suffix already pairs run() with arun().
WHAT NOT TO DO: Do not import vidbyte, accept a recording in a different function as proof, or widen the sync-twin scope to internal runtime components whose arun() takes a runtime-owned RunnerHandle.
KNOWN EDGE CASES: A model call whose response is returned unrecorded makes its function a pass-through, and that function's callers must record instead; a return under `if isinstance(x, AgentResult)` is a middleware abort, not a response, and does not. Calls splatting **kwargs into a tracked runtime are not judged, because the keyword may be inside the splat. Inherited run()/arun() count. Duplicate class names resolve to the same module first, then to a unique definition.
RELATED DOCS: docs/design/lint-sdk-pricing-usage-contracts.md; docs/design/algorithm-side-call-usage.md; AGENTS.md (run() or arun()); field-guide vidbyte-sdk usage tracking.
TESTS: python lint/run.py --rule C011; fixture and mutation results are recorded in the S2 pull request body.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_USAGE_SCOPE = ("vidbyte/agents/", "vidbyte/middleware/")
_HANDLE_RECEIVER = re.compile(r"^(?:_?handle|.+_handle|inner|_?runner|.+_runner)$")
_RECORD_METHODS = frozenset({"record_call", "record_billed_failure"})
_ABORT_RESULT = "AgentResult"
_TRACKER_CLASS = "UsageTracker"
_TRACKER_PARAMETER = "usage_tracker"
_ENTRY_SUFFIXES = ("Agent", "Runner", "Harness", "Session", "Machine")
_NEUTRAL_BASES = frozenset({"object", "ABC", "Generic", "Protocol", "Exception", "BaseException", "RuntimeError", "ValueError"})
_UNRECORDED = "usage-unrecorded-model-call"
_CHILD_RUNTIME = "usage-child-runtime-without-tracker"
_ORPHAN_TRACKER = "usage-orphan-tracker"
_TWIN_MISSING = "sync-twin-missing"
_TWIN_DRIFT = "sync-twin-signature-drift"
_KINDS = (_UNRECORDED, _CHILD_RUNTIME, _ORPHAN_TRACKER, _TWIN_MISSING, _TWIN_DRIFT)

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, slots=True)
class ContractGap:
    """One C011 violation: its sub-check kind, location, and the facts its diagnostic quotes."""

    kind: str
    rel_path: str
    line: int
    symbol: str
    facts: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        # The kind selects the explanation, and the location anchors the repair.
        if self.kind not in _KINDS:
            raise ValueError(f"ContractGap.kind must be one of {_KINDS}, got {self.kind!r}.")
        if not self.rel_path or self.line < 1 or not self.symbol:
            raise ValueError(f"ContractGap needs a path, a positive line, and a symbol, got {self.rel_path!r}:{self.line} {self.symbol!r}.")


@dataclass(frozen=True, slots=True)
class ClassRecord:
    """One in-repo class definition with the simple names of its bases."""

    rel_path: str
    node: ast.ClassDef
    bases: tuple[str, ...]

    def own_method(self, name: str) -> FunctionNode | None:
        # The method defined directly in this class body, if any.
        return next((item for item in self.node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name), None)


class ClassIndex:
    """Resolves in-repo class inheritance by simple name across every tracked vidbyte module."""

    def __init__(self, files: list[SourceFile]) -> None:
        # Index every class definition by name; duplicate names keep every definition.
        self.by_name: dict[str, list[ClassRecord]] = {}
        for source in files:
            for node in ast.walk(source.tree) if source.tree is not None else ():
                if isinstance(node, ast.ClassDef):
                    record = ClassRecord(rel_path=source.rel, node=node, bases=tuple(ClassIndex.base_name(base) for base in node.bases))
                    self.by_name.setdefault(node.name, []).append(record)

    @staticmethod
    def base_name(node: ast.expr) -> str:
        # `Base`, `module.Base`, and `Base[T]` all name the class `Base`.
        target = node.value if isinstance(node, ast.Subscript) else node
        if isinstance(target, ast.Attribute):
            return target.attr
        return target.id if isinstance(target, ast.Name) else ast.unparse(target)

    def records(self) -> list[ClassRecord]:
        # Every indexed class, in a stable order.
        return sorted((record for group in self.by_name.values() for record in group), key=lambda record: (record.rel_path, record.node.lineno))

    def resolve(self, name: str, from_path: str) -> ClassRecord | None:
        # A same-module definition wins; otherwise only an unambiguous name resolves.
        candidates = self.by_name.get(name, [])
        local = [record for record in candidates if record.rel_path == from_path]
        if local:
            return local[0]
        return candidates[0] if len(candidates) == 1 else None

    def lineage(self, record: ClassRecord) -> tuple[list[ClassRecord], list[str]]:
        # The class followed by its in-repo ancestors (depth-first, own class first), plus base names that did not resolve.
        seen: list[ClassRecord] = []
        unresolved: list[str] = []
        stack = [record]
        while stack:
            current = stack.pop(0)
            if any(current is item for item in seen):
                continue
            seen.append(current)
            for base in current.bases:
                parent = self.resolve(base, current.rel_path)
                if parent is None:
                    unresolved.append(base)
                else:
                    stack.append(parent)
        return seen, unresolved

    @staticmethod
    def find_method(lineage: list[ClassRecord], name: str) -> tuple[ClassRecord, FunctionNode] | None:
        # The first class in the lineage that defines `name`, with that definition.
        for record in lineage:
            method = record.own_method(name)
            if method is not None:
                return record, method
        return None


@dataclass(frozen=True, slots=True)
class ModelCall:
    """One model call inside a function and what the function does with its response."""

    function: str
    line: int
    call_text: str
    bound: tuple[str, ...]
    returned_directly: bool


class ModelCallScanner:
    """Finds model calls in one function and the names its response is recorded or returned under."""

    def __init__(self, pass_through: frozenset[str]) -> None:
        # Method names whose return value is an unrecorded model response, beyond RunnerHandle.invoke.
        self.pass_through = pass_through

    def calls(self, function: FunctionNode) -> list[ModelCall]:
        # Each model call with the names it is bound to; a call written inside `return` is returned directly.
        found: list[ModelCall] = []
        for statement in ast.walk(function):
            if not isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Return, ast.Expr)) or statement.value is None:
                continue
            for node in ast.walk(statement.value):
                if isinstance(node, ast.Call) and self.is_model_call(node):
                    found.append(ModelCall(function=function.name, line=node.lineno, call_text=ast.unparse(node.func), bound=self._bound_names(statement, node), returned_directly=isinstance(statement, ast.Return)))
        return found

    def is_model_call(self, node: ast.Call) -> bool:
        # `<handle-like>.invoke(...)`, or a call to a computed pass-through method.
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if name == "invoke" and isinstance(func, ast.Attribute):
            receiver = func.value.attr if isinstance(func.value, ast.Attribute) else func.value.id if isinstance(func.value, ast.Name) else ""
            return bool(_HANDLE_RECEIVER.match(receiver))
        return name in self.pass_through

    @staticmethod
    def _bound_names(statement: ast.stmt, call: ast.Call) -> tuple[str, ...]:
        # Names the response lands in: `x = await call`, `x, _, _ = await call`, or `x: T = await call`.
        value = statement.value if isinstance(statement, (ast.Assign, ast.AnnAssign)) else None
        direct = value is call or (isinstance(value, ast.Await) and value.value is call)
        if not direct:
            return ()
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target] if isinstance(statement, ast.AnnAssign) else []
        return tuple(node.id for target in targets for node in ast.walk(target) if isinstance(node, ast.Name) and node.id != "_")

    @staticmethod
    def recorded_and_returned(function: FunctionNode) -> tuple[set[str], set[str]]:
        # Names passed to a usage-recording call, and names returned (alone or in a tuple), anywhere in the function.
        # A return under `if isinstance(x, AgentResult):` hands back a middleware abort result, not a model response,
        # so it does not make the function a pass-through.
        abort_returns = {id(node) for branch in ast.walk(function) if isinstance(branch, ast.If) and isinstance(branch.test, ast.Call) and isinstance(branch.test.func, ast.Name) and branch.test.func.id == "isinstance" and len(branch.test.args) == 2 and ast.unparse(branch.test.args[1]).endswith(_ABORT_RESULT) for statement in branch.body for node in ast.walk(statement) if isinstance(node, ast.Return)}
        recorded: set[str] = set()
        returned: set[str] = set()
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
                if name in _RECORD_METHODS:
                    recorded.update(item.id for argument in (*node.args, *(keyword.value for keyword in node.keywords)) for item in ast.walk(argument) if isinstance(item, ast.Name))
            elif isinstance(node, ast.Return) and node.value is not None and id(node) not in abort_returns:
                elements = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
                returned.update(element.id for element in elements if isinstance(element, ast.Name))
        return recorded, returned


class UnrecordedCallAnalyzer:
    """Sub-check usage-unrecorded-model-call: every agent-layer model response is recorded, or returned for the caller to record."""

    def analyze(self, files: list[SourceFile]) -> list[ContractGap]:
        # Collect every function in the agent and middleware layers once.
        functions = [(source, node) for source in files if source.rel.startswith(_USAGE_SCOPE) and source.tree is not None for node in ast.walk(source.tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]

        # Learn the pass-through methods: functions that return a model response without recording it.
        pass_through = self._pass_through(functions)

        # Report each model call whose response is neither recorded nor returned in its own function.
        scanner = ModelCallScanner(pass_through)
        gaps: list[ContractGap] = []
        reported: set[tuple[str, int]] = set()
        for source, function in functions:
            recorded, returned = ModelCallScanner.recorded_and_returned(function)
            for call in scanner.calls(function):
                if call.returned_directly or set(call.bound) & (recorded | returned) or (source.rel, call.line) in reported:
                    continue
                reported.add((source.rel, call.line))
                gaps.append(ContractGap(kind=_UNRECORDED, rel_path=source.rel, line=call.line, symbol=f"{function.name}:{call.call_text}", facts=(("function", function.name), ("call", call.call_text), ("bound", ", ".join(call.bound)), ("pass_through", ", ".join(sorted(pass_through))))))
        return gaps

    @staticmethod
    def _pass_through(functions: list[tuple[SourceFile, FunctionNode]]) -> frozenset[str]:
        # Repeats until stable, so a pass-through that calls another pass-through is learned too.
        names: set[str] = set()
        while True:
            scanner = ModelCallScanner(frozenset(names))
            learned = set(names)
            for _source, function in functions:
                recorded, returned = ModelCallScanner.recorded_and_returned(function)
                if any((call.returned_directly or set(call.bound) & returned) and not set(call.bound) & recorded for call in scanner.calls(function)):
                    learned.add(function.name)
            if learned == names:
                return frozenset(names)
            names = learned


class ChildRuntimeAnalyzer:
    """Sub-check usage-child-runtime-without-tracker: a runtime that accepts usage_tracker is always handed one."""

    def analyze(self, files: list[SourceFile], index: ClassIndex) -> list[ContractGap]:
        # Find every class whose own or inherited __init__ takes a usage_tracker parameter.
        tracked: dict[str, str] = {}
        for record in index.records():
            lineage, _unresolved = index.lineage(record)
            init = ClassIndex.find_method(lineage, "__init__")
            if init is not None and _TRACKER_PARAMETER in {argument.arg for argument in (*init[1].args.args, *init[1].args.kwonlyargs)}:
                tracked[record.node.name] = init[0].node.name

        # Report each construction of such a class that neither passes usage_tracker nor splats keyword arguments.
        gaps: list[ContractGap] = []
        for source in files:
            for node in ast.walk(source.tree) if source.tree is not None else ():
                if isinstance(node, ast.Call) and self._called_name(node) in tracked and not any(keyword.arg in {None, _TRACKER_PARAMETER} for keyword in node.keywords):
                    name = self._called_name(node)
                    gaps.append(ContractGap(kind=_CHILD_RUNTIME, rel_path=source.rel, line=node.lineno, symbol=f"{name}(...)", facts=(("runtime", name), ("init_owner", tracked[name]))))
        return gaps

    @staticmethod
    def _called_name(node: ast.Call) -> str:
        # `AgentRuntime(...)` or `module.AgentRuntime(...)` -> "AgentRuntime".
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return node.func.id if isinstance(node.func, ast.Name) else ""


class OrphanTrackerAnalyzer:
    """Sub-check usage-orphan-tracker: a UsageTracker is created only by the agent that owns the run's usage."""

    def analyze(self, files: list[SourceFile], index: ClassIndex) -> list[ContractGap]:
        # Visit every UsageTracker() construction with the class and function that contain it.
        gaps: list[ContractGap] = []
        for source in files:
            for owner, function, call, parent in self._constructions(source):
                lineage, _unresolved = index.lineage(owner) if owner is not None else ([], [])
                # An agent class may own a tracker it creates in __init__ and stores on self.
                agent_owned = function is not None and function.name == "__init__" and any(record.node.name.endswith("Agent") for record in lineage) and isinstance(parent, (ast.Assign, ast.AnnAssign))
                # A runtime may fall back to its own tracker only for an omitted usage_tracker parameter.
                parameter_fallback = function is not None and function.name == "__init__" and isinstance(parent, ast.BoolOp) and isinstance(parent.op, ast.Or) and any(isinstance(item, ast.Name) and item.id == _TRACKER_PARAMETER for item in parent.values) and _TRACKER_PARAMETER in {argument.arg for argument in (*function.args.args, *function.args.kwonlyargs)}
                if not (agent_owned or parameter_fallback):
                    where = f"{owner.node.name}.{function.name}" if owner is not None and function is not None else function.name if function is not None else "module level"
                    gaps.append(ContractGap(kind=_ORPHAN_TRACKER, rel_path=source.rel, line=call.lineno, symbol=f"{where}:UsageTracker()", facts=(("where", where),)))
        return gaps

    @staticmethod
    def _constructions(source: SourceFile) -> list[tuple[ClassRecord | None, FunctionNode | None, ast.Call, ast.AST | None]]:
        # (enclosing class, enclosing function, the call, the call's direct parent) for each UsageTracker() call.
        found: list[tuple[ClassRecord | None, FunctionNode | None, ast.Call, ast.AST | None]] = []
        if source.tree is None:
            return found
        parents = {child: node for node in ast.walk(source.tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == _TRACKER_CLASS:
                chain: list[ast.AST] = [node]
                while chain[-1] in parents:
                    chain.append(parents[chain[-1]])
                function = next((item for item in chain if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
                klass = next((item for item in chain if isinstance(item, ast.ClassDef)), None)
                owner = ClassRecord(rel_path=source.rel, node=klass, bases=tuple(ClassIndex.base_name(base) for base in klass.bases)) if klass is not None else None
                found.append((owner, function, node, parents.get(node)))
        return found


class SyncTwinAnalyzer:
    """Sub-checks sync-twin-missing and sync-twin-signature-drift for public entry classes."""

    def analyze(self, index: ClassIndex) -> list[ContractGap]:
        # Visit each public, non-Protocol class whose name, or an in-repo ancestor's name, marks it an entry point.
        gaps: list[ContractGap] = []
        for record in index.records():
            lineage, unresolved = index.lineage(record)
            if record.node.name.startswith("_") or "Protocol" in record.bases or not any(item.node.name.endswith(_ENTRY_SUFFIXES) for item in lineage):
                continue
            arun = ClassIndex.find_method(lineage, "arun")
            run = ClassIndex.find_method(lineage, "run")
            if arun is None or not isinstance(arun[1], ast.AsyncFunctionDef):
                continue

            # A class that defines arun() needs a synchronous run(), its own or inherited.
            if (run is None or isinstance(run[1], ast.AsyncFunctionDef)) and arun[0] is record and not set(unresolved) - _NEUTRAL_BASES:
                gaps.append(ContractGap(kind=_TWIN_MISSING, rel_path=record.rel_path, line=record.node.lineno, symbol=record.node.name, facts=(("class", record.node.name), ("arun_line", str(arun[1].lineno)), ("arun_signature", self._signature_text(arun[1])), ("run_state", "async" if run is not None else "absent"))))
                continue

            # When the class itself defines either twin, the two must accept the same parameters.
            # The finding sits on the twin this class defines itself, since that is where the drift was introduced.
            if run is not None and (arun[0] is record or run[0] is record) and self._signature(arun[1]) != self._signature(run[1]):
                anchor = run[1] if run[0] is record else arun[1]
                gaps.append(ContractGap(kind=_TWIN_DRIFT, rel_path=record.rel_path, line=anchor.lineno, symbol=f"{record.node.name}.{anchor.name}", facts=(("class", record.node.name), ("arun_owner", f"{arun[0].node.name} ({arun[0].rel_path}:{arun[1].lineno})"), ("run_owner", f"{run[0].node.name} ({run[0].rel_path}:{run[1].lineno})"), ("run_inherited", "no" if run[0] is record else "yes"), ("arun_signature", self._signature_text(arun[1])), ("run_signature", self._signature_text(run[1])))))
        return gaps

    @staticmethod
    def _signature(function: FunctionNode) -> tuple[object, ...]:
        # Parameter names, kinds, and default expressions after self; annotations and the return type may differ.
        arguments = function.args
        positional = [*arguments.posonlyargs, *arguments.args]
        defaults = [None] * (len(positional) - len(arguments.defaults)) + [ast.unparse(item) for item in arguments.defaults]
        keyword_defaults = [ast.unparse(item) if item is not None else None for item in arguments.kw_defaults]
        named = tuple((item.arg, default) for item, default in zip(positional, defaults, strict=True))[1:]
        keyword_only = tuple((item.arg, default) for item, default in zip(arguments.kwonlyargs, keyword_defaults, strict=True))
        return (named, keyword_only, arguments.vararg.arg if arguments.vararg else None, arguments.kwarg.arg if arguments.kwarg else None)

    @staticmethod
    def _signature_text(function: FunctionNode) -> str:
        # The parameter list as written, without annotations, for the diagnostic.
        copy = ast.parse(ast.unparse(function)).body[0]
        if not isinstance(copy, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return "(...)"
        for argument in (*copy.args.posonlyargs, *copy.args.args, *copy.args.kwonlyargs, copy.args.vararg, copy.args.kwarg):
            if argument is not None:
                argument.annotation = None
        return f"({ast.unparse(copy.args)})"


class AgentOwnedUsageAndSyncTwinsRule(Rule):
    """Requires agent-layer model usage to reach the agent's tracker and public entry classes to pair run() with arun()."""

    id = "C011"
    name = "agent-owned-usage-and-sync-twins"
    severity = "blocking"
    summary = "Two halves of the agent-owned run contract. Usage: in vidbyte/agents/ and vidbyte/middleware/, every model call's response is recorded with UsageTracker.record_call (or record_billed_failure) in the same function or returned for the caller to record; every runtime whose __init__ accepts usage_tracker is constructed with it; and only an agent's __init__ (or an omitted usage_tracker parameter's fallback) creates a UsageTracker. Sync twins: every public *Agent, *Runner, *Harness, *Session, or *Machine class (or subclass) that defines async arun() also offers a synchronous run(), own or inherited, with the same parameters."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Build one class index, then run the five sub-checks and report them under the one C011 count.
        files = list(catalog.python_files())
        index = ClassIndex(files)
        gaps = [*UnrecordedCallAnalyzer().analyze(files), *ChildRuntimeAnalyzer().analyze(files, index), *OrphanTrackerAnalyzer().analyze(files, index), *SyncTwinAnalyzer().analyze(index)]
        sources = {source.rel: source for source in files}
        return [Finding(rule_id=self.id, rel_path=gap.rel_path, line=gap.line, source_line=sources[gap.rel_path].line_at(gap.line), symbol=gap.symbol, extra={"kind": gap.kind, **dict(gap.facts)}) for gap in gaps]

    def explain(self, finding: Finding) -> Diagnostic:
        # Each sub-check has its own consequence and repair; all share the rejected shortcuts about the shared count.
        kind = finding.extra["kind"]
        verify = self.verify_command()
        if kind == _UNRECORDED:
            return self._unrecorded(finding, verify)
        if kind == _CHILD_RUNTIME:
            return self._child_runtime(finding, verify)
        if kind == _ORPHAN_TRACKER:
            return self._orphan(finding, verify)
        if kind == _TWIN_MISSING:
            return self._twin_missing(finding, verify)
        return self._twin_drift(finding, verify)

    @staticmethod
    def _unrecorded(finding: Finding, verify: str) -> Diagnostic:
        # A model response that bypasses the tracker is spend the run never reports.
        extra = finding.extra
        bound = f"is stored in `{extra['bound']}` but never passed to a recording call or returned" if extra["bound"] else "is not stored under a name, so nothing can record it"
        return Diagnostic(
            what_happened=f"{finding.location()} `{extra['function']}` calls `{extra['call']}(...)`, a model call, and the response {bound} in `{extra['function']}`. Its tokens and cost never reach the agent's UsageTracker.",
            why_blocked="An agent owns one UsageTracker and every model call made on its behalf must record into it, so get_usage(), CostBudgetMiddleware, and the Vidbyte backend wallet see the run's real spend (PR #285 review comment 3635839045: \"we have attached a usage tracker inside of the agent class ... propagate from the agent class to the runtime\"). Calls that skip it are under-billed silently: this exact gap has been fixed four times recently, for context-window algorithm side calls (#551), AggregateAgent children (#537), Codex fallback turns (#562), and queued-prompt runs (#572).",
            how_to_fix="\n".join((
                f"1. Reach the agent's tracker from `{extra['function']}`: inside an AgentRuntime use `self.usage_tracker`; in a component built by BaseAgent (such as an actor runtime), accept a `usage_tracker` constructor argument and have BaseAgent pass `self._usage_tracker` to it, as BaseAgent._runtime already does for the linear and Jev runtimes (vidbyte/agents/base.py).",
                f"2. Immediately after the model call returns, record it: `tracker.record_call(<response>)`, as AgentRuntime._invoke_context_window_runner does after `runner.invoke(...)` (vidbyte/agents/runtime.py).",
                "3. If the call can fail after the provider billed it, record that too with `record_billed_failure(...)`, as DecisionModelRunner.arun does.",
                f"4. If `{extra['function']}` is only a wrapper whose caller records, return the raw response unchanged instead; the caller then records it (as AgentRuntime._invoke_with_middleware returns raw_result to _arun_once, which records it).",
                "5. Add a test that runs the path once and asserts the agent's get_usage() call count went up by one.",
            )),
            correct_examples=("vidbyte/agents/runtime.py AgentRuntime._invoke_context_window_runner - invokes the handle, then records the response in self.usage_tracker before returning it.", "vidbyte/agents/algorithms/reflexion.py ReflexionRuntimeAlgorithm - records its reflection model call with self.runtime.usage_tracker.record_call(raw_result) in the same function that received it.", "vidbyte/lib/runners/decision.py DecisionModelRunner.arun - records success and billed failure into the active ledger."),
            will_not_work=("Recording the call in a different function or a later step: C011 requires the record_call in the function that received the response, so no exception path can skip it.", "Estimating tokens from the output text: the tracker prices the provider-reported usage on the response.", "Raising C011's baseline in lint/baseline.json: the baseline also covers the sync-twin sub-checks, and a new unrecorded call is real under-billing."),
            verify=f"{verify} && python -m pytest tests/test_agent_pricing.py -q",
        )

    @staticmethod
    def _child_runtime(finding: Finding, verify: str) -> Diagnostic:
        # A child runtime without the parent's tracker records into a private fallback tracker nobody reads.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.location()} constructs `{extra['runtime']}(...)` without `usage_tracker=`. {extra['init_owner']}.__init__ accepts usage_tracker and falls back to a fresh UsageTracker, so every model call this child runtime makes is recorded where the owning agent never looks.",
            why_blocked="Usage is owned by the agent and propagated to every runtime working for it (PR #285 review comment 3635839045). A child runtime with its own fallback tracker under-reports the run's cost exactly as the AggregateAgent child gap fixed in #537 did.",
            how_to_fix=f"1. Pass the owning runtime's tracker to the constructor: `{extra['runtime']}(..., usage_tracker=self.runtime.usage_tracker)` (or `self.parent_runtime.usage_tracker`, whichever object owns this call).\n2. Add a test asserting the parent agent's get_usage() includes the child runtime's model calls.",
            correct_examples=("vidbyte/agents/algorithms/prosecutor_defender_judge.py DebateStageRuntimeFactory - builds each stage AgentRuntime with usage_tracker=self.parent_runtime.usage_tracker.", "vidbyte/agents/algorithms/independent_critic.py - builds the critic runtime with usage_tracker=self.runtime.usage_tracker."),
            will_not_work=("Merging the child's fallback tracker into the parent afterwards: an exception between the call and the merge loses the usage.", "Raising C011's baseline in lint/baseline.json: the shared count would hide this new gap behind the sync-twin findings."),
            verify=verify,
        )

    @staticmethod
    def _orphan(finding: Finding, verify: str) -> Diagnostic:
        # A tracker created outside the agent splits the run's usage across ledgers.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.location()} creates a new UsageTracker() in {extra['where']}. Only an agent's __init__ owns a tracker, and a runtime may create one only as the fallback for an omitted usage_tracker parameter.",
            why_blocked="A second tracker splits one run's usage: calls recorded into it are invisible to the agent's get_usage(), budgets, and the backend wallet (PR #285 review comment 3635839045; the #537 and #572 usage fixes both repaired split ledgers).",
            how_to_fix=f"1. Delete the new UsageTracker() in {extra['where']}.\n2. Accept the owning agent's tracker as a `usage_tracker` parameter (or read `self.runtime.usage_tracker`) and record into that.\n3. If {extra['where']} really starts a new, separately billed run, make it a BaseAgent (whose __init__ owns the tracker) and merge its rollup into the parent ledger the way BaseAgent.generate_reply does.",
            correct_examples=("vidbyte/agents/base.py BaseAgent.__init__ - the agent creates the one tracker for its runs.", "vidbyte/agents/runtime.py AgentRuntime.__init__ - `usage_tracker or UsageTracker()` falls back only when the caller passed none."),
            will_not_work=("Merging the extra tracker into the agent's tracker at the end of the run: any exception before the merge loses the usage.", "Raising C011's baseline in lint/baseline.json: the shared count would hide this new gap behind older findings."),
            verify=verify,
        )

    @staticmethod
    def _twin_missing(finding: Finding, verify: str) -> Diagnostic:
        # A public entry class without run() cannot be called from synchronous code.
        extra = finding.extra
        state = "defines run() as async, so there is still no synchronous entry point" if extra["run_state"] == "async" else "has no run(), own or inherited"
        return Diagnostic(
            what_happened=f"{finding.location()} `{extra['class']}` is a public entry class with `async def arun{extra['arun_signature']}` (line {extra['arun_line']}), but it {state}.",
            why_blocked="AGENTS.md tells every caller to \"call run() or arun()\", and every other public agent, runner, harness, session, and state machine (BaseAgent, CodexHarnessAgent, EvalRunner, Text/Image/VideoModelRunner, ParadigmHarness, Session, StateMachine) pairs arun() with a synchronous run() of the same signature. Review asked for exactly this twin on PRs #280, #281, and #282 (comments 3606335886, 3607423669, 3607414084: \"also create a run() function, not async\"). Without it, synchronous callers must hand-roll asyncio.run(...) around the class and lose the running-loop guard every other entry class gives them.",
            how_to_fix=f"1. Add `def run{extra['arun_signature']}` to `{extra['class']}` directly below arun(), with the same parameters and the same return annotation (without the coroutine).\n2. In its body, refuse to run inside an active event loop and otherwise bridge to arun(): copy the guard from vidbyte/lib/runners/text.py TextModelRunner.run, which raises a clear error when `asyncio.get_running_loop()` succeeds and otherwise returns `asyncio.run(self.arun(...))` with every argument forwarded.\n3. Add a test calling run() from synchronous code and asserting it returns what arun() returns.",
            correct_examples=("vidbyte/lib/runners/text.py TextModelRunner.run - synchronous twin of arun() with the identical parameter list.", "vidbyte/evals/runner.py EvalRunner.run - forwards suite and tags to arun() through asyncio.run."),
            will_not_work=("Calling `asyncio.get_event_loop().run_until_complete(...)`: it is deprecated without a running loop and fails inside one.", "Giving run() a narrower parameter list than arun(): C011 then reports sync-twin-signature-drift.", "Raising C011's baseline in lint/baseline.json: the shared count would let a new usage gap pass in its place."),
            verify=verify,
        )

    @staticmethod
    def _twin_drift(finding: Finding, verify: str) -> Diagnostic:
        # Twins with different parameters make the sync and async entry points behave differently.
        extra = finding.extra
        first = f"`{extra['class']}` overrides arun() but inherits run() from {extra['run_owner']}: override run() in `{extra['class']}` too, with exactly arun()'s parameters `{extra['arun_signature']}`." if extra["run_inherited"] == "yes" else f"Make the parameter list of run() in {extra['run_owner']} match arun()'s `{extra['arun_signature']}` exactly (names, positional or keyword-only kind, and defaults); annotations may differ only by the coroutine return type."
        return Diagnostic(
            what_happened=f"{finding.location()} `{extra['class']}` exposes `arun{extra['arun_signature']}` from {extra['arun_owner']} and `run{extra['run_signature']}` from {extra['run_owner']}; the parameter names, kinds, or defaults differ.",
            why_blocked="run() is the synchronous twin of arun() (AGENTS.md: \"call run() or arun()\"), so callers expect to switch between them without changing arguments. A parameter only one twin accepts, or a different default, makes the same call behave differently depending on whether the caller had an event loop.",
            how_to_fix=f"1. {first}\n2. Forward every parameter from run() to arun() unchanged, through the running-loop guard and `asyncio.run(self.arun(...))` that TextModelRunner.run uses.\n3. Rerun C011, then add a test that calls run() and arun() with the same arguments and asserts the same result.",
            correct_examples=("vidbyte/lib/runners/text.py TextModelRunner - run() and arun() share one parameter list.", "vidbyte/sessions/session.py Session - run(message, **options) forwards to arun(message, **options)."),
            will_not_work=("Absorbing the difference with **kwargs in only one twin: the signatures still differ and the extra arguments go unchecked.", "Raising C011's baseline in lint/baseline.json: the shared count would let a new usage gap pass in its place."),
            verify=verify,
        )


RULE = AgentOwnedUsageAndSyncTwinsRule()
