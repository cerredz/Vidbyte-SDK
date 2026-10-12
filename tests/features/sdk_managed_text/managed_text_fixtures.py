"""FILE: tests/features/sdk_managed_text/managed_text_fixtures.py

PURPOSE: Shared offline fakes and provider-shaped answer factories for the Vidbyte-managed text feature pack.
ROLE IN CODEBASE: Imported by every test module in tests/features/sdk_managed_text/. It stands in only for the HTTP boundary below TextModelRunner and for the retry wait, so TextModelConfig, ProviderModelRegistry, the provider adapters, the runner and VidbyteGatewayTransport all run unmocked.
ARCHITECTURE NOTE: ScriptedGateway records a deep copy of every inner request(...) call and answers from a script. In managed state the runner wraps it in VidbyteGatewayTransport, so it sees the gateway request; in BYOK state it sees the vendor request. Calling an instance returns itself, so it can also replace the HttpTransport class where a runner looks it up.
FUNCTION INVENTORY: ScriptedGateway.request(**kwargs) records and answers one attempt; BackoffRecorder(delay) records one retry wait and optionally cancels; provider_answer(provider, text) builds a realistic 200 per dialect; provider_usage(provider) returns the usage block that answer carries; gateway_error(status) builds a gateway "error": true body; relayed_provider_error(provider, status) builds a vendor error body whose "error" is an object; edge_page(status, body) builds a non-JSON-object answer; header(request, name) reads a recorded header case-insensitively; idempotency_key(request) returns the recorded Idempotency-Key header.
COMMON MODIFICATION PATTERNS: Add a provider to MANAGED_MODELS, provider_answer and relayed_provider_error together when the gateway starts serving it. Keep every scripted body carrying BODY_CANARY and LEAKED_KEY so credential-safety assertions stay meaningful.
WHAT NOT TO DO IN THIS FILE: 1. Do not import symbols the feature adds (TextModelMode, VidbyteGatewayTransport, the new constants) at module level: before the feature exists that would make every test module a collection error and stop the rest of the suite. 2. Do not touch the network. 3. Do not encode production logic (cap defaults, retry rules) here; tests assert those from the spec's literal values.
KNOWN EDGE CASES: The last scripted step repeats, so ScriptedGateway(gateway_error(502)) answers 502 to every attempt. Exceptions in the script are raised as-is, including BaseException subclasses such as asyncio.CancelledError.
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; docs/spec/managed-generative-models/spec.md section 9.2 (wire contract and failure mapping).
TESTS: python -m pytest tests/features/sdk_managed_text
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpResponse

# Test credentials. C020 does not scan tests/, and this mirrors tests/test_jev_managed_gateway.py:39.
VIDBYTE_KEY = "vb_live_" + "a" * 32
OTHER_VIDBYTE_KEY = "vb_live_" + "b" * 32
# A key-shaped string that a hostile or echoing gateway or provider body carries; it must never reach an error.
LEAKED_KEY = "vb_live_" + "L" * 32
# A unique token placed in every scripted body; finding it in an error means body text leaked.
BODY_CANARY = "canary-7f3a9c"

# The one gateway route (spec section 4, INV-1), spelled as a literal so a changed constant is caught.
GATEWAY_URL = "https://vidbyte-backend.onrender.com/api/v1/models/generate"
# Where the retry wait is looked up (spec section 13).
SLEEP_TARGET = "vidbyte.lib.http.vidbyte_gateway.asyncio.sleep"
# Where TextModelRunner looks up its default transport class (spec section 13).
RUNNER_TRANSPORT_TARGET = "vidbyte.lib.runners.text.HttpTransport"

# The six providers the gateway serves, each with a realistic model id (registries/models.py defaults, section 4 for openai).
MANAGED_MODELS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "gpt-5.5",
    ModelProvider.ANTHROPIC: "claude-sonnet-5",
    ModelProvider.GEMINI: "gemini-3.5-flash",
    ModelProvider.XAI: "grok-4.5",
    ModelProvider.DEEPSEEK: "deepseek-v4-pro",
    ModelProvider.KIMI: "kimi-k2.7-code",
}
# Text providers the SDK supports but the gateway does not (INV-8, NG-5).
UNMANAGED_TEXT_PROVIDERS: tuple[ModelProvider, ...] = (
    ModelProvider.OPENROUTER,
    ModelProvider.GLM,
    ModelProvider.MINIMAX,
    ModelProvider.META,
    ModelProvider.MISTRAL,
)

_REAL_SLEEP = asyncio.sleep
_CHAT_PROVIDERS = frozenset({ModelProvider.XAI, ModelProvider.DEEPSEEK, ModelProvider.KIMI})


class ScriptedGateway:
    """Inner transport stand-in: records each request and answers from a script whose last step repeats."""

    def __init__(self, *steps: HttpResponse | BaseException) -> None:
        # Keeps the scripted answers in order; a BaseException step is raised instead of answered.
        self.steps = list(steps)
        self.requests: list[dict[str, Any]] = []

    def __call__(self) -> ScriptedGateway:
        # Stands in for the HttpTransport class, so a runner that builds its own transport gets this recorder.
        return self

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Records a deep copy so later mutation by the caller cannot hide what this attempt sent.
        self.requests.append(copy.deepcopy(kwargs))
        step = self.steps[min(len(self.requests), len(self.steps)) - 1]
        if isinstance(step, BaseException):
            raise step
        return step


class BackoffRecorder:
    """Replaces asyncio.sleep for retry waits: records each delay, never waits, and can cancel on demand."""

    def __init__(self, *, cancel_with: asyncio.CancelledError | None = None) -> None:
        # Holds the delays requested so far and an optional cancellation to raise from the first wait.
        self.delays: list[float] = []
        self.cancel_with = cancel_with

    async def __call__(self, delay: float, result: object = None) -> object:
        # Yields to the event loop once, so concurrent calls genuinely interleave at the retry wait.
        self.delays.append(delay)
        if self.cancel_with is not None:
            raise self.cancel_with
        await _REAL_SLEEP(0)
        return result


def answer(status: int, payload: object) -> HttpResponse:
    # Encodes one JSON answer exactly as HttpTransport would hand it back.
    return HttpResponse(status_code=status, body=json.dumps(payload), headers={"content-type": "application/json"})


def edge_page(status: int, body: str) -> HttpResponse:
    # A hosting-edge answer whose body is not a JSON object (HTML page, empty body, array, scalar).
    return HttpResponse(status_code=status, body=body, headers={"content-type": "text/html"})


def provider_usage(provider: ModelProvider) -> dict[str, int]:
    # The usage block each dialect reports: Gemini under usageMetadata, the others under usage.
    if provider is ModelProvider.GEMINI:
        return {"promptTokenCount": 12, "candidatesTokenCount": 2, "totalTokenCount": 14}
    if provider in _CHAT_PROVIDERS:
        return {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14}
    return {"input_tokens": 12, "output_tokens": 2}


def provider_answer(provider: ModelProvider, text: str = "Hi") -> HttpResponse:
    # A realistic 200 in the provider's own response shape, as the gateway relays it.
    usage = provider_usage(provider)
    if provider is ModelProvider.OPENAI:
        payload: dict[str, Any] = {"id": "resp_1", "object": "response", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}], "usage": usage}
    elif provider is ModelProvider.ANTHROPIC:
        payload = {"id": "msg_1", "type": "message", "role": "assistant", "content": [{"type": "text", "text": text}], "usage": usage}
    elif provider is ModelProvider.GEMINI:
        payload = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}], "usageMetadata": usage}
    else:
        payload = {"id": "chatcmpl-1", "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}], "usage": usage}
    return answer(200, payload)


def gateway_error(status: int) -> HttpResponse:
    # The gateway's own error shape: top-level "error": true, a code, and a message that echoes a credential.
    return answer(status, {"error": True, "code": "model_gateway_refused", "message": f"{BODY_CANARY} echoed Bearer {LEAKED_KEY}", "request_id": "req_1"})


def relayed_provider_error(provider: ModelProvider, status: int) -> HttpResponse:
    # A vendor error relayed by the gateway; every vendor nests an object under "error", never the boolean true.
    detail = f"{BODY_CANARY} upstream said key {LEAKED_KEY}"
    if provider is ModelProvider.ANTHROPIC:
        return answer(status, {"type": "error", "error": {"type": "invalid_request_error", "message": detail}})
    if provider is ModelProvider.GEMINI:
        return answer(status, {"error": {"code": status, "message": detail, "status": "INVALID_ARGUMENT"}})
    return answer(status, {"error": {"message": detail, "type": "invalid_request_error", "param": None, "code": "rate_limit_exceeded"}})


def header(request: dict[str, Any], name: str) -> str | None:
    # HTTP header names are case-insensitive, so look one up without pinning its spelling.
    for key, value in request["headers"].items():
        if key.lower() == name.lower():
            return str(value)
    return None


def idempotency_key(request: dict[str, Any]) -> str | None:
    # The Idempotency-Key header one recorded attempt carried.
    return header(request, "Idempotency-Key")


__all__ = [
    "BODY_CANARY",
    "BackoffRecorder",
    "GATEWAY_URL",
    "LEAKED_KEY",
    "MANAGED_MODELS",
    "OTHER_VIDBYTE_KEY",
    "RUNNER_TRANSPORT_TARGET",
    "SLEEP_TARGET",
    "ScriptedGateway",
    "UNMANAGED_TEXT_PROVIDERS",
    "VIDBYTE_KEY",
    "answer",
    "edge_page",
    "gateway_error",
    "header",
    "idempotency_key",
    "provider_answer",
    "provider_usage",
    "relayed_provider_error",
]
