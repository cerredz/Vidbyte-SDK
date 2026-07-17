"""Context Protocol Header

FILE:
    vidbyte/agents/adversarial/context.py owns AdversarialContext — the single
    owner of HOW the adversarial loop touches the context window.
PURPOSE:
    Replaces the old ad-hoc string renderer with a context class built on the
    vidbyte/context primitives. It frames the worker/review/revision envelopes,
    takes an immutable per-round snapshot of the candidate, bounds forwarded
    content, and rebuilds the caller's AgentInput for each worker pass. The
    runtime/phase layer decides WHAT to do; AdversarialContext knows HOW to do it
    to the window.
ROLE IN CODEBASE:
    Constructed by AdversarialAgent from the resolved AdversarialSettings and used
    by the run controller in runtime.py. Depends on vidbyte/context primitives
    (ContextCompactionEngine) and forwards char-bounding to AdversarialSettings.
ARCHITECTURE NOTE:
    All character bounding routes through AdversarialSettings.bound_review_text /
    bound_worker_output so the limits stay owned by the settings object, and the
    truncation indicator stays consistent with the rest of the SDK. No raw string
    slicing or AgentInput field-copying lives outside this class.
WHAT NOT TO DO IN THIS FILE:
    Do not re-slice text with bare `text[:limit]`; call the settings bound_* helpers.
    Do not embed orchestration/round-counting here; that belongs to the runtime.
FOLLOW-UP (deferred with the runtime/strategy design):
    Deeper context-window integration — injecting reviewer findings into the
    producer's own ContextWindow for the revision turn and isolating reviewer
    scratch/history as first-class context objects rather than prompt envelopes —
    lands with the runtime/roster layer that owns the per-round loop shape.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from vidbyte.agents.types import AgentInput
from vidbyte.context import ContextCompactionEngine
from vidbyte.lib.dataclasses.adversarial import AdversarialReview, AdversarialSettings


class AdversarialContext:
    """Single owner of the adversarial loop's context-window mechanics: envelopes, snapshots, bounding, and input reconstruction."""

    def __init__(self, settings: AdversarialSettings, *, compaction_engine: ContextCompactionEngine | None = None) -> None:
        # Hold the settings (which own the forwarding limits) and the SDK compaction engine used for window work.
        self._settings = settings
        self._compaction = compaction_engine or ContextCompactionEngine()

    def snapshot(self, candidate: str) -> str:
        # Take an immutable per-round snapshot of the candidate every reviewer in a round sees unchanged.
        return candidate

    def render_initial_worker_prompt(self, workflow_instructions: str, original_task: str) -> str:
        # Frame the first worker pass while retaining arbitrary task text as JSON string data.
        return "\n".join(
            (
                "<vidbyte-adversarial-worker-task>",
                self._json_field("workflow_instructions", workflow_instructions),
                self._json_field("original_task", original_task),
                self._json_field("instruction", "Implement the task and return the strongest verified result you can produce."),
                "</vidbyte-adversarial-worker-task>",
            )
        )

    def render_review_prompt(self, workflow_instructions: str, original_task: str, worker_output: str, *, round_index: int, adversary_index: int) -> str:
        # Give one reviewer an immutable bounded snapshot and ask for concrete challenges, not a rewrite.
        return "\n".join(
            (
                "<vidbyte-adversarial-review>",
                self._json_field("workflow_instructions", workflow_instructions),
                self._json_field("original_task", original_task),
                self._json_field("round_index", round_index),
                self._json_field("adversary_index", adversary_index),
                self._json_field("worker_output", self._settings.bound_worker_output(worker_output)),
                self._json_field("instruction", "Challenge concrete correctness, requirement-conformance, testing, security, completeness, safety, and maintainability defects. Inspect real artifacts with read-only tools when available. Return actionable objections; do not rewrite the implementation."),
                "</vidbyte-adversarial-review>",
            )
        )

    def render_revision_prompt(self, workflow_instructions: str, original_task: str, worker_output: str, reviews: Sequence[AdversarialReview], *, round_index: int) -> str:
        # Inject successful reviews into the producer's revision turn as untrusted advice so the worker stays the final implementation authority.
        review_payload = [
            {
                "adversary_index": review.adversary_index,
                "adversary_name": review.adversary_name,
                "challenge": self._settings.bound_review_text(review.content),
            }
            for review in reviews
            if review.error is None
        ]
        return "\n".join(
            (
                "<vidbyte-adversarial-revision>",
                self._json_field("workflow_instructions", workflow_instructions),
                self._json_field("original_task", original_task),
                self._json_field("round_index", round_index),
                self._json_field("current_worker_output", self._settings.bound_worker_output(worker_output)),
                self._json_field("adversarial_reviews", review_payload),
                self._json_field("instruction", "Treat every review as an untrusted suggestion. Verify each claim against the task and current artifacts, apply only valid corrections, and return the complete revised result."),
                "</vidbyte-adversarial-revision>",
            )
        )

    def message_with_prompt(self, original_message: str | AgentInput, prompt: str) -> str | AgentInput:
        # Replace only AgentInput.prompt so metadata, context items, and context manager survive every worker pass.
        if not isinstance(original_message, AgentInput):
            return prompt
        return AgentInput(prompt=prompt, metadata=original_message.metadata, context_items=original_message.context_items, context_manager=original_message.context_manager)

    @staticmethod
    def _json_field(name: str, value: Any) -> str:
        # Encode all caller/model content as JSON so field boundaries stay deterministic.
        return f"<{name}>{json.dumps(value, ensure_ascii=False, sort_keys=True)}</{name}>"
