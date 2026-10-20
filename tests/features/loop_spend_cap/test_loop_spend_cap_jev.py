"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_jev.py

PURPOSE: Prove JevAgent enforces a spend cap on everything its run spends: it refuses a
specialist whose delegated run could spend past the cap, its own pre-loop decision
calls count toward the cap before the first generative call, a continuation's budget
extension never lifts the cap, and an unpriced call still fails closed with
UsageAccountingError after the cap stops the loop.
ROLE IN CODEBASE: Behavior tests for spec AC-13, AC-14, AC-20, AC-25 (EC-17, EC-18,
EC-19, INV-20) against JevAgent._require_capped_specialists, JevRuntime and
JevUsageAccount.
ARCHITECTURE NOTE: Decision calls are faked at TypeSafeProvider.run_decision, below
DecisionModelRunner, so the real recording hook writes them into the run ledger; the
generative model is a scripted runner bound to the agent. The decision key is built at
runtime from parts, never written as a key-shaped literal.
FUNCTION INVENTORY: test_a_capped_jev_agent_refuses_a_specialist_that_could_outspend_it;
test_a_capped_jev_agent_accepts_specialists_capped_no_higher_than_it;
test_preflight_decision_spend_alone_stops_the_run_before_any_generative_call;
test_a_continuation_budget_extension_never_lifts_the_cap;
test_an_unpriced_call_still_fails_closed_after_the_cap_stops_the_loop.
COMMON MODIFICATION PATTERNS: A new JevAgent phase that spends adds one case proving its
spend reaches the loop's next check point.
WHAT NOT TO DO IN THIS FILE: 1. Do not fake DecisionModelRunner itself; its recording
hook is under test. 2. Do not write a key-shaped literal; this repository is public.
3. Do not hard-code a dollar figure; derive it with reference_cost.
KNOWN EDGE CASES: The specialist refusal compares caps with "no higher than", so a
specialist capped exactly at JevAgent's cap constructs and one float step above it is
refused. JevAgent replaces reply.metadata["usage_rollup"] with its run total.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-11, INV-13, INV-20, AC-13, AC-14,
AC-20, AC-25; tests/test_jev_usage_ledger.py.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_jev.py
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any
from unittest.mock import patch

import pytest

from tests.agent_test_support import bind_test_runner
from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    MAX_SPEND,
    PRICED_MODEL,
    PRICED_PROVIDER,
    REACHED_TEXT,
    UNPRICED_MODEL,
    LookupTool,
    ScriptedRunner,
    call_response,
    capped_settings,
    reference_cost,
    text_response,
    usage,
)
from tests.test_jev_usage_ledger import _answer
from vidbyte import (
    BaseAgent,
    JevAgent,
    JevAgentSettings,
    JevPreflightPreset,
    JevRuntimeSettings,
    JevSpecialist,
)
from vidbyte.agents.jev.continuation.base import JevContinuation
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_SPECIALIST_NONE
from vidbyte.lib.dataclasses.jev import JevContinuationEvidence, JevDecisionRequest
from vidbyte.lib.enums import DecisionModelMode, ModelProvider
from vidbyte.lib.errors import ConfigurationError, UsageAccountingError
from vidbyte.lib.runners.types import DecisionModelResponse

RUN_DECISION = "vidbyte.providers.typesafe.TypeSafeProvider.run_decision"
JEV_MODEL = "jev-1.13.0"
CAP = 0.25
CLEAR = 0.95


def _decision_response(questions: Sequence[Any] = ()) -> DecisionModelResponse:
    answers = {
        question.name: _answer(question, CLEAR, JEV_SPECIALIST_NONE)
        for question in questions
    }
    return DecisionModelResponse(
        provider=ModelProvider.TYPESAFE,
        model=JEV_MODEL,
        answers=answers,
        raw={},
        usage=usage(3_000, 0),
    )


async def _run_decision(
    self: object,
    *,
    request: JevDecisionRequest,
    transport: object,
    config: object = None,
) -> DecisionModelResponse:
    # Answers every question clearly, so a preflight gate passes and the run reaches its main loop.
    return _decision_response(request.questions)


def _jev(
    runner: object,
    *,
    loop: AgentLoopSettings,
    preflight: tuple[JevPreflightPreset, ...] = (),
    agents: tuple[JevSpecialist, ...] = (),
    tools: tuple[object, ...] = (),
) -> JevAgent:
    settings = JevAgentSettings(
        name="jev",
        system_prompt="Work carefully.",
        provider=PRICED_PROVIDER.value,
        model_name=PRICED_MODEL,
        tools=tools,
        loop=loop,
        agents=agents,
    )
    runtime = JevRuntimeSettings(
        preflight=preflight,
        decision=DecisionModelConfig(
            mode=DecisionModelMode.VIDBYTE_MANAGED, api_key="vb_live_" + "x" * 32
        ),
    )
    return bind_test_runner(JevAgent(settings, runtime), runner)


def _specialist(loop: AgentLoopSettings) -> JevSpecialist:
    agent = BaseAgent(
        name="database",
        system_prompt="Change the schema.",
        provider=PRICED_PROVIDER.value,
        model_name=PRICED_MODEL,
        agent_loop_settings=loop,
    )
    return JevSpecialist(
        "database", "Changes to the database schema and its migrations.", agent
    )


@pytest.mark.parametrize(
    "specialist_cap",
    [None, math.nextafter(CAP, math.inf)],
    ids=["uncapped_specialist", "one_step_above"],
)
def test_a_capped_jev_agent_refuses_a_specialist_that_could_outspend_it(
    specialist_cap: float | None,
) -> None:
    # AC-13 and EC-18: a delegated run never enters JevAgent's loop, so only the specialist's own cap can bound it.
    assert (
        _jev(
            ScriptedRunner(),
            loop=AgentLoopSettings(),
            agents=(_specialist(AgentLoopSettings()),),
        ).name
        == "jev"
    )
    specialist_loop = (
        AgentLoopSettings()
        if specialist_cap is None
        else capped_settings(specialist_cap)
    )

    with pytest.raises(ConfigurationError) as caught:
        _jev(
            ScriptedRunner(),
            loop=capped_settings(CAP),
            agents=(_specialist(specialist_loop),),
        )

    assert (
        str(caught.value)
        == f"JevAgent specialist 'database' must set agent_loop_settings.max_spend_usd no higher than this JevAgent's {CAP}, because a delegated run never enters JevAgent's loop."
    )
    assert caught.value.details == {
        "specialist": "database",
        "max_spend_usd": CAP,
        "specialist_max_spend_usd": specialist_cap,
    }


@pytest.mark.parametrize("specialist_cap", [CAP, CAP / 2], ids=["equal", "lower"])
def test_a_capped_jev_agent_accepts_specialists_capped_no_higher_than_it(
    specialist_cap: float,
) -> None:
    # AC-13: "no higher than" includes equality.
    agent = _jev(
        ScriptedRunner(),
        loop=capped_settings(CAP),
        agents=(_specialist(capped_settings(specialist_cap)),),
    )

    assert agent.agent_loop_settings.max_spend_usd == CAP


def test_preflight_decision_spend_alone_stops_the_run_before_any_generative_call() -> (
    None
):
    # AC-14 and EC-17: the gate's decision call lands in the run ledger, so CP1 of iteration 0 stops before the main model.
    def answer() -> object:
        return text_response("done", usage=usage(100, 20))

    control_runner = ScriptedRunner(answer())
    with patch(RUN_DECISION, new=_run_decision):
        _jev(
            control_runner,
            loop=AgentLoopSettings(),
            preflight=(JevPreflightPreset.CLARITY,),
        ).run("Add a login page to the web app.")
    assert control_runner.calls == 1

    runner = ScriptedRunner(answer())
    agent = _jev(
        runner,
        loop=capped_settings(reference_cost(_decision_response())),
        preflight=(JevPreflightPreset.CLARITY,),
    )
    with patch(RUN_DECISION, new=_run_decision):
        reply = agent.run("Add a login page to the web app.")

    assert (reply.content, reply.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert runner.calls == 0
    assert agent.response.usage.decision.model_call_count == 1


class ExtendOnce(JevContinuation):
    """Sends the first finish attempt back to work with one extra iteration, then accepts every later one."""

    def __init__(self) -> None:
        self.granted = 0

    async def should_continue(
        self, final_answer: str, responses: Sequence[str], calls: Sequence[Any]
    ) -> bool:
        return self.granted == 0

    def budget_extension(self) -> tuple[int, int, int]:
        return 1, 0, 0

    def continue_(
        self, messages: list[dict[str, Any]]
    ) -> JevContinuationEvidence | None:
        self.granted += 1
        messages.append(
            {"role": "user", "content": "Keep going and finish the remaining work."}
        )
        return None


def _continued_run(
    loop: AgentLoopSettings, responses: Sequence[object]
) -> tuple[Any, ScriptedRunner, JevAgent]:
    runner = ScriptedRunner(*responses)
    agent = _jev(runner, loop=loop)
    agent.continuation = ExtendOnce()
    with patch(RUN_DECISION, new=_run_decision):
        reply = agent.run("Add a login page to the web app.")
    return reply, runner, agent


def test_a_continuation_budget_extension_never_lifts_the_cap() -> None:
    # AC-20 and INV-11: the extension raises max_iterations only; the cap still stops the continued attempt.
    def script() -> list[object]:
        return [
            text_response("draft", usage=usage(1_000, 100)),
            text_response("final", usage=usage(1_000, 100)),
        ]

    control, control_runner, control_agent = _continued_run(
        AgentLoopSettings(max_iterations=1), script()
    )
    assert (
        control.content,
        control_runner.calls,
        control_agent.response.continuation_budget,
    ) == ("final", 2, {"max_iterations": 1})

    responses = script()
    reply, runner, agent = _continued_run(
        capped_settings(reference_cost(*responses), max_iterations=1), responses
    )

    assert agent.response.continuation_budget == {"max_iterations": 1}
    assert (reply.content, reply.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert runner.calls == 2
    assert reply.metadata["iteration_outputs"] == ("draft", "final")


def test_an_unpriced_call_still_fails_closed_after_the_cap_stops_the_loop() -> None:
    # AC-25, EC-19 and INV-20: the cap's blind stop ends the loop before the tool runs, and settle() still raises.
    def script() -> list[object]:
        return [
            call_response(
                ("lookup", {"q": "users"}),
                usage=usage(1_000, 100),
                model=UNPRICED_MODEL,
            ),
            text_response("done", usage=usage(10, 1)),
        ]

    control_lookup = LookupTool()
    with patch(RUN_DECISION, new=_run_decision), pytest.raises(UsageAccountingError):
        _jev(
            ScriptedRunner(*script()), loop=AgentLoopSettings(), tools=(control_lookup,)
        ).run("Add a migration.")
    assert len(control_lookup.executed) == 1

    lookup, runner = LookupTool(), ScriptedRunner(*script())
    agent = _jev(runner, loop=capped_settings(CAP), tools=(lookup,))
    with (
        patch(RUN_DECISION, new=_run_decision),
        pytest.raises(UsageAccountingError) as caught,
    ):
        agent.run("Add a migration.")

    assert caught.value.details["unpriced"] == [f"openai:{UNPRICED_MODEL}"]
    assert (lookup.executed, runner.calls) == ([], 1)
