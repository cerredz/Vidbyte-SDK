"""FILE: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py

PURPOSE: Prove each HTTP connector sends exactly the request its vendor documents (method, URL, auth form, version header, body keys, transport limits) and reads the created object's link the documented way; and that delivered text is safe and sized: mass mentions neutralized, bodies capped with the marker, titles kept to one 250-character line, webhook structured payloads JSON-safe.
ROLE IN CODEBASE: Contract tests of the eleven connectors in vidbyte/lib/outputs/ (through vidbyte.agents.output), OutputText (through the connectors), and OutputHttp's link check (D-21), against spec §9.2 table (a).
ARCHITECTURE NOTE: Each connector is driven directly with connector.send(reply, OutputContent(...)) for exact wire checks, or through OutputDispatcher.deliver when the shaping rule is part of the promise; the only fake is the single HTTP send (and the SMTP classes for the email subject).
FUNCTION INVENTORY: test_each_http_connector_sends_its_documented_request (AC-17, FR-15); test_created_object_link_* (D-21, EC-22); test_channel_wide_mentions_* and test_notion_mention_tags_* (AC-9, INV-12, EC-6); test_body_at_its_cap_* / test_body_over_its_cap_* / test_jira_description_* / test_destinations_without_a_documented_cap_* (INV-14); test_slack_escapes_after_truncation_* (§9.2 helpers); test_long_reply_* (AC-10, EC-7); test_title_newlines_* (EC-18); test_long_first_line_becomes_*_at_every_titled_destination and test_title_whitespace_runs_* (INV-15 for GitHub, Linear, Jira, Notion, and email; S4 R-14); test_webhook_structured_* (§9.2 webhook row, EC-40).
COMMON MODIFICATION PATTERNS: When a vendor contract changes, update its row in WIRE_ROWS from the vendor reference page and the spec together; never loosen a row to match code. A new destination with a title gets a HTTP_TITLE_OF entry, so the one-line title rule covers it.
WHAT NOT TO DO IN THIS FILE: 1. Do not import the constants module to build an expected wire value; wire literals are written out so a wrong constant is caught. 2. Do not compare header names case-insensitively; HttpTransport adds its own lowercase content-type default.
KNOWN EDGE CASES: chat_text drops the title when the body's first line already is the title. Slack escapes after truncation, so a capped body has no escapable characters here. Jira's ADF paragraphs come from the truncated body, so the marker becomes its own paragraph. Notion and Linear identifiers are lowercase dashed UUIDs, so normalization cannot change them.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§9.2 wire contract table, D-21; §6.1 INV-12, INV-14, INV-15)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import ANY

import pytest
from pydantic import BaseModel

from tests.features.agent_output_connectors.factories import (
    CONFLUENCE_BASIC,
    CONFLUENCE_PAGE_URL,
    CONNECTOR_CASES,
    DISCORD_URL,
    GITHUB_CREATED,
    GITHUB_TOKEN,
    GITLAB_ISSUE_URL,
    GITLAB_KEY,
    GOOGLE_CHAT_URL,
    HTTP_DESTINATION_KEYS,
    HUBSPOT_KEY,
    JIRA_BASIC,
    LINEAR_ISSUE_URL,
    LINEAR_KEY,
    LINEAR_TEAM_ID,
    NOTION_KEY,
    NOTION_PAGE_URL,
    NOTION_PARENT_PAGE_ID,
    SLACK_URL,
    SMTP_PASSWORD,
    TEAMS_URL,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
    TYPEFULLY_DRAFT_URL,
    TYPEFULLY_KEY,
    WEBHOOK_URL,
    build_reply,
    receipt_rows,
)

TITLE = "Checkout total ignores coupons"
BODY = "Applying SAVE10 leaves the total unchanged.\n\nSteps: add ten items, apply SAVE10."
CHAT = f"{TITLE}\n\n{BODY}"
MARKER = "\n\n[truncated]"
LINEAR_MUTATION = "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { url } } }"

# One row per HTTP destination, written from spec §9.2 table (a): URL, required headers, exact JSON body, receipt URL.
WIRE_ROWS = {
    "slack": (SLACK_URL, {"content-type": "application/json"}, {"text": TITLE, "blocks": [{"type": "markdown", "text": CHAT}]}, None),
    "discord": (DISCORD_URL, {}, {"content": CHAT, "allowed_mentions": {"parse": []}}, None),
    "teams": (TEAMS_URL, {}, {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": {"type": "AdaptiveCard", "version": "1.2", "body": [{"type": "TextBlock", "text": TITLE, "weight": "Bolder", "size": "Medium", "wrap": True}, {"type": "TextBlock", "text": BODY, "wrap": True}], "msteams": {"width": "Full"}}}]}, None),
    "google_chat": (GOOGLE_CHAT_URL, {"content-type": "application/json; charset=UTF-8"}, {"text": CHAT}, None),
    "telegram": (f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendRichMessage", {}, {"chat_id": TELEGRAM_CHAT_ID, "rich_message": {"markdown": CHAT}}, None),
    "github_issue": ("https://api.github.com/repos/acme/shop/issues", {"authorization": f"Bearer {GITHUB_TOKEN}", "accept": "application/vnd.github+json", "x-github-api-version": "2026-03-10"}, {"title": TITLE, "body": BODY, "labels": ["bug"]}, "https://github.com/acme/shop/issues/412"),
    "linear_issue": ("https://api.linear.app/graphql", {"authorization": LINEAR_KEY}, {"query": LINEAR_MUTATION, "variables": {"input": {"teamId": LINEAR_TEAM_ID, "title": TITLE, "description": BODY}}}, LINEAR_ISSUE_URL),
    "jira_issue": ("https://acme.atlassian.net/rest/api/3/issue", {"authorization": JIRA_BASIC}, {"fields": {"project": {"key": "PROJ"}, "issuetype": {"name": "Task"}, "summary": TITLE, "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Applying SAVE10 leaves the total unchanged."}]}, {"type": "paragraph", "content": [{"type": "text", "text": "Steps: add ten items, apply SAVE10."}]}]}}}, "https://acme.atlassian.net/browse/PROJ-1"),
    "notion_page": ("https://api.notion.com/v1/pages", {"authorization": f"Bearer {NOTION_KEY}", "notion-version": "2026-03-11"}, {"parent": {"type": "page_id", "page_id": NOTION_PARENT_PAGE_ID}, "properties": {"title": {"title": [{"text": {"content": TITLE}}]}}, "markdown": BODY}, NOTION_PAGE_URL),
    "webhook": (WEBHOOK_URL, {}, {"agent": "checkout-scout", "title": TITLE, "body": BODY, "structured": None}, None),
    "gitlab_issue": ("https://gitlab.com/api/v4/projects/acme%2Fshop/issues", {"private-token": GITLAB_KEY}, {"title": TITLE, "description": BODY, "labels": "bug"}, GITLAB_ISSUE_URL),
    "confluence_page": ("https://acme-wiki.atlassian.net/wiki/api/v2/pages", {"authorization": CONFLUENCE_BASIC}, {"spaceId": "98304", "status": "current", "title": TITLE, "parentId": "12345", "body": {"representation": "atlas_doc_format", "value": ANY}}, CONFLUENCE_PAGE_URL),
    "typefully_draft": ("https://api.typefully.com/v2/social-sets/123/drafts", {"authorization": f"Bearer {TYPEFULLY_KEY}"}, {"draft_title": TITLE, "platforms": {"x": {"enabled": True, "posts": [{"text": BODY}]}, "linkedin": {"enabled": True, "posts": [{"text": BODY}]}}}, TYPEFULLY_DRAFT_URL),
    "hubspot_task": ("https://api.hubapi.com/crm/v3/objects/tasks", {"authorization": f"Bearer {HUBSPOT_KEY}"}, {"properties": {"hs_task_subject": TITLE, "hs_task_body": BODY, "hs_timestamp": ANY}}, None),
}

# Where each capped destination puts its text, and that text's cap (spec §9.2 table (a), "Body cap").
CAPPED = {
    "slack": (40_000, lambda body: body["text"], True),
    "discord": (2_000, lambda body: body["content"], True),
    "teams": (7_000, lambda body: body["attachments"][0]["content"]["body"][1]["text"], False),
    "google_chat": (8_000, lambda body: body["text"], True),
    "telegram": (32_768, lambda body: body["rich_message"]["markdown"], True),
    "github_issue": (65_536, lambda body: body["body"], False),
}
UNCAPPED = {
    "linear_issue": lambda body: body["variables"]["input"]["description"],
    "notion_page": lambda body: body["markdown"],
    "webhook": lambda body: body["body"],
}


async def _send_one(output_api, fake_http, key: str, title: str, body: str, **overrides):
    # Builds the destination with its placeholder credential, answers with its documented success, and sends once.
    case = CONNECTOR_CASES[key]
    fake_http.answer(case.host, case.success)
    connector = case.build(output_api, **overrides)
    receipt = await connector.send(build_reply(body, sender="checkout-scout"), output_api.OutputContent(title, body))
    [send] = fake_http.sends
    return receipt, send


@pytest.mark.asyncio
@pytest.mark.parametrize("key", HTTP_DESTINATION_KEYS)
async def test_each_http_connector_sends_its_documented_request(output_api, fake_http, key) -> None:
    # AC-17 / FR-15 / §9.2: one POST per send, the vendor's exact URL, auth form, version header, and body, with the transport limits.
    url, required_headers, json_body, receipt_url = WIRE_ROWS[key]

    receipt, send = await _send_one(output_api, fake_http, key, TITLE, BODY)

    assert send["method"] == "POST"
    assert send["url"] == url
    assert all(name == name.lower() for name in send["headers"]), "header names must be lowercase (spec §12.4)"
    assert {name: send["headers"].get(name) for name in required_headers} == required_headers
    assert send["json_body"] == json_body
    assert send["timeout_seconds"] == 10.0
    assert send["max_response_bytes"] == 1_000_000
    assert receipt_rows([receipt]) == [(key, "sent", receipt_url, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "status", "body"),
    [
        pytest.param("linear_issue", 200, json.dumps({"data": None, "errors": [{"message": "Argument Validation Error", "extensions": {"code": "INVALID_INPUT"}}]}), id="linear-graphql-errors"),
        pytest.param("linear_issue", 200, json.dumps({"data": {"issueCreate": {"success": True, "issue": {}}}}), id="linear-missing-url"),
        pytest.param("linear_issue", 200, json.dumps({"data": {"issueCreate": {"success": True, "issue": {"url": 7}}}}), id="linear-non-text-url"),
        pytest.param("github_issue", 201, json.dumps({"number": 412, "html_url": "http://github.com/acme/shop/issues/412"}), id="github-plain-http-link"),
        pytest.param("github_issue", 201, json.dumps({"number": 412, "html_url": "   "}), id="github-blank-link"),
        pytest.param("github_issue", 201, "created", id="github-not-json"),
        pytest.param("github_issue", 201, json.dumps([{"html_url": "https://github.com/acme/shop/issues/412"}]), id="github-json-list"),
        pytest.param("jira_issue", 201, json.dumps({"id": "10001", "key": "", "self": "https://acme.atlassian.net/rest/api/3/issue/10001"}), id="jira-blank-key"),
        pytest.param("notion_page", 200, json.dumps({"object": "page", "id": NOTION_PARENT_PAGE_ID}), id="notion-missing-url"),
    ],
)
async def test_created_object_link_that_is_missing_or_unsafe_makes_a_2xx_response_failed_invalid_response(output_api, fake_http, key, status, body) -> None:
    # D-21 / EC-22 / AC-17: a 2xx without a usable https link is not a created object, so it must not be reported SENT.
    case = CONNECTOR_CASES[key]
    fake_http.answer(case.host, (status, body))
    connector = case.build(output_api)

    receipt = await connector.send(build_reply(BODY), output_api.OutputContent(TITLE, BODY))

    assert receipt_rows([receipt]) == [(key, "failed", None, "invalid_response")]
    assert len(fake_http.sends) == 1


@pytest.mark.asyncio
async def test_channel_wide_mentions_are_neutralized_for_each_chat_destination(output_api, fake_http) -> None:
    # AC-9 (a) / INV-12 / EC-6: a prompt-injected reply must not ping a whole channel, server, or space.
    text = "<!channel> & @everyone <users/all>"
    for key in ("slack", "discord", "google_chat", "telegram"):
        fake_http.answer(CONNECTOR_CASES[key].host, CONNECTOR_CASES[key].success)
    outputs = tuple(CONNECTOR_CASES[key].build(output_api) for key in ("slack", "discord", "google_chat", "telegram"))
    reply = build_reply(text)

    await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    [slack] = fake_http.sends_to("hooks.slack.com")
    [discord] = fake_http.sends_to("discord.com")
    [google_chat] = fake_http.sends_to("chat.googleapis.com")
    [telegram] = fake_http.sends_to("api.telegram.org")
    assert slack["json_body"] == {"text": "&lt;!channel&gt; &amp; @everyone &lt;users/all&gt;", "blocks": [{"type": "markdown", "text": "＜!channel> & @everyone <users/all>"}]}
    assert discord["json_body"]["allowed_mentions"] == {"parse": []}
    assert "＜users/all>" in google_chat["json_body"]["text"]
    assert "<users/" not in google_chat["json_body"]["text"]
    assert "parse_mode" not in telegram["json_body"]
    assert set(telegram["json_body"]) == {"chat_id", "rich_message"}


@pytest.mark.asyncio
async def test_notion_mention_tags_in_the_markdown_body_are_neutralized(output_api, fake_http) -> None:
    # AC-9 (b) / INV-12: Notion's enhanced markdown turns <mention-…/> into a notification.
    body = '<mention-user url="user://u"/> done'
    fake_http.answer("api.notion.com", CONNECTOR_CASES["notion_page"].success)
    reply = build_reply(body)

    await output_api.OutputDispatcher.deliver((CONNECTOR_CASES["notion_page"].build(output_api),), reply, reply.metadata)

    [notion] = fake_http.sends
    assert "＜mention-user" in notion["json_body"]["markdown"]
    assert "<mention-" not in notion["json_body"]["markdown"]


def _chat_body_for(key: str, length: int) -> str:
    # Chat destinations cap the title-plus-body text; issue bodies cap the body alone.
    cap_includes_title = CAPPED[key][2]
    return "x" * (length - len("Load test") - 2 if cap_includes_title else length)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", list(CAPPED))
async def test_body_at_its_cap_is_sent_whole(output_api, fake_http, key) -> None:
    # INV-14: the cap is inclusive, so a text of exactly the cap is not marked as truncated.
    cap, text_of, _ = CAPPED[key]
    body = _chat_body_for(key, cap)

    _, send = await _send_one(output_api, fake_http, key, "Load test", body)

    text = text_of(send["json_body"])
    assert len(text) == cap
    assert not text.endswith(MARKER)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", list(CAPPED))
@pytest.mark.parametrize("excess", [1, 3_000], ids=["one-over", "far-over"])
async def test_body_over_its_cap_is_cut_to_exactly_the_cap_with_the_marker_in_one_request(output_api, fake_http, key, excess) -> None:
    # INV-14 / D-14: one reply is one request; the destination never rejects it for length.
    cap, text_of, _ = CAPPED[key]
    body = _chat_body_for(key, cap + excess)

    _, send = await _send_one(output_api, fake_http, key, "Load test", body)

    text = text_of(send["json_body"])
    assert len(text) == cap
    assert text.endswith(MARKER)
    assert len(fake_http.sends) == 1


@pytest.mark.asyncio
async def test_slack_escapes_after_truncation_so_no_entity_is_cut_in_half(output_api, fake_http) -> None:
    # §9.2 helpers: escape runs on the truncated text, so every "&" survives as a whole "&amp;".
    body = "&" * (40_001 - len("Load test\n\n"))

    _, send = await _send_one(output_api, fake_http, "slack", "Load test", body)

    assert send["json_body"]["text"] == "Load test\n\n" + "&amp;" * (40_000 - len(MARKER) - len("Load test\n\n")) + MARKER


@pytest.mark.asyncio
@pytest.mark.parametrize("excess", [0, 1], ids=["at-cap", "one-over"])
async def test_jira_description_paragraphs_come_from_the_body_capped_at_32767_characters(output_api, fake_http, excess) -> None:
    # INV-14 / §9.2 Jira row: ADF paragraphs are built from the truncated body, so the marker becomes its own paragraph.
    body = "x" * (32_767 + excess)

    _, send = await _send_one(output_api, fake_http, "jira_issue", "Load test", body)

    paragraphs = [paragraph["content"][0]["text"] for paragraph in send["json_body"]["fields"]["description"]["content"]]
    assert paragraphs == ([body] if excess == 0 else ["x" * (32_767 - len(MARKER)), "[truncated]"])


@pytest.mark.asyncio
@pytest.mark.parametrize("key", list(UNCAPPED))
async def test_destinations_without_a_documented_cap_get_the_full_body(output_api, fake_http, key) -> None:
    # INV-14 / A-6 / A-8: no cap is invented where the vendor documents none.
    body = "y" * 100_000

    _, send = await _send_one(output_api, fake_http, key, "Load test", body)

    assert UNCAPPED[key](send["json_body"]) == body


@pytest.mark.asyncio
async def test_long_reply_is_capped_for_discord_and_its_long_first_line_becomes_a_250_character_one_line_title(output_api, fake_http, fake_smtp) -> None:
    # AC-10 / EC-7 / EC-18 / INV-15: Discord gets 2,000 characters; the GitHub title and the email Subject are one line of 250 with no marker.
    paragraph = " ".join(f"word{index:04d}" for index in range(60))[:400]
    assert len(paragraph) == 400 and not paragraph.endswith(" ")
    fake_http.answer("discord.com", CONNECTOR_CASES["discord"].success)
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))
    long_reply = build_reply("z" * 5_000)
    titled_reply = build_reply(f"{paragraph}\nSecond line of the report.")
    email = CONNECTOR_CASES["email"].build(output_api)

    await output_api.OutputDispatcher.deliver((CONNECTOR_CASES["discord"].build(output_api),), long_reply, long_reply.metadata)
    await output_api.OutputDispatcher.deliver((output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN), email), titled_reply, titled_reply.metadata)

    [discord] = fake_http.sends_to("discord.com")
    assert len(discord["json_body"]["content"]) == 2_000
    assert discord["json_body"]["content"].endswith(MARKER)
    [github] = fake_http.sends_to("api.github.com")
    [session] = fake_smtp.sessions
    for title in (github["json_body"]["title"], str(session.message["Subject"])):
        assert title == paragraph[:250]
        assert len(title) == 250
        assert "\r" not in title and "\n" not in title
        assert "[truncated]" not in title


@pytest.mark.asyncio
async def test_title_newlines_collapse_to_one_line_so_they_cannot_inject_an_email_header(output_api, fake_http, fake_smtp) -> None:
    # EC-18 / INV-15 / T-2: a model-written "\nBcc:" stays inside the Subject and the issue title.
    fake_http.answer("api.github.com", (201, GITHUB_CREATED))
    reply = build_reply('{"title": "x", "body": "y"}', structured={"title": "Weekly report\r\nBcc: x@evil.com", "body": "All checks passed."})
    outputs = (output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN), CONNECTOR_CASES["email"].build(output_api))

    receipts = await output_api.OutputDispatcher.deliver(outputs, reply, reply.metadata)

    assert [row[1] for row in receipt_rows(receipts)] == ["sent", "sent"]
    [github] = fake_http.sends
    [session] = fake_smtp.sessions
    assert github["json_body"]["title"] == "Weekly report Bcc: x@evil.com"
    assert str(session.message["Subject"]) == "Weekly report Bcc: x@evil.com"
    assert session.message["Bcc"] is None
    assert session.login == ("bot@acme.com", SMTP_PASSWORD)


# Where each titled HTTP destination puts its title (spec §9.2 table (a)); email's title is the Subject header.
HTTP_TITLE_OF = {
    "github_issue": lambda body: body["title"],
    "linear_issue": lambda body: body["variables"]["input"]["title"],
    "jira_issue": lambda body: body["fields"]["summary"],
    "notion_page": lambda body: body["properties"]["title"]["title"][0]["text"]["content"],
}
TITLED_KEYS = (*HTTP_TITLE_OF, "email")


async def _delivered_title(output_api, fake_http, fake_smtp, key: str, reply) -> str:
    # Delivers one reply through the shaping rule to one titled destination and returns the title it sent.
    case = CONNECTOR_CASES[key]
    if key != "email":
        fake_http.answer(case.host, case.success)

    receipts = await output_api.OutputDispatcher.deliver((case.build(output_api),), reply, reply.metadata)

    assert [row[1] for row in receipt_rows(receipts)] == ["sent"]
    if key == "email":
        [session] = fake_smtp.sessions
        return str(session.message["Subject"])
    [send] = fake_http.sends
    return HTTP_TITLE_OF[key](send["json_body"])


@pytest.mark.asyncio
@pytest.mark.parametrize("key", TITLED_KEYS)
async def test_long_first_line_becomes_a_250_character_one_line_title_at_every_titled_destination(output_api, fake_http, fake_smtp, key) -> None:
    # AC-10 / EC-7 / INV-15 / S4 R-14: Jira, Linear, and Notion sending the raw 400-character title passed the GitHub-and-email-only test.
    paragraph = " ".join(f"word{index:04d}" for index in range(60))[:400]
    reply = build_reply(f"{paragraph}\nSecond line of the report.")

    title = await _delivered_title(output_api, fake_http, fake_smtp, key, reply)

    assert title == paragraph[:250]
    assert "[truncated]" not in title


@pytest.mark.asyncio
@pytest.mark.parametrize("key", TITLED_KEYS)
async def test_title_whitespace_runs_and_newlines_collapse_to_one_space_at_every_titled_destination(output_api, fake_http, fake_smtp, key) -> None:
    # EC-18 / INV-15 / T-2 / S4 R-14: every run of whitespace, CR and LF included, becomes one space before the title is sent.
    reply = build_reply('{"title": "x", "body": "y"}', structured={"title": "Weekly report\r\n\r\nBcc:\tx@evil.com", "body": "All checks passed."})

    title = await _delivered_title(output_api, fake_http, fake_smtp, key, reply)

    assert title == "Weekly report Bcc: x@evil.com"


class _TimedReport(BaseModel):
    title: str
    found_at: datetime


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("structured", "expected"),
    [
        pytest.param(_TimedReport(title="T", found_at=datetime(2026, 10, 11, 9, 30, tzinfo=timezone.utc)), {"title": "T", "found_at": "2026-10-11T09:30:00Z"}, id="pydantic-model-json-mode"),
        pytest.param({"severity": "high", "items": [1, 2]}, {"severity": "high", "items": [1, 2]}, id="mapping-as-is"),
        pytest.param(["a", "b"], ["a", "b"], id="list-as-is"),
        pytest.param(None, None, id="none"),
        pytest.param(object(), None, id="other-object-dropped"),
    ],
)
async def test_webhook_structured_field_is_a_json_value_or_none(output_api, fake_http, structured, expected) -> None:
    # §9.2 webhook row / §12.3 row 18: the receiver gets the agent's validated structure in JSON form.
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"))
    reply = build_reply("Checkout total ignores coupons.", sender="checkout-scout", structured=structured)

    await output_api.OutputDispatcher.deliver((output_api.WebhookOutput(url=WEBHOOK_URL),), reply, reply.metadata)

    [send] = fake_http.sends
    assert send["json_body"]["agent"] == "checkout-scout"
    assert send["json_body"]["structured"] == expected


@pytest.mark.asyncio
async def test_webhook_structured_mapping_with_a_non_json_value_is_failed_unexpected_type_error(output_api, fake_http) -> None:
    # EC-40: a mapping passes through as-is, so a value JSON cannot encode fails that send instead of crashing the delivery.
    reply = build_reply("Checkout total ignores coupons.", structured={"found_at": datetime(2026, 10, 11, tzinfo=timezone.utc)})

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver((output_api.WebhookOutput(url=WEBHOOK_URL),), reply, reply.metadata)

    assert receipt_rows(info.value.receipts) == [("webhook", "failed", None, "unexpected:TypeError")]
