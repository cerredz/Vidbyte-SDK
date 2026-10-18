"""FILE: tests/features/harness_threads/test_harness_threads_claude_argv.py

PURPOSE: The Claude Code child process contract (spec claude-thread-functions §9.2): the exact argv after the launcher for each verb with no options and with every option set (AC-5, INV-8, D-7), every permission mode and reasoning effort reaching argv as its vendor value and never an approve-everything flag (INV-18, D-12), a flag-like prompt that travels only on stdin, then EOF (AC-5, INV-8, INV-11, EC-26, D-5), the child's working folder (INV-17), and the plain-str argv, timeout, output cap, stdin and environment overlay of the CliInvocation the call builds (INV-9, §9.2).
ROLE IN CODEBASE: Start here when Claude Code receives a malformed command line, a prompt turns into a flag or an operand, or a Claude run is bounded wrongly.
ARCHITECTURE NOTE: The argv is read from what the stand-in received after its scenario path, so the launcher prefix (the stand-in command) is left out exactly as AC-5 says. The CliInvocation checks use a spy around CliRunner.run that records each invocation and delegates to the real runner.
FUNCTION INVENTORY: spy_runner records invocations; expected_argv builds the §9.2 argv for one call; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new option is a spec change first (§8.5 ClaudeFlag, §9.2), then one more element in expected_argv.
WHAT NOT TO DO IN THIS FILE: Do not loosen the exact argv comparisons into membership checks; the order is the §9.2 contract.
KNOWN EDGE CASES: The stand-in reads stdin to EOF before it logs, so a logged stdin_text equal to the prompt also proves the pipe was closed (INV-11, vendor-facts q8). The fork's --resume is the source id and its --session-id the new id the SDK minted, which the answer echoes; the minted id is random, so expected_argv takes it from the call's result.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-8, INV-9, INV-11, INV-17, INV-18, §6.2 AC-5, §6.3 EC-26, §8.1 D-5, D-7, D-12, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_argv.py
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

VERBS = ("run", "continue", "fork")
FLAG_PROMPT = "--yolo"
PERMISSION_VALUES = ("manual", "acceptEdits", "dontAsk", "plan")
EFFORT_VALUES = ("low", "medium", "high", "xhigh", "max")
APPROVE_EVERYTHING = ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions", "bypassPermissions", "auto")
OVERLAY_NAMES = {"ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR", "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"}
# Permission rules without a shell, so they stand beside any mode.
RULES = ("Edit", "Read(./src/**)", "mcp__github__create_issue")
SHELL_RULES = [(("Bash(git *)",), True), (("PowerShell",), True), (("Edit", "Read(//tmp/**)", "BashOutput"), False)]


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


def expected_argv(verb: str, *, thread: str | None, minted: str | None = None, mode: str = "manual", model: str | None = None, effort: str | None = None, turns: str | None = None, budget: str | None = None, allowed: tuple[str, ...] = (), disallowed: tuple[str, ...] = ()) -> list[str]:
    # §9.2, in its order: the four fixed options, then --model, --effort,
    # --max-turns, --max-budget-usd, one --allowedTools and one
    # --disallowedTools per rule, --resume and --fork-session when they
    # apply, then --session-id with the id a run or fork mints (the
    # limits, the rules and the minted id from the PR #1044 review); no
    # operand. A continue never sends --session-id.
    argv = ["--print", "--output-format", "json", "--setting-sources", "user", "--permission-mode", mode]
    argv += ["--model", model] if model is not None else []
    argv += ["--effort", effort] if effort is not None else []
    argv += ["--max-turns", turns] if turns is not None else []
    argv += ["--max-budget-usd", budget] if budget is not None else []
    argv += [element for rule in allowed for element in ("--allowedTools", rule)]
    argv += [element for rule in disallowed for element in ("--disallowedTools", rule)]
    argv += ["--resume", thread] if verb != "run" else []
    argv += ["--fork-session"] if verb == "fork" else []
    return argv + (["--session-id", minted] if verb != "continue" else [])


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS)
async def test_argv_matches_the_documented_form_without_options(sandbox, call, pack, verb) -> None:
    # AC-5 / §9.2: only the always-present options, in order; the prompt
    # is no argv element and arrives on stdin.
    thread = (await call("claude")).thread_id if verb != "run" else None
    result = await call("claude", verb, pack.PROMPT, thread_id=thread)
    start = sandbox.starts("claude")[-1]
    assert start["argv"] == expected_argv(verb, thread=thread, minted=result.thread_id)
    assert start["stdin_kind"] == "pipe" and start["stdin_text"] == pack.PROMPT
    assert pack.PROMPT not in start["argv"] and start["stray"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS)
async def test_every_option_keeps_the_separate_style_and_a_flag_like_prompt_stays_on_stdin(api, sandbox, call, verb) -> None:
    # AC-5 / INV-8 / D-7 / EC-26: --flag value pairs in the §9.2 order;
    # "--yolo" reaches Claude Code only as stdin text.
    thread = (await call("claude")).thread_id if verb != "run" else None
    enums = api.enums
    config = {"permission_mode": enums.ClaudePermissionMode.ACCEPT_EDITS, "reasoning_effort": enums.ClaudeReasoningEffort.XHIGH, "max_turns": 7, "max_budget_usd": 2.5, "allowed_tools": RULES, "disallowed_tools": ("WebFetch",)}
    result = await call("claude", verb, FLAG_PROMPT, thread_id=thread, model="claude-opus-5-5", config=config)
    assert result.text == f"claude answer to: {FLAG_PROMPT}"
    start = sandbox.starts("claude")[-1]
    argv = start["argv"]
    assert argv == expected_argv(verb, thread=thread, minted=result.thread_id, mode="acceptEdits", model="claude-opus-5-5", effort="xhigh", turns="7", budget="2.5", allowed=RULES, disallowed=("WebFetch",))
    assert FLAG_PROMPT not in argv and start["stdin_text"] == FLAG_PROMPT
    flags = {member.value for member in enums.ClaudeFlag}
    assert all(element in flags for element in argv if element.startswith("-")), "INV-16: every flag is a ClaudeFlag member"


@pytest.mark.asyncio
@pytest.mark.parametrize(("allowed", "scrubbed"), SHELL_RULES, ids=["bash", "powershell", "no-shell"])
async def test_an_allowed_shell_rule_has_claude_scrub_the_key_from_its_commands(api, sandbox, call, monkeypatch, allowed, scrubbed) -> None:
    # PR #1044 review 4301898216 (C4): an allowed Bash or PowerShell rule
    # adds CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 to the overlay, so the
    # commands the model runs never see the key; other rules add nothing.
    invocations = spy_runner(api, monkeypatch)
    await call("claude", config={"allowed_tools": allowed})
    (invocation,) = invocations
    assert set(invocation.env_overlay) == OVERLAY_NAMES | ({"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"} if scrubbed else set())
    assert invocation.env_overlay.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB") == ("1" if scrubbed else None)


@pytest.mark.asyncio
async def test_tool_rules_at_their_caps_fit_a_windows_command_line(api, sandbox, call, monkeypatch) -> None:
    # PR #1044 review 4301898216: 32 allowed and 32 denied rules of the
    # longest length, each holding spaces, still fit a Windows command
    # line (32,766 UTF-16 units, measured) once quoted, and the call
    # starts on every platform.
    caps = api.constants
    rule = "Bash(" + "x " * ((caps.CLAUDE_TOOL_RULE_MAX_CHARS - len("Bash()")) // 2) + ")"
    assert len(rule) == caps.CLAUDE_TOOL_RULE_MAX_CHARS
    invocations = spy_runner(api, monkeypatch)
    rules = (rule,) * caps.CLAUDE_TOOL_RULES_MAX_ITEMS
    result = await call("claude", config={"allowed_tools": rules, "disallowed_tools": rules})
    (invocation,) = invocations
    assert len(subprocess.list2cmdline(invocation.argv)) < 32766
    assert result.thread_id


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", PERMISSION_VALUES)
async def test_each_permission_mode_reaches_argv_as_its_vendor_value(api, sandbox, call, mode) -> None:
    # INV-18 / D-12: the four modes, passed as members, become their
    # 2.1.302 values; nothing approves everything.
    result = await call("claude", config={"permission_mode": api.enums.ClaudePermissionMode(mode)})
    argv = sandbox.only_start("claude")["argv"]
    assert argv == expected_argv("run", thread=None, minted=result.thread_id, mode=mode)
    assert not any(element in APPROVE_EVERYTHING for element in argv)


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", EFFORT_VALUES)
async def test_each_reasoning_effort_reaches_argv_as_its_vendor_value(api, sandbox, call, effort) -> None:
    # §8.5 ClaudeReasoningEffort / §9.2: --effort <value> after the
    # fixed options; no effort set means no --effort at all.
    result = await call("claude", config={"reasoning_effort": api.enums.ClaudeReasoningEffort(effort)})
    assert sandbox.only_start("claude")["argv"] == expected_argv("run", thread=None, minted=result.thread_id, effort=effort)


@pytest.mark.asyncio
async def test_child_runs_in_the_resolved_workspace_whatever_pwd_says(sandbox, call, monkeypatch) -> None:
    # INV-17 / §9.2: the child's working folder is the resolved
    # workspace; an inherited PWD never wins.
    elsewhere = sandbox.root / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("PWD", str(elsewhere))
    (sandbox.workspace / "sub").mkdir()
    await call("claude", workspace=sandbox.workspace / "sub" / "..")
    start = sandbox.only_start("claude")
    assert os.path.normcase(start["cwd"]) == os.path.normcase(str(sandbox.workspace))


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS)
async def test_runner_gets_plain_strings_the_call_timeout_the_cap_stdin_and_the_overlay(api, sandbox, call, pack, monkeypatch, verb) -> None:
    # INV-9 / INV-11 / §9.2: one invocation per call with plain str
    # argv and variables, config.timeout_seconds, the 64 MiB cap, the
    # prompt as stdin_text, the workspace as cwd and exactly the four
    # overlay variables.
    thread = (await call("claude", config={"timeout_seconds": 45.5})).thread_id if verb != "run" else None
    invocations = spy_runner(api, monkeypatch)
    result = await call("claude", verb, pack.PROMPT, thread_id=thread, config={"timeout_seconds": 45.5})
    (invocation,) = invocations
    assert all(type(element) is str for element in invocation.argv)
    assert all(type(name) is str and type(value) is str for name, value in invocation.env_overlay.items())
    assert (invocation.timeout_seconds, invocation.max_output_bytes, invocation.stdin_text) == (45.5, api.constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES, pack.PROMPT)
    assert Path(invocation.cwd).resolve() == sandbox.workspace
    assert set(invocation.env_overlay) == OVERLAY_NAMES
    assert invocation.env_overlay["ANTHROPIC_API_KEY"] == pack.API_KEY
    assert invocation.env_overlay["DISABLE_AUTOUPDATER"] == invocation.env_overlay["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == api.constants.NATIVE_ENABLED_SWITCH == "1"
    assert os.path.normcase(invocation.env_overlay["CLAUDE_CONFIG_DIR"]) == os.path.normcase(str(sandbox.claude_config()))
    assert pack.API_KEY not in invocation.argv and not any(pack.API_KEY in element for element in invocation.argv)
    expected = expected_argv(verb, thread=thread, minted=result.thread_id)
    assert list(invocation.argv[-len(expected) :]) == expected
