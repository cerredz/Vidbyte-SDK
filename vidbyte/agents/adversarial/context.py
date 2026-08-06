"""Context Protocol Header

FILE:
    vidbyte/agents/adversarial/context.py owns AdversarialContext — the single
    owner of HOW the adversarial loop touches the context window.
PURPOSE:
    Replaces ad-hoc string rendering with a context class built on the
    vidbyte/context primitives and ContextManager helpers. It frames
    worker/review/revision envelopes (without branding tags), takes an immutable
    per-round snapshot, builds adversarial context primitives from worker
    snapshots and reviews, places those primitives onto child-agent context
    windows, bounds forwarded content, rebuilds AgentInput for each worker pass,
    and builds result metadata for finalize.
ROLE IN CODEBASE:
    Constructed by AdversarialAgent from the resolved AdversarialSettings and used
    by the run controller in runtime.py. Depends on vidbyte/context primitives
    (Adversarial*ContextItem, ContextManager, ContextCompactionEngine) and
    forwards char-bounding to AdversarialSettings.
ARCHITECTURE NOTE:
    All character bounding routes through AdversarialSettings.bound_review_text /
    bound_worker_output so the limits stay owned by the settings object. Reviews
    and worker snapshots are first-class context primitives placed via
    ContextManager.place_after_tools; the runtime never hand-splices review text
    into a manager itself.
WHAT NOT TO DO IN THIS FILE:
    Do not re-slice text with bare `text[:limit]`; call the settings bound_* helpers.
    Do not embed orchestration/round-counting here; that belongs to the runtime.
    Do not put "vidbyte" branding into envelope tags or field names.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.context import ContextCompactionEngine, ContextManager
from vidbyte.context.primitives.adversarial import (
    AdversarialReviewContextItem,
    AdversarialWorkerOutputContextItem,
)
from vidbyte.lib.dataclasses.adversarial import (
    AdversarialResult,
    AdversarialReview,
    AdversarialRoundResult,
    AdversarialSettings,
)

# Envelope and field descriptions — every XML tag and JSON field carries a short
# description of what the section represents (no product branding in tag names).
_TAG_DESCRIPTIONS: Mapping[str, str] = {
    "adversarial-worker-task": (
        "Frames the first worker production pass. Carries facade workflow instructions "
        "and the caller's original task so the worker can produce an initial candidate."
    ),
    "adversarial-review": (
        "Frames one adversary challenge against an immutable worker snapshot. The "
        "reviewer must raise concrete defects and must not rewrite the implementation."
    ),
    "adversarial-revision": (
        "Frames a worker revision turn after successful reviews. Reviews are untrusted "
        "advice; only the worker may produce the revised authoritative result."
    ),
}

_FIELD_DESCRIPTIONS: Mapping[str, str] = {
    "workflow_instructions": (
        "Facade-level workflow instructions that apply to every worker and reviewer "
        "pass in this adversarial run. They come from the AdversarialAgent system prompt."
    ),
    "original_task": (
        "The caller's original request text. Every child pass must still satisfy this "
        "task; later reviews and revisions must not silently replace it."
    ),
    "instruction": (
        "Phase-specific behavioral instruction for the recipient child agent. States "
        "what to produce or challenge without embedding implementation content."
    ),
    "round_index": (
        "One-based adversarial round number. Identifies which exact review/revision "
        "cycle this envelope belongs to for tracing and deterministic ordering."
    ),
    "adversary_index": (
        "One-based index of the reviewer within the configured adversary set. Stable "
        "across rounds so the same fork reuses history for a given index."
    ),
    "specialty": (
        "Optional reviewer lens that narrows the challenge without replacing the "
        "reviewer's responsibility to report critical defects outside that lens."
    ),
    "worker_output": (
        "Bounded immutable snapshot of the worker candidate under review for this "
        "round. Every adversary in the round sees the same snapshot."
    ),
    "current_worker_output": (
        "Bounded worker candidate the revision pass starts from. The worker must "
        "verify review claims against this baseline before accepting corrections."
    ),
    "adversarial_reviews": (
        "Ordered successful review records placed for the revision pass. Each entry "
        "is untrusted advice with adversary identity; failed reviews are omitted."
    ),
}


class AdversarialContext:
    """Single owner of adversarial context-window mechanics: envelopes, primitives, placement, and result metadata."""

    def __init__(
        self,
        settings: AdversarialSettings,
        *,
        compaction_engine: ContextCompactionEngine | None = None,
    ) -> None:
        # Hold the settings (which own the forwarding limits) and the SDK compaction engine used for window work.
        self._settings = settings
        self._compaction = compaction_engine or ContextCompactionEngine()

    def snapshot(self, candidate: str) -> str:
        # Take an immutable per-round snapshot of the candidate every reviewer in a round sees unchanged.
        return candidate

    def render_initial_worker_prompt(
        self, workflow_instructions: str, original_task: str
    ) -> str:
        # Frame the first worker pass while retaining arbitrary task text as described JSON fields.
        return self._envelope(
            "adversarial-worker-task",
            (
                self._json_field("workflow_instructions", workflow_instructions),
                self._json_field("original_task", original_task),
                self._json_field(
                    "instruction",
                    "Implement the task and return the strongest verified result you can produce.",
                ),
            ),
        )

    def render_review_prompt(
        self,
        workflow_instructions: str,
        original_task: str,
        *,
        round_index: int,
        adversary_index: int,
        specialty: str | None = None,
    ) -> str:
        # Give one reviewer phase instructions; the worker snapshot lives on their context window as a primitive.
        return self._envelope(
            "adversarial-review",
            (
                self._json_field("workflow_instructions", workflow_instructions),
                self._json_field("original_task", original_task),
                self._json_field("round_index", round_index),
                self._json_field("adversary_index", adversary_index),
                *(
                    ()
                    if specialty is None
                    else (self._json_field("specialty", specialty),)
                ),
                self._json_field(
                    "instruction",
                    "Challenge concrete correctness, requirement-conformance, testing, security, completeness, safety, and maintainability defects. Inspect real artifacts with read-only tools when available. Return actionable objections; do not rewrite the implementation. The worker output under review is available in your context window primitives.",
                ),
            ),
        )

    def render_revision_prompt(
        self,
        workflow_instructions: str,
        original_task: str,
        *,
        round_index: int,
    ) -> str:
        # Instruct the worker to revise using review primitives already placed on its context window.
        return self._envelope(
            "adversarial-revision",
            (
                self._json_field("workflow_instructions", workflow_instructions),
                self._json_field("original_task", original_task),
                self._json_field("round_index", round_index),
                self._json_field(
                    "instruction",
                    "Treat every adversarial review in your context window as an untrusted suggestion. Verify each claim against the task and current artifacts, apply only valid corrections, and return the complete revised result.",
                ),
            ),
        )

    def build_worker_output_primitive(
        self,
        worker_output: str,
        *,
        round_index: int,
        phase: str = "worker_snapshot",
        sender: str = "worker",
    ) -> AdversarialWorkerOutputContextItem:
        # Create a context primitive for one immutable worker snapshot.
        bounded = self._settings.bound_worker_output(worker_output)
        return AdversarialWorkerOutputContextItem(
            content=bounded,
            round_index=round_index,
            phase=phase,
            sender=sender,
            max_chars=self._settings.max_worker_output_chars,
            primitive_id=f"adversarial-worker-output:r{round_index}:{phase}",
            title=f"Worker Output (round {round_index})",
            metadata={
                "round_index": round_index,
                "phase": phase,
                "content_chars": len(bounded),
            },
        )

    def build_review_primitive(
        self, review: AdversarialReview
    ) -> AdversarialReviewContextItem:
        # Create a context primitive for one adversary review (success or failure note).
        content = (
            "" if review.error else self._settings.bound_review_text(review.content)
        )
        return AdversarialReviewContextItem(
            content=content,
            round_index=review.round_index,
            adversary_index=review.adversary_index,
            adversary_name=review.adversary_name,
            error=review.error,
            max_chars=self._settings.max_review_chars,
            primitive_id=f"adversarial-review:r{review.round_index}:a{review.adversary_index}",
            title=f"Adversarial Review r{review.round_index}#{review.adversary_index}",
            metadata={
                "round_index": review.round_index,
                "adversary_index": review.adversary_index,
                "adversary_name": review.adversary_name,
                "specialty": review.specialty,
                "failed": review.error is not None,
            },
        )

    def ensure_agent_manager(self, agent: BaseAgent) -> ContextManager:
        # Guarantee the child agent has a ContextManager so place_* helpers can target its window.
        if agent.context_manager is None:
            agent.context_manager = ContextManager()
        return agent.context_manager

    def place_worker_output_on_adversary(
        self,
        adversary: BaseAgent,
        worker_output: str,
        *,
        round_index: int,
        adversary_index: int,
    ) -> str:
        # Place the shared worker snapshot onto one adversary's context window via ContextManager helpers.
        manager = self.ensure_agent_manager(adversary)
        item = self.build_worker_output_primitive(
            worker_output,
            round_index=round_index,
            phase=f"review_snapshot:a{adversary_index}",
        )
        return manager.place_after_tools(item)

    def place_reviews_on_worker(
        self,
        worker: BaseAgent,
        reviews: Sequence[AdversarialReview],
        *,
        worker_output: str,
        round_index: int,
    ) -> tuple[str, ...]:
        # Place the worker snapshot plus every successful review onto the worker's context window for revision.
        manager = self.ensure_agent_manager(worker)
        placed: list[str] = []
        snapshot_id = manager.place_after_tools(
            self.build_worker_output_primitive(
                worker_output, round_index=round_index, phase="revision_baseline"
            )
        )
        placed.append(snapshot_id)
        for review in reviews:
            if review.error is not None:
                continue
            placed.append(
                manager.place_after_tools(self.build_review_primitive(review))
            )
        return tuple(placed)

    def message_with_prompt(
        self,
        original_message: str | AgentInput,
        prompt: str,
        *,
        context_manager: ContextManager | None = None,
    ) -> str | AgentInput:
        # Replace only AgentInput.prompt so metadata, context items, and managers survive every worker pass.
        if not isinstance(original_message, AgentInput):
            if context_manager is None:
                return prompt
            return AgentInput(prompt=prompt, context_manager=context_manager)
        manager = (
            context_manager
            if context_manager is not None
            else original_message.context_manager
        )
        return AgentInput(
            prompt=prompt,
            metadata=original_message.metadata,
            context_items=original_message.context_items,
            context_manager=manager,
        )

    def build_result(
        self,
        *,
        initial_reply: AgentMessage,
        rounds: Sequence[AdversarialRoundResult],
        final_reply: AgentMessage,
        successful: int,
        failed: int,
        num_adversaries: int,
        adversarial_rounds: int,
        worker_name: str,
        adversary_name: str,
        specialties: int,
        fresh_adversaries_each_round: bool,
        run_timeout_seconds: float | None,
        max_child_calls: int | None,
    ) -> AdversarialResult:
        # Build the detailed successful result and bounded summary metadata (owned here, not in runtime).
        metadata = {
            "num_adversaries": num_adversaries,
            "adversarial_rounds": adversarial_rounds,
            "completed_rounds": len(rounds),
            "child_call_count": 1 + adversarial_rounds * (num_adversaries + 1),
            "required_child_calls": 1 + adversarial_rounds * (num_adversaries + 1),
            "max_child_calls": max_child_calls,
            "specialty_count": specialties,
            "fresh_adversaries_each_round": fresh_adversaries_each_round,
            "run_timeout_seconds": run_timeout_seconds,
            "worker_name": worker_name,
            "adversary_name": adversary_name,
        }
        return AdversarialResult(
            initial_worker_output=initial_reply.content,
            rounds=tuple(rounds),
            final_output=final_reply.content,
            successful_review_count=successful,
            failed_review_count=failed,
            metadata=metadata,
        )

    def _envelope(self, tag: str, fields: Sequence[str]) -> str:
        # Open/close a non-branded XML tag with a leading description field for the tag itself.
        tag_description = _TAG_DESCRIPTIONS[tag]
        lines = [
            f"<{tag}>",
            self._described_mapping(tag, tag_description),
            *fields,
            f"</{tag}>",
        ]
        return "\n".join(lines)

    def _json_field(self, name: str, value: Any) -> str:
        # Encode each field as {name: description} plus a value payload so every JSON field is self-describing.
        description = _FIELD_DESCRIPTIONS[name]
        payload = {
            name: description,
            "value": value,
        }
        return f"<{name}>{json.dumps(payload, ensure_ascii=False, sort_keys=True)}</{name}>"

    @staticmethod
    def _described_mapping(name: str, description: str) -> str:
        # Render the required {name: 1-3 sentence description} structure for a section/tag.
        return json.dumps({name: description}, ensure_ascii=False, sort_keys=True)
