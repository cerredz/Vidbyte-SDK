VERDICT: NEEDS REWORK — the design shape is right and honors every settled decision, but it is grounded on `ff1bc933` code that open PR #1113 is rewriting (helpers, journal internals, settings error details, default caps, line counts), and it leaves event and handoff sizes unbounded across the SDK→CLI→backend boundary.

WHAT THE SPEC GETS RIGHT
- Every fixed-contract item is honored exactly: the 14 kinds, the `InfiniteEvent` fields, `InfiniteEvents` in `vidbyte/agents/infinite/events.py`, `on_event` appended last, `run_stopped` emitted from `except BaseException: ...; raise` with a bare re-raise (S019), `reply.metadata["infinite_run_id"]` set through `replace()` (`AgentResult` is frozen and slotted), `run_handoff` not overriding `BaseAgent.handoff`, no `to_dict`, and the export locations.
- Durable before announced (INV-4), a fail-open shield that catches `Exception` only (D-3), and synchronous inline delivery (D-4) match repo precedent (`multi/ledger_controller.py`, the jev managed logger). This is the boring, correct choice.
- D-8/INV-28: structured drop and commit records rendered byte-identically into the card strings protect the existing substring tests. Adding `answer`/`files` to `run_finished` stays loadable for old journals, because the old `_parse` reads only `stop_reason`.
- The §13 test-seam facts are accurate: the fixtures, the `events()` name clash, the old shape of `run_finished_record()`, the 112-test baseline, and the 3 harness_threads failures that predate this work.

FINDINGS (ranked)

R-1 [Blocker] [L4/L11] §8.2, §11, §12.3 rows 4/5/7–11/13/22, §8.4, D-19, D-22/AC-21, INV-26 — The spec is written against code that open PR #1113 replaces, so S2 would build on files that are about to change
  Evidence: PR #1113 "fix: resolve review comments from PR #1084" (head `ai/resolve-pr-1084-comments` @ `97dc0765`, base `feat/infinite-memory-agent`, OPEN). `ff1bc933` is an ancestor of it, and `3d051b24` is not in `origin/feat/infinite-memory-agent` (now `66f38e72`, with no infinite changes since `ff1bc933`). On the fix branch:
  - `lib/dataclasses/infinite.py` validates through `RecordFieldValidator`/`RecordFieldConverter`, and the `_text_field`/`_text_items`/`_count_field`/`_choice_field` helpers are gone. Its header says: "A check the canonical validators lack becomes a new option or method there, never a helper here."
  - The journal is built on `AppendOnlyJsonl` (`vidbyte/lib/util/jsonl.py`), and `_whole_lines` no longer exists.
  - `LocalFileSystemBackend.write_text` gains `atomic: bool = False`.
  - Settings errors carry `details={"field": "InfiniteMemoryAgentSettings.<name>"}`.
  - Defaults rise 5–10x: max_depth 20, max_parallel 20, max_agents 1,000, max_files 2,000, max_tokens 2,000,000, max_file_tokens 100,000, max_entry_tokens 150, max_entries_per_agent 25, max_iterations 500, INFINITE_NEW_FILES_PER_AGENT 10.
  - Lines after the header: launch 368 (spec measured 384), lib dataclasses 177 (214), workspace 332, memory 251, journal 157, runtime 106, agent 111, settings 196, constants 183.

  Independently of the rebase, field guide `strict-config-dataclasses.md` ("Validate record fields through RecordFieldValidator / RecordFieldConverter; add an option rather than a private field helper"; Check: "The record module defines no `_..._field` helpers") and `class-bound-helpers.md` ("extend an existing class with an option") forbid what §8.2/§11 prescribe: copy the `_text_field` pattern into 15 new records, and row 4's "one new private helper". `vidbyte/lib/dataclasses/validation.py` already exists at the base.
  Failure: S2 implements against stale internals. The PR then conflicts with #1113 in 8+ files. Review rejects the helper pattern a second time. AC-21 (`{"field": "on_event"}`), INV-26 (`_whole_lines`), D-19 (non-atomic write), the §8.4 raises, and the NFR-4/EC-25 byte arithmetic are all wrong after the rebase.
  Smallest fix: Re-baseline the spec on `97dc0765`, or on `feat/infinite-memory-agent` once #1113 merges, before S2 starts. Specifically:
  - Validate every new record through `RecordFieldValidator`, with a qualified `Record.field` name. Add any missing option to `validation.py` as a backward-compatible keyword, in a new §12.3 row.
  - Re-measure §8.4 and row 22. Launch at 368 + ~21 ≈ 389 likely needs no raise.
  - AC-21/D-22: use the qualified field name.
  - D-19: use `write_text(..., atomic=True, newline="\n")`.
  - INV-26: name the behavior (four kinds, order, fsync, torn tail), not private functions.
  - Recompute every size bound from the new defaults.

R-2 [Blocker] [L6/L5] §9.1 Volume, NFR-4, EC-25, A-4 — Details sizes are unbounded, and NFR-4's "≤ ~32 KiB" is false even at the current defaults
  Evidence:
  - `subagent_finished.files` holds raw model paths. They are not deduplicated per file (`./notes/a.md` and `notes/a.md` are separate entries), and neither count nor length is capped, so "bounded by max_files" does not hold.
  - The lengths of `file_written.path`, of `subagent_launched.context` items (≤ 20 items, each of unbounded length), of `extras`, and of `seeds` are not stated.
  - `run_resumed.interrupted` can hold up to max_agents/2 agent keys. No maximum `agent_key` length is stated: it is about 4 + depth × 45 characters, so ~454 at depth 10 and ~904 at the fix branch's depth 20.
  - Worst cases: at `ff1bc933` defaults, `run_resumed` reaches ~45 KB. At #1113 defaults, `subagent_finished` (2,000 files) reaches ~300 KB and `interrupted` ~450 KB.
  - The sibling backend config (`worktrees/vidbyte-agent-run-dashboard/backend/lib/config/agent_runs.py`) caps settings at 65,536 bytes, the body at 4 MiB, a context ref at 512 characters, and `agent_name` at 128 characters. A deep agent key, used as the artifact's writer name, exceeds the 128-character cap.
  Failure: One oversized event makes the whole checkpoint batch (≤ 200 events) fail with a 422. The CLI serializes with plain `dataclasses.asdict`, so nothing trims on the way. The run's dashboard then stalls silently, which is exactly the "debug and monitor" outcome the request exists for.
  Smallest fix: In §9.1, give every list a named item cap and every string a length cap (for example, path ≤ 512), as constants in the infinite constants module rather than settings. Add optional `*_total` counts, and compute summary counts from the full lists. State the maximum `agent_key` length. Make NFR-4 testable as "compact JSON per kind ≤ N bytes at the maximum allowed settings". Rewrite A-4 against the sibling's real caps.

R-3 [Major] [L7/L9] INV-10, NFR-9, T-3 vs EC-16, D-23 — "No absolute developer paths in events" is contradicted by the spec's own design
  Evidence: EC-16 and D-23 keep `file_written.path`, the card files, and the handoff Files section as the raw model path, and EC-16 admits that path can be absolute. `tool_refused.problem`, `batch_rejected.problem`, and `run_stopped.message` pass `str(exc)` through. OSError texts embed absolute paths, the workspace raises `ConfigurationError("The workspace at {self.root}...")`, and `"{path} is outside the workspace"` echoes the model's path. The repo norm is S017 ("Keeps filesystem paths, secrets... private").
  Failure: The dashboard shows the developer's home path, which T-3 promises it never will. A tester cannot make INV-10 pass.
  Smallest fix: Return the normalized relative path from `write_note`, which `_note_path` already computes, and strip the workspace root prefix from error texts. Alternatively, narrow INV-10/NFR-9/T-3 to what is actually guaranteed and add an A-n stating that the CLI sink scrubs paths.

R-4 [Major] [L5] D-22, AC-21 — `callable()` accepts an `async def` sink, which silently loses every event
  Evidence: Calling an async function returns a coroutine that is never awaited. The shield sees no exception, so every event vanishes, and the only signal is a RuntimeWarning. The repo's other observer seams accept async functions: `vidbyte/agents/multi/ledger_controller.py` uses `AgentTransfer.maybe_await`, and `vidbyte/workflows/contracts.py:514` declares `async def on_event`. Developers will therefore pass one, especially the CLI sibling, whose uploader is I/O.
  Failure: There are no events, no error, and an empty dashboard.
  Smallest fix: In the settings check, refuse values where `inspect.iscoroutinefunction(value)` is true, and also check the object's `__call__`. Add this to AC-21. Optionally, close and log any awaitable a sink returns.

R-5 [Major] [L6] §9.1 handoff, AC-16 — Handoff section sizes are not stated, but the backend caps them
  Evidence: Outcome holds the full answer, which is unbounded (EC-24 tests 100k). Work done is roughly cards × (key + ~1,600-character summary). The backend allows 24 sections of at most 16,000 characters each (`AGENT_RUN_MAX_SECTIONS`, `AGENT_RUN_SECTION_BODY_MAX_CHARS`). Request §C uploads the handoff as kind `handoff`, ordinal 0, without chunking.
  Failure: The handoff upload is rejected for exactly the large runs where it matters most.
  Smallest fix: State the maximum size of each section in §9.1 Volume, and add an A-n that the CLI sibling chunks or splits sections. Optionally, cap each card line to a single line in Work done and Unverified.

R-6 [Major] [L4] §12.3 row 3, §9.1 `INFINITE_HANDOFF_SECTIONS`, EC-29 — The section descriptions are model-facing text, placed in a constants module that forbids it
  Evidence: `HandoffAgent` (`vidbyte/agents/handoff.py:121`) feeds `render_section_brief()` to the model, and EC-29 designs for exactly that use. The infinite constants header says: "Do not put model-facing sentences here; they belong in vidbyte/prompts/prompts/infinite_memory/". Row 3 calls the descriptions "caller-facing labels". The sibling `EngineeringHandoff` keeps its titles and descriptions inline in its own module.
  Failure: A review comment or a placement-workflow move.
  Smallest fix: Keep the titles and descriptions in `vidbyte/context/handoff/infinite.py`, as `EngineeringHandoff` does, and drop row 3's constant. Alternatively, drop EC-29.

R-7 [Major] [L10/L5] D-19, AC-16, INV-23 — The handoff file is written in text mode, which writes CRLF on Windows (the user's platform)
  Evidence: `LocalFileSystemBackend.write_text(path, content, *, encoding, create_parents, newline=None)` opens the file with "w" and `newline=None`, so `\n` becomes `\r\n` on Windows. The write also follows a symlink planted in `.runs/`, and it is not atomic, which EC-23 already concedes.
  Failure: The file bytes do not match `to_context_text()`, so AC-16's byte comparison fails on Windows CI and on the developer's machine.
  Smallest fix: Pass `newline="\n"`. After the rebase, also pass `atomic=True`: the temp file plus `os.replace` both replaces a planted link and makes the write atomic.

R-8 [Minor] [L10] AC-4, AC-20 — AC-4 cannot be met as written
  Evidence: AC-4 compares journal fields (ignoring only `at`) and the bytes of `entries.jsonl` and `files.jsonl` across two separate runs. Those files embed the run id (`run_started.run`, the entry's `run`, the files record's `run`) and `at` stamps with one-second precision. AC-20 says to "match base_commit", which a test cannot execute.
  Failure: The S3 test-writer either weakens the check without saying so or writes a test that is flaky or always fails.
  Smallest fix: Compare after replacing the run id and every `at` with a placeholder. Change AC-20 to "match the documented record shapes plus the two additions".

R-9 [Minor] [L9] INV-9, NFR-2 vs D-8 — The spec says "no details record is built" without a sink, but D-8 builds them on every run
  Evidence: D-8 and §9.1 make the pair's drop and commit lists `InfiniteDroppedEntry`/`InfiniteCommittedEntry` on the run path, whether or not a sink is set. `InfiniteDroppedEntry` is also `memory_dropped`'s details type.
  Failure: A literal test of INV-9, for example one that counts constructions, fails.
  Smallest fix: Reword INV-9 to "no `InfiniteEvent`, and no details record beyond D-8's entry records, is built."

R-10 [Minor] [L1] D-21, A-4 — The list of deviations from §B is incomplete
  Evidence: `run_stopped.error_type` replaces §B's "error code", and `batch_rejected` gains `tool` through the shared `InfiniteRefusalDetails`. D-21 and A-4 mention neither.
  Failure: The sibling specs build against §B and mismatch these fields.
  Smallest fix: List both in D-21 and A-4.

R-11 [Minor] [L8] §9.1 Validation — The spec never says which fields may span several lines, and the truncation marker contains newlines
  Evidence: `OUTPUT_TRUNCATION_MARKER = "\n\n[truncated]"` (`vidbyte/lib/constants/outputs.py:32`). Any one-line check on a capped field refuses every truncated value, including a single-line check on `done_criteria` items (as the old `_text_items` default one_line=True did). The shield then drops the whole `subagent_launched` event (INV-8), with only a log line. Card texts use a second marker, `INFINITE_TRUNCATION_MARKER` (" … [cut]"), so one event stream contains two different markers.
  Failure: Events with long criteria or context items are silently dropped.
  Smallest fix: In §9.1, mark every text and tuple-item field as either single-line (built with `single_line`, no marker) or multi-line (built with `truncate`), and name the marker each one uses.

R-12 [Minor] [L4] §12.3 row 6, §8.5 shield — "one shields (catch Exception), one builds and delivers" implies a call chain two levels deep or nested lambdas
  Evidence: With 14 public methods, each one has to hand its builder to the shield. That means either public method → shield → builder (style rule 1 forbids a helper that calls another helper) or a lambda or closure per method.
  Failure: A style review asks for a rewrite.
  Smallest fix: Specify a `@contextmanager` `_shielded(kind)`, used as `with self._shielded(kind): self._deliver(kind, details)` inside each public method, so every call stays one level deep.

R-13 [Minor] [L8] NFR-1, §12.3 row 22 — The "events module ≤ 400" budget is enforced by nothing
  Evidence: Row 22 raises the module count and two line caps, but adds neither `vidbyte/agents/infinite/events.py` nor the handoff module to `BUDGET_MODULES`. Separately, the launch raise from 400 to 420 is probably unnecessary after the rebase (368 lines), and the lib dataclasses raise from 400 to 560 needs re-measuring from 177.
  Failure: NFR-1 is claimed but has no test. Raises that are not needed are spent from the pre-approved single test edit.
  Smallest fix: In the same S2 edit, add `events.py` to `BUDGET_MODULES`, and set each raise from the re-measured baseline (see R-1).

VERIFIED CLAIMS
- Baseline (run here): `tests/features/infinite_memory_agent`: 112 passed. `tests/features/harness_threads/test_harness_threads_surface.py`: 3 failed and 6 passed, and the 3 failures are exactly the pre-existing tests the spec names. HOLDS.
- Budget test `test_new_modules_stay_inside_the_complexity_budget` (contract test :453-461): at most 8 modules, and 12 `BUDGET_MODULES` ≤ 400 lines after the header. Lines at `ff1bc933`: launch 384, lib dataclasses 214, workspace 358, memory 265, runtime 110, agent 103, settings 248, journal 183, constants 160, enums 58. HOLDS at the base; stale against #1113 (R-1).
- No caller outside the package uses `InfiniteAgentMemory`, `InfiniteLaunchTool`, `InfinitePair`, or `journal.finish`. HOLDS.
- D-10:
  - `_LINEAR_LOOP_RUNTIMES` includes INFINITE_MEMORY (`base.py:83`).
  - `BaseAgent._runtime` passes the agent's `usage_tracker`.
  - `_runtime_metadata` returns stop_reason, tool_call_count, and usage_rollup.
  - The reply merges `**dict(result.metadata)`.
  - `AgentResult` is `frozen=True, slots=True` (`lib/dataclasses/strategies.py:5`), so `replace()` is required.
  HOLDS.
- The runtime re-raises runner exceptions unwrapped, which makes AC-6 plausible. HOLDS.
- `LocalFileSystemBackend.write_text(path, content, *, encoding, create_parents, newline=None)` exists. HOLDS, but the default newline breaks AC-16 on Windows (R-7).
- `OutputText.truncate` keeps the marker inside the cap, and `single_line` adds no marker. The marker is "\n\n[truncated]". HOLDS (R-11).
- `Handoff.section_titles()` returns a tuple. `fill()` rebuilds through the `type(self)(...)` keyword constructor. `EngineeringHandoff` overrides only DEFAULT_TITLE and default_sections. HOLDS.
- The public-API generator is AST-based and never imports vidbyte. `--check` exists and refuses dirty inputs. The contract's source commit is 9eca4a33, with 644 exports. HOLDS.
- Export sites: `vidbyte/__init__.py` (:12, :104-109, :755-761), `agents/__init__.py` (:84-89, :390-395), `context/__init__.py` (:88-93), and `context/handoff/__init__.py`. The JevResponse `replace` precedent (:144-150) and the `managed.py` logger (:27, :64) are where the spec says. HOLDS.
- grep ignores `.runs`, `_file_tokens` excludes `.runs`, and the journal's `find` globs `*.jsonl`, so the handoff `.md` is safe. HOLDS.
- Constants: `INFINITE_NEW_FILES_PER_AGENT = 1`, `INFINITE_CONTEXT_MAX_ITEMS = 20`, task-name pattern `^[a-z0-9][a-z0-9-]{0,39}$`, card cap 400 tokens. HOLDS at the base. #1113 changes the first one to 10.
- FALSE or STALE:
  - "files bounded by max_files" (raw paths, no deduplication; R-2).
  - NFR-4 "≤ ~32 KiB" (R-2).
  - INV-10, no absolute paths (R-3).
  - Reliance on `_text_field` helpers and on `_whole_lines`, and the `{"field": "on_event"}` details (R-1).
