"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_jev.py

PURPOSE: Prove JevAgent enforces a spend cap on everything its run spends: it refuses a
specialist whose delegated run could spend past the cap, its own pre-loop decision
calls count toward the cap before the first generative call, a reached cap starts no
specialist the gate chose, a continuation's budget extension never lifts the cap, and
an unpriced call still fails closed with UsageAccountingError after the cap stops the
loop.
ROLE IN CODEBASE: Behavior tests for spec AC-13, AC-14, AC-20, AC-25, AC-33 (EC-17,
EC-18, EC-19, INV-5, INV-9, INV-10, INV-20) against JevAgent._require_capped_specialists,
JevRuntime (its main loop and its delegated path) and JevUsageAccount.
ARCHITECTURE NOTE: Decision calls are faked at TypeSafeProvider.run_decision, below
DecisionModelRunner, so the real recording hook writes them into the run ledger; the
generative model is a scripted runner bound to the agent. The decision key is built at
runtime from parts, never written as a key-shaped literal.
FUNCTION INVENTORY: test_a_capped_jev_agent_refuses_a_specialist_that_could_outspend_it;
test_a_capped_jev_agent_accepts_specialists_capped_no_higher_than_it;
test_preflight_decision_spend_alone_stops_the_run_before_any_generative_call;
test_a_reached_cap_starts_no_specialist_the_gate_chose;
test_a_continuation_budget_extension_never_lifts_the_cap;
test_an_unpriced_call_still_fails_closed_after_the_cap_stops_the_loop.
COMMON MODIFICATION PATTERNS: A new JevAgent phase that spends adds one case proving its
spend reaches the loop's next check point.
WHAT NOT TO DO IN THIS FILE: 1. Do not fake DecisionModelRunner itself; its recording
hook is under test. 2. Do not write a key-shaped literal; this repository is public.
3. Do not hard-code a dollar figure; derive it with reference_cost.
KNOWN EDGE CASES: The specialist refusal compares caps with "no higher than", so a
specialist capped exactly at JevAgent's cap constructs and one float step above it is
refused. JevAgent replaces reply.metadata["usage_rollup"] with its run total. A
specialist capped at C whose own first call reaches C also ends "max_spend", so the
delegated-path test proves the check by the specialist's call count and
iteration_count 0, never by the stop reason alone. On that stop
JevAgent.response.specialist still names the gate's choice (spec A-8), so no test
asserts it is None. The RUN_STATE_RELATION writer can call its model more than once,
so its scripted runner holds several responses.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-5, INV-6, INV-9, INV-10, INV-11,
INV-13, INV-20, A-8, AC-13, AC-14, AC-20, AC-25, AC-33; tests/test_jev_usage_ledger.py.
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
    usage_costing_at_least,
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
from vidbyte.lib.enums.failure import FailureCode, FailureDisposition, FailureStatus
from vidbyte.lib.errors import ConfigurationError, UsageAccountingError
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.sessions.failure.router import FailureMetadataNormalizer

RUN_DECISION = "vidbyte.providers.typesafe.TypeSafeProvider.run_decision"
JEV_MODEL = "jev-1.13.0"
CAP = 0.25
CLEAR = 0.95
SPECIALIST = "database"


def _decision_response(
    questions: Sequence[Any] = (), *, choice: str = JEV_SPECIALIST_NONE
) -> DecisionModelResponse:
    answers = {
        question.name: _answer(question, CLEAR, choice) for question in questions
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


async def _run_delegating_decision(
    self: object,
    *,
    request: JevDecisionRequest,
    transport: object,
    config: object = None,
) -> DecisionModelResponse:
    # Answers every question clearly and routes the request to the database specialist, so the run takes the delegated path.
    return _decision_response(request.questions, choice=SPECIALIST)


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


# The run-state writer may call its model more than once, so it is scripted with this many replies.
WRITER_REPLIES = 4


def _delegated_run(
    loop: AgentLoopSettings,
    *,
    cap: float,
    preflight: tuple[JevPreflightPreset, ...],
    writer_response: object,
) -> tuple[Any, JevAgent, ScriptedRunner, ScriptedRunner, ScriptedRunner]:
    # Runs a JevAgent whose gate routes the request to one specialist capped at `cap`, whose own first call alone
    # reaches that cap; returns the reply, the agent, and the specialist's, main model's and run-state writer's runners.
    specialist_runner = ScriptedRunner(
        text_response("Migration written.", usage=usage_costing_at_least(cap))
    )
    specialist = _specialist(capped_settings(cap))
    bind_test_runner(specialist.agent, specialist_runner)
    main_runner = ScriptedRunner(text_response("unreachable", usage=usage(100, 20)))
    agent = _jev(main_runner, loop=loop, preflight=preflight, agents=(specialist,))
    writer_runner = ScriptedRunner(*[writer_response] * WRITER_REPLIES)
    if agent.run_state is not None:
        bind_test_runner(agent.run_state, writer_runner)
    with patch(RUN_DECISION, new=_run_delegating_decision):
        reply = agent.run("Add a migration for the users table.")
    return reply, agent, specialist_runner, main_runner, writer_runner


@pytest.mark.parametrize("source", ["gate_decision", "run_state_relation_writer"])
def test_a_reached_cap_starts_no_specialist_the_gate_chose(source: str) -> None:
    # AC-33, EC-17 and INV-5 (r4): on the delegated path CP1 runs after the gate and the run-state writer and before
    # the specialist starts, because the specialist's own cap starts at $0 on its own ledger and never sees that spend.
    decision_cost = reference_cost(_decision_response())
    writer_response = text_response("{}", usage=usage(40_000, 2_000))
    writes = source == "run_state_relation_writer"
    if writes:
        cap = reference_cost(writer_response)
        preflight: tuple[JevPreflightPreset, ...] = (
            JevPreflightPreset.RUN_STATE_RELATION,
        )
        # The gate's decision alone stays below C, so only the writer's spend can reach it.
        assert decision_cost < cap
    else:
        cap, preflight = decision_cost, ()
    _, _, control_specialist, control_main, control_writer = _delegated_run(
        AgentLoopSettings(),
        cap=cap,
        preflight=preflight,
        writer_response=writer_response,
    )
    # Without JevAgent's cap the same script delegates: the specialist runs, the main model never does.
    assert (control_specialist.calls, control_main.calls) == (1, 0)
    assert (control_writer.calls > 0) is writes

    reply, agent, specialist_runner, main_runner, writer_runner = _delegated_run(
        capped_settings(cap),
        cap=cap,
        preflight=preflight,
        writer_response=writer_response,
    )

    metadata = reply.metadata
    assert (reply.content, metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    # A specialist capped at C whose own first call reaches C also stops on max_spend, so the stop reason alone
    # cannot prove the check ran before the specialist; its call count and iteration_count 0 do.
    assert (specialist_runner.calls, metadata["iteration_count"]) == (0, 0)
    assert main_runner.calls == 0
    assert (writer_runner.calls > 0) is writes
    # INV-9: the stop carries what CP1 sees at iteration 0, and JevAgent's run total as its usage rollup.
    assert (metadata["tokens_used"], metadata["tool_call_count"]) == (None, 0)
    assert (tuple(metadata["tool_call_states"]), tuple(metadata["tool_calls"])) == (
        (),
        (),
    )
    rollup = metadata["usage_rollup"]
    assert rollup == agent.response.usage.total == agent.get_usage()
    assert rollup.cost_usd is not None and rollup.cost_usd >= cap
    assert rollup.cost_measured is True
    assert agent.response.usage.decision.model_call_count == 1
    # INV-10: sessions route the stop as one exhausted resource, with exactly the three detail keys.
    (failure,) = FailureMetadataNormalizer.from_reply(reply)
    assert (failure.code, failure.status, failure.disposition) == (
        FailureCode.RESOURCE_EXHAUSTED,
        FailureStatus.EXHAUSTED,
        FailureDisposition.ROUTE,
    )
    assert dict(failure.details) == {
        "stop_reason": MAX_SPEND,
        "iteration_count": 0,
        "tokens_used": None,
    }


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
