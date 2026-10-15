"""FILE: tests/features/agent_output_connectors/test_output_connectors_comments.py

PURPOSE: Prove the follow-ups' comment, append, and label modes on the first-batch issue and page connectors: GitHub comment_on, Linear comment_on and labels, Jira comment_on (with an ADF body and a focused-comment link) and labels, and Notion append_to; and that every forbidden or missing mode combination fails at construction naming both parameters.
ROLE IN CODEBASE: Contract tests of vidbyte/lib/outputs/github.py, linear.py, jira.py, notion.py, and gitlab.py constructors (OutputArguments.exclusive, matching, identifier, number) and their comment-mode requests, against docs/spec/output-connector-followups/spec.md §9.2 tables (a) and (b).
ARCHITECTURE NOTE: Each connector is driven directly with connector.send(reply, OutputContent(...)) over the scripted HttpTransport._send_once (fake_http); the receipt link is read the real way by OutputResponses.link.
FUNCTION INVENTORY: test_github_comment_on_* (AC-16, D-11); test_linear_comment_on_* and test_linear_comment_answered_* (AC-17, EC-23); test_linear_labels_* (AC-17, FR-22); test_jira_comment_on_* and test_jira_comment_created_* (AC-18, EC-24, D-12); test_jira_labels_* (AC-18, FR-22); test_notion_append_to_* (AC-19, D-13); test_comment_or_append_target_that_does_not_exist_* (EC-22, EC-25); test_forbidden_or_missing_mode_combinations_* (AC-20, FR-23, D-12); test_invalid_comment_targets_and_labels_* (§9.2(b), EC-41).
COMMON MODIFICATION PATTERNS: Add a combination or a bad target as one table row naming the parameters the message must contain.
WHAT NOT TO DO IN THIS FILE: 1. Do not import the constants module to build an expected wire value; the GraphQL mutation and URLs are written out. 2. Do not assert the error wording beyond the parameter names.
KNOWN EDGE CASES: A comment sends the chat text (title, blank line, body), because a comment has no title field (D-11), while a labelled issue keeps the title field. Jira's issue_type is ignored in comment mode (D-12). Linear identifiers are sent as given; Notion and Linear label UUIDs go through OutputArguments.identifier, which returns the dashed lowercase form.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/output-connector-followups/spec.md (§6.2 AC-16 to AC-20; §6.3 EC-22 to EC-25, EC-41; §8.1 D-11 to D-13; §9.2 tables (a) and (b))
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_comments.py
"""

from __future__ import annotations

import json
import re

import pytest

from tests.features.agent_output_connectors.factories import (
    GITHUB_TOKEN,
    GITLAB_KEY,
    JIRA_BASIC,
    JIRA_TOKEN,
    LINEAR_KEY,
    LINEAR_TEAM_ID,
    NOTION_KEY,
    NOTION_PARENT_PAGE_ID,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.errors import ConfigurationError

TITLE = "Checkout total ignores coupons"
BODY = "Applying SAVE10 leaves the total unchanged.\n\nSteps: add ten items, apply SAVE10."
CHAT = f"{TITLE}\n\n{BODY}"
MARKER = "\n\n[truncated]"
GITHUB_HEADERS = {"authorization": f"Bearer {GITHUB_TOKEN}", "accept": "application/vnd.github+json", "x-github-api-version": "2026-03-10"}
GITHUB_COMMENT_URL = "https://github.com/acme/shop/issues/412#issuecomment-2400000001"
LINEAR_COMMENT_MUTATION = "mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success comment { url } } }"
LINEAR_ISSUE_MUTATION = "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { url } } }"
LINEAR_COMMENT_URL = "https://linear.app/acme/issue/ENG-123/checkout#comment-5e1d9a"
LINEAR_LABEL_ID = "0b6a4f3e-2c1d-4e5f-8a9b-1c2d3e4f5a6b"
JIRA_SITE = {"site": "acme.atlassian.net", "email": "bot@acme.com", "api_token": JIRA_TOKEN}
NOTION_PAGE_ID = "6a7b8c9d-0e1f-4a2b-9c3d-4e5f6a7b8c9d"


def _names(word: str, message: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


async def _send(output_api, fake_http, connector, host: str, answer: tuple[int, str], body: str = BODY):
    # Answers the destination once, sends one reply, and returns its receipt and the one recorded request.
    fake_http.answer(host, answer)
    receipt = await connector.send(build_reply(body), output_api.OutputContent(TITLE, body))
    [send] = fake_http.sends
    return receipt, send


# --- GitHub comment_on -----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected_body"),
    [
        pytest.param(BODY, CHAT, id="chat-text"),
        pytest.param("x" * 70_000, f"{TITLE}\n\n" + "x" * (65_536 - len(MARKER) - len(TITLE) - 2) + MARKER, id="capped-at-65536"),
    ],
)
async def test_github_comment_on_posts_the_chat_text_and_links_the_comment(output_api, fake_http, body, expected_body) -> None:
    # AC-16 / FR-18 / D-11: one POST to the issue's comments; the receipt links the new comment.
    connector = output_api.GitHubIssueOutput(repo="acme/shop", comment_on=412, token=GITHUB_TOKEN)

    receipt, send = await _send(output_api, fake_http, connector, "api.github.com", (201, json.dumps({"id": 2400000001, "html_url": GITHUB_COMMENT_URL})), body)

    assert (send["method"], send["url"]) == ("POST", "https://api.github.com/repos/acme/shop/issues/412/comments")
    assert {name: send["headers"].get(name) for name in GITHUB_HEADERS} == GITHUB_HEADERS
    assert send["json_body"] == {"body": expected_body}
    assert receipt_rows([receipt]) == [("github_issue", "sent", GITHUB_COMMENT_URL, None)]


# --- Linear ----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", ["ENG-123", "eng-123", "9CFB482A-81E3-4154-B5B9-2C805E70A02D"], ids=["identifier", "lowercase-identifier", "dashed-uuid"])
async def test_linear_comment_on_uses_comment_create_and_links_the_comment(output_api, fake_http, reference) -> None:
    # AC-17 / FR-19: issueId accepts an identifier or a UUID, sent as given; the comment URL is the link.
    connector = output_api.LinearIssueOutput(comment_on=reference, api_key=LINEAR_KEY)
    answer = (200, json.dumps({"data": {"commentCreate": {"success": True, "comment": {"url": LINEAR_COMMENT_URL}}}}))

    receipt, send = await _send(output_api, fake_http, connector, "api.linear.app", answer)

    assert send["url"] == "https://api.linear.app/graphql"
    assert send["headers"]["authorization"] == LINEAR_KEY
    assert send["json_body"] == {"query": LINEAR_COMMENT_MUTATION, "variables": {"input": {"issueId": reference, "body": CHAT}}}
    assert receipt_rows([receipt]) == [("linear_issue", "sent", LINEAR_COMMENT_URL, None)]


@pytest.mark.asyncio
async def test_linear_comment_answered_with_graphql_errors_is_failed_invalid_response(output_api, fake_http) -> None:
    # EC-23: Linear answers 200 with errors[] for an unknown issue; no comment link means not SENT.
    connector = output_api.LinearIssueOutput(comment_on="ENG-999", api_key=LINEAR_KEY)
    answer = (200, json.dumps({"data": {"commentCreate": None}, "errors": [{"message": "Entity not found: Issue"}]}))

    receipt, _ = await _send(output_api, fake_http, connector, "api.linear.app", answer)

    assert receipt_rows([receipt]) == [("linear_issue", "failed", None, "invalid_response")]


@pytest.mark.asyncio
async def test_linear_labels_add_label_ids_to_the_issue_input(output_api, fake_http) -> None:
    # AC-17 / FR-22: labelIds appears only when labels are given; the rest of the input is today's.
    connector = output_api.LinearIssueOutput(team_id=LINEAR_TEAM_ID, labels=[LINEAR_LABEL_ID], api_key=LINEAR_KEY)
    answer = (200, json.dumps({"data": {"issueCreate": {"success": True, "issue": {"url": "https://linear.app/acme/issue/ENG-7/x"}}}}))

    receipt, send = await _send(output_api, fake_http, connector, "api.linear.app", answer)

    issue = {"teamId": LINEAR_TEAM_ID, "title": TITLE, "description": BODY, "labelIds": [LINEAR_LABEL_ID]}
    assert send["json_body"] == {"query": LINEAR_ISSUE_MUTATION, "variables": {"input": issue}}
    assert receipt.status.value == "sent"


# --- Jira ------------------------------------------------------------------

JIRA_COMMENT_CREATED = (201, json.dumps({"id": "10042", "self": "https://acme.atlassian.net/rest/api/3/issue/10010/comment/10042"}))


@pytest.mark.asyncio
async def test_jira_comment_on_posts_an_adf_comment_and_links_it_by_focused_comment_id(output_api, fake_http) -> None:
    # AC-18 / FR-20 / D-11 / D-12: the chat text as ADF paragraphs; issue_type is ignored in comment mode.
    connector = output_api.JiraIssueOutput(**JIRA_SITE, comment_on="PROJ-12", issue_type="Bug")

    receipt, send = await _send(output_api, fake_http, connector, "acme.atlassian.net", JIRA_COMMENT_CREATED)

    assert (send["method"], send["url"]) == ("POST", "https://acme.atlassian.net/rest/api/3/issue/PROJ-12/comment")
    assert send["headers"]["authorization"] == JIRA_BASIC
    doc = {"type": "doc", "version": 1, "content": [_paragraph(TITLE), _paragraph("Applying SAVE10 leaves the total unchanged."), _paragraph("Steps: add ten items, apply SAVE10.")]}
    assert send["json_body"] == {"body": doc}
    assert receipt_rows([receipt]) == [("jira_issue", "sent", "https://acme.atlassian.net/browse/PROJ-12?focusedCommentId=10042", None)]


@pytest.mark.asyncio
async def test_jira_comment_created_without_an_id_is_failed_invalid_response(output_api, fake_http) -> None:
    # EC-24 / INV-9: the link is built from the id, so a 201 without one cannot be reported SENT.
    connector = output_api.JiraIssueOutput(**JIRA_SITE, comment_on="PROJ-12")

    receipt, _ = await _send(output_api, fake_http, connector, "acme.atlassian.net", (201, json.dumps({"self": "https://acme.atlassian.net/rest/api/3/issue/10010/comment"})))

    assert receipt_rows([receipt]) == [("jira_issue", "failed", None, "invalid_response")]


@pytest.mark.asyncio
async def test_jira_labels_are_added_to_the_issue_fields(output_api, fake_http) -> None:
    # AC-18 / FR-22: fields.labels appears only when labels are given; the other fields are today's.
    connector = output_api.JiraIssueOutput(**JIRA_SITE, project="PROJ", labels=["ci", "nightly"])
    created = (201, json.dumps({"id": "10001", "key": "PROJ-1", "self": "https://acme.atlassian.net/rest/api/3/issue/10001"}))

    receipt, send = await _send(output_api, fake_http, connector, "acme.atlassian.net", created)

    description = {"type": "doc", "version": 1, "content": [_paragraph("Applying SAVE10 leaves the total unchanged."), _paragraph("Steps: add ten items, apply SAVE10.")]}
    fields = {"project": {"key": "PROJ"}, "issuetype": {"name": "Task"}, "summary": TITLE, "description": description, "labels": ["ci", "nightly"]}
    assert send["json_body"] == {"fields": fields}
    assert receipt_rows([receipt]) == [("jira_issue", "sent", "https://acme.atlassian.net/browse/PROJ-1", None)]


# --- Notion ----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("page_id", [NOTION_PAGE_ID, NOTION_PAGE_ID.replace("-", "")], ids=["dashed", "compact"])
async def test_notion_append_to_patches_the_page_markdown_with_mentions_neutralized(output_api, fake_http, page_id) -> None:
    # AC-19 / FR-21 / D-13: one PATCH that inserts at the end; the answer has no page link, so the receipt has none.
    connector = output_api.NotionPageOutput(append_to=page_id, api_key=NOTION_KEY)
    body = '<mention-user url="user://u"/> please look'

    receipt, send = await _send(output_api, fake_http, connector, "api.notion.com", (200, json.dumps({"object": "page_markdown"})), body)

    assert (send["method"], send["url"]) == ("PATCH", f"https://api.notion.com/v1/pages/{NOTION_PAGE_ID}/markdown")
    assert {name: send["headers"].get(name) for name in ("authorization", "notion-version")} == {"authorization": f"Bearer {NOTION_KEY}", "notion-version": "2026-03-11"}
    assert send["json_body"] == {"type": "insert_content", "insert_content": {"content": f'{TITLE}\n\n＜mention-user url="user://u"/> please look'}}
    assert receipt_rows([receipt]) == [("notion_page", "sent", None, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("class_name", "options", "host", "key"),
    [
        pytest.param("GitHubIssueOutput", {"repo": "acme/shop", "comment_on": 412, "token": GITHUB_TOKEN}, "api.github.com", "github_issue", id="EC-22-github-issue-missing"),
        pytest.param("NotionPageOutput", {"append_to": NOTION_PAGE_ID, "api_key": NOTION_KEY}, "api.notion.com", "notion_page", id="EC-25-notion-page-not-shared"),
    ],
)
async def test_comment_or_append_target_that_does_not_exist_is_failed_http_404(output_api, fake_http, class_name, options, host, key) -> None:
    # EC-22 / EC-25: a missing or unshared target is one FAILED receipt; nothing else is created instead.
    connector = getattr(output_api, class_name)(**options)

    receipt, _ = await _send(output_api, fake_http, connector, host, (404, ""))

    assert receipt_rows([receipt]) == [(key, "failed", None, "http_404")]


# --- Construction ----------------------------------------------------------

FORBIDDEN_COMBINATIONS = [
    pytest.param("GitHubIssueOutput", {"repo": "acme/shop", "labels": ["bug"], "comment_on": 412, "token": GITHUB_TOKEN}, ("labels", "comment_on"), id="github-labels-and-comment_on"),
    pytest.param("LinearIssueOutput", {"team_id": LINEAR_TEAM_ID, "comment_on": "ENG-1", "api_key": LINEAR_KEY}, ("team_id", "comment_on"), id="linear-team_id-and-comment_on"),
    pytest.param("LinearIssueOutput", {"api_key": LINEAR_KEY}, ("team_id", "comment_on"), id="linear-neither"),
    pytest.param("LinearIssueOutput", {"comment_on": "ENG-1", "labels": [LINEAR_LABEL_ID], "api_key": LINEAR_KEY}, ("labels", "comment_on"), id="linear-labels-and-comment_on"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE, "project": "PROJ", "comment_on": "PROJ-1"}, ("project", "comment_on"), id="jira-project-and-comment_on"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE}, ("project", "comment_on"), id="jira-neither"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE, "comment_on": "PROJ-1", "labels": ["ci"]}, ("labels", "comment_on"), id="jira-labels-and-comment_on"),
    pytest.param("NotionPageOutput", {"parent_page_id": NOTION_PARENT_PAGE_ID, "append_to": NOTION_PAGE_ID, "api_key": NOTION_KEY}, ("parent_page_id", "append_to"), id="notion-both"),
    pytest.param("NotionPageOutput", {"api_key": NOTION_KEY}, ("parent_page_id", "append_to"), id="notion-neither"),
    pytest.param("GitLabIssueOutput", {"project": "acme/shop", "labels": ["bug"], "merge_request": 7, "token": GITLAB_KEY}, ("labels", "merge_request"), id="gitlab-labels-and-merge_request"),
]


@pytest.mark.parametrize(("class_name", "options", "parameters"), FORBIDDEN_COMBINATIONS)
def test_forbidden_or_missing_mode_combinations_name_both_parameters(output_api, fake_http, class_name, options, parameters) -> None:
    # AC-20 / FR-23 / D-12 / INV-11: a target the vendor cannot honour fails at construction, before any request.
    with pytest.raises(ConfigurationError) as info:
        getattr(output_api, class_name)(**options)

    message = str(info.value)
    assert [parameter for parameter in parameters if not _names(parameter, message)] == [], message
    assert "S3CRET" not in message
    assert fake_http.sends == []


INVALID_TARGETS = [
    pytest.param("LinearIssueOutput", {"comment_on": "9cfb482a81e34154b5b92c805e70a02d"}, "comment_on", id="linear-compact-uuid"),
    pytest.param("LinearIssueOutput", {"comment_on": "ENG 123"}, "comment_on", id="linear-space"),
    pytest.param("LinearIssueOutput", {"comment_on": "123"}, "comment_on", id="linear-number-only"),
    pytest.param("LinearIssueOutput", {"comment_on": 123}, "comment_on", id="linear-int"),
    pytest.param("LinearIssueOutput", {"team_id": LINEAR_TEAM_ID, "labels": ["bug"]}, "labels", id="linear-label-not-a-uuid"),
    pytest.param("LinearIssueOutput", {"team_id": LINEAR_TEAM_ID, "labels": LINEAR_LABEL_ID}, "labels", id="linear-labels-as-one-string"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE, "comment_on": "proj-12"}, "comment_on", id="jira-lowercase-key"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE, "comment_on": "PROJ12"}, "comment_on", id="jira-no-dash"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE, "comment_on": "PROJ-12/../x"}, "comment_on", id="jira-path"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE, "project": "PROJ", "labels": ["needs review"]}, "labels", id="EC-41-jira-label-with-space"),
    pytest.param("JiraIssueOutput", {**JIRA_SITE, "project": "PROJ", "labels": [""]}, "labels", id="jira-blank-label"),
    pytest.param("NotionPageOutput", {"append_to": "not-a-uuid"}, "append_to", id="notion-append-to-not-a-uuid"),
]


@pytest.mark.parametrize(("class_name", "options", "parameter"), INVALID_TARGETS)
def test_invalid_comment_targets_and_labels_name_their_parameter(output_api, class_name, options, parameter) -> None:
    # §9.2(b) / EC-41 / INV-11: a malformed target or label is refused at construction.
    credential = {"LinearIssueOutput": {"api_key": LINEAR_KEY}, "JiraIssueOutput": {}, "NotionPageOutput": {"api_key": NOTION_KEY}}[class_name]

    with pytest.raises(ConfigurationError) as info:
        getattr(output_api, class_name)(**options, **credential)

    assert _names(parameter, str(info.value)), str(info.value)
