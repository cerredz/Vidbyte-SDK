"""FILE: tests/features/harness_threads/test_harness_threads_opencode_commands.py

PURPOSE: The opencode command functions against an opencode stand-in that dispatches `--command` the way opencode 1.18.31 does: the argv with `--command=<name>` or `--agent=plan` and #1036's options, the arguments on stdin and an empty stdin without them (AC-16, INV-9, INV-24), the four functions' names and arguments (INV-25), and an unknown command reported by an error event or on stderr as `opencode.command_not_run` (AC-16, D-8, EC-52).
ROLE IN CODEBASE: Start here when an opencode command function sends the wrong command, puts its arguments on argv, or reports an unknown command as a plain run failure.
ARCHITECTURE NOTE: The stand-in knows the commands `init` and `review` unless the scenario's `commands` lists others; an unknown name prints `Command not found: "<name>". Available commands: ...` as an error event (or, with `not_found_channel: stderr`, on stderr) and exits 1. Its answer is `opencode ran /<command> with: <stdin>`, so the result text shows what arrived on stdin.
FUNCTION INVENTORY: opencode_argv builds the expected argv; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new opencode command function is one row in CASES.
WHAT NOT TO DO IN THIS FILE: Do not assert how stdin is closed; only that it carries the arguments or nothing.
KNOWN EDGE CASES: The thread id is the session the stand-in printed, read from its log.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-8, INV-9, INV-24, INV-25, §6.2 AC-16, §6.3 EC-52, §9.2, D-8
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_opencode_commands.py
"""

from __future__ import annotations

import pytest

CASES = [
    ("command-with-arguments", "run_opencode_command", ("review", "main..feature/login"), {}, "review", "main..feature/login"),
    ("command-without-arguments", "run_opencode_command", ("init",), {}, "init", ""),
    ("review-target", "run_opencode_review", ("src/store.py",), {}, "review", "src/store.py"),
    ("review-no-target", "run_opencode_review", (), {}, "review", ""),
    ("init", "run_opencode_init", (), {}, "init", ""),
]


def opencode_argv(workspace, model: str, tail: str) -> list[str]:
    return ["run", "--format=json", f"--dir={workspace}", f"--model={model}", tail]


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "name", "positional", "keywords", "command", "stdin"), CASES, ids=[case[0] for case in CASES])
async def test_command_functions_send_the_command_on_argv_and_the_arguments_on_stdin(sandbox, skill, pack, case, name, positional, keywords, command, stdin) -> None:
    # AC-16 / INV-9 / INV-25 / §9.2: run --format=json --dir --model
    # --command=<c>; stdin = the arguments, empty without them; the key
    # stays in the inline config.
    result = await skill(name, *positional, **keywords)
    start = sandbox.only_start("opencode")
    assert start["argv"] == opencode_argv(sandbox.workspace, pack.OPENCODE_MODEL, f"--command={command}")
    assert start["stdin_text"] == stdin
    session = sandbox.records("session", "opencode")[0]["session"]
    assert (result.harness.value, result.thread_id, result.text, result.text_truncated) == ("opencode", session, f"opencode ran /{command} with: {stdin}", False)
    assert start["credentials"]["OPENCODE_CONFIG_CONTENT"] is not None
    assert all(pack.API_KEY not in element for element in start["argv"]) and pack.API_KEY not in start["stdin_text"]


@pytest.mark.asyncio
async def test_a_project_command_the_stand_in_knows_runs(sandbox, skill) -> None:
    # D-8: opencode's own dispatch decides; a custom command passes.
    result = await skill("run_opencode_command", "team-check", "src/", fake={"commands": ["init", "review", "team-check"]})
    assert result.text == "opencode ran /team-check with: src/"


@pytest.mark.asyncio
async def test_plan_runs_the_plan_agent_with_the_task_on_stdin(api, sandbox, skill, pack) -> None:
    # AC-16 / §9.2: run ... --agent=plan, stdin = the task; a config
    # agent of "plan" is the same run.
    result = await skill("run_opencode_plan", "Plan the cache rewrite")
    start = sandbox.only_start("opencode")
    assert start["argv"] == opencode_argv(sandbox.workspace, pack.OPENCODE_MODEL, "--agent=plan") and start["stdin_text"] == "Plan the cache rewrite"
    assert result.text == "opencode answer to: Plan the cache rewrite"
    again = await skill("run_opencode_plan", "Plan again", config={"agent": "plan"})
    assert sandbox.starts("opencode")[-1]["argv"][-1] == "--agent=plan" and again.text == "opencode answer to: Plan again"


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["event", "stderr"])
async def test_an_unknown_command_is_command_not_run(api, sandbox, skill, check_error, channel) -> None:
    # AC-16 / EC-52 / D-8: opencode 1.18.31's text, as an error event or
    # on stderr, is command_not_run, not run_failed.
    fake = {"not_found_channel": channel} if channel == "stderr" else {}
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_opencode_command", "no-such", "x", fake=fake)
    check_error(caught.value, harness="opencode", operation="run_opencode_command", code="opencode.command_not_run", workspace=sandbox.workspace)
    assert 'Command not found: "no-such"' in str(caught.value)


@pytest.mark.asyncio
async def test_another_vendor_error_stays_run_failed(api, sandbox, skill, check_error) -> None:
    # D-8: only the Command-not-found text is command_not_run.
    with pytest.raises(api.NativeThreadError) as caught:
        await skill("run_opencode_init", fake={"mode": "fail", "vendor_text": "Command failed: init could not write AGENTS.md"})
    check_error(caught.value, harness="opencode", operation="run_opencode_init", code="opencode.run_failed", workspace=sandbox.workspace, vendor="Command failed: init could not write AGENTS.md")
