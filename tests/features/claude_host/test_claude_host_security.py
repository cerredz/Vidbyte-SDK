"""FILE: tests/features/claude_host/test_claude_host_security.py

PURPOSE: Proves the host's secret and boundary rules: SDK error text and env or header values never reach a reason, a next step, a tool output, tool metadata or a record's repr; validation names keys but never secret values; a model cannot widen the developer's bound request through extra tool arguments; and a handle id from another host, or one never issued, is unknown.
ROLE IN CODEBASE: Security layer of tests/features/claude_host/ (spec AC-24, INV-12, NFR-9, T-2, T-3, T-4, EC-48, D-13, D-14). Exercises vidbyte/harnesses/native/claude/, vidbyte/lib/dataclasses/claude.py and vidbyte/tools/builtins/claude/ over the fake SDK.
ARCHITECTURE NOTE: Every secret is a dummy marker string from claude_host_fixtures (ERROR_MARKER, ENV_MARKER, HEADER_MARKER, PROMPT_MARKER). The fake SDK errors carry the markers in their text and stderr, so any reason that embeds str(exc) leaks one. Each test also proves the marker was really in play, for example by finding the env marker on the options the client received.
COMMON MODIFICATION PATTERNS: Add a validation case to SECRET_VALIDATION_CASES as (label, builder, fields the reason may name). Add a new surface to SecretMarkerTests by collecting its text and passing it to assert_clean.
WHAT NOT TO DO IN THIS FILE: 1. Never use a real secret, token or email address; only the dummy markers. 2. Do not compare reasons with exact text; check that markers are absent and that a field is named. 3. Do not import feature symbols at module level.
KNOWN EDGE CASES: repr=False hides env and headers from repr only. A failing assertEqual on two records would print them, so these tests assert on strings and never compare a request with assertEqual. The tool that refuses unknown arguments and the tool that ignores them both satisfy D-13, so the bound-request test accepts either: a refusal must be configuration.invalid_argument and start nothing, an accepted call must run its turns, and no client may see anything the model added.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.1 (INV-12), 6.2, 9.1 "Validation summary", 10 (T-2, T-3, T-4) and NFR-9.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_security.py
"""

from __future__ import annotations

import asyncio
import json
import unittest
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vidbyte.lib.dataclasses.tools import ToolCall, ToolStatus

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    CONFIGURATION_CODES,
    DEFAULT_PROMPT,
    ENV_MARKER,
    ERROR_MARKER,
    FAKE_CLI_PATH,
    HANG_GUARD_SECONDS,
    HEADER_MARKER,
    INVALID_ARGUMENT,
    OTHER_CLI_PATH,
    OTHER_DIR,
    PROMPT_MARKER,
    SHORT_TIMEOUT_SECONDS,
    WORK_DIR,
    ClaudeHostCase,
    ProcessError,
    answer_for,
    eventually,
    init_message,
)

MARKERS = (ERROR_MARKER, ENV_MARKER, HEADER_MARKER)
DOCS_URL = "https://docs.example.test/mcp"
STEER_MESSAGE = "focus on tests"
SESSION_NOT_FOUND = "claude.session_not_found"


def docs_server() -> Any:
    """Return an HTTP MCP server record whose header holds the header marker."""
    from vidbyte.lib.dataclasses.claude import ClaudeMcpServer
    from vidbyte.lib.enums.claude import ClaudeMcpTransport

    return ClaudeMcpServer(name="docs", transport=ClaudeMcpTransport.HTTP, url=DOCS_URL, headers={"Authorization": f"Bearer {HEADER_MARKER}"})


def files_server() -> Any:
    """Return a stdio MCP server record whose env holds the env marker."""
    from vidbyte.lib.dataclasses.claude import ClaudeMcpServer
    from vidbyte.lib.enums.claude import ClaudeMcpTransport

    return ClaudeMcpServer(name="files", transport=ClaudeMcpTransport.STDIO, command="npx", args=("-y", "files-server"), env={"FILES_TOKEN": ENV_MARKER})


def secret_request(prompt: str = "") -> Any:
    """Return a bound request in WORK_DIR whose env and MCP servers carry the markers."""
    from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

    return ClaudeSpawnRequest(prompt=prompt, cwd=WORK_DIR, env={"API_TOKEN": ENV_MARKER}, mcp_servers=(docs_server(), files_server()))


def leaking_process_error() -> ProcessError:
    """Build an SDK error whose text and stderr carry every marker, as a CLI that echoes its environment would."""
    return ProcessError(f"Command failed {ERROR_MARKER}", exit_code=1, stderr=f"{ERROR_MARKER} {ENV_MARKER} {HEADER_MARKER}")


def plain(value: Any) -> Any:
    """Return an enum's wire value, or the value itself."""
    return getattr(value, "value", value)


def secret_validation_cases() -> tuple[tuple[str, Callable[[], Any], tuple[str, ...], str], ...]:
    """Return (label, builder, fields the reason may name, marker it must not show) for records that must fail validation."""
    from vidbyte.lib.dataclasses.claude import ClaudeImage, ClaudeMcpServer, ClaudeSpawnRequest, ClaudeSystemPrompt
    from vidbyte.lib.enums.claude import ClaudeImageMediaType, ClaudeMcpTransport, ClaudeSystemPromptMode

    stdio = ClaudeMcpTransport.STDIO
    http = ClaudeMcpTransport.HTTP
    replace_prompt = ClaudeSystemPrompt(mode=ClaudeSystemPromptMode.REPLACE, text=PROMPT_MARKER)
    return (
        ("env value that is not text", lambda: ClaudeSpawnRequest(env={"API_TOKEN": ENV_MARKER, "RETRY_TOKEN": ENV_MARKER.encode()}), ("env", "RETRY_TOKEN"), ENV_MARKER),
        ("env key that is not text", lambda: ClaudeSpawnRequest(env={7: ENV_MARKER}), ("env",), ENV_MARKER),
        ("output cap set twice", lambda: ClaudeSpawnRequest(max_output_tokens=32_000, env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": ENV_MARKER}), ("env", "max_output_tokens"), ENV_MARKER),
        ("header value that is not text", lambda: ClaudeMcpServer(name="docs", transport=http, url=DOCS_URL, headers={"Authorization": HEADER_MARKER.encode()}), ("headers", "Authorization"), HEADER_MARKER),
        ("http server without a URL", lambda: ClaudeMcpServer(name="docs", transport=http, headers={"Authorization": HEADER_MARKER}), ("url",), HEADER_MARKER),
        ("server env value that is not text", lambda: ClaudeMcpServer(name="files", transport=stdio, command="npx", env={"FILES_TOKEN": ENV_MARKER.encode()}), ("env", "FILES_TOKEN"), ENV_MARKER),
        ("stdio server without a command", lambda: ClaudeMcpServer(name="files", transport=stdio, env={"FILES_TOKEN": ENV_MARKER}), ("command",), ENV_MARKER),
        ("prompt that is not text", lambda: ClaudeSpawnRequest(prompt=PROMPT_MARKER.encode()), ("prompt",), PROMPT_MARKER),
        ("image data that is not base64", lambda: ClaudeImage(media_type=ClaudeImageMediaType.PNG, data=f"{PROMPT_MARKER}!"), ("data",), PROMPT_MARKER),
        ("replacement prompt with dynamic sections", lambda: ClaudeSpawnRequest(system_prompt=replace_prompt, exclude_dynamic_system_prompt_sections=True), ("exclude_dynamic_system_prompt_sections", "system_prompt"), PROMPT_MARKER),
        ("settings that are not text", lambda: ClaudeSpawnRequest(settings={"apiKeyHelper": ENV_MARKER}), ("settings",), ENV_MARKER),
    )


class SecurityCase(ClaudeHostCase):
    """Adds marker checks and a toolset builder."""

    def assert_clean(self, *texts: Any) -> None:
        for text in texts:
            rendered = text if isinstance(text, str) else json.dumps(text, default=str)
            for marker in MARKERS:
                self.assertNotIn(marker, rendered)

    def toolset(self, host: Any, request: Any) -> dict[str, Any]:
        from vidbyte.tools.toolsets.claude import ClaudeTools

        return {tool.spec().name: tool for tool in ClaudeTools(host, request)}

    async def call(self, tool: Any, arguments: dict[str, Any]) -> Any:
        return await asyncio.wait_for(tool.execute(ToolCall(tool_name=tool.spec().name, arguments=arguments)), HANG_GUARD_SECONDS)

    def assert_error_clean(self, error: Any) -> None:
        self.assertTrue(error.reason)
        self.assertTrue(error.next_step)
        self.assert_clean(error.reason, error.next_step, str(error))


class SecretMarkerTests(SecurityCase):
    """AC-24, INV-12 and NFR-9: no marker reaches a reason, a next step, a tool output or tool metadata."""

    async def test_a_failed_turn_keeps_every_marker_out_of_its_result_and_tool_output(self) -> None:
        self.fake.reply(DEFAULT_PROMPT, init_message(), leaking_process_error())
        host = await self.open_host()
        tools = self.toolset(host, secret_request())
        spawned = await self.call(tools["spawn_claude_session"], {"prompt": DEFAULT_PROMPT})
        self.assertIs(spawned.status, ToolStatus.SUCCESS, spawned.output)
        handle_id = json.loads(spawned.output)["handle_id"]
        waited = await self.call(tools["wait_claude_turn"], {"handle_id": handle_id, "timeout_seconds": HANG_GUARD_SECONDS})
        self.assertEqual(json.loads(waited.output)["status"], "failed")
        usage = await self.call(tools["track_claude_session_usage"], {"handle_id": handle_id})
        result = await asyncio.wait_for(host.get_claude_turn_result(host.get_handle(handle_id)), HANG_GUARD_SECONDS)
        self.assertIsNotNone(result.failure)
        # The markers were really in play: the client received both, and the SDK error carried all three.
        options = self.fake.turn_clients()[0].options
        self.assertEqual(dict(options.env or {}).get("API_TOKEN"), ENV_MARKER)
        self.assertIn(HEADER_MARKER, json.dumps(options.mcp_servers, default=str))
        self.assert_clean(result.failure.reason, result.failure.next_step)
        for tool_result in (spawned, waited, usage):
            self.assert_clean(tool_result.output, dict(tool_result.metadata))

    async def test_host_calls_and_tool_errors_keep_every_marker_out(self) -> None:
        from vidbyte.lib.errors import ClaudeOperationError

        self.fake.connect_error = leaking_process_error
        self.fake.history.read_error = lambda: OSError(f"session folder unreadable {ERROR_MARKER}")
        self.fake.history.fork_error = lambda: ValueError(f"bad anchor {ERROR_MARKER}")
        session = self.fake.history.add_session()
        host = await self.open_host()
        tools = self.toolset(host, secret_request())
        # The readiness probe reports the failed start in its record.
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertIsNotNone(readiness.failure)
        self.assert_clean(readiness.failure.reason, readiness.failure.next_step)
        # Raising host calls: the probe behind models, a history read and an offline fork.
        for label, call in (
            ("list_claude_models", lambda: host.list_claude_models()),
            ("list_claude_sessions", lambda: host.list_claude_sessions()),
            ("fork_claude_session", lambda: host.fork_claude_session(session)),
        ):
            with self.subTest(call=label):
                with self.assertRaises(ClaudeOperationError) as caught:
                    await asyncio.wait_for(call(), HANG_GUARD_SECONDS)
                self.assert_error_clean(caught.exception)
        # The same failures through the tools, plus a turn whose start fails.
        spawned = await self.call(tools["spawn_claude_session"], {"prompt": DEFAULT_PROMPT})
        waited = await self.call(tools["wait_claude_turn"], {"handle_id": json.loads(spawned.output)["handle_id"], "timeout_seconds": HANG_GUARD_SECONDS})
        self.assertEqual(json.loads(waited.output)["status"], "failed")
        results = [spawned, waited]
        for tool_name, arguments in (
            ("check_claude_ready", {}),
            ("list_claude_models", {}),
            ("list_claude_sessions", {}),
            ("get_claude_session_info", {"session_id": session}),
            ("fork_claude_session", {"session_id": session}),
        ):
            results.append(await self.call(tools[tool_name], arguments))
        self.assertEqual([result.status for result in results[3:]], [ToolStatus.ERROR] * 4)
        for tool_result in results:
            self.assert_clean(tool_result.output, dict(tool_result.metadata))

    async def test_reprs_of_requests_and_mcp_servers_hide_env_and_headers(self) -> None:
        request = secret_request(DEFAULT_PROMPT)
        for record in (request, docs_server(), files_server(), request.mcp_servers):
            with self.subTest(record=type(record).__name__):
                self.assert_clean(repr(record), str(record))
        # The records still hold the values: repr hides them, nothing else does.
        self.assertEqual(dict(request.env), {"API_TOKEN": ENV_MARKER})
        self.assertIn(HEADER_MARKER, dict(docs_server().headers)["Authorization"])


class SecretValidationTests(unittest.TestCase):
    """T-3 and NFR-9: validation names the field or key and never echoes an env, header, prompt, image or settings value."""

    def test_validation_errors_never_echo_secret_values(self) -> None:
        from vidbyte.lib.errors import ClaudeOperationError

        for label, build, fields, marker in secret_validation_cases():
            with self.subTest(case=label):
                with self.assertRaises(ClaudeOperationError) as caught:
                    build()
                error = caught.exception
                self.assertIn(error.failure_code, CONFIGURATION_CODES)
                self.assertTrue(any(field in error.reason for field in fields), f"the reason {error.reason!r} names none of {fields}")
                for text in (error.reason, error.next_step, str(error)):
                    self.assertNotIn(marker, text)


class BoundRequestTests(SecurityCase):
    """T-2 and D-13: spawn, continue and launch take prompts, ids and limits only; every other field stays the developer's."""

    async def test_extra_model_arguments_never_reach_the_options(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.lib.enums.claude import ClaudePermissionMode

        host = await self.open_host()
        bound = ClaudeSpawnRequest(cwd=WORK_DIR, permission_mode=ClaudePermissionMode.PLAN, max_budget_usd=0.5)
        tools = self.toolset(host, bound)
        session = self.fake.history.add_session()
        chosen_session = str(uuid.uuid4())
        escalation = {
            "permission_mode": "bypassPermissions",
            "max_budget_usd": 100.0,
            "cli_path": OTHER_CLI_PATH,
            "cwd": OTHER_DIR,
            "env": {"API_TOKEN": ENV_MARKER},
            "restricted": False,
        }
        calls = (
            ("spawn_claude_session", {"prompt": "Review src/ for bugs.", "session_id": chosen_session, **escalation}),
            ("continue_claude_session", {"session_id": session, "prompt": "Now fix the first bug.", **escalation}),
            ("launch_claude_subagents", {"prompts": ["Review src/.", "Review tests/."], "limit": 2, "session_id": chosen_session, **escalation}),
        )
        for tool_name, arguments in calls:
            with self.subTest(tool=tool_name):
                clients_before = len(self.fake.clients)
                result = await self.call(tools[tool_name], arguments)
                if result.status is ToolStatus.SUCCESS:
                    # A tool that ignored the extra arguments still ran its turns, so the checks below see their clients.
                    await self.wait_for_handles(host, result.output)
                    self.assertGreater(len(self.fake.clients), clients_before)
                else:
                    # A tool that refused them says so as an invalid argument and starts nothing. Any other refusal,
                    # such as a cwd conflict or a busy session id, means an extra argument reached the request.
                    self.assertEqual(result.metadata.get("error"), INVALID_ARGUMENT)
                    self.assertEqual(len(self.fake.clients), clients_before)
        # Whether a tool refused the extra arguments or ignored them, no client ever saw them.
        for client in self.fake.clients:
            options = client.options
            self.assertEqual(plain(options.permission_mode), "plan")
            self.assertEqual(options.max_budget_usd, 0.5)
            self.assertEqual(Path(options.cli_path), Path(FAKE_CLI_PATH))
            self.assertEqual(Path(options.cwd), Path(WORK_DIR))
            self.assertNotIn("API_TOKEN", dict(options.env or {}))
            self.assertNotEqual(options.session_id, chosen_session)

    async def wait_for_handles(self, host: Any, output: str) -> None:
        payload = json.loads(output)
        for item in payload if isinstance(payload, list) else [payload]:
            await self.finished(host, host.get_handle(item["handle_id"]))


class ForeignHandleTests(SecurityCase):
    """T-4, EC-48 and D-14: a handle from another host, or one never issued, is session_not_found, and the owner's turn is untouched."""

    async def test_another_host_cannot_see_or_touch_a_turn(self) -> None:
        from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
        from vidbyte.lib.errors import ClaudeOperationError

        self.fake.hold(DEFAULT_PROMPT)
        owner = await self.open_host()
        other = await self.open_host()
        handle = await self.spawn(owner)
        client = await self.client_for(handle)
        await eventually(lambda: bool(client.queries), "the prompt was sent")
        # get_handle on the other host, and a never-issued id on the owner.
        for label, host, handle_id in (("another host", other, handle.handle_id), ("never issued", owner, str(uuid.uuid4()))):
            with self.subTest(lookup=label):
                with self.assertRaises(ClaudeOperationError) as caught:
                    host.get_handle(handle_id)
                self.assertEqual(caught.exception.failure_code, SESSION_NOT_FOUND)
                self.assertEqual(caught.exception.next_step, CLAUDE_NEXT_STEPS[SESSION_NOT_FOUND])
        # The other host's star functions do not know the owner's handle.
        for label, call in (
            ("wait_claude_turn", lambda: other.wait_claude_turn(handle, timeout_seconds=SHORT_TIMEOUT_SECONDS)),
            ("get_claude_turn_result", lambda: other.get_claude_turn_result(handle)),
            ("steer_claude_session", lambda: other.steer_claude_session(handle, STEER_MESSAGE)),
            ("interrupt_claude_turn", lambda: other.interrupt_claude_turn(handle)),
            ("track_claude_session_usage", lambda: other.track_claude_session_usage(handle)),
        ):
            with self.subTest(call=label):
                await self.raises(call(), SESSION_NOT_FOUND)
        # Neither do the other host's tools.
        tools = self.toolset(other, ClaudeSpawnRequest(cwd=WORK_DIR))
        for tool_name, arguments in (
            ("wait_claude_turn", {"handle_id": handle.handle_id, "timeout_seconds": SHORT_TIMEOUT_SECONDS}),
            ("get_claude_turn_result", {"handle_id": handle.handle_id}),
            ("steer_claude_session", {"handle_id": handle.handle_id, "message": STEER_MESSAGE}),
            ("interrupt_claude_turn", {"handle_id": handle.handle_id}),
            ("track_claude_session_usage", {"handle_id": handle.handle_id}),
        ):
            with self.subTest(tool=tool_name):
                result = await self.call(tools[tool_name], arguments)
                self.assertIs(result.status, ToolStatus.ERROR)
                self.assertEqual(dict(result.metadata), {"error": SESSION_NOT_FOUND, "error_type": "ClaudeOperationError"})
        # The owner's turn never saw a steer or an interrupt, and still finishes normally.
        self.assertEqual(client.interrupt_calls, 0)
        self.assertEqual(self.fake.all_queries(), [DEFAULT_PROMPT])
        self.assertEqual((await self.snapshot(owner, handle)).status.value, "running")
        client.finish(answer_for(DEFAULT_PROMPT))
        final = await self.finished(owner, handle)
        self.assertEqual((final.status.value, final.result_text), ("completed", answer_for(DEFAULT_PROMPT)))


if __name__ == "__main__":
    unittest.main()
