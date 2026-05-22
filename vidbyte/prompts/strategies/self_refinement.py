from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SelfRefinementCreatePrompt:
    task: str

    def export(self) -> str:
        """Return the user task as the initial creation prompt."""
        return self.task


@dataclass(frozen=True, slots=True)
class SelfRefinementFeedbackPrompt:
    original_task: str
    current_draft: str

    def export(self) -> str:
        """Return the feedback prompt with task and current draft context."""
        return "\n".join(
            [
                "Give feedback on the current draft for the original task.",
                "Feedback must be concrete, actionable, and scoped to the task.",
                "",
                "Original task:",
                self.original_task,
                "",
                "Current draft:",
                self.current_draft,
            ]
        )


@dataclass(frozen=True, slots=True)
class SelfRefinementRefinePrompt:
    original_task: str
    initial_draft: str
    current_draft: str
    latest_feedback: str
    prior_history: tuple[str, ...] = ()

    def export(self) -> str:
        """Return the refinement prompt with initial draft, history, and feedback."""
        parts = [
            "Refine the current draft using the latest feedback.",
            "Return the full revised answer, not a patch or commentary about the changes.",
            "",
            "Original task:",
            self.original_task,
            "",
            "Initial draft:",
            self.initial_draft,
        ]
        if self.prior_history:
            parts.extend(["", "Prior refinement history:", "\n".join(self.prior_history)])
        parts.extend(
            [
                "",
                "Current draft:",
                self.current_draft,
                "",
                "Latest feedback:",
                self.latest_feedback,
                "",
                "Refined answer:",
            ]
        )
        return "\n".join(parts)
