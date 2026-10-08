"""FILE: scripts/sdk_edge_probes/run.py

PURPOSE: Run concrete, offline consumer programs through the SDK's public agent and handoff APIs to expose interactions missed by isolated unit tests.
ROLE IN CODEBASE: Developer-run probe harness outside the installable vidbyte package. Builds real Agent, HandoffAgent, Trace, middleware and tool objects; replaces only model transport.
ARCHITECTURE NOTE: An in-memory runner returns provider-shaped TextModelResponse objects; _runner_cache injection is deliberately isolated to bind_offline to avoid external API keys or network calls.
FUNCTION INVENTORY: bind_offline(agent, runner) substitutes text transport; done(answer) creates a model isDone call; run_agent_flow() checks two sequential tool/trace/usage runs; run_budget_flow() tests middleware enforcement; run_tool_limit_flow() tests same-iteration tool policy; run_structured_flow() validates structured output; run_handoff_flow() generates an EngineeringHandoff; run_jev_flow() combines preflight and generative usage; main() executes all programs.
COMMON MODIFICATION PATTERNS: Add another small consumer scenario with observable assertions, not a mock of SDK business logic. Keep all scripted response bodies explicit.
WHAT NOT TO DO IN THIS FILE: 1. Never call live model providers. 2. Never patch the SDK run loop or permission logic. 3. Do not import test-only helpers.
KNOWN EDGE CASES: Reused agents must not leak a previous run's tool counters or cost into the next; handoff generation owns an output schema distinct from plain text replies.
RELATED DOCS: scripts/sdk_edge_probes/README.md records how to run these probes and findings.
TESTS: Run `python -m scripts.sdk_edge_probes.run`; the full source gate runs repository tests separately.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from vidbyte import Agent, EngineeringHandoff, HandoffAgent, JevAgent, JevAgentSettings, JevPreflightPreset, JevRuntimeSettings, Trace, tool
from vidbyte.agents.settings import AgentLoopSettings, ToolSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants import RUNNER_TYPE_TEXT
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.enums import DecisionModelMode, JevQuestionType, ModelProvider
from vidbyte.lib.runners.types import DecisionModelResponse, TextModelResponse
from vidbyte.middleware.builtins import CostBudgetMiddleware, RuntimeLimitMiddleware


class ScriptedRunner:
    """Return offline responses in the same order a text provider would."""

    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = outputs
        self.calls = 0

    def run(self, prompt: str, **kwargs: object) -> TextModelResponse:
        self.calls += 1
        return TextModelResponse(
            provider=ModelProvider.OPENAI,
            model="gpt-5.4-mini",
            text="",
            raw=self.outputs.pop(0),
            usage={"input_tokens": 100, "output_tokens": 10},
        )


def bind_offline(agent: Agent, runner: ScriptedRunner) -> None:
    # Only the outbound model call is replaced; runtime, middleware, tool execution and accounting remain real.
    agent._runner_cache[RUNNER_TYPE_TEXT] = runner


def done(answer: str) -> dict[str, object]:
    return {"output": [{"type": "function_call", "name": "isDone", "arguments": json.dumps({"final_answer": answer})}]}


async def run_agent_flow() -> None:
    seen: list[str] = []

    @tool
    def lookup(topic: str) -> str:
        """Look up a local topic for this offline probe."""
        seen.append(topic)
        return "found:" + topic

    events: list[dict[str, object]] = []
    runner = ScriptedRunner([
        {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic":"sdk"}', "call_id": "first"}]},
        done("first finished"),
        done("second finished"),
    ])
    agent = Agent(
        name="offline-consumer", system_prompt="Use tools, then finish.",
        provider="openai", model_name="gpt-5.4-mini", tools=[lookup],
        agent_loop_settings=AgentLoopSettings(max_iterations=3, tool_settings=ToolSettings(max_calls=2)),
        middleware=[RuntimeLimitMiddleware(max_model_calls=3)], trace=Trace.debug(events),
    )
    bind_offline(agent, runner)
    first = await agent.arun("look up sdk")
    assert first.content == "first finished" and seen == ["sdk"]
    assert first.metadata["tool_call_count"] == 2
    assert agent.get_usage().model_call_count == 2
    second = await agent.arun("finish without a lookup")
    assert second.content == "second finished" and second.metadata["tool_call_count"] == 1
    assert agent.get_usage().model_call_count == 1
    assert events and runner.calls == 3
    print("PASS: agent tool + middleware + trace + usage across two runs")


async def run_budget_flow() -> None:
    @tool
    def lookup() -> str:
        """Perform a read-only offline lookup."""
        return "found"

    runner = ScriptedRunner([{"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}])
    agent = Agent(name="budget-consumer", system_prompt="Look up and finish.", provider="openai", model_name="gpt-5.4-mini", tools=[lookup], middleware=[CostBudgetMiddleware(max_spend_usd=0.00001, cost_per_million_tokens=1)])
    bind_offline(agent, runner)
    reply = await agent.arun("look up a fact")
    assert reply.metadata["stop_reason"] == "middleware_abort" and runner.calls == 1
    print("PASS: cost budget stops a running agent before its next model call")


async def run_tool_limit_flow() -> None:
    calls: list[int] = []

    @tool
    def lookup(number: int) -> str:
        """Return a local test value."""
        calls.append(number)
        return str(number)

    runner = ScriptedRunner([{"output": [
        {"type": "function_call", "name": "lookup", "arguments": '{"number":1}', "call_id": "one"},
        {"type": "function_call", "name": "lookup", "arguments": '{"number":2}', "call_id": "two"},
    ]}])
    agent = Agent(name="limited-consumer", system_prompt="Lookup twice.", provider="openai", model_name="gpt-5.4-mini", tools=[lookup], agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(max_calls_per_iteration=1)))
    bind_offline(agent, runner)
    reply = await agent.arun("try two lookups")
    assert calls == [1] and reply.metadata["tool_settings_budget"] == "max_calls_per_iteration"
    print("PASS: per-iteration tool budget blocks the second same-turn call")

    followup = ScriptedRunner([
        {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"number":3}'}]}, done("first run"),
        {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"number":4}'}]}, done("second run"),
    ])
    reused = Agent(name="reused-policy", system_prompt="Look up one number.", provider="openai", model_name="gpt-5.4-mini", tools=[lookup], agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(max_calls_per_tool={"lookup": 1})))
    bind_offline(reused, followup)
    await reused.arun("lookup 3")
    await reused.arun("lookup 4")
    assert calls == [1, 3, 4]
    print("PASS: per-tool budget resets for a reused agent on a new run")


async def run_handoff_flow() -> None:
    runner = ScriptedRunner([done(json.dumps({"sections": {
        "Objective": "Ship an SDK feature.", "Changes Made": "Added a probe.",
        "Verification Status": "Passed.", "Open Threads": "None.",
        "Risks & Gotchas": "No network.", "Next Steps": "Review.",
    }}))])
    agent = HandoffAgent(EngineeringHandoff(), provider="openai", model_name="gpt-5.4-mini")
    bind_offline(agent, runner)
    handoff = await agent.generate_handoff("A completed task needing transfer")
    assert isinstance(handoff, EngineeringHandoff)
    assert "Ship an SDK feature" in handoff.to_context_text()
    print("PASS: typed handoff generated by SDK agent")

    markdown = "## Objective\nRecover a prose handoff.\n\n## Changes Made\nNone.\n"
    retry_runner = ScriptedRunner([done(markdown) for _ in range(4)])
    fallback = HandoffAgent(EngineeringHandoff(), provider="openai", model_name="gpt-5.4-mini")
    bind_offline(fallback, retry_runner)
    recovered = await fallback.generate_handoff("An incomplete source run")
    assert recovered.sections["Objective"] == "Recover a prose handoff."
    assert retry_runner.calls == 4
    print("PASS: handoff retries invalid structured output then recovers markdown")


async def run_structured_flow() -> None:
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}
    runner = ScriptedRunner([done('{"answer":"yes"}')])
    agent = Agent(name="structured-consumer", system_prompt="Answer as JSON.", provider="openai", model_name="gpt-5.4-mini", output_schema=schema)
    bind_offline(agent, runner)
    reply = await agent.arun("is the SDK ready?")
    assert reply.metadata["structured"] == {"answer": "yes"}
    print("PASS: validated structured output through agent loop")


async def offline_decision(self: object, *, request: JevDecisionRequest, transport: object, config: object = None) -> DecisionModelResponse:
    # Replace the outbound Jev call, but leave the real decision runner's usage ledger intact.
    answers = {question.name: JevAnswer(
        question_name=question.name, question_type=JevQuestionType.NOUL,
        choice="true", probabilities={"true": 0.95, "false": 0.05}, noul=0.95,
    ) for question in request.questions}
    return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 30, "output_tokens": 2})


async def run_jev_flow() -> None:
    settings = JevAgentSettings(name="jev-consumer", system_prompt="Finish the task.", provider="openai", model_name="gpt-5.4-mini")
    runtime = JevRuntimeSettings(preflight=(JevPreflightPreset.CLARITY,), decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key="vb_live_" + "x" * 32))
    agent = JevAgent(settings, runtime)
    bind_offline(agent, ScriptedRunner([done("jev finished")]))
    with patch("vidbyte.providers.typesafe.TypeSafeProvider.run_decision", new=offline_decision):
        reply = await agent.arun("Write a concise answer.")
    assert reply.content == "jev finished"
    assert agent.response.usage.total.model_call_count == 2
    assert agent.response.usage.total.cost_complete
    print("PASS: Jev preflight + agent loop + combined priced usage")


async def main() -> None:
    await run_agent_flow()
    await run_budget_flow()
    await run_tool_limit_flow()
    await run_structured_flow()
    await run_handoff_flow()
    await run_jev_flow()


if __name__ == "__main__":
    asyncio.run(main())
