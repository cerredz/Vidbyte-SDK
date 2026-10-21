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
