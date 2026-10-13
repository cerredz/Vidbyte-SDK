"""FILE: tests/features/opencode_host/test_opencode_host_security.py

PURPOSE: Secret handling for OpencodeHost (AC-5, INV-6, T-3): a vendor error that echoes the attached or owned server password, a backend key, or an MCP env or header value is scrubbed to `<redacted>` in the error and in the tool result; provider `key` and `options` never reach a result; secret fields never reach a `repr`; and the host logs nothing.
ROLE IN CODEBASE: Start here when a secret shows up in an error, a tool result, a repr or a log. Covers NativeErrorFactory.register_secret and scrub as OpencodeHost and the opencode tools use them, plus OpencodeWire's provider mapping.
ARCHITECTURE NOTE: Every secret-shaped value is generated per test with uuid4, so the committed fixtures hold none. The fake echoes the value inside a vendor error body (`data.message`, or the MCP status `error`), which is exactly the text the host must scrub before it surfaces it.
FUNCTION INVENTORY: assert_scrubbed_error and assert_scrubbed_tool check one error or tool result for a value; the test_* functions are one secret source each.
COMMON MODIFICATION PATTERNS: A new secret source is one more test that registers the value through the host's own inputs and makes the fake echo it.
WHAT NOT TO DO IN THIS FILE: 1. Do not print a secret in an assertion message; the helpers name only where it leaked. 2. Do not commit a key-shaped literal; generate it.
KNOWN EDGE CASES: AC-5 lists the message, context, tool output and metadata together; these tests require the value to be absent from all of them and `<redacted>` to appear in the error's message or context, because the spec does not fix which of the two carries the scrubbed vendor text.
RELATED DOCS: tests/features/opencode_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md AC-5, INV-6, §10 T-3 and T-4, D-18
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/opencode_host/test_opencode_host_security.py
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import pytest

KNOWN_SESSION = "ses_known0001"
PROMPT = "List the top-level folders."


def assert_scrubbed_error(error: Any, value: str) -> None:
    surfaces = {"message": str(error), "next_step": error.next_step, "context": json.dumps(dict(error.context)), "args": repr(error.args)}
    leaked = [name for name, text in surfaces.items() if value in text]
    assert not leaked, f"INV-6: the secret leaked into {leaked}"
    assert "<redacted>" in surfaces["message"] + surfaces["context"], "AC-5: the scrubbed vendor text carries <redacted>"


def assert_scrubbed_tool(result: Any, value: str) -> None:
    assert result.metadata.get("error"), "expected an error result"
    leaked = [name for name, text in (("output", result.output), ("metadata", json.dumps(dict(result.metadata), default=str))) if value in text]
    assert not leaked, f"INV-6: the secret leaked into the tool {leaked}"


def echo_on(fake: Any, route: str, value: str) -> None:
    fake.override(route, 500, {"name": "UnknownError", "data": {"message": f"upstream rejected credential {value} for this request"}})


@pytest.mark.asyncio
async def test_attached_server_password_in_a_vendor_error_is_redacted(opencode_api, opencode_tools_api, fake_opencode, make_opencode_host, attached_secret, tool_by_name) -> None:
    # AC-5: the attached server_password is a value the host injected (into the basic-auth header).
    async with make_opencode_host() as host:
        echo_on(fake_opencode, "session_list", attached_secret)
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.list_opencode_sessions()
        result = await tool_by_name(opencode_tools_api.OpencodeTools(host), "list_opencode_sessions").execute(opencode_tools_api.ToolCall("list_opencode_sessions", {}))
    assert_scrubbed_error(caught.value, attached_secret)
    assert_scrubbed_tool(result, attached_secret)


@pytest.mark.asyncio
async def test_owned_server_password_in_a_vendor_error_is_redacted(opencode_api, opencode_tools_api, fake_opencode, serve_fake, fast_timings, tool_by_name) -> None:
    # AC-5 / T-3: the random owned-server password, read back from the basic-auth header the host sent.
    settings = opencode_api.OpencodeHostSettings(workspace=fake_opencode.workspace, opencode_command=serve_fake.command())
    async with opencode_api.OpencodeHost(settings) as host:
        server_password = fake_opencode.requests[0].auth[1]
        echo_on(fake_opencode, "provider", server_password)
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.list_opencode_providers()
        result = await tool_by_name(opencode_tools_api.OpencodeTools(host), "list_opencode_providers").execute(opencode_tools_api.ToolCall("list_opencode_providers", {}))
    assert_scrubbed_error(caught.value, server_password)
    assert_scrubbed_tool(result, server_password)


@pytest.mark.asyncio
async def test_backend_key_in_a_vendor_error_is_redacted(opencode_api, fake_opencode, serve_fake, fast_timings, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-5: a backend key the host copied into the owned server's environment (D-16).
    key_value = "ds-" + uuid.uuid4().hex
    monkeypatch.setenv("DEEPSEEK_API_KEY", key_value)
    settings = opencode_api.OpencodeHostSettings(workspace=fake_opencode.workspace, opencode_command=serve_fake.command(), backends=(opencode_api.HarnessBackendName.DEEPSEEK,))
    async with opencode_api.OpencodeHost(settings) as host:
        echo_on(fake_opencode, "config_providers", key_value)
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.list_opencode_models()
    assert_scrubbed_error(caught.value, key_value)


@pytest.mark.asyncio
async def test_mcp_environment_value_in_a_failed_status_is_redacted(opencode_api, opencode_tools_api, fake_opencode, make_opencode_host, tool_by_name) -> None:
    # AC-5 / EC-92: the MCP status `error` echoes an env value the host sent in the MCP config.
    env_value = "mcp-" + uuid.uuid4().hex
    config = opencode_api.OpencodeMcpServerConfig(name="files", kind=opencode_api.OpencodeMcpKind.LOCAL, command=("node", "files-server.js"), environment={"FILES_ACCESS": env_value})
    fake_opencode.mcp_answer = {"files": {"status": "failed", "error": f"spawn failed with FILES_ACCESS={env_value}"}}
    async with make_opencode_host(mcp_servers={"files": config}) as host:
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.add_opencode_mcp_server(config)
        result = await tool_by_name(opencode_tools_api.OpencodeTools(host), "add_opencode_mcp_server").execute(opencode_tools_api.ToolCall("add_opencode_mcp_server", {"name": "files"}))
    assert caught.value.failure_code is opencode_api.FailureCode.OPENCODE_MCP_SERVER_FAILED
    assert_scrubbed_error(caught.value, env_value)
    assert_scrubbed_tool(result, env_value)


@pytest.mark.asyncio
async def test_mcp_header_value_in_a_vendor_error_is_redacted(opencode_api, fake_opencode, make_opencode_host) -> None:
    # AC-5: an MCP header value is a secret the host injected, even when the config came straight from the caller.
    header_value = "hdr-" + uuid.uuid4().hex
    config = opencode_api.OpencodeMcpServerConfig(name="remote-docs", kind=opencode_api.OpencodeMcpKind.REMOTE, url="https://mcp.invalid/docs", headers={"Authorization": header_value})
    async with make_opencode_host() as host:
        echo_on(fake_opencode, "mcp_add", header_value)
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.add_opencode_mcp_server(config)
    assert caught.value.failure_code is opencode_api.FailureCode.OPENCODE_API_ERROR
    assert_scrubbed_error(caught.value, header_value)


@pytest.mark.asyncio
async def test_vendor_text_in_an_error_is_capped(opencode_api, fake_opencode, make_opencode_host) -> None:
    # INV-6: vendor text the host surfaces is capped at NATIVE_VENDOR_MESSAGE_MAX_CHARS (1000).
    async with make_opencode_host() as host:
        fake_opencode.override("session_list", 500, {"name": "UnknownError", "data": {"message": "z" * 5000}})
        with pytest.raises(opencode_api.NativeHostError) as caught:
            await host.list_opencode_sessions()
    assert len(caught.value.context["vendor_error"]) <= 1000
    assert "z" * 5000 not in str(caught.value)


@pytest.mark.asyncio
async def test_provider_key_and_options_never_reach_a_result(opencode_api, opencode_tools_api, fake_opencode, make_opencode_host, tool_by_name) -> None:
    # AC-9 / INV-6: Provider.key and Provider.options are never copied into a result or a tool output.
    async with make_opencode_host() as host:
        providers = await host.list_opencode_providers()
        models = await host.list_opencode_models()
        toolset = opencode_tools_api.OpencodeTools(host)
        provider_output = await tool_by_name(toolset, "list_opencode_providers").execute(opencode_tools_api.ToolCall("list_opencode_providers", {}))
        model_output = await tool_by_name(toolset, "list_opencode_models").execute(opencode_tools_api.ToolCall("list_opencode_models", {}))
    for provider in providers:
        assert not hasattr(provider, "key") and not hasattr(provider, "options")
    assert fake_opencode.provider_key not in repr(providers) + repr(models)
    for output in (provider_output.output, model_output.output):
        assert fake_opencode.provider_key not in output
        assert "apiKey" not in output and "baseURL" not in output


def test_secret_fields_never_reach_a_repr(opencode_api, tmp_path, attached_secret) -> None:
    # INV-6 / §9.1: server_password, MCP environment and MCP headers are repr=False.
    env_value = "env-" + uuid.uuid4().hex
    header_value = "hdr-" + uuid.uuid4().hex
    settings = opencode_api.OpencodeHostSettings(workspace=tmp_path, server_url="http://127.0.0.1:4096", server_username="opencode", server_password=attached_secret)
    local = opencode_api.OpencodeMcpServerConfig(name="files", kind=opencode_api.OpencodeMcpKind.LOCAL, command=("node", "files-server.js"), environment={"FILES_ACCESS": env_value})
    remote = opencode_api.OpencodeMcpServerConfig(name="docs", kind=opencode_api.OpencodeMcpKind.REMOTE, url="https://mcp.invalid/docs", headers={"Authorization": header_value})
    assert attached_secret not in repr(settings) and attached_secret not in str(settings)
    assert env_value not in repr(local) and env_value not in str(local)
    assert header_value not in repr(remote) and header_value not in str(remote)


@pytest.mark.asyncio
async def test_the_host_logs_nothing(opencode_api, fake_opencode, make_opencode_host, attached_secret, caplog: pytest.LogCaptureFixture) -> None:
    # INV-6: new modules add no logging calls, so no record can carry a secret.
    caplog.set_level(logging.DEBUG)
    async with make_opencode_host() as host:
        await host.check_opencode_ready()
        handle = await host.continue_opencode_session(KNOWN_SESSION, opencode_api.OpencodePromptRequest(prompt=PROMPT))
        await host.wait_opencode_turn(handle, timeout_seconds=30.0)
        echo_on(fake_opencode, "session_list", attached_secret)
        with pytest.raises(opencode_api.NativeHostError):
            await host.list_opencode_sessions()
    native = [record for record in caplog.records if record.name.startswith(("vidbyte.harnesses.native", "vidbyte.tools.builtins.opencode"))]
    assert native == [], f"unexpected log records from {sorted({record.name for record in native})}"
    assert all(attached_secret not in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_no_allow_everything_rule_is_ever_sent(opencode_api, fake_opencode, make_opencode_host) -> None:
    # INV-9 / AC-19: a spawn with no rules sends none, and never the (*, *, allow) rule.
    async with make_opencode_host() as host:
        handle = await host.spawn_opencode_session(opencode_api.OpencodeSpawnRequest(turn=opencode_api.OpencodePromptRequest(prompt=PROMPT)))
        await host.wait_opencode_turn(handle, timeout_seconds=30.0)
    body = fake_opencode.seen("session_create")[0].body or {}
    assert body.get("permission", []) == []
    sent = json.dumps([item.body for item in fake_opencode.requests if item.body is not None])
    assert '"action": "allow"' not in sent
