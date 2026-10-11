"""FILE: vidbyte/lib/agents/protocol.py

PURPOSE: Declares the call contract every Vidbyte agent kind satisfies.
ROLE IN CODEBASE: PipelineNode is typed as this, so BasePipeline._invoke's dispatch is
    checked rather than duck-typed against a method name that may not exist.
ARCHITECTURE NOTE: Lives in vidbyte.lib so vidbyte/pipelines/types.py can name the
    contract without depending on either agent implementation. BaseAgent satisfies it
    structurally with no change; CodexHarnessAgent satisfies it once it grows
    generate_reply.
FUNCTION INVENTORY: VidbyteAgent declares name, generate_reply, and arun — exactly what
    the pipeline and workflow call sites invoke, and nothing more.
COMMON MODIFICATION PATTERNS: Add a member only when a shared call site needs it; a
    protocol listing everything BaseAgent offers would exclude other agent kinds for
    methods no caller uses.
WHAT NOT TO DO IN THIS FILE: Do not narrow the parameter types to one agent kind's input
    union, and do not treat runtime_checkable as a behavioral guarantee — it verifies that
    the methods exist, not that they mean the same thing.
KNOWN EDGE CASES: An object with the right methods and wrong semantics satisfies this
    check; the protocol replaces an AttributeError at call time with a type error earlier.
RELATED DOCS: docs/design/codex-pipelines.md
TESTS: tests/test_codex_pipelines.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VidbyteAgent(Protocol):
    """The call contract every Vidbyte agent kind satisfies."""

    @property
    def name(self) -> str:
        """Return the agent's stable display name."""
        ...

    async def generate_reply(self, message: Any, **options: Any) -> Any:
        """Produce one reply for a caller that dispatches by this name."""
        ...

    async def arun(self, message: Any, **options: Any) -> Any:
        """Produce one reply through the agent's own primary entry point."""
        ...


__all__ = ["VidbyteAgent"]
