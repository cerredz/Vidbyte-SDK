"""Context Protocol Header

Description:
    Enumerates the fixed vocabularies used by the public YAML configuration loader.
Purpose:
    Replaces bare string/frozenset constants in vidbyte.config with typed enums so the
    supported document kinds and agent-loop fields have one authoritative definition.
Architecture:
    - ConfigKind: The document kinds the loader can parse and dispatch on.
    - AgentLoopField: The loop keys an agent document may set, mirroring AgentLoopSettings.
Relations:
    Consumed by vidbyte.config.loader and vidbyte.lib.dataclasses.config.
Similar Files:
    - vidbyte/lib/enums/agent_runtime.py: Runtime enum used by the same agent settings.
"""

from __future__ import annotations

from enum import Enum


class ConfigKind(str, Enum):
    """Supported ``kind`` values for a versioned configuration document."""

    AGENT = "agent"
    HARNESS = "harness"
    TOOLS = "tools"
    MIDDLEWARE = "middleware"


class AgentLoopField(str, Enum):
    """Loop keys accepted under ``agent.loop``, one-to-one with AgentLoopSettings kwargs.

    Kept in lockstep with :class:`vidbyte.agents.settings.AgentLoopSettings` so a document
    that names a field the loop object cannot accept is rejected with a precise field error
    instead of a raw ``TypeError`` raised deep inside settings construction.
    """

    MAX_ITERATIONS = "max_iterations"
    MAX_TOKENS = "max_tokens"
    MAX_TOOL_CALLS = "max_tool_calls"
    MAX_PARALLEL_TOOL_CALLS = "max_parallel_tool_calls"
    MAX_RETRIES = "max_retries"
    TIMEOUT_SECONDS = "timeout_seconds"
    CONTEXT_WINDOW_BUDGET = "context_window_budget"
    COMPACTION_TRIGGER_TOKENS = "compaction_trigger_tokens"
    COMPACTION_TARGET_TOKENS = "compaction_target_tokens"
    ALLOWED_TOOLS = "allowed_tools"

    @classmethod
    def names(cls) -> frozenset[str]:
        # Returns the accepted loop-field names for allowlist validation.
        return frozenset(member.value for member in cls)


__all__ = ["AgentLoopField", "ConfigKind"]
