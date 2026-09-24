"""FILE: vidbyte/agents/jev/builders.py

PURPOSE: Defines the two generative builders behind JevAgent's done checks: one turns the request into a JevRunState before the loop, the other turns the run into a matching JevRunHandoff at each finish attempt.
ROLE IN CODEBASE: JevRuntime constructs a fresh builder per build and reads its validated record; both extend JevStructuredBuilderAgent, a tool-free BaseAgent with a strict output schema.
ARCHITECTURE NOTE: Builders reuse the main agent's runner and model settings, and assemble their system prompt and output schema from the enabled JevRunSection objects, so adding a section never changes this file.
COMMON MODIFICATION PATTERNS: Change builder wording in vidbyte/prompts/prompts/jev_run_state/; change a section's fields in its JevRunSection, not here.
KNOWN EDGE CASES: Unlike HandoffAgent there is no prose fallback: a schema miss raises OutputSchemaViolationError, because a finish gate must never accept an unparsed handoff.
RELATED DOCS: docs/design/jev-required-sequence.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_required_sequence.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.event_log import JevRunEventLog
from vidbyte.agents.jev.run_state import (
    JevRunHandoff,
    JevRunSection,
    JevRunState,
    JsonPayload,
    JsonSchema,
)
from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.pricing.records import UsageRollup
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.jev import JEV_BUILDER_MAX_ITERATIONS
from vidbyte.lib.constants.runners import RUNNER_TYPE_TEXT
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.prompts.catalog import Prompts


class JevStructuredBuilderAgent(BaseAgent):
    """Tool-free agent that returns exactly one JSON object validated against its output schema."""

    def __init__(self, *, name: str, system_prompt: str, output_schema: JsonSchema, settings: JevAgentSettings, runner: object) -> None:
        # Mirrors the main agent's model identity and binds its already-selected runner.
        # @intent builders-share-the-main-runner
        # Reusing the exact runner keeps one execution boundary per JevAgent run (and lets tests script
        # builder and main-loop responses in a single sequence) instead of resolving a second client.
        super().__init__(
            name=name,
            system_prompt=system_prompt,
            output_schema=output_schema,
            agent_loop_settings=AgentLoopSettings(max_iterations=JEV_BUILDER_MAX_ITERATIONS),
            provider=settings.provider,
            model_name=settings.model_name,
            api_key=settings.api_key,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )
        self._runner_cache[RUNNER_TYPE_TEXT] = runner

    async def abuild_payload(self, prompt: str) -> JsonPayload:
        """Run once and return the schema-validated JSON object."""
        reply = await self.arun(prompt)
        structured = reply.metadata.get("structured")
        if not isinstance(structured, Mapping):
            raise AgentExecutionError(
                f"Builder '{self.name}' returned no structured object.",
                details={"builder": self.name, "structured_type": type(structured).__name__},
            )
        return structured

    def usage(self) -> UsageRollup:
        """Return this builder's token usage so the run report can show what the done checks cost."""
        return self.get_usage()

    @staticmethod
    def compose_prompt(base: Prompt, section_texts: Sequence[str]) -> str:
        # Joins the base builder prompt with each enabled section's instructions, in section order.
        return "\n\n".join((Prompts().get(base), *section_texts))


class JevRunStateAgent(JevStructuredBuilderAgent):
    """Builds the JevRunState for one request before the main loop starts."""

    def __init__(self, *, settings: JevAgentSettings, runner: object, sections: Sequence[JevRunSection]) -> None:
        # Assembles the prompt and schema from the base state plus every enabled section.
        self.sections = tuple(sections)
        super().__init__(
            name="jev-run-state",
            system_prompt=self.compose_prompt(Prompt.JEV_RUN_STATE_STATE_BUILDER, [section.state_instructions() for section in self.sections]),
            output_schema=JevRunState.schema({section.key: section.state_schema() for section in self.sections}),
            settings=settings,
            runner=runner,
        )

    async def abuild(self, request: str) -> JevRunState:
        """Return the validated run state; raises when the answer does not fit the schema or the request."""
        payload = await self.abuild_payload(f"# User request\n{request}")
        return JevRunState.from_payload(payload, request=request, sections=self.sections)


class JevRunHandoffAgent(JevStructuredBuilderAgent):
    """Builds the JevRunHandoff for one finish attempt, shaped by the run state's active sections."""

    def __init__(self, *, settings: JevAgentSettings, runner: object, run_state: JevRunState, sections: Sequence[JevRunSection]) -> None:
        # The handoff schema depends on the state (for example the stage IDs), so it is built per run.
        self.run_state = run_state
        self.sections = tuple(sections)
        super().__init__(
            name="jev-run-handoff",
            system_prompt=self.compose_prompt(Prompt.JEV_RUN_STATE_HANDOFF_BUILDER, [section.handoff_instructions() for section in self.sections]),
            output_schema=JevRunHandoff.schema({section.key: section.handoff_schema(run_state.sections[section.key]) for section in self.sections}),
            settings=settings,
            runner=runner,
        )

    async def abuild(self, *, proposed_answer: str, event_log: JevRunEventLog, correction: str = "") -> JevRunHandoff:
        """Return the validated handoff; raises when it cites unknown events or misses a section entry."""
        payload = await self.abuild_payload(self.render_input(proposed_answer=proposed_answer, event_log=event_log, correction=correction))
        return JevRunHandoff.from_payload(
            payload,
            run_state=self.run_state,
            sections=self.sections,
            event_ids=event_log.event_ids(),
            through_event_id=event_log.last_event_id(),
        )

    def render_input(self, *, proposed_answer: str, event_log: JevRunEventLog, correction: str) -> str:
        """Render the request, run state, proposed answer, event log, and optional correction."""
        parts: list[tuple[str, Any]] = [
            ("Original request", self.run_state.request),
            ("Run state", json.dumps(self.run_state.to_payload(), indent=2)),
            ("Proposed final answer", proposed_answer or "(empty)"),
            ("Event log", event_log.render()),
        ]
        if correction:
            parts.append(("Correction", correction))
        return "\n\n".join(f"# {title}\n{body}" for title, body in parts)


__all__ = ["JevRunHandoffAgent", "JevRunStateAgent", "JevStructuredBuilderAgent"]
