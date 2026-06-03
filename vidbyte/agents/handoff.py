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
    Subclasses vidbyte.agents.base.BaseAgent, consumes vidbyte.context.handoffs.Handoff,
    reads Prompt.HANDOFF_SYSTEM_PROMPT through vidbyte.prompts.Prompts. Constructed by
    AgentClient.handoff() and by BaseAgent.handoff().
Similar Files:
    - vidbyte/agents/base.py: The base agent this configures.
    - vidbyte/context/handoffs.py: The Handoff spec/primitive this fills.
"""

from __future__ import annotations

import re
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.context.handoffs import Handoff, MinimalHandoff
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

_SECTION_HEADER = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$", re.MULTILINE)


class HandoffAgent(BaseAgent):
    """Configured BaseAgent that fills a Handoff spec from a completed run's transcript."""

    def __init__(self, handoff: Handoff | None = None, *, name: str = "handoff", **kwargs: Any) -> None:
        # Store the spec, build the section-aware system prompt, and never auto-trigger its own handoff.
        self.spec: Handoff = handoff if handoff is not None else MinimalHandoff()
        kwargs.pop("handoff", None)
        kwargs.pop("system_prompt", None)
        super().__init__(name=name, system_prompt=self.build_system_prompt(), handoff=None, **kwargs)

    def build_system_prompt(self) -> str:
        # Compose the static handoff instructions with this spec's required sections and output title.
        base = Prompts().get(Prompt.HANDOFF_SYSTEM_PROMPT)
        brief = self.spec.render_section_brief()
        sections_block = f"# Required Sections\nProduce exactly these sections, each as a `## <Title>` markdown block:\n{brief}" if brief else "# Required Sections\nNo fixed sections are required; write a concise free-form handoff."
        instructions_line = f"\n\n# Author Instructions\n{self.spec.instructions}" if self.spec.instructions else ""
        return f"{base}\n\n# Output Title\n{self.spec.title}\n\n{sections_block}{instructions_line}"

    async def generate_handoff(self, source: str) -> Handoff:
        # Run the agent over the source-run digest and return a filled Handoff of the spec's subclass.
        reply = await self.arun(source)
        sections, extra = self._split_sections(reply.content)
        return self._build_filled(reply.content, sections, extra)

    def parse_sections(self, text: str) -> dict[str, str]:
        # Public helper returning only the spec-matching section content parsed from model output.
        sections, _ = self._split_sections(text)
        return sections

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
        sections = {title: "" for title in self.spec.section_titles()}
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


__all__ = [
    "HandoffAgent",
]
