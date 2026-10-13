# S2 test author, addendum 3: RACE-1 regression tests

- **Stage:** S2 addendum 3, a narrow regression-test pass inside the S5 repair loop.
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-grok-opencode-meta-hosts`, on branch `feat/native-grok-opencode-meta-hosts`.
- **Base:** `05d45151`. Test commit `ba70578e`.
- **Inputs read:**
  - `review.md` from line 102 to the end (RACE-1);
  - the spec ranges for INV-13, EC-51 to EC-53, EC-96, EC-97, EC-102 and EC-115, plus §13 and the `NativePeer` interface in §8.5;
  - `test-plan.md` addenda r8 and 2;
  - the Grok and Muse pack files;
  - the verifier's scratch prototypes and fix probes.
- **Not read:** nothing under `vidbyte/`.

## What was produced

| File | Change |
|---|---|
| `tests/features/muse_host/fake_muse_peer.py` | Adds the `msp["turn/interrupt"]["order"]` knob (`answer_first` or `completed_first`), `MspPeer.completed_sent`, and an `interrupt_order` log record. `TurnWorker.send_completed` sets the event only for the ack's own turn. Without the key, the fake runs the same statements in the same order as before. |
| `tests/features/muse_host/test_muse_host_turns.py` | Adds 5 functions (8 cases): R-18 (a), R-18 (b) ×4, the -32030 guard, the R-20 Muse twin guard, and R-21. Adds the helpers `poll_until`, `interrupt_expecting_no_error` and `assert_the_interrupted_turn_stands`. Makes the granted R-18 (c) scenario change. Updates the header. |
| `tests/features/grok_host/test_grok_host_turns.py` | Adds 2 functions: R-19 and R-20. Adds the `CancelDrainGate` class with its `cancel_drain_gate` fixture, which is used by this file only, as the pack's conftest rule asks. Adds `poll_until` and `interrupt_expecting_no_error`. Updates the header. |
| `tests/features/{grok_host,muse_host}/FEATURE.md` | Updates the failure inventory, the historical regressions and the test suite map, as addendum 2 did. No new `FEATURE.md` was created. |
| `tests/features/{grok_host,muse_host}/README.md` | Adds a `## Logs` entry each. The Muse File Index also names the knob. |
| `docs/spec/native-grok-opencode-meta-hosts/test-plan.md` | Adds `## Addendum 3 — RACE-1 regression tests`, with a coverage map, omissions, the red run, the granted change and notes. |

The spec, `review.md`, `pipeline.md` and §6.2 were not touched.

## Failure inventory (input + state → wrong output)

1. **R-18 (a).** The turn is held, and Muse never answers `turn/interrupt` but ends the turn `cancelled` → the driver closes the peer while the call is pending → `muse.process_exited` for an interrupt that worked.
2. **R-18 (b).** `turn/completed` is written before the interrupt's answer, whatever the answer is → `muse.process_exited`. That is the CI order. If the answer were read before the close, -32030 would give `muse.api_error`.
3. **R-18 (c).** In the existing -32013/-32014 test, the fake set `interrupt_event` before answering, so the turn thread could win → a flaky gate (the CI failure itself).
4. **R-18 guard.** A fix keyed on the answer code or on `running` → a -32030 for a still-running turn is swallowed (EC-102 broken).
5. **R-18 and R-21 guards.** A fix that swallows every closed-transport error → EC-96 (a peer exit) and EC-97 (silence) stop raising. The existing rows `test_muse_host_errors.py:355-356,363-364` cover this.
6. **R-19.** Grok answers `end_turn` while `session/cancel` is still being drained, and the driver closes the peer → the post-drain check gives `BrokenPipeError` → `grok.process_exited` for a cancel that reached Grok.
7. **R-19 guard.** A fix that swallows every cancel-write failure → EC-51 (the peer stopped reading, no answer) stops raising. The existing POSIX test covers this.
8. **R-20.** Grok has answered, and the driver is in its close (the peer ignores EOF) → `was_running=True` with nothing sent, which matches neither EC-52 nor EC-53.
9. **R-20 Muse twin.** A Muse change that starts interrupting a completed turn while its driver closes → `turn/interrupt` sent and `was_running=True`.
10. **R-21.** The turn completes while `turn/steer` waits → `muse.process_exited` (`check_muse_ready`) instead of EC-115's `muse.turn_not_found` (`continue_muse_session`).
11. **Seam vacuity (R-19).** If the gate never engages, or never sees the close, the test would pass without forcing the window. Two `seam:` precondition assertions catch this.
12. **Knob vacuity (R-18 b).** If the knob were not read, the default race would decide the result. The `interrupt_order` record with `completed_sent=True` catches this.

## What was pruned, and why

- **Opencode:** not affected (decided).
- **A Grok -32030 twin:** a cancel is a notification and gets no answer.
- **Duplicates of EC-51, EC-96 and EC-97:** these rows already exist and must stay green.
- **R-21 with a late steer answer:** this would need a second fake knob, which the brief did not grant, and it is EC-115's own third clause.
- **Asserting R-19's internal exception path:** it differs by CPython version and platform.
- **A unit test of the knob:** the knob is proven where it is used.
- **Opencode's optional re-check:** it is not a finding.

## Red run, exact output

These are the final lines of the four-pack command, with the new tests staged:

```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q -rf --tb=line tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
…
FAILED tests/features/grok_host/test_grok_host_turns.py::test_interrupt_whose_cancel_write_loses_to_the_turn_end_succeeds
FAILED tests/features/grok_host/test_grok_host_turns.py::test_interrupt_after_grok_answered_while_the_driver_is_still_closing_sends_nothing
FAILED tests/features/muse_host/test_muse_host_turns.py::test_interrupt_that_loses_to_turn_completed_succeeds
FAILED tests/features/muse_host/test_muse_host_turns.py::test_interrupt_answered_after_turn_completed_succeeds[minus-32013]
FAILED tests/features/muse_host/test_muse_host_turns.py::test_interrupt_answered_after_turn_completed_succeeds[minus-32014]
FAILED tests/features/muse_host/test_muse_host_turns.py::test_interrupt_answered_after_turn_completed_succeeds[minus-32030]
FAILED tests/features/muse_host/test_muse_host_turns.py::test_interrupt_answered_after_turn_completed_succeeds[accepted]
FAILED tests/features/muse_host/test_muse_host_turns.py::test_steer_that_loses_to_turn_completed_raises_turn_not_found
8 failed, 1651 passed, 19 skipped in 155.03s (0:02:35)
```

The baseline at HEAD was 1649 passed and 19 skipped. 1651 is that baseline plus the 2 new guards.

**The 5-run loop.** The new tests and R-18 (c) ran alone 5 times:

```
$ for i in 1 2 3 4 5; do PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q -rA --tb=line tests/features/muse_host/test_muse_host_turns.py tests/features/grok_host/test_grok_host_turns.py -k "loses_to or answered_after_turn_completed or rejected_with_32030 or still_closing or interrupt_answered_interrupted_or_cancelled"; done
run 1: 8 failed, 4 passed, 61 deselected in 3.43s
run 2: 8 failed, 4 passed, 61 deselected in 3.24s
run 3: 8 failed, 4 passed, 61 deselected in 3.28s
run 4: 8 failed, 4 passed, 61 deselected in 3.39s
run 5: 8 failed, 4 passed, 61 deselected in 3.27s
```

These are the red reasons, tallied over the 5 logs:

```
  5 …test_grok_host_turns.py:104: Failed: INV-13: interrupt_grok_turn raised grok.process_exited (reason 'stdin_write_failed') for a session/cancel it sent to a running turn whose own end closed the peer
  5 …test_grok_host_turns.py:269: AssertionError: EC-52: Grok had answered, so the turn was finished and nothing is sent
  5 …muse_host\conftest.py:269: AssertionError: expected muse.turn_not_found, got muse.process_exited: The Muse Code process stopped before it answered.
 25 …test_muse_host_turns.py:86: Failed: INV-13: interrupt_muse_turn raised muse.process_exited (reason 'closed') for an interrupt it sent to a running turn whose own end won the race
```

Every green case was green in all 5 runs: R-18 (c) in 10 of 10 runs, and the -32030 guard and the Muse twin in 5 of 5 each.

**Satisfiability check (scratch only, nothing committed).** I built a shim in `scratchpad/s2-addendum3/fixcheck/`. It loads each pack's conftest and the unchanged worktree test modules, and it applies the verifier's proposed-fix monkeypatches, copied from `test_fix_probe_{muse,grok}.py`. Each of 5 runs over the 23 selected cases gave `1 failed, 21 passed, 1 skipped`; the one failure was R-21. The passes cover:
- R-18 (a), R-18 (b) ×4 and R-18 (c) ×2;
- R-19 (both seam preconditions held) and R-20;
- both guards;
- the EC-96, EC-97 and EC-115 interrupt rows (host and tool), and EC-2 for interrupt;
- the existing Grok interrupt tests.

The skip is EC-51, which is POSIX-only. R-21 failed because the probes carry no steer fix. So R-21's satisfiability is **not** proven; it rests on the review's one-line fix.

**Lint.** `python lint/run.py` → `SDK-LINT: PASS`. A001 (643), A007 (255), S062 (889) and S024 (25) are all at their baselines.

## Fixtures added or extended

- **Extended:** `fake_muse_peer.py` (the knob; no default changed, and conftest's `default_scenario` is untouched).
- **Added:** the `cancel_drain_gate` fixture and the `CancelDrainGate` class, in `test_grok_host_turns.py` only.
- **Not changed:** no conftest. The existing fixtures used are `muse_api`, `muse_fake`, `make_muse_host`, `fast_stop`, `check_native_error`, `grok_api`, `grok_fake` and `make_grok_host`.

## The granted change (R-18 c)

`test_interrupt_answered_interrupted_or_cancelled_counts_as_success`, scenario dict only:
- before: `{"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"error": {"code": code, "message": "already stopping"}}}}`;
- after: `{"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"order": "answer_first", "error": {"code": code, "message": "already stopping"}}}}`.

The comment and the assertions are unchanged.

## What made the tests hard to write (for the orchestrator)

1. **The R-19 seam rests on internals the spec does not name as test seams.** The spec names `NativePeer.notify` (§8.5), but not "the transport awaits the drain through `asyncio.wait_for` in the caller's task"; only the verifier's prototype shows that. I kept the seam delegating and task-scoped, and I made it wait for the fake's own `eof` record. The prototype used the private `peer._transport.closed`; `eof` is stronger, because it proves the OS pipe is closed, and it needs no private attribute. If iteration 6 fixes R-19 by any route other than the `ended` predicate (for example, sending the cancel from the driver task, or dropping `wait_for`), the test fails with a `seam:` message. That failure would be a seam break, not a wrong fix, and it needs an orchestrator decision.
2. **EC-102 for `interrupt_muse_turn` is implicit.** §6.3.5 lists only EC-96 and EC-97 as host-wide rows for interrupt, with EC-115 for a foreign handle. The -32030 guard relies on §6.3.2's catch-all, as the review and the brief decided. A one-word spec addition (EC-102) would make this explicit. I requested no change.
3. **R-18 (b) depends on a sub-ordering on today's code.** If a host ever read the answer before its close, three of its four cases (-32013, -32014, accepted) would be green today. The verifier saw the close win in 30 of 30 runs, and I saw it win in 20 of 20. After the fix, both sub-orderings must pass, and under the probe fix they did.
4. **R-20's window is about `NATIVE_STOP_GRACE_SECONDS` (0.3 s with `fast_stop`).** A 10 ms poll lands well inside it on this machine. If a much slower runner missed the window, the test would pass vacuously **today**, but it would never give a false red after the fix.

## Open items

- R-21 cannot be checked against any fix here, because the verifier's probes have no steer fix. Iteration 6 is the first run that can make it green.
- The R-19 seam is coupled to the cancel's drain going through `asyncio.wait_for` in the interrupting task (point 1 above).
