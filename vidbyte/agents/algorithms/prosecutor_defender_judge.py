"""Context Protocol Header

FILE: vidbyte/agents/algorithms/prosecutor_defender_judge.py
PURPOSE: Runs one producer and three strictly sequential, isolated debate roles,
then attaches a verdict without revising the producer candidate.
ROLE IN CODEBASE: AgentRuntimeContextAlgorithms dispatches this return-level
adapter; public settings and typed records live in the context/lib namespaces.
ARCHITECTURE NOTE: Every stage runtime and BaseAgentContext is built from a
positive projection. Only validated normalized records cross stage boundaries.
FUNCTION INVENTORY: The runtime adapter orchestrates the protocol; the factory
builds isolated runtimes; the projector grants resources; the validator owns
evidence, field-bound, ID-order, and judge-reason integrity.
WHAT NOT TO DO: Never copy producer context/options/middleware, append review
calls to producer accounting, forward raw stage transcripts, or revise output.
KNOWN EDGE CASES: Zero allegations still runs defender and judge; caller
cancellation always propagates; timeout is an ordinary stage failure.
RELATED DOCS: docs/design/context-window-prosecutor-defender-judge.md.
TEST FILES: No new tests are authorized by the approved no-tests design.
CONCURRENCY MODEL: Review roles are strictly sequential; asyncio.timeout owns
and awaits cancellation of the single active stage invocation.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from vidbyte.agents.hashing import hex_digest
from vidbyte.context.algorithms.prosecutor_defender_judge import DebateStageSettings, ProsecutorDefenderJudgeAlgorithm, ProsecutorDefenderJudgeFailurePolicy
from vidbyte.context.templates import NullRecorder
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.agents.prosecutor_defender_judge import dump_payload, json_safe_mapping, optional_int, runner_model_name, safe_error_category, safe_tool_call_summary, safe_trace_error
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, ContextArtifact
from vidbyte.lib.dataclasses.prosecutor_defender_judge import AllegationRecord, DebateStageRecord, DefenderReportPayload, DefenseRecord, EvidenceCitationPayload, EvidenceCitationRecord, EvidenceSource, JudgeDecision, JudgeDecisionRecord, JudgeReasonCode, JudgeReportPayload, ProsecutorDefenderJudgeReport, ProsecutorReportPayload
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCallContext, ToolPermission

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime

_ROLES = ("prosecutor", "defender", "judge")
_SURVIVING_REASONS = frozenset({JudgeReasonCode.SUPPORTED_UNREBUTTED, JudgeReasonCode.SUPPORTED_AFTER_REBUTTAL, JudgeReasonCode.CONCEDED})
_REJECTED_REASONS = frozenset({JudgeReasonCode.UNSUPPORTED, JudgeReasonCode.REBUTTED, JudgeReasonCode.DUPLICATE, JudgeReasonCode.OUT_OF_SCOPE})
_REJECTED_TOOL_CLASSES = frozenset({"AgentTool", "DynamicActorTool", "ForkConversationTool", "McpBridgedTool"})


class _DebateStageFailure(Exception):
    """Internal stage-labelled failure used to apply one public failure policy."""

    def __init__(self, role: str, phase: str, cause: Exception) -> None:
        # Retains role/phase provenance while leaving the original exception chained.
        super().__init__(f"{role} failed during {phase}: {type(cause).__name__}")
        self.role = role
        self.phase = phase
        self.cause = cause


@dataclass(frozen=True, slots=True)
class _PermittedArtifact:
    """Exact artifact value copied through a stage-specific allowlist."""

    name: str
    artifact_type: str
    content: str

    def to_dict(self) -> dict[str, str]:
        # Serializes only the three explicitly permitted artifact fields.
        return {"name": self.name, "artifact_type": self.artifact_type, "content": self.content}


@dataclass(frozen=True, slots=True)
class _StageProjection:
    """Positive capability projection for one isolated review role."""

    role: str
    settings: DebateStageSettings
    artifacts: tuple[_PermittedArtifact, ...]
    tools: Tools

    def artifact_bodies(self) -> dict[str, str]:
        # Returns exact artifact bodies keyed by their unambiguous names.
        return {artifact.name: artifact.content for artifact in self.artifacts}


class _StageInvocationCounter:
    """Wraps one stage handle and counts every provider invocation, including retries."""

    def __init__(self, inner: RunnerHandle) -> None:
        # Stores the isolated handle and initializes exact stage-local accounting.
        self.inner = inner
        self.count = 0

    async def invoke(self, runner: object, message: str, **options: Any) -> object:
        # Counts and delegates one invocation without copying any parent options.
        del runner
        self.count += 1
        return await self.inner.invoke(message, **options)

    def handle(self) -> RunnerHandle:
        # Exposes a normal RunnerHandle backed by the counting invocation boundary.
        return RunnerHandle(runner=self.inner.runner, provider=self.inner.provider, invoke=self.invoke, extract_text=self.inner.extract_text, extract_metadata=self.inner.extract_metadata)


@dataclass(frozen=True, slots=True)
class _StageExecution:
    """Fresh runtime, runner handle, context, and projection for one role."""

    projection: _StageProjection
    runtime: AgentRuntime
    handle: RunnerHandle
    context: BaseAgentContext
    provider: str
    model: str | None
    invocation_counter: _StageInvocationCounter


@dataclass(frozen=True, slots=True)
class _StageOutcome:
    """Validated stage result plus safe execution provenance."""

    execution: _StageExecution
    result: AgentResult
    duration_ms: float

    def tool_outputs(self) -> dict[str, tuple[str, ...]]:
        # Groups stage-local tool result bodies for exact citation validation.
        grouped: dict[str, list[str]] = {}
        for call in tuple(dict(self.result.metadata).get("tool_calls", ())):
            output = getattr(getattr(call, "result", None), "output", None)
            if output is not None:
                grouped.setdefault(str(getattr(call, "tool_name", "")), []).append(str(output))
        return {name: tuple(outputs) for name, outputs in grouped.items()}

    def stage_record(self) -> DebateStageRecord:
        # Reduces stage execution to content-free accounting and provenance.
        metadata = dict(self.result.metadata)
        calls = tuple(metadata.get("tool_calls", ()))
        summaries = tuple(safe_tool_call_summary(call) for call in calls)
        iterations = int(metadata.get("iteration_count", 0) or 0)
        return DebateStageRecord(role=self.execution.projection.role, status="completed", provider=self.execution.provider, model=self.execution.model, artifact_names=tuple(item.name for item in self.execution.projection.artifacts), tool_names=self.execution.projection.tools.names(), stop_reason=str(metadata.get("stop_reason")) if metadata.get("stop_reason") is not None else None, duration_ms=round(self.duration_ms, 3), iteration_count=iterations, model_call_count=self.execution.invocation_counter.count, tool_call_count=int(metadata.get("tool_call_count", len(calls)) or 0), tokens_used=optional_int(metadata.get("tokens_used")), tool_calls=summaries, metadata=json_safe_mapping(self.execution.projection.settings.metadata))


class DebateResourceProjector:
    """Builds exact artifact/tool capability subsets and rejects unsafe grants."""

    def __init__(self, algorithm: ProsecutorDefenderJudgeAlgorithm) -> None:
        # Stores shared exact-input limits used by all three projections.
        self.algorithm = algorithm

    def project(self, role: str, settings: DebateStageSettings, context: BaseAgentContext, tools: Tools) -> _StageProjection:
        # Creates one positive projection without copying any producer-private state.
        artifacts = self.project_artifacts(settings.artifact_names, context)
        projected_tools = self.project_tools(settings.tool_names, tools)
        return _StageProjection(role=role, settings=settings, artifacts=artifacts, tools=projected_tools)

    def project_artifacts(self, names: Sequence[str], context: BaseAgentContext) -> tuple[_PermittedArtifact, ...]:
        # Selects exact, unambiguous producer artifacts and enforces size bounds.
        projected: list[_PermittedArtifact] = []
        total_chars = 0
        for name in names:
            matches = tuple(artifact for artifact in context.artifacts if str(artifact.name) == name)
            if not matches:
                raise ConfigurationError(f"Permitted artifact {name!r} does not exist in producer context.")
            if len(matches) != 1:
                raise ConfigurationError(f"Permitted artifact {name!r} is ambiguous because producer context contains duplicates.")
            artifact = matches[0]
            if not isinstance(artifact, ContextArtifact) or not isinstance(artifact.content, str):
                raise ConfigurationError(f"Permitted artifact {name!r} must be a text ContextArtifact.")
            if len(artifact.content) > self.algorithm.max_artifact_chars:
                raise ConfigurationError(f"Permitted artifact {name!r} exceeds max_artifact_chars; exact review input cannot be truncated.")
            total_chars += len(artifact.content)
            if total_chars > self.algorithm.max_total_artifact_chars:
                raise ConfigurationError("Permitted artifacts exceed max_total_artifact_chars; exact review input cannot be truncated.")
            projected.append(_PermittedArtifact(name=name, artifact_type=str(artifact.artifact_type), content=artifact.content))
        return tuple(projected)

    def project_tools(self, names: Sequence[str], tools: Tools) -> Tools:
        # Selects exact safe/read tools, cloning only explicitly fork-safe instances.
        selected = tools.subset(names)
        projected = []
        for tool in selected:
            self._assert_tool_is_review_safe(tool)
            clone = getattr(tool, "clone_for_fork", None)
            projected_tool = clone() if callable(clone) else tool
            if callable(clone) and projected_tool is tool:
                raise ConfigurationError(f"Tool {tool.name!r} clone_for_fork() must return a distinct unbound tool.")
            self._assert_tool_is_review_safe(projected_tool)
            if projected_tool.name != tool.name:
                raise ConfigurationError(f"Tool {tool.name!r} clone_for_fork() changed its public name.")
            projected.append(projected_tool)
        return Tools(projected)

    def _assert_tool_is_review_safe(self, tool: object) -> None:
        # Rejects mutating, remote-bridge, delegation, and live-parent-bound tools.
        spec = tool.spec()  # type: ignore[attr-defined]
        if spec.permission not in (ToolPermission.SAFE, ToolPermission.READ):
            raise ConfigurationError(f"Review tool {spec.name!r} must declare SAFE or READ permission, not {spec.permission.value!r}.")
        if spec.binds_to_primitive is not None:
            raise ConfigurationError(f"Review tool {spec.name!r} is bound to live primitive {spec.binds_to_primitive!r}.")
        metadata = dict(spec.metadata)
        if metadata.get("source") == "mcp" or metadata.get("internal_agent_tool"):
            raise ConfigurationError(f"Review tool {spec.name!r} is a remote or agent-delegation capability and cannot be projected.")
        if tool.__class__.__name__ in _REJECTED_TOOL_CLASSES:
            raise ConfigurationError(f"Review tool {spec.name!r} uses unsupported live-bound type {tool.__class__.__name__}.")
        if callable(getattr(tool, "bind_agent", None)) or callable(getattr(tool, "bind_context_getter", None)):
            raise ConfigurationError(f"Review tool {spec.name!r} can bind live parent-agent state and cannot be projected.")


class DebateStageRuntimeFactory:
    """Constructs fresh role runtimes, handles, and minimal contexts."""

    def __init__(self, parent_runtime: AgentRuntime) -> None:
        # Retains only explicit shared transport authorities, not parent context state.
        self.parent_runtime = parent_runtime

    def build(self, projection: _StageProjection, schema: type[BaseModel], system_prompt: str, handle: RunnerHandle) -> _StageExecution:
        # Creates a fresh runtime/context with empty middleware and exact tools.
        from vidbyte.agents.runtime import AgentRuntime

        stage_handle, provider, model = self._stage_handle(projection.settings, handle)
        invocation_counter = _StageInvocationCounter(stage_handle)
        runtime = AgentRuntime(agent_name=f"{self.parent_runtime.agent_name}-{projection.role}", system_prompt=system_prompt, tools=projection.tools, permission_policy=self.parent_runtime.permission_policy, config=AgentRuntimeConfig(max_iterations=projection.settings.max_iterations, max_tokens=projection.settings.max_tokens, max_tool_calls=projection.settings.max_tool_calls), tracer=self.parent_runtime._tracer, middleware=(), run_id=None, algorithm=None, context_manager=None, recorder=NullRecorder(), output_schema=schema, output_contract=None, include_internal_tools=False)
        context = BaseAgentContext(system_prompt=system_prompt, history=(), file_paths=(), tools=projection.tools.specs(), run_metadata={}, tool_calls=(), responses=(), budget=None, artifacts=(), memory=None, permissions=None, metadata={}, context_items=())
        return _StageExecution(projection=projection, runtime=runtime, handle=invocation_counter.handle(), context=context, provider=provider, model=model, invocation_counter=invocation_counter)

    def _stage_handle(self, settings: DebateStageSettings, handle: RunnerHandle) -> tuple[RunnerHandle, str, str | None]:
        # Resolves inherited transport or creates a dedicated validated text runner.
        if settings.provider is None or settings.model is None:
            return handle, handle.provider, runner_model_name(handle.runner)
        runner = ModalityDetector.create_runner(ModelModality.TEXT, provider=settings.provider, model=settings.model)
        return handle.with_runner(runner, settings.provider), settings.provider, settings.model


class DebateTranscriptValidator:
    """Normalizes reports and enforces evidence and ordered-ID integrity."""

    def __init__(self, algorithm: ProsecutorDefenderJudgeAlgorithm, task: str, candidate: str) -> None:
        # Stores exact trusted source bodies and shared dynamic report limits.
        self.algorithm = algorithm
        self.task = task
        self.candidate = candidate

    def normalize_allegations(self, payload: ProsecutorReportPayload, projection: _StageProjection, tool_outputs: Mapping[str, tuple[str, ...]]) -> tuple[AllegationRecord, ...]:
        # Assigns SDK IDs after validating every allegation and citation source.
        self._assert_report_size(payload)
        self._assert_field(payload.summary, "prosecutor.summary", allow_empty=True)
        if len(payload.allegations) > self.algorithm.max_allegations:
            raise ValueError("Prosecutor returned more allegations than max_allegations.")
        records: list[AllegationRecord] = []
        for index, allegation in enumerate(payload.allegations, start=1):
            allegation_id = f"ALG-{index:03d}"
            self._assert_field(allegation.category, f"{allegation_id}.category")
            self._assert_field(allegation.claim, f"{allegation_id}.claim")
            self._assert_field(allegation.candidate_excerpt, f"{allegation_id}.candidate_excerpt", allow_empty=True)
            self._assert_field(allegation.recommended_fix, f"{allegation_id}.recommended_fix")
            if allegation.candidate_excerpt and allegation.candidate_excerpt not in self.candidate:
                raise ValueError(f"{allegation_id} candidate_excerpt is not an exact substring of the candidate.")
            evidence = self._normalize_evidence(allegation.evidence, projection, tool_outputs, allegation_id=None)
            records.append(AllegationRecord(allegation_id=allegation_id, severity=allegation.severity, category=allegation.category, claim=allegation.claim, candidate_excerpt=allegation.candidate_excerpt, evidence=evidence, recommended_fix=allegation.recommended_fix))
        return tuple(records)

    def normalize_defenses(self, payload: DefenderReportPayload, allegations: Sequence[AllegationRecord], projection: _StageProjection, tool_outputs: Mapping[str, tuple[str, ...]]) -> tuple[DefenseRecord, ...]:
        # Requires exactly one ordered, allegation-specific defense for every ID.
        self._assert_report_size(payload)
        expected = tuple(item.allegation_id for item in allegations)
        actual = tuple(item.allegation_id for item in payload.responses)
        self._assert_ordered_ids("defender", expected, actual)
        allegation_map = {item.allegation_id: item for item in allegations}
        records: list[DefenseRecord] = []
        for response in payload.responses:
            self._assert_field(response.response, f"{response.allegation_id}.defense.response")
            evidence = self._normalize_evidence(response.evidence, projection, tool_outputs, allegation_id=response.allegation_id, allegation=allegation_map[response.allegation_id])
            records.append(DefenseRecord(allegation_id=response.allegation_id, position=response.position, response=response.response, evidence=evidence))
        return tuple(records)

    def normalize_decisions(self, payload: JudgeReportPayload, allegations: Sequence[AllegationRecord], defenses: Sequence[DefenseRecord]) -> tuple[JudgeDecisionRecord, ...]:
        # Requires one ordered decision per pair and enforces reason-code polarity.
        self._assert_report_size(payload)
        expected = tuple(item.allegation_id for item in allegations)
        actual = tuple(item.allegation_id for item in payload.decisions)
        self._assert_ordered_ids("judge", expected, actual)
        if tuple(item.allegation_id for item in defenses) != expected:
            raise ValueError("Judge input defenses do not match canonical allegation order.")
        records: list[JudgeDecisionRecord] = []
        for decision in payload.decisions:
            self._assert_field(decision.rationale, f"{decision.allegation_id}.judge.rationale")
            allowed = _SURVIVING_REASONS if decision.decision is JudgeDecision.SURVIVES else _REJECTED_REASONS
            if decision.reason_code not in allowed:
                raise ValueError(f"Judge reason_code {decision.reason_code.value!r} is incompatible with decision {decision.decision.value!r}.")
            records.append(JudgeDecisionRecord(allegation_id=decision.allegation_id, decision=decision.decision, reason_code=decision.reason_code, rationale=decision.rationale))
        return tuple(records)

    def _normalize_evidence(self, citations: Sequence[EvidenceCitationPayload], projection: _StageProjection, tool_outputs: Mapping[str, tuple[str, ...]], allegation_id: str | None, allegation: AllegationRecord | None = None) -> tuple[EvidenceCitationRecord, ...]:
        # Validates citation cardinality, source authority, and exact excerpts.
        if len(citations) > self.algorithm.max_evidence_per_item:
            raise ValueError("Evidence citation count exceeds max_evidence_per_item.")
        records: list[EvidenceCitationRecord] = []
        for citation in citations:
            self._assert_field(citation.excerpt, "evidence.excerpt")
            self._assert_field(citation.support, "evidence.support")
            bodies = self._citation_bodies(citation, projection, tool_outputs, allegation_id, allegation)
            if not any(citation.excerpt in body for body in bodies):
                raise ValueError(f"Evidence excerpt is not an exact substring of permitted source {citation.source.value!r}.")
            records.append(EvidenceCitationRecord(source=citation.source, source_name=citation.source_name, excerpt=citation.excerpt, support=citation.support))
        return tuple(records)

    def _citation_bodies(self, citation: EvidenceCitationPayload, projection: _StageProjection, tool_outputs: Mapping[str, tuple[str, ...]], allegation_id: str | None, allegation: AllegationRecord | None) -> tuple[str, ...]:
        # Resolves only the exact source bodies authorized for the current stage.
        if citation.source is EvidenceSource.ORIGINAL_TASK:
            self._assert_canonical_source_name(citation.source_name, "original_task")
            return (self.task,)
        if citation.source is EvidenceSource.CANDIDATE:
            self._assert_canonical_source_name(citation.source_name, "candidate")
            return (self.candidate,)
        if citation.source is EvidenceSource.ARTIFACT:
            if citation.source_name not in projection.artifact_bodies():
                raise ValueError(f"Evidence cites unpermitted artifact {citation.source_name!r}.")
            return (projection.artifact_bodies()[str(citation.source_name)],)
        if citation.source is EvidenceSource.TOOL:
            if citation.source_name not in projection.tools.names():
                raise ValueError(f"Evidence cites unpermitted tool {citation.source_name!r}.")
            outputs = tuple(tool_outputs.get(str(citation.source_name), ()))
            if not outputs:
                raise ValueError(f"Evidence cites tool {citation.source_name!r} without a stage-local result.")
            return outputs
        if citation.source is EvidenceSource.ALLEGATION:
            if allegation_id is None or allegation is None or citation.source_name != allegation_id:
                raise ValueError("Defense allegation evidence must cite the matching allegation ID.")
            return (json.dumps(allegation.to_dict(), ensure_ascii=False, sort_keys=True), allegation.claim, allegation.candidate_excerpt, allegation.recommended_fix)
        raise ValueError(f"Unsupported evidence source: {citation.source!r}.")

    def _assert_report_size(self, payload: BaseModel) -> None:
        # Rejects oversized normalized reports before forwarding them downstream.
        serialized = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(serialized) > self.algorithm.max_stage_report_chars:
            raise ValueError("Structured stage report exceeds max_stage_report_chars.")

    def _assert_field(self, value: str, field_name: str, *, allow_empty: bool = False) -> None:
        # Enforces the caller-configured per-field bound without truncation.
        if not allow_empty and not value:
            raise ValueError(f"{field_name} must not be empty.")
        if len(value) > self.algorithm.max_field_chars:
            raise ValueError(f"{field_name} exceeds max_field_chars.")

    @staticmethod
    def _assert_ordered_ids(role: str, expected: tuple[str, ...], actual: tuple[str, ...]) -> None:
        # Rejects missing, duplicate, unknown, or reordered IDs with one exact check.
        if actual != expected:
            raise ValueError(f"{role} IDs must exactly match canonical allegation order; expected {expected}, got {actual}.")

    @staticmethod
    def _assert_canonical_source_name(source_name: str | None, canonical: str) -> None:
        # Allows null or the canonical label for singleton task/candidate sources.
        if source_name not in (None, canonical):
            raise ValueError(f"Source name for {canonical!r} must be null or {canonical!r}.")


class ProsecutorDefenderJudgeRuntimeAlgorithm:
    """Return-level runtime adapter for the verdict-only debate protocol."""

    name = "prosecutor_defender_judge"

    def __init__(self, runtime: AgentRuntime, algorithm: ProsecutorDefenderJudgeAlgorithm) -> None:
        # Stores immutable config and composes projector/factory responsibilities.
        self.runtime = runtime
        self.algorithm = algorithm
        self.projector = DebateResourceProjector(algorithm)
        self.factory = DebateStageRuntimeFactory(runtime)

    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Public dispatch entrypoint: produce one candidate, then hand the frozen
        # candidate to the isolated debate. arun owns only the producer pass and
        # the candidate fingerprint; run() owns the review protocol itself.

        # Record that the producer system prompt was assembled, then run the
        # ordinary producer loop exactly once with the caller's original runtime
        # state (tools, middleware, options, output contract) fully intact.
        self.runtime.recorder.append("system_prompt")
        producer = await self._run_producer(message, handle, context, metadata, options, trace_context)

        # Freeze the exact producer candidate and fingerprint it. This sha256 is
        # the referential anchor the review stages and returned metadata are bound
        # to; the candidate text is never revised, replaced, or re-generated after
        # this point.
        candidate = producer.output
        candidate_sha256 = hex_digest(candidate)
        self.runtime.recorder.append("prosecutor_defender_judge_candidate", candidate_sha256=candidate_sha256, candidate_chars=len(candidate))

        # Delegate the three strictly sequential review stages to run(). arun stays
        # thin so the producer contract and the review contract remain separable.
        return await self.run(message=message, candidate=candidate, candidate_sha256=candidate_sha256, producer=producer, context=context, handle=handle, trace_context=trace_context)

    async def run(self, *, message: str, candidate: str, candidate_sha256: str, producer: AgentResult, context: BaseAgentContext, handle: RunnerHandle, trace_context: SpanContext | None) -> AgentResult:
        # Executes the isolated prosecutor -> defender -> judge protocol against a
        # frozen candidate and returns either the attached verdict or, under the
        # configured failure policy, the untouched producer result.
        outcomes: list[_StageOutcome] = []
        try:
            # Preflight validates exact inputs and builds all three isolated stage
            # runtimes up front, so no review call happens until every stage can be
            # constructed. The validator holds the trusted task/candidate bodies.
            executions = self._preflight(message, candidate, context, handle)
            validator = DebateTranscriptValidator(self.algorithm, message, candidate)

            # Stage 1 (prosecutor): receives the task, exact candidate, and permitted
            # evidence, then emits typed allegations. Normalization assigns stable
            # SDK-owned allegation IDs and rejects any unsupported evidence citation.
            prosecutor_outcome = await self._run_stage(executions[0], self._prosecutor_payload(message, candidate, executions[0].projection), trace_context)
            allegations = validator.normalize_allegations(self._structured(prosecutor_outcome, ProsecutorReportPayload), prosecutor_outcome.execution.projection, prosecutor_outcome.tool_outputs())
            outcomes.append(prosecutor_outcome)
            self.runtime.recorder.append("prosecutor_defender_judge_prosecutor", allegation_count=len(allegations))

            # Stage 2 (defender): must answer every allegation exactly once, in order.
            # Normalization enforces the one-to-one ID mapping and blocks the defender
            # from introducing unrelated top-level defense claims.
            defender_outcome = await self._run_stage(executions[1], self._defender_payload(message, candidate, allegations, executions[1].projection), trace_context)
            defenses = validator.normalize_defenses(self._structured(defender_outcome, DefenderReportPayload), allegations, defender_outcome.execution.projection, defender_outcome.tool_outputs())
            outcomes.append(defender_outcome)
            self.runtime.recorder.append("prosecutor_defender_judge_defender", defense_count=len(defenses))

            # Stage 3 (judge): decides which allegation IDs survive. Normalization
            # requires one ordered decision per allegation/defense pair and forbids
            # the judge from inventing new findings.
            judge_outcome = await self._run_stage(executions[2], self._judge_payload(message, candidate, allegations, defenses, executions[2].projection), trace_context)
            decisions = validator.normalize_decisions(self._structured(judge_outcome, JudgeReportPayload), allegations, defenses)
            outcomes.append(judge_outcome)
            self.runtime.recorder.append("prosecutor_defender_judge_judge", decision_count=len(decisions))

            # Derive the overall verdict deterministically from the judge decisions
            # and attach it under producer.metadata without touching any other field.
            return self._successful_result(producer, candidate_sha256, allegations, defenses, decisions, outcomes)
        except _DebateStageFailure as failure:
            # A stage raised an already-labelled failure (preflight, timeout, stage
            # invocation, or malformed structured output). Apply the public policy.
            self.runtime.recorder.append("prosecutor_defender_judge_failure", failed_stage=failure.role, phase=failure.phase)
            return self._handle_failure(producer, candidate_sha256, failure, outcomes)
        except Exception as exc:
            # An inter-stage validation/normalization error escaped unlabelled;
            # attribute it to the stage that just completed and fail closed.
            failure = _DebateStageFailure(self._next_role(outcomes), "validation", exc)
            self.runtime.recorder.append("prosecutor_defender_judge_failure", failed_stage=failure.role, phase=failure.phase)
            return self._handle_failure(producer, candidate_sha256, failure, outcomes)

    async def _run_producer(self, message: str, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        # Calls the ordinary producer loop exactly once with original runtime state.
        span = self.runtime._start_semantic_span("algorithm.prosecutor_defender_judge.producer", parent=trace_context, stage="producer")
        try:
            result = await self.runtime._arun_once(message, handle=handle, context=context, metadata=metadata, options=dict(options or {}), trace_context=span or trace_context)
            self.runtime._end_semantic_span(span, output="completed")
            return result
        except BaseException as exc:
            self.runtime._end_semantic_span(span, error=safe_trace_error(exc))
            raise

    def _preflight(self, task: str, candidate: str, context: BaseAgentContext, handle: RunnerHandle) -> tuple[_StageExecution, ...]:
        # Validates exact inputs and constructs all three isolated stages before review.
        try:
            self._assert_exact_input(task, self.algorithm.max_task_chars, "original task")
            self._assert_exact_input(candidate, self.algorithm.max_candidate_chars, "candidate")
        except Exception as exc:
            raise _DebateStageFailure("prosecutor", "preflight", exc) from exc
        settings = (self.algorithm.prosecutor, self.algorithm.defender, self.algorithm.judge)
        schemas: tuple[type[BaseModel], ...] = (ProsecutorReportPayload, DefenderReportPayload, JudgeReportPayload)
        systems = (self.algorithm.prosecutor_system_prompt_text, self.algorithm.defender_system_prompt_text, self.algorithm.judge_system_prompt_text)
        executions: list[_StageExecution] = []
        for role, stage_settings, schema, system_loader in zip(_ROLES, settings, schemas, systems):
            try:
                projection = self.projector.project(role, stage_settings, context, self.runtime.user_tools)
                executions.append(self.factory.build(projection, schema, system_loader(), handle))
            except Exception as exc:
                raise _DebateStageFailure(role, "preflight", exc) from exc
        return tuple(executions)

    async def _run_stage(self, execution: _StageExecution, payload: Mapping[str, Any], trace_context: SpanContext | None) -> _StageOutcome:
        # Runs one isolated role under its timeout and closes its structural span.
        role = execution.projection.role
        prompt = self._render_stage_prompt(role, dump_payload(payload))
        span = self.runtime._start_semantic_span(f"algorithm.prosecutor_defender_judge.{role}", parent=trace_context, stage=role, provider=execution.provider, model=execution.model, artifact_names=tuple(item.name for item in execution.projection.artifacts), tool_names=execution.projection.tools.names(), candidate_sha256=hex_digest(str(payload.get("candidate", ""))), candidate_chars=len(str(payload.get("candidate", ""))))
        started = time.perf_counter()
        try:
            async with asyncio.timeout(execution.projection.settings.timeout_seconds):
                result = await execution.runtime._arun_once(prompt, handle=execution.handle, context=execution.context, metadata={"context_window_algorithm": self.name, "prosecutor_defender_judge_stage": role}, options={}, trace_context=span or trace_context)
            outcome = _StageOutcome(execution=execution, result=result, duration_ms=(time.perf_counter() - started) * 1000)
            self.runtime._end_semantic_span(span, output="completed")
            return outcome
        except asyncio.CancelledError:
            self.runtime._end_semantic_span(span, error=RuntimeError("CancelledError"))
            raise
        except Exception as exc:
            self.runtime._end_semantic_span(span, error=safe_trace_error(exc))
            raise _DebateStageFailure(role, "timeout" if isinstance(exc, TimeoutError) else "invocation", exc) from exc

    def _structured(self, outcome: _StageOutcome, schema: type[BaseModel]) -> Any:
        # Revalidates structured output and attributes malformed payloads to the role.
        role = outcome.execution.projection.role
        structured = outcome.result.structured
        if structured is None:
            raise _DebateStageFailure(role, "structured_output", ValueError("Stage result did not contain validated structured output."))
        try:
            if isinstance(structured, schema):
                return structured
            return schema.model_validate(structured)
        except (ValidationError, TypeError, ValueError) as exc:
            raise _DebateStageFailure(role, "structured_output", exc) from exc

    def _successful_result(self, producer: AgentResult, candidate_sha256: str, allegations: tuple[AllegationRecord, ...], defenses: tuple[DefenseRecord, ...], decisions: tuple[JudgeDecisionRecord, ...], outcomes: Sequence[_StageOutcome]) -> AgentResult:
        # Attaches the complete verdict report while preserving every producer field.
        survivors = tuple(item.allegation_id for item in decisions if item.decision is JudgeDecision.SURVIVES)
        report = ProsecutorDefenderJudgeReport(candidate_sha256=candidate_sha256, verdict="needs_changes" if survivors else "pass", surviving_allegation_ids=survivors, allegations=allegations, defenses=defenses, decisions=decisions, stages=tuple(outcome.stage_record() for outcome in outcomes), metadata=json_safe_mapping(self.algorithm.metadata))
        metadata = dict(producer.metadata)
        metadata[self.name] = report.to_dict()
        return dataclasses.replace(producer, metadata=metadata)

    def _handle_failure(self, producer: AgentResult, candidate_sha256: str, failure: _DebateStageFailure, outcomes: Sequence[_StageOutcome]) -> AgentResult:
        # Raises by default or returns the exact candidate with marked safe failure metadata.
        if self.algorithm.failure_policy is ProsecutorDefenderJudgeFailurePolicy.RAISE:
            raise AgentExecutionError(f"Prosecutor/Defender/Judge review failed at stage {failure.role!r} during {failure.phase}: {type(failure.cause).__name__}.", details={"algorithm": self.name, "failed_stage": failure.role, "phase": failure.phase, "error_type": type(failure.cause).__name__}) from failure.cause
        metadata = dict(producer.metadata)
        metadata[self.name] = self._failure_metadata(candidate_sha256, failure, outcomes)
        return dataclasses.replace(producer, metadata=metadata)

    def _failure_metadata(self, candidate_sha256: str, failure: _DebateStageFailure, outcomes: Sequence[_StageOutcome]) -> dict[str, Any]:
        # Builds a bounded no-verdict envelope that cannot imply later stages ran.
        completed = {outcome.execution.projection.role: outcome.stage_record().to_dict() for outcome in outcomes}
        stages: dict[str, Any] = {}
        for role, settings in zip(_ROLES, (self.algorithm.prosecutor, self.algorithm.defender, self.algorithm.judge)):
            stages[role] = completed.get(role, {"role": role, "status": "failed" if role == failure.role else "not_started", "artifact_names": list(settings.artifact_names), "tool_names": list(settings.tool_names)})
        message, truncated = self._bounded_failure_message(f"Review stage {failure.role} failed during {failure.phase}.")
        return {"schema_version": 1, "status": "review_failed", "reviewed": False, "review_only": True, "candidate_revised": False, "candidate_sha256": candidate_sha256, "failed_stage": failure.role, "failure_phase": failure.phase, "error_type": type(failure.cause).__name__, "error_category": safe_error_category(failure.cause), "error_message": message, "error_message_truncated": truncated, "stages": stages, "isolation": {"context_projection": "positive_allowlist", "producer_middleware_inherited": False, "producer_options_inherited": False, "internal_tools_included": False}, "metadata": json_safe_mapping(self.algorithm.metadata)}

    def _prosecutor_payload(self, task: str, candidate: str, projection: _StageProjection) -> dict[str, Any]:
        # Builds exactly the three prosecutor payload keys from permitted evidence.
        return {"original_task": task, "candidate": candidate, "permitted_artifacts": [item.to_dict() for item in projection.artifacts]}

    def _defender_payload(self, task: str, candidate: str, allegations: Sequence[AllegationRecord], projection: _StageProjection) -> dict[str, Any]:
        # Builds exactly the defender payload keys with normalized allegations.
        return {"original_task": task, "candidate": candidate, "allegations": [item.to_dict() for item in allegations], "permitted_artifacts": [item.to_dict() for item in projection.artifacts]}

    def _judge_payload(self, task: str, candidate: str, allegations: Sequence[AllegationRecord], defenses: Sequence[DefenseRecord], projection: _StageProjection) -> dict[str, Any]:
        # Builds exactly the judge payload keys with matched canonical records.
        return {"original_task": task, "candidate": candidate, "allegations": [item.to_dict() for item in allegations], "defenses": [item.to_dict() for item in defenses], "permitted_artifacts": [item.to_dict() for item in projection.artifacts]}

    def _render_stage_prompt(self, role: str, payload_json: str) -> str:
        # Routes one exact JSON payload through the role-specific prompt template.
        renderers = {"prosecutor": self.algorithm.render_prosecutor_prompt, "defender": self.algorithm.render_defender_prompt, "judge": self.algorithm.render_judge_prompt}
        return renderers[role](payload_json)

    def _bounded_failure_message(self, message: str) -> tuple[str, bool]:
        # Bounds the sanitized display message and returns an explicit truncation flag.
        if len(message) <= self.algorithm.max_failure_message_chars:
            return message, False
        suffix = "...[truncated]"
        kept = max(0, self.algorithm.max_failure_message_chars - len(suffix))
        return (message[:kept] + suffix)[: self.algorithm.max_failure_message_chars], True

    @staticmethod
    def _assert_exact_input(value: str, maximum: int, label: str) -> None:
        # Rejects oversized exact review input instead of silently truncating it.
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text.")
        if len(value) > maximum:
            raise ValueError(f"{label} exceeds its exact-input limit of {maximum} characters.")

    @staticmethod
    def _next_role(outcomes: Sequence[_StageOutcome]) -> str:
        # Attributes inter-stage validation failure to the stage just completed.
        return _ROLES[min(len(outcomes), len(_ROLES) - 1)]


__all__ = [
    "DebateResourceProjector",
    "DebateStageRuntimeFactory",
    "DebateTranscriptValidator",
    "ProsecutorDefenderJudgeRuntimeAlgorithm",
]
