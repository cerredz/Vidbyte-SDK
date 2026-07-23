"""Context Protocol Header.

Path: vidbyte/agents/algorithms/specialist_panel.py
Purpose: Execute one producer and a review-only concurrent specialist panel.
Role: AgentRuntimeContextAlgorithms constructs SpecialistPanelRuntimeAlgorithm; the
    adapter runs the producer, delegates each lifecycle stage to a dedicated
    collaborator, and returns the producer-owned AgentResult with an attached report.
Collaborators: _ReviewerPlanner turns roles into isolated reviewer plans; _PanelExecutor
    runs the concurrent first round behind a single barrier; _ReviewValidator admits only
    schema-valid bounded reviews; _PanelReportAssembler orders outcomes and enforces the
    success threshold. Each subclasses _PanelStage and is composed into the main class.
Invariants: Preflight completes before fanout. Reviewer contexts are allowlist-built and
    contain no producer history, scratch state, middleware, implicit tools, or peer
    findings. Producer result fields remain authoritative.
Never: Copy prompt/evidence content into report or structural trace metadata, mutate
    producer runtime state for a reviewer, or aggregate before the first round ends.
Related: docs/design/context-window-specialist-panel.md and the public configuration
    in vidbyte/context/algorithms/specialist_panel.py.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import html
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from vidbyte.agents.contract import AgentLoopSettingsOutputContract
from vidbyte.context.algorithms.specialist_panel import SpecialistPanelAlgorithm, SpecialistRole
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ArtifactContextItem
from vidbyte.context.templates import NullRecorder
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, ContextArtifact
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.specialist_panel import SpecialistFailureRecord, SpecialistPanelReport, SpecialistReviewPayload, SpecialistReviewRecord
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import SpecialistPanelConfigurationError, SpecialistPanelExecutionError, SpecialistPanelStageError, SpecialistReviewError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolPermission

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime
    from vidbyte.tools.base import BaseTool


@dataclass(frozen=True, slots=True)
class _ReviewerPlan:
    """Fully validated reviewer boundary with no producer-context reference."""

    role: SpecialistRole
    runtime: AgentRuntime
    context: BaseAgentContext
    handle: RunnerHandle
    prompt: str
    provider: str
    model: str | None


class _PanelStage:
    """Shared base for panel collaborators bound to one producer runtime and config.

    Each concrete stage owns exactly one part of the panel lifecycle so the main
    algorithm stays a thin orchestrator; the shared base keeps the runtime reference
    and the single monotonic-duration helper every stage needs.
    """

    def __init__(self, runtime: AgentRuntime, algorithm: SpecialistPanelAlgorithm) -> None:
        # Retain the producer runtime and immutable panel configuration for the stage.
        self.runtime = runtime
        self.algorithm = algorithm

    def _elapsed_ms(self, started_at: float) -> int:
        # Convert the runtime's monotonic clock delta to a non-negative integer duration.
        return max(0, int((self.runtime.middleware.clock() - started_at) * 1000))


class _ReviewerPlanner(_PanelStage):
    """Resolve every role into a fully isolated, allowlist-built reviewer plan.

    This is the isolation core: it selects only the exact tools, artifacts, prompt,
    and provider each role declared, and constructs a fresh reviewer runtime and
    context that carry none of the producer's history, middleware, or scratch state.
    """

    def preflight(self, task: str, candidate: str, context: BaseAgentContext, handle: RunnerHandle, panel_id: str) -> tuple[_ReviewerPlan, ...]:
        # Resolve every role boundary before creating the first reviewer coroutine.
        artifact_index = self._artifact_index(context)
        return tuple(self._plan_reviewer(role, task, candidate, artifact_index, handle, panel_id) for role in self.algorithm.roles)

    def _artifact_index(self, context: BaseAgentContext) -> Mapping[str, tuple[ContextArtifact, ...]]:
        # Preserve duplicate names so requested ambiguous evidence can fail closed.
        indexed: dict[str, list[ContextArtifact]] = {}
        for artifact in context.artifacts:
            if not isinstance(artifact, ContextArtifact):
                raise SpecialistPanelConfigurationError(f"Specialist Panel artifacts must be ContextArtifact values; found {type(artifact).__name__}.")
            indexed.setdefault(artifact.name, []).append(artifact)
        return {name: tuple(items) for name, items in indexed.items()}

    def _plan_reviewer(self, role: SpecialistRole, task: str, candidate: str, artifact_index: Mapping[str, tuple[ContextArtifact, ...]], handle: RunnerHandle, panel_id: str) -> _ReviewerPlan:
        # Build one reviewer from positive tool, artifact, prompt, and provider allowlists.
        artifacts = self._select_artifacts(role, artifact_index)
        tools = self._select_tools(role)
        reviewer_handle, provider, model = self._resolve_handle(role, handle)
        # Render the isolation-critical system contract and exact-evidence user request.
        system_prompt = self.algorithm.reviewer_system_prompt_text(role)
        artifact_text = self._render_artifacts(artifacts)
        prompt = self.algorithm.render_reviewer_prompt(role, task=task, candidate=candidate, artifacts=artifact_text)
        # Construct the fresh runtime and context that hold no producer state.
        reviewer_runtime = self._build_reviewer_runtime(role, tools, system_prompt, panel_id)
        reviewer_context = self._build_reviewer_context(role, reviewer_runtime, artifacts, system_prompt, panel_id)
        return _ReviewerPlan(role=role, runtime=reviewer_runtime, context=reviewer_context, handle=reviewer_handle, prompt=prompt, provider=provider, model=model)

    def _select_artifacts(self, role: SpecialistRole, artifact_index: Mapping[str, tuple[ContextArtifact, ...]]) -> tuple[ContextArtifact, ...]:
        # Select exact artifact names, rejecting missing, ambiguous, or oversized evidence.
        selected: list[ContextArtifact] = []
        for name in role.artifact_names:
            matches = artifact_index.get(name, ())
            if not matches:
                raise SpecialistPanelConfigurationError(f"Specialist {role.specialist_id!r} requested missing artifact {name!r}.")
            if len(matches) != 1:
                raise SpecialistPanelConfigurationError(f"Specialist {role.specialist_id!r} requested ambiguous artifact {name!r}; found {len(matches)} exact-name matches.")
            artifact = matches[0]
            if len(artifact.content) > self.algorithm.max_artifact_chars:
                raise SpecialistPanelConfigurationError(f"Specialist {role.specialist_id!r} artifact {name!r} exceeds max_artifact_chars ({len(artifact.content)} > {self.algorithm.max_artifact_chars}).")
            selected.append(ContextArtifact(name=artifact.name, content=artifact.content, artifact_type=artifact.artifact_type))
        return tuple(selected)

    def _select_tools(self, role: SpecialistRole) -> Tools:
        # Clone the exact user-tool subset and enforce role-level mutation opt-in.
        selected = self.runtime.user_tools.subset(role.tool_names)
        cloned: list[BaseTool] = []
        for tool in selected.all():
            # Fork tools that support isolation cloning; otherwise reuse the stateless tool.
            clone = getattr(tool, "clone_for_fork", None)
            reviewer_tool = clone() if callable(clone) else tool
            if callable(getattr(reviewer_tool, "bind_agent", None)):
                raise SpecialistPanelConfigurationError(f"Specialist {role.specialist_id!r} tool {tool.name!r} requires a BaseAgent binding unavailable to isolated reviewer runtimes.")
            # A reviewer is review-only unless the role explicitly opts into mutation.
            permission = reviewer_tool.spec().permission
            if permission in (ToolPermission.WRITE, ToolPermission.EXECUTE) and not role.allow_mutating_tools:
                raise SpecialistPanelConfigurationError(f"Specialist {role.specialist_id!r} tool {tool.name!r} requires allow_mutating_tools=True for {permission.value!r} permission.")
            cloned.append(reviewer_tool)
        return Tools(cloned)

    def _resolve_handle(self, role: SpecialistRole, inherited: RunnerHandle) -> tuple[RunnerHandle, str, str | None]:
        # Inherit the producer handle or construct the role's validated text-model override.
        if role.provider is None or role.model is None:
            return inherited, inherited.provider, self.runtime._runner_model_name(inherited.runner)
        runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=role.provider, model=role.model)
        return inherited.with_runner(runner, role.provider), role.provider, role.model

    def _build_reviewer_runtime(self, role: SpecialistRole, tools: Tools, system_prompt: str, panel_id: str) -> AgentRuntime:
        # Construct isolated runtime state with no middleware, context manager, internal tool, or output contract.
        config = AgentRuntimeConfig(max_iterations=self.algorithm.reviewer_max_iterations, max_tokens=self.algorithm.reviewer_max_tokens, max_tool_calls=self.algorithm.reviewer_max_tool_calls, compaction_trigger_tokens=self.runtime.config.compaction_trigger_tokens, compaction_target_tokens=self.runtime.config.compaction_target_tokens)
        return type(self.runtime)(agent_name=f"{self.runtime.agent_name}:specialist:{role.specialist_id}", system_prompt=system_prompt, tools=tools, permission_policy=self.runtime.permission_policy, config=config, tracer=self.runtime._tracer, middleware=(), run_id=f"{panel_id}:reviewer:{role.specialist_id}", algorithm=None, context_manager=None, recorder=NullRecorder(), output_schema=SpecialistReviewPayload, output_contract=AgentLoopSettingsOutputContract(()), include_internal_tools=False)

    def _build_reviewer_context(self, role: SpecialistRole, runtime: AgentRuntime, artifacts: tuple[ContextArtifact, ...], system_prompt: str, panel_id: str) -> BaseAgentContext:
        # Positively construct the complete context so new producer fields cannot leak later.
        evidence = self._managed_evidence(artifacts)
        return BaseAgentContext(system_prompt=system_prompt, agent_name=runtime.agent_name, role=role.responsibility, history=(), file_paths=(), tools=runtime.user_tools.specs(), run_metadata={}, tool_calls=(), responses=(), budget=None, artifacts=evidence, memory=None, permissions=None, metadata={"algorithm": SpecialistPanelRuntimeAlgorithm.name, "panel_id": panel_id, "specialist_id": role.specialist_id}, context_items=())

    @staticmethod
    def _managed_evidence(artifacts: tuple[ContextArtifact, ...]) -> tuple[ContextArtifact, ...]:
        # Assemble the reviewer's allowed evidence through the SDK context-window manager
        # and its ArtifactContextItem primitives instead of hand-built dicts, so evidence
        # placement flows through vidbyte/context while the rendered content is unchanged.
        manager = ContextManager()
        manager.extend(ArtifactContextItem(name=artifact.name, content=artifact.content, artifact_type=artifact.artifact_type) for artifact in artifacts)
        return tuple(ContextArtifact(name=item.name, content=item.content, artifact_type=item.artifact_type) for item in manager.items())

    @staticmethod
    def _render_artifacts(artifacts: tuple[ContextArtifact, ...]) -> str:
        # Render exact selected artifact names and contents inside explicit evidence boundaries.
        if not artifacts:
            return "<allowed_artifacts>None permitted.</allowed_artifacts>"
        blocks = [f'<artifact name="{html.escape(artifact.name, quote=True)}" type="{html.escape(artifact.artifact_type, quote=True)}">\n{artifact.content}\n</artifact>' for artifact in artifacts]
        return "<allowed_artifacts>\n" + "\n".join(blocks) + "\n</allowed_artifacts>"


class _PanelExecutor(_PanelStage):
    """Run the independent reviewers concurrently behind one first-round barrier.

    This is the concurrency core: it launches every reviewer coroutine, waits for the
    whole round, and cancels the remainder only on cancellation or a process-level
    failure. Ordinary reviewer errors return as typed results, never as exceptions.
    """

    def __init__(self, runtime: AgentRuntime, algorithm: SpecialistPanelAlgorithm, validator: _ReviewValidator) -> None:
        # Compose the shared stage state with the validator that shapes each outcome.
        super().__init__(runtime, algorithm)
        self._validator = validator

    async def run_panel(self, plans: tuple[_ReviewerPlan, ...], panel_id: str, trace_context: SpanContext | None) -> tuple[SpecialistReviewRecord | SpecialistFailureRecord | BaseException, ...]:
        # Create the entire independent first round before awaiting its barrier.
        tasks = tuple(asyncio.create_task(self._run_reviewer(plan, panel_id, trace_context)) for plan in plans)
        pending = set(tasks)
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                # A terminal (cancellation / process-level) failure aborts the whole round.
                terminal = self._terminal_task_failure(done)
                if terminal is not None:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    raise terminal
            return tuple(task.result() for task in tasks)
        except BaseException:
            # Never leave reviewer coroutines running once the round is abandoned.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    @staticmethod
    def _terminal_task_failure(tasks: set[asyncio.Task[SpecialistReviewRecord | SpecialistFailureRecord]]) -> BaseException | None:
        # Return only cancellation or process-level failures; ordinary reviewer errors are typed results.
        for task in tasks:
            if task.cancelled():
                return asyncio.CancelledError()
            error = task.exception()
            if error is not None:
                return error
        return None

    async def _run_reviewer(self, plan: _ReviewerPlan, panel_id: str, trace_context: SpanContext | None) -> SpecialistReviewRecord | SpecialistFailureRecord:
        # Execute and validate one reviewer without touching any shared outcome collection.
        started_at = self.runtime.middleware.clock()
        span = self.runtime._start_semantic_span("algorithm.specialist_panel.reviewer", parent=trace_context, panel_id=panel_id, specialist_id=plan.role.specialist_id, tool_count=len(plan.role.tool_names), artifact_count=len(plan.role.artifact_names))
        try:
            # Bound each reviewer independently; a timeout is a typed failure, not a raise.
            result = await asyncio.wait_for(plan.runtime._arun_once(plan.prompt, handle=plan.handle, context=plan.context, metadata={"algorithm": SpecialistPanelRuntimeAlgorithm.name, "panel_id": panel_id, "specialist_id": plan.role.specialist_id}, options=self._mutable_json_mapping(plan.role.reviewer_options), trace_context=span or trace_context), timeout=self.algorithm.reviewer_timeout_seconds)
            record = self._validator.validate(plan, result, started_at)
            self.runtime._end_semantic_span(span, output="completed")
            return record
        except asyncio.TimeoutError:
            failure = self._validator.failure(plan.role, "timeout", f"review exceeded {self.algorithm.reviewer_timeout_seconds:g} seconds", started_at)
            self.runtime._end_semantic_span(span, error=TimeoutError(failure.safe_message))
            return failure
        except SpecialistReviewError as exc:
            failure = self._validator.failure(plan.role, exc.error_type, exc.safe_message, started_at)
            self.runtime._end_semantic_span(span, error=exc)
            return failure
        except asyncio.CancelledError as exc:
            # Cancellation propagates so the barrier can abandon the round deterministically.
            self.runtime._end_semantic_span(span, error=exc)
            raise
        except Exception as exc:
            # Any other execution error is content-free and recorded as a typed failure.
            failure = self._validator.failure(plan.role, "execution", f"review execution failed ({type(exc).__name__})", started_at)
            self.runtime._end_semantic_span(span, error=SpecialistPanelStageError(failure.safe_message))
            return failure

    @staticmethod
    def _mutable_json_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
        # Rehydrate defensively frozen reviewer options into provider-friendly JSON collections.
        return {key: _PanelExecutor._mutable_json_value(item) for key, item in value.items()}

    @staticmethod
    def _mutable_json_value(value: Any) -> Any:
        # Convert nested immutable mappings and tuples without introducing new values.
        if isinstance(value, Mapping):
            return _PanelExecutor._mutable_json_mapping(value)
        if isinstance(value, tuple):
            return [_PanelExecutor._mutable_json_value(item) for item in value]
        return value


class _ReviewValidator(_PanelStage):
    """Admit only schema-valid, bounded reviews covering every requirement exactly once.

    This is the trust core: it converts a raw reviewer AgentResult into a typed
    SpecialistReviewRecord, or classifies the rejection into a content-free failure,
    so no invalid or oversized model text ever reaches the panel report.
    """

    def validate(self, plan: _ReviewerPlan, result: AgentResult, started_at: float) -> SpecialistReviewRecord:
        # Admit only schema-valid, bounded reviews covering each configured output requirement exactly once.
        if result.structured is None:
            if result.output.strip():
                raise SpecialistReviewError("invalid_structured_output", "reviewer output did not validate against the fixed structured schema")
            raise SpecialistReviewError("missing_structured_output", "reviewer returned no structured output")
        try:
            payload = SpecialistReviewPayload.model_validate(result.structured)
        except ValidationError as exc:
            raise SpecialistReviewError("invalid_structured_output", "reviewer structured output did not match the fixed schema") from exc
        if len(payload.findings) > self.algorithm.max_findings_per_role:
            raise SpecialistReviewError("review_limit", f"review exceeded max_findings_per_role ({len(payload.findings)} > {self.algorithm.max_findings_per_role})")
        self._validate_assessments(plan.role, payload)
        review_chars = len(payload.model_dump_json())
        if review_chars > self.algorithm.max_review_chars:
            raise SpecialistReviewError("review_limit", f"serialized review exceeds max_review_chars ({review_chars} > {self.algorithm.max_review_chars})")
        # Only bounded accounting metadata is carried onto the typed record.
        result_metadata = dict(result.metadata)
        return SpecialistReviewRecord(specialist_id=plan.role.specialist_id, responsibility=plan.role.responsibility, provider=plan.provider, model=plan.model, tool_names=plan.role.tool_names, artifact_names=plan.role.artifact_names, output_requirements=plan.role.output_requirements, review=payload, tokens_used=self._optional_int(result_metadata.get("tokens_used")), model_call_count=max(1, int(result_metadata.get("iteration_count", 1) or 1)), tool_call_count=int(result_metadata.get("tool_call_count", 0) or 0), duration_ms=self._elapsed_ms(started_at))

    @staticmethod
    def _validate_assessments(role: SpecialistRole, payload: SpecialistReviewPayload) -> None:
        # Require a one-to-one normalized assessment for every trusted role requirement.
        expected = tuple(_ReviewValidator._normalize_requirement(item) for item in role.output_requirements)
        actual = tuple(_ReviewValidator._normalize_requirement(item.requirement) for item in payload.requirement_assessments)
        if len(actual) != len(set(actual)) or set(actual) != set(expected) or len(actual) != len(expected):
            raise SpecialistReviewError("invalid_structured_output", "requirement_assessments must cover each configured output requirement exactly once")

    def failure(self, role: SpecialistRole, error_type: str, safe_message: str, started_at: float) -> SpecialistFailureRecord:
        # Build a bounded content-free failure record from a stable internal category.
        return SpecialistFailureRecord(specialist_id=role.specialist_id, responsibility=role.responsibility, error_type=error_type, safe_message=safe_message[:500], duration_ms=self._elapsed_ms(started_at))  # type: ignore[arg-type]

    @staticmethod
    def _normalize_requirement(value: str) -> str:
        # Normalize whitespace and case solely for exact requirement-coverage comparison.
        return " ".join(value.split()).casefold()

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        # Normalize optional accounting metadata without admitting non-numeric values.
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None


class _PanelReportAssembler(_PanelStage):
    """Order the round's outcomes, enforce the threshold, and build the final report.

    This is the decision core: it preserves configured role order, re-raises only
    process-level failures, fails closed when too few reviews succeeded, and emits the
    bounded, role-provenanced report attached to the producer result.
    """

    def partition(self, plans: tuple[_ReviewerPlan, ...], outcomes: tuple[SpecialistReviewRecord | SpecialistFailureRecord | BaseException, ...]) -> tuple[tuple[SpecialistReviewRecord, ...], tuple[SpecialistFailureRecord, ...]]:
        # Preserve configured role order and propagate cancellation or process-level failures.
        reviews: list[SpecialistReviewRecord] = []
        failures: list[SpecialistFailureRecord] = []
        for plan, outcome in zip(plans, outcomes):
            if isinstance(outcome, SpecialistReviewRecord):
                reviews.append(outcome)
            elif isinstance(outcome, SpecialistFailureRecord):
                failures.append(outcome)
            elif isinstance(outcome, BaseException) and not isinstance(outcome, Exception):
                raise outcome
            else:
                failures.append(SpecialistFailureRecord(specialist_id=plan.role.specialist_id, responsibility=plan.role.responsibility, error_type="execution", safe_message=f"review execution failed ({type(outcome).__name__})", duration_ms=0))
        return tuple(reviews), tuple(failures)

    def enforce_threshold(self, reviews: tuple[SpecialistReviewRecord, ...], failures: tuple[SpecialistFailureRecord, ...]) -> None:
        # Fail closed unless the caller's explicit successful-review threshold was met.
        required = self.algorithm.effective_min_successful()
        if len(reviews) >= required:
            return
        failure_summary = ", ".join(f"{failure.specialist_id}:{failure.error_type}" for failure in failures)
        raise SpecialistPanelExecutionError(f"Specialist Panel produced {len(reviews)} successful reviews but requires {required}; failures: {failure_summary or 'none recorded'}.")

    def build_report(self, panel_id: str, candidate: str, reviews: tuple[SpecialistReviewRecord, ...], failures: tuple[SpecialistFailureRecord, ...], panel_started: float) -> SpecialistPanelReport:
        # Assemble the bounded, role-provenanced report; the candidate is hashed, never copied.
        return SpecialistPanelReport(schema_version=1, panel_id=panel_id, candidate_sha256=hashlib.sha256(candidate.encode("utf-8")).hexdigest(), configured_roles=tuple(role.specialist_id for role in self.algorithm.roles), min_successful=self.algorithm.effective_min_successful(), reviews=reviews, failures=failures, duration_ms=self._elapsed_ms(panel_started))


class SpecialistPanelRuntimeAlgorithm:
    """Run one producer and a concurrent, role-separated first review round."""

    name = "specialist_panel"

    def __init__(self, runtime: AgentRuntime, algorithm: SpecialistPanelAlgorithm) -> None:
        # Retain the producer runtime and immutable panel configuration, then wire the
        # lifecycle collaborators so arun() stays a thin, readable orchestrator.
        self.runtime = runtime
        self.algorithm = algorithm
        self._planner = _ReviewerPlanner(runtime, algorithm)
        self._validator = _ReviewValidator(runtime, algorithm)
        self._executor = _PanelExecutor(runtime, algorithm, self._validator)
        self._assembler = _PanelReportAssembler(runtime, algorithm)

    def run(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Synchronous entry point for callers outside an event loop; mirrors arun() exactly.
        return asyncio.run(self.arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context))

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Run one producer, fan out isolated specialists, then attach an ordered report.
        panel_started = self.runtime.middleware.clock()
        producer = await self._run_producer(message, handle, context, metadata, options, trace_context)
        # Guard the shared reviewer inputs and the report slot before any fanout begins.
        self._enforce_input_bounds(message, producer.output)
        self._reject_existing_report(producer)
        panel_id = self._panel_id()
        # Resolve every reviewer boundary, run the barrier, then aggregate deterministically.
        plans = self._planner.preflight(message, producer.output, context, handle, panel_id)
        outcomes = await self._executor.run_panel(plans, panel_id, trace_context)
        reviews, failures = self._assembler.partition(plans, outcomes)
        self._assembler.enforce_threshold(reviews, failures)
        report = self._assembler.build_report(panel_id, producer.output, reviews, failures, panel_started)
        # The producer result stays authoritative; only the report metadata slot is added.
        return dataclasses.replace(producer, metadata={**dict(producer.metadata), "specialist_panel": dict(report.to_metadata())})

    async def _run_producer(self, message: str, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        # Execute the producer exactly once while keeping the structural child span content-free.
        span = self.runtime._start_semantic_span("algorithm.specialist_panel.producer", parent=trace_context, stage="producer")
        try:
            result = await self.runtime._arun_once(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=span or trace_context)
            self.runtime._end_semantic_span(span, output="completed")
            return result
        except BaseException as exc:
            # The trace records only a content-free stage error; the original error re-raises.
            safe_error = SpecialistPanelStageError(f"producer execution failed ({type(exc).__name__})")
            self.runtime._end_semantic_span(span, error=safe_error)
            raise

    def _enforce_input_bounds(self, task: str, candidate: str) -> None:
        # Fail rather than truncate when either exact shared reviewer input exceeds its safeguard.
        if len(task) > self.algorithm.max_task_chars:
            raise SpecialistPanelExecutionError(f"Specialist Panel task exceeds max_task_chars ({len(task)} > {self.algorithm.max_task_chars}); increase the explicit safeguard or reduce the task.")
        if len(candidate) > self.algorithm.max_candidate_chars:
            raise SpecialistPanelExecutionError(f"Specialist Panel candidate exceeds max_candidate_chars ({len(candidate)} > {self.algorithm.max_candidate_chars}); increase the explicit safeguard or reduce the candidate.")

    @staticmethod
    def _reject_existing_report(producer: AgentResult) -> None:
        # Refuse to overwrite a report slot a prior stage already populated.
        if "specialist_panel" in dict(producer.metadata):
            raise SpecialistPanelExecutionError("Specialist Panel cannot overwrite existing AgentResult.metadata['specialist_panel']; use a fresh producer result.")

    def _panel_id(self) -> str:
        # Generate a lineage-friendly opaque identifier without exposing review content.
        prefix = self.runtime.run_id or self.runtime.agent_name
        return f"{prefix}:specialist-panel:{uuid.uuid4().hex[:8]}"


__all__ = ["SpecialistPanelRuntimeAlgorithm"]
