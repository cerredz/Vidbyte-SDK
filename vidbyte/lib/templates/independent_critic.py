"""Context Protocol Header

Description:
    Defines the canonical Independent Critic recorder-slot template.
Purpose:
    Lets harnesses verify the producer/reviewer stage order and the optional
    failure marker without inspecting model content.
Architecture:
    - IndependentCriticContextWindowTemplate: Builds the fixed success or failure sequence.
Relations:
    Validates recorder output from IndependentCriticRuntimeAlgorithm and is
    exported by vidbyte.lib.templates.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class IndependentCriticContextWindowTemplate(ContextWindowTemplate):
    """Template for the structural slots of one independent critic run."""

    def __init__(self, *, review_fails: bool = False) -> None:
        # Build the immutable stage sequence, adding failure only after review starts.
        slots = ["system_prompt", "independent_critic_candidate", "independent_critic_review"]
        if review_fails:
            slots.append("independent_critic_failure")
        super().__init__(slots)


__all__ = [
    "IndependentCriticContextWindowTemplate",
]
