"""FILE: vidbyte/agents/jev/builders.py

PURPOSE: Implements the two role-specific generative agents used by every Jev done-criteria preset.
ROLE IN CODEBASE: JevRuntime constructs these subclasses around a JevAgent's configured generative model.
ARCHITECTURE NOTE: State extraction and run handoff are separate model tasks; each composes one prompt and one schema from the enabled sections.
COMMON MODIFICATION PATTERNS: Keep each builder strict, tool-free, and runner-cache-sharing; add a preset's prompt fragments to the maps below.
KNOWN EDGE CASES: A builder cannot reuse the main agent's public history, but receives the exact source snapshot in its input.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-scope-coverage-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-multipart-done-criteria.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.presets import JevPresets
from vidbyte.agents.jev.run_state import JevRunHandoff, JevRunSnapshot, JevRunState
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import OutputSchemaViolationError
from vidbyte.prompts.catalog import Prompts

STATE_SECTION_PROMPTS: Mapping[JevPresets, Prompt] = {
    JevPresets.MultiPart: Prompt.JEV_STATE_BUILDER_MULTI_PART,
    JevPresets.ScopeCoverage: Prompt.JEV_STATE_BUILDER_SCOPE_COVERAGE,
}
HANDOFF_SECTION_PROMPTS: Mapping[JevPresets, Prompt] = {
    JevPresets.MultiPart: Prompt.JEV_HANDOFF_BUILDER_MULTI_PART,
    JevPresets.ScopeCoverage: Prompt.JEV_HANDOFF_BUILDER_SCOPE_COVERAGE,
}


def _compose_prompt(base: Prompt, sections: tuple[Prompt, ...]) -> str:
    # Joins the base instructions with one fragment per included section, in preset declaration order.
    catalog = Prompts()
    return "\n\n".join((catalog.get(base), *(catalog.get(item) for item in sections)))


class JevRunStateBuilderAgent(BaseAgent):
    """Generative sub-agent that converts the original request into stable structured state."""

    def __init__(self, *, source_agent: BaseAgent, settings: JevAgentSettings, presets: tuple[JevPresets, ...]) -> None:
        # Configures one strict, tool-free state builder with the source agent's generative model.
        # @intent strict-builder-boundary
        # The source agent contributes its runner cache; explicit settings avoid coupling this helper to facade internals.
        super().__init__(
            name=f"{source_agent.name}-jev-state",
            system_prompt=_compose_prompt(Prompt.JEV_STATE_BUILDER, tuple(STATE_SECTION_PROMPTS[item] for item in presets)),
            provider=settings.provider,
            model_name=settings.model_name,
            api_key=settings.api_key,
            temperature=settings.temperature,
            tools=(),
            output_schema=JevRunState.output_schema(presets),
        )
        self._presets = presets
        self._runner_cache.update(source_agent._runner_cache)

    async def build_state(self, request: str) -> JevRunState:
        # Runs the once-per-run request projection and rejects absent structured output.
        # @intent reject-unstructured-state
        # Missing schema output must stop the run before the main agent operates with an incomplete Jev state.
        reply = await self.arun(request)
        payload = reply.metadata.get("structured")
        if payload is None:
            raise self._schema_error(reply.content, "the state builder returned no structured object")
        return JevRunState.from_payload(payload, presets=self._presets, original_request=request)

    @staticmethod
    def _schema_error(raw_output: str, reason: str) -> OutputSchemaViolationError:
        # Creates a typed failure that identifies the invalid builder output without leaking configuration.
        return OutputSchemaViolationError("Jev run state generation failed its output contract.", raw_output=raw_output, validation_error=reason)


class JevRunHandoffBuilderAgent(BaseAgent):
    """Generative sub-agent that maps observed run progress to every section the state requires."""

    def __init__(self, *, source_agent: BaseAgent, settings: JevAgentSettings, state: JevRunState) -> None:
        # Configures one strict, tool-free handoff builder against the exact generated state IDs.
        # @intent bind-handoff-to-state
        # The handoff schema is derived from this run's stable IDs so omissions cannot be accepted.
        sections = []
        if JevRunHandoff.needs_deliverables(state):
            sections.append(HANDOFF_SECTION_PROMPTS[JevPresets.MultiPart])
        if JevRunHandoff.needs_scope(state):
            sections.append(HANDOFF_SECTION_PROMPTS[JevPresets.ScopeCoverage])
        super().__init__(
            name=f"{source_agent.name}-jev-handoff",
            system_prompt=_compose_prompt(Prompt.JEV_HANDOFF_BUILDER, tuple(sections)),
            provider=settings.provider,
            model_name=settings.model_name,
            api_key=settings.api_key,
            temperature=settings.temperature,
            tools=(),
            output_schema=JevRunHandoff.output_schema(state),
        )
        self._state = state
        self._runner_cache.update(source_agent._runner_cache)

    async def build_handoff(self, snapshot: JevRunSnapshot) -> JevRunHandoff:
        # Generates the attempt-specific evidence handoff and enforces exact ID coverage in code.
        reply = await self.arun(snapshot.render())
        payload = reply.metadata.get("structured")
        if payload is None:
            raise OutputSchemaViolationError(
                "Jev run handoff generation failed its output contract.",
                raw_output=reply.content,
                validation_error="the handoff builder returned no structured object",
            )
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise OutputSchemaViolationError(
                    "Jev run handoff generation failed its output contract.",
                    raw_output=reply.content,
                    validation_error="structured handoff content was not valid JSON",
                ) from exc
        if not isinstance(payload, Mapping):
            raise OutputSchemaViolationError(
                "Jev run handoff generation failed its output contract.",
                raw_output=reply.content,
                validation_error=f"expected an object, got {type(payload).__name__}",
            )
        return JevRunHandoff.from_payload(payload, self._state, snapshot)


__all__ = ["JevRunHandoffBuilderAgent", "JevRunStateBuilderAgent"]
