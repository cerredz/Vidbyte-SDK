# S4 findings verifier — infinite-memory-derived-events

Code verified: `git diff origin/main...c1c3ecc0` (merge base `181f1992`). Worktree HEAD `6185889b` differs only in `pipeline.md`. Output: `docs/spec/infinite-memory-derived-events/review.md`.

Verdict: **MERGEABLE AFTER FIXES**. The review has 6 confirmed Majors and 0 Blockers.
- The Majors split by owner: 1 docs, 1 code, and 4 tests.
- There are 7 Minors: 5 trivial and 2 follow-ups.
- No finding was refuted, and none was downgraded. One proposed repair was refuted: R-E1's fix (a).

How the evidence was made. Every verdict below rests on my own runs, never on a reviewer's output.
- Probes: `s4-verifier/vprobes.py`, probes V1 to V7. Each drives the real agent through the pack's `ScriptedTree`.
- Mutations and candidate fixes: `s4-verifier/vmutate.py`, in a sandbox `git archive c1c3ecc0` copy (`s4-verifier/sb`). Each edit was restored from `s4-verifier/pristine_vidbyte` after its run, and `diff -r -x __pycache__` confirmed the restore every time.
- Proposed test changes: `sb/tests/.../test_s4v_proposed.py` and `test_s4v_ac15.py`, which exist in the sandbox only.
- Lint and the budget test with the R-C1 fix: a full-tree archive (`s4-verifier/full`, a git repo, because the lint needs one).

The worktree was never edited, except for these two files. `git status --short` shows only the three reviewer reports, plus `review.md` and this file.

## 1. Merge map

| Original | Lens | Proposed severity | → Merged | Final severity | Note |
|---|---|---|---|---|---|
| R-E1 | engineering | Major | R-1 | Major | `pair_started` OSError mid-batch. The finding is kept; its fix (a) is refuted, see §3.1. |
| R-C2 | conformance | Minor | R-1 | Major | The same root cause as R-E1, plus the sink half. Raised to Major by the merge (highest proposed); see §3.1 for the reason. |
| R-E6 | engineering | Minor | R-1 | Major | The sink half of R-C2. The same doc edit fixes it. |
| R-C1 | conformance | Major | R-2 (code) + R-5 (tests) | Major | Split by owner, as the briefing requires: one code fix plus the test that pins it. |
| R-E4 | engineering | Major | R-3 | Major | Mutation M7. |
| R-E2 | engineering | Major | R-4 | Major | Mutation M10, plus the false claim at test-plan.md:56. |
| R-E3 | engineering | Major | R-6 | Major | Mutation M1. |
| R-C3 | conformance | Minor | R-7 | Minor · trivial | |
| R-V1 | conventions | Minor | R-8 | Minor · trivial | |
| R-V2 | conventions | Minor | R-9 | Minor · trivial | |
| R-V3 | conventions | Minor | R-10 | Minor · trivial | |
| R-V4 | conventions | Minor | R-11 | Minor · trivial | |
| R-E5 | engineering | Minor | R-12 | Minor · follow-up | Mutation M11. Kept Minor; see §3.4. |
| R-V5 | conventions | Minor `[scope-adding]` | R-13 | Minor · follow-up | Not for repair. |

Ordering within the Major tier follows how much code the fix touches, smallest first:
- R-1: docs, 0 code lines.
- R-2: 1 line of code.
- R-3: 2 test lines.
- R-4: about 4 test lines.
- R-5 and R-6: about 25 test lines each.

## 2. Verification of each Blocker and Major

### R-1 (R-E1 + R-C2 + R-E6): CONFIRMED

**Code.** `launch.py:160-163` journals and announces in one loop: `pair_started(key)`, then `subagent_launched(...)`, pair by pair. If a later `pair_started` raises, the earlier pairs have already been announced, and `execute` raises before `ParallelPipeline` creates any pair task. The same interleaving exists at `181f1992` (`launch.py:148-151`). So the orphan launch predates the PR. INV-10 (`spec.md:197`) and `in_flight` (D-9) are new in this PR.

**Probe V2.** `pair_started` raises `OSError("No space left on device")` for key `…/b`. The script is `[a, b]`, then `[c]`, then `done`.
```
V2 kinds=['run_started', 'subagent_launched', 'subagent_launched', 'generator_finished', 'verifier_started', 'verifier_finished', 'subagent_finished', 'batch_finished', 'run_finished']
V2 launched(name,in_flight,agents_started)=[('a', 1, 2), ('c', 2, 4)] closed=[('subagent_finished', 'c')] answer='done'
V2 root's first launch result: '[tool_error kind=execution_error]\nTool execution failed: No space left on device'
V2 journal=['run_started', 'pair_started', 'pair_started', 'pair_finished', 'run_finished']
V2 scripts never consumed (pairs that never ran): ['analyst/root/a/gen', 'analyst/root/a/ver', 'analyst/root/b/gen', 'analyst/root/b/ver']
```

**Probe V3.** The sink raises `KeyboardInterrupt` on the first `subagent_launched` of `[a, b]`.
```
V3 KeyboardInterrupt: kinds=['run_started', 'subagent_launched', 'run_stopped'] journal=['run_started', 'pair_started']
```

**Spec reading.** INV-10 lists only EC-4 and EC-10 as exceptions, and G-3's "How we will know" repeats that. Neither path above is EC-4 (a task created but never started) or EC-10 (a finish followed by an abort). INV-16 still holds literally, because `a` was launched and never ended. What breaks is D-9's "running now" meaning, the same consequence EC-4 already accepts ("`in_flight` stays raised for the rest of the session").

**Existing guard?** None. `batch_rejected` catches only `ConfigurationError` and `ToolExecutionError` (`launch.py:145`). Nothing announces an `OSError` that escapes the start loop.

### R-2 (R-C1, code): CONFIRMED

**Code.** `phase = InfinitePairPhase.COMMIT` is set only at `launch.py:300`, inside the inner `try`. The `except (VidbyteSdkError, OSError, ValueError)` branch (`:307-312`) calls `_finish(last, …)` while `phase` is still `GENERATOR` or `VERIFIER`.

**Spec reading.** Three places agree:
- EC-10 says the abort is announced "(phase `commit`)" and does not limit this to one path.
- §12.3 row 6 says "so that every path reaches `_commit`/`_finish` in phase `commit` (D-10, EC-10)".
- D-10's own placement note adds "so a failed generator's `_finish` also runs in phase `commit`".

The error branch's `_finish` is such a path. D-10's stated placement does not cover it, so the spec contradicts itself there, and its stated intent is unambiguous. EC-25's "with the phase it was in" is vague; the fix row asks for it to say `commit`.

**Probe V1 at `c1c3ecc0`.** The sink raises `KeyboardInterrupt` on the first `subagent_finished`.
```
V1 normal           KeyboardInterrupt: finished=[('done', 'passed', '')] aborted=[('cancelled', 'KeyboardInterrupt', 'commit', 0)] journal=['run_started', 'pair_started', 'pair_finished']
V1 generator-error  KeyboardInterrupt: finished=[('failed', 'unchecked', 'RuntimeError')] aborted=[('cancelled', 'KeyboardInterrupt', 'generator', 0)] journal=['run_started', 'pair_started', 'pair_finished']
V1 verifier-error   KeyboardInterrupt: finished=[('done', 'unchecked', 'RuntimeError')] aborted=[('cancelled', 'KeyboardInterrupt', 'verifier', 0)] journal=['run_started', 'pair_started', 'pair_finished']
```

**The fix applied in the sandbox** (`vmutate.py FIX-RC1 V1 V4`): `phase = InfinitePairPhase.COMMIT` inserted before `self.error = exc`.
```
[FIX-RC1] pack:
  414 passed in 8.93s
  V1 normal           … aborted=[('cancelled', 'KeyboardInterrupt', 'commit', 0)]
  V1 generator-error  … aborted=[('cancelled', 'KeyboardInterrupt', 'commit', 0)]
  V1 verifier-error   … aborted=[('cancelled', 'KeyboardInterrupt', 'commit', 0)]
  V4 aborted=[('cancelled', 'CancelledError', 'verifier', 1)]
```

**The fix in the full-tree copy:**
```
launch.py total lines: 468 after header: 456
SDK-LINT: PASS
 vidbyte/agents/infinite/launch.py | 1 +
1 passed, 26 deselected   (test_infinite_memory_contract.py -k budget)
```

**AC-12 is undisturbed.** A `CancelledError` is not an `Exception`, so it never enters the inner branch. `test_a_cancelled_flat_generator_announces_its_abort_before_run_stopped` is among the 414 passes, and V4 (a cancel during the verifier) still reads `verifier`. The other phase assertions in the pack pass explicit phases to component calls.

**Severity.** Major, not Blocker. The wrong value appears only on a double fault: a child error that becomes the card, followed by either a sink interrupt on that card's finish or a second journal failure. In the EC-10 case the card and its `subagent_finished` were already delivered correctly. Only the abort's step label is wrong, and nothing else in the stream, the journal, or control flow changes.

### R-3 (R-E4, tests): CONFIRMED

**Spec reading.** D-9 requires the decrement to survive a raising sink: "so a sink that raises cannot skip it (R-17)". INV-16 says `in_flight` equals the pairs launched minus those that ended, and FR-5 makes `in_flight` P0. The comment at `events.py:419-420` restates the rule. The pack's only raising-sink case for `in_flight` is the launch half (`:608-609`, which kills M40).

**M7, my own edit:** remove the decrement before `_shielded`, report `max(self._in_flight - 1, 0)` in the record, and decrement after `_deliver`.
```
[M7] pack:
  414 passed in 9.46s
  V5 launched in_flight=[('a', 1), ('b', 2)] run_finished.events_failed=[2]
```
Unmutated V5 gives `[('a', 1), ('b', 1)]` and `events_failed=[2]`.

**The proposed change** (`test_re4_…` in the sandbox) is the existing test's sink plus one condition. It PASSED at BASE and with FIX-RC1, and FAILED under M7. The arithmetic: under M7, `a`'s finish leaves the count at 3, so `d` reads 3 instead of 2. Every other value in the test is unchanged.

### R-4 (R-E2, tests, and the claim at test-plan.md:56): CONFIRMED

**Spec reading.**
- D-16 defines `files` as `len(workspace.descriptions(journal.run_id))`, "the notes created through `write_note` in this run". It names R-9 as the reason against the r1 rule.
- AC-15 (P0) says "`files` as the number of notes created in this run (its `files.jsonl` records)".
- `test-plan.md:56` lists "`files` counting another run's notes" among what the AC-15 test catches.

**Code.** The test runs once on a fresh `tmp_path` (`test_infinite_memory_derived_run.py:266-289`). So `files.jsonl` holds only this run's records, and the filter at `:295` is a no-op.

**M10:** `len(workspace.descriptions(journal.run_id))` becomes `len(workspace.descriptions())`.
```
[M10] pack:
  414 passed in 10.38s
  V6 run_finished.files per run=[1, 2]
```
Unmutated V6 gives `[1, 1]`.

**The proposed change on the real AC-15 body.** `test_s4v_ac15.py` is the AC-15 test copied verbatim, plus a seeded `notes/old.md` and its `files.jsonl` record under `RUN_A`.
```
[BASE] PASSED test_re2_ac15_seeded   1 passed
[M10]  FAILED test_re2_ac15_seeded   1 failed
```

**Docs or tests owner?** Both symptoms come from one cause: the claim is false because the test is weak. The single change that resolves both is the tests-owner seed, which makes the claim true. So the row is owned by `tests`. If the orchestrator does not route it, the fallback is a docs-only strike of the claim at test-plan.md:56.

### R-5 (R-C1's pin, tests): CONFIRMED

`test_infinite_memory_derived_pairs.py:647` is the only EC-10 test, and it uses `simple_pair`, so the pair takes the normal path. The sandbox test `test_rc1_…[generator, verifier]` gave:
```
[BASE]    FAILED …[generator]  FAILED …[verifier]
[FIX-RC1] PASSED …[generator]  PASSED …[verifier]
```
It also fails under M1, M7, and M10, but only because those runs do not carry the R-2 fix. It pins R-2, not those mutations.

### R-6 (R-E3, tests): CONFIRMED

**Spec reading.** D-10 sets `phase` to VERIFIER "before `verifier_started`". FR-11 (P0) gives `subagent_aborted` its `phase`, and README:120 documents the three values. Searching the pack for `InfinitePairPhase.VERIFIER` finds it only as an explicit argument to component calls (`test_infinite_memory_derived_pairs.py:629-642`). It is never produced by a run.

**M1:** `phase, last = InfinitePairPhase.VERIFIER, checker` becomes `last = checker`.
```
[M1] pack:
  414 passed in 8.94s
  V4 aborted=[('cancelled', 'CancelledError', 'generator', 1)]
```
Unmutated V4 gives `[('cancelled', 'CancelledError', 'verifier', 1)]`, with kinds `[run_started, subagent_launched, memory_staged, generator_finished, verifier_started, subagent_aborted, run_stopped]`.

**The proposed test** `test_re3_…` PASSED at BASE and with FIX-RC1, and FAILED under M1.

## 3. Adjudications

### 3.1 R-C2 + R-E1 (+ R-E6): code fix (a) or doc fix (b)?

**Decision: (b), docs only, as one Major row.**

**Why (a) is refuted.** Journaling every new pair before announcing any of them changes the value `subagent_launched` reads from `journal.agents_started`. That value is `2 × len(started)` (`journal.py:150-152`). Under (a), `b` reads 6 instead of 4. In the sandbox (`vmutate.py FIX-RE1-two-pass V2`):
```
FAILED tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py::test_a_batch_beside_a_replay_announces_its_offset_index_counters_and_verdict_totals
1 failed, 413 passed in 9.19s
E         {'b': (1, 1, 0, 2, 6, 50, ...)} != {'b': (1, 1, 0, 2, 4, 50, ...)}
```
AC-10's docstring pins "b (… 4 agents started …)". The repair agent may not edit tests. The journal content and order were indeed unchanged under (a): V2 printed the same journal, and the orphan was gone. So (a) satisfies G-5 and NG-8 but contradicts a pinned AC-10 value. It also leaves the sink-interrupt half open. Rescuing it would mean recomputing `agents_started` in `events.py`, which sits at 658/660 lines. That is churn for no gain.

**Why not a handler.** A catch-announce-re-raise around the start loop would emit `subagent_aborted` for each announced pair. It would add a code path, which D-23 and EC-26 reject in favour of narrowing the claim. It would also report a misleading phase (`generator`) for a pair that never started. It flips to preferred only if the dashboard must close every launched row by its own event.

**Why Major.**
- The README and INV-10 are the consumer contract a dashboard will build against.
- The trigger is realistic: EC-25 already treats journal-append failures as real.
- The consequence, a row left "running" with `in_flight` too high, is the exact thing G-3 and B3 exist to remove. B3's purpose in request.md §C is "a UI shows it running forever", and the weighted word is "mainly for semantic/ui/visibility reasons".
- R-C2 rated it Minor because the case is bounded: a consumer can close rows on `run_finished`. That bound is true, and it is why the fix is docs only rather than code. It does not make the current text accurate.

### 3.2 R-C1: the one-line fix and AC-12

Confirmed safe; see the evidence in §2 under R-2. A `CancelledError` bypasses the inner branch, so AC-12's `generator` phase and a verifier-time cancel are untouched. No existing test asserts a phase on the error branch.

### 3.3 Calibration of R-E2, R-E3, and R-E4

Each surviving mutation breaks a behaviour the spec requires in a P0 field:

| Mutation | Spec rule broken | P0 field | Rating |
|---|---|---|---|
| M1 (R-E3) | D-10 | FR-11 `phase` | Major |
| M7 (R-E4) | D-9 / R-17, INV-16 | FR-5 `in_flight` | Major |
| M10 (R-E2) | D-16 / R-9 | AC-15 `files` | Major |

None is incidental behaviour, so none is refuted or downgraded.

### 3.4 R-E5 (M11): kept Minor

The engineering reviewer rated it Minor, and the briefing's summary listed M11 among the Majors. I kept Minor for three reasons:
- `subagent_aborted.error_type` is pinned by AC-12 and AC-13.
- The cause rule itself is pinned on `subagent_finished` by AC-14.
- Only the explicit-`__cause__` branch on the abort path is unpinned. It needs the pair's own code to raise `X from Y`. Cancellations and interrupts never carry a `__cause__`, and every SDK, `OSError`, and `ValueError` error becomes the card instead.

V7 confirms the behaviour (`KeyError` at BASE, `RuntimeError` under M11; the pack passes 414 under M11), so it stays a tests follow-up.

### 3.5 R-V5

Kept as a Minor follow-up, `[scope-adding]`. §8.5 defines `level` as a count ≤ the scale, so the record matches the spec. Changing it needs a spec amendment first.

### 3.6 Reviewer disagreements

- **R-C2 vs R-E1 severity.** Resolved in §3.1.
- **R-C1's EC-25 half.** It cannot be executed without a journal fault seam (test-plan.md:158 says none exists). I verified it by reading the code: a second journal failure inside the error branch raises from `_finish` with the same `phase` local as the EC-10 case. The same one-line fix covers it.

## 4. Severity blind spots (step 6)

Checked; none rises to Blocker or Major beyond the six rows.

- **The fixes collide on header lines.** R-1 (optional), R-7, and R-9 all edit the KNOWN EDGE CASES line of `launch.py:9`. R-9 and R-10 edit `events.py:9` and line 11 in six modules. Each header field must stay one line; the A001 convention and §12.4 require the header to end at line 12. The budget test counts lines after the module docstring (`test_infinite_memory_contract.py:466-471`), so edits inside the docstring are line-neutral for the caps. No test pins any docstring text: `grep __doc__|getdoc` over the pack finds nothing.
- **The R-C1 fix and the R-E3 test interact,** but harmlessly: the VERIFIER-phase test passes with and without R-2's fix.
- **`run_finished`'s new `files.jsonl` read is guarded.** It could have dropped the terminal event on a damaged file. It does not: `_text` reads with `errors="replace"` and `_descriptions` skips malformed lines (`workspace.py:275-278`, `:359-371`).
- **`deepest` computed from key segments is guarded.** Task names cannot contain `/` (`INFINITE_TASK_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"`).
- **A cancel during the fairness `asyncio.sleep`** (after `generator_finished`) reports phase `generator`. That is exactly D-10's prescribed sequence, so it is not a finding.
- **R-C3's claim about the error classes** was checked with `issubclass`:
  ```
  UsageAccountingError VidbyteSdkError not-AgentExecutionError
  FailureRaisedError VidbyteSdkError not-AgentExecutionError
  AllModelsFailedError VidbyteSdkError AgentExecutionError
  ```

## 5. Notes for the repair agent and the orchestrator

- **Reproduce R-1 and R-2.** From the worktree root:
  `PYTHONPATH=$(pwd) python -I -c "import sys; sys.path.insert(0, r'<worktree>'); sys.argv=['v','V1','V2','V3']; exec(open(r'<scratchpad>/s4-verifier/vprobes.py').read())"`
  Lines starting `V1 generator-error` and `V1 verifier-error` must read `commit` after R-2. V2 and V3 do not change, because R-1 is docs only.
- **Reproduce the surviving mutations:** `cd <scratchpad>/s4-verifier && python vmutate.py M1 V4` (likewise `M7 V5`, `M10 V6`, `M11 V7`).
- **Run the proposed tests against all variants:** `python vrun.py BASE FIX-RC1 M1 M7 M10`.
- **Re-read before editing:**
  - Field guide `comment-format.md`: R-2's comment clause, at most 72 columns.
  - Field guide `blocking-lint-invariants.md`: no new literals; the fix uses an enum member.
  - AGENTS.md principle 2: narration must match the steps.
  - `vidbyte/agents/infinite/README.md` "Notes for agents" (R-1, R-7).
  - The launch.py header rule list (R-7, R-9).
- **Cap state.** launch.py goes from 455 to 456 of 470 lines after R-2, or 457 with one added comment line. events.py is 658 of 660, and no confirmed row edits its body.

## 6. Commands run (final lines)

- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` (worktree) → `414 passed in 10.45s`
- Sandbox baseline, after adding `contracts/` to the archive: `414 passed in 10.02s`. The first sandbox run was `1 failed, 413 passed` only because `contracts/sdk-public-api.json` was absent from the partial archive.
- `python vmutate.py M1 V4` → `414 passed in 8.94s`; `V4 aborted=[('cancelled', 'CancelledError', 'generator', 1)]`
- `python vmutate.py M7 V5` → `414 passed in 9.46s`; `V5 launched in_flight=[('a', 1), ('b', 2)] run_finished.events_failed=[2]`
- `python vmutate.py M10 V6` → `414 passed in 10.38s`; `V6 run_finished.files per run=[1, 2]`
- `python vmutate.py M11 V7` → `414 passed in 8.92s`; `V7 aborted=[('failed', 'RuntimeError', 'commit')]`
- `python vmutate.py FIX-RC1 V1 V4` → `414 passed in 8.93s`; V1 gives `commit` in all three cases; V4 gives `verifier`.
- `python vmutate.py FIX-RE1-two-pass V2` → `FAILED …test_a_batch_beside_a_replay_announces_its_offset_index_counters_and_verdict_totals` / `1 failed, 413 passed in 9.19s`
- `python vrun.py BASE FIX-RC1 M1 M7 M10`:
  - BASE: `2 failed, 3 passed`. The failures are the rc1 pin, red as intended.
  - FIX-RC1: `5 passed`.
  - M1: re3 FAILED. M7: re4 FAILED. M10: re2 FAILED.
- `python vrun.py BASE M10` on `test_s4v_ac15.py` → BASE `1 passed`; M10 `1 failed`.
- Full-tree copy: `python lint/run.py | tail -2` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS`, both before and with FIX-RC1. The budget test gave `1 passed, 26 deselected`.
- `git show 181f1992:vidbyte/agents/infinite/launch.py | grep -n 'pair_started(key)' -B3 -A4` → the interleaved loop exists at the base (`:148-151`).
- `git status --short` (worktree) after all runs → only the three reviewer reports, untracked, before `review.md` and this report were written.

## 7. Scope disclosure

While checking R-V2, I ran one `grep` that printed three table rows (EC-4, EC-10, EC-37) of `docs/spec/infinite-memory-events/spec.md`. That file is outside the `docs/` files the briefing allows. No verdict depends on it. R-9 rests on allowed sources:
- The `events.py:9` header text itself, which cites "(EC-10)" for two different cases.
- The derived spec, whose edge cases end at EC-29. So "(EC-37)" in launch.py cannot name a derived-spec row, and FR-15 is the row that states the behaviour.

No other file under `docs/` outside the briefing's list was read.

## 8. Scratch files (outside the worktree)

All under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/452d7a62-18aa-47aa-9d05-a78769228dbf/scratchpad/s4-verifier/`:
- `vprobes.py`: probes V1 to V7.
- `vmutate.py`: the M1, M7, M10, and M11 mutations, and the FIX-RC1 and FIX-RE1-two-pass edits.
- `vrun.py`: the runner for the proposed tests.
- `sb/`: the sandbox `vidbyte`, `tests`, `contracts`, and `pyproject.toml` at `c1c3ecc0`, including `tests/features/infinite_memory_agent/test_s4v_proposed.py` and `test_s4v_ac15.py`.
- `pristine_vidbyte/`: the restore source.
- `full/`: the full-tree git copy used for lint.
