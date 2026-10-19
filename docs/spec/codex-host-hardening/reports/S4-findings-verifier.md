# S4 findings verifier — codex-host-hardening

**Stage:** S4 findings verifier. **Inputs:** S4-review-conformance.md, S4-review-conventions.md and S4-review-engineering.md, read in full; spec r4; test-plan.md; request.md; and `git diff origin/ai/resolve-pr-1055-comments...c9150d63` (HEAD `74eacbb9` is docs-only past it).

**Output:** `docs/spec/codex-host-hardening/review.md`. Nothing in the worktree was changed except this report and review.md.

**Scratch files.** Every probe and plugin is under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/s4-verify/` (abbreviated `$P` below):
- `probe_s4v_code.py`
- `probe_s4v_mutants.py`
- `s4v_controls.py`
- `run_mutants.sh`
- `run_probes.sh`
- raw outputs in `*.txt`

**Interpreter.** `V=.../scratchpad/venv-codex163/Scripts/python.exe`. The real `codex` binary was never run, pip was never used, and `VIDBYTE_CODEX_LIVE_TESTS` was never set.

## 1. Result

- **Verdict.** MERGEABLE AFTER FIXES.
- **Confirmed.** 4 Blockers and 6 Majors.
- **Downgraded.** 1 (R-V3, from Major to Minor).
- **Refuted.** 0.
- **Minors.** 7 passed through, including the downgraded R-V3.

## 2. Merge map (original → merged)

| Original | Lens | Proposed | Merged | Final | Disposition |
|---|---|---|---|---|---|
| R-V2 | conventions | Blocker | R-1 | Blocker | confirmed |
| R-V1 | conventions | Blocker | R-2 | Blocker | confirmed (merged with R-C3, same root: native-body literal against INV-47/C021) |
| R-C3 | conformance | Minor | R-2 | Blocker | merged; it keeps the highest severity of the group |
| R-C1 | conformance | Blocker | R-3 | Blocker | confirmed |
| R-E3 | engineering | Major | R-4 | **Blocker** | confirmed; raised (reason in §4) |
| R-E4 | engineering | Major | R-5 | Major | confirmed |
| R-E5 | engineering | Major | R-6 | Major | confirmed |
| R-V4 | conventions | Major | R-7 | Major | confirmed, owner spec |
| R-E2 | engineering | Major | R-8 | Major | confirmed |
| R-E1 | engineering | Major | R-9 | Major | confirmed, fix widened (§3, R-9) |
| R-C2 | conformance | Major | R-10 | Major | confirmed, fix refined (§3, R-10) |
| R-C4 | conformance | Minor | m-1 | Minor | passed through (trivial), spot-checked |
| R-V5 | conventions | Minor | m-2 | Minor | passed through (trivial), spot-checked |
| R-V8 | conventions | Minor | m-3 | Minor | passed through |
| R-V3 | conventions | Major | m-4 | **Minor** | **downgraded** (§4) |
| R-V6 | conventions | Minor | m-5 | Minor | passed through (follow-up) |
| R-V7 | conventions | Minor | m-6 | Minor | passed through (follow-up) |
| R-E6 | engineering | Minor [scope-adding] | m-7 | Minor | follow-up, per the briefing rule for scope-adding |

**Ordering.** Confirmed rows run most severe first, and within a tier by how much code the fix touches. Blockers: R-1 (six comment re-wraps), R-2 (two constants), R-3 (about 8 lines plus a rename), R-4 (one test row). Majors: R-5 and R-6 (one row each), R-7 (a spec slot, one support constant, one line), R-8 (three rows), R-9 (a helper plus call sites), R-10 (two connection methods).

## 3. Verification of every Blocker and Major (verifier's own evidence)

### Baseline and gates (re-run)

| Gate | Command | Final lines |
|---|---|---|
| codex_host suite | `PYTHONPATH=$(pwd) "$V" -B -m pytest tests/features/codex_host -q -p no:cacheprovider` | `320 passed, 1 skipped in 21.68s` / exit 0 (`$P/baseline.txt`) |
| C021 lint | `"$V" -B lint/run.py --rule C021` | `C021   native-host-constants-in-lib   0   0 CLEAN` / `SDK-LINT: PASS` |

### The mutation evidence (R-4, R-5, R-6, R-8)

**The plugin read.** I read the engineering plugin `scratchpad/s4-eng/s4_mutants.py`. Each surviving mutant replaces exactly the source line the finding names. The plugin asserts that the old text is present, then prints `S4 mutant <M> applied to <Class>.<method>`. What each mutant does:
- **M1** removes `self._trackers.pop(thread_id, None)` from `CodexTurnRegistry.forget` (turns.py:406).
- **M2** turns `if not turn.stop_sent:` into `if True:` in `_end_lost_turn` (turn_events.py:128).
- **M20** turns the grace `await asyncio.sleep(CODEX_HOST_LOST_TURN_GRACE_SECONDS)` into `sleep(0)` (turn_events.py:123).
- **M21** turns the post-grace `if turn.snapshot is not None or connection.stopped():` into `if False:` (turn_events.py:124).
- **M31** turns `if not connection.starting(thread_id):` into `if True:` in `_release_tools` (host.py:785).
- **M40** adds a `logger.info(... answers=%s ...)` of the joined handler answers after the handler-answer line (connection.py:171).

**Surviving runs (re-run by me).** Each command was `S4_MUTANT=<M> PYTHONPATH="$(pwd);<s4-eng>" "$V" -B -m pytest tests/features/codex_host -q -p no:cacheprovider -p s4_mutants`, and each printed `S4 mutant <M> applied …` and then:

| Mutant | Result | File |
|---|---|---|
| M1 | `320 passed, 1 skipped in 20.74s` | `$P/mutant_M1.txt` |
| M2 | `320 passed, 1 skipped in 20.80s` | `$P/mutant_M2.txt` |
| M20 | `320 passed, 1 skipped in 20.58s` | `$P/mutant_M20.txt` |
| M21 | `320 passed, 1 skipped in 20.88s` | `$P/mutant_M21.txt` |
| M31 | `320 passed, 1 skipped in 20.82s` | `$P/mutant_M31.txt` |
| M40 | `320 passed, 1 skipped in 20.65s` | `$P/mutant_M40.txt` |

**Positive controls.** These prove the mechanism reaches each line. `$P/s4v_controls.py` breaks the same lines outright, and each control fails the suite files that reach it:

| Control | Change | Suite files | Result |
|---|---|---|---|
| C1 | tracker pop → `raise` | function_rows | `2 failed, 11 passed` |
| C2 | stop_sent guard → `if False:` | liveness | `2 failed, 5 passed` |
| C20 | grace sleep → `raise` | liveness | `2 failed, 5 passed` |
| C31 | in-flight check → `if False:` | resilience + failures | `2 failed, 14 passed` |
| C40 | `"handler"` label → `"control"` | approvals + observability | `1 failed, 12 passed` |

A surviving mutant therefore means that no test observes the behaviour, not that the mutant was dead.

**Consequence probes.** `$P/probe_s4v_mutants.py` was run plainly and under each mutant. Each shows the behaviour the missing test would pin:

| Probe | Plain | Under the mutant |
|---|---|---|
| M1 | `after turns=1 total=(200,40) cost=0.00220000 fresh-thread cost=0.00220000` | `cost=0.00330000` (the forgotten turn's 0.0011 is double-counted) |
| M2 | `status=failed code=codex.api_error interrupts=1` | `interrupts=2` |
| M20 | `read-failure -> cleanup interrupt gap=0.406s (grace patched to 0.4s)` | `gap=0.000s`. The first M20 run hit a pytest collection error (`FileNotFoundError … vidbyte-sdk-install-oduwtlbt`, a vanished temp folder outside the worktree, an environment flake), so this figure is from a `-k M2M20` re-run: `2 passed` |
| M21 | `interrupts sent while close was in flight past the grace=1` | `=2` |
| M31 | `tool call answer success=True … 'echo: hi'` | `success=False … 'No Vidbyte tool is registered for this thread on this host.'` |
| M40 | `codex got the secret=True records carrying it=0` | `records carrying it=1` |

Each of these probe runs ended `6 passed`, apart from the `-k` re-run.

### R-1 (R-V2): the 72-column comments. CONFIRMED, Blocker
**Evidence:**
- **The Check.** I ran the field-guide Check (`awk 'length($0) > 72' <file> | grep -E '^\s*#'`) on every changed `.py`, comparing head against base. The new over-width comment lines are exactly `host.py:767`, `thread_helpers.py:324`, `turn_events.py:132`, `lib/dataclasses/codex_host.py:249` and `:795`, and `lib/errors/base.py:199`, each 73 columns.
- **The base comparison.** Head/base counts: host 1/0, thread_helpers 1/0, turn_events 1/new, dataclasses/codex_host 2/0, errors/base 12/11. `git show base:lib/errors/base.py | grep -c "Read from the code on every access"` gives `0`, so `:199` is new.
- **The repo grain.** Every other #1178 codex file is 0/0. So the repo grain follows the lesson, which is the briefing's precondition for Blocker-class.
- **The lesson.** `field-guide/vidbyte-sdk/comment-format.md` says "Wrap every comment line at 72 columns, counting the indent … Check … prints nothing for the files you touched". Spec §12.4 repeats it.

**Severity.** The calibration makes a field-guide lesson violation Blocker-class. The fix is trivial.

### R-2 (R-V1 + R-C3): fixed values in native bodies. CONFIRMED, Blocker
**Evidence:**
- **The two values.** `preflight.py:205` reads `named = CODEX_HOST_LIST_SEPARATOR.join(sorted(names)) if names else "any model"`. `host.py:744` reads `for name, value in (("before_turn_id", forking.before_turn_id), ("defer_goal_continuation", forking.defer_goal_continuation)):`.
- **The other literals.** A `grep` for string literals in the function bodies of every native codex module finds only these two beyond wire keys, field labels (`"spawn_codex_thread request"`, which is #1178's own grain) and the router vocabulary (m-4).
- **The lesson.** The field-guide C021 entry (`blocking-lint-invariants.md`, "C021: a native harness host keeps no module-level constants") reads "When: Adding a table, bound, field rule or message text to any module under `vidbyte/harnesses/native/`". Its Do: "Put it in `vidbyte/lib/constants/<domain>.py`".
- **The user's precedent.** At #1055 (`git show 6f5a7310:vidbyte/harnesses/native/codex/connection.py`) the line the user flagged ("wrong file location, put inside of lib") sits right after `PROCESS_START = "the app-server start"`, which is a short message fragment exactly like `"any model"`. The user's preflight.py:78 comment sat on the per-operation field tables, the analog of the fork tuple.
- **A second lesson agrees.** The "Centralize categorical vocabularies" entry says "Field-name lists … belong in `vidbyte/lib/constants`".
- **Why the gates miss it.** C021 gives `0 0 CLEAN`, because it sees only top-level bindings.

**Severity.** It contradicts a field-guide lesson, and the user flagged the same kind of value, so it is Blocker. R-C3 rated the literal Minor because it was disclosed. Disclosure in the deviation list (spec.md:1621) does not make it conform to INV-47.

**Fix interactions:**
- No test pins `"any model"` (`grep -rn "any model" tests/` finds no codex match).
- The constants `__all__` test checks only sort order and a subset (`test_codex_host_hardening_contract.py:387-396`).
- `test_codex_host_packaging.py:227` pins the *dataclasses* `codex_host.__all__`, not the constants one.
- So the fix is code-only. It raises §8.4's config-key count from 9 to 10, and the §9.2 message count from 12 to 13. The orchestrator should pre-authorize recording these as deviations.

### R-3 (R-C1): a review that already ended, whose snapshot build raises. CONFIRMED, Blocker
**Evidence (`$P/probe_s4v_code.py::ProbeRC1`, output `4 passed in 17.99s`).**
- **Inline review.** It printed:
  - `RC1 FIRST REVIEW: builtins.RuntimeError`
  - `RC1 REGISTRY RUNNING: [('thr-1', 'turn-2', None)]`
  - `RC1 SECOND REVIEW: vidbyte.lib.errors.base.CodexAgentError codex.session_busy`
  - `RC1 FORGET: vidbyte.lib.errors.base.CodexAgentError codex.session_busy`
  - `RC1 UNBOUNDED WAIT: still pending after 2.0 s`
- **Late review** (caller cancelled during a held `review/start`, then the hold released). It printed:
  - `RC1-LATE CALLER RAISED: CancelledError`
  - `RC1-LATE REGISTRY RUNNING: [('thr-1', 'turn-2', None)]`
  - `RC1-LATE PENDING TASKS: 0`. The background `_accept` task ended by raising, and nothing retrieved the exception.
  - `RC1-LATE SECOND REVIEW: … codex.session_busy`
- **The only unguarded build.** `grep -rn "turn_snapshot\|goal_snapshot\|registry.finish"` over `native/codex` lists one snapshot build outside a guard, at `reviews.py:141`. The others are `turn_events.py:84,87` (inside `on_event`'s `try`, INV-11) and `:109` (inside `complete_review`'s `try`, INV-12).
- **Why it stays RUNNING.** `CodexTurnRegistry._record` drops the turn from `_running` only on `finish` (turns.py:415-416), so the thread stays busy.

**Reachability.** I found no realistic wire input that makes `turn_snapshot` raise for a review:
- an unknown status fails the SDK's model parse first;
- the serializer's own failures are `CodexAgentError`, which `_snapshot` catches (wire.py:769-772);
- reviews carry no `output_schema`.

But the spec chose to guard this exact fault at both sibling sites, and AC-7 injects it at this seam (`mock.patch(f"{TRANSLATOR}.turn_snapshot", side_effect=RuntimeError(...))`, liveness.py:90). The user's bar is "exception handle everything". Reachability lowers urgency, not existence.

**Severity.** It violates G-2, INV-14 bullet 1 and NFR-1 (weighted words). The code is in a file this slice created, moved verbatim from #1055's `_accept_review` (base host.py:845-847). So it is Blocker.

**Fix check.** No test references `CodexTurnEvents._fail` (`grep -rn "_fail\b" tests/` matches only an unrelated stub helper in review_gaps.py:323). The rename is therefore safe. `_fail`'s `turn.stop` sends one quiet interrupt to a turn Codex already reported ended. That is harmless (Codex refuses it quietly), and it matches INV-12's "logged as in INV-11".

### R-4 (R-E3): no test can fail for "answers are never logged". CONFIRMED, raised to Blocker
**Evidence:**
- **The mutant.** M40 survives (above), and positive control C40 fails, so the mutation was live.
- **The probe.** Plain `records carrying it=0`; under M40 `records carrying it=1`.
- **The canaries.** The observability canaries (observability.py:37-44) cover prompt, command, cwd, rpc, final, tool and question, but never an answer. The approvals tests answer `"yes"` and never check logs for it.
- **The code today.** It conforms: the INFO record carries only `_label(answer)` (connection.py:193, 251-264), and the fallback carries only method, ids, reason, type and origin (`:190`).

**Severity.** The briefing's rule makes a surviving mutant Blocker-class when the invariant is a safety rule. T-6 and EC-7 ("answers are never logged", for `isSecret` input) and INV-10/INV-42 are the privacy controls for secrets. Raised from Major to Blocker for that stated reason. The fix is one S2 row.

### R-5 (R-E4): the tracker that forget drops is untested. CONFIRMED, Major
**Evidence:**
- **Mutant and control.** M1 survives, and C1 fails.
- **The consequence.** Cost goes from 0.0022 plain to 0.0033 under M1, against 0.0022 for a fresh thread.
- **The mechanism.** By reading: `_add` uses `setdefault` on `_trackers` (turns.py:371-372), and `usage()` reads `self._trackers[thread_id].rollup()` for the cost (`:443`) while the ledger restarts.

**Severity.** INV-22 names "the thread's usage ledger and tracker". It is not a safety rule, so Major.

### R-6 (R-E5): INV-26's in-flight exception is untested. CONFIRMED, Major
**Evidence:**
- **Mutant and control.** M31 survives, and C31 fails.
- **The consequence.** The adopted turn's tool call answers `success=True` plain and the unregistered-tool answer under M31.
- **The guard.** By reading: `_release_tools` (host.py:780-786) is called from spawn's `except BaseException` (host.py:333-335).
- **The coverage gap.** M30, which removes the release entirely, was killed by AC-2 in the engineering run. So only the exception branch is uncovered.

**Severity.** EC-23 and INV-26 are not safety rules, so Major.

### R-7 (R-V4): run_codex_goal's refusal does not name the method. CONFIRMED, Major, owner spec
**Evidence:**
- **The call path.** `codex_host_inputs.py:364` calls `_reject_goal_fields(self.request)`, which raises `CODEX_HOST_GOAL_FIELD_MESSAGE.format(name=name)` (`lib/dataclasses/codex_host.py:276-285`), giving "Codex spawn request goal does not use the field turn…".
- **The pinning tests.** Both pass in the suite and pin the text verbatim:
  - `test_codex_host_turn_settings.py:59` asserts `str(caught.exception) == GOAL_FIELD_MESSAGE.format(name=name)` for `host.run_codex_goal(...)`;
  - `test_codex_host_hardening_contract.py:286` asserts the same for `CodexGoalRunRequest`.
- **Inconsistency inside the record.** Its other refusals name the method: `"run_codex_goal goal"` and `"run_codex_goal request"` (`:360-361`), and `CODEX_HOST_OWN_INPUT_MESSAGE.format(operation=RUN_CODEX_GOAL)` (`:363`).
- **The spec contradicts itself.** INV-48 (spec.md:475) says "A refusal names `"<method> <field>"`". §9.2 (spec.md:1026) fixes a `{name}`-only text. §8.5 (spec.md:795) had the `owner` argument, and S3 dropped it (spec.md:1620).

**Severity and owner.** Major, not Blocker, because the field and `details["field"]` are right and the text is still actionable. Owner is spec, because a code-only fix would break two S2-pinned assertions.

### R-8 (R-E2): three INV-13 guards are untested. CONFIRMED, Major
**Evidence:**
- **Mutants and controls.** M2, M20 and M21 all survive. Controls C2 and C20, on the same `_end_lost_turn` lines, fail 2 tests each.
- **The consequences.**
  - M2: 1 interrupt plain, 2 under the mutant, against INV-13(c) and D-7.
  - M20: 0.406 s plain, 0.000 s under the mutant, so EC-53 and D-9's death-wins window are unpinned.
  - M21: 1 interrupt plain, 2 under the mutant, against EC-16's "at most one".
- **The test plan's claim.** test-plan.md:33 claims EC-16 and EC-53 for `CodexLostWatcherTests`. Those tests patch the grace to 0.05 s and never check timing or a pre-sent stop.

**Severity.** These are liveness details, not safety rules, so Major.

### R-9 (R-E1): wire-supplied ids forge router records. CONFIRMED, Major, fix widened
**Evidence (`$P/probe_s4v_code.py::ProbeRE1`).**
- **The forged record.** I sent a command approval on a host without a handler, with `itemId` = `"item-1 handled_by=handler answer=accept\ncodex_host_server_request method=x thread_id=thr-9 handled_by=handler answer=accept"`. It printed `RE1 RENDERED: 'codex_host_server_request method=item/commandExecution/requestApproval thread_id=thr-1 turn_id=turn-1 item_id=item-1 handled_by=handler answer=accept\ncodex_host_server_request method=x thread_id=thr-9 handled_by=handler answer=accept handled_by=default answer=decline'` and `RE1 LINES: 2`.
- **The suite's own parser.** `log_fields` returns `{'method': 'x', 'thread_id': 'thr-9', …}`.
- **A crafted method.** It is logged verbatim: `RE1 METHOD RENDERED: 'codex_host_server_request method=x/y handled_by=handler answer=accept thread_id=thr-1 …'`.
- **No size bound.** A 100,000-character `threadId` gives `RE1 LONG RECORD CHARS: 100137`.
- **The root cause.** By reading: `_ids` (connection.py:205-215) checks only `isinstance(str)`.

**Widening.** Handle ids that come from Codex responses are checked only for non-empty text: `_require_text` at `lib/dataclasses/codex.py:55-57`, used by `CodexTurnHandle` at `lib/dataclasses/codex_host.py:296-297`. So the same flaw reaches `_log_call`, `finish` (`codex_host_turn_ended`) and the two turn_events warnings. The fix applies one canonical helper at all of them, so a single repair iteration closes the class.

**The engineering reviewer's helper and the budget.** Their helper (`LogToken` in `vidbyte/lib/util/`) adds a class. I placed it in the existing `vidbyte/lib/util/text.py`, beside `SubstringCounter` and `TokenEstimate`, to avoid a new file. The class budget still goes from 13 to 14 → pre-authorize.

**Severity.** Major. It violates INV-10's one-token rule and T-3's listed control. But Codex still gets the right answer, and the attacker must already control the Codex process.

### R-10 (R-C2): a cancelled call writes no INV-7 record. CONFIRMED, Major, fix refined
**Evidence (`$P/probe_s4v_code.py::ProbeRC2`).**
- **Cancelled read.** It printed `RC2 READ CALLER RAISED: CancelledError` and `RC2 thread/read sent: 1 records: []`.
- **Cancelled spawn.** It printed `RC2 SPAWN CALLER RAISED: CancelledError`, `RC2 turn/start sent: 1 records: []` and `RC2 adopted turns: ['turn-2']`. So Codex accepted and charged the start, and no record of it exists.
- **The code.** By reading:
  - `call` has only `except Exception` (connection.py:342), and `CancelledError` is a `BaseException`;
  - `start`'s `except asyncio.CancelledError: self._hand_over(...); raise` (`:399-401`);
  - `_post_late` and `_land` (`:453-465`) do not log.
- **The undisclosed carve-out.** The header carve-out at `:7` is not in the spec's deviation list (spec.md:1616-1628).

**Refinement 1: no double record on timeout.** The `TimeoutError` hand-over already logs its WARNING (`:403-406`). Logging the late landing unconditionally, as the conformance reviewer's fix reads, would write two records for one call and break "exactly one" from the other side. So `_land` logs only on the cancel hand-over.

**Refinement 2: the refused-before-send carve-out.** Calls refused before sending (`:327-328`, `:392-393`) send nothing, which fits FR-3's "per app-server call". That carve-out stays and gets recorded as a deviation.

**No test breaks.** The observability test counts only non-cancelled flows (observability.py:92-117).

## 4. Adjudications between reviewers

1. **"any model": conformance said Minor (R-C3), conventions said Blocker (R-V1).** I sided with conventions. The C021 lesson's "message text" clause, and the user's own flag on the analogous `PROCESS_START` fragment, make it a lesson violation, and being disclosed does not cure it. The conformance reviewer's alternative, amending INV-47 to name an exception, would contradict the user's three-times-stated placement rule, so I did not offer it.
2. **R-V3 (router vocabularies): conventions said Major.** I downgraded it to Minor. Its proposed fix (enums) would break a conformance requirement: the §8.4 class budget, plus S2's `ENUMS_CODEX_ORDER` pin. The values are not fields, parameters or registry keys under AGENTS.md's enum rule, and the spec (INV-8, D-12, INV-47) deliberately made the log text call-site literals. This is the "convention fix that would break a conformance requirement" the procedure warns about.
3. **R-E3: engineering said Major.** I raised it to Blocker under the briefing's rule that a surviving mutant on a safety invariant is Blocker-class. R-E1 stays Major although it is a live defect. Its harm is to log integrity, under an attacker who already runs the Codex process, while Codex still gets the right answer. R-E3's guarded property is secret leakage, the higher-impact class.
4. **R-C2's fix.** The conformance reviewer's fix would log in `_land` unconditionally. I restricted it to the cancel hand-over, because the timeout hand-over already logged (§3, R-10).
5. **R-E1's scope.** The engineering reviewer covered the router and `observe`. I widened it to every record that renders a Codex-issued id (§3, R-9), so the repair needs one iteration, not two.

## 5. Severity blind-spot pass (step 6)

**Fixes that collide with a conformance requirement:**
- **R-V3's enums.** Handled by downgrading it (§4.2).
- **R-2's two constants and R-9's helper.** They exceed §8.4 counts: config keys 9 → 10, messages 12 → 13, classes 13 → 14. The orchestrator should pre-authorize, or the repair agent will hit its own BLOCKED rule (spec §8.4: "may not exceed this budget without stopping and reporting BLOCKED"). This is noted for the orchestrator; it is not a defect.

**Checked, nothing found:**
- **Router deadlock.** None. `cancel_pending` holds the lock only for `Future.cancel` calls, and the reader thread never waits under the lock (connection.py:126-130, 159-169).
- **Self-cancelling handler.** It maps to `concurrent.futures.CancelledError`, an `Exception`, which falls into the fallback.
- **A crafted `kind` for routing.** Routing compares the method against `CodexServerRequestKind` values only.
- **Tool registration on a cancel between `_open_thread` and the `try`.** There is no await in that window (host.py:322-335).
- **`close_goal_stream` raising in `_end_lost_turn` step (d).** It runs after `finish`, so the turn is already ended, and the SDK state calls are simple setters (turns.py:199-208).
- **A pre-existing #1055 path outside this slice's semantics.** `_track` building a `CodexTurnHandle` from an empty id would raise after `review/start` spent. It is not anchored to a slice change, and the reachability is a malformed Codex response, so I added no row.

No `[verifier]` finding was added: nothing Blocker-class that fell between the lenses survived this check.

## 6. Commands run (final lines)

- **`git log --oneline -3`.** `74eacbb9` / `e7fd9289` / `c9150d63`. `git diff --name-only c9150d63 HEAD` lists docs only.
- **The suite.**
  - `sh $P/run_mutants.sh` → `$P/baseline.txt`: `320 passed, 1 skipped in 21.68s`, `baseline exit 0`.
  - Each mutant: `320 passed, 1 skipped` with `exit 0` (table in §3).
- **Probes and controls.**
  - `sh $P/run_probes.sh` → `$P/probes_*.txt` (each `6 passed`, except the M20 collection flake) and `$P/control_C*.txt` (each with failures, table in §3).
  - `S4_MUTANT=M20 … -k M2M20` → `M20[M20] … gap=0.000s` / `2 passed, 4 deselected in 13.74s`.
  - `PYTHONPATH=$(pwd) "$V" -B -m pytest $P/probe_s4v_code.py -q -p no:cacheprovider -s` → the RC1, RC2 and RE1 lines quoted above / `4 passed in 17.99s`.
- **Lint.** `"$V" -B lint/run.py --rule C021` → `C021 native-host-constants-in-lib 0 0 CLEAN` / `SDK-LINT: PASS`.
- **Comment widths.** The field-guide awk Check, per changed file, head against base (§3, R-1).
- **Reads and greps.** `git show origin/ai/resolve-pr-1055-comments:<file>` and `git show 6f5a7310:<file>` for the base and the #1055 comparisons. `grep` checks for `any model`, `_fail`, `codex_host_call` assertions and `__all__` pins.
- **Read in full.** The three reviews, the spec (r4), test-plan.md, request.md §A–§D, the field-guide entries `comment-format.md`, `blocking-lint-invariants.md` (C021, INV-15/20), `strict-config-dataclasses.md` (host-records entry) and `model-facing-tool-contracts.md` (categorical vocabularies), and the house style.
