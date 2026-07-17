"""Context Protocol Header

FILE:
    vidbyte/agents/adversarial/runtime.py owns the deterministic run controller
    that AdversarialAgent delegates one run to, plus the internal request/outcome
    bridges that thread state between the connector and the loop.
PURPOSE:
    Holds the isolated run-local child forks, the exact call ordering, threshold
    enforcement invocation, tracing, and cleanup for one adversarial run. Keeping
    this here is what lets AdversarialAgent stay a thin connector: orchestration is
    delegated, not embedded in the agent.
ROLE IN CODEBASE:
    Constructed per run by AdversarialAgent.generate_reply. Calls
    BaseAgent.fork()/generate_reply(), AdversarialContext for all context-window
    mechanics, and AdversarialSettings.enforce_review_threshold for the review
    floor. Returns an _AdversarialRunOutcome the connector commits.
ARCHITECTURE NOTE:
    The threshold DECISION lives on AdversarialSettings; this controller only
    invokes it with run-local context. Prompt/snapshot/bounding mechanics live on
    AdversarialContext. This module owns sequencing, isolation, and lifecycle only.
FOLLOW-UP (deferred — runtime/strategy design, do not action here yet):
    This controller hard-codes exactly one adversarial type (sequential
    independent review -> producer revise). The approved follow-up reshapes it into
    a Template-Method AdversarialRuntime whose run() is a fixed skeleton with
    overridable produce/should_continue/review/adjudicate/resolve/finalize hooks,
    a swappable ReviewerRoster (roster.py) and ReviewerPhase (phases.py), and an
    adjudicate step. That reshape, structured findings, and the strategy presets
    are intentionally NOT done in this pass.
WHAT NOT TO DO IN THIS FILE:
    Do not add early stopping or skip later reviewers after a failure; those
    rewrites would make adversarial_rounds a best-effort maximum and invalidate the
    public call formula. Do not re-derive the review-threshold rule inline; call
    the settings helper. Do not parallelize reviewer calls until child runner/tool
    concurrency is explicit.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vidbyte.agents.adversarial.context import AdversarialContext
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentForkSettings, AgentInput, AgentMessage
from vidbyte.context import BaseContext
from vidbyte.lib.dataclasses.adversarial import AdversarialResult, AdversarialReview, AdversarialRoundResult, AdversarialSettings
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.errors import AdversarialExecutionError, ConfigurationError
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.tools.types import ToolCallContext


@dataclass(frozen=True, slots=True)
class _AdversarialRunRequest:
    """Immutable caller state forwarded to every worker pass in one facade run."""

    message: str | AgentInput
    original_prompt: str
    modality: ModelModality | str | None
    context: BaseContext | None
    history: tuple[AgentMessage, ...]
    options: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _AdversarialRunOutcome:
    """Internal bridge from child orchestration back to facade lifecycle state."""

    result: AdversarialResult
    final_worker_reply: AgentMessage
    tool_call_contexts: tuple[ToolCallContext, ...]


class _AdversarialRunController:
    """Own one run's isolated children, exact call ordering, and cleanup."""

    def __init__(self, *, facade_name: str, workflow_instructions: str, worker_prototype: BaseAgent, adversary_prototype: BaseAgent, settings: AdversarialSettings, context: AdversarialContext, tracer: TracerBase, trace_context: SpanContext, request: _AdversarialRunRequest) -> None:
        # Capture immutable orchestration inputs and initialize run-local child state.
        self._facade_name = facade_name
        self._workflow_instructions = workflow_instructions
        self._worker_prototype = worker_prototype
        self._adversary_prototype = adversary_prototype
        self._settings = settings
        self._context = context
        self._tracer = tracer
        self._trace_context = trace_context
        self._request = request
        self._worker: BaseAgent | None = None
        self._adversaries: list[BaseAgent] = []
        self._run_agents: list[BaseAgent] = []

    # @intent exact-adversarial-sequence
    # The facade promises a predictable cost and review contract: one initial worker
    # pass, then every configured reviewer followed by exactly one worker revision for
    # each configured round. Reviewers see the same immutable snapshot within a round.
    # Do not add early stopping or skip later reviewers after a failure; those rewrites
    # would make adversarial_rounds a best-effort maximum and invalidate the public call
    # formula. Partial reviewer failures are represented as data and evaluated only after
    # all reviewers for that round have had their configured attempt.
    async def run(self) -> _AdversarialRunOutcome:
        # Execute the exact staged workflow and always release resources owned by run-local forks.
        try:
            self._fork_run_agents()
            initial_reply = await self._call_worker(self._context.render_initial_worker_prompt(self._workflow_instructions, self._request.original_prompt), phase="initial_worker", round_index=0)
            rounds, final_reply, successful, failed = await self._run_rounds(initial_reply)
            result = self._build_result(initial_reply, rounds, final_reply, successful, failed)
            return _AdversarialRunOutcome(result=result, final_worker_reply=final_reply, tool_call_contexts=tuple(self._require_worker()._tool_call_contexts))
        finally:
            await self._close_run_agents()

    def _fork_run_agents(self) -> None:
        # Create one worker and the configured reviewer set before the first model call.
        self._worker = self._fork_prototype(self._worker_prototype, f"{self._facade_name}:worker")
        self._adversaries = [
            self._fork_prototype(self._adversary_prototype, f"{self._facade_name}:adversary:{index}")
            for index in range(1, self._settings.num_adversaries + 1)
        ]

    # @intent prototype-behavior-preservation
    # Child forks isolate mutable histories and MCP lifecycles, but they must not erase a
    # specialized prototype's behavior. A plausible fallback to BaseAgent would preserve
    # provider configuration while silently discarding aggregation, continual tracing, or
    # another subtype's execution semantics. Fail before the first model call so callers
    # can supply an exact BaseAgent or implement a subtype-preserving fork contract.
    def _fork_prototype(self, prototype: BaseAgent, child_name: str) -> BaseAgent:
        # Invoke the prototype's public fork API and validate that its behavioral subtype survives.
        try:
            parameters = inspect.signature(prototype.fork).parameters
            child = prototype.fork(AgentForkSettings(name=child_name)) if "settings" in parameters else prototype.fork(name=child_name)
        except Exception as exc:
            raise ConfigurationError(
                f"AdversarialAgent could not fork child prototype '{prototype.name}'.",
                details={
                    "facade": self._facade_name,
                    "prototype": prototype.name,
                    "prototype_type": type(prototype).__name__,
                    "child_name": child_name,
                    "error_type": type(exc).__name__,
                    "expected": "a public subtype-preserving fork implementation",
                    "remediation": "Use an exact BaseAgent or implement fork() on the specialized subtype.",
                },
            ) from exc
        if isinstance(child, BaseAgent):
            self._run_agents.append(child)
        if not isinstance(child, type(prototype)):
            raise ConfigurationError(
                f"AdversarialAgent child fork erased prototype subtype '{type(prototype).__name__}'.",
                details={
                    "facade": self._facade_name,
                    "prototype": prototype.name,
                    "expected_type": type(prototype).__name__,
                    "actual_type": type(child).__name__,
                    "child_name": child_name,
                    "remediation": "Use an exact BaseAgent or implement a subtype-preserving fork() override.",
                },
            )
        return child

    async def _run_rounds(self, initial_reply: AgentMessage) -> tuple[list[AdversarialRoundResult], AgentMessage, int, int]:
        # Reuse the same run-local worker and reviewer per index across all exact rounds.
        rounds: list[AdversarialRoundResult] = []
        current_reply = initial_reply
        successful_total = 0
        failed_total = 0
        for round_index in range(1, self._settings.adversarial_rounds + 1):
            round_result, current_reply, successful, failed = await self._run_round(round_index, current_reply)
            rounds.append(round_result)
            successful_total += successful
            failed_total += failed
        return rounds, current_reply, successful_total, failed_total

    async def _run_round(self, round_index: int, current_reply: AgentMessage) -> tuple[AdversarialRoundResult, AgentMessage, int, int]:
        # Review one immutable worker snapshot, enforce the threshold, and request one full revision.
        snapshot = self._context.snapshot(current_reply.content)
        reviews = await self._collect_reviews(round_index, snapshot)
        successful_reviews = tuple(review for review in reviews if review.error is None)
        failed_count = len(reviews) - len(successful_reviews)
        self._enforce_review_threshold(round_index, successful_reviews, reviews)
        revision_prompt = self._context.render_revision_prompt(self._workflow_instructions, self._request.original_prompt, snapshot, successful_reviews, round_index=round_index)
        revised_reply = await self._call_worker(revision_prompt, phase="worker_revision", round_index=round_index)
        result = AdversarialRoundResult(round_index=round_index, reviewed_worker_output=snapshot, reviews=tuple(reviews), revised_worker_output=revised_reply.content)
        return result, revised_reply, len(successful_reviews), failed_count

    async def _collect_reviews(self, round_index: int, worker_output: str) -> list[AdversarialReview]:
        # Call reviewer forks sequentially so shared runner/tool objects never receive implicit concurrency.
        reviews: list[AdversarialReview] = []
        for adversary_index, adversary in enumerate(self._adversaries, start=1):
            prompt = self._context.render_review_prompt(self._workflow_instructions, self._request.original_prompt, worker_output, round_index=round_index, adversary_index=adversary_index)
            reviews.append(await self._call_adversary(adversary, prompt, round_index, adversary_index))
        return reviews

    async def _call_adversary(self, adversary: BaseAgent, prompt: str, round_index: int, adversary_index: int) -> AdversarialReview:
        # Convert ordinary reviewer errors, timeouts, and blank replies into ordered partial-failure records.
        span = self._tracer.start_span("adversarial.review", parent=self._trace_context, agent_name=adversary.name, role="reviewer", status="started", round_index=round_index, adversary_index=adversary_index)
        trace_metadata = {
            "adversarial_facade": self._facade_name,
            "adversarial_role": "reviewer",
            "adversarial_round": round_index,
            "adversarial_index": adversary_index,
        }
        try:
            call = adversary.generate_reply(prompt, recipient=self._facade_name, trace_metadata=trace_metadata)
            reply = await call if self._settings.per_adversary_timeout is None else await asyncio.wait_for(call, timeout=self._settings.per_adversary_timeout)
            content = reply.content
            if not content.strip():
                raise ValueError("blank adversary reply")
            metadata = {"content_chars": len(content), "reply_metadata_keys": tuple(sorted(str(key) for key in reply.metadata))}
            self._tracer.end_span(span, output=f"{len(content)} characters")
            return AdversarialReview(round_index=round_index, adversary_index=adversary_index, adversary_name=adversary.name, content=content, metadata=metadata)
        except Exception as exc:
            self._tracer.end_span(span, error=exc)
            return AdversarialReview(
                round_index=round_index,
                adversary_index=adversary_index,
                adversary_name=adversary.name,
                error=f"{type(exc).__name__}: adversary review failed",
                metadata={"error_type": type(exc).__name__},
            )
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise

    async def _call_worker(self, prompt: str, *, phase: str, round_index: int) -> AgentMessage:
        # Forward the original typed input context and safe call options to the same run-local worker.
        worker = self._require_worker()
        span = self._tracer.start_span("adversarial.worker", parent=self._trace_context, agent_name=worker.name, role="worker", status="started", phase=phase, round_index=round_index)
        try:
            options = self._worker_options(phase, round_index)
            forwarded_message = self._context.message_with_prompt(self._request.message, prompt)
            reply = await worker.generate_reply(forwarded_message, context=self._request.context, history=self._request.history, recipient=self._facade_name, **options)
        except Exception as exc:
            self._tracer.end_span(span, error=exc)
            raise self._worker_error(worker, phase, round_index, error_type=type(exc).__name__, actual="worker generate_reply raised") from exc
        except BaseException as exc:
            self._tracer.end_span(span, error=exc)
            raise
        if not reply.content.strip():
            error = self._worker_error(worker, phase, round_index, error_type="BlankWorkerOutput", actual="worker returned blank content")
            self._tracer.end_span(span, error=error)
            raise error
        self._tracer.end_span(span, output=f"{len(reply.content)} characters")
        return reply

    def _worker_options(self, phase: str, round_index: int) -> dict[str, Any]:
        # Copy caller options, preserve their trace metadata, and add bounded workflow routing fields.
        options = dict(self._request.options)
        trace_metadata = dict(options.pop("trace_metadata", {}) or {})
        trace_metadata.update(
            {
                "adversarial_facade": self._facade_name,
                "adversarial_role": "worker",
                "adversarial_phase": phase,
                "adversarial_round": round_index,
            }
        )
        options["trace_metadata"] = trace_metadata
        if self._request.modality is not None:
            options["modality"] = self._request.modality
        return options

    def _enforce_review_threshold(self, round_index: int, successful: Sequence[AdversarialReview], all_reviews: Sequence[AdversarialReview]) -> None:
        # Delegate the review-floor decision to the settings, supplying run-local diagnostic context.
        failed = [review.adversary_name for review in all_reviews if review.error is not None]
        self._settings.enforce_review_threshold(
            len(successful),
            len(all_reviews),
            context={
                "function": "_AdversarialRunController._enforce_review_threshold",
                "facade": self._facade_name,
                "round_index": round_index,
                "failed_adversaries": failed,
            },
        )

    def _worker_error(self, worker: BaseAgent, phase: str, round_index: int, *, error_type: str, actual: str) -> AdversarialExecutionError:
        # Build a safe diagnostic packet without embedding prompts, replies, credentials, or exception text.
        return AdversarialExecutionError(
            f"Adversarial worker '{worker.name}' failed during {phase} at round {round_index}.",
            details={
                "file": "vidbyte/agents/adversarial/runtime.py",
                "function": "_AdversarialRunController._call_worker",
                "facade": self._facade_name,
                "worker": worker.name,
                "phase": phase,
                "round_index": round_index,
                "error_type": error_type,
                "expected": "a successful non-blank worker AgentMessage",
                "actual": actual,
                "remediation": "Inspect the worker prototype's provider, model, tools, trace, and output contract.",
            },
        )

    def _build_result(self, initial_reply: AgentMessage, rounds: Sequence[AdversarialRoundResult], final_reply: AgentMessage, successful: int, failed: int) -> AdversarialResult:
        # Retain full successful artifacts while keeping summary metadata small and deterministic.
        metadata = {
            "num_adversaries": self._settings.num_adversaries,
            "adversarial_rounds": self._settings.adversarial_rounds,
            "completed_rounds": len(rounds),
            "child_call_count": 1 + self._settings.adversarial_rounds * (self._settings.num_adversaries + 1),
            "worker_name": self._worker_prototype.name,
            "adversary_name": self._adversary_prototype.name,
        }
        return AdversarialResult(initial_worker_output=initial_reply.content, rounds=tuple(rounds), final_output=final_reply.content, successful_review_count=successful, failed_review_count=failed, metadata=metadata)

    def _require_worker(self) -> BaseAgent:
        # Keep controller helper assumptions explicit for cold debugging and type narrowing.
        if self._worker is None:
            raise ConfigurationError(
                "Adversarial run-local worker was not initialized.",
                details={"facade": self._facade_name, "phase": "fork_children", "expected": "worker fork before execution"},
            )
        return self._worker

    async def _close_run_agents(self) -> None:
        # Close only run-local MCP handles; prototypes remain reusable across facade runs.
        if not self._run_agents:
            return
        cleanup = asyncio.gather(*(agent.close_mcp_servers() for agent in self._run_agents), return_exceptions=True)
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
            raise
