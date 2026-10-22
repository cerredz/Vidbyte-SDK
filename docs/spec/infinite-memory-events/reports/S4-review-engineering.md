LENS: engineering
VERDICT: MERGEABLE AFTER FIXES. The event path and the handoff are sound on size, ordering, cancellation and sink isolation, but a symlink loop in the workspace makes `run_handoff` raise for every run, and the test pack lets 14 of 42 plausible regressions through (5 more survivors were dismissed as equivalent or outside the diff), including the D-18 cost rule, EC-17 in the handoff, and the NFR-2 no-sink measure.

Reviewed: `git diff 7efceb5504b0d2ac64a3b5874ada635a47ac35cf...24297ccf`. The worktree HEAD is 41bf4988, its code is identical to 24297ccf, and the tree is clean. All mutations ran in a scratch copy outside the repo, which has its own throwaway git: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/3e21357e-da06-45b9-8218-c0b25aec2a6d/scratchpad/mut`. The baseline there is 186 passed.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **Sink isolation and cancellation are exact, and the tests guard them.**
  - `_shielded` catches only `Exception`.
  - The runtime's `except BaseException: events.run_stopped(exc); raise` re-raises.
  - `run_stopped` sorts the cause into FAILED or CANCELLED.
  - A returned coroutine is closed.
  - Mutations to any of these four were killed: `shield_baseexception`, `runtime_except_exception`, `stop_all_failed`, `coroutine_not_closed`. Leave them as they are.
- **Durable-before-announced holds, and the tests guard it.**
  - `pair_started` is written before `subagent_launched`, and `pair_finished` before `subagent_finished` (launch.py:148-153, :369-383).
  - Both mutations that swap the order were killed: `launch_before_durable`, `finish_before_durable`.
- **The size bounds hold to the byte.**
  - An independent probe built every details record at its worst case: U+1F600, `\x01`, `\x00`, `"`, `\`, space and `é` at every cap, keys of 512 characters, counts at 2^63−1, and the longest enums.
  - It reproduced every details figure in the spec §9.2 table exactly. The maximum is 27,015 bytes, for `subagent_finished`.
  - The key digest and its room arithmetic are pinned: `key_digest_wrong_string` and `key_room_off_by_one` were killed.
  - The handoff bound comes out at about 366,403 characters, 23 chunks of 16,000 at most.
- **Model text cannot steer the shape of the JSON.**
  - No details record has a Mapping field, so no model-controlled string ever becomes a JSON or Mongo key. That rules out `$`, dots and NUL as key characters.
  - Enums serialize by value.
  - One-line fields refuse `\u2028`.
  - `.runs/` is left out of the caps and of grep (INV-25).

## FINDINGS

R-E1 [Major] [failure modes / security] vidbyte/agents/infinite/workspace.py:251 — `InfiniteWorkspace.relative` lets RuntimeError escape, so one looped note breaks `run_handoff` for every run in the workspace

- **Evidence:**
  - The code is `except (ToolExecutionError, ValueError, OSError): return path`.
  - The module header says "relative names a note … and never raises". On Python 3.11, which is the floor in `requires-python = ">=3.11"`, `Path.resolve()` raises `RuntimeError("Symlink loop …")`. A RuntimeError is not an OSError.
  - Line 130 of agent.py calls `relative` on every description in `files.jsonl`, from all runs.
  - `scratchpad/demo/loop_handoff_other_run.py` sets this up: a description recorded by an earlier run, for `notes/a.md`, where `a.md` and `b.md` link to each other, and a journal for this run with `files=[]`. It printed:
    ```
    workspace.relative RAISED RuntimeError Symlink loop from '…\memory\notes\b.md'
    run_handoff RAISED RuntimeError Symlink loop from '…\memory\notes\b.md'
    ```
  - `scratchpad/demo/loop_handoff.py`, where the looped note is in this run's `files`, gave the same result.
- **Failure:**
  - A model that has a bash tool can cause this. The workspace header expects bash to change the folder between any two calls. So can a developer process. It only takes replacing a note it wrote with a symlink loop.
  - After that, `run_handoff` raises for every run in the workspace, including runs that never touched the note.
  - In the event path, `subagent_finished` is dropped through the shield (events.py:250). Each such pair loses one event and logs one warning.
- **Smallest fix:**
  - Add `RuntimeError` to the except tuple. In the scratch copy, both demos then printed `run_handoff OK`, and the pack still gave 182 passed.
  - Add one test that monkeypatches `FileSystemPermissions.resolve_scoped_path` to raise RuntimeError.
- **Spec IDs:** FR-16, T-2 (a model action breaking the upload), EC-3.

R-E2 [Major] [test quality] vidbyte/agents/infinite/events.py:396 — the D-18 cost-completeness rule is untested for usage built from several parts or from none

- **Evidence:**
  - The code is `known = bool(rollups) and all(isinstance(rollup, UsageRollup) and rollup.cost_complete and rollup.cost_usd is not None for rollup in rollups)`.
  - Mutation `cost_any_not_all` (`all(` → `any(`) gave `SURVIVED :: 186 passed`.
  - Mutation `cost_empty_rollups_known` (drop `bool(rollups) and`) gave `SURVIVED :: 186 passed`.
  - The test plan points EC-14's usage to "AC-23's code path" (test-plan.md:81), but AC-23 asserts tokens only.
  - AC-37f uses single rollups only.
- **Failure:** either regression ships green.
  - **`any`:** say the generator is priced at $0.02, and the verifier's rollup has `cost_complete=False`. Then `subagent_finished.cost_usd` becomes 0.02 and is presented as the pair's total, when it should be `None`.
  - **No `bool(rollups)`:** say the generator raised before it replied, so the pair has no replies. Then `cost_usd` becomes `0.0` and not `None`. That shows "unknown" as 0 dollars, which D-18 forbids.
- **Smallest fix:** add two cases to `test_generator_usage_is_read_from_the_reply_rollup_and_unknown_cost_is_none`, or a sibling test, through `subagent_finished`:
  - a pair of rollups, (complete 0.02, incomplete 0.01), expects `cost_usd is None`;
  - a pair with `replies == ()` expects `(0, None)`.
- **Spec IDs:** D-18, EC-3, EC-14, AC-23, AC-37(f).

R-E3 [Major] [test quality] vidbyte/agents/infinite/agent.py:172 — the handoff half of EC-17 has no test; removing the surrogate replacement passes all 186 tests, yet `run_handoff` crashes

- **Evidence:**
  - The code is `return OutputText.truncate(body.encode("utf-8", errors="replace").decode("utf-8"), cap, …)`.
  - Mutation `handoff_no_surrogate_fix` gave `SURVIVED :: 186 passed`.
  - `scratchpad/demo/surrogate_handoff.py` builds a journal whose `answer` holds `"\ud800"`, then calls `run_handoff`:
    - on the baseline: `OK ': final_response\n\nPrices checked ? done.'`
    - with the mutation: `RAISED UnicodeEncodeError 'utf-8' codec can't encode character '\ud800' … surrogates not allowed`
- **Failure:** the journal stores a model's lone surrogate as ASCII JSON, and the surrogate comes back when the journal is read. With the replacement gone, `run_handoff` cannot write the handoff for that run, and no test notices.
- **Smallest fix:** extend AC-35, or add a test, to write a finished journal with `answer="…\ud800…"`. Assert that `run_handoff` succeeds, that the Outcome holds `?`, and that the file decodes as UTF-8.
- **Spec IDs:** EC-17, INV-23, AC-35.

R-E4 [Major] [test quality] vidbyte/agents/infinite/events.py:341 — the NFR-2/INV-9 measure, "0 `InfiniteEvent` instances" with no sink, is never measured, and the guard in `_deliver` hides a missing early return

- **Evidence:**
  - The code is `returned = self.on_event(event) if self.on_event is not None else None`.
  - Mutation `no_sink_still_builds` removed the `if self.on_event is None: return` in `memory_staged`. Result: `SURVIVED :: 186 passed`.
  - Removing only the `_deliver` guard also gave `186 passed`.
  - Removing both gave `FAILED …test_without_a_sink_the_journal_gains_only_answer_and_files_and_nothing_is_logged — 1 failed, 185 passed`.
  - NFR-2 says: "0 `InfiniteEvent` instances … (AC-20)". The test plan (test-plan.md:98) declines this for lack of a benchmark harness, but counting instances needs no benchmark.
- **Failure:** with no sink, a refactor can drop any of the 14 early returns. Every memory call, launch and file write would then format text and validate records of up to 27 KB that nobody reads. INV-9 would be broken, and the suite would stay green.
- **Smallest fix:** delete the redundant `if self.on_event is not None else None` in `_deliver`. A missing early return then raises TypeError into the shield, which logs it, and the existing AC-20 assertion "events module logs nothing" catches it. The scratch run above shows this.
- **Spec IDs:** NFR-2, INV-9, AC-20.

R-E5 [Major] [test quality] vidbyte/agents/infinite/events.py:146-148, :163 — the counts that must cover every depth are only tested at the root, next to root-only helpers that would be an easy swap

- **Evidence:**
  - `interrupted = journal.interrupted`, `finished=self._count(len(journal.cards))`, and `pairs=self._count(len(journal.cards))`.
  - The journal also has the older root-only `finished_children(key)` and `interrupted_children(key)`.
  - Each swap to the root-only helper was run as a mutation:

    | Mutation | Result |
    |---|---|
    | `resumed_root_only_finished` | SURVIVED, 186 passed |
    | `resumed_root_only_interrupted` | SURVIVED, 186 passed |
    | `run_finished_root_pairs` | SURVIVED, 186 passed |

  - AC-5 resumes with `finished=0` and one root-level interrupted pair. AC-2 is a one-pair run.
- **Failure:** take a resumed run where a depth-2 pair finished and another was interrupted. `run_resumed` would report `finished` and `interrupted` without them, `run_finished.pairs` would undercount, and nothing would fail.
- **Smallest fix:** run a two-level script once with a list sink. Assert:
  - `run_finished.details.pairs == 2`;
  - when the nested pair is interrupted, then resumed, `run_resumed.details.interrupted` contains the nested key and `finished` counts the nested card.
- **Spec IDs:** FR-13, AC-5, §9.1 rows `run_resumed` and `run_finished` ("pair keys, all depths").

R-E6 [Minor] [test quality] vidbyte/agents/infinite/events.py:187, :220, :375, :148 — nested attribution and verifier/interrupted key shortening are not pinned

- **Evidence:** four mutations survived, each with 186 passed:

  | Mutation | Line | What it does |
  |---|---|---|
  | `batch_rejected_root_envelope` | :187 | attributes `batch_rejected` to the root |
  | `replayed_root_envelope` | :220 | attributes `subagent_replayed` to the root |
  | `key_no_verifier_suffix` | :375 | drops the `/ver` branch of `_key` |
  | `interrupted_not_shortened` | :148 | stops shortening interrupted keys |

  AC-22 covers `subagent_launched` only. AC-32 covers generator keys only.
- **Failure:**
  - A nested launcher's rejections and replays would land under the root in the dashboard tree.
  - A key over 512 characters, at a deep verifier or among interrupted keys, would fail `InfiniteEvent` validation. That event would then be dropped through the shield.
- **Smallest fix:** add to AC-22, as a parametrized nested case, a rejected batch and a replay from a depth-1 launcher. Add a verifier key and an interrupted key over 508 characters to AC-32.
- **Spec IDs:** INV-11, D-25, AC-22, AC-32.

R-E7 [Minor] [test quality] vidbyte/agents/infinite/agent.py:138, memory.py:104, events.py:230 — three data rules that the field table states are unpinned

- **Evidence:** three mutations survived, each with 186 passed:

  | Mutation | Location | What it does |
  |---|---|---|
  | `handoff_drop_root_files` | agent.py:138 | drops `*journal.root_files` from Files |
  | `description_on_append` | memory.py:104 | reports `description` on an append |
  | `duration_seconds` | events.py:230 | gives `duration_ms` in seconds |

  AC-33's root note is created, so it already appears through `created`. AC-11's append passes no description.
- **Failure:**
  - Notes the root only appended to or edited would vanish from the handoff's Files.
  - A `description` the model passed on an append would appear, when the rule is `""` unless created.
  - `duration_ms` would be 1,000× too small.
- **Smallest fix:**
  - Have AC-33 or AC-18's new-journal case append as the root to a note that already exists.
  - Have AC-11 pass a description on the append.
  - Patch `time.monotonic` in one pairs test. Spec §13 does not forbid this.
- **Spec IDs:** FR-13, EC-21, §9.1 `file_written` and `generator_finished`, AC-11, AC-33.

R-E8 [Minor] [data and scale] vidbyte/agents/infinite/agent.py:130 — `run_handoff` resolves every description the workspace has ever recorded, so its cost grows with the whole history

- **Evidence:**
  - The code is `described = {workspace.relative(path): text for path, text in workspace.descriptions().items()}`. That covers all runs.
  - `write_note` already stores the relative path (workspace.py:184).
  - `scratchpad/demo/relative_cost.py` measured `relative(): 214 us per call`.
- **Failure:**
  - One run with 1,000 agents, each creating 10 notes (`INFINITE_NEW_FILES_PER_AGENT = 10`), adds 10,000 descriptions, which is about 2.1 s of resolving per handoff.
  - The cost grows linearly over every later run, because each call resolves all of it again.
  - This is also why R-E1 reaches runs that never touched the looped note.
- **Smallest fix:** resolve only the paths the handoff lists. For example, build `paths` first and keep `{p: text for p, text in workspace.descriptions().items() if p in set(paths)}`, then resolve only the leftover keys. [scope-adding: follow-up]
- **Spec IDs:** FR-16 (n/a for a hard bound).

R-E9 [Minor] [security / error handling] vidbyte/lib/dataclasses/validation.py (`require_callable`, `synchronous`) — a `functools.partial` of an object with an async `__call__` passes the settings check

- **Evidence:** a direct probe of `RecordFieldValidator.require_callable(..., optional=True, synchronous=True)` printed:
  ```
  partial(async def) -> refused ConfigurationError
  partial(async __call__ object) -> ACCEPTED
  bound method of async __call__ -> refused ConfigurationError
  ```
  The check is `inspect.iscoroutinefunction(value) or inspect.iscoroutinefunction(type(value).__call__)`.
- **Failure:** EC-31 lists "an object with an async `__call__`, or a `partial` of one". Such a sink is accepted when the settings are built. Every event is then dropped, with one warning per event, by the coroutine guard in `_deliver`. The run is not blinded silently, but it is blinded late, not refused up front.
- **Smallest fix:** unwrap partials (`while isinstance(value, functools.partial): value = value.func`) before both checks. Add the case to the AC-21 parametrization.
- **Spec IDs:** EC-31, INV-36, T-1.

## Not findings (checked and dismissed)

- `finished_files_writer_only` survived, but launch.py:266 is outside this diff (#1084 code).
- `staged_before_append` and `dropped_before_remove` survived, but the sink receives a record, not the list, so the order cannot be observed (equivalent mutants).
- `handoff_atomic_off` survived. Atomicity cannot be observed in-process, and the code passes `atomic=True`.
- `relative_no_resolve_fallback` survived. The ValueError branch is only reachable when the scope root and `self.root` disagree.
- A slow sink blocks the loop by design (EC-9, NG-5, D-4), which is decided and documented.
- KeyboardInterrupt raised inside the sink on the opening event gives no `run_stopped`, which matches D-9.
- There is no threading: ParallelPipeline uses `asyncio.gather` on one loop. Memory events fire after the workspace call returns, outside its lock.

## VERIFIED CLAIMS

1. **The tests are untouched and green at HEAD: held.**
   - The worktree pack gave `186 passed in 6.18s`.
   - `git status --porcelain` printed nothing.
   - HEAD is 41bf4988, with code identical to 24297ccf.
2. **The details worst case is 27,015 bytes and every row of §9.2 is exact: held.** The probe's details figures matched the table exactly.
3. **The whole event is at most 32,768 bytes: held. The forwarded figure "≤ 31,091" (spec.md:651) is 2 bytes low.**
   - `datetime.isoformat()` of a millisecond-stamped `at` gives 31,093. With microsecond 0 it gives 31,086.
   - Every consumer bound is 65,536 or 32,768, so this changes nothing. It is noted, not raised as a finding.
4. **The handoff takes at most 23 chunks: held.** The page overhead around the section bodies is about 203 characters, which is within 300. 239,000 + 8 × 15,900 + 203 ≈ 366,403, which is within 366,500 and so ⌈366,403 / 16,000⌉ = 23. By sections with headings it is 15 + 8 = 23, since "## Unverified or failed work\n" is 29 characters, under the 100-character room.
5. **No model-controlled JSON keys: held.** No details record has a Mapping field.
6. **The cost rule is correct as written: held.**
   - `_usage` matches D-18 for single and multiple parts, and for no parts.
   - `cost_unknown_zero` and `cost_ignores_complete` were killed.
   - The multi-part and no-part branches are unpinned (R-E2).
7. **The cancel path announces and re-raises: held.** The lifecycle test killed `runtime_except_exception`, `generator_finished_after_yield` and `run_stopped_message_repr`.
8. **The `files.jsonl` description is already relative: held.** workspace.py:184 writes `{"path": relative, …}`.
9. **"`relative` never raises" (workspace.py header): did NOT hold.** See R-E1.
10. **EC-31 covers a partial of an async-call object: did NOT hold.** See R-E9.

## COMMANDS RUN

- `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider` (worktree)
  - `186 passed in 6.18s`
  - `git status --porcelain` printed nothing; `git rev-parse --short HEAD` printed `41bf4988`.
- `PYTHONIOENCODING=utf-8 PYTHONPATH=<worktree> python scratchpad/sizes.py`
  - `overall details max 27015 event max 31093`
- `python scratchpad/envelope.py`
  - `0 31086 '2026-10-16T00:00:00+00:00'`
  - `123000 31093 '…00.123000+00:00'`
- `python scratchpad/mutate.py`, batch 1 of 29 mutations: 18 KILLED, 11 SURVIVED. The survivors were:

  | Survivor | Finding |
  |---|---|
  | `cost_any_not_all` | R-E2 |
  | `no_sink_still_builds` | R-E4 |
  | `handoff_no_surrogate_fix` | R-E3 |
  | `resumed_root_only_finished` | R-E5 |
  | `resumed_root_only_interrupted` | R-E5 |
  | `batch_rejected_root_envelope` | R-E6 |
  | `replayed_root_envelope` | R-E6 |
  | `key_no_verifier_suffix` | R-E6 |
  | `interrupted_not_shortened` | R-E6 |
  | `description_on_append` | R-E7 |
  | `duration_seconds` | R-E7 |

- `python scratchpad/mutate.py <batch 2>`, 13 mutations: 5 KILLED, 8 SURVIVED.
  - Killed: `handoff_drop_created`, `generator_finished_after_yield`, `run_stopped_message_repr`, `require_callable_no_type_call`, `launched_key_in_details_not_shortened`.
  - Survivors:

    | Survivor | Where it went |
    |---|---|
    | `cost_empty_rollups_known` | R-E2 |
    | `run_finished_root_pairs` | R-E5 |
    | `handoff_drop_root_files` | R-E7 |
    | `finished_files_writer_only` | dismissed |
    | `staged_before_append` | dismissed |
    | `dropped_before_remove` | dismissed |
    | `handoff_atomic_off` | dismissed |
    | `relative_no_resolve_fallback` | dismissed |

- `python scratchpad/demo/surrogate_handoff.py`
  - Baseline: `OK ': final_response\n\nPrices checked ? done.'`
  - Mutated: `RAISED UnicodeEncodeError … surrogates not allowed`
- `python scratchpad/demo/loop_handoff.py` and `python scratchpad/demo/loop_handoff_other_run.py`
  - Both printed `run_handoff RAISED RuntimeError Symlink loop from …`.
  - With `RuntimeError` added in scratch, both printed `run_handoff OK`, and the pack gave `182 passed in 5.99s`.
- A `require_callable` probe: `partial(async __call__ object) -> ACCEPTED`.
- `_deliver` guard experiment:
  - Guard removed only: `186 passed`.
  - Guard and one early return removed: `1 failed, 185 passed` (the AC-20 test).
- `python scratchpad/demo/relative_cost.py`
  - `relative(): 214 us per call; … 300,000 calls ~ 64.3 s per run_handoff`
