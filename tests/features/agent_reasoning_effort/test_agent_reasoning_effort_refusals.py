"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_refusals.py

PURPOSE: Prove that every effort the SDK cannot send is refused at construction, with
the spec's section 8.5 text character for character and its details, before any HTTP
request: every "refused" cell of the section 9.2 table on BaseAgent, TextModelConfig
and JevAgentSettings; every id with no row; every gateway mode; every fallback-chain
entry in either order; thinking_config and an overlapping extra_body; a value outside
the six; a non-text Runner; an agent without a provider or model; and that R3's
spend-cap refusal still comes first.
ROLE IN CODEBASE: Covers spec AC-4, AC-5, AC-6 (refusals), AC-7, AC-10, AC-16,
AC-18, EC-1 to EC-5, EC-7 to EC-10, EC-21 to EC-24, INV-3 to INV-8, INV-11, INV-18,
INV-20 and NFR-2 for vidbyte/agents/reasoning_effort.py, vidbyte/agents/base.py,
vidbyte/lib/dataclasses/{agents,model_configs}.py, vidbyte/agents/jev/settings.py and
vidbyte/lib/runners/utility.py.
ARCHITECTURE NOTE: The wire is installed in every test and must record zero
requests, so a refusal that happens after a paid call fails here. Texts are built
from the fixtures' section 8.5 templates and the module's REASONING_EFFORT_AS_OF;
the existing refusals that must keep their text (spend cap, gateway shape) are
captured in the same test from the same build without an effort, never copied.
FUNCTION INVENTORY: _refusal returns the ConfigurationError a build raises;
_jev_settings and _text_config build the other two carriers; the test_* functions
are one behaviour each.
COMMON MODIFICATION PATTERNS: A new refusal site adds one carrier branch to the
sweep tests and one exact-text row.
WHAT NOT TO DO IN THIS FILE: 1. Do not loosen an exact text to a substring; vidbyte-cli
C5 shows these texts to users. 2. Do not write REASONING_EFFORT_AS_OF or a key-shaped
value as a literal. 3. Do not import a feature name outside the FEATURE_MISSING guard.
KNOWN EDGE CASES: TextModelConfig on GLM, Meta or a custom endpoint in a gateway mode
keeps its earlier _require_gateway_shape refusal; BaseAgent builds no config at
construction, so its guard gives the mode text there. The guard checks the pair the
runner resolves, so a slug without a provider is checked as anthropic.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.1, 6.2 AC-4 to AC-7,
AC-10, AC-16, AC-18, 6.3, 8.5 and 9.2; tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_refusals.py
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    GATEWAY_PROVIDERS,
    NO_ROW,
    PROVIDERS,
    REPRESENTATIVE,
    SENT,
    Wire,
    bad_value_text,
    capability_reason,
    cell_id,
    clear_provider_environment,
    direct_agent,
    guard_text,
    identity_text,
    mode_reason,
    no_row_reason,
    provider_key,
    provider_keys,
    refused_cells,
)
from vidbyte import JevAgentSettings
from vidbyte.agents import FallbackModel
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.model_configs import TextModelConfig
from vidbyte.lib.enums import TextModelMode
from vidbyte.lib.enums.native_threads import GrokReasoningEffort, MuseReasoningEffort
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.runners.utility import Runner

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.lib.configs import REASONING_EFFORT_AS_OF
    from vidbyte.lib.enums import ReasoningEffort
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

REFUSED_CELLS = refused_cells()
BAD_VALUES = ("max", "", "HIGH", 3, GrokReasoningEffort.MAX)
GATEWAY_MODES = (
    ("default", "AUTO"),
    ("AUTO", "AUTO"),
    ("VIDBYTE_MANAGED", "VIDBYTE_MANAGED"),
)
NOT_GATEWAY_SERVED = tuple(
    provider for provider in PROVIDERS if provider not in GATEWAY_PROVIDERS
)


@pytest.fixture(autouse=True)
def wire(monkeypatch: pytest.MonkeyPatch) -> Wire:
    clear_provider_environment(monkeypatch)
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)
    return Wire().install(monkeypatch)


def _refusal(
    build: Callable[[], object], error_type: type[Exception] = ConfigurationError
) -> Any:
    with pytest.raises(error_type) as refused:
        build()
    return refused.value


def _jev_settings(provider: str, model: str, **options: Any) -> JevAgentSettings:
    options.setdefault("model_mode", TextModelMode.DIRECT)
    return JevAgentSettings(
        name="jev",
        system_prompt="Work carefully.",
        provider=provider,
        model_name=model,
        **options,
    )


def _text_config(provider: str, model: str, **options: Any) -> TextModelConfig:
    options.setdefault("mode", TextModelMode.DIRECT)
    return TextModelConfig(provider=provider, model=model, **options)


def _assert_carrier_texts(provider: str, model: str, value: str, reason: str) -> None:
    # The three section 8.5 carrier texts for one reason, with their details.
    agent_error = _refusal(
        lambda: direct_agent(provider, model, reasoning_effort=value)
    )
    assert str(agent_error) == guard_text("planner", reason)
    assert dict(agent_error.details) == {
        "agent": "planner",
        "field": "reasoning_effort",
        "reasoning_effort": value,
    }
    assert provider_key(provider) not in str(agent_error)

    config_error = _refusal(
        lambda: _text_config(provider, model, reasoning_effort=value)
    )
    assert str(config_error) == f"TextModelConfig sets reasoning_effort, but {reason}."
    details = dict(config_error.details)
    # The spec gives the model detail as the config's model; padding is not pinned.
    assert str(details.pop("model")).strip() == model.strip()
    assert details == {
        "field": "TextModelConfig.reasoning_effort",
        "provider": provider,
        "reasoning_effort": value,
        "mode": "direct",
    }

    settings_error = _refusal(
        lambda: _jev_settings(provider, model, reasoning_effort=value)
    )
    assert (
        str(settings_error) == f"JevAgentSettings sets reasoning_effort, but {reason}."
    )
    assert dict(settings_error.details) == {
        "field": "JevAgentSettings.reasoning_effort",
        "reasoning_effort": value,
    }


@pytest.mark.parametrize(
    ("provider", "model", "value", "supported"),
    REFUSED_CELLS,
    ids=[cell_id(*cell) for cell in REFUSED_CELLS],
)
def test_every_refused_cell_is_refused_on_every_carrier_before_any_request(
    provider: str, model: str, value: str, supported: tuple[str, ...], wire: Wire
) -> None:
    # AC-4, INV-3, INV-4, INV-11, INV-20, EC-2 to EC-4, D-4: a line with
    # a "sent" cell gets the capability text listing that line's values.
    _assert_carrier_texts(
        provider, model, value, capability_reason(provider, model, value, supported)
    )

    assert wire.requests == []


@pytest.mark.parametrize(
    ("provider", "model"), NO_ROW, ids=[cell_id(*line) for line in NO_ROW]
)
def test_an_id_with_no_row_is_refused_with_the_no_row_text(
    provider: str, model: str, wire: Wire
) -> None:
    # AC-4, EC-10, EC-23, EC-24, INV-20: the text names the table's date
    # and its sources section, so the user can tell the table may lag.
    _assert_carrier_texts(
        provider,
        model,
        "low",
        no_row_reason(provider, model, "low", REASONING_EFFORT_AS_OF),
    )

    assert wire.requests == []


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize(
    ("given", "mode_name"), GATEWAY_MODES, ids=[given for given, _ in GATEWAY_MODES]
)
def test_a_gateway_mode_is_refused_with_the_text_naming_direct(
    provider: str, given: str, mode_name: str, wire: Wire
) -> None:
    # AC-5, EC-1, INV-5, D-2: the default AUTO, explicit AUTO and
    # VIDBYTE_MANAGED all refuse, even for a cell DIRECT would send.
    model, value = REPRESENTATIVE[provider]
    mode = {} if given == "default" else {"model_mode": TextModelMode[mode_name]}
    reason = mode_reason(mode_name)

    agent_error = _refusal(
        lambda: BaseAgent(
            name="planner",
            system_prompt="Plan database migrations.",
            provider=provider,
            model_name=model,
            api_keys=[provider_key(provider)],
            reasoning_effort=value,
            **mode,
        )
    )
    assert str(agent_error) == guard_text("planner", reason)
    settings_error = _refusal(
        lambda: JevAgentSettings(
            name="jev",
            system_prompt="Work carefully.",
            provider=provider,
            model_name=model,
            reasoning_effort=value,
            **mode,
        )
    )
    assert (
        str(settings_error) == f"JevAgentSettings sets reasoning_effort, but {reason}."
    )
    if provider in GATEWAY_PROVIDERS:
        config_mode = {} if given == "default" else {"mode": TextModelMode[mode_name]}
        config_error = _refusal(
            lambda: TextModelConfig(
                provider=provider, model=model, reasoning_effort=value, **config_mode
            )
        )
        assert (
            str(config_error) == f"TextModelConfig sets reasoning_effort, but {reason}."
        )
        assert config_error.details["mode"] == TextModelMode[mode_name].value
    assert "TextModelMode.DIRECT" in reason
    assert wire.requests == []


def test_the_mode_reason_comes_once_and_before_any_chain_entrys_capability(
    wire: Wire,
) -> None:
    # Section 8.5 order and de-duplication: in AUTO every entry has the
    # same mode reason, and it outranks the primary's missing form.
    fallback = [FallbackModel("openai", "gpt-5.5")]
    error = _refusal(
        lambda: BaseAgent(
            name="planner",
            system_prompt="Plan database migrations.",
            provider="gemini",
            model_name="gemini-3.5-flash",
            api_keys=provider_keys("gemini", "openai"),
            fallback=fallback,
            reasoning_effort="xhigh",
        )
    )

    assert str(error) == guard_text("planner", mode_reason("AUTO"))
    assert wire.requests == []


@pytest.mark.parametrize("provider", NOT_GATEWAY_SERVED)
@pytest.mark.parametrize("mode_name", ["AUTO", "VIDBYTE_MANAGED"])
def test_text_model_config_keeps_its_earlier_refusal_for_what_the_gateway_cannot_serve(
    provider: str, mode_name: str
) -> None:
    # AC-5: _require_gateway_shape runs before the effort check, so GLM
    # and Meta keep their UnsupportedProviderError, text unchanged.
    model, value = REPRESENTATIVE[provider]
    before = _refusal(
        lambda: TextModelConfig(
            provider=provider, model=model, mode=TextModelMode[mode_name]
        ),
        UnsupportedProviderError,
    )

    error = _refusal(
        lambda: TextModelConfig(
            provider=provider,
            model=model,
            mode=TextModelMode[mode_name],
            reasoning_effort=value,
        ),
        UnsupportedProviderError,
    )

    assert str(error) == str(before)
    assert "TextModelMode.DIRECT" in str(error)


def test_text_model_config_keeps_its_custom_endpoint_refusal_in_a_gateway_mode() -> (
    None
):
    # AC-5: a custom endpoint in a gateway mode is refused by the
    # endpoint check first, with its own text naming DIRECT.
    endpoint = "https://proxy.example.test/v1"
    before = _refusal(
        lambda: TextModelConfig(provider="openai", model="gpt-5.5", endpoint=endpoint)
    )

    error = _refusal(
        lambda: TextModelConfig(
            provider="openai",
            model="gpt-5.5",
            endpoint=endpoint,
            reasoning_effort="high",
        )
    )

    assert (type(error), str(error)) == (type(before), str(before))
    assert "TextModelMode.DIRECT" in str(error)


# (chain as (provider, model) pairs, effort, the refused entries in chain order)
CHAINS = (
    (
        (("gemini", "gemini-3.5-flash"), ("openai", "gpt-5.5")),
        "xhigh",
        (("gemini", "gemini-3.5-flash"),),
    ),
    (
        (("openai", "gpt-5.5"), ("gemini", "gemini-3.5-flash")),
        "xhigh",
        (("gemini", "gemini-3.5-flash"),),
    ),
    (
        (
            ("openai", "gpt-5.5"),
            ("gemini", "gemini-3.5-flash"),
            ("anthropic", "claude-sonnet-5"),
        ),
        "xhigh",
        (("gemini", "gemini-3.5-flash"),),
    ),
    (
        (("openai", "gpt-5.5"), ("anthropic", "claude-sonnet-5"), ("xai", "grok-4.5")),
        "xhigh",
        (("xai", "grok-4.5"),),
    ),
    (
        (("gemini", "gemini-3.5-flash"), ("xai", "grok-4.5")),
        "xhigh",
        (("gemini", "gemini-3.5-flash"), ("xai", "grok-4.5")),
    ),
    (
        (
            ("gemini", "gemini-3.5-flash"),
            ("openai", "gpt-5.5"),
            ("gemini", "gemini-3.5-flash"),
        ),
        "xhigh",
        (("gemini", "gemini-3.5-flash"),),
    ),
    ((("openai", "gpt-5.5"), ("openai", "o3")), "low", (("openai", "o3"),)),
)


@pytest.mark.parametrize(
    ("chain", "value", "refused"),
    CHAINS,
    ids=[
        "bad_primary",
        "bad_fallback",
        "bad_middle",
        "bad_last",
        "two_bad_in_order",
        "repeated_bad_once",
        "no_row_fallback",
    ],
)
def test_every_chain_entry_is_checked_in_either_order(
    chain: tuple[tuple[str, str], ...],
    value: str,
    refused: tuple[tuple[str, str], ...],
    wire: Wire,
) -> None:
    # AC-6, INV-6, EC-5, D-5: a bad primary before a good fallback (and
    # the reverse) would pay for a failed call every turn; the reasons
    # are unique and in chain order.
    keys = provider_keys(*dict.fromkeys(provider for provider, _ in chain))
    fallback = [FallbackModel(provider, model) for provider, model in chain[1:]]
    reasons = [
        capability_reason(provider, model, value, SENT[provider][model])
        if model in SENT.get(provider, {})
        else no_row_reason(provider, model, value, REASONING_EFFORT_AS_OF)
        for provider, model in refused
    ]

    error = _refusal(
        lambda: direct_agent(
            *chain[0], keys=keys, fallback=fallback, reasoning_effort=value
        )
    )

    assert str(error) == guard_text("planner", *reasons)
    assert wire.requests == []


THINKING_AND_OVERLAP = (
    (
        "anthropic",
        "claude-sonnet-5",
        "high",
        {"thinking_config": {"type": "enabled", "budget_tokens": 2048}},
        "both",
    ),
    ("gemini", "gemini-3.5-flash", "low", {"thinking_config": {}}, "both"),
    (
        "openai",
        "gpt-5.5",
        "low",
        {"thinking_config": {}, "extra_body": {"reasoning": {"summary": "auto"}}},
        "both",
    ),
    (
        "openai",
        "gpt-5.5",
        "low",
        {"extra_body": {"reasoning": {"summary": "auto"}, "store": False}},
        ("reasoning",),
    ),
    (
        "glm",
        "glm-5.3",
        "high",
        {
            "extra_body": {
                "thinking": {"type": "enabled"},
                "reasoning_effort": "low",
                "do_sample": False,
            }
        },
        ("reasoning_effort", "thinking"),
    ),
    (
        "anthropic",
        "claude-sonnet-5",
        "none",
        {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 1024}}},
        ("thinking",),
    ),
    (
        "anthropic",
        "claude-sonnet-5",
        "medium",
        {"extra_body": {"output_config": {"effort": "low"}}},
        ("output_config",),
    ),
    (
        "gemini",
        "gemini-2.5-flash",
        "none",
        {"extra_body": {"generationConfig": {"temperature": 0.1}}},
        ("generationConfig",),
    ),
    (
        "deepseek",
        "deepseek-v4-pro",
        "low",
        {"extra_body": {"reasoning_effort": "high"}},
        ("reasoning_effort",),
    ),
)


@pytest.mark.parametrize(
    ("provider", "model", "value", "options", "expected"),
    THINKING_AND_OVERLAP,
    ids=[cell_id(*case[:3], index) for index, case in enumerate(THINKING_AND_OVERLAP)],
)
def test_effort_beside_thinking_config_or_an_overlapping_extra_body_is_refused(
    provider: str, model: str, value: str, options: dict[str, Any], expected: Any
) -> None:
    # AC-7, INV-7, EC-7, EC-8: payload.update(extra_body) would erase the
    # fragment, and two thinking controls are ambiguous; thinking_config
    # is checked before the overlap, and {} counts as set.
    error = _refusal(
        lambda: _text_config(provider, model, reasoning_effort=value, **options)
    )

    if expected == "both":
        assert (
            str(error)
            == "TextModelConfig sets both reasoning_effort and thinking_config; set only one of them."
        )
    else:
        assert (
            str(error)
            == f"TextModelConfig sets reasoning_effort, but extra_body also sets {', '.join(expected)}, which the effort's wire form uses; remove them from extra_body or unset reasoning_effort."
        )
    assert dict(error.details) == {"field": "TextModelConfig.reasoning_effort"}


def test_the_capability_and_mode_reasons_come_before_thinking_config() -> None:
    # Section 8.5 order in TextModelConfig: conversion, then mode or
    # capability, then thinking_config, then the extra_body overlap.
    thinking = {
        "thinking_config": {"type": "enabled"},
        "extra_body": {"output_config": {}},
    }
    capability = _refusal(
        lambda: _text_config(
            "gemini", "gemini-3.5-flash", reasoning_effort="xhigh", **thinking
        )
    )
    mode = _refusal(
        lambda: _text_config(
            "openai",
            "gpt-5.5",
            reasoning_effort="high",
            mode=TextModelMode.AUTO,
            **thinking,
        )
    )
    conversion = _refusal(
        lambda: _text_config(
            "openai",
            "gpt-5.5",
            reasoning_effort="max",
            mode=TextModelMode.AUTO,
            **thinking,
        )
    )

    assert (
        str(capability)
        == f"TextModelConfig sets reasoning_effort, but {capability_reason('gemini', 'gemini-3.5-flash', 'xhigh', SENT['gemini']['gemini-3.5-flash'])}."
    )
    assert (
        str(mode)
        == f"TextModelConfig sets reasoning_effort, but {mode_reason('AUTO')}."
    )
    assert str(conversion) == bad_value_text("TextModelConfig.reasoning_effort", "max")


@pytest.mark.parametrize("value", BAD_VALUES, ids=[repr(value) for value in BAD_VALUES])
def test_a_value_outside_the_six_is_refused_on_every_carrier(
    value: object, wire: Wire
) -> None:
    # AC-10, INV-8: no case folding and no foreign value; the message
    # lists the six in order and shows the value's repr.
    agent_error = _refusal(
        lambda: direct_agent("openai", "gpt-5.5", reasoning_effort=value)
    )
    config_error = _refusal(
        lambda: _text_config("openai", "gpt-5.5", reasoning_effort=value)
    )
    settings_error = _refusal(
        lambda: _jev_settings("openai", "gpt-5.5", reasoning_effort=value)
    )

    for error, field_name in (
        (agent_error, "AgentRunnerConfig.reasoning_effort"),
        (config_error, "TextModelConfig.reasoning_effort"),
        (settings_error, "JevAgentSettings.reasoning_effort"),
    ):
        assert str(error) == bad_value_text(field_name, value)
        assert error.details["field"] == field_name
    assert wire.requests == []


@pytest.mark.parametrize(
    "value",
    ["high", GrokReasoningEffort.HIGH, MuseReasoningEffort.HIGH],
    ids=["plain_string", "grok_member", "muse_member"],
)
def test_a_plain_string_or_another_enums_member_is_stored_as_the_member(
    value: object,
) -> None:
    # AC-10, INV-8: the value becomes the ReasoningEffort member once, at
    # the first record, so nothing downstream sees a foreign type.
    stored = (
        direct_agent(
            "openai", "gpt-5.5", reasoning_effort=value
        ).runner_config.reasoning_effort,
        _text_config("openai", "gpt-5.5", reasoning_effort=value).reasoning_effort,
        _jev_settings("openai", "gpt-5.5", reasoning_effort=value).reasoning_effort,
    )

    assert all(
        type(member) is ReasoningEffort and member is ReasoningEffort.HIGH
        for member in stored
    ), stored


def test_a_non_text_runner_refuses_the_effort_instead_of_dropping_it() -> None:
    # AC-16, EC-9, FR-5: ImageModelConfig has no such field, so the
    # options filter would drop the effort silently.
    keys = [provider_key("openai")]
    error = _refusal(
        lambda: Runner(
            provider="openai",
            model_name="gpt-image-2",
            api_keys=keys,
            reasoning_effort=ReasoningEffort.HIGH,
        ).build()
    )

    assert (
        str(error)
        == "Runner sets reasoning_effort, but model 'gpt-image-2' resolves to a image runner, which has no reasoning effort."
    )
    assert dict(error.details) == {
        "provider": "openai",
        "model": "gpt-image-2",
        "runner_type": "image",
    }
    assert (
        Runner(
            provider="openai",
            model_name="gpt-image-2",
            api_keys=keys,
            reasoning_effort=None,
        ).build()
        is not None
    )


@pytest.mark.parametrize(
    ("provider", "model"),
    [("openai", None), (None, "gpt-5.5"), (None, None)],
    ids=["no_model", "no_provider", "neither"],
)
def test_an_agent_without_both_a_provider_and_a_model_is_refused(
    provider: str | None, model: str | None, wire: Wire
) -> None:
    # EC-22: such an agent can never run (Runner.build needs both), so an
    # effort on it would be silently unused.
    error = _refusal(
        lambda: BaseAgent(
            name="planner",
            system_prompt="Plan database migrations.",
            provider=provider,
            model_name=model,
            model_mode=TextModelMode.DIRECT,
            reasoning_effort="high",
        )
    )

    assert str(error) == identity_text("planner")
    assert dict(error.details) == {
        "agent": "planner",
        "field": "reasoning_effort",
        "reasoning_effort": "high",
    }
    assert wire.requests == []


def test_a_slug_without_a_provider_is_checked_against_the_row_the_runner_resolves(
    wire: Wire,
) -> None:
    # EC-21, D-5: the guard derives the pair as the runner does, so
    # anthropic/claude-sonnet-5 is checked against claude-sonnet-5's row.
    error = _refusal(
        lambda: BaseAgent(
            name="planner",
            system_prompt="Plan database migrations.",
            provider=None,
            model_name="anthropic/claude-sonnet-5",
            api_keys=[provider_key("anthropic")],
            model_mode=TextModelMode.DIRECT,
            reasoning_effort="minimal",
        )
    )

    assert str(error).startswith("Agent planner sets reasoning_effort, but anthropic:")
    assert str(error).endswith(
        f"has no documented form for reasoning effort 'minimal' (it supports {', '.join(SENT['anthropic']['claude-sonnet-5'])})."
    )
    assert wire.requests == []


def test_a_padded_upper_case_id_is_named_as_given_but_stripped(wire: Wire) -> None:
    # AC-18: support is gpt-5.5's, and every carrier quotes the caller's
    # own id, stripped, so they can find it.
    _assert_carrier_texts(
        "openai",
        " GPT-5.5 ",
        "minimal",
        capability_reason("openai", " GPT-5.5 ", "minimal", SENT["openai"]["gpt-5.5"]),
    )

    assert wire.requests == []


def test_the_spend_cap_refusal_still_runs_before_the_effort_guard(wire: Wire) -> None:
    # INV-18: R3's refusal keeps its text and its place; the effort guard
    # (which would refuse this unlisted id too) runs after it.
    loop = AgentLoopSettings(max_spend_usd=1.0)
    before = _refusal(
        lambda: direct_agent("openai", "gpt-effort-probe", agent_loop_settings=loop)
    )

    error = _refusal(
        lambda: direct_agent(
            "openai",
            "gpt-effort-probe",
            agent_loop_settings=loop,
            reasoning_effort="high",
        )
    )

    assert str(error) == str(before)
    assert "reasoning_effort" not in str(error)
    assert wire.requests == []
