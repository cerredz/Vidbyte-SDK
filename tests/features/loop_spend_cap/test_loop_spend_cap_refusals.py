"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_refusals.py

PURPOSE: Prove every agent that could not enforce or measure a spend cap refuses it in
its constructor, before any spend, with the spec's message, and that the same agents
construct unchanged without a cap.
ROLE IN CODEBASE: Behavior tests for spec INV-13: the non-linear runtime refusal and
AgentSpendCap.model_refusal as BaseAgent.__init__ applies them, the same refusal on a
forked child, and the Codex refusal through CODEX_UNSUPPORTED_LOOP_FIELDS.
ARCHITECTURE NOTE: Every case is a plain constructor call with no runner bound and no
network: the runner type and the pricebook lookup depend only on the configured
provider and model. Each unpriced model name is checked against the live pricebook at
test time, so a future price entry fails loudly instead of silently changing what a
case proves.
FUNCTION INVENTORY: test_a_capped_non_linear_runtime_is_refused;
test_a_capped_non_text_model_is_refused_naming_its_runner_type;
test_a_capped_agent_with_an_unpriced_configured_model_is_refused_naming_each_one;
test_a_capped_agent_whose_whole_chain_is_measurable_constructs;
test_a_capped_parent_cannot_fork_a_child_onto_an_unpriced_model;
test_codex_refuses_a_capped_loop_through_its_existing_field_list.
COMMON MODIFICATION PATTERNS: A new agent kind that cannot see the loop adds one refusal
case and one uncapped control; a new runtime type is added to the non-linear list only
if it reads no loop budget.
WHAT NOT TO DO IN THIS FILE: 1. Do not bind a runner before constructing; the refusal
must not depend on one. 2. Do not assert a pricebook rate; assert only priced or not.
3. Do not test MultiAgent or AggregateAgent here: they take no loop settings at all.
KNOWN EDGE CASES: A fallback chain's index 0 is the primary, so the primary is listed
first and only when it is the unpriced one. OpenRouter is exempt because it reports its
own cost per call. The model names ending "-z" and "-b" carry letter suffixes, which the
pricebook never treats as a release suffix.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-13, section 9.2 refusal messages,
AC-11, AC-12, AC-27, AC-30, EC-32, EC-39.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_refusals.py
"""

from __future__ import annotations

import pytest

from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    PRICED_MODEL,
    PRICED_PROVIDER,
    UNPRICED_MODEL,
    assert_price_preconditions,
    capped_settings,
)
from vidbyte.agents import FallbackModel
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.contracts import CodexContractValidator
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.codex import CodexHarnessAgentSettings
from vidbyte.lib.enums import AgentRuntimeType, ModelProvider
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.runners import Runner

IMAGE_MODEL = "gpt-image-2"
PRICED_FALLBACK = (ModelProvider.DEEPSEEK, "deepseek-v4-flash")
OPENROUTER_MODEL = "openai/" + UNPRICED_MODEL
NON_LINEAR = [
    AgentRuntimeType.MCTS_SEARCH,
    AgentRuntimeType.ACTOR_MODEL,
    AgentRuntimeType.ACTOR_MODEL_P2P,
    AgentRuntimeType.ACTOR_MODEL_BROADCAST,
]


def _agent(
    *,
    loop: AgentLoopSettings | None,
    provider: str = PRICED_PROVIDER.value,
    model_name: str = PRICED_MODEL,
    **options: object,
) -> BaseAgent:
    return BaseAgent(
        name="researcher",
        system_prompt="You research.",
        provider=provider,
        model_name=model_name,
        agent_loop_settings=loop,
        **options,
    )


def _assert_unpriced_text_model(provider: ModelProvider, model: str) -> None:
    # The case proves the price refusal only while the model is a text model the pricebook lacks.
    assert ModelPricingRegistry.default().resolve(provider, model) is None, (
        f"{provider.value}:{model} gained a price"
    )
    assert (
        Runner.from_model(
            provider=provider.value, model_name=model
        ).resolve_runner_type()
        == "text"
    )


def _unpriced_message(*pairs: str) -> str:
    return f"Agent researcher sets max_spend_usd, but the pricebook has no price for {', '.join(pairs)}, so its spend could not be measured."


@pytest.mark.parametrize(
    "runtime", NON_LINEAR, ids=[runtime.value for runtime in NON_LINEAR]
)
def test_a_capped_non_linear_runtime_is_refused(runtime: AgentRuntimeType) -> None:
    # AC-11: none of these runtimes reads a loop budget, so a cap there would be silently ignored.
    assert _agent(loop=AgentLoopSettings(), runtime=runtime).runtime_type is runtime

    with pytest.raises(ConfigurationError) as caught:
        _agent(loop=capped_settings(1.0), runtime=runtime)

    assert (
        str(caught.value)
        == f"Agent researcher uses non-linear runtime {runtime.value}, which does not enforce max_spend_usd."
    )


def test_a_capped_non_text_model_is_refused_naming_its_runner_type() -> None:
    # AC-12 and EC-32: an image runner runs outside the loop and records no usage.
    runner_type = Runner.from_model(
        provider=PRICED_PROVIDER.value, model_name=IMAGE_MODEL
    ).resolve_runner_type()
    assert runner_type != "text"
    assert (
        _agent(
            loop=AgentLoopSettings(), model_name=IMAGE_MODEL
        ).runner_config.model_name
        == IMAGE_MODEL
    )

    with pytest.raises(ConfigurationError) as caught:
        _agent(loop=capped_settings(1.0), model_name=IMAGE_MODEL)

    assert (
        str(caught.value)
        == f"Agent researcher sets max_spend_usd, but its {runner_type} runner runs outside the agent loop, which is the only place the spend cap is enforced."
    )
    assert caught.value.details == {"agent": "researcher"}


@pytest.mark.parametrize(
    ("model_name", "fallback", "named"),
    [
        (UNPRICED_MODEL, None, [f"openai:{UNPRICED_MODEL}"]),
        (
            PRICED_MODEL,
            [
                FallbackModel("openai", UNPRICED_MODEL + "-z"),
                FallbackModel(*PRICED_FALLBACK),
                FallbackModel("openai", UNPRICED_MODEL + "-b"),
            ],
            [f"openai:{UNPRICED_MODEL}-z", f"openai:{UNPRICED_MODEL}-b"],
        ),
    ],
    ids=["unpriced_primary", "unpriced_fallbacks_in_chain_order"],
)
def test_a_capped_agent_with_an_unpriced_configured_model_is_refused_naming_each_one(
    model_name: str, fallback: list[FallbackModel] | None, named: list[str]
) -> None:
    # AC-30 (i) and (ii), EC-5: an unpriced configured model could only be found after a paid call, so it is refused first.
    assert_price_preconditions()
    for suffix in ("-z", "-b"):
        _assert_unpriced_text_model(ModelProvider.OPENAI, UNPRICED_MODEL + suffix)
    assert (
        _agent(loop=AgentLoopSettings(), model_name=model_name, fallback=fallback).name
        == "researcher"
    )

    with pytest.raises(ConfigurationError) as caught:
        _agent(loop=capped_settings(1.0), model_name=model_name, fallback=fallback)

    assert str(caught.value) == _unpriced_message(*named)
    assert caught.value.details == {"agent": "researcher"}


@pytest.mark.parametrize(
    ("provider", "model_name", "fallback"),
    [
        (PRICED_PROVIDER.value, PRICED_MODEL, None),
        (PRICED_PROVIDER.value, PRICED_MODEL, [FallbackModel(*PRICED_FALLBACK)]),
        (ModelProvider.OPENROUTER.value, OPENROUTER_MODEL, None),
        (
            PRICED_PROVIDER.value,
            PRICED_MODEL,
            [FallbackModel(ModelProvider.OPENROUTER.value, OPENROUTER_MODEL)],
        ),
    ],
    ids=[
        "priced_primary",
        "priced_fallback",
        "openrouter_primary",
        "openrouter_fallback",
    ],
)
def test_a_capped_agent_whose_whole_chain_is_measurable_constructs(
    provider: str, model_name: str, fallback: list[FallbackModel] | None
) -> None:
    # AC-30 (iii) and EC-8: every chain entry is priced, or is OpenRouter, which reports its own cost.
    assert ModelPricingRegistry.default().resolve(*PRICED_FALLBACK) is not None

    agent = _agent(
        loop=capped_settings(0.25),
        provider=provider,
        model_name=model_name,
        fallback=fallback,
    )

    assert agent.agent_loop_settings.max_spend_usd == 0.25
    assert agent.runtime_config.max_spend_usd == 0.25


def test_a_capped_parent_cannot_fork_a_child_onto_an_unpriced_model() -> None:
    # INV-12 and INV-13: a fork is a BaseAgent built from the parent's loop settings, so its constructor refuses too.
    assert_price_preconditions()
    assert (
        _agent(loop=AgentLoopSettings())
        .fork(AgentForkSettings(model_name=UNPRICED_MODEL))
        .runner_config.model_name
        == UNPRICED_MODEL
    )
    parent = _agent(loop=capped_settings(1.0))

    with pytest.raises(ConfigurationError) as caught:
        parent.fork(AgentForkSettings(model_name=UNPRICED_MODEL))

    assert f"openai:{UNPRICED_MODEL}" in str(caught.value)
    assert "max_spend_usd" in str(caught.value)


def test_codex_refuses_a_capped_loop_through_its_existing_field_list() -> None:
    # AC-27 and EC-39: Codex owns its model loop, so nothing could check the cap; the refusal names the field.
    def settings(loop: AgentLoopSettings) -> CodexHarnessAgentSettings:
        return CodexHarnessAgentSettings(
            name="codex-agent",
            system_prompt="You are a Codex harness agent.",
            loop=loop,
        )

    CodexContractValidator.validate(AgentLoopSettings())
    assert CodexHarnessAgent(settings(AgentLoopSettings())).name == "codex-agent"

    with pytest.raises(ConfigurationError, match="max_spend_usd"):
        CodexContractValidator.validate(capped_settings(5))
    with pytest.raises(CodexAgentError) as caught:
        CodexHarnessAgent(settings(capped_settings(5)))

    assert caught.value.failure_code == "codex.vidbyte_translation_failed"
    assert isinstance(caught.value.__cause__, ConfigurationError)
    assert "max_spend_usd" in str(caught.value.__cause__)
