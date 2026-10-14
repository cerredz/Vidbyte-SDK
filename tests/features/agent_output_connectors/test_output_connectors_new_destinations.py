"""FILE: tests/features/agent_output_connectors/test_output_connectors_new_destinations.py

PURPOSE: Prove the five follow-up destinations end to end at their real seams: GitLab issues and merge-request notes, the GitHub Actions job summary file, Confluence pages, Typefully drafts, and HubSpot tasks, including their caps, title shaping, receipt links, construction checks, and the job summary's off-loop, one-at-a-time appends.
ROLE IN CODEBASE: Contract tests of vidbyte/lib/outputs/gitlab.py, github_job_summary.py, confluence.py, typefully.py, and hubspot.py, plus the file_error caution in OutputDeliveryError, against docs/spec/output-connector-followups/spec.md §9.2 tables (a) and (b).
ARCHITECTURE NOTE: HTTP connectors are driven over the scripted HttpTransport._send_once (fake_http). The job summary writes a real file under tmp_path through the real LocalFileSystemBackend; which thread opened the file is observed with a Python audit hook on the "open" event, so nothing in the write path is replaced.
FUNCTION INVENTORY: test_gitlab_* (AC-21, EC-26, EC-27, D-21); test_job_summary_* (AC-22, EC-28, EC-30, EC-31, INV-12, D-18); test_delivery_error_lists_file_error_* (AC-36, FR-35); test_confluence_* (AC-23, D-10); test_typefully_* (AC-24, INV-7, D-19); test_hubspot_* (AC-25, D-20); test_new_connector_titles_* (INV-13); _watch_opens and _record_open (audit-hook helpers).
COMMON MODIFICATION PATTERNS: Add a bad argument as one row of the matching INVALID_* table; add a destination's title location to TITLE_FIELDS.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock LocalFileSystemBackend or the summary executor; the file and the worker thread are real (spec §13). 2. Do not compare wall-clock times beyond the bracket around one send. 3. Do not build an expected body from the constants module; the values are written out from §9.2.
KNOWN EDGE CASES: The audit hook cannot be removed once added, so it is added once per process and records only files registered by _watch_opens, matched by a unique file name. The job summary appends with newline=None, so on Windows each "\n" is written as CRLF; read_text turns it back, so the tests compare text, not bytes. A wrong implementation that writes on the event loop is caught by the recorded thread id; one that uses two worker threads is caught when the two sends overlap, which large bodies make the usual case.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/output-connector-followups/spec.md (§6.2 AC-21 to AC-25, AC-36; §6.3 EC-26 to EC-31; §8.1 D-18 to D-21; §9.2 tables (a) and (b); §13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_new_destinations.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.features.agent_output_connectors.factories import (
    CONFLUENCE_BASIC,
    CONFLUENCE_KEY,
    CONNECTOR_CASES,
    GITLAB_ISSUE_URL,
    GITLAB_KEY,
    HUBSPOT_KEY,
    TYPEFULLY_DRAFT_URL,
    TYPEFULLY_KEY,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.errors import ConfigurationError

TITLE = "Checkout total ignores coupons"
BODY = "Applying SAVE10 leaves the total unchanged.\n\nSteps: add ten items, apply SAVE10."
CHAT = f"{TITLE}\n\n{BODY}"
MARKER = "\n\n[truncated]"
SEPARATOR = "\n\n"
CONFLUENCE_SITE = {"site": "acme.atlassian.net", "email": "bot@acme.com", "api_token": CONFLUENCE_KEY}
CONFLUENCE_CREATED = (200, json.dumps({"id": "557060", "_links": {"webui": "/spaces/ENG/pages/557060/Checkout"}}))
TYPEFULLY_CREATED = (201, json.dumps({"id": 9001, "private_url": TYPEFULLY_DRAFT_URL}))
HUBSPOT_CREATED = (201, json.dumps({"id": "512", "properties": {}}))
HS_TIMESTAMP_PATTERN = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z"

# File names whose opens the audit hook records, mapped to the opening thread ids.
_OPENED: dict[str, list[int]] = {}
_HOOK_ADDED: list[bool] = []


def _record_open(event: str, args: tuple) -> None:
    # Audit hooks run in the thread that opens the file, so the id shows where the append ran.
    if event == "open" and args and isinstance(args[0], str):
        threads = _OPENED.get(os.path.basename(args[0]))
        if threads is not None:
            threads.append(threading.get_ident())


def _watch_opens(path: Path) -> list[int]:
    # Registers one uniquely named file; the hook itself is added once per process.
    if not _HOOK_ADDED:
        sys.addaudithook(_record_open)
        _HOOK_ADDED.append(True)
    return _OPENED.setdefault(path.name, [])


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


async def _send(output_api, fake_http, connector, host: str, answer: tuple[int, str], title: str = TITLE, body: str = BODY):
    # Answers the destination once, sends one reply, and returns its receipt and the one recorded request.
    fake_http.answer(host, answer)
    receipt = await connector.send(build_reply(body), output_api.OutputContent(title, body))
    [send] = fake_http.sends
    return receipt, send


# --- GitLab ----------------------------------------------------------------

GITLAB_CREATED = (201, json.dumps({"iid": 7, "web_url": GITLAB_ISSUE_URL}))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("labels", "expected_extra"),
    [pytest.param(["bug", "ci"], {"labels": "bug,ci"}, id="labels-comma-separated"), pytest.param([], {}, id="no-labels-no-key")],
)
async def test_gitlab_issue_posts_title_description_and_labels_and_links_web_url(output_api, fake_http, labels, expected_extra) -> None:
    # AC-21 / FR-24: the project path is URL-encoded, the token travels in private-token, and web_url is the link.
    connector = output_api.GitLabIssueOutput(project="acme/shop", labels=labels, token=GITLAB_KEY)

    receipt, send = await _send(output_api, fake_http, connector, "gitlab.com", GITLAB_CREATED)

    assert (send["method"], send["url"]) == ("POST", "https://gitlab.com/api/v4/projects/acme%2Fshop/issues")
    assert send["headers"].get("private-token") == GITLAB_KEY
    assert send["json_body"] == {"title": TITLE, "description": BODY, **expected_extra}
    assert receipt_rows([receipt]) == [("gitlab_issue", "sent", GITLAB_ISSUE_URL, None)]


@pytest.mark.asyncio
async def test_gitlab_merge_request_note_posts_the_chat_text_and_is_sent_without_a_link(output_api, fake_http) -> None:
    # AC-21 / D-21: a numeric project id is used as is; the note answer has no web_url, so the receipt has no URL.
    connector = output_api.GitLabIssueOutput(project=42, host="gitlab.acme.dev", merge_request=7, token=GITLAB_KEY)

    receipt, send = await _send(output_api, fake_http, connector, "gitlab.acme.dev", (201, json.dumps({"id": 301, "body": CHAT})))

    assert (send["method"], send["url"]) == ("POST", "https://gitlab.acme.dev/api/v4/projects/42/merge_requests/7/notes")
    assert send["headers"].get("private-token") == GITLAB_KEY
    assert send["json_body"] == {"body": CHAT}
    assert receipt_rows([receipt]) == [("gitlab_issue", "sent", None, None)]


@pytest.mark.asyncio
async def test_gitlab_self_managed_host_with_port_and_nested_group_path(output_api, fake_http) -> None:
    # §9.2(b): a port without a leading zero passes, and every "/" of a nested path is encoded.
    connector = output_api.GitLabIssueOutput(project="acme/platform/shop", host="gitlab.acme.dev:8443", token=GITLAB_KEY)

    receipt, send = await _send(output_api, fake_http, connector, "gitlab.acme.dev", (201, json.dumps({"iid": 3, "web_url": "https://gitlab.acme.dev:8443/acme/platform/shop/-/issues/3"})))

    assert send["url"] == "https://gitlab.acme.dev:8443/api/v4/projects/acme%2Fplatform%2Fshop/issues"
    assert receipt.url == "https://gitlab.acme.dev:8443/acme/platform/shop/-/issues/3"


@pytest.mark.asyncio
async def test_gitlab_http_web_url_is_failed_invalid_response(output_api, fake_http) -> None:
    # EC-26 / INV-9: a receipt link is only ever https://, even though the issue was created.
    connector = output_api.GitLabIssueOutput(project="acme/shop", host="gitlab.acme.dev", token=GITLAB_KEY)

    receipt, _ = await _send(output_api, fake_http, connector, "gitlab.acme.dev", (201, json.dumps({"iid": 7, "web_url": "http://gitlab.acme.dev/acme/shop/-/issues/7"})))

    assert receipt_rows([receipt]) == [("gitlab_issue", "failed", None, "invalid_response")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "text_of", "cap"),
    [
        pytest.param({"project": "acme/shop"}, lambda body: body["description"], 1_048_576, id="issue-description"),
        pytest.param({"project": "acme/shop", "merge_request": 7}, lambda body: body["body"], 1_000_000, id="merge-request-note"),
    ],
)
@pytest.mark.parametrize("excess", [0, 1], ids=["at-cap", "one-over"])
async def test_gitlab_text_is_cut_to_its_documented_cap(output_api, fake_http, options, text_of, cap, excess) -> None:
    # §9.2(a) / INV-13: the description caps the body; the note caps the chat text, marker included.
    connector = output_api.GitLabIssueOutput(**options, token=GITLAB_KEY)
    is_note = "merge_request" in options
    body = "x" * (cap + excess - (len(TITLE) + 2 if is_note else 0))

    _, send = await _send(output_api, fake_http, connector, "gitlab.com", GITLAB_CREATED, body=body)

    text = text_of(send["json_body"])
    assert len(text) == cap
    assert text.endswith(MARKER) is bool(excess)


INVALID_GITLAB = [
    pytest.param({"project": "acme shop"}, "project", id="EC-27-project-space"),
    pytest.param({"project": "../x"}, "project", id="EC-27-project-dot-dot"),
    pytest.param({"project": "shop"}, "project", id="EC-27-project-no-namespace"),
    pytest.param({"project": "acme/../x"}, "project", id="project-dot-dot-segment"),
    pytest.param({"project": "/acme/shop"}, "project", id="project-leading-slash"),
    pytest.param({"project": "acme/shop/"}, "project", id="project-trailing-slash"),
    pytest.param({"project": 0}, "project", id="project-zero"),
    pytest.param({"project": -1}, "project", id="project-negative"),
    pytest.param({"project": True}, "project", id="project-bool"),
    pytest.param({"project": "acme/shop", "host": "gitlab.com:99999"}, "host", id="EC-27-host-port-too-big"),
    pytest.param({"project": "acme/shop", "host": "gitlab.com:0"}, "host", id="EC-27-host-port-zero"),
    pytest.param({"project": "acme/shop", "host": "gitlab.com:080"}, "host", id="host-port-leading-zero"),
    pytest.param({"project": "acme/shop", "host": "https://gitlab.com"}, "host", id="EC-27-host-scheme"),
    pytest.param({"project": "acme/shop", "host": "gitlab.com/evil"}, "host", id="host-path"),
    pytest.param({"project": "acme/shop", "host": "bot@gitlab.com"}, "host", id="host-userinfo"),
    pytest.param({"project": "acme/shop", "merge_request": 0}, "merge_request", id="merge-request-zero"),
    pytest.param({"project": "acme/shop", "merge_request": True}, "merge_request", id="merge-request-bool"),
    pytest.param({"project": "acme/shop", "merge_request": "7"}, "merge_request", id="merge-request-string"),
    pytest.param({"project": "acme/shop", "labels": "bug"}, "labels", id="labels-one-string"),
]


@pytest.mark.parametrize(("options", "parameter"), INVALID_GITLAB)
def test_gitlab_invalid_arguments_name_their_parameter(output_api, options, parameter) -> None:
    # EC-27 / INV-10 / INV-11: the target is fixed at construction; no scheme, path, or userinfo trick passes.
    with pytest.raises(ConfigurationError) as info:
        output_api.GitLabIssueOutput(**options, token=GITLAB_KEY)

    assert re.search(rf"\b{parameter}\b", str(info.value)), str(info.value)
    assert "S3CRET" not in str(info.value)


# --- GitHub job summary ----------------------------------------------------


@pytest.mark.asyncio
async def test_job_summary_appends_the_chat_text_and_a_blank_line_after_what_is_there(output_api, tmp_path) -> None:
    # AC-22 / FR-25 / INV-12: an append, never an overwrite, and no network call.
    path = tmp_path / "summary.md"
    path.write_text("## Earlier step\n", encoding="utf-8")
    connector = output_api.GitHubJobSummaryOutput(path=str(path))

    receipt = await connector.send(build_reply(BODY), output_api.OutputContent(TITLE, BODY))

    assert receipt_rows([receipt]) == [("github_job_summary", "sent", None, None)]
    assert path.read_text(encoding="utf-8") == "## Earlier step\n" + CHAT + SEPARATOR


@pytest.mark.asyncio
async def test_job_summary_path_comes_from_github_step_summary(output_api, tmp_path, monkeypatch) -> None:
    # D-18 / §9.3: GitHub Actions sets GITHUB_STEP_SUMMARY per step; it is the path when none is passed.
    path = tmp_path / "step_summary"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))

    receipt = await output_api.GitHubJobSummaryOutput().send(build_reply(BODY), output_api.OutputContent(TITLE, BODY))

    assert receipt.status.value == "sent"
    assert path.read_text(encoding="utf-8") == CHAT + SEPARATOR


@pytest.mark.asyncio
async def test_job_summary_concurrent_appends_run_off_the_loop_one_after_the_other(output_api, tmp_path) -> None:
    # AC-22 / EC-31 / INV-12 / D-18: two sends at once; each block stays whole, on one worker thread, never the loop's.
    path = tmp_path / f"summary-{uuid.uuid4().hex}.md"
    path.write_text("", encoding="utf-8")
    opened = _watch_opens(path)
    connector = output_api.GitHubJobSummaryOutput(path=str(path))
    first = output_api.OutputContent("First review", "a" * 200_000)
    second = output_api.OutputContent("Second review", "b" * 200_000)
    loop_thread = threading.get_ident()

    receipts = await asyncio.gather(connector.send(build_reply(first.body), first), connector.send(build_reply(second.body), second))

    assert receipt_rows(receipts) == [("github_job_summary", "sent", None, None)] * 2
    first_block = f"First review\n\n{'a' * 200_000}" + SEPARATOR
    second_block = f"Second review\n\n{'b' * 200_000}" + SEPARATOR
    assert path.read_text(encoding="utf-8") in (first_block + second_block, second_block + first_block)
    assert len(opened) == 2, "each send must open the summary file once"
    assert loop_thread not in opened, "the append ran on the event-loop thread"
    assert len(set(opened)) == 1, "the appends ran on more than one thread, so they could interleave"


@pytest.mark.asyncio
@pytest.mark.parametrize("excess", [0, 1], ids=["at-cap", "one-over"])
async def test_job_summary_text_is_cut_so_the_block_is_at_most_262144_characters(output_api, tmp_path, excess) -> None:
    # §9.2(a) / INV-13: truncate(chat, 262,144 - 2) then the blank line, so a block never passes 262,144.
    path = tmp_path / "summary.md"
    path.write_text("", encoding="utf-8")
    body = "x" * (262_142 + excess - len(TITLE) - 2)

    await output_api.GitHubJobSummaryOutput(path=str(path)).send(build_reply(body), output_api.OutputContent(TITLE, body))

    text = path.read_text(encoding="utf-8")
    assert len(text) == 262_144
    assert text.endswith(MARKER + SEPARATOR) is bool(excess)


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["missing-directory", "path-is-a-directory"])
async def test_job_summary_os_error_is_failed_file_error_and_creates_nothing(output_api, tmp_path, where) -> None:
    # AC-22 / EC-30 / D-18: create_parents=False, so a missing directory is not made; OSError maps to file_error.
    path = tmp_path / "missing" / "summary.md" if where == "missing-directory" else tmp_path

    receipt = await output_api.GitHubJobSummaryOutput(path=str(path)).send(build_reply(BODY), output_api.OutputContent(TITLE, BODY))

    assert receipt_rows([receipt]) == [("github_job_summary", "failed", None, "file_error")]
    assert not (tmp_path / "missing").exists()


@pytest.mark.asyncio
async def test_delivery_error_lists_file_error_among_codes_that_may_already_be_delivered(output_api, tmp_path) -> None:
    # AC-36 / FR-35 / EC-30: a failed append may have written part of the text, so the resend caution must cover it.
    path = tmp_path / "missing" / "summary.md"
    reply = build_reply(BODY)

    with pytest.raises(output_api.OutputDeliveryError) as info:
        await output_api.OutputDispatcher.deliver((output_api.GitHubJobSummaryOutput(path=str(path)),), reply, reply.metadata)

    err = info.value
    assert err.safe_runtime_details == {"failed": [["github_job_summary", "file_error"]], "receipt_count": 1}
    assert [item for item in err.repair_approaches if "file_error" in item and "may already have been delivered" in item], err.repair_approaches
    assert str(path) not in repr(err.details)


# --- Confluence ------------------------------------------------------------

CONFLUENCE_BODY_DOC = {"type": "doc", "version": 1, "content": [_paragraph("Applying SAVE10 leaves the total unchanged."), _paragraph("Steps: add ten items, apply SAVE10.")]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ids", "expected_ids"),
    [
        pytest.param({"space_id": "98304", "parent_id": "12345"}, {"spaceId": "98304", "parentId": "12345"}, id="string-ids"),
        pytest.param({"space_id": 98304, "parent_id": 12345}, {"spaceId": "98304", "parentId": "12345"}, id="int-ids-sent-as-strings"),
        pytest.param({"space_id": "98304"}, {"spaceId": "98304"}, id="no-parent-no-parentId"),
    ],
)
async def test_confluence_creates_a_v2_page_with_an_adf_body_and_links_it(output_api, fake_http, ids, expected_ids) -> None:
    # AC-23 / FR-26 / D-10: the ADF document travels as a JSON string; the link is the site's /wiki plus _links.webui.
    connector = output_api.ConfluencePageOutput(**CONFLUENCE_SITE, **ids)

    receipt, send = await _send(output_api, fake_http, connector, "acme.atlassian.net", CONFLUENCE_CREATED)

    assert (send["method"], send["url"]) == ("POST", "https://acme.atlassian.net/wiki/api/v2/pages")
    assert send["headers"].get("authorization") == CONFLUENCE_BASIC
    value = send["json_body"]["body"].pop("value")
    assert send["json_body"] == {**expected_ids, "status": "current", "title": TITLE, "body": {"representation": "atlas_doc_format"}}
    assert isinstance(value, str)
    assert json.loads(value) == CONFLUENCE_BODY_DOC
    assert receipt_rows([receipt]) == [("confluence_page", "sent", "https://acme.atlassian.net/wiki/spaces/ENG/pages/557060/Checkout", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("excess", [0, 1], ids=["at-cap", "one-over"])
async def test_confluence_body_is_cut_at_500000_characters_before_it_becomes_adf(output_api, fake_http, excess) -> None:
    # §9.2(a) / INV-13: truncate(body, 500,000); the marker's blank line makes "[truncated]" its own paragraph.
    connector = output_api.ConfluencePageOutput(**CONFLUENCE_SITE, space_id="98304")
    body = "x" * (500_000 + excess)

    _, send = await _send(output_api, fake_http, connector, "acme.atlassian.net", CONFLUENCE_CREATED, body=body)

    content = json.loads(send["json_body"]["body"]["value"])["content"]
    expected = [_paragraph("x" * (500_000 - len(MARKER))), _paragraph("[truncated]")] if excess else [_paragraph(body)]
    assert content == expected


INVALID_CONFLUENCE = [
    pytest.param({"site": "acme.example.com"}, "site", id="site-not-atlassian"),
    pytest.param({"site": "https://acme.atlassian.net"}, "site", id="site-scheme"),
    pytest.param({"site": "acme.atlassian.net/evil"}, "site", id="site-path"),
    pytest.param({"space_id": "ENG"}, "space_id", id="space-id-key-not-id"),
    pytest.param({"space_id": ""}, "space_id", id="space-id-blank"),
    pytest.param({"space_id": 0}, "space_id", id="space-id-zero"),
    pytest.param({"space_id": True}, "space_id", id="space-id-bool"),
    pytest.param({"parent_id": "12a"}, "parent_id", id="parent-id-not-digits"),
    pytest.param({"parent_id": -5}, "parent_id", id="parent-id-negative"),
    pytest.param({"email": "bot at acme.com"}, "email", id="email-not-an-address"),
]


@pytest.mark.parametrize(("override", "parameter"), INVALID_CONFLUENCE)
def test_confluence_invalid_arguments_name_their_parameter(output_api, override, parameter) -> None:
    # §9.2(b) / INV-10 / INV-11: the site and space are fixed at construction.
    options = {**CONFLUENCE_SITE, "space_id": "98304", **override}

    with pytest.raises(ConfigurationError) as info:
        output_api.ConfluencePageOutput(**options)

    assert re.search(rf"\b{parameter}\b", str(info.value)), str(info.value)


# --- Typefully -------------------------------------------------------------


@pytest.mark.asyncio
async def test_typefully_creates_one_draft_for_the_chosen_platforms_and_never_schedules(output_api, fake_http) -> None:
    # AC-24 / INV-7 / FR-27: exact body, so publish_at, plan_at, and share can never ride along.
    connector = output_api.TypefullyDraftOutput(social_set_id=123, platforms=["x", output_api.TypefullyPlatform.LINKEDIN], api_key=TYPEFULLY_KEY)

    receipt, send = await _send(output_api, fake_http, connector, "api.typefully.com", TYPEFULLY_CREATED)

    assert (send["method"], send["url"]) == ("POST", "https://api.typefully.com/v2/social-sets/123/drafts")
    assert send["headers"].get("authorization") == f"Bearer {TYPEFULLY_KEY}"
    post = {"enabled": True, "posts": [{"text": BODY}]}
    assert send["json_body"] == {"draft_title": TITLE, "platforms": {"x": post, "linkedin": post}}
    assert receipt_rows([receipt]) == [("typefully_draft", "sent", TYPEFULLY_DRAFT_URL, None)]


@pytest.mark.asyncio
async def test_typefully_duplicate_platforms_are_dropped_in_order_and_ids_may_be_strings(output_api, fake_http) -> None:
    # §9.2(b) / D-19: members() keeps the first of each platform; a string social set id is used as given.
    connector = output_api.TypefullyDraftOutput(social_set_id="ss_9-A", platforms=["linkedin", "x", output_api.TypefullyPlatform.LINKEDIN], api_key=TYPEFULLY_KEY)

    _, send = await _send(output_api, fake_http, connector, "api.typefully.com", TYPEFULLY_CREATED)

    assert send["url"] == "https://api.typefully.com/v2/social-sets/ss_9-A/drafts"
    assert list(send["json_body"]["platforms"]) == ["linkedin", "x"]


INVALID_TYPEFULLY = [
    pytest.param({"platforms": []}, "platforms", id="no-platforms"),
    pytest.param({"platforms": ["myspace"]}, "platforms", id="unknown-platform"),
    pytest.param({"platforms": "linkedin"}, "platforms", id="platforms-one-string"),
    pytest.param({"social_set_id": "a b"}, "social_set_id", id="social-set-space"),
    pytest.param({"social_set_id": "../1"}, "social_set_id", id="social-set-path"),
    pytest.param({"social_set_id": 0}, "social_set_id", id="social-set-zero"),
    pytest.param({"social_set_id": True}, "social_set_id", id="social-set-bool"),
]


@pytest.mark.parametrize(("override", "parameter"), INVALID_TYPEFULLY)
def test_typefully_invalid_arguments_name_their_parameter(output_api, override, parameter) -> None:
    # §9.2(b) / INV-11: platforms are TypefullyPlatform members, at least one; the social set id is a safe path segment.
    options = {"social_set_id": 123, "platforms": ["x"], "api_key": TYPEFULLY_KEY, **override}

    with pytest.raises(ConfigurationError) as info:
        output_api.TypefullyDraftOutput(**options)

    assert re.search(rf"\b{parameter}\b", str(info.value)), str(info.value)


# --- HubSpot ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_hubspot_creates_a_task_stamped_with_the_send_time_in_utc(output_api, fake_http) -> None:
    # AC-25 / D-20 / FR-28: hs_timestamp is UTC ISO 8601 with milliseconds and Z, taken at send time.
    connector = output_api.HubSpotTaskOutput(access_token=HUBSPOT_KEY)
    before = datetime.now(timezone.utc).replace(microsecond=0)

    receipt, send = await _send(output_api, fake_http, connector, "api.hubapi.com", HUBSPOT_CREATED)

    after = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert (send["method"], send["url"]) == ("POST", "https://api.hubapi.com/crm/v3/objects/tasks")
    assert send["headers"].get("authorization") == f"Bearer {HUBSPOT_KEY}"
    properties = dict(send["json_body"]["properties"])
    stamp = properties.pop("hs_timestamp")
    assert list(send["json_body"]) == ["properties"]
    assert properties == {"hs_task_subject": TITLE, "hs_task_body": BODY}
    assert re.fullmatch(HS_TIMESTAMP_PATTERN, stamp), stamp
    assert before <= datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc) <= after
    assert receipt_rows([receipt]) == [("hubspot_task", "sent", None, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("excess", [0, 1], ids=["at-cap", "one-over"])
async def test_hubspot_task_body_is_cut_at_65536_characters(output_api, fake_http, excess) -> None:
    # §9.2(a) / INV-13: hs_task_body is truncate(body, 65,536), marker included.
    connector = output_api.HubSpotTaskOutput(access_token=HUBSPOT_KEY)

    _, send = await _send(output_api, fake_http, connector, "api.hubapi.com", HUBSPOT_CREATED, body="x" * (65_536 + excess))

    text = send["json_body"]["properties"]["hs_task_body"]
    assert len(text) == 65_536
    assert text.endswith(MARKER) is bool(excess)


# --- Shared ----------------------------------------------------------------

TITLE_FIELDS = {
    "gitlab_issue": lambda body: body["title"],
    "confluence_page": lambda body: body["title"],
    "typefully_draft": lambda body: body["draft_title"],
    "hubspot_task": lambda body: body["properties"]["hs_task_subject"],
}


@pytest.mark.asyncio
@pytest.mark.parametrize("key", list(TITLE_FIELDS))
async def test_new_connector_titles_are_one_line_of_at_most_250_characters(output_api, fake_http, key) -> None:
    # INV-13: every title goes through single_line(title, 250), so a multi-line or long title never breaks the field.
    case = CONNECTOR_CASES[key]
    title = "Checkout\n  total ignores coupons " + "y" * 300

    _, send = await _send(output_api, fake_http, case.build(output_api), case.host, case.success, title=title)

    assert TITLE_FIELDS[key](send["json_body"]) == ("Checkout total ignores coupons " + "y" * 300)[:250]
