"""FILE: tests/features/opencode_host/test_opencode_host_records.py

PURPOSE: The opencode request and settings records of spec §9.1: OpencodePromptRequest and OpencodeSpawnRequest (EC-66), OpencodePermissionRule with the refused allow-everything rule (AC-19, INV-9), OpencodeMcpServerConfig (EC-91), and OpencodeHostSettings with its URL, credential, exclusivity, backend, MCP, timeout and live-turn rules (EC-152).
ROLE IN CODEBASE: Start here when a bad opencode value gets past a record, or a good one is refused. These are the INV-5 boundary checks that run before any request is sent.
ARCHITECTURE NOTE: Each table row overrides one field of a known-good record, so a failure can only come from that field. Every rejection must be a ConfigurationError whose message names "<Record>.<field>" (spec §9.1 common rules). The fixture here imports only the record, enum, error and constant modules, so these tests can pass before the host exists.
FUNCTION INVENTORY: records_api imports the record modules; base_fields returns a known-good field set per record; expect_rejected asserts the ConfigurationError shape; the *_CASES tables hold the rows; the test_* functions run them.
COMMON MODIFICATION PATTERNS: Add a row to the matching table when spec §9.1 adds a check; keep one bad value per row.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert that a message quotes a value; the spec only says when it may not. 2. Do not put a credential-shaped literal in a row; secret values are generated per test.
KNOWN EDGE CASES: The credential-pairing and command-versus-URL rules involve two fields, so those rows accept a message naming either field. The allow-everything rule spans all three rule fields, so that row only requires the record name. A whitespace-only `system` is not tested, because EC-66 only bounds its length.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1, EC-66, EC-91, EC-152, AC-19, INV-9
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_records.py
"""

from __future__ import annotations

import importlib
import math
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

PROMPT = "List the top-level folders."
ATTACHED_URL = "http://127.0.0.1:4096"
LONG_TEXT = "x" * 200


@pytest.fixture
def records_api() -> SimpleNamespace:
    # Only the §9.1 record, enum, error and constant modules; the host is not needed here.
    records = importlib.import_module("vidbyte.lib.dataclasses.opencode")
    native_enums = importlib.import_module("vidbyte.lib.enums.native_hosts")
    return SimpleNamespace(
        OpencodeHostSettings=records.OpencodeHostSettings,
        OpencodePermissionRule=records.OpencodePermissionRule,
        OpencodePromptRequest=records.OpencodePromptRequest,
        OpencodeSpawnRequest=records.OpencodeSpawnRequest,
        OpencodeMcpServerConfig=records.OpencodeMcpServerConfig,
        OpencodePermissionAction=native_enums.OpencodePermissionAction,
        OpencodeMcpKind=native_enums.OpencodeMcpKind,
        HarnessBackendName=importlib.import_module("vidbyte.lib.enums.harness_backends").HarnessBackendName,
        ConfigurationError=importlib.import_module("vidbyte.lib.errors").ConfigurationError,
        constants=importlib.import_module("vidbyte.lib.constants.native_hosts"),
    )


def expect_rejected(api: SimpleNamespace, record_name: str, field_names: tuple[str, ...], build: Any) -> str:
    with pytest.raises(api.ConfigurationError) as caught:
        build()
    message = str(caught.value)
    assert any(f"{record_name}.{name}" in message for name in field_names), f"message must name {record_name}.{'/'.join(field_names)}: {message!r}"
    return message


def local_mcp(api: SimpleNamespace, **overrides: Any) -> Any:
    return api.OpencodeMcpServerConfig(**{"name": "files", "kind": api.OpencodeMcpKind.LOCAL, "command": ("node", "files-server.js"), **overrides})


def remote_mcp(api: SimpleNamespace, **overrides: Any) -> Any:
    return api.OpencodeMcpServerConfig(**{"name": "docs", "kind": api.OpencodeMcpKind.REMOTE, "url": "https://mcp.invalid/docs", **overrides})


def attached_settings(api: SimpleNamespace, workspace: Path, **overrides: Any) -> Any:
    fields = {"workspace": workspace, "server_url": ATTACHED_URL, "server_username": "opencode", "server_password": "pw-" + uuid.uuid4().hex}
    return api.OpencodeHostSettings(**{**fields, **overrides})


def test_record_defaults_match_the_spec(records_api, tmp_path) -> None:
    # §9.1 defaults, read from §9.3 constants: 1800 s turns, 20 s startup, 30 s requests, 4 live turns.
    prompt = records_api.OpencodePromptRequest(prompt=PROMPT)
    assert (prompt.model, prompt.agent, prompt.system, prompt.max_turn_seconds) == (None, None, None, 1800.0)
    spawn = records_api.OpencodeSpawnRequest(turn=prompt)
    assert (spawn.title, spawn.permission_rules) == (None, ())
    settings = records_api.OpencodeHostSettings(workspace=tmp_path)
    assert (settings.opencode_command, settings.server_url, settings.server_username, settings.server_password) == (None, None, None, None)
    assert (settings.backends, dict(settings.mcp_servers), settings.max_live_turns) == ((), {}, 4)
    assert (settings.startup_timeout_seconds, settings.request_timeout_seconds) == (20.0, 30.0)
    config = local_mcp(records_api)
    assert (dict(config.environment), config.url, dict(config.headers), config.timeout_ms) == ({}, None, {}, None)


PROMPT_CASES = [
    pytest.param("prompt", "", id="prompt-empty"),
    pytest.param("prompt", "   ", id="prompt-blank"),
    pytest.param("prompt", "p" * 200001, id="prompt-over-cap"),
    pytest.param("prompt", 7, id="prompt-type"),
    pytest.param("model", "", id="model-empty"),
    pytest.param("model", "coder-1", id="model-no-provider"),
    pytest.param("model", "/coder-1", id="model-empty-provider"),
    pytest.param("model", "acme/", id="model-empty-model"),
    pytest.param("model", "-acme/coder-1", id="model-leading-dash"),
    pytest.param("model", "acme/coder 1", id="model-whitespace"),
    pytest.param("model", "a" * 129 + "/coder-1", id="model-provider-over-128"),
    pytest.param("model", "acme/" + "m" * 129, id="model-id-over-128"),
    pytest.param("agent", "", id="agent-empty"),
    pytest.param("agent", "a" * 129, id="agent-over-128"),
    pytest.param("agent", "-plan", id="agent-leading-dash"),
    pytest.param("agent", "my agent", id="agent-whitespace"),
    pytest.param("system", "s" * 20001, id="system-over-cap"),
    pytest.param("max_turn_seconds", True, id="seconds-bool"),
    pytest.param("max_turn_seconds", math.nan, id="seconds-nan"),
    pytest.param("max_turn_seconds", math.inf, id="seconds-inf"),
    pytest.param("max_turn_seconds", 0, id="seconds-zero"),
    pytest.param("max_turn_seconds", -1.0, id="seconds-negative"),
    pytest.param("max_turn_seconds", 14400.5, id="seconds-over-max"),
    pytest.param("max_turn_seconds", "60", id="seconds-string"),
]


@pytest.mark.parametrize(("field_name", "value"), PROMPT_CASES)
def test_prompt_request_rejects_a_bad_field(field_name: str, value: Any, records_api) -> None:
    # EC-66 / INV-5: OpencodePromptRequest validates every field at construction.
    expect_rejected(records_api, "OpencodePromptRequest", (field_name,), lambda: records_api.OpencodePromptRequest(**{"prompt": PROMPT, field_name: value}))


def test_prompt_request_accepts_values_at_the_limits(records_api) -> None:
    # EC-66 bounds are inclusive; a model id may itself contain slashes after the provider.
    request = records_api.OpencodePromptRequest(prompt="p" * 200000, model="openrouter/vendor/coder-x", agent="a" * 128, system="s" * 20000, max_turn_seconds=14400)
    assert request.model == "openrouter/vendor/coder-x"
    assert records_api.OpencodePromptRequest(prompt=PROMPT, model="a" * 128 + "/" + "m" * 128).max_turn_seconds == 1800.0


def test_spawn_request_rejects_a_bad_field(records_api) -> None:
    # EC-66: instance check on turn, title text <= 128, at most OPENCODE_MAX_PERMISSION_RULES (64) rules.
    turn = records_api.OpencodePromptRequest(prompt=PROMPT)
    rule = records_api.OpencodePermissionRule(permission="bash", pattern="*", action=records_api.OpencodePermissionAction.ASK)
    expect_rejected(records_api, "OpencodeSpawnRequest", ("turn",), lambda: records_api.OpencodeSpawnRequest(turn=PROMPT))
    expect_rejected(records_api, "OpencodeSpawnRequest", ("turn",), lambda: records_api.OpencodeSpawnRequest(turn=None))
    expect_rejected(records_api, "OpencodeSpawnRequest", ("title",), lambda: records_api.OpencodeSpawnRequest(turn=turn, title=""))
    expect_rejected(records_api, "OpencodeSpawnRequest", ("title",), lambda: records_api.OpencodeSpawnRequest(turn=turn, title="t" * 129))
    expect_rejected(records_api, "OpencodeSpawnRequest", ("permission_rules",), lambda: records_api.OpencodeSpawnRequest(turn=turn, permission_rules=(rule,) * 65))
    expect_rejected(records_api, "OpencodeSpawnRequest", ("permission_rules",), lambda: records_api.OpencodeSpawnRequest(turn=turn, permission_rules=("bash:*:ask",)))
    accepted = records_api.OpencodeSpawnRequest(turn=turn, title="t" * 128, permission_rules=(rule,) * 64)
    assert len(accepted.permission_rules) == 64


RULE_CASES = [
    pytest.param("permission", "", id="permission-empty"),
    pytest.param("permission", "p" * 201, id="permission-over-200"),
    pytest.param("pattern", "", id="pattern-empty"),
    pytest.param("pattern", "p" * 201, id="pattern-over-200"),
    pytest.param("action", "allow", id="action-plain-string"),
    pytest.param("action", None, id="action-none"),
]


@pytest.mark.parametrize(("field_name", "value"), RULE_CASES)
def test_permission_rule_rejects_a_bad_field(field_name: str, value: Any, records_api) -> None:
    # EC-66: texts 1..OPENCODE_RULE_MAX_CHARS (200); action is an OpencodePermissionAction member.
    fields = {"permission": "bash", "pattern": "*", "action": records_api.OpencodePermissionAction.ASK, field_name: value}
    expect_rejected(records_api, "OpencodePermissionRule", (field_name,), lambda: records_api.OpencodePermissionRule(**fields))


def test_the_allow_everything_rule_is_refused(records_api) -> None:
    # AC-19 / INV-9: permission "*", pattern "*" and action ALLOW raises ConfigurationError at construction.
    with pytest.raises(records_api.ConfigurationError) as caught:
        records_api.OpencodePermissionRule(permission="*", pattern="*", action=records_api.OpencodePermissionAction.ALLOW)
    assert "OpencodePermissionRule" in str(caught.value)


def test_narrower_or_non_allow_wildcard_rules_are_accepted(records_api) -> None:
    # INV-9 refuses only the one approve-everything combination.
    action = records_api.OpencodePermissionAction
    accepted = [
        records_api.OpencodePermissionRule(permission="*", pattern="*", action=action.DENY),
        records_api.OpencodePermissionRule(permission="*", pattern="*", action=action.ASK),
        records_api.OpencodePermissionRule(permission="bash", pattern="*", action=action.ALLOW),
        records_api.OpencodePermissionRule(permission="*", pattern="src/**", action=action.ALLOW),
        records_api.OpencodePermissionRule(permission="p" * 200, pattern="q" * 200, action=action.ALLOW),
    ]
    assert [rule.action for rule in accepted] == [action.DENY, action.ASK, action.ALLOW, action.ALLOW, action.ALLOW]


MCP_CASES = [
    pytest.param("local", "name", {"name": ""}, id="name-empty"),
    pytest.param("local", "name", {"name": "bad name"}, id="name-space"),
    pytest.param("local", "name", {"name": "files/x"}, id="name-slash"),
    pytest.param("local", "name", {"name": "n" * 65}, id="name-over-64"),
    pytest.param("local", "kind", {"kind": "local"}, id="kind-plain-string"),
    pytest.param("local", "command", {"command": ()}, id="local-without-command"),
    pytest.param("local", "url", {"url": "https://mcp.invalid/files"}, id="local-with-url"),
    pytest.param("local", "command", {"command": ("node", "")}, id="local-empty-argv-item"),
    pytest.param("local", "command", {"command": ("node", "files\x00.js")}, id="local-nul-argv-item"),
    pytest.param("remote", "url", {"url": None}, id="remote-without-url"),
    pytest.param("remote", "command", {"command": ("node", "docs.js")}, id="remote-with-command"),
    pytest.param("remote", "url", {"url": "ftp://mcp.invalid/docs"}, id="remote-ftp"),
    pytest.param("remote", "url", {"url": "http://mcp.invalid/docs"}, id="remote-plain-http-non-loopback"),
    pytest.param("local", "environment", {"environment": {"1BAD": "v"}}, id="env-key-digit-first"),
    pytest.param("local", "environment", {"environment": {"BAD KEY": "v"}}, id="env-key-space"),
    pytest.param("local", "environment", {"environment": {"K": 1}}, id="env-value-type"),
    pytest.param("local", "environment", {"environment": {f"K{index}": "v" for index in range(65)}}, id="env-over-64"),
    pytest.param("remote", "headers", {"headers": {"Bad Header": "v"}}, id="header-key-space"),
    pytest.param("remote", "headers", {"headers": {f"H{index}": "v" for index in range(65)}}, id="headers-over-64"),
    pytest.param("local", "timeout_ms", {"timeout_ms": 0}, id="timeout-zero"),
    pytest.param("local", "timeout_ms", {"timeout_ms": 600001}, id="timeout-over-max"),
    pytest.param("local", "timeout_ms", {"timeout_ms": True}, id="timeout-bool"),
    pytest.param("local", "timeout_ms", {"timeout_ms": 1.5}, id="timeout-float"),
]


@pytest.mark.parametrize(("kind", "field_name", "overrides"), MCP_CASES)
def test_mcp_config_rejects_a_bad_field(kind: str, field_name: str, overrides: dict[str, Any], records_api) -> None:
    # EC-91 / INV-5: name pattern, LOCAL/REMOTE shape, https or loopback http, key patterns, 1..600000 ms.
    build = local_mcp if kind == "local" else remote_mcp
    expect_rejected(records_api, "OpencodeMcpServerConfig", (field_name,), lambda: build(records_api, **overrides))


def test_mcp_config_accepts_values_at_the_limits(records_api) -> None:
    # EC-91 bounds are inclusive; plain http is allowed to a loopback host.
    environment = {f"K_{index}": "v" for index in range(64)}
    assert len(local_mcp(records_api, environment=environment, timeout_ms=600000).environment) == 64
    assert local_mcp(records_api, name="n" * 64, timeout_ms=1).timeout_ms == 1
    assert remote_mcp(records_api, url="http://127.0.0.1:9000/mcp", headers={"X-Api-Key": "v"}).url == "http://127.0.0.1:9000/mcp"
    assert remote_mcp(records_api, url="http://localhost:9000/mcp").kind is records_api.OpencodeMcpKind.REMOTE


def test_mcp_config_errors_never_quote_environment_or_header_values(records_api) -> None:
    # EC-91 / INV-6: the message names the field and never includes a value from environment or headers.
    secret = "mcp-" + uuid.uuid4().hex
    for overrides, field_name, build in (
        ({"environment": {"BAD KEY": secret}}, "environment", local_mcp),
        ({"environment": {f"K{index}": secret for index in range(65)}}, "environment", local_mcp),
        ({"headers": {"Bad Header": secret}}, "headers", remote_mcp),
        ({"headers": {"Authorization": secret}, "url": "http://mcp.invalid/docs"}, "url", remote_mcp),
    ):
        message = expect_rejected(records_api, "OpencodeMcpServerConfig", (field_name,), lambda build=build, overrides=overrides: build(records_api, **overrides))
        assert secret not in message


def settings_cases(api: SimpleNamespace, workspace: Path) -> list[tuple[str, tuple[str, ...], dict[str, Any]]]:
    file_path = workspace / "a-file.txt"
    file_path.write_text("x", encoding="utf-8")
    files = local_mcp(api)
    backend = api.HarnessBackendName
    return [
        ("workspace-relative", ("workspace",), {"workspace": Path("relative-dir")}),
        ("workspace-missing", ("workspace",), {"workspace": workspace / "missing"}),
        ("workspace-file", ("workspace",), {"workspace": file_path}),
        ("workspace-str", ("workspace",), {"workspace": str(workspace)}),
        ("command-empty", ("opencode_command",), {"server_url": None, "server_username": None, "server_password": None, "opencode_command": ()}),
        ("command-empty-item", ("opencode_command",), {"server_url": None, "server_username": None, "server_password": None, "opencode_command": ("",)}),
        ("command-nul", ("opencode_command",), {"server_url": None, "server_username": None, "server_password": None, "opencode_command": ("open\x00code",)}),
        ("command-str", ("opencode_command",), {"server_url": None, "server_username": None, "server_password": None, "opencode_command": "opencode"}),
        ("url-ftp", ("server_url",), {"server_url": "ftp://127.0.0.1:4096"}),
        ("url-http-remote", ("server_url",), {"server_url": "http://opencode.invalid:4096"}),
        ("url-userinfo", ("server_url",), {"server_url": "http://opencode@127.0.0.1:4096"}),
        ("url-query", ("server_url",), {"server_url": "http://127.0.0.1:4096/?directory=x"}),
        ("url-fragment", ("server_url",), {"server_url": "http://127.0.0.1:4096/#top"}),
        ("url-no-host", ("server_url",), {"server_url": "http://"}),
        ("url-no-scheme", ("server_url",), {"server_url": "127.0.0.1:4096"}),
        ("username-without-password", ("server_username", "server_password"), {"server_password": None}),
        ("password-without-username", ("server_username", "server_password"), {"server_username": None}),
        ("credentials-without-url", ("server_username", "server_password", "server_url"), {"server_url": None}),
        ("command-and-url", ("opencode_command", "server_url"), {"opencode_command": ("opencode",)}),
        ("backends-duplicate", ("backends",), {"backends": (backend.DEEPSEEK, backend.DEEPSEEK)}),
        ("backends-plain-string", ("backends",), {"backends": ("deepseek",)}),
        ("mcp-key-mismatch", ("mcp_servers",), {"mcp_servers": {"other": files}}),
        ("mcp-value-type", ("mcp_servers",), {"mcp_servers": {"files": "node files-server.js"}}),
        ("mcp-over-16", ("mcp_servers",), {"mcp_servers": {f"s{index}": local_mcp(api, name=f"s{index}") for index in range(17)}}),
        ("startup-zero", ("startup_timeout_seconds",), {"startup_timeout_seconds": 0}),
        ("startup-nan", ("startup_timeout_seconds",), {"startup_timeout_seconds": math.nan}),
        ("startup-bool", ("startup_timeout_seconds",), {"startup_timeout_seconds": True}),
        ("startup-over-max", ("startup_timeout_seconds",), {"startup_timeout_seconds": 600.5}),
        ("request-negative", ("request_timeout_seconds",), {"request_timeout_seconds": -1.0}),
        ("request-inf", ("request_timeout_seconds",), {"request_timeout_seconds": math.inf}),
        ("request-over-max", ("request_timeout_seconds",), {"request_timeout_seconds": 600.5}),
        ("live-zero", ("max_live_turns",), {"max_live_turns": 0}),
        ("live-over-16", ("max_live_turns",), {"max_live_turns": 17}),
        ("live-bool", ("max_live_turns",), {"max_live_turns": True}),
        ("live-float", ("max_live_turns",), {"max_live_turns": 2.0}),
    ]


def test_host_settings_reject_each_bad_field(records_api, tmp_path) -> None:
    # §9.1 OpencodeHostSettings rules and EC-152; one bad field per row on a known-good attached settings record.
    failures = []
    for row_id, field_names, overrides in settings_cases(records_api, tmp_path):
        try:
            expect_rejected(records_api, "OpencodeHostSettings", field_names, lambda overrides=overrides: attached_settings(records_api, tmp_path, **overrides))
        except AssertionError as error:
            failures.append(f"{row_id}: {error}")
    assert failures == [], "\n".join(failures)


def test_host_settings_errors_never_quote_the_password(records_api, tmp_path) -> None:
    # INV-6: server_password is secret, so no settings error quotes it.
    secret = "pw-" + uuid.uuid4().hex
    for overrides in ({"server_username": None}, {"server_url": None}, {"server_url": "http://opencode.invalid:4096"}, {"opencode_command": ("opencode",)}):
        with pytest.raises(records_api.ConfigurationError) as caught:
            attached_settings(records_api, tmp_path, server_password=secret, **overrides)
        assert secret not in str(caught.value)


def test_host_settings_accept_each_valid_mode(records_api, tmp_path) -> None:
    # §9.1: PATH lookup, an owned command with backends, loopback http, remote https with credentials, and the inclusive caps.
    backend = records_api.HarnessBackendName
    servers = {f"s{index}": local_mcp(records_api, name=f"s{index}") for index in range(16)}
    accepted = [
        records_api.OpencodeHostSettings(workspace=tmp_path),
        records_api.OpencodeHostSettings(workspace=tmp_path, opencode_command=("opencode",), backends=(backend.GLM, backend.DEEPSEEK)),
        records_api.OpencodeHostSettings(workspace=tmp_path, server_url="http://localhost:4096"),
        records_api.OpencodeHostSettings(workspace=tmp_path, server_url="http://[::1]:4096"),
        attached_settings(records_api, tmp_path, server_url="https://opencode.invalid", mcp_servers=servers, max_live_turns=16, startup_timeout_seconds=600, request_timeout_seconds=600),
    ]
    assert accepted[1].backends == (backend.GLM, backend.DEEPSEEK)
    assert len(accepted[4].mcp_servers) == 16 and accepted[4].max_live_turns == 16
