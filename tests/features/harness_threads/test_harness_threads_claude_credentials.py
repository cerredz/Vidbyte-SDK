"""FILE: tests/features/harness_threads/test_harness_threads_claude_credentials.py

PURPOSE: The caller's Anthropic key and the Claude Code child's environment (spec claude-thread-functions INV-3, INV-4, INV-17): the child authenticates only with api_key, every inherited ANTHROPIC_*/CLAUDE* variable is dropped except CLAUDE_CODE_GIT_BASH_PATH, CLAUDE_CONFIG_DIR is the private config folder, self-update and nonessential traffic are off, an unrelated variable passes through and os.environ is never written (AC-6, EC-11 to EC-13, D-6, D-20); a key the vendor echoes on stdout and stderr is scrubbed from every surface and never reaches argv, stdin, a written file, a repr or a log (AC-7, INV-3).
ROLE IN CODEBASE: Start here when a Claude run could bill another account, reach another endpoint, join the caller's own Claude Code session, or show the key anywhere.
ARCHITECTURE NOTE: The stand-in logs the names of every ANTHROPIC_*/CLAUDE* variable it saw (never their values), the digest of ANTHROPIC_API_KEY, and the plain values of CLAUDE_CONFIG_DIR, DISABLE_AUTOUPDATER, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC, CLAUDE_CODE_GIT_BASH_PATH and VIDBYTE_UNRELATED_SETTING. The sandbox fixture first drops the test shell's own Anthropic variables (the agent shell carries a real key, CLAUDECODE and CLAUDE_CONFIG_DIR), so each test sets exactly the caller environment it describes with monkeypatch. The AC-7 stand-in echoes argv, stdin and its key into both its JSON `result` and its stderr, with copies straddling NATIVE_VENDOR_MESSAGE_MAX_CHARS.
FUNCTION INVENTORY: fragments lists the 8-character windows of a key; spy_runner wraps CliRunner.run; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new inherited variable worth naming is one more entry in INHERITED; a new child variable is a spec change first (§9.2).
WHAT NOT TO DO IN THIS FILE: Do not log or print the key; compare digests from the stand-in log.
KNOWN EDGE CASES: Environment names are upper case on win32, so the inherited names here are upper case. DISABLE_AUTOUPDATER has neither prefix, so a caller's own value is overridden by the overlay rather than dropped. The held-call test waits for the call to finish as well as to start, so a call that fails at once is awaited and reported instead of being left to the garbage collector (on Python 3.11.0 a finalised task's logged traceback re-enters ast.parse during pytest's report and crashes the session).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-3, INV-4, INV-17, §6.2 AC-6, AC-7, §6.3 EC-11 to EC-13, §8.1 D-6, D-20, §9.2, §9.3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_credentials.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid

import pytest

GIT_BASH = r"D:\Tools\Git\bin\bash.exe"
UNRELATED = "kept-as-is"


def fragments(secret: str, width: int = 8) -> list[str]:
    return [secret[index : index + width] for index in range(len(secret) - width + 1)]


def spy_runner(api, monkeypatch) -> list:
    # Records every CliInvocation the call hands to CliRunner.run, then
    # runs it for real.
    seen: list = []
    real_run = api.CliRunner.run

    async def recording_run(self, invocation):
        seen.append(invocation)
        return await real_run(self, invocation)

    monkeypatch.setattr(api.CliRunner, "run", recording_run)
    return seen


def inherited(sandbox) -> dict[str, str]:
    # AC-6 / EC-11 / EC-12: every credential, provider switch, config
    # redirect and parent-session variable the spec names.
    return {
        "ANTHROPIC_API_KEY": "sk-ant-callers-own-env-key", "ANTHROPIC_AUTH_TOKEN": "callers-auth-token", "ANTHROPIC_BASE_URL": "http://127.0.0.1:9/collect",
        "ANTHROPIC_PROFILE": "work", "ANTHROPIC_MODEL": "claude-other-model", "CLAUDE_CODE_OAUTH_TOKEN": "callers-oauth-token", "CLAUDECODE": "1",
        "CLAUDE_CONFIG_DIR": str(sandbox.root / "callers-own-claude-config"), "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_ENTRYPOINT": "cli",
        "CLAUDE_CODE_MESSAGING_TOKEN": "parent-session-token", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CODE_MAX_RETRIES": "0",
        "CLAUDE_CODE_GIT_BASH_PATH": GIT_BASH, "VIDBYTE_UNRELATED_SETTING": UNRELATED, "DISABLE_AUTOUPDATER": "0",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["run", "continue", "fork"])
async def test_child_sees_only_the_callers_key_the_private_folder_and_the_switches(sandbox, call, pack, monkeypatch, verb) -> None:
    # AC-6 / INV-4 / INV-17 / D-6 / D-20: the caller's environment holds
    # other keys, tokens, a base URL, Bedrock, a parent Claude Code
    # session and its config folder; the child gets api_key, the private
    # config folder and the two switches, keeps only
    # CLAUDE_CODE_GIT_BASH_PATH of the prefixed names, and gets the
    # unrelated variable unchanged.
    thread = (await call("claude")).thread_id if verb != "run" else None
    for name, value in inherited(sandbox).items():
        monkeypatch.setenv(name, value)
    before = dict(os.environ)
    await call("claude", verb, "Again.", thread_id=thread)
    start = sandbox.starts("claude")[-1]
    assert start["claude_names"] == ["ANTHROPIC_API_KEY", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "CLAUDE_CODE_GIT_BASH_PATH", "CLAUDE_CONFIG_DIR"]
    assert start["credentials"]["ANTHROPIC_API_KEY"] == pack.key_digest(pack.API_KEY)
    plain = start["plain"]
    assert os.path.normcase(plain["CLAUDE_CONFIG_DIR"]) == os.path.normcase(str(sandbox.claude_config())), "INV-13: <home>/.vidbyte/claude-configs/<sha256 key>"
    assert (plain["DISABLE_AUTOUPDATER"], plain["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"]) == ("1", "1")
    assert plain["CLAUDE_CODE_GIT_BASH_PATH"] == GIT_BASH and plain["VIDBYTE_UNRELATED_SETTING"] == UNRELATED
    assert dict(os.environ) == before


@pytest.mark.asyncio
async def test_os_environ_never_holds_the_key_while_claude_runs(sandbox, call, pack, wait_until) -> None:
    # INV-3: the key travels only in the child's environment; the SDK
    # never writes os.environ, even for a moment.
    before = dict(os.environ)
    task = asyncio.create_task(call("claude", fake={"mode": "hold"}))
    try:
        # A call that ends before the stand-in starts is awaited below,
        # so its own failure is the one reported.
        assert await wait_until(lambda: task.done() or bool(sandbox.records("held") or sandbox.starts("claude")), 30.0)
        assert dict(os.environ) == before
        assert pack.API_KEY not in os.environ.values()
    finally:
        sandbox.release()
    result = await task
    assert result.thread_id
    assert dict(os.environ) == before


@pytest.mark.asyncio
async def test_key_echoed_by_claude_is_redacted_everywhere_and_never_written(api, sandbox, call, pack, monkeypatch, caplog) -> None:
    # AC-7 / INV-3: the stand-in echoes argv, stdin and its key into its
    # JSON result and its stderr and fails; no fragment of the key
    # survives in the error, its attributes, the invocations, the log or
    # any file under the sandbox's home and workspace.
    key = f"sk-ant-{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
    invocations = spy_runner(api, monkeypatch)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", api_key=key, fake={"mode": "echo_secrets", "echo_key": key, "echo_cap": api.constants.NATIVE_VENDOR_MESSAGE_MAX_CHARS})
    error = caught.value
    assert error.failure_code.value == "claude.run_failed", str(error)
    assert api.constants.NATIVE_REDACTED in str(error) and api.constants.NATIVE_REDACTED in (error.vendor_message or "")
    surfaces = {
        "str": str(error), "repr": repr(error), "vendor_message": error.vendor_message or "", "details": json.dumps(error.details, default=str),
        "attributes": repr([error.thread_id, error.exit_code, error.error_type, error.likely_cause, error.next_step, error.safe_runtime_details]),
        "invocations": repr(invocations), "log": caplog.text,
    }
    for surface, text in surfaces.items():
        leaked = [piece for piece in fragments(key) if piece in text]
        assert leaked == [], f"{surface} holds a fragment of the key: {leaked[:3]}"
    (invocation,) = invocations
    assert all(key not in element for element in invocation.argv)
    assert invocation.stdin_text == pack.PROMPT
    start = sandbox.only_start("claude")
    assert all(key not in element for element in start["argv"]) and key not in start["stdin_text"]
    written = [path for folder in (sandbox.home, sandbox.workspace) for path in folder.rglob("*") if path.is_file() and key.encode("utf-8") in path.read_bytes()]
    assert written == [], f"INV-3: the key was written to {written}"


def test_records_and_invocations_hide_the_key_in_their_repr(lib_api, sandbox, pack) -> None:
    # AC-7 / INV-3: NativeThreadRequest.api_key and
    # CliInvocation.env_overlay are repr=False; ClaudeThreadConfig holds
    # no key at all.
    enums = lib_api.enums
    request = lib_api.NativeThreadRequest(harness=enums.NativeHarness.CLAUDE, verb=enums.NativeThreadVerb.RUN, prompt="Explain.", api_key=pack.API_KEY, workspace=sandbox.workspace)
    invocation = lib_api.CliInvocation(argv=("claude", "--print"), env_overlay={"ANTHROPIC_API_KEY": pack.API_KEY}, timeout_seconds=5.0, max_output_bytes=1024, cwd=sandbox.workspace, stdin_text="Explain.")
    config = lib_api.ClaudeThreadConfig(claude_command=("claude",))
    for record in (request, invocation, config):
        assert pack.API_KEY not in repr(record) and pack.API_KEY not in str(record)
    assert request.api_key == pack.API_KEY
