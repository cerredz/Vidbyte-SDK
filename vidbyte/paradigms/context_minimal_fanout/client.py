"""Context Protocol Header

Description:
    Defines the namespace client factory for the context-minimal fanout paradigm.
Purpose:
    Lets the paradigm be reached through sdk.paradigms.context_minimal_fanout for
    namespace consistency, while the documented entry point is the direct class.
Architecture:
    - ContextMinimalFanoutClient: Factory that builds ContextMinimalFanoutParadigm.
Relations:
    Attached by vidbyte.paradigms.client.ParadigmClient.
"""

from __future__ import annotations

from typing import Any

from vidbyte.paradigms.context_minimal_fanout.paradigm import (
    ContextMinimalFanoutParadigm,
)


class ContextMinimalFanoutClient:
    """Namespace client for the context-minimal fanout paradigm."""

    def __call__(self, **kwargs: Any) -> ContextMinimalFanoutParadigm:
        # Builds the paradigm harness from keyword settings.
        return ContextMinimalFanoutParadigm(**kwargs)

    def create(self, **kwargs: Any) -> ContextMinimalFanoutParadigm:
        # Explicit alias for callers that prefer a named factory method.
        return ContextMinimalFanoutParadigm(**kwargs)


__all__ = [
    "ContextMinimalFanoutClient",
]
