"""Context Protocol Header

Description:
    Defines the adversarial-agent custom trace under vidbyte.trace: a typed
    continual schema, semantic span factory, and fail-open controller that
    explicitly records worker vs adversary phase boundaries.
Purpose:
    Makes adversarial runs inspectable so traces show the worker producer and
    the adversary reviewers as distinct roles — matching other custom traces
    (ActionTrace schema, MultiAgentTrace spans, AggregateTrace spans).
Architecture:
    - AdversarialAgentTraceModel / AdversarialAgentTrace: typed schema for the
      structured artifact (worker_events, adversary_events, round_status, …).
    - AdversarialTrace: semantic SpanSpec factory (adversarial.run/worker/
      adversary/round/finalize) routed by TraceController.
    - AdversarialAgentTraceController: deterministic, fail-open accumulator
      driven by runtime phase events; no extra model calls so the public
      child-call formula stays exact.
Relations:
    Used by vidbyte.agents.adversarial.runtime / agent. Re-exported by
    vidbyte.trace. Depends on TraceSchema and SpanSpec contracts.
Similar Files:
    - vidbyte/trace/continual/prebuilt.py
    - vidbyte/trace/components/agents.py
    - vidbyte/agents/multi/tracing.py
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema
from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail

_MAX_PREVIEW_CHARS = 2000


class AdversarialAgentTraceModel(BaseModel):
    """Tracks worker production, adversary challenges, and revision progress for one adversarial run."""

    original_task: str = Field(
        description=(
            "The caller's original task text that the adversarial facade is refining. Set this "
            "once from the first update and keep it stable for the rest of the run so later "
            "worker and adversary events stay anchored to the same request."
        ),
    )
    worker_name: str = Field(
        description=(
            "Name of the run-local worker child agent that produces and revises candidates. "
            "Record it when the run starts and do not rename it mid-run; this field is how the "
            "trace distinguishes producer work from reviewer work."
        ),
    )
    adversary_name: str = Field(
        description=(
            "Name of the adversary prototype whose forks perform sequential reviews. Record it "
            "when the run starts so every review event can be attributed to the adversarial side "
            "of the facade rather than the worker."
        ),
    )
    worker_events: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only log of worker phases: initial production and each revision. Each entry "
            "should name the phase, round index, and a one-line essence of the worker output or "
            "failure. Never rewrite prior worker events; only append the event that just finished."
        ),
    )
    adversary_events: list[str] = Field(
        default_factory=list,
        description=(
            "Append-only log of adversary review attempts. Each entry should name the round, "
            "adversary index/name, success or failure, and a one-line summary of the challenge. "
            "Append only; do not edit earlier adversary events."
        ),
    )
    round_status: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map from round index (string key) to the latest known status for that round, such as "
            "'reviewing', 'revising', 'completed', or 'threshold_failed'. Update only the round "
            "that just changed so other rounds keep their prior values."
        ),
    )
    mistakes: list[str] = Field(
        default_factory=list,
        description=(
            "Reviewer failures, blank worker outputs, threshold misses, or other mistakes observed "
            "during the adversarial run. Append new entries only; keep prior mistakes unless the "
            "context shows they were not actually mistakes."
        ),
    )
    current_status: str = Field(
        description=(
            "Latest overall state of the adversarial run: which phase is active, how many rounds "
            "completed, how many reviews succeeded or failed, and what remains. Replace this on "
            "every update so it always reflects the most recent worker/adversary progress."
        ),
    )


AdversarialAgentTrace = TraceSchema.from_model(
    AdversarialAgentTraceModel,
    name="adversarial_agent_trace",
    description="Tracks worker production, adversary challenges, and revision progress for one adversarial run.",
)


class AdversarialTrace:
    """Factory for adversarial-agent semantic spans that distinguish worker vs adversary roles."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Root adversarial facade run under the agent trace.
        return SpanSpec("adversarial.run", SpanKind.CHAIN, "adversarial", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def worker(**attributes: Any) -> SpanSpec:
        # One worker production or revision phase.
        return SpanSpec("adversarial.worker", SpanKind.CHAIN, "adversarial", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def adversary(**attributes: Any) -> SpanSpec:
        # One adversary review attempt.
        return SpanSpec("adversarial.adversary", SpanKind.CHAIN, "adversarial", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def round(**attributes: Any) -> SpanSpec:
        # One full review + revision round.
        return SpanSpec("adversarial.round", SpanKind.CHAIN, "adversarial", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def finalize(**attributes: Any) -> SpanSpec:
        # Final result assembly after all configured rounds.
        return SpanSpec("adversarial.finalize", SpanKind.CHAIN, "adversarial", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)


class AdversarialAgentTraceController:
    """Deterministic, fail-open accumulator for one adversarial run's worker/adversary trace.

    Fills AdversarialAgentTrace fields from phase boundaries without extra model
    calls, so the public child-call formula stays exact. Safe to call from the
    run controller on every worker and adversary completion.
    """

    def __init__(self, *, schema: TraceSchema = AdversarialAgentTrace) -> None:
        # Own a complete empty artifact keyed by every declared schema field.
        self._schema = schema
        self._artifact: dict[str, Any] = {
            "original_task": "",
            "worker_name": "",
            "adversary_name": "",
            "worker_events": [],
            "adversary_events": [],
            "round_status": {},
            "mistakes": [],
            "current_status": "not_started",
        }
        self.update_count = 0
        self.error_count = 0
        self.last_error: str | None = None

    def record_start(
        self,
        *,
        original_task: str,
        worker_name: str,
        adversary_name: str,
        num_adversaries: int,
        adversarial_rounds: int,
    ) -> None:
        # Seed identities and configuration for both child roles.
        try:
            self._artifact["original_task"] = original_task[:_MAX_PREVIEW_CHARS]
            self._artifact["worker_name"] = worker_name
            self._artifact["adversary_name"] = adversary_name
            self._artifact["current_status"] = (
                f"started: worker={worker_name}, adversary={adversary_name}, "
                f"num_adversaries={num_adversaries}, rounds={adversarial_rounds}"
            )
            self.update_count += 1
            self.last_error = None
        except Exception as exc:
            self._record_error(exc)

    def record_worker(
        self,
        *,
        phase: str,
        round_index: int,
        worker_name: str,
        content_preview: str,
        failed: bool = False,
    ) -> None:
        # Append one worker production or revision event.
        try:
            preview = (content_preview or "").strip().replace("\n", " ")
            if len(preview) > 240:
                preview = preview[:240] + "..."
            outcome = "failed" if failed else "ok"
            entry = f"worker[{worker_name}] phase={phase} round={round_index} {outcome}: {preview or '(empty)'}"
            self._artifact["worker_events"] = [*list(self._artifact.get("worker_events") or []), entry]
            if failed:
                self._artifact["mistakes"] = [*list(self._artifact.get("mistakes") or []), entry]
            self._artifact["current_status"] = f"worker {phase} round={round_index} ({outcome})"
            if phase == "worker_revision":
                status = dict(self._artifact.get("round_status") or {})
                status[str(round_index)] = "revising" if not failed else "worker_failed"
                self._artifact["round_status"] = status
            self.update_count += 1
            self.last_error = None
        except Exception as exc:
            self._record_error(exc)

    def record_adversary(
        self,
        *,
        round_index: int,
        adversary_index: int,
        adversary_name: str,
        content_preview: str = "",
        error: str | None = None,
    ) -> None:
        # Append one adversary review attempt with success or failure.
        try:
            failed = error is not None
            preview = (error or content_preview or "").strip().replace("\n", " ")
            if len(preview) > 240:
                preview = preview[:240] + "..."
            outcome = "failed" if failed else "ok"
            entry = (
                f"adversary[{adversary_name}] round={round_index} index={adversary_index} "
                f"{outcome}: {preview or '(empty)'}"
            )
            self._artifact["adversary_events"] = [*list(self._artifact.get("adversary_events") or []), entry]
            if failed:
                self._artifact["mistakes"] = [*list(self._artifact.get("mistakes") or []), entry]
            status = dict(self._artifact.get("round_status") or {})
            status[str(round_index)] = "reviewing"
            self._artifact["round_status"] = status
            self._artifact["current_status"] = (
                f"adversary review round={round_index} index={adversary_index} ({outcome})"
            )
            self.update_count += 1
            self.last_error = None
        except Exception as exc:
            self._record_error(exc)

    def record_round_complete(self, *, round_index: int, successful_reviews: int, failed_reviews: int) -> None:
        # Mark one review+revision round finished.
        try:
            status = dict(self._artifact.get("round_status") or {})
            status[str(round_index)] = f"completed (ok={successful_reviews}, failed={failed_reviews})"
            self._artifact["round_status"] = status
            self._artifact["current_status"] = (
                f"round {round_index} completed: successful_reviews={successful_reviews}, "
                f"failed_reviews={failed_reviews}"
            )
            self.update_count += 1
            self.last_error = None
        except Exception as exc:
            self._record_error(exc)

    def finalize(self, *, successful_review_count: int, failed_review_count: int, completed_rounds: int) -> None:
        # Record the terminal summary after the staged run completes.
        try:
            self._artifact["current_status"] = (
                f"completed: rounds={completed_rounds}, successful_reviews={successful_review_count}, "
                f"failed_reviews={failed_review_count}"
            )
            self.update_count += 1
            self.last_error = None
        except Exception as exc:
            self._record_error(exc)

    def snapshot(self) -> dict[str, Any]:
        # Return a serializable copy of the accumulated trace artifact.
        return {
            "original_task": self._artifact.get("original_task") or "",
            "worker_name": self._artifact.get("worker_name") or "",
            "adversary_name": self._artifact.get("adversary_name") or "",
            "worker_events": list(self._artifact.get("worker_events") or []),
            "adversary_events": list(self._artifact.get("adversary_events") or []),
            "round_status": dict(self._artifact.get("round_status") or {}),
            "mistakes": list(self._artifact.get("mistakes") or []),
            "current_status": self._artifact.get("current_status") or "",
        }

    def metadata(self) -> dict[str, Any]:
        # Return compact trace bookkeeping for result/message metadata.
        summary: dict[str, Any] = {
            "schema": self._schema.name,
            "update_count": self.update_count,
            "error_count": self.error_count,
            "worker_event_count": len(self._artifact.get("worker_events") or []),
            "adversary_event_count": len(self._artifact.get("adversary_events") or []),
        }
        if self.last_error:
            summary["last_error"] = self.last_error
        return summary

    def _record_error(self, exc: BaseException) -> None:
        # Fail open: never raise into the adversarial run.
        self.error_count += 1
        self.last_error = f"{type(exc).__name__}: {exc}"


__all__ = [
    "AdversarialAgentTrace",
    "AdversarialAgentTraceController",
    "AdversarialAgentTraceModel",
    "AdversarialTrace",
]
