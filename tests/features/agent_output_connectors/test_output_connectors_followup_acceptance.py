"""FILE: tests/features/agent_output_connectors/test_output_connectors_followup_acceptance.py

PURPOSE: Prove the follow-ups' caller-visible promise end to end: the spec §4 snippet, run as written, edits-or-creates one GitHub review comment, appends to the job summary, opens a Discord forum post, posts rich Markdown into a Telegram topic, signs the webhook, and prints exactly the five receipt lines; and guard that every first-batch HTTP connector built with first-batch arguments still sends the same headers and no raw-bytes body.
ROLE IN CODEBASE: Drives vidbyte.Agent through the real _generate_reply and dispatcher with the real connectors, an offline scripted model, HTTP scripted at HttpTransport._send_once, and a real job-summary file.
ARCHITECTURE NOTE: Only the model runner and the single HTTP send are replaced. Credentials come from the environment, as in the snippet; the conftest isolated_output_env fixture clears them between tests.
FUNCTION INVENTORY: test_followup_spec_snippet_* runs spec §4 (AC-1); test_first_batch_connectors_keep_their_headers_* is the INV-2 regression guard (AC-34).
COMMON MODIFICATION PATTERNS: When the §4 snippet changes, copy it here unchanged and update the printed lines from the spec, never from a run.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock BaseAgent, OutputDispatcher, or a connector. 2. Do not join the printed lines with adjacent string literals (lint S062); build them from a list.
KNOWN EDGE CASES: agent.run is synchronous (asyncio.run inside), so the snippet test is a plain function. A plain-text reply's title is its first line, and its chat text is the reply itself because the body opens with that title. The AC-34 guard is green before implementation by design: it pins behavior the follow-ups must not change.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/output-connector-followups/spec.md (§4; §6.1 INV-2, INV-8; §6.2 AC-1, AC-34)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_followup_acceptance.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from tests.agent_test_support import bind_test_runner
from tests.features.agent_output_connectors.factories import (
    CONNECTOR_CASES,
    DISCORD_URL,
    GITHUB_TOKEN,
    JIRA_BASIC,
    LINEAR_KEY,
    NOTION_KEY,
    TELEGRAM_TOKEN,
    WEBHOOK_URL,
    AnswerRunner,
    build_reply,
)

ANSWER = "Review of pull request 412\nThe coupon check was removed from checkout.py."
COMMENT_URL = "https://github.com/acme/shop/pull/412#issuecomment-2400000001"
SNIPPET_KEY = "MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"


def test_followup_spec_snippet_reaches_five_destinations_and_prints_the_documented_lines(fake_http, monkeypatch, capsys, tmp_path) -> None:
    # AC-1: spec §4 run as written; GitHub answers one empty comments page, then the new comment.
    summary = tmp_path / "step_summary"
    summary.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", GITHUB_TOKEN)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", DISCORD_URL)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TELEGRAM_TOKEN)
    monkeypatch.setenv("VIDBYTE_OUTPUT_WEBHOOK_URL", WEBHOOK_URL)
    fake_http.answer("/issues/412/comments?", (200, "[]"))
    fake_http.answer("/issues/412/comments", (201, json.dumps({"id": 2400000001, "html_url": COMMENT_URL})))
    fake_http.answer("discord.com", (204, ""))
    fake_http.answer("api.telegram.org", (200, json.dumps({"ok": True, "result": {"message_id": 7}})))
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"))

    from vidbyte import (
        Agent,
        DiscordOutput,
        GitHubIssueOutput,
        GitHubJobSummaryOutput,
        OutputDeliveryError,
        TelegramOutput,
        WebhookOutput,
    )

    agent = Agent(
        name="ci-reviewer",
        system_prompt="Review the diff and report what is wrong.",
        provider="openai",
        model_name="gpt-4.1",
        outputs=[
            GitHubIssueOutput(repo="acme/shop", comment_on=412, key="ci-review"),  # GITHUB_TOKEN; edits one comment
            GitHubJobSummaryOutput(),                                               # GITHUB_STEP_SUMMARY
            DiscordOutput(forum=True, forum_tags=["1203040506070809"]),             # DISCORD_WEBHOOK_URL
            TelegramOutput(chat_id="@acme_alerts", topic_id=7),                     # TELEGRAM_BOT_TOKEN
            WebhookOutput(headers={"Authorization": "Bearer n8n-demo-key"}, secret="whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"),
        ],
    )
    bind_test_runner(agent, AnswerRunner(ANSWER))

    try:
        reply = agent.run("Review pull request 412")
    except OutputDeliveryError as err:
        reply = err.reply

    for receipt in reply.metadata["deliveries"]:
        print(receipt.destination.value, receipt.status.value, receipt.url)

    printed = [
        f"github_issue sent {COMMENT_URL}",
        "github_job_summary sent None",
        "discord sent None",
        "telegram sent None",
        "webhook sent None",
    ]
    assert capsys.readouterr().out == "\n".join(printed) + "\n"
    # The promises behind the five lines: read then write, append, forum post, topic, signature.
    assert [(send["method"], send["url"]) for send in fake_http.sends_to("api.github.com")] == [
        ("GET", "https://api.github.com/repos/acme/shop/issues/412/comments?per_page=100&page=1"),
        ("POST", "https://api.github.com/repos/acme/shop/issues/412/comments"),
    ]
    assert fake_http.sends_to("api.github.com")[1]["json_body"] == {"body": ANSWER + "\n\n<!-- vidbyte:ci-review -->"}
    assert summary.read_text(encoding="utf-8") == ANSWER + "\n\n"
    [discord] = fake_http.sends_to("discord.com")
    assert discord["json_body"] == {"content": ANSWER, "allowed_mentions": {"parse": []}, "thread_name": "Review of pull request 412", "applied_tags": ["1203040506070809"]}
    [telegram] = fake_http.sends_to("api.telegram.org")
    assert telegram["url"] == f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendRichMessage"
    assert telegram["json_body"] == {"chat_id": "@acme_alerts", "rich_message": {"markdown": ANSWER}, "message_thread_id": 7}
    [webhook] = fake_http.sends_to("hook.eu1.make.com")
    headers, content = webhook["headers"], webhook["content"]
    assert (headers["authorization"], headers["content-type"], webhook["json_body"]) == ("Bearer n8n-demo-key", "application/json", None)
    assert json.loads(content) == {"agent": "ci-reviewer", "title": "Review of pull request 412", "body": ANSWER, "structured": None}
    signed = f"{headers['webhook-id']}.{headers['webhook-timestamp']}.".encode() + content
    digest = hmac.new(base64.b64decode(SNIPPET_KEY), signed, hashlib.sha256).digest()
    assert headers["webhook-signature"] == "v1," + base64.b64encode(digest).decode()


# The exact headers each first-batch connector sent at base 336d6c78, recorded at _send_once.
FIRST_BATCH_HEADERS = {
    "slack": {"content-type": "application/json"},
    "discord": {},
    "teams": {},
    "google_chat": {"content-type": "application/json; charset=UTF-8"},
    "telegram": {},
    "github_issue": {"authorization": f"Bearer {GITHUB_TOKEN}", "accept": "application/vnd.github+json", "x-github-api-version": "2026-03-10"},
    "linear_issue": {"authorization": LINEAR_KEY},
    "jira_issue": {"authorization": JIRA_BASIC},
    "notion_page": {"authorization": f"Bearer {NOTION_KEY}", "notion-version": "2026-03-11"},
    "webhook": {},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("key", list(FIRST_BATCH_HEADERS))
async def test_first_batch_connectors_keep_their_headers_and_send_no_raw_bytes(output_api, fake_http, key) -> None:
    # AC-34 / INV-2 / INV-14 regression guard: first-batch arguments give one JSON POST with exactly today's headers.
    case = CONNECTOR_CASES[key]
    fake_http.answer(case.host, case.success)

    await case.build(output_api).send(build_reply("Nightly scan: no regressions."), output_api.OutputContent("Nightly scan", "No regressions."))

    [send] = fake_http.sends
    assert (send["method"], send["headers"], send.get("content")) == ("POST", FIRST_BATCH_HEADERS[key], None)
