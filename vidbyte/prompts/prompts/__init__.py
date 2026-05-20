from __future__ import annotations

from vidbyte.prompts.prompts.agent_roles import AgentRolePrompt
from vidbyte.prompts.prompts.vmao import VMAOPrompts
from vidbyte.prompts.registry import prompt_registry

for prompt in (
    AgentRolePrompt("worker", "You are a focused worker agent. Complete the assigned task clearly and report uncertainty."),
    AgentRolePrompt("service", "You are a service agent. Coordinate supporting operations and return concise status."),
    AgentRolePrompt("support", "You are a support agent. Fill gaps, clarify context, and preserve useful details."),
    AgentRolePrompt("evaluator", "You are an evaluator agent. Judge outputs against the task and explain the selected result."),
    VMAOPrompts("planner"),
    VMAOPrompts("planner_repair"),
    VMAOPrompts("synthesizer"),
    VMAOPrompts("verifier"),
    VMAOPrompts("gap_planner"),
):
    prompt_registry.register(prompt)

__all__ = [
    "AgentRolePrompt",
    "VMAOPrompts",
]
