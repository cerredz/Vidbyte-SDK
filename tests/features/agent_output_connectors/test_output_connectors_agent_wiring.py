"""FILE: tests/features/agent_output_connectors/test_output_connectors_agent_wiring.py

PURPOSE: Prove outputs= is wired into every agent the user named and kept out of every agent the SDK builds: forks and AgentTool children never deliver, restore re-attaches only what the caller passes, JevAgentSettings and CodingAgent carry outputs, cancellation propagates, drained follow-ups deliver on their own pass, capped runs are skipped, and a caller-written connector works.
ROLE IN CODEBASE: Integration tests across vidbyte.agents.base (outputs keyword, _generate_reply delivery block, restore), vidbyte.agents.fork, vidbyte.tools.agent_tool, vidbyte.agents.jev (settings and agent), and vidbyte.agents.coding.
ARCHITECTURE NOTE: Agents run with offline scripted runners (tests/agent_test_support.py) and HTTP scripted at HttpTransport._send_once; nothing below the runner or above the send is replaced.
FUNCTION INVENTORY: test_fork_and_agent_tool_* (AC-12); test_export_and_restore_* (AC-13); test_jev_agent_* (AC-14); test_coding_agent_* (AC-15); test_cancellation_* (AC-18); test_delivery_failure_drops_* (INV-7); test_each_drained_follow_up_* (INV-2); test_drained_follow_up_delivery_failure_* (EC-20); test_run_stopped_by_max_iterations_* (EC-43); test_caller_written_connector_* (FR-5).
COMMON MODIFICATION PATTERNS: Add a case when another agent type gains outputs (or must not); assert delivery through the recorded wire requests, never through private dispatcher state.
WHAT NOT TO DO IN THIS FILE: 1. Do not monkeypatch BaseAgent.__init__ or AgentForker; they are under test. 2. Do not edit tests/test_jev_agent.py or the coding-agent contract test; they pin the signatures this file re-checks.
KNOWN EDGE CASES: Outside a run, agent._queued_prompts is the pending list the next run claims as its own queue, so AC-18 holds a reference to that list object and checks it was emptied. JevAgent needs priced usage on every model turn (AnswerRunner supplies it). OfflineTestAgent forks carry the runner, so an AgentTool child really runs.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§6.1 INV-2, INV-16, INV-17, INV-20; §6.2 AC-12 to AC-15, AC-18)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_agent_wiring.py
"""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import fields

import pytest

from tests.agent_test_support import bind_test_runner, build_test_agent
from tests.features.agent_output_connectors.factories import (
    SECRET_MARKER,
    SLACK_URL,
    AnswerRunner,
    ScriptedConnector,
    ScriptedResponse,
    receipt_rows,
)
from vidbyte import tool
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev import JevAgent, JevAgentSettings
from vidbyte.lib.dataclasses import ToolCall
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.dataclasses.sessions import RunState
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.agent_tool import AgentTool

OTHER_SLACK_URL = "https://hooks.slack.com/services/T000/B111/S3CRETrestored"


class _ToolLoopRunner:
    """A model that never finishes: every turn asks for the lookup tool again."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, prompt: str, **kwargs: object) -> ScriptedResponse:
        self.calls += 1
        return ScriptedResponse({"output": [{"type": "function_call", "name": "lookup", "arguments": json.dumps({"topic": "checkout"}), "call_id": f"lookup_{self.calls}"}]})


@tool
def lookup(topic: str) -> str:
    """Look up one topic."""
    return f"notes about {topic}"


def _slack_texts(fake_http) -> list[str]:
    return [send["json_body"]["text"] for send in fake_http.sends_to("hooks.slack.com")]


@pytest.mark.asyncio
async def test_fork_and_agent_tool_children_never_deliver_the_parents_outputs(output_api, fake_http) -> None:
    # AC-12 / INV-16 / D-7: one user run through as_tool() must not fan out into posts from sub-agents the caller never configured.
    metadata = AgentMetadata(name="scout", description="Investigates one question.", use_cases="Delegated investigation.")
    parent = build_test_agent(name="scout", system_prompt="Investigate.", runner=AnswerRunner("child finding"), agent_metadata=metadata, outputs=[output_api.SlackOutput(webhook_url=SLACK_URL)])

    assert parent.fork().outputs == ()
    tool_ = AgentTool(parent)
    result = await tool_.execute(ToolCall(tool_.spec().name, {}))

    # The child really ran (so a delivery would have happened if it carried outputs).
    assert (result.status.value, result.output) == ("success", "child finding")
    assert fake_http.sends == []


def test_export_and_restore_never_serialize_outputs_and_reattach_only_what_the_caller_passes(output_api, fake_http) -> None:
    # AC-13 / INV-17: outputs hold live credentials, so RunState keeps its field set and restore() starts with none.
    fake_http.answer("hooks.slack.com", (200, "ok"))
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=AnswerRunner("unused"), outputs=[output_api.SlackOutput(webhook_url=SLACK_URL)])

    state = agent.export_state()

    assert "outputs" not in {item.name for item in fields(RunState)}
    assert "SlackOutput" not in repr(state)
    assert BaseAgent.restore(state).outputs == ()
    connector = output_api.SlackOutput(webhook_url=OTHER_SLACK_URL)
    restored = BaseAgent.restore(state, outputs=[connector])
    assert restored.outputs == (connector,)
    bind_test_runner(restored, AnswerRunner("restored finding"))
    restored.run("Investigate again")
    assert [send["url"] for send in fake_http.sends] == [OTHER_SLACK_URL]
    assert _slack_texts(fake_http) == ["restored finding"]


def test_jev_agent_takes_outputs_from_its_settings_and_delivers_the_finished_reply(output_api, fake_http) -> None:
    # AC-14 / FR-2 / D-8: the capability is a validated JevAgentSettings field; JevAgent's constructor stays (settings, runtime_settings).
    fake_http.answer("hooks.slack.com", (200, "ok"))
    connector = output_api.SlackOutput(webhook_url=SLACK_URL)
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini", outputs=[connector])

    agent = bind_test_runner(JevAgent(settings), AnswerRunner("jev answer"))
    reply = agent.run("Summarize the incident")

    assert settings.outputs == (connector,)
    assert agent.outputs == settings.outputs
    assert _slack_texts(fake_http) == ["jev answer"]
    assert receipt_rows(reply.metadata["deliveries"]) == [("slack", "sent", None, None)]
    assert tuple(inspect.signature(JevAgent.__init__).parameters) == ("self", "settings", "runtime_settings")


def test_jev_agent_settings_reject_a_bare_string_outputs_value() -> None:
    # AC-14 / INV-21: a string would otherwise be iterated character by character.
    with pytest.raises(ConfigurationError, match="outputs"):
        JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini", outputs="slack")


def test_coding_agent_accepts_outputs_through_its_base_options_and_delivers(output_api, fake_http, tmp_path) -> None:
    # AC-15 / D-9: CodingAgent forwards outputs= to BaseAgent with no constructor change of its own.
    from vidbyte import CodingAgent

    fake_http.answer("hooks.slack.com", (200, "ok"))
    connector = output_api.SlackOutput(webhook_url=SLACK_URL)
    agent = CodingAgent(name="coder", system_prompt="Fix the failing test.", root_dir=tmp_path, provider="openai", model_name="gpt-4.1", outputs=[connector])

    assert agent.outputs == (connector,)
    bind_test_runner(agent, AnswerRunner("Fixed the coupon rounding test."))
    agent.run("Fix the first failure")
    assert _slack_texts(fake_http) == ["Fixed the coupon rounding test."]


@pytest.mark.asyncio
async def test_cancellation_during_delivery_propagates_unwrapped_and_clears_the_runs_queued_prompts(output_api) -> None:
    # AC-18 / INV-20: cancellation is never turned into a receipt or an OutputDeliveryError, and the follow-up never runs.
    cancelling = ScriptedConnector(output_api.OutputDestination.WEBHOOK, error=asyncio.CancelledError())
    runner = AnswerRunner("first answer", "follow-up answer")
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=runner, outputs=[cancelling])
    agent.enqueue_prompts(["follow-up"])
    # Outside a run this is the pending list that the next run claims as its own queue.
    run_queue = agent._queued_prompts

    with pytest.raises(asyncio.CancelledError):
        await agent.arun("first")

    assert run_queue == []
    assert runner.calls == 1
    assert len(cancelling.contents) == 1


def test_delivery_failure_drops_the_runs_queued_follow_ups_instead_of_running_them_later(output_api, fake_http) -> None:
    # INV-7 / D-4: like a schema failure, a failed delivery raises before the drain and leaves no follow-up waiting.
    fake_http.answer("hooks.slack.com", (404, "no_service"))
    runner = AnswerRunner("first answer", "follow-up answer")
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=runner, outputs=[output_api.SlackOutput(webhook_url=SLACK_URL)])
    agent.enqueue_prompts(["follow-up"])
    # Outside a run this is the pending list that the next run claims as its own queue.
    run_queue = agent._queued_prompts

    with pytest.raises(output_api.OutputDeliveryError):
        agent.run("first")

    assert run_queue == []
    assert runner.calls == 1
    assert len(fake_http.sends) == 1


def test_each_drained_follow_up_reply_is_delivered_once_on_its_own_pass_after_the_reply_that_queued_it(output_api, fake_http) -> None:
    # INV-2 / INV-26: delivery sits before the drain, so the first reply posts first and each reply posts exactly once.
    fake_http.answer("hooks.slack.com", (200, "ok"), (200, "ok"))
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=AnswerRunner("first answer", "second answer"), outputs=[output_api.SlackOutput(webhook_url=SLACK_URL)])
    agent.enqueue_prompts(["follow-up"])

    reply = agent.run("first")

    assert _slack_texts(fake_http) == ["first answer", "second answer"]
    assert receipt_rows(reply.metadata["deliveries"]) == [("slack", "sent", None, None)]
    [follow_up] = agent.last_queued_replies
    assert receipt_rows(follow_up.metadata["deliveries"]) == [("slack", "sent", None, None)]


def test_drained_follow_up_delivery_failure_is_recorded_on_the_first_reply_without_failing_it(output_api, fake_http) -> None:
    # EC-20: the drain's existing contract stores repr(exc); the repr must name the failure and carry no secret.
    fake_http.answer("hooks.slack.com", (200, "ok"), (404, "no_service"))
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=AnswerRunner("first answer", "second answer"), outputs=[output_api.SlackOutput(webhook_url=SLACK_URL)])
    agent.enqueue_prompts(["follow-up"])

    reply = agent.run("first")

    assert receipt_rows(reply.metadata["deliveries"]) == [("slack", "sent", None, None)]
    error = reply.metadata["queued_prompt_error"]
    assert "OutputDeliveryError" in error
    assert "slack (http_404:no_service)" in error
    assert SECRET_MARKER not in error


def test_run_stopped_by_max_iterations_is_skipped_for_every_output_and_returns_normally(output_api, fake_http) -> None:
    # EC-43 / INV-9 (b): the runtime's own stop notice must never become a Slack post or a GitHub issue.
    outputs = [output_api.SlackOutput(webhook_url=SLACK_URL), output_api.WebhookOutput(url="https://hook.eu1.make.com/S3CRETcapped")]
    agent = build_test_agent(name="capped", system_prompt="Investigate.", runner=_ToolLoopRunner(), tools=(lookup,), max_iterations=1, outputs=outputs)

    reply = agent.run("Scan checkout")

    assert reply.metadata["stop_reason"] == "max_iterations"
    assert receipt_rows(reply.metadata["deliveries"]) == [("slack", "skipped", None, None), ("webhook", "skipped", None, None)]
    assert fake_http.sends == []


def test_caller_written_connector_that_only_satisfies_the_protocol_is_accepted_and_delivered(output_api) -> None:
    # FR-5: OutputConnector is a structural Protocol, so a caller's own class needs no BaseOutput subclass.
    custom = ScriptedConnector(output_api.OutputDestination.WEBHOOK)
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=AnswerRunner("# Coupon bug\nSAVE10 is ignored."), outputs=[custom])

    reply = agent.run("Scan checkout")

    assert agent.outputs == (custom,)
    [content] = custom.contents
    assert (content.title, content.body) == ("Coupon bug", "# Coupon bug\nSAVE10 is ignored.")
    assert receipt_rows(reply.metadata["deliveries"]) == [("webhook", "sent", None, None)]
