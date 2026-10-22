# Code map: codex-host-thread-helpers (S0 scout)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-thread-helpers`, branch `feat/codex-host`, HEAD `c181be65` (merge of `66558ee9` = PR #1055 head and `72a4ade1` = origin/main, which contains #1036). Scouted 2026-10-15. Every path, line number and quote below was opened in this session. Anything not seen in a file is marked "unverified". Paths are relative to the worktree. The SDK lives at `<venv>/Lib/site-packages/openai_codex/`, where `<venv>` = `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers`. The schema copy is at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/codex-schema/` (written `<schema>/` below).

## 1. Rules, commands and conventions that bind this change

### 1.1 AGENTS.md (81 lines; `CLAUDE.md` is just `@AGENTS.md`)

- **Repository Map:** read `REPO_MAP.md` before creating or moving a file. Each folder `README.md` has to be read to the end before changing the folder. A009 caps a folder README at 40,000 characters.
- **Two rules for every change:**
  - "Do not grep, glob, or read files under `docs/` as part of ordinary work."
  - "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- **Principle 1, "Keep Call Chains One Level Deep":** "a function may call another of its own functions, but that second function should not call a third". Avoid nested functions.
- **Principle 2, "Narrate Main Functions in Plain English":** comments run through the main function so that a reader can follow the feature from the comments alone.
- **Principle 3, "Build in Layers of Small, Single-Purpose Classes":** `vidbyte/lib/` is the bottom layer. "Keep files well below 1,000 lines; when a file heads toward four digits, split it into smaller modules along subsystem lines before adding more."
- **Principle 4, "Use Validated Dataclasses for Core Inputs and Outputs":**
  - Use `@dataclass(frozen=True, slots=True)`, validated in `__post_init__`.
  - "type any field whose value comes from a small, closed set as an enum."
- **Principle 5, "Write Shared Logic Once, as a Canonical Helper in `lib/`":** pagination is named as an example of such a job.
- **Placement Rules**, which the `AGENTS.md placement` workflow enforces on every PR:
  - "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`". Never create `types.py`, `records.py`, `models.py` or `schemas.py`.
  - "Every new enum ... is defined in `vidbyte/lib/enums/<domain>.py`, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
  - "Existing code": older modules are not precedent. "Moving it to `vidbyte/lib/` is a change of its own and belongs in its own pull request."
- **Not stated in AGENTS.md:**
  - No install, lint or test command other than the full gate.
  - No PR or commit conventions.
  - Those come from the sources in 1.2.

### 1.2 Commands (with their source)

| Purpose | Command | Source |
|---|---|---|
| Install (this worktree only) | already done: the isolated venv `<venv>/Scripts/python` holds an editable install with `.[dev,codex]`. Never `pip install -e` into the global Python. | request.md §C "Constraints" |
| Full gate | `python scripts/run_ci.py` | AGENTS.md "Repository Map" |
| Gate from a worktree | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no `PYTHONPATH` | field guide `local-ci-verification.md` |
| Lint | `python lint/run.py` (`--rule <ID>`, `--all`). The final line must be `SDK-LINT: PASS`. | workspace facts `vidbyte-gates.md`; S0-merge-main.md |
| One test file | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_<topic>.py` | spec §13; header `TESTS:` lines |
| Area | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host` (needs the `codex` extra) | `tests/features/codex_host/FEATURE.md:104` |
| CI view of the area | the same command with `sys.modules['openai_codex'] = None`; PR body result: `36 passed, 80 skipped` | `docs/spec/codex-host/pr-body.md` Verification |
| All tests | `PYTHONPATH=$(pwd) python -m pytest -q` | spec §13 |
| Public API contract | `python scripts/generate-sdk-public-api.py --check` | pr-body.md Verification |
| CI (dispatch only) | `gh workflow run ci.yml --ref feat/codex-host` and `gh workflow run static-policy.yml --ref feat/codex-host` | request.md §C |

PR and commit conventions come from request.md §C, not AGENTS.md:
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The PR body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Push fast-forward only. PR #1055 stays draft.

### 1.3 Field-guide quick checks that bind this change (quoted)

- **comment-format.md:** "Wrap every comment line at 72 columns, counting the indent". Check: "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched. A002 still passes, because the `@intent` line has to stay within 20 lines of the `def`."
- **model-facing-tool-contracts.md:**
  - "give the tool and every parameter a consistent 4–5 sentence general description, and omit concrete examples from model-facing prose."
  - Centralize categorical vocabularies: "Define the canonical values as `str, Enum` classes under `vidbyte/lib/enums`".
- **provider-api-contracts.md:**
  - "Wrap config resolution, send, parse, and normalize in one `try`."
  - "Never catch `BaseException`, so cancellation propagates."
- **blocking-lint-invariants.md:**
  - A003: a new class in `vidbyte/lib/errors/base.py` needs the literal 8-field `DIAGNOSTIC_FIELDS`. Check: "`python lint/run.py --rule A003`".
  - S060/S039: "`python lint/run.py --rule S060` and `--rule S039` stay at their baselines". There is no `dict[str, Any]` encoder on a lib record, and `TypedDict` is banned.
  - S012: "Give it a descriptive name ... keep `request` for real transport calls". S012's baseline is 0.
  - A006: check with `python lint/run.py --rule A006`.
- **local-ci-verification.md:**
  - Run the source stage with `PYTHONPATH`, and the package stage without it.
  - Semgrep: "`git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`. Version must be `semgrep==1.170.1`."
  - S051: "`python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` and filter the output to your paths".
- **class-bound-helpers.md:**
  - "The module's public `__all__` exports the class (and constants), not a list of peer free functions for the same concern."
  - "compare emitted argument names against the installed SDK signatures."
- **strict-config-dataclasses.md:** "Every new bound either references a vendor constant or is at least as large as the broad cap in the same constants file." Also: "each validation comparison should reference the feature's constants module."

### 1.4 Per-file conventions observed in the touched files

- **The A001 header.** Every `.py` file opens with a docstring of seven fields: `FILE`, `PURPOSE`, `ROLE IN CODEBASE`, `ARCHITECTURE NOTE`, `COMMON MODIFICATION PATTERNS`, `KNOWN EDGE CASES`, `RELATED DOCS`, `TESTS`, plus `FUNCTION INVENTORY` and `WHAT NOT TO DO` where present. The `COMMON MODIFICATION PATTERNS` line in each codex file is the binding extension recipe; each one is quoted in §2.
- **No implicit string concatenation.** Rule S062 also scans the tests.
- **Narrated public methods.** Every public host method opens with a `# @intent <name>` block when it is a boundary function (A002).

## 2. Files this change will touch

### 2.1 Host layer: `vidbyte/harnesses/native/codex/` (every file here is excluded from #1036's static policy)

- **`vidbyte/harnesses/native/codex/host.py`** (771 lines)
  - **Today:** `CodexHost`, an async context manager over one `codex app-server`.
    - 15 public methods at lines 219-491. Private helpers start at line 493 (`_guard`), and include `_open_thread` 533, `_start_turn` 551, `_start_goal` 569-602 and `_accept` 604. Module messages are at 94-102, and `REVIEW_REQUEST = CodexSpawnRequest()` is at 105.
    - It imports `Tools` from `vidbyte.tools.catalog` (line 71).
    - `_open()` (146) lazily imports connection, wire and turns.
    - Methods are plain async methods on the class. There is no mixin and no delegation module: the module functions in `oneshot.py` each open a host and call the same method.
  - **Change:** host the new public operations. The request (§C "Constraints") says new functions go in new modules rather than growing host.py past ~900 lines.
  - **Pattern** (header line 6): "A new operation is one public method: guard, field rules, preflight, the calls through CodexConnection, then a record from CodexResponseTranslator." `list_codex_threads` (335-353) is the read pattern:
    ```python
    operation = CodexHostOperation.LIST_CODEX_THREADS
    self._guard(operation, talks=True)
    connection = self._connection
    listing = self._params.thread_list(cwd, search, archived, source_kinds, sort, sort_direction, cursor)
    page = await connection.call(operation, CODEX_THREAD_LIST_METHOD, connection.client.thread_list, listing)
    return self._responses.page(page)
    ```
  - **`_guard(operation, *, talks)`** (493-502):
    - Raises `ConfigurationError` when the host is not open or is on another loop.
    - Raises `codex.process_exited` when `talks` and the host is closing or dead.
- **`vidbyte/harnesses/native/codex/connection.py`** (361 lines)
  - **Today:** `CodexConnection`:
    - `call(operation, method, function, *args, thread_id="", cleanup=False)` (166) runs on the host executor, bounded by `CODEX_HOST_REQUEST_TIMEOUT_SECONDS`. Every exception goes through `CodexErrorMapper.from_exception(...) from None`.
    - `raw(method, params)` (190) builds a `request_with_retry_on_overload` partial with `response_model=RAW_RESPONSES[method]`. Methods in `SPENDING_RAW_METHODS` get `max_attempts=CODEX_HOST_SINGLE_ATTEMPT`.
    - `start()` (214) is the shielded spending start. `starting(thread_id)` is at 244.
  - **`RAW_RESPONSES`** (67-73) maps exactly five methods: rate limits, sandbox readiness, `model/list`, `review/start` and `thread/goal/set`. **`SPENDING_RAW_METHODS`** (76) holds `{review/start, thread/goal/set}`.
  - **Change:** any new method without a typed `CodexClient` call gets a `RAW_RESPONSES` row. These are `thread/delete`, `thread/goal/get`, `skills/list` and `thread/turns/list`; see §4.a.
  - **Pattern** (header line 6): "A new app-server call goes through call() with a typed CodexClient method, or through raw() with its generated response model when openai-codex has no typed method; a raw call that spends usage is added to SPENDING_RAW_METHODS, so it is sent once (D-2)."
- **`vidbyte/harnesses/native/codex/wire.py`** (609 lines)
  - **Today:** `CodexParamsTranslator` (149):
    - `thread_list` (267-287) returns `{"cwd","searchTerm","archived","sourceKinds","sortKey","sortDirection","cursor"}` and drops falsy values. It has **no `limit`**.
    - Also `input_items` (243-250), `review` (290), `goal_budget` (297) and `model_page` (303).
  - **Today:** `CodexResponseTranslator` (363):
    - `thread_info` (457-485): `name=thread.name or ""`, `cwd=thread.cwd.root`, `status=CodexThreadStatus(thread.status.root.type)`, `model=thread.model or ""` and `forked_from_id=thread.forked_from_id or ""`. Turns become `CodexTurnSummary` with `final_answer(turn.items) or ""`.
    - `page` (487-491) sets `next_cursor = response.next_cursor or ""`.
    - Also `fork_point` (493) and `stored_turn` (503). `final_answer(items)` is module-level (134).
  - **Change:** param builders and record translators for the new methods.
  - **Pattern:** one `@staticmethod` per wire shape. The method names its section, and each multi-line comment wraps at 72 columns.
- **`vidbyte/harnesses/native/codex/errors.py`** (179 lines)
  - **Today:** `CodexErrorMapper`:
    - `error(code, message, operation, thread_id="")` (61) uses `next_step=CODEX_NEXT_STEPS[code.value]`, so a code with no next step raises `KeyError`.
    - `from_exception` (68-94):
      - A death or `TransportClosedError` becomes `codex.process_exited`.
      - A `JsonRpcError` goes through `_rpc_code`.
      - A plain `CodexError` becomes `codex.protocol_mismatch`, or `codex.api_error` for the goal-start window.
      - A `ValidationError` becomes `codex.protocol_mismatch`, and a `TimeoutError` becomes `codex.api_error`.
    - `_rpc_code(method, *, malformed, refused)` (97-107):
      - Any `thread/read` error becomes `codex.session_not_found`.
      - A refused `thread/fork` becomes `codex.fork_failed`.
      - A malformed error (`-32602`, `-32601`, `-32700`) becomes `codex.protocol_mismatch`.
      - Anything else becomes `codex.api_error`.
  - **Change:** context overrides for the new methods' JSON-RPC errors, if the spec wants specific codes. Without them, an unknown thread on `thread/delete`, `thread/compact/start` or `thread/goal/get` maps to `codex.api_error` (InvalidRequest, -32600) and never to `session_not_found`.
  - **Pattern:** the `_rpc_code` branch list. Messages quote only `exc.code`/`exc.message`, never `str(exc)`.
- **`vidbyte/harnesses/native/codex/preflight.py`** (186 lines)
  - **Today:** `CodexPreflight`:
    - `run(operation, request, *, check_model=True)` (99) checks `account/read`, rate limits (`ordinary_usage_allowed is False` → `codex.usage_limited`), the Windows sandbox, then models.
    - `require_idle` (162) checks only the local registry and `connection.starting`.
    - `require_thread(operation, thread_id, include_turns=False)` (169) calls `client.thread_read`.
    - `REJECTED_FIELDS` (51-76) and `reject_unusable_fields` (staticmethod).
  - **Change:** none is required. The new read helpers must not call `run()` (decision 5). `require_thread` and `require_idle` are the reusable existence and busy checks.
  - **Pattern:** `require_*` methods that raise `CodexErrorMapper.error(...)`.
- **`vidbyte/harnesses/native/codex/turns.py`** (419 lines)
  - **Today:** `CodexLiveTurn` 70, `CodexGoalTurn` 204, `CodexGoalFinishRule` 222, `CodexTurnWatcher` 268 and `CodexTurnRegistry` 313. The registry has `busy` 326, `reserve` 331, `release` 336, `track` 340, `track_goal` 346 and `usage` 405.
  - **Change:** only if a new function registers a turn, for example a skill turn started through the existing `_start_turn`/`_accept`. Compaction's turn is not registered today (see §4.d).
  - **Pattern:** "A new way a turn can end goes through CodexTurnRegistry.finish" (host.py header).
- **`vidbyte/harnesses/native/codex/oneshot.py`** (115 lines) and **`vidbyte/harnesses/native/codex/__init__.py`** (30 lines)
  - **Today:**
    - `oneshot.py` holds six module functions. Each is `async with CodexHost(settings) as host: return await host.<same>(...)` with a keyword-only `settings`.
    - `__init__` exports `CodexHost` plus the six functions in a list-literal `__all__`.
  - **Change:** only if a new name is also offered as a module function. `__all__` is pinned exactly; see §3.
  - **Pattern** (`__init__` line 6): "A new public name is imported from its own module here and added to __all__ in sorted order after CodexHost."
- **New modules.** request.md §C suggests new modules (for example a threads/skills split) under `vidbyte/harnesses/native/codex/`.
  - **Placement constraint:** `tests/features/harness_threads/test_harness_threads_static_policy.py:27,31` skips only paths whose first part under `native/` is `codex`.
  - Any new subpackage elsewhere under `vidbyte/harnesses/native/` falls under #1036's INV-15 and INV-20 rules:
    - no module-level constants;
    - no literals other than `""`, `0` and `1`;
    - no import of `vidbyte.tools`.

### 2.2 The lib layer

- **`vidbyte/lib/constants/codex.py`** (543 lines)
  - **Today:**
    - `CODEX_FAILURE_CLASSIFICATION` (99-272) has one row per `codex.*` code.
    - Method constants include `CODEX_GOAL_SET_METHOD` 363, `CODEX_THREAD_LIST_METHOD` 451 and `CODEX_THREAD_READ_METHOD` 452.
    - `CODEX_NEXT_STEPS` (420-440).
    - An explicit `__all__` (460-543) in definition order, not sorted.
    - There are **no constants** for `thread/compact/start`, `thread/delete`, `thread/goal/get`, `skills/list` or `thread/turns/list`.
  - **Change:**
    - New method-name constants.
    - Any new bound (a page size, or a cap on paging).
    - Classification rows and next steps for any new code.
  - **Pattern:** spec §12.3 row 4: "Add every new name at the end of `__all__`". `tests/test_codex_failure_recovery.py:190-203` requires a classification row for every `codex.*` FailureCode.
- **`vidbyte/lib/enums/codex.py`** (270 lines)
  - **Today:** these enums are already present:
    - `CodexThreadStatus` (154): NOT_LOADED, IDLE, SYSTEM_ERROR, ACTIVE.
    - `CodexThreadSortKey` (163): PROVIDER_DEFAULT, CREATED_AT, UPDATED_AT, RECENCY_AT, SECTION_POSITION.
    - `CodexSortDirection` (173): PROVIDER_DEFAULT, ASC, DESC.
    - `CodexThreadSourceKind` (181).
    - `CodexGoalStatus` (212): NONE plus the 6 wire values.
    - `CodexInputType`, which includes SKILL.
    - `CodexHostOperation` (224-243), with 17 members: OPEN_HOST, VALIDATE_SPAWN_REQUEST and one per function, with value = function name.
  - **Change:** new `CodexHostOperation` members. Each one is also the tool name, because `ToolSpec(name=OPERATION.value)`. There may also be new enums, for example a skill scope or an items view.
  - **Pattern:** `str, Enum` with one-line docstrings. The `__all__` (246) keeps `CodexFailureClass` first and the rest alphabetical; this order is pinned.
- **`vidbyte/lib/enums/__init__.py`** (315 lines)
  - **Today:** Codex imports at lines 42-63 and `__all__` Codex entries at 197-218. There are 22 `Codex*` names, pinned in order by `ENUMS_CODEX_ORDER`.
  - **Change:** insert any new public enum in sorted position in both lists.
  - **Pattern:** request.md export-list rule: insert only your own entries.
- **`vidbyte/lib/enums/failure.py`** (340 lines)
  - **Today:** `codex.*` codes sit at lines 41-61. `CODEX_RUN_OPTION_UNSUPPORTED` is at 46, the 15 host codes run from `CODEX_NOT_INSTALLED` to `CODEX_TURN_TIMED_OUT` (61), and `INPUT_EMPTY` is at 62. `RULE_EVALUATION_FAILED` is at 159, followed by #1036's 28 GROK_/OPENCODE_/MUSE_ codes.
  - **Change:** any new `codex.*` code.
  - **Placement constraint:**
    - `test_harness_threads_surface.py:176-193` pins the tail after `RULE_EVALUATION_FAILED` to exactly the 28 harness codes, so a new code may not go at the end of the enum.
    - `test_codex_host_records.py:395` pins the 15 host codes as a contiguous slice right after `CODEX_RUN_OPTION_UNSUPPORTED`.
    - So the safe insertion zone is between `CODEX_TURN_TIMED_OUT` and `INPUT_EMPTY` (line 61/62).
- **`vidbyte/lib/dataclasses/codex_host.py`** (511 lines)
  - **Today:** 15 records, including:
    - `CodexGoal` (108): `objective`, `token_budget=None`.
    - `CodexSpawnRequest` (120).
    - `CodexTurnSummary` (367), "without its items".
    - `CodexThreadInfo` (385): thread_id, name, preview, cwd, status, model, model_provider, created_at, updated_at, forked_from_id, ephemeral, turns. It has **no `parent_thread_id`, no `source` and no `recency_at`**.
    - `CodexThreadPage` (417): `threads`, `next_cursor`.
  - Private validators `_reject_small_int` 57, `_reject_bad_seconds` 66, `_reject_non_str` 75, `_reject_optional_count` 82, `_reject_wrong_type` 90 and `_reject_bad_tuple` 100. It also imports `_require_text`, `_optional_text`, `_require_non_negative_int` and `_require_bool` from `codex.py`.
  - `__all__` (495) is an alphabetical list literal of the 15 names, pinned by `RECORD_EXPORTS`.
  - **Change:** any new record (summary, lineage, skill listing, goal state, transcript page).
  - **Pattern** (header line 6): "Add a field with its check in the same record's __post_init__, reusing the codex.py helpers; a new record is added here and to the alphabetical __all__."
- **`vidbyte/lib/dataclasses/codex.py`** (1,205 lines; already over 1,000)
  - **Today:** `CodexSkillInput(name, path)` (450-459) validates that both are non-empty text. `CodexRunInput(items, ...)` (485) accepts `CodexSkillInput` items.
  - **Change: none.** Spec D-26 and NG-12 forbid growing or editing this file; it is reused by import only.
- **`vidbyte/lib/errors/base.py`** (614 lines)
  - **Today:** `CodexAgentError.__init__` takes `next_step` (lines 152, 160-161 per S0-merge-main). `NativeThreadError` is at 559 with the 8-field packet.
  - **Change: none expected.** All codex failures reuse `CodexAgentError`; a new class would trigger A003.

### 2.3 Tool layer (only these four `vidbyte/tools` paths may change: INV-21, `test_harness_threads_surface.py:228`)

- **`vidbyte/tools/builtins/codex/`**
  - **The files:**
    - `_base.py` (223): `CodexToolScope` 47 and `_CodexHostTool(BaseTool)` 104. `_run(name, work)` (112) maps a `CodexAgentError` to an error result with metadata {code, next_step}. The resolvers are `_resolve_text` 133, `_resolve_count` 143, `_resolve_seconds` 153, `_resolve_choice` 163, `_resolve_choices` 174, `_resolve_texts` 185 and `_resolve_schema` 193, plus `_json` 203.
    - `descriptions.py` (62).
    - `threads.py` (335): spawn, continue, fork, list and read.
    - `readiness.py` (97), `live.py` (190) and `delegation.py` (134).
    - `__init__.py` (56): a sorted `__all__` of 15 tools plus `CodexToolScope`.
  - **Change:**
    - One READ or WRITE tool per new function, except delete.
    - One description constant per tool and per parameter.
    - The new classes in `__init__`.
  - **Pattern:** `ListCodexThreadsTool` in `threads.py`:
    ```python
    def spec(self) -> ToolSpec:
        return ToolSpec(name=LIST.value, description=LIST_CODEX_THREADS_DESCRIPTION, permission=ToolPermission.READ, input_schema={"type": "object", "additionalProperties": False, "properties": {...}})
    async def execute(self, call: ToolCall) -> ToolResult:
        return await self._run(LIST.value, self._perform(call))
    ```
  - **Pattern notes in the file headers:**
    - `descriptions.py:6`: "A new parameter adds one constant here and one schema property in its tool; a WRITE tool's description always says it starts or changes paid Codex work."
    - `descriptions.py:7`: constant names avoid words the security lint reads as credentials (`SPAWN_GOAL_BUDGET_DESCRIPTION`).
    - `_base.py:6`: "A new argument type gets one _resolve_ helper here".
- **`vidbyte/tools/builtins/__init__.py`** (358 lines)
  - **Today:** re-exports the 15 tools (import block from line 32). The docstring bullet "- Codex host tools from builtins.codex." is at line 11.
  - **Change:** add the new tool classes in sorted position.
- **`vidbyte/tools/toolsets/codex.py`** (82 lines)
  - **Today:** `CodexHostTools.__init__` builds a `tool_classes` tuple of 15 in function order (60-76). Its comment reads "Hand the fifteen tools to the catalog" (78).
  - **Change:** one line per new tool.
  - **Pattern** (line 6): "A new CodexHost function adds its tool to vidbyte/tools/builtins/codex/ and one line here, at its place in the function order."
- **`vidbyte/tools/toolsets/__init__.py`** (26 lines): no change is expected. `__all__` is pinned to `["CodexHostTools", "CodingAgentTools", "ParadigmMinimalToolset"]`.

### 2.4 Files that must NOT change (pinned or out of scope)

- **`vidbyte/harnesses/native/__init__.py`** (62 lines): SHA-256 is pinned by `NATIVE_INIT_SHA256` (`test_codex_host_packaging.py:26`). Its 17 names are pinned by `test_harness_threads_surface.py` `EXPECTED_EXPORTS`. It re-exports no codex name.
- **`REPO_MAP.md:159-163`** and **`vidbyte/harnesses/README.md:178`:** the exact texts are pinned (`test_codex_host_packaging.py:91-92`, tests at 185-197). Both describe the codex host generically, so no edit is needed; see §4.e.
- **`vidbyte/lib/enums/native_threads.py`:** `NativeHarness` (19-24) is GROK/OPENCODE/MUSE only, and its members are pinned (`test_harness_threads_surface.py:36`).
- **`contracts/sdk-public-api.json`:** no CodexHost name is in it. Spec D-25 says there are no root exports. Root already exports `CodexSkillInput` (line 104) and other older Codex names.
- Any other file under `vidbyte/tools/` or `vidbyte/lib/configs` (INV-21).

## 3. Tests that cover these files

### 3.1 Framework and layout

- **Framework:** pytest 8.3.5 with pytest-asyncio 1.3.0 (spec §13). The pack uses `unittest.TestCase` and `unittest.IsolatedAsyncioTestCase`.
- **SDK gating:** `requires_sdk` (`codex_host_support.py`) skips without openai-codex. CI installs only `.[dev]`, so host tests skip there and must be run locally.
- **Pack layout:** `tests/features/codex_host/` has no `__init__.py` and no `conftest.py`.
- **`README.md` (39 lines):** its "## File Index" must list exactly the tracked children (S020, spec §13). A new test file needs a bullet there and a line in its "Logs".
- **`FEATURE.md` (112 lines):** has a "Test Suite Map".

### 3.2 Pack files (line counts)

- `codex_host_fakes.py` (899): the in-memory app-server.
- `codex_host_support.py` (513): `NEXT_STEPS` 61-81, `NEW_FAILURE_CODES` (83+), `CLASSIFICATION_ROWS`, `TOOL_TABLE` 122-162, `TOOL_NAMES` 163, `HostTestCase`, `assert_codex_error` (289-296) and `StubCodexHost` (420-513).
- The test modules:
  - `test_codex_host_records.py` (510)
  - `test_codex_host_packaging.py` (246)
  - `test_codex_host_bridge.py` (86)
  - `test_codex_host_tools.py` (494)
  - `test_codex_host_lifecycle.py` (366)
  - `test_codex_host_turns.py` (451)
  - `test_codex_host_threads.py` (509)
  - `test_codex_host_review_goals.py` (224)
  - `test_codex_host_failures.py` (257)
  - `test_codex_host_router.py` (79)
  - `test_codex_host_sdk_contract.py` (129)
  - `test_codex_host_review_gaps.py` (440)
- Related outside the pack:
  - `tests/features/harness_threads/test_harness_threads_surface.py` (258) and `test_harness_threads_static_policy.py` (116).
  - `tests/test_codex_failure_recovery.py:190-203`: a classification row for every code.
  - `tests/test_session_failures.py:139+`: the dot rule.

### 3.3 Fake app-server (`codex_host_fakes.py`)

- **Seam.** `client_class(server)` subclasses the real `openai_codex.client.CodexClient` and swaps only the subprocess. Tests patch `vidbyte.harnesses.native.codex.connection.CodexClient` and `shutil.which`.
- **Request log.** `server.requests` is a list of `Request(method, params, request_id, thread_name, thread_daemon)`. Read it with `matching(method, predicate)`, `wait_for`, `methods()` and `count`.
- **Scripted errors.** `server.fail(method, FakeRpcError(code, msg), times=, predicate=)`. Also `hold()`, `before_response()` and `release_all()`.
- **Methods answered.** `_handlers` (449-467) answers exactly these methods:
  - initialize
  - account/read
  - account/rateLimits/read
  - windowsSandbox/readiness
  - model/list
  - thread/start
  - thread/resume
  - thread/fork
  - thread/read
  - thread/list
  - thread/name/set
  - turn/start
  - turn/steer
  - turn/interrupt
  - review/start
  - thread/goal/clear
  - thread/goal/set
- **Methods not answered.** These include `thread/compact/start`, `thread/delete`, `thread/goal/get`, `skills/list`, `thread/turns/list`, `thread/items/list` and `thread/loaded/list`. Each raises `FakeRpcError(-32601, "method not found: ...")`.
- **Fake behaviour that matters for the new helpers:**
  - **Unknown thread.** `thread_or_error` (741-745) raises `-32600 "thread not found: <id>"`.
  - **`_thread_list`** (835-836) ignores every param, returns every thread, and always returns `nextCursor: "cursor-after-page"`. A loop that pages until the cursor is empty never ends on this fake. There is a `repeat_last_cursor` switch (447).
  - **`FakeThread.wire`** (158-181):
    - `createdAt` is BASE_TIME and `updatedAt` is BASE_TIME+60 for every thread.
    - It has no `parentThreadId` and no `recencyAt`.
    - `source` is always `"appServer"`.
    - `status` is `{"type":"active","activeFlags":[]}` when a turn is in progress, else `{"type":"idle"}`. It is never `notLoaded` or `systemError`.
    - It sets `forkedFromId` when forked.
  - **`_turn_start`** (842-851) ignores the `input` items, so a Skill input is accepted but not checked.
  - **`_goal_set`** (882-899) stores `thread.goal` as a dict (createdAt, objective, status, threadId, timeUsedSeconds, tokensUsed, updatedAt, and tokenBudget when sent). It emits `thread/goal/updated`, and a `turn/started` when the objective is active. Switches: `goal_updates`, `goal_starts_turn`, `budget_echo`.
  - **`seed_thread(completed_turns, reviewer, policy, running_turn)`** builds threads.

### 3.4 Pins that a new function or tool changes (later stages must update them; the tests are owned by the test author)

| Pin | Where | What it fixes |
|---|---|---|
| `TOOL_TABLE` / `TOOL_NAMES` | `codex_host_support.py:122-163` | 15 rows of (name, class, permission, params, required), in R3 order |
| `len(tools) == 15` and `tools.names() == TOOL_NAMES` | `test_codex_host_tools.py:141` | the toolset size and order |
| subprocess probe `(15, "check_codex_ready")` | `test_codex_host_packaging.py:165` | the tool count |
| §4 snippet prints `"15 check_codex_ready"` | `test_codex_host_lifecycle.py:101` | the tool count |
| `CodexHostOperation` members == OPEN_HOST, VALIDATE_SPAWN_REQUEST plus `{name.upper(): name for name in TOOL_NAMES}` | `test_codex_host_records.py:61` | every operation is assumed to be a tool, so **a delete operation without a tool breaks this derivation** |
| `NATIVE_CODEX_EXPORTS` (7 names) | `test_codex_host_packaging.py:28`, asserted at 208 | `vidbyte.harnesses.native.codex.__all__` |
| `RECORD_EXPORTS` (15 names) | `test_codex_host_packaging.py:30+`, asserted at 209 | `codex_host.__all__` |
| `ENUMS_CODEX_ORDER` (22 names) and `NEW_ENUMS` | `test_codex_host_packaging.py` (rows 53/72), asserted at 224 | the Codex* order in `vidbyte.lib.enums.__all__` |
| `builtin_codex.__all__` == TOOL_TABLE classes + `CodexToolScope` | `test_codex_host_packaging.py:212` | the tool exports |
| `toolsets.__all__` and docstring bullets | `test_codex_host_packaging.py:239-242` | unchanged unless a toolset is added |
| `NEXT_STEPS` exact dict equality with `CODEX_NEXT_STEPS` | `codex_host_support.py:61-81`; `test_codex_host_records.py:411` | each new code's next step |
| `CLASSIFICATION_ROWS` | `codex_host_support.py`; `test_codex_host_records.py:405-410` | the row per code |
| the 15 host codes as a slice after CODEX_RUN_OPTION_UNSUPPORTED | `test_codex_host_records.py:395` | the slice; appending after TURN_TIMED_OUT keeps it |
| the tail after RULE_EVALUATION_FAILED == the 28 harness codes | `test_harness_threads_surface.py:176-193` | no codex code may go at the end |
| the §9.3 constants dict (method names, bounds) and `assertIn(name, constants.__all__)` | `test_codex_host_records.py:414-450` | only the listed constants; new ones are not pinned unless added |
| `CALL_LIST` of every `CodexClient` method the host calls | `test_codex_host_sdk_contract.py:22-46` | a newly used typed method (for example `thread_compact`) needs a row |
| `SDK_WIRE_SOURCES` | `test_codex_host_records.py:64+` | a new enum mirroring a generated SDK enum gets a row |
| `assert_codex_error` checks `error.operation in CodexHostOperation values` | `codex_host_support.py:289-296` | — |
| `_valid_arguments` per tool name; `test_every_tool_turns_host_errors_into_error_results` iterates `TOOL_NAMES` | `test_codex_host_tools.py:170` | the stub host needs a method per tool |
| `StubCodexHost`, one method per host function | `codex_host_support.py:420-513` | — |
| module functions list | `test_codex_host_lifecycle.py:312-353` (the `calls` tuple) | only if module functions are added |
| list params asserted exactly | `test_codex_host_threads.py:246-268` | the existing list call |
| goal spawn request order on the thread `["thread/read","thread/goal/clear","thread/goal/set","thread/goal/set"]` | `test_codex_host_review_goals.py` | the goal path |
| static-policy skip `HOST_SUBPACKAGE = "codex"` and INV-21 excludes | `test_harness_threads_static_policy.py:27`; `test_harness_threads_surface.py:228` | placement |
| inherited failure (on main too): `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, "assert 148 == 120" | `test_harness_threads_surface.py:193` | not caused by this run; do not try to fix it here |

## 4. Notes for the spec author

### 4.0 Contradictions: request assumes X; code shows Y

1. **The summary record.**
   - Request assumes the helper summary record can carry `parent_thread_id` (NativeThreadSummary parity).
   - Code shows `CodexThreadInfo` has no `parent_thread_id`, `source`, `recency_at`, `agent_nickname` or `agent_role` (`vidbyte/lib/dataclasses/codex_host.py:385`). `CodexResponseTranslator.thread_info` drops `thread.parent_thread_id` (`wire.py:457-485`).
   - `Thread.parent_thread_id` is described as "only be set if this thread is a subagent" (`v2_all.py`, Thread fields from 12130).
   - `name` is `""` when absent, not `None`.
2. **Search scope.**
   - Request assumes `search_codex_threads(cwd, query)` searches threads.
   - Code shows `search=` maps to `searchTerm` (`wire.py:280`). The schema calls it "Optional substring filter for the extracted thread title" (`v2_all.py` ThreadListParams 10121+).
   - The tool text says it matches "names or previews" (`vidbyte/tools/builtins/codex/descriptions.py:46`). So the existing description overstates the match; previews are not in the schema text.
3. **Page size.**
   - Request assumes `list_recent_codex_threads(cwd, limit)`.
   - Code shows `list_codex_threads` has no `limit` and `CodexParamsTranslator.thread_list` never sends one (`wire.py:267-287`). The schema has `limit` (`ge=0`, "defaults to a reasonable server-side value").
4. **Default source filter.**
   - Request assumes recent and since listings see the threads the SDK created.
   - Code shows the schema's `sourceKinds` "When omitted or empty, defaults to interactive sources". The PR's own tool text says "Without source filters Codex lists only threads started interactively, so ask for the app server source to see threads started by tools like these" (`descriptions.py:20`).
   - unverified: whether `appServer` counts as interactive. The PR text asserts it does not.
5. **Full transcript.**
   - Request assumes `read_codex_thread(include_turns=True)` may give the full transcript.
   - Code shows it returns `CodexTurnSummary` rows only: id, status, final answer, error message and timestamps. Items are dropped (`wire.py:461-470`; `codex_host.py:367` "without its items").
   - `thread/turns/list` and `thread/items/list` are unused.
6. **Goal readback.**
   - Request assumes a goal wrapper can verify via `thread/goal/get`.
   - Code shows the spawn goal path never calls `thread/goal/get`. It calls `client.start_goal_operation(thread_id, goal.objective)` (`host.py:583`), then, only with a budget, a raw `thread/goal/set {threadId, tokenBudget}` whose echo is compared (`host.py:587-591`, `BUDGET_ECHO_MESSAGE` → `codex.protocol_mismatch`).
   - The only post-start signal is `CodexTurnSnapshot.goal_status`, which comes from `thread/goal/updated` notifications.
7. **Goal start preconditions.**
   - Request assumes `run_codex_goal(objective, ...)` is a "simple wrapper".
   - Code shows openai-codex's `start_goal_operation` requires the thread to be idle ("thread must be idle before starting a goal", `client.py:617`, raised as InvalidRequestError -32600) and persisted.
   - `CodexSpawnRequest` enforces `prompt` XOR `goal` (spec D-9). The spawn **tool** already exposes `goal_objective` and `goal_token_budget` (`threads.py:90-118`).
8. **Skill path.**
   - Request assumes `run_codex_skill(skill, prompt)` can name a skill.
   - Code shows `SkillUserInput` requires `name`, `path` and `type` (`<schema>/v2/TurnStartParams.json`, UserInput skill variant). `CodexSkillInput` requires both name and path as non-empty text (`vidbyte/lib/dataclasses/codex.py:450-459`).
   - So a skill turn needs the `path` that `skills/list` reports (`SkillMetadata.path`).
   - Today only the Python path can send skill items: `spawn_codex_thread`/`continue_codex_thread` take a `CodexRunInput` (`wire.py:243-250`). The tools take `prompt: string` only (`threads.py:90,164`).
9. **Bundled skills.**
   - Request assumes four bundled skills (imagegen, openai-docs, skill-creator, skill-installer).
   - Disk shows five: `review-agent` is also present, with `policy.allow_implicit_invocation: false` in `agents/openai.yaml`. See §4.c.
10. **New-module placement.**
    - Request assumes new functions go in "new modules (e.g. a threads/skills split)".
    - Code shows that only `native/codex/...` is exempt from #1036's static policy (`test_harness_threads_static_policy.py:27,31`). host.py also imports `vidbyte.tools.catalog` (line 71), which INV-20 forbids for non-codex native modules.
11. **Tools for every operation.**
    - Request assumes every new function except delete is a tool, while delete has an operation and no tool.
    - Code shows `test_codex_host_records.py:61` derives every `CodexHostOperation` member from `TOOL_NAMES`.
12. **Cross-harness `harness` field.**
    - Request assumes a `NativeThreadSummary`-shaped field set "WITHOUT importing that record".
    - Code shows `NativeHarness` has no CODEX member (`vidbyte/lib/enums/native_threads.py:19-24`), and its members are pinned (`test_harness_threads_surface.py:36`). `NativeThreadResult(harness, thread_id, text, text_truncated)` is at `vidbyte/lib/dataclasses/native_threads.py:213`. `NativeThreadError` (`vidbyte/lib/errors/base.py:559`) is #1036's error and is not used by codex.
13. **Request text says `list_codex_threads(cwd, search, archived, source_kinds, sort)`.** Code shows it also takes `sort_direction` and `cursor` (`host.py:335-344`).
14. **Workspace facts.** `vidbyte-gates.md` says lint prints `AGENT-LINT: PASS`. This repo prints `SDK-LINT: PASS` (S0-merge-main.md).

### 4.a App-server methods for the catalog

Abbreviations: `C` = `<venv>/Lib/site-packages/openai_codex/client.py`; `G` = `.../openai_codex/generated/v2_all.py`; `S` = `<schema>/v2/`.

| Method | Params (schema) | Response | High-level call in openai-codex 0.162.1 | Sent by wire.py/connection.py today | Called by CodexHost today |
|---|---|---|---|---|---|
| `thread/list` | `archived?: bool`, `cursor?: str`, `cwd?: str \| [str]` ("exactly matches"), `limit?: uint ≥0`, `modelProviders?: [str]`, `originators?: [str]` ("the local app-server rejects a nonempty list"), `searchTerm?: str` (title substring), `sectionId?`, `sortDirection?: asc\|desc` (default desc), `sortKey?: created_at\|updated_at\|recency_at\|section_position` (default created_at), `sourceKinds?: [ThreadSourceKind]` (default interactive), `useStateDbOnly?: bool` (G 10121) | `{data: [Thread], nextCursor: str\|None ("if None, there are no more items"), backwardsCursor}` (G 12328) | typed `CodexClient.thread_list(params)` (C 493); high-level `Codex.thread_list` (api.py 175) | yes: `wire.thread_list` (267-287), no `limit` | `list_codex_threads` (`host.py:335-353`), one page |
| `thread/read` | `threadId: str`, `includeTurns: bool` (G 5733) | `{thread: Thread}` (G 12356); `Thread.turns` is populated only with includeTurns | typed `thread_read(thread_id, include_turns=False)` (C 498) | via the typed call | `read_codex_thread` (355-360); `CodexPreflight.require_thread` (preflight 169) for continue, fork and review read-back |
| `thread/turns/list` | `threadId: str` (req), `cursor?: str`, `limit?: uint`, `itemsView?: notLoaded\|summary\|full` (default summary), `sortDirection?` (default descending) (S ThreadTurnsListParams.json; G 10432) | `{data: [Turn], nextCursor, backwardsCursor}` (G 12505) | **none** (no CodexClient method; request literal at G 10670) | no (`RAW_RESPONSES` lacks it) | no |
| `thread/compact/start` | `threadId: str` (S ThreadCompactStartParams.json) | `{}` (G 5262). Later notification `thread/compacted {threadId, turnId}` (G 1135, 4646); item `contextCompaction` (G 5534) | typed `thread_compact(thread_id)` (C 534-539); `Thread.compact()` (api.py 675) | no | no |
| `thread/delete` | `threadId: str` (G 5269) | `{}` (G 5276). Notification `ThreadDeletedNotification{threadId}` (G 5283) | **none** (literal at G 6932) | no | no |
| `thread/goal/set` | `threadId`, `objective?`, `status?: ThreadGoalStatus`, `tokenBudget?`, `origin?` (G 9938) | `{goal: ThreadGoal}` (G 9952) | typed `thread_goal_set(thread_id, *, objective, status)` (C 549; no tokenBudget); `start_goal_operation(thread_id, objective)` (C 599-648) | raw budget set via `RAW_RESPONSES` + `SPENDING_RAW_METHODS` (connection 67-76); `wire.goal_budget` (297) | yes: `_start_goal` (`host.py:569-602`) via `start_goal_operation` plus raw budget set |
| `thread/goal/get` | `threadId: str` (G 5322) | `{goal: ThreadGoal\|null}` (G 9931). `ThreadGoal` = createdAt, objective, status, threadId, timeUsedSeconds, tokenBudget?, tokensUsed, updatedAt (G 9906) | **none** (literal at G 6959) | no | no |
| `skills/list` | `cwds?: [str]` ("When empty, defaults to the current session working directory."), `forceReload?: bool` ("bypass the skills cache") (S SkillsListParams.json; G 4962) | `{data: [SkillsListEntry{cwd, errors:[{message,path}], skills:[SkillMetadata]}]}` (G 9815-9824). `SkillMetadata` = name, description, enabled, path, scope (user\|repo\|system\|admin), interface?, dependencies?, pluginId?, shortDescription? (G 9788) | **none** (literal at G 7167) | no | no |
| `turn/start` with a Skill item | `input: [UserInput]`; the skill variant is `{type:"skill", name, path}`, with all three required (S TurnStartParams.json) | `{turn: Turn}` | typed `turn_start(thread_id, input_items, params)` (C 650); SDK `SkillInput(name, path)` (`_inputs.py:32`) | yes: `wire.input_items` (243-250) maps `CodexSkillInput` to `{"name","path","type":"skill"}` | indirectly: `spawn_codex_thread`/`continue_codex_thread` accept `CodexRunInput` items; no test sends one |
| `review/start` | `threadId`, `target`, `delivery?` (detached deprecated) (G 9114) | `{reviewThreadId, turn}` (G 12056) | **none** | raw, single attempt (connection 71, 76); `wire.review` (290) | `start_codex_review` (`host.py:463-491`) |

Related methods the schema has: `thread/loaded/list {cursor?, limit?}` returns `{data: [threadId], nextCursor}` (G 5605-5627, "Thread ids for sessions currently loaded in memory"). `thread/items/list {threadId, turnId?, cursor?, limit?, sortDirection?}` (G 5570). Neither is called. The installed CLI is 0.162.1 (`C:/Users/422mi/AppData/Roaming/npm/node_modules/@openai/codex/package.json`), and the venv also has `openai_codex_cli_bin-0.162.1`. The JSON schema copy and `v2_all.py` agree on every method above. `ClientRequest.json` lists 105 methods.

### 4.b What the existing 15 functions already cover

- **`list_codex_threads`**
  - **Signature:** `list_codex_threads(cwd="", search="", archived=False, source_kinds=(), sort=CodexThreadSortKey.PROVIDER_DEFAULT, sort_direction=CodexSortDirection.PROVIDER_DEFAULT, cursor="") -> CodexThreadPage` (`host.py:335-353`).
  - **Wire:**
    - `search` maps to `searchTerm`.
    - `sort` maps to `sortKey`, and `sort_direction` to `sortDirection`. Both enums have the needed values: `UPDATED_AT` and `DESC`.
    - No `limit` is sent.
    - **It does not page**: one call returns one page, and the caller passes `cursor`.
    - `next_cursor` is `""` when Codex sends null (`wire.py:487-491`).
  - **Other paths:**
    - Module function: `oneshot.list_codex_threads`.
    - Tool: `ListCodexThreadsTool` (READ). Its params are cwd, search, archived, source_kinds, sort, sort_direction and cursor (`codex_host_support.py:141-146`).
  - **No time filter.** No `ThreadListParams` field filters by time. Records carry `created_at`/`updated_at` as Unix seconds.
- **`read_codex_thread`**
  - **Signature:** `read_codex_thread(thread_id, include_turns=False) -> CodexThreadInfo` (`host.py:355-360`), via `require_thread`.
  - With turns, it returns every turn `thread/read` includes, each reduced to `CodexTurnSummary(turn_id, status, final_response, error_message, started_at, completed_at)`. Items are not returned, so it is **not a full transcript**.
  - Any `thread/read` error becomes `codex.session_not_found` (`errors.py:101-102`).
- **`fork_codex_thread`**
  - Reads with turns, then requires a completed fork point, else `codex.fork_failed` (`host.py:301-333`).
  - Returns `CodexThreadInfo` with `forked_from_id`.
  - Lineage today is one hop only: `forked_from_id` from any `CodexThreadInfo`. There is no parent-thread field.
- **`spawn_codex_thread` goal path** (`host.py:244-265`, `_start_goal` 569-602)
  - When `request.goal` is set:
    - Builds no input items.
    - Runs `preflight.run`.
    - Calls `_open_thread` (`thread/start`), then `start_goal_operation`. The SDK reads the thread, checks idle and persisted, clears the goal, then sets `objective`/`status=active`.
    - Optionally runs the raw budget set and echo check.
  - Returns a `CodexTurnHandle` for the goal run's turn. `wait_codex_turn` later gives a `CodexTurnSnapshot` with `goal_status: CodexGoalStatus`.
  - The goal is never read back with `thread/goal/get`.
  - Goal cleanup orders follow INV-25 (spec D-8).
- **`start_codex_review`**
  - Signature: `start_codex_review(thread_id, target: CodexReviewTarget, delivery=CodexReviewDelivery.INLINE) -> CodexTurnHandle` (`host.py:463-491`).
  - Runs `require_idle`, then `preflight.run(operation, REVIEW_REQUEST, check_model=False)` (480).
  - Sends a raw `review/start` once, then reads back for registration (D-23).
  - Request §C: "Do not duplicate or rename it."
- **Spend preflight `CodexPreflight.run`** (`preflight.py:99`)
  - **Called by:** spawn (`host.py:256`), continue (286), launch (446) and review (480, `check_model=False`).
  - **Not called by:** check_codex_ready, get_codex_rate_limits, list_codex_models, fork, list, read, wait, get, steer, interrupt or track.
  - **What it calls:** `account/read`, then the raw `account/rateLimits/read`. An error or `None` passes, and `False` becomes `codex.usage_limited`. Then win32 sandbox readiness, then the paged model list cached for the host's lifetime.
  - **Order in continue** (`host.py:267-299`):
    - `require_idle` → `registry.reserve` → `preflight.run` → `require_thread` → `thread/resume` → `turn/start`.
- **Busy check.** `require_idle` (preflight 162-167) sees only this host's own registry and in-flight starts. It raises `codex.session_busy`, "The thread already has a running turn on this host."

### 4.c Bundled system skills (`C:/Users/422mi/.codex/skills/.system/`; marker `.codex-system-skills.marker` = `c986fbc6aee014e`)

| Folder | SKILL.md (lines) | What it does | Interactive / needs a person? | Network / credentials | `agents/openai.yaml` |
|---|---|---|---|---|---|
| `imagegen` | 315 | Generates or edits bitmap images. The default mode is the "built-in `image_gen` tool ... Does not require `OPENAI_API_KEY`". The fallback is a CLI `scripts/image_gen.py` that "Requires `OPENAI_API_KEY`". | Conditional. "If any critical detail is missing and blocks success, ask a question; otherwise proceed". "Never silently switch ... ask the user first". The CLI fallback runs only "if the user explicitly asks". | The built-in tool spends the model plan (unverified whether `image_gen` is available in app-server sessions). The CLI needs `OPENAI_API_KEY` and network. Output goes to `$CODEX_HOME/generated_images/...`, and project-bound output is copied into the workspace. | `display_name: "Image Gen"`, `default_prompt: "Use $imagegen to make or edit an image for this project."` |
| `openai-docs` | 38 | Gives cited answers from official OpenAI and Codex docs. "First substantive action: Search ..." limited to `developers.openai.com`, `platform.openai.com` and `learn.chatgpt.com`. | No question step. It answers a request. | Needs web search/fetch (network). "Documentation ... do not require an API key." It uses `openai-platform-api-key` only before building or running an API-backed app. | `display_name: "OpenAI Docs"` |
| `review-agent` (**not in request's list**) | 57 | "Perform a read-only, defect-first review of a specified code change". "Do not modify files, create commits, push branches, post review comments, or delegate". Output is `[P1] ... — path:line` findings or "No findings." | No question step. | Local git only (`git merge-base`, `git diff`). | `policy: allow_implicit_invocation: false` (explicit-only). It overlaps the existing `start_codex_review` (`review/start`). |
| `skill-creator` | 229 | Creates or updates a skill folder. Writes to `$CODEX_HOME/skills` by default, and uses `scripts/init_skill.py` and `scripts/quick_validate.py`. | Conditional. "Ask clarifying questions only when the missing information matters and cannot be reasonably inferred". "Ask for approval when the proposed evaluation would require additional authorization". | No network named. It writes files outside the workspace (`~/.codex/skills`). | `display_name: "Skill Creator"` |
| `skill-installer` | 58 | Lists and installs skills from GitHub (`openai/skills` `.curated`/`.experimental`, or any repo) into `$CODEX_HOME/skills/<name>`. | Yes for listing: it ends with "Which ones would you like installed?" Install runs when a name or path is given. | "All of these scripts use network, so when running in the sandbox, request escalation". Private repos use git credentials or `GITHUB_TOKEN`/`GH_TOKEN`. | `display_name: "Skill Installer"` |

- **What `skills/list` would report.** unverified: no app-server was run. From the schema, each skill would come back as `SkillMetadata{name, description, enabled, path, scope, ...}`, and these five would be expected under `scope: "system"`.
- **Not in the schema:** `SkillMetadata` has no field for `allow_implicit_invocation`.
- **Unverified:** whether `path` is the folder or the `SKILL.md` file, and whether `skills/list` reports these skills for any `cwd`.

### 4.d Thread status, busy and loaded semantics, and error codes

- **Status.** `ThreadStatus` is a union of `notLoaded`, `idle`, `systemError` and `active{activeFlags: [waitingOnApproval|waitingOnUserInput]}` (G 6228-6265, `ThreadActiveFlag` G 5085). `Thread.status` is "Current runtime status for the thread".
  - `CodexThreadStatus` mirrors the four type tags. `thread_info` drops `activeFlags`.
  - `thread/status/changed {threadId, status}` exists (G after 6265). The host does not subscribe to it.
  - unverified: whether a thread loaded by another process (the TUI or another `CodexHost`) appears as `notLoaded` to this host's app-server. Each `CodexHost` runs its own app-server, and `thread/loaded/list` reports "sessions currently loaded in memory".
- **Loaded threads.** `thread/loaded/list` exists but is unused. There is also `ThreadClosedNotification` (G 5248).
- **Busy.**
  - The host's only busy check is local (`require_idle`, `preflight.py:162-167`).
  - The SDK refuses `turn/start` while its router holds a goal on the thread (`client.py` `_start_turn`, 659). It also refuses a goal start unless `thread/read` reports `idle` (`client.py:617`, -32600 "thread must be idle before starting a goal").
- **Compaction.**
  - It runs as a turn. Evidence: `ContextCompactedNotification{threadId, turnId}` (G 1135) and `NonSteerableTurnKind.compact` with `ActiveTurnNotSteerable` error info (G 2998, 7754-7768).
  - It is a WRITE that uses the model (unverified: whether it spends plan usage).
  - The host would not register or watch that turn. The router drops events for turns with no subscriber (spec D-23), and `require_idle` would not see the turn as busy.
  - unverified: what `thread/compact/start` returns on a thread with a running turn, or on an unloaded or unknown thread. The fake answers -32601.
- **Delete.**
  - `thread/delete {threadId} → {}`, plus `ThreadDeletedNotification` (G 5269-5290).
  - unverified: behaviour on a loaded or running thread, on an unknown id, and whether a deleted thread is also removed from `thread/list`.
- **JSON-RPC errors.** `openai_codex/errors.py:86-109` maps codes to exception classes:
  - -32700 → `ParseError`
  - -32600 → `InvalidRequestError`
  - -32601 → `MethodNotFoundError`
  - -32602 → `InvalidParamsError`
  - -32603 → `InternalRpcError`
  - -32000..-32099 → `ServerBusyError`/`RetryLimitExceededError` on overload data, else `CodexRpcError`
- **How the host maps them** (`errors.py:68-107`):
  - Any error on `thread/read` → `codex.session_not_found`.
  - A refused `thread/fork` → `codex.fork_failed`.
  - -32601, -32602, -32700 → `codex.protocol_mismatch`. So a runtime older than the method, for example under the 0.151.0 minimum, reports protocol_mismatch.
  - Everything else → `codex.api_error`.
  - The fake's unknown thread is `-32600 "thread not found: <id>"` (`codex_host_fakes.py:741-745`). unverified: the real server's code and message for an unknown thread on each method.
- **Turn errors.** `codexErrorInfo` values (G 525-541) map through `CODEX_ERROR_INFO_CODES` (`errors.py` `turn_problem`):
  - contextWindowExceeded, usageLimitExceeded, rateLimitExceeded, serverOverloaded, unauthorized, badRequest, threadRollbackFailed, sandboxError and others.
  - An unknown key → `codex.api_error`.
- **Existing codes available for reuse** (`failure.py:41-61`):
  - codex.fork_failed, codex.response_invalid and codex.run_option_unsupported.
  - The 15 host codes, including codex.session_not_found, codex.session_busy, codex.api_error, codex.protocol_mismatch and codex.process_exited.
  - There is no `codex.command_not_run`, no skill-unknown code and no goal-not-set code. Request §C quotes "`<harness>.command_not_run`" from the catalog reply.
- **Retries.** `CodexConnection.raw` retries non-spending raw methods up to the SDK default `max_attempts=3` on overload (`client.py:731-746`). A raw `thread/delete` or `thread/goal/get` would therefore be retried on overload unless it is added to `SPENDING_RAW_METHODS`. Typed calls (`thread_compact`) use `self.request` with no retry (`client.py:534-539`).

### 4.e Size and placement budget (`wc -l` at HEAD c181be65)

| File | Lines |
|---|---|
| `vidbyte/harnesses/native/codex/host.py` | 771 |
| `.../codex/wire.py` | 609 |
| `.../codex/turns.py` | 419 |
| `.../codex/connection.py` | 361 |
| `.../codex/preflight.py` | 186 |
| `.../codex/errors.py` | 179 |
| `.../codex/oneshot.py` | 115 |
| `.../codex/__init__.py` | 30 |
| `vidbyte/tools/builtins/codex/threads.py` | 335 |
| `.../builtins/codex/_base.py` | 223 |
| `.../builtins/codex/live.py` | 190 |
| `.../builtins/codex/delegation.py` | 134 |
| `.../builtins/codex/readiness.py` | 97 |
| `.../builtins/codex/descriptions.py` | 62 |
| `.../builtins/codex/__init__.py` | 56 |
| `vidbyte/tools/toolsets/codex.py` | 82 |
| `vidbyte/tools/builtins/__init__.py` | 358 |
| `vidbyte/lib/constants/codex.py` | 543 |
| `vidbyte/lib/enums/codex.py` | 270 |
| `vidbyte/lib/enums/__init__.py` | 315 |
| `vidbyte/lib/enums/failure.py` | 340 |
| `vidbyte/lib/dataclasses/codex_host.py` | 511 |
| `vidbyte/lib/dataclasses/codex.py` | 1,205 (already over; do not touch) |
| `vidbyte/lib/errors/base.py` | 614 |

- **Headroom to ~900–1,000 lines:**
  - host.py ~130–230
  - wire.py ~290–390
  - constants/codex.py ~360
  - codex_host.py ~390
  - tools threads.py ~565
- **REPO_MAP.md (67,764 characters):**
  - `##### \`vidbyte/harnesses/native/\`` is at line 159, with text at 161 (the host shape) and 163 (#1036 thread functions).
  - It describes the host generically: "small, atomic functions such as starting, continuing, forking, steering and waiting on a session".
  - **Pinned byte-exact** as `REPO_MAP_SECTION` (`test_codex_host_packaging.py:91`, asserted at 185-192).
- **`vidbyte/harnesses/README.md` (11,360 characters; A009 cap 40,000):**
  - The `native/` bullet is at line 178. It names `CodexHost` and "its module functions" without listing them.
  - **Pinned byte-exact** as `README_BULLET` (`test_codex_host_packaging.py:92`, asserted at 194-197).
- **Editing these two texts.** Neither needs an edit for new functions. Any edit must update the pins in the same commit.
- **Other docs that enumerate counts:**
  - `tests/features/codex_host/README.md` and `FEATURE.md` say "fifteen" (README:5,25; FEATURE:5,22).
  - The A001 headers of `tools/builtins/codex/__init__.py:3`, `_base.py:3`, `descriptions.py:3` and `toolsets/codex.py:3,5,78` say "fifteen".
  - `codex_host.py:3` says "fifteen validated records".
  - None of these is test-pinned except the counts listed in §3.4.

### 4.f Unverified (could not be seen in a file)

- **Real app-server behaviour.** The real responses and errors for these cases:
  - `thread/compact/start`, `thread/delete` and `thread/goal/get` on unknown, running or loaded threads;
  - `skills/list` output on this machine;
  - whether `thread/turns/list` needs `historyMode: paginated` (`Thread.historyMode` exists, `ThreadHistoryMode` legacy|paginated at G 5345).
- **Interactive sources.** Whether `sourceKinds` "interactive sources" includes `appServer`.
- **Minimum version.** Whether these methods exist in codex 0.151.0, the host's `CODEX_HOST_MINIMUM_VERSION` (spec D-5).
- **image_gen.** Whether the built-in `image_gen` tool is available to app-server turns.
- **Compaction usage.** Whether compaction spends plan usage.
- **The bundled binary.** The codex binary the PR runs is resolved with `shutil.which` (D-4). The bundled `codex_cli_bin` 0.162.1 in the venv is not used.
