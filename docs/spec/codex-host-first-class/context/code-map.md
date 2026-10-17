# Code map: codex-host-first-class (slice 2)

Written by the S0 scout on 2026-10-17. The worktree is `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-first-class`, on branch `feat/codex-host-first-class`, with HEAD at `a7730107`. The only untracked path is `docs/spec/codex-host-first-class/`.

Every path, symbol and line below was opened in this session. Protocol facts come from two sources:
- **The schema** of the installed `codex-cli 0.163.0`. "schema" means `scratchpad/codex-research/schema-exp/codex_app_server_protocol.v2.schemas.json`, and stable/experimental is decided by presence in `schema-stable/ClientRequest.json`. The gap report states this provenance at `docs/spec/codex-host-hardening/context/codex-gap-report.md:4,39`.
- **The SDK** `openai-codex 0.163.0`, installed in `scratchpad/venv-codex163/Lib/site-packages/openai_codex/`. It was read with the venv interpreter only.

`V` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/venv-codex163/Scripts/python.exe`.

---

## 1. Rules, commands and conventions

### AGENTS.md (binding)

**General Coding Style Guidelines:**
- **§1 "Keep Call Chains One Level Deep"** (AGENTS.md:21-23). A main function calls a flat list of helpers, and a helper calls no further helper of its own. Do not nest function definitions.
- **§2 "Narrate Main Functions in Plain English"** (:25-27). Write plain-English step comments through the main function, and update them in the same edit.
- **§3 "Build in Layers of Small, Single-Purpose Classes"** (:29-31).
  - `vidbyte/lib/` is the bottom layer and never imports upward.
  - "Keep files well below 1,000 lines; when a file heads toward four digits, split it into smaller modules along subsystem lines before adding more."
- **§4 "Use Validated Dataclasses for Core Inputs and Outputs"** (:33-35). Use `@dataclass(frozen=True, slots=True)`, validate in `__post_init__`, and type closed sets as enums.
- **§5 "Write Shared Logic Once, as a Canonical Helper in `lib/`"** (:37-41).

**Placement Rules** (:43-81):
- Every new dataclass goes in `vidbyte/lib/dataclasses/<domain>.py`, with no `types.py`, `records.py` or the like.
- Every new enum goes in `vidbyte/lib/enums/<domain>.py`. "every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
- Closed-set fields are typed with an enum, not `str`.
- "Existing code": editing a legacy module in place is fine, but don't copy it as precedent.

**Repository Map** (:7-15):
- Read each folder's `README.md` to the end before changing the folder. Its `## Notes for agents` section records past review mistakes. None of the touched folders has that section; see §2.7.
- A009 caps a folder README at 40,000 characters. `vidbyte/agents/codex/README.md` has a legacy ceiling of 65,000 (`lint/rules/a009_readme_size_limit.py:29-31`) and is now 52,311 characters.
- "Do not grep, glob, or read files under `docs/`" unless named.
- "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`."

AGENTS.md defines no commit or PR convention. The session's attribution lines apply: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, and PR bodies end "🤖 Generated with [Claude Code](https://claude.com/claude-code)".

### Commands

Run every command from the worktree root.

- **Install:** none needed. The venv `V` is the editable worktree install with openai-codex 0.163.0. The extra pin is `pyproject.toml:42`, `codex = ["openai-codex>=0.163.0,<0.164.0"]`, and it is pinned by `test_codex_host_hardening_contract.py:589-595`.
- **One test file:** `PYTHONPATH=$(pwd) "$V" -m pytest -q tests/features/codex_host/test_codex_host_<x>.py -p no:cacheprovider`. Each test-file header carries its own `TESTS:` line in this form.
- **Area tests:** `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider`.
- **Live smoke (opt-in, never on by default):** `VIDBYTE_CODEX_LIVE_TESTS=1 PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_live_smoke.py`. The gate is `LIVE_ENV` at `test_codex_host_live_smoke.py:22,32`.
- **Lint:** `"$V" lint/run.py`. The last line is `SDK-LINT: PASS` (`lint/core/report.py:58`; the fail form is `SDK-LINT: FAIL`). Run one rule with `--rule <ID>`. Lint reads `git ls-files`, so `git add` new modules first (field guide `blocking-lint-invariants.md:72`).
- **Full gate:** `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source`, then `"$V" scripts/run_ci.py --stage package` with no PYTHONPATH. The stages are at `scripts/run_ci.py:74-76,261-262`; the reason for the split is in `field-guide/vidbyte-sdk/local-ci-verification.md:3-8`.
- **Inherited source-stage failure:** `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, which fails with `assert 167 == 120` (`:176-195`; field guide `local-ci-verification.md:66-71`).
- **Branch-scope check:** `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` (`test_harness_threads_surface.py:224-233`) excludes `vidbyte/tools/builtins/codex`, `vidbyte/tools/builtins/__init__.py`, `vidbyte/tools/toolsets/codex.py` and `vidbyte/tools/toolsets/__init__.py`. Any other change under `vidbyte/tools`, such as `vidbyte/tools/base.py`, or under `vidbyte/lib/configs`, fails it locally.

### Lint rules most likely to bite

The baselines are in `lint/baseline.json`.

| Rule | Baseline | What it enforces |
|---|---|---|
| C021 | 0 (`:30`) | No top-level UPPER_CASE binding in any module under `vidbyte/harnesses/native/`. Tables, bounds and messages go in `vidbyte/lib/constants/codex_host.py`. The rule file is `lint/rules/c021_native_host_constants_in_lib.py`, and the test twin is at `test_codex_host_hardening_contract.py:549-566`. |
| S008 | 19 (`:38`) | Complexity at most 10 and branches at most 12, per the briefing (`lint/rules/s008_bounded_function_complexity.py`). |
| S024 | 25 (`:52`) | Nesting at most 3 (`s024_maximum_control_flow_nesting.py`). |
| S012 | 0, per the field guide | No method named `request` (field guide `blocking-lint-invariants.md:31-36`). The SDK's own `CodexClient.request` is not ours. |
| A002 | 703 (`:3`) | `# @intent` sits within 20 lines of its `def`. |
| A001 | — | Agent-readable file header (`FILE / PURPOSE / ROLE IN CODEBASE / ARCHITECTURE NOTE / COMMON MODIFICATION PATTERNS / KNOWN EDGE CASES / RELATED DOCS / TESTS`) on every new module. `vidbyte/agents/codex/config.py` has none. |
| A003 | — | A new class in `vidbyte/lib/errors/base.py` needs the 8 `DIAGNOSTIC_FIELDS` (`blocking-lint-invariants.md:10-15`). |
| A006 | — | Directed layers; `TYPE_CHECKING` edges are the only exemption (`:38-43`). |
| S060 / S039 | — | No `dict[str, Any]` wire encoder on a lib record, and no TypedDict (`:17-22`). |
| C002 | — | Don't copy another record's stored status bool (`:46-51`). |

**Comments** wrap at 72 columns. A multi-line `#` block sits directly above the line it explains, with `# @intent <name>` on its own first line. The check is `awk 'length($0) > 72' <file> | grep -E '^\s*#'` (field guide `comment-format.md:3-8`). It is not a lint rule, so leave untouched files alone.

### User conventions from the #1055 review, now in code

- **Native-host constants and messages live in lib** (C021 above). A value that needs an SDK type is stored as the type's name and resolved at the call (`blocking-lint-invariants.md:68-73`). An example is `getattr(v2_all, CODEX_HOST_RAW_RESPONSE_MODELS[method])` at `connection.py:372`.
- **The error packet** reads "`<op> failed with <code>. <summary> The thread id was <id>. Likely cause: <cause> Next step: <step>`". It is built only by `CodexErrorMapper.error` (`errors.py:75-109`) from `CODEX_HOST_LIKELY_CAUSES[code]` (`codex_host.py:217-241`) and `CODEX_NEXT_STEPS[code]` (`constants/codex.py:491-515`). The test helper `mapped_summary` checks the head and the tail (`codex_host_support.py:297-309`).
- **Every host function builds a validated input record** from `vidbyte/lib/dataclasses/codex_host_inputs.py` right after `_guard`. This is pinned by `test_codex_host_inputs.py:212-225`.
- **Model-facing tool text** follows the field guide `model-facing-tool-contracts.md:3-15`:
  - 4–5 general sentences per tool and per parameter, with no concrete examples;
  - categorical vocabularies as `str, Enum` in `vidbyte/lib/enums`, with choices derived from the members;
  - field-name lists, but not vocabularies, may live in `vidbyte/lib/constants`.
  - `descriptions.py:5` adds two rules: each string is one literal of at least four sentences, and a WRITE tool says it starts or changes paid Codex work.

---

## 2. Files this change will touch

### 2.1 The host and its collaborators (briefing B)

`vidbyte/harnesses/native/codex/` has the following modules, with line counts from `wc -l`:

| File | Lines | What it does today |
|---|---|---|
| `host.py` | **937** | `CodexHost`, the public API. Each method is a thin main function that delegates. |
| `wire.py` | **797** | `CodexParamsTranslator` (params dicts) and `CodexResponseTranslator` (records). |
| `connection.py` | 604 | `CodexServerRequestRouter` (`:76-276`) and `CodexConnection` (`:278-601`). |
| `turns.py` | 456 | `CodexLiveTurn`, `CodexGoalTurn`, `CodexGoalFinishRule`, `CodexTurnWatcher`, `CodexTurnRegistry`. |
| `thread_helpers.py` | 351 | `CodexThreadHelpers`: listings, lineage, turns, compact, delete, goal, fork. |
| `errors.py` | 240 | `CodexErrorMapper`. |
| `skill_functions.py` | 225 | `CodexSkillHost` Protocol and `CodexSkillFunctions`: goal and skill runs. |
| `preflight.py` | 210 | `CodexPreflight`: usage, sandbox, models, idle and exists checks. |
| `turn_events.py` | 157 | `CodexTurnEvents`: ends turns from events, lost watchers, review completion. |
| `reviews.py` | 156 | `CodexReviews`: `review/start` and its adoption. |
| `oneshot.py` | 137 | Six module functions, each `async with CodexHost(settings) as host`. |
| `__init__.py` | 30 | `__all__` is `CodexHost` plus the six oneshot functions. |

**How CodexHost is wired.** `_open` (`host.py:190-238`) lazy-imports the SDK-touching modules (INV-1/D-21), then builds the collaborators:
- `CodexTurnRegistry(loop)` at `:220`;
- `CodexConnection(params.client_config(binary), loop, handler)` at `:222`;
- `CodexPreflight(...)` at `:224`;
- `CodexThreadHelpers(connection, params, responses, preflight, registry)` at `:228`;
- `CodexTurnEvents(connection, responses, registry, threads)` at `:229`;
- `CodexReviews(...)` at `:230`;
- `CodexSkillFunctions(self)` at `:231`.

**Private host helpers:**
- `_guard(operation, talks=)` at `:730-739`;
- `_owned(operation, handle)` at `:741-747`, which refuses handles the registry does not hold;
- `_reject_experimental_fork_fields` at `:749-759`;
- `_tool_bridge` at `:761-771`;
- `_open_thread` at `:773-792`;
- `_start_turn` at `:802-818`;
- `_start_goal` at `:820-854`;
- `_accept`, `_adopt_late_turn`, `_adopt_late_goal`, `_end_running_turns` and `_on_death` at `:856-935`.

**Public method order** (`host.py:273-728`) has a test pin (§3.4):
1. `check_codex_ready`, `get_codex_rate_limits`, `list_codex_models`;
2. `spawn`, `continue`, `fork`, `list`, `read`;
3. `wait_codex_turn` (`:442-463`), `get_codex_turn_result`, `steer`, `interrupt`, `track_codex_thread_usage`, `forget_codex_turns` (`:521-535`);
4. `launch_codex_subagents`, `start_codex_review` (`:583-601`);
5. then the 12 helper methods in pinned order, from `list_recent_codex_threads` (`:603`) through `run_codex_openai_docs` (`:719`).

**The thin-method pattern**, as `get_codex_goal` (`host.py:678-683`) and `delete_codex_thread` (`:664-676`) show:
1. `operation = CodexHostOperation.X`, then `self._guard(operation, talks=True|False)`.
2. Build the input record: `CodexThreadRef(operation=..., thread_id=...)` (`codex_host_inputs.py:129`), `CodexTurnRef` (`:141`), or a function-specific record.
3. Delegate to a collaborator method that runs the preflight and then one call:
   - a typed call: `await connection.call(operation, METHOD, connection.client.<typed>, *args, thread_id=...)` (`connection.py:318-362`);
   - a raw call: `fn = connection.raw(METHOD, params)` (`:364-374`), then `await connection.call(operation, METHOD, fn, thread_id=...)`. `thread_helpers.py:192-194` is the example.
4. Translate with `CodexResponseTranslator` into a `vidbyte/lib/dataclasses/codex_host.py` record.

**Error path.** `connection.call` maps every exception with `CodexErrorMapper.from_exception(exc, operation, method, dead=, bound_seconds=, thread_id=)` and raises `from None` (`connection.py:353-356`).

**INV-7 call record.** `_log_call` (`connection.py:435-462`) writes DEBUG `codex_host_call operation= method= thread_id= duration_ms=`. On failure it writes WARNING `codex_host_call_failed … failure_code= error_type= origin=`. Ids go through `LogToken.of(value, CODEX_HOST_LOG_TOKEN_MAX_CHARS)`. `_log_late` (`:464`) covers callers that left early.

**Retries.**
- Typed calls retry only when the method is in `CODEX_HOST_RETRIED_METHODS` (`codex_host.py:63`: `account/read`, `thread/read`, `thread/list`, `thread/name/set`), wrapped in `retry_on_overload` (`connection.py:339-340`).
- The raw path always uses `client.request_with_retry_on_overload`. It sends once only for methods in `CODEX_HOST_SPENDING_RAW_METHODS` (`codex_host.py:59`: `review/start`, `thread/goal/set`), via `max_attempts=CODEX_HOST_SINGLE_ATTEMPT` (`constants/codex.py:382`).
- A raw method must have its response class name in `CODEX_HOST_RAW_RESPONSE_MODELS` (`codex_host.py:46-56`). The name is resolved with `getattr(v2_all, name)` at `connection.py:372`.

**Spending starts** go through `connection.start(...)` (`connection.py:391-433`), which also adopts a turn whose caller has left (`host.py:802-818`).

**Patterns to model new families on** (request.md:142-145):
- **Thin helper:** `CodexThreadHelpers` (`thread_helpers.py`). It runs: guard → record → `require_idle` / `reserve` → `_stored_status` → one call → `release`. `compact` (`:149-174`) and `delete` (`:176-195`) are the mutation examples.
- **Run wrapper:** `CodexSkillFunctions`. It goes only through the host's public API, typed by the `CodexSkillHost` Protocol (`skill_functions.py`; never imports host.py), relabels errors with `CodexErrorMapper.relabel` (`errors.py:173`), and sends one interrupt on failure.
- **Turn-event consumer:** `CodexTurnEvents` (`turn_events.py`).

host.py and wire.py are both near the line ceiling (§4.3).

### 2.2 Turn and stream machinery (briefing C)

**How a notification reaches a turn today:**
1. `client.turn_start(thread_id, items, params)`. In the SDK, `_start_turn` (`client.py:650-680`) registers the turn's default router consumer before it returns, and refuses a thread that has a goal operation running (`:666-670`).
2. `CodexTurnRegistry.track` makes a `CodexLiveTurn` (`turns.py:359-363`, class at `:73`).
3. `CodexLiveTurn.watch` (`turns.py:154-177`) starts one `CodexTurnWatcher`, a daemon thread named `codex-host-watcher` (`:281-328`, `:296`):
   - a plain turn reads `client.next_turn_notification(turn_id)`;
   - a goal run reads `client.next_goal_notification(state)`;
   - each note is posted to the host loop with `loop.call_soon_threadsafe(on_event, note)` (`:323`);
   - a failed read posts `on_lost` (`:324-327`);
   - a plain turn's watcher stops after `turn/completed` (`:328`), while a goal run's watcher reads until its stream closes;
   - cleanup unregisters the turn route.
   - A timeout is a loop timer, `loop.call_later(timeout, self.stop, …)` (`:176-177`).
4. `CodexTurnEvents.on_event` (`turn_events.py:64-91`) ignores events for an ended turn and calls `turn.observe(note)`. It sends one interrupt when the output cap is passed, and ends the turn on its end event. An exception inside it is routed to `fail` (`:90-91`). `on_lost` (`:93-96`) runs `_end_lost_turn` as a task.
5. `CodexLiveTurn.observe` (`turns.py:101-117`) keeps only three things:
   - `ItemCompletedNotification`, appended to `self.items` (an unbounded `list`, `:85`) and logged as `codex_host_turn_item`;
   - `ThreadTokenUsageUpdatedNotification`, kept as first and latest usage;
   - `TurnCompletedNotification`.
   **Every other per-turn notification is read and dropped**: deltas, `turn/plan/updated`, `turn/diff/updated`, `item/started`, and so on.
6. The end builds a `CodexTurnSnapshot` (`codex_host.py:316`). `registry.finish` (`turns.py:391`) logs `codex_host_turn_ended` and resolves `turn.ended`, an `asyncio.Future` from `loop.create_future()` (`:94`).
7. `wait_codex_turn` (`host.py:442-463`) builds `CodexTurnWaitRequest` (`codex_host_inputs.py:228`), then `_owned`, then `asyncio.wait_for(asyncio.shield(turn.ended), timeout)`. On timeout it returns `turn.snapshot or responses.running(handle)`. There is no default timeout.
8. `CodexTurnHandle` (`codex_host.py:290`) is only the record `(thread_id, turn_id)`.

**Notifications with no turnId** go to the SDK's global queue (`_message_router.py:308-310`). The host's liveness monitor reads that queue in a loop and discards every note (`connection.py:540-548`). Today nothing observes `thread/settings/updated`, `mcpServer/startupStatus/updated`, `thread/archived`, `thread/queue/changed` and the like.

**What the SDK offers:**
- `TurnHandle.stream()` returns `Iterator[Notification]` (`api.py:822-845`), and `AsyncTurnHandle.stream()` returns `AsyncIterator[Notification]` (`api.py:879-893`). The async one reads with `asyncio.to_thread(self._subscription.next)` and stops on its own `turn/completed`.
- Both sit on `_TurnSubscription`, a per-consumer cursor over shared events (`_message_router.py:31-60`). It is created by `MessageRouter.subscribe_turn` (`:177-181`), which the client exposes only privately as `CodexClient._subscribe_turn_notifications` (`client.py:409-410`).
- The public low-level API (`register_turn_notifications`, `next_turn_notification`, `unregister_turn_notifications` at `client.py:412-422`) gives **one** default consumer per turn (`_message_router.py:208-226`), and the host's watcher already uses it.
- `CodexClient.stream_text(thread_id, text, params)` (`client.py:781`) starts its own turn and yields `AgentMessageDeltaNotification` only.

**Bounds and backpressure.** There are none:
- The router keeps each turn's events in a `dict` until every subscriber has read them (`_message_router.py:183-206`, pruning in `_prune_turn_events`), and nothing caps it.
- The global queue is an unbounded `queue.Queue()` (`:90`).
- The host's `items` list is unbounded (`turns.py:85`).
- The only bounds are wall clocks:
  - `CODEX_HOST_REQUEST_TIMEOUT_SECONDS == CODEX_TOOL_CALL_TIMEOUT_SECONDS == 300.0` (`constants/codex.py:319,357`);
  - `CODEX_HOST_TOOL_MAX_WAIT_SECONDS = 240.0` (`:360`), which the tool layer applies to waits (`live.py:71-78`);
  - the per-turn `timeout_seconds` timer.

### 2.3 Plan mode (briefing D)

**Where `TurnStartParams` is built.** `CodexParamsTranslator.turn_start` (`wire.py:256-281`):
1. Start from `CodexContentTranslator.turn_kwargs(...)` (`vidbyte/agents/codex/config.py:185-206`), which lists `approval_mode`, `cwd`, `effort`, `model`, `output_schema`, `personality`, `sandbox`, `service_tier` and `summary`. The same function serves `CodexHarnessAgent`.
2. Add the sandbox policy with `networkAccess` and `writableRoots`, then `disabled_plugin_ids` and `service_tier_for_turn`.
3. Finish with `TurnStartParams.model_validate(values).model_dump(by_alias=True, exclude_none=True, mode="json")` (`:281`).

`host._start_turn` (`host.py:814`) passes that dict to `client.turn_start(thread_id, items, params)`. In the SDK, `_params_dict` returns a dict unchanged (`client.py:84-110`, `:107-108`), so keys added after validation reach the wire.

**Existing post-validation injections** are the pattern for experimental fields:
- `thread_start`: `params[CODEX_DYNAMIC_TOOLS_PARAM] = [...]` after the dump (`wire.py:207-209`; `CODEX_DYNAMIC_TOOLS_PARAM = "dynamicTools"` at `constants/codex.py:314`);
- `thread_fork`: `params["beforeTurnId"]` and `params["deferGoalContinuation"] = True` (`wire.py:249-253`).

Each injection also has a local gate on `CodexClientSettings.experimental_api` (`lib/dataclasses/codex.py:113`, default `True`):
- `_tool_bridge` raises `CODEX_HOST_EXPERIMENTAL_API_TEXT` (`host.py:767-768`, `constants/codex.py:371`);
- `_reject_experimental_fork_fields` walks `CODEX_HOST_FORK_EXPERIMENTAL_FIELDS` (`codex_host.py:161`) and raises `ConfigurationError(CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE.format(field=name), details={"field": name})` (`host.py:749-759`, `codex_host.py:285`).

`experimental_api` reaches the SDK through `CodexContentTranslator.client_kwargs` → `CodexConfig`, and the SDK sends `capabilities.experimentalApi` in `initialize` (`client.py:315`).

**The SDK drops `collaborationMode`; verified in this session.**
- `TurnStartParams.model_validate({"threadId": "t", "input": [], "collaborationMode": {...}}).model_dump(...)` gives `{'input': [], 'threadId': 't'}`.
- `TurnStartParams.model_config == {'populate_by_name': True}`, so pydantic's default `extra="ignore"` applies.
- The SDK's `TurnStartParams` fields do not include `collaboration_mode`. The schema marks it exp-only, along with `additionalContext`, `cyberAccessProgram`, `environments`, `multiAgentMode`, `permissions`, `responsesapiClientMetadata` and `runtimeWorkspaceRoots`.

**Schema shapes** (schema-exp v2 definitions):

| Definition | Shape |
|---|---|
| `TurnStartParams.collaborationMode` | `CollaborationMode \| null`, exp-only field. Description: "EXPERIMENTAL - Set a pre-set collaboration mode. Takes precedence over model, reasoning_effort, and developer instructions if set. For `collaboration_mode.settings.developer_instructions`, `null` means 'use the built-in instructions for the selected mode'." |
| `CollaborationMode` | `{mode: ModeKind, settings: Settings}`, both required. Defined in the stable schema; the SDK model `v2_all.CollaborationMode` has fields `mode` and `settings`. |
| `ModeKind` | enum `["plan", "default"]` (SDK `v2_all.ModeKind`). |
| `Settings` | `{model: string (required), reasoning_effort: ReasoningEffort \| null, developer_instructions: string \| null}`. The wire keys are **snake_case**. SDK `v2_all.Settings`. |
| `collaborationMode/list` | [EXP] (`methods.txt:127`, "Lists collaboration mode presets"). Params `CollaborationModeListParams = {}`; response `CollaborationModeListResponse = {data: [CollaborationModeMask]}`. **Neither** params nor response exists in SDK `v2_all`. |
| `CollaborationModeMask` | `{name (required), mode: ModeKind \| null, model: string \| null, reasoning_effort: ReasoningEffort \| null}`, snake_case on the wire. SDK `v2_all.CollaborationModeMask` exists. |
| plan `ThreadItem` | `{id, text, type: "plan"}` (SDK `v2_all.PlanThreadItem`). `"plan"` is already in `CODEX_SUPPORTED_ITEM_TYPES` (`constants/codex.py:67-81`). |
| `item/plan/delta` | `PlanDeltaNotification {delta, itemId, threadId, turnId}`; the method list notes "EXPERIMENTAL - proposed plan streaming deltas" (`methods.txt:218`). |
| `turn/plan/updated` | `TurnPlanUpdatedNotification {plan: [TurnPlanStep{step, status}], explanation?, threadId, turnId}`. |

Plan mode asks its questions through the server request `item/tool/requestUserInput`. Slice 1's router answers it: by default with `{"answers": {}}` (`CODEX_HOST_SERVER_REQUEST_DEFAULT_ANSWERS`, `codex_host.py:82-90`), or through the developer's `approval_handler`. The source is the gap report, `codex-gap-report.md:64`.

### 2.4 The tool layer (briefing E)

**Files** in `vidbyte/tools/builtins/codex/`:

| File | Lines | Holds |
|---|---|---|
| `_base.py` | 251 | `CodexToolScope` and `_CodexHostTool` |
| `__init__.py` | 82 | the 26 tool classes plus `CodexToolScope` |
| `descriptions.py` | 84 | the model-facing text |
| `threads.py` | 335 | spawn, continue, fork, list, read |
| `thread_helpers.py` | 240 | recent, since, search, lineage, turns, compact |
| `skill_functions.py` | 212 | get_goal, run_goal, list_skills, run_skill, run_openai_docs |
| `live.py` | 190 | wait, get, steer, interrupt, track |
| `delegation.py` | 134 | launch, review |
| `readiness.py` | 97 | ready, rate limits, models |

The catalog is `vidbyte/tools/toolsets/codex.py` (105 lines). Both `vidbyte/tools/builtins/__init__.py` (380 lines; Codex imports at `:32-58`, `__all__` entries between `:230` and `:368`, docstring bullet at `:11`) and `vidbyte/tools/toolsets/__init__.py` (`:11,19,25`) re-export.

**How a tool is declared.** Each tool is one `_CodexHostTool` subclass (`_base.py:112-248`) with three parts:
- `spec()` returns `ToolSpec(name=OP.value, description=<DESCRIPTION constant>, permission=ToolPermission.READ|WRITE, input_schema={"type": "object", "additionalProperties": False, "required": [...], "properties": {...}})`;
- `execute(call)` returns `await self._run(OP.value, self._perform(call))`;
- `_perform` reads the arguments with the `_resolve_*` helpers, calls the host once, and returns a JSON string through `self._json(record)`.

`thread_helpers.py:48-75` is the simplest example. The `_resolve_*` helpers are:
- in `_base.py`: `_resolve_text` (`:153`), `_resolve_count` (`:163`), `_resolve_timestamp` (`:173`), `_resolve_seconds` (`:181`), `_resolve_choice` (`:191`), `_resolve_choices` (`:202`), `_resolve_texts` (`:213`), `_resolve_schema` (`:221`);
- `BaseTool._resolve_bool_argument` (`vidbyte/tools/base.py:99-109`).

`ToolPermission` (`vidbyte/lib/dataclasses/tools.py:47-53`) is `SAFE | READ | WRITE | EXECUTE`.

`_run` (`_base.py:120-141`) never raises:
- `CodexAgentError` keeps its code and next step;
- `ConfigurationError` and `ToolExecutionError` become `configuration.invalid_argument`;
- any other `Exception` becomes `codex.api_error`, logged once as `codex_host_tool_failed tool= error_type= origin=`;
- cancellation propagates.

Module-level constants such as `RECENT = CodexHostOperation...` are allowed in `vidbyte/tools/` (C021 covers `native/` only), but enums and vocabularies must come from `vidbyte/lib`.

**Registration.**
1. Import the class in `builtins/codex/__init__.py` and add it to `__all__` in sorted order (`:6`).
2. Add one line to `CodexHostTools.tool_classes` "at its place in the function order" (`toolsets/codex.py:72-99`).
3. Re-export it from `vidbyte/tools/builtins/__init__.py`. This is pinned (§3.4).
4. Put the text in `descriptions.py`.

**Scope.**
- `CodexToolScope` (`_base.py:55-109`) holds `max_live_turns`, `spawn_defaults` and the owned handles.
- A turn-starting tool calls `scope.reserve(host, n, OP)` / `release` in `finally` / `own(handles)`; see `threads.py:139-146` and `skill_functions.py:99-105`.
- Handle tools call `scope.require_owned(handle, OP)` (`live.py:76`). The wait is capped at `CODEX_HOST_TOOL_MAX_WAIT_SECONDS` (`live.py:71-78`).
- The posture comes only from `spawn_defaults`; the model sets only a few values (`threads.py:5-6`, INV-34).

**Tool rules in the request** (request.md:103-105):
- Destructive or unsandboxed functions are never tools: `delete_codex_thread` (INV-2), `reset_codex_memories`, revert, and any `process/spawn`. `reset_codex_memories` is also marked "(never a tool)" at `request.md:282`.
- Tools never let a model widen approvals or the sandbox.
- The service tier stays developer-only.
- The test literal `FORBIDDEN_PARAMETERS` already pins these names out of every tool schema: `approvals_reviewer`, `approval_policy`, `approval_mode`, `sandbox`, `network_access`, `writable_roots`, `turn_service_tier`, `service_tier`, `approval_handler`, `handler`, `before_turn_id`, `defer_goal_continuation`, `force_reload` (`test_codex_host_tool_hardening.py:50-65`).
- `forget_codex_turns` also has no tool today: the tool count is 26 against 28 host functions.

**`vidbyte/agents/codex/tools.py`** (198 lines) is not the model-facing CodexHost tool layer. It holds `CodexToolTranslator` (`:50`) and `CodexToolBridge` (`:83`), which attach Vidbyte tools to a Codex thread as app-server dynamic tools (`dynamicTools` on `thread/start` only), and `CodexToolCallHandler` (`:137`). Its tests are `tests/test_codex_tools.py` and `tests/features/codex_host/test_codex_host_bridge.py`.

### 2.5 Lib records, constants and enums (briefing F, files)

| Path | Lines | Today | Notes |
|---|---|---|---|
| `vidbyte/lib/constants/codex_host.py` | 475 | Host tables and messages: `CODEX_HOST_RAW_RESPONSE_MODELS` (`:46-56`), `SPENDING` (`:59`), `RETRIED` (`:63`), `SERVER_REQUEST_DEFAULT_ANSWERS` (`:82-90`), `REJECTED_FIELDS` (`:105-153`), `FORK_EXPERIMENTAL_FIELDS` (`:161`), `LIKELY_CAUSES` (`:217-241`), messages. | `__all__` (`:361-475`) is ASCII-sorted and pinned sorted (`test_codex_host_hardening_contract.py:519-520`). This is where slice 1 put new method constants such as `CODEX_CURRENT_TIME_READ_METHOD`. |
| `vidbyte/lib/constants/codex.py` | 640 | Older Codex constants: method names (`:429-441`, `:521-532`), `CODEX_FAILURE_CLASSIFICATION` (`:100`), `CODEX_NEXT_STEPS` (`:491-515`), timeouts (`:319-360`). | `__all__` (`:537-640`) is not sorted, and its **tail is pinned** (`test_codex_host_helper_surface.py:286-288`), so appending here breaks that test. |
| `vidbyte/lib/dataclasses/codex_host.py` | **873** | Output records `CodexGoal` … `CodexServerAnswer` (classes `:120-828`), including `CodexSpawnRequest` (`:132-273`), `CodexTurnHandle` (`:290`) and `CodexTurnSnapshot` (`:316`). | `__all__` (`:846-873`) has 26 names, pinned as `RECORD_EXPORTS`. The file is near the ceiling. |
| `vidbyte/lib/dataclasses/codex_host_inputs.py` | 424 | 17 input records, `CodexHostSetup` (`:100`) through `CodexSkillRunRequest` (`:380`). | `__all__` (`:406-424`) is pinned by set equality with `VALID_RECORDS` (`test_codex_host_inputs.py:136`). |
| `vidbyte/lib/dataclasses/codex.py` | **1,205** | `CodexClientSettings` (`:102`, `experimental_api` `:113`), `CodexThreadSettings` (`:186`), `CodexTurnSettings` (`:247-273`: approval_mode, cwd, effort, model, personality, sandbox, service_tier, summary), `CodexAgentSettings` (`:277`), `CodexRunInput` (`:485`), `CodexItem` (`:725`), `CodexRunResult` (`:765`). | Over the ceiling. Slice-1 spec §12.3 row 7 / D-17 says "no growth". `__all__` is computed from the `Codex*` globals. |
| `vidbyte/lib/enums/codex.py` | 330 | 27 enums, among them `CodexHostOperation` (`:267-299`), `CodexGoalStatus` (`:246`), `CodexReasoningEffort` (`:38`) and `CodexServerRequestKind` (`:137`). | `__all__` (`:302-329`): `CodexFailureClass` first, the rest alphabetical (pinned). There is **no** other `codex*.py` in `vidbyte/lib/enums/`. |
| `vidbyte/lib/enums/__init__.py` | 341 | Codex imports at `:44-70`; Codex entries in `__all__` at `:212-237` (list starts `:200`). | The Codex order is pinned as `ENUMS_CODEX_ORDER`. |
| `vidbyte/lib/enums/failure.py` | 344 | `FailureCode` (`:22`). The Codex block runs `:35-65`: `CODEX_RUN_OPTION_UNSUPPORTED` at `:46`, the 15 host codes `:47-61`, the 4 helper codes `:62-65`. Then `INPUT_EMPTY` (`:66`) and `RULE_EVALUATION_FAILED` (`:163`), followed by the 28 harness codes. | See §4.3: no free slot exists for a new code. |
| `vidbyte/lib/errors/base.py` | — | `CodexAgentError` (`:138`), with `next_step` (`:189-190`) and `retryable` (`:196`). | Codes come from `FailureCode`. |
| `vidbyte/agents/codex/config.py` | 295 | `CodexContentTranslator.turn_kwargs` (`:185-206`), shared with `CodexHarnessAgent`. | Has no A001 header. |

### 2.6 Wire translator and errors

- **`wire.py`, `CodexParamsTranslator`.** The methods are:
  - `client_config` (`:188-194`), `thread_start` (`:196-210`), `thread_resume` (`:212-222`), `thread_fork` (`:224-254`), `turn_start` (`:256-281`);
  - `thread_list` (`:307-331`), which builds a plain dict and drops falsy values, with no `model_validate`;
  - `thread_params` (`:334`), `server_answer` (`:377-386`), `default_answer` (`:388-396`), `review`, `goal_budget`, `model_page`, `_approvals`, `_thread_sandbox`, `_agents_config`.
- **`wire.py`, `CodexResponseTranslator`** (`:472-794`). Its methods include `thread_info` (`:570-599`), `summary`, `goal` (`:620-636`), `skills`, `turn_page`, `running`, `turn_snapshot`, `goal_snapshot` and `_snapshot`.
- **`errors.py`, `CodexErrorMapper`.** Its methods are `error` (`:75-109`), `from_exception` (`:112`), `_rpc_code` (`:146`, per-method refusal meanings for `thread/read`, `turn/steer` and `thread/fork`), `relabel` (`:173`), and builders including `process_exited` and `goal_problem`.

### 2.7 Docs, READMEs and support files the change reaches

None of these folder READMEs has a `## Notes for agents` section.

| Path | Size | Notes |
|---|---|---|
| `vidbyte/harnesses/README.md` | 11,360 chars | The `native/` bullet is pinned **verbatim** as `README_BULLET` (`test_codex_host_packaging.py:110,212-215`). |
| `REPO_MAP.md` | — | The `vidbyte/harnesses/native/` section is pinned verbatim as `REPO_MAP_SECTION` (`test_codex_host_packaging.py:109,203-210`). |
| `vidbyte/harnesses/native/__init__.py` | — | Pinned by SHA-256 (`test_codex_host_packaging.py:26,198-201`). |
| `vidbyte/tools/README.md` | 6,456 chars | |
| `vidbyte/lib/README.md` | 4,174 chars | |
| `tests/features/codex_host/README.md` | 16,555 chars | Has a File Index (`:16-52`) and a dated `## Logs` (`:54`). |
| `tests/features/codex_host/FEATURE.md` | — | Contract, failure modes, and the Test Suite Map (`:155-195`). |

`vidbyte/harnesses/native/codex/` has no README.

---

## 3. Tests

### 3.1 Framework and layout

- Tests use `unittest` classes run by pytest; host tests use `unittest.IsolatedAsyncioTestCase`.
- `tests/features/codex_host/` holds 30 `test_codex_host_*.py` modules (10,675 lines) and three helpers:
  - `codex_host_fakes.py` (902 lines);
  - `codex_host_helper_fakes.py` (237);
  - `codex_host_support.py` (828).
  It also has `FEATURE.md` and `README.md`. The file index is at `README.md:23-52`.
- **openai-codex gating.** Modules that need the SDK use `requires_sdk` (`codex_host_support.py:37-38`). CI installs only the dev extra, so these are skipped there. Contract modules import feature names inside each test, so a missing name fails one test rather than collection.
- `tests/features/harness_threads/` holds 14 test files, `conftest.py` and `fake_harness.py`. The ones that matter here are:
  - `test_harness_threads_surface.py`, with the inherited failure and the branch scope (§1);
  - `test_harness_threads_static_policy.py`, which skips `native/codex` (`:26-31`).
- `tests/test_codex_*.py` holds 8 files, 4,537 lines in all. They cover `CodexHarnessAgent` and the dynamic-tool bridge: `agent_input_bridge`, `failure_recovery`, `fork_inheritance`, `middleware`, `output_contracts`, `pipelines`, `tools` and `usage_tracking`. `test_codex_failure_recovery.py` and `test_codex_fork_inheritance.py` construct `CodexTurnSettings`.

### 3.2 The fake app-server (`codex_host_fakes.py`)

**How it attaches.** `client_class(server)` (`:408-410`) builds a subclass of the **real** `openai_codex.client.CodexClient` (`FakeCodexClient`, `:350-405`). `HostTestCase` patches it at the seam `vidbyte.harnesses.native.codex.connection.CodexClient` (`codex_host_support.py:41,397-399`). Lines go to `FakeAppServer.receive` (`:534-555`), which answers each request on its own daemon thread (`:544`, `_answer` `:557-566`).

**What it answers** is the `_handlers` table at `:469-486`:
- `initialize`, `account/read`, `account/rateLimits/read`, `windowsSandbox/readiness`, `model/list`;
- `thread/start`, `thread/resume`, `thread/fork`, `thread/read`, `thread/list`, `thread/name/set`;
- `turn/start`, `turn/steer`, `turn/interrupt`, `review/start`;
- through `HelperHandlers._helper_handlers()` (`codex_host_helper_fakes.py:106-115`, with `_thread_list` at `:117`): `thread/goal/clear`, `thread/goal/set`, `thread/goal/get`, `thread/compact/start`, `thread/delete`, `thread/turns/list`, `skills/list`.

Any other method gets `-32601 method not found` (`:573-575`). That includes every slice-2 method: `thread/settings/update`, `turn/settings/update`, `collaborationMode/list`, `mcpServerStatus/list`, the memory methods, `thread/archive`/`unarchive`, `thread/revert`, `thread/inject_items`, the queue methods, the background-terminal methods, and `thread/search`.

**Adding a method.** Add a handler to `_handlers`, building the answer from the generated model's aliases (`:7`). A thread-helper, goal or skill method goes in `codex_host_helper_fakes.py` instead (`:7`).
- `codex_host_fakes.py` is at 902 lines. The established split is a mixin with no state, like `HelperHandlers` (`codex_host_helper_fakes.py:66-115`), which `FakeAppServer(HelperHandlers)` inherits (`:413`). Its switches are initialised by `_init_helper_switches()` (`:468`; `helper_fakes:80-104`) and are off by default.
- A handler returns a dict, or a `Reply(result, before=[notes], after=[notes])` (`:56-62`).
- Raise `FakeRpcError(code, message, data)` (`:65-78`) for a JSON-RPC error. A bug inside a handler is recorded in `handler_errors`, which `_assert_fake_healthy` fails on (`:584-587`, `support:408-410`).

**Holding and failing calls:**
- `server.hold(method, predicate)` returns a `Hold` with `wait_arrived()`, `release()` and `wait_responded()` (`:86-112`, `:625-630`). A hold is capped at `HOLD_LIMIT_SECONDS = 60` (`:39`), and `release_all` runs at cleanup (`support:392`).
- `server.fail(method, error, times=, predicate=)` (`:638-641`).
- `server.before_response(method, action, predicate)` writes notifications before the response line (`:643-646`).
- `overloaded_error()` produces the `-32001` overload answer (`:81-83`).

**Emitting notifications:**
- `server.emit([(method, params), ...])` pushes lines onto stdout, one FIFO (`:670-672`).
- `emit_usage` (`:674-675`), `item_note` (`:677-678`) and `final_item` (`:680-681`).
- `completion_notes(thread_id, turn_id, final=, status=, usage=, error=, phase=)` stores the outcome and returns the item, usage and `turn/completed` notes (`:683-698`); `complete_turn` emits them (`:700-702`).
- `goal_update` (`:704-708`).
- `server_request(method, params)` sends a server request and returns a `Future` of the client's answer (`:710-718`).
- `die(stderr)` (`:720-725`) and `send_raw(text)` (`:727-730`).

`_turn_start` emits `turn/started` after the response, and the completion too when `autocomplete` is set (`:869-878`).

**Observing requests:** `server.requests` and `server.wait_for(method, predicate, count)` (`:653-656`), `matching` (`:658`), `methods()` (`:661`) and `kinds()` (`:664`).

**Thread store:** `FakeThread` (`:142-200`), `FakeTurn` (`:115-139`), `new_thread`, `seed_thread`, `name_next` and `thread_or_error` (`:734-772`). An ephemeral thread lists no turns (`helper_fakes:217`).

**Version drift.** `FAKE_VERSION = "0.162.1"` (`:33`), and the header still says it answers "the way codex app-server 0.162 does" (`:3`), while the SDK pin is 0.163.

### 3.3 Support helpers (`codex_host_support.py`)

**`HostTestCase`** (`:382-525`). In `asyncSetUp` (`:385-402`) it builds the fake, patches the seam, and patches `shutil.which`. Its helpers are:
- `patch_connection(name, value)` (`:412-416`), which patches a bound in the connection module namespace;
- `patch_skill_functions` and `patch_platform`;
- `wait_for_request`, `wait_until`, `ask` (sends a server request through the real reader thread, `:438-441`) and `count`;
- **`open_host(settings=None, approval_handler=None)`** (`:447-455`), which enters the host and registers a close cleanup;
- **`capture_logs(*names)`** (`:457-470`), a `LogRecorder` on `HOST_LOGGER = "vidbyte.harnesses.native.codex"` and `TOOLS_LOGGER = "vidbyte.tools.builtins.codex"` (`:279-280`);
- `close_host`, `spawn(host, prompt, **fields)`, `wait_done`, `assert_problem`, `assert_codex_error(awaitable, code)` (`:496-508`) and `run_in_other_loop`.

**Log helpers:**
- `log_events(records, event)` (`:539-541`).
- **`log_fields(record)` is strict** (`:544-555`). Any word without `=` raises `AssertionError` (S5 R-12), so every logged value must be one token, which `LogToken.of` guarantees.

**Spec literals:** `NEXT_STEPS` (`:64-91`), `NEW_FAILURE_CODES` (`:95-115`), `CLASSIFICATION_ROWS` (`:118-138`), `TOOL_TABLE` (`:141-193`), `TOOL_NAMES` (`:194`), `HELPER_METHODS` (`:197-210`), the messages, `RETRYABLE_CODES`, `RETRIED_METHODS`, `GOAL_REJECTED_FIELDS` and `DEFAULT_ANSWERS` (`:263-275`).

**Other helpers:**
- `mapped_summary` (`:297-309`), `error_texts`, `assert_no_canary` and the privacy canaries (`:48-52`);
- `FieldCarryingMapper` (`:351-379`);
- `make_echo_tool`.

**`StubCodexHost`** (`:584-828`) is a duck-typed host for the tool tests. It answers 27 methods, every host method except `forget_codex_turns`, which has no tool. Each new tool needs one stub method that calls `self._enter(name, ...)`.

The file is at 828 lines.

### 3.4 Pins that adding names will break (briefing F)

Each row is a superseded edit the spec must list.

| Test file:line | Literal | What it pins |
|---|---|---|
| `test_codex_host_packaging.py:28,226` | `NATIVE_CODEX_EXPORTS` | `vidbyte.harnesses.native.codex.__all__` = CodexHost + 6 oneshot functions, exact list. |
| `test_codex_host_packaging.py:31-58,227` | `RECORD_EXPORTS` | `vidbyte.lib.dataclasses.codex_host.__all__`, exact 26-name list. |
| `test_codex_host_packaging.py:79-106,242` | `ENUMS_CODEX_ORDER` | The `Codex*` entries of `vidbyte.lib.enums.__all__`, exact order (26 names). |
| `test_codex_host_packaging.py:60-75,243-248` | `NEW_ENUMS` | Each one is re-exported, and `enums/codex.py.__all__[1:]` is sorted with `CodexFailureClass` first. |
| `test_codex_host_packaging.py:183` | `(26, "check_codex_ready")` | Tool count in the import probe. |
| `test_codex_host_packaging.py:228-230` | `TOOL_TABLE` | `sorted(builtin_codex.__all__) == sorted(TOOL_TABLE classes + ["CodexToolScope"])`. |
| `test_codex_host_packaging.py:250-252` | `TOOL_TABLE` | Every tool class is re-exported by `vidbyte.tools.builtins`. |
| `test_codex_host_packaging.py:257` | literal list | `toolsets.__all__ == ["CodexHostTools", "CodingAgentTools", "InfiniteMemoryAgentTools", "ParadigmMinimalToolset"]`. |
| `codex_host_support.py:141-194` | `TOOL_TABLE` / `TOOL_NAMES` | `(name, class, permission, parameters, required)` for each tool, in catalog order. It feeds every row below. |
| `test_codex_host_tools.py:155-157` | `len(tools) == 26`, `TOOL_NAMES` | Count, order, and each spec against `TOOL_TABLE`. |
| `test_codex_host_tools.py:190` | `_valid_arguments(handle)[name]` | Every tool in `TOOL_NAMES` needs a valid-argument row and a `StubCodexHost` method. |
| `test_codex_host_helper_tools.py:33,125-133` | `NEW_ROWS = TOOL_TABLE[15:]`, `len(tools) == 26`, `VALID_ARGUMENTS` (`:43`) | Rows appended to `TOOL_TABLE` fall into `NEW_ROWS`. |
| `test_codex_host_tool_hardening.py:38-48,50-65,127-128` | `NO_HANDLE_ARGUMENTS`, `FORBIDDEN_PARAMETERS`, `len(tools) == 26` | No tool offers a forbidden parameter. |
| `test_codex_host_records.py:37-70,535-539` | `EXPECTED_ENUMS` | Exact `{member: value}` dicts for 13 enums. `CodexHostOperation` = `OPEN_HOST`, `VALIDATE_SPAWN_REQUEST`, one per `TOOL_NAMES`, `DELETE_CODEX_THREAD`, `FORGET_CODEX_TURNS`. A new operation needs either a `TOOL_TABLE` row or an explicit entry here. |
| `test_codex_host_records.py:73-87` | `SDK_WIRE_SOURCES` | Enum values against the SDK's generated enums. A new wire enum may join. |
| `test_codex_host_records.py:432-440` | `NEW_FAILURE_CODES` | The 19 codes sit right after `CODEX_RUN_OPTION_UNSUPPORTED`. |
| `test_codex_host_records.py:443-449` | `CLASSIFICATION_ROWS`, `NEXT_STEPS` | `dict(CODEX_NEXT_STEPS) == NEXT_STEPS`, an exact table. |
| `test_codex_host_error_details.py:69` | `NEXT_STEPS` | `set(CODEX_HOST_LIKELY_CAUSES) == set(NEXT_STEPS)`. |
| `test_codex_host_helper_surface.py:245-251` | `HELPER_METHODS` | `CodexHostOperation` members **after `START_CODEX_REVIEW`** are exactly the 12 helper methods. Appending a member at the end breaks it; `FORGET_CODEX_TURNS` was inserted before `LAUNCH_CODEX_SUBAGENTS` instead (`enums/codex.py:286`). |
| `test_codex_host_helper_surface.py:253-266` | literal | `FailureCode` between `CODEX_TURN_TIMED_OUT` and `INPUT_EMPTY` is exactly the 4 helper codes. |
| `test_codex_host_helper_surface.py:272-288` | `NEW_CONSTANTS`, `ENUM_CONSTANTS` | The **tail** of `vidbyte.lib.constants.codex.__all__` equals these names. |
| `test_codex_host_helper_surface.py:301-306` | `HELPER_METHODS` | The 12 public host functions directly after `start_codex_review` (by `vars(CodexHost)` order, `inspect.isfunction`). |
| `test_codex_host_helper_surface.py:108-122,308-317` | `HOST_SIGNATURES` | Signatures of the 12 helper methods. Each must be a coroutine function with only POSITIONAL_OR_KEYWORD params. |
| `test_codex_host_helper_lifecycle.py:124` | `HELPER_METHODS` | The snippet's call order. |
| `test_codex_host_inputs.py:136` | `VALID_RECORDS` | `set(VALID_RECORDS) == set(codex_host_inputs.__all__)`. |
| `test_codex_host_inputs.py:212-217` | boundary `rows` | Every public `CodexHost` coroutine function with an argument has a row. The set is computed with `inspect.iscoroutinefunction`, which is **False for an `async def … yield` generator** (verified in this session). |
| `test_codex_host_hardening_contract.py:56-88,516-531` | `NEW_CONSTANTS` | Values in `constants/codex_host.py`, plus `codex_host.__all__ == sorted(...)`. |
| `test_codex_host_hardening_contract.py:533-547` | `FORK_ROW_BEFORE` | `CODEX_HOST_REJECTED_FIELDS[START_CODEX_REVIEW]` == every `CodexSpawnRequest` field except `timeout_seconds` and `max_output_tokens`. The fork row's tail after `FORK_ROW_BEFORE` is **exactly** `{turn_service_tier, network_access, writable_roots}`. A new `CodexSpawnRequest` field changes the review row, and adding it to the fork row breaks the set check. |
| `test_codex_host_hardening_contract.py:549-566` | AST scan | C021 twin over all of `native/`. |
| `test_codex_host_hardening_contract.py:568-583` | literal | `turn_events.py` and `reviews.py` export exactly one class and import no SDK at module level. |
| `test_codex_host_hardening_records.py:430` | `GOAL_REJECTED_FIELDS` | `("turn", "output_schema", "disabled_plugin_ids", "turn_service_tier", "network_access", "writable_roots")`. |
| `test_codex_host_sdk_contract.py:22-48,91-98` | `CALL_LIST` | Every `CodexClient` method the host calls, with its params. A new typed call needs a row. `thread_archive`, `thread_unarchive`, `thread_goal_clear`, `pause_goal` and `thread_goal_set` are not there today. |
| `test_codex_host_sdk_contract.py:56-69,166-173` | `HARDENING_WIRE_FIELDS` | Each generated params field the host sends through a model. |
| `test_codex_host_sdk_contract.py:175-183` | literal | `ThreadForkParams` lacks `beforeTurnId` and `deferGoalContinuation`. This is the template for proving a post-validation field is missing. |
| `test_codex_host_packaging.py:108-110,203-215` | `REPO_MAP_SECTION`, `README_BULLET` | Verbatim texts of `REPO_MAP.md` and `vidbyte/harnesses/README.md`. |
| `test_harness_threads_surface.py:176-195` | `NEW_FAILURE_CODES` (harness) | The `FailureCode` tail after `RULE_EVALUATION_FAILED` is exactly the 28 harness codes. |

### 3.5 Commands

The commands are in §1. The README says to run the area with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host` (`FEATURE.md:195`).

---

## 4. Notes for the spec author

### 4.1 Per-function protocol table (briefing A)

**Abbreviations used in the table:**
- **EXP** means the method is absent from `schema-stable/ClientRequest.json`, so it needs `experimental_api`.
- **stable** means it is present there.
- `m:N` is the line in `scratchpad/codex-research/methods.txt`, where `X` marks experimental.
- "SDK typed" is a `CodexClient` method (`openai_codex/client.py`); "models" are `openai_codex/generated/v2_all.py` classes.
- `*` marks a required field.

Every notification below appears in both the stable and the experimental schema; `m:186` reports "85 exp, 85 stable".

**P0**

| Function | Method(s) | Stability | SDK 0.163.0 | Params → response | Notifications | Existing host coverage |
|---|---|---|---|---|---|---|
| `update_codex_thread_settings` | `thread/settings/update` | EXP (m:34) | **No typed method; `ThreadSettingsUpdateParams` and `ThreadSettingsUpdateResponse` missing.** | `{threadId*, model, effort, summary, serviceTier, cwd, approvalPolicy, approvalsReviewer, sandboxPolicy, permissions, collaborationMode, disabledPluginIds, personality, multiAgentMode}` → `{}`. `serviceTier`: "`null` clears; omission leaves it unchanged". `permissions`: "Cannot be combined with `sandboxPolicy`". | `thread/settings/updated {threadId, threadSettings: ThreadSettings}` (SDK model exists; `ThreadSettings` lacks the exp-only `multiAgentMode`). | None. The notification has no turnId, so the liveness monitor discards it (`connection.py:540-548`). |
| `list_codex_collaboration_modes` | `collaborationMode/list` | EXP (m:127) | No typed method; Params and Response **missing**; `CollaborationModeMask` exists. | `{}` → `{data: [CollaborationModeMask{name*, mode, model, reasoning_effort}]}` (snake_case wire keys). | — | None. |
| `run_codex_plan` | `turn/start` with `collaborationMode {mode: "plan", settings{model*, reasoning_effort, developer_instructions}}` (exp-only **field** on a stable method) | method stable; field EXP | `turn_start` typed (`client.py:650`). **`TurnStartParams.model_validate` drops `collaborationMode`** (verified). | as §2.3. Output is a `plan` item `{id, text, type}`. | `item/plan/delta` (`PlanDeltaNotification`), `turn/plan/updated` (`TurnPlanUpdatedNotification`), plus the usual turn notes. Questions arrive as the `item/tool/requestUserInput` server request. | `wire.py:256-281`; injection pattern `wire.py:207-209,249-253`; router default answer `codex_host.py:82-90`. |
| `collaboration_mode` on turn settings | same field | EXP field | as above | — | — | `CodexTurnSettings` (`lib/dataclasses/codex.py:247-273`, shared with `CodexHarnessAgent` via `config.py:185-206`); `CodexSpawnRequest` (`codex_host.py:132-273`). |
| `stream_codex_turn` | no method; consumes per-turn notifications | n/a | `TurnHandle.stream` (`api.py:822`) and `AsyncTurnHandle.stream` (`api.py:879`) over the private `_subscribe_turn_notifications` (`client.py:409`). The public low-level API has one consumer per turn. | — | `item/started`, `item/completed`, `item/agentMessage/delta`, `item/reasoning/textDelta`, `item/reasoning/summaryTextDelta`, `item/reasoning/summaryPartAdded`, `item/plan/delta`, `item/commandExecution/outputDelta`, `turn/plan/updated`, `turn/diff/updated`, `thread/tokenUsage/updated`, `turn/completed` (m:187-271). | The watcher already receives all of them (`turns.py:304-328`). `observe` keeps 3 kinds (`turns.py:101-117`). |
| `wait_codex_turns` | none (local) | n/a | — | — | — | Per-turn `ended` future (`turns.py:94`); `wait_codex_turn` (`host.py:442-463`); tool cap of 240 s (`live.py:71-78`). |
| `list_codex_mcp_servers` | `mcpServerStatus/list` | stable (m:134) | No typed method. Models **exist**: `ListMcpServerStatusParams` (`cursor, detail, limit, server_name, thread_id`), `ListMcpServerStatusResponse`, `McpServerStatus`. A raw call with `"ListMcpServerStatusResponse"` resolves. | `{threadId, serverName, detail: full\|toolsAndAuthOnly, cursor, limit}` → `{data: [McpServerStatus{name*, authStatus*, tools* (object), resources*, resourceTemplates*, httpOrigin, pluginId, runtimeStatus, serverCapabilities, serverInfo, toolsError}], nextCursor}`. | `mcpServer/startupStatus/updated {name, status: starting\|ready\|failed\|cancelled, error, failureReason, threadId}`; no turnId, so it is discarded today. | None. |

**P1**

| Function | Method(s) | Stability | SDK 0.163.0 | Params → response | Notifications | Existing host coverage |
|---|---|---|---|---|---|---|
| `update_codex_turn_settings` | `turn/settings/update` | EXP (m:101) | None; Params, Response and `TurnSettingsUpdateStatus` missing. | `{threadId*, turnId*, model, effort, summary, serviceTier, approvalsReviewer}` → `{status*: "applied"\|"targetUnavailable"}`. "Unsupported fields are rejected rather than silently ignored." | unverified: none found specific to it. | `CodexTurnRegistry.get` / `_owned` know live turns (`turns.py:382`, `host.py:741`). |
| `set_codex_thread_memory_mode` | `thread/memoryMode/set` | EXP (m:35) | Params and Response missing; enum `ThreadMemoryMode` exists (`enabled`, `disabled`). | `{threadId*, mode*}` → `{}`. | — | None. |
| `get_codex_memory_status` | `memory/status` | EXP (m:36) | Missing. | `{minConsolidatedThreads: uint32 \| null}` ("Defaults to 20; supported range is 1..=4096"; the schema minimum is 0) → `{v2ConsolidatedThreads*: int, v2Ready*: bool}`. | — | None. |
| `reset_codex_memories` | `memory/reset` | EXP (m:37) | Missing. | params type `null` (ClientRequest entry has no `params`) → `MemoryResetResponse {}`. | — | None. Never a tool (request.md:103,282). |
| `start_codex_side_chat` | `thread/fork {ephemeral: true, developerInstructions: <existing>\n\n<SIDE>}` → `thread/inject_items [boundary item]` → `turn/start` | all stable (m:11, m:67, m:100) | `thread_fork` typed; `ThreadForkParams` has `ephemeral` and `developer_instructions`. `ThreadInjectItemsParams` and `ThreadInjectItemsResponse` exist, but there is **no typed inject method**. | inject: `{threadId*, items*: [raw Responses API items]}` → `{}`. | the fork's and the turn's | `fork_codex_thread` → `CodexThreadHelpers.fork` (`thread_helpers.py:203-240`), `wire.thread_fork` (`wire.py:224-254`). TUI source: `codex-src/codex-rs/tui/src/app/side.rs:44` (`SIDE_DEVELOPER_INSTRUCTIONS`), `:609-611` (concatenation), `:637` (`ephemeral = true`), `:780` (`thread_inject_items`). |
| `create_codex_worktree` | **no app-server method** | n/a | — | — | — | None. unverified: the managed-worktree default root. Only `codex-src/codex-rs/tui/` was cloned, so the `codex_worktree` crate is absent. The nearest is the TUI's `managed_worktree_creation.rs`, plus `cwd` on `thread/start`. |
| goal pause / resume / edit | `thread/goal/set` | stable (m:19) | Typed `thread_goal_set(thread_id, *, objective, status)` (`client.py:549`) has no `tokenBudget` and no `origin`; `pause_goal` (`client.py:568`). Models exist. | `{threadId*, objective, status: ThreadGoalStatus, tokenBudget, origin: "user"\|"automatic"}` → `{goal: ThreadGoal}`. | `thread/goal/updated {threadId, goal, turnId?}`. While a goal operation is registered, these go to its state (`_message_router.py:298-307`). | Raw `thread/goal/set` is in `RAW_RESPONSE_MODELS` and `SPENDING_RAW_METHODS` (`codex_host.py:46-59`). Goal reads: `_stored_goal` (raw `thread/goal/get`, `thread_helpers.py:304`) and `get_codex_goal`. Goal runs: `CodexGoalTurn` / `CodexGoalFinishRule` (`turns.py:217-279`). |
| goal clear | `thread/goal/clear` | stable (m:21) | Typed `thread_goal_clear(thread_id)` (`client.py:541`) has no `origin`. | `{threadId*, origin}` → `{cleared*: bool}`. | `thread/goal/cleared {threadId}`. | The fake answers it (`helper_fakes:168-172`). It is not in `CALL_LIST`. |
| `archive_codex_thread` / `unarchive_codex_thread` | `thread/archive`, `thread/unarchive` | stable (m:12, m:39) | Typed `thread_archive` (`client.py:513`), `thread_unarchive` (`client.py:520`). | `{threadId*}` → `{}`; unarchive → `{thread*: Thread}`. | `thread/archived {threadId}`, `thread/unarchived {threadId}`. | Only listing with `archived` (`wire.py:323`). |
| `revert_codex_thread` | `thread/revert` | stable (m:46) | No typed method; models exist. | `{threadId*, beforeTurnId*}` → `{thread*, itemsBackwardsCursor, turnsBackwardsCursor}`. | `thread/reverted {threadId}`. | None. Never a tool (request.md:103). |
| `rename_codex_thread` | `thread/name/set` | stable (m:17) | Typed `thread_set_name` (`client.py:527`); already in `CALL_LIST` and `RETRIED_METHODS`. | `{threadId*, name*}` → `{}`. | `thread/name/updated {threadId, threadName}`. | Used by spawn and fork through `request.name` (`host.py:773-792`). |
| `inject_codex_items` | `thread/inject_items` | stable (m:67) | No typed method; models exist. | as above. | — | None. |
| `queue_codex_message` + `thread/queue/*` | `thread/queue/add`, `/list`, `/start` (and `/update`, `/delete`, `/reorder`) | EXP (m:22-27) | Params and Responses missing; `QueuedSubmission` exists (`client_user_message_id, id, input`). | add `{threadId*, clientUserMessageId*, input*: [UserInput]}` → `{queuedSubmission*}`; list `{threadId*, cursor, limit}` → `{data, nextCursor}`; start `{threadId*, queuedSubmissionId}` → `{turn*: Turn}` (starts a turn). | `thread/queue/changed {threadId}`. | None. |
| `list_codex_background_terminals` / `clean_codex_background_terminals` | `thread/backgroundTerminals/list`, `/clean` | EXP (m:44, m:43) | All missing, including `ThreadBackgroundTerminal`. | list `{threadId*, cursor, limit}` → `{data: [ThreadBackgroundTerminal{command*, cwd*, itemId*, processId*, cpuPercent, osPid, rssKb}], nextCursor}`; clean `{threadId*}` → `{}`. | — | None. |
| `search_codex_thread_content` | `thread/search` | EXP (m:59) | Params and Response missing; `ThreadSearchResult` exists. | `{searchTerm*, archived, cursor, limit, sortKey: created_at\|updated_at\|recency_at, sortDirection, sourceKinds}` → `{data: [ThreadSearchResult{snippet, thread}], nextCursor, backwardsCursor}`. Account-wide; no `threadId`. Nearest per-thread method: `thread/searchOccurrences` (EXP, m:60, `{threadId*, searchTerm*, cursor, limit}`). | — | `search_codex_threads` uses `thread/list searchTerm`, title only (`descriptions.py:31`). |
| `list_codex_child_threads` | `thread/list` with `parentThreadId` / `ancestorThreadId` | method stable; **both fields exp-only** in the schema | **SDK `ThreadListParams` lacks both** (verified; `model_validate({"parentThreadId": …})` drops it). `wire.thread_list` builds a plain dict (`wire.py:307-331`), and `client.thread_list` passes dicts through (`client.py:493-496`). | — | — | `CodexThreadHelpers.list_threads` / `_list_page` (`thread_helpers.py:91`), `CodexThreadSummary.parent_thread_id`. |

### 4.2 Contradictions found

1. **Thread-list parent filters.** Slice-1's code map, `docs/spec/codex-host-hardening/context/code-map.md:131`, says "0.163.0 `ThreadListParams` has `parentThreadId` and `ancestorThreadId`". That is true of the app-server schema, where both are exp-only fields. It is **false of the SDK model**, `openai_codex 0.163.0 v2_all.ThreadListParams`, whose fields are `archived, cursor, cwd, excluded_thread_ids, limit, model_providers, originators, search_term, section_id, sort_direction, sort_key, source_kinds, use_state_db_only`.
2. **Queue scope.** request.md:287 lists "`queue_codex_message` and the `thread/queue/*` methods" under P1. The gap report's proposal names only `add|list|start` (`codex-gap-report.md:152,334`), and its matrix ranks `update`, `delete` and `reorder` as P2 (`codex-gap-report.md:469-471`; same rows in scratchpad `codex-research/coverage-matrix.md:25-27`). The briefing names `queue_codex_message` and `thread/queue/*`.
3. **Settings fields.** The gap report's field list for `thread/settings/update` (`codex-gap-report.md:271`) omits `personality` and `multiAgentMode`, which the schema has.
4. **The SDK's `extra` setting.** The gap report says the SDK models use `extra="ignore"` (`codex-gap-report.md:24`). Their `model_config` sets no `extra`, only `{'populate_by_name': True}`, and pydantic's default ignore gives the same dropping. The effect is as claimed.
5. **Line drift.** The gap report cites `PR:wire.py:203-205` for the `dynamicTools` injection (`codex-gap-report.md:282`). It is now `wire.py:207-209`.
6. **Stale counts in headers.** `vidbyte/tools/builtins/codex/__init__.py:3` and `vidbyte/tools/toolsets/codex.py:3,5` say "one per CodexHost function except delete_codex_thread", but `forget_codex_turns` has no tool either. `codex_host_support.py:6` says the stub answers "twenty-seven host methods".
7. **Fake version.** `codex_host_fakes.py:3,33` describes and reports app-server 0.162.1, while the SDK pin and the CLI are 0.163.
8. **Names in request.md.** request.md:145 calls the tables `RAW_RESPONSES` and `SPENDING_RAW_METHODS`. The code names are `CODEX_HOST_RAW_RESPONSE_MODELS` and `CODEX_HOST_SPENDING_RAW_METHODS` (`codex_host.py:46,59`).
9. **Lint pass line.** vidbyte-gates.md (`~/.claude/skills/spec-pipeline/references/vidbyte-gates.md:28`) says the last lint line reads `AGENT-LINT: PASS`. This repo prints `SDK-LINT: PASS` (`lint/core/report.py:58`).
10. **Full gate.** vidbyte-gates.md:19 gives the full gate as `--stage source` then a bare `python scripts/run_ci.py`. From a worktree that tests the canonical checkout, and the field guide (`local-ci-verification.md:3-8`) and the briefing require `PYTHONPATH=$(pwd)` for source and none for package.

### 4.3 Gaps and constraints the spec must face

These are facts only, with no proposals.

1. **The raw path cannot carry most experimental methods as written.** `CodexConnection.raw` resolves `getattr(v2_all, CODEX_HOST_RAW_RESPONSE_MODELS[method])` (`connection.py:372`), and `request_with_retry_on_overload` requires `response_model` (`client.py:731`). The 0.163.0 SDK has **no response model** for any of these: `thread/settings/update`, `turn/settings/update`, `collaborationMode/list`, `thread/memoryMode/set`, `memory/status`, `memory/reset`, `thread/queue/add|list|start`, `thread/backgroundTerminals/list|clean`, `thread/search`.
2. **Size ceilings.**
   - `host.py` is 937 lines and `wire.py` 797. AGENTS.md §3 says to split before adding.
   - `lib/dataclasses/codex_host.py` is 873 lines.
   - `lib/dataclasses/codex.py` is 1,205, already over, with slice-1 D-17 "no growth".
   - `codex_host_fakes.py` is 902 lines and `codex_host_support.py` 828.
   - Today `codex_host.py` is the only output-record domain module beside `codex_host_inputs.py`.
3. **`collaboration_mode` placement.** `CodexTurnSettings` is in the over-limit `codex.py` and feeds `CodexHarnessAgent` through the shared `turn_kwargs`. Slice 1 put its turn-only fields (`turn_service_tier`, `network_access`, `writable_roots`) on `CodexSpawnRequest` instead. Any new `CodexSpawnRequest` field also touches `CODEX_HOST_REJECTED_FIELDS`, the review row pin, and the fork row pin (§3.4).
4. **`CollaborationMode.settings.model` is required on the wire**, while `CollaborationModeMask.model` may be null. Whether omitting `developer_instructions` equals sending `null` ("use the built-in instructions") is **unverified**. Every params dump in `wire.py` uses `exclude_none=True` (for example `:281`), so a JSON `null` cannot survive that path. The same applies to `serviceTier: null` ("clears") on `thread/settings/update`.
5. **Event streaming.**
   - The only SDK multi-consumer handle is private (`_subscribe_turn_notifications`, `client.py:409`). The public default consumer is already taken by the host watcher.
   - Per-turn and global queues are unbounded (§2.2).
   - `observe` drops every delta.
   - A model-facing tool returns one JSON string (`_base.py:120-141`), so an iterator has no direct tool shape.
6. **Turn-less notifications are discarded.** `thread/settings/updated`, `mcpServer/startupStatus/updated`, `thread/archived`, `thread/unarchived`, `thread/reverted`, `thread/name/updated`, `thread/goal/cleared` (outside a goal operation) and `thread/queue/changed` all land on the global queue, which `_monitor` discards (`connection.py:540-548`).
7. **No free failure-code slot.** Records:432-440 pins 19 codes after `CODEX_RUN_OPTION_UNSUPPORTED`. helper_surface:253-266 pins exactly 4 codes between `CODEX_TURN_TIMED_OUT` and `INPUT_EMPTY`. harness_threads:176-184 pins the tail after `RULE_EVALUATION_FAILED`. A new code also needs `NEXT_STEPS`, `CODEX_HOST_LIKELY_CAUSES` and `CLASSIFICATION_ROWS` entries.
8. **No free operation slot.** `CodexHostOperation` members after `START_CODEX_REVIEW` are pinned to the 12 helpers (helper_surface:245-251), and `EXPECTED_ENUMS` pins the full member set (records:63-69).
9. **Constants placement.** `constants/codex.py.__all__`'s tail is pinned (helper_surface:286-288). `constants/codex_host.py.__all__` must stay sorted (hardening_contract:519-520).
10. **Fake coverage.** The fake answers none of the slice-2 methods (§3.2).
11. **Spending and goal behaviour of new methods.**
    - `thread/queue/start` returns a started `turn`.
    - `thread/goal/set` with `status: active` may start paid turns. The fake starts a turn only when an `objective` is sent (`helper_fakes:188-191`); real behaviour for a status-only resume is **unverified**.
    - `client.turn_start` refuses a thread that has a goal operation running (`client.py:666-670`).
12. **Side chat.** An ephemeral fork has no stored turns. The fake's `thread/turns/list` gives `[]` for ephemeral threads (`helper_fakes:217`), and the TUI says side threads cannot be renamed (`side.rs:19`). Goal runs and skill read-backs need stored threads (`codex_host_inputs` skill rule; `EPHEMERAL_SKILL_MESSAGE`).
13. **Async generators escape the boundary pin.** A host method written as an `async def … yield` generator is not seen by the input-boundary pin (`test_codex_host_inputs.py:216`), because that pin uses `iscoroutinefunction`. The helper order pin uses `inspect.isfunction`, which does see it.
14. **Branch scope.** A change outside the four excluded tools paths fails `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` locally. `vidbyte/tools/base.py` is one example.

### 4.4 Unverified

- **unverified:** the managed-worktree default root path. The `codex_worktree` crate is not in `codex-src/` (only `codex-rs/tui/`); the gap report also marks it UNVERIFIED (`codex-gap-report.md:315,413`).
- **unverified:** any notification specific to `turn/settings/update`.
- **unverified:** whether `thread/goal/set {status: "active"}` with no objective starts a turn on the real binary.
- **unverified:** whether an omitted `Settings.developer_instructions` behaves as `null`.
- **unverified:** request.md's open question on whether `thread.config` applies on resume and whether `review_model` is read from thread config (request.md:150). It was not checked against the binary in this stage.
- **unverified:** the effect of `mcpServerStatus/list` without `threadId`. The schema field has no description.
