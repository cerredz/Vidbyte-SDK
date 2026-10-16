VERDICT: SOUND WITH FIXES — all 13 r1 dispositions hold against the r2 text and the 7efceb55 code, and the size arithmetic reproduces independently. The re-baseline missed one #1113 behavior change: launch refusals that the middleware makes no longer reach `batch_rejected`.

WHAT THE SPEC GETS RIGHT
- The re-baseline is real. Every budget line count matches the budget test's own `_lines_after_header` at 7efceb55: launch 368, lib records 177, workspace 332, memory 251, settings 196, journal 157, agent 111, runtime 106, constants 183, enums 58, package `__init__` 14, toolset 41, validation 251, text 37. The pack passes 113 tests. Records validate through RecordFieldValidator/RecordFieldConverter with qualified names. AC-21 uses the qualified field. The handoff write is `write_text(..., newline="\n", atomic=True)`, and that matches the backend signature at `vidbyte/lib/tools/filesystem/backends/local.py:25`.
- The bounds are fixed constants, so they hold at any settings value. No settings validator has a maximum (`settings.py:96-97, :199-200` set minimums only). An independent rebuild of the worst-case shapes lands within 4 bytes of the spec's table.
- The new lib options are additive:
  - `require_number(..., maximum)` has 4 callers (native_threads.py:170/187/205, process.py:65), all keyword `maximum=` only.
  - `OutputText.truncate(text, limit)` has 13 callers under `vidbyte/lib/outputs/`, all with two positional arguments.
  - No equivalent UTC-datetime check, coroutine check, or char-cap-with-marker helper exists anywhere in `vidbyte/lib`. Neither class is in `contracts/sdk-public-api.json`.
- Every line type rests on a real upstream rule. The "e" sources are one line by code, not by assumption: `InfiniteEntryDraft.text/refs` and `InfiniteTaskCard.context` use `one_line=True`, card files use `one_line=True`, `_note_path` refuses multi-line paths (workspace.py:287), and new-note descriptions are checked with `splitlines` (workspace.py:166). All of them use the same `splitlines` definition as `_text_problem`.

FINDINGS (ranked)

R-14 [Major] [L1/L9] §6.1 INV-15, §5 flow diagram, §9.1 `batch_rejected` row, D-21/A-4 — Launch refusals made by DelegationLimitsMiddleware never produce `batch_rejected`, so INV-15 is false at 7efceb55
  Evidence: #1113 moved the batch-size cap out of the tool and added a depth refusal. Both now happen in the runtime's `before_tool_call`, before `InfiniteLaunchTool.execute` runs:
  - `vidbyte/middleware/builtins/delegation_limits.py:53-56` refuses at max_depth, and `:65-68` refuses over max_parallel. Each returns `MiddlewareDecision.deny_tool(...)`.
  - The root gets this middleware at depth 0 (`agent.py:80`). Every generator gets it one level deeper (`launch.py:272`), and every generator now holds `launch_subagent` (`launch.py:263-272`).
  - At ff1bc933, max_parallel was refused inside `execute` (`launch.py:156-157`, which flowed into the rejection branch request §B cites as "launch.py:127"), and generators at max depth had no launch tool at all (`:279`).
  - Only the duplicate-name, foreign-tool, unknown-entry, and max_agents refusals (`_check`, `launch.py:156-180`) and argument-parse errors still reach the `:132` branch where row 8 emits.
  Failure: A generator at max_depth that tries to delegate (default 20, and every generator holds the tool) produces no event, and neither does a root batch over max_parallel. The dashboard and CLI never see these refusals, although INV-15 says every rejected batch emits exactly one `batch_rejected`. AC-7 tests only a duplicate name, so tests would not catch it.
  Smallest fix:
  - Narrow INV-15 to "a batch that `InfiniteLaunchTool.execute` refuses".
  - Add an EC row: a call denied by DelegationLimitsMiddleware (depth or batch size) delivers no event, and the model sees "Tool denied by middleware: ...".
  - Add the same sentence to the §9.2 caps-for-siblings list and to A-4.
  - [scope-adding] Optionally add Q-6, "emit `batch_rejected` for middleware denials?", default no. Emitting would need an infinite-specific observation point on the middleware decision, which costs budget the agent package does not have.

R-15 [Minor] [L5] INV-36, D-27, EC-32, AC-29 — The returned-awaitable rule logs a working sink as a failure on every event
  Evidence: INV-36 counts any awaitable returned by a synchronous sink as a sink failure (`TypeError`) and closes it only "when it has `close()`". A common synchronous sink, `lambda e: loop.create_task(upload(e))` or `asyncio.ensure_future(...)`, returns a Task. A Task is awaitable, has no `close()`, and is already scheduled.
  Failure: The event is in fact delivered (the task runs), yet every event logs a WARNING `error_type=TypeError`. The developer reads the warnings as lost events.
  Smallest fix: Apply the rule only to coroutine objects (`inspect.iscoroutine(result)`): close the coroutine, then count the failure. Ignore every other return value, Futures and Tasks included, as the §9.2 "return value is ignored" sentence already says.

R-16 [Minor] [L11/L8] §8.4, §12.3 row 22, D-2 — Both budget margins are thinner than stated, and an overflow needs a second test edit that the ruling does not cover
  Evidence: I counted the row 8 delta line by line:
  - imports +4
  - `self.events` +1
  - `batch_rejected` +1
  - the task-ordered launch/replay loop with its rewritten @intent block +7
  - `replies` +1
  - generator_finished and its comment +3
  - the split verifier line +2
  - `subagent_finished`, plus the drop-rendering @intent block that §12.4 requires in `_finish` +6

  That gives launch about 394 lines (6 lines of headroom), against the spec's ~392 (8). A per-field count of the 16 records in the existing style (one validator call per line, loops for shared rules, about 23 import lines) gives the lib records module about 577 lines, against the spec's ~560 and a cap of 600.

  §14 says to stop BLOCKED on overflow. The only way out would then be a second edit of an existing test, which the single pre-approved edit does not cover.
  Failure: Either S3 trims mandated narration or @intent comments to fit, or the pipeline stalls mid-implementation.
  Smallest fix: Have the orchestrator pre-rule now. Option 1: let row 22 set launch ≤ 410 and lib records ≤ 620 in the same single edit, with these counts as the reason. Option 2: state that an overflow of ≤ 10 lines may be absorbed by moving the two item records' validation into a shared loop. Do not leave this to a mid-S3 BLOCKED.

R-17 [Minor] [L10] AC-30, §12.3 row 23 — The new validator options have no direct acceptance check where a mistake would drop events silently
  Evidence: AC-30 uses `cost_usd=1.2345678901234567e-300`, which is never 0. No AC builds a details record with `cost_usd=0.0` (a free or cached model), an `at` with a non-zero UTC offset, or an `at` whose microseconds are not a multiple of 1,000. INV-38 is pinned only for the old behavior (`test_harness_threads_records.py:21,26` refuses 0).
  Failure: If `allow_zero=True` is left off one `cost_usd` check, or the resolution rule is wrong, every zero-cost `generator_finished`, `subagent_finished`, and `run_finished` is refused and skipped by the shield (INV-8). Only a log line reports it, and the pack stays green.
  Smallest fix: Extend AC-30, or add an AC, with these cases:
  - `cost_usd=0.0` is accepted.
  - `at` with `+01:00` is refused.
  - `at` with microsecond 1 is refused.
  - `require_callable(None, ..., optional=False)` is refused.

R-18 [Minor] [L4/L9] §12.3 rows 7 and 10, D-19, §13 — A few line anchors drifted at the re-baseline
  Evidence:
  - Row 7 gives `InfiniteAgentMemory.__init__ (:39)`; :39 is the class line, and `__init__` is at :42.
  - Row 10 gives `__init__ (:40)`; :40 is the class line, and `__init__` is at :43.
  - Row 10 gives `find (:64)`; :64 is inside `start`, and `find` is at :67-68.
  - Row 10 gives the `_parse` RUN_FINISHED case as `(:153-154)`; the case is at :151-152, and :153-154 is the `except` clause.
  - D-19 says the handoff call is "the same call the workspace makes", but the workspace passes `newline=""` (workspace.py:153/185/205). The bytes are the same, so this is harmless.
  - §13 credits `tests/test_record_field_validation.py` with INV-38. The zero-refusal is actually pinned in `tests/features/harness_threads/test_harness_threads_records.py:21,26`.
  Failure: Small navigation errors for S3. In row 10, an implementer who edits at ":153-154" would land in the error handler.
  Smallest fix: Correct the four anchors and the two sentences.

VERIFIED CLAIMS

Disposition check (r1 → r2), against the r2 text and the 7efceb55 code:
- R-1: RESOLVED. `base_commit` is 7efceb55 (`git merge-base --is-ancestor` holds, and there is no source diff between 7efceb55 and 977141c4). All 14 line counts were re-measured with the test's own method and match. §9.1 Validation and row 4 use only canonical validators, with no `_..._field` helper. Row 23 adds options. AC-21/D-22 are qualified. INV-26 now states behavior. D-29 `find(..., unfinished=False)` fits `find`'s real structure (pattern check :75, newest-first sort :78, "already finished" refusal :89-90). Remaining gaps: R-14, and the anchor drift in R-18.
- R-2: RESOLVED. I rebuilt the details shapes independently as `asdict`-shaped dicts (scratchpad `r2check/sizes.py`), each filled with U+1F600, `\x01`, `"`, U+2028, or `a`, under all four `ensure_ascii` × separators combinations:

  | Kind | Details (spec) | Whole event (spec) | Compact UTF-8 (spec) |
  |---|---|---|---|
  | subagent_finished | 27,011 (27,015) | 31,089 (31,091) | 14,544 (14,548) |
  | subagent_launched | 25,197 (25,201) | 29,275 (29,277) | 13,280 (13,284) |
  | memory_saved | 18,023 (18,023) | — | — |
  | run_resumed | 8,686 (8,686) | — | — |

  Even `indent=2` gives 31,671 bytes, under 32,768. Every list and string in all 13 details records has a cap:
  - Every list holds 5 items plus an `*_omitted` count. The exception is tags/refs, which hold ≤ 8 by the existing `INFINITE_MAX_TAGS/REFS = 8`.
  - text 500, path 500, line 120, label 64, keys 512, staged keys 64.
  - The task name is ≤ 64 by `INFINITE_TASK_NAME_PATTERN = ^[a-z0-9][a-z0-9-]{0,63}$`, and the run id is 25 characters by `INFINITE_RUN_ID_PATTERN`.
  - D-25 arithmetic: 1 + 16 + 1 + 490 = 508, plus "/gen" = 512. Unshortened keys start with "root", so they can never collide with the "~" form.
- R-3: RESOLVED (narrowed). `_note_path` already computes the relative POSIX path (workspace.py:295, :304), and `files.jsonl` stores that same string (:176), so `relative()` matches descriptions (A-7). INV-10, NFR-9, and T-3 now promise only what holds. NG-13 and A-9 place free-text scrubbing in the CLI.
- R-4: RESOLVED. Python ≥ 3.11 (`pyproject`): `inspect.iscoroutinefunction` sees through `functools.partial` and bound async methods, and `type(value).__call__` covers async `__call__`. Remaining gap: R-15.
- R-5: RESOLVED. `Handoff.to_context_text` (`context/handoff/base.py:41-47`) renders title + "\n\n" + "## {title}\n{body}" joined by "\n\n", with no "# " prefix. The overhead is 53 + 150 = 203 ≤ 300, so the total is ≤ 366,403 ≤ 366,500. The Outcome heading plus body is 239,011 (15 chunks). The largest other section is 29 + 15,900 = 15,929 (1 chunk). The total is 23 ≤ 24.
- R-6: RESOLVED. No handoff wording is left in the §9.1 constants (only the suffix and three caps). D-13 and row 12 put the wording inline, as `EngineeringHandoff` does. `HandoffAgent` reads `render_section_brief()` (`vidbyte/agents/handoff.py:121`).
- R-7: RESOLVED. `write_text(..., newline, atomic)` exists (`local.py:25-48`): a temporary file plus `os.replace`, with the temporary file removed on failure. The temporary name `.<name>.*.tmp` does not match the journal's `*.jsonl` glob.
- R-8: RESOLVED. AC-4 normalizes the run id and every `at`. AC-20's key sets match `_append` (`event`, `at`, plus fields) and the `start` and `finish` field sets.
- R-9 and R-10: RESOLVED, as worded in INV-9 and D-21/A-4.
- R-11: RESOLVED. There is one marker (`INFINITE_TRUNCATION_MARKER = " … [cut]"`, constants :132, one line). `OutputText.truncate` returns exactly `limit` characters, with the marker inside, when cutting (text.py:37-39).
- R-12: RESOLVED. `@contextmanager _shielded(kind)` + `_deliver` keeps one level. The public method passes the already-shortened key into `_deliver`, and `_deliver` calls no own helper.
- R-13: RESOLVED. `BUDGET_MODULES` (contract test :93-106) gains both new modules, and the module count check is at :475. Remaining gap: the margins in R-16.

Re-baseline spot checks at 7efceb55. All HOLD except those listed in R-18:
- launch.py: 368 lines; :76 `__init__`; :132 rejection branch; :138-139 pair_started loop; :195-196 lists; :205-206 memories; :218 generator `arun`; :232 verifier line; :271 child launch tool; :331-344 `_commit`; :346-352 `_finish`.
- journal: `finish(self, stop_reason)` at :103 (gains `answer` and `files`); `find(cls, workspace_root, run_id)` at :67-68 (gains `unfinished`).
- memory.py: :71, :76, :80, :88, :95-101; error branches :147, :201, :234, :259.
- runtime.py: :78, :83, :84, :97, :101.
- Exports: `vidbyte/__init__.py` :12, :106-107, :758-759; `agents/__init__.py` :84-89, :392; `lib/enums/__init__.py` :80-87, :223-228.
- Fixtures (unchanged by #1113): `build_settings` :87, `build_agent` :104, `snapshot` :474, `journal_paths` :484, `events` :497, `run_finished_record` :545.
- Precedents: `ledger_controller.py` :163-174 (`except Exception`); `workflows/contracts.py:514` (`async def on_event`); `runtime.py:2067-2084` (the three metadata keys); lib README :41; infinite README :34 and 12,162 characters.
- Types: `AgentResult` has `output`; `UsageRollup.cost_usd` is `float | None` and `total_tokens` is `int | None`.
- AC-31 can be built: ToolSpec names have no length cap, `INFINITE_NEW_FILES_PER_AGENT = 10`, and `INFINITE_CONTEXT_MAX_ITEMS = 100`.

Lib-option blast radius (rows 23 and 24):
- Every caller still behaves the same. There are 4 `require_number` callers and 13 `truncate` callers.
- The options are placed per AGENTS.md style 5 and `class-bound-helpers.md`, and §12.4 carries the "existing callers unchanged" obligation.
- A006 allows `vidbyte.context` → `vidbyte.lib.outputs`. The events module imports launch, memory, and journal types under TYPE_CHECKING only, which A006 ignores, so the change adds no cycle.
- Gap: R-17 (no AC for the new options' edge cases).
