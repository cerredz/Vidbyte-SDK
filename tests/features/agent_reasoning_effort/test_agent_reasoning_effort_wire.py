"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_wire.py

PURPOSE: Prove on the HTTP seam that every "sent" cell of the spec's section 9.2 table
adds exactly its fragment to the vendor body, deep-merged, with the URL, headers and
key unchanged: through TextModelConfig and each of the four payload builders, through
an agent on each provider, through the streaming builders, through Runner from the
keyword or from options, through a fallback chain whose hops each send their own
form, through a context-window algorithm that reuses the agent's own runner, beside
Anthropic structured output, Gemini temperature and schema, and a disjoint
extra_body; and that thinking_config without an effort is forwarded as before.
ROLE IN CODEBASE: Covers spec AC-2, AC-3, AC-6 (capable chain), AC-7 (disjoint
extra_body), AC-14, AC-15, AC-18 (agent level), AC-20, AC-24, AC-26, AC-29, EC-6,
EC-21, EC-28, EC-30, EC-35, INV-2, INV-9, INV-17, FR-4 and FR-5 for
vidbyte/providers/{openai,anthropic,gemini,compatible}.py,
vidbyte/lib/runners/utility.py, vidbyte/agents/base.py and vidbyte/agents/fallback.py.
ARCHITECTURE NOTE: The only fake is the transport (Wire, or StreamWire for streams);
TextModelConfig, the runners, the adapters, BaseAgent and AgentFallback are real.
Every expectation is the metamorphic identity body(effort) ==
deep_merge(body(unset), fragment), with both bodies built in the same test, so no
golden body is stored and an unrelated adapter change cannot turn this red.
FUNCTION INVENTORY: _config builds a DIRECT TextModelConfig with a run-time key;
_one_call sends one call through TextModelRunner and returns its request;
_one_stream does the same through StreamingTextModelRunner; _first_vendor_request
runs an agent once; _runner_call builds an openai/gpt-5.5 Runner and sends one call;
the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new provider adds its fragment rule and reply shape in
the fixtures; the sweep picks up every SENT row by itself.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare against a stored body. 2. Do not bind a
ScriptedRunner; it bypasses the adapters and cannot see the fragment. 3. Do not write
a key-shaped literal. 4. Do not import a feature name outside the FEATURE_MISSING guard.
KNOWN EDGE CASES: The gpt-5.6 alias is sent with the alias as the body's model and
gpt-5.6-sol's support. Anthropic's none form is "thinking" alone, so a disjoint
extra_body may set "thinking" only beside a level that uses output_config. The built
config is read through TextModelRunner._config, which has no public accessor
(tests/features/sdk_provider_keys reads it the same way).
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.1 INV-2, INV-9,
INV-17, 6.2 AC-2, AC-3, AC-6, AC-7, AC-14, AC-15, AC-20, AC-24, AC-26, AC-29, 6.3
EC-30, EC-35, 9.2 and 13;
tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_wire.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    ALGORITHM_REPLIES,
    NON_TEXT_MODELS,
    OWN_MODEL_ALGORITHMS,
    PROVIDERS,
    REPRESENTATIVE,
    StreamWire,
    Wire,
    cell_id,
    clear_provider_environment,
    deep_merge,
    direct_agent,
    first_request,
    fragment,
    provider_key,
    provider_keys,
    sent_cells,
)
from vidbyte.agents import FallbackModel
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.model_configs import TextModelConfig
from vidbyte.lib.enums import TextModelMode
from vidbyte.lib.runners.streaming_text import StreamingTextModelRunner
from vidbyte.lib.runners.text import TextModelRunner
from vidbyte.lib.runners.utility import Runner

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.lib.enums import ReasoningEffort
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

PROMPT = "Plan a zero-downtime rename of users.email."
SYSTEM = "Plan database migrations."
SCHEMA = {
    "type": "object",
    "properties": {"plan": {"type": "string"}},
    "required": ["plan"],
}
SENT_CELLS = sent_cells()
# A disjoint extra_body per provider shape (AC-7): none of its keys is a fragment key.
DISJOINT_EXTRA = (
    ("openai", "gpt-5.5", "low", {"service_tier": "flex", "store": False}),
    (
        "anthropic",
        "claude-sonnet-5",
        "high",
        {"thinking": {"type": "adaptive"}, "top_k": 5},
    ),
    ("gemini", "gemini-3.5-flash", "medium", {"labels": {"team": "data"}}),
    ("deepseek", "deepseek-v4-pro", "high", {"user": "migration-bot"}),
    ("glm", "glm-5.3", "low", {"do_sample": False}),
)


@pytest.fixture(autouse=True)
def _feature_present(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_environment(monkeypatch)
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _config(provider: str, model: str, **options: Any) -> TextModelConfig:
    return TextModelConfig(
        provider=provider,
        model=model,
        api_keys=[provider_key(provider)],
        mode=TextModelMode.DIRECT,
        **options,
    )


def _one_call(config: TextModelConfig) -> dict[str, Any]:
    # One call through the real runner and adapter; the wire is the transport.
    wire = Wire(text='{"plan": "Add the column, backfill, swap."}')
    TextModelRunner(config, transport=wire).run(PROMPT, system=SYSTEM)
    (request,) = wire.requests
    return request


def _one_stream(config: TextModelConfig) -> dict[str, Any]:
    wire = StreamWire()
    list(StreamingTextModelRunner(config, transport=wire).stream(PROMPT, system=SYSTEM))
    (request,) = wire.requests
    return request


def _first_vendor_request(
    monkeypatch: pytest.MonkeyPatch, agent: BaseAgent
) -> dict[str, Any]:
    wire = Wire(text='{"plan": "Add the column, backfill, swap."}').install(monkeypatch)
    return first_request(wire, agent, PROMPT)


def _runner_call(**options: Any) -> tuple[Any, dict[str, Any]]:
    # One DIRECT openai/gpt-5.5 call through Runner.build; returns the runner and its request.
    wire = Wire()
    runner = Runner(
        provider="openai",
        model_name="gpt-5.5",
        api_keys=[provider_key("openai")],
        model_mode=TextModelMode.DIRECT,
        **options,
    ).build(transport=wire)
    runner.run(PROMPT, system=SYSTEM)
    (request,) = wire.requests
    return runner, request


def _same_route(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    # INV-9: the effort never changes the endpoint, the headers, or the key they carry.
    assert (left["method"], left["url"], left["headers"]) == (
        right["method"],
        right["url"],
        right["headers"],
    )


@pytest.mark.parametrize(
    ("provider", "model", "value"),
    SENT_CELLS,
    ids=[cell_id(*cell) for cell in SENT_CELLS],
)
def test_each_sent_cell_adds_exactly_its_fragment_to_the_vendor_body(
    provider: str, model: str, value: str
) -> None:
    # AC-2, AC-3, AC-20, INV-2, FR-4: every builder attaches; the value
    # is spelled as the vendor documents it (Gemini upper case), never
    # remapped, and nothing else in the body moves.
    unset = _one_call(_config(provider, model))
    effort = _one_call(
        _config(provider, model, reasoning_effort=ReasoningEffort(value))
    )

    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment(provider, value)
    )
    _same_route(effort, unset)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_agent_sends_its_own_providers_fragment_and_nothing_else(
    provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-2, AC-20, INV-9: the agent path (BaseAgent, Runner, the config)
    # reaches the same identity; no key enters the body.
    model, value = REPRESENTATIVE[provider]
    unset = _first_vendor_request(monkeypatch, direct_agent(provider, model))
    effort = _first_vendor_request(
        monkeypatch,
        direct_agent(provider, model, reasoning_effort=ReasoningEffort(value)),
    )

    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment(provider, value)
    )
    _same_route(effort, unset)
    assert provider_key(provider) not in json.dumps(effort["json_body"])


def test_anthropic_structured_output_keeps_its_format_beside_the_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-14, EC-6, D-7: _attach_response_format assigns output_config
    # whole, so only a deep merge after it keeps both keys.
    unset = _first_vendor_request(
        monkeypatch, direct_agent("anthropic", "claude-sonnet-5", output_schema=SCHEMA)
    )
    effort = _first_vendor_request(
        monkeypatch,
        direct_agent(
            "anthropic",
            "claude-sonnet-5",
            output_schema=SCHEMA,
            reasoning_effort=ReasoningEffort.HIGH,
        ),
    )

    assert "format" in unset["json_body"]["output_config"]
    assert effort["json_body"]["output_config"] == {
        **unset["json_body"]["output_config"],
        "effort": "high",
    }
    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment("anthropic", "high")
    )


@pytest.mark.parametrize(
    ("model", "value", "thinking"),
    [
        ("gemini-3.5-flash", "low", {"thinkingLevel": "LOW"}),
        ("gemini-2.5-flash", "none", {"thinkingBudget": 0}),
    ],
)
def test_gemini_keeps_temperature_and_schema_beside_the_thinking_config(
    model: str, value: str, thinking: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-15, D-7: _attach_generation_config builds generationConfig, so
    # only a deep merge after it keeps temperature and the schema.
    unset = _first_vendor_request(
        monkeypatch,
        direct_agent("gemini", model, temperature=0.3, output_schema=SCHEMA),
    )
    effort = _first_vendor_request(
        monkeypatch,
        direct_agent(
            "gemini",
            model,
            temperature=0.3,
            output_schema=SCHEMA,
            reasoning_effort=ReasoningEffort(value),
        ),
    )

    generation = effort["json_body"]["generationConfig"]
    assert generation == {
        **unset["json_body"]["generationConfig"],
        "thinkingConfig": thinking,
    }
    assert generation["temperature"] == 0.3


@pytest.mark.parametrize(
    ("provider", "model", "value", "extra_body"),
    DISJOINT_EXTRA,
    ids=[cell_id(*case[:3]) for case in DISJOINT_EXTRA],
)
def test_a_disjoint_extra_body_is_sent_beside_the_fragment(
    provider: str, model: str, value: str, extra_body: dict[str, Any]
) -> None:
    # AC-7: an extra_body that shares no top-level key with the fragment
    # is accepted, and both reach the vendor.
    unset = _one_call(_config(provider, model, extra_body=extra_body))
    effort = _one_call(
        _config(
            provider,
            model,
            extra_body=extra_body,
            reasoning_effort=ReasoningEffort(value),
        )
    )

    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment(provider, value)
    )
    assert all(effort["json_body"][key] == extra_body[key] for key in extra_body)


@pytest.mark.parametrize(
    ("provider", "model", "value"),
    [
        ("openai", "gpt-5.5", "medium"),
        ("anthropic", "claude-sonnet-5", "low"),
        ("anthropic", "claude-opus-5", "none"),
    ],
)
def test_a_stream_carries_the_same_fragment(
    provider: str, model: str, value: str
) -> None:
    # Section 9.2 "Every agent": the stream builders reuse the payload
    # builders, so a streaming call carries the fragment too.
    unset = _one_stream(_config(provider, model))
    effort = _one_stream(
        _config(provider, model, reasoning_effort=ReasoningEffort(value))
    )

    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment(provider, value)
    )
    _same_route(effort, unset)


def test_runner_build_hands_the_effort_to_the_text_config() -> None:
    # FR-5: Runner._config_options_for passes the effort to a text
    # config; dropping it there would silently send nothing.
    def runner_call(**options: Any) -> dict[str, Any]:
        wire = Wire()
        runner = Runner(
            provider="xai",
            model_name="grok-4.7",
            api_keys=[provider_key("xai")],
            model_mode=TextModelMode.DIRECT,
            **options,
        ).build(transport=wire)
        runner.run(PROMPT, system=SYSTEM)
        (request,) = wire.requests
        return request

    unset, effort = runner_call(), runner_call(reasoning_effort=ReasoningEffort.XHIGH)

    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment("xai", "xhigh")
    )


def test_an_options_effort_reaches_the_text_config_and_the_wire() -> None:
    # AC-26, FR-5, INV-3, review R-3: options["reasoning_effort"] is a
    # TextModelConfig field, so Runner hands it on as it does the keyword;
    # an unset keyword must not overwrite it with None.
    _, unset = _runner_call()
    runner, effort = _runner_call(options={"reasoning_effort": "high"})

    assert runner._config.reasoning_effort is ReasoningEffort.HIGH
    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment("openai", "high")
    )
    _same_route(effort, unset)


def test_the_keyword_effort_wins_over_an_options_effort() -> None:
    # AC-29, FR-5: with both set, the keyword wins, as temperature's does,
    # so only the keyword's fragment reaches the vendor.
    _, unset = _runner_call()
    runner, both = _runner_call(
        reasoning_effort=ReasoningEffort.LOW, options={"reasoning_effort": "high"}
    )

    assert runner._config.reasoning_effort is ReasoningEffort.LOW
    assert both["json_body"] == deep_merge(
        unset["json_body"], fragment("openai", "low")
    )


def test_an_options_effort_of_none_is_unset_on_every_runner_type() -> None:
    # EC-35, INV-1: None in options means unset, like the keyword's
    # default: the text body is the body without it, and no non-text
    # runner is refused.
    _, unset = _runner_call()
    runner, none = _runner_call(options={"reasoning_effort": None})
    built = [
        Runner(
            provider="openai",
            model_name=model,
            api_keys=[provider_key("openai")],
            options={"reasoning_effort": None},
        ).build()
        for model, _ in NON_TEXT_MODELS
    ]

    assert runner._config.reasoning_effort is None
    assert none["json_body"] == unset["json_body"]
    assert "reasoning" not in none["json_body"]
    assert len(built) == len(NON_TEXT_MODELS)
    assert None not in built


@pytest.mark.parametrize(
    ("key", "algorithm", "calls"),
    [case[1:] for case in OWN_MODEL_ALGORITHMS],
    ids=[case[0] for case in OWN_MODEL_ALGORITHMS],
)
def test_an_algorithm_on_the_agents_own_runner_sends_the_effort_on_every_call(
    key: str, algorithm: object, calls: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-24, EC-30, INV-2, D-19: the critic without a reviewer and the
    # debate without stage models reuse the agent's own runner, so they
    # are not refused, and every model call of the run carries the effort.
    def run_requests(**options: Any) -> list[dict[str, Any]]:
        wire = Wire(text=ALGORITHM_REPLIES[key]).install(monkeypatch)
        direct_agent("openai", "gpt-5.5", algorithm=algorithm, **options).run(PROMPT)
        return wire.vendor_requests()

    unset = run_requests()
    effort = run_requests(reasoning_effort=ReasoningEffort.HIGH)

    assert len(effort) == len(unset) == calls
    for sent, plain in zip(effort, unset, strict=True):
        assert sent["json_body"] == deep_merge(
            plain["json_body"], fragment("openai", "high")
        )
        _same_route(sent, plain)


def test_a_chain_that_can_take_the_value_sends_each_hops_own_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-6, INV-2, D-6: every hop's runner gets the effort, in that
    # hop's provider form; the first two hops fail so all three are sent.
    chain = (
        ("anthropic", "claude-sonnet-5"),
        ("gemini", "gemini-3.5-flash"),
        ("openai", "gpt-5.5"),
    )
    keys = provider_keys("anthropic", "gemini", "openai")
    fallback = [FallbackModel(provider, model) for provider, model in chain[1:]]

    def hop_requests(**options: Any) -> list[dict[str, Any]]:
        wire = Wire(
            fail={
                "https://api.anthropic.com": 500,
                "https://generativelanguage.googleapis.com": 500,
            }
        ).install(monkeypatch)
        first_request(
            wire,
            direct_agent(*chain[0], keys=keys, fallback=fallback, **options),
            PROMPT,
        )
        return wire.vendor_requests()

    unset, effort = hop_requests(), hop_requests(reasoning_effort=ReasoningEffort.HIGH)

    assert [request["url"] for request in effort] == [
        request["url"] for request in unset
    ]
    assert len(effort) == len(chain)
    for (provider, _), sent, plain in zip(chain, effort, unset, strict=True):
        assert sent["json_body"] == deep_merge(
            plain["json_body"], fragment(provider, "high")
        ), provider


@pytest.mark.parametrize(
    ("provider", "model", "routed"),
    [
        (None, "anthropic/claude-sonnet-5", "anthropic"),
        ("openai", " GPT-5.5 ", "openai"),
        ("openai", "gpt-5.6", "openai"),
    ],
    ids=["slug_without_provider", "padded_upper_case", "alias"],
)
def test_a_normalized_model_id_is_sent_with_its_rows_form(
    provider: str | None, model: str, routed: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # EC-21, AC-18: the guard checks the pair the runner resolves, so a
    # slug, padding, case or an alias reaches the row it names.
    def agent(**options: Any) -> BaseAgent:
        return BaseAgent(
            name="planner",
            system_prompt=SYSTEM,
            provider=provider,
            model_name=model,
            api_keys=[provider_key(routed)],
            model_mode=TextModelMode.DIRECT,
            **options,
        )

    unset = _first_vendor_request(monkeypatch, agent())
    effort = _first_vendor_request(
        monkeypatch, agent(reasoning_effort=ReasoningEffort.HIGH)
    )

    assert effort["json_body"] == deep_merge(
        unset["json_body"], fragment(routed, "high")
    )
    _same_route(effort, unset)


@pytest.mark.parametrize(
    ("provider", "model", "thinking_config", "where"),
    [
        (
            "anthropic",
            "claude-sonnet-5",
            {"type": "enabled", "budget_tokens": 2048},
            ("thinking",),
        ),
        ("anthropic", "claude-sonnet-5", {}, None),
        (
            "gemini",
            "gemini-2.5-flash",
            {"thinkingBudget": 512},
            ("generationConfig", "thinkingConfig"),
        ),
        ("gemini", "gemini-2.5-flash", {}, ("generationConfig", "thinkingConfig")),
    ],
    ids=["anthropic_truthy", "anthropic_empty", "gemini_set", "gemini_empty"],
)
def test_thinking_config_without_an_effort_is_forwarded_as_before(
    provider: str,
    model: str,
    thinking_config: dict[str, Any],
    where: tuple[str, ...] | None,
) -> None:
    # INV-17: with the effort explicitly unset, Anthropic still forwards
    # a truthy thinking_config and Gemini any thinking_config not None.
    body = _one_call(
        _config(provider, model, thinking_config=thinking_config, reasoning_effort=None)
    )["json_body"]

    if where is None:
        assert "thinking" not in body
        return
    found: Any = body
    for key in where:
        found = found[key]
    assert found == thinking_config
