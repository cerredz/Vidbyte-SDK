# S2 test author report — infinite-memory-events

- **Status:** DONE
- **Spec:** `docs/spec/infinite-memory-events/spec.md` r3 (approved). Only the §6.2 **Proof** column was filled; no other spec text changed (checked by a script: 37 lines changed, each only by its last cell).
- **Base:** HEAD before S2 `9a180d40` (branch `feat/infinite-memory-events`, base `7efceb55`).
- **Commits:** `28f45271` `test(infinite): add failing tests for infinite-memory-events [AC-1..AC-37]` (tests, shared fixture, row 22 edit, pack README/FEATURE, `test-plan.md`); then `docs(spec): record test proof for infinite-memory-events` (spec §6.2 Proof column and this report).
- **No production code** was created or changed. No install was run; every command ran from the worktree root with `PYTHONPATH=$(pwd)`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`.

## Inventory

53 new test functions, 73 collected cases, in 8 new files, plus the one pre-approved edit of an existing test. Full per-test map (spec ID, failure caught, why it cannot pass vacuously) is in `docs/spec/infinite-memory-events/test-plan.md`.

| File | Functions / cases | Level | Spec IDs |
|---|---|---|---|
| `tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py` | 13 / 13 | run | AC-1, AC-2 (+AC-13), AC-3, AC-4, AC-15, AC-20, AC-23, AC-25, AC-26, AC-29 a, AC-29 b, EC-5, INV-7 |
| `tests/features/infinite_memory_agent/test_infinite_memory_events_lifecycle.py` | 4 / 4 | run | AC-5, AC-6, AC-17, AC-27 |
| `tests/features/infinite_memory_agent/test_infinite_memory_events_pairs.py` | 14 / 14 | run | AC-7, AC-8, AC-9, AC-10 a, AC-10 b, AC-11, AC-12, AC-14, AC-22, AC-28, AC-31, AC-34, AC-35, AC-36 |
| `tests/features/infinite_memory_agent/test_infinite_memory_events_records.py` | 11 / 30 | record, writer | AC-21 (2 tests), AC-24, AC-30 (3 tests), AC-32, AC-37 a, b, f, EC-36, INV-12 |
| `tests/features/infinite_memory_agent/test_infinite_memory_handoff.py` | 7 / 8 | run | AC-16, AC-18, AC-19, AC-33, EC-19, EC-20, INV-24 |
| `tests/test_record_field_validation_event_options.py` | 3 / 3 | helper | AC-37 b, c, d (rows 23) |
| `tests/test_output_text_truncate_marker.py` | 1 / 1 | helper | AC-37 e (row 24) |
| `tests/features/infinite_memory_agent/infinite_events_fixtures.py` | shared helper (no tests) | — | AC-13 via `assert_portable` |

Levels: **run** = a whole `InfiniteMemoryAgent` run where only the model runner is scripted (`ScriptedTree`) and the sink is real; **writer** = a real `InfiniteEvents` with a real workspace, journal, launch tool, and memory; **record** = lib records built directly; **helper** = a lib helper called directly. No mock other than the scripted model runner; no sleeps, no wall-clock values, no network; paths built with `pathlib`, files read as bytes where line endings matter.

## Deliberately not written (and why)

Mirrors the "Tests deliberately NOT written" table of `test-plan.md`:

- **EC-1** (raising sink on `subagent_launched` in a batch of 3): AC-4 raises on every event, including that one, and compares the whole run.
- **EC-4** (`on_event=[]`): the same `callable()` refusal as `42` and `"x"` in AC-21.
- **EC-6, EC-7, EC-28** (`journal.finish` `OSError`, journal start failure, read-only `.runs/`): need a faked journal (a real seam, spec §13) or `chmod`, which Windows does not honor. The `except BaseException` around the run is pinned by AC-5, AC-6, AC-27.
- **EC-8, EC-11** (cancel with 3 pairs; staged entries of a cancelled pair): AC-5's exact kinds list already excludes `subagent_finished`; the rest is #1084 behavior pinned by `test_infinite_memory_resume.py`.
- **EC-9, EC-10** (slow sink, two threads), **EC-12** (uncaught pair error), **EC-23** (two concurrent handoff writers): nothing deterministic to assert without sleeps or threads.
- **EC-14, EC-15 events part, EC-22, EC-29**: behavior unchanged from #1084 or `BaseAgent.handoff`, already pinned elsewhere; the parts that change are covered by AC-23, INV-24, AC-33, AC-16.
- **EC-16 extra spellings, EC-18**: same code path as AC-34 and AC-17.
- **EC-27** (clock change): needs mocking `datetime`, forbidden by spec §13. **EC-35** (symlink swap): needs elevated rights on Windows.
- **INV-5, INV-8, INV-25, INV-30**: either pinned by exact-order tests (AC-2, AC-8, AC-22), only reachable through a faked record (forbidden), or already true and pinned today (would pass before implementation).
- **AC-24 contract file**: owned by the gate `python scripts/generate-sdk-public-api.py --check` (C016), named in the Proof column instead.
- **Non-ASCII key refusal, exact `duration_ms`, no-sink overhead**: unspecified validator, wall-clock dependent, no benchmark harness.

## Red run

Command (from the worktree root):

```
PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider --tb=line
```

Final lines:

```
FAILED tests/features/infinite_memory_agent/test_infinite_memory_handoff.py::test_the_handoff_lists_this_runs_live_entries_by_kind_and_every_card_in_finishing_order
FAILED tests/test_record_field_validation_event_options.py::test_require_number_accepts_zero_only_with_allow_zero
FAILED tests/test_record_field_validation_event_options.py::test_require_utc_datetime_accepts_only_a_zero_offset_at_the_resolution
FAILED tests/test_record_field_validation_event_options.py::test_require_callable_refuses_none_unless_optional_and_async_sinks_when_synchronous
FAILED tests/test_output_text_truncate_marker.py::test_truncate_keeps_the_callers_marker_inside_the_limit_and_the_default_is_unchanged
74 failed, 112 passed in 4.69s
```

74 failures = the 73 new cases + the edited budget test. Every failure is for the right reason (missing symbol, module, keyword, or behavior), counted from the `--tb=line` output:

```
22 TypeError: InfiniteMemoryAgentSettings.__init__() got an unexpected keyword argument 'on_event'
21 ImportError: cannot import name ... from 'vidbyte.lib.dataclasses.infinite'
 7 ModuleNotFoundError: No module named 'vidbyte.context.handoff.infinite'
 6 ModuleNotFoundError: No module named 'vidbyte.agents.infinite.events'
 6 ImportError: cannot import name ... from 'vidbyte.lib.enums.infinite'
 4 AttributeError: 'InfiniteMemoryAgent' object has no attribute 'run_handoff'
 1 TypeError: RecordFieldValidator.require_number() got an unexpected keyword argument 'allow_zero'
 1 TypeError: OutputText.truncate() got an unexpected keyword argument 'marker'
 1 KeyError: 'infinite_run_id'                                  (AC-15)
 1 ImportError: cannot import name 'InfiniteEvent' from 'vidbyte' (AC-24)
 1 AttributeError: ... RecordFieldValidator has no attribute 'require_utc_datetime'
 1 AttributeError: ... RecordFieldValidator has no attribute 'require_callable'
 1 AssertionError: vidbyte/agents/infinite/events.py is missing   (budget test, row 22)
 1 AssertionError: (AC-20) run_finished keys lack 'answer' and 'files'
```

The rest of the touched area is green at the same HEAD:

```
python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider --ignore-glob='*events*' \
  --ignore=tests/features/infinite_memory_agent/test_infinite_memory_handoff.py \
  --deselect tests/features/infinite_memory_agent/test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget
........................................                                 [100%]
112 passed, 1 deselected in 4.08s

python -m pytest tests/test_record_field_validation.py tests/features/agent_output_connectors tests/features/harness_threads/test_harness_threads_records.py tests/test_handoff_agent.py -q -p no:cacheprovider
.......................................                                  [100%]
759 passed in 5.71s

python -m pytest tests --collect-only -q -p no:cacheprovider
6135 tests collected in 3.38s

python lint/run.py
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS

ruff check --config lint/ruff.toml tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py
All checks passed!
```

## Proving the scripts are sound before the feature exists

A red test proves nothing if its script would also break after the feature lands. Two scratch-only checks (in the session scratchpad, nothing committed):

1. **Dry run.** A throwaway pytest plugin dropped `on_event` from `build_agent` and supplied stand-ins for the missing enums, `InfiniteDroppedEntry`, and `InfiniteHandoff.FILE_LINE`. Every run-level script completed (`tree.assert_complete()` passed), and each test then failed only at its first event or handoff assertion. The exception is AC-10 (b), whose ordering hook is the sink itself; its script was checked with a scratch hook on the pair's finish and produced the card `s1 (Initech charges 30 USD per seat): This text is already recorded as #1; do not save it again.`
2. **Card-level facts on today's code.** Probes confirmed what the pairs and handoff tests rely on: the drop and refusal texts (AC-9, AC-10 a, AC-12), the 797-character error review (AC-28), the card's two spellings `['./notes/a.md', 'notes/a.md']` (AC-34), the ASCII journal with `\ud800` kept in the card (AC-35), the journal `[run_started, pair_started, pair_finished, run_finished]` and the wrapped denial texts (AC-36), the resumed answer (AC-18), and finishing order deep/ok/unsure/broken with entry ids 3 superseded, 4, 5 (INV-24).
3. **AC-4 comparison baseline.** Two identical list-sink runs were confirmed to give equal `run_view`/`calls_view` (run id, stamps, tmp path, call ids replaced), so the raising-sink comparison can only fail on a real difference.
4. **AC-30 figures.** A standalone script built every details record at its caps and reproduced the §9.1 Worst case table exactly for all 13 records before the test was written.

## Fixtures

- **Added:** `tests/features/infinite_memory_agent/infinite_events_fixtures.py` — the spec's caps and marker written out as literals (`MARKER = " … [cut]"`, 280/500/120/64/512/5, 32,768 bytes, handoff caps 239,000/15,900/1,000/366,500, the nine titles), the AC-2 script (`ac2_tree` and its texts), and readers: `cut`/`line` (INV-12 restated without `OutputText`), `kinds`, `of_kind`, `one`, `json_sizes`, `assert_portable`, `run_view`, `calls_view`, `event_warnings`. It builds on `infinite_memory_fixtures.py`.
- **Unchanged:** `tests/features/infinite_memory_agent/infinite_memory_fixtures.py` (no diff).
- **Pack docs:** `README.md` (intro, six File Index entries, log line) and `FEATURE.md` (contract bullets, observable outcomes, an "Events and handoff" failure-mode block, Test Suite Map entries, omitted strategies) were extended for the new files, as S020 and the pack rules require.

## Existing test edited (pre-approved row 22 only)

`tests/features/infinite_memory_agent/test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget`: package module count `<= 8` → `<= 9`; `BUDGET_MODULES` gains `vidbyte/agents/infinite/events.py` and `vidbyte/context/handoff/infinite.py`; caps `launch.py` 410 and `vidbyte/lib/dataclasses/infinite.py` 620, every other module 400; the comment says "fourteen"; the docstring says why. No other existing assertion was touched.

## Spec defects and ambiguities found (with how the tests read them)

1. **AC-23 / AC-2 token counts.** The fixture's `DEFAULT_USAGE` has no `total_tokens`, so the reply rollup reports `total_tokens=None` and every AC-2 token count is 0. AC-23 scripts `total_tokens` on every step with distinct numbers. The spec does not say this.
2. **AC-36 wording.** "The tool result starts with `Tool denied by middleware:`" is false for what the model sees: the content is `[tool_error kind=middleware_denied]\nTool denied by middleware: ...`. The test checks with `in`, as the delegation tests do.
3. **§9.1 whole-event figures** are about 2 bytes off an independent construction (the details figures match exactly). Events are checked only against the 32,768-byte bound, not the per-event figure.
4. **AC-32** says the two keys "differ only in their first character", but both start with `root`; read as the first character of the first task name (position 5).
5. **AC-30** does not name the refused field for an over-cap committed or dropped item; the test accepts a field name that starts with `InfiniteSubagentFinishedDetails.committed` or `.dropped`.
6. **AC-37 (f)** calls `generator_finished` with no earlier `subagent_launched`, but D-17 measures `duration_ms` from that event; the implementer must default it (for example 0) rather than raise.
7. **AC-18** does not fix where `NO_ANSWER` sits in Outcome; the test checks that both the task and `NO_ANSWER` are in it.
8. **Phase note, not a defect:** with row 22 applied the budget test stays red until both `events.py` (P2) and `context/handoff/infinite.py` (P3) exist, because the existing `is_file()` check now covers them.

## Niche facts for the implementer

- Feature imports are inside test bodies (pack rule), so a missing module fails one test, never collection.
- Warning text compared exactly: `infinite_event_failed run_id=<id> kind=<kind.value> error_type=<type>`; `str()` of a `(str, Enum)` member on 3.11 is `InfiniteEventKind.RUN_STARTED`, so pass `.value`; no `exc_info`.
- Key digest: `hashlib.sha256(pair_key.encode("ascii")).hexdigest()[:16]`, lowercase; shortened pair key is exactly 508 characters; agent keys add `/gen` or `/ver`.
- `cost_usd` is `None` unless every part's `UsageRollup` has `cost_complete=True`; a missing or foreign `usage_rollup` is 0 tokens and unknown cost.
- Item records (`InfiniteCommittedEntry`, `InfiniteDroppedEntry`) accept full-length text; only the details record cuts and refuses.
- Internal constructors called with keywords: `InfiniteLaunchTool(settings, workspace, journal, key=, depth=, extras=, events=)`, `InfiniteAgentMemory(workspace, key=, role=, run_id=, depth=, events=)`, `InfiniteEvents(on_event, run_id)`, `InfiniteRunJournal.start(root, task)`.
- Do not edit `infinite_memory_fixtures.py`, any existing test, or the caps and marker in `infinite_events_fixtures.py`. AC-25 needs a POSIX bash (Git for Windows bash locally).

## The test most likely to catch a real bug

AC-10 (b), `test_an_entry_a_sibling_committed_first_is_reported_dropped_with_the_rule_message`: the order is forced (sibling `a` commits first; `b`'s verifier waits for `a`'s `subagent_finished`), and the reason for `b`'s drop today exists only as card text from the commit path. An implementation that builds `dropped` from the verifier outcome alone reports it as `verifier`/`unchecked` or as committed. Runner-up: AC-4, which compares a raising-sink run with a list-sink run file by file and model call by model call, so any emission point that is not shielded or that changes state shows up.

## Open items

None blocking. Defects 1–7 above are interpretations recorded in the tests and `test-plan.md`; the orchestrator may want S1 to fold 2, 4, and 6 into the spec text.
