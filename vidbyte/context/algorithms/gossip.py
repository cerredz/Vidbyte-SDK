"""Context Protocol Header

Description:
    Implements the public Gossip/Epidemic Knowledge Propagation algorithm configuration.
Purpose:
    Defines the frozen, type-safe settings for running N agents with partial
    knowledge through random pairwise gossip rounds until convergence, then
    synthesizing a final answer from all converged knowledge stores.
Architecture:
    - GossipAlgorithm: Immutable public configuration class.
Relations:
    Used by ContextWindowPresets and AgentRuntimeContextAlgorithms to configure
    the runtime adapter.
Similar Files:
    - vidbyte/context/algorithms/beam_search.py: Similar multi-trial runtime pattern.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import ConfigurationError

_MAX_AGENTS_LIMIT = 20
_MAX_KNOWLEDGE_CHARS_LIMIT = 1_000_000
_MAX_ROUNDS_LIMIT = 20

_DEFAULT_ANGLES = (
    "Approach from first principles and foundational concepts.",
    "Focus on edge cases, failure modes, and what could go wrong.",
    "Consider alternative approaches and trade-offs.",
    "Ground the analysis in concrete examples and evidence.",
    "Examine constraints, requirements, and non-negotiable boundaries.",
    "Synthesize implications and downstream consequences.",
    "Evaluate from a critical, adversarial perspective.",
    "Focus on practical implementation and execution details.",
)

_DEFAULT_AGENT_SYSTEM_PROMPT = (
    "You are a knowledge extraction agent. Given a task and a specific analytical angle, "
    "produce a dense, structured knowledge summary that captures the most important insights "
    "from your assigned perspective. Be specific, concrete, and concise."
)

_DEFAULT_MERGE_SYSTEM_PROMPT = (
    "You are a knowledge integration specialist. You will receive two knowledge summaries "
    "on the same topic. Merge them into a single, unified knowledge store that preserves "
    "all unique insights from both sources, resolves contradictions, and eliminates redundancy. "
    "Be concise but complete."
)

_DEFAULT_SYNTHESIZER_SYSTEM_PROMPT = (
    "You are a synthesis expert. Using the converged knowledge stores from multiple analytical "
    "agents, produce a single comprehensive, coherent answer to the original task. "
    "Integrate all perspectives into a unified, high-quality response."
)


@dataclass(frozen=True, slots=True)
class GossipAlgorithm:
    """Public immutable config for the Gossip/Epidemic runtime algorithm."""

    num_agents: int = 4
    gossip_rounds: int = 3
    max_knowledge_chars: int = 2000
    agent_system_prompt: str | None = None
    merge_system_prompt: str | None = None
    synthesizer_system_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates all configuration fields at construction time.
        _validate_num_agents(self.num_agents)
        _validate_gossip_rounds(self.gossip_rounds)
        _validate_knowledge_chars(self.max_knowledge_chars)
        _validate_prompt_override(self.agent_system_prompt, "agent_system_prompt")
        _validate_prompt_override(self.merge_system_prompt, "merge_system_prompt")
        _validate_prompt_override(self.synthesizer_system_prompt, "synthesizer_system_prompt")
        _validate_metadata_keys(self.metadata)

    def agent_system_prompt_text(self) -> str:
        """Return the system prompt for individual agent initialization."""
        return self.agent_system_prompt or _DEFAULT_AGENT_SYSTEM_PROMPT

    def merge_system_prompt_text(self) -> str:
        """Return the system prompt for pairwise knowledge merge calls."""
        return self.merge_system_prompt or _DEFAULT_MERGE_SYSTEM_PROMPT

    def synthesizer_system_prompt_text(self) -> str:
        """Return the system prompt for the final synthesis call."""
        return self.synthesizer_system_prompt or _DEFAULT_SYNTHESIZER_SYSTEM_PROMPT

    def build_angle_for_agent(self, agent_index: int, task: str) -> str:
        """Return the analytical angle prefix for the agent at the given index."""
        angle = _DEFAULT_ANGLES[agent_index % len(_DEFAULT_ANGLES)]
        return f"Task:\n{task}\n\nYour analytical angle: {angle}"

    def render_merge_prompt(self, knowledge_a: str, knowledge_b: str) -> str:
        """Format a merge prompt containing both knowledge stores."""
        return (
            f"Knowledge store A:\n{knowledge_a}\n\n"
            f"Knowledge store B:\n{knowledge_b}\n\n"
            "Merged knowledge store:"
        )

    def render_synthesis_prompt(self, task: str, knowledge_stores: list[str]) -> str:
        """Format a synthesis prompt from all converged knowledge stores."""
        formatted = "\n\n---\n\n".join(
            f"Agent {i + 1} knowledge:\n{store}" for i, store in enumerate(knowledge_stores)
        )
        return f"Original task:\n{task}\n\nConverged knowledge from all agents:\n\n{formatted}\n\nFinal answer:"

    def truncate_knowledge(self, output: str) -> str:
        """Trim knowledge store text to max_knowledge_chars with a suffix."""
        if len(output) <= self.max_knowledge_chars:
            return output
        return output[: self.max_knowledge_chars].rstrip() + "\n...[knowledge truncated]"


def _validate_num_agents(num_agents: int) -> None:
    # Raises ConfigurationError if num_agents is less than two or exceeds limit.
    if num_agents < 2:
        raise ConfigurationError("num_agents must be at least 2 for gossip exchange.")
    if num_agents > _MAX_AGENTS_LIMIT:
        raise ConfigurationError(f"num_agents ({num_agents}) exceeds the safeguard limit of {_MAX_AGENTS_LIMIT}.")


def _validate_gossip_rounds(gossip_rounds: int) -> None:
    # Raises ConfigurationError if gossip_rounds is less than one or exceeds limit.
    if gossip_rounds < 1:
        raise ConfigurationError("gossip_rounds must be at least 1.")
    if gossip_rounds > _MAX_ROUNDS_LIMIT:
        raise ConfigurationError(f"gossip_rounds ({gossip_rounds}) exceeds the safeguard limit of {_MAX_ROUNDS_LIMIT}.")


def _validate_knowledge_chars(max_knowledge_chars: int) -> None:
    # Raises ConfigurationError if max_knowledge_chars is not positive or exceeds limit.
    if max_knowledge_chars <= 0:
        raise ConfigurationError("max_knowledge_chars must be greater than zero.")
    if max_knowledge_chars > _MAX_KNOWLEDGE_CHARS_LIMIT:
        raise ConfigurationError(
            f"max_knowledge_chars ({max_knowledge_chars}) exceeds the safeguard limit of {_MAX_KNOWLEDGE_CHARS_LIMIT}."
        )


def _validate_prompt_override(value: str | None, field_name: str) -> None:
    # Raises ConfigurationError if an optional prompt override is provided but empty.
    if value is not None and not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string when provided.")


def _validate_metadata_keys(metadata: Mapping[str, Any]) -> None:
    # Raises ConfigurationError if any metadata key is not a string.
    for key in metadata:
        if not isinstance(key, str):
            raise ConfigurationError(f"metadata keys must be strings, found: {type(key).__name__}.")


__all__ = [
    "GossipAlgorithm",
]
