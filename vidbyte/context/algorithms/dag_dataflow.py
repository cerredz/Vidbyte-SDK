"""Context Protocol Header

Description:
    Implements the public DAG Dataflow algorithm configuration.
Purpose:
    Defines the frozen, type-safe settings for planning a dependency graph of
    tasks, executing nodes in topological order with parallelism, and synthesizing
    a final answer from all node outputs.
Architecture:
    - DAGDataflowAlgorithm: Immutable public configuration class.
Relations:
    Used by ContextWindowPresets and AgentRuntimeContextAlgorithms to configure
    the runtime adapter.
Similar Files:
    - vidbyte/context/algorithms/multi_provider_agentic_grader.py: A similar
      context-window algorithm public configuration with LLM-driven stages.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import AgentExecutionError, ConfigurationError

_MAX_NODES_LIMIT = 50
_MAX_PLAN_CHARS_LIMIT = 1_000_000
_MAX_NODE_OUTPUT_CHARS_LIMIT = 1_000_000

_DEFAULT_PLANNER_SYSTEM_PROMPT = (
    "You are a task decomposition expert. Break the given task into a dependency graph of subtasks. "
    "Respond with a JSON array only — no prose. Each element must be an object with exactly three keys: "
    '"id" (a short unique string like "A" or "step_1"), '
    '"description" (a plain-English description of the subtask), and '
    '"dependencies" (an array of id strings this subtask depends on; empty array if none). '
    "Keep the graph acyclic. Do not include markdown fences."
)

_DEFAULT_NODE_SYSTEM_PROMPT = (
    "You are a focused subtask executor. Solve only the subtask described. "
    "Use the provided inputs from completed prerequisite subtasks to inform your answer. "
    "Be concise and precise."
)

_DEFAULT_SYNTHESIZER_SYSTEM_PROMPT = (
    "You are a synthesis expert. Combine the outputs from all completed subtasks into a single, "
    "coherent, complete answer to the original task."
)


@dataclass(frozen=True, slots=True)
class DAGDataflowAlgorithm:
    """Public immutable config for the DAG Dataflow runtime algorithm."""

    max_nodes: int = 10
    max_parallel: int = 3
    max_plan_chars: int = 4000
    max_node_output_chars: int = 3000
    planner_system_prompt: str | None = None
    node_system_prompt: str | None = None
    synthesizer_system_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates all configuration fields at construction time.
        _validate_positive_int(self.max_nodes, "max_nodes", limit=_MAX_NODES_LIMIT)
        _validate_positive_int(self.max_parallel, "max_parallel")
        _validate_positive_chars(self.max_plan_chars, "max_plan_chars", limit=_MAX_PLAN_CHARS_LIMIT)
        _validate_positive_chars(self.max_node_output_chars, "max_node_output_chars", limit=_MAX_NODE_OUTPUT_CHARS_LIMIT)
        _validate_prompt_override(self.planner_system_prompt, "planner_system_prompt")
        _validate_prompt_override(self.node_system_prompt, "node_system_prompt")
        _validate_prompt_override(self.synthesizer_system_prompt, "synthesizer_system_prompt")
        _validate_metadata_keys(self.metadata)

    def planner_system_prompt_text(self) -> str:
        """Return the system prompt for the DAG planning stage."""
        return self.planner_system_prompt or _DEFAULT_PLANNER_SYSTEM_PROMPT

    def node_system_prompt_text(self) -> str:
        """Return the system prompt for individual node execution."""
        return self.node_system_prompt or _DEFAULT_NODE_SYSTEM_PROMPT

    def synthesizer_system_prompt_text(self) -> str:
        """Return the system prompt for the final synthesis call."""
        return self.synthesizer_system_prompt or _DEFAULT_SYNTHESIZER_SYSTEM_PROMPT

    def parse_dag_plan(self, plan_text: str) -> list[dict[str, Any]]:
        """Parse the JSON DAG from planner output, stripping markdown fences."""
        cleaned = _strip_markdown_fences(plan_text.strip())
        try:
            nodes = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise AgentExecutionError(
                f"DAG planner returned invalid JSON: {exc}",
                details={"raw_output": plan_text[:500]},
            ) from exc
        if not isinstance(nodes, list):
            raise AgentExecutionError(
                "DAG planner output must be a JSON array.",
                details={"raw_output": plan_text[:500]},
            )
        return nodes[: self.max_nodes]

    def truncate_node_output(self, output: str) -> str:
        """Trim node output to max_node_output_chars with a suffix."""
        if len(output) <= self.max_node_output_chars:
            return output
        return output[: self.max_node_output_chars].rstrip() + "\n...[node output truncated]"

    def truncate_plan(self, plan_text: str) -> str:
        """Trim plan text to max_plan_chars with a suffix."""
        if len(plan_text) <= self.max_plan_chars:
            return plan_text
        return plan_text[: self.max_plan_chars].rstrip() + "\n...[plan truncated]"


def _strip_markdown_fences(text: str) -> str:
    # Removes leading/trailing ```json or ``` fences from model output.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _validate_positive_int(value: int, field_name: str, limit: int | None = None) -> None:
    # Raises ConfigurationError if value is not a positive integer within optional limit.
    if value < 1:
        raise ConfigurationError(f"{field_name} must be at least 1.")
    if limit is not None and value > limit:
        raise ConfigurationError(f"{field_name} ({value}) exceeds the safeguard limit of {limit}.")


def _validate_positive_chars(value: int, field_name: str, limit: int | None = None) -> None:
    # Raises ConfigurationError if value is not a positive integer within optional limit.
    if value <= 0:
        raise ConfigurationError(f"{field_name} must be greater than zero.")
    if limit is not None and value > limit:
        raise ConfigurationError(f"{field_name} ({value}) exceeds the safeguard limit of {limit}.")


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
    "DAGDataflowAlgorithm",
]
