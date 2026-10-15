"""FILE: tests/features/harness_threads/test_harness_threads_argv.py

PURPOSE: How every argv is built and handed to the runner: the canonical CliArgv.build in both styles (D-12, FR-15, INV-16), the exact §9.2 argv for each harness and verb with no options and with every option set, a flag-like prompt that never becomes a flag (AC-15, INV-7, EC-4), every flag a value of a flag enum (AC-14), and the plain-str argv and environment, timeouts, output caps, stdin and environment names each CliInvocation carries (INV-2, INV-8, INV-10, INV-16).
ROLE IN CODEBASE: Start here when a vendor receives a malformed command line, a value turns into a flag, or a run is bounded wrongly.
ARCHITECTURE NOTE: CliArgv is pure and tested directly. The per-harness argv is read from what the stand-in received. The CliInvocation checks use a spy around CliRunner.run that records each invocation and delegates to the real runner.
FUNCTION INVENTORY: spy_runner records invocations; expected_argv builds the §9.2 argv for one call; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new option is a spec change first (§8.5 flag enum, §9.2), then one more element in expected_argv.
WHAT NOT TO DO IN THIS FILE: Do not loosen the exact argv comparisons into membership checks; the order is the §9.2 contract.
KNOWN EDGE CASES: The Muse fork's --session-id is the new id from the serve exchange, read from the stand-in's `forked` record.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-7, INV-8, INV-10, INV-16, §6.2 AC-14, AC-15, §8.5 CliArgv, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_argv.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

HARNESSES = ("grok", "opencode", "muse")
VERBS = ("run", "continue", "fork")
EXEC_ROLES = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}
FLAG_ENUMS = {"grok": "GrokFlag", "opencode": "OpencodeFlag", "muse": "MuseFlag"}
FLAG_PROMPT = "--yolo"


def spy_runner(api, monkeypatch) -> list:
    seen: list = []
    real_run = api.CliRunner.run

    async def recording_run(self, invocation):
        seen.append(invocation)
        return await real_run(self, invocation)

    monkeypatch.setattr(api.CliRunner, "run", recording_run)
    return seen


def expected_argv(harness: str, verb: str, *, workspace: str, prompt: str, thread: str | None, model: str | None, full: bool) -> list[str]:
    # §9.2, in its order.
    if harness == "grok":
        argv = ["--output-format=json", f"--cwd={workspace}", f"--permission-mode={'plan' if full else 'default'}"]
        argv += ["--model=grok-code-fast-1", "--reasoning-effort=high"] if full else []
        argv += [f"--resume={thread}"] if verb != "run" else []
        argv += ["--fork-session"] if verb == "fork" else []
        return [*argv, f"--single={prompt}"]
    if harness == "opencode":
        argv = ["run", "--format=json", f"--dir={workspace}", f"--model={model}"]
        argv += ["--agent=build", "--variant=high"] if full else []
        argv += [f"--session={thread}"] if verb != "run" else []
        return argv + (["--fork"] if verb == "fork" else [])
    argv = ["exec", "--json", "--provider", "meta", "--workspace", workspace]
    argv += ["--session-id", thread] if verb != "run" else []
    argv += ["--model", "muse-large", "--reasoning-effort", "ultra"] if full else []
    return [*argv, "--user-input-auto-resolve", "--", prompt]


def test_joined_style_makes_one_element_per_option(lib_api) -> None:
    # D-12 / INV-16: JOINED gives flag=value as one plain str; a switch is its flag; the order is kept; a dash value stays inside.
    enums, option = lib_api.enums, lib_api.CliOption
    argv = lib_api.CliArgv.build(
        ("opencode-bin",),
        command=("run",),
        options=(option(enums.OpencodeFlag.FORMAT, "json"), option(enums.OpencodeFlag.FORK), option(enums.OpencodeFlag.AGENT, "-x")),
        style=lib_api.CliOptionStyle.JOINED,
    )
    assert argv == ("opencode-bin", "run", "--format=json", "--fork", "--agent=-x")
    assert isinstance(argv, tuple) and all(type(element) is str for element in argv)


def test_separate_style_keeps_values_apart_and_operands_last(lib_api) -> None:
    # D-12 / INV-16: SEPARATE gives flag, value; operands follow the options, enum operands become plain str.
    enums, option = lib_api.enums, lib_api.CliOption
    argv = lib_api.CliArgv.build(
        ("muse-bin",),
        command=("exec",),
        options=(option(enums.MuseFlag.JSON), option(enums.MuseFlag.WORKSPACE, "/mnt/c/w"), option(enums.MuseFlag.SESSION_ID, "abc")),
        style=lib_api.CliOptionStyle.SEPARATE,
        operands=(enums.MuseFlag.END_OF_OPTIONS, FLAG_PROMPT),
    )
    assert argv == ("muse-bin", "exec", "--json", "--workspace", "/mnt/c/w", "--session-id", "abc", "--", FLAG_PROMPT)
    assert all(type(element) is str for element in argv)


def test_separate_style_refuses_a_value_that_starts_with_a_dash(lib_api) -> None:
    # INV-7: a separate value starting with "-" would be read as a flag, so CliArgv refuses it and names the flag.
    option = lib_api.CliOption
    for value in ("--yolo", "-e"):
        with pytest.raises(lib_api.ConfigurationError) as caught:
            lib_api.CliArgv.build(("muse-bin",), options=(option(lib_api.enums.MuseFlag.SESSION_ID, value),), style=lib_api.CliOptionStyle.SEPARATE)
        assert caught.value.details["field"] == "--session-id"


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("harness", HARNESSES)
async def test_argv_matches_the_documented_form_without_options(sandbox, call, pack, harness, verb) -> None:
    # §9.2: only the always-present options, in order.
    thread = (await call(harness)).thread_id if verb != "run" else None
    await call(harness, verb, pack.PROMPT, thread_id=thread)
    start = sandbox.starts(EXEC_ROLES[harness])[-1]
    session = sandbox.records("forked")[-1]["session"] if harness == "muse" and verb == "fork" else thread
    assert start["argv"] == expected_argv(harness, verb, workspace=str(sandbox.workspace), prompt=pack.PROMPT, thread=session, model=pack.OPENCODE_MODEL, full=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("harness", HARNESSES)
async def test_every_option_keeps_its_style_and_a_flag_like_prompt_stays_text(api, sandbox, call, pack, harness, verb) -> None:
    # AC-15 / AC-14 / INV-7 / EC-4: joined --flag=value for Grok and opencode, separate elements for Muse; "--yolo" never its own flag.
    thread = (await call(harness)).thread_id if verb != "run" else None
    enums = api.enums
    if harness == "grok":
        options = {"model": "grok-code-fast-1", "config": {"permission_mode": enums.GrokPermissionMode.PLAN, "reasoning_effort": enums.GrokReasoningEffort.HIGH}}
    elif harness == "opencode":
        options = {"config": {"agent": "build", "variant": "high"}}
    else:
        options = {"model": "muse-large", "config": {"reasoning_effort": enums.MuseReasoningEffort.ULTRA}}
    result = await call(harness, verb, FLAG_PROMPT, thread_id=thread, **options)
    assert result.text == f"{harness} answer to: {FLAG_PROMPT}"
    start = sandbox.starts(EXEC_ROLES[harness])[-1]
    session = sandbox.records("forked")[-1]["session"] if harness == "muse" and verb == "fork" else thread
    argv = start["argv"]
    assert argv == expected_argv(harness, verb, workspace=str(sandbox.workspace), prompt=FLAG_PROMPT, thread=session, model=pack.OPENCODE_MODEL, full=True)
    flags = {member.value for member in getattr(enums, FLAG_ENUMS[harness])}
    if harness == "muse":
        before_operands = argv[: argv.index("--")]
        assert FLAG_PROMPT not in before_operands and argv[argv.index("--") + 1 :] == [FLAG_PROMPT]
        assert all(element in flags for element in before_operands[1:] if element.startswith("-"))
    else:
        assert FLAG_PROMPT not in argv
        assert all(element.split("=", 1)[0] in flags for element in argv if element.startswith("-"))
    if harness == "opencode":
        assert start["stdin_text"] == FLAG_PROMPT


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_runner_gets_plain_strings_the_call_timeout_and_the_harness_cap(api, sandbox, call, pack, monkeypatch, harness) -> None:
    # INV-16 plain str argv and environment; INV-8 timeout and stdout caps; INV-10 stdin; §9.2 environment names per child.
    invocations = spy_runner(api, monkeypatch)
    constants = api.constants
    first = await call(harness, config={"timeout_seconds": 45.5})
    if harness == "muse":
        await call("muse", "continue", "Again.", thread_id=first.thread_id, config={"timeout_seconds": 45.5})
    for invocation in invocations:
        assert all(type(element) is str for element in invocation.argv)
        assert all(type(name) is str and type(value) is str for name, value in invocation.env_overlay.items())
        assert pack.API_KEY not in invocation.argv
    if harness == "grok":
        (invocation,) = invocations
        assert (invocation.timeout_seconds, invocation.max_output_bytes, invocation.stdin_text) == (45.5, constants.GROK_CLI_MAX_OUTPUT_BYTES, None)
        assert Path(invocation.cwd).resolve() == sandbox.workspace
        assert set(invocation.env_overlay) == {"XAI_API_KEY", "GROK_CODE_XAI_API_KEY", "GROK_HOME", "GROK_DISABLE_AUTOUPDATER"}
        assert invocation.env_overlay["XAI_API_KEY"] == invocation.env_overlay["GROK_CODE_XAI_API_KEY"] == pack.API_KEY
    elif harness == "opencode":
        (invocation,) = invocations
        assert (invocation.timeout_seconds, invocation.max_output_bytes, invocation.stdin_text) == (45.5, constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES, pack.PROMPT)
        assert Path(invocation.cwd).resolve() == sandbox.workspace
        assert set(invocation.env_overlay) == {"OPENCODE_CONFIG_CONTENT", "OPENCODE_DISABLE_AUTOUPDATE"}
        assert pack.API_KEY not in invocation.env_overlay.values() and pack.API_KEY in invocation.env_overlay["OPENCODE_CONFIG_CONTENT"]
    else:
        serves = [invocation for invocation in invocations if "serve" in invocation.argv]
        execs = [invocation for invocation in invocations if "exec" in invocation.argv]
        assert len(serves) == 1 and len(execs) == 2 and len(invocations) == 3
        for invocation in execs:
            assert (invocation.timeout_seconds, invocation.max_output_bytes, invocation.stdin_text) == (45.5, constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES, None)
            assert set(invocation.env_overlay) == {"META_API_KEY", "MUSE_NO_AUTO_UPDATE", "XDG_CONFIG_HOME", "MUSE_AUTH_PATH"}
            assert invocation.env_overlay["META_API_KEY"] == pack.API_KEY
        serve = serves[0]
        assert serve.timeout_seconds == constants.NATIVE_CONTROL_TIMEOUT_SECONDS and serve.stdin_text
        assert set(serve.env_overlay) == {"MUSE_NO_AUTO_UPDATE", "XDG_CONFIG_HOME", "MUSE_AUTH_PATH"}
        assert pack.API_KEY not in serve.env_overlay.values()
