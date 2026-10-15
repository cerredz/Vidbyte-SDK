"""FILE: tests/features/sdk_model_usage/test_billed_unusable_replies.py

PURPOSE: Prove a billed HTTP 200 whose reply has no usable text stays on the run's usage bill instead of being dropped.
ROLE IN CODEBASE: Exercises the text adapters in vidbyte/providers/ and the failed-call branch of vidbyte/agents/runtime.py.
ARCHITECTURE NOTE: A scripted in-memory HttpTransport.request answers every call; adapters, runtime, fallback and pricing stay production code.
FUNCTION INVENTORY: test_unusable_reply_error_carries_billed_usage checks each text adapter; test_billed_refusal_then_fallback_bills_both_calls checks an agent run.
COMMON MODIFICATION PATTERNS: Add a provider-shaped unusable 200 when a new text adapter is added.
WHAT NOT TO DO IN THIS FILE: 1. Do not reach the network; the transport is scripted. 2. Do not hard-code tariff rates; the pricebook owns them.
KNOWN EDGE CASES: Anthropic refuses with an empty content list; Gemini can spend its whole budget on thinking and return no parts.
RELATED DOCS: tests/features/sdk_model_usage/FEATURE.md documents this accounting contract.
TESTS: This module and scripts/run_ci.py source gate.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from vidbyte import Agent
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.dataclasses.agents import FallbackModel
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.http import HttpResponse, HttpTransport
from vidbyte.providers.anthropic import AnthropicProvider
from vidbyte.providers.compatible import DeepSeekProvider
from vidbyte.providers.gemini import GeminiProvider
from vidbyte.providers.openai import OpenAIProvider
from vidbyte.providers.openrouter import OpenRouterProvider
from vidbyte.providers.xai import XAIProvider

ANTHROPIC_REFUSAL = {"id": "m1", "type": "message", "role": "assistant", "model": "claude-sonnet-5", "content": [], "stop_reason": "refusal", "usage": {"input_tokens": 1000, "output_tokens": 3}}
GEMINI_THINKING_ONLY = {"candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS", "index": 0}], "usageMetadata": {"promptTokenCount": 1000, "thoughtsTokenCount": 800, "totalTokenCount": 1800}}
GEMINI_OK = {"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP", "index": 0}], "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 5, "totalTokenCount": 1005}}
CHAT_EMPTY = {"choices": [{"index": 0, "message": {"role": "assistant", "content": None}, "finish_reason": "length"}], "usage": {"prompt_tokens": 1000, "completion_tokens": 7}}
RESPONSES_EMPTY = {"id": "r1", "output": [{"type": "reasoning", "summary": []}], "usage": {"input_tokens": 1000, "output_tokens": 7}}
# A Gemini key in the AQ. form (its prefix proves gemini); built at runtime so no key-shaped literal sits in the source.
GEMINI_TEST_KEY = "AQ" + "." + "x" * 40


class _ScriptedTransport:
    """Answers every request with one fixed provider body."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    async def request(self, **_: Any) -> HttpResponse:
        return HttpResponse(status_code=200, body=json.dumps(self._body), headers={"content-type": "application/json"})


@pytest.mark.parametrize(("provider_type", "model", "provider_key", "body", "usage_key"), [
    (AnthropicProvider, "claude-sonnet-5", "sk-ant-mock", ANTHROPIC_REFUSAL, "usage"),
    (GeminiProvider, "gemini-3.5-flash", GEMINI_TEST_KEY, GEMINI_THINKING_ONLY, "usageMetadata"),
    (XAIProvider, "grok-4", "xai-mock", CHAT_EMPTY, "usage"),
    (DeepSeekProvider, "deepseek-v4-flash", "d-mock", CHAT_EMPTY, "usage"),
    (OpenRouterProvider, "openai/gpt-5.4-mini", "sk-or-v1-mock", CHAT_EMPTY, "usage"),
    (OpenAIProvider, "gpt-5.4-mini", "sk-mock", RESPONSES_EMPTY, "usage"),
], ids=["anthropic", "gemini", "xai", "deepseek", "openrouter", "openai"])
def test_unusable_reply_error_carries_billed_usage(provider_type: Any, model: str, provider_key: str, body: dict[str, Any], usage_key: str) -> None:
    # Each adapter talks to its own vendor directly with a key shaped like that vendor's keys.
    provider = provider_type(model=model, api_keys=[provider_key], mode=TextModelMode.DIRECT)
    # The adapter still rejects the reply, but the error keeps the usage the provider billed for it.
    with pytest.raises(ProviderResponseError) as caught:
        asyncio.run(provider.run_text(prompt="hi", system=None, metadata=None, transport=_ScriptedTransport(body)))
    assert caught.value.details["usage"] == body[usage_key]


def test_billed_refusal_then_fallback_bills_both_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    # Anthropic bills an empty refusal, the agent falls back to Gemini, and both charges reach the rollup.
    async def scripted(_transport: object, *, url: str, **_: Any) -> HttpResponse:
        body = ANTHROPIC_REFUSAL if "anthropic" in url else GEMINI_OK
        return HttpResponse(status_code=200, body=json.dumps(body), headers={"content-type": "application/json"})

    monkeypatch.setattr(HttpTransport, "request", scripted)
    agent = Agent(name="a", system_prompt="Answer.", max_iterations=3, provider="anthropic", model_name="claude-sonnet-5", api_keys=["sk-ant-mock", GEMINI_TEST_KEY], model_mode=TextModelMode.DIRECT, fallback=[FallbackModel(provider="gemini", model="gemini-3.5-flash")])
    result = asyncio.run(agent.arun("hi"))
    rollup = agent.get_usage()

    assert "ok" in str(result.content)
    assert [(call.provider, call.model, call.failed) for call in rollup.calls] == [("anthropic", "claude-sonnet-5", True), ("gemini", "gemini-3.5-flash", False)]
    assert (rollup.calls[0].usage.input_tokens, rollup.calls[0].usage.output_tokens) == (1000, 3)
    assert rollup.unaccounted_call_count == 0
    assert all(call.cost_usd is not None and call.cost_usd > 0 for call in rollup.calls)
    assert rollup.cost_usd == pytest.approx(sum(call.cost_usd for call in rollup.calls))
    assert agent.get_cost_usd() == pytest.approx(rollup.cost_usd)
