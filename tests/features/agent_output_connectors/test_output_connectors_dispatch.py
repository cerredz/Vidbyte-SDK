"""FILE: tests/features/agent_output_connectors/test_output_connectors_dispatch.py

PURPOSE: Prove the agent-side linking rules: which replies are skipped, how a reply becomes a title and a body, how render replaces that rule, that every connector is attempted concurrently with receipts in configured order, that a stalled destination is cut off by the deadline, and that the error carries its diagnostic packet and cause.
ROLE IN CODEBASE: Integration tests of vidbyte.agents.output.dispatcher.OutputDispatcher.deliver and OutputShaping (through deliver), with real Slack, GitHub, and webhook connectors over the scripted HTTP seam.
ARCHITECTURE NOTE: OutputDispatcher and OutputShaping are the logic under test and are never replaced; ScriptedConnector stands in only where a test needs a caller-written connector that waits, signals, or raises.
FUNCTION INVENTORY: test_stopped_or_blank_reply_* and test_finished_reply_* (AC-8, INV-9); test_default_shaping_* (AC-11 a-c, INV-13, EC-17); test_render_* (AC-11 d-e, EC-16); test_send_that_returns_anything_but_a_delivery_receipt_* (AC-11 f, EC-16, S4 R-2); test_connector_bug_* (EC-36); test_sends_run_concurrently_* (AC-19, INV-6); test_destination_that_never_answers_* (AC-6 e, EC-47); test_delivery_error_carries_* (D-20, A003); test_resending_only_the_failed_* (AC-24); test_two_replies_delivered_at_once_* (EC-27).
COMMON MODIFICATION PATTERNS: Add a shaping case as one row of SHAPING_CASES; add a skip case as one stop reason; assert on recorded wire requests and receipts.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock OutputShaping, OutputText, or OutputDispatcher. 2. Do not sleep to prove concurrency; gate with asyncio.Event. 3. Do not rely on the 35 s production deadline; patch the dispatcher module's constant.
KNOWN EDGE CASES: The concurrency test would deadlock if sends ran one after another, so it shortens the deadline as a backstop and wraps the call in a safety timeout. A blank reply and a stopped run both skip every connector with no request, and nothing is raised.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§6.1 INV-6, INV-9, INV-13; §6.2 AC-6, AC-8, AC-11, AC-19, AC-24; §8.5 OutputDispatcher)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_dispatch.py
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from tests.agent_test_support import build_test_agent
from tests.features.agent_output_connectors.factories import (
    GITHUB_CREATED,
    GITHUB_ISSUE_URL,
    GITHUB_TOKEN,
    SECRET_MARKER,
    SLACK_URL,
    AnswerRunner,
    HttpScript,
    ScriptedConnector,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.dataclasses.agents import AgentStopReason
from vidbyte.lib.errors import ConfigurationError

GITHUB_ISSUES_URL = "https://api.github.com/repos/acme/shop/issues"
STOP_NOTICE = "Agent runtime stopped after reaching max_iterations."
# Every runtime stop reason except the two that mean the model finished with an accepted answer.
UNFINISHED_STOP_REASONS = tuple(reason.value for reason in AgentStopReason if reason.value not in ("final_response", "is_done"))


class _BugReport(BaseModel):
    title: str
    body: str


class _Finding(BaseModel):
    summary: str
    severity: str


def _github_and_slack(output_api):
    return (output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN), output_api.SlackOutput(webhook_url=SLACK_URL))


def _answer_github_and_slack(fake_http: HttpScript) -> None:
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))
    fake_http.answer("hooks.slack.com", (200, "ok"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "stop_reason"),
    [
        pytest.param("   \n\t", "final_response", id="whitespace-content"),
        pytest.param("", "is_done", id="empty-content"),
        pytest.param("Agent runtime stopped by middleware: budget guard.", "middleware_abort", id="middleware-abort"),
        pytest.param(STOP_NOTICE, "max_iterations", id="max-iterations-notice"),
        *[pytest.param("A finished-looking answer about checkout.", reason, id=f"stop-{reason}") for reason in UNFINISHED_STOP_REASONS],
    ],
)
async def test_stopped_or_blank_reply_is_skipped_for_every_output_with_no_request_and_no_error(output_api, fake_http, content, stop_reason) -> None:
    # AC-8 / INV-9 / D-22: no destination is scripted, so any request would fail the test as an unscripted send.
    reply = build_reply(content, stop_reason=stop_reason)

    receipts = await output_api.OutputDispatcher.deliver(_github_and_slack(output_api), reply, reply.metadata)

    assert isinstance(receipts, tuple)
    assert receipt_rows(receipts) == [("github_issue", "skipped", None, None), ("slack", "skipped", None, None)]
    assert reply.metadata["deliveries"] == receipts
    assert fake_http.sends == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", [None, "final_response", "is_done"], ids=["no-stop-reason", "final-response", "is-done"])
async def test_finished_reply_is_delivered_whether_its_stop_reason_is_absent_or_a_normal_finish(output_api, fake_http, stop_reason) -> None:
    # INV-9 / EC-38: only the two normal stops, or no stop reason at all (Jev's clarification stop), are delivered.
    fake_http.answer("hooks.slack.com", (200, "ok"))
    reply = build_reply("Checkout total ignores coupons.", stop_reason=stop_reason)

    receipts = await output_api.OutputDispatcher.deliver((output_api.SlackOutput(webhook_url=SLACK_URL),), reply, reply.metadata)

    assert receipt_rows(receipts) == [("slack", "sent", None, None)]
    assert len(fake_http.sends) == 1


SHAPING_CASES = [
    # (id, reply content, structured value, GitHub title, GitHub body, Slack text)
    ("structured-model", json.dumps({"title": "T", "body": "B"}), _BugReport(title="T", body="B"), "T", "B", "T\n\nB"),
    ("structured-mapping", json.dumps({"title": "T", "body": "B"}), {"title": "T", "body": "B"}, "T", "B", "T\n\nB"),
    ("plain-heading", "# Heading\nrest", None, "Heading", "# Heading\nrest", "# Heading\nrest"),
    ("plain-first-line", "Checkout total ignores coupons.\nSAVE10 is ignored.", None, "Checkout total ignores coupons.", "Checkout total ignores coupons.\nSAVE10 is ignored.", "Checkout total ignores coupons.\nSAVE10 is ignored."),
    ("structured-without-title", '{"summary": "coupon ignored", "severity": "high"}', _Finding(summary="coupon ignored", severity="high"), "checkout-scout", '{"summary": "coupon ignored", "severity": "high"}', 'checkout-scout\n\n{"summary": "coupon ignored", "severity": "high"}'),
    ("structured-blank-title", '{"title": "  ", "body": "B"}', {"title": "  ", "body": "B"}, "checkout-scout", "B", "checkout-scout\n\nB"),
    ("structured-non-text-title", '{"title": 7, "body": "B"}', {"title": 7, "body": "B"}, "checkout-scout", "B", "checkout-scout\n\nB"),
    ("structured-blank-body", '{"title": "T", "body": " "}', {"title": "T", "body": " "}, "T", '{"title": "T", "body": " "}', 'T\n\n{"title": "T", "body": " "}'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("content", "structured", "title", "body", "slack_text"), [pytest.param(*case[1:], id=case[0]) for case in SHAPING_CASES])
async def test_default_shaping_turns_each_reply_into_one_title_and_one_body(output_api, fake_http, content, structured, title, body, slack_text) -> None:
    # AC-11 (a)-(c) / INV-13 / EC-17: structured fields first, then the first line of plain content, else the agent's name.
    _answer_github_and_slack(fake_http)
    reply = build_reply(content, sender="checkout-scout", structured=structured)

    receipts = await output_api.OutputDispatcher.deliver(_github_and_slack(output_api), reply, reply.metadata)

    assert receipt_rows(receipts) == [("github_issue", "sent", GITHUB_ISSUE_URL, None), ("slack", "sent", None, None)]
    [github] = fake_http.sends_to("api.github.com")
    [slack] = fake_http.sends_to("hooks.slack.com")
    assert github["json_body"] == {"title": title, "body": body, "labels": []}
    assert slack["json_body"] == {"text": title, "blocks": [{"type": "markdown", "text": slack_text}]}


@pytest.mark.asyncio
async def test_render_replaces_the_shaping_rule_for_its_own_connector_only(output_api, fake_http) -> None:
    # AC-11 (d) / FR-8: render receives the reply itself; the other connector keeps the default rule.
    _answer_github_and_slack(fake_http)
    seen = []

    def render(reply):
        seen.append(reply)
        return output_api.OutputContent("X", "Y")

    reply = build_reply("# Heading\nrest")
    outputs = (output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN, render=render), output_api.SlackOutput(webhook_url=SLACK_URL))

    await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    assert seen == [reply]
    assert seen[0] is reply
    [github] = fake_http.sends_to("api.github.com")
    [slack] = fake_http.sends_to("hooks.slack.com")
    assert github["json_body"] == {"title": "X", "body": "Y", "labels": []}
    assert slack["json_body"] == {"text": "Heading", "blocks": [{"type": "markdown", "text": "# Heading\nrest"}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("returned", ["X\n\nY", None, {"title": "X", "body": "Y"}], ids=["str", "none", "mapping"])
async def test_render_that_returns_anything_but_output_content_fails_only_its_connector(output_api, fake_http, returned) -> None:
    # AC-11 (e) / Q-5 default: the bad connector sends nothing and is FAILED; the others are still attempted.
    fake_http.answer("hooks.slack.com", (200, "ok"))
    reply = build_reply("Checkout total ignores coupons.")
    outputs = (output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN, render=lambda _reply: returned), output_api.SlackOutput(webhook_url=SLACK_URL))

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    assert receipt_rows(info.value.receipts) == [("github_issue", "failed", None, "unexpected:ConfigurationError"), ("slack", "sent", None, None)]
    assert fake_http.sends_to("api.github.com") == []
    assert isinstance(info.value.__cause__, ConfigurationError)


@pytest.mark.asyncio
async def test_render_that_raises_fails_its_connector_and_chains_the_delivery_error_from_that_exception(output_api, fake_http) -> None:
    # EC-16: a caller's render bug is reported with its type and kept as the error's cause.
    fake_http.answer("hooks.slack.com", (200, "ok"))
    failure = KeyError("summary")

    def render(_reply):
        raise failure

    reply = build_reply("Checkout total ignores coupons.")
    outputs = (output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN, render=render), output_api.SlackOutput(webhook_url=SLACK_URL))

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    assert receipt_rows(info.value.receipts) == [("github_issue", "failed", None, "unexpected:KeyError"), ("slack", "sent", None, None)]
    assert info.value.__cause__ is failure


@pytest.mark.asyncio
@pytest.mark.parametrize("returned", [None, "sent"], ids=["none", "str"])
async def test_send_that_returns_anything_but_a_delivery_receipt_fails_only_its_connector(output_api, fake_http, returned) -> None:
    # AC-11 (f) / EC-16 / INV-11 / S4 R-2: checked like render's value, so the code is never unexpected:NoneType and the error has a cause.
    fake_http.answer("hooks.slack.com", (200, "ok"))
    careless = ScriptedConnector(output_api.OutputDestination.WEBHOOK, result=returned)
    reply = build_reply("Checkout total ignores coupons.")

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver((careless, output_api.SlackOutput(webhook_url=SLACK_URL)), reply, reply.metadata)

    assert receipt_rows(info.value.receipts) == [("webhook", "failed", None, "unexpected:ConfigurationError"), ("slack", "sent", None, None)]
    assert isinstance(info.value.__cause__, ConfigurationError)
    assert reply.metadata["deliveries"] == info.value.receipts
    assert len(careless.contents) == 1


@pytest.mark.asyncio
async def test_connector_bug_inside_send_becomes_an_unexpected_receipt_and_the_others_still_send(output_api, fake_http) -> None:
    # EC-36 / INV-6: an ordinary exception from send is a receipt, not a crash of the whole delivery.
    fake_http.answer("hooks.slack.com", (200, "ok"))
    failure = TypeError("payload is not a mapping")
    broken = ScriptedConnector(output_api.OutputDestination.WEBHOOK, error=failure)
    reply = build_reply("Checkout total ignores coupons.")

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver((broken, output_api.SlackOutput(webhook_url=SLACK_URL)), reply, reply.metadata)

    assert receipt_rows(info.value.receipts) == [("webhook", "failed", None, "unexpected:TypeError"), ("slack", "sent", None, None)]
    assert info.value.__cause__ is failure
    assert str(info.value) == "1 of 2 outputs failed: webhook (unexpected:TypeError)"


@pytest.mark.asyncio
async def test_sends_run_concurrently_and_receipts_keep_configured_order_not_finish_order(output_api, dispatcher_module, monkeypatch) -> None:
    # AC-19 / INV-6 / D-6: the first connector cannot finish until the second has run, which only concurrent sends allow.
    # A sequential dispatcher would leave the first send waiting until the shortened deadline marked it FAILED.
    monkeypatch.setattr(dispatcher_module, "OUTPUT_DELIVERY_DEADLINE_SECONDS", 2.0)
    second_ran = asyncio.Event()
    finished: list[str] = []
    first = ScriptedConnector(output_api.OutputDestination.WEBHOOK, wait_for=second_ran, finished=finished)
    second = ScriptedConnector(output_api.OutputDestination.SLACK, signal=second_ran, finished=finished)
    reply = build_reply("Checkout total ignores coupons.")

    receipts = await asyncio.wait_for(output_api.OutputDispatcher.deliver((first, second), reply, reply.metadata), 10.0)

    assert finished == ["slack", "webhook"]
    assert receipt_rows(receipts) == [("webhook", "sent", None, None), ("slack", "sent", None, None)]


@pytest.mark.asyncio
async def test_destination_that_never_answers_is_failed_network_at_the_deadline_without_holding_back_the_others(output_api, fake_http, dispatcher_module, monkeypatch) -> None:
    # AC-6 (e) / EC-47 / NFR-2: the dispatcher imports the deadline by name, at its documented value, and enforces it per connector.
    assert dispatcher_module.OUTPUT_DELIVERY_DEADLINE_SECONDS == 35.0
    monkeypatch.setattr(dispatcher_module, "OUTPUT_DELIVERY_DEADLINE_SECONDS", 0.05)
    fake_http.answer("hooks.slack.com", HttpScript.HANG)
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))
    reply = build_reply("Checkout total ignores coupons.")
    outputs = (output_api.SlackOutput(webhook_url=SLACK_URL), output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN))

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await asyncio.wait_for(output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata), 10.0)

    assert receipt_rows(info.value.receipts) == [("slack", "failed", None, "network"), ("github_issue", "sent", GITHUB_ISSUE_URL, None)]
    assert str(info.value) == "1 of 2 outputs failed: slack (network)"


@pytest.mark.asyncio
async def test_delivery_error_carries_the_full_diagnostic_packet_with_no_secret(output_api, fake_http) -> None:
    # D-20 / A003 / §12.3 row 25: the packet names each failed destination and code, and is mirrored into details.
    fake_http.answer("hooks.slack.com", (404, "no_service"))
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))
    reply = build_reply("Checkout total ignores coupons.")
    outputs = (output_api.SlackOutput(webhook_url=SLACK_URL), output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN))

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    err = info.value
    fields = ("error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests")
    assert tuple(type(err).DIAGNOSTIC_FIELDS) == fields
    assert err.error_kind == "output_delivery_failed"
    assert err.expected == "every configured output delivered or skipped"
    assert err.actual == str(err) == "1 of 2 outputs failed: slack (http_404:no_service)"
    assert err.safe_runtime_details == {"failed": [["slack", "http_404:no_service"]], "receipt_count": 2}
    assert tuple(err.related_docs) == ("vidbyte/lib/outputs/README.md", "vidbyte/agents/output/README.md")
    assert tuple(err.relevant_tests) == ("python scripts/run_ci.py",)
    assert err.likely_causes and err.repair_approaches
    assert {name: err.details[name] for name in fields} == {name: getattr(err, name) for name in fields}
    assert err.reply is reply
    assert err.__cause__ is None
    assert SECRET_MARKER not in repr(err.details)


@pytest.mark.asyncio
@pytest.mark.parametrize(("retry_answer", "expected_status"), [((200, "ok"), "sent"), ((404, "no_service"), "failed")], ids=["resend-succeeds", "resend-fails-again"])
async def test_resending_only_the_failed_connectors_makes_one_new_request_to_that_destination(output_api, fake_http, retry_answer, expected_status) -> None:
    # AC-24 / EC-42: the documented recovery recipe avoids a duplicate GitHub issue.
    fake_http.answer("hooks.slack.com", (404, "no_service"), retry_answer)
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))
    outputs = [output_api.SlackOutput(webhook_url=SLACK_URL), output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN)]
    agent = build_test_agent(name="checkout-scout", system_prompt="Find the worst bug.", runner=AnswerRunner("Checkout total ignores coupons."), outputs=outputs)
    with pytest.raises(output_api.OutputDeliveryError) as info:
        await agent.arun("Scan checkout")
    err = info.value
    sends_before = len(fake_http.sends)

    failed = tuple(connector for connector, receipt in zip(agent.outputs, err.receipts, strict=True) if receipt.status is output_api.DeliveryStatus.FAILED)
    if expected_status == "sent":
        receipts = await output_api.OutputDispatcher.deliver(failed, err.reply, {})
    else:
        with pytest.raises(output_api.OutputDeliveryError) as again:
            await output_api.OutputDispatcher.deliver(failed, err.reply, {})
        receipts = again.value.receipts

    assert failed == (outputs[0],)
    assert [send["url"] for send in fake_http.sends[sends_before:]] == [SLACK_URL]
    assert [row[:2] for row in receipt_rows(receipts)] == [("slack", expected_status)]


@pytest.mark.asyncio
async def test_two_replies_delivered_at_once_through_the_same_connector_each_post_their_own_text(output_api, fake_http) -> None:
    # EC-27 / T-4: connectors and the dispatcher hold no per-send state, so concurrent deliveries do not mix replies.
    fake_http.answer("hooks.slack.com", (200, "ok"), repeat=True)
    connector = output_api.SlackOutput(webhook_url=SLACK_URL)
    first, second = build_reply("First finding."), build_reply("Second finding.")

    await asyncio.gather(output_api.OutputDispatcher.deliver((connector,), first, first.metadata), output_api.OutputDispatcher.deliver((connector,), second, second.metadata))

    assert sorted(send["json_body"]["text"] for send in fake_http.sends) == ["First finding.", "Second finding."]
    assert receipt_rows(first.metadata["deliveries"]) == receipt_rows(second.metadata["deliveries"]) == [("slack", "sent", None, None)]
