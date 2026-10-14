"""FILE: tests/features/agent_output_connectors/test_output_connectors_update_in_place.py

PURPOSE: Prove GitHub update-in-place: a sticky comment found by its marker across up to 10 pages and edited, one issue per key found by label, reads before the single write, read failures that write nothing, marker forging neutralized, and the read and patch transport rules (method, body, timeout, retries, size ceiling, redirects, log filter), plus the OutputRequest and OutputRead records they use.
ROLE IN CODEBASE: Contract tests of vidbyte/lib/outputs/github.py with github_api.py (GitHubRequests, GitHubResponses), OutputHttp.read and OutputHttp.patch in vidbyte/lib/outputs/delivery.py, and OutputRequest and OutputRead in vidbyte/lib/dataclasses/outputs.py, against docs/spec/output-connector-followups/spec.md §8.5 and §9.2.
ARCHITECTURE NOTE: Most tests script HttpTransport._send_once (fake_http) and assert the ordered (method, URL) list it recorded. The size-ceiling, redirect, and log tests keep the real _send_once over httpx.MockTransport (httpx_destination), whose route here is a callable that answers a GET and a PATCH differently.
FUNCTION INVENTORY: test_sticky_* (AC-27, AC-29, D-15, EC-39); test_marker_* (D-14, D-16, AC-31, FR-33); test_read_failure_* (AC-28, INV-1); test_keyed_issue_* (AC-30, FR-32); test_invalid_key_or_comment_on_* (AC-32); test_reads_and_patches_* (AC-33, INV-4, D-22, EC-40); test_output_http_* (FR-30); test_output_request_* and test_output_read_* (§9.1); _wire, _page, _network_error.
COMMON MODIFICATION PATTERNS: Add a read outcome as one READ_FAILURES row, and a failure of a later page's read as one LATER_PAGE_FAILURES row; add a marker case as one MARKER_CASES row with the write it must cause.
WHAT NOT TO DO IN THIS FILE: 1. Do not answer the comments-page fragment and the edit fragment with one route: "/issues/412/comments" is not part of "/issues/comments/99", and the POST to "/issues/412/comments" has no "?". 2. Do not assert the order of keys inside a JSON body; compare whole values.
KNOWN EDGE CASES: The fake returns headers={} on every response, so paging can only stop on a short page or after 10 pages (D-15). A 500 on a read is not retried, unlike the transport default, because reads retry only 429 (INV-4). The 16,000,001-byte page is not valid JSON, so a read with no ceiling would answer invalid_response instead of network.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/output-connector-followups/spec.md (§6.2 AC-27 to AC-33; §6.3 EC-35 to EC-40; §8.1 D-14 to D-16, D-22; §8.5 pseudocode; §9.1; §13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_update_in_place.py
"""

from __future__ import annotations

import importlib
import json
import logging
import re

import httpx
import pytest

from tests.features.agent_output_connectors.factories import (
    GITHUB_CREATED,
    GITHUB_ISSUE_URL,
    GITHUB_TOKEN,
    SECRET_MARKER,
    build_reply,
    receipt_rows,
)
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError

TITLE = "Checkout total ignores coupons"
BODY = "Applying SAVE10 leaves the total unchanged.\n\nSteps: add ten items, apply SAVE10."
CHAT = f"{TITLE}\n\n{BODY}"
MARKER = "\n\n[truncated]"
REPO_API = "https://api.github.com/repos/acme/shop"
POST_COMMENT_URL = f"{REPO_API}/issues/412/comments"
KEYED_ISSUES_URL = f"{REPO_API}/issues?labels=vidbyte%3Anightly&state=open&sort=created&direction=asc&per_page=100"
STICKY_SUFFIX = "\n\n<!-- vidbyte:ci-review -->"
READ_FRAGMENT = "/issues/412/comments?per_page"
EDIT_FRAGMENT = "/issues/comments/"
KEYED_FRAGMENT = "/issues?labels="
COMMENT_LINK = "https://github.com/acme/shop/pull/412#issuecomment-99"
EDITED = (200, json.dumps({"id": 99, "html_url": COMMENT_LINK}))
POSTED = (201, json.dumps({"id": 2400000001, "html_url": "https://github.com/acme/shop/pull/412#issuecomment-2400000001"}))
GITHUB_HEADERS = {"authorization": f"Bearer {GITHUB_TOKEN}", "accept": "application/vnd.github+json", "x-github-api-version": "2026-03-10"}


def _page_url(page: int) -> str:
    return f"{POST_COMMENT_URL}?per_page=100&page={page}"


def _edit_url(comment_id: int) -> str:
    return f"{REPO_API}/issues/comments/{comment_id}"


def _page(first_id: int, count: int = 100) -> tuple[int, str]:
    # A full page of unmarked comments with ascending ids.
    return (200, json.dumps([{"id": first_id + offset, "body": f"Looks good {offset}"} for offset in range(count)]))


def _wire(fake_http) -> list[tuple[str, str]]:
    return [(send["method"], send["url"]) for send in fake_http.sends]


def _network_error() -> ProviderRequestError:
    return ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt="ConnectError: connection reset by peer")


def _sticky(output_api, **overrides):
    return output_api.GitHubIssueOutput(**{"repo": "acme/shop", "comment_on": 412, "key": "ci-review", "token": GITHUB_TOKEN, **overrides})


def _keyed(output_api):
    return output_api.GitHubIssueOutput(repo="acme/shop", labels=["bug"], key="nightly", token=GITHUB_TOKEN)


async def _send(output_api, connector, body: str = BODY):
    return await connector.send(build_reply(body), output_api.OutputContent(TITLE, body))


# --- Sticky comment --------------------------------------------------------


@pytest.mark.asyncio
async def test_sticky_marked_comment_on_page_two_is_edited_after_both_reads(output_api, fake_http) -> None:
    # AC-27 / INV-1 / D-15: GET page 1, GET page 2, then one PATCH of the marked comment; no POST.
    marked = (200, json.dumps([{"id": 99, "body": "Earlier review" + STICKY_SUFFIX}]))
    fake_http.answer(READ_FRAGMENT, _page(1001), marked)
    fake_http.answer(EDIT_FRAGMENT, EDITED)

    receipt = await _send(output_api, _sticky(output_api))

    assert _wire(fake_http) == [("GET", _page_url(1)), ("GET", _page_url(2)), ("PATCH", _edit_url(99))]
    assert fake_http.sends[2]["json_body"] == {"body": CHAT + STICKY_SUFFIX}
    assert receipt_rows([receipt]) == [("github_issue", "sent", COMMENT_LINK, None)]


@pytest.mark.asyncio
async def test_sticky_without_a_marker_on_a_short_page_posts_one_marked_comment(output_api, fake_http) -> None:
    # AC-27 / D-15: a page shorter than 100 ends the search; the only write is a POST with the marked body.
    fake_http.answer(READ_FRAGMENT, (200, json.dumps([{"id": 5, "body": "First!"}])))
    fake_http.answer("/issues/412/comments", POSTED)

    receipt = await _send(output_api, _sticky(output_api))

    assert _wire(fake_http) == [("GET", _page_url(1)), ("POST", POST_COMMENT_URL)]
    assert fake_http.sends[1]["json_body"] == {"body": CHAT + STICKY_SUFFIX}
    assert receipt.status.value == "sent"


@pytest.mark.asyncio
async def test_sticky_search_stops_after_ten_full_pages_then_posts(output_api, fake_http) -> None:
    # AC-29 / D-15: at most GITHUB_MAX_PAGES reads; an eleventh read would find no scripted answer.
    fake_http.answer(READ_FRAGMENT, *[_page(1 + 100 * index) for index in range(10)])
    fake_http.answer("/issues/412/comments", POSTED)

    receipt = await _send(output_api, _sticky(output_api))

    assert _wire(fake_http) == [("GET", _page_url(page)) for page in range(1, 11)] + [("POST", POST_COMMENT_URL)]
    assert receipt.status.value == "sent"


@pytest.mark.asyncio
async def test_sticky_marked_comment_deleted_before_the_patch_is_failed_http_404_without_a_post(output_api, fake_http) -> None:
    # EC-39 / INV-1: one write per send, so a failed PATCH never falls back to a POST.
    fake_http.answer(READ_FRAGMENT, (200, json.dumps([{"id": 99, "body": STICKY_SUFFIX}])))
    fake_http.answer(EDIT_FRAGMENT, (404, ""))

    receipt = await _send(output_api, _sticky(output_api))

    assert _wire(fake_http) == [("GET", _page_url(1)), ("PATCH", _edit_url(99))]
    assert receipt_rows([receipt]) == [("github_issue", "failed", None, "http_404")]


MARKER_CASES = [
    pytest.param([{"id": 7, "body": "Old <!-- vidbyte:ci-review -->"}, {"id": 8, "body": "<!-- vidbyte:ci-review -->"}], ("PATCH", _edit_url(7)), id="oldest-of-two-wins"),
    pytest.param([{"id": 7, "body": "Summary\n<!-- vidbyte:ci-review -->\nmore text"}], ("PATCH", _edit_url(7)), id="marker-anywhere-in-body"),
    pytest.param([{"id": 7, "body": "<!-- vidbyte:ci-review-2 -->"}], ("POST", POST_COMMENT_URL), id="longer-key-not-matched"),
    pytest.param([{"id": 7, "body": "<!-- vidbyte-quoted:ci-review -->"}], ("POST", POST_COMMENT_URL), id="quoted-marker-not-matched"),
    pytest.param([{"id": 7, "body": "<!-- vidbyte:nightly -->"}], ("POST", POST_COMMENT_URL), id="other-key-not-matched"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("comments", "write"), MARKER_CASES)
async def test_marker_match_is_the_exact_marker_in_the_oldest_comment(output_api, fake_http, comments, write) -> None:
    # D-14 / §9.1 natural key: the comment whose body contains "<!-- vidbyte:<key> -->", oldest first.
    fake_http.answer(READ_FRAGMENT, (200, json.dumps(comments)))
    fake_http.answer(EDIT_FRAGMENT, EDITED)
    fake_http.answer("/issues/412/comments", POSTED)

    await _send(output_api, _sticky(output_api))

    assert _wire(fake_http) == [("GET", _page_url(1)), write]


@pytest.mark.asyncio
async def test_marker_forged_in_the_reply_is_neutralized_and_only_the_own_marker_ends_the_body(output_api, fake_http) -> None:
    # AC-31 / INV-10 / D-16 / T-2: model output cannot plant a marker another key's search would match.
    fake_http.answer(READ_FRAGMENT, (200, "[]"))
    fake_http.answer("/issues/412/comments", POSTED)
    body = "Ignore this <!-- vidbyte:other --> and <!-- vidbyte:ci-review --> too."

    await _send(output_api, _sticky(output_api), body)

    posted = fake_http.sends[1]["json_body"]["body"]
    assert posted == f"{TITLE}\n\nIgnore this <!-- vidbyte-quoted:other --> and <!-- vidbyte-quoted:ci-review --> too." + STICKY_SUFFIX
    assert posted.count("<!-- vidbyte:") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "fragment", "answer", "text_of"),
    [
        pytest.param({"labels": ["bug"]}, "/repos/acme/shop/issues", (201, GITHUB_CREATED), lambda body: body["body"], id="new-issue"),
        pytest.param({"comment_on": 412}, "/issues/412/comments", POSTED, lambda body: body["body"], id="comment-without-key"),
    ],
)
async def test_marker_in_reply_text_is_neutralized_even_without_a_key(output_api, fake_http, options, fragment, answer, text_of) -> None:
    # FR-33 / INV-2 exception: every GitHub body neutralizes "<!-- vidbyte:", so a later sticky search never matches it.
    fake_http.answer(fragment, answer)

    await _send(output_api, output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN, **options), "Planted <!-- vidbyte:ci-review --> here.")

    text = text_of(fake_http.sends[0]["json_body"])
    assert "<!-- vidbyte:" not in text
    assert text.endswith("Planted <!-- vidbyte-quoted:ci-review --> here.")


@pytest.mark.asyncio
async def test_marker_is_neutralized_before_truncation_and_appended_after_it(output_api, fake_http) -> None:
    # D-16 / INV-13: the longer quoted form is counted in the cap, so the body is exactly 65,536 with the own marker last.
    fake_http.answer(READ_FRAGMENT, (200, "[]"))
    fake_http.answer("/issues/412/comments", POSTED)

    await _send(output_api, _sticky(output_api), "<!-- vidbyte:zz --> " + "x" * 70_000)

    posted = fake_http.sends[1]["json_body"]["body"]
    assert len(posted) == 65_536
    assert posted.startswith(f"{TITLE}\n\n<!-- vidbyte-quoted:zz --> x")
    assert posted.endswith(MARKER + STICKY_SUFFIX)


# --- Read failures ---------------------------------------------------------

READ_FAILURES = [
    pytest.param([(429, "")] * 3, "http_429", 3, id="429-three-times"),
    pytest.param([(500, "")], "http_500", 1, id="500-not-retried"),
    pytest.param([_network_error()], "network", 1, id="network"),
    pytest.param([(200, "<html>rate limited</html>")], "invalid_response", 1, id="non-json"),
    pytest.param([(200, json.dumps({"message": "Not a list"}))], "invalid_response", 1, id="json-object"),
    pytest.param([(200, json.dumps([1, "two"]))], "invalid_response", 1, id="list-of-non-objects"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sticky", "keyed"])
@pytest.mark.parametrize(("answers", "error_code", "reads"), READ_FAILURES)
async def test_read_failure_is_that_reads_receipt_and_nothing_is_written(output_api, fake_http, mode, answers, error_code, reads) -> None:
    # AC-28 / INV-1 / §9.2(c): reads map failures like posts do, retry only 429, and stop the send before any write.
    connector = _sticky(output_api) if mode == "sticky" else _keyed(output_api)
    fake_http.answer(READ_FRAGMENT if mode == "sticky" else KEYED_FRAGMENT, *answers)

    receipt = await _send(output_api, connector)

    assert receipt_rows([receipt]) == [("github_issue", "failed", None, error_code)]
    assert [method for method, _ in _wire(fake_http)] == ["GET"] * reads


LATER_PAGE_FAILURES = [
    pytest.param((500, ""), "http_500", id="500"),
    pytest.param(_network_error(), "network", id="network"),
    pytest.param((200, "<html>rate limited</html>"), "invalid_response", id="non-json"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("failure", "error_code"), LATER_PAGE_FAILURES)
async def test_read_failure_on_a_later_page_is_that_reads_receipt_and_nothing_is_written(output_api, fake_http, failure, error_code) -> None:
    # AC-28 / INV-1 / R-5: page 1 is full, so page 2 is read; a
    # failure there ends the send with no write, not a POST as if
    # the list had ended. The POST is answered so that a wrong
    # write shows on the wire instead of raising.
    fake_http.answer(READ_FRAGMENT, _page(1001), failure)
    fake_http.answer("/issues/412/comments", POSTED)

    receipt = await _send(output_api, _sticky(output_api))

    assert receipt_rows([receipt]) == [("github_issue", "failed", None, error_code)]
    assert _wire(fake_http) == [("GET", _page_url(1)), ("GET", _page_url(2))]


# --- One issue per key -----------------------------------------------------


@pytest.mark.asyncio
async def test_keyed_issue_found_skips_pull_requests_and_comments_on_the_oldest_issue(output_api, fake_http) -> None:
    # AC-30 / FR-32 / D-14: the list endpoint, oldest first; an entry with pull_request is a PR, not an issue.
    issues = [{"number": 5, "pull_request": {"url": f"{REPO_API}/pulls/5"}}, {"number": 9}, {"number": 11}]
    fake_http.answer(KEYED_FRAGMENT, (200, json.dumps(issues)))
    fake_http.answer("/issues/9/comments", (201, json.dumps({"id": 1, "html_url": "https://github.com/acme/shop/issues/9#issuecomment-1"})))

    receipt = await _send(output_api, _keyed(output_api))

    assert _wire(fake_http) == [("GET", KEYED_ISSUES_URL), ("POST", f"{REPO_API}/issues/9/comments")]
    assert fake_http.sends[1]["json_body"] == {"body": CHAT}
    assert receipt_rows([receipt]) == [("github_issue", "sent", "https://github.com/acme/shop/issues/9#issuecomment-1", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize("issues", [[], [{"number": 5, "pull_request": {}}]], ids=["none-open", "only-a-pull-request"])
async def test_keyed_issue_missing_creates_the_issue_with_the_key_label_added(output_api, fake_http, issues) -> None:
    # AC-30 / FR-32: the create keeps the caller's labels and adds "vidbyte:<key>"; the issue body has no marker.
    fake_http.answer(KEYED_FRAGMENT, (200, json.dumps(issues)))
    fake_http.answer("/repos/acme/shop/issues", (201, GITHUB_CREATED))

    receipt = await _send(output_api, _keyed(output_api))

    assert _wire(fake_http) == [("GET", KEYED_ISSUES_URL), ("POST", f"{REPO_API}/issues")]
    assert fake_http.sends[1]["json_body"] == {"title": TITLE, "body": BODY, "labels": ["bug", "vidbyte:nightly"]}
    assert receipt_rows([receipt]) == [("github_issue", "sent", GITHUB_ISSUE_URL, None)]


INVALID_KEY_OR_COMMENT_ON = [
    pytest.param({"comment_on": 412, "key": "ci review"}, "key", id="key-space"),
    pytest.param({"comment_on": 412, "key": "ci/review"}, "key", id="key-slash"),
    pytest.param({"comment_on": 412, "key": "ci:review"}, "key", id="key-colon"),
    pytest.param({"comment_on": 412, "key": "k" * 43}, "key", id="key-43-chars"),
    pytest.param({"comment_on": 412, "key": ""}, "key", id="key-empty"),
    pytest.param({"comment_on": 0}, "comment_on", id="comment-on-zero"),
    pytest.param({"comment_on": -3}, "comment_on", id="comment-on-negative"),
    pytest.param({"comment_on": True}, "comment_on", id="comment-on-bool"),
    pytest.param({"comment_on": "412"}, "comment_on", id="comment-on-string"),
    pytest.param({"comment_on": 4.5}, "comment_on", id="comment-on-float"),
]


@pytest.mark.parametrize(("options", "parameter"), INVALID_KEY_OR_COMMENT_ON)
def test_invalid_key_or_comment_on_names_its_parameter(output_api, options, parameter) -> None:
    # AC-32 / §9.1: a key is [A-Za-z0-9._-]{1,42}, so "vidbyte:" plus the key fits GitHub's 50-character label.
    with pytest.raises(ConfigurationError) as info:
        output_api.GitHubIssueOutput(repo="acme/shop", token=GITHUB_TOKEN, **options)

    assert re.search(rf"\b{parameter}\b", str(info.value)), str(info.value)


@pytest.mark.asyncio
async def test_longest_valid_key_is_accepted_and_used_in_the_marker(output_api, fake_http) -> None:
    # AC-32 boundary: 42 characters from the allowed set pass.
    key = "v1.2_x-y" + "a" * 34
    fake_http.answer(READ_FRAGMENT, (200, "[]"))
    fake_http.answer("/issues/412/comments", POSTED)

    await _send(output_api, _sticky(output_api, key=key))

    assert fake_http.sends[1]["json_body"]["body"].endswith(f"\n\n<!-- vidbyte:{key} -->")


# --- Read and patch transport rules ----------------------------------------


@pytest.mark.asyncio
async def test_reads_and_patches_use_the_output_transport_rules(output_api, fake_http) -> None:
    # AC-33 / INV-4 / D-22: GET with no body and the 16 MB ceiling; PATCH with a JSON body and the 1 MB ceiling; both 10 s.
    fake_http.answer(READ_FRAGMENT, (200, json.dumps([{"id": 99, "body": STICKY_SUFFIX}])))
    fake_http.answer(EDIT_FRAGMENT, EDITED)

    await _send(output_api, _sticky(output_api))

    read, patch = fake_http.sends
    assert (read["method"], read["json_body"], read.get("content"), read["timeout_seconds"], read["max_response_bytes"]) == ("GET", None, None, 10.0, 16_000_000)
    assert (patch["method"], patch.get("content"), patch["timeout_seconds"], patch["max_response_bytes"]) == ("PATCH", None, 10.0, 1_000_000)
    assert [{name: send["headers"].get(name) for name in GITHUB_HEADERS} for send in (read, patch)] == [GITHUB_HEADERS, GITHUB_HEADERS]


def _sticky_route(page_body: bytes):
    # Answers every GET with page_body and every PATCH with the edited comment.
    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=page_body)
        return httpx.Response(200, json={"id": 99, "html_url": COMMENT_LINK})

    return route


@pytest.mark.asyncio
async def test_reads_and_patches_accept_a_page_above_the_write_ceiling(output_api, httpx_destination) -> None:
    # D-22: 100 comments of up to 65,536 characters do not fit in 1 MB, so reads have their own 16 MB ceiling.
    page = json.dumps([{"id": 99, "body": "x" * 1_000_100 + STICKY_SUFFIX}]).encode()
    httpx_destination.routes["api.github.com"] = _sticky_route(page)

    receipt = await _send(output_api, _sticky(output_api))

    assert [request.method for request in httpx_destination] == ["GET", "PATCH"]
    assert receipt_rows([receipt]) == [("github_issue", "sent", COMMENT_LINK, None)]


@pytest.mark.asyncio
async def test_reads_and_patches_refuse_a_page_over_16000000_bytes_as_network_and_write_nothing(output_api, httpx_destination) -> None:
    # EC-40 / D-22 / INV-1: the transport refuses the oversized read, so the send ends before any write.
    httpx_destination.routes["api.github.com"] = _sticky_route(b"[" + b" " * 16_000_000)

    receipt = await _send(output_api, _sticky(output_api))

    assert receipt_rows([receipt]) == [("github_issue", "failed", None, "network")]
    assert [request.method for request in httpx_destination] == ["GET"]


@pytest.mark.asyncio
async def test_reads_and_patches_never_follow_a_redirect(output_api, httpx_destination) -> None:
    # AC-33 / INV-4 / T-3: a 302 on a read is a failure after one request, and the token never reaches the Location host.
    httpx_destination.routes["api.github.com"] = httpx.Response(302, headers={"location": "https://collector.example.net/steal"})
    httpx_destination.routes["collector.example.net"] = httpx.Response(200, json=[])

    receipt = await _send(output_api, _sticky(output_api))

    assert receipt_rows([receipt]) == [("github_issue", "failed", None, "http_302")]
    assert [request.url.host for request in httpx_destination] == ["api.github.com"]


@pytest.mark.asyncio
async def test_reads_and_patches_drop_the_httpx_request_log_while_the_callers_own_requests_still_log(output_api, httpx_destination, caplog) -> None:
    # AC-33 / INV-3: the log guard covers reads and patches as it covers posts, and stays scoped to the send.
    caplog.set_level(logging.INFO)
    httpx_destination.routes["api.github.com"] = _sticky_route(json.dumps([{"id": 99, "body": STICKY_SUFFIX}]).encode())
    httpx_destination.routes["api.example.com"] = httpx.Response(200, json={"ok": True})

    receipt = await _send(output_api, _sticky(output_api))
    async with httpx.AsyncClient() as client:
        await client.post("https://api.example.com/v1/reports", json={"report": "nightly"})

    assert receipt.status.value == "sent"
    assert [request.method for request in httpx_destination] == ["GET", "PATCH", "POST"]
    messages = [record.getMessage() for record in caplog.records]
    assert [message for message in messages if message.startswith("HTTP Request:") and "api.github.com" in message] == []
    assert any(message.startswith("HTTP Request: POST https://api.example.com/v1/reports") for message in messages), messages


# --- OutputHttp.read and OutputHttp.patch ----------------------------------


def _delivery():
    return importlib.import_module("vidbyte.lib.outputs.delivery")


def _records():
    return importlib.import_module("vidbyte.lib.dataclasses.outputs")


def _github_destination():
    return importlib.import_module("vidbyte.lib.enums.outputs").OutputDestination.GITHUB_ISSUE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "failure", "data"),
    [
        pytest.param((200, '[{"id": 1}]'), None, [{"id": 1}], id="json-list"),
        pytest.param((404, ""), ("github_issue", "failed", None, "http_404"), None, id="status-failure"),
        pytest.param((200, "not json"), ("github_issue", "failed", None, "invalid_response"), None, id="non-json-failure"),
    ],
)
async def test_output_http_read_returns_parsed_json_or_a_failed_receipt(fake_http, answer, failure, data) -> None:
    # FR-30 / §8.5: read returns OutputRead(data=<parsed JSON>) or OutputRead(failure=<FAILED receipt>), never both.
    records = _records()
    fake_http.answer("api.github.com", answer)

    read = await _delivery().OutputHttp.read(_github_destination(), records.OutputRequest(_page_url(1), dict(GITHUB_HEADERS), None))

    assert isinstance(read, records.OutputRead)
    assert (None if read.failure is None else receipt_rows([read.failure])[0], read.data) == (failure, data)
    assert fake_http.sends[0]["method"] == "GET"


@pytest.mark.asyncio
async def test_output_http_patch_sends_one_patch_and_links_the_response(fake_http) -> None:
    # FR-30 / §8.5: patch keeps post's guarantees, with method PATCH.
    records = _records()
    fake_http.answer("api.github.com", EDITED)
    request = records.OutputRequest(_edit_url(99), dict(GITHUB_HEADERS), {"body": "edited"}, link_path=("html_url",))

    receipt = await _delivery().OutputHttp.patch(_github_destination(), request)

    assert receipt_rows([receipt]) == [("github_issue", "sent", COMMENT_LINK, None)]
    assert [(send["method"], send["url"], send["json_body"]) for send in fake_http.sends] == [("PATCH", _edit_url(99), {"body": "edited"})]


def test_output_request_holds_a_json_body_or_content_or_neither_and_hides_content() -> None:
    # §9.1 / INV-3: reads pass neither; signed webhooks pass content, which repr never shows.
    records = _records()

    read = records.OutputRequest("https://api.github.com/x", {}, None)
    signed = records.OutputRequest("https://hook.example.net/x", {}, None, content=b'{"token": "S3CRETbytes"}')

    assert (read.json_body, read.content, signed.json_body) == (None, None, None)
    assert SECRET_MARKER not in repr(signed)


@pytest.mark.parametrize(
    ("options", "fields"),
    [
        pytest.param({"json_body": {"a": 1}, "content": b"{}"}, ("json_body", "content"), id="both"),
        pytest.param({"json_body": None, "content": "{}"}, ("content",), id="content-str"),
        pytest.param({"json_body": [1, 2]}, ("json_body",), id="json-body-list"),
    ],
)
def test_output_request_refuses_a_bad_body_naming_the_field(options, fields) -> None:
    # §9.1: never both bodies; content is bytes; json_body is a mapping or None.
    with pytest.raises(ConfigurationError) as info:
        _records().OutputRequest("https://api.github.com/x", {}, **options)

    assert any(re.search(rf"\b{field}\b", str(info.value)) for field in fields), str(info.value)


def test_output_read_holds_data_or_a_failed_receipt_and_hides_data() -> None:
    # §9.1 / INV-3: data is parsed vendor JSON, so repr leaves it out.
    records = _records()
    enums = importlib.import_module("vidbyte.lib.enums.outputs")
    failed = records.DeliveryReceipt(enums.OutputDestination.GITHUB_ISSUE, enums.DeliveryStatus.FAILED, error_code="http_404")

    assert records.OutputRead(failure=failed).data is None
    assert SECRET_MARKER not in repr(records.OutputRead(data={"token": "S3CRETread"}))


@pytest.mark.parametrize(
    ("options", "field"),
    [
        pytest.param({"failure": "sent"}, "failure", id="failure-not-a-receipt"),
        pytest.param({"failure": "SENT-RECEIPT"}, "failure", id="failure-sent-receipt"),
        pytest.param({"failure": "FAILED-RECEIPT", "data": [{"id": 1}]}, "data", id="data-with-failure"),
    ],
)
def test_output_read_refuses_an_inconsistent_record_naming_the_field(options, field) -> None:
    # §9.1: failure is None or a FAILED receipt, and data is None when failure is set.
    records = _records()
    enums = importlib.import_module("vidbyte.lib.enums.outputs")
    receipts = {
        "SENT-RECEIPT": records.DeliveryReceipt(enums.OutputDestination.GITHUB_ISSUE, enums.DeliveryStatus.SENT),
        "FAILED-RECEIPT": records.DeliveryReceipt(enums.OutputDestination.GITHUB_ISSUE, enums.DeliveryStatus.FAILED, error_code="network"),
    }
    resolved = {name: receipts.get(value, value) if isinstance(value, str) else value for name, value in options.items()}

    with pytest.raises(ConfigurationError) as info:
        records.OutputRead(**resolved)

    assert re.search(rf"\b{field}\b", str(info.value)), str(info.value)
