"""FILE: vidbyte/agents/jev/done/handoff.py

PURPOSE: Implements JevHandoff, the generative agent that reads the main agent's context at each finish attempt, compiles evidence for all enabled done checks, and extracts post-run claims and problems.
ROLE IN CODEBASE: JevRunState constructs JevHandoff and calls compile() at each finish attempt; the compiled record is projected into Jev's single batched decision request.
ARCHITECTURE NOTE: The output schema has one typed section per enabled check. The handoff reads the request, run state, supplied user turns, and main-agent window as context, reuses JevAgent's model, and has no tools. It gathers cumulative per-turn observations, request-derived evidence, and post-run claim and problem items; proxy milestones remain separate from direct target evidence.
COMMON MODIFICATION PATTERNS: Add each check to `_SECTIONS` and convert its typed payload in `_record()`. Match ids to run-state items only for request-derived checks; validate dynamic claim and problem ids in their typed records.
KNOWN EDGE CASES: A model failure, invalid payload, or request-derived id mismatch returns None so checks fail open. Cumulative evidence requires one entry for each obligation and supplied turn; problem evidence requires exactly one original-request completion item. History is cleared before each call so a prior attempt cannot leak into the next.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-cumulative-obligations-done-check.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-mid-run-problem-repair-gate.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
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
    JevCumulativeObligationEvidence,
    JevCumulativeObligationEvidencePayload,
    JevCumulativeObligationsEvidence,
    JevCumulativeUserTurnEvidence,
    JevDeliverableEvidence,
    JevHandoffPayload,
    JevHandoffRecord,
    JevMultiPartEvidence,
    JevMultiPartEvidencePayload,
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevProblemsResolvedEvidencePayload,
    JevRunStateRecord,
    JevSectionPayload,
    JevTargetOutcomeEvidence,
    JevTargetOutcomeEvidenceItem,
    JevTargetOutcomeEvidencePayload,
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
    _SECTIONS: ClassVar[Mapping[JevDoneCheck, type[JevSectionPayload]]] = MappingProxyType({
        JevDoneCheck.MULTI_PART: JevMultiPartEvidencePayload,
        JevDoneCheck.CLAIMS: JevClaimsEvidencePayload,
        JevDoneCheck.CUMULATIVE_OBLIGATIONS: JevCumulativeObligationEvidencePayload,
        JevDoneCheck.TARGET_OUTCOME: JevTargetOutcomeEvidencePayload,
        JevDoneCheck.PROBLEMS_RESOLVED: JevProblemsResolvedEvidencePayload,
    })

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
    def window(run_state: str, responses: Sequence[str], calls: Sequence[ToolCallContext], final_answer: str, *, sender: str, user_turns: Sequence[str] = ()) -> ContextManager:
        """Build the handoff's context from state, exact supplied user turns, run responses and tool calls, and final answer."""
        # @intent the-handoff-reads-the-main-agents-window
        # The owner asked for the main agent's context window to reach the handoff through vidbyte.context, so the
        # run is passed as the SDK's own response and tool-call primitives instead of a hand-built transcript.
        items: list[ContextItem] = [TextContextItem(title=RUN_STATE_TITLE, content=run_state, source=HANDOFF_SOURCE)]
        if user_turns:
            turns = "\n\n".join(f"User turn {index}:\n{text}" for index, text in enumerate(user_turns))
            items.append(TextContextItem(title="Exact user turns for cumulative obligations", content=turns, source=HANDOFF_SOURCE))
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
        cumulative_obligations = None
        obligations_section = getattr(payload, JevDoneCheck.CUMULATIVE_OBLIGATIONS.value, None)
        if isinstance(obligations_section, JevCumulativeObligationEvidencePayload):
            cumulative_obligations = JevCumulativeObligationsEvidence(tuple(
                JevCumulativeObligationEvidence(item.id, item.evidence.strip(), item.missing.strip())
                for item in obligations_section.obligations
            ), tuple(JevCumulativeUserTurnEvidence(item.id, item.evidence.strip()) for item in obligations_section.turns))
            expected = () if state.cumulative_obligations is None else state.cumulative_obligations.ids()
            if cumulative_obligations.ids() != expected:
                return None
            expected_turns = () if state.cumulative_obligations is None else tuple(f"turn_{index}" for index in range(len(state.cumulative_obligations.user_turns)))
            if cumulative_obligations.turn_ids() != expected_turns:
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
        target_outcome = None
        outcome_section = getattr(payload, JevDoneCheck.TARGET_OUTCOME.value, None)
        if isinstance(outcome_section, JevTargetOutcomeEvidencePayload):
            # Request-derived target items require one exact evidence match each; an incomplete handoff fails open.
            target_outcome = JevTargetOutcomeEvidence(tuple(
                JevTargetOutcomeEvidenceItem(item.id, item.observed_proxy.strip(), item.direct_evidence.strip(), item.missing.strip())
                for item in outcome_section.items
            ))
            expected = () if state.target_outcome is None else state.target_outcome.ids()
            if sorted(target_outcome.ids()) != sorted(expected):
                return None
        problems_resolved = None
        problem_section = getattr(payload, JevDoneCheck.PROBLEMS_RESOLVED.value, None)
        if isinstance(problem_section, JevProblemsResolvedEvidencePayload):
            problems_resolved = JevProblemsResolvedEvidence(tuple(
                JevProblemResolutionItem(
                    item.id,
                    item.kind,
                    item.title.strip(),
                    item.description.strip(),
                    item.scope.strip(),
                    item.qualifications.strip(),
                    item.repair.strip(),
                    item.verification.strip(),
                    item.evidence.strip(),
                    item.missing.strip(),
                )
                for item in problem_section.items
            ))
        return JevHandoffRecord(
            multi_part=multi_part,
            cumulative_obligations=cumulative_obligations,
            claims=claims,
            target_outcome=target_outcome,
            problems_resolved=problems_resolved,
            usage=self.get_usage(),
        )


__all__ = ["JevHandoff"]
