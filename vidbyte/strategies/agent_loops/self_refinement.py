from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.lib.runners import TextModelRunner, TextModelResponse
from vidbyte.strategies.base import BaseStrategy, require_positive
from vidbyte.strategies.types import StrategyResult


DEFAULT_FEEDBACK_SYSTEM_PROMPT = (
    "Review the current draft. Provide specific, actionable feedback for improving it. "
    "If no changes are needed, say 'no changes needed'."
)

DEFAULT_STOP_PHRASES = (
    "no changes needed",
    "no further changes",
    "already sufficient",
    "nothing to improve",
)


@dataclass(frozen=True, slots=True)
class SelfRefinementStep:
    """One feedback/refinement step in a Self-Refine loop."""

    iteration: int
    draft: str
    feedback: str
    refined: str | None
    stopped: bool = False


class SelfRefinementStrategy(BaseStrategy):
    """Iteratively generate feedback and refine a draft."""

    name: ClassVar[str] = "self_refinement"

    def __init__(
        self,
        *,
        create_system_prompt: str,
        refine_system_prompt: str,
        iterations: int,
        feedback_system_prompt: str | None = None,
        stop_phrases: tuple[str, ...] | None = None,
        stop_on_no_feedback: bool = True,
    ) -> None:
        require_positive(iterations, field_name="iterations")
        self.create_system_prompt = _require_non_empty(
            create_system_prompt,
            field_name="create_system_prompt",
        )
        self.refine_system_prompt = _require_non_empty(
            refine_system_prompt,
            field_name="refine_system_prompt",
        )
        self.feedback_system_prompt = (
            _require_non_empty(feedback_system_prompt, field_name="feedback_system_prompt")
            if feedback_system_prompt is not None
            else DEFAULT_FEEDBACK_SYSTEM_PROMPT
        )
        self.iterations = iterations
        self.stop_phrases = stop_phrases or DEFAULT_STOP_PHRASES
        self.stop_on_no_feedback = stop_on_no_feedback

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        create_response = runner.run(prompt, system=self.create_system_prompt)
        current_draft = _require_non_empty(create_response.text, field_name="initial_draft")
        initial_draft = current_draft
        calls: list[TextModelResponse] = [create_response]
        steps: list[SelfRefinementStep] = []

        for iteration in range(1, self.iterations + 1):
            feedback_response = runner.run(
                _feedback_prompt(original_task=prompt, current_draft=current_draft),
                system=self.feedback_system_prompt,
            )
            feedback = _require_non_empty(feedback_response.text, field_name="feedback")
            calls.append(feedback_response)

            if self.stop_on_no_feedback and _should_stop(feedback, stop_phrases=self.stop_phrases):
                steps.append(
                    SelfRefinementStep(
                        iteration=iteration,
                        draft=current_draft,
                        feedback=feedback,
                        refined=None,
                        stopped=True,
                    )
                )
                break

            refine_response = runner.run(
                _refinement_prompt(
                    original_task=prompt,
                    initial_draft=initial_draft,
                    current_draft=current_draft,
                    latest_feedback=feedback,
                    prior_steps=tuple(steps),
                ),
                system=self.refine_system_prompt,
            )
            refined = _require_non_empty(refine_response.text, field_name="refined_output")
            calls.append(refine_response)

            steps.append(
                SelfRefinementStep(
                    iteration=iteration,
                    draft=current_draft,
                    feedback=feedback,
                    refined=refined,
                )
            )
            current_draft = refined

        return StrategyResult(
            output=current_draft,
            strategy_name=self.name,
            calls=tuple(calls),
            metadata={
                "iterations_requested": self.iterations,
                "iterations_completed": len(steps),
                "stopped_early": bool(steps and steps[-1].stopped),
                "steps": tuple(_step_metadata(step) for step in steps),
            },
        )


def _require_non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise StrategyExecutionError(f"{field_name} must be non-empty.")
    return normalized


def _feedback_prompt(*, original_task: str, current_draft: str) -> str:
    return "\n".join(
        [
            "Give feedback on the current draft for the original task.",
            "Feedback must be concrete and actionable.",
            "",
            "Original task:",
            original_task,
            "",
            "Current draft:",
            current_draft,
        ]
    )


def _refinement_prompt(
    *,
    original_task: str,
    initial_draft: str,
    current_draft: str,
    latest_feedback: str,
    prior_steps: tuple[SelfRefinementStep, ...],
) -> str:
    parts = [
        "Refine the current draft using the latest feedback.",
        "Return the full revised answer, not a patch or commentary about the changes.",
        "",
        "Original task:",
        original_task,
        "",
        "Initial draft:",
        initial_draft,
    ]
    if prior_steps:
        parts.extend(["", "Prior refinement history:", _format_history(prior_steps)])
    parts.extend(
        [
            "",
            "Current draft:",
            current_draft,
            "",
            "Latest feedback:",
            latest_feedback,
            "",
            "Refined answer:",
        ]
    )
    return "\n".join(parts)


def _format_history(steps: tuple[SelfRefinementStep, ...]) -> str:
    blocks: list[str] = []
    for step in steps:
        if step.stopped:
            blocks.append(
                f"Iteration {step.iteration}: feedback={step.feedback!r}; stopped before refinement."
            )
        else:
            blocks.append(
                f"Iteration {step.iteration}: feedback={step.feedback!r}; refined={step.refined!r}"
            )
    return "\n".join(blocks)


def _should_stop(feedback: str, *, stop_phrases: tuple[str, ...]) -> bool:
    lowered = feedback.lower()
    return any(phrase.lower() in lowered for phrase in stop_phrases)


def _step_metadata(step: SelfRefinementStep) -> dict[str, object]:
    return {
        "iteration": step.iteration,
        "draft": step.draft,
        "feedback": step.feedback,
        "refined": step.refined,
        "stopped": step.stopped,
    }
