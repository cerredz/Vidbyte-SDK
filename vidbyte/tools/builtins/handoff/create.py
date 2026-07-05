"""Context Protocol Header

Description:
    Implements CreateHandoffTool — an agent-facing builtin for authoring structured
    handoff documents of arbitrary structure during a run.
Purpose:
    Lets an agent deliberately produce one or more handoffs, supplying the section
    titles and content directly. Records each result on the agent and in its context
    registry. The tool description dynamically shows past handoffs for consistency.
Architecture:
    - CreateHandoffTool: BaseTool bound to a live agent that builds a Handoff from
      caller-supplied sections, records it, and returns the rendered markdown.
Relations:
    Bound by vidbyte.agents.base.BaseAgent._bind_agent_tool_context. Depends on
    vidbyte.context.handoff.Handoff and BaseAgent.record_handoff.
Similar Files:
    - vidbyte/tools/builtins/context_primitives/upsert.py: Other agent-state builtin.
    - vidbyte/agents/handoff.py: HandoffAgent used by the auto-handoff path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.context.handoff import Handoff
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_STATIC_DESCRIPTION = """\
Author a structured handoff document that captures what you accomplished and what the receiver needs \
to know to continue. Call this tool whenever you want to create a persistent, transferable summary \
that another agent or a human can pick up and use without losing context.

When you call this tool you design the sections yourself — choose section titles that match what \
the receiver actually needs. There is no required structure. Pick titles that fit the task.

What makes a good handoff section:
- Be specific, not generic. Instead of "work on the feature," write "implement the rate-limiter \
middleware in backend/middleware/api/rate_limit.py and add integration tests under tests/rate_limiting/."
- Separate facts from inferences. Mark anything inferred but not verified with "inferred:" so the \
receiver knows what to double-check.
- Name concrete artifacts. Reference files, commands, schemas, or test results by name so the \
receiver can find them immediately.
- State why decisions were made, not only what was done. The receiver encounters the same trade-offs \
and needs the reasoning to preserve intent.
- Make the next action executable. End with steps ordered by dependency so the receiver can start \
without re-planning.

Common section patterns to consider (choose the ones that fit your task):
- Objective / Goal: What you were trying to achieve and what counts as complete.
- Changes Made / Work Done: What was built, modified, or deleted and why.
- Verification Status: What was tested, what passed, what was skipped, and what still needs checking.
- Open Threads / Blockers: Unfinished work, unresolved decisions, or missing information.
- Risks & Gotchas: Fragile areas, hidden dependencies, or things that could surprise the next worker.
- Next Steps: Ordered, concrete actions the receiver should execute immediately.
- Summary / Findings: A concise statement of the outcome for research or investigation tasks.
- Sources: Documents, URLs, datasets, or tool outputs that support the findings.
- Question: The research question, decision, or uncertainty the run was trying to resolve.
- Confidence & Gaps: Confidence in findings and unresolved information gaps.
- Recommended Next Queries: Specific follow-ups, source checks, or searches to run next.\
"""


class CreateHandoffTool(BaseTool):
    """Builtin tool that authors structured handoffs of arbitrary structure during a run."""

    def __init__(self) -> None:
        # Starts unbound; BaseAgent attaches the live agent via bind_agent().
        self._agent: Any = None

    def bind_agent(self, agent: Any) -> None:
        """Attach the live agent used for handoff recording."""
        self._agent = agent

    def clone_for_fork(self) -> CreateHandoffTool:
        # Returns a fresh unbound handoff tool so parent and child handoff state stay separate.
        return CreateHandoffTool()

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration with a rich description including past handoff context."""
        return ToolSpec(
            name="create_handoff",
            description=self._build_description(),
            permission=ToolPermission.SAFE,
            binds_to_primitive="handoff",
            input_schema=self._input_schema(),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Build a Handoff from caller-supplied sections, record it on the agent, and return it."""
        if self._agent is None:
            return ToolResult.error("create_handoff", "create_handoff is not bound to an agent.")
        args = dict(call.arguments)
        try:
            handoff = self._build_handoff(args)
        except ValueError as exc:
            return ToolResult.error("create_handoff", str(exc))
        self._agent.record_handoff(handoff)
        return self._render_result(handoff)

    def _build_handoff(self, args: Mapping[str, Any]) -> Handoff:
        """Validate caller args and construct the Handoff with a stable primitive id."""
        title = str(args.get("title", "")).strip()
        if not title:
            raise ValueError("create_handoff requires a non-empty 'title'.")
        sections = args.get("sections")
        if not isinstance(sections, Mapping) or not sections:
            raise ValueError("create_handoff requires a non-empty 'sections' object mapping section title to content.")
        normalized = {str(k): str(v) for k, v in sections.items()}
        primitive_id = self._next_primitive_id()
        instructions_parts: list[str] = []
        if audience := str(args.get("audience", "")).strip():
            instructions_parts.append(f"Audience: {audience}")
        if extra := str(args.get("instructions", "")).strip():
            instructions_parts.append(f"Instructions: {extra}")
        instructions = "\n".join(instructions_parts) or None
        return Handoff(title=title, sections=normalized, instructions=instructions, primitive_id=primitive_id)

    def _next_primitive_id(self) -> str:
        """Return a stable, monotonic primitive id scoped to the bound agent's run."""
        count = len(self._agent.handoffs) + 1 if self._agent is not None else 1
        return f"handoff:{count}"

    def _render_result(self, produced: Handoff) -> ToolResult:
        """Return the rendered handoff markdown with structured metadata."""
        metadata: dict[str, Any] = {
            "primitive_id": produced.primitive_id,
            "sections": dict(produced.sections),
        }
        return ToolResult.success("create_handoff", produced.to_context_text(), metadata=metadata)

    def _build_description(self) -> str:
        """Build the tool description, appending past handoff context when available."""
        parts = [_STATIC_DESCRIPTION]
        past = self._past_handoff_context()
        if past:
            parts.append(past)
        return "\n\n".join(parts)

    def _past_handoff_context(self) -> str:
        """Render a compact summary of handoffs already created this run as inspiration."""
        if self._agent is None:
            return ""
        handoffs: list[Handoff] = getattr(self._agent, "handoffs", [])
        if not handoffs:
            return ""
        lines = ["Handoffs authored so far this run (use these for context and consistency):"]
        for i, h in enumerate(handoffs, start=1):
            section_titles = ", ".join(h.sections.keys()) if h.sections else "(no sections)"
            lines.append(f"  {i}. \"{h.title}\" — sections: {section_titles}")
        return "\n".join(lines)

    def _input_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for the tool's inputs."""
        return {
            "type": "object",
            "required": ["title", "sections"],
            "additionalProperties": False,
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the handoff document.",
                },
                "sections": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "Handoff content as an object mapping section title to section content. "
                        "Design the sections to match what the receiver needs to continue."
                    ),
                },
                "audience": {
                    "type": "string",
                    "description": "Who will receive this handoff and what they need to do next.",
                },
                "instructions": {
                    "type": "string",
                    "description": "Extra authoring context or intent to attach to the handoff.",
                },
            },
        }


__all__ = ["CreateHandoffTool"]
