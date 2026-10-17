"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_publish_guard.py

PURPOSE: Prove the PR-body local-path guard of references/provider-run.md section 9 works as written: run through `sh` over a temporary body, it prints `grep exit 1` for a clean body (URLs with path-like segments, a word equal to the user name, HOME `/` or empty) and `grep exit 0` for a body that holds the worktree's name in another spelling, the home directory, the user name between slashes or backslashes, or no body at all.
ROLE IN CODEBASE: Behaviour layer of tests/features/onboard_model_provider_skill/ (spec NFR-1, D-16, EC-63, FR-10; review R-11). S9 in test_onboard_skill_security.py pins the guard's words; this file proves those words do what the paragraph beside them says.
ARCHITECTURE NOTE: The test reads the one guard line from the skill file, replaces only `<worktree>` and `<evidence>` with paths under pytest's tmp_path, and runs it with `sh -c` and a chosen HOME. It never retypes the command, so a changed guard is the guard that runs. It is offline: no git, gh, network or vendor. The fake user name and home are made up, so no machine's real paths matter.
FUNCTION INVENTORY: test_the_pr_body_guard_passes_only_a_clean_body (G1, parametrized over GUARD_CASES); _guard_line reads the line; _run_guard runs it.
COMMON MODIFICATION PATTERNS: When section 9 changes the guard, keep every case's expected exit; add a case for any new spelling the guard must catch, with a dirty line that only that pattern matches.
WHAT NOT TO DO IN THIS FILE: 1. Do not hard-code this machine's paths or user name; use tmp_path and the fake HOME. 2. Do not run git, gh, Claude, the network or any other skill command. 3. Do not pass shell=True; sh gets the line as one argument.
KNOWN EDGE CASES: Skipped, with the reason, when no `sh` is on PATH. On Windows, `sh` is Git for Windows' MSYS shell, which reads the forward-slash `C:/...` paths written here, and HOME is passed as a POSIX path that MSYS keeps. With HOME empty, MSYS may set its own home before the guard runs; the clean body still prints `grep exit 1`, because it holds no path of that home either.
RELATED DOCS: tests/features/onboard_model_provider_skill/FEATURE.md; docs/spec/provider-onboarding-skill/spec.md EC-63 and D-16; docs/spec/provider-onboarding-skill/reports/S5-repair-2.md.
TESTS: python -m pytest tests/features/onboard_model_provider_skill/test_onboard_skill_publish_guard.py -q
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.features.onboard_model_provider_skill.onboard_skill_fixtures import (
    PROCEDURE_FILE,
    PROCEDURE_REF,
    read_markdown,
)

SH = shutil.which("sh")
FAKE_USER = "s2guard"
FAKE_HOME = "/home/" + FAKE_USER
WORKTREE_NAME = "checkout-onboard-s2vendor"
# A body a correct run writes: placeholders for local paths, path-like URL segments (stripped before matching), and a
# word equal to the user name that is not a path segment.
CLEAN_BODY_LINES = (
    "## Motivation",
    "S2vendor, rank 1 in the seed list. The s2guard team and the app and dev extras are unaffected.",
    "## Verification",
    "`cd <worktree> && PYTHONPATH=<worktree> <py> -m pytest tests/features/sdk_provider_keys -q` -> `412 passed`; logs in <evidence>/gate-source.log",
    "## Sources",
    "| fact | URL | opened | quote |",
    "|---|---|---|---|",
    "| API keys | https://cloud.vendor.example/app/keys | 2026-10-17 | `S2VENDOR_API_KEY` |",
    "| docs | https://docs.vendor.example/home/s2guard/dev/s2guard/quickstart | 2026-10-17 | `chat/completions` |",
    "Opened by the onboard-model-provider skill; never merged automatically.",
    "Generated with [Claude Code](https://claude.com/claude-code)",
    "",
)
CLEAN_BODY = "\n".join(CLEAN_BODY_LINES)
# (case id, HOME, the line added to the clean body or None for no body file, expected exit of grep)
GUARD_CASES = (
    ("clean", FAKE_HOME, "", 1),
    ("clean, HOME is /", "/", "", 1),
    ("clean, HOME is empty", "", "", 1),
    ("worktree evidence path with backslashes", FAKE_HOME, "Logs: C:\\work\\" + WORKTREE_NAME + "-evidence\\gate-source.log", 0),
    ("worktree twin path with a leading /c/", FAKE_HOME, "Known-red rerun in /c/work/" + WORKTREE_NAME + "-main/", 0),
    ("worktree path, HOME is /", "/", "Edited in /srv/" + WORKTREE_NAME + "/vidbyte", 0),
    ("home directory", FAKE_HOME, "Cache at " + FAKE_HOME + "/.cache/pip", 0),
    ("user name between slashes", FAKE_HOME, "Notes in /Users/" + FAKE_USER + "/notes.txt", 0),
    ("user name between backslashes", FAKE_HOME, "Profile C:\\Users\\" + FAKE_USER + "\\AppData", 0),
    ("no body file", FAKE_HOME, None, 0),
)


def _guard_line() -> str:
    # The one sh line of section 9 that reads pr-body.md and greps it, exactly as the file holds it.
    publish = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 9. Publish")
    lines = [command for command in publish.shell_commands() if "pr-body.md" in command and "grep" in command]
    assert len(lines) == 1, "section 9 step 1 holds one PR-body guard line"
    return lines[0]


def _run_guard(line: str, worktree: Path, home: str) -> list[str]:
    # Fill in the two placeholders and run the line with sh, offline, under the given HOME.
    command = line.replace("<worktree>", worktree.as_posix()).replace("<evidence>", worktree.as_posix() + "-evidence")
    assert not re.search(r"<[a-z]+>", command), f"the guard holds a placeholder this test does not fill: {command}"
    finished = subprocess.run([SH, "-c", command], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, env={**os.environ, "HOME": home}, check=False)
    return [output for output in finished.stdout.splitlines() if output.strip()]


@pytest.mark.skipif(SH is None, reason="no sh on PATH; the guard is a POSIX sh line")
@pytest.mark.parametrize(("home", "added", "expected"), [case[1:] for case in GUARD_CASES], ids=[case[0] for case in GUARD_CASES])
def test_the_pr_body_guard_passes_only_a_clean_body(tmp_path: Path, home: str, added: str | None, expected: int) -> None:
    # G1 · EC-63 / NFR-1 / D-16 / review R-11: a clean body passes in every HOME, including a root container's, and
    # every local path or name the body must not hold blocks the push, as does a body that could not be read.
    worktree = tmp_path / WORKTREE_NAME
    evidence = tmp_path / (WORKTREE_NAME + "-evidence")
    evidence.mkdir()
    if added is not None:
        (evidence / "pr-body.md").write_text(CLEAN_BODY + added + "\n", encoding="utf-8", newline="\n")

    printed = _run_guard(_guard_line(), worktree, home)

    assert printed and printed[-1] == f"grep exit {expected}", f"expected `grep exit {expected}`; the guard printed {printed}"
    if expected == 1:
        assert printed == ["grep exit 1"], f"a clean body prints no matching line; the guard printed {printed}"
    else:
        assert [output for output in printed[:-1] if re.match(r"\d+:", output)], f"a blocked body prints the matching line; the guard printed {printed}"
    if added is None:
        assert any("pr-body.md was not read" in output for output in printed), "a body that cannot be read fails closed"
