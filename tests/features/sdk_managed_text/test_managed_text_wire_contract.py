"""FILE: tests/features/sdk_managed_text/test_managed_text_wire_contract.py

PURPOSE: Proves what a managed request carries on the wire beyond the envelope: the output-token cap in each dialect's own field, extra_body passed through untouched, the 630 s per-attempt timeout floor, and only the body keys the gateway's allowed lists accept.
ROLE IN CODEBASE: Wire-contract layer of tests/features/sdk_managed_text/ (spec INV-2, INV-9, INV-10; AC-8, AC-9, AC-26; EC-8, EC-20; NG-14). Exercises the TextModelRunner construction-time pinning in vidbyte/lib/runners/text.py and the real adapters in vidbyte/providers/.
ARCHITECTURE NOTE: Each test runs a managed call with only VIDBYTE_API_KEY set and reads the envelope the scripted inner transport received; the adapters are real, so a key the adapter emits shows up exactly as the gateway would see it.
COMMON MODIFICATION PATTERNS: When backend's allowed lists or an adapter's emitted keys change, update EMITTED_KEYS from the spec's section 9.2 table, never from the adapter's current output.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see managed_text_fixtures.py). 2. Do not compare caps with >= or <=: an explicit caller value must arrive exactly.
KNOWN EDGE CASES: A Gemini generationConfig in extra_body replaces the adapter's one, so its cap disappears by design (EC-8). TextModelConfig accepts a NaN timeout, and max(nan, 630.0) is nan. Since byok-api-keys, the vendor-direct oracle and the caller-timeout case need TextModelMode.DIRECT; a provider key in AUTO relays through the gateway and gets the floor too (INV-20).
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; docs/spec/managed-generative-models/spec.md sections 6.1 (INV-9, INV-10) and 9.2 ("Keys the SDK emits per dialect").
TESTS: python -m pytest tests/features/sdk_managed_text/test_managed_text_wire_contract.py
"""

from __future__ import annotations

import os
import re
import unittest
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import GATEWAY_URL, MANAGED_MODELS, VIDBYTE_KEY, ScriptedGateway, provider_answer
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelRunner

MANAGED_ONLY = {"VIDBYTE_API_KEY": VIDBYTE_KEY}
RELAY_HEADER = "X-Vidbyte-Provider-Key"
# byok-api-keys FR-15: oracle keys that each match their own provider (table A), so the DIRECT oracle binds the key to the provider under test.
ORACLE_KEYS = {
    ModelProvider.OPENAI: "sk-proj-" + "oracle",
    ModelProvider.ANTHROPIC: "sk-ant-" + "oracle",
    ModelProvider.GEMINI: "AQ" + "." + "o" * 40,
    ModelProvider.XAI: "xai-" + "oracle",
    ModelProvider.DEEPSEEK: "d-oracle",
    ModelProvider.KIMI: "k-oracle",
}
# The cap field each dialect uses (spec section 9.2 "Cap field per dialect").
CAP_FIELD = {
    ModelProvider.OPENAI: "max_output_tokens",
    ModelProvider.ANTHROPIC: "max_tokens",
    ModelProvider.XAI: "max_tokens",
    ModelProvider.DEEPSEEK: "max_tokens",
    ModelProvider.KIMI: "max_tokens",
}
# Spec section 9.2 "Keys the SDK emits per dialect", copied from the table, not from the adapters.
_CHAT_KEYS = frozenset({"model", "messages", "temperature", "top_p", "max_tokens", "stop", "tools", "tool_choice", "response_format", "metadata"})
EMITTED_KEYS = {
    ModelProvider.OPENAI: frozenset({"model", "input", "instructions", "temperature", "top_p", "max_output_tokens", "tools", "tool_choice", "text", "metadata"}),
    ModelProvider.ANTHROPIC: frozenset({"model", "messages", "max_tokens", "system", "temperature", "top_p", "stop_sequences", "tools", "tool_choice", "thinking", "metadata", "output_config"}),
    ModelProvider.GEMINI: frozenset({"contents", "systemInstruction", "generationConfig", "tools", "toolConfig", "safetySettings", "cachedContent", "labels"}),
    ModelProvider.XAI: _CHAT_KEYS,
    ModelProvider.DEEPSEEK: _CHAT_KEYS,
    ModelProvider.KIMI: _CHAT_KEYS,
}
GEMINI_GENERATION_CONFIG_KEYS = frozenset({"temperature", "topP", "maxOutputTokens", "responseMimeType", "responseSchema", "thinkingConfig"})
FORBIDDEN_KEYS = ("service_tier", "previous_response_id", "conversation")
CAMEL_CASE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_ANSWER_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
_TOOL_PARAMETERS = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
_FUNCTION_TOOL = {"type": "function", "function": {"name": "lookup", "description": "Find.", "parameters": _TOOL_PARAMETERS}}
# Every optional field each adapter maps, split into config fields and the call-time fields TextModelRunner.arun overrides.
_COMMON_FIELDS: dict[str, Any] = {"system": "Be brief.", "temperature": 0.3, "top_p": 0.9, "max_output_tokens": 4096, "stop_sequences": ("END",), "metadata": {"team": "sdk"}}
FULL_CONFIG: dict[ModelProvider, tuple[dict[str, Any], dict[str, Any]]] = {
    ModelProvider.OPENAI: ({"thinking_config": {"effort": "low"}}, {"tools": (_FUNCTION_TOOL,), "tool_choice": "auto"}),
    ModelProvider.ANTHROPIC: ({"thinking_config": {"type": "enabled", "budget_tokens": 1024}}, {"tools": ({"name": "lookup", "description": "Find.", "input_schema": _TOOL_PARAMETERS},), "tool_choice": {"type": "auto"}}),
    ModelProvider.GEMINI: (
        {
            "tool_config": {"functionCallingConfig": {"mode": "AUTO"}},
            "safety_settings": ({"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},),
            "cached_content": "cachedContents/abc123",
            "thinking_config": {"thinkingBudget": 512},
        },
        {"tools": ({"function_declarations": [{"name": "lookup", "description": "Find.", "parameters": _TOOL_PARAMETERS}]},)},
    ),
    ModelProvider.XAI: ({}, {"tools": (_FUNCTION_TOOL,), "tool_choice": "auto"}),
    ModelProvider.DEEPSEEK: ({}, {"tools": (_FUNCTION_TOOL,), "tool_choice": "auto"}),
    ModelProvider.KIMI: ({}, {"tools": (_FUNCTION_TOOL,), "tool_choice": "auto"}),
}


def managed_call(provider: ModelProvider, *, run_options: dict[str, Any] | None = None, **config_options: Any) -> ScriptedGateway:
    # Runs one managed call with only VIDBYTE_API_KEY set and returns what the inner transport received.
    transport = ScriptedGateway(provider_answer(provider, '{"answer": "Hi"}'))
    with patch.dict(os.environ, MANAGED_ONLY, clear=True):
        runner = TextModelRunner(TextModelConfig(provider=provider.value, model=MANAGED_MODELS[provider], **config_options), transport=transport)
        runner.run("Hi", **(run_options or {}))
    return transport


def native_body(transport: ScriptedGateway) -> dict[str, Any]:
    # The provider-native body inside the single gateway envelope.
    request = transport.requests[0]
    if request["url"] != GATEWAY_URL:
        raise AssertionError(f"expected one gateway request, got {request['url']}")
    return request["json_body"]["body"]


def byok_body(provider: ModelProvider, run_options: dict[str, Any], **config_options: Any) -> dict[str, Any]:
    # The body the same config produces vendor-direct with a provider key, as the oracle for the managed body (INV-2; byok-api-keys FR-15: DIRECT).
    from vidbyte.lib.config import TextModelMode

    transport = ScriptedGateway(provider_answer(provider, '{"answer": "Hi"}'))
    with patch.dict(os.environ, {}, clear=True):
        runner = TextModelRunner(TextModelConfig(provider=provider.value, model=MANAGED_MODELS[provider], api_keys=[ORACLE_KEYS[provider]], mode=TextModelMode.DIRECT, **config_options), transport=transport)
        runner.run("Hi", **run_options)
    if transport.requests[0]["url"] == GATEWAY_URL:
        raise AssertionError("the DIRECT oracle must go to the vendor, not the gateway")
    return transport.requests[0]["json_body"]


def cap_of(provider: ModelProvider, body: dict[str, Any]) -> object:
    # Reads the output-token cap from the dialect's own field.
    if provider is ModelProvider.GEMINI:
        return body.get("generationConfig", {}).get("maxOutputTokens")
    return body.get(CAP_FIELD[provider])


class OutputCapTests(unittest.TestCase):
    """Checks INV-9: every managed body carries a cap, the caller's own value always wins, and extra_body is never rewritten."""

    def test_managed_body_carries_the_default_cap_or_the_callers_exact_value_in_each_dialects_field(self) -> None:
        # AC-8 (a)(b): unset gives 32,768 (not Anthropic's BYOK 1,024, not absent); 100 catches max(N, 32768) and 40,000 catches min(N, 32768).
        for provider in MANAGED_MODELS:
            for requested, expected in ((None, 32768), (100, 100), (40_000, 40_000)):
                with self.subTest(provider=provider.value, max_output_tokens=requested):
                    body = native_body(managed_call(provider, max_output_tokens=requested))
                    cap = cap_of(provider, body)
                    self.assertIs(type(cap), int)
                    self.assertEqual(cap, expected)
                    self.assertNotIn("max_completion_tokens", body)

    def test_extra_body_generation_config_and_completion_cap_reach_the_gateway_unchanged(self) -> None:
        # AC-8 (c)(d), EC-8, NG-14: the SDK adds and removes nothing after the extra_body merge; the gateway decides these cases.
        gemini = managed_call(ModelProvider.GEMINI, extra_body={"generationConfig": {"temperature": 0.2}})
        self.assertEqual(len(gemini.requests), 1)
        self.assertEqual(native_body(gemini), {"contents": [{"role": "user", "parts": [{"text": "Hi"}]}], "generationConfig": {"temperature": 0.2}})
        xai = managed_call(ModelProvider.XAI, extra_body={"max_completion_tokens": 2000})
        self.assertEqual(len(xai.requests), 1)
        self.assertEqual(native_body(xai), {"model": "grok-4.5", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 32768, "max_completion_tokens": 2000})


class TimeoutFloorTests(unittest.TestCase):
    """Checks INV-10: each managed attempt waits at least 630 s, computed floor first, while BYOK keeps the caller's timeout."""

    def test_each_managed_attempt_gets_the_630_second_floor_and_a_nan_timeout_resolves_to_the_floor(self) -> None:
        # AC-9, EC-20: a 60 s client timeout would give up on a paid upstream call; max(timeout, 630.0) would leave NaN as NaN.
        for requested, expected in ((60.0, 630.0), (30.0, 630.0), (120.0, 630.0), (900.0, 900.0), (float("nan"), 630.0)):
            with self.subTest(timeout_seconds=requested):
                transport = managed_call(ModelProvider.OPENAI, timeout_seconds=requested)
                self.assertEqual([request["url"] for request in transport.requests], [GATEWAY_URL])
                self.assertEqual(transport.requests[0]["timeout_seconds"], expected)
        # byok-api-keys INV-20: a provider key beside a Vidbyte key in AUTO is relayed through the gateway, so it gets the floor too.
        from vidbyte.lib.config import TextModelMode

        relay = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-byok", **MANAGED_ONLY}, clear=True):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", timeout_seconds=30.0), transport=relay).run("Hi")
        self.assertEqual([request["url"] for request in relay.requests], [GATEWAY_URL])
        self.assertEqual(relay.requests[0]["timeout_seconds"], 630.0)
        self.assertEqual({key.lower(): value for key, value in relay.requests[0]["headers"].items()}.get(RELAY_HEADER.lower()), "sk-byok")
        # The floor must be keyed on gateway use: a DIRECT call beside a Vidbyte key keeps its own 30 s (INV-6).
        byok = ScriptedGateway(provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-byok", **MANAGED_ONLY}, clear=True):
            TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", timeout_seconds=30.0, mode=TextModelMode.DIRECT), transport=byok).run("Hi")
        self.assertEqual(byok.requests[0]["timeout_seconds"], 30.0)
        self.assertNotIn(GATEWAY_URL, [request["url"] for request in byok.requests])


class EmittedKeyTests(unittest.TestCase):
    """Checks INV-2 and AC-26: with every mapped field set, each dialect's managed body stays inside the gateway's allowed keys."""

    def test_managed_body_emits_only_the_keys_on_each_dialects_allowed_list(self) -> None:
        # AC-26: a key outside the list is a guaranteed 422 at the gateway, so the SDK must never add service_tier, a Gemini model, or snake_case Gemini keys.
        for provider, (config_fields, call_fields) in FULL_CONFIG.items():
            with self.subTest(provider=provider.value):
                messages = ({"role": "user", "content": "Earlier question"}, {"role": "assistant", "content": "Earlier answer"})
                run_options = {"messages": messages, "response_format": _ANSWER_SCHEMA, "metadata": {"run": "r1"}, **call_fields}
                body = native_body(managed_call(provider, run_options=run_options, **_COMMON_FIELDS, **config_fields))
                # The same config sent BYOK is the oracle: equality proves the body is unchanged and that every mapped field was exercised.
                self.assertEqual(body, byok_body(provider, run_options, **_COMMON_FIELDS, **config_fields))
                self.assertLessEqual(set(body), EMITTED_KEYS[provider])
                self.assertEqual(cap_of(provider, body), 4096)
                for forbidden in FORBIDDEN_KEYS:
                    self.assertNotIn(forbidden, body)
                if provider is ModelProvider.GEMINI:
                    self.assertNotIn("model", body)
                    self.assertLessEqual(set(body["generationConfig"]), GEMINI_GENERATION_CONFIG_KEYS)
                    for key in [*body, *body["generationConfig"]]:
                        self.assertRegex(key, CAMEL_CASE)
                    for tool in body["tools"]:
                        self.assertEqual(set(tool), {"function_declarations"})


if __name__ == "__main__":
    unittest.main()
