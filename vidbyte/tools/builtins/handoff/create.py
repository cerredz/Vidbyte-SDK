"""Context Protocol Header

Description:
    Implements CreateHandoffTool — an agent-facing builtin for authoring structured
    handoff documents during a run.
Purpose:
    Lets an agent deliberately produce one or more handoffs from explicit intent,
    routing generation through the existing HandoffAgent path and recording each
    result on the agent and in its context registry.
Architecture:
    - CreateHandoffTool: BaseTool bound to a live agent that resolves a Handoff spec
      from caller intent, generates it via BaseAgent.handoff(), and records it.
Relations:
    Bound by vidbyte.agents.base.BaseAgent._bind_agent_tool_context. Depends on
    vidbyte.context.handoff schemas and BaseAgent.handoff / BaseAgent.record_handoff.
Similar Files:
    - vidbyte/tools/builtins/context_primitives/upsert.py: Other agent-state builtin.
    - vidbyte/agents/handoff.py: The generator this delegates to.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.context.handoff import EngineeringHandoff, Handoff, MinimalHandoff, ResearchHandoff
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_SUPPORTED_TYPES = ("engineering", "research", "minimal", "custom")


class CreateHandoffTool(BaseTool):
    """Builtin tool that authors structured handoffs from caller intent during a run."""

    _SCHEMA_REGISTRY: dict[str, type[Handoff]] = {
        "engineering": EngineeringHandoff,
        "research": ResearchHandoff,
        "minimal": MinimalHandoff,
    }

    def __init__(self) -> None:
        # Starts unbound; BaseAgent attaches the live agent via bind_agent().
        self._agent: Any = None

    def bind_agent(self, agent: Any) -> None:
        """Attach the live agent used for generation and handoff recording."""
        self._agent = agent

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration with a rich intent input schema."""
        return ToolSpec(
            name="create_handoff",
            description=(
                "Author a structured handoff document from explicit intent and the current run. "
                "Choose a schema (engineering, research, minimal, or custom) and provide the objective "
                "and context the receiver needs. Can be called multiple times in one run."
            ),
            permission=ToolPermission.SAFE,
            binds_to_primitive="handoff",
            input_schema=self._input_schema(),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Resolve intent into a spec, generate via the bound agent, record, and render the result."""
        if self._agent is None:
            return ToolResult.error("create_handoff", "create_handoff is not bound to an agent.")
        args = dict(call.arguments)
        try:
            spec, handoff_type = self._resolve_spec(args)
        except ValueError as exc:
            return ToolResult.error("create_handoff", str(exc))
        produced = await self._generate(spec)
        self._agent.record_handoff(produced)
        return self._render_result(produced, handoff_type)

    def _resolve_spec(self, args: Mapping[str, Any]) -> tuple[Handoff, str]:
        """Build the concrete Handoff spec for the requested type, attaching intent, title, and id."""
        handoff_type = str(args.get("handoff_type", "")).strip().lower()
        if handoff_type not in _SUPPORTED_TYPES:
            raise ValueError(f"Unknown handoff_type '{handoff_type}'. Supported: {', '.join(_SUPPORTED_TYPES)}.")
        if not str(args.get("objective", "")).strip():
            raise ValueError("create_handoff requires a non-empty 'objective'.")
        intent = self._compose_intent(args)
        title = str(args.get("title", "")).strip() or None
        primitive_id = self._next_primitive_id()
        if handoff_type == "custom":
            sections = self._normalize_custom_sections(args.get("custom_sections"))
            spec: Handoff = Handoff(sections=sections, title=title, instructions=intent, primitive_id=primitive_id)
        else:
            spec = self._SCHEMA_REGISTRY[handoff_type](title=title, instructions=intent, primitive_id=primitive_id)
        return spec, handoff_type

    def _compose_intent(self, args: Mapping[str, Any]) -> str:
        """Join the present intent fields into a single labeled instruction block for the generator."""
        labels = (
            ("objective", "Objective"),
            ("audience", "Audience"),
            ("scope", "Scope"),
            ("non_goals", "Non-Goals"),
            ("instructions", "Author Instructions"),
        )
        parts = [f"{label}: {value}" for key, label in labels if (value := str(args.get(key, "")).strip())]
        return "\n".join(parts)

    def _normalize_custom_sections(self, raw: Any) -> dict[str, str]:
        """Validate and stringify a custom section map, requiring at least one section."""
        if not isinstance(raw, Mapping) or not raw:
            raise ValueError("handoff_type 'custom' requires a non-empty 'custom_sections' object.")
        return {str(title): str(guidance) for title, guidance in raw.items()}

    def _next_primitive_id(self) -> str:
        """Return a stable, monotonic primitive id scoped to the bound agent's run."""
        return f"handoff:{len(self._agent.handoffs) + 1}"

    async def _generate(self, spec: Handoff) -> Handoff:
        """Generate a filled handoff through the bound agent's HandoffAgent path."""
        return await self._agent.handoff(spec)

    def _render_result(self, produced: Handoff, handoff_type: str) -> ToolResult:
        """Render the produced handoff as markdown with structured metadata for the caller."""
        metadata: dict[str, Any] = {
            "primitive_id": produced.primitive_id,
            "handoff_type": handoff_type,
            "sections": dict(produced.sections),
        }
        extra = produced.metadata.get("extra_sections")
        if extra:
            metadata["extra_sections"] = dict(extra)
        raw = produced.metadata.get("raw_output")
        if raw:
            metadata["raw_output"] = raw
        return ToolResult.success("create_handoff", produced.to_context_text(), metadata=metadata)

    def _input_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing the tool's rich intent inputs."""
        return {
            "type": "object",
            "required": ["handoff_type", "objective"],
            "additionalProperties": False,
            "properties": {
                "handoff_type": {
                    "type": "string",
                    "enum": list(_SUPPORTED_TYPES),
                    "description": "Which handoff schema to produce.",
                },
                "objective": {
                    "type": "string",
                    "description": "Why this handoff exists and the target state the receiver must reach.",
                },
                "audience": {
                    "type": "string",
                    "description": "Who receives this handoff (next agent/human) and what they must do next.",
                },
                "title": {
                    "type": "string",
                    "description": "Optional title override for the handoff.",
                },
                "scope": {
                    "type": "string",
                    "description": "What is in scope for the receiver.",
                },
                "non_goals": {
                    "type": "string",
                    "description": "Explicit exclusions / what not to do.",
                },
                "instructions": {
                    "type": "string",
                    "description": "Extra authoring guidance for the generator.",
                },
                "custom_sections": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Required when handoff_type=custom: map of section title -> section guidance.",
                },
            },
        }


__all__ = ["CreateHandoffTool"]
