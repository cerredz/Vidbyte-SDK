"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_copy_paths.py

PURPOSE: Prove that every path that copies an agent keeps its reasoning effort and
re-checks it against the copy's model: export_state then restore (and the request the
restored agent sends, on every hop of a restored fallback chain), an old checkpoint
without the key, a stored value the table no longer allows, a plain fork, a fork to
another model (capable or not), the fork tool the model drives, and the ContinualTrace
and Handoff side agents.
ROLE IN CODEBASE: Covers spec AC-11, AC-12, EC-18, EC-19, EC-29, INV-14, FR-8, T-2,
D-6, D-16 and review R-4 for vidbyte/agents/base.py (_export_runtime_config, restore),
vidbyte/agents/fork.py, vidbyte/agents/continual_trace.py, vidbyte/agents/handoff.py
and vidbyte/tools/builtins/fork/fork.py (unchanged).
ARCHITECTURE NOTE: The copies run for real against the Wire, so a copy that keeps the
field but loses it on the way to the runner still fails. AgentForker and
BaseAgent.__init__ are never patched (tests/agent_test_support.py:24). The side
agents are built from a source that has not run, so they build their own runners
instead of reusing the source's cache.
FUNCTION INVENTORY: _without_effort returns a checkpoint with the key removed or
replaced; _fork_tool_call runs the fork tool once; the test_* functions are one
behaviour each.
COMMON MODIFICATION PATTERNS: A new copy path of the runner settings adds one test
here that builds the copy and reads its first request.
WHAT NOT TO DO IN THIS FILE: 1. Do not test that a per-hop effort survives restore;
the spec states that limitation (D-6). The one agent-wide effort does survive, and
every rebuilt hop sends it in its own form; that is tested. 2. Do not monkeypatch
AgentForker or BaseAgent.__init__. 3. Do not write a key-shaped literal.
KNOWN EDGE CASES: A fork child takes its parent's name. The fork tool catches every
exception and returns ToolResult.error with the exception's type name.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.1 INV-14, 6.2 AC-11,
AC-12, 6.3 EC-18, EC-19, EC-29, 8.1 D-6 and 9.2 "Every agent";
tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_copy_paths.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from typing import Any

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    SENT,
    Wire,
    capability_reason,
    clear_provider_environment,
    deep_merge,
    direct_agent,
    first_request,
    fragment,
    guard_text,
    provider_key,
    provider_keys,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.continual_trace import ContinualTraceAgent
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.context.handoff import MinimalHandoff
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.sessions import RunState
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.fork import ForkConversationTool
from vidbyte.tools.types import ToolCall, ToolResult

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.lib.enums import ReasoningEffort
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

TRACE_SCHEMA = {"note": "One short note."}


@pytest.fixture(autouse=True)
def wire(monkeypatch: pytest.MonkeyPatch) -> Wire:
    clear_provider_environment(monkeypatch)
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)
    return Wire(text='{"summary": "Renamed the column.", "note": "Done."}').install(
        monkeypatch
    )


def _without_effort(state: RunState, replacement: str | None = None) -> RunState:
    # A checkpoint as an older SDK wrote it (no key), or with another stored value.
    runtime_config = {
        key: value
        for key, value in state.runtime_config.items()
        if key != "reasoning_effort"
    }
    if replacement is not None:
        runtime_config["reasoning_effort"] = replacement
    return dataclasses.replace(state, runtime_config=runtime_config)


def _fork_tool_call(parent: BaseAgent, model: str) -> ToolResult:
    tool = ForkConversationTool(allowed_models=[model])
    tool.bind_agent(parent)
    return asyncio.run(
        tool.execute(
            ToolCall(
                tool_name="fork_conversation",
                arguments={"prompt": "Try another branch.", "model": model},
            )
        )
    )


def test_a_checkpoint_carries_the_effort_and_the_restored_agent_sends_it(
    wire: Wire,
) -> None:
    # AC-11, INV-14, D-13: the checkpoint stores the plain value, and
    # restore rebuilds an agent whose requests carry the same fragment.
    state = direct_agent(
        "openai", "gpt-5.5", reasoning_effort=ReasoningEffort.LOW
    ).export_state()

    assert state.runtime_config["reasoning_effort"] == "low"
    assert type(state.runtime_config["reasoning_effort"]) is str
    assert (
        json.loads(json.dumps(dict(state.runtime_config)))["reasoning_effort"] == "low"
    )
    restored = BaseAgent.restore(state, api_keys=[provider_key("openai")])
    assert restored.runner_config.reasoning_effort is ReasoningEffort.LOW
    assert (
        first_request(wire, restored)["json_body"]["reasoning"]
        == fragment("openai", "low")["reasoning"]
    )


def test_a_restored_chain_sends_the_kept_effort_in_each_hops_own_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-11, INV-14, D-6, review R-4: the checkpoint keeps the one
    # agent-wide effort and stores the hops as identity strings, so
    # restore rebuilds the chain from that effort and each hop sends it in
    # its own provider's form. The primary answers 500 so both hops send.
    keys = provider_keys("openai", "anthropic")
    chain = (("openai", "gpt-5.5"), ("anthropic", "claude-sonnet-5"))

    def restored_hops(**options: Any) -> tuple[BaseAgent, list[dict[str, Any]]]:
        state = direct_agent(
            *chain[0], keys=keys, fallback=["anthropic/claude-sonnet-5"], **options
        ).export_state()
        restored = BaseAgent.restore(state, api_keys=keys)
        wire = Wire(fail={"https://api.openai.com": 500}).install(monkeypatch)
        restored.run("Plan a zero-downtime rename of users.email.")
        return restored, wire.vendor_requests()

    _, unset = restored_hops()
    restored, effort = restored_hops(reasoning_effort=ReasoningEffort.HIGH)

    assert restored.runner_config.reasoning_effort is ReasoningEffort.HIGH
    assert [request["url"] for request in effort] == [
        request["url"] for request in unset
    ]
    assert len(effort) == len(chain)
    assert (
        effort[0]["json_body"]["reasoning"],
        effort[1]["json_body"]["output_config"],
    ) == ({"effort": "high"}, {"effort": "high"})
    for (provider, _), sent, plain in zip(chain, effort, unset, strict=True):
        assert sent["json_body"] == deep_merge(
            plain["json_body"], fragment(provider, "high")
        ), provider


def test_an_old_checkpoint_without_the_key_restores_with_no_effort(wire: Wire) -> None:
    # INV-14, D-13: restore reads the key with .get, so a checkpoint from
    # before this change restores, at the provider default.
    state = _without_effort(
        direct_agent(
            "openai", "gpt-5.5", reasoning_effort=ReasoningEffort.LOW
        ).export_state()
    )

    restored = BaseAgent.restore(state, api_keys=[provider_key("openai")])

    assert restored.runner_config.reasoning_effort is None
    assert "reasoning" not in first_request(wire, restored)["json_body"]


def test_restoring_a_value_the_table_no_longer_allows_is_refused(wire: Wire) -> None:
    # EC-18, INV-3: restore re-runs the guard, so a stale stored value is
    # refused loudly instead of being sent.
    state = _without_effort(
        direct_agent("openai", "gpt-5", reasoning_effort="high").export_state(), "xhigh"
    )

    with pytest.raises(ConfigurationError) as refused:
        BaseAgent.restore(state, api_keys=[provider_key("openai")])

    assert str(refused.value) == guard_text(
        state.agent_name,
        capability_reason("openai", "gpt-5", "xhigh", SENT["openai"]["gpt-5"]),
    )
    assert wire.requests == []


def test_a_plain_fork_carries_the_effort_onto_the_wire(wire: Wire) -> None:
    # AC-12, FR-8: AgentForker copies the effort as it copies temperature.
    child = direct_agent("openai", "gpt-5.5", reasoning_effort="none").fork()

    assert child.runner_config.reasoning_effort is ReasoningEffort.NONE
    assert first_request(wire, child)["json_body"]["reasoning"] == {"effort": "none"}


def test_a_fork_to_a_model_that_can_take_the_effort_sends_it(wire: Wire) -> None:
    # AC-12: the child keeps the parent's effort on its own model.
    child = direct_agent("openai", "gpt-5.5", reasoning_effort="none").fork(
        AgentForkSettings(model_name="gpt-5.4")
    )

    body = first_request(wire, child)["json_body"]
    assert (body["model"], body["reasoning"]) == ("gpt-5.4", {"effort": "none"})


@pytest.mark.parametrize(
    ("value", "settings", "refused"),
    [
        ("none", {"model_name": "gpt-5"}, ("openai", "gpt-5")),
        (
            "xhigh",
            {"provider": "gemini", "model_name": "gemini-3.5-flash"},
            ("gemini", "gemini-3.5-flash"),
        ),
    ],
    ids=["model_switch", "provider_and_model_switch"],
)
def test_a_fork_to_a_model_that_cannot_take_the_effort_is_refused(
    value: str, settings: dict[str, Any], refused: tuple[str, str], wire: Wire
) -> None:
    # AC-12, EC-19: the child's own construction checks the effort
    # against the child's model, before any request.
    parent = direct_agent(
        "openai",
        "gpt-5.5",
        keys=provider_keys("openai", "gemini"),
        reasoning_effort=value,
    )

    with pytest.raises(ConfigurationError) as error:
        parent.fork(AgentForkSettings(**settings))

    provider, model = refused
    assert str(error.value) == guard_text(
        parent.name, capability_reason(provider, model, value, SENT[provider][model])
    )
    assert wire.requests == []


def test_the_fork_tool_turns_the_refusal_into_an_error_result_and_offers_no_effort(
    wire: Wire,
) -> None:
    # AC-12, EC-19, T-2, D-16: a model-chosen fork to an incapable model
    # returns the reason to the model; the tool's schema cannot set one.
    parent = direct_agent("openai", "gpt-5.5", reasoning_effort="none")

    result = _fork_tool_call(parent, "gpt-5")

    assert result.status.value == "error", result.output
    assert result.output == guard_text(
        parent.name,
        capability_reason("openai", "gpt-5", "none", SENT["openai"]["gpt-5"]),
    )
    assert result.metadata["error_type"] == "ConfigurationError"
    assert wire.vendor_requests() == []
    schema = ForkConversationTool(allowed_models=["gpt-5"]).spec().input_schema
    assert "reasoning_effort" not in json.dumps(schema)


@pytest.mark.parametrize("side", ["handoff", "continual_trace"])
def test_side_agents_built_from_a_source_carry_its_effort(
    side: str, wire: Wire
) -> None:
    # FR-8, section 9.2 "Every agent": side agents route like their
    # source, so they send its effort beside any output_config they set.
    def build(**options: Any) -> BaseAgent:
        source = direct_agent("anthropic", "claude-sonnet-5", **options)
        if side == "handoff":
            return HandoffAgent.from_source_agent(source, MinimalHandoff())
        return ContinualTraceAgent.from_source_agent(source, TRACE_SCHEMA)

    unset_agent, effort_agent = build(), build(reasoning_effort="low")
    unset = first_request(wire, unset_agent, "Summarize the run.")["json_body"]
    effort = first_request(wire, effort_agent, "Summarize the run.")["json_body"]

    assert effort_agent.runner_config.reasoning_effort is ReasoningEffort.LOW
    assert effort["output_config"] == {
        **unset.get("output_config", {}),
        "effort": "low",
    }
