"""FILE: vidbyte/workflows/errors.py
PURPOSE: Defines safe, typed failures for workflow declaration and execution boundaries.
ROLE IN CODEBASE: Raised by graph.py and machine.py, then re-exported through vidbyte.workflows and vidbyte.

ARCHITECTURE NOTE:
    Workflow errors follow the SDK's VidbyteSdkError(message, details=...) contract.
    Each distinct public failure family has a grepable type and static diagnostic
    context; raise sites add only run-specific identifiers. Raw state, prompts,
    verifier output, and secrets must never be inserted automatically.

PUBLIC API INVENTORY:
    WorkflowError: Root workflow exception with safe diagnostic details.
    WorkflowDefinitionError: Invalid or ambiguous graph declaration.
    WorkflowExecutionError: Base for failures during a compiled run.
    WorkflowStateError: State validation, cloning, or candidate-shape failure.
    WorkflowValidationError: Validator policy requested an exception.
    StageExecutionError: Stage invocation exhausted its declared recovery policy.
    WorkflowRoutingError: No declared route matches an emitted outcome or branch.
    TransitionLimitError: Selected transition attempts exceeded the run budget.
    WorkflowBudgetError: A stage, run, detour, or child exhausted a declared ceiling.
    WorkflowCommandError: A stage returned conflicting or undeclared control intent.
    WorkflowPersistenceError: Canonical event/checkpoint storage lost consistency.
    WorkflowResumeError: A suspended run cannot resume from the requested boundary.
    WorkflowApprovalError: A confirmation response is stale, malformed, or mismatched.
    WorkflowInterruptError: An explicit stage interrupt cannot consume its response.
    WorkflowStuckError: Deterministic loop evidence crossed a configured threshold.
    WorkflowCapabilityError: A stage profile or tool action cannot be enforced safely.
    WorkflowDetourError: A detour entry, stack, or return contract is invalid.
    WorkflowSubgraphError: Child mapping, execution, suspension, or join failed.
    WorkflowErrorRecord: Serializable, bounded error evidence stored in run results.

COMMON MODIFICATION PATTERNS:
    Add a new class only for a caller-actionable failure family, give it static
    expected behavior and remediation, export it from __init__.py, and list its
    raise sites in the relevant source headers.

WHAT NOT TO DO IN THIS FILE:
    1. Do not capture full workflow state, prompts, API keys, or model output.
    2. Do not choose fallback routes from an exception; graph policy is explicit.
    3. Do not duplicate agent/provider/eval errors owned by their native packages.

KNOWN EDGE CASES:
    Chained exceptions may contain provider-specific details through __cause__;
    the workflow error's own details remain intentionally small and safe.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Inline smoke checks inspect error types and safe detail keys.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar

from vidbyte.lib.errors import VidbyteSdkError


class WorkflowError(VidbyteSdkError):
    """Root for every workflow failure with safe static diagnostic context."""

    description: ClassVar[str] = "A declared workflow could not be constructed or executed safely."
    expected: ClassVar[str] = "Workflow definitions and runs must preserve declared routes, typed state, bounded execution, and safe diagnostics."
    remediation: ClassVar[str] = "Inspect the error type and safe details, then correct the graph definition or failing callback without bypassing validation."
    related_files: ClassVar[tuple[str, ...]] = ("vidbyte/workflows/graph.py", "vidbyte/workflows/machine.py")

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        # Combines invocation-specific identifiers with static repair context.
        packet = dict(details or {})
        packet.setdefault("error_type", type(self).__name__)
        packet.setdefault("description", self.description)
        packet.setdefault("expected", self.expected)
        packet.setdefault("remediation", self.remediation)
        packet.setdefault("related_files", self.related_files)
        super().__init__(message, details=packet)

    def to_context_packet(self) -> dict[str, Any]:
        # Returns one self-contained, safe diagnostic mapping for logs and agents.
        return {"message": self.message, **self.details}


@dataclass(frozen=True, slots=True)
class WorkflowErrorRecord:
    """Bounded serializable evidence for a workflow lifecycle ERROR result."""

    error_type: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Copies safe detail fields so persisted error evidence cannot be mutated.
        object.__setattr__(self, "error_type", str(self.error_type).strip() or "WorkflowError")
        object.__setattr__(self, "message", str(self.message)[:2000])
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    @classmethod
    def from_error(cls, error: BaseException) -> "WorkflowErrorRecord":
        # Converts a public workflow error or arbitrary exception into bounded evidence.
        details = error.details if isinstance(error, VidbyteSdkError) else {}
        return cls(type(error).__name__, str(error)[:2000], details=details)


class WorkflowDefinitionError(WorkflowError):
    """Raised when a graph cannot compile into one unambiguous definition."""

    description = "The StateGraph declaration is missing required nodes/routes or contains an ambiguous, unknown, or unreachable definition."
    expected = "Compilation requires one declared entry, at least one reachable terminal, reachable stages, known targets, and one route definition per source/outcome pair."
    remediation = "Inspect the node/outcome identifiers in details, add or correct the declaration, and call compile() again before running agents."
    related_files = ("vidbyte/workflows/graph.py", "vidbyte/workflows/contracts.py")


class WorkflowExecutionError(WorkflowError):
    """Base class for failures after a graph has compiled."""

    description = "A compiled StateMachine failed before reaching a declared terminal result."
    expected = "A run should either reach a named terminal or raise a typed child error with run and stage identifiers while leaving external side effects caller-owned."
    remediation = "Inspect the child error type, run_id, stage, outcome, and chained cause; fix the failing callback or policy rather than adding an implicit fallback."
    related_files: ClassVar[tuple[str, ...]] = ("vidbyte/workflows/machine.py", "vidbyte/workflows/contracts.py")


class WorkflowStateError(WorkflowExecutionError):
    """Raised when initial or candidate state cannot be validated or cloned."""

    description = "Workflow state did not satisfy the graph's declared StateT contract or could not be isolated through the configured cloner."
    expected = "Initial, attempt, candidate, snapshot, and committed values must remain valid StateT instances and be cloneable without aliasing committed state."
    remediation = "Keep executable objects outside StateT, return the declared state type from stages, or provide compatible state_validator and state_cloner callables."
    related_files = ("vidbyte/workflows/graph.py", "vidbyte/workflows/machine.py", "vidbyte/workflows/contracts.py")


class WorkflowValidationError(WorkflowExecutionError):
    """Raised when validator policy is RAISE for an abstention or error."""

    description = "A stage validator or transition guard abstained, errored, raised, or returned an invalid contract while ValidatorErrorPolicy.RAISE was active."
    expected = "Validators return ValidationResult and the configured policy deterministically decides whether non-decisions fail open, fail closed, or raise."
    remediation = "Fix the named validator, choose an explicit fail-open/fail-closed policy, or add a declared rejection route when recovery is intended."
    related_files = ("vidbyte/workflows/validation.py", "vidbyte/workflows/machine.py")


class StageExecutionError(WorkflowExecutionError):
    """Raised when a stage cannot produce a usable result within its policy."""

    description = "A workflow stage failed, timed out, or returned the wrong contract after its deterministic retry policy was exhausted."
    expected = "A stage returns StageResult[StateT], or its StagePolicy declares an error_outcome that resolves to an explicit recovery route."
    remediation = "Inspect the chained stage exception, correct the stage/result adapter, adjust a justified retry/timeout policy, or declare an explicit handled error route."
    related_files = ("vidbyte/workflows/stages.py", "vidbyte/workflows/machine.py", "vidbyte/workflows/graph.py")


class WorkflowRoutingError(WorkflowExecutionError):
    """Raised when a semantic outcome or branch key has no declared destination."""

    description = "A stage, validator, guard, or router emitted a bounded code that the compiled graph does not map from the current source."
    expected = "Every runtime outcome that may occur has one declared direct transition or branch map entry; components never supply arbitrary target names."
    remediation = "Correct the emitted semantic code or add one explicit graph route from the reported source; do not add an implicit catch-all in the runtime."
    related_files = ("vidbyte/workflows/graph.py", "vidbyte/workflows/routing.py", "vidbyte/workflows/machine.py")


class TransitionLimitError(WorkflowExecutionError):
    """Raised when a run selects more transitions than its configured budget."""

    description = "The run exhausted max_transitions through cycles, retries encoded as routes, or guard redirect chains before reaching a terminal."
    expected = "Every selected transition consumes one budget unit so non-linear workflows remain bounded even when agents or validators repeat outcomes."
    remediation = "Inspect transition records for the repeating source/outcome pair, repair the stopping condition, or raise the limit only when the longer path is intentional."
    related_files: ClassVar[tuple[str, ...]] = ("vidbyte/workflows/machine.py", "vidbyte/workflows/contracts.py")


class WorkflowBudgetError(WorkflowExecutionError):
    """Raised when deterministic workflow resource accounting reaches a ceiling."""

    description = "A stage, root run, detour, or child graph exhausted a declared visit, step, call, token, cost, time, depth, or concurrency ceiling."
    expected = "Every resource-consuming boundary is charged before unsafe work begins, and a run stops rather than silently exceeding its configured economics."
    remediation = "Inspect the named counter and limit, repair a repeated route or right-size the explicit budget; never bypass accounting in a stage callback."
    related_files = ("vidbyte/workflows/budget.py", "vidbyte/workflows/machine.py", "vidbyte/workflows/subgraphs.py")


class WorkflowCommandError(WorkflowExecutionError):
    """Raised when a stage command conflicts with the compiled control contract."""

    description = "A WorkflowCommand selected conflicting control actions, wrote an undeclared channel, or requested a goto/send/detour operation unavailable from its source stage."
    expected = "One command may select exactly one primary control action, and every destination or child graph is declared statically on the compiled definition."
    remediation = "Remove conflicting fields or add the precise command transition/subgraph declaration; do not permit arbitrary runtime target names."
    related_files = ("vidbyte/workflows/contracts.py", "vidbyte/workflows/graph.py", "vidbyte/workflows/machine.py")


class WorkflowPersistenceError(WorkflowExecutionError):
    """Raised when canonical event or checkpoint persistence loses consistency."""

    description = "A workflow store rejected an append/checkpoint/definition, returned corrupt data, or observed an optimistic sequence conflict."
    expected = "Events are append-only, uniquely identified, monotonically sequenced, and checkpointed without rewriting prior workflow truth."
    remediation = "Inspect the store path/run ID/expected sequence, repair corrupt caller-owned data or serialize writers, then resume from the latest compatible boundary."
    related_files = ("vidbyte/workflows/persistence.py", "vidbyte/workflows/stores/memory.py", "vidbyte/workflows/stores/file.py")


class WorkflowResumeError(WorkflowExecutionError):
    """Raised when a stored run cannot resume at a compatible suspension boundary."""

    description = "The requested run is absent, finished, errored, running, unversioned, definition-incompatible, or missing the checkpoint/event evidence needed for resume."
    expected = "Only suspended runs resume against the exact definition, schema, reducer identities, request kind, and latest canonical sequence that created them."
    remediation = "Use inspect() to verify lifecycle and pending request, supply the original compatible machine/store, and respond with the current request ID."
    related_files: ClassVar[tuple[str, ...]] = ("vidbyte/workflows/machine.py", "vidbyte/workflows/projection.py", "vidbyte/workflows/persistence.py")


class WorkflowApprovalError(WorkflowResumeError):
    """Raised for stale, duplicate, mismatched, or invalid approval responses."""

    description = "A human confirmation response did not match the currently pending approval request or omitted the required approval decision."
    expected = "Approval responses reference exactly one active request, carry a boolean decision, and cannot select a graph target or be replayed."
    remediation = "Read result.pending, respond once with ResumeCommand.approve/reject using its request_id, and let the compiled edge choose continuation."
    related_files = ("vidbyte/workflows/approval.py", "vidbyte/workflows/machine.py", "vidbyte/workflows/contracts.py")


class WorkflowInterruptError(WorkflowResumeError):
    """Raised when an explicit stage interrupt cannot consume a resume value."""

    description = "A stage interrupt response was absent, had the wrong request ID/kind/schema, or no longer matched the replay ordinal reached by the stage."
    expected = "On replay, StageContext.interrupt consumes stored values in declaration order and suspends again only at the first unanswered ordinal."
    remediation = "Resume the active interrupt with ResumeCommand.resume and keep pre-interrupt external effects idempotent under the supplied key."
    related_files = ("vidbyte/workflows/contracts.py", "vidbyte/workflows/machine.py")


class WorkflowStuckError(WorkflowExecutionError):
    """Raised when deterministic agent loop evidence crosses a stuck threshold."""

    description = "The workflow-owned detector observed repeated action/results, action/errors, monologues, ping-pong actions, or context-window failures above policy."
    expected = "Loop fingerprints ignore volatile identifiers while preserving semantic content identity, and threshold breaches transition lifecycle to ERROR."
    remediation = "Inspect the safe pattern/fingerprint/count evidence, change the prompt/tool/result or route stopping condition, then start or resume intentionally."
    related_files = ("vidbyte/workflows/detection.py", "vidbyte/workflows/stages.py", "vidbyte/workflows/machine.py")


class WorkflowCapabilityError(WorkflowExecutionError):
    """Raised when a stage capability or action policy cannot be enforced safely."""

    description = "A stage requested tool visibility/model/action policy on an opaque stage, named an unknown or duplicate tool, or attempted an action denied by deterministic guards."
    expected = "Visible tools are resolved exactly before model invocation and action safety executes independently before every instrumented tool call."
    remediation = "Use AgentStage or another policy-aware stage, correct tool names/specs, or change the explicit capability/action policy after reviewing the denial evidence."
    related_files = ("vidbyte/workflows/capabilities.py", "vidbyte/workflows/stages.py", "vidbyte/workflows/graph.py")


class WorkflowDetourError(WorkflowExecutionError):
    """Raised when detour matching, depth, continuation, or return is invalid."""

    description = "A signal-triggered detour exceeded nesting, targeted an invalid stage, returned with an empty stack, or referenced a stale continuation."
    expected = "Detours enter through compiled rules, keep immutable frames, checkpoint boundaries, and return only through WorkflowCommand.return_from_detour."
    remediation = "Inspect the rule/frame/depth details, declare the correct target and return mode, or remove an invalid return command from an ordinary stage."
    related_files = ("vidbyte/workflows/detours.py", "vidbyte/workflows/graph.py", "vidbyte/workflows/machine.py")


class WorkflowSubgraphError(WorkflowExecutionError):
    """Raised when isolated child graph execution or deterministic joining fails."""

    description = "A Send referenced an unknown child, duplicated a key, exceeded recursion/concurrency/budget, failed mapping, suspended unexpectedly, or could not join safely."
    expected = "Each child has isolated state/events/checkpoints, a bounded budget, unique key/run ID, and summaries merged in input rather than completion order."
    remediation = "Inspect the child/key/policy details, correct mapping or budget declarations, and resume suspended children before retrying the parent join."
    related_files = ("vidbyte/workflows/subgraphs.py", "vidbyte/workflows/graph.py", "vidbyte/workflows/machine.py")


__all__ = [
    "StageExecutionError",
    "TransitionLimitError",
    "WorkflowDefinitionError",
    "WorkflowApprovalError",
    "WorkflowBudgetError",
    "WorkflowCapabilityError",
    "WorkflowCommandError",
    "WorkflowDetourError",
    "WorkflowError",
    "WorkflowErrorRecord",
    "WorkflowExecutionError",
    "WorkflowInterruptError",
    "WorkflowPersistenceError",
    "WorkflowResumeError",
    "WorkflowRoutingError",
    "WorkflowStateError",
    "WorkflowStuckError",
    "WorkflowSubgraphError",
    "WorkflowValidationError",
]
