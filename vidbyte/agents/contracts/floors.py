"""Context Protocol Header

Description:
    The prebuilt deterministic effort-floor output contracts.
Purpose:
    Each floor requires a runtime counter to reach a minimum before the agent may stop.
    A floor is pure declaration: it names the counter (key), the paired ceiling (ceiling_key),
    and a human unit; all comparison and feedback logic lives on OutputContract.
Architecture:
    - MinToolCalls / MinTokens / MinIterations / MinElapsedSeconds: one counter each.
Relations:
    Subclasses of vidbyte.agents.contracts.OutputContract; validated against AgentLoopSettings
    ceilings by vidbyte.agents.contract.AgentOutputContract at construction.
Similar Files:
    - vidbyte/agents/contracts/__init__.py: OutputContract base with satisfied()/error().
"""

from __future__ import annotations

from vidbyte.agents.contracts import OutputContract


class MinToolCalls(OutputContract):
    """Requires at least `minimum` tool calls before the agent may stop."""

    key = "tool_call_count"
    ceiling_key = "max_tool_calls"
    unit = "tool calls"


class MinTokens(OutputContract):
    """Requires at least `minimum` tokens consumed before the agent may stop."""

    key = "tokens_used"
    ceiling_key = "max_tokens"
    unit = "tokens"


class MinIterations(OutputContract):
    """Requires at least `minimum` loop iterations before the agent may stop."""

    key = "iteration_count"
    ceiling_key = "max_iterations"
    unit = "iterations"


class MinElapsedSeconds(OutputContract):
    """Requires at least `minimum` elapsed seconds before the agent may stop."""

    key = "elapsed_seconds"
    ceiling_key = "timeout_seconds"
    unit = "seconds"
