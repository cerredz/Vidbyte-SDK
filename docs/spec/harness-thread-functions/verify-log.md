# Verification log: Harness thread functions (run, continue and fork Grok, opencode and Muse threads with the caller's API key)

Gate set (from context/code-map.md §1):
- new tests (local): `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads`
- whole suite (local): `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider`
- custom lint (local): `python lint/run.py` (after `git add` of new files); S009 must stay at or under 350
- import order S051 (local): `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` (the I001 on `vidbyte/lib/errors/__init__.py` is main's)
- comment width (local, field guide `comment-format.md`): `awk 'length($0) > 72' <file> | grep -E '^\s*#'` over every changed file under `vidbyte/`
- full gate, source stage (local): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
- full gate, package stage (local): `python scripts/run_ci.py --stage package` with `PYTHONPATH` unset
- Semgrep (local and remote; not in run_ci): `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` and `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, run from the semgrep venv with `PYTHONUTF8=1`, after a commit (tracked files only)
- remote checks (remote-only, dispatched by hand): `ci.yml` (Package, Source / Python 3.11, Source / Python 3.12) and `static-policy.yml`, read through `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`

## Iteration 1 — 2026-10-15 12:45 — S5 repair agent (report `reports/S5-repair-1.md`)

**Defects in.** Confirmed findings R-1 to R-11 from `review.md`, plus the trivial R-15, R-16 and R-17. The feature pack started at `33 failed, 395 passed, 2 skipped in 76.18s` (launcher 9, errors 9, process_bounds 8, arguments 4, skills 2, runner 1), all of them S4 regression tests for those findings. Follow-up findings (R-12 to R-14, R-18 to R-26) were left as they are.

**Hypotheses and attempts.**
- R-11: `Process.wait()` cannot mark the end of a run, because on Python 3.12+ it resolves only after every pipe has closed, which a grandchild holding the pipes can delay for good. The exit signal has to come from the protocol's `process_exited`, so a `SubprocessStreamProtocol` subclass sets an event there. Verified on Python 3.11 and in a scratch Python 3.13 venv; there is no local 3.12, so the remote Source / Python 3.12 job is the check for it.
- R-4: `shutil.which` on win32 always puts the current folder first, even with `path=`, so it cannot be kept. Adding `PATH`/`PATHEXT` members to `NativeEnvironmentVariable` was dropped because the surface test pins its members; they became constants. The bare-name lookup was lifted into `CliRunner.run` so `run → launch → find_program` stays one level deep.
- R-5: a raising helper inside `NativeErrorFactory` was rejected (it recreates the two-level chain R-3 removes), as were cross-harness imports, a new class, and an `is_thread_id` on the validator (more feature coupling in the canonical validator, R-22). The chosen helpers are static methods on existing classes, as pre-authorized.
- R-8: counting the quoted form needs `subprocess.list2cmdline` and UTF-16 units; the check runs only on win32 and only for the argv prompts (Grok, Muse). A WinError 206 that still happens maps to `OS_ERROR` (`launch_failed`) instead of `not_installed`.
- R-10: `asyncio.to_thread` cannot be cancelled, so the preparation runs as a shielded task and a cancel waits for it before removing what it made.

**Changes.** One commit per defect: R-2 `74114bd1`, R-3 `3466a6fc`, R-7 `cdf4efde`, R-5 `efae78a5`, R-6 `bdc8cd7a`, R-4 `f64ba4b8`, R-8 `2e8ae979`, R-11 `1583ee8c`, R-9 `69c3f9a5`, R-10 `9e09b9b1`, R-15 `d8e838bb`, R-16 `250692ad`, R-17 `17650ceb`, R-1 `b8305b44`. Spec §17 deviations 13 to 22 and the review status column in `de8d1592`. No test, lint rule, baseline or config changed; `git diff 91625f11..HEAD -- tests` is empty.

**Gates (run in this worktree, this iteration).**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` | PASS (was 33 failed) | `428 passed, 2 skipped in 47.03s` (the 2 skips are platform skips, e.g. "Muse is looked up on PATH only outside win32 (EC-29)") |
| whole suite | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` | PASS on the run_ci re-run; the standalone run hit the known flake | standalone: `FAILED tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` / `1 failed, 5600 passed, 16 skipped, 1 warning in 97.74s`. Alone afterwards: failed, failed, passed, then 5 of 5 passed. The run_ci source re-run below runs the same `python -m pytest`: `5601 passed, 16 skipped in 92.72s` |
| custom lint | `python lint/run.py` | PASS | `S009 RATCHETED: 350 known finding(s)` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` (IMPROVED, not rebaselined: A002 703→585, C011 2→1, C012 24→23, S001 59→56, S010 5→0, S025 263→261, S061 6→5) |
| import order (I001) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (no new finding) | Over the branch's changed files: `vidbyte\lib\errors\__init__.py:22:1: I001 [*] Import block is un-sorted or un-formatted` / `Found 1 error.`, which origin/main's copy of that file also gives (`Found 1 error.`); S051 `259 259 RATCHETED` |
| comment width | `awk 'length($0) > 72' <file> \| grep -E '^\s*#'` over every changed `vidbyte/` file | PASS | only `vidbyte/lib/enums/failure.py now=6 main=6` and `vidbyte/lib/errors/base.py now=9 main=9` (unchanged from main) |
| full gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS (2nd run) | 1st run: `1 failed, 5600 passed, 16 skipped` (same MCP flake) / `CI failed: Command failed with exit code 1: ... -m pytest`. 2nd run: `SDK-LINT: PASS` ... `================= 5601 passed, 16 skipped in 92.72s (0:01:32) =================` / `CI passed.` |
| full gate, package | `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Semgrep test | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` (semgrep venv, `PYTHONUTF8=1`) | PASS | `1/1: ✓ All tests passed` / `No tests for fixes found.` |
| Semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Ran 1 rule on 958 files: 0 findings.` (exit 0) |
| remote checks | `gh workflow run ci.yml` (run 38771195576) and `static-policy.yml` (run 38771198811) on `de8d1592`, read via `gh api repos/cerredz/Vidbyte-SDK/commits/de8d1592.../check-runs` | PASS 4/4 | `Package success` · `Static policy success` · `Source / Python 3.11 success` · `Source / Python 3.12 success` |

The MCP test is a timing race in a file this branch does not touch (`vidbyte/tools/mcp/transport.py` and its test are identical to origin/main): it cancels the first request after 50 ms, so when starting the child takes longer the first line is never written and the second request waits out its 5 s timeout. An origin/main export passed it 5 of 5 times, and the branch passed it 5 of 5 times once the machine was idle.

**Still open.** None. Every confirmed finding (R-1 to R-11) and the trivial R-15 to R-17 are fixed; the follow-ups R-12 to R-14 and R-18 to R-26 stay with their owners as tagged.
