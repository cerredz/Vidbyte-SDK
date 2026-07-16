"""Context Protocol Header

FILE: vidbyte/agents/algorithms/pairwise_tournament.py
PURPOSE: Executes isolated candidate fan-out, deterministic position-balanced knockout
    rounds, and exact winning-result assembly for PairwiseTournamentAlgorithm.
ROLE IN CODEBASE: AgentRuntimeContextAlgorithms selects this return-level adapter. It
    consumes public configuration and emits trusted report records from
    vidbyte/lib/dataclasses/pairwise_tournament.py.
ARCHITECTURE NOTE: This module is the trust boundary between untrusted producer/judge
    text and deterministic advancement. Judges can return only A, B, or abstain; this
    coordinator alone owns candidate IDs, source provenance, seeding, and winner mapping.
FUNCTION INVENTORY: PairwiseTournamentRuntimeAlgorithm orchestrates the feature;
    _CandidateRuntimeFactory creates isolated producers; _JudgeResourceProjector and
    _JudgeRuntimeFactory build positive judge projections; _PairwiseMatchRunner resolves
    bidirectional legs; _TournamentBracket enforces round barriers and deterministic byes.
COMMON MODIFICATION PATTERNS: Add policy to the public config first, enforce it in one
    leaf class here, add only content-free report fields, then update both public READMEs.
WHAT NOT TO DO: Never expose candidate IDs/source labels/bracket state to a judge, share
    candidate contexts, truncate evidence, merge losing calls, or advance free-form text.
KNOWN EDGE CASES: Candidate partial success renumbers successful candidates in configured
    source order; one failed leg cancels its sibling; persistent disagreement is fail-closed
    unless lower-seed fallback was explicitly configured.
RELATED DOCS: docs/design/context-window-pairwise-tournament.md.
TESTS: Existing repository regressions plus inline manual bracket/isolation/cancellation
    verification. The approved no-tests workflow adds no test file.
CONCURRENCY MODEL: Candidate tasks share no runtime/context state. Matches in one round
    run concurrently behind a full barrier; both legs in a match are sibling tasks;
    recorder/report mutation occurs only in coordinator order after barriers close.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import inspect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.pairwise_tournament import MatchFailurePolicy, PairwiseTournamentAlgorithm, TournamentSeeding, UnresolvedMatchPolicy
from vidbyte.context.manager import ContextManager
from vidbyte.context.templates import NullRecorder
from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext, ContextArtifact
from vidbyte.lib.dataclasses.pairwise_tournament import PairwiseCandidateRecord, PairwiseJudgePayload, PairwiseLegRecord, PairwiseMatchRecord, PairwiseRoundRecord, PairwiseTournamentReport
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.models import ProviderModelRegistry
from vidbyte.lib.tracing import NullTracer, SpanContext
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolPermission

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime
    from vidbyte.tools.base import BaseTool


@dataclass(frozen=True, slots=True)
class _CandidateSource:
    """Opaque coordinator source paired with private provider/model provenance."""

    source_id: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class _CandidateRun:
    """Successful producer result before neutral candidate IDs are assigned."""

    source: _CandidateSource
    result: AgentResult
    duration_ms: int


@dataclass(frozen=True, slots=True)
class _TournamentCandidate:
    """Trusted exact producer result and neutral tournament identity."""

    candidate_id: str
    digest: str
    source: _CandidateSource
    result: AgentResult
    duration_ms: int


@dataclass(frozen=True, slots=True)
class _JudgeResources:
    """Validated judge tool blueprints and exact artifact copies."""

    tools: tuple[BaseTool, ...]
    artifacts: tuple[ContextArtifact, ...]


@dataclass(frozen=True, slots=True)
class _JudgeDecision:
    """Strict judge payload paired with bounded stage accounting."""

    payload: PairwiseJudgePayload
    tokens_used: int | None
    model_call_count: int
    tool_call_count: int


class _LegFailure(Exception):
    """Internal carrier for a content-free failed-leg record."""

    def __init__(self, record: PairwiseLegRecord) -> None:
        # Carries only structural failure data so sibling cancellation cannot leak an error body.
        super().__init__(record.error_type or "judge_leg_failed")
        self.record = record


class PairwiseTournamentRuntimeAlgorithm:
    """Return-level runtime adapter for deterministic pairwise candidate selection."""

    name = "pairwise_tournament"

    def __init__(self, runtime: AgentRuntime, algorithm: PairwiseTournamentAlgorithm) -> None:
        # Stores the parent runtime and immutable tournament configuration.
        self.runtime = runtime
        self.algorithm = algorithm

    # @intent exact-winner-provenance
    # The tournament is a selector, not a synthesizer. Producer output, structured data,
    # calls, and existing metadata must come from one exact candidate so downstream
    # callers can audit which real run won. Only the strategy label and a namespaced,
    # content-free bracket report may differ from that producer result.
    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult:
        # Runs preflight, candidate fan-out, round barriers, and exact winner assembly.
        started_at = self.runtime.middleware.clock()
        self.runtime.recorder.append("system_prompt")
        try:
            sources = self._resolve_sources(options)
            resources = _JudgeResourceProjector(self.runtime, self.algorithm).project(context)
            self.runtime.recorder.append("pairwise_tournament_candidate_fanout", candidate_count=len(sources))
            raw_runs = await self._run_candidate_barrier(message, handle, context, sources, metadata, options, trace_context)
            self.runtime.recorder.append("pairwise_tournament_candidate_barrier", configured_count=len(sources))
            candidates, omitted_source_ids = self._collect_candidates(sources, raw_runs)
            self._record_candidate_completion_spans(candidates, trace_context)
            seeded = self._seed_candidates(candidates)
            judge_factory = _JudgeRuntimeFactory(self.runtime, self.algorithm, handle, resources)
            match_runner = _PairwiseMatchRunner(self.runtime, self.algorithm, message, judge_factory, self._seed_ranks(seeded))
            winner, rounds = await _TournamentBracket(self.runtime, self.algorithm, match_runner).run(seeded, trace_context)
            report = self._build_report(candidates, omitted_source_ids, seeded, rounds, winner, started_at)
            if "pairwise_tournament" in winner.result.metadata:
                raise AgentExecutionError("Winning candidate metadata uses the reserved pairwise_tournament namespace.")
            self.runtime.recorder.append("pairwise_tournament_winner", winner_candidate_id=winner.candidate_id)
            winner_metadata = {**dict(winner.result.metadata), "pairwise_tournament": report.to_metadata()}
            return dataclasses.replace(winner.result, strategy_name=self.name, metadata=winner_metadata)
        except BaseException as exc:
            self.runtime.recorder.append("pairwise_tournament_failure", error_type=type(exc).__name__)
            raise

    def _resolve_sources(self, options: Mapping[str, Any] | None) -> tuple[_CandidateSource, ...]:
        # Resolves active text providers and assigns private source IDs in configured order.
        active = ProviderModelRegistry.resolve_active(self.algorithm.provider_models, options)
        if not 2 <= len(active) <= 16:
            raise ConfigurationError(f"pairwise_tournament requires 2-16 active candidate sources, resolved {len(active)}.")
        return tuple(_CandidateSource(f"source-{index:03d}", provider, model) for index, (provider, model) in enumerate(active.items(), 1))

    async def _run_candidate_barrier(self, message: str, handle: RunnerHandle, context: BaseAgentContext, sources: tuple[_CandidateSource, ...], metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None) -> list[Any]:
        # Starts every isolated producer before awaiting one full ordered candidate barrier.
        factory = _CandidateRuntimeFactory(self.runtime)
        tasks = [self._run_candidate(source, message, handle, context, metadata, options, trace_context, factory) for source in sources]
        return list(await asyncio.gather(*tasks, return_exceptions=True))

    async def _run_candidate(self, source: _CandidateSource, message: str, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None, options: Mapping[str, Any] | None, trace_context: SpanContext | None, factory: _CandidateRuntimeFactory) -> _CandidateRun:
        # Executes one producer in a fresh runtime/context without peer output or shared state.
        span = self.runtime._start_semantic_span("algorithm.pairwise_tournament.candidate", parent=trace_context, source_id=source.source_id, status="running")
        started_at = self.runtime.middleware.clock()
        try:
            candidate_runtime, candidate_context = factory.create(source, context)
            runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=source.provider, model=source.model)
            candidate_handle = handle.with_runner(runner, source.provider)
            result = await candidate_runtime._arun_once(message, handle=candidate_handle, context=candidate_context, metadata={**dict(metadata or {}), "context_window_algorithm": self.name, "candidate_source_id": source.source_id, "candidate_provider": source.provider, "candidate_model": source.model}, options=_copy_mapping(options), trace_context=None)
        except Exception:
            self.runtime._end_semantic_span(span, output="failed")
            raise
        except BaseException:
            self.runtime._end_semantic_span(span, output="cancelled")
            raise
        self.runtime._end_semantic_span(span, output="completed")
        return _CandidateRun(source, result, _duration_ms(started_at, self.runtime.middleware.clock()))

    def _collect_candidates(self, sources: tuple[_CandidateSource, ...], runs: list[Any]) -> tuple[tuple[_TournamentCandidate, ...], tuple[str, ...]]:
        # Applies candidate failure policy, validates exact outputs, and assigns neutral IDs.
        failures = tuple(source.source_id for source, result in zip(sources, runs) if isinstance(result, BaseException))
        if failures and self.algorithm.require_all_candidates:
            raise AgentExecutionError("Pairwise tournament candidate barrier failed under require_all_candidates.", details={"failed_source_ids": failures, "configured_count": len(sources)})
        successful = tuple(result for result in runs if isinstance(result, _CandidateRun))
        if len(successful) < 2:
            raise AgentExecutionError("Pairwise tournament requires at least two successful candidates.", details={"successful_count": len(successful), "failed_source_ids": failures})
        candidates: list[_TournamentCandidate] = []
        for index, run in enumerate(successful, 1):
            output = run.result.output
            if not isinstance(output, str) or not output.strip():
                raise AgentExecutionError("Pairwise tournament candidate output must be nonblank.", details={"source_id": run.source.source_id})
            if len(output) > self.algorithm.max_candidate_chars:
                raise AgentExecutionError("Pairwise tournament candidate exceeds max_candidate_chars.", details={"source_id": run.source.source_id, "output_chars": len(output), "limit": self.algorithm.max_candidate_chars})
            candidates.append(_TournamentCandidate(f"candidate-{index:03d}", _sha256(output), run.source, run.result, run.duration_ms))
        return tuple(candidates), failures

    def _seed_candidates(self, candidates: tuple[_TournamentCandidate, ...]) -> tuple[_TournamentCandidate, ...]:
        # Produces the deterministic effective seed order without altering candidate identities.
        if self.algorithm.seeding is TournamentSeeding.CONTENT_HASH:
            return tuple(sorted(candidates, key=lambda candidate: (candidate.digest, candidate.candidate_id)))
        return candidates

    def _record_candidate_completion_spans(self, candidates: tuple[_TournamentCandidate, ...], trace_context: SpanContext | None) -> None:
        # Emits trusted candidate IDs, hashes, timing, and accounting only after the barrier.
        for candidate in candidates:
            span = self.runtime._start_semantic_span("algorithm.pairwise_tournament.candidate.result", parent=trace_context, candidate_id=candidate.candidate_id, candidate_hash=candidate.digest, source_id=candidate.source.source_id, duration_ms=candidate.duration_ms, tokens_used=_tokens_used(candidate.result), status="completed")
            self.runtime._end_semantic_span(span, output="completed")

    def _seed_ranks(self, seeded: tuple[_TournamentCandidate, ...]) -> Mapping[str, int]:
        # Maps neutral candidate IDs to stable zero-based effective seed ranks.
        return {candidate.candidate_id: index for index, candidate in enumerate(seeded)}

    def _build_report(self, candidates: tuple[_TournamentCandidate, ...], omitted_source_ids: tuple[str, ...], seeded: tuple[_TournamentCandidate, ...], rounds: tuple[PairwiseRoundRecord, ...], winner: _TournamentCandidate, started_at: float) -> PairwiseTournamentReport:
        # Assembles bounded structural provenance without task, candidate, evidence, or rationale text.
        candidate_records = tuple(PairwiseCandidateRecord(candidate.candidate_id, candidate.digest, candidate.source.source_id, candidate.source.provider, candidate.source.model, candidate.duration_ms, _tokens_used(candidate.result), _metadata_count(candidate.result, "iteration_count"), _metadata_count(candidate.result, "tool_call_count")) for candidate in candidates)
        matches = tuple(match for round_record in rounds for match in round_record.matches)
        legs = tuple(leg for match in matches for leg in match.legs)
        return PairwiseTournamentReport(
            schema_version="1.0",
            status="completed",
            seeding=self.algorithm.seeding.value,
            candidate_records=candidate_records,
            omitted_source_ids=omitted_source_ids,
            seed_order=tuple(candidate.candidate_id for candidate in seeded),
            seed_hashes=tuple(candidate.digest for candidate in seeded),
            rounds=rounds,
            winner_candidate_id=winner.candidate_id,
            winner_digest=winner.digest,
            winner_source_id=winner.source.source_id,
            winner_provider=winner.source.provider,
            winner_model=winner.source.model,
            candidate_count=len(candidates),
            match_count=len(matches),
            judge_leg_count=len(legs),
            fallback_count=sum(match.resolution != "judge_consensus" for match in matches),
            candidate_tokens_used=_sum_optional(record.tokens_used for record in candidate_records),
            judge_tokens_used=_sum_optional(leg.tokens_used for leg in legs),
            candidate_model_call_count=sum(record.model_call_count for record in candidate_records),
            candidate_tool_call_count=sum(record.tool_call_count for record in candidate_records),
            judge_model_call_count=sum(leg.model_call_count for leg in legs),
            judge_tool_call_count=sum(leg.tool_call_count for leg in legs),
            duration_ms=_duration_ms(started_at, self.runtime.middleware.clock()),
            configured_metadata=dict(self.algorithm.metadata),
        )


class _CandidateRuntimeFactory:
    """Builds independent producer runtimes from the parent producer contract."""

    def __init__(self, runtime: AgentRuntime) -> None:
        # Stores the producer runtime whose authorized behavior each candidate inherits.
        self.runtime = runtime

    def create(self, source: _CandidateSource, context: BaseAgentContext) -> tuple[AgentRuntime, BaseAgentContext]:
        # Clones mutable producer state and returns a default-algorithm runtime plus context.
        from vidbyte.agents.runtime import AgentRuntime
        tools = Tools(_clone_tool(tool, purpose="candidate") for tool in self.runtime.user_tools.all())
        manager = _clone_context_manager(self.runtime.context_manager)
        candidate_runtime = AgentRuntime(agent_name=f"{self.runtime.agent_name}:pairwise:{source.source_id}", system_prompt=self.runtime.system_prompt, tools=tools, permission_policy=self.runtime.permission_policy, config=self.runtime.config, tracer=NullTracer(), middleware=self.runtime.middleware.middleware, run_id=_child_run_id(self.runtime.run_id, source.source_id), algorithm=None, context_manager=manager, recorder=NullRecorder(), output_schema=self.runtime.output_schema, output_contract=self.runtime.output_contract, include_internal_tools=self.runtime.include_internal_tools)
        visible_tools = candidate_runtime.tools if candidate_runtime.include_internal_tools else candidate_runtime.user_tools
        candidate_context = _clone_candidate_context(context, visible_tools)
        return candidate_runtime, candidate_context


class _JudgeResourceProjector:
    """Preflights exact judge artifact and tool allowlists before model calls."""

    def __init__(self, runtime: AgentRuntime, algorithm: PairwiseTournamentAlgorithm) -> None:
        # Stores the producer resource surface and deny-by-default judge configuration.
        self.runtime = runtime
        self.algorithm = algorithm

    def project(self, context: BaseAgentContext) -> _JudgeResources:
        # Returns exact artifact copies and safe/read tool blueprints after full validation.
        artifacts = self._project_artifacts(context.artifacts)
        tools = self._project_tools()
        return _JudgeResources(tools, artifacts)

    def _project_artifacts(self, artifacts: Sequence[ContextArtifact]) -> tuple[ContextArtifact, ...]:
        # Selects exact unique names and rejects missing, ambiguous, or oversized evidence.
        by_name: dict[str, list[ContextArtifact]] = {}
        for artifact in artifacts:
            by_name.setdefault(artifact.name, []).append(artifact)
        selected: list[ContextArtifact] = []
        total_chars = 0
        for name in self.algorithm.judge_artifact_names:
            matches = by_name.get(name, [])
            if not matches:
                raise ConfigurationError(f"Judge artifact {name!r} was requested but is missing.")
            if len(matches) != 1:
                raise ConfigurationError(f"Judge artifact {name!r} is ambiguous because its name is duplicated.")
            artifact = matches[0]
            if len(artifact.content) > self.algorithm.max_artifact_chars:
                raise ConfigurationError(f"Judge artifact {name!r} exceeds max_artifact_chars.")
            total_chars += len(artifact.content)
            selected.append(ContextArtifact(name=artifact.name, content=artifact.content, artifact_type=artifact.artifact_type, metadata={}))
        if total_chars > self.algorithm.max_total_artifact_chars:
            raise ConfigurationError("Selected judge artifacts exceed max_total_artifact_chars.")
        return tuple(selected)

    def _project_tools(self) -> tuple[BaseTool, ...]:
        # Selects exact names and rejects mutating, bound, remote, or uncloneable tool authority.
        available = {tool.name: tool for tool in self.runtime.user_tools.all()}
        selected: list[BaseTool] = []
        for name in self.algorithm.judge_tool_names:
            tool = available.get(name)
            if tool is None:
                raise ConfigurationError(f"Judge tool {name!r} was requested but is missing.")
            _validate_judge_tool(tool)
            _clone_tool(tool, purpose="judge preflight")
            selected.append(tool)
        return tuple(selected)


class _JudgeRuntimeFactory:
    """Builds a fresh positive-projection judge runtime for every orientation."""

    def __init__(self, runtime: AgentRuntime, algorithm: PairwiseTournamentAlgorithm, incoming_handle: RunnerHandle, resources: _JudgeResources) -> None:
        # Stores only the transport and preflighted judge resources needed for fresh legs.
        self.runtime = runtime
        self.algorithm = algorithm
        self.incoming_handle = incoming_handle
        self.resources = resources

    async def judge(self, task: str, slot_a: _TournamentCandidate, slot_b: _TournamentCandidate) -> _JudgeDecision:
        # Invokes one isolated structured-output judge without bracket, source, or peer state.
        judge_runtime, judge_context, judge_handle = self._create_leg()
        prompt = self.algorithm.render_judge_prompt(task, slot_a.result.output, slot_b.result.output)
        result = await judge_runtime._arun_once(prompt, handle=judge_handle, context=judge_context, metadata={"context_window_algorithm": "pairwise_tournament", "judge_stage": "leg"}, options={}, trace_context=None)
        if len(result.output) > self.algorithm.max_judge_output_chars:
            raise AgentExecutionError("Pairwise judge output exceeds max_judge_output_chars.", details={"output_chars": len(result.output), "limit": self.algorithm.max_judge_output_chars})
        payload = self._validate_payload(result)
        return _JudgeDecision(payload, _tokens_used(result), _metadata_count(result, "iteration_count"), _metadata_count(result, "tool_call_count"))

    def _create_leg(self) -> tuple[AgentRuntime, BaseAgentContext, RunnerHandle]:
        # Creates fresh tools, empty middleware/context state, strict schema, and stateless transport.
        from vidbyte.agents.runtime import AgentRuntime
        tools = Tools(_clone_tool(tool, purpose="judge") for tool in self.resources.tools)
        judge_runtime = AgentRuntime(agent_name=f"{self.runtime.agent_name}:pairwise:judge", system_prompt=self.algorithm.judge_system_prompt_text(), tools=tools, permission_policy=_judge_permission_policy(self.runtime.permission_policy), config=AgentRuntimeConfig(max_iterations=4, max_tool_calls=max(1, len(tools) * 2)), tracer=NullTracer(), middleware=(), run_id=None, algorithm=None, context_manager=None, recorder=NullRecorder(), output_schema=PairwiseJudgePayload, include_internal_tools=False)
        judge_context = BaseAgentContext(system_prompt=self.algorithm.judge_system_prompt_text(), history=(), tools=tools.specs(), file_paths=(), run_metadata={}, tool_calls=(), responses=(), artifacts=self.resources.artifacts, memory=None, permissions=None, metadata={}, context_items=())
        return judge_runtime, judge_context, self._judge_handle()

    def _judge_handle(self) -> RunnerHandle:
        # Uses an optional dedicated judge model or the incoming handle as stateless transport.
        if self.algorithm.judge_provider is None or self.algorithm.judge_model is None:
            return self.incoming_handle
        runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=self.algorithm.judge_provider, model=self.algorithm.judge_model)
        return self.incoming_handle.with_runner(runner, self.algorithm.judge_provider)

    def _validate_payload(self, result: AgentResult) -> PairwiseJudgePayload:
        # Normalizes provider output through the strict schema and applies configured bounds.
        try:
            payload = result.structured if isinstance(result.structured, PairwiseJudgePayload) else PairwiseJudgePayload.model_validate_json(result.output)
        except Exception as exc:
            raise AgentExecutionError("Pairwise judge did not return the required structured decision.", details={"error_type": type(exc).__name__}) from None
        if len(payload.summary) > self.algorithm.max_summary_chars:
            raise AgentExecutionError("Pairwise judge summary exceeds max_summary_chars.", details={"summary_chars": len(payload.summary), "limit": self.algorithm.max_summary_chars})
        if len(payload.criteria) > self.algorithm.max_criteria:
            raise AgentExecutionError("Pairwise judge criteria exceed max_criteria.", details={"criteria_count": len(payload.criteria), "limit": self.algorithm.max_criteria})
        return payload


class _PairwiseMatchRunner:
    """Runs position-balanced judge legs and resolves one deterministic bracket match."""

    def __init__(self, runtime: AgentRuntime, algorithm: PairwiseTournamentAlgorithm, task: str, judge_factory: _JudgeRuntimeFactory, seed_ranks: Mapping[str, int]) -> None:
        # Stores isolated judge construction and coordinator-only seed ranks.
        self.runtime = runtime
        self.algorithm = algorithm
        self.task = task
        self.judge_factory = judge_factory
        self.seed_ranks = dict(seed_ranks)

    # @intent position-bias-control
    # A single A/B comparison can advance the first or second slot because of presentation
    # bias rather than candidate quality. Every attempt therefore requires two independent,
    # fresh decisions with positions reversed. Only agreement after mapping slots back to
    # canonical candidates counts as judge consensus; no one-leg shortcut may advance.
    async def run_match(self, left: _TournamentCandidate, right: _TournamentCandidate, round_index: int, match_index: int, trace_context: SpanContext | None) -> PairwiseMatchRecord:
        # Runs bounded bidirectional attempts and applies only explicit unresolved/failure policy.
        match_id = f"round-{round_index:03d}-match-{match_index:03d}"
        span = self.runtime._start_semantic_span("algorithm.pairwise_tournament.match", parent=trace_context, match_id=match_id, round_index=round_index, match_index=match_index, status="running")
        started_at = self.runtime.middleware.clock()
        records: list[PairwiseLegRecord] = []
        try:
            for attempt in range(self.algorithm.max_tiebreak_attempts + 1):
                legs = await self._run_leg_pair(left, right, match_id, attempt, span or trace_context)
                records.extend(legs)
                if any(leg.status in ("failed", "cancelled") for leg in legs):
                    record = self._resolve_failure(left, right, match_id, round_index, match_index, tuple(records), started_at)
                    self.runtime._end_semantic_span(span, output=record.resolution)
                    return record
                winners = tuple(leg.winner_candidate_id for leg in legs)
                if winners[0] is not None and winners[0] == winners[1]:
                    record = self._record_match(left, right, match_id, round_index, match_index, tuple(records), winners[0], "judge_consensus", True, started_at)
                    self.runtime._end_semantic_span(span, output="judge_consensus")
                    return record
            record = self._resolve_unresolved(left, right, match_id, round_index, match_index, tuple(records), started_at)
            self.runtime._end_semantic_span(span, output=record.resolution)
            return record
        except BaseException:
            self.runtime._end_semantic_span(span, output="failed")
            raise

    async def _run_leg_pair(self, left: _TournamentCandidate, right: _TournamentCandidate, match_id: str, attempt: int, trace_context: SpanContext | None) -> tuple[PairwiseLegRecord, PairwiseLegRecord]:
        # Starts both orientations together and cancels/awaits a sibling when either leg fails.
        orientations = (("A_B", left, right), ("B_A", right, left))
        tasks = [asyncio.create_task(self._run_leg(match_id, attempt, orientation, slot_a, slot_b, trace_context)) for orientation, slot_a, slot_b in orientations]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            if any(task.exception() is not None for task in done if not task.cancelled()):
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            else:
                await asyncio.gather(*pending)
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        records: list[PairwiseLegRecord] = []
        for task, (orientation, _slot_a, _slot_b) in zip(tasks, orientations):
            if task.cancelled():
                records.append(self._cancelled_leg_record(match_id, attempt, orientation))
                continue
            exception = task.exception()
            if isinstance(exception, _LegFailure):
                records.append(exception.record)
            elif exception is not None:
                records.append(self._failed_leg_record(match_id, attempt, orientation, type(exception).__name__))
            else:
                records.append(task.result())
        return records[0], records[1]

    async def _run_leg(self, match_id: str, attempt: int, orientation: str, slot_a: _TournamentCandidate, slot_b: _TournamentCandidate, trace_context: SpanContext | None) -> PairwiseLegRecord:
        # Runs one fresh structured judge and maps its visible slot choice to a canonical ID.
        leg_id = f"{match_id}-attempt-{attempt:02d}-{orientation.lower()}"
        span = self.runtime._start_semantic_span("algorithm.pairwise_tournament.leg", parent=trace_context, leg_id=leg_id, attempt=attempt, orientation=orientation, status="running")
        started_at = self.runtime.middleware.clock()
        try:
            decision = await asyncio.wait_for(self.judge_factory.judge(self.task, slot_a, slot_b), timeout=self.algorithm.leg_timeout_seconds)
        except asyncio.CancelledError:
            self.runtime._end_semantic_span(span, output="cancelled")
            raise
        except Exception as exc:
            record = self._failed_leg_record(match_id, attempt, orientation, type(exc).__name__, started_at)
            self.runtime._end_semantic_span(span, output="failed")
            raise _LegFailure(record) from None
        winner = slot_a.candidate_id if decision.payload.winner_slot == "A" else slot_b.candidate_id if decision.payload.winner_slot == "B" else None
        status = "abstained" if winner is None else "decided"
        record = PairwiseLegRecord(leg_id, attempt, orientation, decision.payload.winner_slot, winner, status, _duration_ms(started_at, self.runtime.middleware.clock()), decision.tokens_used, decision.model_call_count, decision.tool_call_count)
        self.runtime._end_semantic_span(span, output=status)
        return record

    def _resolve_failure(self, left: _TournamentCandidate, right: _TournamentCandidate, match_id: str, round_index: int, match_index: int, legs: tuple[PairwiseLegRecord, ...], started_at: float) -> PairwiseMatchRecord:
        # Fails closed by default or records an explicit lower-seed failure fallback.
        if self.algorithm.match_failure_policy is MatchFailurePolicy.RAISE:
            error_types = tuple(leg.error_type for leg in legs if leg.error_type)
            raise AgentExecutionError("Pairwise tournament judge leg failed.", details={"match_id": match_id, "error_types": error_types})
        winner = self._lower_seed(left, right)
        return self._record_match(left, right, match_id, round_index, match_index, legs, winner.candidate_id, "failure_lower_seed", False, started_at)

    def _resolve_unresolved(self, left: _TournamentCandidate, right: _TournamentCandidate, match_id: str, round_index: int, match_index: int, legs: tuple[PairwiseLegRecord, ...], started_at: float) -> PairwiseMatchRecord:
        # Fails closed after bounded disagreement or marks an explicit lower-seed fallback.
        if self.algorithm.unresolved_policy is UnresolvedMatchPolicy.RAISE:
            raise AgentExecutionError("Pairwise tournament match remained unresolved after bounded tiebreak attempts.", details={"match_id": match_id, "attempt_count": self.algorithm.max_tiebreak_attempts + 1})
        winner = self._lower_seed(left, right)
        return self._record_match(left, right, match_id, round_index, match_index, legs, winner.candidate_id, "policy_lower_seed", False, started_at)

    def timeout_fallback(self, left: _TournamentCandidate, right: _TournamentCandidate, round_index: int, match_index: int, error_type: str) -> PairwiseMatchRecord:
        # Applies match-level failure policy only after wait_for has cancelled and awaited the match.
        match_id = f"round-{round_index:03d}-match-{match_index:03d}"
        if self.algorithm.match_failure_policy is MatchFailurePolicy.RAISE:
            raise AgentExecutionError("Pairwise tournament match failed.", details={"match_id": match_id, "error_type": error_type})
        winner = self._lower_seed(left, right)
        return PairwiseMatchRecord(match_id, round_index, match_index, (left.candidate_id, right.candidate_id), (), winner.candidate_id, "failure_lower_seed", False, 0)

    def _record_match(self, left: _TournamentCandidate, right: _TournamentCandidate, match_id: str, round_index: int, match_index: int, legs: tuple[PairwiseLegRecord, ...], winner_id: str, resolution: str, consensus: bool, started_at: float) -> PairwiseMatchRecord:
        # Builds one immutable bracket-order match record from trusted coordinator values.
        return PairwiseMatchRecord(match_id, round_index, match_index, (left.candidate_id, right.candidate_id), legs, winner_id, resolution, consensus, _duration_ms(started_at, self.runtime.middleware.clock()))

    def _lower_seed(self, left: _TournamentCandidate, right: _TournamentCandidate) -> _TournamentCandidate:
        # Returns the entrant with the smaller effective seed rank.
        return left if self.seed_ranks[left.candidate_id] < self.seed_ranks[right.candidate_id] else right

    def _failed_leg_record(self, match_id: str, attempt: int, orientation: str, error_type: str, started_at: float | None = None) -> PairwiseLegRecord:
        # Builds a content-free failed-leg record with no exception message or payload.
        duration = 0 if started_at is None else _duration_ms(started_at, self.runtime.middleware.clock())
        return PairwiseLegRecord(f"{match_id}-attempt-{attempt:02d}-{orientation.lower()}", attempt, orientation, None, None, "failed", duration, error_type=error_type)

    def _cancelled_leg_record(self, match_id: str, attempt: int, orientation: str) -> PairwiseLegRecord:
        # Builds a content-free sibling-cancellation record after the task has settled.
        return PairwiseLegRecord(f"{match_id}-attempt-{attempt:02d}-{orientation.lower()}", attempt, orientation, None, None, "cancelled", 0, error_type="CancelledError")


class _TournamentBracket:
    """Executes adjacent pairings with deterministic byes and per-round barriers."""

    def __init__(self, runtime: AgentRuntime, algorithm: PairwiseTournamentAlgorithm, match_runner: _PairwiseMatchRunner) -> None:
        # Stores coordinator dependencies and creates the match-concurrency gate.
        self.runtime = runtime
        self.algorithm = algorithm
        self.match_runner = match_runner
        self.semaphore = asyncio.Semaphore(algorithm.max_concurrency)

    # @intent round-barrier-determinism
    # Match completion order must never become bracket order. Every round snapshots its
    # entrants, schedules canonical adjacent matches, waits for the entire barrier, and
    # only then constructs the next entrant tuple. This prevents provider latency from
    # changing future opponents or exposing partial peer results to later judges.
    async def run(self, seeded: tuple[_TournamentCandidate, ...], trace_context: SpanContext | None) -> tuple[_TournamentCandidate, tuple[PairwiseRoundRecord, ...]]:
        # Advances canonical match-order winners and final byes until one entrant remains.
        entrants = seeded
        rounds: list[PairwiseRoundRecord] = []
        round_index = 1
        while len(entrants) > 1:
            round_record, entrants = await self._run_round(entrants, round_index, trace_context)
            rounds.append(round_record)
            self.runtime.recorder.append("pairwise_tournament_round", iteration=round_index, match_count=len(round_record.matches), has_bye=round_record.bye_candidate_id is not None)
            round_index += 1
        return entrants[0], tuple(rounds)

    async def _run_round(self, entrants: tuple[_TournamentCandidate, ...], round_index: int, trace_context: SpanContext | None) -> tuple[PairwiseRoundRecord, tuple[_TournamentCandidate, ...]]:
        # Schedules all adjacent matches before one ordered gather barrier and then advances.
        span = self.runtime._start_semantic_span("algorithm.pairwise_tournament.round", parent=trace_context, round_index=round_index, entrant_count=len(entrants), status="running")
        started_at = self.runtime.middleware.clock()
        pairs = tuple((entrants[index], entrants[index + 1]) for index in range(0, len(entrants) - 1, 2))
        bye = entrants[-1] if len(entrants) % 2 else None
        tasks = [asyncio.create_task(self._run_guarded_match(left, right, round_index, match_index, span or trace_context)) for match_index, (left, right) in enumerate(pairs, 1)]
        try:
            results = await self._await_round_barrier(tasks)
            failures = tuple(result for result in results if isinstance(result, BaseException))
            if failures:
                raise AgentExecutionError("Pairwise tournament round barrier contained failed matches.", details={"round_index": round_index, "error_types": tuple(type(item).__name__ for item in failures)})
            matches = tuple(result for result in results if isinstance(result, PairwiseMatchRecord))
            by_id = {candidate.candidate_id: candidate for candidate in entrants}
            advancing = tuple(by_id[match.winner_candidate_id] for match in matches) + ((bye,) if bye is not None else ())
            record = PairwiseRoundRecord(round_index, tuple(candidate.candidate_id for candidate in entrants), matches, bye.candidate_id if bye else None, tuple(candidate.candidate_id for candidate in advancing), _duration_ms(started_at, self.runtime.middleware.clock()))
            self.runtime._end_semantic_span(span, output="completed")
            return record, advancing
        except BaseException:
            self.runtime._end_semantic_span(span, output="failed")
            raise

    async def _run_guarded_match(self, left: _TournamentCandidate, right: _TournamentCandidate, round_index: int, match_index: int, trace_context: SpanContext | None) -> PairwiseMatchRecord:
        # Applies match concurrency and timeout without publishing a partial winner.
        async with self.semaphore:
            try:
                return await asyncio.wait_for(self.match_runner.run_match(left, right, round_index, match_index, trace_context), timeout=self.algorithm.match_timeout_seconds)
            except asyncio.CancelledError:
                raise
            except TimeoutError as exc:
                return self.match_runner.timeout_fallback(left, right, round_index, match_index, type(exc).__name__)

    async def _await_round_barrier(self, tasks: list[asyncio.Task[PairwiseMatchRecord]]) -> list[Any]:
        # Awaits one gather barrier and cancels/awaits every task on round timeout or caller cancellation.
        gatherer = asyncio.gather(*tasks, return_exceptions=True)
        try:
            if self.algorithm.round_timeout_seconds is None:
                return list(await gatherer)
            return list(await asyncio.wait_for(gatherer, timeout=self.algorithm.round_timeout_seconds))
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise


def _clone_tool(tool: BaseTool, *, purpose: str) -> BaseTool:
    # Clones mutable tool wrappers and rejects live objects that cannot be isolated.
    clone_method = getattr(tool, "clone_for_fork", None)
    if not callable(clone_method) and _tool_has_live_binding(tool):
        raise ConfigurationError(f"Tool {tool.name!r} retains live state and does not support isolated cloning for {purpose}.")
    try:
        cloned = clone_method() if callable(clone_method) else copy.deepcopy(tool)
    except Exception as exc:
        raise ConfigurationError(f"Tool {tool.name!r} cannot be isolated for {purpose}.", details={"tool_name": tool.name, "error_type": type(exc).__name__}) from None
    if cloned is tool and getattr(tool, "__dict__", None):
        raise ConfigurationError(f"Tool {tool.name!r} returned shared mutable state during {purpose} cloning.")
    if getattr(cloned, "name", None) != tool.name:
        raise ConfigurationError(f"Tool {tool.name!r} changed identity during {purpose} cloning.")
    return cloned


def _tool_has_live_binding(tool: BaseTool) -> bool:
    # Detects remote, session, client, or context-bound state that deepcopy cannot safely isolate.
    spec = tool.spec()
    metadata = dict(spec.metadata)
    module_name = type(tool).__module__.lower()
    if metadata.get("source") == "mcp" or ".mcp" in module_name or spec.binds_to_primitive is not None:
        return True
    function = getattr(tool, "func", None)
    if callable(function) and (getattr(function, "__closure__", None) or inspect.ismethod(function)):
        return True
    return any("session" in name.lower() or name.lower().endswith("client") or "context_getter" in name.lower() for name in vars(tool))


def _validate_judge_tool(tool: BaseTool) -> None:
    # Rejects authority that could mutate state or access producer-bound/live resources.
    spec = tool.spec()
    if spec.permission not in (ToolPermission.SAFE, ToolPermission.READ):
        raise ConfigurationError(f"Judge tool {tool.name!r} must declare SAFE or READ permission.")
    metadata = dict(spec.metadata)
    module_name = type(tool).__module__.lower()
    if metadata.get("source") == "mcp" or metadata.get("internal_agent_tool") or ".mcp" in module_name:
        raise ConfigurationError(f"Judge tool {tool.name!r} cannot be MCP-backed or agent-bound.")
    if spec.binds_to_primitive is not None:
        raise ConfigurationError(f"Judge tool {tool.name!r} cannot bind to mutable context primitives.")
    if any("session" in name.lower() or name.lower().endswith("client") for name in vars(tool)):
        raise ConfigurationError(f"Judge tool {tool.name!r} cannot retain session or client bindings.")
    function = getattr(tool, "func", None)
    if callable(function) and (getattr(function, "__closure__", None) or inspect.ismethod(function)):
        raise ConfigurationError(f"Judge tool {tool.name!r} cannot close over live producer authority.")


def _clone_context_manager(manager: ContextManager | None) -> ContextManager | None:
    # Copies mutable context registries and placements while preserving immutable primitives.
    if manager is None:
        return None
    try:
        cloned = copy.deepcopy(manager)
    except Exception as exc:
        raise ConfigurationError("Candidate context_manager must be independently copyable.", details={"error_type": type(exc).__name__}) from None
    if cloned is manager:
        raise ConfigurationError("Candidate context_manager cloning returned shared mutable state.")
    return cloned


def _clone_candidate_context(context: BaseAgentContext, visible_tools: Tools) -> BaseAgentContext:
    # Deep-copies producer-visible context and replaces tool specs with candidate-local clones.
    try:
        cloned = copy.deepcopy(context)
    except Exception as exc:
        raise ConfigurationError("Candidate context must be independently copyable.", details={"error_type": type(exc).__name__}) from None
    if cloned is context:
        raise ConfigurationError("Candidate context cloning returned shared mutable state.")
    return dataclasses.replace(cloned, tools=visible_tools.specs())


def _judge_permission_policy(parent: PermissionPolicy) -> PermissionPolicy:
    # Intersects parent authorization with the judge's SAFE/READ-only contract.
    return PermissionPolicy(allowed=frozenset(permission for permission in parent.allowed if permission in (ToolPermission.SAFE, ToolPermission.READ)))


def _copy_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    # Deep-copies candidate invocation options so concurrent producers cannot share mutation.
    try:
        return copy.deepcopy(dict(value or {}))
    except Exception as exc:
        raise ConfigurationError("Pairwise tournament candidate options must be independently copyable.", details={"error_type": type(exc).__name__}) from None


def _tokens_used(result: AgentResult) -> int | None:
    # Extracts a non-negative integer token count without trusting arbitrary metadata types.
    value = dict(result.metadata).get("tokens_used")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _metadata_count(result: AgentResult, key: str) -> int:
    # Extracts one non-negative bounded stage count and defaults invalid metadata to zero.
    value = dict(result.metadata).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _sum_optional(values: Iterable[int | None]) -> int | None:
    # Sums present accounting values and returns None when no stage reported usage.
    present = tuple(value for value in values if value is not None)
    return sum(present) if present else None


def _sha256(value: str) -> str:
    # Returns the canonical UTF-8 SHA-256 digest used for identity and optional seeding.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _duration_ms(started_at: float, finished_at: float) -> int:
    # Converts monotonic elapsed seconds to a stable non-negative millisecond integer.
    return max(0, int(round((finished_at - started_at) * 1000)))


def _child_run_id(parent_run_id: str | None, source_id: str) -> str:
    # Creates an opaque candidate-local lineage ID without exposing provider identity.
    return f"{parent_run_id}:pairwise:{source_id}" if parent_run_id else f"pairwise:{source_id}"


__all__ = ["PairwiseTournamentRuntimeAlgorithm"]
