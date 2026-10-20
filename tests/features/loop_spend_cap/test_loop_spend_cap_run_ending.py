"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_run_ending.py

PURPOSE: Prove a spend-cap stop ends the run it belongs to everywhere a middleware abort
already does: nothing reflects on it, reviews it, grades it, verifies it, retries it on
a fresh budget, or drains queued prompts after it.
ROLE IN CODEBASE: Behavior tests for spec INV-23 at every listed site: Reflexion
should_reflect, the independent critic and prosecutor-defender-judge producer checks,
the multi-provider grader's trial check, AgentTransfer.default_report_parser,
MagenticOneOrchestrator._structured_phase, InfiniteMemory's generator status, the
BaseAgent queued-prompt drain, and the output-schema check.
ARCHITECTURE NOTE: The algorithm cases drive AgentRuntime with the algorithm attached
and one scripted runner, so producer, reviewer, reflection and grader calls all reach
the same counter; the grader's per-provider runners come from the patched
ModalityDetector.create_runner, the seam its own tests use. The InfiniteMemory case
patches BaseAgent._runner_for_model, the one fake its feature pack uses, routing by
agent name. Each case runs an uncapped control first, so the harness is proven to make
the call the capped run must not make.
FUNCTION INVENTORY: test_reflexion_never_reflects_on_an_attempt_the_cap_stopped;
test_a_reflection_that_reaches_the_cap_stops_the_next_attempt_before_its_first_call;
test_a_capped_producer_is_returned_unreviewed;
test_the_grader_returns_a_capped_trial_without_grading;
test_a_capped_worker_blocks_its_task_without_retry;
test_a_capped_manager_phase_is_not_retried_as_a_parse_failure;
test_a_capped_infinite_memory_generator_is_failed_and_never_verified;
test_a_capped_reply_runs_no_queued_prompt;
test_a_drained_reply_that_hits_the_cap_ends_the_drain;
test_a_capped_reply_with_an_output_schema_raises_with_the_cap_stop.
COMMON MODIFICATION PATTERNS: A new place that retries, reviews or continues a finished
run adds one case: a capped run whose first stop is max_spend, an uncapped control
proving the follow-up call happens, and an assertion that it did not.
WHAT NOT TO DO IN THIS FILE: 1. Do not add max_spend to STOPPED_REPLIES in
tests/multi_agent/test_worker_stop_report.py; a capped worker is blocked, not stopped.
2. Do not edit the existing middleware-abort tests these mirror. 3. Do not reach the
network; clear provider key variables for the grader.
KNOWN EDGE CASES: The grader's trials share one tracker, so the second trial may also
stop on the cap; either way the run's result is a max_spend result and no grader call
runs. A drained prompt is its own reply with its own cap (INV-11).
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-11, INV-23, AC-23, AC-28, AC-29,
AC-31, AC-32, EC-20, EC-21, EC-23, EC-40, EC-42;
tests/test_algorithms_honor_middleware_abort.py; tests/multi_agent/test_manager_middleware_abort.py.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_run_ending.py
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from tests.agent_test_support import bind_test_runner
from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    MAX_SPEND,
    PRICED_MODEL,
    PRICED_PROVIDER,
    REACHED_TEXT,
    LookupTool,
    PricedSearchTool,
    ScriptedRunner,
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
from tests.test_pdj_stage_model_provenance import _ALLEGATIONS, _DECISIONS, _DEFENSES
from vidbyte import (
    ContextWindowAlgorithm,
    IndependentCriticAlgorithm,
    MultiProviderAgenticGraderAlgorithm,
    OutputSchemaViolationError,
    ProsecutorDefenderJudgeAlgorithm,
    ReflexionAlgorithm,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.infinite import (
    InfiniteMemoryAgent,
    InfiniteMemoryAgentSettings,
    InfiniteWorkspaceSettings,
)
from vidbyte.agents.multi import (
    AgentBinding,
    AgentTransfer,
    MagenticOneOrchestrator,
    MultiAgent,
)
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.context.algorithms.independent_critic import CriticFailurePolicy
from vidbyte.context.algorithms.prosecutor_defender_judge import (
    ProsecutorDefenderJudgeFailurePolicy,
)
from vidbyte.lib.config.constants import API_KEY_ENV_VARS
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.dataclasses.agents import AgentForkSettings, AgentRuntimeConfig
from vidbyte.lib.dataclasses.multi_agent import (
    AgentDispatch,
    MultiAgentSettings,
    TaskLedgerSnapshot,
)
from vidbyte.lib.enums.multi_agent import TaskStatus
from vidbyte.lib.errors import MultiAgentExecutionError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools.builtins.run_prompts_sequentially import RunPromptsSequentiallyTool

REVIEW_PASS = json.dumps(
    {"verdict": "pass", "summary": "The answer is supported.", "findings": []}
)
PHASES = {
    "plan": "PHASE=plan",
    "progress": "PHASE=progress",
    "replan": "PHASE=replan",
    "finalize": "PHASE=finalize",
}
ROOT = "lead"


def _config(cap: float | None, **fields: Any) -> AgentRuntimeConfig:
    return (
        AgentRuntimeConfig(**fields)
        if cap is None
        else AgentRuntimeConfig(max_spend_usd=cap, **fields)
    )


def _run_algorithm(
    responses: Sequence[object],
    algorithm: ContextWindowAlgorithm,
    *,
    cap: float | None,
    **fields: Any,
) -> tuple[Any, ScriptedRunner]:
    runner = ScriptedRunner(*responses)
    runtime = build_runtime(
        _config(cap, **fields), tools=[LookupTool()], algorithm=algorithm
    )
    return asyncio.run(run_runtime(runtime, runner)), runner


def _reflexion() -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(
        name="reflexion", reflexion=ReflexionAlgorithm(max_trials=3)
    )


def test_reflexion_never_reflects_on_an_attempt_the_cap_stopped() -> None:
    # AC-23 (i) and EC-21: a capped attempt is not a failed trial, so no reflection call and no second attempt.
    def script() -> list[object]:
        return [
            call_response(("lookup", {"q": "Paris"}), usage=usage(1_000, 100)),
            text_response("Try harder.", usage=usage(200, 20)),
            done_response("Paris.", usage=usage(10, 1)),
        ]

    responses = script()
    result, runner = _run_algorithm(
        responses, _reflexion(), cap=reference_cost(responses[0])
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert runner.calls == 1
    assert (
        result.metadata["reflexion"]["trial_count"],
        result.metadata["reflexion"]["reflection_count"],
    ) == (1, 0)


def test_a_reflection_that_reaches_the_cap_stops_the_next_attempt_before_its_first_call() -> (
    None
):
    # AC-23 (ii) and INV-11: the cap spans every attempt of one reply, so the second attempt's first CP1 stops it.
    def script() -> list[object]:
        return [
            call_response(("lookup", {"q": "Paris"}), usage=usage(1_000, 100)),
            text_response("Use the lookup result.", usage=usage(800, 60)),
            done_response("fixed", usage=usage(10, 1)),
        ]

    control, control_runner = _run_algorithm(
        script(), _reflexion(), cap=None, max_iterations=1
    )
    assert (control.output, control_runner.calls) == ("fixed", 3)

    responses = script()
    result, runner = _run_algorithm(
        responses,
        _reflexion(),
        cap=reference_cost(responses[0], responses[1]),
        max_iterations=1,
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert runner.calls == 2
    assert (
        result.metadata["reflexion"]["trial_count"],
        result.metadata["reflexion"]["reflection_count"],
    ) == (2, 1)


@pytest.mark.parametrize("kind", ["independent_critic", "prosecutor_defender_judge"])
def test_a_capped_producer_is_returned_unreviewed(kind: str) -> None:
    # AC-28 and EC-22: the producer's answer reaches the cap at CP2; no reviewer or debate stage runs on its stop text.
    if kind == "independent_critic":
        algorithm = ContextWindowAlgorithm(
            name=kind,
            independent_critic=IndependentCriticAlgorithm(
                failure_policy=CriticFailurePolicy.RETURN_CANDIDATE
            ),
        )
        reviews = [REVIEW_PASS]
    else:
        algorithm = ContextWindowAlgorithm(
            name=kind,
            prosecutor_defender_judge=ProsecutorDefenderJudgeAlgorithm(
                failure_policy=ProsecutorDefenderJudgeFailurePolicy.RETURN_CANDIDATE
            ),
        )
        reviews = [
            json.dumps(_ALLEGATIONS),
            json.dumps(_DEFENSES),
            json.dumps(_DECISIONS),
        ]

    def script() -> list[object]:
        return [
            text_response("FINAL Paris.", usage=usage(1_000, 100)),
            *(text_response(review, usage=usage(10, 1)) for review in reviews),
        ]

    control, control_runner = _run_algorithm(script(), algorithm, cap=None)
    assert (kind in control.metadata, control_runner.calls) == (True, 1 + len(reviews))

    responses = script()
    result, runner = _run_algorithm(
        responses, algorithm, cap=reference_cost(responses[0])
    )

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert runner.calls == 1
    assert kind not in result.metadata


def test_the_grader_returns_a_capped_trial_without_grading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-28 and EC-23: a trial the cap stopped is the run's result, with its stop text, and the grader is never called.
    for env_var in API_KEY_ENV_VARS.values():
        monkeypatch.delenv(env_var, raising=False)
    algorithm = ContextWindowAlgorithm(
        name="multi_provider_agentic_grader",
        multi_provider_agentic_grader=MultiProviderAgenticGraderAlgorithm(
            provider_models={"openai": "gpt-4o", "anthropic": "claude-sonnet-5"},
            grader_model="gpt-4.1-mini",
        ),
    )

    def run(
        cap: float | None, crossing: object
    ) -> tuple[Any, ScriptedRunner, ScriptedRunner]:
        openai, anthropic = (
            ScriptedRunner(crossing),
            ScriptedRunner(text_response("Paris is the capital.", usage=usage(10, 1))),
        )
        grader = ScriptedRunner(text_response("Paris.", usage=usage(10, 1)))
        runners = {
            ("openai", "gpt-4o"): openai,
            ("anthropic", "claude-sonnet-5"): anthropic,
            ("openai", "gpt-4.1-mini"): grader,
        }
        runtime = build_runtime(_config(cap), algorithm=algorithm)
        with patch(
            "vidbyte.agents.algorithms.multi_provider_agentic_grader.ModalityDetector.create_runner",
            side_effect=lambda modality, provider, model, **kwargs: runners[
                (provider, model)
            ],
        ):
            return asyncio.run(run_runtime(runtime, ScriptedRunner())), openai, grader

    control, _, control_grader = run(
        None, text_response("Paris.", usage=usage(1_000, 100))
    )
    assert (
        "multi_provider_agentic_grader" in control.metadata,
        control_grader.calls,
    ) == (True, 1)

    crossing = text_response("Paris.", usage=usage(1_000, 100))
    result, openai, grader = run(reference_cost(crossing), crossing)

    assert (result.output, result.metadata["stop_reason"]) == (REACHED_TEXT, MAX_SPEND)
    assert (openai.calls, grader.calls) == (1, 0)
    assert "multi_provider_agentic_grader" not in result.metadata


def test_a_capped_worker_blocks_its_task_without_retry() -> None:
    # AC-29 (i): a real capped worker reply is BLOCKED with one non-retryable max_spend blocker, never a retryable worker_stopped.
    response = call_response(("lookup", {"q": "Paris"}), usage=usage(1_000, 100))
    worker = priced_agent(
        ScriptedRunner(response),
        name="worker",
        tools=[LookupTool()],
        loop=capped_settings(reference_cost(response)),
    )
    reply = worker.run("Find the capital.")
    dispatch = AgentDispatch(
        run_id="run",
        base_revision=0,
        task_id="task-1",
        owner="worker",
        goal="goal",
        instruction="run",
    )

    report = AgentTransfer.default_report_parser(
        reply, dispatch, TaskLedgerSnapshot(run_id="run", goal="goal")
    )

    assert reply.metadata["stop_reason"] == MAX_SPEND
    assert report.status is TaskStatus.BLOCKED
    (blocker,) = report.blockers
    assert (blocker.code, blocker.retryable, blocker.message) == (
        "max_spend",
        False,
        "Worker run stopped at its spend cap.",
    )


class PhaseRunner:
    """The manager's model: answers each phase by its marker and counts calls per phase."""

    def __init__(self, plan_reply: TextModelResponse) -> None:
        self.plan_reply = plan_reply
        self.calls = dict.fromkeys(PHASES, 0)

    async def arun(self, prompt: str, **options: Any) -> object:
        phase = next(name for name, marker in PHASES.items() if marker in prompt)
        self.calls[phase] += 1
        return (
            self.plan_reply
            if phase == "plan"
            else text_response("unused", usage=usage(1, 1))
        )


class StaticWorker(BaseAgent):
    """A provider-free worker; the plan phase stops before any task is dispatched."""

    def __init__(self) -> None:
        super().__init__(name="worker", system_prompt="work")

    def fork(self, settings: AgentForkSettings | None = None) -> StaticWorker:
        return StaticWorker()

    async def generate_reply(
        self, message: str | AgentInput, **options: Any
    ) -> AgentMessage:
        return AgentMessage(sender=self.name, recipient="team", content="worker output")


def _fork_phase(
    runner: PhaseRunner,
    created: list[str],
    source: BaseAgent,
    phase: str,
    settings: AgentForkSettings,
) -> BaseAgent:
    created.append(phase)
    return bind_test_runner(source.fork(settings), runner)


def test_a_capped_manager_phase_is_not_retried_as_a_parse_failure() -> None:
    # AC-29 (ii) and EC-42: the plan phase reaches the cap on its one call; a parse retry would fork a fresh phase agent with a fresh cap.
    plan_body = json.dumps(
        {
            "plan_summary": "one task",
            "tasks": [{"task_id": "task-1", "goal": "do work", "owner": "worker"}],
        }
    )
    plan_reply = TextModelResponse(
        provider=PRICED_PROVIDER,
        model=PRICED_MODEL,
        text=plan_body,
        raw={},
        usage=usage(400, 60),
    )
    runner, created = PhaseRunner(plan_reply), []
    manager = bind_test_runner(
        BaseAgent(
            name="manager",
            system_prompt="manage",
            provider=PRICED_PROVIDER.value,
            model_name=PRICED_MODEL,
            agent_loop_settings=capped_settings(
                reference_cost(plan_reply), max_iterations=1
            ),
        ),
        runner,
    )
    orchestrator = MagenticOneOrchestrator(
        manager,
        planning_prompt=PHASES["plan"],
        progress_prompt=PHASES["progress"],
        replanning_prompt=PHASES["replan"],
        final_prompt=PHASES["finalize"],
        parse_retries=2,
        manager_agent_factory=partial(_fork_phase, runner, created),
    )
    team = MultiAgent(
        name="team",
        system_prompt="coordinate",
        orchestrator=orchestrator,
        agents=(AgentBinding(StaticWorker(), transfer=AgentTransfer()),),
        settings=MultiAgentSettings(max_rounds=4),
    )

    with pytest.raises(MultiAgentExecutionError) as caught:
        asyncio.run(team.generate_reply("complete the task"))

    assert str(caught.value) == "Multi-agent manager phase stopped at its spend cap."
    assert caught.value.details["stop_reason"] == MAX_SPEND
    assert (caught.value.details["phase"], caught.value.details["attempts"]) == (
        "plan",
        1,
    )
    assert getattr(caught.value.__cause__, "stop_reason", None) == MAX_SPEND
    assert (runner.calls["plan"], created.count("plan")) == (1, 1)


def _infinite_agent(tmp_path: Path, loop: AgentLoopSettings) -> InfiniteMemoryAgent:
    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    settings = InfiniteMemoryAgentSettings(
        name=ROOT,
        system_prompt="You research.",
        provider=PRICED_PROVIDER.value,
        model_name=PRICED_MODEL,
        root_dir=project,
        workspace=InfiniteWorkspaceSettings(root=project / "memory"),
        loop=loop,
    )
    return InfiniteMemoryAgent(settings)


def _infinite_run(
    tmp_path: Path, loop: AgentLoopSettings, generator_answer: TextModelResponse
) -> tuple[Any, dict[str, ScriptedRunner]]:
    card = {
        "name": "alpha",
        "goal": "Find the price of alpha.",
        "done_criteria": ["The price has a source"],
        "generator_prompt": "Research alpha.",
        "verifier_prompt": "Check the alpha price.",
    }
    runners = {
        ROOT: ScriptedRunner(
            call_response(("launch_subagent", {"tasks": [card]}), usage=usage(100, 10)),
            text_response("All done.", usage=usage(10, 1)),
        ),
        f"{ROOT}/root/alpha/gen": ScriptedRunner(generator_answer),
        f"{ROOT}/root/alpha/ver": ScriptedRunner(
            text_response("Checked.\nVERDICT: passed", usage=usage(10, 1))
        ),
    }

    def runner_for(agent: BaseAgent) -> tuple[object, str]:
        return runners[agent.name], RUNNER_TYPE_TEXT

    agent = _infinite_agent(tmp_path, loop)
    with patch.object(BaseAgent, "_runner_for_model", new=runner_for):
        reply = agent.run("Price alpha.")
    return reply, runners


def test_a_capped_infinite_memory_generator_is_failed_and_never_verified(
    tmp_path: Path,
) -> None:
    # AC-29 (iii): the generator's answer reaches its own cap at CP2, so it is FAILED and no verifier runs on its stop text.
    def answer() -> TextModelResponse:
        return text_response("alpha costs 10 dollars.", usage=usage(1_000, 100))

    _, control = _infinite_run(
        tmp_path / "control", AgentLoopSettings(max_iterations=8), answer()
    )
    assert control[f"{ROOT}/root/alpha/ver"].calls == 1

    generator_answer = answer()
    reply, runners = _infinite_run(
        tmp_path / "capped",
        capped_settings(reference_cost(generator_answer), max_iterations=8),
        generator_answer,
    )

    assert runners[f"{ROOT}/root/alpha/gen"].calls == 1
    assert runners[f"{ROOT}/root/alpha/ver"].calls == 0
    assert reply.metadata["stop_reason"] == MAX_SPEND


def test_a_capped_reply_runs_no_queued_prompt() -> None:
    # AC-31 (i) and EC-20, through enqueue_prompts and through the model-facing run_prompts_sequentially tool.
    first = call_response(("lookup", {"q": "Paris"}), usage=usage(1_000, 100))
    enqueued = priced_agent(
        ScriptedRunner(first, text_response("unused", usage=usage(1, 1))),
        tools=[LookupTool()],
        loop=capped_settings(reference_cost(first)),
    )
    enqueued.enqueue_prompts(["second question", "third question"])

    reply = enqueued.run("first question")

    assert reply.metadata["stop_reason"] == MAX_SPEND
    assert reply.metadata["queued_prompts_truncated"] == 2
    assert "queued_prompt_runs" not in reply.metadata
    assert enqueued.last_queued_replies == []

    operation_cost = 0.01
    turn = call_response(
        (
            "run_prompts_sequentially",
            {"prompts": ["second question", "third question"]},
        ),
        ("priced_search", {"q": "Paris"}),
        usage=usage(1_000, 100),
    )
    runner = ScriptedRunner(turn, text_response("unused", usage=usage(1, 1)))
    queued_by_model = priced_agent(
        runner,
        tools=[RunPromptsSequentiallyTool(), PricedSearchTool(operation_cost)],
        loop=capped_settings(reference_cost(turn, operations=[operation_cost])),
    )

    reply = queued_by_model.run("first question")

    assert reply.metadata["stop_reason"] == MAX_SPEND
    assert reply.metadata["queued_prompts_truncated"] == 2
    assert "queued_prompt_runs" not in reply.metadata
    assert runner.calls == 1


def test_a_drained_reply_that_hits_the_cap_ends_the_drain() -> None:
    # AC-31 (ii) and INV-11: each drained prompt is its own reply with its own cap; once one stops on it, the rest are dropped.
    def script() -> list[object]:
        return [
            text_response("first answer", usage=usage(10, 1)),
            call_response(("lookup", {"q": "Paris"}), usage=usage(1_000, 100)),
            *(text_response("later answer", usage=usage(10, 1)) for _ in range(3)),
        ]

    control = priced_agent(ScriptedRunner(*script()), tools=[LookupTool()])
    control.enqueue_prompts(["second", "third", "fourth"])
    assert control.run("first").metadata["queued_prompt_runs"] == 3

    responses = script()
    runner = ScriptedRunner(*responses)
    agent = priced_agent(
        runner, tools=[LookupTool()], loop=capped_settings(reference_cost(responses[1]))
    )
    agent.enqueue_prompts(["second", "third", "fourth"])

    reply = agent.run("first")

    assert reply.metadata["stop_reason"] == "final_response"
    assert [queued.metadata["stop_reason"] for queued in agent.last_queued_replies] == [
        MAX_SPEND
    ]
    assert (
        reply.metadata["queued_prompt_runs"],
        reply.metadata["queued_prompts_truncated"],
    ) == (1, 2)
    assert runner.calls == 2


class Capital(BaseModel):
    city: str


def test_a_capped_reply_with_an_output_schema_raises_with_the_cap_stop() -> None:
    # AC-32 and EC-40: a cap stop carries no schema instance, so the schema check raises with the cap's stop reason, before the drain.
    first = call_response(("lookup", {"q": "Paris"}), usage=usage(1_000, 100))
    runner = ScriptedRunner(
        first, text_response('{"city": "Paris"}', usage=usage(1, 1))
    )
    agent = priced_agent(
        runner,
        tools=[LookupTool()],
        loop=capped_settings(reference_cost(first)),
        output_schema=Capital,
    )
    agent.enqueue_prompts(["second question"])

    with pytest.raises(OutputSchemaViolationError) as caught:
        agent.run("first question")

    assert caught.value.stop_reason == MAX_SPEND
    assert (
        agent.last_reply is not None
        and agent.last_reply.metadata["stop_reason"] == MAX_SPEND
    )
    assert runner.calls == 1
