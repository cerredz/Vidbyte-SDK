"""FILE: tests/features/harness_threads/test_harness_threads_acceptance.py

PURPOSE: The developer-facing outcomes: the spec §4 snippet runs as written against stand-ins found on PATH (AC-1), each run_<harness>_thread returns the vendor's new thread id and final text (AC-2, FR-4, D-21), and opencode binds the caller's key to the provider its model names, which is how GLM and DeepSeek are reached (AC-17, FR-8, D-8).
ROLE IN CODEBASE: Start here when a thread function stops returning what the vendor answered, or when the documented snippet breaks.
ARCHITECTURE NOTE: AC-1 runs the snippet in a fresh interpreter with PATH, USERPROFILE/HOME and the two placeholder keys set the way the AC states; only the two literal folder paths are swapped for sandbox folders. Every other test calls the public functions with the stand-in as <harness>_command and reads what the stand-in logged.
FUNCTION INVENTORY: the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: When spec §4 changes, copy the new snippet into SNIPPET verbatim.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit SNIPPET beyond the spec text. 2. Do not set real keys; the placeholders are not keys.
KNOWN EDGE CASES: On win32 the PATH stand-ins are `.exe` launchers (batch files are refused, INV-14), built from pip's distlib launcher; the test skips without it.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §4, §6.2 AC-1, AC-2, AC-17, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_acceptance.py
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

HARNESSES = ("grok", "opencode", "muse")
EXEC_ROLES = {"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}
GROK_PLACEHOLDER = "xai-placeholder-key-0001"
DEEPSEEK_PLACEHOLDER = "sk-placeholder-key-0002"
SNIPPET = '''import asyncio
import os

from vidbyte.harnesses.native import (
    GrokPermissionMode,
    GrokThreadConfig,
    NativeThreadError,
    fork_grok_thread,
    run_grok_thread,
    run_opencode_thread,
)


async def main() -> None:
    repo = "C:/code/my-repo"
    try:
        first = await run_grok_thread("Add a --verbose flag to cli.py.", api_key=os.environ["XAI_API_KEY"], workspace=repo, skills=["C:/code/skills/python-style"], config=GrokThreadConfig(permission_mode=GrokPermissionMode.ACCEPT_EDITS))
        print(first.thread_id, first.text)
        branch = await fork_grok_thread(first.thread_id, "Now write a test for it.", api_key=os.environ["XAI_API_KEY"], workspace=repo)
        print(branch.thread_id, branch.text)
        review = await run_opencode_thread("Review cli.py for bugs.", api_key=os.environ["DEEPSEEK_API_KEY"], workspace=repo, model="deepseek/deepseek-v4-pro")
        print(review.thread_id, review.text)
    except NativeThreadError as error:
        print(error.failure_code.value, error.next_step)


asyncio.run(main())
'''


def test_developer_snippet_runs_as_written_against_stand_ins_on_path(sandbox, pack) -> None:
    # AC-1: stand-in grok and opencode first on PATH, placeholder keys in the caller's environment, the user home redirected.
    sandbox.stand_in(sandbox.bin, "grok", "grok")
    sandbox.stand_in(sandbox.bin, "opencode", "opencode")
    skill = sandbox.make_skill("python-style")
    assert SNIPPET.count("C:/code/my-repo") == 1 and SNIPPET.count("C:/code/skills/python-style") == 1
    source = SNIPPET.replace("C:/code/my-repo", sandbox.workspace.as_posix()).replace("C:/code/skills/python-style", skill.as_posix())
    environment = {**os.environ, "PYTHONPATH": str(pack.REPO_ROOT), "PATH": str(sandbox.bin), "USERPROFILE": str(sandbox.home), "HOME": str(sandbox.home), "XAI_API_KEY": GROK_PLACEHOLDER, "DEEPSEEK_API_KEY": DEEPSEEK_PLACEHOLDER}
    finished = subprocess.run([sys.executable, "-c", source], cwd=sandbox.root, env=environment, capture_output=True, text=True, timeout=240, stdin=subprocess.DEVNULL, check=False)
    assert finished.returncode == 0, finished.stderr[-3000:]
    lines = finished.stdout.splitlines()
    grok_answers, opencode_answers = sandbox.answers("grok"), sandbox.answers("opencode")
    assert len(grok_answers) == 2 and len(opencode_answers) == 1, finished.stdout
    first_id, fork_id, review_id = grok_answers[0]["session"], grok_answers[1]["session"], opencode_answers[0]["session"]
    assert lines == [
        f"{first_id} grok answer to: Add a --verbose flag to cli.py.",
        f"{fork_id} grok answer to: Now write a test for it.",
        f"{review_id} opencode answer to: Review cli.py for bugs.",
    ]
    assert fork_id != first_id
    run_start, fork_start = sandbox.starts("grok")
    assert run_start["options"]["--permission-mode"] == "acceptEdits"
    assert run_start["credentials"]["XAI_API_KEY"] == pack.key_digest(GROK_PLACEHOLDER)
    assert list(run_start["skills"]) == ["python-style"]
    assert fork_start["options"]["--resume"] == first_id and fork_start["switches"] == ["--fork-session"]
    review_start = sandbox.only_start("opencode")
    assert review_start["options"]["--model"] == "deepseek/deepseek-v4-pro"
    assert review_start["opencode_config"]["provider"]["deepseek"]["options"]["apiKey"] == pack.key_digest(DEEPSEEK_PLACEHOLDER)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_run_returns_the_vendors_new_thread_id_and_final_text(api, sandbox, call, pack, harness) -> None:
    # AC-2 / FR-4 / D-21: harness set, the id the vendor created, the vendor's final text, not truncated.
    result = await call(harness)
    assert isinstance(result, api.NativeThreadResult)
    assert result.harness is api.enums.NativeHarness(harness)
    answers = sandbox.answers(EXEC_ROLES[harness])
    assert len(answers) == 1
    assert result.thread_id == answers[0]["session"]
    assert result.text == f"{harness} answer to: {pack.PROMPT}"
    assert result.text_truncated is False


@pytest.mark.asyncio
async def test_opencode_final_text_is_the_last_messages_text_parts(sandbox, call, api) -> None:
    # D-21 / §12.3 row 40: the text parts of the last text event's message, joined by a newline; earlier narration is left out.
    result = await call("opencode", fake={"final_parts": ["First finding.", "Second finding."]})
    assert result.text == "First finding.\nSecond finding."
    assert "Let me look at the files first." not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("model", "provider"), [("zai-coding-plan/glm-5.3", "zai-coding-plan"), ("deepseek/deepseek-v4-pro", "deepseek")])
async def test_opencode_binds_the_key_to_the_models_provider(sandbox, call, pack, model, provider) -> None:
    # AC-17 / FR-8: --model=<model>, and the inline config binds api_key to exactly that provider.
    result = await call("opencode", model=model)
    start = sandbox.only_start("opencode")
    assert start["options"]["--model"] == model
    assert start["opencode_config"] == {"provider": {provider: {"options": {"apiKey": pack.key_digest(pack.API_KEY)}}}}
    assert result.thread_id == sandbox.answers("opencode")[0]["session"]
