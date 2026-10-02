"""FILE: vidbyte/agents/jev/alignment/skills.py

PURPOSE: Resolves explicit skill sources, selects relevant candidates for one JevAgent request, and appends only passing text bodies to that run's system prompt.
ROLE IN CODEBASE: JevAgent builds this preload only for nonempty `JevAlignmentSettings.skills`; JevRuntime invokes it after prompt and tool alignment and before run-state setup and the main loop.
ARCHITECTURE NOTE: The preload keeps one stable outcome per configured candidate, bounds indexed TypeSafe requests, and records metadata without storing skill text in JevAgent.response. Context replacement is immutable; runtime mutation cleanup remains JevRuntime's responsibility.
FUNCTION INVENTORY:
    JevSkillsPreload.__init__(skills, decision, threshold, response) -> None: stores the validated run-time inputs.
    JevSkillsPreload.run(message, context) -> BaseAgentContext: batches questions, records per-skill outcomes, and returns the skill-extended context.
    JevSkillsPreload._build_batches(message) -> tuple: greedily packs whole candidate records under local serialized-byte bounds and returns oversized indices separately.
    JevSkillsPreload._score_skill(index, skill, answers) -> JevSkillResult: independently scores one fixed-index answer.
    JevSkillsPreload._sum_usage(usages) -> JevUsage | None: adds available usage from successful batches once.
    JevSkillsPreload._append_selected(context, selected) -> BaseAgentContext: appends exact full texts to a replaced system prompt.
COMMON MODIFICATION PATTERNS: Resolve explicit sources at run time before building bounded relevance batches; preserve input positions and isolate expected source failures.
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
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_MAX_QUESTIONS
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevJson,
    JevSkillResult,
    JevSkillsOutcome,
)
from vidbyte.lib.dataclasses.skills import ClaudeSkillReference, SkillDocument, SkillSource
from vidbyte.lib.enums.jev import JevQuestionType, JevSkillStatus
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight.skills import JevSkillRelevanceQuestion
from vidbyte.providers.skills import SkillSourceError, SkillSourceResolver

_SKILL_SECTION = """

--- Caller-selected skill guidance for this request ---

"""
_SKILL_INDEX_BASE = 1
_MAX_REQUEST_JSON_BYTES = 60_000
_MAX_STATE_AND_QUESTION_JSON_BYTES = 30_000
_SkillBatch = tuple[tuple[int, ...], JevDecisionRequest]


_SOURCE_FAILURE_DETAIL = "Skill source could not be resolved."
_DUPLICATE_SOURCE_DETAIL = "Resolved skill name is ambiguous."
_DECISION_FAILURE_DETAIL = "Skill relevance could not be evaluated."
_UNSUPPORTED_NATIVE_DETAIL = "Native Claude skills require an Anthropic model."
_OVERSIZED_DETAIL = "Skill candidate exceeds Jev's request size limit."
_NATIVE_CAP_DETAIL = "Anthropic supports at most 20 skills per request."


class JevSkillsPreload(JevPreload):
    """Selects relevant documents once for one run and appends their exact bodies."""

    def __init__(self, *, skills: tuple[SkillDocument | SkillSource, ...], decision: DecisionModelConfig, threshold: float, response: JevResponse, provider: ModelProvider = ModelProvider.ANTHROPIC, claude_api_key: str | None = None, source_resolver: SkillSourceResolver | None = None) -> None:
        # @intent validated-settings-cross-the-preload-boundary
        # JevAgent passes normalized candidates, a validated decision policy, the response writer, and a closed resolver with no construction-time I/O.
        self.skills = skills
        self.decision = decision
        self.threshold = threshold
        self.response = response
        self.provider = provider
        self.source_resolver = source_resolver or SkillSourceResolver(claude_api_key=claude_api_key)

    async def run(self, message: str, context: BaseAgentContext) -> BaseAgentContext:
        # @intent each-candidate-has-an-independent-result
        # Batching bounds the request without truncating candidate text; an outage or oversized record only affects its own batch or candidate.
        available, results = await self._resolve_candidates()
        indexed_skills = tuple(sorted(available.items()))
        batches, oversized = self._build_batches(message, indexed_skills)
        for index in oversized:
            skill = available[index]
            results[index] = self._unavailable_result(index, skill, _OVERSIZED_DETAIL)
        selected_indices: set[int] = set()
        usages: list[JevUsage | None] = []
        for indices, request in batches:
            try:
                decision = await DecisionModelHelper(self.decision).arun(request)
            except VidbyteSdkError:
                for index in indices:
                    skill = available[index]
                    results[index] = self._unavailable_result(index, skill, _DECISION_FAILURE_DETAIL)
                continue
            usages.append(JevUsage.from_usage_payload(decision.usage or {}))
            for index in indices:
                skill = available[index]
                result = self._score_skill(index, skill, decision.answers)
                results[index] = result
                if result.status is JevSkillStatus.SELECTED:
                    selected_indices.add(index)
        ordered_results = tuple(results[index] for index in range(1, len(self.skills) + 1))
        selected_text: list[SkillDocument] = []
        native_refs: list[ClaudeSkillReference] = []
        for index in sorted(selected_indices):
            skill = available[index]
            if skill.claude_reference is None:
                selected_text.append(skill)
                continue
            if len(native_refs) >= 20:
                results[index] = self._unavailable_result(index, self.skills[index - _SKILL_INDEX_BASE], _NATIVE_CAP_DETAIL, resolved=skill)
                continue
            native_refs.append(skill.claude_reference)
        ordered_results = tuple(results[index] for index in range(1, len(self.skills) + 1))
        self.response.skills(JevSkillsOutcome(results=ordered_results, usage=self._sum_usage(usages), claude_skills=tuple(native_refs)))
        return self._append_selected(context, tuple(selected_text))

    async def _resolve_candidates(self) -> tuple[dict[int, SkillDocument], dict[int, JevSkillResult]]:
        # Resolves sources at run time and converts only expected per-source failures into indexed outcomes.
        available: dict[int, SkillDocument] = {}
        results: dict[int, JevSkillResult] = {}
        for index, candidate in enumerate(self.skills, start=_SKILL_INDEX_BASE):
            if isinstance(candidate, SkillSource) and candidate.kind is SkillSourceKind.CLAUDE and self.provider is not ModelProvider.ANTHROPIC:
                results[index] = self._unavailable_result(index, candidate, _UNSUPPORTED_NATIVE_DETAIL)
                continue
            if isinstance(candidate, SkillSource):
                try:
                    document = await self.source_resolver.resolve(candidate)
                except SkillSourceError:
                    results[index] = self._unavailable_result(index, candidate, _SOURCE_FAILURE_DETAIL)
                    continue
            else:
                document = candidate
            if document.claude_reference is not None and self.provider is not ModelProvider.ANTHROPIC:
                results[index] = self._unavailable_result(index, candidate, _UNSUPPORTED_NATIVE_DETAIL, resolved=document)
                continue
            available[index] = document
        names: dict[str, list[int]] = {}
        for index, skill in available.items():
            names.setdefault(skill.name, []).append(index)
        for indices in names.values():
            if len(indices) < 2:
                continue
            for index in indices:
                results[index] = self._unavailable_result(index, self.skills[index - _SKILL_INDEX_BASE], _DUPLICATE_SOURCE_DETAIL, resolved=available[index])
                available.pop(index)
        return available, results

    def _unavailable_result(self, index: int, candidate: SkillDocument | SkillSource, detail: str, *, resolved: SkillDocument | None = None) -> JevSkillResult:
        # Builds a safe per-index unavailable record without copying source locations, exception text, or credentials.
        document = resolved or (candidate if isinstance(candidate, SkillDocument) else None)
        if document is not None:
            name, description, source = document.name, document.description, document.source
        else:
            name = candidate.skill_name or f"skill_{index}"
            description = "Skill source candidate."
            source = candidate.kind.value if isinstance(candidate.kind, SkillSourceKind) else None
        return JevSkillResult(name=name, description=description, source=source, status=JevSkillStatus.UNAVAILABLE, detail=detail)

    def _build_batches(self, message: str, indexed_skills: Sequence[tuple[int, SkillDocument]] | None = None) -> tuple[tuple[_SkillBatch, ...], tuple[int, ...]]:
        # @intent pack-without-truncating-candidates
        # Each trial serializes the same model/state/question shape as the provider body and keeps the original global question index.
        indexed = tuple(indexed_skills) if indexed_skills is not None else tuple(
            (index, skill)
            for index, skill in enumerate(self.skills, start=_SKILL_INDEX_BASE)
            if isinstance(skill, SkillDocument) and (skill.text is not None or skill.claude_reference is not None)
        )
        batches: list[_SkillBatch] = []
        oversized: list[int] = []
        current: list[tuple[int, SkillDocument]] = []
        for index, skill in indexed:
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
        questions = tuple(JevSkillRelevanceQuestion(index, metadata_only=skill.claude_reference is not None).to_question() for index, skill in indexed)
        skills_state = {}
        for index, skill in indexed:
            candidate_state = {
                "kind": "claude_native_metadata" if skill.claude_reference is not None else "text",
                "name": skill.name,
                "description": skill.description,
                "source": skill.source,
            }
            if skill.text is not None:
                candidate_state["text"] = skill.text
            skills_state[JevSkillRelevanceQuestion(index).name] = candidate_state
        state = {
            "request": message,
            "skills": skills_state,
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
            return JevSkillResult(name=skill.name, description=skill.description, source=skill.source, status=JevSkillStatus.UNAVAILABLE, detail=_DECISION_FAILURE_DETAIL)
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
        text = _SKILL_SECTION + "\n\n---\n\n".join(skill.text for skill in selected if skill.text is not None)
        return replace(context, system_prompt=f"{context.system_prompt or ''}{text}")


__all__ = ["JevSkillsPreload"]
