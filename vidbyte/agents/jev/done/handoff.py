"""FILE: vidbyte/agents/jev/done/handoff.py

PURPOSE: Implements JevHandoff, the generative agent that reads the main agent's context window at each finish attempt and compiles evidence for every enabled done check. It validates required-action output excerpts against their cited source and extracts claims, observed-trigger actions, and run problems that cannot exist before work.
ROLE IN CODEBASE: JevRunState builds one JevHandoff at construction and calls compile() from its check(); Jev then answers one question per item, all in one request, over the compiled evidence.
ARCHITECTURE NOTE: The output schema is JevHandoffPayload plus one described field per enabled check. The handoff reads the request, run state, and main-agent window as standard context primitives, reuses JevAgent's generative model, has no tools, and is constrained by the composed schema. Claims, guaranteed-action candidates, and observed problem episodes are extracted after work because their item lists cannot exist in the pre-run state; Jev independently judges their evidence, and private action-necessity rationale stays out of Jev state.
COMMON MODIFICATION PATTERNS: Change field instructions in `vidbyte/lib/dataclasses/jev.py`; add each check's enabled handoff section to `_SECTIONS` and convert it in `_record()`. Match ids to run-state items only for request-derived checks, validate dynamic ids in their typed records, and validate output excerpts against the exact cited source.
KNOWN EDGE CASES: A generative failure, invalid schema reply, request-derived id mismatch, or invalid required-action trace returns None so checks fail open. Dynamic claim, action, and problem ids must be unique; PROBLEMS_RESOLVED must include exactly one original-request completion item. History is cleared before each call, so evidence from a prior finish attempt cannot leak into the next.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-required-actions-done-criteria.md, docs/design/jev-target-outcome-done-check.md, docs/design/jev-mid-run-problem-repair-gate.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
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
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevProblemsResolvedEvidencePayload,
    JevRequiredActionEvidence,
    JevRequiredActionsEvidence,
    JevRequiredActionsEvidencePayload,
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
        JevDoneCheck.REQUIRED_ACTIONS: JevRequiredActionsEvidencePayload,
        JevDoneCheck.TARGET_OUTCOME: JevTargetOutcomeEvidencePayload,
        JevDoneCheck.PROBLEMS_RESOLVED: JevProblemsResolvedEvidencePayload,
    })

    def __init__(self, settings: JevAgentSettings, continual: JevContinualSettings) -> None:
        # Reuses the JevAgent's generative model and key and takes its limits from the continuation settings; the prompt, schema, and empty tool list are fixed here.
        # @intent handoff-can-only-report
        # The handoff writer compiles evidence for a checker; with no tools and a fixed prompt it can neither
        # continue the user's work nor be steered by the caller into judging it.
        payload = self.schema(tuple(JevDoneCheck(check) for check in continual.checks))
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
        items.extend(ResponseContextItem(content=f"response[{index}]: {text}", sender=sender) for index, text in enumerate(responses) if text.strip())
        items.extend(
            ToolCallContextItem(
                name=f"trace[{index}] {call.name} state={getattr(call.state, 'value', call.state)}",
                arguments=dict(call.arguments),
                output=call.output,
                metadata={"state": str(getattr(call.state, "value", call.state)), "trace_index": index},
            )
            for index, call in enumerate(calls)
        )
        items.append(TextContextItem(title=FINAL_ANSWER_TITLE, content=final_answer if final_answer.strip() else NO_FINAL_ANSWER, source=HANDOFF_SOURCE))
        return ContextManager(items)

    async def compile(self, request: str, state: JevRunStateRecord, window: ContextManager, calls: Sequence[ToolCallContext] = (), responses: Sequence[str] = (), final_answer: str = "") -> JevHandoffRecord | None:
        """Return evidence for every enabled check, or None when a request-derived section does not match run state."""
        self.history.clear()
        self.rendered = ""
        try:
            reply = await self.arun(AgentInput(prompt=request, context_manager=window))
            if not isinstance(reply.structured, self.payload):
                return None
            record = self._record(reply.structured, state, calls, responses, final_answer)
            # The continuation hands this text back to the main agent when a check fails.
            self.rendered = "" if record is None else reply.structured.model_dump_json()
            return record
        except VidbyteSdkError:
            # A handoff outage, a reply that never matched the schema, or evidence that fails its record's
            # validation fails the done check open, exactly as a Jev outage does.
            return None

    def _record(self, payload: JevHandoffPayload, state: JevRunStateRecord, calls: Sequence[ToolCallContext] = (), responses: Sequence[str] = (), final_answer: str = "") -> JevHandoffRecord | None:
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
        required_actions = None
        actions_section = getattr(payload, JevDoneCheck.REQUIRED_ACTIONS.value, None)
        if isinstance(actions_section, JevRequiredActionsEvidencePayload):
            required_actions = self._required_action_evidence(actions_section, responses, final_answer)
            if not self._valid_required_action_trace(required_actions, state, calls):
                return None
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
            claims=claims,
            required_actions=required_actions,
            target_outcome=target_outcome,
            problems_resolved=problems_resolved,
            usage=self.get_usage(),
        )

    @classmethod
    def _required_action_evidence(cls, section: JevRequiredActionsEvidencePayload, responses: Sequence[str], final_answer: str) -> JevRequiredActionsEvidence:
        """Convert handoff action evidence and retain output excerpts only when their exact source is present."""
        action_evidence: list[JevRequiredActionEvidence] = []
        for item in section.actions:
            output_is_cited = cls._valid_output_excerpt(item.output_source, item.output_excerpt, responses, final_answer)
            action_evidence.append(JevRequiredActionEvidence(
                item.id,
                item.evidence.strip(),
                tuple(item.trace_indices),
                item.completion_trace_index,
                item.missing.strip(),
                item.output_source if output_is_cited else None,
                item.output_excerpt.strip() if output_is_cited and item.output_excerpt is not None else None,
            ))
        return JevRequiredActionsEvidence(tuple(action_evidence))

    @staticmethod
    def _valid_required_action_trace(evidence: JevRequiredActionsEvidence, state: JevRunStateRecord, calls: Sequence[ToolCallContext]) -> bool:
        """Check that action evidence matches run-state ids and cites only actual successful trace calls."""
        expected = () if state.required_actions is None else state.required_actions.ids()
        if evidence.ids() != expected:
            return False
        return all(JevHandoff._valid_action_call(item, calls) for item in evidence.actions)

    @staticmethod
    def _valid_action_call(item: JevRequiredActionEvidence, calls: Sequence[ToolCallContext]) -> bool:
        """Validate one action's cited indices and its optional successful completion call."""
        if any(index >= len(calls) for index in item.trace_indices):
            return False
        if item.completion_trace_index is None:
            return True
        call = calls[item.completion_trace_index]
        return str(getattr(call.state, "value", call.state)) == "succeeded"

    @staticmethod
    def _valid_output_excerpt(source: str | None, excerpt: str | None, responses: Sequence[str], final_answer: str) -> bool:
        """Return whether the cited excerpt appears exactly in its claimed recorded source."""
        if source is None or excerpt is None or not excerpt.strip():
            return False
        if source == "final_answer":
            text = final_answer
        elif source.startswith("response[") and source.endswith("]"):
            try:
                index = int(source[9:-1])
                text = responses[index]
            except (ValueError, IndexError):
                return False
        else:
            return False
        return excerpt.strip() in text


__all__ = ["JevHandoff"]
