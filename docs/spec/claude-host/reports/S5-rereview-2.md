LENS: conformance
VERDICT: SOUND — R-22 and R-23 are fixed exactly as the verifier specified, and spec r6 now describes the code. The four new tests fail on the old code for the right reasons, and every iteration 1 fix still holds; only two Minors remain, and neither changes behaviour.

Scope of this re-review:
- The repair commits b5989730 [R-22] and 2c537b1a [R-23], which change only `vidbyte/harnesses/native/claude/session.py`.
- The 4 new tests in `test_claude_host_review_gaps.py`.
- Spec r6 (9211d4ef).
- Iteration 1's fixes, re-checked at 490e627b.

Local HEAD deafe420 adds only `pipeline.md`. `git diff --stat 490e627b HEAD -- vidbyte tests lint pyproject.toml REPO_MAP.md` is empty, and the tree is clean.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **The yield sits where deviation 14 and row 7 put it.**
  - It is now the opening of `_take_steer` (session.py:261-262): `if self._steer is not None: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)`. The take follows at :263, and the pump awaits it at :173.
  - So the message is still in its slot during the one pass. A caller interrupt (:492), the session's close under `aclose` (:508), the time budget (:381) or a failed steer interrupt (:395-396) can each still withdraw it.
  - The yield is gone from `_query` (:228-234), which now does only its docstring's job.
  - The call depth is unchanged. `run → _take_steer` already existed, and the only calls inside `_take_steer` are to the standard library.
  - Do not move the yield back after the take. The `yield_after_take` variant fails all three StopInSteerWindowTests.
- **The R-23 reset is complete and correctly bounded.**
  - It clears exactly the seven per-result fields of `ClaudeTurnResult` (claude_host.py:112-121): `result_text`, `structured_output`, `num_turns`, `duration_ms`, `stop_reason`, `terminal_reason` and `permission_denials`.
  - It runs only inside `if steer is not None:`, after the take, so a steer withdrawn in the window leaves the first result as the handle's.
  - It keeps `session_id`, which the busy guard reads at host.py:202 and :392, plus `hooks_applied`, and `total_cost_usd` for INV-20. `_outcome` is untouched, and R-1's guard (failures.py:183) already ignores the outcome's result fields.
  - Moving the reset before the yield is wrong: the `reset_before_yield` variant fails P3 with `('completed', '') != ('completed', 'The first answer.')`.
- **The four new tests discriminate, each through its own stop path.**
  - At 615fc54a they fail with:
    - P1: `None != 'action.precondition_failed'`;
    - P2b: the same message;
    - P3: `Lists differ: [..., 'focus on tests'] != [...]`;
    - R-23: `Tuples differ: ('The parser bug is fixed.', …) != ('', None, None, None, '', '', ())`.
  - Each test is tied to its own stop path:
    - Removing `close()`'s `_steer = None` fails only P2b.
    - Removing `interrupt()`'s fails P1, plus the original PendingSteerDiscardTests.
    - Removing the withdrawal in `_interrupt_client` fails P3, plus SteerWithdrawalTests.
    - Dropping any one of the seven reset fields fails SteeredResultFieldsTests, and so does adding `total_cost_usd=None` to the reset.
- **The contracts and every earlier fix still hold.**
  - Since S2 (9a8ecc3c) the claude_host test tree has additions only: `23 0`, `4 0` and `377 0`. Iteration 2 added `6 0`, `2 0` and `76 0`.
  - `lint/baseline.json` is untouched, and the PR adds no suppression.
  - The marker blob SHA-256 is `0374a2c8…942f497a`.
  - The 31 non-test paths split into 22 added and 9 modified files, with 4077 lines added and 0 deleted.
  - The R-7 mutants M1–M4 are each still killed.

FINDINGS (ranked, most severe first, max 15)

R-C4 [Minor] [verify-claims / test coverage of R-23's kept fields] tests/features/claude_host/test_claude_host_review_gaps.py:358-373 (code: vidbyte/harnesses/native/claude/session.py:266-269) — SteeredResultFieldsTests pins only one of the three fields R-23 keeps. A reset that also clears `session_id` passes 181/181 and breaks INV-4 during a steered prompt.
  Evidence:
  - The code comment claims all three stay (session.py:266-268): "the session id, the hooks flag and the cumulative cost stay". The test asserts only `result.total_cost_usd == 0.008` (:373).
  - Variant runs (`swap.py`, the HEAD source exec'd into the real session module with one edit):
    - `reset_plus_session` → `181 passed`;
    - `reset_plus_hooks` → `181 passed`;
    - control `reset_plus_cost` → `1 failed, 180 passed`.
  - `probe_kept_fields.py`: a spawn with a chosen session id, steered, and checked while the steered prompt is still running:
    - HEAD → `{'status': 'running', 'session_id_kept': True, 'busy': 'continue refused: claude.session_busy'}`;
    - `reset_plus_session` → `{'status': 'running', 'session_id_kept': False, 'busy': 'continue ADMITTED on the live session: 6a000e75'}`.
  Failure:
  - **Today:** no wrong outcome. HEAD keeps all three fields.
  - **The unguarded risk:** a later edit that "clears the interrupted result" more completely would pass the pack. That edit would do two things:
    - Blank the `session_id` that `_on_result` writes. The host's busy guard reads `snapshot().session_id` (host.py:202, :392), so a continue on the same session would be admitted while the steered prompt runs, and two processes would write one transcript. That breaks INV-4 and EC-11.
    - Drop `hooks_applied`, which would break FR-25 after a steer.
  Smallest fix: one more assertion in the existing test, `self.assertEqual(result.session_id, handle.session_id)`. Optionally, also assert `hooks_applied` on a request that registers a hook. This adds no new test class and changes no existing test.
  Spec IDs: INV-4, EC-11, FR-25 (unguarded on the steer path); R-23

R-C5 [Minor] [deviations not recorded] docs/spec/claude-host/spec.md:1157 (§12.3 row 7) — neither row 7's pump sequence nor §17 describes R-23's reset of the result fields when the steer is taken.
  Evidence:
  - Row 7 r6 reads: "→ if the message is still in its slot, take it, `query(message)` and continue, else stop".
  - `grep -n "R-23\|result fields" spec.md` finds no description of the reset. r6 (9211d4ef) predates 2c537b1a.
  - The code at session.py:264-269 applies `replace(self._result, result_text="", …, permission_denials=())` at the take.
  Failure: the behaviour conforms to D-3 ("that next result is the handle's") and AC-9. But it changes what a live `get_claude_turn_result` shows during a steered prompt: empty result fields instead of the interrupted prompt's. A reader of row 7 cannot learn this. Round 1 held the same standard for the yield (R-24).
  Smallest fix: spec text only. Append to row 7's take step: "and clear the interrupted prompt's result fields (text, structured output, turns, duration, stop and terminal reasons, denials), keeping the session id, `hooks_applied` and the cumulative cost (D-3, INV-20)". Alternatively, add one sentence to deviation 14. No code change.
  Spec IDs: §12.3 row 7, §17, D-3

VERIFIED CLAIMS:
- **R-22: the yield moved before the take, and the steered prompt still follows its interrupt.** Held.
  - The code at session.py:173 and :253-263 matches deviation 14 and row 7.
  - The repair's probe set, re-run against HEAD (`repair2/probe_fixed.py`):
    - P1 → `raised action.precondition_failed`, calls `[…, 'receive_messages', 'interrupt', 'disconnect']`, final `('interrupted', None, 'The first answer.')`;
    - P2b → `raised action.precondition_failed`, with one query;
    - P3 → `raised claude.process_exited`, with one query, final `('completed', None, 'The first answer.')`;
    - P4 → `raised action.precondition_failed`, final `('failed', 'claude.budget_exhausted', 'The first answer.')`.
  - The R-2 control gives `[…, 'interrupt', 'query', 'disconnect']` → `('completed', None, 'steered answer')`.
  - P2a (aclose scheduled after `finish()`) still sends the steered prompt before close. That is the verifier's refuted ordering, so it is not re-raised.
- **"P4 has no committed test" is not a coverage hole.** Held.
  - The `watch_keeps_steer` variant is killed by `PendingSteerDiscardTests::test_the_time_budget_discards_a_pending_steer`.
  - The window placement is pinned by P1, P2b and P3. A plausible P4 regression would therefore fail an existing test.
- **The red runs.** Held. At 615fc54a, all four new tests fail (`4 failed, 177 passed`). At b5989730, only SteeredResultFieldsTests fails (`1 failed, 180 passed`). With no yield at all, SteerInResultWindowTests also fails (`4 failed`).
- **`CLAUDE_STEER_YIELD_SECONDS = 0` at constants/claude.py:54 (row 14).** Held.
  - It has a one-line reason comment.
  - `git grep STEER_YIELD` finds only the constant and session.py:35 and :262.
  - No stale "yields once before it sends" text remains in vidbyte, tests, lint or REPO_MAP.md.
- **EC-52 and row 12 as revised in r6.** Held.
  - The code is session.py:340-342. An unknown type, status or overage status is skipped, and an absent overage status is recorded.
  - `RateLimitRuleTests::test_a_window_with_an_unknown_status_or_overage_value_is_skipped` passes.
- **Iteration 1's fixes.** Held.
  - R-1: the guard is at failures.py:183, after the assistant-error loop.
  - R-2: SteerInResultWindowTests passes.
  - R-3: SdkRecordDriftTests passes.
  - R-5: ContinueRacingCloseTests passes.
  - R-6 and R-12: the RateLimitRuleTests pass.
  - R-7: M1 to M4 give `1 failed` (RateLimitRuleTests), `1 failed` (RateLimitRuleTests), `2 failed` (SteerWithdrawalTests and StopInSteerWindowTests P3) and `1 failed` (CancelledCloseTests).
  - R-10: `git grep "def whole\|\.whole("` finds nothing.
  - R-11: `match kind:` is at history.py:109.
  - R-13 and R-14: host and tools are unchanged since 615fc54a, because `git diff 615fc54a 490e627b -- vidbyte` touches only session.py.
  - R-4, R-8 and R-9: deviations 1, 12 and 13 are present in r6.
- **AC-1.** Held. The §4 snippet, extracted from spec.md and exec'd verbatim under the fake seam with `which` patched, prints `completed Answer: List the TODO comments in this repository.` and then `0.0123`. Both clients get `cli_path` `C:/fake/claude/bin/claude.exe`. With `locate_cli` returning "", it prints `claude.not_installed Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.`, with 0 clients.
- **Gates.** Held.
  - The pack gives `181 passed`, and lint gives `SDK-LINT: PASS`.
  - Remote runs 38519522362 (CI) and 38519524093 (Static policy) both report `success` at headSha 490e627b.
  - main is 8387d666, which is an ancestor of the branch, so no catch-up merge is needed.
  - The PR is still a draft, with head 490e627b.
- **The repair report's "no existing test changed".** Held. `git diff --numstat 615fc54a 490e627b -- tests` gives `6 0`, `2 0` and `76 0`, all additions.
- **Comment width.** Held. No `+` comment line in `git diff 615fc54a 490e627b -- vidbyte` passes 72 columns.
- **Not a finding (outside this lens).** The test file's A001 PURPOSE and ROLE lines still list only R-1 to R-12, although FEATURE.md and README.md record R-22 and R-23.

COMMANDS RUN:
- `git status --short`; `git log --oneline -15`; `git diff --stat 490e627b HEAD -- vidbyte tests lint …` → empty; `git diff --stat 615fc54a 490e627b -- …` → 4 files (session.py, FEATURE.md, README.md, review_gaps).
- `git show b5989730 -- vidbyte`; `git show 2c537b1a -- vidbyte`; `git diff -U0 c6039bb7 9211d4ef -- spec.md` → 7 hunks (frontmatter, EC-52, rows 7/12/14, review log, revision row, deviation 14).
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` → `181 passed in 5.48s`.
- `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` → `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` / `exit=0`.
- `swap.py <variant> <pack>` (scratchpad/rereview2; exec into the real module, restored after each run, and no worktree file written):
  - head → `181 passed`;
  - 615fc54a → `4 failed, 177 passed`;
  - b5989730 → `1 failed, 180 passed`;
  - noyield → `4 failed, 177 passed`;
  - yield_after_take → `3 failed, 178 passed`;
  - yield_always → `181 passed`;
  - reset_before_yield → `1 failed, 180 passed`;
  - no_reset → `1 failed, 180 passed`;
  - reset_plus_cost → `1 failed, 180 passed`;
  - reset_plus_session → `181 passed`;
  - reset_plus_hooks → `181 passed`;
  - close_keeps_steer → `1 failed, 180 passed`;
  - interrupt_keeps_steer → `2 failed, 179 passed`;
  - watch_keeps_steer → `1 failed, 180 passed`;
  - no_withdraw → `2 failed, 179 passed`;
  - reset_minus_<each of 7 fields> → `1 failed, 180 passed` each.
- `swap.py 615fc54a|reset_before_yield <gaps file> --tb=line` → the assertion messages quoted above.
- `scratchpad/mutant.py $W M1..M4` → each killed (see VERIFIED CLAIMS).
- `repair2/probe_fixed.py` → the P1, P2a, P2b, P3 and P4 results and the R-2 control, as quoted.
- `rereview2/probe_kept_fields.py head reset_plus_session` → as quoted in R-C4.
- `rereview2/snippet.py` → the AC-1 output quoted above.
- Contracts:
  - `git diff --numstat origin/main...490e627b -- tests` → 14 files, all `N 0`;
  - `git diff origin/main...490e627b -- lint/baseline.json | wc -l` → `0`;
  - `git show 490e627b:vidbyte/harnesses/native/__init__.py | sha256sum` → `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`;
  - `git diff --name-status origin/main...490e627b -- . ':!tests' ':!docs'` → `22 A`, `9 M`; numstat → `added 4077 deleted 0`;
  - suppression grep on added lines → none.
- `gh run view 38519522362|38519524093 --json conclusion,headSha` → `success`, `490e627b…`; `gh api …/commits/main` → `8387d666…`; `gh api …/pulls/1044` → `draft: true`, head `490e627b…`.
