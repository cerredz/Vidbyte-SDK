# S1 spec author report — infinite-memory-events (r1)

- **Status:** DONE
- **Spec:** `docs/spec/infinite-memory-events/spec.md`, revision 1, committed as `5c88ffb9` (only `spec.md` is in the commit; the orchestrator's uncommitted edits to `pipeline.md` and `request.md` were left untouched).
- **Base:** `ff1bc933` (PR #1084 head), worktree HEAD before the commit `9131138d`.

## Approach chosen

There is one per-run `InfiniteEvents` class in a new module of the agent package, `events.py`. The runtime builds it after the journal opens and passes it explicitly to the following: the root memory, the launch tool, child launch tools, and each pair's generator and verifier memories.

**Events.** There is one public method per event kind. Each method returns at once when there is no sink. Otherwise it builds a flat, frozen details record. Each kind has its own details record, with the field names of the request's §B table. Texts are capped with `OutputText.truncate`, and the summary is built from a template constant and passed through `OutputText.single_line`. The method then calls the sink synchronously on the loop thread. Any `Exception`, whether raised while building the event or by the sink, is caught, logged as error type only, and dropped. A `BaseException` propagates.

**Emission order.** Every event that reports a change on disk is emitted after that change is written.

**`run_stopped`.** It is emitted from a `try` / `except BaseException: ...; raise` block in `runtime.arun`. That block covers everything after the opening event, including `journal.finish`, so a failed finish counts as stopped.

**Run id.** It is added to the reply through `replace(result, metadata=...)`.

**Handoff.**
- The class is `InfiniteHandoff`, in the context layer's `handoff/` package. Its static renderers take lib records.
- `InfiniteMemoryAgent.run_handoff` gathers the inputs and assembles the nine sections. It writes `.runs/<id>.handoff.md` and makes no model call.
- To make a handoff possible for any past run, the journal's existing `run_finished` record gains `answer` and `files`. Both are read with defaults, so old journals still load.
- The workspace gains two readers: `run_entries(run_id)` and `descriptions(run_id=None)`.

**Drops and commits.** A pair's drop and commit lists become structured records (`InfiniteDroppedEntry` and `InfiniteCommittedEntry`). The card text is rendered from them and is byte-identical to before.

## Smaller designs rejected (spec §8.3)

- **Calling `on_event` inline at about 14 call sites, with no class.** Rejected because it fails FR-5 (a single class), INV-7 and INV-8 (every site would need its own try/except, and `launch.py` has no room for that), and the typed records.
- **Tailing the journal.** Rejected because 10 of the 14 kinds are not in the journal.
- **Keeping drops as free text.** Rejected because the drop reason would not be machine-readable.

## Budget (spec §8.4)

- New production files: 2 (`vidbyte/agents/infinite/events.py` and `vidbyte/context/handoff/infinite.py`).
- New classes: 21 in total: 15 records, 4 enums, `InfiniteEvents`, and `InfiniteHandoff`.
- New config keys: 1 (`on_event`).
- New dependencies: 0.

The #1084 contract test `test_new_modules_stay_inside_the_complexity_budget` cannot hold this design, so the spec uses the orchestrator's pre-approved single test edit. It is §12.3 row 22, owned by S2:

| Limit | Before | After | Why |
|---|---|---|---|
| Modules in the agent package | 8 | 9 | `events.py` |
| Lines in `vidbyte/agents/infinite/launch.py` | 400 | 420 | about 405 estimated; it had 16 lines of headroom |
| Lines in `vidbyte/lib/dataclasses/infinite.py` | 400 | 560 | about 525 estimated |

Every other module stays at 400.

## Counts

| Item | Count |
|---|---|
| Goals | 4 |
| Non-goals | 11 |
| Invariants | 32 (7 of them "must not regress") |
| Acceptance criteria | 28 |
| Edge cases | 29 |
| Functional requirements | 20 |
| Non-functional requirements | 9 |
| Design decisions | 23 |
| Threat rows | 4 |
| Work items | 10 |
| §12.3 rows | 22 (2 CREATE) |
| Assumptions | 8 |
| Questions | 3, all non-blocking with default "no" |

## Verification done by S1, independent of the spec text

- **Baseline on `9131138d`:**
  - The infinite test pack: 112 passed.
  - `generate-sdk-public-api.py --check` reports the contract is current (644 exports).
  - `lint/run.py` passes. It reports "S063 IMPROVED 4->3", which was already there before this work.
  - `run_ci.py --stage source` (with PYTHONPATH): 3 failed, 5959 passed, 16 skipped. All 3 failures are pre-existing branch-scoped `harness_threads` surface tests, which the field guide's `local-ci-verification.md` documents.
  - The package stage was not run.
- **Standalone probe on Python 3.11.0 (Windows):**
  - A SIGINT during `asyncio.run` gives the coroutine `CancelledError`, and the caller then gets `KeyboardInterrupt`. This supports A-1.
  - `dataclasses.asdict` on frozen, slotted records holding tuples of records, str enums, and `datetime` produces output that `json.dumps(..., default=isoformat)` serializes, with str enums written as their values.
  - `OutputText.truncate` keeps output at or under the cap.
  - The §4 summary line renders exactly as the spec prints it.
- **Source checks:**
  - `launch_subagent` refuses duplicate task names (used in AC-7).
  - No `run_handoff`, `InfiniteEvent`, `InfiniteHandoff`, or `infinite_run_id` exists anywhere yet.
  - Memory and launch tools are async `BaseTool`s; no `to_thread` offload exists on these paths. This supports A-2.
- **Self-check (scripted):**
  - All 18 sections are present.
  - No ID gaps, and no reference to an undefined ID.
  - Every AC maps to a W row.
  - The number of CREATE rows equals the §8.4 new-file count.
  - Every row names a governing standard.
  - No repository file paths appear outside §11–§14, except where the template allows them (§8.2 and §13).
  - The weighted words from request §D are cited in the FR/NFR sources. "once every 50 iterations" and the server-side-token part of the dashboard request are NG-1 and NG-2, which belong to the sibling runs. "make all the prs" is a process instruction (stage S6).
- **Tool state:** `semgrep` crashes on import in the global Python (semgrep 1.170.1 against the installed `mcp` 2.x). The spec says to run it from a scratch venv with `mcp<2`, or to rely on the Static policy run.

## Niche facts for the next agents

**Contract names (from §8.5):**
- `InfiniteEvents` has 14 methods named after the event kinds.
- Details records: `Infinite{RunStarted,RunResumed,RunFinished,RunStopped,Refusal,SubagentLaunched,SubagentReplayed,GeneratorFinished,SubagentFinished,MemorySaved,MemoryStaged,FileWritten}Details`, plus `InfiniteCommittedEntry` and `InfiniteDroppedEntry`. `memory_dropped` uses `InfiniteDroppedEntry` as its details.
- Enums: `InfiniteDropReason`, `InfiniteFileChange`, `InfiniteStopCause`.
- Constant: `INFINITE_RUN_ID_METADATA_KEY`.
- Journal: `InfiniteRunJournal.load`, `.cards`, `.interrupted`, `.answer`, `.root_files`.
- Workspace: `InfiniteWorkspace.run_entries` and `.descriptions`.

**Pair events:** `batch_rejected`, `subagent_launched`, `subagent_replayed`, and `subagent_finished` all carry the *launcher's* `agent_key`, `role`, and `depth`. The pair itself is named in the details (`name`, `key`, and `parent`/`depth` on launch).

**Exactly-once memory reporting:**
- `memory_saved` is emitted for the root's own commits only.
- A pair's commits appear only in `subagent_finished.details.committed`.
- A verifier's `drop_entry` emits `memory_dropped` and also appears in `dropped`.

**Fixture name clash:** the test fixtures already have a helper named `events(records)` that returns journal record names. New event lists in tests should use a different name.

**Fields added beyond the §B table, which sibling specs should accept:** `run_resumed.task`, `file_written.description`, and `drops.note`. A worst-case `subagent_finished` at default settings is about 30 KB, because `files` is bounded only by `max_files`.

**Rules most likely to be broken:**
- Card `dropped` strings must stay byte-identical. Tests substring-match them.
- The journal after a cancel must be exactly `[run_started, pair_started]`.
- Do not catch `BaseException` in `InfinitePair.run`.
- S019 applies to the runtime's `except BaseException` block.
- A001 headers on the two new files.
- S020: `events.py` must be added to the README File Index.
- C016: regenerate the public-API contract after the `__init__` commit.

## Open items

- Q-1: write the handoff automatically when a run finishes? Default: no.
- Q-2: emit `memory_saved` for pair commits too? Default: no.
- Q-3: export the details records from `vidbyte`? Default: no.
- A-4 needs confirmation from the sibling specs: they accept the extra details fields, and the backend's details byte cap is at least about 32 KiB (or the CLI trims `files`).
- This report is not committed. The commit instruction named only `spec.md`.

---

## Addendum: revision r2 (2026-10-16, revision round 1)

**Status:** DONE. spec.md r2 committed as `a27ff27c`, on top of `91576d73`, which sits on `7efceb55` (the merged #1113). Only `spec.md` was staged. `pipeline.md` (the orchestrator's edit) and this report are left uncommitted.

### What changed and why
- **Re-baseline (R-1, ruling 1).** `base_commit` is now `7efceb5504b0d2ac64a3b5874ada635a47ac35cf`. Every path:line, symbol, and line count was re-read at the new base. The records validate only through `RecordFieldValidator`/`RecordFieldConverter`, with qualified `Record.field` names and no `_..._field` helpers. Missing checks become backward-compatible options in a new row 23: `require_number(allow_zero=)`, `require_utc_datetime`, and `require_callable(optional=, synchronous=)`. The handoff write is `write_text(..., newline="\n", atomic=True)`. Row 22 raises only the lib records module (400 → 600), keeps `launch` at 400 (368 now, about 392 estimated), sets the module count 8 → 9, and adds `events.py` and `context/handoff/infinite.py` to `BUDGET_MODULES` (R-13). r1's separate `journal.load` became `find(..., unfinished=False)` (D-29).
- **Event size bound (R-2, ruling 2).** The settings validators have no maximum on any cap, so every event cap is a fixed constant. Every field has a cap: summary 280, text 500, path 500, line 120, label 64, keys 512 ASCII, staged keys 64. Lists hold 5 items plus an `*_omitted` count, and summaries count the full lists. Ints are at most 2^63 − 1, with larger settings clamped. Keys use the digest rule in D-25: over 508 characters, a key becomes `~` + 16 hex digits of its SHA-256 + `/` + its last 490 characters, and the agent key adds `/gen` or `/ver`. A lone surrogate becomes `?`. Text is cut by `OutputText.truncate`, which gains a `marker=` keyword (row 24), with `INFINITE_TRUNCATION_MARKER`, so the stream has one marker (R-11). `memory_dropped` gets its own `InfiniteMemoryDroppedDetails`. Details records number 13, and there are 16 records in total.
- **Handoff bound (R-5, ruling 3).** The SDK owns the bound. Outcome is at most 239,000 characters, the other eight sections at most 15,900 each, and every list line at most 1,000. The total is at most 366,500, so it fits 23 chunks of 16,000 however the CLI splits it: by section body, by section including its heading, or as one text. The final values are tighter than the 240,000/16,000 in my first r2 draft, so a heading always fits in the same chunk as its body.
- **Async sink (R-4, ruling 4).** Settings refuse coroutine functions, an async `__call__`, and partials of either. A returned awaitable is closed and logged as a `TypeError` sink failure. Async support is Q-5, default no (D-27 explains why, compared with `ledger_controller` and `workflows/contracts.py:514`).
- **Paths (R-3).** The new `InfiniteWorkspace.relative` gives workspace-relative POSIX paths in events and the handoff, with `files` deduplicated per path. NG-11 is struck. INV-10, NFR-9, and T-3 are narrowed: the SDK builds no absolute path itself, and free text passes through capped. A-9 says the CLI scrubs, and Q-4 (SDK-side placeholders) defaults to no.
- **Other findings.** R-6: all handoff wording moved inline into `InfiniteHandoff`, and the drop notes stay inline at their sites. R-7: atomic writes with LF line endings. R-8: AC-4 normalizes run ids and timestamps, and AC-20 checks exact record key sets. R-9: INV-9 rewritten. R-10: D-21 and A-4 list `error_type` and `batch_rejected.tool`. R-12: `@contextmanager _shielded(kind)` plus `_deliver`.
- **Found while revising (not raised by a reviewer).** `AgentLoopSettings.max_iterations` can be `None`, so `run_started.max_iterations` is `int | None`, and AC-31 passes it through `loop=AgentLoopSettings(...)`.

### Baselines at HEAD `91576d73` (base `7efceb55`)
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`: 113 passed (4.89 s), with vidbyte imported from the worktree.
- `python scripts/generate-sdk-public-api.py --check`: current at 9eca4a33 (vidbyte-sdk 0.3.0, 644 exports).
- `python lint/run.py`: SDK-LINT PASS. S063 still prints the pre-existing "IMPROVED 4 -> 3", which was not updated.
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: 3 failed, 6,043 passed, 16 skipped (97 s). The 3 failures are the known `harness_threads` surface checks against `main`, the same 3 as at r1. Log: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/3e21357e-da06-45b9-8218-c0b25aec2a6d/scratchpad/run_ci_source_r2.log`.

### Worst-case sizes (bytes)
Script: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/3e21357e-da06-45b9-8218-c0b25aec2a6d/scratchpad/worst_case.py`, run with `python -I`. It fills every cap with U+1F600, `\x01`, space, quote, é, and a, and measures 4 serializations.

| Kind | Details, worst of 4 | Compact UTF-8 | Whole event |
|---|---|---|---|
| run_started | 15,450 | 7,861 | 19,526 |
| run_resumed | 8,686 | 5,675 | 12,762 |
| run_finished | 6,930 | 3,535 | 11,006 |
| run_stopped | 6,824 | 3,435 | 10,900 |
| batch_rejected / tool_refused | 6,795 | 3,408 | 10,871 |
| subagent_launched | 25,201 | 13,284 | 29,277 |
| subagent_replayed | 644 | 637 | 4,720 |
| generator_finished | 6,962 | 3,565 | 11,038 |
| subagent_finished | **27,015** | 14,548 | **31,091** |
| memory_saved | 18,023 | 9,238 | 22,099 |
| memory_staged | 6,147 | 3,140 | 10,223 |
| memory_dropped | 1,658 | 883 | 5,734 |
| file_written | 13,544 | 6,815 | 17,620 |

### Stage E self-check (r2)
All 18 sections are present in template order, and no section is skipped. IDs have no gaps, and every referenced ID is defined. Counts: G 4, NG 13 (NG-11 struck), INV 38, AC 35, EC 36, FR 23, NFR 9, D 29, T 4, W 11, A 10, Q 5 (0 blocking), R 13. All 25 §12.3 rows name their governing standard. The spec contains no test code. The §8.5 names are used consistently. §16 logs R-1..R-13 as accepted. §17 has rows for r1 and r2. §0.2 is still "None yet".

### Open items for the orchestrator
- Forward these to the Vidbyte and CLI runs:
  - Every event's details is at most 32,768 bytes in the worst case (27,015 measured; compact UTF-8 at most 14,548), and a whole event is at most 31,091 bytes.
  - `agent_key` and every key field are ASCII and at most 512 characters, using the digest rule.
  - `summary` is 1–280 characters, and counts are at most 2^63 − 1.
  - The handoff is at most 23 chunks of 16,000 characters (Outcome 239,000, sections 15,900).
  - The CLI must shorten `files.jsonl` `by` keys itself to fit the record `agent_name` limit of 128.
  - The CLI scrubs credentials and home paths in free text (A-9).
  - The field changes from §B are listed in D-21.
- Row 22 touches the module-level `BUDGET_MODULES` tuple, which only the budget test reads (R-13). It is still the single pre-approved edit.
- `launch` has about 8 lines of headroom at 400. If S3 runs out, it must stop with BLOCKED rather than raise the cap.
