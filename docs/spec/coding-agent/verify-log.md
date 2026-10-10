# Verification log: CodingAgent — a minimal BaseAgent with seven file-system and web tools

Gate set (from context/code-map.md §1, plus the orchestrator's S5 briefing):
- **Feature pack, Windows 3.11 (local):** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/`
- **Feature pack, WSL 3.12 (local; runs the POSIX-only cases):** `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -- bash -lc 'cd /mnt/c/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent && PYTHONPATH=$(pwd) /tmp/s2-coding-agent-venv/bin/python -m pytest -q tests/features/coding_agent/'`
- **Lint (local; also step 2 of the source stage):** `python lint/run.py` must print `SDK-LINT: PASS`. It counts only git-tracked files, and it includes C016 (`generate-sdk-public-api.py --check`).
- **Full local gate, source half (local):** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`. It runs the bytecode check, lint, compileall, the three check scripts and the full pytest.
- **Full local gate, package half (local):** `python scripts/run_ci.py --stage package`, with PYTHONPATH unset (setting it breaks the smoke import).
- **Remote CI (remote-only, manual dispatch):** `gh workflow run ci.yml --ref feat/coding-agent` (Source 3.11, Source 3.12, Package 3.11 on ubuntu-latest).
- **Remote Semgrep (remote-only, manual dispatch):** `gh workflow run static-policy.yml --ref feat/coding-agent`.
- **Not a gate here:** `gh pr checks` reports "no checks" until the two workflows are dispatched, because both are workflow_dispatch only.

## Iteration 1 — 2026-10-10 — agent report: reports/S5-repair-1.md
**Defects in:** R-1 (Blocker), R-2 (Blocker; test change granted), R-3 (Major), R-4 (Major), and the trivial Minors R-5, R-6 and R-7 (README edit granted). R-8 and R-9 were not forwarded; they stay `follow-up`. Every gate was green going in, at `4c4a62ef` (CI `38046509073`, Static policy `38046510490`).

**Hypotheses and attempts:** one hypothesis per defect. Each was confirmed by reproducing the defect first, and none failed.
- **R-1.**
  - *Hypothesis:* the close is not in `finally`, and `PermissionError` is not suppressed on the kill or on `transport.close()`.
  - *Before:* reproduced on WSL 3.12.3 with the verifier's `probe_stop.py` and `probe_eperm_alive.py`. Every failing row ended `is_closing=False`, raising `CancelledError` or `PermissionError`.
  - *Fix:* review.md "Fix detail R-1", applied exactly.
  - *After:* every row ended `is_closing=True`; the timeout paths returned `ERROR {'error': 'timeout'}` and the cancel paths raised `CancelledError`.
  - *Not enough on its own (the verifier's evidence):* suppressing `PermissionError` on the kill plus a `finally` close still raises from `close()`, because `Popen.kill()` suppresses only `ProcessLookupError`. Both suppressions are required.
  - *Nesting:* S024 stays at 21/25; `try`/`with`/`if` is depth 3.
- **R-2.**
  - *Hypothesis:* pytest fd capture puts the null device on fd 0, so a spawn that inherits stdin still sees end of file.
  - *Before:* `drive_ec11.py existing mutant` gave `1 passed … pytest_exit=0 mutant_spawns=1` on Windows 3.11.
  - *Change:* the test body was replaced with review.md "Fix detail R-2" After (plus `import os`). The before and after text are both in review.md; the commit is `a49b7dd8`.
  - *After, Windows 3.11:* the mutant gave `1 failed in 10.28s … pytest_exit=1` and the code `1 passed in 0.12s`.
  - *After, WSL 3.12:* the mutant gave `1 failed in 10.28s … pytest_exit=1` and the code `1 passed in 0.07s`.
  - *Gotchas:*
    - The verifier's scratch copy (`drive_ec11.py … proposed code`) takes about 8.5 s on Windows even with the real code. The repo test takes 0.1 s, so do not read the scratch timing as a hang.
    - In a `wsl.exe -- bash -lc '…'` loop, `$m` is expanded away by wsl.exe. Loop outside wsl.exe instead.
- **R-3.**
  - *Hypothesis:* `Path("")` is `Path(".")`, so `Path("").is_dir()` is True.
  - *Fix:* `os.path.isdir(root_dir)`.
  - *After:* `''` raises ConfigurationError; `'.'`, absolute paths and `Path('.')` are still accepted; all five AC-11 cases pass; mypy is clean.
- **R-4.**
  - *Hypothesis:* the literal has 6 sentences, two of them wrong.
  - *Fix:* replaced it with the "Fix detail R-4" text.
  - *After:* S025's `SentenceCounter` returns 5, S025 moves from 263 to 261, and S062 has no finding in the file.
- **R-5, R-6, R-7.**
  - Text only, each reproduced first. R-6 printed `(NotADirectoryError). Shorten the command…` for a removed root.
  - The neutral R-6 hint avoids the three strings that `test_bash_tool_contract.py:150` forbids.

**Changes:**
- `415f7c22` R-1: the `_stop` try/finally, the PermissionError suppressions and the `@intent` comment, plus the spec §17 deviation bullet.
- `a49b7dd8` R-2: the EC-11 test, under the grant.
- `64df91ce` R-3: `os.path.isdir`.
- `977c7d23` R-4: the bash description.
- `15aed1e0` R-5: the README bullet and the `coding.py` header.
- `388993f9` R-6: the spawn_failed hint.
- `581fc272` R-7: the pack README line, under the grant.
- `git diff d158d5f6..HEAD --stat -- tests/` shows exactly the two granted files.

**Gate matrix out:**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (pack, Windows 3.11) | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/` | PASS | `86 passed, 11 skipped in 5.29s` |
| new tests (pack, WSL 3.12) | wsl.exe … `/tmp/s2-coding-agent-venv/bin/python -m pytest -q tests/features/coding_agent/` | PASS | `97 passed in 17.33s` |
| lint | `python lint/run.py` | PASS | `SDK-LINT: PASS` (S024 21/25, S025 261/263, S017 78/79, C016 0/0) |
| full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `2715 passed, 12 skipped in 20.51s` / `CI passed.` |
| full local gate, package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `Installed vidbyte-sdk 0.2.0 passed smoke checks.` / `CI passed.` |
| remote CI | `gh workflow run ci.yml` → `38075705506` on `581fc272` | PASS | Source 3.11 `2718 passed, 9 skipped`; Source 3.12 `2718 passed, 9 skipped, 12 warnings`; Package `CI passed.` |
| remote Semgrep | `gh workflow run static-policy.yml` → `38075707127` on `581fc272` | PASS | `Ran 1 rule on 857 files: 0 findings.` |

**Still open:** none. R-8 and R-9 are `follow-up` by the orchestrator's decision.

*Observation outside every gate:* ruff I001 flags `tests/features/coding_agent/test_coding_agent_contract.py:14` and `test_coding_agent_web_fetch.py:14`. Both are unchanged since S2. S051 scans only `pyproject.toml vidbyte` (`lint/core/ruff.py:68`), so no gate counts them. Fixing them needs a test-tree grant.
