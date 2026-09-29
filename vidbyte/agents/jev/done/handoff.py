"""FILE: vidbyte/agents/jev/done/handoff.py

PURPOSE: Implements JevHandoff, the generative agent that reads the main agent's context window at each finish attempt, compiles evidence for request-derived checks including output quantities, and extracts checkable final-answer claims for CLAIMS.
ROLE IN CODEBASE: JevRunState builds one JevHandoff at construction and calls compile() from its check(); Jev then answers one question per item, all in one request, over the compiled evidence.
ARCHITECTURE NOTE: The handoff is general: its output schema is JevHandoffPayload plus one field per enabled check, typed as that check's evidence payload and described by its SECTION text. It reads the user's request as its message and the run state and main agent's window as standard `vidbyte.context` primitives, including every `ToolCallContextItem`; it reuses the JevAgent's generative model, has no tools, and is constrained by the composed schema. Claims are generated from the final answer here because their item list does not exist before the main agent works.
COMMON MODIFICATION PATTERNS: Change field instructions in `vidbyte/lib/dataclasses/jev.py`; add an enabled handoff section to _SECTIONS and convert it in _record(). Output-count entries retain every candidate's visible value and source evidence and match the request-derived obligation ids. Compare ids to run-state items only for checks whose candidates were written before work, not for dynamic final-answer claims.
KNOWN EDGE CASES: A generative failure, a reply that never matches the schema, or request-derived evidence whose ids differ from the run state's returns None, so checks fail open. Claims have no pre-run id list; their ids must be valid and unique within the generated claim section. History is cleared before each call, so an earlier finish attempt's handoff never leaks into a later one.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-output-count-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
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
    JevClaimAssertion,
    JevClaimContext,
    JevClaimEvidence,
    JevClaimIdentity,
    JevClaimScope,
    JevClaimsEvidence,
    JevClaimsEvidencePayload,
    JevDeliverableEvidence,
    JevHandoffPayload,
    JevHandoffRecord,
    JevMultiPartEvidence,
    JevMultiPartEvidencePayload,
    JevOutputCountEntry,
    JevOutputCountEvidence,
    JevOutputCountEvidenceItem,
    JevOutputCountEvidencePayload,
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
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({JevDoneCheck.MULTI_PART: JevMultiPartEvidencePayload, JevDoneCheck.OUTPUT_COUNT: JevOutputCountEvidencePayload, JevDoneCheck.CLAIMS: JevClaimsEvidencePayload})

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
        """Return evidence for every enabled check, or None when a request-derived section does not match run state."""
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
        output_count = None
        output_count_section = getattr(payload, JevDoneCheck.OUTPUT_COUNT.value, None)
        if isinstance(output_count_section, JevOutputCountEvidencePayload):
            output_count = JevOutputCountEvidence(tuple(
                JevOutputCountEvidenceItem(
                    item.id,
                    tuple(JevOutputCountEntry(candidate.id, candidate.value.strip(), candidate.distinct_key.strip(), candidate.evidence.strip()) for candidate in item.entries),
                    item.missing.strip(),
                )
                for item in output_count_section.obligations
            ))
            expected = () if state.output_count is None else state.output_count.ids()
            if sorted(output_count.ids()) != sorted(expected):
                return None
        claims = None
        claims_section = getattr(payload, JevDoneCheck.CLAIMS.value, None)
        if isinstance(claims_section, JevClaimsEvidencePayload):
            # The claim ids are created from this final answer, so validate uniqueness here instead of matching
            # them to a pre-run list that cannot contain statements the main agent has not made yet.
            # @intent claims-are-derived-after-the-work
            claims = JevClaimsEvidence(tuple(
                JevClaimEvidence(
                    item.id,
                    JevClaimContext(
                        identity=JevClaimIdentity(
                            title=item.claim.identity.title.strip(),
                            description=item.claim.identity.description.strip(),
                            intent=None if item.claim.identity.intent is None else item.claim.identity.intent.strip(),
                        ),
                        scope=JevClaimScope(
                            scope=item.claim.scope.scope.strip(),
                            qualifications=tuple(value.strip() for value in item.claim.scope.qualifications),
                        ),
                        kind=item.claim.kind,
                        output=None if item.claim.output is None else item.claim.output.strip(),
                        assertions=tuple(
                            JevClaimAssertion(
                                assertion.id,
                                assertion.statement.strip(),
                                assertion.completion_criteria.strip(),
                            )
                            for assertion in item.claim.assertions
                        ),
                    ),
                    item.evidence.strip(),
                    item.missing.strip(),
                )
                for item in claims_section.claims
            ))
        return JevHandoffRecord(multi_part=multi_part, output_count=output_count, claims=claims, usage=self.get_usage())


__all__ = ["JevHandoff"]
