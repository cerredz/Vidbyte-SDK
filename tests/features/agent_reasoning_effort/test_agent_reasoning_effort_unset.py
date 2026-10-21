"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_unset.py

PURPOSE: Prove that an unset reasoning effort, whether omitted or passed as None,
changes nothing: for every provider and every TextModelMode the request URL, headers
and body equal those of the build without the argument and carry no reasoning key, a
checkpoint gains no key, a config whose effort is replaced by None is the never-set
config, and an explicitly unset JevAgent sends what the default one sends.
ROLE IN CODEBASE: Covers spec AC-8, NFR-1, INV-1 and D-13 for vidbyte/agents/base.py,
vidbyte/lib/dataclasses/model_configs.py, the four payload builders, the gateway
transport and vidbyte/agents/jev/settings.py. This is the user's "just run the jev
agent with no parameters" promise.
ARCHITECTURE NOTE: Each comparison builds both requests in the same test run against
the Wire, never against a stored golden body. The explicit None build cannot even be
constructed before the feature exists, which is what makes this red first; after it
exists, the separate key-absence check is the independent oracle that a builder never
sends a reasoning key with a null or default value.
FUNCTION INVENTORY: _request builds an agent and returns its first vendor request;
_comparable drops the per-call idempotency key; the test_* functions are one
behaviour each.
COMMON MODIFICATION PATTERNS: A new provider or mode joins CASES. A new wire-form location
joins _effort_fields.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare against a stored body or checkpoint.
2. Do not write a key-shaped literal. 3. Do not import a feature name outside the
FEATURE_MISSING guard.
KNOWN EDGE CASES: Gateway requests carry a fresh Idempotency-Key per call, so it is the
one header dropped before comparing. GLM and Meta are not gateway-served, so they are
checked in DIRECT only.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.1 INV-1, 6.2 AC-8,
7 NFR-1 and 8.1 D-13; tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_unset.py
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    GATEWAY_PROVIDERS,
    PROVIDERS,
    REPRESENTATIVE,
    VIDBYTE_KEY,
    Wire,
    clear_provider_environment,
    first_request,
    provider_key,
)
from vidbyte import JevAgent, JevAgentSettings
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.model_configs import TextModelConfig
from vidbyte.lib.enums import TextModelMode
from vidbyte.lib.runners.text import TextModelRunner

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.lib.enums import ReasoningEffort
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

CASES = [
    (provider, mode)
    for provider in PROVIDERS
    for mode in ("DIRECT", "AUTO", "VIDBYTE_MANAGED")
    if mode == "DIRECT" or provider in GATEWAY_PROVIDERS
]
# The top-level keys the section 9.2 wire forms add to a vendor body.
EFFORT_TOP_KEYS = {"reasoning", "reasoning_effort", "thinking"}


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_environment(monkeypatch)
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _request(
    monkeypatch: pytest.MonkeyPatch, provider: str, mode: str, **options: Any
) -> dict[str, Any]:
    wire = Wire().install(monkeypatch)
    agent = BaseAgent(
        name="planner",
        system_prompt="Plan database migrations.",
        provider=provider,
        model_name=REPRESENTATIVE[provider][0],
        api_keys=[provider_key(provider)],
        vidbyte_api_key=VIDBYTE_KEY,
        model_mode=TextModelMode[mode],
        **options,
    )
    return first_request(wire, agent)


def _effort_fields(body: Mapping[str, Any]) -> set[str]:
    # Every place a section 9.2 fragment lands, inside a vendor body or a gateway envelope's body.
    inner = body["body"] if isinstance(body.get("body"), Mapping) else body
    found = set(inner) & EFFORT_TOP_KEYS
    if "effort" in dict(inner.get("output_config") or {}):
        found.add("output_config.effort")
    if "thinkingConfig" in dict(inner.get("generationConfig") or {}):
        found.add("generationConfig.thinkingConfig")
    return found


def _comparable(request: Mapping[str, Any]) -> dict[str, Any]:
    # A gateway call carries a fresh idempotency key; everything else must match.
    headers = {
        key: value
        for key, value in dict(request["headers"] or {}).items()
        if key.lower() != "idempotency-key"
    }
    return {
        "method": request["method"],
        "url": request["url"],
        "headers": headers,
        "json_body": request["json_body"],
    }


@pytest.mark.parametrize(
    ("provider", "mode"), CASES, ids=[f"{provider}:{mode}" for provider, mode in CASES]
)
def test_an_unset_effort_sends_the_request_the_omitted_argument_sends(
    provider: str, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-8, NFR-1, INV-1: None is the default everywhere; it adds no key,
    # in no mode, so the provider's own default applies.
    omitted = _request(monkeypatch, provider, mode)
    explicit = _request(monkeypatch, provider, mode, reasoning_effort=None)

    assert _comparable(explicit) == _comparable(omitted)
    assert _effort_fields(explicit["json_body"]) == set()


@pytest.mark.parametrize("mode", ["DIRECT", "AUTO"])
def test_an_unset_checkpoint_has_no_effort_key(mode: str) -> None:
    # AC-8, D-13: the key is written only when the effort is set, so an
    # unset checkpoint is the checkpoint written before this change.
    def runtime_config(**options: Any) -> dict[str, Any]:
        agent = BaseAgent(
            name="planner",
            system_prompt="Plan database migrations.",
            provider="openai",
            model_name="gpt-5.5",
            api_keys=[provider_key("openai")],
            model_mode=TextModelMode[mode],
            **options,
        )
        return dict(agent.export_state().runtime_config)

    explicit = runtime_config(reasoning_effort=None)

    assert explicit == runtime_config()
    assert "reasoning_effort" not in explicit


def test_a_config_whose_effort_is_replaced_by_none_is_the_never_set_config() -> None:
    # INV-1: TextModelRunner rebuilds its config with dataclasses.replace
    # on every call, so clearing the field must restore the plain body.
    keys = [provider_key("anthropic")]
    never_set = TextModelConfig(
        provider="anthropic",
        model="claude-sonnet-5",
        api_keys=keys,
        mode=TextModelMode.DIRECT,
    )
    cleared = dataclasses.replace(
        TextModelConfig(
            provider="anthropic",
            model="claude-sonnet-5",
            api_keys=keys,
            mode=TextModelMode.DIRECT,
            reasoning_effort=ReasoningEffort.HIGH,
        ),
        reasoning_effort=None,
    )

    bodies = []
    for config in (never_set, cleared):
        wire = Wire()
        TextModelRunner(config, transport=wire).run(
            "Plan a zero-downtime rename of users.email."
        )
        bodies.append(wire.bodies[0])

    assert never_set.reasoning_effort is None and cleared.reasoning_effort is None
    assert bodies[1] == bodies[0]
    assert _effort_fields(bodies[1]) == set()


def test_an_explicitly_unset_jev_agent_sends_what_the_default_one_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-8, NFR-1: "just run the jev agent with no parameters" keeps its
    # behaviour when a caller such as vidbyte-cli passes None.
    def jev_request(**options: Any) -> dict[str, Any]:
        settings = JevAgentSettings(
            name="jev",
            system_prompt="Work carefully.",
            provider="anthropic",
            model_name="claude-sonnet-5",
            api_keys=[provider_key("anthropic")],
            model_mode=TextModelMode.DIRECT,
            **options,
        )
        return first_request(
            Wire().install(monkeypatch), JevAgent(settings), "Rename users.email."
        )

    explicit = jev_request(reasoning_effort=None)

    assert _comparable(explicit) == _comparable(jev_request())
    assert _effort_fields(explicit["json_body"]) == set()
