"""FILE: tests/features/harness_compose/test_harness_compose_acceptance.py

PURPOSE: The developer-facing outcome (AC-1): the spec §4 snippet runs as written in a fresh interpreter against stand-in `grok` and `opencode` programs found on PATH and the real git, and prints exactly the chain's two thread ids and None, the two verdict decisions and their agreement, and `None 3`; no compose worktree folder or registration remains, and the working tree differs from the commit only by what the stand-in writers wrote.
ROLE IN CODEBASE: Start here when the documented snippet stops running or prints something else.
ARCHITECTURE NOTE: Only the literal folder path "C:/code/my-repo" is swapped for the sandbox repository. Each stand-in answers by matching its prompt (`replies`, first match wins), so one `grok` and one `opencode` program play every role the snippet binds: chain writer and reviewer, verify writer and verifiers, planner, proposers, selector and implementer.
FUNCTION INVENTORY: grok_replies and opencode_replies script the two stand-ins; the test function runs the snippet and reads the logs.
COMMON MODIFICATION PATTERNS: When spec §4 changes, copy the new snippet into SNIPPET verbatim and adjust the replies to the roles it binds.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit SNIPPET beyond the spec text. 2. Do not set real keys; the placeholders are not keys.
KNOWN EDGE CASES: The more specific reply rules come first, because the task text appears in every ensemble prompt and the verify prompt in both verifier prompts. On win32 the PATH stand-ins are `.exe` launchers built from pip's distlib launcher; the test skips without it.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §4, §6.2 AC-1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_acceptance.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

VERIFY_PROMPT = "Write a test for the --verbose flag."
SNIPPET = '''import asyncio
import os

from vidbyte.harnesses.native import GrokPermissionMode, GrokThreadConfig, fork_grok_thread, run_grok_thread, run_opencode_thread
from vidbyte.harnesses.native.compose import EnsembleRoster, bind_thread, run_ensemble, run_opencode_then_grok, verify_with


async def main() -> None:
    repo, xai = "C:/code/my-repo", os.environ["XAI_API_KEY"]
    plan = GrokThreadConfig(permission_mode=GrokPermissionMode.PLAN)
    opencode = bind_thread(run_opencode_thread, api_key=os.environ["ZHIPU_API_KEY"], workspace=repo, model="zai-coding-plan/glm-5.3")
    grok = bind_thread(run_grok_thread, api_key=xai, workspace=repo, config=GrokThreadConfig(permission_mode=GrokPermissionMode.ACCEPT_EDITS))
    planner = bind_thread(run_grok_thread, api_key=xai, workspace=repo, config=plan)
    proposer = bind_thread(fork_grok_thread, api_key=xai, workspace=repo, config=plan)
    chained = await run_opencode_then_grok("Add a --verbose flag to cli.py.", opencode=opencode, grok=grok)
    print([outcome.thread_id for outcome in chained.outcomes], chained.failed_step)
    review = await verify_with(opencode, [planner, opencode], prompt="Write a test for the --verbose flag.")
    print([str(answer.value.decision) for answer in review.verdicts if answer.ok], review.agreement)
    roster = EnsembleRoster(planner=planner, proposers=[proposer, proposer, opencode], selector=planner, implementer=grok)
    result = await run_ensemble("Make the CLI start faster.", roster=roster)
    print(result.failed_stage, len(result.proposals))


asyncio.run(main())
'''


def grok_replies(pack) -> list[dict]:
    plan = pack.plan_json([("ROLE-ONE", "IDENTITY-ONE"), ("ROLE-TWO", "IDENTITY-TWO"), ("ROLE-THREE", "IDENTITY-THREE")])
    return [
        {"contains": "GUIDANCE-FASTER", "text": "Implemented the lazy imports.", "write_files": {"startup.txt": "lazy imports\n"}},
        {"contains": "PROPOSAL-ONE", "text": pack.selection_json(3, guidance="GUIDANCE-FASTER")},
        {"contains": "IDENTITY-ONE", "text": "PROPOSAL-ONE: import lazily."},
        {"contains": "IDENTITY-TWO", "text": "PROPOSAL-TWO: cache the parser."},
        {"contains": VERIFY_PROMPT, "text": pack.verdict_json("approve")},
        {"contains": pack.PROMPT, "text": "Extended the flag.", "write_files": {"cli_verbose.txt": "verbose notes\n"}},
        {"contains": pack.TASK, "text": plan},
    ]


def opencode_replies(pack) -> list[dict]:
    return [
        {"exact": pack.PROMPT, "final_parts": ["Added the flag."], "write_files": {"cli.py": "def main(verbose=False):\n    return 0\n"}},
        {"exact": VERIFY_PROMPT, "final_parts": ["Wrote the test."], "write_files": {"tests/test_verbose.py": "def test_verbose():\n    assert True\n"}},
        {"contains": "IDENTITY-THREE", "final_parts": ["PROPOSAL-THREE: drop the plugin scan."]},
        {"contains": VERIFY_PROMPT, "final_parts": [pack.verdict_json("approve")]},
    ]


def test_developer_snippet_runs_as_written_against_stand_ins_on_path(compose_api, sandbox, pack) -> None:
    # AC-1: stand-ins on PATH, the real git, placeholder keys in the
    # caller's environment, the user home redirected, the snippet's
    # folder a repository with one commit.
    sandbox.make_repo()
    sandbox.stand_in(sandbox.bin, "grok", "grok", label="grok", replies=grok_replies(pack))
    sandbox.stand_in(sandbox.bin, "opencode", "opencode", label="opencode", replies=opencode_replies(pack))
    source = SNIPPET.replace('"C:/code/my-repo"', json.dumps(sandbox.workspace.as_posix()))
    assert source.count(sandbox.workspace.as_posix()) == 1
    environment = {
        **os.environ, "PYTHONPATH": str(pack.REPO_ROOT), "PATH": sandbox.path_with_git(), "USERPROFILE": str(sandbox.home), "HOME": str(sandbox.home),
        "TMP": str(sandbox.tmp), "TEMP": str(sandbox.tmp), "TMPDIR": str(sandbox.tmp),
        "XAI_API_KEY": pack.fresh_key("xai-placeholder"), "ZHIPU_API_KEY": pack.fresh_key("zhipu-placeholder"),
    }
    finished = subprocess.run([sys.executable, "-c", source], cwd=sandbox.root, env=environment, capture_output=True, text=True, timeout=240, stdin=subprocess.DEVNULL, check=False)
    assert finished.returncode == 0, finished.stderr
    assert "Traceback" not in finished.stderr

    opencode_writer = next(launch for launch in sandbox.launches(role="opencode") if launch["start"].get("stdin_text") == pack.PROMPT)
    grok_reviewer = next(launch for launch in sandbox.launches(role="grok") if pack.PROMPT in (pack.launch_prompt(launch) or ""))
    expected = [
        f"{[pack.launch_session(opencode_writer), pack.launch_session(grok_reviewer)]!r} None",
        "['approve', 'approve'] True",
        "None 3",
    ]
    assert finished.stdout.splitlines() == expected
    assert sandbox.leftovers() == [], "no compose worktree or index folder remains"
    assert sandbox.worktrees() == 1, "no worktree registration remains"
    assert sandbox.status() == {" M cli.py", "?? cli_verbose.txt", "?? startup.txt", "?? tests/test_verbose.py"}
