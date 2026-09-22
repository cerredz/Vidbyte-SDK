"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent.
ROLE IN CODEBASE: JevAgent selects JevRuntime while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: The initial runtime deliberately inherits the linear loop unchanged; later named Jev capabilities are implemented here behind validated settings.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: Merely constructing or running this scaffold performs no Jev decision call and therefore needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-agent-scaffold.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.runtime import AgentRuntime
from vidbyte.agents.jev.settings import JevAgentSettings


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for opinionated Jev capabilities."""

    def __init__(self, *, jev_settings: JevAgentSettings, **kwargs: Any) -> None:
        # Retains the validated settings by identity and delegates all current behavior to AgentRuntime.
        self.jev_settings = jev_settings
        super().__init__(**kwargs)


__all__ = ["JevRuntime"]
