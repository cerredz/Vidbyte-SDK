"""FILE: vidbyte/agents/jev/alignment/skills.py

PURPOSE: Implements JevSkillsPreload, the single JevAgent alignment capability that selects and loads relevant skill instructions for one run.
ROLE IN CODEBASE: JevAgent constructs it when JevAlignmentSettings.skills is non-empty; JevRuntime runs it after preflight and injects its selected bodies into the current context.
ARCHITECTURE NOTE: This subclass owns candidate requests, Jev calls, answer handling, source loading, usage, and outcomes. The fixed question definition is shared in vidbyte/lib/jev/skill_preload.py.
COMMON MODIFICATION PATTERNS: Add a private helper here when selection needs another deterministic step; keep remote retrieval in a separate adapter that produces JevSkillCandidate values.
WHAT NOT TO DO IN THIS FILE: (1) Do not expose caller-authored questions or selection callbacks. (2) Do not mutate shared prompts or settings. (3) Do not load full candidate bodies before Jev selects them.
KNOWN EDGE CASES: Any failed or malformed Jev decision fails closed for injection. A selected local file that cannot be read is omitted by name, without exposing its path or partial contents.
RELATED DOCS: docs/design/jev-skill-preloading.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_skill_preload.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from vidbyte.agents.jev.alignment.agent import JevAgentAlignment
from vidbyte.agents.jev.settings import JevAgentSettings, JevSkillCandidate
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_NOUL_YES_THRESHOLD
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevLoadedSkill,
    JevSkillsPreloadBatch,
    JevSkillsPreloadResult,
)
from vidbyte.lib.enums.jev import JevSkillsPreloadStatus
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.skill_preload import (
    JEV_SKILL_FIT_QUESTION,
    JEV_SKILL_FIT_QUESTION_NAME,
)
from vidbyte.lib.runners.types import DecisionModelResponse


class JevSkillsPreload(JevAgentAlignment):
    """Select relevant skill candidates and materialize their bodies for one JevAgent run."""

    def __init__(self, settings: JevAgentSettings, decision: DecisionModelConfig | None = None) -> None:
        super().__init__(settings, decision)
        self._decision_model = DecisionModelHelper(self.decision)

    async def preload_skills(
        self, message: str, candidates: Sequence[JevSkillCandidate]
    ) -> JevSkillsPreloadBatch:
        """Evaluate candidates independently, then load only selected instructions."""
        if not candidates:
            return JevSkillsPreloadBatch(JevSkillsPreloadResult(JevSkillsPreloadStatus.NO_MATCH))

        # Send one item per request so Jev judges each candidate against the same original request.
        requests = self._candidate_requests(message, candidates)
        responses = await self._decision_responses(requests)
        if responses is None:
            return self._unavailable(candidates, "Jev skill relevance selection is unavailable; no skill instructions were added.")

        # Do not load or inject any body unless every candidate decision is present and valid.
        usage = self._combined_usage(responses)
        selected = self._selected_candidates(candidates, responses)
        if selected is None:
            return self._unavailable(
                candidates,
                "Jev returned an incomplete skill relevance result; no skill instructions were added.",
                usage=usage,
            )
        return self._materialize_selected(selected, usage)

    @staticmethod
    def _candidate_requests(message: str, candidates: Sequence[JevSkillCandidate]) -> tuple[JevDecisionRequest, ...]:
        """Build one request per candidate with its description, never its full instruction body."""
        return tuple(
            JevDecisionRequest(
                state={"request": message, "skill_name": candidate.name, "skill_description": candidate.description},
                questions=(JEV_SKILL_FIT_QUESTION,),
            )
            for candidate in candidates
        )

    async def _decision_responses(
        self, requests: Sequence[JevDecisionRequest]
    ) -> tuple[DecisionModelResponse, ...] | None:
        """Run all candidate checks and reject the batch if any answer is missing or fails."""
        outcomes = await asyncio.gather(
            *(self._decision_model.arun(request) for request in requests),
            return_exceptions=True,
        )
        for outcome in outcomes:
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
        if any(isinstance(outcome, Exception) for outcome in outcomes):
            return None
        responses = tuple(outcome for outcome in outcomes if isinstance(outcome, DecisionModelResponse))
        return responses if len(responses) == len(requests) else None

    @staticmethod
    def _selected_candidates(
        candidates: Sequence[JevSkillCandidate], responses: Sequence[DecisionModelResponse]
    ) -> tuple[JevSkillCandidate, ...] | None:
        """Threshold each named noul answer and return None when any result cannot be scored."""
        selected: list[JevSkillCandidate] = []
        try:
            for candidate, response in zip(candidates, responses, strict=True):
                score = DecisionModelHelper.score_noul(
                    response.answers,
                    (JEV_SKILL_FIT_QUESTION_NAME,),
                    JEV_NOUL_YES_THRESHOLD,
                )
                if score is None:
                    return None
                if score.passed:
                    selected.append(candidate)
        except (ConfigurationError, KeyError, TypeError, ValueError):
            return None
        return tuple(selected)

    def _materialize_selected(
        self, candidates: Sequence[JevSkillCandidate], usage: JevUsage | None
    ) -> JevSkillsPreloadBatch:
        """Load selected bodies and build the redacted public outcome."""
        loaded, unavailable = self._load_selected(candidates)
        if loaded:
            status = JevSkillsPreloadStatus.SELECTED
            detail = "Selected skill instructions are run-local and are not retained by JevAgent."
        elif unavailable:
            status = JevSkillsPreloadStatus.UNAVAILABLE
            detail = None
        else:
            status = JevSkillsPreloadStatus.NO_MATCH
            detail = None
        return JevSkillsPreloadBatch(
            JevSkillsPreloadResult(
                status=status,
                selected=tuple(skill.name for skill in loaded),
                unavailable=unavailable,
                input_tokens=self._usage_count(usage, "input_tokens"),
                output_tokens=self._usage_count(usage, "output_tokens"),
                detail=detail,
            ),
            loaded=loaded,
        )

    def _load_selected(
        self, candidates: Sequence[JevSkillCandidate]
    ) -> tuple[tuple[JevLoadedSkill, ...], tuple[str, ...]]:
        """Materialize selected candidates independently so one bad local file does not block the others."""
        loaded: list[JevLoadedSkill] = []
        unavailable: list[str] = []
        for candidate in candidates:
            try:
                loaded.append(JevLoadedSkill(candidate.name, self._load_content(candidate)))
            except ConfigurationError:
                # Keep the failure observable by name only; local paths and partial bodies stay private.
                unavailable.append(candidate.name)
        return tuple(loaded), tuple(unavailable)

    @staticmethod
    def _load_content(candidate: JevSkillCandidate) -> str:
        """Return inline text or read one explicit local UTF-8 file after selection."""
        if candidate.content is not None:
            return candidate.content
        path = Path(candidate.path or "").expanduser()
        try:
            if not path.is_file():
                raise ConfigurationError(f"Selected Jev skill {candidate.name!r} must point to a regular file.")
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ConfigurationError(f"Could not read selected Jev skill {candidate.name!r} as UTF-8 text.") from exc
        if not content.strip():
            raise ConfigurationError(f"Selected Jev skill {candidate.name!r} contains no instructions.")
        return content

    @staticmethod
    def _combined_usage(responses: Sequence[DecisionModelResponse]) -> JevUsage | None:
        """Sum known decision usage, preserving a missing token count instead of inventing one."""
        parsed = tuple(JevUsage.from_usage_payload(response.usage or {}) for response in responses)
        if not any(item is not None for item in parsed):
            return None
        input_tokens = [item.input_tokens for item in parsed if item is not None and item.input_tokens is not None]
        output_tokens = [item.output_tokens for item in parsed if item is not None and item.output_tokens is not None]
        payload = {
            "input_tokens": sum(input_tokens) if len(input_tokens) == len(responses) else None,
            "output_tokens": sum(output_tokens) if len(output_tokens) == len(responses) else None,
        }
        return JevUsage.from_usage_payload(payload)

    @staticmethod
    def _usage_count(usage: JevUsage | None, field_name: str) -> int | None:
        """Return a token count as a built-in int for the public result record."""
        value = None if usage is None else getattr(usage, field_name)
        return None if value is None else int(value)

    def _unavailable(
        self, candidates: Sequence[JevSkillCandidate], detail: str, *, usage: JevUsage | None = None
    ) -> JevSkillsPreloadBatch:
        """Build a fail-closed result that names unavailable candidates without exposing their sources."""
        return JevSkillsPreloadBatch(
            JevSkillsPreloadResult(
                status=JevSkillsPreloadStatus.UNAVAILABLE,
                unavailable=tuple(candidate.name for candidate in candidates),
                input_tokens=self._usage_count(usage, "input_tokens"),
                output_tokens=self._usage_count(usage, "output_tokens"),
                detail=detail,
            )
        )


__all__ = ["JevSkillsPreload"]
