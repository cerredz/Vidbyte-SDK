"""FILE: vidbyte/agents/jev/done/handoff.py

PURPOSE: Implements JevHandoff, the generative agent that reads the main agent's context window each time it tries to finish and compiles the evidence every enabled done check needs, in a shape tailored to each check.
ROLE IN CODEBASE: JevRunState builds one JevHandoff at construction and calls compile() from its check(); Jev then answers one question per item, all in one request, over the compiled evidence.
ARCHITECTURE NOTE: The handoff is general: its output schema is JevHandoffPayload plus one field per enabled JevDoneCheck, typed as that check's evidence payload and described by its SECTION text, so a new check adds one entry to _SECTIONS instead of a new class. It reads the user's request as its message and the run state and the main agent's window as a vidbyte.context ContextManager of standard primitives; it reuses the JevAgent's generative model, but its prompt is fixed, it has no tools, and its reply is held to the composed schema.
COMMON MODIFICATION PATTERNS: Change what the agent writes in vidbyte/prompts/prompts/jev_handoff/system_prompt.md and each field's description in vidbyte/lib/dataclasses/jev.py; add a done check's evidence section to _SECTIONS and its record conversion to _record().
KNOWN EDGE CASES: A generative failure, a reply that never matches the schema, or evidence whose item ids (deliverable ids, or expert-depth detail ids) differ from the run state's returns None, so the done check fails open. History is cleared before every call, so an earlier finish attempt's handoff never leaks into a later one.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-expert-depth-done-criteria.md, skills/jev-continuation/SKILL.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import Field, create_model

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings, JevContinualSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context import ContextManager
from vidbyte.context.primitives import (
    ContextItem,
    ResponseContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import (
    JevDeliverableEvidence,
    JevExpertDepthEvidence,
    JevExpertDepthEvidencePayload,
    JevExpertDetailEvidence,
    JevHandoffPayload,
    JevHandoffRecord,
    JevMultiPartEvidence,
    JevMultiPartEvidencePayload,
    JevRunStateRecord,
    JevSectionPayload,
)
from vidbyte.lib.enums.jev import JevDoneCheck
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.types import ToolCallContext

# The titles and source of the context items that frame the main agent's window, named in the system prompt.
RUN_STATE_TITLE = "Run state"
FINAL_ANSWER_TITLE = "Final answer"
NO_FINAL_ANSWER = "The main agent gave no final answer."
HANDOFF_SOURCE = "jev_done"


class JevHandoff(BaseAgent):
    """Generative agent that compiles, from the main agent's context window, the evidence every enabled done check needs."""

    # One evidence section per done check; the field name is the check's value, so the reply mirrors the run state.
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartEvidencePayload, JevDoneCheck.EXPERT_DEPTH: JevExpertDepthEvidencePayload})

    def __init__(self, settings: JevAgentSettings, continual: JevContinualSettings) -> None:
        # Reuses the JevAgent's generative model and key and takes its limits from the continuation settings; the prompt, schema, and empty tool list are fixed here.
        # @intent handoff-can-only-report
        # The handoff writer compiles evidence for a checker; with no tools and a fixed prompt it can neither
        # continue the user's work nor be steered by the caller into judging it.
        payload = self.schema(continual.checks)
        super().__init__(
            name=f"{settings.name}-handoff",
            system_prompt=Prompts().get(Prompt.JEV_HANDOFF_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=continual.handoff_max_iterations, max_tokens=continual.handoff_max_tokens),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=payload,
        )
        self.checks = continual.checks
        self.payload = payload
        self.rendered = ""

    @classmethod
    def schema(cls, checks: tuple[JevDoneCheck, ...]) -> type[JevHandoffPayload]:
        """Return the handoff's output schema: JevHandoffPayload plus one described evidence section per enabled check."""
        sections: dict[str, Any] = {check.value: (cls._SECTIONS[check], Field(description=cls._SECTIONS[check].SECTION)) for check in checks}
        return create_model("JevHandoffPayload", __base__=JevHandoffPayload, **sections)

    @staticmethod
    def window(run_state: str, responses: Sequence[str], calls: Sequence[ToolCallContext], final_answer: str, *, sender: str) -> ContextManager:
        """Build the handoff's context: the run state, then the main agent's responses and tool calls, then its final answer."""
        # @intent the-handoff-reads-the-main-agents-window
        # The owner asked for the main agent's context window to reach the handoff through vidbyte.context, so the
        # run is passed as the SDK's own response and tool-call primitives instead of a hand-built transcript.
        items: list[ContextItem] = [TextContextItem(title=RUN_STATE_TITLE, content=run_state, source=HANDOFF_SOURCE)]
        items.extend(ResponseContextItem(content=text, sender=sender) for text in responses if text.strip())
        items.extend(ToolCallContextItem(name=call.name, arguments=dict(call.arguments), output=call.output, metadata={"state": str(getattr(call.state, "value", call.state))}) for call in calls)
        items.append(TextContextItem(title=FINAL_ANSWER_TITLE, content=final_answer if final_answer.strip() else NO_FINAL_ANSWER, source=HANDOFF_SOURCE))
        return ContextManager(items)

    async def compile(self, request: str, state: JevRunStateRecord, window: ContextManager) -> JevHandoffRecord | None:
        """Return the evidence for every enabled check, or None when the agent wrote none that matches the run state."""
        self.history.clear()
        self.rendered = ""
        try:
            reply = await self.arun(AgentInput(prompt=request, context_manager=window))
            if not isinstance(reply.structured, self.payload):
                return None
            record = self._record(reply.structured, state)
            # The continuation hands this text back to the main agent when a check fails.
            self.rendered = "" if record is None else reply.structured.model_dump_json()
            return record
        except VidbyteSdkError:
            # A handoff outage, a reply that never matched the schema, or evidence that fails its record's
            # validation fails the done check open, exactly as a Jev outage does.
            return None

    def _record(self, payload: JevHandoffPayload, state: JevRunStateRecord) -> JevHandoffRecord | None:
        # Converts the validated reply into the frozen record, requiring one evidence entry per run-state deliverable.
        # @intent evidence-covers-exactly-the-run-state
        # Jev judges each deliverable by id, so evidence for a deliverable the state never listed, or
        # no evidence for one it did, would silently skip a check; either one makes the handoff unavailable.
        multi_part = None
        section = getattr(payload, JevDoneCheck.MULTI_PART.value, None)
        if isinstance(section, JevMultiPartEvidencePayload):
            multi_part = JevMultiPartEvidence(tuple(JevDeliverableEvidence(item.id, item.evidence.strip(), item.missing.strip()) for item in section.deliverables))
            expected = () if state.multi_part is None else state.multi_part.ids()
            if sorted(multi_part.ids()) != sorted(expected):
                return None
        # The same rule holds for expert depth, whose items are the details of every deliverable.
        expert_depth = None
        section = getattr(payload, JevDoneCheck.EXPERT_DEPTH.value, None)
        if isinstance(section, JevExpertDepthEvidencePayload):
            expert_depth = JevExpertDepthEvidence(tuple(JevExpertDetailEvidence(item.id, item.evidence.strip(), item.missing.strip()) for item in section.details))
            expected = () if state.expert_depth is None else state.expert_depth.ids()
            if sorted(expert_depth.ids()) != sorted(expected):
                return None
        return JevHandoffRecord(multi_part=multi_part, expert_depth=expert_depth, usage=self.get_usage())


__all__ = ["JevHandoff"]
