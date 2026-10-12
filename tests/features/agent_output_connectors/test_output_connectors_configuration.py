"""FILE: tests/features/agent_output_connectors/test_output_connectors_configuration.py

PURPOSE: Prove configuration fails at construction, before any model call, with a ConfigurationError that names the offending parameter and never a credential; and that each credential resolves once, explicit argument first, then its environment variable, stripped, else the documented missing-credential message.
ROLE IN CODEBASE: Boundary tests of OutputArguments (through the eleven connector constructors), the vidbyte.lib.dataclasses.outputs records they build, and OutputDispatcher.connectors (through BaseAgent(outputs=)).
ARCHITECTURE NOTE: Every connector is built through the public constructor with placeholder credentials; credentials in the environment come from monkeypatch.setenv after the autouse fixture has removed any real value.
FUNCTION INVENTORY: test_invalid_connector_argument_* (AC-20, INV-21, EC-13); test_invalid_outputs_value_* (AC-20, EC-14, EC-15); test_two_connectors_for_the_same_destination_* (EC-15); test_slack_credential_* (AC-2, INV-5, EC-11, EC-12); test_every_connector_reads_its_own_environment_variable_* (§9.3, FR-7); test_every_connector_without_a_credential_* (INV-5, EC-11); test_explicit_credential_is_stripped_*; test_credential_rotated_* (EC-37).
COMMON MODIFICATION PATTERNS: Add an invalid argument as one INVALID_ARGUMENTS row naming the parameter the message must contain.
WHAT NOT TO DO IN THIS FILE: 1. Do not read a real environment variable; the autouse fixture clears all eleven. 2. Do not assert a full message except the documented missing-credential one.
KNOWN EDGE CASES: A blank explicit argument falls through to the environment variable. A whitespace-only variable counts as missing. Two different instances for the same destination are allowed; the same instance twice is not.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§6.1 INV-5, INV-21; §6.2 AC-2, AC-20; §9.3)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_configuration.py
"""

from __future__ import annotations

import re

import pytest

from tests.agent_test_support import build_test_agent
from tests.features.agent_output_connectors.factories import (
    ALL_DESTINATION_KEYS,
    CONNECTOR_CASES,
    GITHUB_TOKEN,
    HTTP_DESTINATION_KEYS,
    JIRA_TOKEN,
    LINEAR_KEY,
    LINEAR_TEAM_ID,
    NOTION_KEY,
    NOTION_PARENT_PAGE_ID,
    SECRET_MARKER,
    SLACK_URL,
    SMTP_PASSWORD,
    TELEGRAM_TOKEN,
    AnswerRunner,
    build_reply,
)
from vidbyte.lib.errors import ConfigurationError

SLACK_ENV_PADDED = " https://hooks.slack.com/services/T/B/X\n"
SLACK_ENV_URL = "https://hooks.slack.com/services/T/B/X"
OTHER_SLACK_URL = "https://hooks.slack.com/services/T000/B222/S3CRETsecond"
EMAIL_BASE = {"to": "ops@acme.com", "host": "smtp.gmail.com", "username": "bot@acme.com", "password": SMTP_PASSWORD}
JIRA_BASE = {"site": "acme.atlassian.net", "project": "PROJ", "email": "bot@acme.com", "api_token": JIRA_TOKEN}

# (connector class, constructor arguments, the parameter the message must name)
INVALID_ARGUMENTS = [
    pytest.param("SlackOutput", {"webhook_url": "http://hooks.slack.com/services/T000/B000/S3CRETplain"}, "webhook_url", id="slack-http-scheme"),
    pytest.param("SlackOutput", {"webhook_url": "hooks.slack.com/services/T000/B000/S3CRETnoscheme"}, "webhook_url", id="slack-no-scheme"),
    pytest.param("SlackOutput", {"webhook_url": "https://"}, "webhook_url", id="slack-no-host"),
    pytest.param("DiscordOutput", {"webhook_url": "ftp://discord.com/api/webhooks/000/S3CRETdiscord"}, "webhook_url", id="discord-ftp-scheme"),
    pytest.param("TeamsOutput", {"webhook_url": "http://default000.environment.api.powerplatform.com/S3CRETteams"}, "webhook_url", id="teams-http-scheme"),
    pytest.param("GoogleChatOutput", {"webhook_url": "http://chat.googleapis.com/v1/spaces/AAAA/messages?key=S3CRETkey"}, "webhook_url", id="google-chat-http-scheme"),
    pytest.param("WebhookOutput", {"url": "http://hook.eu1.make.com/S3CRETwebhook"}, "url", id="webhook-http-scheme"),
    pytest.param("WebhookOutput", {"url": "https:///S3CRETpath-only"}, "url", id="webhook-no-host"),
    pytest.param("GitHubIssueOutput", {"repo": "acme", "token": GITHUB_TOKEN}, "repo", id="github-repo-without-name"),
    pytest.param("GitHubIssueOutput", {"repo": "acme/", "token": GITHUB_TOKEN}, "repo", id="github-repo-blank-name"),
    pytest.param("GitHubIssueOutput", {"repo": "acme/shop", "labels": "bug", "token": GITHUB_TOKEN}, "labels", id="github-labels-bare-string"),
    pytest.param("LinearIssueOutput", {"team_id": "ENG", "api_key": LINEAR_KEY}, "team_id", id="linear-team-key-not-uuid"),
    pytest.param("NotionPageOutput", {"parent_page_id": "x", "api_key": NOTION_KEY}, "parent_page_id", id="notion-page-not-uuid"),
    pytest.param("JiraIssueOutput", {**JIRA_BASE, "site": "https://acme.atlassian.net"}, "site", id="jira-site-with-scheme"),
    pytest.param("JiraIssueOutput", {**JIRA_BASE, "site": "acme.example.com"}, "site", id="jira-site-not-atlassian"),
    pytest.param("JiraIssueOutput", {**JIRA_BASE, "email": "jira-bot"}, "email", id="jira-email-not-address"),
    pytest.param("JiraIssueOutput", {**JIRA_BASE, "project": "   "}, "project", id="jira-blank-project"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "to": "not-an-address"}, "to", id="email-to-not-address"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "to": "ops@acme.com, cfo@acme.com"}, "to", id="email-to-comma-list-in-one-string"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "to": ("ops@acme.com", "ops team@acme.com")}, "to", id="email-to-item-with-space"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "sender": "Alerts <alerts@acme.com>"}, "sender", id="email-sender-display-name"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "port": 0}, "port", id="email-port-zero"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "port": 65_536}, "port", id="email-port-too-high"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "port": True}, "port", id="email-port-bool"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "port": "587"}, "port", id="email-port-string"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "host": "   "}, "host", id="email-blank-host"),
    pytest.param("TelegramOutput", {"chat_id": True, "bot_token": TELEGRAM_TOKEN}, "chat_id", id="telegram-chat-id-bool"),
    pytest.param("TelegramOutput", {"chat_id": "   ", "bot_token": TELEGRAM_TOKEN}, "chat_id", id="telegram-chat-id-blank"),
    pytest.param("SlackOutput", {"webhook_url": SLACK_URL, "render": 1}, "render", id="slack-render-not-callable"),
    pytest.param("EmailOutput", {**EMAIL_BASE, "render": "subject"}, "render", id="email-render-not-callable"),
]


@pytest.mark.parametrize(("class_name", "arguments", "parameter"), INVALID_ARGUMENTS)
def test_invalid_connector_argument_is_rejected_at_construction_naming_the_parameter_and_no_secret(output_api, class_name, arguments, parameter) -> None:
    # AC-20 / INV-21 / EC-13 / T-1: the user learns which argument is wrong without the secret being printed.
    with pytest.raises(ConfigurationError) as info:
        getattr(output_api, class_name)(**arguments)

    message = str(info.value)
    assert re.search(rf"\b{re.escape(parameter)}\b", message), message
    assert SECRET_MARKER not in message
    assert SECRET_MARKER not in repr(info.value.details)


def _invalid_outputs(output_api) -> dict[str, object]:
    slack = output_api.SlackOutput(webhook_url=SLACK_URL)
    return {
        "bare-string": "slack",
        "bare-bytes": b"slack",
        "single-connector": slack,
        "connector-class": [output_api.SlackOutput],
        "plain-object": [object()],
        "mapping": {"slack": slack},
        "not-iterable": 7,
        "same-instance-twice": [slack, slack],
    }


@pytest.mark.parametrize("case", ["bare-string", "bare-bytes", "single-connector", "connector-class", "plain-object", "mapping", "not-iterable", "same-instance-twice"])
def test_invalid_outputs_value_is_rejected_when_the_agent_is_built(output_api, case) -> None:
    # AC-20 / INV-21 / EC-14 / EC-15: the alternative is iterating characters, a deep TypeError, or posting every reply twice.
    runner = AnswerRunner("unused")

    with pytest.raises(ConfigurationError) as info:
        build_test_agent(name="scout", system_prompt="Investigate.", runner=runner, outputs=_invalid_outputs(output_api)[case])

    assert re.search(r"\boutputs\b", str(info.value)), str(info.value)
    assert SECRET_MARKER not in str(info.value)
    assert runner.calls == 0


def test_two_connectors_for_the_same_destination_are_allowed_and_each_gets_its_own_request(output_api, fake_http) -> None:
    # EC-15: two Slack channels are two instances; a list normalizes to a tuple.
    fake_http.answer("hooks.slack.com", (200, "ok"), (200, "ok"))
    first, second = output_api.SlackOutput(webhook_url=SLACK_URL), output_api.SlackOutput(webhook_url=OTHER_SLACK_URL)
    agent = build_test_agent(name="scout", system_prompt="Investigate.", runner=AnswerRunner("Nightly scan: no regressions."), outputs=[first, second])

    agent.run("Run the nightly scan")

    assert agent.outputs == (first, second)
    assert sorted(send["url"] for send in fake_http.sends) == sorted([SLACK_URL, OTHER_SLACK_URL])


async def _slack_url_used(output_api, fake_http, connector) -> str:
    fake_http.answer("hooks.slack.com", (200, "ok"))
    await connector.send(build_reply("Nightly scan: no regressions."), output_api.OutputContent("Nightly scan", "No regressions."))
    return fake_http.sends[-1]["url"]


@pytest.mark.asyncio
async def test_slack_credential_from_the_environment_is_stripped(output_api, fake_http, monkeypatch) -> None:
    # AC-2 / EC-12: a pasted value with a trailing newline still works.
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SLACK_ENV_PADDED)

    assert await _slack_url_used(output_api, fake_http, output_api.SlackOutput()) == SLACK_ENV_URL


@pytest.mark.asyncio
@pytest.mark.parametrize(("explicit", "expected"), [(SLACK_URL, SLACK_URL), (f"  {SLACK_URL}\n", SLACK_URL), ("   ", SLACK_ENV_URL), (None, SLACK_ENV_URL)], ids=["explicit-wins", "explicit-stripped", "blank-explicit-falls-back", "no-explicit"])
async def test_slack_credential_prefers_a_non_blank_explicit_argument_over_the_environment(output_api, fake_http, monkeypatch, explicit, expected) -> None:
    # AC-2 / INV-5 steps 1-2: explicit first when non-blank after strip, then the variable.
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SLACK_ENV_PADDED)

    assert await _slack_url_used(output_api, fake_http, output_api.SlackOutput(webhook_url=explicit)) == expected


@pytest.mark.parametrize("environment", [None, "  \n"], ids=["unset", "whitespace-only"])
def test_slack_credential_missing_everywhere_raises_the_documented_message(output_api, monkeypatch, environment) -> None:
    # AC-2 / EC-11 / INV-5 step 3: the message names the parameter and the variable and nothing else of the user's.
    if environment is not None:
        monkeypatch.setenv("SLACK_WEBHOOK_URL", environment)

    with pytest.raises(ConfigurationError) as info:
        output_api.SlackOutput()

    assert str(info.value) == "Missing credential for slack output. Pass webhook_url or set SLACK_WEBHOOK_URL."


@pytest.mark.asyncio
@pytest.mark.parametrize("key", HTTP_DESTINATION_KEYS)
async def test_every_connector_reads_its_own_environment_variable_and_strips_it(output_api, fake_http, monkeypatch, key) -> None:
    # §9.3 / FR-7 / INV-5: each connector works with one variable set and no credential argument.
    case = CONNECTOR_CASES[key]
    monkeypatch.setenv(case.env_var, f"  {case.credential}\n")
    fake_http.answer(case.host, case.success)
    connector = case.build_without_credential(output_api)

    receipt = await connector.send(build_reply("Nightly scan: no regressions."), output_api.OutputContent("Nightly scan", "No regressions."))

    [send] = fake_http.sends
    assert case.wire_secret in send["url"] or case.wire_secret in send["headers"].values()
    assert receipt.status.value == "sent"


@pytest.mark.parametrize("key", ALL_DESTINATION_KEYS)
@pytest.mark.parametrize("environment", [None, " \t "], ids=["unset", "whitespace-only"])
def test_every_connector_without_a_credential_names_its_parameter_and_variable(output_api, monkeypatch, key, environment) -> None:
    # INV-5 step 3 / EC-11 / §12.3 row 5: one message format for every destination.
    case = CONNECTOR_CASES[key]
    if environment is not None:
        monkeypatch.setenv(case.env_var, environment)

    with pytest.raises(ConfigurationError) as info:
        case.build_without_credential(output_api)

    assert str(info.value) == f"Missing credential for {key} output. Pass {case.parameter} or set {case.env_var}."


@pytest.mark.asyncio
async def test_explicit_credential_is_stripped_before_it_reaches_a_header(output_api, fake_http) -> None:
    # INV-5 step 1: a pasted token with a trailing newline must not become an invalid Authorization header.
    fake_http.answer("api.github.com", CONNECTOR_CASES["github_issue"].success)
    connector = output_api.GitHubIssueOutput(repo="acme/shop", token=f"  {GITHUB_TOKEN}\n")

    await connector.send(build_reply("Checkout total ignores coupons."), output_api.OutputContent("Checkout bug", "Checkout total ignores coupons."))

    assert fake_http.sends[0]["headers"]["authorization"] == f"Bearer {GITHUB_TOKEN}"


@pytest.mark.asyncio
async def test_credential_rotated_in_the_environment_after_construction_is_not_picked_up(output_api, fake_http, monkeypatch) -> None:
    # EC-37: resolution happens once, in the constructor; a new connector sees the new value.
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SLACK_URL)
    built_before = output_api.SlackOutput()
    monkeypatch.setenv("SLACK_WEBHOOK_URL", OTHER_SLACK_URL)

    assert await _slack_url_used(output_api, fake_http, built_before) == SLACK_URL
    assert await _slack_url_used(output_api, fake_http, output_api.SlackOutput()) == OTHER_SLACK_URL


def test_identifiers_accept_dashed_and_compact_uuids(output_api) -> None:
    # §8.5 OutputArguments.identifier: Linear and Notion copy ids in either form.
    linear = output_api.LinearIssueOutput(team_id=LINEAR_TEAM_ID.upper(), api_key=LINEAR_KEY)
    notion = output_api.NotionPageOutput(parent_page_id=NOTION_PARENT_PAGE_ID.replace("-", ""), api_key=NOTION_KEY)

    assert (linear.destination.value, notion.destination.value) == ("linear_issue", "notion_page")
