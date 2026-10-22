"""FILE: tests/features/loop_spend_cap/loop_spend_cap_fixtures.py

PURPOSE: Shared offline harness for the loop spend cap pack: scripted priced model
responses, a scripted runner, the reference cost computed from the live pricebook,
the spec's exact stop texts, and small recording tools.
ROLE IN CODEBASE: Imported by every test module in tests/features/loop_spend_cap/.
It replaces only the model wire (a fake runner bound to an agent, or a RunnerHandle
given to AgentRuntime), so UsageTracker, AgentRuntime._arun_once, and
BaseAgent.generate_reply's ledger scope and merge run for real (spec section 13).
ARCHITECTURE NOTE: Every dollar figure a test expects is computed at test time by
recording the same scripted responses into a fresh UsageTracker over the default
pricebook (reference_cost), so a pricebook rate change never turns the pack red, and
the reference sums in the same order as the agent's own ledger, so exact-boundary
tests (spend equal to the cap) compare identical floats.
FUNCTION INVENTORY: usage / text_response / call_response / done_response build
scripted model turns; reference_cost / usage_costing_at_least derive dollars from
the pricebook; blind_text builds the INV-9 unmeasured stop text; ScriptedRunner plays
responses and records each call; LookupTool, LaunchLikeTool and PricedSearchTool
record whether they executed; runtime_handle / run_runtime drive AgentRuntime
directly; capped_settings builds AgentLoopSettings with a cap; priced_agent builds a
BaseAgent on the priced model with a scripted runner bound.
COMMON MODIFICATION PATTERNS: A new scenario adds a response builder here only when
two or more test modules need it; a test that needs a different price builds its
responses with another priced model and still derives the cost with reference_cost.
WHAT NOT TO DO IN THIS FILE: 1. Do not import any name the spend cap feature adds
(AgentSpendCap, AgentStopReason.MAX_SPEND, cost_measured) at module level; each test
must fail on its own missing name, and the pack must still collect. 2. Do not
hard-code a dollar figure derived from today's rates. 3. Do not write a key-shaped
literal; build keys at runtime. 4. Do not mock UsageTracker or the runtime.
KNOWN EDGE CASES: UNPRICED_MODEL resolves to the text runner through the "gpt-"
prefix but matches no pricebook key, so construction can be tested against it; the
helpers assert both facts so a future pricebook entry fails loudly instead of
silently changing what a test proves. A response with usage=None is recorded as an
unaccounted call (UsageTracker.record_call), which is how blind-meter tests are built.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md sections 6, 8.5, 9.2 and 13;
tests/features/loop_spend_cap/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Mapping, Sequence
from typing import Any

from tests.agent_test_support import bind_test_runner
from vidbyte.agents import AgentRuntime
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.pricing import UsageTracker
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricingRegistry
from vidbyte.lib.runners import Runner, TextModelResponse
from vidbyte.tools import Tools
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec

# The priced model spec section 13 names for capped fixtures, and a text model the pricebook can never price.
PRICED_PROVIDER = ModelProvider.OPENAI
PRICED_MODEL = "gpt-5.4-mini"
UNPRICED_MODEL = "gpt-unpriced-spend-cap-probe"

# The two stop texts of spec INV-9, character for character.
REACHED_TEXT = "Agent runtime stopped after reaching max_spend_usd."
BLIND_PREFIX = "Agent runtime stopped because max_spend_usd is set and this run's spend could not be fully measured: "
MAX_SPEND = "max_spend"

_CALL_IDS = itertools.count(1)


def blind_text(*causes: str) -> str:
    """The INV-9 unmeasured stop text: the causes that hold, joined by '; ', in the spec's order."""
    return BLIND_PREFIX + "; ".join(causes) + "."


def usage(input_tokens: int, output_tokens: int = 0) -> dict[str, int]:
    """An OpenAI Responses usage payload."""
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def text_response(
    text: str,
    *,
    usage: Mapping[str, Any] | None,
    provider: ModelProvider = PRICED_PROVIDER,
    model: str = PRICED_MODEL,
) -> TextModelResponse:
    """A plain-text model turn (no tool call) that reports the given usage."""
    return TextModelResponse(
        provider=provider,
        model=model,
        text=text,
        raw={},
        usage=dict(usage) if usage is not None else None,
    )


def call_response(
    *calls: tuple[str, Mapping[str, Any]],
    usage: Mapping[str, Any] | None,
    provider: ModelProvider = PRICED_PROVIDER,
    model: str = PRICED_MODEL,
    text: str = "",
) -> TextModelResponse:
    """A model turn that asks for the given tool calls, in order, in OpenAI Responses shape."""
    output = [
        {
            "type": "function_call",
            "name": name,
            "arguments": json.dumps(dict(arguments)),
            "call_id": f"call-{next(_CALL_IDS)}",
        }
        for name, arguments in calls
    ]
    return TextModelResponse(
        provider=provider,
        model=model,
        text=text,
        raw={"output": output},
        usage=dict(usage) if usage is not None else None,
    )


def done_response(
    answer: str, *, usage: Mapping[str, Any] | None, model: str = PRICED_MODEL
) -> TextModelResponse:
    """A model turn that calls isDone with the given final answer."""
    return call_response(("isDone", {"final_answer": answer}), usage=usage, model=model)


def reference_cost(*responses: object, operations: Sequence[float] = ()) -> float:
    """The measured spend the agent's own ledger reaches after recording these responses, then these reported operation costs, in order."""
    tracker = UsageTracker()
    for response in responses:
        tracker.record_call(response)
    for cost in operations:
        tracker.record_operation("search", "brave", reported_cost_usd=cost)
    rollup = tracker.rollup()
    assert rollup.cost_usd is not None and rollup.unaccounted_call_count == 0, (
        "reference responses must all be priced"
    )
    return rollup.cost_usd


def usage_costing_at_least(target: float, *, output_tokens: int = 0) -> dict[str, int]:
    """A usage payload whose one priced call costs at least `target` dollars at today's pricebook rates."""
    input_tokens = 1_000
    while (
        reference_cost(text_response("", usage=usage(input_tokens, output_tokens)))
        < target
    ):
        input_tokens *= 2
    return usage(input_tokens, output_tokens)


def assert_price_preconditions() -> None:
    """Fails loudly if the pricebook ever stops pricing PRICED_MODEL or starts pricing UNPRICED_MODEL."""
    registry = ModelPricingRegistry.default()
    assert registry.resolve(PRICED_PROVIDER, PRICED_MODEL) is not None, (
        f"{PRICED_MODEL} must stay priced for these fixtures"
    )
    assert registry.resolve(PRICED_PROVIDER, UNPRICED_MODEL) is None, (
        f"{UNPRICED_MODEL} must stay unpriced for these fixtures"
    )
    assert (
        Runner.from_model(
            provider=PRICED_PROVIDER.value, model_name=UNPRICED_MODEL
        ).resolve_runner_type()
        == "text"
    )


class ScriptedRunner:
    """Plays one scripted response per model call and records what each call was sent."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.options: list[dict[str, Any]] = []

    @property
    def calls(self) -> int:
        return len(self.prompts)

    async def arun(self, prompt: str, **options: Any) -> object:
        self.prompts.append(prompt)
        self.options.append(dict(options))
        if not self.responses:
            raise AssertionError(f"unscripted model call #{len(self.prompts)}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class LookupTool(BaseTool):
    """A free developer tool that records every execution."""

    def __init__(self, name: str = "lookup") -> None:
        self._name = name
        self.executed: list[dict[str, Any]] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self._name, description="Looks a fact up.")

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed.append(dict(call.arguments))
        return ToolResult.success(call.tool_name, "found")


class LaunchLikeTool(LookupTool):
    """An internal tool, as the runtime classifies launch_subagent or launch_swarm (spec metadata internal=True)."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description="Launches helper agents.",
            metadata={"internal": True},
        )


class PricedSearchTool(PricedOperationTool):
    """A priced search operation whose provider reports its own cost, so the operation spends exactly `cost` dollars."""

    operation = "search"
    provider = "brave"

    def __init__(self, cost: float) -> None:
        super().__init__(client=None)
        self.cost = cost
        self.executed: list[dict[str, Any]] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(name="priced_search", description="Runs a paid web search.")

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed.append(dict(call.arguments))
        return self._contract_result("searched", reported_cost_usd=self.cost)


async def _invoke(runner: ScriptedRunner, prompt: str, **options: Any) -> object:
    return await runner.arun(prompt, **options)


def _text_of(response: object) -> str:
    return str(getattr(response, "text", response))


def _metadata_of(response: object) -> dict[str, Any]:
    return dict(getattr(response, "metadata", {}) or {})


def runtime_handle(runner: ScriptedRunner) -> RunnerHandle:
    """A RunnerHandle over a scripted runner, labelled openai so tool calls parse in Responses shape."""
    return RunnerHandle(
        runner=runner,
        provider=PRICED_PROVIDER.value,
        invoke=_invoke,
        extract_text=_text_of,
        extract_metadata=_metadata_of,
    )


def build_runtime(
    config: object,
    *,
    tools: Sequence[BaseTool] = (),
    middleware: Sequence[object] = (),
    algorithm: object = None,
    runtime_class: type[AgentRuntime] = AgentRuntime,
) -> AgentRuntime:
    """An AgentRuntime with its own fresh UsageTracker, as BaseAgent builds one."""
    return runtime_class(
        agent_name="worker",
        system_prompt="Work.",
        tools=Tools(list(tools)),
        permission_policy=PermissionPolicy(),
        config=config,
        middleware=tuple(middleware),
        algorithm=algorithm,
    )


async def run_runtime(
    runtime: AgentRuntime, runner: ScriptedRunner, message: str = "Look up Paris."
) -> Any:
    """One AgentRuntime.arun over the scripted runner."""
    context = runtime.build_context(
        message,
        base_context=None,
        history=(),
        agent_history=(),
        agent_metadata={},
        existing_tool_calls=(),
    )
    return await runtime.arun(message, handle=runtime_handle(runner), context=context)


def capped_settings(cap: float, **fields: Any) -> AgentLoopSettings:
    """AgentLoopSettings with the spend cap set (raises TypeError until the field exists)."""
    return AgentLoopSettings(max_spend_usd=cap, **fields)


def priced_agent(
    runner: object,
    *,
    name: str = "researcher",
    loop: AgentLoopSettings | None = None,
    agent_type: type[BaseAgent] = BaseAgent,
    **options: Any,
) -> BaseAgent:
    """A BaseAgent on the priced model with the scripted runner bound as its text runner."""
    options.setdefault("provider", PRICED_PROVIDER.value)
    options.setdefault("model_name", PRICED_MODEL)
    agent = agent_type(
        name=name, system_prompt="Answer directly.", agent_loop_settings=loop, **options
    )
    return bind_test_runner(agent, runner)
