"""FILE: tests/features/sdk_provider_keys/provider_keys_fixtures.py

PURPOSE: Shared offline fakes for the provider-keys feature pack: runtime-built fake keys that match (or deliberately miss) each provider's key format, agent-finishing answers per dialect, a transport that answers each provider in its own dialect, and an environment that records which variables were read.
ROLE IN CODEBASE: Imported by every test module in tests/features/sdk_provider_keys/. Like tests/features/sdk_managed_text/managed_text_fixtures.py, it stands in only for the inner HTTP transport and the process environment, so ProviderKeyMatcher, ProviderKeys, TextModelConfig.credentials(), ProviderModelRegistry, the adapters, TextModelRunner and VidbyteGatewayTransport all run unmocked.
ARCHITECTURE NOTE: ProviderRouter records a deep copy of every inner request(...) call and answers by provider: a gateway request by its envelope's "provider", a vendor request by its URL. Calling an instance returns itself, so it can replace the HttpTransport class where TextModelRunner looks it up (RUNNER_TRANSPORT_TARGET). RecordingEnviron replaces os.environ and records every key read through get, [] and in.
FUNCTION INVENTORY: responses_done / anthropic_done / chat_done / done_answer(provider, text) build a 200 whose only content is an isDone tool call; ProviderRouter(answers) records and answers per provider; RecordingEnviron(values) records environment reads; flat(value) renders requests or errors as one searchable string; key_view(record) is the order-free view of a ProviderKeys record; provider_key_header(request) reads the relay header; RELAY_HEADER is the header name spelled as the wire contract fixes it.
COMMON MODIFICATION PATTERNS: Add a fake key here when a provider gains a key-format rule (spec section 9.2 table F); build it by concatenation so no full key shape sits in the tree. Add a vendor base URL to VENDOR_BASES when an agent test drives a new provider in DIRECT.
WHAT NOT TO DO IN THIS FILE: 1. Do not import symbols the feature adds (TextModelMode.DIRECT, ProviderKeyMatcher, ProviderKeys, TextCredentials, the new constants) at module level: the pack must still collect while it is red. 2. Do not write a full secret-scanner shape as one literal (AIza + 35, sk-ant-api03- + 93 + AA, T3BlbkFJ-signed OpenAI keys, vb_live_ keys); build them by concatenation at the test that needs them. 3. Do not touch the network.
KNOWN EDGE CASES: The fakes deliberately avoid each other's reserved prefixes (sk-ant-, sk-or-, sk-proj-, sk-admin-, sk-svcacct-, xai-, AIza, AQ., LLM|), so an unproven fake can bind to deepseek, kimi or mistral. ProviderRouter raises KeyError for a provider it has no answer for, which surfaces as a test failure, never as a silent pass.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 9.2 (tables F, A, R, M, G) and 13.
TESTS: python -m pytest tests/features/sdk_provider_keys
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from tests.features.sdk_managed_text.managed_text_fixtures import GATEWAY_URL, answer, header
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpResponse

# The relay header, spelled as the cross-repo wire contract fixes it (spec section 9.2 "Wire"); a renamed constant is caught.
RELAY_HEADER = "X-Vidbyte-Provider-Key"

# Proven fakes: each fully matches its spec section 9.2 table F rule, and none is a real-key shape.
K_ANTHROPIC = "sk-ant-" + "test" + "A" * 20
K_ANTHROPIC_2 = "sk-ant-" + "test" + "B" * 20
K_OPENAI = "sk-proj-" + "P" * 24
K_OPENAI_2 = "sk-proj-" + "Q" * 24
K_OPENAI_ADMIN = "sk-admin-" + "M" * 16
K_XAI = "xai-" + "X" * 24
K_OPENROUTER = "sk-or-v1-" + "R" * 24
# A Gemini fake in the AQ. form (ruling r4-1), built from parts so no literal looks like a real Gemini key.
K_GEMINI_AQ = "AQ" + "." + "x" * 40
# A Meta Model API fake (LLM|<app id>|<secret>), built from parts so no literal looks like a real Meta key.
K_META = "LLM" + "|" + "1" * 15 + "|" + "m" * 32

# Unproven fakes: no table F prefix and no reserved prefix, so only table A and unique assignment decide their owner.
K_UNPROVEN = "d-mock-" + "u" * 16
K_UNPROVEN_2 = "k-mock-" + "v" * 16
# Unproven fakes that start with sk-: openai can take them as well as deepseek, kimi and the other open providers.
K_SK_UNPROVEN = "sk-" + "s" * 32
K_SK_UNPROVEN_2 = "sk-" + "t" * 32

# Where each vendor's adapter sends a DIRECT call (vidbyte/lib/registries/models.py endpoints), spelled as literals.
VENDOR_BASES: dict[str, ModelProvider] = {
    "https://api.openai.com/": ModelProvider.OPENAI,
    "https://api.anthropic.com/": ModelProvider.ANTHROPIC,
    "https://api.x.ai/": ModelProvider.XAI,
    "https://api.deepseek.com/": ModelProvider.DEEPSEEK,
    "https://api.moonshot.ai/": ModelProvider.KIMI,
    "https://api.mistral.ai/": ModelProvider.MISTRAL,
    "https://generativelanguage.googleapis.com/": ModelProvider.GEMINI,
    "https://api.meta.ai/": ModelProvider.META,
}

_USAGE_CHAT = {"prompt_tokens": 40, "completion_tokens": 5, "total_tokens": 45}
_USAGE_MESSAGES = {"input_tokens": 40, "output_tokens": 5}


def responses_done(text: str) -> HttpResponse:
    # OpenAI Responses dialect: the model ends the run with one isDone function call.
    return answer(200, {"id": "resp_1", "object": "response", "output": [{"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": text}), "call_id": "call_1"}], "usage": _USAGE_MESSAGES})


def anthropic_done(text: str) -> HttpResponse:
    # Anthropic Messages dialect: the model ends the run with one isDone tool_use block.
    return answer(200, {"id": "msg_1", "type": "message", "role": "assistant", "content": [{"type": "tool_use", "id": "tu_1", "name": "isDone", "input": {"final_answer": text}}], "stop_reason": "tool_use", "usage": _USAGE_MESSAGES})


def chat_done(text: str) -> HttpResponse:
    # Chat-completions dialect (xai, deepseek, kimi, mistral): the model ends the run with one isDone tool call.
    tool_call = {"id": "call_1", "type": "function", "function": {"name": "isDone", "arguments": json.dumps({"final_answer": text})}}
    return answer(200, {"id": "chatcmpl-1", "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [tool_call]}, "finish_reason": "tool_calls"}], "usage": _USAGE_CHAT})


def done_answer(provider: ModelProvider, text: str) -> HttpResponse:
    # The isDone answer in the dialect the provider's adapter parses.
    if provider is ModelProvider.OPENAI:
        return responses_done(text)
    if provider is ModelProvider.ANTHROPIC:
        return anthropic_done(text)
    return chat_done(text)


class ProviderRouter:
    """Inner transport stand-in that answers each request in its provider's dialect and records it."""

    def __init__(self, answers: Mapping[ModelProvider, HttpResponse]) -> None:
        # One answer per provider; a request for any other provider raises KeyError and fails the test.
        self.answers = dict(answers)
        self.requests: list[dict[str, Any]] = []

    def __call__(self) -> ProviderRouter:
        # Stands in for the HttpTransport class, so every runner an agent builds records into this one object.
        return self

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Records a deep copy, then answers for the provider the request is for.
        self.requests.append(copy.deepcopy(kwargs))
        return self.answers[self.provider_of(kwargs)]

    @staticmethod
    def provider_of(request: Mapping[str, Any]) -> ModelProvider:
        # A gateway request names its provider in the envelope; a vendor request is known by its URL.
        if request["url"] == GATEWAY_URL:
            return ModelProvider(request["json_body"]["provider"])
        for base, provider in VENDOR_BASES.items():
            if str(request["url"]).startswith(base):
                return provider
        raise KeyError(f"no provider for URL {request['url']}")

    def for_provider(self, provider: ModelProvider) -> list[dict[str, Any]]:
        # The recorded requests one provider received, in order.
        return [request for request in self.requests if self.provider_of(request) is provider]


class RecordingEnviron(dict):  # type: ignore[type-arg]
    """A stand-in for os.environ that records every variable name read through get, [] or in."""

    def __init__(self, values: Mapping[str, str]) -> None:
        super().__init__(values)
        self.reads: list[str] = []

    def get(self, key: Any, default: Any = None) -> Any:
        self.reads.append(str(key))
        return super().get(key, default)

    def __getitem__(self, key: Any) -> Any:
        self.reads.append(str(key))
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        self.reads.append(str(key))
        return super().__contains__(key)


def flat(value: Any) -> str:
    # One searchable string for requests, errors and records, so "the key appears nowhere" is a substring check.
    return json.dumps(value, sort_keys=True, default=repr)


def key_view(record: Any) -> tuple[dict[str, str], Any, tuple[str, ...], tuple[str, ...]]:
    # The order-free meaning of a ProviderKeys record: which key each provider holds, the Vidbyte key, and the matched names.
    keys = {str(getattr(provider, "value", provider)): key for provider, key in zip(record.providers, record.keys)}
    return (
        keys,
        record.vidbyte_api_key,
        tuple(str(getattr(provider, "value", provider)) for provider in record.matched_primary),
        tuple(str(getattr(provider, "value", provider)) for provider in record.matched_others),
    )


def provider_key_header(request: dict[str, Any]) -> str | None:
    # The relay header one recorded request carried, or None.
    return header(request, RELAY_HEADER)


__all__ = [
    "K_ANTHROPIC",
    "K_ANTHROPIC_2",
    "K_GEMINI_AQ",
    "K_META",
    "K_OPENAI",
    "K_OPENAI_2",
    "K_OPENAI_ADMIN",
    "K_OPENROUTER",
    "K_SK_UNPROVEN",
    "K_SK_UNPROVEN_2",
    "K_UNPROVEN",
    "K_UNPROVEN_2",
    "K_XAI",
    "ProviderRouter",
    "RELAY_HEADER",
    "RecordingEnviron",
    "VENDOR_BASES",
    "anthropic_done",
    "chat_done",
    "done_answer",
    "flat",
    "key_view",
    "provider_key_header",
    "responses_done",
]
