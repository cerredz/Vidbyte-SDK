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

## Iteration 2 — 2026-10-10 — agent report: reports/S5-repair-2.md
**Defects in:** one gate, `merge-main`. GitHub reported `mergeable=CONFLICTING DIRTY`, because `main` (`d7b25110`, 45 commits past the merge base `8f23fd67`) conflicted in `contracts/sdk-public-api.json`. No review finding was open: R-1 to R-7 are `fixed`, and R-8 and R-9 are `follow-up`.

**Hypotheses and attempts:**
- **Main moved four times during the iteration; check `git ls-remote origin refs/heads/main` before every merge and before the final gate run.**
  - *First:* the merge of `d7b25110` was staged when `git diff --cached origin/main` showed main-only files (`vidbyte/tools/base.py`, the filesystem tools, `tests/test_mongodb_tools.py`) as differences. A concurrent fetch had moved `origin/main` to `6b7ba7c3` (#700, strict tool booleans). I aborted that merge and merged `6b7ba7c3` instead.
  - *Second:* after the first merge was committed and gated, `bfe395fe` (#698, Jev skills preload) landed. I merged it as a second merge commit. No rebase, no rewrite.
  - *Third:* while remote CI ran on `6d2191f7` (all four checks green), `c6e758fe` (#701, null optional tool arguments; it changes `glob.py`, `grep.py` and `read_lines.py`) landed, and the PR showed `mergeStateStatus=BEHIND`. I merged it as `38dca66d` (auto-merged, contract untouched) and re-ran every gate. Remote checks went 4/4 green on `38dca66d`.
  - *Fourth:* while the iteration-2 docs commit `8b50a6ee` was being made, `ebeb56b5` (#703, the review-agents CI swap plus docstring-only text in `a009_readme_size_limit.py`) and `84f7aee3` (#705, provider rows null limit) landed. I checked first with `git merge-tree --write-tree HEAD origin/main` (clean), then merged them as `d104bd78` and re-ran every gate. Main's protection has `strict: true`, so a branch behind main cannot merge.
  - *Check:* `git diff origin/main..HEAD --stat` must show only the 8 §12.3 files, the pack and `docs/spec/coding-agent/`. If it shows main-side files as deletions, main has moved again.
- **The contract.** The only conflict in either merge was `contracts/sdk-public-api.json:3`, the `source.commit` line (main `787afabf`, branch `1bb1d3b4`). The briefing's "two additions, CodingAgent and BashTool" is inexact: the contract lists root exports only, and `BashTool` is exported from `vidbyte.tools.builtins`, so `CodingAgent` is the only branch line.
  - *Tried first:* take main's whole file, commit the merge (`563f1db8`), then run the generator, which stamped the merge commit (`72ef4638`). The generator writes only when the data differs from the committed file, and it refuses to write while `vidbyte/__init__.py` is uncommitted, which is the case mid-merge. So "regenerate before the merge commit" is impossible unless the hunk is kept by hand.
  - *Reverted to:* main's `source` line plus the branch's `"CodingAgent"` line, applied in the second merge (`6d2191f7`). **Why:** main's own #698 added five exports and kept `787afabf`, so that is the repo's practice; C016 compares data only. A branch-specific stamp keeps line 3 different from main, and line 3 is exactly what conflicted with the 0.2.1 release bump. The net contract diff against main is now the one `"CodingAgent"` line. Both `--check` and write mode report it current at `787afabf` (599 exports).
- **Main's new lint rules (A009, C006–C015, S063, S064).** All of them ran with no error. A per-path filter of `python lint/run.py --all --format json` shows zero findings in `coding.py`, `bash.py`, both READMEs, the contract and the pack, under every rule. Every rule's count is at or under main's baseline. No source change was needed.
  - *Inherited:* the only findings in feature-touched files are in the three `__init__.py` files: A001 (main's "Context Protocol Header" form), plus S001 F401 and S015 in `vidbyte/__init__.py`. I compared those lines with `git show origin/main:vidbyte/__init__.py`; they are byte-identical, only shifted by the one added import line.
- **Interactions with what main changed.**
  - `BaseAgent.__init__` is unchanged by main (only `restore`, `run`, `run_sequentially` and the trace scrub changed), so INV-2 still holds and the signature test passes.
  - `PricedOperationTool._PAYLOAD_KEY` is still `"operation_payload"` (`operations/base.py:40`); main's `fetch.py` change only touched `_url_list`.
  - `runtime.py:1208` still prices `ActivityToolFormatter.unwrap(tool)`, which goes through `_unwrap_tool` and so unwraps `_ToolWrapper`.
  - #700's `_resolve_bool_argument` does not reach `BashTool`, whose only argument is a string.
  - #701's `_optional_argument` (null means the default) applies to the wired glob, grep and read tools; the pack's acceptance cases for them pass.
- **Not reached:** the known flake `test_cancelled_turn_releases_its_waiting_reader` did not occur in any of the four full runs.

**Changes:**
- `563f1db8`: merge of `origin/main` at `6b7ba7c3`. The contract was resolved to main's file.
- `72ef4638`: contract regenerated on the merged tree, stamped `563f1db8`. It was superseded by the next commit.
- `6d2191f7`: merge of `origin/main` at `bfe395fe`. The contract keeps main's `source` line plus `CodingAgent`.
- `38dca66d`: merge of `origin/main` at `c6e758fe`. It auto-merged with no conflict.
- `8b50a6ee`: this entry and `reports/S5-repair-2.md`, first version.
- `d104bd78`: merge of `origin/main` at `84f7aee3`. It auto-merged with no conflict.
- No feature source, test, baseline, rule or config change.
- `git diff d158d5f6..HEAD --stat -- tests/features/coding_agent/` still shows only the two files granted in iteration 1.
- `git diff origin/main...HEAD --name-only -- tests/` shows only `tests/features/coding_agent/`.

**Gate matrix out (code HEAD `d104bd78`, main `84f7aee3` merged):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| merge-main | `gh pr view 690 --json mergeable,mergeStateStatus,isDraft` | PASS | `{"headRefOid":"d104bd78…","mergeStateStatus":"BLOCKED","mergeable":"MERGEABLE"}`, main `84f7aee3` is an ancestor of HEAD. BLOCKED = the PR is a draft (`isDraft: true`); main's protection requires Source 3.11, Source 3.12 and Package on the head SHA, `strict: true`. |
| contract | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 787afabf… (vidbyte-sdk 0.2.1, 599 exports).` |
| new tests (pack, Windows 3.11) | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/` | PASS | `86 passed, 11 skipped in 5.06s` |
| new tests (pack, WSL 3.12) | wsl.exe … `/tmp/s2-coding-agent-venv/bin/python -m pytest -q tests/features/coding_agent/` | PASS | `97 passed in 17.27s` |
| lint | `python lint/run.py` (inside the source stage) | PASS | `S063 RATCHETED: 4` / `S064 RATCHETED: 4` / `SDK-LINT: PASS` |
| full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `reasoning trace contracts: ok (182 tools, 55 shapes)` / `2865 passed, 12 skipped in 20.65s` / `CI passed.` (#703 deleted `tests/test_review_agents.py`) |
| full local gate, package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote CI | `gh workflow run ci.yml --ref feat/coding-agent` → `38081495740` on `d104bd78` | PASS | Source 3.11 `2865 passed, 12 skipped in 28.60s` / `CI passed.`; Source 3.12 `2865 passed, 12 skipped, 12 warnings in 23.99s` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote Semgrep | `gh workflow run static-policy.yml --ref feat/coding-agent` → `38081497380` on `d104bd78` | PASS | `Ran 1 rule on 869 files: 0 findings.` |
| remote check-runs | `gh api repos/cerredz/Vidbyte-SDK/commits/d104bd78…/check-runs` | PASS (4/4) | `Package: success` / `Static policy: success` / `Source / Python 3.12: success` / `Source / Python 3.11: success` |

**Still open:** none. R-8 and R-9 stay `follow-up`. The docs-only commit that records this entry needs its own CI dispatch, because branch protection checks the head SHA; its run IDs are in the S5 STATUS message.
