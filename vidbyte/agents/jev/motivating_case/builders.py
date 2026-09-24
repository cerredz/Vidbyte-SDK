"""FILE: vidbyte/agents/jev/motivating_case/builders.py

PURPOSE: Defines the two generative sub-agents of the motivating-case check: one builds the run state, one builds each finish-attempt handoff.
ROLE IN CODEBASE: JevRuntime runs MotivatingCaseStateBuilderAgent once before the loop and MotivatingCaseHandoffBuilderAgent at each finish attempt.
ARCHITECTURE NOTE: Both reuse the source JevAgent's generative model and runner cache, run tool-free with a strict output schema, and never fall back to prose.
COMMON MODIFICATION PATTERNS: Change a builder's prompt asset and its record's output schema together; keep interpretation here and judgment in Jev.
KNOWN EDGE CASES: Schema violations raise OutputSchemaViolationError; JevRuntime turns them into a fail-open metadata status.
RELATED DOCS: docs/design/jev-motivating-case.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.motivating_case.evidence import RunEventLedger
from vidbyte.agents.jev.motivating_case.handoff import MotivatingCaseHandoff
from vidbyte.agents.jev.motivating_case.state import MotivatingCaseState
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import OutputSchemaViolationError
from vidbyte.prompts.catalog import Prompts


class _JevBuilderAgent(BaseAgent):
    """Tool-free structured-output sub-agent that shares its source agent's generative model."""

    def __init__(self, *, source_agent: BaseAgent, name_suffix: str, prompt: Prompt, output_schema: dict[str, Any]) -> None:
        # Mirrors the source agent's model identity and runner cache so builders need no separate credentials.
        # @intent builders-share-source-model
        # Reusing the source runner cache means builders need no extra credentials and tests script one runner for the whole run.
        config = source_agent.runner_config
        super().__init__(
            name=f"{source_agent.name}-{name_suffix}",
            system_prompt=Prompts().get(prompt),
            provider=config.provider,
            model_name=config.model_name,
            api_key=config.api_key,
            temperature=config.temperature,
            output_schema=output_schema,
        )
        self._runner_cache.update(source_agent._runner_cache)

    @staticmethod
    def _structured(reply: AgentMessage) -> object:
        # Returns the runtime-validated structured object, parsing a JSON string when a provider returned one.
        payload = reply.metadata.get("structured")
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError as exc:
                raise OutputSchemaViolationError("Jev builder returned structured content that is not JSON.", raw_output=reply.content, validation_error=str(exc)) from exc
        if payload is None:
            raise OutputSchemaViolationError("Jev builder returned no structured object.", raw_output=reply.content, validation_error="missing structured output")
        return payload


class MotivatingCaseStateBuilderAgent(_JevBuilderAgent):
    """Turns the original request into the boundary scenarios it is about, once per run."""

    def __init__(self, *, source_agent: BaseAgent) -> None:
        # Configures the state builder with its prompt and strict state schema.
        super().__init__(source_agent=source_agent, name_suffix="jev-motivating-state", prompt=Prompt.JEV_MOTIVATING_CASE_STATE_BUILDER, output_schema=MotivatingCaseState.output_schema())

    async def build_state(self, request: str, *, note: str | None = None) -> MotivatingCaseState:
        # Builds and validates the state; the optional note carries the recall guard's disagreement on a rebuild.
        # @intent state-quotes-checked-against-request
        # Parsing against the original request (not the prompt with the reviewer note) keeps quote verification anchored to user text.
        prompt = request if note is None else f"{request}\n\n---\nReviewer note: {note}"
        reply = await self.arun(prompt)
        return MotivatingCaseState.from_payload(self._structured(reply), request)


class MotivatingCaseHandoffBuilderAgent(_JevBuilderAgent):
    """Links each scenario to the events that built, ran, inspected, or blocked it, at one finish attempt."""

    def __init__(self, *, source_agent: BaseAgent, state: MotivatingCaseState) -> None:
        # Configures the handoff builder against the exact scenario ids of this run's state.
        super().__init__(source_agent=source_agent, name_suffix="jev-motivating-handoff", prompt=Prompt.JEV_MOTIVATING_CASE_HANDOFF_BUILDER, output_schema=MotivatingCaseHandoff.output_schema(state))
        self._state = state

    async def build_handoff(self, request: str, ledger: RunEventLedger, final_output: str) -> MotivatingCaseHandoff:
        # Renders the request, state, events, and candidate reply, then enforces exact scenario coverage.
        # @intent handoff-coverage-enforced-in-code
        # The schema already pins ids and counts, but from_payload re-checks coverage because providers do not all enforce schemas.
        reply = await self.arun(self.render_input(request, ledger, final_output))
        payload = self._structured(reply)
        if not isinstance(payload, Mapping):
            raise OutputSchemaViolationError("Jev handoff builder returned a non-object.", raw_output=reply.content, validation_error=type(payload).__name__)
        return MotivatingCaseHandoff.from_payload(payload, self._state)

    def render_input(self, request: str, ledger: RunEventLedger, final_output: str) -> str:
        # Lays out the four inputs under headings the prompt refers to by name.
        # @intent builder-sees-bounded-events
        # The builder reads the bounded rendering while quotes are verified against full records, so truncation can never forge evidence.
        return "\n\n".join(
            [
                f"# Original request\n{request}",
                f"# Run state\n{json.dumps(self._state.to_payload(), ensure_ascii=False)}",
                f"# Events\n{ledger.render()}",
                f"# Candidate final reply\n{final_output}",
            ]
        )


__all__ = ["MotivatingCaseHandoffBuilderAgent", "MotivatingCaseStateBuilderAgent"]
