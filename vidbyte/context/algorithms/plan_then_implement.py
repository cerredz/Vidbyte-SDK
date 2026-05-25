"""Context Protocol Header

Description:
    Builds planner prompts, bounds plan text, and creates plan artifacts for the
    runtime to attach before normal direct agent execution.
Purpose:
    Gives agents a pre-run planning phase that creates a persistent ContextArtifact
    visible to all subsequent model calls through existing BaseContext.build_context().
Architecture:
    - build_plan_prompt(): Renders the planner prompt for the runner.
    - plan_artifact_from_text(): Creates a ContextArtifact from bounded plan text.
    - fallback_plan(): Deterministic fallback when the planner returns empty output.
Relations:
    Used by AgentRuntime._prepare_algorithm_context().
    Depends on vidbyte.context.algorithms.types and vidbyte.lib.dataclasses.context.
"""

from __future__ import annotations

from vidbyte.context.algorithms.types import PlanThenImplementConfig
from vidbyte.lib.dataclasses.context import ContextArtifact

DEFAULT_PLAN_PROMPT = (
    "Create a concise implementation plan for the user's request. "
    "Return only the plan. Include objective, steps, risks, and verification."
)


def build_plan_prompt(
    request: str,
    context_text: str,
    config: PlanThenImplementConfig,
) -> str:
    """Render the planner prompt combining the request, context, and custom prompt."""
    prompt = config.planner_prompt or DEFAULT_PLAN_PROMPT
    parts: list[str] = [
        prompt,
        "",
        f"Request: {request}",
    ]
    if context_text:
        parts.append(f"Context: {context_text}")
    return "\n".join(parts)


def plan_artifact_from_text(
    plan_text: str,
    request: str,
    config: PlanThenImplementConfig,
    *,
    fallback_used: bool = False,
) -> ContextArtifact:
    """Create a bounded ContextArtifact from plan text."""
    bounded_text = plan_text
    if config.max_plan_chars > 0 and len(plan_text) > config.max_plan_chars:
        bounded_text = plan_text[:config.max_plan_chars].rstrip() + "\n...[plan text bounded]"
    return ContextArtifact(
        name=config.artifact_name,
        content=bounded_text,
        artifact_type="plan",
        metadata={
            "plan_request": request,
            "plan_fallback_used": fallback_used,
            "plan_raw_chars": len(plan_text),
            **dict(config.metadata),
        },
    )


def fallback_plan(request: str) -> str:
    """Return a deterministic fallback plan when the planner produces empty output."""
    return (
        f"Objective: Complete the user's request: {request}\n"
        "Steps:\n"
        "  1. Understand the request scope and constraints.\n"
        "  2. Execute the work using available tools.\n"
        "  3. Verify the result against the original request.\n"
        "Risks: Incomplete understanding of the request.\n"
        "Verification: Confirm the output matches the request intent."
    )


__all__ = [
    "DEFAULT_PLAN_PROMPT",
    "build_plan_prompt",
    "fallback_plan",
    "plan_artifact_from_text",
]
