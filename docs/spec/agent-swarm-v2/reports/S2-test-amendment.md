# S2 test amendment: AgentSwarm v2 (spec r4, before S5)

Spec: `docs/spec/agent-swarm-v2/spec.md` r4 · Branch `feat/agent-swarm` (PR #1174) · Base `79f378cf` (spec r4) · Last test commit `224cbfef` · Framework pytest 8.3.5, offline, scripted runner only.

This round adds the tests that the verified S4 review (`review.md`) needs, so that the S5 repair agent has to fix only product code. Seven cases are new, 275 in all. No existing assertion was loosened, skipped, xfailed or deleted. Four of the new cases are red now, and each fails for its named product defect only. The other three are green and each one kills its mutant.

## Changes and their commits

| Finding | Commit | What changed |
|---|---|---|
| R-3 | `c9a5d0db` | `test_agent_swarm_contract.py`: `BUDGET_LINES = 400` plus `BUDGET_LINE_OVERRIDES = {"vidbyte/agents/agent_swarm/runtime.py": 500}`. The test asserts that the overrides are a subset of `BUDGET_MODULES`, and fails with `<module> is <n> lines after its header, over its <limit>-line limit`. A probe showed it passes at 500 and 400 lines and fails at 501 and 401. It is green on today's code. Test-plan row INV-37 updated. |
| R-5 | `2f346592` | Docstrings only. The AC-10 retry is described as installed by the test (`RetryModelErrorOnce` in the fixtures, and the stop module's AC-10 docstring and header). FEATURE.md wording and the test-plan AC-10 row match. No assertion changed. |
| R-12 | `afa17494` | Test plan only. The EC-27 row now gives the correct reason. |
| R-2 | `77606b69` | Fixtures gain a Gemini response shape: `GEMINI_MODEL`, `FAKE_GEMINI_KEY`, `functionCall` parts and `usageMetadata`. Two new tests in `test_agent_swarm_compaction.py`: `test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call` and `test_an_openai_history_of_write_calls_only_compacts_at_the_trigger`. **Red.** |
| R-6 | `50280d62` | `test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not`. **Red.** |
| R-9 | `0af17c80` | `test_agent_swarm_stop.py::test_a_model_call_refused_after_the_stop_records_no_history_trimmed`. **Red.** |
| R-7 | `78b067d1` | Three mutant killers, all green on today's code. `compact_while_stopping` is killed by `test_agent_swarm_stop.py::test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction`. `self_writer_as_peer` is killed by `test_agent_swarm_observer.py::test_one_agent_writing_one_file_twice_records_file_changed_with_no_peer_both_times`. `side_call_tokens_not_added` is killed by `test_agent_swarm_compaction.py::test_the_summary_call_tokens_are_added_to_the_members_tokens_used`. |
| bookkeeping | `224cbfef` | FEATURE.md cited 22 test names that no longer existed, left over from the first S2 rename pass. Each now names the real test. A check script confirms that all 55 cited names resolve to a test function in the pack. |

Each R-n commit also carries its own bookkeeping:
- the header FUNCTION INVENTORY and other A001 header lines of each touched module;
- the README File Index and Logs;
- the FEATURE.md failure modes, Test Suite Map and Historical Regressions;
- a test-plan row per new test, a new "Amendment run" section, and implementer note 9.

## Red tests (S5 must turn these green)

- R-2: `tests/features/agent_swarm/test_agent_swarm_compaction.py::test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call`
- R-2: `tests/features/agent_swarm/test_agent_swarm_compaction.py::test_an_openai_history_of_write_calls_only_compacts_at_the_trigger`
- R-6: `tests/features/agent_swarm/test_agent_swarm_compaction.py::test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not`
- R-9: `tests/features/agent_swarm/test_agent_swarm_stop.py::test_a_model_call_refused_after_the_stop_records_no_history_trimmed`

## Proof

### 1. Full pack at `224cbfef`

```
PYTHONPATH="C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider
```

```
FAILED tests/features/agent_swarm/test_agent_swarm_compaction.py::test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call
FAILED tests/features/agent_swarm/test_agent_swarm_compaction.py::test_an_openai_history_of_write_calls_only_compacts_at_the_trigger
FAILED tests/features/agent_swarm/test_agent_swarm_compaction.py::test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not
FAILED tests/features/agent_swarm/test_agent_swarm_stop.py::test_a_model_call_refused_after_the_stop_records_no_history_trimmed
4 failed, 271 passed in 7.42s
```

This is 268 existing cases plus R-3's changed test plus the three R-7 tests passing, and exactly the four new red ones failing. Each red test fails on its product assertion after its precondition assertions have passed. The precondition assertions check the parts or `content: None` history shape, the pre-stop trim, and the measured context at or above the trigger. The failing lines are:

```
compaction.py:239  >  assert compactions == [(AgentSwarmCompactionTrigger.AUTO, "", TRIGGER, 2)], describe(result.events)
                   E  assert [] == [(<AgentSwarm...'', 72000, 2)]
compaction.py:266  >  assert compactions == [(AgentSwarmCompactionTrigger.AUTO, "", TRIGGER, 2)], describe(result.events)
                   E  assert [] == [(<AgentSwarm...'', 72000, 2)]
compaction.py:315  >  assert side_after == [4, 6, 10, 14], f"summary side calls followed loop calls {side_after}"
                   E  AssertionError: summary side calls followed loop calls [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
stop.py:230        >  assert [(event.kind.value, event.tool_name, event.tool_status) for event in events[stopping.sequence :] if event.agent == "builder"] == [(TOOL_CALLED, TAVILY_TOOL, ToolStatus.SUCCESS), (RELEASED, "", None)], describe(events)
                   E  At index 1 diff: ('history_trimmed', '', None) != ('agent_released', '', None)
```

### 2. The three R-7 mutant runs

Harness: `<scratchpad>/s4eng/mut/s4mut.py` (`S4MUT=<id>`, `-p s4mut`; it rewrites one method in memory). Each run fails the four known-red tests plus exactly its own R-7 test.

```
S4MUT=compact_while_stopping      ... FAILED test_agent_swarm_stop.py::test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction
                                  E  AssertionError: builder's model calls: [3] at the stop, 4 in all
                                  5 failed, 270 passed in 6.61s
S4MUT=self_writer_as_peer         ... FAILED test_agent_swarm_observer.py::test_one_agent_writing_one_file_twice_records_file_changed_with_no_peer_both_times
                                  E  At index 1 diff: ('builder', 'builder') != ('builder', '')
                                  5 failed, 270 passed in 6.71s
S4MUT=side_call_tokens_not_added  ... FAILED test_agent_swarm_compaction.py::test_the_summary_call_tokens_are_added_to_the_members_tokens_used
                                  E  AssertionError: {'builder': 72012, 'tester': 5}
                                  5 failed, 270 passed in 6.55s
```

### 3. The red tests turn green under correct fixes

I tested every fix as an in-memory pytest plugin; no product file changed.
- The verifier's plugins are under `<scratchpad>/s4verify/plug`.
- Mine are under `<scratchpad>/s2amend/plug`. They were written from the spec text, separately from the verifier's.

```
verifier fixes (str estimate, S4V_GROWTH=target) + R-9 skip-the-trim     275 passed in 6.31s
independent fixes (JSON estimate, own target rule) + R-9 trim-silently   275 passed in 6.39s
R-2 tests, str keep-last fix alone                                       2 passed
R-2 tests, JSON keep-last fix alone                                      2 passed
stop module, R-9 skip alone / silent alone                               10 passed / 10 passed
rejected rule (growth = trigger - target), verifier fixes otherwise      1 failed, 274 passed
                                  E  AssertionError: summary side calls followed loop calls [4, 6, 12]
```

R-6's test fails the rejected trigger-minus-target rule on purpose, because spec r4 chose target-sized growth.

### 4. Lint

```
python lint/run.py                      -> exit 0, last line: SDK-LINT: PASS
python lint/run.py --format json --all  -> exit_code 0; 90 rules: 47 CLEAN, 35 RATCHETED, 8 IMPROVED, 0 failing;
                                           3,899 findings, 89 under tests/, 0 under tests/features/agent_swarm
```

Lint does scan `tests/`, since 89 of its findings are in other test folders, and it reports nothing in this pack.

Ruff is not a repo gate: there is no repo config and it is not in CI. Run with default settings, it reports 13 findings in the pack at `79f378cf` and 17 at HEAD. The 4 new ones are `I001` on the function-level imports of the new compaction tests (lines 224, 251, 278 and 331). They follow the pack's existing pattern; the 8 older `I001` findings have the same cause. I kept the pack's style rather than reorder imports in a test-only round.

### 5. Diff since spec r4 (before this report)

```
git -C <WT> diff 79f378cf..HEAD --stat
 docs/spec/agent-swarm-v2/test-plan.md              |  38 ++++-
 tests/features/agent_swarm/FEATURE.md              |  64 ++++----
 tests/features/agent_swarm/README.md               |   9 +-
 tests/features/agent_swarm/agent_swarm_fixtures.py |  24 ++-
 .../agent_swarm/test_agent_swarm_compaction.py     | 163 ++++++++++++++++++++-
 .../agent_swarm/test_agent_swarm_contract.py       |  12 +-
 .../agent_swarm/test_agent_swarm_observer.py       |  28 +++-
 .../features/agent_swarm/test_agent_swarm_stop.py  |  83 ++++++++++-
 8 files changed, 367 insertions(+), 54 deletions(-)
```

Only the pack, `test-plan.md` and (in the next commit) this report change. No `vidbyte/**`, `spec.md`, `review.md` or `pipeline.md` change is mine. The working copy shows `docs/spec/agent-swarm-v2/pipeline.md` as modified; that edit is the orchestrator's, and I never staged it.

## Notes for the repair agent

1. **R-2.** Estimate every whole message, not only its `content`. A Gemini turn keeps its size in `parts` (`functionCall` and `functionResponse`), and an OpenAI call turn has `content: None` with `tool_calls`. Any whole-message text passes: `str(message)`, JSON, or the engine's own message text. Both tests expect exactly `[(AUTO, "", 72000, 2)]`, so the keep-last split must still land on two whole provider groups.
2. **R-6.** Take the estimate right after each compaction, whatever triggered it (automatic or a `compact` request). An automatic compaction then waits until the history has grown by `AGENT_SWARM_COMPACTION_TARGET_TOKENS` (27,000) past that estimate. A `compact` request stays unconditional. The test expects side calls after loop calls `[4, 6, 10, 14]`, and its expected tuples are `(auto, measured[3], 2)`, `(tool, measured[5], 5)`, `(auto, measured[9], 10)` and `(auto, measured[13], 9)`.
3. **R-6, continued.** The test's goal alone is over the 72,000-token trigger (`"g" * (4*72000 + 12000)`), so every loop call measures at or above the trigger, and the test asserts this. Do not "fix" the test by leaving the goal out of the measured context; hysteresis is the only fix it accepts. The rejected trigger-minus-target rule gives `[4, 6, 12]` and fails.
4. **R-9.** Once the swarm is stopping, record no `history_trimmed`. Either skip the trim or trim without recording it; both pass. The trim before the stop must still record `[(True, 2)]`, and the test asserts that first.
5. **R-7.** The three new tests pass now. They are there to keep three spec-pinned lines from being deleted: no compaction while stopping, no peer when an agent rewrites its own file, and the side call's tokens added to `tokens_used`. A repair that breaks any of those lines turns its test red.
6. **R-3.** `runtime.py` may grow to 500 lines after its header. Every other budget module stays at 400.

## Round 2 (spec r6, S5 iteration 2): R-20 and R-21

Base `ee7e06e8` (product code unchanged since `04cf9caa`) · Test commits `ce8053ed` (R-20), `b4dc91d0` (R-21). All five new cases pass on the repaired code. None is red, because this round only adds tests for behavior the repair already has.

The re-review found three mutants that left the pack green. Each now fails a new test on its own product assertion. No existing assertion changed, and nothing was skipped, xfailed or deleted.

### Changes and their commits

| Finding | Commit | What changed |
|---|---|---|
| R-20 | `ce8053ed` | Two Gemini tests in `test_agent_swarm_compaction.py`. They reach the two paths of `_estimate` that no test reached. **Growth check:** `test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target`. The provider reports the trigger on every call and builder makes fourteen 30,000-character reads. Summary calls must follow loop calls `[4, 8, 12]`, with compactions `(auto, "", 72000, 2|9|9)` and no `history_trimmed`. **Fallback:** `test_a_gemini_member_whose_provider_reports_no_usage_compacts_when_its_estimate_reaches_the_trigger`. Builder makes five 60,000-character reads with `usage={}`. The `model_called` events are zeros, the one summary call follows loop call 5, and the compaction is `(auto, "", <the member's _estimate of the history at that check>, 8)`. The commit also adds three leaf helpers (`_write_parts`, `_gemini_builder`, `_is_side_call`). test-plan.md:83 (the R-2 Gemini row) now claims only the keep count, with the mutant it kills (`keep_content_only`), and points to the two R-20 rows. |
| R-21 | `b4dc91d0` | **Restart:** `test_a_compact_request_restarts_the_growth_an_automatic_compaction_waits_for`. A `compact` request is builder's first compaction, and loop calls 3 and 4 report the trigger. Summary calls must follow loop calls `[2, 4]`: `(tool, "", 3, 2)`, then `(auto, "", 72000, 6)`. **Boundary:** `test_a_repeat_automatic_compaction_is_due_at_exactly_the_target_of_growth_and_not_one_token_below`, with rows `exactly-the-target` and `one-below`. After the first compaction, builder's last read is sized as it asks for it, so that the history grows by exactly 27,000 tokens, or 26,999, by the member's own static `_estimate` (spec §8.5). The test asserts that growth before the outcome. Exactly the target must compact at iteration 4, dropping 3. One token less must not compact. The fixture change: `ToolStep` and `tool_call` take an optional `call_id` (default `""` keeps the session-wide counter), which all three provider shapes honor. A test-plan section, "Amendment run 2", is added. |

Each commit also carries its bookkeeping:
- the compaction module's PURPOSE, ROLE (now spec r6, S5 re-review R-20, R-21), FUNCTION INVENTORY and KNOWN EDGE CASES. The inventory now also lists the older `_next_own` and `_is_summary`, which it omitted.
- the fixtures header (FUNCTION INVENTORY, KNOWN EDGE CASES);
- the README File Index and a 2026-10-21 Logs entry;
- the FEATURE.md failure modes, Test Suite Map, fixture line and Historical Regressions;
- one test-plan row per new test, and the header and Pack lines.

### Why the oracles are exact but do not depend on the `str(message)` formula

INV-33 says what the estimate counts (whole messages), not its exact text. So each oracle is exact, but none of them pins the `str(message)` formula:
- Every count-based threshold has thousands of tokens of margin.
- The two values that only the estimate defines are taken from the member's own `AgentSwarmMemberRuntime._estimate`. These are the fallback's `input_tokens` and the growth at the exact-target boundary.

I checked this with an in-memory plugin, `<SCRATCH>/s2amend2/plug/s2v_alt_estimate.py`, that swaps in three other correct whole-message estimates: JSON per message, the whole list as one JSON text, and the message's string values only. All five new cases pass under each (`2 passed` for R-20 and `3 passed` for R-21, per variant).

The boundary test fixes its two reads' call ids. Ids from the session-wide counter would otherwise make its outcome depend on test order, because an id can gain a digit between two calls (for example 999 to 1000). The boundary test passes alone (`2 passed`) and in the full pack.

### Proof

**1. Full pack at `b4dc91d0`:**

```
PYTHONPATH="C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider
280 passed in 7.17s
```

This is 275 earlier cases plus 5 new ones, all green.

**2. The three re-review mutants now fail new tests.** The command is `RR1MUT=<id> PYTHONPATH="<WT>;<SCRATCH>/rereview1/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p rr1mut`.

```
estimate_content_only  3 failed, 277 passed in 6.75s
  FAILED test_agent_swarm_compaction.py::test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target
         E  AssertionError: summary side calls followed loop calls [4]
  FAILED test_agent_swarm_compaction.py::test_a_gemini_member_whose_provider_reports_no_usage_compacts_when_its_estimate_reaches_the_trigger
         E  AssertionError: summary side calls followed loop calls []
  FAILED test_agent_swarm_compaction.py::test_a_repeat_automatic_compaction_is_due_at_exactly_the_target_of_growth_and_not_one_token_below[exactly-the-target]
snapshot_only_auto     1 failed, 279 passed in 6.66s
  FAILED test_agent_swarm_compaction.py::test_a_compact_request_restarts_the_growth_an_automatic_compaction_waits_for
         E  AssertionError: summary side calls followed loop calls [2, 3]
growth_strict_gt       1 failed, 279 passed in 6.67s
  FAILED test_agent_swarm_compaction.py::test_a_repeat_automatic_compaction_is_due_at_exactly_the_target_of_growth_and_not_one_token_below[exactly-the-target]
         E  AssertionError: summary side calls followed loop calls [2]
```

Under `estimate_content_only`, the boundary test's own measurements use the mutated estimate, so its growth still lands on the target. The failure comes after that: the content-only growth disagrees with the whole-message keep count, so `messages_dropped` is 5, not 3.

I also ran a mutant of my own, in memory: `growth_minus_one`, where growth one token short of the target counts. Only the `one-below` row catches it (`1 failed, 279 passed`, `summary side calls followed loop calls [2, 4]`).

**3. The earlier mutants keep their verdicts.** I ran all 31 mutants before (`ee7e06e8`) and after (`b4dc91d0`): 16 `S4MUT` and 15 `RR1MUT`. The three `end_reason_*` mutants ran with `-x`, as in the re-review, because they leave a swarm that never stops.
- Before: 27 killed and 4 survivors (`keep_last_zero`, `snapshot_only_auto`, `growth_strict_gt`, `estimate_content_only`).
- After: 30 killed. The only survivor is `keep_last_zero`, the known equivalent mutant (`280 passed in 6.55s`; spec EC-27 and the test plan say why).
- No failing test was lost: each mutant's set of failing tests after is a superset of its set before.
- The spot checks asked for:

```
S4MUT=compact_while_stopping      1 failed, 279 passed in 6.71s   test_agent_swarm_stop.py::test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction
S4MUT=self_writer_as_peer         1 failed, 279 passed in 6.70s   test_agent_swarm_observer.py::test_one_agent_writing_one_file_twice_records_file_changed_with_no_peer_both_times
S4MUT=side_call_tokens_not_added  1 failed, 279 passed in 6.67s   test_agent_swarm_compaction.py::test_the_summary_call_tokens_are_added_to_the_members_tokens_used
RR1MUT=keep_content_only          4 failed, 276 passed in 6.76s   the two R-2 tests (as before) + the two R-20 tests
```

Several killed mutants now also fail the new tests, which adds evidence for each kill:
- `hyst_off`, `snapshot_before`, `snapshot_never` and `growth_from_trigger` fail 3 more tests each.
- `dropped_no_plus_one` and `side_call_not_budgeted` fail 5 more each.
- `trim_records_unchanged` fails 2 more.

**4. Lint:**

```
python lint/run.py                      -> exit 0, last line: SDK-LINT: PASS
python lint/run.py --format json --all  -> exit_code 0; 90 rules: 47 CLEAN, 35 RATCHETED, 8 IMPROVED, 0 failing;
                                           3,896 findings, 89 under tests/, 0 under tests/features/agent_swarm
```

Ruff is not a repo gate. Its default run goes from 17 to 21 findings in the pack. The 4 new ones are `I001` on the new tests' function-level imports, the pack's existing pattern.

**5. Diff since `ee7e06e8` (before this report):**

```
git -C <WT> diff ee7e06e8..HEAD --stat
 docs/spec/agent-swarm-v2/test-plan.md              |  27 ++-
 tests/features/agent_swarm/FEATURE.md              |   8 +-
 tests/features/agent_swarm/README.md               |   5 +-
 tests/features/agent_swarm/agent_swarm_fixtures.py |  18 +-
 .../agent_swarm/test_agent_swarm_compaction.py     | 203 ++++++++++++++++++++-
 5 files changed, 242 insertions(+), 19 deletions(-)
```

`git diff 04cf9caa..HEAD -- vidbyte/` is empty. The working tree is clean apart from this report, which the next commit adds.

### Notes for the next stage

1. No product change is needed for R-20 or R-21, and none was made. The repaired code already passes all 280 cases.
2. The R-20 fallback test and the R-21 boundary test call `AgentSwarmMemberRuntime._estimate` as their measuring instrument; spec §8.5 names it `static _estimate(messages) -> int`. If it is renamed or made an instance method, update those two tests. Do not change their thresholds.
3. A test that sizes a message to the exact token needs `tool_call(..., call_id="...")`. Ids from the counter vary with test order.
4. Process note: my first baseline loop was stopped while it ran, but its shell kept going and appended four more lines to the baseline file while the tests were being edited. Those lines were discarded. The "before" verdicts above come only from runs that finished on the unmodified tree.
