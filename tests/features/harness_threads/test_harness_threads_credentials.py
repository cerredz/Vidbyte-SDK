"""FILE: tests/features/harness_threads/test_harness_threads_credentials.py

PURPOSE: The caller's key and the child process contract: the key wins over every stored or environment credential (AC-3, INV-3, EC-7, EC-8, D-6), it never reaches argv, stdin, an error, a repr or a log and `os.environ` is never written (AC-4, INV-2, EC-10, NFR-3), each child gets its documented variables, standard input and folder (INV-10, INV-17, INV-18, §9.2), and a successful call writes only where the spec allows and starts only the expected processes (AC-19, INV-12, INV-13).
ROLE IN CODEBASE: Start here when a run bills the wrong account, a key shows up anywhere, or a call leaves files behind.
ARCHITECTURE NOTE: The stand-in logs credential digests, never values. The AC-4 stand-in echoes everything it was given (argv, stdin, the raw credential variables) into its own error output, with copies of the key straddling NATIVE_VENDOR_MESSAGE_MAX_CHARS, so a factory that caps before it scrubs leaves a key fragment behind. A spy around CliRunner.run records each CliInvocation and delegates to the real runner, so the reprs the call built can be checked without replacing the seam.
FUNCTION INVENTORY: fragments lists the 8-character windows of a key; spy_runner wraps CliRunner.run; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new credential variable is one more entry in fake_harness.CREDENTIAL_NAMES and one more check in test_child_authenticates_with_the_callers_key.
WHAT NOT TO DO IN THIS FILE: Do not log or print the key; compare digests from the stand-in log.
KNOWN EDGE CASES: The sandbox redirects tempfile.tempdir, so the Muse per-call config folder is created, and must be removed, inside the sandbox. The Grok stand-in writes its own sessions/ folder into GROK_HOME, as Grok does; AC-19 allows that and nothing else there.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-2, INV-3, INV-10, INV-12, INV-13, INV-17, INV-18, §6.2 AC-3, AC-4, AC-19, §9.2, §9.3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_credentials.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

import pytest

HARNESSES = ("grok", "opencode", "muse")
EXEC_ROLES = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}


def fragments(secret: str, width: int = 8) -> list[str]:
    return [secret[index : index + width] for index in range(len(secret) - width + 1)]


def spy_runner(api, monkeypatch) -> list:
    # Records every CliInvocation the call hands to CliRunner.run, then runs it for real.
    seen: list = []
    real_run = api.CliRunner.run

    async def recording_run(self, invocation):
        seen.append(invocation)
        return await real_run(self, invocation)

    monkeypatch.setattr(api.CliRunner, "run", recording_run)
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_child_authenticates_with_the_callers_key(sandbox, call, pack, monkeypatch, harness) -> None:
    # AC-3 / INV-3 / EC-7 / EC-8: the caller's environment holds other keys and a MUSE_AUTH_PATH; the child still gets api_key.
    saved_auth = sandbox.root / "saved-muse-auth.json"
    saved_auth.write_text('{"note": "a saved login the run must not use"}', encoding="utf-8")
    for name, value in (("XAI_API_KEY", "xai-env-other-key"), ("GROK_CODE_XAI_API_KEY", "xai-env-alias-key"), ("META_API_KEY", "meta-env-other-key"), ("DEEPSEEK_API_KEY", "sk-env-other-key"), ("MUSE_AUTH_PATH", str(saved_auth))):
        monkeypatch.setenv(name, value)
    before = dict(os.environ)
    expected = pack.key_digest(pack.API_KEY)
    await call(harness)
    start = sandbox.only_start(EXEC_ROLES[harness])
    if harness == "grok":
        assert start["credentials"]["XAI_API_KEY"] == expected and start["credentials"]["GROK_CODE_XAI_API_KEY"] == expected
        home = Path(start["plain"]["GROK_HOME"])
        assert os.path.normcase(str(home)) == os.path.normcase(str(sandbox.grok_home())), "INV-13: <home>/.vidbyte/grok-homes/<sha256 key>"
        assert not home.resolve().is_relative_to(sandbox.workspace)
    elif harness == "opencode":
        assert start["opencode_config"] == {"provider": {"deepseek": {"options": {"apiKey": expected}}}}
    else:
        assert start["credentials"]["META_API_KEY"] == expected
        config_home = Path(start["plain"]["XDG_CONFIG_HOME"])
        assert start["xdg_config_exists"] is True and config_home.resolve().is_relative_to(sandbox.tmp)
        assert not config_home.exists(), "the per-call Muse config folder is removed when the call ends"
        assert Path(start["plain"]["MUSE_AUTH_PATH"]) == config_home / "muse" / "auth.json"
        assert start["muse_auth_file_exists"] is False
        await call("muse")
        assert sandbox.starts("muse-exec")[1]["plain"]["XDG_CONFIG_HOME"] != str(config_home), "each call gets a fresh folder"
    assert dict(os.environ) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_key_echoed_by_the_vendor_is_redacted_everywhere(api, sandbox, call, pack, monkeypatch, caplog, harness) -> None:
    # AC-4 / INV-2 / EC-10 / NFR-3: the stand-in echoes argv, stdin and its credentials into its error output and exits 1.
    key = f"vbk-{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
    invocations = spy_runner(api, monkeypatch)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, api_key=key, fake={"mode": "echo_secrets", "echo_key": key, "echo_cap": api.constants.NATIVE_VENDOR_MESSAGE_MAX_CHARS})
    error = caught.value
    assert error.failure_code.value == f"{harness}.run_failed", str(error)
    assert api.constants.NATIVE_REDACTED in str(error) and api.constants.NATIVE_REDACTED in (error.vendor_message or "")
    surfaces = {
        "str": str(error), "repr": repr(error), "vendor_message": error.vendor_message or "", "details": json.dumps(error.details, default=str),
        "attributes": repr([error.thread_id, error.exit_code, error.error_type, error.likely_cause, error.next_step, error.safe_runtime_details]),
        "invocations": repr(invocations), "log": caplog.text,
    }
    for surface, text in surfaces.items():
        leaked = [piece for piece in fragments(key) if piece in text]
        assert leaked == [], f"{surface} holds a fragment of the key: {leaked[:3]}"
    for invocation in invocations:
        assert all(key not in element for element in invocation.argv)
        assert key not in (invocation.stdin_text or "")
    start = sandbox.only_start(EXEC_ROLES[harness])
    assert all(key not in element for element in start["argv"])


def test_request_record_repr_hides_the_key(lib_api, sandbox, pack) -> None:
    # AC-4 / INV-2: api_key is field(repr=False) on NativeThreadRequest.
    request = lib_api.NativeThreadRequest(harness=lib_api.enums.NativeHarness.GROK, verb=lib_api.enums.NativeThreadVerb.RUN, prompt="Explain.", api_key=pack.API_KEY, workspace=sandbox.workspace)
    assert pack.API_KEY not in repr(request) and pack.API_KEY not in str(request)
    assert request.api_key == pack.API_KEY


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_child_gets_its_documented_switches_stdin_and_folder(sandbox, call, pack, monkeypatch, harness) -> None:
    # INV-10 / INV-17 / INV-18: self-update off, stdin as documented, and the workspace chosen explicitly (an inherited PWD never wins).
    elsewhere = sandbox.root / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("PWD", str(elsewhere))
    workspace = str(sandbox.workspace)
    if harness == "grok":
        await call("grok")
        start = sandbox.only_start("grok")
        assert start["plain"]["GROK_DISABLE_AUTOUPDATER"] == "1"
        assert start["stdin_kind"] != "pipe", "INV-10: Grok gets no stdin (DEVNULL)"
        assert start["options"]["--cwd"] == workspace and Path(start["cwd"]).resolve() == sandbox.workspace
    elif harness == "opencode":
        await call("opencode")
        start = sandbox.only_start("opencode")
        assert start["plain"]["OPENCODE_DISABLE_AUTOUPDATE"] == "1"
        assert start["stdin_kind"] == "pipe" and start["stdin_text"] == pack.PROMPT, "INV-10: the prompt on stdin, then EOF"
        assert start["options"]["--dir"] == workspace and Path(start["cwd"]).resolve() == sandbox.workspace
    else:
        first = await call("muse")
        await call("muse", "continue", "Again.", thread_id=first.thread_id)
        for start in sandbox.starts("muse-exec"):
            assert start["plain"]["MUSE_NO_AUTO_UPDATE"] == "1"
            assert start["stdin_kind"] != "pipe", "INV-10: muse exec gets no stdin (DEVNULL)"
            assert start["options"]["--workspace"] == workspace
        serve = sandbox.only_start("muse-serve")
        assert serve["stdin_kind"] == "pipe" and serve["plain"]["MUSE_NO_AUTO_UPDATE"] == "1"
        assert serve["credentials"]["META_API_KEY"] != pack.key_digest(pack.API_KEY), "§9.2: serve runs without the key"
        assert sandbox.records("eof", "muse-serve"), "the serve child reached EOF on its stdin"


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_os_environ_never_holds_the_key_while_the_child_runs(sandbox, call, pack, wait_until, harness) -> None:
    # INV-2: the key travels only in the child's environment; the SDK never writes os.environ, even for a moment.
    before = dict(os.environ)
    task = asyncio.create_task(call(harness, fake={"mode": "hold"}))
    try:
        assert await wait_until(lambda: bool(sandbox.records("held") or sandbox.starts(EXEC_ROLES[harness])), 30.0)
        assert dict(os.environ) == before
        assert pack.API_KEY not in os.environ.values()
    finally:
        sandbox.release()
    result = await task
    assert result.thread_id
    assert dict(os.environ) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_successful_call_writes_only_where_the_spec_allows(sandbox, call, pack, harness) -> None:
    # AC-19 / INV-12 / INV-13: nothing in the workspace, the skill folders or the user home except the private Grok home; Muse's temp folder is gone.
    skill = sandbox.make_skill("review-notes", extra_files={"references/checklist.md": "Check the edges.\n"})
    before_files = sandbox.snapshot()
    before_environ = dict(os.environ)
    if harness == "muse":
        first = await call("muse", skills=[skill])
        await call("muse", "continue", "Again.", thread_id=first.thread_id, skills=[skill])
        assert [record["role_file"] for record in sandbox.starts()] == ["muse-exec", "muse-serve", "muse-exec"]
    else:
        await call(harness, skills=[skill])
        assert [record["role_file"] for record in sandbox.starts()] == [EXEC_ROLES[harness]]
    after_files = sandbox.snapshot()
    added = sorted(set(after_files) - set(before_files))
    changed = sorted(path for path in before_files if after_files.get(path) != before_files[path])
    assert changed == [], f"files changed: {changed}"
    if harness == "grok":
        home = sandbox.grok_home().relative_to(sandbox.root).as_posix()
        allowed_parents = {"home/.vidbyte", "home/.vidbyte/grok-homes", home}
        outside = [path for path in added if path not in allowed_parents and not path.startswith(home + "/")]
        assert outside == [], f"written outside the private Grok home: {outside}"
        inside = {path[len(home) + 1 :].split("/", 1)[0] for path in added if path.startswith(home + "/")}
        assert inside <= {"skills", "sessions"}, f"the SDK writes only skills/ in the private home (sessions/ is the stand-in's): {inside}"
    else:
        assert added == [], f"written: {added}"
    assert dict(os.environ) == before_environ
