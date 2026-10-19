# S5 repair iteration 1 — harness-browser-tools

Stage: S5 repair, iteration 1 of 8 · Branch `feat/harness-browser-tools` · Start HEAD `36366afa` · Code HEAD `f759c787` (pushed; CI and Static policy green on `170c1284`, the last code commit) · PR https://github.com/cerredz/Vidbyte-SDK/pull/1183 · Log: `verify-log.md` iteration 1.

Every open confirmed finding (R-1 to R-6) and every Minor tagged trivial (R-7 to R-10) is fixed, one commit each. R-16 and R-17 are marked fixed by their test commits. No test was changed except the pre-granted `README_BULLET` constant. Every local gate is green apart from one failure inherited from `origin/main`, and both remote workflows are green.

Scratch tools written for this iteration, in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/1da32edd-ec0f-4839-ba1f-52db538ed13c/scratchpad/s5/`:
- `edit.py`: exact, CRLF-preserving replacement that asserts each anchor occurs exactly once;
- `r1.py` … `r10.py`, `r3_spec.py`, `proof.py`, `red_notes.py`, `review_status.py`: the edits themselves;
- `widecomments.sh`: the R-1 scan of the working tree against the merge base;
- `a002count.py`: the R-6 per-file A002 delta, counted with multiplicity;
- `mypyprobe/`: the R-8 platform-narrowing probe.

## 1. Gate matrix

| Gate | Command (from the worktree root) | Result | Final lines |
|---|---|---|---|
| R-2 red test | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_browser_lifecycle.py -k never_listed` | PASS (was `2 failed, 2 passed`) | `....  [100%]` · `4 passed, 30 deselected in 9.41s` |
| focused: lifecycle | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_browser_lifecycle.py` | PASS | `................s.................  [100%]` · `33 passed, 1 skipped in 52.81s` |
| focused: mounts | `… test_harness_threads_browser_mounts.py` | PASS | `51 passed in 52.48s` |
| focused: lifecycle + runtime after R-3 | `… test_harness_threads_browser_lifecycle.py tests/features/harness_threads/test_harness_threads_browser_runtime.py` | PASS | `59 passed, 1 skipped in 62.25s (0:01:02)` |
| focused: contract, registry, static policy, records | (after R-6, R-7, R-10) | PASS | `65 passed in 7.51s`; `62 passed in 7.57s`; `97 passed in 8.59s` |
| focused: codex packaging | `… tests/features/codex_host/test_codex_host_packaging.py` (after R-5) | PASS | `7 passed in 3.54s` |
| area | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads tests/features/codex_host` | PASS except 1 inherited | `E       AssertionError: assert 167 == 120` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 818 passed, 3 skipped in 179.71s (0:02:59)` |
| lint | `PYTHONPATH=$(pwd) py -3.11 lint/run.py` | PASS | `A002 IMPROVED 703 -> 562` · `S024 25 25 RATCHETED` · `S064 RATCHETED: 4 known finding(s)` · `A007 255 255 RATCHETED` · `SDK-LINT: PASS` |
| R-1 scan | `bash s5/widecomments.sh` | PASS | prints nothing |
| R-3 chains | `py -3.11 s4verify/chains.py HEAD <32 changed files>` | PASS | `vidbyte/lib/enums/failure.py :: FailureCode: from_exception -> _from_exception_name -> _from_exception_fallback` (already on main; nothing new) |
| R-6 delta | `PYTHONPATH=$(pwd) py -3.11 s5/a002count.py 6f5a7310 <32 changed files>` | PASS | `files: 32  A002 at 6f5a7310: 21  in working tree: 21` · `NEW in working tree: 0` |
| full source gate | `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source` (background) | PASS except 1 inherited | `SDK-LINT: PASS` · `context primitive introductions: ok` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 6628 passed, 17 skipped in 257.15s (0:04:17)` |
| package gate | `py -3.11 scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote: Static policy | run 39095652163 on `170c1284` | PASS | `1/1: ✓ All tests passed` · `✅ Scan completed successfully.` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 1016 files: 0 findings.` |
| remote: CI | run 39095651003 on `170c1284` | PASS 3/3 | 3.11: `6441 passed, 205 skipped in 146.87s (0:02:26)` · `CI passed.`; 3.12: `SDK-LINT: PASS` · `6441 passed, 205 skipped, 19 warnings in 158.54s (0:02:38)` · `CI passed.`; Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |

**The inherited failure.** The briefing's last matrix records that this test fails identically on `origin/main`. The field guide's `local-ci-verification.md` names it (`assert 167 == 120` "on main itself"). It is a merge-base length check, and CI skips it because its shallow checkout has no `origin/main`. No S5 commit touches failure codes or `lib/enums/failure.py`.

The Windows MCP stdio flake did not occur in the source run.

**The docs-only commit.** The commit that carries this report, `verify-log.md` and `review.md` was pushed after the runs above, and both workflows were dispatched again on it. Their result is in the STATUS block.

## 2. Per finding

### R-1 (Blocker) — ten added comment lines over 72 columns — fixed @`8286f1aa`
I rewrapped the ten blocks the S4 scan named, keeping each `@intent` line first.

The S4 scan reads `origin/main...HEAD`, which sees commits only. So `widecomments.sh` diffs the merge base against the working tree, which also covers uncommitted edits.

After every later fix I re-ran the scan. It prints nothing for the whole branch, including the new `@intent` blocks of R-3 and R-6.

### R-2 (Blocker) — Grok counted a failed call as connection evidence — fixed @`fb8c0508`
I applied the verifier's proven hypothesis:
- `GrokWire.connected` reads only `available_commands.tools`. I deleted the `rawInput` branch.
- `GrokBrowserHarness.missing` adds only calls whose status is `COMPLETED`.

I renamed both `@intent` markers (`grok-servers-show-only-in-the-tool-list`, `grok-evidence-is-a-listed-server-or-a-completed-call`) and rewrote them to the r5 rule. The `grok/browser.py` header (ARCHITECTURE NOTE, FUNCTION INVENTORY, KNOWN EDGE CASES) and the `grok/wire.py` FUNCTION INVENTORY now state that a failed call, "Tool not found" included, is no evidence.

Evidence:
- the reproducing command went from `2 failed, 2 passed` to `4 passed`;
- lifecycle gives `33 passed, 1 skipped`, and mounts `51 passed`.

The spec wording was already corrected in r5, so no spec edit was needed. The AC-12 Proof cell now names test commit `8b02afdd` and this fix.

### R-3 (Blocker) — three-level cleanup chain and per-removal budget — fixed @`4c686557`
I weighed three shapes before choosing; see verify-log iteration 1.

**The chosen shape.** `complete` and `discard` compute `deadline = loop.time() + BROWSER_REAP_TIMEOUT_SECONDS` before the reap. They pass it to `_remove(folder, deadline)`, which holds the retry loop: inner `suppress(OSError)`, an existence check, a stop at the deadline, then a pause. I deleted `_remove_attempts`, and `_remove` got the `@intent browser-removal-retries-until-the-cleanup-deadline` block, so A002 does not flag it.

**Documents updated in the same commit:**
- the header FUNCTION INVENTORY and KNOWN EDGE CASES;
- the `complete` and `discard` narration;
- the `BROWSER_REMOVE_*` constants comment;
- spec §17 deviations 4 and 13.

**Evidence:**
- `S064 4/4`, `S024 25/25`;
- the chain check lists only main's own `FailureCode` chain;
- lifecycle plus runtime give `59 passed, 1 skipped`, and that includes `test_a_second_cancel_cannot_stop_the_cleanup`.

**Behaviour note for the re-reviewer.** The first removal try always runs, even when the reap used the whole budget. So the worst case is the 10 s budget plus one `rmtree`, where the old shape allowed 20–30 s. In exchange, one `rmtree` that hangs is no longer cut off at 10 s. I rejected wrapping each try in `asyncio.wait_for(..., max(0, deadline - now))`: once the reap has spent the budget, the timeout is 0 and the first try never starts, which goes against INV-12's "attempts … to remove". A cancelled `to_thread` keeps running anyway, so that wrapper bounds only the wait, not the work.

**Flip condition.** If a hung removal is ever observed, bound each wait with `max(remaining, BROWSER_REMOVE_PAUSE_SECONDS)`.

### R-4 (Major) — tavily's invented key fact and the README key rule — fixed @`36e5129e`
The review's two sites are fixed:
- the registry row comment now reads "starts without TAVILY_API_KEY but answers no call without one (spec A-10)";
- the README rule now reads "cannot answer a call without a key is `REQUIRED`; works without a key but takes one is `OPTIONAL`".

The same false fact appeared in two places the review did not list, and I fixed both:
- `constants/browser_tools.py:173` ("exits at start without its key");
- the `select` narration ("cannot start without a key").

The README tavily table row now states the fact. No test pins any of these texts; the registry tests give `40 passed`.

### R-5 (Major) — the README did not say CodexHost has no browser functions — fixed @`1990e363`
This used the pre-granted route.

**What changed.** README.md:178 now reads "Each thread harness (grok, opencode, muse) also has three browser functions, … `fork_muse_with_browser`; `CodexHost` has no browser functions yet (spec Q-19)." The `README_BULLET` constant in `tests/features/codex_host/test_codex_host_packaging.py` received the identical substring replacement in the same commit, and no other line of that file changed.

**How the edit was made.** The literal escapes `"` as `\"`, so I chose a replaced span that holds neither a quote nor a backslash.

**Checks:**
- an AST read confirmed that the constant equals README line 178 after CRLF→LF;
- the pin's guarded property, the sentence "callers import it and its module functions from `vidbyte.harnesses.native.codex`", is still present;
- the packaging test gives `7 passed`.

`git diff fb7be13e..HEAD --stat -- tests/` shows only `tests/features/codex_host/test_codex_host_packaging.py | 2 +-`. The before and after texts are in verify-log.md. The spec part (NG-2, Q-19) was already done in r5.

### R-6 (Major) — 12 new A002 boundary functions without `@intent` — fixed @`103a27a5` (and `_remove` @`4c686557`)
`s4verify/a002delta.py` keys findings by (file, name, categories), so it collapses the two `__post_init__` hits and reports 11. My `a002count.py` counts with multiplicity and finds the 12 the review lists.

Each now carries a 72-column `@intent` block that says why the rule exists:
- the three `_call`s: one `NativeThreadError` per failure (INV-6);
- `read_stream`: failures carry the thread Grok already named;
- `_install`: a broken install is never published;
- Muse `_server`: the verified entry shape (EC-39);
- opencode `_server`: the key travels only inside `OPENCODE_CONFIG_CONTENT` (INV-4);
- `_rules`: deny the server before the exact allows (AC-6);
- `BrowserToolDefinition.__post_init__`: a bad row fails at import;
- `BrowserServer.__post_init__`: the command matches the transport;
- `_checked_keys`: keys match the selected tools (AC-8);
- `_remove`: handled in R-3.

I also marked the four `_call`/`read_stream` sites that mirror #1036 siblings, keeping their blocks short, because the target was 0 new findings and a short block costs one line. Per-file A002 against the merge base is 21 → 21 (0 new), and the repo-wide count fell 574 → 562 (baseline 703, which I did not edit).

### R-7 (Minor, trivial) — `BrowserToolRequest.tools` in repr — fixed @`07ac09b6`
`tools: Sequence[str] = field(repr=False)`. The class docstring and the header's "do not drop repr=False" rule now name `tools`. `repr(BrowserToolRequest(tools=['playwright'], tool_keys={}))` gives `BrowserToolRequest()`. The registry and contract tests give `62 passed`.

### R-8 (Minor, trivial) — literals beside their constants — fixed @`e8e543a9`
The exit-code and count literals now use their constants:
- reaper.py `_windows_count` and `_kill_marked`: `NATIVE_SUCCESS_EXIT_CODE` and `NATIVE_REAP_NONE_COUNT`;
- `BrowserRuntimes.node`: `exit_code == native_threads.NATIVE_SUCCESS_EXIT_CODE`.

With that, `hostkit/browser.py` again holds no literal of its own. The only constant left is the neutral `""` that stands for "no node".

**Not changed, with evidence.** Both of reaper.py's `sys.platform == "win32"` checks keep the literal. With `NATIVE_WINDOWS_PLATFORM`, `py -3.11 -m mypy --platform win32 … reaper.py` reports `reaper.py:111: error: Module has no attribute "SIGKILL"`, because mypy narrows the platform only on the literal. `lib/process/runner.py` in the same folder uses the literal everywhere for the same reason. Two added comment lines at the check now say so, and mypy is clean on `--platform win32` and on `--platform linux`.

**Bullet left as is.** `killed = 0` (a counter's start) is left alone; the review did not list it.

### R-9 (Minor, trivial) — headers' TESTS lines — fixed @`31ae9ba4`
The TESTS lines of the six `{grok,opencode,muse}/{threads,wire}.py` headers now name `test_harness_threads_browser_mounts.py` and `test_harness_threads_browser_lifecycle.py`.

I gave this commit a `docs(harnesses)` title instead of `fix(...)`, because it changes header text only. Its title carries `[R-9]`, and I did not rewrite history to retitle it.

### R-10 (Minor, trivial) — `BrowserToolDefinition` validation gaps — fixed @`ece025b3`
The fix is a validation check in the dataclass, so it counts as trivial:
- `_checked_stdio` refuses a REQUIRED or OPTIONAL row whose `key_variable` is None, naming `BrowserToolDefinition.key_variable`;
- `_checked_remote` also refuses `arguments`, `profile_option`, `output_option`, `caps_option` and a non-empty `environment`.

All 13 registry rows still load. Probes of a keyed stdio row without a variable, and of a remote row with arguments, an environment or a caps option, were each refused; the unchanged rows were accepted. The records, registry and contract tests give `97 passed`.

### R-16 and R-17 — status only
I set them to `fixed @131b854f` and `fixed @5979eabb`, as the briefing directed. Their sibling tests are now named in the AC-13 and AC-28 Proof cells (`170c1284`).

### Spec edits (allowed set only)
- §17 deviations 4 and 13, for R-3 (`4c686557`).
- §6.2 Proof cells: AC-12 (the R-2 test and fix), AC-13 (`test_a_second_cancel_cannot_stop_the_cleanup`, R-16, R-3) and AC-28 (`test_opencode_never_counts_a_call_on_a_users_own_enabled_server`, R-17), in `170c1284`.
- In `f759c787`, the stale S3 "(red: …)" notes in the AC-3 and AC-12 Proof cells now read "red at S3 … green since the post-S3 repairs". Both tests pass in the area run.

The spec status stays `reviewed`, and nothing else in the spec changed.

## 3. Test changes proposed (BLOCKED)
None. The only test edit is the pre-granted `README_BULLET` constant.

## 4. Findings I believe are wrong
None. All ten were reproduced or confirmed against the code before I fixed them:
- R-1, by the scan;
- R-2, by the red test;
- R-3, by the chain script and the code;
- R-4, against the vendor facts and A-10;
- R-5, from the README text;
- R-6, by `a002count.py`;
- R-7 to R-10, by reading the code.

The one partial disagreement is R-8's `"win32"`. I resolved it inside the finding, with the mypy evidence above. I did not dispute the finding.

## 5. What remains open, and what I would try next
**Open items.** Nothing confirmed is open.
- The local inherited test stays red on every branch until main fixes its merge-base check. Do not fix it here.
- The follow-ups for S6 are R-11 to R-15, R-18 and R-19.

**Hypotheses not yet tried, for a later agent:**
- If the conformance re-review objects to the R-3 trade (an unbounded single `rmtree`), bound each try with `asyncio.wait_for(to_thread(...), max(deadline - loop.time(), BROWSER_REMOVE_PAUSE_SECONDS))` under the one `suppress(OSError, TimeoutError)`. Then re-run S064, S024 and the lifecycle file.
- If a reviewer wants `killed = 0` named too, use `NATIVE_REAP_NONE_COUNT`. It changes nothing at runtime.

**Interactions between fixes:**
- R-3 created the A002 hit on `_remove` that R-6 counts, so it was marked in the R-3 commit.
- R-6 and R-3 added comment blocks, and the R-1 scan was re-run after each fix.
- R-2 renamed two `@intent` markers. No test or lint reads marker names.
