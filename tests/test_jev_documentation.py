"""FILE: tests/test_jev_documentation.py

PURPOSE: Verifies JevAgent's documentation lookup without network access: the setting, the question set, the highest-answer decision, the search agent, link verification, fail-open behavior, and that only the main agent's current run sees the links.
ROLE IN CODEBASE: Covers docs/design/jev-documentation.md; scripts/test-jev-agent-scaffold.py runs it alongside tests/test_jev_agent.py.
ARCHITECTURE NOTE: A scripted Jev runner replaces DecisionModelRunner, scripted generative runners replace the main and search models, and a fake search client stands behind the real ExaSearchTool; the production agent, runtime, recorder middleware, and link verification stay under test.
COMMON MODIFICATION PATTERNS: Add a case whenever a question, the threshold, a status branch, or the provider table changes.
KNOWN EDGE CASES: Search API keys are patched in the environment where construction reads them, and no test may send a live provider request.
RELATED DOCS: docs/design/jev-documentation.md and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_documentation.py and python scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

import json
import os
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevDocumentationStatus as RootJevDocumentationStatus
from vidbyte.agents.jev import (
    JevAgent,
    JevAgentSettings,
    JevDocumentation,
    JevDocumentationStatus,
)
from vidbyte.agents.jev.documentation.agent import MAX_LINKS
from vidbyte.agents.jev.documentation.questions import DOCUMENTATION_QUESTIONS, DOCUMENTATION_THRESHOLD
from vidbyte.agents.jev.documentation.search import SearchHitRecorder, SearchHits, bind_search_hits, build_search_tool
from vidbyte.agents.jev.runtime import DOCUMENTATION_METADATA_KEY
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
from vidbyte.lib.dataclasses.operations import SearchHit, SearchPayload
from vidbyte.lib.enums import JevDocumentationProvider, JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.builtins.operations import ExaClient, ExaSearchTool, TavilySearchTool
from vidbyte.tools.types import ToolResult

PROMPT = "You are a coding assistant for the Acme web team."
REQUEST = "Add Stripe Checkout to our Next.js app."
JEV_PATH = "vidbyte.agents.jev.documentation.agent.DecisionModelRunner"
TOOL_PATH = "vidbyte.agents.jev.documentation.agent.build_search_tool"
GENERAL = "documentation.outside_interface"
STRIPE_DOCS = "https://docs.stripe.com/payments/checkout"
STRIPE_API = "https://docs.stripe.com/api/checkout/sessions"


class ScriptedJev:
    """Stands in for DecisionModelRunner: answers every question from a probability table and records requests."""

    def __init__(self, table: Mapping[str, float] | None = None, *, default: float = 0.1, fail: bool = False) -> None:
        self.table = dict(table or {})
        self.default = default
        self.fail = fail
        self.requests: list[JevDecisionRequest] = []

    def __call__(self, config: object = None) -> ScriptedJev:
        # Acts as the runner class, so patching DecisionModelRunner with an instance returns the instance.
        return self

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        # Records the request and returns one noul answer per question.
        self.requests.append(request)
        if self.fail:
            raise ProviderRequestError("TypeSafe is unavailable.", provider="typesafe")
        answers = {question.name: _noul(question.name, self.table.get(question.name, self.default)) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 12, "output_tokens": 3})


class ScriptedRunner:
    """Minimal generative runner that returns scripted responses and records invocation kwargs."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Returns the next response, or raises it when it is an exception.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class RawResponse:
    """OpenAI-shaped raw response wrapper for scripted tool calls."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.text = ""
        self.raw = raw


class FakeSearchClient:
    """Stands in for ExaClient: returns fixed hits for every query and records the queries."""

    max_attempts = 1

    def __init__(self, *urls: str) -> None:
        self.urls = urls
        self.queries: list[str] = []

    async def search(self, query: str, **kwargs: Any) -> SearchPayload:
        self.queries.append(query)
        hits = tuple(SearchHit(title=f"Page {index}", url=url) for index, url in enumerate(self.urls))
        return SearchPayload(provider="exa", query=query, hits=hits, billable_units=len(hits) or 1)


def _noul(name: str, probability: float) -> JevAnswer:
    # Builds a normalized noul answer with P(true) = probability.
    choice = "true" if probability >= 0.5 else "false"
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice=choice, probabilities={"true": probability, "false": 1.0 - probability}, noul=probability)


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "coder", "system_prompt": PROMPT, "provider": "openai", "model_name": "gpt-4.1-mini", "documentation": "exa"}
    values.update(overrides)
    return JevAgentSettings(**values)


def _text(text: str) -> TextModelResponse:
    return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


def _call(name: str, arguments: dict[str, Any], call_id: str) -> RawResponse:
    return RawResponse({"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


def _searcher(final_answer: str) -> ScriptedRunner:
    # Scripts the search agent: one search, then a final list of links.
    return ScriptedRunner(_call("exa_search", {"query": "Stripe Checkout Next.js docs"}, "s1"), _call("isDone", {"final_answer": final_answer}, "done"))


def _agent(main: ScriptedRunner, searcher: ScriptedRunner, client: FakeSearchClient | None, **overrides: Any) -> JevAgent:
    tool = None if client is None else ExaSearchTool(client=client)
    with patch(TOOL_PATH, return_value=tool):
        agent = bind_test_runner(JevAgent(_settings(**overrides)), main)
    assert agent.documentation is not None
    bind_test_runner(agent.documentation, searcher)
    return agent


class JevDocumentationSettingsTests(unittest.TestCase):
    def test_documentation_is_off_by_default_and_takes_one_provider_value(self) -> None:
        # [Hidden Assumption] the one value both enables the lookup and names the provider.
        self.assertIsNone(_settings(documentation=None).documentation)
        self.assertIs(_settings(documentation="tavily").documentation, JevDocumentationProvider.TAVILY)
        self.assertIs(_settings(documentation=JevDocumentationProvider.EXA).documentation, JevDocumentationProvider.EXA)
        self.assertIs(RootJevDocumentationStatus.FOUND, JevDocumentationStatus.FOUND)

    def test_invalid_documentation_values_are_rejected(self) -> None:
        # [Edge Case] True must not silently pick a provider, and unknown providers fail at construction.
        for value in (True, "google", 3):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                _settings(documentation=value)

    def test_search_tool_needs_the_provider_key(self) -> None:
        # [Silent Failure] a priced tool without a client returns a stub, so no key must mean no tool.
        with patch.dict(os.environ, {"EXA_API_KEY": ""}):
            self.assertIsNone(build_search_tool(JevDocumentationProvider.EXA))
        with patch.dict(os.environ, {"EXA_API_KEY": "exa-test", "TAVILY_API_KEY": "tv-test"}):
            exa = build_search_tool(JevDocumentationProvider.EXA)
            tavily = build_search_tool(JevDocumentationProvider.TAVILY)
        self.assertIsInstance(exa, ExaSearchTool)
        self.assertIsInstance(exa._client, ExaClient)
        self.assertIsInstance(tavily, TavilySearchTool)

    def test_search_agent_requires_a_documentation_setting(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevDocumentation(_settings(documentation=None))

    def test_question_set_shape(self) -> None:
        # [Hidden Assumption] every question is a positive-polarity noul over `request`, ending in the question.
        names = [question.name for question in DOCUMENTATION_QUESTIONS]
        self.assertEqual(len(names), 10)
        self.assertEqual(len(set(names)), len(names))
        for question in DOCUMENTATION_QUESTIONS:
            self.assertTrue(question.name.startswith("documentation."))
            self.assertIs(question.question_type, JevQuestionType.NOUL)
            self.assertIn("`request`", str(question.instructions))
            self.assertTrue(str(question.instructions).rstrip().endswith("?"))


class JevDocumentationRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_documentation_off_makes_no_jev_call(self) -> None:
        jev = ScriptedJev()
        agent = bind_test_runner(JevAgent(_settings(documentation=None)), ScriptedRunner(_text("answer")))
        with patch(JEV_PATH, jev):
            reply = await agent.arun(REQUEST)
        self.assertEqual(jev.requests, [])
        self.assertIsNone(agent.documentation)
        self.assertNotIn(DOCUMENTATION_METADATA_KEY, reply.metadata)

    async def test_one_strong_sign_finds_links_for_this_run_only(self) -> None:
        # [Silent Failure] one strong sign decides even when the other nine are weak; the links reach only this run.
        jev = ScriptedJev({"documentation.integration": 0.95})
        main = ScriptedRunner(_text("answer"))
        searcher = _searcher(f"{STRIPE_DOCS} - Stripe Checkout\n{STRIPE_API} - Checkout Sessions API")
        agent = _agent(main, searcher, FakeSearchClient(STRIPE_DOCS, STRIPE_API))
        with patch(JEV_PATH, jev):
            reply = await agent.arun(REQUEST)
        result = reply.metadata[DOCUMENTATION_METADATA_KEY]
        self.assertIs(result.status, JevDocumentationStatus.FOUND)
        self.assertTrue(result.needs_documentation)
        self.assertEqual([(link.url, link.title) for link in result.links], [(STRIPE_DOCS, "Stripe Checkout"), (STRIPE_API, "Checkout Sessions API")])
        system = main.calls[0]["kwargs"]["system"]
        self.assertIn(PROMPT, system)
        self.assertIn("## Documentation", system)
        self.assertIn(f"- Stripe Checkout: {STRIPE_DOCS}", system)
        self.assertEqual(agent.system_prompt, PROMPT)
        self.assertEqual(agent.settings.system_prompt, PROMPT)
        self.assertEqual(jev.requests[0].state, {"request": REQUEST})
        self.assertEqual(result.usage.input_tokens, 12)

    async def test_weak_signs_mean_no_documentation(self) -> None:
        # [Hidden Assumption] below the threshold the search agent never runs and the prompt is unchanged.
        jev = ScriptedJev(default=DOCUMENTATION_THRESHOLD - 0.05)
        main = ScriptedRunner(_text("answer"))
        searcher = _searcher(STRIPE_DOCS)
        agent = _agent(main, searcher, FakeSearchClient(STRIPE_DOCS))
        with patch(JEV_PATH, jev):
            reply = await agent.arun("Explain how binary search works.")
        result = reply.metadata[DOCUMENTATION_METADATA_KEY]
        self.assertIs(result.status, JevDocumentationStatus.NOT_NEEDED)
        self.assertFalse(result.needs_documentation)
        self.assertEqual(len(result.probabilities), 10)
        self.assertEqual(searcher.calls, [])
        self.assertNotIn("## Documentation", main.calls[0]["kwargs"]["system"])

    async def test_links_search_never_returned_are_dropped(self) -> None:
        # [Silent Failure] a URL the model invented must never reach the main agent.
        jev = ScriptedJev({GENERAL: 0.9})
        main = ScriptedRunner(_text("answer"))
        searcher = _searcher(f"https://docs.stripe.com/made-up - Invented\n{STRIPE_DOCS}. - Real")
        agent = _agent(main, searcher, FakeSearchClient(STRIPE_DOCS))
        with patch(JEV_PATH, jev):
            reply = await agent.arun(REQUEST)
        result = reply.metadata[DOCUMENTATION_METADATA_KEY]
        self.assertEqual([link.url for link in result.links], [STRIPE_DOCS])
        self.assertNotIn("made-up", main.calls[0]["kwargs"]["system"])

    async def test_links_are_deduplicated_and_capped(self) -> None:
        # [Edge Case] repeated links count once, and at most MAX_LINKS reach the prompt.
        urls = [f"https://docs.example.com/page-{index}" for index in range(MAX_LINKS + 2)]
        jev = ScriptedJev({GENERAL: 0.9})
        searcher = _searcher("\n".join([urls[0], *urls]))
        agent = _agent(ScriptedRunner(_text("answer")), searcher, FakeSearchClient(*urls))
        with patch(JEV_PATH, jev):
            reply = await agent.arun(REQUEST)
        self.assertEqual([link.url for link in reply.metadata[DOCUMENTATION_METADATA_KEY].links], urls[:MAX_LINKS])

    async def test_no_suitable_page_reports_no_links(self) -> None:
        jev = ScriptedJev({GENERAL: 0.9})
        main = ScriptedRunner(_text("answer"))
        agent = _agent(main, _searcher("none"), FakeSearchClient(STRIPE_DOCS))
        with patch(JEV_PATH, jev):
            reply = await agent.arun(REQUEST)
        result = reply.metadata[DOCUMENTATION_METADATA_KEY]
        self.assertIs(result.status, JevDocumentationStatus.NO_LINKS)
        self.assertTrue(result.needs_documentation)
        self.assertNotIn("## Documentation", main.calls[0]["kwargs"]["system"])

    async def test_jev_failure_fails_open(self) -> None:
        # [Hidden Failure] documentation is advisory; the main run continues without links.
        main = ScriptedRunner(_text("answer"))
        searcher = _searcher(STRIPE_DOCS)
        agent = _agent(main, searcher, FakeSearchClient(STRIPE_DOCS))
        with patch(JEV_PATH, ScriptedJev(fail=True)):
            reply = await agent.arun(REQUEST)
        result = reply.metadata[DOCUMENTATION_METADATA_KEY]
        self.assertIs(result.status, JevDocumentationStatus.UNAVAILABLE)
        self.assertFalse(result.needs_documentation)
        self.assertEqual(reply.content, "answer")
        self.assertEqual(searcher.calls, [])

    async def test_missing_search_key_keeps_the_decision_and_skips_search(self) -> None:
        # [Hidden Failure] a needed lookup without a key reports the key's name and still runs the main agent.
        jev = ScriptedJev({GENERAL: 0.9})
        main = ScriptedRunner(_text("answer"))
        searcher = _searcher(STRIPE_DOCS)
        agent = _agent(main, searcher, None)
        with patch(JEV_PATH, jev):
            reply = await agent.arun(REQUEST)
        result = reply.metadata[DOCUMENTATION_METADATA_KEY]
        self.assertIs(result.status, JevDocumentationStatus.UNAVAILABLE)
        self.assertTrue(result.needs_documentation)
        self.assertIn("EXA_API_KEY", result.detail)
        self.assertEqual(searcher.calls, [])
        self.assertEqual(reply.content, "answer")

    async def test_search_agent_failure_fails_open(self) -> None:
        # [Hidden Failure] a failing search model must not stop the main run.
        jev = ScriptedJev({GENERAL: 0.9})
        main = ScriptedRunner(_text("answer"))
        searcher = ScriptedRunner(ProviderRequestError("model down", provider="openai"))
        agent = _agent(main, searcher, FakeSearchClient(STRIPE_DOCS))
        with patch(JEV_PATH, jev):
            reply = await agent.arun(REQUEST)
        result = reply.metadata[DOCUMENTATION_METADATA_KEY]
        self.assertIs(result.status, JevDocumentationStatus.UNAVAILABLE)
        self.assertTrue(result.needs_documentation)
        self.assertEqual(reply.content, "answer")

    async def test_recorder_writes_only_to_the_bound_lookup(self) -> None:
        # [Edge Case] hits seen outside a bound lookup are dropped instead of leaking into a later lookup.
        payload = SearchPayload(provider="exa", query="q", hits=(SearchHit(title="t", url=STRIPE_DOCS),))
        result = ToolResult.success("exa_search", "ok", metadata={"operation_payload": payload})
        context = MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="coder-documentation", tool_result=result)
        recorder = SearchHitRecorder()
        earlier = SearchHits()
        await recorder.after_tool_call(context)
        hits = SearchHits()
        with bind_search_hits(hits):
            await recorder.after_tool_call(context)
        self.assertEqual(earlier.urls, {})
        self.assertEqual(list(hits.urls), [STRIPE_DOCS])


if __name__ == "__main__":
    unittest.main()
