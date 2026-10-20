"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_runtime.py

PURPOSE: Prove the four spend-cap check points of the shared agent loop stop a run at
the right moment: before the next model call (CP1), on a plain-text finish (CP2),
before every tool call including internal ones (CP3), and before the after-tool
iteration hook (CP4), for a reached cap and for a blind meter, and that a cap the
run never reaches changes nothing.
ROLE IN CODEBASE: Behavior tests for AgentRuntime._arun_once and its new
_spend_cap_stop, driven either through BaseAgent.generate_reply (reply level) or
AgentRuntime.arun with a scripted RunnerHandle (runtime level).
ARCHITECTURE NOTE: Only the model wire is scripted. UsageTracker, the runtime loop,
middleware dispatch and the tool executor are production code. Each expected dollar
figure is the reference_cost of the same scripted responses, so "spend equals the
cap" compares identical floats. A ProbeRuntime subclass counts the two runtime hooks
the spec names (_continue_finish_attempt, _after_tool_iteration) by calling through
to the real ones; a HookProbe middleware records which hooks ran.
FUNCTION INVENTORY: test_a_tool_turn_that_reaches_the_cap_runs_none_of_its_tools;
test_a_cap_the_run_never_reaches_changes_nothing; test_a_plain_text_answer_that_reaches_the_cap_is_replaced_before_any_finish_work;
test_a_finish_or_internal_tool_requested_after_the_cap_never_executes;
test_a_priced_operation_that_crosses_the_cap_stops_the_next_tool_in_its_turn;
test_a_last_tool_that_crosses_the_cap_stops_before_the_after_tool_iteration_hook;
test_a_response_without_usage_stops_the_run_blind;
test_a_response_naming_an_unpriced_model_stops_the_run_and_names_it;
test_openrouter_spend_is_enforced_from_its_reported_cost;
test_a_failed_operation_recording_stops_the_run_blind;
test_spend_after_the_last_tool_check_is_caught_at_the_next_iteration_before_max_iterations.
COMMON MODIFICATION PATTERNS: A new check point adds one test that puts the
crossing spend immediately before it and asserts the stop and what did not run; a
new budget sharing a check point adds a parametrized tie case.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock UsageTracker, AgentRuntime._arun_once or
generate_reply's ledger scope. 2. Do not hard-code a dollar amount from today's
rates; derive it with reference_cost. 3. Do not import AgentStopReason.MAX_SPEND or
AgentSpendCap at module level; each test must fail on its own missing name.
KNOWN EDGE CASES: A max_tokens or max_tool_calls tie at the same check point must
stop with max_spend (INV-8). A cap stop's metadata keys equal those of any other
budget stop (INV-9 "no new metadata key"). OpenRouter's reported cost prices a call
the empty OpenRouter table cannot (EC-8).
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-4, INV-5, INV-8, INV-9, AC-4..AC-9,
AC-22, EC-5..EC-16, EC-25; tests/features/loop_spend_cap/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_runtime.py
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from typing import Any

import pytest

from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    MAX_SPEND,
    PRICED_MODEL,
    REACHED_TEXT,
    UNPRICED_MODEL,
    LaunchLikeTool,
    LookupTool,
    PricedSearchTool,
    ScriptedRunner,
    assert_price_preconditions,
    blind_text,
    build_runtime,
    call_response,
    capped_settings,
    done_response,
    priced_agent,
    reference_cost,
    run_runtime,
    text_response,
    usage,
)
from vidbyte.agents import AgentRuntime
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, FinishReview
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.middleware.base import AgentMiddleware

OPENROUTER_MODEL = "openai/" + UNPRICED_MODEL


class ProbeRuntime(AgentRuntime):
    """AgentRuntime that counts the two specialized-runtime hooks the spec names, then runs the real ones."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.finish_attempts = 0
        self.tool_iterations = 0

    async def _continue_finish_attempt(
        self, result: Any, state: Any, messages: list[dict[str, Any]]
    ) -> bool:
        self.finish_attempts += 1
        return await super()._continue_finish_attempt(result, state, messages)

    async def _after_tool_iteration(
        self, state: Any, messages: list[dict[str, Any]]
    ) -> None:
        self.tool_iterations += 1
        await super()._after_tool_iteration(state, messages)


class ComputeCheckpointRuntime(ProbeRuntime):
    """Records one more priced model call in the after-tool hook, as JevAgent's compute checkpoint does with its decision calls."""

    checkpoint_response: object = None

    async def _after_tool_iteration(
        self, state: Any, messages: list[dict[str, Any]]
    ) -> None:
        await super()._after_tool_iteration(state, messages)
        self.usage_tracker.record_call(self.checkpoint_response)


class HookProbe(AgentMiddleware):
    """Records, in order, every middleware hook the spend cap must run before."""

    def __init__(self) -> None:
        self.hooks: list[str] = []

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append("before_tool_call")
        return MiddlewareDecision.continue_()

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append("after_iteration")
        return MiddlewareDecision.continue_()

    async def review_finish(self, ctx: MiddlewareContext) -> FinishReview:
        self.hooks.append("review_finish")
        return FinishReview.accept()


class PoisonedSearchTool(PricedSearchTool):
    """A priced search whose cost report raises, so the runtime marks the ledger corrupted (EC-7)."""

    def reported_cost_usd(self, call: Any, result: Any) -> float | None:
        raise RuntimeError("cost report unavailable")


def _runtime_config(cap: float | None, fields: dict[str, Any]) -> AgentRuntimeConfig:
    # The capped config is built only when a cap is asked for, so a control run works before the feature exists.
    return (
        AgentRuntimeConfig(**fields)
        if cap is None
        else AgentRuntimeConfig(max_spend_usd=cap, **fields)
    )


def _run_runtime(
    responses: Sequence[object],
    *,
    cap: float | None,
    fields: dict[str, Any] | None = None,
    tools: Sequence[object] = (),
    runtime_class: type[AgentRuntime] = ProbeRuntime,
) -> tuple[Any, ScriptedRunner, Any, HookProbe]:
    probe = HookProbe()
    runner = ScriptedRunner(*responses)
    runtime = build_runtime(
        _runtime_config(cap, dict(fields or {})),
        tools=tools,
        middleware=(probe,),
        runtime_class=runtime_class,
    )
    result = asyncio.run(run_runtime(runtime, runner))
    return result, runner, runtime, probe


def _loop(cap: float | None, **fields: Any) -> AgentLoopSettings:
    return (
        AgentLoopSettings(**fields) if cap is None else capped_settings(cap, **fields)
    )


def _run_agent(
    responses: Sequence[object],
    *,
    cap: float | None,
    tools: Sequence[object] = (),
    **fields: Any,
) -> tuple[Any, ScriptedRunner, Any]:
    runner = ScriptedRunner(*responses)
    agent = priced_agent(runner, tools=list(tools), loop=_loop(cap, **fields))
    reply = agent.run("Look up Paris.")
    return reply, runner, agent


def test_a_tool_turn_that_reaches_the_cap_runs_none_of_its_tools() -> None:
    # AC-4 and EC-25: call 2's own spend brings the run to exactly C, so CP3 must stop before its lookup, with `>=`.
    assert_price_preconditions()
    first = call_response(("lookup", {"q": "first"}), usage=usage(1_000, 100))
    second = call_response(("lookup", {"q": "second"}), usage=usage(1_000, 100))
    cap = reference_cost(first, second)
    lookup = LookupTool()

    reply, runner, agent = _run_agent(
        [first, second, text_response("unreachable", usage=usage(1, 1))],
        cap=cap,
        tools=[lookup],
    )

    assert lookup.executed == [{"q": "first"}]
    assert runner.calls == 2
    assert (reply.content, reply.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    rollup = reply.metadata["usage_rollup"]
    assert rollup.cost_usd is not None and rollup.cost_usd >= cap
    assert rollup.cost_usd == agent.get_usage().cost_usd
    assert rollup.cost_measured is True


def _scenario(name: str) -> tuple[list[object], dict[str, Any]]:
    # Each scenario ends on a different existing stop; the cap sits one float step above all of its spend.
    lookup = ("lookup", {"q": "Paris"})
    turns: dict[str, tuple[list[object], dict[str, Any]]] = {
        "final_response": (
            [
                call_response(lookup, usage=usage(1_000, 100)),
                text_response("Paris.", usage=usage(1_200, 40)),
            ],
            {},
        ),
        "is_done": (
            [
                call_response(lookup, usage=usage(1_000, 100)),
                done_response("Paris.", usage=usage(1_200, 40)),
            ],
            {},
        ),
        "max_iterations": (
            [call_response(lookup, usage=usage(1_000, 100))],
            {"max_iterations": 1},
        ),
        "max_tool_calls": (
            [call_response(lookup, lookup, usage=usage(1_000, 100))],
            {"max_tool_calls": 1},
        ),
        "max_tokens": (
            [call_response(lookup, usage=usage(1_000, 100))],
            {"max_tokens": 1},
        ),
    }
    return turns[name]


def _observable(
    reply: Any, runner: ScriptedRunner, lookup: LookupTool
) -> dict[str, Any]:
    metadata = reply.metadata
    return {
        "content": reply.content,
        "stop_reason": metadata["stop_reason"],
        "iteration_outputs": metadata.get("iteration_outputs"),
        "iteration_count": metadata["iteration_count"],
        "tokens_used": metadata["tokens_used"],
        "tool_call_states": metadata["tool_call_states"],
        "model_calls": runner.calls,
        "lookups": list(lookup.executed),
        "cost_usd": metadata["usage_rollup"].cost_usd,
    }


@pytest.mark.parametrize(
    "name",
    ["final_response", "is_done", "max_iterations", "max_tool_calls", "max_tokens"],
)
def test_a_cap_the_run_never_reaches_changes_nothing(name: str) -> None:
    # INV-8 and INV-17: with the cap one float step above every dollar the run spends, the reply equals the uncapped one.
    responses, fields = _scenario(name)
    cap = math.nextafter(reference_cost(*responses), math.inf)
    lookup = LookupTool()
    uncapped = _observable(
        *_run_agent(_scenario(name)[0], cap=None, tools=[lookup], **fields)[:2], lookup
    )
    assert uncapped["stop_reason"] == name

    lookup = LookupTool()
    capped = _observable(
        *_run_agent(responses, cap=cap, tools=[lookup], **fields)[:2], lookup
    )

    assert capped == uncapped


@pytest.mark.parametrize(
    ("fields", "uncapped_stop"),
    [({}, "final_response"), ({"max_tokens": 1}, "max_tokens")],
    ids=["finish", "max_tokens_tie"],
)
def test_a_plain_text_answer_that_reaches_the_cap_is_replaced_before_any_finish_work(
    fields: dict[str, Any], uncapped_stop: str
) -> None:
    # AC-5, EC-12 and the INV-8 tie at CP2: the answer that reaches C never reaches review_finish, after_iteration or a finish attempt.
    answer = text_response("Paris is the capital.", usage=usage(1_000, 100))
    control, _, control_runtime, control_probe = _run_runtime(
        [text_response("Paris is the capital.", usage=usage(1_000, 100))],
        cap=None,
        fields=fields,
    )
    assert control.metadata["stop_reason"] == uncapped_stop
    if uncapped_stop == "final_response":
        assert (control_probe.hooks, control_runtime.finish_attempts) == (
            ["review_finish", "after_iteration"],
            1,
        )

    result, runner, runtime, probe = _run_runtime(
        [answer], cap=reference_cost(answer), fields=fields
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert result.metadata["iteration_outputs"] == ("Paris is the capital.",)
    assert probe.hooks == []
    assert runtime.finish_attempts == 0
    assert runner.calls == 1


@pytest.mark.parametrize("internal", ["isDone", "launch_helpers"])
def test_a_finish_or_internal_tool_requested_after_the_cap_never_executes(
    internal: str,
) -> None:
    # AC-6 and EC-13: CP3 binds internal tools too, and runs before before_tool_call middleware.
    launch = LaunchLikeTool(name="launch_helpers")
    arguments = {"final_answer": "Paris."} if internal == "isDone" else {}
    response = call_response(
        (internal, arguments), usage=usage(1_000, 100), text="Wrapping up."
    )

    result, runner, runtime, probe = _run_runtime(
        [response], cap=reference_cost(response), tools=[launch]
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert result.metadata["iteration_outputs"] == ("Wrapping up.",)
    assert launch.executed == []
    assert probe.hooks == []
    assert (runtime.finish_attempts, runtime.tool_iterations, runner.calls) == (0, 0, 1)


@pytest.mark.parametrize(
    ("fields", "uncapped_stop"),
    [({}, "final_response"), ({"max_tool_calls": 1}, "max_tool_calls")],
    ids=["free_turn", "max_tool_calls_tie"],
)
def test_a_priced_operation_that_crosses_the_cap_stops_the_next_tool_in_its_turn(
    fields: dict[str, Any], uncapped_stop: str
) -> None:
    # AC-7 and the INV-8 tie at CP3: the search's own spend reaches C, so the lookup after it in the same turn never runs.
    operation_cost = 0.01
    turn = [("priced_search", {"q": "Paris"}), ("lookup", {"q": "Paris"})]
    control_lookup = LookupTool()
    control, *_ = _run_runtime(
        [
            call_response(*turn, usage=usage(1_000, 0)),
            text_response("Paris.", usage=usage(1, 1)),
        ],
        cap=None,
        fields=fields,
        tools=[PricedSearchTool(operation_cost), control_lookup],
    )
    assert control.metadata["stop_reason"] == uncapped_stop

    response = call_response(*turn, usage=usage(1_000, 0))
    search, lookup = PricedSearchTool(operation_cost), LookupTool()
    result, runner, _, _ = _run_runtime(
        [response],
        cap=reference_cost(response, operations=[operation_cost]),
        fields=fields,
        tools=[search, lookup],
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert (len(search.executed), lookup.executed, runner.calls) == (1, [], 1)
    assert result.metadata["usage_rollup"].operation_count == 1


def test_a_last_tool_that_crosses_the_cap_stops_before_the_after_tool_iteration_hook() -> (
    None
):
    # AC-7 and EC-15 (CP4): the turn's last tool crosses C; after_iteration still runs, _after_tool_iteration never does.
    operation_cost = 0.01
    control, control_runner, control_runtime, _ = _run_runtime(
        [
            call_response(("priced_search", {"q": "a"}), usage=usage(1_000, 0)),
            text_response("Paris.", usage=usage(1, 1)),
        ],
        cap=None,
        tools=[PricedSearchTool(operation_cost)],
    )
    assert (
        control.metadata["stop_reason"],
        control_runtime.tool_iterations,
        control_runner.calls,
    ) == ("final_response", 1, 2)

    response = call_response(("priced_search", {"q": "a"}), usage=usage(1_000, 0))
    result, runner, runtime, probe = _run_runtime(
        [response],
        cap=reference_cost(response, operations=[operation_cost]),
        tools=[PricedSearchTool(operation_cost)],
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert probe.hooks == ["before_tool_call", "after_iteration"]
    assert runtime.tool_iterations == 0
    assert runner.calls == 1


def test_a_response_without_usage_stops_the_run_blind() -> None:
    # AC-8 and EC-6: one unaccounted call blinds the meter, so CP3 stops far below the cap and says why.
    def script() -> list[object]:
        return [
            call_response(("lookup", {"q": "Paris"}), usage=None),
            text_response("Paris.", usage=usage(10, 1)),
        ]

    control_lookup = LookupTool()
    control, _, _ = _run_agent(script(), cap=None, tools=[control_lookup])
    assert (control.metadata["stop_reason"], len(control_lookup.executed)) == (
        "final_response",
        1,
    )

    lookup = LookupTool()
    reply, runner, _ = _run_agent(script(), cap=1.0, tools=[lookup])

    assert reply.metadata["stop_reason"] == MAX_SPEND
    assert reply.content == blind_text("1 model calls reported no usage")
    assert reply.content.endswith(
        "could not be fully measured: 1 model calls reported no usage."
    )
    rollup = reply.metadata["usage_rollup"]
    assert (rollup.unaccounted_call_count, rollup.cost_measured) == (1, False)
    assert (lookup.executed, runner.calls) == ([], 1)


def test_a_response_naming_an_unpriced_model_stops_the_run_and_names_it() -> None:
    # AC-9 and EC-5 (run time): the configured model is priced, but call 2 reports a model the pricebook lacks.
    assert_price_preconditions()
    priced = call_response(("lookup", {"q": "first"}), usage=usage(1_000, 100))
    unpriced = call_response(
        ("lookup", {"q": "second"}), usage=usage(1_000, 100), model=UNPRICED_MODEL
    )
    lookup = LookupTool()

    reply, runner, _ = _run_agent([priced, unpriced], cap=1.0, tools=[lookup])

    assert (reply.content, reply.metadata["stop_reason"]) == (
        blind_text(f"no price for openai:{UNPRICED_MODEL}"),
        MAX_SPEND,
    )
    rollup = reply.metadata["usage_rollup"]
    assert rollup.cost_measured is False
    assert rollup.cost_usd == reference_cost(priced)
    assert (lookup.executed, runner.calls) == ([{"q": "first"}], 2)


def _openrouter_answer(usage_payload: dict[str, Any]) -> TextModelResponse:
    return TextModelResponse(
        provider=ModelProvider.OPENROUTER,
        model=OPENROUTER_MODEL,
        text="Paris.",
        raw={},
        usage=usage_payload,
    )


@pytest.mark.parametrize(
    ("usage_payload", "expected_output", "measured"),
    [
        (
            {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.5},
            REACHED_TEXT,
            True,
        ),
        (
            {"prompt_tokens": 10, "completion_tokens": 2},
            blind_text(f"no price for openrouter:{OPENROUTER_MODEL}"),
            False,
        ),
    ],
    ids=["reported_cost_reaches_cap", "no_reported_cost"],
)
def test_openrouter_spend_is_enforced_from_its_reported_cost(
    usage_payload: dict[str, Any], expected_output: str, measured: bool
) -> None:
    # AC-9, EC-8 and EC-9: OpenRouter is exempt at construction, so its reported cost is the meter, and a missing one blinds it.
    runner = ScriptedRunner(_openrouter_answer(usage_payload))
    agent = priced_agent(
        runner,
        provider="openrouter",
        model_name=OPENROUTER_MODEL,
        loop=capped_settings(0.5),
    )

    reply = agent.run("Capital of France?")

    assert (reply.content, reply.metadata["stop_reason"]) == (
        expected_output,
        MAX_SPEND,
    )
    assert reply.metadata["usage_rollup"].cost_measured is measured
    assert reply.metadata["iteration_outputs"] == ("Paris.",)


def test_a_failed_operation_recording_stops_the_run_blind() -> None:
    # EC-7: a recording failure corrupts the ledger, so the next check point stops and names it.
    turn = [("priced_search", {"q": "Paris"}), ("lookup", {"q": "Paris"})]
    control_lookup = LookupTool()
    control, _, _ = _run_agent(
        [
            call_response(*turn, usage=usage(1_000, 0)),
            text_response("Paris.", usage=usage(1, 1)),
        ],
        cap=None,
        tools=[PoisonedSearchTool(0.01), control_lookup],
    )
    assert (control.metadata["stop_reason"], len(control_lookup.executed)) == (
        "final_response",
        1,
    )

    lookup = LookupTool()
    reply, runner, _ = _run_agent(
        [call_response(*turn, usage=usage(1_000, 0))],
        cap=1.0,
        tools=[PoisonedSearchTool(0.01), lookup],
    )

    assert (reply.content, reply.metadata["stop_reason"]) == (
        blind_text("usage recording failed"),
        MAX_SPEND,
    )
    assert reply.metadata["usage_rollup"].cost_measured is False
    assert (lookup.executed, runner.calls) == ([], 1)


def test_spend_after_the_last_tool_check_is_caught_at_the_next_iteration_before_max_iterations() -> (
    None
):
    # AC-22, EC-16 and EC-24: the after-tool hook spends the rest of C, so the next CP1 sees both the cap and
    # max_iterations exhausted, and the cap is checked first; its metadata has exactly the keys of any budget stop.
    def run(
        cap: float | None, response: object, checkpoint: object
    ) -> tuple[Any, ScriptedRunner, Any]:
        runtime_class = type(
            "CheckpointRuntime",
            (ComputeCheckpointRuntime,),
            {"checkpoint_response": checkpoint},
        )
        result, runner, runtime, _ = _run_runtime(
            [response],
            cap=cap,
            fields={"max_iterations": 1},
            tools=[LookupTool()],
            runtime_class=runtime_class,
        )
        return result, runner, runtime

    def turn() -> tuple[object, object]:
        return call_response(
            ("lookup", {"q": "Paris"}), usage=usage(1_000, 100)
        ), text_response("", usage=usage(2_000, 0), model=PRICED_MODEL)

    control, _, _ = run(None, *turn())
    assert control.metadata["stop_reason"] == "max_iterations"

    response, checkpoint = turn()
    result, runner, runtime = run(
        reference_cost(response, checkpoint), response, checkpoint
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert (runtime.tool_iterations, runner.calls) == (1, 1)
    assert set(result.metadata) == set(control.metadata)
