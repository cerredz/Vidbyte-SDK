"""FILE: tests/features/agent_reasoning_effort/agent_reasoning_effort_fixtures.py

PURPOSE: Shared offline harness for the agent reasoning effort pack: the spec's
section 9.2 mapping table as plain test data (which values each model sends, which
ids have no row, and each provider's wire fragment), the section 8.5 refusal texts,
a recorder that stands in for HttpTransport.request and answers every vendor in its
own response shape, provider keys built at run time, and small agent builders.
ROLE IN CODEBASE: Imported by every test module in tests/features/agent_reasoning_effort/.
It replaces only the network (HttpTransport.request, or the transport handed to a
runner), so TextModelConfig, Runner, BaseAgent, AgentFallback, the provider adapters,
the usage ledger and JevAgent all run for real (spec section 13 "Real seams").
ARCHITECTURE NOTE: The oracle tables here are copied from the spec's section 9.2 text,
never from the production table, so a production row that drifts from the spec fails
a test instead of moving the oracle with it. Values are plain strings ("high"), not
ReasoningEffort members, because this module must import cleanly before the feature
exists: each test module guards the feature's own names and fails at setup instead.
FUNCTION INVENTORY: fragment(provider, value) is the section 9.2 wire fragment;
sent_cells / refused_cells / no_row_ids enumerate the table for parametrization;
capability_reason / no_row_reason / mode_reason / guard_text build the section 8.5
texts; deep_merge is the test's own oracle for "the fragment is deep-merged";
nested_keys lists every key of a body; Wire records requests and answers each vendor;
StreamWire records streaming requests; provider_key builds a key that matches its
provider; clear_provider_environment removes every real key; direct_agent builds a
DIRECT BaseAgent; run_agent and first_request drive one reply through the wire.
COMMON MODIFICATION PATTERNS: When the spec's section 9.2 table gains a sourced row,
add it to SENT or NO_ROW here from the spec's text, never from the implementation.
A new provider adds its key builder, its reply shape in Wire, and its fragment rule.
WHAT NOT TO DO IN THIS FILE: 1. Do not import ReasoningEffort, ReasoningEffortRegistry
or any other name the feature adds at module level; the whole pack would stop
collecting. 2. Do not write a key-shaped literal; the repository is public and has
GH013 push protection, so every key is assembled from parts at run time. 3. Do not copy
REASONING_EFFORT_AS_OF as a literal date; tests read it from the module. 4. Do not
reach the network.
KNOWN EDGE CASES: The gpt-5.6 line is an alias of gpt-5.6-sol, so tests check it
through ReasoningEffortRegistry.supported and the wire, not as its own table key.
Wire answers TypeSafe decision calls with HTTP 500 by default; JevAgent's gates fail
open on a decision outage, so the main agent still runs and both requests are seen.
A status other than 200 for a vendor URL makes the adapter raise ProviderRequestError,
which is how fallback hops and single-request Jev children are driven.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 8.5, 9.2 and 13;
tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import pytest

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.enums import TextModelMode
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.http import HttpResponse, HttpTransport

# The six values, in the enum order every refusal lists them (spec FR-1, INV-8).
ENUM_ORDER: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh")
PROVIDERS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "xai",
    "glm",
    "meta",
)

# Spec section 9.2 mapping table: every "sent" cell, per model id, in enum order.
_OPENAI_ALL_BUT_MINIMAL = ("none", "low", "medium", "high", "xhigh")
_OPENAI_LOW_UP = ("low", "medium", "high", "xhigh")
_OPENAI_PRO = ("medium", "high", "xhigh")
_ANTHROPIC_LOW_UP = ("low", "medium", "high", "xhigh")
_ANTHROPIC_ALL = ("none", "low", "medium", "high", "xhigh")
_GEMINI_LEVELS = ("minimal", "low", "medium", "high")
_GEMINI_LOW_UP = ("low", "medium", "high")
_MUSE = ("minimal", "low", "medium", "high")
SENT: dict[str, dict[str, tuple[str, ...]]] = {
    "openai": {
        "gpt-5.6-sol": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.6": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.6-terra": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.6-luna": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-6-sol": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-6-luna": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-6.1-sol": _OPENAI_LOW_UP,
        "gpt-6-astra": _OPENAI_LOW_UP,
        "gpt-5.5": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.5-pro": _OPENAI_PRO,
        "gpt-5.4": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.4-mini": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.4-nano": _OPENAI_ALL_BUT_MINIMAL,
        "gpt-5.4-pro": _OPENAI_PRO,
        "gpt-5.3-codex": _OPENAI_LOW_UP,
        "gpt-5": ("minimal", "low", "medium", "high"),
    },
    "anthropic": {
        "claude-opus-5-5": _ANTHROPIC_LOW_UP,
        "claude-sonnet-5-5": _ANTHROPIC_LOW_UP,
        "claude-fable-5-1": _ANTHROPIC_LOW_UP,
        "claude-mythos-5-1": _ANTHROPIC_LOW_UP,
        "claude-fable-5": _ANTHROPIC_LOW_UP,
        "claude-mythos-5": _ANTHROPIC_LOW_UP,
        "claude-opus-5": _ANTHROPIC_ALL,
        "claude-haiku-5-5": _ANTHROPIC_ALL,
        "claude-sonnet-5": _ANTHROPIC_ALL,
        "claude-opus-4-8": _ANTHROPIC_ALL,
        "claude-haiku-4-5": ("none",),
        "claude-haiku-4-5-20251001": ("none",),
    },
    "gemini": {
        "gemini-3.8-flash": _GEMINI_LOW_UP,
        "gemini-3.6-flash": _GEMINI_LEVELS,
        "gemini-3.5-flash": _GEMINI_LEVELS,
        "gemini-3.5-flash-lite": _GEMINI_LEVELS,
        "gemini-3.1-flash-lite": _GEMINI_LEVELS,
        "gemini-3-flash-preview": _GEMINI_LEVELS,
        "gemini-3.1-pro-preview": _GEMINI_LOW_UP,
        "gemini-2.5-flash": ("none",),
        "gemini-2.5-flash-lite": ("none",),
    },
    "deepseek": {
        "deepseek-v4-pro": ("none", "low", "high"),
        "deepseek-flash": ("none", "low", "high"),
        "deepseek-v4-flash": ("none", "low", "high"),
    },
    "xai": {
        "grok-4.7": ("low", "medium", "high", "xhigh"),
        "grok-4.6": ("low", "medium", "high", "xhigh"),
        "grok-4.5": ("low", "medium", "high"),
        "grok-4.3": ("none", "low", "medium", "high"),
    },
    "glm": {
        "glm-5.2": ("none", "high"),
        "glm-5.3": ("low", "high"),
        "glm-5.3-flash": ("low", "high"),
        "glm-5.3-flashx": ("low", "high"),
    },
    "meta": {
        "muse-spark-1.1": _MUSE,
        "muse-spark-1.2": _MUSE,
        "muse-spark-1.2-contributor": _MUSE,
        "muse-spark-1.3": _MUSE,
        "muse-spark-1.3-contributor": _MUSE,
    },
}
# Spec section 9.2 lines that alias another line rather than holding a row of their own.
ALIASES: dict[tuple[str, str], str] = {("openai", "gpt-5.6"): "gpt-5.6-sol"}

# Ids with no row: the section 9.2 "refused (all)" lines, the ids the runner's prefix
# map builds without a row (NG-14, EC-10), and providers with no wire form at all.
NO_ROW: tuple[tuple[str, str], ...] = (
    ("openai", "o1"),
    ("openai", "o3"),
    ("openai", "o4-mini"),
    ("openai", "gpt-5-mini"),
    ("openai", "gpt-5-nano"),
    ("openai", "gpt-4o"),
    ("openai", "gpt-4.1"),
    ("openai", "gpt-4"),
    ("openai", "gpt-4o-mini"),
    ("openai", "gpt-4.1-mini"),
    ("openai", "gpt-4.1-nano"),
    ("openai", "gpt-5.5-2026-04-23"),
    ("anthropic", "claude-mythos-preview"),
    ("anthropic", "claude-3-5-sonnet-latest"),
    ("anthropic", "claude-opus-4-7"),
    ("gemini", "gemini-2.5-pro"),
    ("gemini", "gemini-3.5-flash-001"),
    ("deepseek", "deepseek-chat"),
    ("deepseek", "deepseek-reasoner"),
    ("xai", "grok-4.5-latest"),
    ("xai", "grok-4"),
    ("xai", "grok-3"),
    ("xai", "grok-4-fast-reasoning"),
    ("xai", "grok-4-fast-non-reasoning"),
    ("xai", "grok-code-fast-1"),
    ("xai", "grok-build-latest"),
    ("glm", "glm-5.1"),
    ("glm", "glm-5-turbo"),
    ("glm", "glm-4.7"),
    ("glm", "glm-4.7-flash"),
    ("glm", "glm-4.7-flashx"),
    ("glm", "glm-4.6"),
    ("glm", "glm-4"),
    ("kimi", "kimi-k2.7-code"),
    ("openrouter", "anthropic/claude-sonnet-5"),
)

# One sent model and value per provider, for agent-level wire tests.
REPRESENTATIVE: dict[str, tuple[str, str]] = {
    "openai": ("gpt-5.5", "high"),
    "anthropic": ("claude-sonnet-5", "high"),
    "gemini": ("gemini-3.5-flash", "high"),
    "deepseek": ("deepseek-v4-pro", "high"),
    "xai": ("grok-4.7", "high"),
    "glm": ("glm-5.2", "high"),
    "meta": ("muse-spark-1.1", "high"),
}
# Providers the Vidbyte gateway serves (AUTO and VIDBYTE_MANAGED route through it).
GATEWAY_PROVIDERS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "xai",
)

GATEWAY_URL = "https://vidbyte-backend.onrender.com/api/v1/models/generate"
REGISTRIES_README_POINTER = (
    '(see "Reasoning Effort Sources" in vidbyte/lib/registries/README.md)'
)


def fragment(provider: str, value: str) -> dict[str, Any]:
    """The section 9.2 "Wire form" fragment one sent cell adds to the vendor body."""
    if provider == "openai":
        return {"reasoning": {"effort": value}}
    if provider == "anthropic":
        return (
            {"thinking": {"type": "disabled"}}
            if value == "none"
            else {"output_config": {"effort": value}}
        )
    if provider == "gemini":
        thinking = (
            {"thinkingBudget": 0}
            if value == "none"
            else {"thinkingLevel": value.upper()}
        )
        return {"generationConfig": {"thinkingConfig": thinking}}
    if provider == "glm":
        if value == "none":
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"}, "reasoning_effort": value}
    if provider in ("deepseek", "xai", "meta"):
        return {"reasoning_effort": value}
    raise AssertionError(f"section 9.2 has no wire form for {provider}")


def sent_cells() -> list[tuple[str, str, str]]:
    """Every (provider, model, value) the section 9.2 table marks "sent"."""
    return [
        (provider, model, value)
        for provider, rows in SENT.items()
        for model, values in rows.items()
        for value in values
    ]


def refused_cells() -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Every "refused" cell on a line that also has a "sent" cell, with that line's sent values."""
    return [
        (provider, model, value, values)
        for provider, rows in SENT.items()
        for model, values in rows.items()
        for value in ENUM_ORDER
        if value not in values
    ]


def cell_id(*parts: object) -> str:
    """A readable pytest id such as openai:gpt-5.5:high."""
    return ":".join(str(part) for part in parts if not isinstance(part, tuple))


def capability_reason(
    provider: str, model: str, value: str, supported: Sequence[str]
) -> str:
    """Section 8.5 "registry, capability" text (no trailing period)."""
    return f"{provider}:{model.strip()} has no documented form for reasoning effort '{value}' (it supports {', '.join(supported)})"


def no_row_reason(provider: str, model: str, value: str, as_of: str) -> str:
    """Section 8.5 "registry, no row" text (no trailing period); as_of is read from the module by the caller."""
    return f"{provider}:{model.strip()} is not in the SDK's reasoning-effort table, so reasoning effort '{value}' cannot be sent to it; the table was checked against vendor docs on {as_of} {REGISTRIES_README_POINTER}"


def mode_reason(mode_name: str) -> str:
    """Section 8.5 "registry, mode" text (no trailing period)."""
    return f"TextModelMode.{mode_name} sends calls through the Vidbyte gateway, which does not accept a reasoning effort; only TextModelMode.DIRECT sends it"


def guard_text(agent_name: str, *reasons: str) -> str:
    """Section 8.5 "BaseAgent (guard)" text: the unique reasons in chain order, joined by '; '."""
    return f"Agent {agent_name} sets reasoning_effort, but {'; '.join(reasons)}."


def identity_text(agent_name: str) -> str:
    """Section 8.5 "BaseAgent (guard), no identity" text."""
    return f"Agent {agent_name} sets reasoning_effort, but it does not name both a provider and a model_name, so the effort cannot be checked against a model."


def bad_value_text(field_name: str, value: object) -> str:
    """Section 8.5 "bad value" text: the existing RecordFieldConverter.to_enum message for the six values."""
    return f"{field_name} must be one of {', '.join(ENUM_ORDER)}; got {value!r}."


def deep_merge(base: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    """The test's own oracle for a deep merge: nested mappings merge key by key, any other value replaces."""
    merged = copy.deepcopy(dict(base))
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def nested_keys(value: object) -> set[str]:
    """Every mapping key anywhere inside a JSON-like value."""
    if isinstance(value, Mapping):
        return set(value) | {
            key for item in value.values() for key in nested_keys(item)
        }
    if isinstance(value, (list, tuple)):
        return {key for item in value for key in nested_keys(item)}
    return set()


def provider_key(provider: str) -> str:
    """A key that matches its provider's documented shape, assembled at run time (never a literal)."""
    secret = "effortprobe" + "Q" * 16
    shapes = {
        "openai": "sk-" + "proj-" + secret,
        "anthropic": "sk-" + "ant-" + secret,
        "gemini": "AQ" + "." + secret,
        "xai": "xai" + "-" + secret,
        "meta": "LLM" + "_" + "4242" + "_" + secret,
        "openrouter": "sk-" + "or-" + secret,
    }
    # DeepSeek, GLM and Kimi document no prefix, so any key without a reserved prefix matches them.
    return shapes.get(provider, provider + "probe" + secret)


def provider_keys(*providers: str) -> list[str]:
    """One run-time key per provider, in the order given."""
    return [provider_key(provider) for provider in providers]


VIDBYTE_KEY = "vb_live_" + "e" * 32


def clear_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removes every real provider key and the Vidbyte key, so only keys a test passes are used."""
    for name in list(os.environ):
        if name.endswith("_API_KEY"):
            monkeypatch.delenv(name, raising=False)


def usage_for(dialect: str) -> dict[str, Any]:
    """A plain usage block in each dialect's own shape."""
    if dialect == "openai":
        return {"input_tokens": 40, "output_tokens": 6}
    if dialect == "anthropic":
        return {"input_tokens": 40, "output_tokens": 6}
    if dialect == "gemini":
        return {
            "promptTokenCount": 40,
            "candidatesTokenCount": 6,
            "totalTokenCount": 46,
        }
    return {"prompt_tokens": 40, "completion_tokens": 6, "total_tokens": 46}


def dialect_of(url: str) -> str:
    """Which response shape a vendor URL answers in."""
    if url.endswith("/responses"):
        return "openai"
    if url.endswith("/messages"):
        return "anthropic"
    if ":generateContent" in url:
        return "gemini"
    return "chat"


def reply_body(dialect: str, text: str, usage: Mapping[str, Any]) -> dict[str, Any]:
    """A realistic 200 body in one dialect's response shape."""
    if dialect == "openai":
        return {
            "id": "resp_1",
            "object": "response",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": dict(usage),
        }
    if dialect == "anthropic":
        return {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
            "usage": dict(usage),
        }
    if dialect == "gemini":
        return {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": text}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": dict(usage),
        }
    return {
        "id": "chatcmpl-1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
        "usage": dict(usage),
    }


def _json(status: int, payload: object) -> HttpResponse:
    return HttpResponse(
        status_code=status,
        body=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


class Wire:
    """Stands in for HttpTransport.request: records every request and answers each vendor in its own shape.

    `fail` maps a URL prefix to an HTTP status; a matching request is answered with a vendor error body.
    `usage` maps a dialect (openai, anthropic, gemini, chat) to the usage block its replies carry.
    """

    def __init__(
        self,
        *,
        fail: Mapping[str, int] | None = None,
        usage: Mapping[str, Mapping[str, Any]] | None = None,
        text: str = "Done.",
    ) -> None:
        self.fail = dict(fail or {})
        self.usage = {key: dict(value) for key, value in (usage or {}).items()}
        self.text = text
        self.requests: list[dict[str, Any]] = []

    @property
    def urls(self) -> list[str]:
        return [request["url"] for request in self.requests]

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [request["json_body"] for request in self.requests]

    def vendor_requests(self) -> list[dict[str, Any]]:
        """Requests to a model vendor or the generate route, without Jev decision and run-close calls."""
        return [
            request
            for request in self.requests
            if "/models/typesafe/" not in request["url"]
            and "/models/runs/" not in request["url"]
        ]

    def decision_requests(self) -> list[dict[str, Any]]:
        """Requests to the TypeSafe decision route."""
        return [
            request
            for request in self.requests
            if "/models/typesafe/" in request["url"]
        ]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> Wire:
        """Replaces HttpTransport.request for the test; a callable instance is not a descriptor, so no transport argument arrives."""
        monkeypatch.setattr(HttpTransport, "request", self)
        return self

    async def __call__(self, **kwargs: Any) -> HttpResponse:
        return await self.request(**kwargs)

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Records a deep copy, so later mutation by the caller cannot hide what this request sent.
        recorded = copy.deepcopy(kwargs)
        recorded["json_body"] = recorded.get("json_body") or {}
        self.requests.append(recorded)
        url = str(kwargs["url"])
        status = next(
            (code for prefix, code in self.fail.items() if url.startswith(prefix)), None
        )
        if "/models/typesafe/" in url:
            return _json(
                status or 500,
                {
                    "error": True,
                    "code": "decision_unavailable",
                    "message": "scripted outage",
                },
            )
        if "/models/runs/" in url:
            return _json(200, {})
        if status is not None:
            return _json(
                status,
                {
                    "error": {
                        "message": "scripted failure",
                        "type": "server_error",
                        "code": "scripted",
                    }
                },
            )
        dialect = (
            self._gateway_dialect(recorded["json_body"])
            if url == GATEWAY_URL
            else dialect_of(url)
        )
        return _json(
            200,
            reply_body(dialect, self.text, self.usage.get(dialect, usage_for(dialect))),
        )

    @staticmethod
    def _gateway_dialect(envelope: Mapping[str, Any]) -> str:
        # The gateway relays the provider's own answer, so answer in the shape of the provider the envelope names.
        provider = str(envelope.get("provider", ""))
        return provider if provider in ("openai", "anthropic", "gemini") else "chat"


class StreamWire:
    """Stands in for SyncHttpTransport: records each streaming request and yields no events."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def stream_request(self, **kwargs: Any) -> Iterator[str]:
        self.requests.append(copy.deepcopy(kwargs))
        return iter(())


def direct_agent(
    provider: str,
    model: str,
    *,
    name: str = "planner",
    keys: Sequence[str] | None = None,
    **options: Any,
) -> BaseAgent:
    """A DIRECT BaseAgent on (provider, model) holding a run-time key for that provider."""
    return BaseAgent(
        name=name,
        system_prompt="Plan database migrations.",
        provider=provider,
        model_name=model,
        api_keys=list(keys) if keys is not None else [provider_key(provider)],
        model_mode=TextModelMode.DIRECT,
        **options,
    )


def run_agent(
    agent: BaseAgent, prompt: str = "Plan a zero-downtime rename of users.email."
) -> None:
    """Runs one reply; a scripted vendor failure that ends the run is expected by some tests and swallowed."""
    try:
        agent.run(prompt)
    except VidbyteSdkError:
        pass


def first_request(
    wire: Wire,
    agent: BaseAgent,
    prompt: str = "Plan a zero-downtime rename of users.email.",
) -> dict[str, Any]:
    """Runs one reply and returns the first request it sent to a model vendor."""
    start = len(wire.requests)
    run_agent(agent, prompt)
    sent = [
        request
        for request in wire.requests[start:]
        if request in wire.vendor_requests()
    ]
    assert sent, f"{agent.name} sent no model request"
    return sent[0]


__all__ = [
    "ALIASES",
    "ENUM_ORDER",
    "GATEWAY_PROVIDERS",
    "GATEWAY_URL",
    "NO_ROW",
    "PROVIDERS",
    "REGISTRIES_README_POINTER",
    "REPRESENTATIVE",
    "SENT",
    "VIDBYTE_KEY",
    "StreamWire",
    "Wire",
    "bad_value_text",
    "capability_reason",
    "cell_id",
    "clear_provider_environment",
    "deep_merge",
    "dialect_of",
    "direct_agent",
    "first_request",
    "fragment",
    "guard_text",
    "identity_text",
    "mode_reason",
    "nested_keys",
    "no_row_reason",
    "provider_key",
    "provider_keys",
    "refused_cells",
    "reply_body",
    "run_agent",
    "sent_cells",
    "usage_for",
]
