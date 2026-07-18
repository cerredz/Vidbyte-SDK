"""Context Protocol Header

FILE: vidbyte/agents/algorithms/parallel_panel.py
PURPOSE: Runs one producer and an isolated, model-only panel that reviews the
same candidate without seeing producer-private state or peer findings. Public
configuration validation belongs in vidbyte/context/algorithms/parallel_panel.py.
ROLE IN CODEBASE: AgentRuntimeContextAlgorithms calls this adapter; it delegates
the producer to AgentRuntime._arun_once and reviewer calls to fresh runtimes.
ARCHITECTURE NOTE: Local immutable outcomes plus one gather barrier prevent
early publication. Context manipulation uses ContextManager and vidbyte.context
primitives rather than hand-built BaseAgentContext fields.
FUNCTION INVENTORY: ParallelPanelRuntimeAlgorithm.run/arun orchestrate production,
preflight, fan-out, barrier policy, and additive result metadata. Private methods
own one isolation or collection concern each.
COMMON MODIFICATION PATTERNS: Change reviewer inputs only in _prepare_snapshot;
change publication policy only after _await_panel returns; keep result assembly
additive and preserve every producer field.
WHAT NOT TO DO: 1. Do not invoke reviews on the producer runtime. 2. Do not read
results before the barrier. 3. Do not pass identities or findings in prompts.
4. Do not truncate candidates or evidence. 5. Do not revise the candidate.
6. Do not bypass ContextManager for reviewer context construction.
KNOWN EDGE CASES: Synchronous custom runners cannot overlap or be preempted;
review completion order never controls result order; panel timeout publishes no
findings, while an individual timeout can be an ordered branch failure.
COMMON ERRORS: AgentExecutionError reports safe counts, identifiers, and failure
classes without including prompt, candidate, artifact, or provider-response text.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/context-window-parallel-panel.md
TESTS: Existing agent runtime regressions plus the design's uncommitted manual
fake-runner verification; no dedicated test file is permitted by the manifest.
CONCURRENCY: All reviewer tasks are created before awaiting. asyncio.gather is
the collection barrier; an optional semaphore limits in-flight provider calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vidbyte.context.algorithms.parallel_panel import ParallelPanelAlgorithm
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import ArtifactContextItem
from vidbyte.context.templates import NullRecorder
from vidbyte.lib.constants.parallel_panel import NO_ARTIFACTS_PLACEHOLDER, REVIEW_TRUNCATION_SUFFIX
from vidbyte.lib.dataclasses.context import BaseAgentContext, BaseContext, ContextArtifact
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.tracing import SpanContext
from vidbyte.tools.catalog import Tools
from vidbyte.tools.security import PermissionPolicy

if TYPE_CHECKING:
    from vidbyte.agents.runtime import AgentRuntime


@dataclass(frozen=True, slots=True)
class _PanelSnapshot:
    """Immutable reviewer-visible input and safe coordinator metadata."""

    system_prompt: str
    user_prompt: str
    candidate_chars: int
    candidate_sha256: str
    artifact_names: tuple[str, ...]
    algorithm_metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _BoundedReview:
    """Bounded reviewer text plus whether the original text exceeded the limit."""

    content: str
    truncated: bool


@dataclass(frozen=True, slots=True)
class _ReviewerOutcome:
    """Private branch result that is not published until the panel barrier."""

    reviewer_index: int
    reviewer_id: str
    success: bool
    content: str = ""
    content_chars: int = 0
    truncated: bool = False
    error_type: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class _ReviewCollection:
    """Stable, index-ordered public records derived after the barrier."""

    reviews: tuple[Mapping[str, Any], ...]
    failures: tuple[Mapping[str, Any], ...]


class ParallelPanelRuntimeAlgorithm:
    """Outer runtime adapter for independent parallel candidate review."""

    name = "parallel_panel"

    def __init__(self, runtime: AgentRuntime, algorithm: ParallelPanelAlgorithm) -> None:
        # Stores the producer runtime and immutable panel policy for one configured agent.
        self.runtime = runtime
        self.algorithm = algorithm

    def run(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: SpanContext | None = None,
    ) -> AgentResult:
        # Synchronous entrypoint that drives the async panel coordinator to completion.
        return asyncio.run(
            self.arun(
                message,
                handle=handle,
                context=context,
                metadata=metadata,
                options=options,
                trace_context=trace_context,
            )
        )

    # @intent independent-first-round-barrier
    # Review findings must remain invisible until every first-round branch settles.
    # Creating every task before the first await gives asynchronous runners an equal
    # start, while collecting only after gather prevents completion order, bounded
    # concurrency, or a fast failure from creating a hidden reviewer hierarchy.
    # A plausible but unsafe rewrite would append each result as it arrives; that
    # would leak partial findings through callbacks, recorder state, or metadata and
    # would violate the exact independent-panel contract even if final output looked
    # identical.
    async def arun(
        self,
        message: str,
        *,
        handle: RunnerHandle,
        context: BaseAgentContext,
        metadata: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        trace_context: SpanContext | None = None,
    ) -> AgentResult:
        # Produces one candidate, runs isolated reviewers through a full barrier, and preserves the candidate.
        self.runtime.recorder.append("system_prompt")
        self.runtime.recorder.append("parallel_panel_producer")
        producer = await self.runtime._arun_once(
            message,
            handle=handle,
            context=context,
            metadata=self._producer_metadata(metadata),
            options=dict(options or {}),
            trace_context=trace_context,
        )
        snapshot = self._prepare_snapshot(task=message, producer=producer, context=context)
        concurrency = self._concurrency_record(handle)
        outcomes = await self._await_panel(
            snapshot=snapshot,
            handle=handle,
            trace_context=trace_context,
            concurrency=concurrency,
        )
        collection = self._collect_outcomes(outcomes)
        self.runtime.recorder.append(
            "parallel_panel_barrier",
            successful_review_count=len(collection.reviews),
            failed_review_count=len(collection.failures),
        )
        self._enforce_success_threshold(collection)
        self.runtime.recorder.append(
            "parallel_panel_collection",
            successful_review_count=len(collection.reviews),
            failed_review_count=len(collection.failures),
            review_order=tuple(record["reviewer_id"] for record in collection.reviews),
        )
        return self._build_result(
            producer=producer,
            snapshot=snapshot,
            collection=collection,
            concurrency=concurrency,
        )

    def _producer_metadata(self, metadata: Mapping[str, Any] | None) -> dict[str, Any]:
        # Marks only the producer stage while preserving all caller-supplied runtime metadata.
        return {
            **dict(metadata or {}),
            "context_window_algorithm": self.name,
            "parallel_panel_stage": "producer",
        }

    def _prepare_snapshot(self, *, task: str, producer: AgentResult, context: BaseAgentContext) -> _PanelSnapshot:
        # Validates exact candidate and evidence content before rendering one shared reviewer snapshot.
        candidate = producer.output if isinstance(producer.output, str) else str(producer.output)
        if not candidate.strip():
            raise AgentExecutionError(
                "Parallel panel requires a nonblank producer candidate before review.",
                details={"algorithm": self.name, "stage": "preflight"},
            )
        if len(candidate) > self.algorithm.max_candidate_chars:
            raise AgentExecutionError(
                "Parallel panel producer candidate exceeds max_candidate_chars and cannot be reviewed exactly.",
                details={
                    "algorithm": self.name,
                    "stage": "preflight",
                    "candidate_chars": len(candidate),
                    "max_candidate_chars": self.algorithm.max_candidate_chars,
                },
            )
        artifacts = self._select_artifacts(context)
        rendered_artifacts = self._render_artifacts(artifacts)
        system_prompt = self.algorithm.reviewer_system_prompt_text()
        user_prompt = self.algorithm.render_reviewer_prompt(
            task=task,
            candidate=candidate,
            artifacts=rendered_artifacts,
        )
        return _PanelSnapshot(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            candidate_chars=len(candidate),
            candidate_sha256=hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
            artifact_names=tuple(artifact.name for artifact in artifacts),
            algorithm_metadata=dict(self.algorithm.metadata),
        )

    def _select_artifacts(self, context: BaseAgentContext) -> tuple[ContextArtifact, ...]:
        # Resolves the configured exact-name allowlist through ContextManager abstractions.
        manager = self._evidence_manager(context)
        available = tuple(manager.to_context().artifacts)
        by_name: dict[str, list[ContextArtifact]] = {}
        for artifact in available:
            by_name.setdefault(artifact.name, []).append(artifact)
        selected: list[ContextArtifact] = []
        for name in self.algorithm.artifact_names:
            matches = tuple(by_name.get(name, ()))
            if not matches:
                raise AgentExecutionError(
                    "Parallel panel requested an artifact that is not present in runtime context.",
                    details={"algorithm": self.name, "stage": "preflight", "artifact_name": name},
                )
            if len(matches) != 1:
                raise AgentExecutionError(
                    "Parallel panel artifact selection is ambiguous because a requested name is duplicated.",
                    details={
                        "algorithm": self.name,
                        "stage": "preflight",
                        "artifact_name": name,
                        "match_count": len(matches),
                    },
                )
            artifact = matches[0]
            content_chars = len(artifact.content)
            if content_chars > self.algorithm.max_artifact_chars:
                raise AgentExecutionError(
                    "Parallel panel artifact exceeds max_artifact_chars and cannot be reviewed exactly.",
                    details={
                        "algorithm": self.name,
                        "stage": "preflight",
                        "artifact_name": name,
                        "artifact_chars": content_chars,
                        "max_artifact_chars": self.algorithm.max_artifact_chars,
                    },
                )
            selected.append(artifact)
        rendered_chars = len(self._render_artifacts(selected)) if selected else 0
        if rendered_chars > self.algorithm.max_total_artifact_chars:
            raise AgentExecutionError(
                "Parallel panel evidence exceeds max_total_artifact_chars and cannot be reviewed exactly.",
                details={
                    "algorithm": self.name,
                    "stage": "preflight",
                    "artifact_count": len(selected),
                    "artifact_chars": rendered_chars,
                    "max_total_artifact_chars": self.algorithm.max_total_artifact_chars,
                },
            )
        return tuple(selected)

    def _evidence_manager(self, context: BaseAgentContext) -> ContextManager:
        # Projects producer-visible artifacts into a ContextManager without inheriting history or tools.
        manager = ContextManager()
        for artifact in tuple(context.artifacts):
            if not isinstance(artifact, ContextArtifact):
                continue
            manager.add(
                ArtifactContextItem(
                    name=artifact.name,
                    content=artifact.content,
                    artifact_type=artifact.artifact_type,
                    metadata=dict(artifact.metadata),
                )
            )
        for item in tuple(context.context_items):
            if isinstance(item, ArtifactContextItem):
                manager.add(item)
        return manager

    @staticmethod
    def _render_artifacts(artifacts: Sequence[ContextArtifact]) -> str:
        # Renders only each allowed artifact's name, declared type, and exact content in configured order.
        if not artifacts:
            return NO_ARTIFACTS_PLACEHOLDER
        return "\n\n".join(
            f"### Permitted Artifact: {artifact.name}\nType: {artifact.artifact_type}\nContent:\n{artifact.content}"
            for artifact in artifacts
        )

    def _concurrency_record(self, handle: RunnerHandle) -> dict[str, Any]:
        # Reports whether the runner can yield asynchronously and whether a semaphore bounds calls.
        async_capable = self._runner_is_async_capable(handle.runner)
        if not async_capable:
            mode = "sync_constrained"
        elif self.algorithm.max_concurrency is None:
            mode = "unbounded_async"
        else:
            mode = "bounded_async"
        return {
            "max_concurrency": self.algorithm.max_concurrency,
            "runner_async_capable": async_capable,
            "mode": mode,
        }

    @staticmethod
    def _runner_is_async_capable(runner: object) -> bool:
        # Conservatively detects runner entry points that are declared async before invocation.
        arun = getattr(runner, "arun", None)
        run = getattr(runner, "run", None)
        call = getattr(runner, "__call__", None)
        return (
            inspect.iscoroutinefunction(arun)
            or inspect.iscoroutinefunction(run)
            or inspect.iscoroutinefunction(runner)
            or inspect.iscoroutinefunction(call)
        )

    async def _await_panel(
        self,
        *,
        snapshot: _PanelSnapshot,
        handle: RunnerHandle,
        trace_context: SpanContext | None,
        concurrency: Mapping[str, Any],
    ) -> tuple[_ReviewerOutcome | BaseException, ...]:
        # Creates every reviewer task before awaiting and returns only after the first-round barrier completes.
        semaphore = (
            asyncio.Semaphore(self.algorithm.max_concurrency)
            if self.algorithm.max_concurrency is not None
            else None
        )
        tasks: list[asyncio.Task[_ReviewerOutcome]] = []
        for reviewer_index in range(self.algorithm.reviewer_count):
            reviewer_id = f"reviewer-{reviewer_index + 1}"
            self.runtime.recorder.append(
                "parallel_panel_review",
                iteration=reviewer_index,
                reviewer_id=reviewer_id,
                reviewer_index=reviewer_index,
            )
            tasks.append(
                asyncio.create_task(
                    self._run_reviewer(
                        reviewer_index=reviewer_index,
                        reviewer_id=reviewer_id,
                        snapshot=snapshot,
                        handle=handle,
                        semaphore=semaphore,
                        trace_context=trace_context,
                        concurrency=concurrency,
                    ),
                    name=f"parallel-panel-{reviewer_id}",
                )
            )
        gatherer = asyncio.gather(*tasks, return_exceptions=True)
        try:
            if self.algorithm.panel_timeout_seconds is None:
                return tuple(await gatherer)
            return tuple(await asyncio.wait_for(gatherer, timeout=self.algorithm.panel_timeout_seconds))
        except TimeoutError as exc:
            await self._cancel_tasks(tasks)
            raise AgentExecutionError(
                "Parallel panel exceeded panel_timeout_seconds before the first-round barrier completed.",
                details={
                    "algorithm": self.name,
                    "stage": "panel",
                    "reviewer_count": self.algorithm.reviewer_count,
                    "panel_timeout_seconds": self.algorithm.panel_timeout_seconds,
                },
            ) from exc
        except asyncio.CancelledError:
            await self._cancel_tasks(tasks)
            raise

    @staticmethod
    async def _cancel_tasks(tasks: Sequence[asyncio.Task[_ReviewerOutcome]]) -> None:
        # Cancels unfinished reviewer calls and awaits every cleanup path before control can leave the panel.
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_reviewer(
        self,
        *,
        reviewer_index: int,
        reviewer_id: str,
        snapshot: _PanelSnapshot,
        handle: RunnerHandle,
        semaphore: asyncio.Semaphore | None,
        trace_context: SpanContext | None,
        concurrency: Mapping[str, Any],
    ) -> _ReviewerOutcome:
        # Runs one isolated reviewer inside the optional in-flight concurrency boundary.
        if semaphore is None:
            return await self._invoke_reviewer(
                reviewer_index=reviewer_index,
                reviewer_id=reviewer_id,
                snapshot=snapshot,
                handle=handle,
                trace_context=trace_context,
                concurrency=concurrency,
            )
        async with semaphore:
            return await self._invoke_reviewer(
                reviewer_index=reviewer_index,
                reviewer_id=reviewer_id,
                snapshot=snapshot,
                handle=handle,
                trace_context=trace_context,
                concurrency=concurrency,
            )

    async def _invoke_reviewer(
        self,
        *,
        reviewer_index: int,
        reviewer_id: str,
        snapshot: _PanelSnapshot,
        handle: RunnerHandle,
        trace_context: SpanContext | None,
        concurrency: Mapping[str, Any],
    ) -> _ReviewerOutcome:
        # Invokes one fresh model-only runtime and converts all ordinary failures into private branch outcomes.
        reviewer_runtime = self._build_reviewer_runtime(
            reviewer_id=reviewer_id,
            system_prompt=snapshot.system_prompt,
        )
        reviewer_context = self._build_reviewer_context(
            reviewer_runtime=reviewer_runtime,
            system_prompt=snapshot.system_prompt,
        )
        span = reviewer_runtime._start_semantic_span(
            "algorithm.parallel-panel.review",
            parent=trace_context,
            reviewer_id=reviewer_id,
            reviewer_index=reviewer_index,
            configured_reviewer_count=self.algorithm.reviewer_count,
            concurrency_mode=str(concurrency["mode"]),
        )
        try:
            call = self._invoke_reviewer_call(
                reviewer_runtime=reviewer_runtime,
                reviewer_context=reviewer_context,
                snapshot=snapshot,
                handle=handle,
                trace_context=span,
            )
            raw_result = (
                await asyncio.wait_for(call, timeout=self.algorithm.per_reviewer_timeout_seconds)
                if self.algorithm.per_reviewer_timeout_seconds is not None
                else await call
            )
            outcome = self._reviewer_success(
                reviewer_index=reviewer_index,
                reviewer_id=reviewer_id,
                raw_result=raw_result,
                handle=handle,
            )
            reviewer_runtime._end_semantic_span(span, output="success" if outcome.success else "failure")
            return outcome
        except TimeoutError:
            reviewer_runtime._end_semantic_span(
                span,
                error=AgentExecutionError("Parallel panel reviewer timed out."),
            )
            return self._reviewer_failure(
                reviewer_index=reviewer_index,
                reviewer_id=reviewer_id,
                error_type="TimeoutError",
                reason="Reviewer exceeded per_reviewer_timeout_seconds.",
            )
        except asyncio.CancelledError as exc:
            reviewer_runtime._end_semantic_span(span, error=exc)
            raise
        except Exception as exc:
            reviewer_runtime._end_semantic_span(
                span,
                error=AgentExecutionError("Parallel panel reviewer failed."),
            )
            return self._reviewer_failure(
                reviewer_index=reviewer_index,
                reviewer_id=reviewer_id,
                error_type=type(exc).__name__,
                reason="Reviewer call failed before producing a usable review.",
            )
        except BaseException:
            reviewer_runtime._end_semantic_span(
                span,
                error=AgentExecutionError("Parallel panel reviewer was interrupted."),
            )
            raise

    def _build_reviewer_runtime(self, *, reviewer_id: str, system_prompt: str) -> AgentRuntime:
        # Constructs a fresh runtime with empty middleware, empty tools, and no implicit internal capability.
        from vidbyte.agents.runtime import AgentRuntime

        return AgentRuntime(
            agent_name=f"{self.runtime.agent_name}-{reviewer_id}",
            system_prompt=system_prompt,
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            tracer=self.runtime._tracer,
            middleware=(),
            algorithm=None,
            context_manager=ContextManager(),
            recorder=NullRecorder(),
            output_schema=None,
            output_contract=None,
            include_internal_tools=False,
        )

    def _build_reviewer_context(self, *, reviewer_runtime: AgentRuntime, system_prompt: str) -> BaseAgentContext:
        # Builds an allowlist-only context through ContextManager so producer fields cannot leak by default.
        manager = ContextManager()
        base = BaseContext(system_prompt=system_prompt)
        return reviewer_runtime.build_context(
            "",
            base_context=base,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
            input_metadata={},
            modality=None,
            agentic_loop=False,
            context_items=(),
            context_manager=manager,
        )

    async def _invoke_reviewer_call(
        self,
        *,
        reviewer_runtime: AgentRuntime,
        reviewer_context: BaseAgentContext,
        snapshot: _PanelSnapshot,
        handle: RunnerHandle,
        trace_context: SpanContext | None,
    ) -> object | AgentResult:
        # Calls the shared handle with only the identical reviewer system and user prompt strings.
        raw_result, _, _ = await reviewer_runtime._invoke_with_middleware(
            handle,
            snapshot.user_prompt,
            {"system": snapshot.system_prompt},
            context=reviewer_context,
            iteration_count=0,
            model_call_count=0,
            call_contexts=(),
            tokens_used=None,
            started_at=reviewer_runtime.middleware.clock(),
            metadata={
                "context_window_algorithm": self.name,
                "parallel_panel_stage": "review",
                "configured_reviewer_count": self.algorithm.reviewer_count,
            },
            run_state={},
            trace_context=trace_context,
        )
        return raw_result

    def _reviewer_success(
        self,
        *,
        reviewer_index: int,
        reviewer_id: str,
        raw_result: object | AgentResult,
        handle: RunnerHandle,
    ) -> _ReviewerOutcome:
        # Extracts and bounds a nonblank ordinary runner response without accepting runtime control results.
        if isinstance(raw_result, AgentResult):
            return self._reviewer_failure(
                reviewer_index=reviewer_index,
                reviewer_id=reviewer_id,
                error_type="UnexpectedAgentResult",
                reason="Reviewer model call returned an unexpected runtime result.",
            )
        review = handle.extract_text(raw_result).strip()
        if not review:
            return self._reviewer_failure(
                reviewer_index=reviewer_index,
                reviewer_id=reviewer_id,
                error_type="BlankReview",
                reason="Reviewer returned a blank review.",
            )
        bounded = self._bound_review(review)
        return _ReviewerOutcome(
            reviewer_index=reviewer_index,
            reviewer_id=reviewer_id,
            success=True,
            content=bounded.content,
            content_chars=len(bounded.content),
            truncated=bounded.truncated,
        )

    def _bound_review(self, review: str) -> _BoundedReview:
        # Bounds advisory review text after completion while retaining an explicit truncation marker when possible.
        if len(review) <= self.algorithm.max_review_chars:
            return _BoundedReview(content=review, truncated=False)
        if self.algorithm.max_review_chars <= len(REVIEW_TRUNCATION_SUFFIX):
            return _BoundedReview(content=review[: self.algorithm.max_review_chars], truncated=True)
        content = (
            review[: self.algorithm.max_review_chars - len(REVIEW_TRUNCATION_SUFFIX)].rstrip()
            + REVIEW_TRUNCATION_SUFFIX
        )
        return _BoundedReview(content=content, truncated=True)

    @staticmethod
    def _reviewer_failure(
        *,
        reviewer_index: int,
        reviewer_id: str,
        error_type: str,
        reason: str,
    ) -> _ReviewerOutcome:
        # Creates a bounded SDK-authored failure record with no provider or prompt body.
        return _ReviewerOutcome(
            reviewer_index=reviewer_index,
            reviewer_id=reviewer_id,
            success=False,
            error_type=error_type[:120],
            reason=reason[:300],
        )

    def _collect_outcomes(self, outcomes: Sequence[_ReviewerOutcome | BaseException]) -> _ReviewCollection:
        # Converts gather results to stable reviewer-index records only after the barrier has completed.
        reviews: list[Mapping[str, Any]] = []
        failures: list[Mapping[str, Any]] = []
        for reviewer_index, raw_outcome in enumerate(outcomes):
            reviewer_id = f"reviewer-{reviewer_index + 1}"
            outcome = (
                raw_outcome
                if isinstance(raw_outcome, _ReviewerOutcome)
                else self._reviewer_failure(
                    reviewer_index=reviewer_index,
                    reviewer_id=reviewer_id,
                    error_type=type(raw_outcome).__name__,
                    reason="Reviewer task failed before producing a usable review.",
                )
            )
            if outcome.success:
                reviews.append(
                    {
                        "reviewer_id": reviewer_id,
                        "reviewer_index": reviewer_index,
                        "content": outcome.content,
                        "content_chars": outcome.content_chars,
                        "truncated": outcome.truncated,
                    }
                )
            else:
                failures.append(
                    {
                        "reviewer_id": reviewer_id,
                        "reviewer_index": reviewer_index,
                        "error_type": outcome.error_type,
                        "reason": outcome.reason,
                    }
                )
        return _ReviewCollection(reviews=tuple(reviews), failures=tuple(failures))

    def _enforce_success_threshold(self, collection: _ReviewCollection) -> None:
        # Fails closed after the barrier when too few independent reviews survived.
        if len(collection.reviews) >= self.algorithm.min_successful_reviews:
            return
        raise AgentExecutionError(
            "Parallel panel completed its barrier below min_successful_reviews; no findings were published.",
            details={
                "algorithm": self.name,
                "stage": "collection",
                "successful_review_count": len(collection.reviews),
                "minimum_successful_reviews": self.algorithm.min_successful_reviews,
                "failures": tuple(
                    {"reviewer_id": record["reviewer_id"], "error_type": record["error_type"]}
                    for record in collection.failures
                ),
            },
        )

    def _build_result(
        self,
        *,
        producer: AgentResult,
        snapshot: _PanelSnapshot,
        collection: _ReviewCollection,
        concurrency: Mapping[str, Any],
    ) -> AgentResult:
        # Preserves every producer result field and adds only namespaced advisory panel metadata.
        review_order = tuple(str(record["reviewer_id"]) for record in collection.reviews)
        panel_metadata = {
            "candidate_chars": snapshot.candidate_chars,
            "candidate_sha256": snapshot.candidate_sha256,
            "configured_reviewer_count": self.algorithm.reviewer_count,
            "successful_review_count": len(collection.reviews),
            "minimum_successful_reviews": self.algorithm.min_successful_reviews,
            "review_order": review_order,
            "reviews": collection.reviews,
            "failures": collection.failures,
            "barrier_completed": True,
            "peer_findings_visible_during_round": False,
            "findings_adjudicated": False,
            "candidate_revised": False,
            "concurrency": dict(concurrency),
            "artifact_names": snapshot.artifact_names,
            "user_metadata": dict(snapshot.algorithm_metadata),
        }
        result_metadata = {
            **dict(producer.metadata),
            "context_window_algorithm": self.name,
            "parallel_panel": panel_metadata,
        }
        return AgentResult(
            output=producer.output,
            strategy_name=producer.strategy_name,
            calls=producer.calls,
            metadata=result_metadata,
            structured=producer.structured,
        )


__all__ = ["ParallelPanelRuntimeAlgorithm"]
