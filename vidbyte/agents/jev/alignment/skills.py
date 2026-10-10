"""FILE: vidbyte/agents/jev/alignment/skills.py

PURPOSE: Selects caller-configured skill documents for one JevAgent request and appends only passing document bodies to that run's system prompt.
ROLE IN CODEBASE: JevAgent builds this preload only for nonempty `JevAlignmentSettings.skills`; JevRuntime invokes it after prompt and tool alignment and before run-state setup and the main loop.
ARCHITECTURE NOTE: The preload packs indexed questions into bounded TypeSafe decision requests, scores each answer independently, and records metadata plus the JevUsage total of the answered requests without storing skill text in JevAgent.response. Context replacement is immutable; runtime mutation cleanup remains JevRuntime's responsibility.
FUNCTION INVENTORY:
    JevSkillsPreload.__init__(skills, decision, threshold, response) -> None: stores the validated run-time inputs.
    JevSkillsPreload.run(message, context) -> BaseAgentContext: asks Jev batch by batch, records per-skill outcomes, and returns the skill-extended context.
    JevSkillsPreload._build_batches(message) -> tuple[JevSkillBatch, ...]: greedily packs whole skills in settings order; a skill too large to send alone joins no batch.
    JevSkillsPreload._build_batch(message, indices) -> JevSkillBatch | None: builds one request, or None when it would exceed the byte bounds.
    JevSkillsPreload._score_skill(index, skill, answers) -> JevSkillResult: independently scores one fixed-index answer.
    JevSkillsPreload._append_selected(context, selected) -> BaseAgentContext: appends exact full texts to a replaced system prompt.
COMMON MODIFICATION PATTERNS: Keep source resolution outside this core contract. Future source adapters may provide resolved SkillDocument values, but must preserve indexed question prose and per-candidate result behavior.
WHAT NOT TO DO:
    1. Do not execute, fetch, or interpret commands from a skill body.
    2. Do not interpolate caller names, descriptions, sources, or text into Jev instructions.
    3. Do not let one missing answer or failed batch erase another candidate's valid answer.
    4. Do not catch cancellation or arbitrary programming errors as provider failures.
KNOWN EDGE CASES: A candidate that cannot fit alone is unavailable without truncation. The first failed batch stops the asking: skills already answered keep their outcome and every skill not yet answered is unavailable. An empty tuple is handled by JevAgent, which constructs no preload and makes no skill call.
RELATED DOCS: `docs/design/jev-skills-preload.md`, `tests/features/jev_skills_preload/FEATURE.md`, and `skills/jev-agent/SKILL.md`.
TESTS: `tests/test_jev_skill_preload.py` and `scripts/test-jev-skills-preload.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace

from vidbyte.agents.jev.preload import JevPreload
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.pricing import JevUsage
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
from vidbyte.lib.dataclasses.skills import SkillDocument
from vidbyte.lib.enums.jev import JevQuestionType, JevSkillStatus
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight.skills import JevSkillRelevanceQuestion


class JevSkillsPreload(JevPreload):
    """Selects relevant documents once for one run and appends their exact bodies."""

    def __init__(self, *, skills: tuple[SkillDocument, ...], decision: DecisionModelConfig, threshold: float, response: JevResponse) -> None:
        # @intent validated-settings-cross-the-preload-boundary
        # JevAgent passes already-normalized documents, a validated decision configuration and threshold, and the response writer for this run.
        self.skills = skills
        self.decision = decision
        self.threshold = threshold
        self.response = response

    async def run(self, message: str, context: BaseAgentContext) -> BaseAgentContext:
        # @intent each-candidate-has-an-independent-result
        # An answer only ever decides its own skill, and a skill Jev never answered for is unavailable rather than a no.
        # Start every skill as unavailable; a skill's status changes only once Jev has actually answered for it.
        results = {
            index: JevSkillResult(name=skill.name, description=skill.description, source=skill.source, status=JevSkillStatus.UNAVAILABLE)
            for index, skill in enumerate(self.skills, start=JEV_SKILL_INDEX_BASE)
        }
        # Split the skills into requests small enough for Jev. A skill too large to send even on its own joins no
        # batch, so it stays unavailable instead of being cut short.
        batches = self._build_batches(message)
        usages: list[JevUsage] = []
        try:
            for batch in batches:
                # Ask Jev about every skill in this batch in one request.
                decision = await DecisionModelHelper(self.decision).arun(batch.request)
                # Count the tokens the request used; a reply without token counts fails like any other Jev error.
                usages.append(JevUsage.from_decision(decision))
                # Score each skill from its own answer, so a missing or malformed answer cannot change a sibling's outcome.
                results.update({index: self._score_skill(index, self.skills[index - JEV_SKILL_INDEX_BASE], decision.answers) for index in batch.indices})
        except VidbyteSdkError:
            # Jev failed, so stop asking: skills it already answered keep their outcome, the rest stay unavailable,
            # and the run goes on without them because skills are optional guidance.
            pass
        # Record every skill's outcome in settings order with the tokens the answered requests used, but never the skill text.
        self.response.skills(JevSkillsOutcome(results=tuple(results.values()), usage=JevUsage.total(usages)))
        # Add the full text of each selected skill to this run's system prompt only.
        selected = tuple(skill for skill, result in zip(self.skills, results.values(), strict=True) if result.status is JevSkillStatus.SELECTED)
        return self._append_selected(context, selected)

    def _build_batches(self, message: str) -> tuple[JevSkillBatch, ...]:
        # @intent pack-without-truncating-candidates
        # Skills are packed whole in settings order, so each keeps its global question index and its full text.
        batches: list[JevSkillBatch] = []
        for index, _ in enumerate(self.skills, start=JEV_SKILL_INDEX_BASE):
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
        skills = (self.skills[index - JEV_SKILL_INDEX_BASE] for index in indices)
        records = {question.name: {"name": skill.name, "description": skill.description, "source": skill.source, "text": skill.text} for question, skill in zip(questions, skills, strict=True)}
        state = {"request": message, "skills": records}
        # Measure the whole body, and the state paired with each single question, the way TypeSafe receives them.
        payloads = {question.name: {"type": question.question_type.value, "instructions": JevJson.thaw(question.instructions), "criteria": {option.name: JevJson.thaw(option.description) for option in question.options}} for question in questions}
        request_bytes = len(json.dumps({"model": self.decision.model, "state": state, "questions": payloads}).encode("utf-8"))
        state_and_question_bytes = max(len(json.dumps({"state": state, "question": payload}).encode("utf-8")) for payload in payloads.values())
        if request_bytes > JEV_SKILLS_MAX_REQUEST_JSON_BYTES or state_and_question_bytes > JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES:
            return None
        return JevSkillBatch(indices=indices, request=JevDecisionRequest(state=state, questions=questions))

    def _score_skill(self, index: int, skill: SkillDocument, answers: Mapping[str, JevAnswer]) -> JevSkillResult:
        # @intent canonical-noul-threshold-owns-selection
        # The helper validates a single indexed noul answer; missing, mismatched, or malformed records remain unavailable instead of becoming a negative decision.
        identifier = JevSkillRelevanceQuestion(index).name
        answer = answers.get(identifier)
        valid_answer = isinstance(answer, JevAnswer) and answer.question_name == identifier and answer.question_type is JevQuestionType.NOUL
        verdict = DecisionModelHelper.score_noul(answers, (identifier,), self.threshold) if valid_answer else None
        if verdict is None:
            return JevSkillResult(name=skill.name, description=skill.description, source=skill.source, status=JevSkillStatus.UNAVAILABLE)
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
