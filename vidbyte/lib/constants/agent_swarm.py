"""FILE: vidbyte/lib/constants/agent_swarm.py

PURPOSE: Defines every named bound, default, pattern, and tool name of AgentSwarm: how many agents a swarm holds and what they may be named, the default turn budget and time limit, the per-agent history and tool-result caps, and the message tool's names.
ROLE IN CODEBASE: Read by AgentSwarmSettings and every module in vidbyte/agents/agent_swarm/, and by the records in vidbyte/lib/dataclasses/agent_swarm.py. The feature tests import them to check settings and output against them.
ARCHITECTURE NOTE: Immutable constants only; behavior lives in vidbyte/agents/agent_swarm/. The limits are enforced in code and never stated in a prompt. The context caps are sized for a 128,000-token model: the member's own prompt, the swarm prompt, the tool schemas, and the history trimmed to 90,000 tokens fit with room left for the reply, and one tool result is cut at 100,000 characters, about 25,000 tokens, under a third of the history. The name pattern is a raw string compiled where it is used.
FUNCTION INVENTORY: No functions; agent-count bounds (AGENT_SWARM_MIN_AGENTS, AGENT_SWARM_MAX_AGENTS), the name pattern, the turn and time defaults and the time ceiling, the history and tool-result caps, the message tool's name and argument names, and the reserved tool names.
COMMON MODIFICATION PATTERNS: Change a bound or default here, never at its use site, so the settings, the runtime, the tests, and the package README stay in step. Add a named constant here before writing another AgentSwarm policy literal.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from any layer above vidbyte/lib. 2. Do not put model-facing sentences here; they belong in vidbyte/prompts/prompts/agent_swarm/. 3. Do not rename the message tool or its arguments without the prompt leaves that describe them.
KNOWN EDGE CASES: Every token figure is the SDK's characters-divided-by-four estimate, not a real tokenizer count. The reserved names are the five file and shell tools plus message. The loop's own isDone is not among them, because this layer may not import it from vidbyte.tools; AgentSwarmSettings refuses that name itself, since the loop would otherwise replace a search tool named isDone with its own.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 8.5 and 9.3); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_contract.py and the rest of tests/features/agent_swarm/
"""

from __future__ import annotations

# The fewest and the most agents one swarm may hold. A swarm of one
# would have nobody to message.
AGENT_SWARM_MIN_AGENTS = 2
AGENT_SWARM_MAX_AGENTS = 100

# An agent's name: a letter or digit, then letters, digits, "_" or "-",
# at most 64 characters. It is the agent's name, its recipient name in
# the message tool, and its name in every event.
AGENT_SWARM_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"

# The swarm-wide turn budget (every first turn plus every wake) and the
# hard time limit in seconds: one hour by default, one week at most.
AGENT_SWARM_DEFAULT_MAX_TURNS = 500
AGENT_SWARM_DEFAULT_TIMEOUT_SECONDS = 3600.0
AGENT_SWARM_MAX_TIMEOUT_SECONDS = 604800.0

# Every agent's history is trimmed to this many tokens before a model
# call, and every tool result the model sees is cut at this many
# characters, so a long-lived conversation fits a 128,000-token model.
AGENT_SWARM_HISTORY_MAX_TOKENS = 90_000
AGENT_SWARM_TOOL_RESULT_MAX_CHARS = 100_000

# The model-facing names of the run-bound message tool and its two
# arguments.
AGENT_SWARM_MESSAGE_TOOL_NAME = "message"
AGENT_SWARM_MESSAGE_TO_ARGUMENT = "to"
AGENT_SWARM_MESSAGE_TEXT_ARGUMENT = "text"

# The names every agent's own tools take, so a developer's search tool
# may take none of them.
AGENT_SWARM_RESERVED_TOOL_NAMES = ("bash", "grep", "read_lines", "write_text", "patch_file", AGENT_SWARM_MESSAGE_TOOL_NAME)

__all__ = [
    "AGENT_SWARM_DEFAULT_MAX_TURNS",
    "AGENT_SWARM_DEFAULT_TIMEOUT_SECONDS",
    "AGENT_SWARM_HISTORY_MAX_TOKENS",
    "AGENT_SWARM_MAX_AGENTS",
    "AGENT_SWARM_MAX_TIMEOUT_SECONDS",
    "AGENT_SWARM_MESSAGE_TEXT_ARGUMENT",
    "AGENT_SWARM_MESSAGE_TOOL_NAME",
    "AGENT_SWARM_MESSAGE_TO_ARGUMENT",
    "AGENT_SWARM_MIN_AGENTS",
    "AGENT_SWARM_NAME_PATTERN",
    "AGENT_SWARM_RESERVED_TOOL_NAMES",
    "AGENT_SWARM_TOOL_RESULT_MAX_CHARS",
]
