"""FILE: tests/test_jev_skill_preload.py

PURPOSE: Verifies validated skill settings, fixed relevance questions, bounded request batching, result isolation, and runtime prompt cleanup.
ROLE IN CODEBASE: Covers docs/design/jev-skills-preload.md and tests/features/jev_skills_preload/FEATURE.md without contacting TypeSafe or a generative provider.
ARCHITECTURE NOTE: Scripted decision and generative runners replace only external model boundaries; production settings, preload batching, response writing, and JevRuntime ordering remain active.
COMMON MODIFICATION PATTERNS: Add contract tests for new status, batching, serialization, and cleanup behavior; keep candidate text out of response assertions except to prove it is absent.
KNOWN EDGE CASES: tiktoken is optional in the dev environment, so only the token-floor check is skipped when unavailable. No test sends a live request.
RELATED DOCS: docs/design/jev-skills-preload.md, tests/features/jev_skills_preload/FEATURE.md, and skills/jev-agent/SKILL.md.
TESTS: `python scripts/test-jev-skills-preload.py`.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent, JevAgentSettings, JevRuntimeSettings
from vidbyte import JevSkillStatus as RootJevSkillStatus
from vidbyte import SkillDocument as RootSkillDocument
from vidbyte.agents.jev.alignment.skills import JevSkillsPreload
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAlignmentSettings, JevContinualSettings
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_SKILLS_MAX_REQUEST_JSON_BYTES,
    JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevJson,
    JevQuestion,
)
from vidbyte.lib.dataclasses.skills import SkillDocument
from vidbyte.lib.enums import (
    JevDoneCheck,
    JevQuestionType,
    JevSkillStatus,
    ModelProvider,
)
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.preflight import skills as skill_question_module
from vidbyte.lib.jev.preflight.skills import JevSkillRelevanceQuestion
from vidbyte.lib.runners.types import DecisionModelResponse, TextModelResponse

_HELPER_PATH = "vidbyte.agents.jev.alignment.skills.DecisionModelHelper"


class ScriptedDecisionRunner:
    """Records bounded request batches and returns indexed answers or scripted failures."""

    def __init__(self, *, probabilities: Mapping[int, float] | None = None, per_call: Sequence[Mapping[int, float]] = (), missing: frozenset[int] = frozenset(), fail_calls: frozenset[int] = frozenset(), unreported_usage_calls: frozenset[int] = frozenset()) -> None:
        # Keeps outcomes deterministic while allowing each batch and call to differ.
        self.probabilities = probabilities or {}
        self.per_call = tuple(per_call)
        self.missing = missing
        self.fail_calls = fail_calls
        self.unreported_usage_calls = unreported_usage_calls
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Stores the exact production request before returning its scripted call outcome.
        self.requests.append(request)
        call_number = len(self.requests)
        if call_number in self.fail_calls:
            raise ProviderRequestError("scripted TypeSafe failure", provider="typesafe")
        probabilities = self.per_call[call_number - 1] if call_number <= len(self.per_call) else self.probabilities
        answers = {
            question.name: _answer(question.name, probabilities.get(_index(question.name), 0.9))
            for question in request.questions
            if _index(question.name) not in self.missing
        }
        return DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-1.13.0",
            answers=answers,
            raw={},
            usage=None if call_number in self.unreported_usage_calls else {"input_tokens": call_number * 10, "output_tokens": call_number},
        )


class CapturingGenerativeRunner:
    """Records the actual system option used by the main generative call."""

    def __init__(self, events: list[str] | None = None) -> None:
        # Keeps every system prompt to verify per-run context isolation.
        self.systems: list[str | None] = []
        self.events = events

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        # Returns a deterministic text result after recording the provider-visible system prompt.
        self.systems.append(kwargs.get("system"))
        if self.events is not None:
            self.events.append("main_loop")
        return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", text="completed", raw={}, usage={"input_tokens": 100, "output_tokens": 20})


def _answer(name: str, probability: float) -> JevAnswer:
    # Builds a normalized noul answer with matching choice and probability fields.
    return JevAnswer(
        question_name=name,
        question_type=JevQuestionType.NOUL,
        choice="true" if probability >= 0.5 else "false",
        probabilities={"true": probability, "false": 1.0 - probability},
        noul=probability,
    )


def _index(question_name: str) -> int:
    # Recovers only the generated integer suffix used by the fake model.
    return int(question_name.rsplit("_", maxsplit=1)[1])


def _helper_class(scripted: ScriptedDecisionRunner) -> type:
    # Replaces transport construction while leaving the canonical noul scorer unchanged.
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedDecisionRunner:
            return scripted

    return ScriptedHelper


def _skills(count: int) -> tuple[SkillDocument, ...]:
    # Builds ordered documents with individually recognizable full bodies.
    return tuple(SkillDocument(name=f"skill_{index}", description=f"description {index}", text=f"FULL BODY {index}", source=f"caller://{index}") for index in range(1, count + 1))


def _preloader(skills: tuple[SkillDocument, ...], response: JevResponse | None = None) -> JevSkillsPreload:
    # Builds the internal preload through its normal configuration boundary.
    return JevSkillsPreload(skills=skills, decision=DecisionModelConfig(api_key="test-key"), threshold=0.5, response=response or JevResponse())


def _agent(skills: tuple[SkillDocument | str, ...] = (), *, continual: JevContinualSettings | None = None) -> JevAgent:
    # Builds a main agent with no gate calls so each integration test can focus on runtime skill behavior.
    settings = JevAgentSettings(
        name="jev-skills-test",
        system_prompt="Agent base prompt.",
        provider=ModelProvider.OPENAI,
        model_name="gpt-4.1-mini",
        alignment=JevAlignmentSettings(skills=skills),
    )
    return JevAgent(settings, JevRuntimeSettings(preflight=(), continual=continual or JevContinualSettings()))


class SkillDocumentSettingsTests(unittest.TestCase):
    """Pins exact-text normalization, duplicate checks, threshold validation, and public exports."""

    def test_document_preserves_exact_text_and_public_exports(self) -> None:
        # [Hidden Assumption] leading whitespace and source provenance survive unchanged at SDK import paths.
        document = SkillDocument(name="review", description="Review changes", text="  exact\nbody  ", source="caller://review")
        self.assertEqual(document.text, "  exact\nbody  ")
        self.assertIs(RootSkillDocument, SkillDocument)
        self.assertIs(RootJevSkillStatus, JevSkillStatus)

    def test_inline_strings_receive_stable_names_without_text_rewriting(self) -> None:
        # [Silent Failure] strings are normalized once, in order, without losing their original bodies.
        from vidbyte.agents.jev.settings import JevAlignmentSettings

        normalized = JevAlignmentSettings(skills=(" first ", "second\n" )).skills
        self.assertEqual(tuple(item.name for item in normalized), ("inline_skill_1", "inline_skill_2"))
        self.assertEqual(tuple(item.text for item in normalized), (" first ", "second\n"))
        self.assertEqual(tuple(item.source for item in normalized), ("inline", "inline"))

    def test_rejects_duplicate_names_and_invalid_documents(self) -> None:
        # [Edge Case] duplicate explicit names or collisions with normalized inline names are ambiguous to callers.
        from vidbyte.agents.jev.settings import JevAlignmentSettings

        duplicate = SkillDocument(name="same", description="first", text="one")
        other = SkillDocument(name="same", description="second", text="two")
        for skills in ((duplicate, other), ("inline", SkillDocument(name="inline_skill_1", description="named", text="body"))):
            with self.subTest(skills=skills), self.assertRaises(ConfigurationError):
                JevAlignmentSettings(skills=skills)
        with self.assertRaises(ConfigurationError):
            SkillDocument(name=" ", description="desc", text="body")

    def test_skill_threshold_accepts_endpoints_and_rejects_invalid_values(self) -> None:
        # [Edge Case] the calibrated cutoff is a probability and bool is not accepted as a numeric shortcut.
        self.assertEqual(JevRuntimeSettings(preflight=(), skills_threshold=0).skills_threshold, 0.0)
        self.assertEqual(JevRuntimeSettings(preflight=(), skills_threshold=1).skills_threshold, 1.0)
        for value in (-0.1, 1.1, True, float("nan"), float("inf"), "0.5"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                JevRuntimeSettings(preflight=(), skills_threshold=value)


class SkillQuestionTests(unittest.TestCase):
    """Checks the fixed indexed rubric, single-literal house style, and its minimum reasoning length."""

    def test_dynamic_question_uses_only_its_fixed_index_and_one_string_per_rule_section(self) -> None:
        # [Hidden Failure] caller metadata can remain state evidence but cannot shape trusted question prose.
        question = JevSkillRelevanceQuestion(7).to_question()
        self.assertEqual(question.name, "skills.skill_7")
        self.assertIs(question.question_type, JevQuestionType.NOUL)
        self.assertEqual(len(skill_question_module._DEFINITIONS), 1)
        self.assertEqual(len(skill_question_module._RULES), 1)
        self.assertNotIn("UNIQUE_CALLER_NAME", question.instructions)
        self.assertNotIn("UNIQUE_CALLER_BODY", question.instructions)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_question_carries_at_least_two_thousand_meaningful_tokens(self) -> None:
        # [Silent Failure] the relevance rubric has enough instruction and boundary examples to support the classification.
        import tiktoken

        question = JevSkillRelevanceQuestion(1).to_question()
        parts = [question.instructions]
        parts.extend(json.dumps(JevJson.thaw(option.description), ensure_ascii=False) for option in question.options)
        self.assertGreaterEqual(len(tiktoken.get_encoding("cl100k_base").encode("\n".join(parts))), 2_000)


class SkillsBatchTests(unittest.IsolatedAsyncioTestCase):
    """Verifies complete, stable, bounded batches and independent relevance outcomes."""

    async def test_small_collection_keeps_full_candidate_records_in_one_request(self) -> None:
        # [Hidden Assumption] one ordinary small collection shares a request, with user data confined to indexed state.
        documents = (
            SkillDocument(name="UNIQUE_CALLER_NAME", description="UNIQUE_CALLER_DESCRIPTION", text="UNIQUE_CALLER_BODY", source="caller://private"),
            SkillDocument(name="another", description="Other guidance", text="OTHER_BODY"),
        )
        preload = _preloader(documents)
        scripted = ScriptedDecisionRunner(probabilities={1: 0.9, 2: 0.2})
        original = BaseAgentContext(system_prompt="Base prompt with suffix.", history=("history",))
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            result = await preload.run("Review this patch", original)

        self.assertEqual(len(scripted.requests), 1)
        request = scripted.requests[0]
        records = request.state["skills"]
        self.assertEqual(tuple(records), ("skills.skill_1", "skills.skill_2"))
        self.assertEqual(records["skills.skill_1"]["text"], documents[0].text)
        self.assertIn("UNIQUE_CALLER_BODY", str(records["skills.skill_1"]))
        self.assertNotIn(documents[0].name, request.questions[0].instructions)
        self.assertEqual(original.system_prompt, "Base prompt with suffix.")
        self.assertEqual(original.history, ("history",))
        self.assertTrue(result.system_prompt.startswith(original.system_prompt))
        self.assertIn(documents[0].text, result.system_prompt)
        self.assertNotIn(documents[1].text, result.system_prompt)
        self.assertEqual(tuple(item.status for item in preload.response.state.skills.results), (JevSkillStatus.SELECTED, JevSkillStatus.SKIPPED))
        self.assertEqual(tuple(item.probability for item in preload.response.state.skills.results), (0.9, 0.2))
        self.assertNotIn(documents[0].text, repr(preload.response.state.skills))

    async def test_missing_candidate_answer_does_not_erase_a_valid_yes(self) -> None:
        # [Hidden Failure] missing data for one indexed answer leaves its independently passing sibling selected.
        preload = _preloader(_skills(2))
        scripted = ScriptedDecisionRunner(probabilities={1: 0.95}, missing=frozenset({2}))
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            context = await preload.run("Update the docs", BaseAgentContext(system_prompt="Base."))

        self.assertIn("FULL BODY 1", context.system_prompt)
        self.assertEqual(tuple(result.status for result in preload.response.state.skills.results), (JevSkillStatus.SELECTED, JevSkillStatus.UNAVAILABLE))

    async def test_many_candidates_use_bounded_batches_with_stable_global_indices(self) -> None:
        # [Edge Case] every full candidate appears exactly once, even after question packing splits the settings order.
        documents = _skills(8)
        preload = _preloader(documents)
        batches = preload._build_batches("Do the requested work")
        self.assertGreater(len(batches), 1)
        indices = tuple(index for batch in batches for index in batch.indices)
        self.assertEqual(indices, tuple(range(1, len(documents) + 1)))
        for batch in batches:
            batch_indices, request = batch.indices, batch.request
            self.assertEqual(tuple(question.name for question in request.questions), tuple(f"skills.skill_{index}" for index in batch_indices))
            self.assertEqual(tuple(request.state["skills"]), tuple(f"skills.skill_{index}" for index in batch_indices))
            self.assertEqual(tuple(request.state["skills"][f"skills.skill_{index}"]["text"] for index in batch_indices), tuple(documents[index - 1].text for index in batch_indices))
            wire = {
                "model": preload.decision.model,
                "state": JevJson.thaw(request.state),
                "questions": {
                    question.name: {
                        "type": question.question_type.value,
                        "instructions": JevJson.thaw(question.instructions),
                        "criteria": {option.name: JevJson.thaw(option.description) for option in question.options},
                    }
                    for question in request.questions
                },
            }
            self.assertLessEqual(len(json.dumps(wire).encode("utf-8")), JEV_SKILLS_MAX_REQUEST_JSON_BYTES)
            for question in request.questions:
                pair = {"state": JevJson.thaw(request.state), "question": wire["questions"][question.name]}
                self.assertLessEqual(len(json.dumps(pair).encode("utf-8")), JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES)

    async def test_failed_batch_and_oversized_skill_leave_answered_skills_selected(self) -> None:
        # [Hidden Failure] neither a late outage nor one too-large document erases passing skills already answered.
        documents = (_skills(3)[0], SkillDocument(name="too_large", description="oversized", text="x" * 35_000), *_skills(4)[1:])
        preload = _preloader(tuple(documents))
        batches = preload._build_batches("Classify each configured item")
        self.assertNotIn(2, {index for batch in batches for index in batch.indices})
        self.assertGreaterEqual(len(batches), 2)
        scripted = ScriptedDecisionRunner(probabilities={index: 0.9 for index in range(1, 7)}, fail_calls=frozenset({len(batches)}))
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            context = await preload.run("Classify each configured item", BaseAgentContext(system_prompt="Base."))

        statuses = tuple(result.status for result in preload.response.state.skills.results)
        failed_indices = set(batches[-1].indices)
        self.assertEqual(statuses[1], JevSkillStatus.UNAVAILABLE)
        for index, status in enumerate(statuses, start=1):
            if index in failed_indices or index == 2:
                self.assertIs(status, JevSkillStatus.UNAVAILABLE)
            else:
                self.assertIs(status, JevSkillStatus.SELECTED)
        self.assertNotIn("x" * 1_000, context.system_prompt)
        successful_calls = len(batches) - 1
        self.assertEqual(preload.response.state.skills.usage.input_tokens, sum(range(10, 10 * (successful_calls + 1), 10)))
        self.assertEqual(preload.response.state.skills.usage.output_tokens, sum(range(1, successful_calls + 1)))

    async def test_batch_failure_leaves_only_its_own_skills_unavailable(self) -> None:
        # [Provider Outage] every batch is asked at once; a failed first batch does not stop or erase the later batches.
        documents = _skills(6)
        preload = _preloader(documents)
        batches = preload._build_batches("Do this work")
        self.assertGreaterEqual(len(batches), 2)
        scripted = ScriptedDecisionRunner(fail_calls=frozenset({1}))
        original = BaseAgentContext(system_prompt="Base context.")
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            result = await preload.run("Do this work", original)

        self.assertEqual(len(scripted.requests), len(batches))
        failed_indices = set(batches[0].indices)
        statuses = tuple(item.status for item in preload.response.state.skills.results)
        self.assertEqual(statuses, tuple(JevSkillStatus.UNAVAILABLE if index in failed_indices else JevSkillStatus.SELECTED for index in range(1, len(documents) + 1)))
        for index in range(1, len(documents) + 1):
            if index in failed_indices:
                self.assertNotIn(f"FULL BODY {index}", result.system_prompt)
            else:
                self.assertIn(f"FULL BODY {index}", result.system_prompt)
        self.assertEqual(preload.response.state.skills.usage.input_tokens, sum(range(20, 10 * (len(batches) + 1), 10)))

    async def test_non_sdk_error_in_a_batch_propagates(self) -> None:
        # [Hidden Failure] gathering every batch must not turn a programming error into an unavailable skill.
        crashing = SimpleNamespace(arun=AsyncMock(side_effect=RuntimeError("bug in the decision path")))
        with patch(_HELPER_PATH, new=_helper_class(crashing)), self.assertRaisesRegex(RuntimeError, "bug in the decision path"):
            await _preloader(_skills(2)).run("Do this work", BaseAgentContext(system_prompt="Base."))

    async def test_failure_in_every_batch_fails_open(self) -> None:
        # [Provider Outage] when every request fails, every skill stays unavailable and the baseline context is kept.
        documents = _skills(6)
        preload = _preloader(documents)
        batches = preload._build_batches("Do this work")
        scripted = ScriptedDecisionRunner(fail_calls=frozenset(range(1, len(batches) + 1)))
        original = BaseAgentContext(system_prompt="Base context.")
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            result = await preload.run("Do this work", original)

        self.assertEqual(result, original)
        self.assertEqual(tuple(item.status for item in preload.response.state.skills.results), (JevSkillStatus.UNAVAILABLE,) * len(documents))
        self.assertEqual(preload.response.state.skills.usage, JevUsage.total(()))
        self.assertEqual((preload.response.state.skills.usage.input_tokens, preload.response.state.skills.usage.output_tokens), (0, 0))

    async def test_decision_without_token_counts_counts_as_a_failed_batch(self) -> None:
        # [Silent Failure] a reply whose cost cannot be recorded never selects skills or reports a partial usage total.
        preload = _preloader(_skills(1))
        scripted = ScriptedDecisionRunner(probabilities={1: 0.95}, unreported_usage_calls=frozenset({1}))
        original = BaseAgentContext(system_prompt="Base.")
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            result = await preload.run("Update the docs", original)

        self.assertEqual(result, original)
        self.assertEqual(preload.response.state.skills.results[0].status, JevSkillStatus.UNAVAILABLE)
        self.assertEqual(preload.response.state.skills.usage.total_tokens, 0)

    async def test_no_skills_performs_zero_decision_calls(self) -> None:
        # [Silent Failure] the empty tuple is a true opt-out and leaves the context unchanged.
        preload = _preloader(())
        scripted = ScriptedDecisionRunner()
        context = BaseAgentContext(system_prompt="Base.")
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            result = await preload.run("Anything", context)

        self.assertIs(result, context)
        self.assertEqual(scripted.requests, [])
        self.assertEqual(preload.response.state.skills.results, ())


class SkillsRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Checks public-run ordering, option overrides, response reset, and bypass paths."""

    async def test_explicit_system_override_is_effective_and_response_resets_between_runs(self) -> None:
        # [Hidden Failure] the caller baseline and current selected skills reach the provider, but prior-run text never leaks.
        agent = _agent(_skills(1))
        runner = CapturingGenerativeRunner()
        bind_test_runner(agent, runner)
        scripted = ScriptedDecisionRunner(per_call=({1: 0.9}, {1: 0.2}))
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            await agent.arun("Apply the guidance", system="Caller override.")
            first_response = agent.response
            await agent.arun("Apply another task", system="Caller override.")

        self.assertEqual(agent.system_prompt, "Agent base prompt.")
        self.assertIn("Caller override.", runner.systems[0])
        self.assertIn("FULL BODY 1", runner.systems[0])
        self.assertIn("Caller override.", runner.systems[1])
        self.assertNotIn("FULL BODY 1", runner.systems[1])
        self.assertEqual(first_response.skills.results[0].status, JevSkillStatus.SELECTED)
        self.assertEqual(agent.response.skills.results[0].status, JevSkillStatus.SKIPPED)

    async def test_runtime_orders_skill_preload_before_run_state(self) -> None:
        # [Hidden Assumption] the main request sees selected skill text, and skills are chosen before run-state setup.
        events: list[str] = []
        continual = JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,))
        agent = _agent(_skills(1), continual=continual)
        runner = CapturingGenerativeRunner(events)
        bind_test_runner(agent, runner)
        scripted = ScriptedDecisionRunner(probabilities={1: 0.9})

        original_preload = agent.skill_preload.run

        async def preload(message: str, context: BaseAgentContext) -> BaseAgentContext:
            events.append("skills")
            return await original_preload(message, context)

        async def begin_state(message: str, prior_user_turns: Sequence[str] = ()) -> None:
            events.append("run_state")

        agent.skill_preload.run = preload
        agent.run_state.begin = begin_state
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            await agent.arun("Edit and verify")

        self.assertEqual(events, ["skills", "run_state", "main_loop"])
        self.assertIn("FULL BODY 1", runner.systems[0])

    async def test_gate_stop_and_specialist_handoff_bypass_skill_decisions(self) -> None:
        # [Hidden Failure] a stopped or delegated request does not spend an extra decision call on the main agent's skills.
        agent = _agent(_skills(1))
        runner = CapturingGenerativeRunner()
        bind_test_runner(agent, runner)
        scripted = ScriptedDecisionRunner()
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            agent.preflight.pass_ = AsyncMock(return_value=False)
            stopped = await agent.arun("Unclear work")
            self.assertEqual(stopped.metadata["strategy"], "jev_preflight")
            agent.preflight.pass_ = AsyncMock(return_value=True)
            delegated_agent = SimpleNamespace(arun=AsyncMock(return_value=AgentMessage(sender="expert", recipient="orchestrator", content="delegated")))
            agent.preflight.specialist = SimpleNamespace(agent=delegated_agent)
            delegated = await agent.arun("Specialist work")

        self.assertEqual(delegated.content, "delegated")
        self.assertEqual(scripted.requests, [])
        self.assertEqual(runner.systems, [])

    async def test_agent_with_no_configured_skills_constructs_no_preload_or_decision_call(self) -> None:
        # [Silent Failure] the public empty default does not create a skill-preload service.
        agent = _agent()
        runner = CapturingGenerativeRunner()
        bind_test_runner(agent, runner)
        scripted = ScriptedDecisionRunner()
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            await agent.arun("Answer normally")

        self.assertIsNone(agent.skill_preload)
        self.assertEqual(scripted.requests, [])
        self.assertEqual(agent.response.skills.results, ())

    async def test_sdk_failure_is_fail_open_for_the_main_agent(self) -> None:
        # [Provider Outage] skills remain optional: the generative run continues with its unmodified effective prompt.
        agent = _agent(_skills(1))
        runner = CapturingGenerativeRunner()
        bind_test_runner(agent, runner)
        scripted = ScriptedDecisionRunner(fail_calls=frozenset({1}))
        with patch(_HELPER_PATH, new=_helper_class(scripted)):
            reply = await agent.arun("Do the work", system="Caller baseline.")

        self.assertEqual(reply.content, "completed")
        self.assertEqual(runner.systems, ["Caller baseline."])
        self.assertEqual(agent.response.skills.results[0].status, JevSkillStatus.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
