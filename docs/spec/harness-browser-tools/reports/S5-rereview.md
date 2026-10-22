LENS: conformance (post-repair re-review)
VERDICT: SOUND — All ten repaired findings and both test additions hold against their evidence, and no fix contradicts spec r5, the user's words, AGENTS.md or the §8.4/§14 limits. Two new Minors remain, and both are optional follow-ups: one error text that the R-2 fix made slightly untrue, and one untested half of the r5 Grok evidence rule.

Reviewed: `git diff origin/main...e2fdf0e2`, file by file, with every hunk of `git diff d00bd8ba..e2fdf0e2` read inside its whole file. The yardsticks were spec r5, request.md §A–§D, test-plan.md, review.md, verify-log.md, reports/S5-repair-1.md and AGENTS.md. Local HEAD 7e4f0857 differs from e2fdf0e2 only in `pipeline.md`. `git diff e2fdf0e2 -- vidbyte tests lint REPO_MAP.md skills` is empty, and the working tree is clean.

WHAT THE IMPLEMENTATION GETS RIGHT (so nobody "fixes" what works)
- **The R-2 fix is exact.** Two parts:
  - `GrokWire.connected` (grok/wire.py:178) now reads only `available_commands.tools`.
  - `GrokBrowserHarness.missing` (grok/browser.py:129-130) adds only calls whose status is COMPLETED.

  The reader still records the failed call as `BrowserToolCall(..., status=FAILED)`, so `tool_calls` stays an honest log. I put the pre-R-2 rule back in memory (mutant M1), and the two new `never_listed` cases fail: `2 failed, 2 passed`. With the shipped rule, all 4 pass.
- **The R-3 cleanup is flat, and it is bounded by one deadline.** `complete` and `discard` compute `deadline` before the reap (hostkit/browser.py:294, 320). `_remove(folder, deadline)` (:358-371) is the only helper level, and the chain scan finds only main's `FailureCode` chain. An in-memory run of `_remove` against a folder that never goes away gave:

  | Deadline | Tries | Time |
  |---|---|---|
  | already passed | 1 | 0.0 s |
  | 10 s ahead | 5 | 1.06 s |
  | 0.3 s ahead | 3 | 0.42 s |

  When the deadline has already passed, one try of 1.5 s still runs. That is what EC-22 asks for: "The profile removal is still attempted" after a reaper timeout.
- **The repairs were surgical.**
  - Commits R-1, R-4, R-6 and R-9 change no code line, only `#` and header lines.
  - The test tree since `fb7be13e` differs in exactly one line, the pre-granted `README_BULLET`.
  - The PR still has 12 new files and 34 new classes, and every file maps to a §12.3 row.
  - `lint/`, `.github/`, `.semgrep/` and `pyproject.toml` are untouched.
  - CI run 39096073590 and Static policy run 39096074746 both succeeded with `headSha` e2fdf0e2.
- **AC-1 and the cancel path are real.** The acceptance `SNIPPET` is byte-identical to spec §4 (1385 characters each) and passes against the fakes. The shield in `execute` carries weight: I swapped `asyncio.shield` for the identity function inside hostkit/browser.py only, and `test_a_second_cancel_cannot_stop_the_cleanup` then fails for all three harnesses (`3 failed, 3 passed`). That confirms the R-16 commit's claim.

FIX CONFIRMATION
- R-1: CONFIRMED FIXED. The scan of the added `#` lines in `git diff -U0 origin/main...e2fdf0e2 -- 'vidbyte/*.py'` (484 lines) finds 0 over 72 columns. The field-guide check `awk 'length($0) > 72' | grep -E '^\s*#'` prints nothing for all 12 new files. A002 passes.
- R-2: CONFIRMED FIXED. Covered above: the code at grok/wire.py:178 and grok/browser.py:129-130, and mutant M1. Spec r5 FR-14, D-11, §9.1, AC-12, EC-16, EC-44 and EC-45 match the code word for word. One new Minor came with it: R-C1.
- R-3: CONFIRMED FIXED. `chains.py e2fdf0e2 <32 files>` finds only `FailureCode: from_exception -> _from_exception_name -> _from_exception_fallback`, which main already has. S064 4/4 and S024 25/25 hold, and the simulation above behaves as described. §17 deviations 4 and 13 match the code.
- R-4: CONFIRMED FIXED. The registry comment (registries/browser_tools.py:104-106), the constants comment (constants/browser_tools.py:174-175), the `select` narration and the README key rule and tavily row now all say the server "starts without the key but answers no call without it" (A-10).
- R-5: CONFIRMED FIXED. An AST read shows that README line 178 equals `README_BULLET` and contains "`CodexHost` has no browser functions yet (spec Q-19)". `REPO_MAP_SECTION` is still in REPO_MAP.md. The packaging test gives 7 passed. The spec part (NG-2, Q-19) is in r5.
- R-6: CONFIRMED FIXED. `a002count.py` reports 21 → 21 against merge base 6f5a7310 (0 new) and 33 → 21 against d00bd8ba. Repo-wide A002 is 703 → 562.
- R-7: CONFIRMED FIXED. `repr(BrowserToolRequest(tools=["playwright", "fc-0123…"], tool_keys={}))` returns `BrowserToolRequest()`.
- R-8: CONFIRMED FIXED. `NATIVE_SUCCESS_EXIT_CODE` is used at hostkit/browser.py:132 and reaper.py:94,105, and `NATIVE_REAP_NONE_COUNT` at reaper.py:95,97,106. mypy is clean on reaper.py for both `--platform win32` and `--platform linux`. The kept `"win32"` literal follows runner.py, which uses it 7 times. (b) is judged acceptable; see VERIFIED CLAIMS.
- R-9: CONFIRMED FIXED. The TESTS lines of all six `{grok,opencode,muse}/{threads,wire}.py` headers name the browser mounts and lifecycle files. The commit type `docs(harnesses)` is accurate for a change to header text only, so (c) is not a defect.
- R-10: CONFIRMED FIXED. All 13 registry rows load, and the registry tests give 40 passed. Probes behaved as follows:
  - a stdio OPTIONAL row with `key_variable=None` is refused (`BrowserToolDefinition.key_variable`);
  - a remote row with arguments, an environment, `caps_option`, `profile_option` or `output_option` is refused;
  - unchanged rows and a NONE-rule stdio row are accepted.

  So the checks refuse only rows that are invalid; that answers (d).
- R-16: CONFIRMED FIXED (commit 131b854f). The noshield mutation fails all 3 cases of the new test. With the shipped code, lifecycle gives 33 passed, 1 skipped (the POSIX-only reaper test).
- R-17: CONFIRMED FIXED (commit 5979eabb). The new test enables the user's `playwright`, which runs a real fake server. It checks from the fakes' logs that this server connected and answered, and that `tool_calls` holds only the `vidbyte-playwright` call; the `alone` case raises `browser.tools_unavailable`. Mounts gives 51 passed. I did not re-run the mutant that also accepts unprefixed ids; the commit records its result as `2 failed, 1 passed`.

FINDINGS (ranked, most severe first)
R-C1 [Minor] [conformance / regression from R-2] vidbyte/lib/constants/browser_tools.py:398 — After R-2, the Grok `tools_unavailable` observation says the output shows no call on a server whose failed call the SDK itself recorded
  Evidence:
  - Line 398: `BROWSER_TOOLS_UNAVAILABLE_DETAIL = "The vendor's output shows neither a connection to nor a call on these mounted servers, so no mounted tool was used on them: {servers}."` It is used for every harness at hostkit/browser.py:288.
  - An in-memory reproduction of the new R-2 case (jina is mounted, not listed, and `jina__read_url` answers "Tool not found" with status failed) printed:
    - `GrokWire.tool_calls` → `(BrowserToolCall(tool=<BrowserTool.JINA: 'jina'>, name='read_url', status=<BrowserToolCallStatus.FAILED: 'failed'>),)`;
    - `missing` → `(<BrowserTool.JINA: 'jina'>,)`;
    - and the detail text above.
  Failure: Grok mounts a server that never connects, and the model calls its tool. The error then tells the caller that the output shows no call on that server, although the stream shows one and the SDK's own reader attributes it to that server. Before R-2 this path did not exist, because any call made a server count, so the sentence was exactly true. It breaks the error-message doctrine that every field must reflect the actual runtime conditions (agentic-engineering error_messages.md, "Do not fabricate any error message data"). The likely cause and the next step remain correct, so behavior does not change.
  Smallest fix: one word in the constant: "…shows neither a connection to nor a completed call on these mounted servers, so no mounted tool was used on them: {servers}." It stays true for opencode, which raises only when there are no calls at all. It also keeps the substring "no mounted tool was used" that the opencode tests look for (lifecycle :45, mounts :358). No test pins the rest of the sentence.
  Spec IDs: FR-14, D-11, D-29, INV-6, EC-16, EC-45.

R-C2 [Minor] [conformance / test coverage] vidbyte/harnesses/native/grok/browser.py:129-130; docs/spec/harness-browser-tools/test-plan.md:91 — The positive half of the r5 Grok rule (an unlisted server counts once a call to it completed) has no test
  Evidence:
  - Spec r5 EC-16 says: "A call the model makes to it anyway counts only if it completed". FR-14 says: "listed in `available_commands` or have completed a call".
  - Mutant M2 replaces `missing` with `seen = set(GrokWire.connected(run.outcome, mount))`, which drops the completed-call evidence. It survives every browser file that runs Grok:
    - lifecycle: `33 passed, 1 skipped`;
    - mounts: `51 passed`;
    - contract: `22 passed`;
    - fakes: `10 passed`.
  - The fake Grok cannot express the case. At fake_browser.py:644 a `grok_unlisted` server is never started, so every call to it is "Tool not found". The test plan's not-tested row for EC-16 (:91) cites wall-clock dependence, which does not apply to this half: the half needs no timing, only a server that is left out of `available_commands` but answers calls.
  - The shipped code does handle the case: the in-memory run with the call set to completed gives `missing → ()`.
  Failure: a later refactor can drop the completed-call branch with all tests green. Then a Grok server that connects after the last `available_commands` event (EC-16), or any server at all if a Grok release stops printing `available_commands`, turns a finished, paid run into `browser.tools_unavailable`.
  Smallest fix (test author; changes the test tree):
  1. Add a fake-Grok scenario key, for example `grok_listed_late: [tool]`, that starts the server and answers its calls but leaves its tools out of `available_commands`.
  2. Add one success case that calls the tool and expects a `BrowserThreadResult` holding the COMPLETED call.
  3. Narrow the test-plan EC-16 row to the timing half only.
  Spec IDs: FR-14, D-11, EC-16, AC-12.

VERIFIED CLAIMS
Each claim, and whether it held:
- HELD: the test tree changed only the pre-granted line after `fb7be13e` (verify-log, briefing). `git diff fb7be13e..e2fdf0e2 --stat -- tests/` shows `tests/features/codex_host/test_codex_host_packaging.py | 2 +-`. The changed line is `README_BULLET`. Since d00bd8ba, 0 `assert` lines were removed. The three test commits (8b02afdd, 131b854f, 5979eabb) only add cases or tests. 8b02afdd keeps the old `[playwright]` and `[jina]` node ids and adds a log check, so a case cannot pass without the guessed call.
- HELD: the §8.4 budget. An AST count over `origin/main...e2fdf0e2` finds 12 added files and 34 new classes. The largest file, constants/browser_tools.py, has 405 lines. The non-test, non-docs files changed are exactly §12.3 rows 1–37.
- HELD: §14 "Never".
  - `lint/baseline.json` and `lint/` are unchanged.
  - No `noqa`, `type: ignore`, `nosec` or `nosemgrep` was added. The only added skip markers are S2's two platform `skipif`s (POSIX `ps`, win32 `.cmd`), which are legitimate.
  - The vidbyte diff adds no `npx`, `@latest` or approve-all mode.
  - The repair commits do not touch `pipeline.md`; only orchestrator commits 2ea367e4, a34436c2 and 36366afa do.
- HELD: the lint ratchets on the reviewed tree:

  | Rule | Result |
  |---|---|
  | A002 | 703 → 562, PASS |
  | S064 | 4 known |
  | S024 | 25 |
  | A007 | 255 |
  | A006 | 34 |
  | S061 | 6 → 5, PASS |

  Each run ends with `SDK-LINT: PASS`.
- HELD: AC-1 / §4. The `SNIPPET` equals the §4 block byte for byte (checked by AST extraction), and `test_harness_threads_browser_acceptance.py` gives 1 passed. The §5 diagram matches the code: `execute` (hostkit/browser.py:67-110) runs register_secret, `select`, `check`, `prepare`, then `run`, `tool_calls`, `require(missing)` and `complete` inside the `try`, and on any failure a shielded `discard` and a re-raise.
- HELD (judgment on briefing (a), R-3 against INV-12): INV-12 says "within `BROWSER_REAP_TIMEOUT_SECONDS`, to kill … and to remove the profiles; that removal is best effort (EC-22)". EC-22 says the removal "is still attempted" after a reaper timeout. Both cannot hold when the reap uses the whole budget. Running one try at the deadline follows EC-22, and the overshoot is bounded by at most one pause plus one `rmtree` per `_remove` call. `complete` with no artifacts calls `_remove` twice, so the worst case there is two first tries, not the "one rmtree" the repair report states. That is a small understatement in the report, not in the spec or the code. The unbounded case, a hung `rmtree`, is no worse than S3: a timed-out `to_thread` never stopped the thread either. A shielded `discard` also does not block a caller that cancels.
- HELD IN PART (briefing (b), R-8): the mypy reason applies only to `_kill_marked` (reaper.py:105), where `signal.SIGKILL` sits behind the check. The check in `reap` (reaper.py:41) guards no platform-only attribute, so there it is kept for consistency with runner.py, not because mypy needs it. This does not change behavior, so it is not a finding.
- HELD (briefing (d), R-10): see FIX CONFIRMATION.
- HELD: the R-16 mutation claim (noshield gives 3 failed), re-run independently.
- HELD: the R-2 red-then-green claim (mutant M1 gives `2 failed, 2 passed`; shipped code gives `4 passed`), re-run independently.
- HELD: R-6's "0 new A002". Re-counted with multiplicity: 21 → 21 against the merge base.
- HELD: no fix made an open follow-up worse. R-11 to R-15, R-18 and R-19 are in code that S5 did not touch, except for the comment-only `_server` and `_rules` @intent blocks. R-18 still parses Grok's output three times: R-2 removed a branch, not a parse.
- HELD: the IDs the repairs touched, walked one at a time:
  - FR-14 and D-11: code = spec. EC-16: held in code; the test half is R-C2.
  - EC-44: a skipped name never enters `calls`, so it is never evidence. EC-45 and AC-12 are held, with tests.
  - INV-12, AC-13 and FR-15 are held (judgment above, plus tests).
  - AC-28 and EC-40 are held (new test).
  - T-1 is held (R-7, plus the existing no-quote checks).
  - A-10 is held (R-4).
  - NG-2, Q-19, §2 and G-5 are held (R-5).
  - INV-14 and INV-16 are held: the S5 diffs to `threads.py` are header-only, the wire diffs touch only the browser `connected` path and comments, and `native_threads.py` changed comments only.
  - INV-15 is held: hostkit/browser.py's only remaining literal is the `""` sentinel for "no node", unchanged since S3.
- HELD: the user's words. Every weighted word holds for the three thread harnesses on every path, with three exceptions, all disclosed:
  1. "every harness … so far in the repo" does not hold for `CodexHost`. That decision is already made (Q-19), and it is now disclosed in README:178 and spec §2/NG-2/Q-19. S6 must name it in the PR body.
  2. "15-20 popular ones" is 13 mountable tools (Q-16).
  3. Muse in WSL mode gets no browser (Q-15).

  The repairs reversed no §C decision and added nothing that was not asked: the repr hiding and the row checks are hardening of existing records.
- HELD: deviations. §17 deviations 4 and 13 are accurate after R-3. R-7 (`tools` repr=False) and R-10 (stricter `BrowserToolDefinition` rules) go beyond the §9.1 Rules column without a §17 line. Both only refuse more, contradict no rule, and are recorded in review.md, so I judged them hardening, not unreported deviations.
- HELD: remote gates on e2fdf0e2. `gh run view 39096073590` returned `{"conclusion":"success","headSha":"e2fdf0e2…","name":"CI"}`, and `gh run view 39096074746` returned `{"conclusion":"success",…,"name":"Static policy"}`.
- NOT RE-CHECKED: NG-2's claim that Claude Code's #1044 "was closed without merging". It is absent from `origin/main`, and its state on GitHub was not queried.

COMMANDS RUN
Each command, with its final lines. All Python runs used `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH=$(pwd)` from the worktree root; pytest also used `-p no:cacheprovider`.
- `git log --oneline -40`; `git status --short`; `git diff --stat d00bd8ba..e2fdf0e2`; `git diff d00bd8ba..e2fdf0e2 -- vidbyte/` (read fully); `git diff --name-status origin/main...e2fdf0e2`.
- `git diff fb7be13e..e2fdf0e2 -- tests/` → 1 file, `README_BULLET` only.
- `git diff origin/main...e2fdf0e2 --stat -- lint/ .github/ .semgrep/ pyproject.toml` → empty.
- `git show -U0 <8286f1aa|103a27a5|31ae9ba4|36e5129e> -- 'vidbyte/*.py'`, filtered to non-comment lines → empty for each commit.
- R-1 scan over the added comment lines → no output (484 added comment lines). The field-guide awk over the 12 new files → no output.
- `py -3.11 scratchpad/s4verify/chains.py e2fdf0e2 <32 files>` → `vidbyte/lib/enums/failure.py :: FailureCode: from_exception -> _from_exception_name -> _from_exception_fallback`.
- `py -3.11 scratchpad/s5/a002count.py 6f5a7310 <32 files>` → `A002 at 6f5a7310: 21  in working tree: 21` · `NEW in working tree: 0`. Against d00bd8ba: `33 → 21`, `NEW: 0`.
- `py -3.11 lint/run.py --rule <A002|S064|S024|A007|A006|S061>` →
  - `A002 IMPROVED 703 -> 562`;
  - `S064 RATCHETED: 4`;
  - `S024 RATCHETED: 25`;
  - `A007 RATCHETED: 255`;
  - `A006 RATCHETED: 34`;
  - `S061 IMPROVED 6 -> 5`.

  Each ends `SDK-LINT: PASS`.
- `py -3.11 -m mypy --platform <win32|linux> --follow-imports=silent --cache-dir=nul vidbyte/lib/process/reaper.py` → `Success: no issues found in 1 source file` (both platforms).
- In-memory checks with `py -3.11 -` (no files written):
  - R-7: `repr` → `BrowserToolRequest()`.
  - R-10: 13 rows load; 6 bad probes refused; 3 good probes accepted.
  - R-3: the `_remove` simulation → `(1, 0.0)`, `(5, 1.06)`, `(3, 0.42)`, `(1, 1.5)`, `(1, 1.0)`.
  - R-C1 and R-C2: the Grok reader reproduction → `missing: (jina,)` for the failed call, and `missing: ()` for the completed call.
  - R-5: README line 178 == `README_BULLET` → `True`; `REPO_MAP_SECTION` in REPO_MAP → `True`.
  - AC-1: SNIPPET == spec §4 → `identical: True 1385 1385`.
- Mutant M1 (pre-R-2 `missing`), `pytest …browser_lifecycle.py -k never_listed` → `FAILED …[playwright-only-call-failed]`, `FAILED …[jina-only-call-failed]`, `2 failed, 2 passed, 30 deselected in 3.85s`.
- Mutant M2 (listed-only `missing`):
  - `pytest …lifecycle.py …mounts.py -k grok` → `31 passed, 54 deselected`.
  - Then one file at a time: lifecycle `33 passed, 1 skipped in 49.50s`; mounts `51 passed in 49.55s`; contract `22 passed in 7.04s`; fakes `10 passed in 1.52s`.
- Mutant noshield (`asyncio.shield` replaced by the identity function in hostkit/browser.py only), `pytest …lifecycle.py -k cancel` → `FAILED …test_a_second_cancel_cannot_stop_the_cleanup[grok|opencode|muse]` · `3 failed, 3 passed, 28 deselected in 53.55s`.
- Shipped code, one file at a time:

  | File | Result |
  |---|---|
  | browser_acceptance | `1 passed in 3.57s` |
  | codex_host packaging | `7 passed in 2.68s` |
  | browser_registry | `40 passed in 1.10s` |
  | browser_runtime | `26 passed in 15.49s` |
  | static_policy | `3 passed in 0.22s` |
  | records | `35 passed in 0.83s` |
  | browser_lifecycle (with `-rs`) | `SKIPPED [1] …:171: the POSIX reaper reads NATIVE_PS_PATHS; win32 uses System32 PowerShell` · `33 passed, 1 skipped in 46.82s` |
  | browser_mounts | `51 passed in 60.13s` |
- `gh run view 39096073590 --json conclusion,headSha,name,status` → `success`, `e2fdf0e2…`, `CI`. `gh run view 39096074746 …` → `success`, `e2fdf0e2…`, `Static policy`.
- Not run, by instruction: the real §4 snippet (it would be a paid call), the whole `tests/` suite, `scripts/run_ci.py` and any vendor CLI. The orchestrator's area run and the CI run cover those.
