# Verification log: Browser tools for every harness thread: run_<harness>_with_browser

Gate set (code-map §1, corrected by the S5 briefing §4; run from the worktree root):
1. Focused tests, one file at a time (local): `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/<file>.py`.
2. The area (local): `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads tests/features/codex_host`. One inherited failure is expected: `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`, fails identically on origin/main).
3. Lint (local): `PYTHONPATH=$(pwd) py -3.11 lint/run.py`; last line `SDK-LINT: PASS`, and no touched rule (A002, S024, S064, A007) above `lint/baseline.json`.
4. Full source gate (local): `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source` (background; known Windows flake `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`).
5. Package gate (local): `py -3.11 scripts/run_ci.py --stage package`, with NO `PYTHONPATH`.
6. Remote only: dispatched `CI` (Source 3.11, Source 3.12, Package) and `Static policy` (semgrep `.semgrep/typed-mapping-boundary-policy.yml`), both on the final HEAD.

Extra checks used as the reproducing commands of the review findings:
- R-1: `bash scratchpad/s5/widecomments.sh` scans the `+` comment lines of `git diff -U0 $(git merge-base origin/main HEAD) -- 'vidbyte/*.py'` (working tree) for lines over 72 columns; it must print nothing.
- R-3: `py -3.11 scratchpad/s4verify/chains.py HEAD <changed files>` lists same-class three-level call chains; only main's `FailureCode.from_exception` chain may remain.
- R-6: `PYTHONPATH=$(pwd) py -3.11 scratchpad/s5/a002count.py 6f5a7310 <changed files>` counts A002 per file with multiplicity (s4verify/a002delta.py collapses two same-named functions); it must say `NEW in working tree: 0`.

(`scratchpad` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/1da32edd-ec0f-4839-ba1f-52db538ed13c/scratchpad`.)

## Iteration 1 — 2026-10-18 04:10 — agent report: reports/S5-repair-1.md
**Defects in:** Blockers R-1, R-2, R-3; Majors R-4, R-5, R-6; trivial Minors R-7, R-8, R-9, R-10; status-only R-16 (`131b854f`) and R-17 (`5979eabb`). Red gate: `pytest -q tests/features/harness_threads/test_harness_threads_browser_lifecycle.py -k never_listed` → `2 failed, 2 passed` (`[playwright-only-call-failed]`, `[jina-only-call-failed]`, DID NOT RAISE). Follow-ups R-11–R-15, R-18, R-19 were not touched (S6 lists them).

**Hypotheses and attempts (in order):**
- R-1: rewrap the 10 blocks at ≤ 72 columns. Worked first time. Note: the S4 scan used `origin/main...HEAD`, which reads commits only; to check uncommitted edits, diff the merge base against the working tree (`widecomments.sh` now does).
- R-2: the verifier's fix (drop the `rawInput` branch from `GrokWire.connected`; count only `COMPLETED` calls in `GrokBrowserHarness.missing`; update both `@intent` blocks and the `grok/browser.py` header). Worked first time: `-k never_listed` 4 passed; lifecycle 33 passed, 1 skipped; mounts 51 passed.
- R-3: three shapes weighed. (a) One deadline computed in `complete`/`discard` before the reap and passed to `_remove(folder, deadline)` with the loop inlined (chosen; verifier-proven). (b) One `asyncio.timeout` around reap + removals in `complete`/`discard`, loop without a clock check: S064 flags the loop and the timeout block nests the method body. (c) Keep `_remove_attempts` and pass the deadline down: keeps the three-level chain. Also rejected: `asyncio.wait_for(to_thread(rmtree), max(0, deadline - now))` to bound one slow `rmtree`, because with the reap having used the whole budget the timeout is 0 and the first removal try never starts (INV-12 says the call attempts removal), and a timed-out `to_thread` keeps running anyway. Result: S064 4/4, S024 25/25, chains: only main's `FailureCode.from_exception` chain; lifecycle + runtime 59 passed, 1 skipped.
- R-4: also fixed the same invented fact in two places the review did not list: `constants/browser_tools.py:173` ("exits at start without its key") and the `select` narration ("cannot start without a key"). The README tavily row now says it starts without the key but answers no call without it.
- R-5: used the pre-granted route. The same substring replacement went into README.md:178 and `README_BULLET` (the literal escapes `"` as `\"`, so the replaced span was chosen to hold no quote or backslash); an AST check confirmed the constant equals README line 178 after CRLF→LF and still holds the Codex import guidance. `test_codex_host_packaging.py` 7 passed.
  - Before: `` … (T-6). Each harness also has three browser functions, `run_grok_with_browser`, … and `fork_muse_with_browser`. They take … ``
  - After: `` … (T-6). Each thread harness (grok, opencode, muse) also has three browser functions, `run_grok_with_browser`, … and `fork_muse_with_browser`; `CodexHost` has no browser functions yet (spec Q-19). They take … ``
- R-6: `s4verify/a002delta.py` collapses same-named functions, so it reports 11; `s5/a002count.py` counts with multiplicity and found the 12 (two `__post_init__`). After R-3 the `_remove_attempts` hit became `_remove`, which got its block in the R-3 commit. All 12 now carry a block (the four sibling-mirroring ones too, kept short): 21 → 21 per-file, 0 new; repo A002 574 → 562.
- R-7: `field(repr=False)` on `BrowserToolRequest.tools`; docstring and header rule updated.
- R-8: replaced the `0` exit-code and count literals (reaper.py, `BrowserRuntimes.node`). Tried also replacing reaper.py's `sys.platform == "win32"` with `NATIVE_WINDOWS_PLATFORM`: rejected, `mypy --platform win32` then reports `signal.SIGKILL` at reaper.py:111 (mypy narrows only on the literal; runner.py in the same folder keeps the literal). Kept the literal with a comment.
- R-9: TESTS lines of the six `threads.py`/`wire.py` headers now name the browser mounts and lifecycle tests.
- R-10: a validation check in the dataclass, so trivial: a REQUIRED/OPTIONAL stdio row needs `key_variable`; a remote row may not set arguments, options or environment. All 13 rows still load; four probes refused as expected.

**Changes:** `8286f1aa` R-1 · `fb8c0508` R-2 · `4c686557` R-3 (incl. spec §17 deviations 4, 13) · `36e5129e` R-4 · `1990e363` R-5 (incl. the pre-granted `README_BULLET`) · `103a27a5` R-6 · `07ac09b6` R-7 · `e8e543a9` R-8 · `31ae9ba4` R-9 · `ece025b3` R-10 · `170c1284` spec §6.2 Proof cells (AC-12, AC-13, AC-28) · `f759c787` stale S3 red notes in the AC-3 and AC-12 Proof cells · this commit (review.md statuses, this log). `git diff fb7be13e..HEAD --stat -- tests/` → only `tests/features/codex_host/test_codex_host_packaging.py | 2 +-`.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| R-2 red test | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_browser_lifecycle.py -k never_listed` | PASS | `4 passed, 30 deselected in 9.41s` |
| focused: lifecycle | `… test_harness_threads_browser_lifecycle.py` | PASS | `33 passed, 1 skipped in 52.81s` (after R-2); with runtime after R-3: `59 passed, 1 skipped in 62.25s` |
| focused: mounts | `… test_harness_threads_browser_mounts.py` | PASS | `51 passed in 52.48s` |
| area | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads tests/features/codex_host` | PASS except 1 inherited | `FAILED …test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`, inherited from origin/main) · `1 failed, 818 passed, 3 skipped in 179.71s (0:02:59)` |
| lint | `PYTHONPATH=$(pwd) py -3.11 lint/run.py` | PASS | `A002 IMPROVED 703 -> 562` · `S064 RATCHETED: 4` · `S024 25/25` · `A007 255/255` · `SDK-LINT: PASS` |
| R-1 scan | `bash s5/widecomments.sh` | PASS | prints nothing |
| R-6 delta | `py -3.11 s5/a002count.py 6f5a7310 <32 files>` | PASS | `files: 32  A002 at 6f5a7310: 21  in working tree: 21` · `NEW in working tree: 0` |
| full source gate | `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source` | PASS except 1 inherited | `SDK-LINT: PASS` · `context primitive introductions: ok` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `1 failed, 6628 passed, 17 skipped in 257.15s (0:04:17)` (the same inherited test; the MCP stdio flake did not occur) |
| package gate | `py -3.11 scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote: Static policy | `gh workflow run "Static policy"`, run 39095652163 on `170c1284` | PASS | `✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 1016 files: 0 findings.` |
| remote: CI | `gh workflow run CI`, run 39095651003 on `170c1284` | PASS (3/3 jobs) | Source / Python 3.11: `6441 passed, 205 skipped in 146.87s` · `CI passed.`; Source / Python 3.12: `SDK-LINT: PASS` · `6441 passed, 205 skipped, 19 warnings in 158.54s` · `CI passed.`; Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` (d00bd8ba had `6434 passed, 205 skipped`; +7 are the post-S4 tests) |

The docs-only commit that adds this entry was pushed after these runs, and both workflows were dispatched again on it; their result is in the S5 STATUS block and reports/S5-repair-1.md.

**Still open:** none of R-1–R-10. Inherited, not this branch's: `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`, local only; CI skips it without `origin/main`). Follow-ups for S6: R-11–R-15, R-18, R-19. The S3-era "(red: …)" notes in the AC-3 and AC-12 Proof cells were stale (both tests pass in the area run), so they now read "red at S3 … green since the post-S3 repairs".
