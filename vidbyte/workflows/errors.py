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
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Inline smoke checks inspect error types and safe detail keys.
"""

from __future__ import annotations

from collections.abc import Mapping
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
    related_files = ("vidbyte/workflows/machine.py", "vidbyte/workflows/contracts.py")


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
    related_files = ("vidbyte/workflows/machine.py", "vidbyte/workflows/contracts.py")


__all__ = [
    "StageExecutionError",
    "TransitionLimitError",
    "WorkflowDefinitionError",
    "WorkflowError",
    "WorkflowExecutionError",
    "WorkflowRoutingError",
    "WorkflowStateError",
    "WorkflowValidationError",
]
