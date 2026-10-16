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
