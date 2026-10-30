"""FILE: tests/features/claude_code_agent/test_claude_code_failures.py

PURPOSE: Failure tests of ClaudeCodeHarnessAgent against the offline `claude` stand-in: every ClaudeCodeFailureKind (NOT_INSTALLED, NOT_AUTHENTICATED, TIMEOUT, EXIT_NONZERO, SCHEMA_VIOLATION, UNSUPPORTED_INPUT, MALFORMED_OUTPUT) from the condition that selects it, the error's attributes and message parts, credential scrubbing, the timeout and cancellation stopping the process tree, and the session id staying unset after a failed first run.
ROLE IN CODEBASE: The executable form of the failure table in docs/design/claude-code-harness-agent.md section 6.6 and of the failure half of tests/features/claude_code_agent/FEATURE.md.
ARCHITECTURE NOTE: Failures before launch (unsupported input, no claude) are proven by the stand-in's empty log; failures after launch use the stand-in scenarios that replay the shapes observed live (the login failure object, the schema run without structured_output, the unknown-session stderr).
FUNCTION INVENTORY: One test per condition; raised() runs one arun and returns its ClaudeCodeAgentError; KIND_TESTS names, for each failure kind, the test that raises it from its real condition, and test_every_failure_kind_has_a_test checks the table covers every kind and names tests that exist.
COMMON MODIFICATION PATTERNS: A new failure condition gets one test here; a new kind also gets its KIND_TESTS entry.
KNOWN EDGE CASES: The batch-launcher test and the command-line length test run only on Windows, so KIND_TESTS names a test for each kind that runs on every platform.
RELATED DOCS: tests/features/claude_code_agent/FEATURE.md; docs/design/claude-code-harness-agent.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/claude_code_agent/test_claude_code_failures.py
"""

from __future__ import annotations

import asyncio
import base64
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.features.claude_code_agent.claude_code_support import (
    SCHEMA,
    ClaudeSandbox,
    process_alive,
    settings,
)
from vidbyte.agents.claude_code import (
    ClaudeCodeAgentError,
    ClaudeCodeFailureKind,
    ClaudeCodeHarnessAgent,
    ClaudeCodeImage,
    ClaudeCodeRunInput,
)
from vidbyte.lib.constants.claude_code import CLAUDE_CODE_FAILURE_TEXTS
from vidbyte.lib.errors import AgentExecutionError, VidbyteSdkError

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")


async def raised(agent: ClaudeCodeHarnessAgent, request: Any = "hello") -> ClaudeCodeAgentError:
    with pytest.raises(ClaudeCodeAgentError) as caught:
        await agent.arun(request)
    return caught.value


@pytest.mark.asyncio
async def test_no_claude_on_path_is_not_installed(sandbox: ClaudeSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = sandbox.root / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.NOT_INSTALLED
    assert "PATH" in str(error) and "claude_bin" in str(error)
    assert sandbox.records() == [] and sandbox.leftovers() == []


@pytest.mark.asyncio
async def test_missing_claude_bin_is_not_installed(sandbox: ClaudeSandbox) -> None:
    missing = sandbox.root / "nowhere" / "claude.exe"

    error = await raised(ClaudeCodeHarnessAgent(settings(claude_bin=missing)))

    assert error.kind is ClaudeCodeFailureKind.NOT_INSTALLED
    assert str(missing) in str(error)


@pytest.mark.asyncio
async def test_explicit_claude_bin_is_used(sandbox: ClaudeSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    elsewhere = sandbox.stand_in(sandbox.root / "elsewhere", "claude")
    monkeypatch.setenv("PATH", str(sandbox.root / "empty"))

    result = await ClaudeCodeHarnessAgent(settings(claude_bin=str(elsewhere))).arun("hi")

    assert result.text == "turn 1: hi"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="batch launchers exist only on Windows")
async def test_windows_batch_launcher_is_refused_and_never_run(sandbox: ClaudeSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    npm_bin = sandbox.root / "npm-bin"
    npm_bin.mkdir()
    marker = sandbox.root / "batch.ran"
    (npm_bin / "claude.cmd").write_text(f'@echo off\r\necho ran> "{marker}"\r\n', encoding="utf-8")
    monkeypatch.setenv("PATH", str(npm_bin))

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.NOT_INSTALLED
    assert "batch launcher" in str(error)
    assert not marker.exists()


@pytest.mark.asyncio
async def test_login_failure_is_not_authenticated(sandbox: ClaudeSandbox) -> None:
    # The object Claude Code printed live with no login: exit 1, is_error
    # true, subtype still "success".
    sandbox.scenario({"mode": "auth_failure"})
    agent = ClaudeCodeHarnessAgent(settings())

    error = await raised(agent)

    assert error.kind is ClaudeCodeFailureKind.NOT_AUTHENTICATED
    assert error.exit_code == 1
    assert "Not logged in" in str(error) and "claude auth login" in str(error)
    assert agent.session_id is None
    (record,) = sandbox.records()
    assert error.session_id == record["options"]["--session-id"]


@pytest.mark.asyncio
async def test_failure_is_read_from_is_error_not_subtype_or_exit_code(sandbox: ClaudeSandbox) -> None:
    # The live login failure says subtype "success"; with a clean exit,
    # only is_error tells the run failed.
    sandbox.scenario({"mode": "auth_failure", "exit": 0})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.NOT_AUTHENTICATED
    assert error.exit_code == 0


@pytest.mark.asyncio
async def test_rejected_key_status_is_not_authenticated(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"mode": "auth_failure", "text": "API Error: request rejected", "status": 401})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.NOT_AUTHENTICATED


@pytest.mark.asyncio
async def test_api_failure_is_exit_nonzero_and_quotes_claude(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"mode": "crash", "stderr": "API Error: 529 Overloaded", "exit": 2})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.EXIT_NONZERO
    assert error.exit_code == 2
    assert 'Claude Code said: "API Error: 529 Overloaded"' in str(error)


@pytest.mark.asyncio
async def test_error_result_with_a_clean_exit_is_still_a_failure(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"mode": "error_result", "text": "API Error: 500 internal", "exit": 0})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.EXIT_NONZERO
    assert "500 internal" in str(error)


@pytest.mark.asyncio
async def test_unknown_flag_says_claude_code_is_too_old(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"mode": "unknown_option"})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.EXIT_NONZERO
    assert "older than" in str(error) and "claude update" in str(error)


@pytest.mark.asyncio
async def test_unknown_saved_session_is_exit_nonzero(sandbox: ClaudeSandbox) -> None:
    saved = str(uuid.uuid4())

    error = await raised(ClaudeCodeHarnessAgent(settings(workspace=sandbox.workspace, session_id=saved)))

    assert error.kind is ClaudeCodeFailureKind.EXIT_NONZERO
    assert f"No conversation found with session ID: {saved}" in str(error)
    assert error.session_id == saved


@pytest.mark.asyncio
async def test_timeout_stops_the_process_tree(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"mode": "sleep", "seconds": 60})
    agent = ClaudeCodeHarnessAgent(settings(timeout_seconds=1.5))

    started = time.monotonic()
    error = await raised(agent)

    assert error.kind is ClaudeCodeFailureKind.TIMEOUT
    assert "1.5 seconds" in str(error)
    assert time.monotonic() - started < 20
    (record,) = sandbox.records()
    assert not process_alive(record["pid"])
    assert not Path(record["instructions_folder"]).exists()
    assert agent.session_id is None


@pytest.mark.asyncio
async def test_cancellation_propagates_and_stops_the_process(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"mode": "sleep", "seconds": 60})
    task = asyncio.create_task(ClaudeCodeHarnessAgent(settings()).arun("slow"))
    deadline = time.monotonic() + 20
    while not sandbox.records() and time.monotonic() < deadline:
        await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    (record,) = sandbox.records()
    assert not process_alive(record["pid"])
    assert not Path(record["instructions_folder"]).exists()


@pytest.mark.asyncio
async def test_missing_structured_output_is_a_schema_violation(sandbox: ClaudeSandbox) -> None:
    # Live: an unsatisfiable schema ends with exit 0, is_error false and no
    # structured_output key, only prose in result.
    sandbox.scenario({"mode": "no_structured_output", "text": "I cannot satisfy n >= 5 and n <= 3."})
    agent = ClaudeCodeHarnessAgent(settings(output_schema=SCHEMA))

    error = await raised(agent)

    assert error.kind is ClaudeCodeFailureKind.SCHEMA_VIOLATION
    assert "n >= 5" in str(error)
    assert agent.session_id is None


@pytest.mark.asyncio
async def test_non_object_structured_output_is_a_schema_violation(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"structured": ["not", "an", "object"]})

    error = await raised(ClaudeCodeHarnessAgent(settings(output_schema=SCHEMA)))

    assert error.kind is ClaudeCodeFailureKind.SCHEMA_VIOLATION


@pytest.mark.asyncio
async def test_unsupported_attachment_is_refused_before_launch(sandbox: ClaudeSandbox) -> None:
    request = ClaudeCodeRunInput(prompt="read this", images=(ClaudeCodeImage(media_type="application/pdf", data_base64=PNG),))

    error = await raised(ClaudeCodeHarnessAgent(settings()), request)

    assert error.kind is ClaudeCodeFailureKind.UNSUPPORTED_INPUT
    assert "application/pdf" in str(error)
    assert error.session_id is None
    assert sandbox.records() == [] and sandbox.leftovers() == []


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="the 32,767-unit command-line limit is a Windows limit")
async def test_schema_too_long_for_the_windows_command_line_is_refused(sandbox: ClaudeSandbox) -> None:
    huge = {"type": "object", "properties": {"answer": {"type": "string", "description": "x" * 40000}}}

    error = await raised(ClaudeCodeHarnessAgent(settings(output_schema=huge)))

    assert error.kind is ClaudeCodeFailureKind.UNSUPPORTED_INPUT
    assert "Windows limit" in str(error)
    assert sandbox.records() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "words"),
    [
        ({"mode": "garbage"}, "final result event"),
        ({"mode": "no_result"}, "final result event"),
        ({"answer_session": "00000000-0000-4000-8000-000000000000"}, "different session"),
        ({"extra_tools": ["Bash"]}, "Bash"),
        ({"mcp_servers": [{"name": "wmux", "status": "connected"}]}, "1 MCP server"),
    ],
)
async def test_unexpected_output_is_malformed(sandbox: ClaudeSandbox, scenario: dict[str, Any], words: str) -> None:
    sandbox.scenario(scenario)
    agent = ClaudeCodeHarnessAgent(settings())

    error = await raised(agent)

    assert error.kind is ClaudeCodeFailureKind.MALFORMED_OUTPUT
    assert words in str(error)
    assert agent.session_id is None


@pytest.mark.asyncio
async def test_output_past_the_cap_is_malformed(sandbox: ClaudeSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vidbyte.agents.claude_code.agent.CLAUDE_CODE_MAX_OUTPUT_BYTES", 4096)
    sandbox.scenario({"mode": "huge", "bytes": 20000})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.MALFORMED_OUTPUT
    assert "could not be read whole" in str(error)


@pytest.mark.asyncio
async def test_credentials_never_reach_the_message(sandbox: ClaudeSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-ant-api03-user-secret-value-0123456789"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    other = "sk-ant-oat01-another-token-abcdefghij"
    sandbox.scenario({"mode": "crash", "stderr": f"invalid x-api-key {secret}; token={other}; Bearer {other}"})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert error.kind is ClaudeCodeFailureKind.NOT_AUTHENTICATED
    texts = (str(error), repr(error.details), repr(error.safe_runtime_details))
    assert not any(secret in text or other in text for text in texts)
    assert "<redacted>" in str(error)


@pytest.mark.asyncio
async def test_error_carries_its_packet(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"mode": "auth_failure"})

    error = await raised(ClaudeCodeHarnessAgent(settings()))

    assert isinstance(error, AgentExecutionError) and isinstance(error, VidbyteSdkError)
    cause, step = CLAUDE_CODE_FAILURE_TEXTS[ClaudeCodeFailureKind.NOT_AUTHENTICATED]
    assert (error.likely_cause, error.next_step) == (cause, step)
    assert error.error_kind == "claude_code.not_authenticated"
    assert error.details["safe_runtime_details"]["kind"] == "not_authenticated"
    message = str(error)
    assert message.index("Claude Code could not authenticate") < message.index("Claude Code said") < message.index("Likely cause") < message.index("Next step")


KIND_TESTS = {
    ClaudeCodeFailureKind.NOT_INSTALLED: "test_no_claude_on_path_is_not_installed",
    ClaudeCodeFailureKind.NOT_AUTHENTICATED: "test_login_failure_is_not_authenticated",
    ClaudeCodeFailureKind.TIMEOUT: "test_timeout_stops_the_process_tree",
    ClaudeCodeFailureKind.EXIT_NONZERO: "test_api_failure_is_exit_nonzero_and_quotes_claude",
    ClaudeCodeFailureKind.SCHEMA_VIOLATION: "test_missing_structured_output_is_a_schema_violation",
    ClaudeCodeFailureKind.UNSUPPORTED_INPUT: "test_unsupported_attachment_is_refused_before_launch",
    ClaudeCodeFailureKind.MALFORMED_OUTPUT: "test_unexpected_output_is_malformed",
}


def test_every_failure_kind_has_a_test() -> None:
    # Each kind of the contract has a written cause and next step, and a
    # test above that raises it from its real condition on every platform.
    assert set(ClaudeCodeFailureKind) == set(CLAUDE_CODE_FAILURE_TEXTS) == set(KIND_TESTS)
    assert all(callable(globals().get(name)) for name in KIND_TESTS.values())
