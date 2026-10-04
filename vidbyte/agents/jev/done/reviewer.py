"""FILE: vidbyte/agents/jev/done/reviewer.py

PURPOSE: Implements JevReviewer, the strict reviewer the self-review done check runs at every finish attempt, before any other check: one tool-free turn over the main agent's own run that lists what a strict reviewer would reject in the work, most serious first.
ROLE IN CODEBASE: JevRunState builds one JevReviewer at construction when JevContinuationGate.SELF_REVIEW is enabled and calls review() from its check() before JevHandoff compiles evidence; the objections become the items the handoff gathers evidence for and Jev judges, and the record reaches the user as JevAgent.response.review.
ARCHITECTURE NOTE: The reviewer is the accuser, not the judge: it writes objections and acceptance conditions (generation), JevHandoff reports what the run shows about each one, and Jev decides which still stand and are in scope (recognition). It reuses the JevAgent's generative model and reads the same ContextManager window as the handoff, because the knowledge of the shortcuts lives in the main agent's own run; its prompt is fixed, it has no tools, and its reply is held to JevReviewPayload.
COMMON MODIFICATION PATTERNS: Change the reviewer's stance in vidbyte/prompts/prompts/jev_review/system_prompt.md and what each objection holds in the JevObjectionPayload field descriptions in vidbyte/lib/dataclasses/jev.py.
KNOWN EDGE CASES: A generative failure or a reply that never matches the schema returns None, so the self-review check fails open. Objections beyond JEV_REVIEW_MAX_OBJECTIONS are dropped, keeping the reviewer's most serious ones, rather than failing the whole review. History is cleared before every call, so an earlier finish attempt's review never leaks into a later one.
RELATED DOCS: docs/design/jev-self-review-done-criteria.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.settings import JevAgentSettings, JevContinuationGateSettings
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context import ContextManager
from vidbyte.lib.constants.jev import JEV_REVIEW_MAX_OBJECTIONS
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.jev import JevObjection, JevReviewPayload, JevReviewRecord
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.prompts.catalog import Prompts


class JevReviewer(BaseAgent):
    """Generative agent that reads the main agent's run as a strict reviewer and lists what it would reject, most serious first."""

    def __init__(self, settings: JevAgentSettings, continual: JevContinuationGateSettings) -> None:
        # Reuses the JevAgent's generative model and key and takes its limits from the continuation settings; the prompt, schema, and empty tool list are fixed here.
        # @intent the-reviewer-can-only-criticize
        # One turn with no tools: the reviewer can neither continue the user's work nor fix what it finds, so its
        # only output is criticism, and the caller cannot steer it into approving the work.
        super().__init__(
            name=f"{settings.name}-review",
            system_prompt=Prompts().get(Prompt.JEV_REVIEW_SYSTEM_PROMPT),
            agent_loop_settings=AgentLoopSettings(max_iterations=continual.review_max_iterations, max_tokens=continual.review_max_tokens),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
            output_schema=JevReviewPayload,
        )
        self.rendered = ""

    async def review(self, request: str, window: ContextManager) -> JevReviewRecord | None:
        """Return what a strict reviewer would reject in the run, most serious first, or None when the reviewer wrote no valid review."""
        self.history.clear()
        self.rendered = ""
        try:
            reply = await self.arun(AgentInput(prompt=request, context_manager=window))
            if not isinstance(reply.structured, JevReviewPayload):
                return None
            # @intent the-most-serious-objections-survive-the-cap
            # The reviewer orders objections most serious first, so a reply over the cap keeps its crux and drops
            # its tail instead of failing the whole review; the handoff then reads exactly what Jev will judge.
            kept = JevReviewPayload(objections=reply.structured.objections[:JEV_REVIEW_MAX_OBJECTIONS])
            record = JevReviewRecord(tuple(JevObjection(item.id, item.objection.strip(), item.resolved_when.strip()) for item in kept.objections), usage=self.get_usage())
            self.rendered = kept.model_dump_json()
            return record
        except VidbyteSdkError:
            # A reviewer outage, a reply that never matched the schema, or objections that fail their record's
            # validation fail the self-review check open, exactly as a Jev outage does.
            return None


__all__ = ["JevReviewer"]
