# S5 repair, iteration 8 of 8: native Grok, opencode and Muse hosts

Worktree `vidbyte-sdk-native-grok-opencode-meta-hosts`, branch `feat/native-grok-opencode-meta-hosts`, PR #1036 (draft). Start a425d3fa; code head 3917b49a; the docs commit that carries this report follows it. The verify-log "Iteration 8" entry holds the same facts with every hypothesis; this report is the summary for the orchestrator.

## Outcome

R-25 is fixed in `vidbyte/tools/mcp/transport.py` only, in two commits:

| Commit | Part | What changed |
|---|---|---|
| f5a2c74a | the drains (`_send` `:323`, `_write_frame` `:423` at a425d3fa) | One leaf `@staticmethod` helper, `_drain_within(stdin, seconds)`:<ul><li>it reads `current_task().cancelling()`;</li><li>it calls `asyncio.wait_for(stdin.drain(), seconds)` in the caller's task, with the coroutine passed directly;</li><li>it raises `CancelledError` when the count rose;</li><li>then it makes the CI-1 `is_closing()` check.</li></ul>`_send` pops and cancels the pending future on `CancelledError`, then re-raises. |
| 3917b49a | the answer wait (`_answer` `:349`) | The same count check inside the existing `try`, after `asyncio.wait_for(future, timeout=seconds)`, so the existing `except asyncio.CancelledError` cleanup runs. |

The module header gained a "Known edge cases:" section. The helper has an `@intent` block, and every added comment line is at most 72 columns. The default drain line and the close-path waits are untouched. No test, lint, semgrep, contract, spec or baseline file changed.

## Gate matrix (code head 3917b49a)

| Gate | Result | Final lines |
|---|---|---|
| 7 Addendum 5 cases, 10 runs | PASS 70/70 | `7 passed, 15 deselected in 4.41s` |
| RACE-1 / R-19 `-k` command | PASS | `12 passed, 63 deselected in 4.00s` |
| AC-4 test, 30 runs | PASS 30/30 | `4 passed in 2.73s` |
| R-22/R-24 pair, 30 + 60 runs | 89/90 | 1 red: R-22's precondition, a test-fake race (below) |
| 1 packs | PASS | `1668 passed, 19 skipped in 182.38s (0:03:02)` |
| 4 lint | PASS, no count rose | `SDK-LINT: PASS` |
| 5 source stage | PASS | `5683 passed, 32 skipped in 200.06s (0:03:20)` / `CI passed.` |
| 6 package stage | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| 7 semgrep | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API check | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote CI 38475662280 | PASS | 3.11 `5676 passed, 39 skipped in 184.23s`; 3.12 `5676 passed, 39 skipped, 19 warnings in 195.64s`; Package `CI passed.` |
| remote CI 38475671014 | PASS | 3.11 `5676 passed, 39 skipped in 182.43s`; 3.12 `5676 passed, 39 skipped, 19 warnings in 174.85s`; Package `CI passed.` |
| remote static policy 38475673751 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| invariants | PASS | INV-19 sha256 `0374a2c8…497a`; INV-22 diff empty; frozen files unchanged since a425d3fa |

Remote CI ran on code head 3917b49a. The later docs commit touches only `docs/spec/native-grok-opencode-meta-hosts/`.

## Per finding

- **R-25 (Major): fixed.**
  - **Before:** the 7 cases were red at a425d3fa (`7 failed, 15 deselected in 22.04s`).
  - **After:** 70/70 green, and AC-4 was green 30/30. The `seam:` assertions held, so the remedy keeps the shapes `drain_window_gate`, `answer_window_gate` and `cancel_drain_gate` find.
  - **On 3.12:** both remote legs pass. On 3.12 the request-site never-retrieved check needs the `_send` cleanup, so the cleanup was exercised there.
- **R-1 to R-24:** unchanged and closed. RACE-1 and R-19 were re-run green, and the R-22/R-24 tests are green apart from the fake race below.

## Proposed test change (not applied; needs the orchestrator)

**Test:** `tests/features/muse_host/test_muse_host_turns.py::test_failed_turn_never_waited_logs_no_unretrieved_exception` (R-22). It fails its precondition about 1 run in 30 to 90, in a fresh process on Windows, after about 31 to 34 s: `precondition: the fake did not send a failed turn/completed for both turns`. This is the failure the orchestrator saw once in 62 runs at 19582f13. It predates R-25's change, and the product code is not involved.

**Cause.** The cause is in `tests/features/muse_host/fake_muse_peer.py`:
- `FrameWriter.send` flushes a frame and only then, outside its lock, writes the `sent` record;
- `MspPeer.run` calls `os._exit(0)` as soon as stdin reaches EOF;
- the host closes the peer as soon as it reads `turn/completed`, so the fake can exit before it records that frame.

**Evidence, from a scratch copy outside the worktree:**
- a 0.2 s sleep between the flush and the record made the test fail 3 of 3 runs, with the same message, at 31.2 s;
- with the fix below, and the sleep kept, it passed 3 of 3 runs;
- without the sleep, the whole Muse pack gave `471 passed, 5 skipped`.

**The proposed fix:**

```diff
@@ FrameWriter.send
             except (OSError, ValueError):
                 os._exit(0)
-        self.log.write("sent", frame=frame)
+            self.log.write("sent", frame=frame)
@@ MspPeer.run (EOF branch)
                 if self.scenario.get("ignore_eof"):
                     held(self.scenario)
+                self.writer.lock.acquire()
                 os._exit(0)
```

**Justification.** The precondition asserts what the fake sent, and the fake can drop that record. No spec ID is contradicted: this is a fake-harness defect, not an assertion change.

**Not checked.** The Grok fake has the same flush-then-log order (`fake_grok_peer.py:74-76`), but no Grok failure from it has been seen.

## Decision recorded (INV-18)

`_answer` serves the default `request()` path too, and the `_send` cleanup also catches a cancel during the plain drain. With defaults, this changes behaviour only for a call that was cancelled:
- the cancelled write's future no longer stays in `_pending`;
- on 3.11, a cancel inside the gh-86296 window raises where main returned the answer.

Main's transport tests pass unchanged. The ruling specified this shape, and guarding it on `timeout_seconds` would add a flag whose only job is to keep main's leak, so the guard was not added.

## Disputed findings

None.

## Still open, and what to try next

- **The fake race above.** Next step: apply the two-line fake fix (test author or orchestrator), then loop the pair 100 times in fresh processes.
  - To reproduce today: `PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/muse_host/test_muse_host_turns.py::test_failed_turn_never_waited_logs_no_unretrieved_exception`, in a loop of fresh processes.
  - To force it: the 0.2 s widening in a scratch copy.
- **The close-path bounded waits** (`:473`, `:499`, `:509` at a425d3fa) have the same 3.11 window. They are the decided follow-up and were not touched.
- **Follow-ups** R-M4, R-M5, R-M7, R-M8 and R-M10 are unchanged.
