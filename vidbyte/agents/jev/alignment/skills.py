"""FILE: vidbyte/agents/jev/alignment/skills.py

PURPOSE: Implements JevSkillsPreload, a JevAgentAlignment subclass that judges each configured skill description against the user's request, then materializes only selected candidate instructions for the current run. It does not retrieve remote sources.
ROLE IN CODEBASE: JevAgent constructs the subclass when JevAlignmentSettings.skills is non-empty; JevRuntime calls preload_skills after the preflight gate and injects the returned loaded bodies as current-run TextContextItems.
ARCHITECTURE NOTE: Selection uses the existing decision model configuration and fixed Jev question; source-independent inline/local text loading stays in skill_loader.py, while third-party retrieval adapters are separate PRs.
FUNCTION INVENTORY: JevSkillsPreload.preload_skills(message, candidates) -> JevSkillsPreloadBatch evaluates one candidate per Jev request and returns both the redacted result and selected run-local bodies. Covered by tests/test_jev_skill_preload.py.
COMMON MODIFICATION PATTERNS: Change candidate recognition in skill_question.py; change threshold or failure policy here; add source retrieval only in a dedicated adapter that produces JevSkillCandidate values.
WHAT NOT TO DO IN THIS FILE: (1) Do not add general-purpose decisions, caller-authored questions, or arbitrary callbacks. (2) Do not append skills to persistent system prompts or mutate JevAgentSettings. (3) Do not perform network retrieval or load full bodies before selection.
KNOWN EDGE CASES: Jev failures fail closed for skill injection while the main task continues; missing answers are treated as unavailable. Selected local files that fail to load are omitted individually, and their paths and contents are excluded from the public result.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/jev-skill-preloading.md and https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/asking-jev-questions/SKILL.md
TESTS: tests/test_jev_skill_preload.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from vidbyte.agents.jev.alignment.agent import JevAgentAlignment
from vidbyte.agents.jev.alignment.skill_loader import JevSkillContentLoader
from vidbyte.agents.jev.alignment.skill_question import skill_fit_question
from vidbyte.agents.jev.settings import JevSkillCandidate
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import JEV_NOUL_TRUE, JEV_NOUL_YES_THRESHOLD
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevLoadedSkill,
    JevQuestion,
    JevSkillsPreloadBatch,
    JevSkillsPreloadResult,
)
from vidbyte.lib.enums.jev import JevSkillsPreloadStatus
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse


class JevSkillsPreload(JevAgentAlignment):
    """Evaluate configured skill candidates before a JevAgent's main model run."""

    async def preload_skills(
        self, message: str, candidates: Sequence[JevSkillCandidate]
    ) -> JevSkillsPreloadBatch:
        """Select and load applicable candidate instructions without changing later runs."""
        if not candidates:
            return JevSkillsPreloadBatch(JevSkillsPreloadResult(JevSkillsPreloadStatus.NO_MATCH))
        try:
            runner = DecisionModelRunner(self.decision)
        except VidbyteSdkError:
            return _unavailable(candidates, "Jev skill relevance selection is unavailable; no skill instructions were added.")
        question = skill_fit_question()
        requests = tuple(_candidate_request(message, candidate, question) for candidate in candidates)
        outcomes = await asyncio.gather(*(runner.arun(request) for request in requests), return_exceptions=True)
        if any(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes):
            raise next(outcome for outcome in outcomes if isinstance(outcome, asyncio.CancelledError))
        if any(isinstance(outcome, Exception) for outcome in outcomes):
            return _unavailable(candidates, "Jev skill relevance selection is unavailable; no skill instructions were added.")

        responses = tuple(outcome for outcome in outcomes if isinstance(outcome, DecisionModelResponse))
        usage = _combined_usage(tuple(response.usage for response in responses))
        try:
            selected = tuple(
                candidate
                for candidate, response in zip(candidates, responses, strict=True)
                if response.answer(question.name).probabilities.get(JEV_NOUL_TRUE, 0.0) >= JEV_NOUL_YES_THRESHOLD
            )
        except (ConfigurationError, KeyError, TypeError, ValueError):
            return JevSkillsPreloadBatch(
                JevSkillsPreloadResult(
                    JevSkillsPreloadStatus.UNAVAILABLE,
                    unavailable=tuple(candidate.name for candidate in candidates),
                    input_tokens=_usage_count(usage, "input_tokens"),
                    output_tokens=_usage_count(usage, "output_tokens"),
                    detail="Jev returned an incomplete skill relevance result; no skill instructions were added.",
                )
            )

        loaded, unavailable = self._load_selected(selected)
        status = JevSkillsPreloadStatus.SELECTED if loaded else JevSkillsPreloadStatus.UNAVAILABLE if unavailable else JevSkillsPreloadStatus.NO_MATCH
        return JevSkillsPreloadBatch(
            JevSkillsPreloadResult(
                status=status,
                selected=tuple(skill.name for skill in loaded),
                unavailable=unavailable,
                input_tokens=_usage_count(usage, "input_tokens"),
                output_tokens=_usage_count(usage, "output_tokens"),
                detail="Selected skill instructions are run-local and are not retained by JevAgent." if loaded else None,
            ),
            loaded=loaded,
        )

    @staticmethod
    def _load_selected(candidates: Sequence[JevSkillCandidate]) -> tuple[tuple[JevLoadedSkill, ...], tuple[str, ...]]:
        loader = JevSkillContentLoader()
        loaded: list[JevLoadedSkill] = []
        unavailable: list[str] = []
        for candidate in candidates:
            try:
                loaded.append(JevLoadedSkill(candidate.name, loader.load(candidate)))
            except (VidbyteSdkError, OSError):
                unavailable.append(candidate.name)
        return tuple(loaded), tuple(unavailable)


def _candidate_request(message: str, candidate: JevSkillCandidate, question: JevQuestion) -> JevDecisionRequest:
    # The state contains the description only; selected instruction text is loaded after Jev answers.
    return JevDecisionRequest(
        state={"request": message, "skill_name": candidate.name, "skill_description": candidate.description},
        questions=(question,),
    )


def _combined_usage(usages: tuple[object, ...]) -> JevUsage | None:
    known = [parsed for usage in usages if usage and (parsed := JevUsage.from_usage_payload(usage)) is not None]
    if not known:
        return None
    input_tokens = [item.input_tokens for item in known if item.input_tokens is not None]
    output_tokens = [item.output_tokens for item in known if item.output_tokens is not None]
    payload = {
        "input_tokens": sum(input_tokens) if len(input_tokens) == len(known) else None,
        "output_tokens": sum(output_tokens) if len(output_tokens) == len(known) else None,
    }
    return JevUsage.from_usage_payload(payload)


def _unavailable(candidates: Sequence[JevSkillCandidate], detail: str) -> JevSkillsPreloadBatch:
    """Build a fail-closed result when Jev relevance decisions cannot be trusted."""
    return JevSkillsPreloadBatch(
        JevSkillsPreloadResult(
            JevSkillsPreloadStatus.UNAVAILABLE,
            unavailable=tuple(candidate.name for candidate in candidates),
            detail=detail,
        )
    )


def _usage_count(usage: JevUsage | None, field_name: str) -> int | None:
    value = None if usage is None else getattr(usage, field_name)
    return None if value is None else int(value)


__all__ = ["JevSkillsPreload"]
