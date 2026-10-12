"""FILE: vidbyte/agents/jev/alignment/skills.py

PURPOSE: Loads the caller-configured skills for one JevAgent request, asks Jev which loaded skills fit the request, and appends only the passing document bodies to that run's system prompt.
ROLE IN CODEBASE: JevAgent builds this preload only for nonempty `JevAlignmentSettings.skills`; JevRuntime invokes it after prompt and tool alignment and before run-state setup and the main loop.
ARCHITECTURE NOTE: Resolution is delegated to SkillLoader (vidbyte/agents/skills/), built once per preload and therefore once per agent; this file only sees the loaded SkillDocument values and each entry's load reason. The preload packs indexed questions into bounded TypeSafe decision requests, scores each answer independently, and records metadata plus the JevUsage total of the answered requests without storing skill text in JevAgent.response. Context replacement is immutable; runtime mutation cleanup remains JevRuntime's responsibility.
FUNCTION INVENTORY:
    JevSkillsPreload.__init__(skills, decision, threshold, response) -> None: stores the validated run-time inputs and builds the skill loader without any I/O.
    JevSkillsPreload.run(message, context) -> BaseAgentContext: loads the skills, asks Jev about every batch concurrently, records per-skill outcomes with a reason for each unavailable skill, and returns the skill-extended context.
    JevSkillsPreload._build_batches(message) -> tuple[JevSkillBatch, ...]: greedily packs whole loaded skills in settings order; a skill too large to send alone joins no batch.
    JevSkillsPreload._build_batch(message, indices) -> JevSkillBatch | None: builds one request, or None when it would exceed the byte bounds.
    JevSkillsPreload._unbatched(batches) -> dict[int, JevSkillResult]: marks each loaded skill in no batch as too large for this request.
    JevSkillsPreload._failed_batch(batch, detail) -> dict[int, JevSkillResult]: marks every skill of a batch whose Jev answer cannot be used.
    JevSkillsPreload._score_skill(index, skill, answers) -> JevSkillResult: independently scores one fixed-index answer.
    JevSkillsPreload._append_selected(context, selected) -> BaseAgentContext: appends exact full texts to a replaced system prompt.
COMMON MODIFICATION PATTERNS: Resolution is delegated to SkillLoader; a new skill source changes vidbyte/agents/skills/, never this file. Changes here must preserve indexed question prose and per-candidate result behavior.
WHAT NOT TO DO:
    1. Do not execute, fetch, or interpret commands from a skill body.
    2. Do not interpolate caller names, descriptions, sources, or text into Jev instructions.
    3. Do not let one missing answer or failed batch erase another candidate's valid answer.
    4. Do not catch cancellation or arbitrary programming errors as provider failures.
    5. Do not keep module-level constants here; the four unavailable details live inside the methods that set them.
KNOWN EDGE CASES: A skill that never loaded is unavailable with the loader's reason and detail and has no description or source. A loaded candidate that cannot fit alone is unavailable as too_large without truncation, recomputed on every run because the limit depends on the request. All batches are asked concurrently; a failed batch leaves only its own skills unavailable, and every other batch keeps its outcome. A run where nothing loads asks Jev nothing and returns the context unchanged. An empty tuple is handled by JevAgent, which constructs no preload and makes no skill call.
RELATED DOCS: `docs/design/jev-skills-preload.md`, `docs/spec/jev-skill-sources/spec.md`, `vidbyte/agents/skills/README.md`, `tests/features/jev_skills_preload/FEATURE.md`, and `skills/jev-agent/SKILL.md`.
TESTS: `tests/test_jev_skill_preload.py`, `tests/features/jev_skills_preload/test_skill_sources_jev_wiring.py`, and `scripts/test-jev-skills-preload.py`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import replace

from vidbyte.agents.jev.preload import JevPreload
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.skills.loader import SkillLoader
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_SKILL_INDEX_BASE,
    JEV_SKILLS_MAX_REQUEST_JSON_BYTES,
    JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES,
    JEV_SKILLS_PROMPT_SECTION,
)
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevJson,
    JevSkillBatch,
    JevSkillResult,
    JevSkillsOutcome,
)
from vidbyte.lib.dataclasses.skills import SkillDocument, SkillEntry
from vidbyte.lib.enums.jev import JevQuestionType, JevSkillStatus
from vidbyte.lib.enums.skills import SkillUnavailableReason
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight.skills import JevSkillRelevanceQuestion


class JevSkillsPreload(JevPreload):
    """Selects relevant documents once for one run and appends their exact bodies."""

    def __init__(self, *, skills: tuple[SkillEntry | SkillDocument, ...], decision: DecisionModelConfig, threshold: float, response: JevResponse) -> None:
        # @intent validated-settings-cross-the-preload-boundary
        # JevAgent passes already-normalized skills, a validated decision configuration and threshold, and the response writer for this run.
        self.skills = skills
        self.decision = decision
        self.threshold = threshold
        self.response = response
        # The loader reads nothing until the first run, so building an
        # agent never touches a skill source.
        self.loader = SkillLoader(skills)

    async def run(self, message: str, context: BaseAgentContext) -> BaseAgentContext:
        # @intent each-candidate-has-an-independent-result
        # An answer only ever decides its own skill, and a skill Jev never answered for is unavailable rather than a no.
        # Load every skill first. Skills loaded on an earlier run cost
        # nothing, and a skill that cannot load stays unavailable with the
        # loader's reason, so one broken source never stops the run.
        resolutions = await self.loader.load()
        loaded = {index: document for index, document in enumerate(self.loader.documents(), start=JEV_SKILL_INDEX_BASE) if document is not None}
        # Start every skill as unavailable. A skill that never loaded keeps
        # the loader's reason and has no description or label to show; a
        # loaded skill counts as unanswered until Jev answers for it.
        results = {
            index: self._score_skill(index, loaded[index], {})
            if index in loaded
            else JevSkillResult(name=skill.name, description=None, source=None, status=JevSkillStatus.UNAVAILABLE, reason=resolution.reason, detail=resolution.detail)
            for index, (skill, resolution) in enumerate(zip(self.skills, resolutions, strict=True), start=JEV_SKILL_INDEX_BASE)
        }
        # Split the loaded skills into requests small enough for Jev. A
        # skill too large to send even on its own joins no batch, so it is
        # marked too large for this request instead of being cut short.
        batches = self._build_batches(message)
        results.update(self._unbatched(batches))
        # Ask Jev about every batch at the same time, one request per batch, so waiting does not grow with the batch count.
        decisions = await asyncio.gather(*(DecisionModelHelper(self.decision).arun(batch.request) for batch in batches), return_exceptions=True)
        usages: list[JevUsage] = []
        for batch, decision in zip(batches, decisions, strict=True):
            # A Jev failure leaves only this batch's skills unavailable, and the run goes on without them because skills
            # are optional guidance. Cancellation and programming errors are not Jev failures, so they propagate.
            if isinstance(decision, VidbyteSdkError):
                results.update(self._failed_batch(batch, f"Jev decision request failed ({type(decision).__name__}); check VIDBYTE_API_KEY and the Jev decision settings; the run continued without this skill"))
                continue
            if isinstance(decision, BaseException):
                raise decision
            # Count the tokens the request used; a reply without token counts fails like any other Jev error.
            try:
                usage = JevUsage.from_decision(decision)
            except VidbyteSdkError:
                results.update(self._failed_batch(batch, "Jev's reply had no token counts, so its answers were not used"))
                continue
            usages.append(usage)
            # Score each skill from its own answer, so a missing or malformed answer cannot change a sibling's outcome.
            results.update({index: self._score_skill(index, loaded[index], decision.answers) for index in batch.indices})
        # Record every skill's outcome in settings order with the tokens the answered requests used, but never the skill text.
        self.response.skills(JevSkillsOutcome(results=tuple(results.values()), usage=JevUsage.total(usages)))
        # Add the full text of each selected skill to this run's system prompt only.
        selected = tuple(loaded[index] for index, result in results.items() if result.status is JevSkillStatus.SELECTED)
        return self._append_selected(context, selected)

    def _build_batches(self, message: str) -> tuple[JevSkillBatch, ...]:
        # @intent pack-without-truncating-candidates
        # Skills are packed whole in settings order, so each keeps its global question index and its full text.
        batches: list[JevSkillBatch] = []
        for index, document in enumerate(self.loader.documents(), start=JEV_SKILL_INDEX_BASE):
            # A skill that has not loaded has nothing to send.
            if document is None:
                continue
            alone = self._build_batch(message, (index,))
            # A skill too large to send even on its own joins no batch.
            if alone is None:
                continue
            grown = self._build_batch(message, (*batches[-1].indices, index)) if batches else None
            # Add the skill to the open batch while the request still fits; otherwise it opens the next batch.
            if grown is None:
                batches.append(alone)
            else:
                batches[-1] = grown
        return tuple(batches)

    def _build_batch(self, message: str, indices: tuple[int, ...]) -> JevSkillBatch | None:
        # @intent byte-bounds-match-the-provider-json-shape
        # Counting the UTF-8 bytes of the JSON body TypeSafe receives keeps the estimate conservative without claiming provider byte limits.
        # The state carries the user's message and each skill's full record under its own question's name.
        questions = tuple(JevSkillRelevanceQuestion(index).to_question() for index in indices)
        documents = self.loader.documents()
        skills = (documents[index - JEV_SKILL_INDEX_BASE] for index in indices)
        records = {question.name: {"name": skill.name, "description": skill.description, "source": skill.source, "text": skill.text} for question, skill in zip(questions, skills, strict=True) if skill is not None}
        state = {"request": message, "skills": records}
        # Measure the whole body, and the state paired with each single question, the way TypeSafe receives them.
        payloads = {question.name: {"type": question.question_type.value, "instructions": JevJson.thaw(question.instructions), "criteria": {option.name: JevJson.thaw(option.description) for option in question.options}} for question in questions}
        request_bytes = len(json.dumps({"model": self.decision.model, "state": state, "questions": payloads}).encode("utf-8"))
        state_and_question_bytes = max(len(json.dumps({"state": state, "question": payload}).encode("utf-8")) for payload in payloads.values())
        if request_bytes > JEV_SKILLS_MAX_REQUEST_JSON_BYTES or state_and_question_bytes > JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES:
            return None
        return JevSkillBatch(indices=indices, request=JevDecisionRequest(state=state, questions=questions))

    def _unbatched(self, batches: tuple[JevSkillBatch, ...]) -> dict[int, JevSkillResult]:
        # @intent too-large-is-decided-per-request
        # Whether a skill fits depends on this run's request, so a loaded
        # skill in no batch is too large for this run only and is never
        # remembered as a load failure.
        detail = "too large to send to Jev with this request: a batch holding only this skill must fit JEV_SKILLS_MAX_REQUEST_JSON_BYTES request bytes and JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES state-and-question bytes; shorten SKILL.md or the request"
        batched = {index for batch in batches for index in batch.indices}
        return {
            index: JevSkillResult(name=document.name, description=document.description, source=document.source, status=JevSkillStatus.UNAVAILABLE, reason=SkillUnavailableReason.TOO_LARGE, detail=detail)
            for index, document in enumerate(self.loader.documents(), start=JEV_SKILL_INDEX_BASE)
            if document is not None and index not in batched
        }

    def _failed_batch(self, batch: JevSkillBatch, detail: str) -> dict[int, JevSkillResult]:
        # @intent failed-batch-fails-only-its-own-skills
        # Every skill in a batch whose answer cannot be used is unavailable
        # with the same detail; other batches keep their own outcomes.
        documents = self.loader.documents()
        return {
            index: JevSkillResult(name=skill.name, description=skill.description, source=skill.source, status=JevSkillStatus.UNAVAILABLE, reason=SkillUnavailableReason.DECISION_FAILED, detail=detail)
            for index in batch.indices
            if (skill := documents[index - JEV_SKILL_INDEX_BASE]) is not None
        }

    def _score_skill(self, index: int, skill: SkillDocument, answers: Mapping[str, JevAnswer]) -> JevSkillResult:
        # @intent canonical-noul-threshold-owns-selection
        # The helper validates a single indexed noul answer; missing, mismatched, or malformed records remain unavailable instead of becoming a negative decision.
        identifier = JevSkillRelevanceQuestion(index).name
        answer = answers.get(identifier)
        valid_answer = isinstance(answer, JevAnswer) and answer.question_name == identifier and answer.question_type is JevQuestionType.NOUL
        verdict = DecisionModelHelper.score_noul(answers, (identifier,), self.threshold) if valid_answer else None
        if verdict is None:
            return JevSkillResult(
                name=skill.name,
                description=skill.description,
                source=skill.source,
                status=JevSkillStatus.UNAVAILABLE,
                reason=SkillUnavailableReason.DECISION_FAILED,
                detail="Jev answered this batch but gave no usable answer for this skill",
            )
        status = JevSkillStatus.SELECTED if verdict.passed else JevSkillStatus.SKIPPED
        return JevSkillResult(name=skill.name, description=skill.description, source=skill.source, status=status, probability=answer.noul)

    @staticmethod
    def _append_selected(context: BaseAgentContext, selected: tuple[SkillDocument, ...]) -> BaseAgentContext:
        # @intent preserve-baseline-and-append-selected-guidance
        # The selected source text is added only to the immutable replacement context for this run and is never copied into its response record.
        if not selected:
            return context
        text = JEV_SKILLS_PROMPT_SECTION + "\n\n---\n\n".join(skill.text for skill in selected)
        return replace(context, system_prompt=f"{context.system_prompt or ''}{text}")


__all__ = ["JevSkillsPreload"]
