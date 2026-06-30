from __future__ import annotations

from typing import Any

from vidbyte.paradigms.context_minimal_fanout.multiple_prompts import MultiplePromptFanoutHarness


class ContextMinimalFanoutClient:
    """Namespace client for context-minimal fanout paradigm factories."""

    def multiple_prompts(self, **kwargs: Any) -> MultiplePromptFanoutHarness:
        # Builds the first concrete context-minimal fanout harness implementation.
        return MultiplePromptFanoutHarness(**kwargs)


__all__ = [
    "ContextMinimalFanoutClient",
]
