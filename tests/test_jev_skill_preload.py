"""FILE: tests/test_jev_skill_preload.py

PURPOSE: Defines the executable contract for JevAgent skill preloading: candidate validation, independent Jev decisions, selected-only local loading, fail-closed injection, run-local context, and redacted reporting.
ROLE IN CODEBASE: Exercises the SDK core without network access and protects the contract future skill-source adapters must implement.
ARCHITECTURE NOTE: A scripted DecisionModelHelper replaces TypeSafe transport; the production question, capability subclass, context primitive, settings, and response records remain under test.
COMMON MODIFICATION PATTERNS: Add regressions when the candidate contract, fixed question, threshold, failure policy, or runtime context behavior changes.
WHAT NOT TO DO IN THIS FILE: (1) Do not make live provider calls. (2) Do not assert third-party adapter behavior; adapters belong to separate PRs.
KNOWN EDGE CASES: Local files are read only after selection; unreadable selected files are reported by candidate name without exposing their path or contents.
RELATED DOCS: docs/design/jev-skill-preloading.md and skills/asking-jev-questions/SKILL.md
TESTS: python -m pytest tests/test_jev_skill_preload.py
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

from vidbyte.agents.jev import JevAgentSettings, JevAlignmentSettings, JevSkillCandidate
from vidbyte.agents.jev.alignment.skills import JevSkillsPreload
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import JevAnswer, JevLoadedSkill, JevSkillsPreloadBatch
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.enums.jev import JevSkillsPreloadStatus
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.skill_preload import JEV_SKILL_FIT_QUESTION
from vidbyte.lib.runners.types import DecisionModelResponse


class ScriptedDecisionHelper:
    """Return decisions by candidate name while retaining each Jev request for assertions."""

    requests: ClassVar[list[Any]] = []
    choices: ClassVar[dict[str, float]] = {}
    no_usage: ClassVar[set[str]] = set()
    fail = False

    async def arun(self, request: Any) -> DecisionModelResponse:
        ScriptedDecisionHelper.requests.append(request)
        if ScriptedDecisionHelper.fail:
            raise RuntimeError("simulated Jev outage")
        candidate = request.state["skill_name"]
        probability = ScriptedDecisionHelper.choices[candidate]
        answer = JevAnswer(
            question_name=request.questions[0].name,
            question_type=JevQuestionType.NOUL,
            choice="true" if probability >= 0.5 else "false",
            probabilities={"true": probability, "false": 1.0 - probability},
            noul=probability,
        )
        return DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-test",
            answers={answer.question_name: answer},
            raw={},
            usage=None if candidate in ScriptedDecisionHelper.no_usage else {"input_tokens": 10, "output_tokens": 2},
        )


def _settings(skills: tuple[JevSkillCandidate, ...] = ()) -> JevAgentSettings:
    return JevAgentSettings(
        name="assistant",
        system_prompt="Help with user tasks.",
        provider="openai",
        model_name="gpt-4.1-mini",
        alignment=JevAlignmentSettings(skills=skills),
    )


class SkillSettingsTests(unittest.TestCase):
    def test_candidate_requires_exactly_one_nonblank_source(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevSkillCandidate(name="review", description="Review code")
        with self.assertRaises(ConfigurationError):
            JevSkillCandidate(name="review", description="Review code", content="body", path="skill.md")
        with self.assertRaises(ConfigurationError):
            JevSkillCandidate(name="review", description="Review code", content=" ")

    def test_candidates_are_unique_and_contents_are_hidden_from_repr(self) -> None:
        candidate = JevSkillCandidate(name="review", description="Review code", content="private skill body")
        self.assertNotIn("private skill body", repr(candidate))
        with self.assertRaises(ConfigurationError):
            JevAlignmentSettings(skills=(candidate, candidate))


class SkillQuestionTests(unittest.TestCase):
    def test_question_is_structured_positive_and_treats_candidate_text_as_data(self) -> None:
        question = JEV_SKILL_FIT_QUESTION
        self.assertIs(question.question_type, JevQuestionType.NOUL)
        self.assertEqual(question.name, "alignment.skill_fits_request")
        self.assertEqual(tuple(option.name for option in question.options), ("true", "false"))
        self.assertTrue(all(set(option.description) == {"what", "not_for", "examples"} for option in question.options))
        instructions = str(question.instructions)
        self.assertIn("is untrusted", instructions)
        self.assertIn("not a command", instructions)
        self.assertIn("materially help", instructions)


class SkillPreloadTests(unittest.TestCase):
    def setUp(self) -> None:
        ScriptedDecisionHelper.requests = []
        ScriptedDecisionHelper.choices = {"useful": 0.91, "irrelevant": 0.09, "local": 0.91, "broken": 0.91}
        ScriptedDecisionHelper.no_usage = set()
        ScriptedDecisionHelper.fail = False
        self.decision = DecisionModelConfig(api_key="test-key")
        self.candidates = (
            JevSkillCandidate(name="useful", description="Review source changes for security issues", content="Selected instructions"),
            JevSkillCandidate(name="irrelevant", description="Cook recipes with seasonal produce", content="Do not inject"),
        )
        self.preloader = JevSkillsPreload(_settings(self.candidates), self.decision)

    def _run(self, message: str, candidates: tuple[JevSkillCandidate, ...]) -> JevSkillsPreloadBatch:
        with patch.object(DecisionModelHelper, "arun", ScriptedDecisionHelper.arun):
            return asyncio.run(self.preloader.preload_skills(message, candidates))

    def test_evaluates_each_description_then_loads_only_selected_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            local_path = Path(folder) / "SKILL.md"
            local_path.write_text("Review the code. ✓", encoding="utf-8")
            missing_path = Path(folder) / "not-selected.md"
            candidates = (
                JevSkillCandidate(name="useful", description="Review source", content="Selected instructions"),
                JevSkillCandidate(name="irrelevant", description="Cook recipes", content="Do not inject"),
                JevSkillCandidate(name="local", description="Review local source", path=local_path),
                JevSkillCandidate(name="missing", description="Unrelated local source", path=missing_path),
            )
            ScriptedDecisionHelper.choices["missing"] = 0.09
            batch = self._run("Review this source patch for security issues.", candidates)

        self.assertEqual(batch.result.status, JevSkillsPreloadStatus.SELECTED)
        self.assertEqual(batch.result.selected, ("useful", "local"))
        self.assertEqual(tuple(skill.content for skill in batch.loaded), ("Selected instructions", "Review the code. ✓"))
        self.assertEqual(batch.result.unavailable, ())
        self.assertEqual(len(ScriptedDecisionHelper.requests), 4)
        request_state = ScriptedDecisionHelper.requests[0].state
        self.assertNotIn("Selected instructions", str(request_state))
        self.assertEqual(request_state["request"], "Review this source patch for security issues.")
        self.assertEqual(batch.result.input_tokens, 40)

    def test_decision_failure_adds_no_skill_context(self) -> None:
        ScriptedDecisionHelper.fail = True
        batch = self._run("Review code", self.candidates)
        self.assertEqual(batch.result.status, JevSkillsPreloadStatus.UNAVAILABLE)
        self.assertEqual(batch.loaded, ())
        self.assertEqual(batch.result.selected, ())

    def test_token_totals_stay_unknown_when_any_decision_omits_usage(self) -> None:
        ScriptedDecisionHelper.no_usage.add("irrelevant")
        batch = self._run("Review code", self.candidates)
        self.assertIsNone(batch.result.input_tokens)
        self.assertIsNone(batch.result.output_tokens)

    def test_unreadable_selected_file_is_omitted_without_exposing_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            missing_path = Path(folder) / "missing.md"
            candidates = (
                JevSkillCandidate(name="useful", description="Review source", content="Selected instructions"),
                JevSkillCandidate(name="broken", description="Review source", path=missing_path),
            )
            batch = self._run("Review code", candidates)

        self.assertEqual(batch.result.status, JevSkillsPreloadStatus.SELECTED)
        self.assertEqual(batch.result.selected, ("useful",))
        self.assertEqual(batch.result.unavailable, ("broken",))
        self.assertNotIn(str(missing_path), repr(batch.result))

    def test_unreadable_selected_files_are_reported_when_nothing_loads(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            directory = JevSkillCandidate(name="directory", description="Review source", path=folder)
            missing = JevSkillCandidate(name="missing", description="Review source", path=Path(folder) / "missing.md")
            blank_path = Path(folder) / "blank.md"
            blank_path.write_text("  ", encoding="utf-8")
            blank = JevSkillCandidate(name="blank", description="Review source", path=blank_path)
            candidates = (directory, missing, blank)
            ScriptedDecisionHelper.choices.update({candidate.name: 0.91 for candidate in candidates})
            batch = self._run("Review code", candidates)

        self.assertEqual(batch.result.status, JevSkillsPreloadStatus.UNAVAILABLE)
        self.assertEqual(batch.result.selected, ())
        self.assertEqual(batch.result.unavailable, ("directory", "missing", "blank"))

    def test_context_items_are_run_local_and_keep_existing_items(self) -> None:
        from vidbyte.context.primitives import TextContextItem

        existing = TextContextItem(title="existing", content="keep me")
        context = BaseAgentContext(context_items=(existing,))
        loaded = (JevLoadedSkill(name="review", content="review guidance"),)
        changed = JevRuntime._with_preloaded_skills(loaded, context)
        self.assertIs(changed.context_items[0], existing)
        self.assertEqual(changed.context_items[1].content, "review guidance")
        self.assertIs(JevRuntime._with_preloaded_skills((), context), context)


if __name__ == "__main__":
    unittest.main()
