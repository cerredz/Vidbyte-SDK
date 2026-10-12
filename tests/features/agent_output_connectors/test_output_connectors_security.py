"""FILE: tests/features/agent_output_connectors/test_output_connectors_security.py

PURPOSE: Prove credentials stay where they belong and model output cannot steer delivery: no credential appears in any rendered surface even when the destination echoes it back, each credential travels only in its own destination's request, no credential-bearing URL reaches httpx's request log, the model's structured output cannot change a URL, repo, or recipient, and path-shaped repo or site values are rejected before they build a URL.
ROLE IN CODEBASE: Security tests across BaseOutput.__repr__, the vidbyte.lib.dataclasses.outputs records, OutputHttp.post error mapping and its httpx log guard, OutputDeliveryError, JevAgentSettings, BaseAgent.export_state, and the connectors' URL construction.
ARCHITECTURE NOTE: Every placeholder credential contains SECRET_MARKER, so one substring scan covers every surface; Jira's Basic header and Telegram's path token are scanned in their wire form too. The log test keeps the real _send_once over httpx.MockTransport (httpx_destination), because httpx writes its request log below _send_once.
FUNCTION INVENTORY: test_no_surface_shows_the_credential_* (AC-3, INV-4, NFR-4); test_records_mask_* (INV-4, §9.1); test_each_credential_travels_only_* (INV-4, T-4); test_url_credential_never_reaches_the_httpx_request_log_* (INV-4, EC-41, T-1, S4 R-1); test_model_output_cannot_* (INV-3, T-2); test_path_shaped_* (D-19).
COMMON MODIFICATION PATTERNS: When a new surface can hold a reply or connector (a trace, a checkpoint), add it to the scanned surfaces in test_no_surface_shows_the_credential_*.
WHAT NOT TO DO IN THIS FILE: 1. Do not use a credential without SECRET_MARKER. 2. Do not weaken a scan to a single surface; a leak is usually in the one nobody checked.
KNOWN EDGE CASES: The failing destination echoes the credential in its error body or SMTP reply on purpose. export_state serializes history, so a leaked receipt or metadata value would show there.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§6.1 INV-3, INV-4; §6.2 AC-3; §10 T-1 to T-5; D-19)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_security.py
"""

from __future__ import annotations

import json
import logging
import smtplib

import httpx
import pytest
from pydantic import BaseModel

from tests.agent_test_support import build_test_agent
from tests.features.agent_output_connectors.factories import (
    CONNECTOR_CASES,
    GITHUB_TOKEN,
    HTTP_DESTINATION_KEYS,
    JIRA_TOKEN,
    SECRET_MARKER,
    SLACK_URL,
    SMTP_PASSWORD,
    WEBHOOK_URL,
    AnswerRunner,
    build_reply,
    receipt_rows,
)
from vidbyte.agents.jev import JevAgentSettings
from vidbyte.lib.errors import ConfigurationError


def _forbidden_fragments(case) -> set[str]:
    # The marker, plus the credential in its wire form (Jira's base64 Basic value carries no marker).
    return {SECRET_MARKER, case.credential, case.wire_secret.removeprefix("Basic ").removeprefix("Bearer ")}


def _arrange_echoing_failure(case, fake_http, fake_smtp) -> None:
    # The destination answers with an error that repeats the credential back.
    if case.key == "email":
        fake_smtp.fail("login", smtplib.SMTPAuthenticationError(535, f"5.7.8 bad password {SMTP_PASSWORD}".encode()))
    else:
        fake_http.answer(case.host, (500, f"internal error for {case.credential}"))


def test_no_surface_shows_the_credential_even_when_the_destination_echoes_it(output_api, fake_http, fake_smtp, any_case) -> None:
    # AC-3 / INV-4 / NFR-4 / T-1 / T-5: repr, str, receipts, the error, metadata, settings, and exported state stay clean.
    _arrange_echoing_failure(any_case, fake_http, fake_smtp)
    connector = any_case.build(output_api)
    agent = build_test_agent(name="nightly", system_prompt="Summarize the nightly scan.", runner=AnswerRunner("Nightly scan: no regressions."), outputs=[connector])
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini", outputs=[connector])

    with pytest.raises(output_api.OutputDeliveryError) as info:
        agent.run("Run the nightly scan")

    err = info.value
    assert [receipt.status.value for receipt in err.receipts] == ["failed"]
    surfaces = {
        "repr(connector)": repr(connector),
        "str(connector)": str(connector),
        "repr(agent.outputs)": repr(agent.outputs),
        "str(agent.outputs)": str(agent.outputs),
        "repr(settings)": repr(settings),
        "repr(receipts)": repr(err.receipts),
        "str(err)": str(err),
        "repr(err)": repr(err),
        "repr(err.details)": repr(err.details),
        "repr(reply.metadata)": repr(err.reply.metadata),
        "repr(export_state)": repr(agent.export_state()),
    }
    leaks = {name: fragment for name, text in surfaces.items() for fragment in _forbidden_fragments(any_case) if fragment in text}
    assert leaks == {}
    assert repr(connector) == f"{any_case.class_name}(credential='***')"


def test_records_mask_their_secret_fields_in_repr() -> None:
    # INV-4 / §9.1: OutputRequest hides url, headers, and body; SmtpSettings hides the password.
    from vidbyte.lib.dataclasses.outputs import OutputRequest, SmtpSettings

    request = OutputRequest(url=SLACK_URL, headers={"authorization": f"Bearer {GITHUB_TOKEN}"}, json_body={"token": JIRA_TOKEN})
    settings = SmtpSettings(host="smtp.gmail.com", port=587, username="bot@acme.com", password=SMTP_PASSWORD, sender="bot@acme.com", recipients=("ops@acme.com",))

    for text in (repr(request), str(request), repr(settings), str(settings)):
        assert SECRET_MARKER not in text
    assert repr(request).startswith("OutputRequest(")
    assert "smtp.gmail.com" in repr(settings)


def test_each_credential_travels_only_in_its_own_destinations_request(output_api, fake_http) -> None:
    # INV-4 / T-4: ten connectors on one agent; no request carries another destination's secret.
    for key in HTTP_DESTINATION_KEYS:
        fake_http.answer(CONNECTOR_CASES[key].host, CONNECTOR_CASES[key].success)
    outputs = [CONNECTOR_CASES[key].build(output_api) for key in HTTP_DESTINATION_KEYS]
    agent = build_test_agent(name="nightly", system_prompt="Summarize the nightly scan.", runner=AnswerRunner("Nightly scan: no regressions."), outputs=outputs)

    agent.run("Run the nightly scan")

    assert len(fake_http.sends) == len(HTTP_DESTINATION_KEYS)
    for key in HTTP_DESTINATION_KEYS:
        [send] = fake_http.sends_to(CONNECTOR_CASES[key].host)
        wire = json.dumps([send["url"], send["headers"], send["json_body"]])
        assert CONNECTOR_CASES[key].wire_secret in send["url"] or CONNECTOR_CASES[key].wire_secret in send["headers"].values()
        others = [other for other in HTTP_DESTINATION_KEYS if other != key and CONNECTOR_CASES[other].credential in wire]
        assert others == [], f"{key} request carries the credential of {others}"


# The six destinations whose request URL carries the credential (Telegram's in its path), with the exact host each posts to.
URL_CREDENTIAL_HOSTS = [
    pytest.param("slack", "hooks.slack.com", id="slack"),
    pytest.param("discord", "discord.com", id="discord"),
    pytest.param("teams", "default000.environment.api.powerplatform.com", id="teams"),
    pytest.param("google_chat", "chat.googleapis.com", id="google-chat"),
    pytest.param("telegram", "api.telegram.org", id="telegram"),
    pytest.param("webhook", "hook.eu1.make.com", id="webhook"),
]
OWN_REQUEST_URL = "https://api.example.com/v1/reports"


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "host"), URL_CREDENTIAL_HOSTS)
async def test_url_credential_never_reaches_the_httpx_request_log_while_the_callers_own_requests_still_do(output_api, httpx_destination, caplog, key, host) -> None:
    # INV-4 / EC-41 / T-1 / S4 R-1: httpx logs "HTTP Request: POST <url>" at INFO, and for these destinations the URL is the secret.
    # The real _send_once runs over MockTransport, because a scripted _send_once never reaches httpx's own log call.
    # INFO is set on the root logger, as a caller would, not on "httpx", so a guard that raises httpx's own level is caught too.
    caplog.set_level(logging.INFO)
    case = CONNECTOR_CASES[key]
    status, body = case.success
    httpx_destination.routes[host] = httpx.Response(status, text=body)
    httpx_destination.routes["api.example.com"] = httpx.Response(200, json={"ok": True})

    receipt = await case.build(output_api).send(build_reply("Nightly scan: no regressions."), output_api.OutputContent("Nightly scan", "No regressions."))
    # The caller's own httpx request, made after the send and outside it, must still be logged: the guard is scoped, not a global mute.
    async with httpx.AsyncClient() as client:
        await client.post(OWN_REQUEST_URL, json={"report": "nightly"})

    assert receipt_rows([receipt]) == [(key, "sent", None, None)]
    assert [request.url.host for request in httpx_destination] == [host, "api.example.com"]
    messages = [record.getMessage() for record in caplog.records]
    assert [message for message in messages if SECRET_MARKER in message] == []
    assert any(message.startswith(f"HTTP Request: POST {OWN_REQUEST_URL}") for message in messages), messages


class _SteeringReport(BaseModel):
    title: str
    body: str
    url: str
    repo: str
    webhook_url: str
    to: str


def test_model_output_cannot_change_where_a_reply_goes(output_api, fake_http, fake_smtp) -> None:
    # INV-3 / T-2: destinations come only from constructor arguments, never from fields the model fills in.
    fake_http.answer("hook.eu1.make.com", (200, "Accepted"))
    fake_http.answer("api.github.com", CONNECTOR_CASES["github_issue"].success)
    steering = {"title": "Checkout bug", "body": "SAVE10 is ignored.", "url": "https://evil.example.net/collect", "repo": "evil/loot", "webhook_url": "https://evil.example.net/hook", "to": "thief@evil.example.net"}
    outputs = [output_api.WebhookOutput(url=WEBHOOK_URL), CONNECTOR_CASES["github_issue"].build(output_api), CONNECTOR_CASES["email"].build(output_api)]
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=AnswerRunner(json.dumps(steering)), output_schema=_SteeringReport, outputs=outputs)

    agent.run("Scan checkout")

    assert sorted(send["url"] for send in fake_http.sends) == sorted([WEBHOOK_URL, "https://api.github.com/repos/acme/shop/issues"])
    [session] = fake_smtp.sessions
    assert (session.host, session.message["To"]) == ("smtp.gmail.com", "ops@acme.com")
    assert all("evil.example.net" not in json.dumps([send["url"], send["headers"]]) for send in fake_http.sends)


@pytest.mark.parametrize(
    ("class_name", "arguments", "parameter"),
    [
        pytest.param("GitHubIssueOutput", {"repo": "acme/shop/../../orgs/acme"}, "repo", id="repo-path-traversal"),
        pytest.param("GitHubIssueOutput", {"repo": "acme/shop?per_page=1"}, "repo", id="repo-query"),
        pytest.param("GitHubIssueOutput", {"repo": "acme/shop#x"}, "repo", id="repo-fragment"),
        pytest.param("GitHubIssueOutput", {"repo": "acme /shop"}, "repo", id="repo-space"),
        pytest.param("GitHubIssueOutput", {"repo": "acme/shop\n"}, "repo", id="repo-newline"),
        pytest.param("JiraIssueOutput", {"site": "acme.atlassian.net/evil"}, "site", id="site-path"),
        pytest.param("JiraIssueOutput", {"site": "acme.atlassian.net:8443"}, "site", id="site-port"),
        pytest.param("JiraIssueOutput", {"site": "acme.atlassian.net.evil.example.net"}, "site", id="site-suffix-attack"),
        pytest.param("JiraIssueOutput", {"site": "evil.example.net#.atlassian.net"}, "site", id="site-fragment-attack"),
        pytest.param("JiraIssueOutput", {"site": "bot@acme.atlassian.net"}, "site", id="site-userinfo"),
        pytest.param("JiraIssueOutput", {"site": ".atlassian.net"}, "site", id="site-empty-tenant"),
    ],
)
def test_path_shaped_repo_or_site_is_rejected_before_it_can_build_a_credentialed_url(output_api, class_name, arguments, parameter) -> None:
    # D-19 / INV-21: Jira takes Basic credentials and GitHub a token, so a crafted repo or site must not redirect them.
    base = {"GitHubIssueOutput": {"token": GITHUB_TOKEN}, "JiraIssueOutput": {"project": "PROJ", "email": "bot@acme.com", "api_token": JIRA_TOKEN}}[class_name]

    with pytest.raises(ConfigurationError) as info:
        getattr(output_api, class_name)(**{**base, **arguments})

    assert parameter in str(info.value)
    assert SECRET_MARKER not in str(info.value)
