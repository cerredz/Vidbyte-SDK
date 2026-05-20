from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.lib.runners import TextModelRunner, TextModelResponse
from vidbyte.prompts.strategies import (
    SelfRefinementCreatePrompt,
    SelfRefinementFeedbackPrompt,
    SelfRefinementRefinePrompt,
)
from vidbyte.strategies.base import BaseStrategy, BaseStrategyUtils
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
    prompts: ClassVar[dict[str, type[object]]] = {
        "create_prompt": SelfRefinementCreatePrompt,
        "feedback_prompt": SelfRefinementFeedbackPrompt,
        "refine_prompt": SelfRefinementRefinePrompt,
    }

    def __init__(self, *, create_system_prompt: str, refine_system_prompt: str, iterations: int, feedback_system_prompt: str | None = None, stop_phrases: tuple[str, ...] | None = None, stop_on_no_feedback: bool = True) -> None:
        """Store prompts and loop controls for the self-refinement strategy."""
        BaseStrategyUtils.require_positive(iterations, field_name="iterations")
        self.create_system_prompt = self._require_non_empty(create_system_prompt, field_name="create_system_prompt")
        self.refine_system_prompt = self._require_non_empty(refine_system_prompt, field_name="refine_system_prompt")
        self.feedback_system_prompt = self._feedback_system_prompt(feedback_system_prompt)
        self.iterations = iterations
        self.stop_phrases = stop_phrases or DEFAULT_STOP_PHRASES
        self.stop_on_no_feedback = stop_on_no_feedback

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        """Run create, feedback, and refinement calls in order."""
        create_response = self.create(prompt, runner=runner)
        current_draft = self._require_non_empty(create_response.text, field_name="initial_draft")
        initial_draft = current_draft
        calls: list[TextModelResponse] = [create_response]
        steps: list[SelfRefinementStep] = []

        for iteration in range(1, self.iterations + 1):
            feedback_response = self.feedback(prompt, current_draft=current_draft, runner=runner)
            feedback = self._require_non_empty(feedback_response.text, field_name="feedback")
            calls.append(feedback_response)

            if self.stop_on_no_feedback and self._should_stop(feedback):
                steps.append(self._stopped_step(iteration, draft=current_draft, feedback=feedback))
                break

            refine_response = self.refine(prompt, initial_draft=initial_draft, current_draft=current_draft, latest_feedback=feedback, prior_steps=tuple(steps), runner=runner)
            refined = self._require_non_empty(refine_response.text, field_name="refined_output")
            calls.append(refine_response)
            steps.append(SelfRefinementStep(iteration=iteration, draft=current_draft, feedback=feedback, refined=refined))
            current_draft = refined

        return self._result(output=current_draft, calls=tuple(calls), steps=tuple(steps))

    def create(self, task: str, *, runner: TextModelRunner) -> TextModelResponse:
        """Create the first draft using the configured create system prompt."""
        return runner.run(SelfRefinementCreatePrompt(task=task).export(), system=self.create_system_prompt)

    def feedback(self, task: str, *, current_draft: str, runner: TextModelRunner) -> TextModelResponse:
        """Generate actionable feedback for the current draft."""
        prompt = SelfRefinementFeedbackPrompt(original_task=task, current_draft=current_draft)
        return runner.run(prompt.export(), system=self.feedback_system_prompt)

    def refine(self, task: str, *, initial_draft: str, current_draft: str, latest_feedback: str, prior_steps: tuple[SelfRefinementStep, ...], runner: TextModelRunner) -> TextModelResponse:
        """Refine the current draft using feedback and previous loop history."""
        prompt = SelfRefinementRefinePrompt(
            original_task=task,
            initial_draft=initial_draft,
            current_draft=current_draft,
            latest_feedback=latest_feedback,
            prior_history=tuple(self._format_step(step) for step in prior_steps),
        )
        return runner.run(prompt.export(), system=self.refine_system_prompt)

    def _result(self, *, output: str, calls: tuple[TextModelResponse, ...], steps: tuple[SelfRefinementStep, ...]) -> StrategyResult:
        """Package the final draft, call history, and loop metadata."""
        return StrategyResult(
            output=output,
            strategy_name=self.name,
            calls=calls,
            metadata={
                "iterations_requested": self.iterations,
                "iterations_completed": len(steps),
                "stopped_early": bool(steps and steps[-1].stopped),
                "steps": tuple(self._step_metadata(step) for step in steps),
            },
        )

    def _feedback_system_prompt(self, feedback_system_prompt: str | None) -> str:
        """Normalize a user-provided feedback system prompt or use the default."""
        if feedback_system_prompt is None:
            return DEFAULT_FEEDBACK_SYSTEM_PROMPT
        return self._require_non_empty(feedback_system_prompt, field_name="feedback_system_prompt")

    def _stopped_step(self, iteration: int, *, draft: str, feedback: str) -> SelfRefinementStep:
        """Create a loop step for an early-stop feedback response."""
        return SelfRefinementStep(iteration=iteration, draft=draft, feedback=feedback, refined=None, stopped=True)

    def _should_stop(self, feedback: str) -> bool:
        """Check feedback text against configured early-stop phrases."""
        lowered = feedback.lower()
        return any(phrase.lower() in lowered for phrase in self.stop_phrases)

    @staticmethod
    def _require_non_empty(value: str, *, field_name: str) -> str:
        """Trim a string setting or model output and reject empty values."""
        normalized = value.strip()
        if not normalized:
            raise StrategyExecutionError(f"{field_name} must be non-empty.")
        return normalized

    @staticmethod
    def _format_step(step: SelfRefinementStep) -> str:
        """Format one prior refinement step for prompt history."""
        if step.stopped:
            return f"Iteration {step.iteration}: feedback={step.feedback!r}; stopped before refinement."
        return f"Iteration {step.iteration}: feedback={step.feedback!r}; refined={step.refined!r}"

    @staticmethod
    def _step_metadata(step: SelfRefinementStep) -> dict[str, object]:
        """Convert one loop step into public result metadata."""
        return {
            "iteration": step.iteration,
            "draft": step.draft,
            "feedback": step.feedback,
            "refined": step.refined,
            "stopped": step.stopped,
        }
