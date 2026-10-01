"""FILE: vidbyte/agents/jev/alignment/skills.py

PURPOSE: Selects caller-configured skill documents for one JevAgent request and appends only passing document bodies to that run's system prompt.
ROLE IN CODEBASE: JevAgent builds this preload only for nonempty `JevAlignmentSettings.skills`; JevRuntime invokes it after prompt and tool alignment and before run-state setup and the main loop.
ARCHITECTURE NOTE: The preload packs indexed questions into bounded TypeSafe decision requests, scores each answer independently, and records metadata plus summed usage without storing skill text in JevAgent.response. Context replacement is immutable; runtime mutation cleanup remains JevRuntime's responsibility.
FUNCTION INVENTORY:
    JevSkillsPreload.__init__(skills, decision, threshold, response) -> None: stores the validated run-time inputs.
    JevSkillsPreload.run(message, context) -> BaseAgentContext: batches questions, records per-skill outcomes, and returns the skill-extended context.
    JevSkillsPreload._build_batches(message) -> tuple: greedily packs whole candidate records under local serialized-byte bounds and returns oversized indices separately.
    JevSkillsPreload._score_skill(index, skill, answers) -> JevSkillResult: independently scores one fixed-index answer.
    JevSkillsPreload._sum_usage(usages) -> JevUsage | None: adds available usage from successful batches once.
    JevSkillsPreload._append_selected(context, selected) -> BaseAgentContext: appends exact full texts to a replaced system prompt.
COMMON MODIFICATION PATTERNS: Keep source resolution outside this core contract. Future source adapters may provide resolved SkillDocument values, but must preserve indexed question prose and per-candidate result behavior.
WHAT NOT TO DO:
    1. Do not execute, fetch, or interpret commands from a skill body.
    2. Do not interpolate caller names, descriptions, sources, or text into Jev instructions.
    3. Do not let one missing answer or failed batch erase another candidate's valid answer.
    4. Do not catch cancellation or arbitrary programming errors as provider failures.
KNOWN EDGE CASES: A candidate that cannot fit alone is unavailable without truncation; a failed batch does not block other batches. An empty tuple is handled by JevAgent, which constructs no preload and makes no skill call.
RELATED DOCS: `docs/design/jev-skills-preload.md`, `tests/features/jev_skills_preload/FEATURE.md`, and `skills/jev-agent/SKILL.md`.
TESTS: `tests/test_jev_skill_preload.py` and `scripts/test-jev-skills-preload.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace

from vidbyte.agents.jev.preload import JevPreload
from vidbyte.agents.pricing import JevUsage
from vidbyte.agents.jev.response import JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_MAX_QUESTIONS
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevJson, JevSkillResult, JevSkillsOutcome
from vidbyte.lib.dataclasses.skills import SkillDocument
from vidbyte.lib.enums.jev import JevQuestionType, JevSkillStatus
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight.skills import JevSkillRelevanceQuestion

_SKILL_SECTION = """

--- Caller-selected skill guidance for this request ---

"""
_SKILL_INDEX_BASE = 1
_MAX_REQUEST_JSON_BYTES = 60_000
_MAX_STATE_AND_QUESTION_JSON_BYTES = 30_000
_SkillBatch = tuple[tuple[int, ...], JevDecisionRequest]


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
        # Batching bounds the request without truncating candidate text; an outage or oversized record only affects its own batch or candidate.
        batches, oversized = self._build_batches(message)
        oversized_set = set(oversized)
        results: dict[int, JevSkillResult] = {
            index: JevSkillResult(name=skill.name, description=skill.description, source=skill.source, status=JevSkillStatus.UNAVAILABLE)
            for index, skill in enumerate(self.skills, start=_SKILL_INDEX_BASE)
            if index in oversized_set
        }
        selected_indices: set[int] = set()
        usages: list[JevUsage | None] = []
        for indices, request in batches:
            try:
                decision = await DecisionModelHelper(self.decision).arun(request)
            except VidbyteSdkError:
                for index in indices:
                    skill = self.skills[index - _SKILL_INDEX_BASE]
                    results[index] = JevSkillResult(name=skill.name, description=skill.description, source=skill.source, status=JevSkillStatus.UNAVAILABLE)
                continue
            usages.append(JevUsage.from_usage_payload(decision.usage or {}))
            for index in indices:
                skill = self.skills[index - _SKILL_INDEX_BASE]
                result = self._score_skill(index, skill, decision.answers)
                results[index] = result
                if result.status is JevSkillStatus.SELECTED:
                    selected_indices.add(index)
        ordered_results = tuple(results[index] for index in range(1, len(self.skills) + 1))
        selected = tuple(skill for index, skill in enumerate(self.skills, start=1) if index in selected_indices)
        self.response.skills(JevSkillsOutcome(results=ordered_results, usage=self._sum_usage(usages)))
        return self._append_selected(context, selected)

    def _build_batches(self, message: str) -> tuple[tuple[_SkillBatch, ...], tuple[int, ...]]:
        # @intent pack-without-truncating-candidates
        # Each trial serializes the same model/state/question shape as the provider body and keeps the original global question index.
        batches: list[_SkillBatch] = []
        oversized: list[int] = []
        current: list[tuple[int, SkillDocument]] = []
        for index, skill in enumerate(self.skills, start=1):
            candidate = (index, skill)
            _, fits_alone = self._build_batch(message, (candidate,))
            if not fits_alone:
                oversized.append(index)
                continue
            _, fits_current = self._build_batch(message, (*current, candidate))
            if current and not fits_current:
                completed, _ = self._build_batch(message, current)
                if completed is not None:
                    batches.append(completed)
                current = [candidate]
            else:
                current.append(candidate)
        if current:
            completed, _ = self._build_batch(message, current)
            if completed is not None:
                batches.append(completed)
        return tuple(batches), tuple(oversized)

    def _build_batch(self, message: str, indexed: Sequence[tuple[int, SkillDocument]]) -> tuple[_SkillBatch | None, bool]:
        # @intent byte-bounds-match-the-provider-json-shape
        # Counting the UTF-8 bytes of a standard JSON encoding keeps the estimate conservative without claiming provider byte limits.
        questions = tuple(JevSkillRelevanceQuestion(index).to_question() for index, _ in indexed)
        state = {
            "request": message,
            "skills": {
                JevSkillRelevanceQuestion(index).name: {
                    "name": skill.name,
                    "description": skill.description,
                    "source": skill.source,
                    "text": skill.text,
                }
                for index, skill in indexed
            },
        }
        question_payloads = {
            question.name: {
                "type": question.question_type.value,
                "instructions": JevJson.thaw(question.instructions),
                "criteria": {option.name: JevJson.thaw(option.description) for option in question.options},
            }
            for question in questions
        }
        wire = {"model": self.decision.model, "state": state, "questions": question_payloads}
        request_bytes = len(json.dumps(wire).encode("utf-8"))
        state_question_bytes = max(
            len(json.dumps({"state": state, "question": payload}).encode("utf-8"))
            for payload in question_payloads.values()
        )
        within_bounds = (
            1 <= len(questions) <= JEV_MAX_QUESTIONS
            and request_bytes <= _MAX_REQUEST_JSON_BYTES
            and state_question_bytes <= _MAX_STATE_AND_QUESTION_JSON_BYTES
        )
        if not within_bounds:
            return None, False
        return (tuple(index for index, _ in indexed), JevDecisionRequest(state=state, questions=questions)), True

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
    def _sum_usage(usages: Sequence[JevUsage | None]) -> JevUsage | None:
        # @intent batch-usage-is-counted-once
        # Successful batch usage is folded into one TypeSafe record, matching existing Jev alignment aggregation semantics.
        present = [usage for usage in usages if usage is not None]
        if not present:
            return None
        return JevUsage.from_usage_payload({
            "input_tokens": sum(usage.input_tokens or 0 for usage in present),
            "output_tokens": sum(usage.output_tokens or 0 for usage in present),
        })

    @staticmethod
    def _append_selected(context: BaseAgentContext, selected: tuple[SkillDocument, ...]) -> BaseAgentContext:
        # @intent preserve-baseline-and-append-selected-guidance
        # The selected source text is added only to the immutable replacement context for this run and is never copied into its response record.
        if not selected:
            return context
        text = _SKILL_SECTION + "\n\n---\n\n".join(skill.text for skill in selected)
        return replace(context, system_prompt=f"{context.system_prompt or ''}{text}")


__all__ = ["JevSkillsPreload"]
