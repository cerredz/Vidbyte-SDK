# Code map: infinite-memory-derived-events

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-derived-events` at `181f1992` (the PR #1159 merge). `git status` shows only `docs/spec/infinite-memory-derived-events/` as untracked. I read every path:line below on `181f1992` in this session. Anything I did not open is marked "unverified".

Scope reminder (from request.md:90-92; not relitigated):
- IN: A1–A8, B1–B5, C3, D1, and E1 for the root only.
- OUT: C1, C2, E2, and E1 for pair agents.
- No base-runtime change. Journal format unchanged.
- No new middleware, hook, subclass, or listener.

## 1. Rules, commands, and conventions that bind this change

### 1.1 AGENTS.md (81 lines; `CLAUDE.md` is only `@AGENTS.md`)

**Reading rules**
- Read `REPO_MAP.md` before creating or moving a file.
- Read each touched folder's `README.md` to the end, including `## Notes for agents`.
- `docs/` is opaque.

**Gate**
- "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."

**Style 1: one-level call chains**
- A helper must not call another helper of the same class or module.
- No nested functions unless an API needs a callback.
- `InfiniteEvents` follows this: public method → flat static helpers `_cut`, `_items`, `_key`, `_label`, `_usage`, `_count`, `_launcher_role`.

**Style 2: narrate main functions**
- Narrate main functions in plain-English comments.
- When you change the steps, update the comments in the same edit.
- Multi-line comments are 72-column PEP 8 blocks placed directly above the code. This is from field-guide `comment-format.md`; it is not a lint rule.

**Style 3: layers and file size**
- `vidbyte/lib/` is the bottom layer and must never import upward.
- Keep files "well below 1,000 lines".
- "If describing the job … needs the word 'and', it is probably two."

**Style 4: validated dataclasses**
- Use `@dataclass(frozen=True, slots=True)` with `__post_init__` validation.
- Any field whose value comes from a small, closed set is typed with an enum.

**Style 5: canonical helpers**
- Shared logic is a canonical helper in `vidbyte/lib/`.
- The infinite README notes say: before adding a private helper here, look in `vidbyte/lib/`.

**Placement (binding; enforced on every PR by the "AGENTS.md placement" workflow)**
- Every new dataclass goes in `vidbyte/lib/dataclasses/<domain>.py`.
  - "Add to the existing domain module when there is one; create a new `<domain>.py` only for a new domain."
  - No `types.py`, `records.py`, `models.py`, or `schemas.py`.
- Every new enum goes in `vidbyte/lib/enums/<domain>.py`, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions.
- Editing an existing module in place (adding a field or a member) is fine.

**Not stated**
- AGENTS.md states no PR or commit-message convention.

### 1.2 Folder README and module-header rules

**`vidbyte/agents/infinite/README.md`** (164 lines, 19,397 chars; A009 ceiling 40,000)
- "Events and handoff" section: lines 89-132. The event list is at :103-118.
- :109 says "A call `DelegationLimitsMiddleware` denies never reaches the tool and has no event."
- File Index: :137-148. Notes for agents: :150-164. The notes include:
  - pairs that keep running after an error escaped their batch can deliver events after `run_finished` or `run_stopped`;
  - keep deterministic limits out of the prompt families;
  - look in `vidbyte/lib/` before adding a private helper.

**`vidbyte/agents/infinite/events.py` header**
- :7 gives the recipe for a new kind: "one InfiniteEventKind member, one details record and DETAILS_TYPES entry …, one summary template …, one public method here shaped like the others, and one call at the point the change is durable."
- WHAT NOT TO DO rule 1: do not catch BaseException.

**`vidbyte/agents/infinite/launch.py` header**
- :8 rule 2: "Do not catch CancelledError or BaseException in InfinitePair.run; cancelling the run must stop every pair."
- :8 rule 5: no module-level constants.
- :9 says a batch that `DelegationLimitsMiddleware` refuses "announces nothing (EC-37)".

**`vidbyte/agents/infinite/runtime.py` header**
- :7: "Per-run setup goes in arun before super().arun; per-iteration work goes in _after_tool_iteration."

**`vidbyte/agents/infinite/memory.py` header**
- Rule 4: no module-level constants.

**`vidbyte/agents/infinite/workspace.py` header**
- No caching.
- Write under the lock.
- Do not raise from `map_text`.

**`vidbyte/agents/infinite/journal.py` header**
- :7: a new record type needs an `InfiniteJournalEvent` member. The format is frozen by scope.

**`vidbyte/agents/infinite/agent.py` header**
- Rule 3: do not share one middleware instance between agents.

**`vidbyte/lib/dataclasses/infinite.py` header**
- Rule 7: a new kind adds a record, an `InfiniteEventDetails` union member, and a `DETAILS_TYPES` entry. A new field adds `_FIELDS` and `_FIGURES` rows in the records test.
- Rule 8: no imports above lib, and no `to_dict`.
- Details fields have no defaults.

**`vidbyte/lib/enums/infinite.py` header**
- :7: a new event kind is a member, a details record, a kind-to-record entry, a summary template, and one `InfiniteEvents` method.
- :8 rule 1: do not change a value.
- :5: "The event values are a contract with the event consumers (the CLI and the dashboard)."

**`vidbyte/lib/constants/infinite.py` header**
- Rule 4: "Do not tie an event cap to a setting."
- `__all__` lists one name per line, so each new constant costs 2 lines.

### 1.3 Lint rules (`python lint/run.py`; blocking and count-ratcheted against `lint/baseline.json`)

| ID | What the module checks (opened) | Baseline | Where it bites here |
|---|---|---|---|
| A001 | Module docstring must have non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, `TESTS:` (a001:24-32). FUNCTION INVENTORY and WHAT NOT TO DO are a house convention, not linted. | 642 | Any new module. |
| A007 | A numeric literal is flagged when nearby names contain `timeout`, `retry`, `attempt`, `backoff`, `delay`, `token`, `char`, `byte`, `truncate`, `limit`, `budget`, `status`, `depth`, or `interval` (a007:23-38), unless it is assigned to an UPPERCASE name. Also flags operational parameter defaults (a007:117-133). | 255 | A5 `attempt`; E1 throttle; C3 percent buckets near `tokens` / `max_tokens`; any `+ 1` next to `attempt` or `depth`. Field guide: name even a floor of `1`. |
| A009 | A README must be ≤ 40,000 chars (a009:20). | 0 | `vidbyte/agents/infinite/README.md` is at 19,397. |
| S008 | Ruff C901, PLR0912, and PLR0915 (s008:23). `lint/ruff.toml` sets no thresholds, so Ruff defaults apply. unverified: the default values (10 / 12 / 50). | 19 | `InfinitePair.run` (launch.py:215-273) and `InfiniteLaunchTool.execute` (:122-168) gain calls. |
| S019 | Inside an `async def`, an `except` that names `BaseException` or `CancelledError`, or is bare, must contain a `raise` (s019:37-43). | 5 | B3 catch-and-re-raise in `InfinitePair.run` passes S019 only with a `raise`. It still conflicts with the launch.py header rule. |
| S020 | A README with `## File Index` must list exactly the tracked direct children with an indexed suffix (s020:23, :32-44). | 1 | A new `.py` in `vidbyte/agents/infinite/` or a new test file must be indexed in that folder's README. |
| S024 | Control-flow nesting ≤ 3 (`if`/`for`/`with`/`try`/`match`; a function resets the count; `elif`, `else`, and handlers add no level) (s024:23, :43-81). | 25 | `with self._shielded(...)` is level 1 inside each event method. A loop plus `if` inside it reaches 3. |
| S043 / S044 | No raw exception text in logs; parameterized logs (README catalogue only; modules not opened). | 0 / 0 | A7 touches `_shielded`'s log line. |
| C016 | `contracts/sdk-public-api.json` must equal the generator output for `vidbyte.__all__` (contracts/README.md). | 0 | Changes only if a name is added to `vidbyte/__init__.py` `__all__`. New members of `InfiniteEventKind` change no name. |

**Rules that do not exist**
- No line-length rule: `lint/core/ruff.py:26-35` SELECTORS has no `E501`, and `lint/ruff.toml` and `pyproject.toml` set no `line-length`.
- No function-length rule beyond S008's statement and branch counts.
- A002 (`# @intent` near load-bearing logic) applies. runtime.py:131 already carries `# @intent the-roots-map-follows-the-disk`. unverified: A002's exact trigger; the field guide says the `@intent` line must stay within 20 lines of the `def`.
- A006 (layering) applies to any new lib-to-agents import. Its module was not opened; the field guide `blocking-lint-invariants.md` describes it.

### 1.4 Commands

**Full gate (AGENTS.md)**
- `python scripts/run_ci.py`

**From a worktree (field-guide `local-ci-verification.md`, first entry)**
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH.
- Check first: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` must print the worktree path.
- Semgrep scans only git-tracked files, so `git add -A` before trusting a clean scan of a new `.py`.

**Lint (`lint/README.md`)**
- `python lint/run.py`, `python lint/run.py --rule A007`, `--all`, `--format json`.
- For S051: `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, run over the whole tree (field guide).

**Pack tests (tests README "Run")**
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`
- One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_events_stream.py -q`
- Bash cases need POSIX bash or Git for Windows bash.

**Public API (contracts/README.md)**
- `python scripts/generate-sdk-public-api.py --check`. Needed only if root exports change.

**Known pre-existing gate failures (field guide; classify them, do not fix)**
- `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, which fails with `assert 167 == 120` on main.
- Two branch-scoped `harness_threads` surface tests, when a branch touches `vidbyte/tools`, `vidbyte/lib/configs`, or root exports.

## 2. Files this change will touch

### 2.1 Line budget

`test_new_modules_stay_inside_the_complexity_budget` (test_infinite_memory_contract.py:474-489) sets the caps:
- Lines are counted after the header docstring (`_lines_after_header`, :466-471).
- Cap is 400, except launch.py at 410 and lib dataclasses at 620 (:480).
- `len(list(package.glob("*.py"))) <= 9` (:484). The package has exactly 9 `.py` files, so **any new module in `vidbyte/agents/infinite/` fails the test**.
- `BUDGET_MODULES` (:94-109) lists 14 files.
- Precedent: the test docstring (:475-479) records that the events spec raised the launch and lib caps.

Every header ends at line 12.

| File | wc -l | After header | Cap | Room |
|---|---|---|---|---|
| vidbyte/agents/infinite/events.py | 412 | 400 | 400 | **0** |
| vidbyte/agents/infinite/launch.py | 410 | 398 | 410 | **12** |
| vidbyte/lib/dataclasses/infinite.py | 616 | 604 | 620 | **16** |
| vidbyte/agents/infinite/workspace.py | 366 | 354 | 400 | 46 |
| vidbyte/lib/constants/infinite.py | 318 | 306 | 400 | 94 |
| vidbyte/agents/infinite/memory.py | 296 | 284 | 400 | 116 |
| vidbyte/agents/infinite/journal.py | 198 | 186 | 400 | 214 |
| vidbyte/agents/infinite/agent.py | 186 | 174 | 400 | 226 |
| vidbyte/agents/infinite/runtime.py | 143 | 131 | 400 | 269 |
| vidbyte/lib/enums/infinite.py | 112 | 100 | 400 | 300 |

These budget modules are not expected to change: `settings.py` (217), `__init__.py` (32), `vidbyte/tools/toolsets/infinite.py` (53), and `vidbyte/context/handoff/infinite.py` (111).

### 2.2 File by file

**vidbyte/lib/enums/infinite.py**
- **Today:** Ten str enums.
  - `InfiniteEventKind` has 14 members (:70-86).
  - `InfiniteDropReason` VERIFIER/UNCHECKED/RULE (:89-94).
  - `InfiniteFileChange` (:97-102).
  - `InfiniteStopCause` FAILED/CANCELLED (:105-109).
  - `__all__` :112.
- **What changes:**
  - New kind members for A2, B1, B2, B3, B4, B5, C3, and E1.
  - A new refusal-rule enum for A3.
  - Any other closed set the request names must be an enum here (AGENTS.md): B3 cancelled|failed and phase, D1 source, C3 bucket.
- **Pattern:** Value = lowercase member name. Never change an existing value.

**vidbyte/lib/enums/__init__.py**
- **Today:** Imports the infinite enums at :106-116 and lists them in `__all__` at :275-284.
- **What changes:** Each new public enum must be exported here (AGENTS.md).
- **Pattern:** Alphabetical, matching the existing block.

**vidbyte/lib/dataclasses/infinite.py**
- **Today:** 22 records.
  - `InfiniteRunFinishedDetails(stop_reason, answer, pairs, agents, tokens, cost_usd)` :301.
  - `InfiniteRefusalDetails(tool, problem)` :339.
  - `InfiniteGeneratorFinishedDetails(status, stop_reason, summary, tool_calls, tokens, cost_usd, duration_ms)` :407.
  - `InfiniteSubagentFinishedDetails` :431.
  - `InfiniteEventDetails` union :565.
  - `DETAILS_TYPES` MappingProxyType :573-588.
  - `InfiniteEvent.__post_init__` checks that details are an instance of `DETAILS_TYPES[kind]`.
- **What changes:**
  - New records for the new kinds (A2, B1–B5, C3, E1).
  - New fields:
    - A3 `rule` on `InfiniteRefusalDetails`;
    - A4 quota fields on the saved/staged/file-written records;
    - A5 fields on launched/finished;
    - A6 and A7 fields on run_finished, and A7 on run_stopped;
    - A8 fields on subagent_finished.
  - D1 source marker on the refusal record.
- **Pattern:** Frozen and slotted, with `RecordFieldValidator`/`RecordFieldConverter` checks (lib README) and no field defaults. Every capped text is bounded by `INFINITE_EVENT_*` caps so the JSON stays ≤ 32,768 bytes.

**vidbyte/lib/constants/infinite.py**
- **Today:**
  - `INFINITE_DEFAULT_MAX_FILES = 2_000` :48, `INFINITE_DEFAULT_MAX_TOKENS = 2_000_000` :49.
  - `INFINITE_MORE_FILES` :135.
  - Event caps :150-160: SUMMARY 280, TEXT 500, PATH 500, LINE 120, LABEL 64, MAX_DETAILS_BYTES 32,768, MAX_ITEMS 5, MAX_COUNT 2^63-1.
  - Summary templates :187-200.
  - Metadata keys :205-208: `stop_reason`, `tool_call_count`, `usage_rollup`, `infinite_run_id`.
- **What changes:**
  - One summary template per new kind.
  - The C3 thresholds and E1 throttle as named constants. A007 requires this, and request.md:129 leaves the values open.
- **Pattern:** UPPERCASE with the `INFINITE_EVENT_` prefix, one `__all__` line each.

**vidbyte/agents/infinite/events.py**
- **Today:** `InfiniteEvents(on_event, run_id)` holds `_launched: dict[str, float]` (monotonic time per pair key).
  - Public methods: `run_started` :122, `run_resumed` :141, `run_finished(journal, result)` :152, `run_stopped(error)` :168, `batch_rejected(launch, problem)` :179, `subagent_launched(launch, card)` :189, `subagent_replayed` :212, `generator_finished(memory, reply, status, summary)` :222, `subagent_finished(pair, card)` :239, `memory_saved` :273, `memory_staged` :283, `memory_dropped(memory, dropped)` :293, `file_written(memory, path, change, text, description)` :302, `tool_refused(memory, tool, problem)` :313.
  - Private methods: `_shielded` :322-333 catches `Exception` and logs only. `_deliver` :335 stamps UTC ms and refuses a returned coroutine.
- **What changes:**
  - One public method per new kind.
  - Enrichment inside the existing methods for A3–A8.
  - An `in_flight` counter for A5 (request.md:61).
  - A failure count in `_shielded` for A7.
- **Pattern:**
  - Start with `if self.on_event is None: return`.
  - Then `with self._shielded(kind):`.
  - Build the capped details with the flat helpers.
  - Finish with `self._deliver(kind, agent_key, role, depth, summary, details)`.
  - The envelope comes from the object passed in, for example `launch.key`/`launch.depth` in `batch_rejected` :183-187.

**vidbyte/agents/infinite/launch.py**
- **Today:**
  - `execute` :122-168.
    - Rejection at :137-138.
    - Started/replayed loop at :148-153: `pair_started` at :150, then `subagent_launched` at :151.
    - `await ParallelPipeline(...).run("")` at :157-158, only when `pairs` is non-empty.
  - `_check` :170-194 (`agents_started` :191).
  - `InfinitePair.run` :215-273.
    - Generator `arun` :236.
    - `generator_finished` :241.
    - Sleep :248.
    - Verifier :252-256, run only if status is not FAILED.
    - `_commit` call :261-262.
    - `except (VidbyteSdkError, OSError, ValueError)` :267.
  - `_agent` :275-314 builds a fresh BaseAgent and nests an `InfiniteLaunchTool` for a generator (:294). Neither is retained.
  - `_commit` :354-367.
    - RULE drop at :364.
    - `commit_entry` at :362.
  - `_finish` :369-383.
    - UNCHECKED drops at :373.
    - `pair_finished` :381.
    - `subagent_finished` :382.
- **What changes:**
  - A1 at :364 and :373.
  - A2 after :362.
  - B1 before the verifier call and B2 after it (:252-256).
  - B3 around `run`.
  - B4 after :158.
  - A5 at :150-151.
  - A8's error type at :267.
  - D1 for generators after :236-241.
- **Pattern:** One `launch.events.<kind>(...)` call per site, after the durable change (journal record, list append).

**vidbyte/agents/infinite/runtime.py**
- **Today:**
  - `arun` :66-127: `events = InfiniteEvents(...)` is a **local** at :86.
    - Root memory and launch are built at :100-101.
    - `super().arun` :115.
    - `journal.finish` :119.
    - `except BaseException` → `run_stopped` → `raise` :120-122.
    - `run_finished` :126.
  - `_after_tool_iteration` :129-135 only re-upserts the map. `_map` :137-140.
- **What changes:**
  - E1, C3, and D1 (root) in `_after_tool_iteration` (request.md:124-125).
  - A6 and A7 inputs at :126.
- **Pattern:** The JevRuntime per-iteration hook (REPO_MAP.md:400), plus `# @intent` and narration.

**vidbyte/agents/infinite/memory.py**
- **Today:**
  - Counters: `accepted` :63; `created` (incremented at :105); `files_written`.
  - `remember` :74-96 (quota raise :79-80; saved :89; staged :95).
  - `write_note` :98-110, `edit_file` :112-119, `drop` :121-132.
  - `quota()` :142-145.
  - Tool `execute`s catch errors and call `tool_refused`:
    - :175-176, :230-231, :264-265 catch `(ConfigurationError, ToolExecutionError, OSError, ValueError)` and pass `str(exc)`.
    - :290-291 catches `ToolExecutionError` only and passes `exc.message`.
- **What changes:**
  - A4 values come from `accepted` and `created`.
  - A3: the refusal rule must reach `tool_refused`.
- **Pattern:** Keep the refusal text the model sees unchanged (request.md:103).

**vidbyte/agents/infinite/workspace.py**
- **Today:**
  - `usage()` :98-101 does a full disk scan via `FolderUsage`.
  - `map_text` :217-241 does the same scan. Its omitted count is computed only inside the text at :239.
  - Raise sites:
    - `entries()` :108;
    - `write_note` :174, :176, :181, :192;
    - `edit_file` :202, :209, :212;
    - `_entry_lines` :276 (has `details`);
    - `_entry_rules` :285, :291, :295, :298, :300;
    - `_note_path` :310, :314, :316, :319, :325;
    - `_room` :334, :336.
  - Only `__init__` and `_entry_lines` pass `details=`.
- **What changes:**
  - A3: a rule on each raise.
  - C3 reads `usage()` and the omitted count.
- **Pattern:** `ToolExecutionError(message, details={...})`, as at :276. Room is only 46 lines.

**vidbyte/agents/infinite/journal.py**
- **Today:**
  - Private `self._started: list[str]`, with repeats.
  - `pair_started` :104-107.
  - `agents_started = INFINITE_MIN_AGENTS * len(self._started)` :145-147.
  - Public readers: `finished`, `finished_children`, `interrupted_children`, `cards`, `interrupted`.
- **What changes:** A5 `attempt` needs a per-key start count. That is a new reader, not a format change.
- **Pattern:** A property or method beside `agents_started`.

**vidbyte/agents/infinite/agent.py**
- **Today:** `run_handoff` :120-167 does an atomic write at :165-166 and then `return handoff`. `_section` is a static method after it.
- **What changes:** B5 goes after :166.
- **Pattern:** Build `InfiniteEvents(self.settings.on_event, journal.run_id)` there (request.md:71).

**vidbyte/agents/infinite/README.md**
- **Today:** Event list :103-118; AC-36 sentence :109; caps text :122; File Index :137-148.
- **What changes:** The new kinds and fields, the D1 reversal of :109, and the File Index if a module is added.

**tests/features/infinite_memory_agent/README.md** (File Index :11-30) and **FEATURE.md** (Known Failure Modes :107 cites AC-36; Test Suite Map)
- **What changes:** Updated by the test author. A new test file must be added to the File Index (S020).

### 2.3 Read for derivation only (not to be edited)

**`vidbyte/agents/runtime.py` (2,304 lines)**
- Loop state `BaseAgentRuntimeLoopState` :159-183 holds:
  - `iteration_count`, `model_call_count`, `tokens_used` (may be None), `call_contexts`, and `started_at` (monotonic);
  - the `tool_call_count` property, which is `len(call_contexts)`.
- `state.iteration_count += 1` :471.
- `_after_tool_iteration` is called at :700, on the continue path only. Its default no-op is at :925-931.
- `_with_middleware_metadata` :1233-1244.
- `_denied_tool_result` :1415-1419 builds the metadata `{"error": "middleware_denied", "reason", **decision.metadata}` with ToolCallState DENIED.
- `_runtime_metadata` :2111-2127 returns:
  - `stop_reason`, `iteration_count`, `tokens_used`, `tool_call_count`, `tool_call_states`, `tool_calls`, `usage_rollup`;
  - but not `model_call_count` and not a duration.

**`vidbyte/middleware/pipeline.py`**
- `events` :57-60.
- `metadata()` :108-122 returns `{"event_count", "events": ({middleware_name, hook, action, reason, metadata}, …)}`.
- Every non-CONTINUE decision is recorded at :160-161 / `_record` :232-246.
- Fail-open errors are also appended (:221-229).

**`vidbyte/middleware/builtins/delegation_limits.py`**
- Denials at :52-56 (`limit: max_depth`, `depth`, `max_depth`) and :63-68 (`limit: max_parallel`, `tasks`, `max_parallel`).

**`vidbyte/agents/base.py`**
- `_generate_reply` :986-1006 merges `result.metadata` into the reply metadata, so a child reply carries `middleware`.
- A new runtime is built per call (:1280, :1319, :1388).

**`vidbyte/pipelines/parallel.py`**
- `asyncio.gather` without `return_exceptions`.

**`vidbyte/lib/errors/base.py`**
- `VidbyteSdkError(message, *, details=None)` stores `.message` and `.details`; `str(exc) == message`.

**`vidbyte/lib/tools/arguments.py:31-53`**
- `ToolArguments.records` raises `ConfigurationError` with `details={"argument", "index"}`.

## 3. Tests that cover those files

**Framework**
- pytest. Async tests use `@pytest.mark.asyncio`.
- Offline harness `infinite_memory_fixtures.py` (557 lines):
  - `ScriptedTree` patches only `BaseAgent._runner_for_model`. The workspace, journal, ParallelPipeline, catalog, and bash run for real.
  - Steps: `tool_call` / `reply` / `fail` / `observe` / `after`.
  - `Gate` / `Signal` order concurrent agents without wall-clock time.
  - Every unscripted call fails.
  - Header rule 1: no feature imports at module level.
- Event helpers in `infinite_events_fixtures.py` (198 lines):
  - `AC2_KINDS` :75 (seven kinds).
  - Cap literals :43-52.
  - `EVENTS_LOGGER` :60.
  - `assert_portable` :138-158 (≤ 32,768 bytes).
  - `ac2_tree` :164.

**Commands:** see §1.4.

**Tests that pin the event set or order** (each must change with the spec; only the S2 test author edits tests)

`test_infinite_memory_events_records.py` (603 lines)
- `_FIGURES` :53-67 (13 records, worst 27,015).
- `_RECORD_OF_KIND` :69-84; `_FIELDS` :87-128; `_ITEM_LISTS` :130; `_EIGHT_ITEM_LISTS` :131; `_COST_RECORDS` :132.
- `_worst` shapes :165-227 pass every field, so a new required field breaks `_build`.
- **AC-24** :274-300:
  - the kind set equals `set(_RECORD_OF_KIND)` (:294);
  - the DropReason, FileChange, and StopCause value sets (:296-298);
  - the four enums are in `vidbyte.lib.enums.__all__` (:292-293);
  - details records are not root-exported (:300).
- AC-30 :344 is parametrized over `_FIGURES`.
- Signatures pinned by direct calls:
  - `subagent_launched(launch, card)` and `file_written(memory, …5 args)` (:469+);
  - `generator_finished(memory, reply, status, summary)` (:513);
  - `subagent_finished(pair, finished)` with `InfinitePair(launch, card, "root/p")` (:546);
  - `run_started(settings, TASK, extras)` (:585).

`test_infinite_memory_events_stream.py` (554 lines)
- **AC-2** :165 checks `kinds(seen) == AC2_KINDS` (:183), plus the envelope (:188), summaries (:189-197), and details (:199-222).
- **AC-3** :226 checks `kinds_at_next_call == [["run_started", "memory_saved"]]` (:250). Anything the root's `_after_tool_iteration` emits on iteration 1 breaks it. Its docstring says the pair entry is "reported only in subagent_finished".
- :366 checks `len(tasks) == len(AC2_KINDS)` (:388).
- **NFR-2** :418-440:
  - `public = inspect.getmembers(InfiniteEvents, inspect.isfunction)` without a leading `_` must equal the sorted kind values (:435-436).
  - Each public method is called with `object()` placeholders and must return before it reads them.
- **AC-25** :470 checks `["run_started","subagent_launched","generator_finished","subagent_finished","run_finished"]` (:493) after 3 quiet root tool iterations.
- Generic (not kind-list) checks: :265 raising sink, :293/:327 durable-before-announce, :445 token totals, :503, :524, :540.

`test_infinite_memory_events_pairs.py` (564 lines)
- :106 `["run_started","batch_rejected","run_finished"]`.
- :128-138 launch/replay order.
- :178 drop_entry list.
- :221 the AC-10b rule drop is forced by a sink Signal on `subagent_finished`.
- :291 `["run_started","file_written","file_written","run_finished"]` (2 root tool iterations).
- :328 refusals list (5 root tool iterations; `max_entries_per_agent=1`).
- :390-418 caps of 10**9, with `max_iterations=10**6`.
- :458 `kinds(deep) == ["memory_staged","generator_finished"]`.
- :479 generator raises.
- **AC-36** :542-560 (`max_parallel=2`, `max_depth=1`; :560 kinds list; :558-559 denial text).

`test_infinite_memory_events_lifecycle.py` (212 lines)
- :88 cancelled `["run_started","subagent_launched","run_stopped"]`.
- :102 resumed.
- :155 `["run_resumed","run_finished"]`, with pairs=1 and agents=6 (:158).
- :182 `["run_started","run_stopped"]`; :193; :209.

`test_infinite_memory_contract.py` (503 lines)
- Budget :474-489 (§2.1).
- Enum value sets :191-206; these do not include InfiniteEventKind.
- Public-API check :171-172.

`test_infinite_memory_handoff.py`
- Its agents have no `on_event`.
- :339-372 calls `events.file_written(...)` directly.

Other pack files (delegation, verification, resume, workspace, acceptance, context, prompts)
- They assert journal records and model-visible text, not events.
- Model-visible text must stay byte-identical (request.md:103).
- Relevant cases:
  - delegation :222 (max_parallel), :256, :274, :466;
  - resume :276 (cancel mid-pair);
  - workspace :340 (map refresh per tool iteration), :374 (map over cap).

## 4. Notes for the spec author

### 4.1 Contradictions

1. Request assumes E1, C3, and the root's D1 can be emitted from `_after_tool_iteration` (request.md:124-125). Code shows `events` is a local in `arun` (runtime.py:86), and `_after_tool_iteration` (runtime.py:129-135) reaches only `self.context_manager` and `self.workspace`. The root launch tool is also local (runtime.py:101).
2. Request assumes `_after_tool_iteration` "runs after each tool iteration". Code shows it is called only at runtime.py:700:
   - after the `after_iteration` middleware lets the loop continue;
   - not on the final-response iteration;
   - not after a continued finish attempt or a contract rejection (runtime.py:680-688 `continue`);
   - not when the `after_iteration` middleware aborts (runtime.py:690-697).
   unverified: whether it runs on an iteration that ends the run by a limit stop.
3. Request assumes state can live in `InfiniteEvents` or the runtime for one run. Code shows a new runtime per call (base.py:1319, :1388), but `BaseAgent._build_context` builds another one (base.py:1280). Field-guide `runtime-boundaries.md` (JevRuntime entry) says "The runtime instance outlives one run". unverified for this agent.
4. Request D1 reuses `batch_rejected` with a source marker (request.md:79). Code shows:
   - `batch_rejected(launch, problem)` takes the envelope from an `InfiniteLaunchTool` (events.py:179-187);
   - no launch object is in scope in `_after_tool_iteration`;
   - a generator's own launch tool is built inside `_agent` and not retained (launch.py:294).
5. Request D1 hint: denials are in `MiddlewarePipeline` events (request.md:124). This holds (pipeline.py:160-161, :232-246). But:
   - the list is cumulative per run and also holds other middleware's non-CONTINUE decisions and fail-open errors (pipeline.py:221-229);
   - `state.call_contexts` is cumulative too (runtime.py:159-183);
   - a generator that raised (launch.py:267) has no reply, so its denials are not visible.
6. Request scope D1 conflicts with these pinned statements, all of which say a denial gives no event:
   - AC-36: pairs test :542-560, `vidbyte/agents/infinite/README.md:109`, `FEATURE.md:107`;
   - launch.py header :9 (EC-37).
7. Request B3 hint is `except BaseException … raise` in `InfinitePair.run` (request.md:69). Code shows:
   - launch.py:8 rule 2 forbids it;
   - S019 accepts it only if the handler contains `raise` (s019:37-43);
   - the request itself says the header "must be reworded".
   The current `except` at launch.py:267 keeps no exception type for later (`_finish` :369 has no error parameter), and no `phase` is tracked.
8. Request A8 `error_type` (request.md:64) assumes the pair keeps the error. Code shows `_finish(status, UNCHECKED, summary, cap(_error_text(exc)), files)` passes only text (launch.py:267-270), and `subagent_finished(pair, card)` reads only pair attributes (events.py:239).
9. Request A6 asks for "duration". Code shows no run start time in `arun` or `InfiniteEvents` (only `_launched` per pair), and result metadata has no duration or `model_call_count` (runtime.py:2111-2127). `tool_call_count` counts every context, including internal `launch_subagent`, isDone, and denied calls. unverified: whether that meets "root tool calls". Request E1 also asks for "model calls"; that value exists only on loop state (runtime.py:159-183), not in metadata.
10. Request A5 `attempt` "from the journal" (request.md:61). Code shows no public per-key count. `_started` is private (journal.py:104-107), and `agents_started` is `2 × len(_started)` (:145-147). `pair_started` runs before `subagent_launched` (launch.py:150-151), so any count includes the current start.
11. Request A5 `batch_id`. Code shows no batch identifier. `ToolCall.call_id` is `str | None` (lib/dataclasses/tools.py:272).
12. Request A5 `in_flight` goes down "on finished". Code shows a pair that raises outside the caught set, or is cancelled, never reaches `subagent_finished` (launch.py:267, :382; gather in pipelines/parallel.py). Siblings keep running and can emit after `run_finished` (README notes).
13. Request A3 assumes "each refusal raise … names a rule". Code shows:
   - only `__init__` and `_entry_lines` pass `details` (workspace.py:276);
   - memory tools also catch `OSError` and `ValueError`, which carry no details (memory.py:175, :230, :264);
   - `tool_refused(memory, tool, problem)` gets `str(exc)`, not the exception (events.py:313);
   - `batch_rejected` also receives `ToolArguments.records` and `RecordFieldValidator` errors (launch.py:137), whose details are `{"argument","index"}` or `{"field"}` (arguments.py:31-53).
14. Request C3 "plus the number of files the map omits". Code shows `map_text` computes `len(lines) - index` only inside the returned text (workspace.py:239). `usage()` and `map_text()` each rescan the disk (workspace.py:98-101, :217-241), and the header forbids caching.
15. Request C3 thresholds of 50/75/90/100 % (request.md:76). Code shows defaults of 2,000 files and 2,000,000 tokens (constants :48-49). Every event test uses default caps except pairs :390 (10**9), so a crossing never fires in the existing tests unless an initial bucket is emitted.
16. Request B5 "path". Code shows the target is absolute: `journal.path.with_name(...)` (agent.py:165). request.md:104 forbids SDK-built absolute paths in events. `_section` returns text only, so "which sections were cut" is not returned (agent.py after :167).
17. Request B4 "after `ParallelPipeline(...).run("")` returns". Code shows the pipeline runs only `if pairs:` (launch.py:157), so an all-replayed batch skips it, and a non-caught pair error propagates out of `gather` before that line.
18. Request hint: `events.py` sits "at its 400-line budget" (request.md:122). This is correct as the test measures it: 412 total, 400 after the header, room 0.
    - Dataclasses has 16 lines of room and launch.py has 12, not 0.
    - A new module in `vidbyte/agents/infinite/` breaks `<= 9` (contract :484).
    - A second `vidbyte/lib/dataclasses/<x>.py` for the same domain may conflict with "Add to the existing domain module when there is one" (AGENTS.md Placement Rules). unverified: how the placement workflow reads that.
19. Request hint "one public method per new kind" is consistent with NFR-2 (stream :435-436). Any other public function on `InfiniteEvents`, including a public staticmethod, breaks that test. A `@property` is not matched by `inspect.isfunction` (unverified by test run).
20. Request A2 "keep it separate from memory_saved so AC-3 holds". The AC-3 docstring (stream :226) says the pair entry is "reported only in subagent_finished". The AC-2 list (:183) contains a committed entry path, so A2, B1, B2, and B4 all change AC-2, AC-25 (:493), AC-36 (:560), and :388.
21. Request lists "B5 arrives after the run's terminal event". Code shows `run_handoff` may run in another process or for a run still going (agent.py header :9, EC-18). unverified: the event's role and depth.

### 4.2 Gaps the spec must close

- E1 throttle value and C3 thresholds (request.md:129). Both are A007 constants. Root tool-iteration counts in pinned lists:
  - stream :493 has 3;
  - pairs :291 has 2;
  - pairs :328 has 5.
- Where the new `InfiniteEvents` code lives, given room 0 and the nine-module limit (request.md:132). The budget test docstring shows a cap raise has precedent (:475-479).
- How the root's D1 avoids re-reporting earlier denials, given the cumulative lists.
- Whether B1 and B2 fire when the generator FAILED. The verifier is skipped then (launch.py:252).

### 4.3 Unverified

- unverified: Ruff default thresholds for C901, PLR0912, and PLR0915.
- unverified: A002, A006, S015, S043, and S044 rule details (modules not opened).
- unverified: S020 scope for the tests README.
- unverified: whether FEATURE.md counts for A009. It has 33,417 chars and is not a README.
- unverified: `scripts/run_ci.py` stage list (not opened).
- unverified: FEATURE.md:174's claim that C016 owns the public-API file.
- unverified: order of `subagent_aborted` vs `run_stopped` on cancellation.
- unverified: `vidbyte/tools/toolsets/infinite.py` and `vidbyte/context/handoff/infinite.py` contents (line counts only).
