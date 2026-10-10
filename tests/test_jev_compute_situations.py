"""FILE: tests/test_jev_compute_situations.py

PURPOSE: Verifies the fixed dynamic-compute evidence questions and their single-request selection behavior.
ROLE IN CODEBASE: Covers the question registry, shared state, JevComputeRecognizer, decision records, and post-brief controller checkpoint.
ARCHITECTURE NOTE: A scripted decision runner exercises the real request construction and score normalization without network calls.
COMMON MODIFICATION PATTERNS: Add focused cases when question evidence, option scoring, state bounds, or checkpoint timing changes.
KNOWN EDGE CASES: Incomplete option answers and provider failures produce no selection; disabled options skip recognition.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: python -m pytest tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

import json
import re
import unittest
from collections.abc import Mapping
from dataclasses import fields
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from vidbyte import tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRuntimeSettings
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD, JEV_RUN_BRIEF_REQUEST_MAX_CHARS
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevComputeDecision,
    JevComputeOptionResult,
    JevComputeQuestion,
    JevDecisionRequest,
    JevRunBrief,
    JevRunBriefAppendPayload,
    JevRunBriefNote,
    JevRunFacts,
)
from vidbyte.lib.enums import DecisionModelMode, JevDynamicComputeOption, JevQuestionType, JevRunBriefUpdateStatus, ModelProvider
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.compute import JevComputeRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse

_HELPER = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
REQUEST = "Audit each file under src/api for SQL injection."
Q = JevRunBriefNote
OPTIONS = tuple(JevDynamicComputeOption)


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


def _brief() -> JevRunBrief:
    return JevRunBrief(
        goal="Audit the API files",
        notes=(Q("E2", "I am checking src/api/a.py."),),
        iteration=3,
        through_event=6,
    )


def _facts() -> JevRunFacts:
    return JevRunFacts(iteration=3, tool_calls=2, error_streak=1, tokens_used=200)


def _events() -> JevRunEventLog:
    return JevRunEventLog.from_run(REQUEST, ["I will inspect the API files.", "The first check returned an error."], [])


class ScriptedJev:
    """Returns scripted P(true) values keyed by question name and retains request bodies for assertions."""

    def __init__(self, yes: Mapping[str, float] | None = None, *, default: float = 0.9, error: Exception | None = None, missing: tuple[str, ...] = ()) -> None:
        self.yes = dict(yes or {})
        self.default = default
        self.error = error
        self.missing = missing
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        answers = {question.name: _answer(question.name, self.yes.get(question.name, self.default)) for question in request.questions if question.name not in self.missing}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 200, "output_tokens": 12})


def _helper(scripted: ScriptedJev) -> type:
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedJev:  # type: ignore[misc]
            return scripted

    return ScriptedHelper


class JevComputeQuestionTests(unittest.TestCase):
    def test_registry_has_twelve_plain_questions_per_option(self) -> None:
        self.assertEqual(OPTIONS, (JevDynamicComputeOption.FRESH_AGENT, JevDynamicComputeOption.FORK_AGENT, JevDynamicComputeOption.SUBAGENT, JevDynamicComputeOption.CLONE, JevDynamicComputeOption.SWARM))
        flattened = tuple(key for option in OPTIONS for key in JevComputeRegistry.question_keys(option))
        self.assertEqual(len(flattened), 60)
        self.assertEqual(len(set(flattened)), 60)
        questions = JevComputeRegistry.questions(OPTIONS)
        self.assertEqual(len(questions), 60)
        self.assertEqual([question.name for question in questions], [key.value for key in flattened])
        openings: list[str] = []
        for option in OPTIONS:
            keys = JevComputeRegistry.question_keys(option)
            self.assertEqual(len(keys), 12)
            for key in keys:
                question = JevComputeRegistry.get(key)
                wire_question = next(item for item in questions if item.name == key.value)
                self.assertIs(type(question), JevComputeQuestion)
                self.assertIs(wire_question.question_type, JevQuestionType.NOUL)
                self.assertEqual([item.name for item in wire_question.options], ["true", "false"])
                self.assertNotRegex(question.instructions, r"`(?:request|brief|facts|recent)`")
                sentences = re.split(r"(?<=[.!?])\s+", question.instructions.strip())
                self.assertEqual(len(sentences), 10, key.value)
                self.assertEqual(len({sentence.casefold() for sentence in sentences}), len(sentences), key.value)
                self.assertTrue(all(sentence.endswith(".") for sentence in (*sentences[:3], *sentences[8:])), key.value)
                self.assertTrue(all(sentence.endswith("?") for sentence in sentences[3:8]), key.value)
                openings.append(sentences[0].casefold())
                for criterion in (question.when_true, question.when_false):
                    criterion_sentences = re.split(r"(?<=\.)\s+", criterion.strip())
                    self.assertEqual(len(criterion_sentences), 3, key.value)
                    self.assertTrue(all(sentence.endswith(".") for sentence in criterion_sentences), key.value)
                    self.assertNotIn("example", criterion.casefold(), key.value)
        self.assertEqual(len(set(openings)), len(openings))

    def test_decision_records_and_registry_have_no_gate_or_veto_policy(self) -> None:
        self.assertEqual({field.name for field in fields(JevComputeDecision)}, {"iteration", "results", "option", "usage"})
        self.assertEqual({field.name for field in fields(JevComputeOptionResult)}, {"option", "score", "answers"})
        self.assertFalse(hasattr(JevComputeRegistry, "definition"))

    def test_settings_default_normalize_and_allow_disabling(self) -> None:
        self.assertEqual(JevComputeSettings().dynamic_compute, OPTIONS[:3])
        normalized = JevComputeSettings(dynamic_compute=("subagent", JevDynamicComputeOption.FRESH_AGENT, "fresh_agent")).dynamic_compute
        self.assertEqual(normalized, (JevDynamicComputeOption.FRESH_AGENT, JevDynamicComputeOption.SUBAGENT))
        self.assertEqual(JevComputeSettings(dynamic_compute=()).dynamic_compute, ())
        with self.assertRaises(ConfigurationError):
            JevComputeSettings(dynamic_compute=("unknown",))
        with self.assertRaises(ConfigurationError):
            JevComputeSettings(dynamic_compute="fresh_agent")  # type: ignore[arg-type]

    def test_shared_state_uses_all_four_common_fields_and_existing_renderers(self) -> None:
        request = "r" * (JEV_RUN_BRIEF_REQUEST_MAX_CHARS + 10)
        brief, facts, events = _brief(), _facts(), _events()
        state = JevComputeStates.build(request, brief, facts, events)
        self.assertEqual(set(state), {"request", "brief", "facts", "recent"})
        self.assertLessEqual(len(state["request"]), JEV_RUN_BRIEF_REQUEST_MAX_CHARS)
        self.assertIn("chars omitted", state["request"])
        self.assertEqual(state["brief"], brief.render())
        self.assertEqual(state["facts"], {"iteration": 3, "tool_calls": 2, "error_streak": 1, "tokens_used": 200})
        expected_events = tuple(line for line in events.lines if not line.partition(" ")[2].startswith("USER: "))
        self.assertEqual(state["recent"], "\n".join(expected_events[-12:]))

    def test_shared_state_keeps_only_twelve_recent_non_request_events_and_clips_each(self) -> None:
        events = JevRunEventLog((
            "E1 USER: ignored request",
            "E2 TOOL old: " + ("x" * 2_500),
            "E3 TOOL older: completed",
            "E4 TOOL kept: " + ("y" * 2_500),
            *(f"E{number} TOOL call: done" for number in range(5, 16)),
        ))
        state = JevComputeStates.build(REQUEST, _brief(), _facts(), events)
        recent = state["recent"].splitlines()  # type: ignore[union-attr]
        self.assertEqual(len(recent), 12)
        self.assertTrue(recent[0].startswith("E4 "))
        self.assertTrue(recent[-1].startswith("E15 "))
        self.assertIn("chars omitted", recent[0])
        self.assertTrue(all(len(line) <= 2_000 for line in recent))


class JevComputeRecognitionTests(unittest.IsolatedAsyncioTestCase):
    async def _recognize(self, scripted: ScriptedJev, options: tuple[JevDynamicComputeOption, ...] = OPTIONS) -> JevComputeDecision:
        recognizer = JevComputeRecognizer(DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), options)
        with patch(_HELPER, new=_helper(scripted)):
            return await recognizer.recognize(3, REQUEST, _brief(), _facts(), _events())

    async def test_one_combined_request_selects_highest_mean_over_enum_order(self) -> None:
        keys = {option: JevComputeRegistry.question_keys(option) for option in OPTIONS}
        scores = {
            OPTIONS[0]: [0.99, *([0.72] * 11)],
            OPTIONS[1]: [*([0.91] * 6), *([0.83] * 6)],
            OPTIONS[2]: [0.82] * 12,
            OPTIONS[3]: [0.81] * 12,
            OPTIONS[4]: [0.80] * 12,
        }
        probabilities = {key.value: score for option in OPTIONS for key, score in zip(keys[option], scores[option])}
        means = {option: sum(scores[option]) / len(scores[option]) for option in OPTIONS}
        scripted = ScriptedJev(probabilities)
        decision = await self._recognize(scripted)
        self.assertEqual(len(scripted.requests), 1)
        sent = scripted.requests[0]
        self.assertEqual([question.name for question in sent.questions], [key.value for option in OPTIONS for key in keys[option]])
        self.assertEqual(set(sent.state), {"request", "brief", "facts", "recent"})  # type: ignore[arg-type]
        self.assertEqual([result.option for result in decision.results], list(OPTIONS))
        for result in decision.results:
            self.assertAlmostEqual(result.score, means[result.option])  # type: ignore[arg-type]
        self.assertIs(decision.option, JevDynamicComputeOption.FORK_AGENT)
        self.assertEqual(decision.usage.input_tokens, 200)  # type: ignore[union-attr]

    async def test_threshold_is_inclusive_and_enum_order_breaks_ties(self) -> None:
        probabilities = {
            key.value: JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD if option is not OPTIONS[2] else JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD - 0.01
            for option in OPTIONS
            for key in JevComputeRegistry.question_keys(option)
        }
        scripted = ScriptedJev(probabilities)
        decision = await self._recognize(scripted)
        self.assertIs(decision.option, OPTIONS[0])

    async def test_missing_answer_makes_only_that_option_unavailable(self) -> None:
        missing_name = JevComputeRegistry.question_keys(OPTIONS[0])[0].value
        decision = await self._recognize(ScriptedJev(default=0.9, missing=(missing_name,)))
        self.assertIsNone(decision.results[0].score)
        self.assertIs(decision.option, OPTIONS[1])

    async def test_provider_failure_selects_no_option(self) -> None:
        decision = await self._recognize(ScriptedJev(error=VidbyteSdkError("down")))
        self.assertIsNone(decision.option)
        self.assertTrue(all(result.score is None for result in decision.results))
        self.assertIsNone(decision.usage)

    async def test_no_options_makes_no_request(self) -> None:
        scripted = ScriptedJev()
        decision = await self._recognize(scripted, ())
        self.assertEqual(scripted.requests, [])
        self.assertIsNone(decision.option)
        self.assertEqual(decision.results, ())


@tool
def lookup(topic: str) -> str:
    """Look up one topic and return what was found about it."""
    return f"found:{topic}"


class ScriptedRunner:
    """Minimal synchronous generative runner that returns scripted model responses in order."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)

    def run(self, prompt: str, **kwargs: Any) -> object:
        return self.responses.pop(0)


def _call(name: str, arguments: dict[str, Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(text="", raw={"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]}, provider=ModelProvider.OPENAI, model="gpt-5.4-mini", usage={"input_tokens": 100, "output_tokens": 20})


class JevComputeCheckpointRecognitionTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, dynamic_compute: tuple[JevDynamicComputeOption, ...] = OPTIONS) -> JevAgent:
        settings = JevAgentSettings(name="researcher", system_prompt="Research.", provider="openai", model_name="gpt-4.1", api_key="main-key", tools=(lookup,))
        runtime = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), compute=JevComputeSettings(dynamic_compute=dynamic_compute))
        runner = ScriptedRunner(*(_call("lookup", {"topic": topic}, f"c{index}") for index, topic in enumerate(("a", "b", "c", "d"))), _call("isDone", {"final_answer": "done"}, "end"))
        return bind_test_runner(JevAgent(settings, runtime), runner)

    def _payload(self) -> JevRunBriefAppendPayload:
        return JevRunBriefAppendPayload.model_validate({"notes": []})

    async def test_checkpoint_asks_one_request_after_a_verified_update(self) -> None:
        agent = self._agent()
        scripted = ScriptedJev(default=0.9)
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=self._payload()))), patch(_HELPER, new=_helper(scripted)):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "done")
        self.assertEqual(len(scripted.requests), 1)
        self.assertEqual(agent.response.run_brief_updates[-1].status, JevRunBriefUpdateStatus.UPDATED)
        self.assertEqual(len(agent.response.compute_decisions), 1)
        self.assertIs(agent.response.compute_decisions[0].option, OPTIONS[0])

    async def test_checkpoint_skips_recognition_after_a_rejected_update(self) -> None:
        agent = self._agent()
        scripted = ScriptedJev(default=0.9)
        rejected = JevRunBriefAppendPayload.model_validate({
            "notes": [{"event": "E1", "text": "The user request is not a citable work event."}],
        })
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=rejected))), patch(_HELPER, new=_helper(scripted)):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "done")
        self.assertEqual(agent.response.run_brief_updates[-1].status, JevRunBriefUpdateStatus.REJECTED)
        self.assertEqual(scripted.requests, [])
        self.assertEqual(agent.response.compute_decisions, [])

    async def test_disabled_options_keep_brief_updates_and_make_no_recognition_request(self) -> None:
        agent = self._agent(())
        scripted = ScriptedJev()
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=self._payload()))), patch(_HELPER, new=_helper(scripted)):
            await agent.arun(REQUEST)
        self.assertTrue(agent.response.run_brief_updates)
        self.assertEqual(agent.response.run_brief_updates[-1].status, JevRunBriefUpdateStatus.UPDATED)
        self.assertEqual(scripted.requests, [])
        self.assertEqual(agent.response.compute_decisions, [])


if __name__ == "__main__":
    unittest.main()
