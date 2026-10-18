# S5 findings verifier, round 2 (scoped, final): codex-host

Stage: the S4 findings verifier, run after the S5 final re-review round 2.
- **Code under review:** `origin/main...7b05e68b`. Local HEAD b1cca482 adds only docs; `git diff --quiet 7b05e68b HEAD -- vidbyte tests lint` is clean.
- **Input:** one review, `reports/S5-rereview-2.md` (conformance lens, R-C5..R-C7). The other two lens slots are n/a in this scoped round.
- **Output:** `review.md`, with rows R-30..R-32 appended, and this report.
- **Scripts:** in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/codex-verifier-r2/` (`$V` below):
  - `a002_revs.py`
  - `probe_interrupt_windows.py`
  - `mutant_pack.py`
  - `a002_fix_in_memory.py`
- **Environment:** `$W` is the worktree, and `$PY` is `C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python.exe`.
- **No side effects:** no real `codex` binary was started, and every mutant and fix was built in memory. `git status --short` showed only `review.md` and this report afterwards.

## Verdict

**MERGEABLE AFTER FIXES.** The round has one confirmed Major (R-30), two Minors (R-31 trivial, R-32 follow-up), 0 refuted and 0 downgraded. One sub-claim was trimmed (an NFR-5 cite), and one was widened (R-31's window also covers Vidbyte's own stop after its bound).

## Merge map

| Original | Proposed severity | Merged ID | Final severity | Result |
|---|---|---|---|---|
| R-C5 | Major | R-30 | Major | CONFIRMED (NFR-5 cite trimmed) |
| R-C6 | Minor | R-31 | Minor | CONFIRMED and widened (verifier probe C6c); trivial, comment-only |
| R-C7 | Minor | R-32 | Minor | CONFIRMED; follow-up, tests-only |

**No merges.** The review has one input, and its three findings have three different failures:
- R-C5 is a lint marker;
- R-C6 is comment text that describes a window wrongly;
- R-C7 is a test gap.

R-C5 and R-C6 touch the same comment block (host.py:401-404), so their fixes are bundled into one edit. They stay separate rows, because each would be wrong without the other: the marker alone keeps the false wording, and the rewording alone keeps the A002 finding.

## R-30 (R-C5): `interrupt_codex_turn` has A002's `send` token and no `# @intent`. CONFIRMED, Major.

### The code
At 7b05e68b, host.py:400-415:
- `async def interrupt_codex_turn` is at line 400.
- The comment block at 401-404 has no `@intent` line.
- `await turn.send_stop(self._connection, operation)` is at line 415.

### The rule
`lint/rules/a002_intent_comments.py`:
- `POLICY_TOKENS["send"] = "external boundaries"` (:44).
- `_categories` splits every `Name` and `Attribute` identifier on `[_\.]+` (:69-75), so `send_stop` yields `send`.
- `_has_intent` scans `lines[lineno-4 : lineno+20]` (:77-80).
- The rule is `severity = "blocking"`, and its `how_to_fix` asks for `# @intent <short-name>` followed by the invariant.

### Analyzer at eight revisions
I wrote my own script, `$V/a002_revs.py`. It runs `IntentAnalyzer().analyze` on each branch `.py` file, read with `git show <rev>:<path>`, so nothing in the worktree changes:
```
origin/main ["base.py:160 __init__ ['retries']", "base.py:250 __init__ ['external boundaries']", "base.py:265 …", "base.py:274 …"]
bbaa5a8b    [base.py ×4 only]
30109e89    [base.py ×4 only]
736d4a58    [base.py ×4 only]
ad363725    ["host.py:400 interrupt_codex_turn ['external boundaries']", base.py ×4]
3d26abfe    [same as ad363725]
77c92838    [same]
7b05e68b    [same]
```
- The host.py:400 finding first appears at ad363725, the R-27 fix.
- The four base.py hits are main's own `__init__`s, shifted by one line by the branch's edit at lines 143 and 151.

### The gate's own output
`cd $W && PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py --rule A002 --all --format json`, filtered to the 27 files in `git diff --name-only origin/main...7b05e68b -- vidbyte`:
```
found 580 baseline 703 verdict IMPROVED listed 580
BRANCH-FILE vidbyte/harnesses/native/codex/host.py 400 interrupt_codex_turn {'categories': 'external boundaries'}
BRANCH-FILE vidbyte/lib/errors/base.py 161 __init__ {'categories': 'retries'}
BRANCH-FILE vidbyte/lib/errors/base.py 251 __init__ {'categories': 'external boundaries'}
BRANCH-FILE vidbyte/lib/errors/base.py 266 __init__ {'categories': 'external boundaries'}
BRANCH-FILE vidbyte/lib/errors/base.py 275 __init__ {'categories': 'external boundaries'}
```

### Why the claim was false
The text form of the same command, without `--format json`, ends:
```
A002   intent-comments                           580    703 IMPROVED

A002 IMPROVED 703 -> 580. Lower it with: python lint/run.py --rule A002 --update-baseline

SDK-LINT: PASS
```
`| grep -c interrupt_codex_turn` on that output gives `0`. So S5-repair-2.md:34 ("A002 lists nothing under the branch's paths") and verify-log.md:229 were written from a view that cannot show per-path findings. Verify-log.md:131 is iteration 1's claim at bbaa5a8b. It was true then, as the bbaa5a8b row above shows.

### Is the false claim false anywhere else?
- **The run.** `lint/run.py --all --format json`, all 90 rules, took 36 s and gave `exit_code 0` with no verdict outside PASS, IMPROVED or RATCHETED.
- **The filter.** I filtered it to the line numbers the branch added, taken from the `+` hunk ranges of `git diff -U0 origin/main...7b05e68b -- vidbyte`. On added lines it lists:
  ```
  A002 IMPROVED 580 703 ADDED-LINE vidbyte/harnesses/native/codex/host.py 400 interrupt_codex_turn
  C011 RATCHETED 2 2 ADDED-LINE vidbyte/harnesses/native/codex/turns.py 357 CodexTurnRegistry._add:UsageTracker()
  ```
- **Every other row in a branch file is on an old line.** They are A001 in two `__init__` files, A002 and A003 in `lib/errors/base.py`, and S062 in `agents/codex/tools.py:75` and `base.py`.
- **C011 turns.py:357 is the finding S4 settled under D-19.** The re-reviewer's claim 5 says the same.
- **Conclusion.** host.py:400 is the only place where "nothing under the branch's paths" fails.

### R-9's seven functions still hold
None of them appears in the 7b05e68b analyzer output: host.py `list_codex_threads` (now :335), oneshot.py:70, preflight.py:176 `reject_unusable_fields` (`# @intent no-setting-is-silently-ignored`), the codex_host.py `__post_init__`s, and threads.py `_perform` and `_continue_defaults` (:108, :205, :283 carry markers). R-9's row stays `fixed @fad8c55f` for its seven sites. R-30 is a new site, added by a later commit.

### Spec reading
- **§12.4 is broken.** Its A002 item (spec.md:1299) says: "Every function whose identifiers contain … send … carries `# @intent <name>` on its own line, within 4 lines before to 20 lines after `def`". host.py:400 breaks it.
- **NFR-5 holds.** Its text (spec.md:548) is "no rule above its baseline", and A002 is 580 against 703, so the cite is trimmed (refuted table).
- **request.md §C** declines nothing related to this.

### Severity: I adjudicated it as Major

**For Major:**
1. **R-9 sets the precedent.** S4-findings-verifier.md:185-197 confirmed R-9 as Major with the reason "§12.4 is broken, and S3-implementer.md:79 claimed it held. The lint gate does not fail, so it is not Blocker-class." Every part of that holds here again:
   - the same rule;
   - the same §12.4 item;
   - the same slack that hides it;
   - a report that claims it holds.

   Rating the identical defect differently in the same review.md would make its tiers arbitrary.
2. **This kind of gap draws human review comments in this repo.** The field guide records that "a new boundary function needs its own `@intent` block" (field-guide/vidbyte-sdk/class-bound-helpers.md:42). That line came from PR #412 review comments 3952586662 and 3952591325.
3. **The record is wrong without the fix.** Two written gate claims, and the substance of R-9's fix statement, are false at HEAD. A PR body built from verify-log.md would carry the false claim.

**For Minor:**
- Behaviour does not change.
- The gate passes.
- The function's narration already gives most of the reason; only the machine-readable marker is missing.

**Decision.** Major. The precedent and the field-guide line decide it. It is not a Blocker, for R-9's reason: the gate passes and behaviour is unchanged. The fix is trivial and comment-only, so routing it costs one small edit.

### The fix, checked in memory
`$V/a002_fix_in_memory.py` replaces host.py:401-404 in the 7b05e68b text with this block:
```
        # @intent the-caller-can-always-retry-a-failed-stop
        # Stop a running turn with one interrupt and no stop reason
        # (AC-16). A finished turn gets nothing (EC-25), and so does a
        # turn whose earlier stop is still being awaited. A stop whose
        # await failed, timed out or was cancelled blocks nothing, so
        # the caller can retry.
```
Output:
```
before [(400, 'interrupt_codex_turn', ('external boundaries',))] | comment lines over 72: 0 | file lines: 769
after none | comment lines over 72: 0 | file lines: 771
```

**What else the fix could trip:**
- S008 selects C901, PLR0912 and PLR0915 (s008_bounded_function_complexity.py), which count branches and statements, not comments. S008 is 19/19.
- NFR-10 needs fewer than 1,000 lines; the file has 771.
- The function stays well under 40 lines.

**What the fix must not do.** It must not rename `send_stop`, or reshape the call, to hide the token. That is the lint-dodging shape R-8 confirmed as Major (C002).

## R-31 (R-C6): the in-flight mark tracks the await, not the request. CONFIRMED and widened, Minor.

### The code
- turns.py:179-188: `send_stop` runs `try: await connection.interrupt(...)` and `finally: self.stop_pending = False`.
- `connection.interrupt` (connection.py:271-290) calls `self.call(...)`.
- `call` (connection.py:166-188) awaits `asyncio.wait_for(self._loop.run_in_executor(self._executor, partial(function, *args)), bound)`.
- When that await is cancelled or times out, `run_in_executor`'s concurrent future cannot be cancelled once running, so the worker stays blocked (EC-70) while `finally` clears the mark.

### My probe
`cd $V && W=$W PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$W;$V" $PY -P -m unittest probe_interrupt_windows -v`. Final lines: `Ran 5 tests in 3.766s` / `OK`. It printed:
```
[C6a] first request held; stop_pending=True stop_sent=True
[C6a] first call -> CancelledError; held answer written=False; stop_pending=False
[C6a] second call returned; turn/interrupt count=2; first still held=True
[C6a] final: interrupted problem=None; turn/interrupt total=2

[C6b] first call -> codex.api_error; held answer written=False; stop_pending=False
[C6b] second call returned; turn/interrupt count=2; first still held=True
[C6b] final: interrupted problem=None

[C6c] timeout stop held; stop_pending=True stop_reason=FailureCode.CODEX_TURN_TIMED_OUT
[C6c] user call inside the bound: turn/interrupt count=1
[C6c] after the 1 s bound: stop_pending=False; held answer written=False
[C6c] user call after the bound: turn/interrupt count=2; first still held=True
[C6c] final: interrupted problem=codex.turn_timed_out
```
C6b and C6c patch `CODEX_HOST_REQUEST_TIMEOUT_SECONDS` to 1.0 in the connection module, using the pack's own `patch_connection`.

### The widening, tagged [verifier]
- **What the re-reviewer said.** "R-16's own case still holds … Vidbyte's timeout, cap and late-acceptance stops in flight still send one request (probes A, B and F)".
- **What C6c shows.** That is true only inside the request bound. Once Vidbyte's own quiet stop outlives its bound, `send_stop`'s `finally` clears the mark as well, and a user call sends a second request.
- **Why this is still Minor.** By D-3, a call whose bound elapsed raised `codex.api_error`, so it has failed, and R-27's accepted design says a failed stop blocks nothing. So the behaviour follows the spec, and only the comments are wrong.
- **The root cause and the fix are R-C6's.** So the widening goes into R-31's row, not into a new finding.

### Spec check: no ID is broken
| ID | Text (spec.md line) | What happens in the window |
|---|---|---|
| §9.2 interrupt row (:876) | "Nothing is sent when the turn has already finished." | The turn has not finished (`snapshot is None`). Holds |
| AC-16 (:387) | One call on a running turn sends one `turn/interrupt` and ends INTERRUPTED, no problem | The window needs two calls, the first abandoned. Holds |
| EC-25 (:438) | A finished turn: no request, returns `None` | Not a finished turn. Holds |
| D-7 (:585) | One interrupt per Vidbyte budget stop; first reason wins; failed interrupts not retried | `stop()` still checks `stop_sent`, which is never reset. The second request is the user's. C6c keeps `codex.turn_timed_out`. Holds |
| EC-27 (:440) | A failed timeout interrupt is not retried; the label applies only if the turn ends interrupted | Vidbyte sends nothing more. The label applies because the turn ended interrupted. Holds |
| EC-30 (:443) | Cap and timeout both fire: first wins, one interrupt | Unchanged path (`stop_sent`). Holds |
| INV-11 (:254-262) | Cancelling a host call re-raises `CancelledError` | C6a: `CancelledError`. Holds |
| D-3 (:581) | A call whose bound elapses raises `codex.api_error`; the worker stays blocked | C6b: `codex.api_error`. Holds |

### What is wrong is the comments (AGENTS.md principle 2)
- turns.py:182: "clear the mark when the request ends, failed or not".
- host.py:402-403: "and so does a turn whose earlier stop is still in flight".

### Fix
- **The rewording.** host.py's is the R-30 block. For turns.py:181-184:
  ```
          # Send the interrupt the caller marked pending, and clear the
          # mark when this await ends: answered, failed, timed out or
          # cancelled. A timed-out or cancelled await can leave the
          # request on a worker (EC-70), so a retry may send a second
          # interrupt. A stop in flight turns a second interrupt away,
          # but a failed one blocks nothing (AC-16).
  ```
  Every line is 72 columns or less, including the 8-space indent (checked with awk; the longest is 69).
- **The residual.** Record the window as an accepted residual beside R-1's, in the PR body.
- **Fix kind and tag.** Comment-only, and trivial.

### Adjudication between the two verifiers
- **Round 1.** The round-1 verifier (S5-findings-verifier-r1.md:209) called the cancelled-caller window "narrow, and the outcome is the pre-R-16 behaviour, so this is not a finding".
- **The re-reviewer.** It rated the window Minor, on the comment only.
- **The two agree.** The behaviour is an accepted residual, and the comment is a real, small defect. Minor stands.

## R-32 (R-C7): no test pins `turn.stop_pending = True` on the user path. CONFIRMED, Minor, follow-up.

### The code
host.py:413-415 runs `turn.stop_sent = True`, then `turn.stop_pending = True`, then `await turn.send_stop(...)`.

### The pack misses it
`$V/mutant_pack.py` replaces host.py:414 with `pass`. It does this in memory: `inspect.getsource`, then `compile` with the annotations future flag, then an assignment onto `CodexHost`. Then it runs the whole pack:
```
== none
116 passed in 7.46s
== user_no_pending
116 passed in 6.85s
```

### The mutant really is in the session
In the same pytest session as the mutant, I also ran my probe test `test_c7_current_code`, which asserts 1 request:
```
E       AssertionError: 2 != 1
probe_interrupt_windows.py:127: AssertionError
1 failed, 116 passed in 27.65s
```

### The probe pair
```
[C7 current] second user call while the first is held: turn/interrupt=1; final interrupted problem=None; total=1
[C7 mutant user_no_pending] second user call while the first is held: turn/interrupt=2; final interrupted problem=None; total=2
```

### Claims checked
- The class docstring (test_codex_host_review_gaps.py:395) says "a user interrupt is skipped only while another stop is in flight".
- FEATURE.md:100 says the pack covers "a user interrupt … while one is in flight".
- Only `test_a_user_interrupt_while_the_timeout_stop_is_in_flight_sends_nothing_more` (:425) tests the in-flight case, and it covers Vidbyte's stop only.

### Fix
Add one method to `CodexHostInterruptAfterFailedStopTests`. It mirrors `_second_user_call_while_first_held` in my probe, but drops the probe's `asyncio.sleep(0.5)`. No sleep is needed: under the mutant the second call awaits its own answered request, so the count is final when it returns.

It is about 12 lines, so it is not trivial by the one-or-two-line rule. It is tagged follow-up, consistent with R-24, which is the same class of gap on the same function. It is cheap to add in iteration 3 alongside R-30.

## Blind-spot check (step 6)

- **A convention fix that could break conformance.** R-30's natural "fix" for a lint finding could be renaming `send_stop`, which would dodge the token. That would repeat R-8's confirmed Major. It is recorded in R-30's fix cell as a "do not".
- **A comment fix that could break a gate.**
  - The R-30 and R-31 blocks are checked at 72 columns.
  - S008 counts statements.
  - NFR-10 holds at 771 lines.
  - The A002 window holds the marker at def+1.
- **Hidden findings in other rules.** The all-rules JSON scan above finds none on lines the branch added, beyond R-30 and the settled C011.
- **A new Blocker-class risk.** I found none.

## Gates I ran (final lines)

- **The pack, unmutated:** `$PY -P $V/mutant_pack.py none` gave `116 passed in 7.46s`.
- **A002 text:** `lint/run.py --rule A002 --all` gave `A002 IMPROVED 703 -> 580. …` / `SDK-LINT: PASS`.
- **A002 JSON:** `exit_code 0`, `found 580 baseline 703 verdict IMPROVED`.
- **All rules, JSON:** `exit_code 0 rules 90`, `non-pass verdicts []`.
- **Worktree state:** `git status --short` after every run was empty until I edited review.md. After that it showed ` M docs/spec/codex-host/review.md`, plus this report.

## Notes for repair iteration 3

- **One edit for R-30 and R-31.** Make it at host.py:401-404 and turns.py:181-184, comments only. Then:
  - re-run `lint/run.py --rule A002 --all --format json` and filter to `vidbyte/harnesses/native/`. The text form hides per-path rows when the verdict is IMPROVED;
  - re-run `awk 'length($0) > 72' <file> | grep -E '^\s*#'` on both files.
- **R-32 (optional, follow-up).** Add one test in the granted file, in `CodexHostInterruptAfterFailedStopTests`. Check that it fails under `$V/mutant_pack.py user_no_pending` plus the new test, and passes on the fixed code.
- **The verify-log entry.** The iteration-3 entry must correct verify-log.md:229 and S5-repair-2.md:34.
- **Read first.** Before touching comments, read field-guide/vidbyte-sdk/comment-format.md. Before touching `interrupt_codex_turn`, read review.md R-16, R-24 and R-27; R-24's M5 shares those lines.
- **What not to change:**
  - `stop()`'s `stop_sent` check;
  - `over_cap()`;
  - the order in which `stop()` sets `stop_pending` before it spawns `send_stop`;
  - `lint/baseline.json`.
