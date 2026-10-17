# Code map: AgentSwarm (S0 scout)

Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm`. Branch `feat/agent-swarm`, head `7e529671`, which is `origin/main` (`0f2aeb48`) plus one commit that captures the request. Every path below is relative to the worktree root. Every claim was read in this session, and anything not read is marked "unverified:". The scout only maps the code; nothing below is a design choice.

## 1. Rules, commands, and conventions from AGENTS.md

**Reading rules**

- Read `REPO_MAP.md` before creating or moving a file, and put new code where it says that kind of code belongs (AGENTS.md:9).
- Read a folder's `README.md` to the end before changing anything in that folder, and obey its `## Notes for agents` (AGENTS.md:11).
- A009 caps each folder README at 40,000 characters (AGENTS.md:11). Current sizes:
  - `vidbyte/agents/README.md`: 29,527 chars, so about 10.4K is left. It has no File Index.
  - `vidbyte/prompts/README.md`: 31,924 chars, so about 8K is left.
  - `vidbyte/tools/README.md`: 6,456 chars.
  - `vidbyte/lib/README.md`: 4,037 chars.
  - `vidbyte/agents/infinite/README.md`: 12,162 chars. It has a File Index, which S020 enforces.
- Do not grep, glob, or read `docs/` during ordinary work (AGENTS.md:13).

**Gate**

- The full gate is `python scripts/run_ci.py` (AGENTS.md:13). No narrow script substitutes for it.

**Style principles (AGENTS.md:17-41)**

- **1, call chains:** one main function calls flat helpers, and a helper does not call another helper. No nested defs unless an API requires a callback.
- **2, narration:** narrate each main function with plain-English comments.
- **3, layering:**
  - `vidbyte/lib/` is the bottom layer and never imports upward.
  - Domain packages (`agents/`, `tools/`, `context/`) sit above it, and composition layers (`pipelines/`, `paradigms/`) sit above them.
  - Keep files "well below 1,000 lines" (AGENTS.md:31).
  - If describing a class needs the word "and", it is two classes.
- **4, validated inputs and outputs:** core inputs and outputs are `@dataclass(frozen=True, slots=True)` records validated in `__post_init__`. A field drawn from a closed set is an enum (AGENTS.md:35).
- **5, shared logic:** shared logic lives once, in `vidbyte/lib/`. Look there first and add an option rather than a copy (AGENTS.md:39-41).

**Placement (AGENTS.md:43-81, binding, enforced by the "AGENTS.md placement" workflow)**

- **Dataclasses** go in `vidbyte/lib/dataclasses/<domain>.py`.
  - Never create a `types.py`, `records.py`, `models.py` or `schemas.py`.
  - Exception 1 (AGENTS.md:56): an agent `*Settings` class lives in `vidbyte/agents/settings/` or in the owning agent's own `settings.py`.
- **Enums** go in `vidbyte/lib/enums/<domain>.py` with no exceptions, and every public enum is added to `vidbyte/lib/enums/__init__.py` `__all__` (AGENTS.md:59-63).
- **Prompts:** a new prompt is a new family under `vidbyte/prompts/prompts/` with its keys in `vidbyte/lib/enums/prompts.py` (AGENTS.md:77, which is stated for Jev and followed by every family).
- **Existing code:** older modules that define dataclasses or enums outside `lib/` are not precedent. Adding a field or member to one in place is allowed (AGENTS.md:79-81). Example: `AgentStopReason` is a `str, Enum` defined in `vidbyte/lib/dataclasses/agents.py:61`.

**Lint (read from `lint/`, not run)**

- `lint/run.py` runs the suite (`--rule <ID>`, `--all`, `--format json`). Exit 0 means every rule is CLEAN, RATCHETED or IMPROVED (lint/README.md:29-48).
- `lint/baseline.json` holds the per-rule ceilings. Never raise one (lint/README.md:50-61).
- The rules most likely to bind on this change:

| Rule | What it enforces | Baseline |
|---|---|---|
| A001 (`lint/rules/a001_agent_readable_file_headers.py:24-32`) | Every tracked `.py` opens with a docstring holding non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:` and `TESTS:`. The actor runtime's "Context Protocol Header" format (`vidbyte/agents/runtimes/actor/actor.py:1-17`) does not satisfy it; follow `vidbyte/agents/infinite/*.py` or `lint/rules/*.py`. | 642 |
| A002 (`a002_intent_comments.py:23-49`) | A function whose identifiers contain policy tokens needs a `# @intent <name>` comment within 20 lines. The tokens are retry, backoff, attempt, permission, authorize, price/pricing/billing, redact/secret, persist/persistence/checkpoint, fallback, transition, transport/request/fetch/send/urlopen/provider/subprocess/mcp. A `send`-named message function will trigger it. | 703 |
| A006 (`a006_directed_dependency_graph.py:23-36`) | `vidbyte.lib`, `providers`, `sessions` and `sources` are lower layers. `agents`, `context`, `middleware`, `tools`, `pipelines`, `workflows`, `harnesses`, `trace`, `evals` and `paradigms` are one orchestration tier. Function-local imports count; only `TYPE_CHECKING` edges and `__init__.py` targets are skipped. | 34 |
| A007 (`a007_operational_constants.py:23-39`) | Literals in timeout, retry, attempt, backoff, delay, token, char, byte, truncate, limit, budget, status, depth or interval positions, or passed to sleep/send/request/read, need named constants. | 255 |
| S024 | At most 3 levels of control-flow nesting (`s024_maximum_control_flow_nesting.py:22`). | 25 |
| S025 | Every `ToolSpec` and `ToolParameter` description has at least 4 sentences (`s025_model_facing_description_depth.py:27`). | 263 |
| S006 (async task ownership), S019 (cancellation never swallowed), S063 (`gather(return_exceptions=True)` results tested against `BaseException`) | Bind on any concurrent runner. | 0, 5, 4 |
| C001 / C006 / C007 / C008 | Settings validation lives on the dataclass, numeric guards reject bool/NaN/inf, bool switches are strict, and primitive validators live only in `vidbyte/lib/dataclasses/validation.py`. | 26 / 104 / 16 / 45 |
| C011 (`c011_agent_owned_usage_and_sync_twins.py:24-37`) | Model usage reaches the agent's `UsageTracker`. A public class whose name ends in `Agent`, `Runner`, `Harness`, `Session` or `Machine` must pair `arun()` with a `run()`. | 2 |
| C015 | Every non-README file in the package ships in the wheel, which matters for new prompt `.md`/`.json` assets. | 3 |
| C016 (`c016_public_api_contract_current.py`) | `contracts/sdk-public-api.json` equals the generator's output for `vidbyte.__all__`. | 0 |
| S015 | `__all__` is unique, bound and complete. | 13 |
| S020 | A README's `## File Index` matches the tracked files. | 1 |
| S055 | No shell subprocess. | 0 |
| S061 | Bounded safe paths for dynamic-path I/O. | 6 |
| S062 | No implicit string concatenation, including model-facing text. | 889 |

**`scripts/run_ci.py` stages (read, not run)**

- `--stage {all,source,package}`, default `all` (run_ci.py:255-272).
- **source** (79-93):
  1. Fail on tracked bytecode.
  2. `lint/run.py`.
  3. `compileall`.
  4. `scripts/check_context_write_paths.py`.
  5. `scripts/check_context_primitive_introductions.py`.
  6. `scripts/check_reasoning_trace_contracts.py`.
  7. `python -m pytest`.
- **package** (95-218): build, twine check, wheel inspection (it must contain `vidbyte/prompts/prompts/error_correction_auditor.md`), then a clean venv install and smoke test with `PYTHONPATH` popped (run_ci.py:193-194, 225-226).
- run_ci does not run the public-API generator. C016 inside lint enforces it.

**Public-API contract**

- `contracts/README.md:24-33`:
  - `python scripts/generate-sdk-public-api.py --check` exits 1 when the file is stale.
  - Running it without `--check` rewrites the file. Commit the source change first, because it refuses to write while `vidbyte/__init__.py` or `pyproject.toml` has uncommitted changes.
  - Never edit the contract by hand.
- The contract today has `version` 0.3.0 and `source.commit` 9eca4a33…, and it already lists the four `Infinite*` root exports (contracts/sdk-public-api.json:2-5, 246-249).

### Field-guide rules (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)

- **runtime-boundaries.md:**
  - **:31-36:** a specialized agent runtime is its own `AgentRuntimeType`. Build one from these parts:
    - map the type in `RuntimeRegistry.resolve`;
    - pass extras through `BaseAgent._runtime_extension_kwargs()`;
    - add the type to `_LINEAR_LOOP_RUNTIMES` in `base.py`;
    - make the runtime refuse to build without its settings, because the enum is string-selectable.
  - **:38-43:** narrow per-run runtime state inside try/finally.
  - **:45-50:** enforce a numeric tool-call cap in middleware `before_tool_call` with `MiddlewareDecision.deny_tool(reason, metadata={"limit":…})`. Prompts say limits exist, with no numbers. A cap that needs run-wide state stays in the tool. The check `grep -rn "format(max_"` must come back empty.
  - **:10-15:** usage stays agent-owned.
  - **:24-29:** do not duplicate `AgentLoopSettings.timeout_seconds` or `CostBudgetMiddleware` as fields of the feature's own record.
- **strict-config-dataclasses.md:**
  - **:11-16:** a `BaseAgent` subclass gathers its own arguments into one frozen, slotted `<Agent>Settings` record whose `__post_init__` does every check. `__init__` raises nothing, key fields are `repr=False`, and the record is not stored on the agent.
    - Tension: that entry names `vidbyte/lib/dataclasses/<agent>.py` as the record's home, while AGENTS.md:56 lets settings live in the agent's own `settings.py`. InfiniteMemoryAgent took the second option, and does store the record (`vidbyte/agents/infinite/agent.py:54`).
  - **:32-37 and :53-58:** bounds are named constants in `vidbyte/lib/constants/<feature>.py`, and caps are generous.
  - **:61-66:** validate fields only through `RecordFieldValidator`/`RecordFieldConverter` (`vidbyte/lib/dataclasses/validation.py:37-262`), adding an option rather than a private `_x_field` helper.
  - **:68-73:** size caps stop runaways, and the constants header states the token budget.
- **prebuilt-agents.md:**
  - **:3-8:** an agent's preloaded tools live in a `<Agent>Tools(Tools)` catalog in `vidbyte/tools/toolsets/<agent>.py`, with a static `get_tools(...)` (and `authenticate_tools(settings)` when a key is involved). The agent module imports no tool class except the toolset. The API key never sits on `agent.tools`.
  - **:10-15:** no `vidbyte-sdk` CLI command for any agent.
- **model-facing-tool-contracts.md:**
  - **:3-8:** each tool and parameter description is 4-5 general sentences with no examples.
  - **:10-15:** categorical vocabularies are `str, Enum` in `vidbyte/lib/enums`, and field-name lists go in `vidbyte/lib/constants`.
- **prompt-families.md:3-8:**
  - Each leaf is its own `<leaf>.md` in `vidbyte/prompts/prompts/<family>/`, and the family JSON lists only `{path, source_url}`.
  - Role prompts have headed sections: purpose, tools, workflow, memory, limits, reply.
  - Every stated behavior must match the code, and prompts carry no numeric limits.
  - Checks: the leaf-count contract test, S025 and A009.
- **comment-format.md:3-8:** multi-line `#` comments are PEP 8 blocks of at most 72 columns, placed directly above the code they explain. `# @intent <name>` sits on its own first line.
- **blocking-lint-invariants.md:**
  - **:24-29:** a lib registry imports an agents-layer class through the package `__init__`, never the concrete module. A006 counts the concrete edge.
  - **:38-43:** a lib record holding a higher-layer object checks its shape, not `isinstance`.
  - **:46-51:** derive a status bool from data instead of storing it (C002).
  - **:54-59:** use the `os.fstat` pattern for capped reads (A007).
  - **:31-36:** do not name a non-HTTP helper `request` (S012 baseline 0).
- **class-bound-helpers.md:**
  - **:3-8:** related helpers go on one class as static methods, not loose free functions.
  - **:59-64:** search `vidbyte/lib/` before creating a "new" canonical module.
- **local-ci-verification.md:**
  - **:3-8:** run `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no `PYTHONPATH`.
  - **:10-15:** `git add` new files before running Semgrep (`semgrep==1.170.1`, `.semgrep/typed-mapping-boundary-policy.yml`).
  - **:31-36:** stage conflict resolutions before linting.
  - **:38-43:** check S051 with ruff over the whole `vidbyte` tree.
  - **:45-50:** two `harness_threads` surface tests fail on any branch that touches `vidbyte/tools`. This is pre-existing, so do not "fix" it.
  - **:52-57:** re-test and run `generate-sdk-public-api.py --check` after every merge of main.
- **review-scope.md:10-15:** a review asking for a much smaller change means rebuilding from main. Every file in the diff must trace to the feature's minimal surface.

## 2. Files this change will touch

Format: path — what it does today — what will change (scope only; the spec decides the shape) — the pattern to follow.

### 2a. Existing files that a new agent package conventionally edits

- **`vidbyte/lib/enums/__init__.py`** (304 lines)
  - Today: the public enum export list (imports plus `__all__`).
  - Will change: export the new swarm enums (event kinds, stop reason, and any others).
  - Pattern: the infinite block, imports at :80-86 and `__all__` entries at :223-228.
- **`vidbyte/lib/enums/agent_runtime.py`**
  - Today: `AgentRuntimeType` with LINEAR, MCTS_SEARCH, ACTOR_MODEL, ACTOR_MODEL_P2P, ACTOR_MODEL_BROADCAST, JEV and INFINITE_MEMORY (:43-52), and `__all__` at :55.
  - Will change: one member, only if the spec gives swarm members a specialized linear runtime.
  - Pattern: `JEV` and `INFINITE_MEMORY`, plus field guide runtime-boundaries.md:31-36.
- **`vidbyte/lib/registries/runtimes.py`**
  - Today: `RuntimeRegistry.resolve` lazily imports each runtime and maps type to class (:31-56). Infinite is at :33 and :48.
  - Will change: one mapping, under the same condition.
  - Pattern: import via the package `__init__` (`from vidbyte.agents.infinite import InfiniteMemoryRuntime`), per blocking-lint-invariants.md:24-29.
- **`vidbyte/agents/base.py`** (1,830 lines, already over the guidance)
  - Today:
    - `_LINEAR_LOOP_RUNTIMES = {LINEAR, JEV, INFINITE_MEMORY}` (:83);
    - `_runtime()` resolves the class, merges `_runtime_extension_kwargs()`, adds `output_contract`, `usage_tracker`, `speed_tracker`, `fallback` and `agent_catalog` for linear-loop types, and builds the runtime (:1408-1461);
    - the hook `_runtime_extension_kwargs()` returns `{}` (:1463-1465).
  - Will change: one entry in `_LINEAR_LOOP_RUNTIMES`, only if a new runtime type is added. Add nothing else to this file.
  - Pattern: the Jev and Infinite precedent.
- **`vidbyte/lib/enums/prompts.py`** (218 lines)
  - Today: the `Prompt(str, Enum)` keys "family.leaf" (:65 onward; infinite starts at :113, jev_swarm at :98) and `SystemPromptPreset` (:209).
  - The header at :7 says "139 static prompt assets across 35 … families". A count of the asset JSONs this session gives exactly 35 families and 139 leaves, so it is accurate now and must be hand-updated.
  - Will change: add one member per new prompt leaf, and update the header counts.
  - Pattern: the `INFINITE_MEMORY_*` members.
- **`vidbyte/prompts/prompts/<new family>/`** (new folder)
  - Today: 39 entries in `vidbyte/prompts/prompts/`.
  - The catalog (`vidbyte/prompts/catalog.py:85-125`) loads each `*.json` one level deep and needs `name`, `description`, `key` and a non-empty `prompts` object. Each leaf is a string or `{path, source_url}` that points to a `.md` (:166-180).
  - Every `Prompt` member must have asset text, or import fails (:189-192). An asset without an enum member also fails (:107-110).
  - Will change: a new family JSON plus one `.md` per leaf.
  - Pattern: `jev_swarm/jev_swarm.json` and `working_principles/working_principles.json`, plus prompt-families.md.
- **`vidbyte/prompts/README.md`** (31,924 chars, no Notes for agents)
  - Today: "Available Prompts" is the canonical index used by the `/vidbyte-prompts` skill. It has a Quick reference table row (:54-87) and a `#### Name — key` description block per family (:89-471).
  - Will change: one table row and one description block.
  - Pattern: the `infinite_memory` row (:67) and its block (:229-250).
- **`vidbyte/tools/toolsets/__init__.py`**
  - Today: exports `CodingAgentTools` and `InfiniteMemoryAgentTools` (:11, :19, :24).
  - Will change: export the new `AgentSwarmTools`.
  - Pattern: the infinite line.
- **`vidbyte/agents/__init__.py`** (574 lines)
  - Today: re-exports agent packages. Infinite is at :84-88 and in `__all__` at :392-395.
  - Will change: re-export the swarm's public names.
  - Pattern: the infinite block.
- **`vidbyte/__init__.py`** (1,376 lines)
  - Today: the root exports. Infinite is imported at :106-108 (agents) and :472 (enum), with `__all__` at :758-761. The header docstring at :12 lists agent exports by hand.
  - Will change: add root exports, if the spec makes the swarm public at the root.
  - Pattern: the infinite lines.
- **`contracts/sdk-public-api.json`**
  - Today: the generated `exports` list (C016).
  - Will change: regenerate it with `python scripts/generate-sdk-public-api.py` after committing the `vidbyte/__init__.py` change. Never edit it by hand (contracts/README.md:24-33).
- **`vidbyte/agents/README.md`**
  - Today: has sections per agent (CodingAgent :96-149, InfiniteMemory :151-181) and Key Modules (:384-399).
  - Will change: a short section and one Key Modules line, within the A009 room noted in section 1.
  - Pattern: the InfiniteMemory section.
- **`vidbyte/tools/README.md`**
  - Today: Key Modules has a `toolsets/` line naming each catalog (:91).
  - Will change: name `AgentSwarmTools` on that line.
- **`REPO_MAP.md`** (423 lines)
  - Today: has a subsection per agent package under `vidbyte/agents/`. The infinite one is at :83-85, and there is no swarm entry (grep finds "swarm" only in the JEV table, :401 and :403).
  - Will change: a new `##### vidbyte/agents/<swarm>/` paragraph.
  - Pattern: the infinite entry. Its prose style is 4-5 general sentences (field guide agents-md-map.md, not read; see the index entry at init.md:25).

### 2b. New files (the paths follow the placement rules; the names are the spec's choice)

- **Agent package `vidbyte/agents/<swarm>/`**
  - Holds the runtime and the coordinating classes (the five named roles).
  - Patterns:
    - `vidbyte/agents/infinite/` has 8 modules, each well under 400 lines after its header (`tests/features/infinite_memory_agent/test_infinite_memory_contract.py:471-480` enforces that budget for Infinite);
    - its `__init__.py` re-exports;
    - its `README.md` has a File Index (S020) and Notes for agents (:103-115).
- **Settings**
  - Lives in `vidbyte/agents/<swarm>/settings.py` (AGENTS.md:56) or `vidbyte/agents/settings/`.
  - Pattern: `InfiniteMemoryAgentSettings`, a frozen slots dataclass (`vidbyte/agents/infinite/settings.py:102-208`) whose `__post_init__` runs from :136. Its default `permission_policy` is `PermissionPolicy.allow_all` (:122), and `loop: AgentLoopSettings` is checked with `require_instance` (:165).
- **Records**
  - Lives in `vidbyte/lib/dataclasses/<domain>.py` (new domain module): the member definition, event records, result record, and so on.
  - Pattern: `vidbyte/lib/dataclasses/infinite.py` (189 lines). It holds six frozen slots records, each validated only through `RecordFieldValidator`/`RecordFieldConverter`. It has no `to_dict` and no `dict[str, Any]` signatures (S060), and sequence fields must already be tuples (header :3-10).
- **Enums**
  - Lives in `vidbyte/lib/enums/<domain>.py`.
  - Pattern: `vidbyte/lib/enums/infinite.py` (str enums whose values are lowercase names; the contract test checks this at test_infinite_memory_contract.py:188-206).
- **Constants**
  - Lives in `vidbyte/lib/constants/<domain>.py`: defaults, limits, tool names and labels.
  - Pattern: `vidbyte/lib/constants/infinite.py` (195 lines). The header states the token-budget arithmetic (:5), and tool names are constants (:91-104).
  - `vidbyte/lib/constants/__init__.py` does not re-export `infinite`, so there is no requirement to re-export.
- **Toolset**
  - Lives in `vidbyte/tools/toolsets/<swarm>.py` (`AgentSwarmTools(Tools)`).
  - Pattern:
    - `vidbyte/tools/toolsets/infinite.py:32-50` uses `__init__(root,…)` plus a static `get_tools(...)` that returns a tuple;
    - `vidbyte/tools/toolsets/coding.py:79-86` has `get_tools(root_dir, fetch_tool, max_rewrite_lines)` returning bash, read_lines, write_text, replace_text, glob, grep and the fetch tool.
- **A `message` tool**
  - A `BaseTool` subclass (`vidbyte/tools/base.py`). Its descriptions come from the prompt catalog, as Infinite's memory tools do (`vidbyte/agents/infinite/memory.py`).
  - It belongs in the agents package if it needs run-bound state. The ARCHITECTURE NOTE in `vidbyte/tools/toolsets/infinite.py:5` says run-bound tools live in `vidbyte/agents/infinite/` "because ... this layer may not import vidbyte.agents".
- **Feature test pack:** `tests/features/<agent_swarm>/` (see section 3).

### 2c. Existing code to reuse; it does not change

- **`vidbyte/agents/runtime.py`** (2,304 lines)
  - `AgentRuntime` loop. `BaseAgentRuntimeLoopState` is at :160.
  - `_after_tool_iteration(state, messages)` is a no-op default (:925-931). It is called only at :700, after `middleware.after_iteration` (:690) on an iteration that ran tools and continues. Then `_adopt_agent_catalog()` runs, and schemas are re-resolved if `self.tools` was replaced (:701-707).
  - `_continue_finish_attempt(result, state, messages) -> bool` defaults to False (:917-923). It is called at both finish points:
    - **The plain reply with no tool calls (:598):** when it returns True, the runtime appends the assistant reply after the hook returns (:599-601) and loops again.
    - **An accepted `isDone` (:673):** a True return goes to the "refused finish" path (:679-686), which adopts the catalog and continues.
  - `build_context` merges `managed_context.history + history + agent_history` (:257).
  - `__all__ = ["AgentRuntime"]` (:2303).
- **`vidbyte/agents/jev/runtime.py`**
  - Overrides `_continue_finish_attempt` (:252-279), where the continuation appends its message and returns True.
  - Overrides `_after_tool_iteration` (:282-290): forward to a controller, then `self.tools = self.compute.tools(self.tools)`.
- **`vidbyte/agents/infinite/runtime.py:45-118`**
  - The constructor refuses to build without its settings and workspace (:48-60). Its message starts "The 'infinite_memory' runtime is only available through InfiniteMemoryAgent".
  - `arun` does per-run setup around `super().arun` (:63).
  - `_after_tool_iteration` is overridden (:104).
- **`vidbyte/agents/infinite/agent.py`** (123 lines)
  - It takes only its settings object (:47-53).
  - It sets `session_persistence_supported = False` (:45); `Session` refuses such agents (`vidbyte/sessions/session.py:104-105`).
  - `super().__init__(runtime=AgentRuntimeType.INFINITE_MEMORY, tools=(*Toolset(...).all(), *settings.tools), permission_policy=..., agent_loop_settings=..., middleware=(...))` is at :70-87.
  - `_runtime_extension_kwargs` is at :89-92.
- **`vidbyte/agents/infinite/launch.py`**
  - Builds plain `BaseAgent` children with the parent's model, keys and policy, a fresh `ContextManager`, and per-child middleware (:252-291).
  - Runs pairs concurrently through `ParallelPipeline` (:144; `vidbyte/pipelines/parallel.py:28`).
  - Contains failures per pair with `except (VidbyteSdkError, OSError, ValueError)` (:244).
- **Actor runtime (`vidbyte/agents/runtimes/actor/`).** Do not change its semantics (request.md:153).
  - `ActorInbox` wraps `asyncio.Queue` with `put`, `get` and `empty` only (inbox.py:23-40).
  - `ActorMessage` is frozen without slots (message.py).
  - `AgentActor.start` loop (actor.py:66-92):
    - it calls `mark_busy` and then `on_receive`;
    - a non-empty reply is sent automatically back to `msg.sender`;
    - it calls `mark_idle` in `finally`;
    - an exception goes to `broker.fail(exc)`.
  - `on_receive` makes one completion and runs no tools (actor.py:94-105).
  - Quiescence is a 10 ms poll (broker.py:236-243). `_check_quiescence` requires message_count > 0, no busy actors, and all inboxes empty (:299-305).
  - P2P `send` to an unknown recipient is silently dropped; the span output is "missing_recipient" (:353-363).
  - `max_loop` counts every message (:333-339).
- **Events precedent**
  - `vidbyte/agents/multi/agent.py:65,93` declares `on_event: MultiAgentEventCallback | None`.
  - `vidbyte/lib/dataclasses/multi_agent.py:525-526` defines `EventHandler = Callable[[LedgerEvent, TaskLedgerSnapshot], None | Awaitable[None]]`, a two-argument callback.
  - Emission (`vidbyte/agents/multi/ledger_controller.py:160-174`):
    - each event is emitted at most once;
    - the callback is awaited via `AgentTransfer.maybe_await` (`vidbyte/agents/multi/transfer.py:145`);
    - an `Exception` is swallowed and its type appended to `state.event_error_types` (multi_agent.py:441).
  - Event retention is capped by `MultiAgentSettings.max_events = 500` (multi_agent.py:405).
- **Tools**
  - `BashTool(root_dir)`: name "bash", permission EXECUTE (`vidbyte/tools/builtins/bash.py:42, 82, 96`). It is not confined to `root_dir` and runs unsandboxed (`vidbyte/agents/README.md:144`).
  - `GrepTool(root_dir, ignore_patterns=…, max_file_bytes=…)`: "grep", READ (`vidbyte/tools/builtins/code_search/grep.py:30-32`). `GlobTool` is "glob", READ.
  - `ReadLinesTool(FileSystemToolConfig)`: "read_lines", READ.
  - `WriteTextTool`: "write_text", WRITE. Its refusal text names `replace_text`.
  - `ReplaceTextTool`: "replace_text", WRITE.
  - `PatchTool(root_dir)` (`vidbyte/tools/builtins/editing/patch.py:24-43`): model-facing name **`patch_file`**, WRITE, with flat params `file_path`, `search_block`, `replace_block`. Its descriptions are one sentence each (below S025's 4-sentence floor, so reusing it as-is adds nothing to the S025 count).
  - `FileSystemToolConfig(root, allow_write, max_overwrite_lines)` is at `vidbyte/lib/dataclasses/filesystem.py:66-102`.
  - `ParadigmMinimalToolset(root, include_execution=True, include_write=False)` contains glob, grep, read_text, read_lines, list_dir, tree, stat, `CodeExecutionTool` and `PatchTool` only when writing is allowed. It has no bash and no write_text (`vidbyte/tools/toolsets/paradigm_minimal.py:29-61`).
- **Search**
  - `PricedOperationTool` subclasses (Brave/Exa/Tavily in `vidbyte/tools/builtins/operations/search.py`) take `client=<Client>(api_key, retry=…)`. Without a client they return a priced contract stub (`vidbyte/tools/README.md:93-111`).
  - The key lives on the client, never discovered from env.
- **Permissions**
  - `PermissionPolicy()` allows SAFE and READ only (`vidbyte/lib/dataclasses/security.py:33-38`), so bash (EXECUTE) and write/patch (WRITE) are denied by default.
  - `allow_all()` is at :58-61.
  - A run-level `PermissionCeiling` caps every agent the run starts (:47-55).
- **Usage roll-up**
  - `BaseAgent.generate_reply` opens `usage_ledger_scope(self._usage_tracker)`. A nested agent merges its rollup into the active parent ledger in `finally` (`vidbyte/agents/base.py:852-889`, `_merge_usage_into` :897-905).
  - The helpers are in `vidbyte/lib/usage_ledger.py:42-48`.
- **History across runs**
  - `BaseAgent.history` (:272) gets each reply appended (:1007). `receive(message)` appends any `AgentMessage` (:849-850).
  - A later run's context includes `agent_history` (`vidbyte/agents/runtime.py:257`).
- **Middleware**
  - `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=…)` is at `vidbyte/middleware/compaction/context_compaction.py:111,163`.
  - `DelegationLimitsMiddleware` is at `vidbyte/middleware/builtins/delegation_limits.py:29`.
  - `AgentLoopSettings` (`vidbyte/agents/settings/loop.py:46-100`) has `max_iterations`, `max_tokens`, `max_tool_calls`, `timeout_seconds` and more.
- **Stop reasons:** `AgentStopReason` is at `vidbyte/lib/dataclasses/agents.py:61-80`. It includes FINAL_RESPONSE, IS_DONE, MAX_ITERATIONS, TIMEOUT, MIDDLEWARE_ABORT, ERROR and others.
- **Validation:** `RecordFieldValidator` and `RecordFieldConverter` are at `vidbyte/lib/dataclasses/validation.py:37-262`. They provide `require_text`, `require_text_items`, `require_int(minimum, maximum)`, `require_number(maximum)`, `require_bool`, `require_enum`, `require_directory`, `to_tuple`, `to_folder` and `require_instance`. Each error carries `details["field"]`.

## 3. Tests that cover those files

**Framework**

- pytest. `pyproject.toml:78-81` sets `testpaths=["tests"]`, `--strict-config --strict-markers`, `asyncio_default_fixture_loop_scope="function"`, and pins `pytest-asyncio==1.3.0` (:49).
- Older modules use `unittest.IsolatedAsyncioTestCase` (e.g. `tests/test_agent_tool_loop.py:50`).
- There is no `tests/conftest.py` and no `tests/fakes/` folder (verified by `ls`). The shared fakes are the helpers below.

**Offline model fakes (no real model calls)**

- **`tests/agent_test_support.py`** (73 lines)
  - `build_test_agent(..., runner=fake)` and `bind_test_runner(agent, runner)` put a fake into `agent._runner_cache[RUNNER_TYPE_TEXT]`.
  - `OfflineTestAgent.fork` keeps the fake when the model identity is unchanged.
- **`tests/features/infinite_memory_agent/infinite_memory_fixtures.py`** (556 lines). This is the closest match for N concurrent agents.
  - `ScriptedTree` patches `BaseAgent._runner_for_model` (:287-295), so every `BaseAgent`, including ones built at run time, gets `_ScriptedRunner(tree, agent.name)`. Its `arun(prompt, **options)` routes by agent name to a list of steps.
  - **Steps:**
    - `tool_call(name, args)` returns an OpenAI-responses-shaped `SimpleNamespace(raw={"output":[{"type":"function_call",…}]})` (:343-345);
    - `reply(text)` returns `TextModelResponse` (:341-342);
    - `fail(err)`;
    - `observe(action, then)`;
    - `after(Gate|Signal, then)`.
  - **Concurrency without sleeps:** `Gate(parties)` and `Signal(label)` are `asyncio.Event`s with a 20-second failure guard (:213-248).
  - **Recording:** `ModelCall(agent, prompt, system, messages, tools, tool_schemas)` (:254-263).
  - **Assertions:**
    - `assert_complete()` fails on unscripted calls, guard problems and unused steps (:363-368);
    - `tool_results`, `tool_result` and `is_error` (the `[tool_error` prefix) read the transcript (:374-388).
- **`tests/features/coding_agent/conftest.py`:** `ScriptedToolRunner` replays one tool call per turn and then `isDone`, in the OpenAI chat-completions shape (header :3-11).
- **`tests/test_agent_tool_loop.py:28-35`:** `ToolCallingRunner` pops `FakeResponse`s. :585 patches `AgentRuntime._continue_finish_attempt`.

**Existing tests that touch the files in section 2**

- **Runtime type and registry**
  - `tests/features/infinite_memory_agent/test_infinite_memory_contract.py:209-222`: `RuntimeRegistry.resolve(...) is InfiniteMemoryRuntime`, a plain `BaseAgent(runtime="infinite_memory")._runtime()` raises, and `fork()._runtime()` raises.
  - `tests/test_jev_agent.py` and `tests/test_agent_runtime.py` reference `AgentRuntimeType` and `RuntimeRegistry`.
- **Hooks**
  - `tests/test_jev_compute.py` covers `AgentRuntime._after_tool_iteration`. Its header :7 says: "The hook runs only after an iteration that ran tools and continues, never on a finishing iteration".
  - `tests/test_agent_tool_loop.py` covers `_continue_finish_attempt`.
- **Exports and contract:** `test_infinite_memory_contract.py:141-170` imports from every documented path, checks the names are in `vidbyte.lib.enums.__all__` and `vidbyte.__all__`, and reads `contracts/sdk-public-api.json` `exports`.
- **Prompt family**
  - `test_infinite_memory_contract.py:172-185` checks the exact leaf set against `Prompt.*` and `Prompts().family(...)`.
  - `tests/test_prompts_interface.py` (70 lines) checks the catalog interface. It has no count pin.
- **Enum values:** `test_infinite_memory_contract.py:188-206`.
- **Session opt-out:** `test_infinite_memory_contract.py:225-231`.
- **Complexity budget:** `test_infinite_memory_contract.py:471-480` (module count and at most 400 lines after the header).
- **Tools:**
  - `tests/test_patch_tool.py`;
  - `tests/test_filesystem_tools.py`;
  - `tests/test_code_search_tools.py`;
  - `tests/features/coding_agent/test_bash_tool_contract.py` and `test_bash_tool_process_bounds.py`;
  - `tests/test_exa_search_failure_metadata.py` and `tests/test_web_operation_client_retry.py` (search clients).
- **Validation:** `tests/test_record_field_validation.py`, if an option is added to `RecordFieldValidator`.
- **on_event:** `tests/multi_agent/test_behavior.py:178-187, 390-401` (an async `on_event(event, snapshot)` and ordering).
- **Actor runtime (must stay green):**
  - `tests/test_agent_runtime.py`, `tests/test_fork_tool.py` and `tests/features/system_prompt_presets/test_system_prompt_presets_propagation.py` reference the actor runtime classes and types;
  - `tests/test_restore_actor_include_actors.py`.
- **Feature-pack convention**
  - `tests/features/<feature>/` holds `README.md` (scope, File Index, Run, Logs), `FEATURE.md` (contract, invariants, failure modes, the test that catches each), a fixtures module, and `test_<feature>_<area>.py` files. See `tests/features/infinite_memory_agent/README.md:1-30`.
  - Feature symbols are imported inside each test, never at module level, so a missing feature fails per test and not at collection (fixtures header :8; contract header ARCHITECTURE NOTE).

**Exact commands** (from the files named; none was run)

- One pack: `PYTHONPATH=$(pwd) python -m pytest tests/features/<pack> -q` (`tests/features/infinite_memory_agent/README.md:24`). The bash cases need POSIX bash, or Git for Windows bash on Windows.
- One rule: `python lint/run.py --rule <ID>` (lint/README.md:31-36).
- Contract: `python scripts/generate-sdk-public-api.py --check`, and the same command without `--check` to regenerate after committing (contracts/README.md:26-29).
- Full gate from a worktree:
  - `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`;
  - then `python scripts/run_ci.py --stage package` with no `PYTHONPATH` (local-ci-verification.md:3-8).
  - `lint/README.md:41-44` shows the PowerShell form `$env:PYTHONPATH=(Get-Location).Path`.
- Semgrep: `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `semgrep==1.170.1` (local-ci-verification.md:10-15).

## 4. Notes for the spec author

**Contradictions between the request and the code**

1. **InfiniteMemoryAgent is merged.** The request assumes it is "still an open, unmerged PR (#1084 …) so nothing may import from it or depend on it" (request.md:49), and lists it under "Things not to touch: InfiniteMemoryAgent code on the unmerged branch" (request.md:152). The code shows it on main:
   - commit `2c84049c` "feat(agents): add InfiniteMemoryAgent … (#1084)" is an ancestor of HEAD;
   - `vidbyte/agents/infinite/` exists (8 modules);
   - it is wired into `RuntimeRegistry` (`vidbyte/lib/registries/runtimes.py:33,48`), `_LINEAR_LOOP_RUNTIMES` (`vidbyte/agents/base.py:83`), the root exports (`vidbyte/__init__.py:106-108, 758-761`) and the contract (`contracts/sdk-public-api.json:246-249`).

   The unmerged branch is still off-limits. Main's `vidbyte/agents/infinite/` is now the closest working precedent: a runtime subclass, a toolset, a settings record, lib records, enums, constants, a prompt family and a feature pack.
2. **PatchTool path and name.** The request assumes `PatchTool in vidbyte/tools/editing/patch.py` (request.md:140). The code shows it at `vidbyte/tools/builtins/editing/patch.py:24`, and `vidbyte/tools/editing/` does not exist. Its model-facing name is `patch_file`, not `patch` (:35).
3. **ParadigmMinimalToolset is not most of the toolset.** The request assumes it "may already be most of `AgentSwarmTools`" (request.md:141). The code shows it has no `bash` and no `write_text`: it adds `CodeExecutionTool` instead, and `PatchTool` only with `include_write=True` (`vidbyte/tools/toolsets/paradigm_minimal.py:46-61`). The toolset closest to bash+grep+read+write+patch is `CodingAgentTools.get_tools` (`vidbyte/tools/toolsets/coding.py:79-86`), which uses `replace_text`, not `patch_file`, for edits.
4. **Where `_after_tool_iteration` fires.** The request assumes it is "called after `middleware.after_iteration`" and is the place to drain the inbox (request.md:125). The code shows it fires only after an iteration that ran tools and continues (`vidbyte/agents/runtime.py:690-700`). It never fires when the model replies without tool calls or when `isDone` is accepted. Those two finish points call `_continue_finish_attempt` instead (:598, :673), which can append to `messages` and return True to keep the same loop running (JevRuntime does this, `vidbyte/agents/jev/runtime.py:252-279`). `tests/test_jev_compute.py:7` states the same fact.
5. **Messages cannot be appended "between tool calls".** The request assumes "Messages reach a busy agent between its tool calls" (request.md:59). The code shows no seam between individual tool calls of one iteration; the earliest seam is after the whole tool batch (:700). Separately, at the no-tool-call finish point, if `_continue_finish_attempt` returns True the runtime appends the assistant reply after the hook has already appended its own message (:598-600). So a message the hook appends lands before that reply, not after. The Jev precedent does exactly this: `JevDoneContinuation.continue_` appends `{"role": "user", …}` inside the hook (`vidbyte/agents/jev/continuation/done.py:86-92`, called from `vidbyte/agents/jev/runtime.py:276`). On main, the resulting order at that finish point is the user continuation message followed by the assistant reply, read from code and not executed.
6. **The actor runtime does not fit as-is.** The request assumes it offers `spawn`, `send`, `mark_busy`/`mark_idle`, `_check_quiescence` and `fail` that may be reusable (request.md:126-134). The code confirms the names. It also shows:
   - `ActorInbox` has no non-blocking get or drain (inbox.py:30-40);
   - the actor loop auto-replies to the sender (actor.py:77-84);
   - an unknown P2P recipient is silently dropped (broker.py:353-363);
   - quiescence is a 10 ms sleep poll (broker.py:236-243);
   - `max_loop` counts messages, not turns (broker.py:333-339);
   - the actor files use the old "Context Protocol Header" that A001 counts against the baseline.
7. **The tools are denied by default.** The request assumes agents can use bash, write and patch (request.md:56). The code shows a default `BaseAgent` policy `PermissionPolicy()` allows SAFE and READ only (`vidbyte/lib/dataclasses/security.py:36-38`; `vidbyte/agents/base.py:214`), so EXECUTE (bash) and WRITE (write_text/patch_file) are denied unless the swarm sets a policy. Infinite and Coding default to `allow_all` (`vidbyte/agents/infinite/settings.py:122`; `vidbyte/agents/README.md:142`).
8. **Bash is not confined to the workplace.** The request assumes "Every agent's tools are rooted in the same directory" (request.md:51). The code shows `bash` "is not confined to `root_dir`, and it runs unsandboxed with the inherited environment" (`vidbyte/agents/README.md:144`). Its root is only the working directory. The infinite README notes that bash can write past every workspace rule (`vidbyte/agents/infinite/README.md:106`).
9. **The callback signature differs from the precedent.** The request assumes "an optional on_event callback (the pattern MultiAgent already uses)" (request.md:54). The code shows MultiAgent's callback takes two arguments, `(event, snapshot)` (`vidbyte/lib/dataclasses/multi_agent.py:525`). Its `LedgerEvent.kind` is matched as a plain string in tests (`tests/multi_agent/test_behavior.py:179`), which predates the enum rule. A new event kind must be an enum in `vidbyte/lib/enums/` (AGENTS.md:61-63).
10. **The name "swarm" is taken.** The request assumes the feature is new. The code shows "swarm" already names JevAgent's SWARM dynamic-compute option:
    - `JevSwarm*` classes;
    - `launch_swarm` tool (`REPO_MAP.md:401`);
    - `jev_swarm` prompt family (`vidbyte/prompts/README.md:76, 291-300`);
    - `JevSwarmPlanQuestionKey` (`vidbyte/lib/enums/__init__.py:110,250`).

    No `AgentSwarm*` name exists yet. A new `swarm` module or prompt family key must not collide with `jev_swarm`.
11. **base.py and runtime.py are already oversized.** The request assumes files stay "well under 1,000 lines" (request.md:92). The code shows `vidbyte/agents/runtime.py` (2,304 lines) and `vidbyte/agents/base.py` (1,830 lines) are already far over. Anything added to either should be a one-line hook or set entry, as the Jev and Infinite precedents did.
12. **The stop-reason enum predates the placement rule.** The request assumes there is a stop reason on the result (request.md:164). The code shows `AgentStopReason` is defined in `vidbyte/lib/dataclasses/agents.py:61`, before the rule existed. Adding a member there is allowed (AGENTS.md:81). A new swarm stop-reason enum must go in `vidbyte/lib/enums/`.
13. **A public class named `…Runner`, `…Agent`, `…Harness`, `…Session` or `…Machine` needs a `run()` twin.** C011 requires any public class with one of those suffixes and an `arun()` to also have `run()` (`lint/rules/c011_agent_owned_usage_and_sync_twins.py:30`). The request's `arun("goal")` does not mention `run`. Class names ending in `Swarm` or `Runtime` are outside that suffix list.
14. **Agent tests use different fakes.** The request assumes the scout would locate "fake or scripted model-client test patterns" (request.md:97). The code shows `REPO_MAP.md:61` describes "a shared layer of fakes and fixtures", but there is no `tests/fakes/` or root `tests/conftest.py`. The fakes are `tests/agent_test_support.py`, `tests/features/coding_agent/conftest.py` and `tests/features/infinite_memory_agent/infinite_memory_fixtures.py` (`ScriptedTree`, routed by agent name, with Gate and Signal).

**Facts the spec author needs**

- Each `BaseAgent` keeps `history` across runs (base.py:272, 1007), and `receive(AgentMessage)` appends to it (:849-850). A later `arun` includes that history in context (runtime.py:257).
- Concurrent runs on one agent keep their own prompt (base.py:274-276 `@intent`).
- Nested agents started inside a run merge their usage into the run's active ledger exactly once (base.py:852-889).
- `ParallelPipeline` is used from the agents layer by Infinite (launch.py:66,144). A006 treats agents and pipelines as one tier, so no A006 finding results.
- `Session` refuses agents with `session_persistence_supported = False` (session.py:104-105). Infinite, Codex and MultiAgent all opt out.
- `PermissionCeiling` caps every agent a run starts (security.py:47-55).
- The prompt enum header counts (139 assets, 35 families) are right today and must be bumped by hand. Nothing tests them.

**unverified:**

- unverified: the message order at the no-tool-call finish point when `state.inner_context_window_algorithm` is set (runtime.py:582-583, 589-590 branch differently), which was not traced.
- unverified: whether `BaseAgent.arun` can be cancelled cleanly mid-tool-call on Windows for `bash`. The CodingAgent and Infinite READMEs say a cancelled bash command may keep running on Windows (`vidbyte/agents/README.md:149`; `vidbyte/agents/infinite/README.md:107`), but no test was read.
- unverified: whether `GrepTool` and `GlobTool` refuse paths outside `root_dir` (only `code_search/base.py` constructor lines were re-checked this pass).
- unverified: the prose rules for a `REPO_MAP.md` entry (`field-guide/vidbyte-sdk/agents-md-map.md` not opened; only its one-line summary at init.md:25).
- unverified: how much of a prior run's tool transcript (`_tool_call_contexts`, passed as `existing_tool_calls`, base.py:1286) a later `arun` replays to the model.
- unverified: the `.semgrep/` policy file contents. Only its name was taken from local-ci-verification.md.
