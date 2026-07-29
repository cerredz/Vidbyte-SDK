"""Context Protocol Header

Description:
    Defines HandoffAgent, a thin configuration over BaseAgent that produces structured
    handoff documents from a completed agent run.
Purpose:
    Turns the comprehensive handoff system prompt plus a Handoff spec into an executable
    agent whose generate_handoff() returns a filled Handoff document.
Architecture:
    - HandoffAgent: BaseAgent subclass that composes its system prompt from the handoff
      prompt asset and the spec's section brief, then parses model output back into sections.
Relations:
    Subclasses vidbyte.agents.base.BaseAgent, consumes vidbyte.context.handoff.Handoff,
    reads Prompt.HANDOFF_SYSTEM_PROMPT through vidbyte.prompts.Prompts. Constructed by
    AgentClient.handoff() and by BaseAgent.handoff(). Source-agent construction
    carries the inferred runner cache so handoffs reuse the already-selected
    execution boundary without reviving a public runner argument.
Similar Files:
    - vidbyte/agents/base.py: The base agent this configures.
    - vidbyte/context/handoff/base.py: The Handoff spec/primitive this fills.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentMessage
from vidbyte.context.handoff import Handoff, MinimalHandoff
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import OutputSchemaViolationError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext

_SECTION_HEADER = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$", re.MULTILINE)


class HandoffAgent(BaseAgent):
    """Configured BaseAgent that fills a Handoff spec from a completed run's transcript."""

    def __init__(self, handoff: Handoff | None = None, *, name: str = "handoff", **kwargs: Any) -> None:
        # Store the spec, build the section-aware system prompt, and never auto-trigger its own handoff.
        self.spec: Handoff = handoff if handoff is not None else MinimalHandoff()
        kwargs.pop("handoff", None)
        kwargs.pop("system_prompt", None)
        kwargs.pop("output_schema", None)
        super().__init__(name=name, system_prompt=self.build_system_prompt(), handoff=None, output_schema=self.build_output_schema(), **kwargs)

    @classmethod
    def from_source_agent(cls, source_agent: BaseAgent, spec: Handoff) -> "HandoffAgent":
        """Build a handoff agent that reuses a source agent's runner and provider configuration."""
        generator = cls(
            spec,
            provider=source_agent.runner_config.provider,
            model_name=source_agent.runner_config.model_name,
            api_key=source_agent.runner_config.api_key,
            temperature=source_agent.runner_config.temperature,
        )
        generator._runner_cache.update(source_agent._runner_cache)
        return generator

    @classmethod
    async def run_auto_handoff(cls, source_agent: BaseAgent, spec: Handoff | None) -> Handoff:
        """Generate the configured auto-handoff for a completed source-agent run."""
        resolved = spec or MinimalHandoff()
        generator = cls.from_source_agent(source_agent, resolved)
        return await generator.generate_handoff(cls.render_source_run(source_agent))

    @classmethod
    def render_source_run(cls, source_agent: BaseAgent) -> str:
        """Compose a comprehensive digest of the most recent source-agent run."""
        final_output = source_agent.last_reply.content if source_agent.last_reply is not None else "No completed run recorded."
        sections = [
            f"# Source Agent\n{source_agent.name}",
            f"# Original System Prompt\n{source_agent.system_prompt}",
            f"# Original Task\n{source_agent.last_prompt or 'No task recorded.'}",
            f"# Conversation Transcript\n{cls.render_history(source_agent.history)}",
            f"# Tool Calls\n{cls.render_tool_calls(source_agent._tool_call_contexts)}",
            f"# Final Result\n{final_output}",
        ]
        return "\n\n".join(sections)

    @staticmethod
    def render_history(history: Sequence[AgentMessage]) -> str:
        """Render an ordered message transcript for handoff generation."""
        if not history:
            return "No conversation history."
        return "\n".join(f"[{message.sender} -> {message.recipient}] {message.content}" for message in history)

    @classmethod
    def render_tool_calls(cls, contexts: Sequence[ToolCallContext]) -> str:
        """Render recorded tool-call lifecycle entries for handoff generation."""
        if not contexts:
            return "No tools were used."
        return "\n".join(cls.render_one_tool_call(context) for context in contexts)

    @staticmethod
    def render_one_tool_call(context: ToolCallContext) -> str:
        """Render a single tool call's arguments, lifecycle state, and output."""
        state = getattr(context.state, "value", context.state)
        return f"- {context.name}({dict(context.arguments)}) [{state}] -> {context.output}"

    def build_system_prompt(self) -> str:
        # Compose the static handoff instructions with this spec's required sections and output title.
        base = Prompts().get(Prompt.HANDOFF_SYSTEM_PROMPT)
        brief = self.spec.render_section_brief()
        sections_block = f"# Required Sections\nProduce exactly these section keys inside the JSON `sections` object:\n{brief}" if brief else "# Required Sections\nNo fixed sections are required; write a concise free-form handoff inside the JSON `sections` object."
        instructions_line = f"\n\n# Author Instructions\n{self.spec.instructions}" if self.spec.instructions else ""
        return f"{base}\n\n# Output Title\n{self.spec.title}\n\n{sections_block}{instructions_line}"

    def build_output_schema(self) -> dict[str, Any]:
        """Build the deterministic JSON schema enforced for this handoff spec."""
        titles = self.spec.section_titles()
        section_properties = {
            title: {"type": "string", "description": description}
            for title, description in self.spec.sections.items()
        }
        section_schema: dict[str, Any] = {
            "type": "object",
            "properties": section_properties,
            "additionalProperties": {"type": "string"} if not titles else False,
        }
        if titles:
            section_schema["required"] = list(titles)
        return {
            "type": "object",
            "properties": {
                "sections": section_schema,
            },
            "required": ["sections"],
            "additionalProperties": False,
        }

    async def generate_handoff(self, source: str) -> Handoff:
        # Run the agent over the source-run digest and return a filled Handoff of the spec's subclass.
        content, payload = await self._run_source(source)
        sections, extra = self._sections_from_payload(payload) if payload is not None else self._split_sections(content)
        return self._build_filled(content, sections, extra)

    async def _run_source(self, source: str) -> tuple[str, Mapping[str, Any] | None]:
        # @intent handoff-degrades-to-prose-on-purpose
        # Every section this spec wants is also recoverable from markdown headers, so a schema miss
        # should yield a sparser document rather than fail the run that merely asked for a handoff.
        # This is the deliberate exception to output_schema being fatal, not a general escape hatch.
        try:
            reply = await self.arun(source)
        except OutputSchemaViolationError as violation:
            return violation.raw_output, self._parse_json_payload(violation.raw_output)
        return reply.content, self._structured_payload(reply)

    def parse_sections(self, text: str) -> dict[str, str]:
        # Public helper returning only the spec-matching section content parsed from model output.
        payload = self._parse_json_payload(text)
        sections, _ = self._sections_from_payload(payload) if payload is not None else self._split_sections(text)
        return sections

    def _structured_payload(self, reply: AgentMessage) -> Mapping[str, Any] | None:
        # Prefer runtime-validated structured output, then fall back to parsing raw JSON content.
        structured = reply.metadata.get("structured")
        payload = self._coerce_payload(structured)
        if payload is not None:
            return payload
        return self._parse_json_payload(reply.content)

    def _parse_json_payload(self, text: str) -> Mapping[str, Any] | None:
        # Parse model JSON output when output_schema enforcement produced structured content.
        try:
            return self._coerce_payload(json.loads(text))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def _sections_from_payload(self, payload: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
        # Extract spec-matching section content from a structured JSON payload.
        raw_sections = payload.get("sections", payload)
        if not isinstance(raw_sections, Mapping):
            return self._empty_sections(), {}
        wanted = {title.lower(): title for title in self.spec.section_titles()}
        if not wanted:
            return {str(title): self._string_value(value) for title, value in raw_sections.items()}, {}
        sections = self._empty_sections()
        extra: dict[str, str] = {}
        for title, value in raw_sections.items():
            canonical = wanted.get(str(title).lower())
            if canonical is not None:
                sections[canonical] = self._string_value(value)
            else:
                extra[str(title)] = self._string_value(value)
        return sections, extra

    def _build_filled(self, raw: str, sections: dict[str, str], extra: dict[str, str]) -> Handoff:
        # Attach raw output / extra sections to metadata so nothing produced is silently lost.
        filled = self.spec.fill(sections)
        if not any(value.strip() for value in sections.values()):
            filled.metadata["raw_output"] = raw
        if extra:
            filled.metadata["extra_sections"] = extra
        return filled

    def _split_sections(self, text: str) -> tuple[dict[str, str], dict[str, str]]:
        # Parse all "## Title" blocks, then sort them into spec sections and model-invented extras.
        parsed = self._parse_all_blocks(text)
        wanted = {title.lower(): title for title in self.spec.section_titles()}
        sections = self._empty_sections()
        extra: dict[str, str] = {}
        for header, body in parsed.items():
            canonical = wanted.get(header.lower())
            if canonical is not None:
                sections[canonical] = body
            else:
                extra[header] = body
        return sections, extra

    @staticmethod
    def _parse_all_blocks(text: str) -> dict[str, str]:
        # Map every markdown header to the text between it and the next header.
        matches = list(_SECTION_HEADER.finditer(text))
        blocks: dict[str, str] = {}
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            blocks[match.group(1).strip()] = text[start:end].strip()
        return blocks

    def _empty_sections(self) -> dict[str, str]:
        # Preserve the spec's section order when constructing a partially filled handoff.
        return {title: "" for title in self.spec.section_titles()}

    @staticmethod
    def _coerce_payload(value: Any) -> Mapping[str, Any] | None:
        # Normalize dict-like structured outputs, including Pydantic model instances.
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if isinstance(value, Mapping):
            return value
        return None

    @staticmethod
    def _string_value(value: Any) -> str:
        # Convert structured section values into handoff section text.
        if isinstance(value, str):
            return value
        return json.dumps(value, sort_keys=True) if isinstance(value, (Mapping, list, tuple)) else str(value)


__all__ = [
    "HandoffAgent",
]
