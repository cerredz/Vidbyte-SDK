"""FILE: tests/features/agent_output_connectors/test_output_connectors_acceptance.py

PURPOSE: Prove the caller-visible promise end to end: one outputs=[...] entry plus one credential delivers each finished, validated reply, a partial failure is reported without losing the reply, an invalid reply sends nothing, an agent without outputs is unchanged, and a session keeps the turn and the failure.
ROLE IN CODEBASE: Drives vidbyte.Agent / BaseAgent through the real _generate_reply path (schema check, history, Session.record_turn, failure ledger) with real Slack and GitHub connectors, an offline scripted model, and HTTP scripted at HttpTransport._send_once.
ARCHITECTURE NOTE: Only the model runner and the single HTTP send are replaced; the dispatcher, shaping, connectors, transport retry loop, Session, and store are real.
FUNCTION INVENTORY: test_spec_snippet_* runs spec §4 as written (AC-1); test_partial_failure_* (AC-5); test_reply_that_fails_its_output_schema_* (AC-4); test_agent_without_outputs_* (AC-21); test_session_* (AC-23); test_agent_bound_to_a_session_* (INV-7, D-4).
COMMON MODIFICATION PATTERNS: Script one more destination with fake_http.answer and assert on receipts, the recorded wire requests, and history; never on private dispatcher state.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock BaseAgent, OutputDispatcher, or a connector; they are the seams under test. 2. Do not use a real credential or open a socket.
KNOWN EDGE CASES: agent.run is synchronous (asyncio.run inside), so these tests are plain functions. A schema-valid reply's content is the model's JSON text. Session dedupes the agent's and its own notification of the same exception, so only a direct agent.run on a bound agent shows the agent's own notification. The runtime re-prompts the model after an invalid structured answer, so that runner repeats its answer.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§4; §6.1 INV-7; §6.2 AC-1, AC-4, AC-5, AC-21, AC-23)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_acceptance.py
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from tests.agent_test_support import bind_test_runner, build_test_agent
from tests.features.agent_output_connectors.factories import (
    GITHUB_CREATED,
    GITHUB_ISSUE_URL,
    GITHUB_TOKEN,
    SECRET_MARKER,
    SLACK_URL,
    AnswerRunner,
    receipt_rows,
)
from vidbyte.lib.errors import AgentExecutionError, OutputSchemaViolationError
from vidbyte.sessions import InMemorySessionStore, Session

BUG_TITLE = "Checkout total ignores coupons"
BUG_BODY = "Applying SAVE10 to a ten-item cart leaves the total unchanged."


class _BugReport(BaseModel):
    title: str
    body: str


def _bug_answer() -> str:
    return json.dumps({"title": BUG_TITLE, "body": BUG_BODY})


def _scout(output_api, runner, **options):
    # The §4 agent shape: a structured BugReport reply delivered to Slack and a GitHub issue.
    outputs = options.pop("outputs", None)
    if outputs is None:
        outputs = [output_api.SlackOutput(webhook_url=SLACK_URL), output_api.GitHubIssueOutput(repo="acme/shop", labels=("bug",), token=GITHUB_TOKEN)]
    return build_test_agent(name="checkout-scout", system_prompt="Find the worst bug in the checkout flow.", runner=runner, output_schema=_BugReport, outputs=outputs, **options)


def test_spec_snippet_delivers_one_validated_reply_to_slack_and_a_github_issue_and_prints_both_receipts(fake_http, monkeypatch, capsys) -> None:
    # AC-1: spec §4 run as written; credentials come from the environment, and an offline runner is bound for run().
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SLACK_URL)
    monkeypatch.setenv("GITHUB_TOKEN", GITHUB_TOKEN)
    fake_http.answer("hooks.slack.com", (200, "ok"))
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))

    from pydantic import BaseModel

    from vidbyte import Agent, GitHubIssueOutput, OutputDeliveryError, SlackOutput

    class BugReport(BaseModel):
        title: str
        body: str

    agent = Agent(
        name="checkout-scout",
        system_prompt="Find the worst bug in the checkout flow.",
        provider="openai",
        model_name="gpt-4.1",
        output_schema=BugReport,
        outputs=[
            SlackOutput(),                                         # reads SLACK_WEBHOOK_URL
            GitHubIssueOutput(repo="acme/shop", labels=("bug",)),  # reads GITHUB_TOKEN
        ],
    )
    bind_test_runner(agent, AnswerRunner(_bug_answer()))

    try:
        reply = agent.run("Scan checkout")
    except OutputDeliveryError as err:
        reply = err.reply
        for receipt in err.failed:
            print("failed:", receipt.destination.value, receipt.error_code)

    for receipt in reply.metadata["deliveries"]:
        print(receipt.destination.value, receipt.status.value, receipt.url)

    assert capsys.readouterr().out == f"slack sent None\ngithub_issue sent {GITHUB_ISSUE_URL}\n"
    [slack] = fake_http.sends_to("hooks.slack.com")
    [github] = fake_http.sends_to("api.github.com")
    assert slack["url"] == SLACK_URL
    assert slack["json_body"] == {"text": BUG_TITLE, "blocks": [{"type": "markdown", "text": f"{BUG_TITLE}\n\n{BUG_BODY}"}]}
    assert github["url"] == "https://api.github.com/repos/acme/shop/issues"
    assert github["headers"]["authorization"] == f"Bearer {GITHUB_TOKEN}"
    assert github["json_body"] == {"title": BUG_TITLE, "body": BUG_BODY, "labels": ["bug"]}


def test_partial_failure_attempts_every_output_then_raises_with_the_recorded_reply_and_one_receipt_each(output_api, fake_http) -> None:
    # AC-5 / EC-1: a revoked Slack webhook must not stop the GitHub issue, and must not fail silently.
    fake_http.answer("hooks.slack.com", (404, "no_service"))
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))
    agent = _scout(output_api, AnswerRunner(_bug_answer()))

    with pytest.raises(output_api.OutputDeliveryError) as info:
        agent.run("Scan checkout")

    err = info.value
    assert isinstance(err, AgentExecutionError)
    # Sends run concurrently, so only the set of requests is fixed, not their order.
    assert sorted(send["url"] for send in fake_http.sends) == sorted([SLACK_URL, "https://api.github.com/repos/acme/shop/issues"])
    assert err.reply is agent.last_reply
    assert agent.history[-1] is err.reply
    assert receipt_rows(err.receipts) == [("slack", "failed", None, "http_404:no_service"), ("github_issue", "sent", GITHUB_ISSUE_URL, None)]
    assert receipt_rows(err.failed) == [("slack", "failed", None, "http_404:no_service")]
    assert err.reply.metadata["deliveries"] == err.receipts
    assert str(err) == "1 of 2 outputs failed: slack (http_404:no_service)"


def test_reply_that_fails_its_output_schema_raises_and_sends_nothing(output_api, fake_http) -> None:
    # AC-4 / INV-1 / EC-8: delivery waits for schema validation, so an unvalidated post never goes out.
    # The runtime re-prompts the model to repair an invalid answer, so the model keeps giving the same one.
    agent = _scout(output_api, AnswerRunner("The checkout looks fine to me.", repeat_last=True))

    with pytest.raises(OutputSchemaViolationError):
        agent.run("Scan checkout")

    assert fake_http.sends == []
    assert "deliveries" not in agent.last_reply.metadata


def test_agent_without_outputs_runs_exactly_as_before_and_writes_no_deliveries_key(fake_http) -> None:
    # AC-21 / INV-22: the feature is invisible to every agent that does not opt in.
    agent = build_test_agent(name="plain", system_prompt="Answer briefly.", runner=AnswerRunner("All clear."))

    reply = agent.run("Is checkout healthy?")

    assert agent.outputs == ()
    assert reply.content == "All clear."
    assert "deliveries" not in reply.metadata
    assert fake_http.sends == []


def test_session_records_the_turn_and_captures_the_delivery_failure_before_it_reaches_the_caller(output_api, fake_http) -> None:
    # AC-23 / INV-7: the checkpoint keeps the reply the model produced, and the failure ledger records the delivery error once.
    fake_http.answer("hooks.slack.com", (404, "no_service"))
    store = InMemorySessionStore()
    agent = build_test_agent(name="nightly", system_prompt="Summarize the nightly scan.", runner=AnswerRunner("Nightly scan: no regressions."), outputs=[output_api.SlackOutput(webhook_url=SLACK_URL)])
    session = Session(agent, store=store)

    with pytest.raises(output_api.OutputDeliveryError):
        session.run("Run the nightly scan")

    head = store.get(session.head)
    assert head.run_state.history[-1]["content"] == "Nightly scan: no regressions."
    failures = session.failures.history()
    assert [failure.summary for failure in failures] == ["OutputDeliveryError"]
    assert SECRET_MARKER not in repr(failures)
    assert SECRET_MARKER not in repr(head)


def test_agent_bound_to_a_session_reports_its_own_delivery_failure_when_run_directly(output_api, fake_http) -> None:
    # INV-7 / D-4: the delivery block notifies the bound session itself, so a direct agent.run still reaches the failure ledger.
    fake_http.answer("hooks.slack.com", (404, "no_service"))
    store = InMemorySessionStore()
    agent = build_test_agent(name="nightly", system_prompt="Summarize the nightly scan.", runner=AnswerRunner("Nightly scan: no regressions."), outputs=[output_api.SlackOutput(webhook_url=SLACK_URL)])
    session = Session(agent, store=store)

    with pytest.raises(output_api.OutputDeliveryError):
        agent.run("Run the nightly scan")

    assert [failure.summary for failure in session.failures.history()] == ["OutputDeliveryError"]
    assert store.get(session.head).run_state.history[-1]["content"] == "Nightly scan: no regressions."
