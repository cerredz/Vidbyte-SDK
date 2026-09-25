"""FILE: tests/test_jev_tool_selector.py

PURPOSE: Verifies Jev tool selection, threshold validation, and runtime tool hiding without network calls.
ROLE IN CODEBASE: Covers the TOOL_SELECTOR setting and its integration before the ordinary Jev agent loop.
ARCHITECTURE NOTE: Scripted decision and generative runners replace external boundaries while production catalog filtering stays active.
COMMON MODIFICATION PATTERNS: Cover settings bounds, each availability outcome, model-visible schemas, and execution lookup together.
KNOWN EDGE CASES: The selector is disabled by default and provider or incomplete-answer failures preserve the full catalog.
RELATED DOCS: docs/design/jev-tool-selector.md and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_tool_selector.py and python scripts/test-jev-tool-selector.py.
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent, JevAgentSettings, JevPreflightPreset, tool
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.catalog import Tools


class ScriptedDecisionRunner:
    """Captures the batched Jev request and returns scripted Noul probabilities."""

    def __init__(self, probabilities: Mapping[str, float] | None = None, *, omit_answer: str | None = None) -> None:
        self.probabilities = probabilities or {}
        self.omit_answer = omit_answer
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Returns one normalized answer per requested tool unless a test omits one deliberately.
        self.requests.append(request)
        answers = {
            question.name: _answer(
                question.name,
                self.probabilities.get(question.name, 0.9),
            )
            for question in request.questions
            if question.name != self.omit_answer
        }
        return DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-test",
            answers=answers,
            raw={},
            usage={"input_tokens": 15, "output_tokens": 3},
        )


class ScriptedGenerativeRunner:
    """Captures tool schemas and emits scripted generative responses."""

    def __init__(self, *responses: object) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = list(responses) or [
            TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="done", raw={})
        ]

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Records model-call options so tests can assert which tools were visible.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.responses.pop(0)


class RawResponse:
    """Wraps OpenAI-shaped raw output for tool-call integration cases."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.text = ""
        self.raw = raw


def _answer(name: str, probability: float) -> JevAnswer:
    """Builds a validated Noul answer with the requested true probability."""
    return JevAnswer(
        question_name=name,
        question_type=JevQuestionType.NOUL,
        choice="true" if probability >= 0.5 else "false",
        probabilities={"true": probability, "false": 1.0 - probability},
        noul=probability,
    )


def _settings(**overrides: Any) -> JevAgentSettings:
    """Builds a valid Jev settings object with caller-provided overrides."""
    values: dict[str, Any] = {
        "name": "selector",
        "system_prompt": "Work carefully.",
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
    }
    values.update(overrides)
    return JevAgentSettings(**values)


class JevToolSelectorSettingsTests(unittest.TestCase):
    """Pins the public preset name and valid threshold range."""

    def test_normalizes_tool_selector_and_accepts_probability_endpoints(self) -> None:
        # [Edge Case] both endpoints are probabilities and strings use the same stable public name.
        self.assertEqual(_settings(preflight=("tool_selector",)).preflight, (JevPreflightPreset.TOOL_SELECTOR,))
        self.assertEqual(_settings(tool_selector_threshold=0).tool_selector_threshold, 0.0)
        self.assertEqual(_settings(tool_selector_threshold=1).tool_selector_threshold, 1.0)

    def test_rejects_out_of_range_and_non_probability_values(self) -> None:
        # [Hidden Failure] bool is an int in Python and NaN evades ordinary range comparisons.
        for value in (-0.01, 1.01, True, float("nan"), float("inf"), "0.5"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                _settings(tool_selector_threshold=value)

    def test_rejects_duplicate_or_unknown_presets(self) -> None:
        # [Edge Case] each capability runs at most once and unsupported names fail during construction.
        for presets in (("tool_selector", "tool_selector"), ("unknown",)):
            with self.subTest(presets=presets), self.assertRaises(ConfigurationError):
                _settings(preflight=presets)


class JevPreflightToolsTests(unittest.IsolatedAsyncioTestCase):
    """Checks batched question generation, probability filtering, and fail-open behavior."""

    async def test_builds_one_question_per_tool_and_keeps_threshold_boundary(self) -> None:
        # [Edge Case] a probability equal to the configured cutoff remains selectable.
        @tool
        def search(query: str) -> str:
            """Search documents for a query."""
            return query

        @tool
        def calendar(day: str) -> str:
            """Read events for a day."""
            return day

        catalog = Tools((search, calendar))
        decision_runner = ScriptedDecisionRunner({"tool_selector.0": 0.4, "tool_selector.1": 0.399})
        selector = JevPreflightTools(DecisionModelConfig(api_key="test-key"), 0.4)

        with patch("vidbyte.agents.jev.preflight.DecisionModelRunner", return_value=decision_runner):
            selected = await selector.run("Find the architecture notes.", catalog)

        self.assertEqual(catalog.names(), ("search", "calendar"))
        self.assertEqual(selected.names(), ("search",))
        self.assertEqual(len(decision_runner.requests), 1)
        self.assertEqual(len(decision_runner.requests[0].questions), 2)
        self.assertEqual(selector.usage.input_tokens, 15)
        self.assertTrue(selector.available)

    async def test_incomplete_answers_keep_all_tools(self) -> None:
        # [Silent Failure] a missing answer cannot silently remove the tool whose answer was absent.
        @tool
        def lookup(query: str) -> str:
            """Look up one record."""
            return query

        catalog = Tools((lookup,))
        decision_runner = ScriptedDecisionRunner(omit_answer="tool_selector.0")
        selector = JevPreflightTools(DecisionModelConfig(api_key="test-key"), 0.2)

        with patch("vidbyte.agents.jev.preflight.DecisionModelRunner", return_value=decision_runner):
            selected = await selector.run("Look up the record.", catalog)

        self.assertEqual(selected.names(), catalog.names())
        self.assertFalse(selector.available)

    async def test_provider_failure_keeps_all_tools(self) -> None:
        # [Hidden Failure] missing Jev credentials or a provider outage must not disable agent tools.
        @tool
        def lookup(query: str) -> str:
            """Look up one record."""
            return query

        catalog = Tools((lookup,))
        selector = JevPreflightTools(DecisionModelConfig(api_key="test-key"), 0.2)

        with patch(
            "vidbyte.agents.jev.preflight.DecisionModelRunner",
            side_effect=ProviderRequestError("provider unavailable", provider="typesafe"),
        ):
            selected = await selector.run("Look up the record.", catalog)

        self.assertEqual(selected.names(), catalog.names())
        self.assertFalse(selector.available)


class JevToolSelectorRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verifies the selected catalog controls schemas and runtime lookup."""

    async def test_filtered_tool_is_hidden_from_model_and_unavailable_for_execution(self) -> None:
        # [Hidden Failure] pruning only schemas would still let a model call the hidden runtime tool.
        @tool
        def keep(query: str) -> str:
            """Search relevant records."""
            return query

        @tool
        def hide(query: str) -> str:
            """Search unrelated records."""
            hidden_calls.append(query)
            return query

        decision_runner = ScriptedDecisionRunner({"tool_selector.0": 0.9, "tool_selector.1": 0.1})
        hidden_calls: list[str] = []
        generative_runner = ScriptedGenerativeRunner(
            RawResponse({"output": [{"type": "function_call", "name": "hide", "arguments": '{"query": "x"}', "call_id": "hidden"}]}),
            RawResponse({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "complete"}]}),
        )
        settings = _settings(
            tools=(keep, hide),
            preflight=(JevPreflightPreset.TOOL_SELECTOR,),
            decision=DecisionModelConfig(api_key="test-key"),
            tool_selector_threshold=0.2,
        )
        agent = bind_test_runner(JevAgent(settings), generative_runner)

        with patch("vidbyte.agents.jev.preflight.DecisionModelRunner", return_value=decision_runner):
            reply = await agent.arun("Search the relevant records.")

        for model_call in generative_runner.calls:
            model_tools = model_call["kwargs"]["tools"]
            model_tool_names = tuple(schema["function"]["name"] for schema in model_tools)
            self.assertEqual(model_tool_names, ("keep", "isDone"))
        self.assertEqual(reply.content, "done")
        self.assertEqual(reply.metadata["tool_call_states"], ("failed", "succeeded"))
        self.assertEqual(hidden_calls, [])
        self.assertEqual(reply.response.tool_selector.candidate_tool_count, 2)
        self.assertEqual(reply.response.tool_selector.selected_tool_count, 1)

    async def test_disabled_selector_makes_no_decision_call(self) -> None:
        # [Edge Case] existing JevAgent settings retain ordinary loop behavior by default.
        generative_runner = ScriptedGenerativeRunner()
        agent = bind_test_runner(JevAgent(_settings()), generative_runner)

        with patch("vidbyte.agents.jev.preflight.DecisionModelRunner") as decision_runner:
            reply = await agent.arun("Answer normally.")

        decision_runner.assert_not_called()
        self.assertEqual(reply.content, "done")
        self.assertIsNone(reply.response.tool_selector)


if __name__ == "__main__":
    unittest.main()
