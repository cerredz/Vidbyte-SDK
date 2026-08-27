"""Context Protocol Header

Description:
    Validates the verifier_runtime field accepted by AgentLoopSettings.
Purpose:
    Keeps the verifier-runtime type check out of
    vidbyte.agents.settings.loop, matching how ToolErrorPolicy and
    ToolSettings each own their nested-settings validation in their own file
    rather than inline inside AgentLoopSettings.
Architecture note:
    - validate_verifier_runtime(): the one function AgentLoopSettings calls.
Relations:
    Called by vidbyte.agents.settings.loop.AgentLoopSettings. Checks against
    vidbyte.agents.runtimes.verifier.settings.VerifierRuntimeSettings.
Similar Files:
    - vidbyte/agents/settings/tool_error.py: ToolErrorPolicy, the nearest
      existing nested-settings validation surface living in its own file.
Role in codebase:
    Keeps AgentLoopSettings' optional verifier type validation isolated.
Common modification patterns:
    Update the accepted settings wrapper without importing runtime behavior at
    module import time.
Known edge cases:
    None is valid and means verifier runtime is disabled.
Related docs:
    docs/design/verifier-runtime.md
Tests:
    Covered by AgentLoopSettings verifier configuration tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.verifier import VerifierRuntimeSettings


def validate_verifier_runtime(verifier_runtime: "VerifierRuntimeSettings | None") -> None:
    """Raises ConfigurationError unless verifier_runtime is None or a VerifierRuntimeSettings instance."""
    if verifier_runtime is None:
        return
    # Local import avoids a module-level cycle through vidbyte.agents.runtimes' package init.
    from vidbyte.agents.runtimes.verifier import VerifierRuntimeSettings

    if not isinstance(verifier_runtime, VerifierRuntimeSettings):
        raise ConfigurationError("AgentLoopSettings.verifier_runtime must be a VerifierRuntimeSettings instance when provided.")


__all__ = ["validate_verifier_runtime"]
