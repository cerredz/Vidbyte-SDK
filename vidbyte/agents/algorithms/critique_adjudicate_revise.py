"""Context Protocol Header

FILE: vidbyte/agents/algorithms/critique_adjudicate_revise.py
PURPOSE: Orchestrates one producer, concurrent isolated critics, a reference-only
    adjudicator, and an accepted-findings-only revision worker. This file owns stage
    isolation and final result assembly; public schemas live in the context package.
ROLE IN CODEBASE: Constructed by vidbyte/agents/context_algorithms.py. It calls the
    existing AgentRuntime loop through fresh child runtimes, consumes public contracts
    from vidbyte/context/algorithms/critique_adjudicate_revise.py, and emits AgentResult.
ARCHITECTURE NOTE: Fresh object graphs and newly serialized envelopes enforce the trust
    boundary. Raw findings never share an object or envelope with the revision worker.
FUNCTION INVENTORY: CritiqueAdjudicateReviseRuntimeAlgorithm.arun / run are the public
    adapter entrypoints. Private orchestrator/leaf methods preflight access, fan out
    critics, execute isolated stages, enforce terminal policies, and assemble results.
COMMON MODIFICATION PATTERNS: Change stage data only in the corresponding envelope
    builder, parser contract, prompt asset, and metadata summary together.
WHAT NOT TO DO IN THIS FILE: 1. Do not derive child context from producer context.
    2. Do not pass producer middleware/history to child runtimes. 3. Do not forward raw
    critic or adjudicator prose to revision. 4. Do not retry stages with allowed tools.
KNOWN EDGE CASES: Critic completion order is nondeterministic but result order is not;
    cancellation propagates; degraded returns cannot undo prior tool side effects.
COMMON ERRORS: ConfigurationError covers preflight authority failures;
    AgentExecutionError covers quorum, stage, parsing, and structured-output failures.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/context-window-critique-adjudicate-revise.md
TESTS: Existing runtime/context regressions plus the approved manual deterministic probes.
CONCURRENCY MODEL: One fresh runtime/context per critic; gather is a full barrier; no
    recorder writes occur inside concurrent critic tasks.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms import ContextWindowAlgorithm
from vidbyte.context.algorithms.critique_adjudicate_revise import (
    AcceptedFinding,
    CriticFailurePolicy,
    CriticFinding,
    CritiqueAdjudicateReviseAlgorithm,
    ReviewStageAccess,
    StageFailurePolicy,
    _AdjudicationProjection,
)
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ArtifactContextItem
from vidbyte.context.templates import NullRecorder
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, ContextArtifact
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError, ToolRegistryError
from vidbyte.lib.tracing import SpanContext
from vidbyte.providers.output_schema import OutputSchemaFormatter
from vidbyte.tools.catalog import Tools

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime
    from vidbyte.trace.schema import SpanSpec


@dataclass(frozen=True, slots=True)
class _StageSpec:
    """All authority and execution settings for one isolated stage call."""

    stage: str
    system_prompt: str
    access: ReviewStageAccess
    timeout_seconds: float
    provider: str | None = None
    model: str | None = None
    critic_id: str | None = None


@dataclass(frozen=True, slots=True)
class _StageOutcome:
    """Sanitized stage accounting plus the complete internal AgentResult."""

    stage: str
    stage_id: str
    provider: str
    model: str | None
    elapsed_seconds: float
    result: AgentResult | None = None
    error_type: str | None = None
    captured_calls: tuple[ToolCallContext, ...] = ()

    @property
    def succeeded(self) -> bool:
        # Reports whether the stage returned a complete runtime result.
        return self.result is not None and self.error_type is None

    @property
    def calls(self) -> tuple[ToolCallContext, ...]:
        # Returns completed child tool contexts without exposing provider responses.
        if self.result is not None:
            calls = tuple(call for call in tuple(dict(self.result.metadata).get("tool_calls", ())) if isinstance(call, ToolCallContext))
            if calls:
                return calls
        return self.captured_calls

    @property
    def tokens_used(self) -> int:
        # Returns a stable numeric token count when the provider reported one.
        if self.result is None:
            return 0
        return int(dict(self.result.metadata).get("tokens_used", 0) or 0)

    @property
    def model_calls(self) -> int:
        # Uses completed runtime iterations as the direct-loop model-call count.
        if self.result is None:
            return 0
        return int(dict(self.result.metadata).get("iteration_count", 0) or 0)


@dataclass(frozen=True, slots=True)
class _ReviewPreflight:
    """Validated immutable producer sources and exact stage artifact payloads."""

    sources: Mapping[str, str]
    critic_artifacts: tuple[Mapping[str, str], ...]
    adjudicator_artifacts: tuple[Mapping[str, str], ...]
    revision_artifacts: tuple[Mapping[str, str], ...]


class CritiqueAdjudicateReviseRuntimeAlgorithm:
    """Return-level runtime adapter for critique-adjudicate-revise."""

    name = "critique_adjudicate_revise"
    _STAGE_OPTION_KEYS = frozenset({"frequency_penalty", "max_completion_tokens", "max_tokens", "presence_penalty", "seed", "temperature", "top_p"})
    _LIVE_BINDING_ATTRIBUTES = ("_context_getter", "_session", "_context", "context", "context_manager", "session")

    def __init__(self, runtime: AgentRuntime, algorithm: CritiqueAdjudicateReviseAlgorithm) -> None:
        # Stores the parent runtime and immutable policy for one dispatched run.
        self.runtime = runtime
        self.algorithm = algorithm
        self._schema_formatter = OutputSchemaFormatter()

    def run(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Synchronous entry point for callers outside an event loop; mirrors arun() exactly.
        return asyncio.run(self.arun(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=trace_context))

    # @intent accepted-findings-quarantine
    # Raw critic material is intentionally stopped at the adjudicator boundary. The
    # adjudicator returns references only, SDK code copies canonical source fields, and
    # revision receives a newly serialized accepted envelope. Reusing an earlier mapping,
    # context, or prompt here could silently expose rejected criticism to the worker.
    # Keep this method as a readable stage table of contents and keep every boundary in a
    # separate leaf method so future changes cannot blur authority between model roles.
    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Runs producer, full critic barrier, adjudication, and at most one revision.
        started_at = self.runtime.middleware.clock()
        outcomes: list[_StageOutcome] = []
        self.runtime.recorder.append("system_prompt")
        self.runtime.recorder.append("critique_adjudicate_revise_producer")
        try:
            producer = await self._run_producer(message, handle, context, metadata, options, trace_context)
            preflight = self._preflight(message, producer, context)
            critic_payload = self._critic_payload(message, producer.output, preflight.critic_artifacts)
            self.runtime.recorder.append("critique_adjudicate_revise_critic_fanout")
            critic_outcomes = await self._run_critics(critic_payload, handle, options, trace_context)
            self.runtime.recorder.append("critique_adjudicate_revise_critic_barrier")
            findings, critic_outcomes = self._parse_critic_outcomes(critic_outcomes, preflight.sources)
            outcomes.extend(critic_outcomes)
            successful_critics = sum(1 for outcome in critic_outcomes if outcome.succeeded)
            self._enforce_critic_policy(critic_outcomes, successful_critics)
            self.runtime.recorder.append("critique_adjudicate_revise_adjudication")
            projection, adjudication_outcome = await self._adjudicate(message, producer.output, findings, preflight.adjudicator_artifacts, handle, options, trace_context)
            outcomes.append(adjudication_outcome)
            if projection is None:
                self.runtime.recorder.append("critique_adjudicate_revise_failure", error_type=adjudication_outcome.error_type or "InvalidAdjudicationOutput")
                return self._degraded_result(producer, "degraded_adjudication_failure", outcomes, critic_outcomes, (), (), started_at, raw_finding_count=len(findings))
            if not projection.accepted:
                self.runtime.recorder.append("critique_adjudicate_revise_revision_skipped")
                return self._final_result(producer, producer.output, producer.structured, "unchanged_no_accepted_findings", outcomes, critic_outcomes, projection, (), started_at)
            self.runtime.recorder.append("critique_adjudicate_revise_revision")
            revision, structured, applied_ids, revision_outcome = await self._revise(message, producer.output, projection.accepted, preflight.revision_artifacts, handle, options, trace_context)
            outcomes.append(revision_outcome)
            if revision is None:
                self.runtime.recorder.append("critique_adjudicate_revise_failure", error_type=revision_outcome.error_type or "InvalidRevisionOutput")
                return self._degraded_result(producer, "degraded_revision_failure", outcomes, critic_outcomes, projection.accepted, (), started_at, projection=projection)
            return self._final_result(producer, revision, structured, "revised", outcomes, critic_outcomes, projection, applied_ids, started_at)
        except asyncio.CancelledError:
            self.runtime.recorder.append("critique_adjudicate_revise_failure", error_type="CancelledError")
            raise
        except BaseException as exc:
            self.runtime.recorder.append("critique_adjudicate_revise_failure", error_type=type(exc).__name__)
            raise

    async def _run_producer(self, message: str, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> AgentResult:
        # Executes exactly one normal producer attempt with the caller's original state.
        from vidbyte.trace.components.algorithms import AlgorithmTrace

        producer_spec = AlgorithmTrace.critique_adjudicate_revise_producer(stage="producer", task_hash=self._content_hash(message))
        span = self.runtime._start_semantic_span(producer_spec.name, parent=trace_context, **dict(producer_spec.attributes))
        try:
            result = await self.runtime._arun_once(message, handle=handle, context=context, metadata=metadata, options=options, trace_context=span or trace_context)
            self.runtime._end_semantic_span(span, output="succeeded")
            return result
        except BaseException as exc:
            self.runtime._end_semantic_span(span, error=self._sanitized_error(exc))
            raise

    def _preflight(self, message: str, producer: AgentResult, context: BaseAgentContext) -> _ReviewPreflight:
        # Validates exact candidate size, artifact identity, tool authority, and stage bounds.
        if len(producer.output) > self.algorithm.max_candidate_chars:
            raise ConfigurationError("Producer candidate exceeds max_candidate_chars; critique-adjudicate-revise never truncates candidates.", details={"candidate_chars": len(producer.output), "maximum": self.algorithm.max_candidate_chars})
        artifacts = self._artifact_index(context.artifacts)
        critic_artifacts = self._select_artifacts(self.algorithm.critic_access, artifacts, "critic")
        adjudicator_artifacts = self._select_artifacts(self.algorithm.adjudicator_access, artifacts, "adjudicator")
        revision_artifacts = self._select_artifacts(self.algorithm.revision_access, artifacts, "revision")
        for stage, access in (("critic", self.algorithm.critic_access), ("adjudicator", self.algorithm.adjudicator_access), ("revision", self.algorithm.revision_access)):
            self._preflight_tools(stage, access)
        sources = {"original_task": message, "candidate": producer.output, **{str(artifact["name"]): str(artifact["content"]) for artifact in critic_artifacts}}
        return _ReviewPreflight(sources=sources, critic_artifacts=critic_artifacts, adjudicator_artifacts=adjudicator_artifacts, revision_artifacts=revision_artifacts)

    def _artifact_index(self, artifacts: Sequence[ContextArtifact]) -> dict[str, ContextArtifact]:
        # Rejects duplicate source names because exact-name admission would be ambiguous.
        indexed: dict[str, ContextArtifact] = {}
        duplicates: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, ContextArtifact):
                raise ConfigurationError("Producer context artifacts must use ContextArtifact records.", details={"actual_type": type(artifact).__name__})
            if not isinstance(artifact.name, str) or not artifact.name.strip():
                raise ConfigurationError("Producer artifacts must have non-empty string names.")
            if not isinstance(artifact.content, str):
                raise ConfigurationError("Producer artifact content must be exact text.", details={"artifact_name": artifact.name, "actual_type": type(artifact.content).__name__})
            if not isinstance(artifact.artifact_type, str) or not artifact.artifact_type.strip():
                raise ConfigurationError("Producer artifact types must be non-empty strings.", details={"artifact_name": artifact.name})
            if artifact.name in {"original_task", "candidate"}:
                raise ConfigurationError("Producer artifact name collides with a reserved review source.", details={"artifact_name": artifact.name})
            if artifact.name in indexed:
                duplicates.add(artifact.name)
            indexed[artifact.name] = artifact
        if duplicates:
            raise ConfigurationError("Producer context contains duplicate artifact names.", details={"duplicate_names": tuple(sorted(duplicates))})
        return indexed

    def _select_artifacts(self, access: ReviewStageAccess, artifacts: Mapping[str, ContextArtifact], stage: str) -> tuple[Mapping[str, str], ...]:
        # Copies only explicitly named artifact content through ContextManager primitives.
        missing = tuple(name for name in access.allowed_artifact_names if name not in artifacts)
        if missing:
            raise ConfigurationError(f"{stage} artifact allowlist references missing names.", details={"stage": stage, "missing_names": missing})
        selected = tuple(artifacts[name] for name in access.allowed_artifact_names)
        managed = self._managed_artifacts(selected)
        return tuple({"name": artifact.name, "artifact_type": artifact.artifact_type, "content": artifact.content} for artifact in managed)

    def _managed_artifacts(self, artifacts: Sequence[ContextArtifact]) -> tuple[ContextArtifact, ...]:
        # Assemble allowlisted evidence through ContextManager + ArtifactContextItem so
        # context-window placement flows through vidbyte/context abstractions.
        manager = ContextManager()
        manager.extend(ArtifactContextItem(name=artifact.name, content=artifact.content, artifact_type=artifact.artifact_type) for artifact in artifacts)
        managed: list[ContextArtifact] = []
        for item in manager.items():
            if not isinstance(item, ArtifactContextItem):
                continue
            managed.append(ContextArtifact(name=item.name, content=item.content, artifact_type=item.artifact_type))
        return tuple(managed)

    def _preflight_tools(self, stage: str, access: ReviewStageAccess) -> None:
        # Proves every tool name exists and every live-bound tool can be safely cloned.
        try:
            selected = self.runtime.user_tools.subset(access.allowed_tool_names)
        except ToolRegistryError as exc:
            raise ConfigurationError(f"{stage} tool allowlist references an unavailable tool.", details={"stage": stage, "error_type": type(exc).__name__}) from exc
        for tool in selected:
            clone = getattr(tool, "clone_for_fork", None)
            if callable(clone):
                try:
                    cloned = clone()
                except Exception as exc:
                    raise ConfigurationError(f"{stage} tool clone_for_fork failed during isolation preflight.", details={"stage": stage, "tool_name": tool.name, "error_type": type(exc).__name__}) from exc
                if cloned is tool:
                    raise ConfigurationError(f"{stage} tool clone_for_fork returned the live producer object.", details={"stage": stage, "tool_name": tool.name})
                continue
            if self._has_live_binding(tool):
                raise ConfigurationError(f"{stage} tool carries a live binding and has no clone_for_fork isolation hook.", details={"stage": stage, "tool_name": tool.name})

    def _has_live_binding(self, tool: object) -> bool:
        # Conservatively detects common producer, context, and session binding fields.
        return any(getattr(tool, attribute, None) is not None for attribute in self._LIVE_BINDING_ATTRIBUTES)

    def _critic_payload(self, message: str, candidate: str, artifacts: Sequence[Mapping[str, str]]) -> str:
        # Serializes one immutable critic envelope reused byte-for-byte by every reviewer.
        return self._serialize_envelope({"schema_version": 1, "algorithm": self.name, "stage": "critic", "original_task": message, "candidate": candidate, "artifacts": list(artifacts)}, "critic")

    async def _run_critics(self, payload: str, handle: RunnerHandle, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> tuple[_StageOutcome, ...]:
        # Schedules all critic coroutines before awaiting the full result barrier.
        tasks = tuple(asyncio.create_task(self._stage_outcome(self._critic_spec(index), payload, handle, options, trace_context), name=f"critique-adjudicate-revise-critic-{index:03d}") for index in range(1, self.algorithm.critic_count + 1))
        try:
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        outcomes: list[_StageOutcome] = []
        for index, result in enumerate(gathered, start=1):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                outcomes.append(self._failed_outcome(self._critic_spec(index), handle, result))
            else:
                outcomes.append(result)
        return tuple(outcomes)

    def _critic_spec(self, index: int) -> _StageSpec:
        # Builds one identity-stable critic specification with shared instructions.
        return _StageSpec(stage="critic", critic_id=f"critic-{index:03d}", system_prompt=self.algorithm.critic_system_prompt_text(), access=self.algorithm.critic_access, timeout_seconds=self.algorithm.critic_timeout_seconds, provider=self.algorithm.critic_provider, model=self.algorithm.critic_model)

    def _parse_critic_outcomes(self, outcomes: Sequence[_StageOutcome], sources: Mapping[str, str]) -> tuple[tuple[CriticFinding, ...], tuple[_StageOutcome, ...]]:
        # Parses successful outputs after the barrier and records parser failures structurally.
        findings: list[CriticFinding] = []
        parsed_outcomes: list[_StageOutcome] = []
        for outcome in outcomes:
            if not outcome.succeeded or outcome.result is None:
                parsed_outcomes.append(outcome)
                continue
            try:
                parsed = self.algorithm.parse_critic_output(outcome.stage_id, outcome.result.output, sources, outcome.calls)
            except BaseException as exc:
                parsed_outcomes.append(dataclasses.replace(outcome, error_type=type(exc).__name__))
                continue
            findings.extend(parsed)
            parsed_outcomes.append(outcome)
        return tuple(findings), tuple(parsed_outcomes)

    def _enforce_critic_policy(self, outcomes: Sequence[_StageOutcome], successful: int) -> None:
        # Fails only after the barrier when all-required or quorum policy is unmet.
        required = self.algorithm.critic_count if self.algorithm.critic_failure_policy is CriticFailurePolicy.REQUIRE_ALL else int(self.algorithm.min_successful_critics or 0)
        if successful >= required:
            return
        failures = tuple({"critic_id": outcome.stage_id, "error_type": outcome.error_type or "InvalidCriticOutput"} for outcome in outcomes if not outcome.succeeded)
        raise AgentExecutionError("critique-adjudicate-revise critic policy was not satisfied after the full barrier.", details={"required": required, "successful": successful, "failures": failures})

    async def _adjudicate(self, message: str, candidate: str, findings: Sequence[CriticFinding], artifacts: Sequence[Mapping[str, str]], handle: RunnerHandle, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> tuple[_AdjudicationProjection | None, _StageOutcome]:
        # Runs reference-only adjudication and applies the configured terminal policy.
        payload = self._serialize_envelope({"schema_version": 1, "algorithm": self.name, "stage": "adjudicator", "original_task": message, "candidate": candidate, "raw_findings": [self._finding_payload(finding) for finding in findings], "artifacts": list(artifacts)}, "adjudicator")
        spec = _StageSpec(stage="adjudicator", system_prompt=self.algorithm.adjudicator_system_prompt_text(), access=self.algorithm.adjudicator_access, timeout_seconds=self.algorithm.adjudication_timeout_seconds, provider=self.algorithm.adjudicator_provider, model=self.algorithm.adjudicator_model)
        outcome = await self._stage_outcome(spec, payload, handle, options, trace_context)
        if outcome.succeeded and outcome.result is not None:
            try:
                return self.algorithm.validate_adjudication(outcome.result.output, findings), outcome
            except BaseException as exc:
                outcome = dataclasses.replace(outcome, error_type=type(exc).__name__)
        if self.algorithm.adjudication_failure_policy is StageFailurePolicy.RETURN_CANDIDATE:
            return None, outcome
        raise AgentExecutionError("critique-adjudicate-revise adjudication failed.", details={"stage": "adjudicator", "error_type": outcome.error_type or "InvalidAdjudicationOutput"})

    async def _revise(self, message: str, candidate: str, accepted: Sequence[AcceptedFinding], artifacts: Sequence[Mapping[str, str]], handle: RunnerHandle, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> tuple[str | None, Any, tuple[str, ...], _StageOutcome]:
        # Runs a fresh worker over accepted findings only and validates its final contract.
        payload = self._serialize_envelope({"schema_version": 1, "algorithm": self.name, "stage": "revision", "original_task": message, "candidate": candidate, "accepted_findings": [self._accepted_payload(finding) for finding in accepted], "artifacts": list(artifacts)}, "revision")
        spec = _StageSpec(stage="revision", system_prompt=self.algorithm.reviser_system_prompt_text(), access=self.algorithm.revision_access, timeout_seconds=self.algorithm.revision_timeout_seconds, provider=self.algorithm.revision_provider, model=self.algorithm.revision_model)
        outcome = await self._stage_outcome(spec, payload, handle, options, trace_context)
        if outcome.succeeded and outcome.result is not None:
            try:
                revised, applied_ids = self.algorithm.parse_revision_output(outcome.result.output, accepted)
                structured = self._validate_structured_revision(revised)
                return revised, structured, applied_ids, outcome
            except BaseException as exc:
                outcome = dataclasses.replace(outcome, error_type=type(exc).__name__)
        if self.algorithm.revision_failure_policy is StageFailurePolicy.RETURN_CANDIDATE:
            return None, None, (), outcome
        raise AgentExecutionError("critique-adjudicate-revise revision failed.", details={"stage": "revision", "error_type": outcome.error_type or "InvalidRevisionOutput"})

    async def _stage_outcome(self, spec: _StageSpec, payload: str, handle: RunnerHandle, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> _StageOutcome:
        # Converts one non-cancel stage failure into sanitized accounting for policy handling.
        started_at = self.runtime.middleware.clock()
        captured_calls: list[ToolCallContext] = []
        try:
            return await self._execute_stage(spec, payload, handle, options, trace_context, captured_calls)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            return self._failed_outcome(spec, handle, exc, max(0.0, self.runtime.middleware.clock() - started_at), tuple(captured_calls))

    async def _execute_stage(self, spec: _StageSpec, payload: str, handle: RunnerHandle, options: Mapping[str, Any] | None, trace_context: SpanContext | None, captured_calls: list[ToolCallContext]) -> _StageOutcome:
        # Constructs a fresh runtime/context and bounds the complete child loop by timeout.
        started_at = self.runtime.middleware.clock()
        stage_handle = self._stage_handle(spec, handle)
        stage_trace = self._stage_trace_spec(spec, stage_handle)
        span = self.runtime._start_semantic_span(stage_trace.name, parent=trace_context, **dict(stage_trace.attributes))
        try:
            stage_runtime = self._build_stage_runtime(spec, captured_calls)
            stage_context = self._build_stage_context(stage_runtime)
            result = await asyncio.wait_for(stage_runtime._arun_once(payload, handle=stage_handle, context=stage_context, metadata=self._stage_metadata(spec), options=self._stage_options(options), trace_context=span or trace_context), timeout=spec.timeout_seconds)
            elapsed = max(0.0, self.runtime.middleware.clock() - started_at)
            result = dataclasses.replace(result, calls=self._annotated_calls(result, spec, stage_handle))
            self.runtime._end_semantic_span(span, output="succeeded")
            return _StageOutcome(stage=spec.stage, stage_id=spec.critic_id or spec.stage, provider=stage_handle.provider, model=self._model_name(spec, stage_handle), elapsed_seconds=elapsed, result=result, captured_calls=tuple(captured_calls))
        except BaseException as exc:
            self.runtime._end_semantic_span(span, error=self._sanitized_error(exc))
            raise

    def _stage_trace_spec(self, spec: _StageSpec, handle: RunnerHandle) -> SpanSpec:
        # Maps each stage to its dedicated AlgorithmTrace factory for semantic spans.
        # Lazy import avoids a package cycle through vidbyte.trace during agent bootstrap.
        from vidbyte.trace.components.algorithms import AlgorithmTrace

        attributes = {
            "stage": spec.stage,
            "stage_id": spec.critic_id or spec.stage,
            "provider": handle.provider,
            "model": self._model_name(spec, handle),
        }
        if spec.stage == "critic":
            return AlgorithmTrace.critique_adjudicate_revise_critic(**attributes)
        if spec.stage == "adjudicator":
            return AlgorithmTrace.critique_adjudicate_revise_adjudicator(**attributes)
        if spec.stage == "revision":
            return AlgorithmTrace.critique_adjudicate_revise_revision(**attributes)
        return AlgorithmTrace.critique_adjudicate_revise(**attributes)

    def _build_stage_runtime(self, spec: _StageSpec, captured_calls: list[ToolCallContext]) -> AgentRuntime:
        # Builds an empty-middleware, no-history runtime with an exact cloned tool subset.
        selected = self.runtime.user_tools.subset(spec.access.allowed_tool_names)
        cloned_tools = Tools(self._clone_stage_tool(tool, spec.stage) for tool in selected)
        config = AgentRuntimeConfig(max_iterations=spec.access.max_iterations, max_tool_calls=spec.access.max_tool_calls, tool_settings=self.runtime.config.tool_settings)
        return self.runtime.__class__(agent_name=f"{self.runtime.agent_name}:{spec.critic_id or spec.stage}", system_prompt=spec.system_prompt, tools=cloned_tools, permission_policy=self.runtime.permission_policy, config=config, tracer=self.runtime._tracer, middleware=(), run_id=self._stage_run_id(spec), algorithm=ContextWindowAlgorithm(name="default"), context_manager=ContextManager(), recorder=NullRecorder(), output_schema=None, include_internal_tools=False, _tool_call_observer=captured_calls.append)

    def _clone_stage_tool(self, tool: object, stage: str) -> object:
        # Clones tools with explicit fork hooks and rejects live-bound shared objects.
        clone = getattr(tool, "clone_for_fork", None)
        if callable(clone):
            try:
                cloned = clone()
            except Exception as exc:
                raise ConfigurationError(f"{stage} tool clone_for_fork failed while constructing an isolated stage.", details={"stage": stage, "tool_name": getattr(tool, "name", type(tool).__name__), "error_type": type(exc).__name__}) from exc
            if cloned is tool:
                raise ConfigurationError(f"{stage} tool clone_for_fork returned the producer object.", details={"stage": stage, "tool_name": getattr(tool, "name", type(tool).__name__)})
            return cloned
        if self._has_live_binding(tool):
            raise ConfigurationError(f"{stage} tool cannot cross the review boundary with a live binding.", details={"stage": stage, "tool_name": getattr(tool, "name", type(tool).__name__)})
        return tool

    def _build_stage_context(self, stage_runtime: AgentRuntime) -> BaseAgentContext:
        # Creates context from the role prompt and a fresh ContextManager without producer state.
        stage_manager = ContextManager()
        return stage_runtime.build_context("", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=(), input_metadata=None, modality=None, agentic_loop=False, context_items=(), context_manager=stage_manager)

    def _stage_handle(self, spec: _StageSpec, handle: RunnerHandle) -> RunnerHandle:
        # Reuses the caller handle unless the stage explicitly selects a provider/model.
        if spec.provider is None or spec.model is None:
            return handle
        runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=spec.provider, model=spec.model)
        return handle.with_runner(runner, spec.provider)

    def _stage_options(self, options: Mapping[str, Any] | None) -> dict[str, Any]:
        # Copies only inert generation controls, excluding caller prompt/history extensions.
        return {key: value for key, value in dict(options or {}).items() if key in self._STAGE_OPTION_KEYS}

    def _stage_metadata(self, spec: _StageSpec) -> dict[str, Any]:
        # Supplies content-free identifiers for accounting without model-visible producer state.
        return {"context_window_algorithm": self.name, "review_stage": spec.stage, "review_stage_id": spec.critic_id or spec.stage}

    def _stage_run_id(self, spec: _StageSpec) -> str | None:
        # Derives an optional lineage ID without exposing task or candidate content.
        if self.runtime.run_id is None:
            return None
        return f"{self.runtime.run_id}:critique-adjudicate-revise:{spec.critic_id or spec.stage}"

    def _annotated_calls(self, result: AgentResult, spec: _StageSpec, handle: RunnerHandle) -> tuple[ToolCallContext, ...]:
        # Labels completed child tool contexts with stable algorithm/stage provenance.
        calls = tuple(call for call in tuple(dict(result.metadata).get("tool_calls", ())) if isinstance(call, ToolCallContext))
        return tuple(dataclasses.replace(call, metadata={**dict(call.metadata), "context_window_algorithm": self.name, "review_stage": spec.stage, "review_stage_id": spec.critic_id or spec.stage}, provider=call.provider or handle.provider, model=call.model or self._model_name(spec, handle)) for call in calls)

    def _failed_outcome(self, spec: _StageSpec, handle: RunnerHandle, exc: BaseException, elapsed_seconds: float = 0.0, captured_calls: tuple[ToolCallContext, ...] = ()) -> _StageOutcome:
        # Captures only exception type and stage identity so payload text cannot leak.
        return _StageOutcome(stage=spec.stage, stage_id=spec.critic_id or spec.stage, provider=spec.provider or handle.provider, model=spec.model or self.runtime._runner_model_name(handle.runner), elapsed_seconds=elapsed_seconds, error_type=type(exc).__name__, captured_calls=captured_calls)

    def _validate_structured_revision(self, revised: str) -> Any:
        # Reuses the producer output schema and fails the revision on invalid structure.
        if self.runtime.output_schema is None:
            return None
        structured, error = self._schema_formatter.validate(revised, self.runtime.output_schema)
        if error:
            raise AgentExecutionError("critique-adjudicate-revise revised candidate violates the producer output schema.", details={"stage": "revision", "error_type": "OutputSchemaValidationError"})
        return structured

    def _serialize_envelope(self, envelope: Mapping[str, Any], stage: str) -> str:
        # Emits deterministic exact JSON and fails closed instead of truncating stage data.
        payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(payload) > self.algorithm.max_stage_input_chars:
            raise AgentExecutionError(f"critique-adjudicate-revise {stage} input exceeds max_stage_input_chars.", details={"stage": stage, "input_chars": len(payload), "maximum": self.algorithm.max_stage_input_chars})
        return payload

    def _finding_payload(self, finding: CriticFinding) -> Mapping[str, Any]:
        # Serializes one grounded raw finding for the adjudicator and no later stage.
        return {"finding_id": finding.finding_id, "critic_id": finding.critic_id, "category": finding.category, "severity": finding.severity, "claim": finding.claim, "recommendation": finding.recommendation, "evidence": [self._evidence_payload(evidence) for evidence in finding.evidence]}

    def _accepted_payload(self, finding: AcceptedFinding) -> Mapping[str, Any]:
        # Serializes only runtime-accepted source material for the revision worker.
        return {"accepted_id": finding.accepted_id, "canonical_finding_id": finding.canonical_finding_id, "source_finding_ids": list(finding.source_finding_ids), "category": finding.category, "severity": finding.severity, "claim": finding.claim, "recommendation": finding.recommendation, "evidence": [self._evidence_payload(evidence) for evidence in finding.evidence]}

    def _evidence_payload(self, evidence: Any) -> Mapping[str, Any]:
        # Converts immutable evidence into the explicit stage protocol shape.
        return {"evidence_id": evidence.evidence_id, "source_kind": evidence.source_kind, "source_name": evidence.source_name, "locator": evidence.locator, "excerpt": evidence.excerpt}

    def _degraded_result(self, producer: AgentResult, status: str, outcomes: Sequence[_StageOutcome], critic_outcomes: Sequence[_StageOutcome], accepted: Sequence[AcceptedFinding], applied_ids: Sequence[str], started_at: float, projection: _AdjudicationProjection | None = None, raw_finding_count: int | None = None) -> AgentResult:
        # Returns the exact producer candidate while making terminal degradation explicit.
        effective_projection = projection or _AdjudicationProjection(accepted=tuple(accepted), accepted_groups=(), rejected_groups=())
        return self._final_result(producer, producer.output, producer.structured, status, outcomes, critic_outcomes, effective_projection, applied_ids, started_at, raw_finding_count=raw_finding_count)

    def _final_result(self, producer: AgentResult, output: str, structured: Any, status: str, outcomes: Sequence[_StageOutcome], critic_outcomes: Sequence[_StageOutcome], projection: _AdjudicationProjection, applied_ids: Sequence[str], started_at: float, raw_finding_count: int | None = None) -> AgentResult:
        # Preserves producer metadata and appends deterministic review calls and summary.
        metadata = dict(producer.metadata)
        metadata["critique_adjudicate_revise"] = self._algorithm_metadata(status, outcomes, critic_outcomes, projection, applied_ids, started_at, raw_finding_count)
        return AgentResult(output=output, strategy_name=self.name, calls=self._all_calls(producer, outcomes), metadata=metadata, structured=structured)

    def _all_calls(self, producer: AgentResult, outcomes: Sequence[_StageOutcome]) -> tuple[Any, ...]:
        # Concatenates producer and child tool calls in stable stage/index order.
        producer_calls = tuple(producer.calls) or tuple(dict(producer.metadata).get("tool_calls", ()))
        child_calls = tuple(call for outcome in outcomes for call in self._outcome_calls(outcome))
        return (*producer_calls, *child_calls)

    def _outcome_calls(self, outcome: _StageOutcome) -> tuple[ToolCallContext, ...]:
        # Annotates retained calls even when their child stage later fails or times out.
        if outcome.result is not None:
            annotated = tuple(call for call in outcome.result.calls if isinstance(call, ToolCallContext))
            if annotated:
                return annotated
        return tuple(dataclasses.replace(call, metadata={**dict(call.metadata), "context_window_algorithm": self.name, "review_stage": outcome.stage, "review_stage_id": outcome.stage_id}, provider=call.provider or outcome.provider, model=call.model or outcome.model) for call in outcome.calls)

    def _algorithm_metadata(self, status: str, outcomes: Sequence[_StageOutcome], critic_outcomes: Sequence[_StageOutcome], projection: _AdjudicationProjection, applied_ids: Sequence[str], started_at: float, raw_finding_count: int | None) -> Mapping[str, Any]:
        # Builds bounded audit metadata while excluding raw/rejected prose and tool output.
        successful_critics = sum(1 for outcome in critic_outcomes if outcome.succeeded)
        failures = tuple({"critic_id": outcome.stage_id, "error_type": outcome.error_type} for outcome in critic_outcomes if not outcome.succeeded)
        accepted_source_count = sum(len(group) for group in projection.accepted_groups)
        rejected_count = sum(len(group) for group, _ in projection.rejected_groups)
        return {**dict(self.algorithm.metadata), "status": status, "requested_critic_count": self.algorithm.critic_count, "successful_critic_count": successful_critics, "critic_failures": failures, "raw_finding_count": raw_finding_count if raw_finding_count is not None else accepted_source_count + rejected_count, "accepted_finding_count": len(projection.accepted), "rejected_finding_count": rejected_count, "accepted_findings": tuple(self._accepted_payload(finding) for finding in projection.accepted), "accepted_disposition_ids": projection.accepted_groups, "rejected_dispositions": tuple({"finding_ids": group, "reason_code": reason} for group, reason in projection.rejected_groups), "applied_finding_ids": tuple(applied_ids), "stage_models": tuple({"stage": outcome.stage, "stage_id": outcome.stage_id, "provider": outcome.provider, "model": outcome.model} for outcome in outcomes), "stage_timeouts_seconds": {"critic": self.algorithm.critic_timeout_seconds, "adjudicator": self.algorithm.adjudication_timeout_seconds, "revision": self.algorithm.revision_timeout_seconds}, "stage_call_counts": tuple({"stage_id": outcome.stage_id, "model_calls": outcome.model_calls, "tool_calls": len(self._outcome_calls(outcome)), "tokens_used": outcome.tokens_used} for outcome in outcomes), "allowlists": {"critic": self._access_metadata(self.algorithm.critic_access), "adjudicator": self._access_metadata(self.algorithm.adjudicator_access), "revision": self._access_metadata(self.algorithm.revision_access)}, "elapsed_seconds": max(0.0, self.runtime.middleware.clock() - started_at)}

    def _access_metadata(self, access: ReviewStageAccess) -> Mapping[str, Any]:
        # Reports configured authority names and limits without artifact or tool content.
        return {"artifact_names": access.allowed_artifact_names, "tool_names": access.allowed_tool_names, "max_iterations": access.max_iterations, "max_tool_calls": access.max_tool_calls}

    def _model_name(self, spec: _StageSpec, handle: RunnerHandle) -> str | None:
        # Returns the explicit stage model or the inherited runner model label.
        return spec.model or self.runtime._runner_model_name(handle.runner)

    @staticmethod
    def _content_hash(value: str) -> str:
        # Produces a stable content-free trace identifier for structural correlation.
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _sanitized_error(exc: BaseException) -> RuntimeError:
        # Retains only exception type for structural spans so payload text cannot leak.
        return RuntimeError(type(exc).__name__)


__all__ = ["CritiqueAdjudicateReviseRuntimeAlgorithm"]
