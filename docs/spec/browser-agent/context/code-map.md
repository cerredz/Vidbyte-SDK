# BrowserAgent code map (S0 scout)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-browser-agent`, branch `feat/browser-agent`, HEAD `08f67e7f4a6fb3e0c524d476965f82d28d89e941` (= origin/main). Every `path:line` below is a file I opened in this worktree. Anything I did not open is marked "unverified". No file under `vidbyte/agents/browser/` exists yet (`ls` fails). The scout report with the read list and line counts is `docs/spec/browser-agent/reports/S0-scout.md`.

## 1. Rules, commands, and conventions that bind this change

### 1.1 Gate and commands as AGENTS.md states them

AGENTS.md (81 lines) gives exactly one command. Under the heading **"## Repository Map"**:

> "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."

Other binding lines under the same heading:
- "**Do not grep, glob, or read files under `docs/` as part of ordinary work**" (the spec folder is the pipeline's own exception).
- "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder. Its closing `## Notes for agents` section, where one exists, records mistakes that review has already caught there" and "lint rule A009 keeps every folder README at or under 40,000 characters".
- Read `REPO_MAP.md` "before you create a file, move code, or search for where something lives".

AGENTS.md states **no** install command, **no** lint command, **no** single-test or area-test command, and **no** commit or PR convention. The commands below come from the files named next to each one.

### 1.2 What `python scripts/run_ci.py` runs (`scripts/run_ci.py`, 287 lines)

- Flags: `--stage all|source|package` (default `all`) and `--dist-dir`.
- Source stage (`scripts/run_ci.py:79-93`), in order:
  1. no tracked bytecode;
  2. `lint/run.py`;
  3. `compileall`;
  4. `scripts/check_context_write_paths.py`;
  5. `scripts/check_context_primitive_introductions.py`;
  6. `scripts/check_reasoning_trace_contracts.py`;
  7. `pytest`.
- Package stage (`scripts/run_ci.py:95-115`): build sdist and wheel, `twine check`, assert the wheel contains `vidbyte/prompts/prompts/error_correction_auditor.md`, then install into a clean venv and run a smoke import.
- Pytest config (`pyproject.toml` `[tool.pytest.ini_options]`): `testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]`, `asyncio_default_fixture_loop_scope = "function"`.
- Dev pins: `pytest==8.3.5`, `pytest-asyncio==1.3.0`, `ruff==0.16.4`, `mypy==2.3.1`. `requires-python >=3.11`; version `0.3.0`.

### 1.3 Lint (`lint/run.py`, 75 lines) and the rule IDs that bite this change

- Flags: `--rule <ID>`, `--format text|json`, `--all`, `--update-baseline`. Focused form: `python lint/run.py --rule A006`. Rule modules are in `lint/rules/`; I read each module's docstring.
- **A001**: every new module needs a docstring header with non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:` and `TESTS:` (`lint/rules/a001_agent_readable_file_headers.py:24-32`). Siblings also carry `FUNCTION INVENTORY:` and `WHAT NOT TO DO`; see `vidbyte/lib/constants/infinite.py` and `vidbyte/tools/toolsets/coding.py:3-11`.
- **A002**: a function handling retries, permissions, pricing, redaction, persistence, state or boundary policy needs a `# @intent <name>` comment within 20 lines of its `def` (`lint/rules/a002_intent_comments.py:23-24`).
- **A003**: a new class in `vidbyte/lib/errors/base.py` needs the literal `DIAGNOSTIC_FIELDS` packet.
- **A006**: directed layer graph; `vidbyte/lib` never imports upward. A registry imports agent classes via the package `__init__` only.
- **A007**: operational numbers (timeouts, limits, budgets, truncation) must be named constants.
- **A009**: README ≤ 40,000 characters. Current sizes: `vidbyte/agents/README.md` is 29,527 characters and `vidbyte/prompts/README.md` is 31,924.
- **C001**: no `raise ConfigurationError` inside a plain `*Settings` class body. Validation belongs to a dataclass `__post_init__`.
- **C002**: no duplicate `isinstance(x, bool)` guard for the same identity.
- **C008**: primitive validators (positive int, finite number, bool, timeout, limit) have one owner. Use `RecordFieldValidator` instead of a private copy.
- **C011**: every model call's usage reaches the agent's `UsageTracker`, and a public class ending in `Agent`, `Runner`, `Harness`, `Session` or `Machine` that defines `arun()` also needs a sync `run()` (`lint/rules/c011_agent_owned_usage_and_sync_twins.py:26-30`).
- **C015**: package-data coverage. Prompt `.md`/`.json` files ship through `pyproject.toml` `"vidbyte.prompts.prompts" = ["*.json", "*.md", "*/*.json", "*/*.md"]`.
- **C016**: `contracts/sdk-public-api.json` must equal the generator's output for `vidbyte/__init__.py` `__all__`.
- **S008**: function complexity. **S024**: nesting depth.
- **S015**: every `__all__` entry is statically bound.
- **S020**: README File Index parity, opt-in per README. Only a README with a File Index heading is checked.
- **S025**: model-facing tool and parameter description depth.
- **S039**: banned APIs. **S060**: no `dict[str, Any]` in public-seam signatures.
- **S051**: import sorting, checked with ruff (see 1.4).
- Comment blocks are wrapped at 72 columns (field guide `comment-format.md`; not a lint rule).

### 1.4 Worktree gate commands (field guide `local-ci-verification.md`, recorded next to AGENTS.md; AGENTS.md wins on conflict)

- Source stage: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`. Package stage: `python scripts/run_ci.py --stage package`, with no `PYTHONPATH`.
  - **Check:** `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` must print the worktree path. The shared Python has an editable install that resolves `import vidbyte` to the canonical checkout.
- Semgrep: run `git add -A` first, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, with `semgrep==1.170.1`.
  - **Check:** scan the new path explicitly and confirm the rule ran on it. Semgrep scans only tracked files.
- S051: `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, filtered to your own paths.
  - **Check:** S051 returns to its baseline count.
- Two `harness_threads` surface tests fail locally on any branch that touches `vidbyte/tools`, `vidbyte/lib/configs`, or root exports. They are pre-existing.
  - **Check:** a control edit on main fails the same way.
- After every merge of main: run the feature tests and `scripts/generate-sdk-public-api.py --check`.
  - **Check:** the feature tests pass on the merge commit itself.
- `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` is flaky on CI 3.11. Rerun it before investigating.
- Merge: `gh pr merge <n> --squash --admin --match-head-commit <sha>` after re-dispatching both workflows on the exact head.

### 1.5 AGENTS.md style principles (heading "## General Coding Style Guidelines")

- "### 1. Keep Call Chains One Level Deep": "one main function that calls a flat list of helpers, where each helper does its job and returns without calling further helpers of its own". It also says to avoid nested functions unless an API requires a callback.
- "### 2. Narrate Main Functions in Plain English": short plain-English comments throughout each main function's body.
- "### 3. Build in Layers of Small, Single-Purpose Classes": "`vidbyte/lib/` is the bottom layer … nothing in `vidbyte/lib/` may import from a layer above it" and "Keep files well below 1,000 lines". If describing a class needs the word "and", it is probably two classes.
- "### 4. Use Validated Dataclasses for Core Inputs and Outputs": "Prefer `@dataclass(frozen=True, slots=True)`", validated in `__post_init__`, with closed sets typed as enums.
- "### 5. Write Shared Logic Once, as a Canonical Helper in `lib/`": search `vidbyte/lib/` first and extend what exists with an option.

### 1.6 AGENTS.md Placement Rules (heading "## Placement Rules"; binding and enforced by the "AGENTS.md placement" workflow)

- "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`** … Do not create `types.py`, `records.py`, `models.py`, or `schemas.py` modules next to the code that uses the dataclass."
- Exception 1: "**Agent settings objects.** A `*Settings` class that configures an agent lives in `vidbyte/agents/settings/`, or in the owning agent's own `settings.py`."
- "**Every new enum … is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions." Any closed-set field, parameter or registry key is typed with such an enum.
- Under "### New JEV code": "**A new Jev-facing prompt** is a new family under `vidbyte/prompts/prompts/`, with its key in `vidbyte/lib/enums/prompts.py`." The same pattern is what Infinite used.
- "### Existing code": modules on main that define dataclasses or enums elsewhere predate the rules and are "not precedent". `McpServerConfig` and `McpToolPermission` in `vidbyte/tools/mcp/types.py:31-47`, and `CompactionMode` in `vidbyte/middleware/compaction/base.py`, are such cases.

### 1.7 Field-guide entries that apply, each with its quick check (the entry's **Check:** line)

The field guide (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/init.md`) is an index of topic files. Each entry has a **Do** line and a **Check** line. The "quick check" is that **Check** line, quoted here.

- `runtime-boundaries.md`, "A specialized agent's runtime is its own AgentRuntimeType, not a class-override hook". Do: add an enum member and a `RuntimeRegistry.resolve` row, pass kwargs through `_runtime_extension_kwargs()`, add the member to `_LINEAR_LOOP_RUNTIMES`, and refuse to build without settings.
  - **Check:** "`RuntimeRegistry.resolve(AgentRuntimeType.X)` is the subclass; `BaseAgent(runtime="x")._runtime()` raises a message naming the real agent; runtime tests keep usage/speed tracker identity."
- `runtime-boundaries.md`, "Narrow runtime state for one run inside try/finally".
  - **Check:** "A test runs a restricted run, then a normal run on the same agent, and asserts the second sees the full tool list and prompt."
- `runtime-boundaries.md`, "Enforce a deterministic tool-call cap in middleware; the prompt carries only behavior". Do: `MiddlewareDecision.deny_tool(reason, metadata={"limit": ...})` in `before_tool_call`; prompts carry no numbers.
  - **Check:** "`grep -rn "format(max_" vidbyte/agents/<agent>` is empty. A test calls the tool past each cap and sees `Tool denied by middleware` naming the limit, with nothing started or journaled."
- `runtime-boundaries.md`, "Reuse shared context compaction infrastructure".
  - **Check:** "Compaction metadata is preserved, provider message order remains valid, and no bespoke compaction algorithm is introduced."
- `runtime-boundaries.md`, "Keep model usage accounting agent-owned".
  - **Check:** "Runtime metadata and the agent usage API expose the same rollup without duplicate records."
- `runtime-boundaries.md`, "Don't duplicate general agent/loop budget settings in a sub-runtime's own Params".
  - **Check:** "Grep the new `Params` dataclass's fields against `AgentLoopSettings` and any active middleware".
- `prompt-families.md`, "Each prompt leaf is its own sectioned Markdown file that states only behavior the code has". Do: `<leaf>.md` files plus a family JSON of `{path, source_url}`; no numeric limits in prose.
  - **Check:** "The family JSON has no inline text, the leaf-count contract test passes, and S025 and A009 pass."
- `prebuilt-agents.md`, "A prebuilt agent's preloaded tools live in a `<Agent>Tools(Tools)` catalog under `vidbyte/tools/toolsets/`".
  - **Check:** "The agent module imports no tool classes except the toolset. `repr(agent.export_state())` and `repr(agent.tools)` contain no key."
- `prebuilt-agents.md`, "An SDK agent runs from Python only; never add a `vidbyte-sdk` command for it".
  - **Check:** "`git ls-files vidbyte/cli` lists only `README.md`, `__init__.py`, `__main__.py`, and `skills.py`."
- `model-facing-tool-contracts.md`, "Make tool schemas teach the model the complete event contract". Do: 6–9 meaningful fields, 4–5 sentence descriptions, no examples.
  - **Check:** "Inspect every ToolSpec for field count, description length, example-free prose, and validation/rendering parity; keep shared enums and constants under `vidbyte/lib`."
- `model-facing-tool-contracts.md`, "Centralize categorical vocabularies".
  - **Check:** "Search the tool module for local categorical literal tuples and compare the generated parser choices with the enum values."
- `strict-config-dataclasses.md`, "A BaseAgent subclass gathers its own constructor arguments into one lib record and passes BaseAgent's through".
  - **Check:** "`__init__` contains no `raise`. … `repr(settings)` shows no key."
- `strict-config-dataclasses.md`, "Validate record fields through RecordFieldValidator / RecordFieldConverter".
  - **Check:** "The record module defines no `_..._field` helpers."
- `strict-config-dataclasses.md`, "Keep reusable validation bounds in the shared constants package".
  - **Check:** "each validation comparison should reference the feature's constants module."
- `strict-config-dataclasses.md`, "Size a scale-oriented agent's default caps generously, then fit the history cap to the context budget".
  - **Check:** "No test pins a cap with a literal. The constants header states the token budget sum."
- `class-bound-helpers.md`, "Prefer a static helper class over a bag of module-level free functions".
  - **Check:** "The module's public `__all__` exports the class (and constants)".
- `class-bound-helpers.md`, "Search `vidbyte/lib/` before creating a "new" canonical module".
  - **Check:** "`git status` shows existing lib modules as modified with additive diffs, never rewritten."
- `blocking-lint-invariants.md`, "A lib registry reaches an agents-layer class through its package `__init__`".
  - **Check:** "`python lint/run.py --rule A006`."
- `blocking-lint-invariants.md`, "Lib records can't expose a `dict[str, Any]` wire encoder, and `typing.TypedDict` is banned".
  - **Check:** "`python lint/run.py --rule S060` and `--rule S039` stay at their baselines."
- `blocking-lint-invariants.md`, "A003 requires the full DIAGNOSTIC_FIELDS packet".
  - **Check:** "`python lint/run.py --rule A003`".
- `jev-capability-layout.md`, "Continuation logic lives in a `JevContinuation` subclass; `JevRuntime` only asks and delegates".
  - **Check:** "`grep -n "check(" vidbyte/agents/jev/runtime.py` finds nothing".
- `jev-capability-layout.md`, "A Jev capability module holds no module-level constants or type aliases".
  - **Check:** "The top level of the capability module holds only imports, the class, and `__all__`."
- `jev-capability-layout.md`, "A capability's main function catches Jev failures once, at its top level".
  - **Check:** "No `try` sits inside a `for` loop in the main function."
- `jev-capability-layout.md`, "Work that splits across fresh agents is a main-agent tool run through pipelines, not a planner".
  - **Check:** "No planner agent, queue, or plan record. The module stays near 150 lines".
- `comment-format.md`, "A multi-line comment is a PEP 8 block of at most 72 columns".
  - **Check:** "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched."
- `review-scope.md`, "This PR overcomplicated it".
  - **Check:** "Every file in the diff is traceable to a review comment or to the feature's minimal surface (settings, gate, runtime, tests, docs)."

### 1.8 Commits and PRs

AGENTS.md states no commit or PR convention. The orchestrator's trailer is `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Regenerating `contracts/sdk-public-api.json` needs a commit first: `scripts/generate-sdk-public-api.py` refuses to write while its inputs differ from HEAD ("Commit the source change first, then rerun"). The implementer therefore commits the export change and then regenerates the contract in a follow-up commit.

## 2. Files this change will touch

Format: `path` — what it does today — what changes — the pattern to follow.

### 2.1 Existing files that get a row, member, or export

- `vidbyte/lib/enums/agent_runtime.py` (55 lines)
  - Today: `AgentRuntimeType(str, Enum)` at :43-52 holds `LINEAR`, `MCTS_SEARCH`, three actor members, `JEV = "jev"` (:51) and `INFINITE_MEMORY = "infinite_memory"` (:52).
  - Change: a `BROWSER` member.
  - Pattern: the `INFINITE_MEMORY = "infinite_memory"` line.
- `vidbyte/lib/registries/runtimes.py` (69 lines)
  - Today: `RuntimeRegistry.resolve` (:30-56) lazy-imports `from vidbyte.agents.infinite import InfiniteMemoryRuntime` and `from vidbyte.agents.jev import JevRuntime` inside the method, then maps them in one `_registry` dict (`AgentRuntimeType.JEV: JevRuntime`, `AgentRuntimeType.INFINITE_MEMORY: InfiniteMemoryRuntime`). An unknown type raises `ConfigurationError(f"Unknown runtime type '{runtime_type.value}'. Supported: …")`.
  - Change: one import from the `vidbyte.agents.browser` package `__init__` and one dict row.
- `vidbyte/agents/base.py` (1830 lines)
  - Today: `_LINEAR_LOOP_RUNTIMES = frozenset({AgentRuntimeType.LINEAR, AgentRuntimeType.JEV, AgentRuntimeType.INFINITE_MEMORY})` (:83), with its comment block at :80-82. The set is read at :243, :1435 and :1478.
  - Change: add `BROWSER` to the set and its comment.
  - Hooks the runtime uses but does not change:
    - `_runtime()` (:1408-1461) builds the runtime per call, merging `_runtime_extension_kwargs()` (:1463-1465, default `{}`) with `output_contract`, `usage_tracker`, `speed_tracker`, `fallback` and `agent_catalog`.
    - `generate_reply` (:852-890) opens the usage ledger and merges a nested agent's usage into the active parent ledger (:873-885, `_merge_usage_into(parent)`).
    - `_generate_reply` awaits `_ensure_mcp_connected` (:916).
    - `run()` (:1107-1114) and `arun()` (:1098).
    - `_output_contract_with_schema` (:1486-1494).
    - `_runner_for_model` (:1659) is the test seam.
- `vidbyte/lib/enums/__init__.py` (304 lines)
  - Today: a domain import block, e.g. `from vidbyte.lib.enums.infinite import (InfiniteAgentRole, …)` at :80-86, plus an alphabetical `__all__` (Infinite names at :223-228; `AgentRuntimeType` at :183).
  - Change: an import block for `vidbyte.lib.enums.browser` and `__all__` rows.
- `vidbyte/lib/enums/prompts.py` (218 lines)
  - Today: `Prompt(str, Enum)` (:65-206). A member value is `"<family_key>.<leaf>"`, e.g. `GOALS_GOAL_PROMPT` (:161) and the `INFINITE_MEMORY_*` members (:113-152). The header's hand-kept counts read "139 static prompt assets across 35" families (:7-8); :45-46 says to reconcile them after additions.
  - Change: one member per new leaf, plus the header counts.
- `vidbyte/agents/__init__.py`
  - Today: eager imports `from vidbyte.agents.infinite import (InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteMemoryRuntime, InfiniteWorkspaceSettings)` (:84-89) and `from vidbyte.agents.jev import (…)` (:90-). `__all__` starts at :308; the Infinite names are at :392-395.
  - Change: an import block and `__all__` rows.
- `vidbyte/__init__.py`
  - Today: the header line "Agent exports: … InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings, InfiniteMemoryPreset …" (:12); eager imports from `vidbyte.agents` (:104-112); enum import `InfiniteMemoryPreset` (:472); `__all__` (:731), with the Infinite names at :758-764.
  - Change: same three places.
- `contracts/sdk-public-api.json`
  - Today: generated from root `__all__`; the Infinite names are at lines 246-257.
  - Change: regenerate with `scripts/generate-sdk-public-api.py`, after a commit (see 1.8). C016 fails while it is stale.
- `vidbyte/tools/toolsets/__init__.py` (26 lines)
  - Today: exports `CodingAgentTools`, `InfiniteMemoryAgentTools` and `ParadigmMinimalToolset`.
  - Change, only if `BrowserAgentTools` follows `prebuilt-agents.md` into `vidbyte/tools/toolsets/browser.py`: an export row. See §4 item 9.
- `REPO_MAP.md` (423 lines)
  - Today: one `##### \`vidbyte/agents/<pkg>/\`` heading per agent package, followed by one paragraph of 5–6 sentences (Infinite at :83-85, Jev at :87-89).
  - Change: a `##### \`vidbyte/agents/browser/\`` row. The toolsets row (:359-361) says "It holds three such bundles", and the constants row (:187-189) lists domains; both may need a word if files land there.
- `vidbyte/agents/README.md` (405 lines, 29,527 characters)
  - Today: a "## InfiniteMemory Agent" section with a usage snippet (:151-181) and a Key Modules bullet (:394). It has no File Index.
  - Change: a section and a bullet, staying under A009's 40,000 characters.
- `vidbyte/prompts/README.md` (484 lines, 31,924 characters)
  - Today: a quick reference table row per family (goals :65, infinite_memory :67); a per-family description, e.g. "#### InfiniteMemory Agent — `infinite_memory`" (:229-250); Key Modules (:473-478).
  - Change: a table row and a family section.

### 2.2 New files and the sibling each one follows

- `vidbyte/agents/browser/agent.py` (new). Siblings: `vidbyte/agents/jev/agent.py` (132 lines) and `vidbyte/agents/infinite/agent.py` (123 lines).
  - `JevAgent.__init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings | None = None)` (:35-106) does four things:
    - refuses a wrong type with `ConfigurationError("JevAgent requires a JevAgentSettings instance.")` (:39-40);
    - builds `self._response = JevResponse()` (:47);
    - calls `super().__init__(name=…, runtime=AgentRuntimeType.JEV, tools=settings.tools, permission_policy=…, agent_loop_settings=settings.loop, api_keys=settings.api_keys, model_mode=…, provider=…, model_name=…, temperature=…, timeout_seconds=…, outputs=…, system_prompt_presets=…)` (:91-106);
    - returns its collaborators from `_runtime_extension_kwargs` (:127-129).
  - `InfiniteMemoryAgent` (:42) sets `session_persistence_supported = False` (:45) and refuses a wrong type at :53 with `f"InfiniteMemoryAgent requires an InfiniteMemoryAgentSettings instance; got {type(settings).__name__}."`.
- `vidbyte/agents/browser/runtime.py` (new). Siblings: `vidbyte/agents/jev/runtime.py` (293 lines) and `vidbyte/agents/infinite/runtime.py` (118 lines).
  - Jev `__init__(*, runtime_settings=None, …, **kwargs)` (:43-84) refuses without settings (:60-74) with "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev')." and sets `self.usage = JevUsageAccount(self.usage_tracker, self.agent_name)` (:84).
  - Jev `arun` (:86-102) wraps `_arun_metered` (:104-155) in the usage scope. `_arun_metered` calls `self.response.start(message)` (:118) and `super().arun(...)` (:145), and returns `self.response.finished(result, self.usage.settle())` (:155).
  - Jev narrows tools per run with `replace(context, tools=…)` in `_keep_read_only_tools` (:171-180).
  - Jev's finish hook `_continue_finish_attempt` is at :252-279 and `_after_tool_iteration` at :282-290.
  - Infinite `__init__(*, settings=None, workspace=None, resuming=None, **kwargs)` (:48) refuses at :54. It refuses a caller tool that takes a reserved name at :72, using `INFINITE_RESERVED_TOOL_NAMES`.
  - Infinite re-renders a top-of-context card in `_after_tool_iteration` (:104-110) via `self.context_manager.upsert(self._map(), placement=ContextWindowPlacement.TOP_OF_CONTEXT)`. `_map()` (:112-115) returns `TextContextItem(title=…, content=…, primitive_id=INFINITE_MAP_PRIMITIVE_ID)`.
  - Infinite copies the context manager per run (:92-93).
- `vidbyte/agents/browser/settings.py` (new; the settings exception to the dataclass rule). Siblings: `vidbyte/agents/jev/settings.py` (417 lines) and `vidbyte/agents/infinite/settings.py` (208 lines).
  - Infinite settings are `@dataclass(frozen=True, slots=True)` (:57 and :102), with `api_keys: ProviderKeys | Iterable[str | None] | None = field(default_factory=ProviderKeys, repr=False)` (:118) and `vidbyte_api_key: str | None = field(default=None, repr=False)` (:133).
  - `__post_init__` (:136) calls `ProviderKeyMatcher.match(self.api_keys, primary=self.provider, vidbyte_api_key=self.vidbyte_api_key, field_name="InfiniteMemoryAgentSettings.api_keys")` (:170) and `RecordFieldValidator.require_int(getattr(self, name), f"InfiniteMemoryAgentSettings.{name}", minimum=…)` (:200).
  - In Jev settings the equivalent fields are at :139, :149 and :166. `JevRunBriefSettings` (:285-339) shows the optional per-role provider/model override pattern.
  - Another key-holding record: `vidbyte/lib/dataclasses/coding.py:54-57` declares `firecrawl_api_key`, `browserbase_api_key`, `parallel_api_key` and `tavily_api_key`, each `field(default=None, repr=False)`. `_check_fetch_keys` raises errors that "name the parameter, never the value".
- `vidbyte/agents/browser/usage.py` (new). Sibling: `vidbyte/agents/jev/usage.py` (94 lines).
  - `JevUsageAccount(tracker, agent_name)` provides `scope()` (:33-37), which wraps `usage_ledger_scope(self._tracker)` from `vidbyte/lib/usage_ledger.py:48`.
  - `require_accounted()` (:39-58) raises `UsageAccountingError` (`vidbyte/lib/errors/base.py:506-537`) when `failures(rollup)` (:74) is non-empty, including `UNPRICED_CALL` (:79, `unpriced` :84).
  - Other methods: `report()`, `settle()`.
- `vidbyte/agents/browser/response.py` (new). Sibling: `vidbyte/agents/jev/response.py` (157 lines).
  - `JevResponse` (:44-154) is the one writer: `start(message)`, one method per event, then `finished(result, usage)`. `_with_usage` adds `"usage_rollup": usage.total` to the metadata.
  - The record it builds is read through `JevAgent.response` (`agent.py:108-111`).
- `vidbyte/agents/browser/events.py` (new). There is no sibling on main; see §4 item 3. The nearest callback shape is `MultiAgent.__init__(…, on_event: MultiAgentEventCallback | None = None, …)` (`vidbyte/agents/multi/agent.py:65`), stored at :93.
- Browser tools catalog (new; location open, see §4 item 9).
  - Field-guide sibling: `vidbyte/tools/toolsets/infinite.py` (53 lines). `InfiniteMemoryAgentTools(Tools)` has `__init__` and a static `get_tools(...)`, and its header says "Do not import from vidbyte.agents".
  - `vidbyte/tools/toolsets/coding.py` (138 lines) has `authenticate_tools(settings)` plus `get_tools(...)`; its header (:8) says "Do not read fetch keys from environment variables" and "Do not keep the settings record or a key on the catalog".
  - Infinite's model-facing tool spec reads its descriptions from the prompt family (`vidbyte/agents/infinite/launch.py:105-115`).
- `vidbyte/agents/browser/README.md` (new). Sibling: `vidbyte/agents/infinite/README.md` (115 lines), with `## File Index` (:91-101), checked by S020, and `## Notes for agents` (:103-115). `vidbyte/agents/jev/README.md` (55 lines) has neither.
- `vidbyte/agents/browser/__init__.py` (new). Siblings: `vidbyte/agents/infinite/__init__.py` (26 lines) and `vidbyte/agents/jev/__init__.py` (281 lines, with a docstring header and re-exports of lib records and enums). The registry imports the runtime from this `__init__` (A006).
- `vidbyte/lib/dataclasses/browser.py` (new). Sibling: `vidbyte/lib/dataclasses/infinite.py` (189 lines): six frozen slotted records with tuple fields only. Its header says "Do not add to_dict or from_dict methods or dict[str, Any] signatures". It is not exported from `vidbyte/lib/dataclasses/__init__`. Field checks go through `vidbyte/lib/dataclasses/validation.py` (262 lines):
  - `RecordFieldValidator` (:37-158):
    - `require_text(value, field_name, *, max_chars=None, pattern=None, allow_blank=False, one_line=False)`;
    - `require_text_items(value, field_name, *, max_items=None, max_chars=None, pattern=None, one_line=False)`, which accepts a tuple only;
    - `require_number(value, field_name, *, maximum)`;
    - `require_int(value, field_name, *, minimum, maximum=None)`;
    - `require_bool`;
    - `require_enum(value, enum_type, field_name)`;
    - `require_instance(value, field_name, expected, *, optional=False)`.
  - `RecordFieldConverter` (:161-259): `to_mapping(value, field_name) -> MappingProxyType[str, str]`, `to_enum`, `to_folder`.
  - All of these raise `ConfigurationError(..., details={"field": field_name})`.
- `vidbyte/lib/enums/browser.py` (new). Sibling: `vidbyte/lib/enums/infinite.py` (70 lines): six `str, Enum` classes, e.g. `InfiniteJournalEvent` (:53-59).
- `vidbyte/lib/constants/browser.py` (new). Sibling: `vidbyte/lib/constants/infinite.py` (195 lines).
  - Its docstring header carries the cap arithmetic ("sized for a 128,000-token model… about 105,000 tokens").
  - Constants are grouped under comments, e.g. `INFINITE_HISTORY_MAX_TOKENS = 90_000` (:72), `INFINITE_RESERVED_TOOL_NAMES` (:104-109) and `INFINITE_MAP_PRIMITIVE_ID = "infinite_memory_map"` (:126); `__all__` is at :138-195.
  - `vidbyte/lib/constants/__init__.py` (167 lines) re-exports only codex, cot_events, failure, reasoning_strategies, runners and speed. The infinite and jev constants are imported from their own modules.
- `vidbyte/prompts/prompts/<family>/<family>.json` plus `<leaf>.md` (new). Sibling: `vidbyte/prompts/prompts/infinite_memory/`. Its `infinite_memory.json` (167 lines) has 40 leaves of `{path, source_url}`. Its `root_system_prompt.md` (72 lines) has sectioned role text, and `launch_tool_description.md` (15 lines) has the sections What it does / When to use it / How it behaves / Rules and refusals.
  - Loader: `Prompts._load` (`vidbyte/prompts/catalog.py:85-126`) finds `*.json` at the top level or one directory deep (:128-138) and requires `name`, `description`, `key` and a non-empty `prompts` (:147-157).
  - A leaf `path` must end in `.md` (:166-181). Every enum member needs an asset and every asset needs a member, or the import fails (:107-111, :189-193). The call is `Prompts().get(Prompt.X)` (:34-38).
- `tests/features/browser_agent/` (new). See §3.

### 2.3 Neighbours the change reads from (no edits expected)

- `vidbyte/agents/runtime.py` (2304 lines): the inherited linear loop.
  - `_arun_once` (:297-707).
  - `_continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool` (:917-923) returns False. It is called at :598 (final text answer) and :673 (isDone). Returning True sends the loop back to work with whatever the hook appended to `messages`.
  - `_after_tool_iteration(state, messages)` (:925-931) is called at :700.
  - `_build_iteration_call_options` (:1596-1618) adds `response_format` at :1616-1617.
  - `_build_system_string` (:1668-1677) renders the context manager into the system string, and `_build_conversation_messages` (:1655-1661) builds the conversation.
  - `_final_result` (:1703-1735).
  - `_process_tool_call` (:1737-1825) appends via `_append_tool_result_message` (:1935-1953), which calls `ToolsFormatter.format_tool_result(call, visible_result, provider)` and `messages.append(dict(formatted))`. History is `list[dict[str, Any]]` of provider-formatted messages.
  - `_apply_before_model_call_transform` (:1085-1094) rewrites only the outgoing call's `messages`, not the stored history.
  - `_budget_stop` (:2046-2089).
- `vidbyte/agents/mixins.py` (388 lines): MCP lifecycle.
  - `attach_mcp_servers` (:97-145) is all-or-nothing and raises `McpAttachmentError`.
  - `_ensure_mcp_connected` (:200-244).
  - `_run_releasing_mcp` (:246-262) closes the servers and re-queues their configs after each sync `run()`.
  - `mcp_servers()` (:264-266) returns the handles.
  - Fork helpers are at :277-290, `close_mcp_servers` at :292-305, and `__aexit__` closes the servers (:387-388).
- `vidbyte/agents/fork.py` (252 lines): a fork re-queues the parent's MCP configs (:98-99), so it gets new subprocesses, and drops the parent's bridged MCP tools (:176-188).
- `vidbyte/tools/mcp/`:
  - `types.py` (71 lines): `McpToolPermission` (:31-36); `McpServerConfig(command, name=None, permission=EXECUTE, env=None, timeout=30.0)` (:39-47), frozen with no validation; `McpServerHandle(config, client, transport, bridged_tools)` (:50-71) with `name` and `tool_names`.
  - `attach.py` (105 lines): `attach_mcp_server` (:35-105).
  - `bridge.py` (133 lines): `McpBridgedTool(BaseTool)` (:29) takes its name from the raw remote name, with spec metadata `{"source": "mcp"}`; `execute` is at :61-69; `McpToolBridge` is at :112.
  - `client.py` (173 lines): `max_output_chars=8000` (:31); `call_tool` (:90-115); `_content_to_text` (:124-173).
  - `presets.py` (502 lines): `McpPresetRegistry.get` (:370-374), `list_presets` (:377-381) and `build_config(preset_name, env=None, permission=EXECUTE, timeout=30.0, extra_args=None)` (:384-421).
  - `transport.py` (507 lines): the env allowlist (:34-62) and `build_child_env` (:80-89).
  - `README.md` (169 lines).
- `vidbyte/lib/config/mcp_presets.py` (1833 lines): `McpPresetDefinition(name, category, description, command, required_env, optional_env=(), default_env=None, docs_url=None)` (:25-35); the browser, search and fetch presets are listed in §4 item 7.
- `vidbyte/lib/errors/base.py` (615 lines):
  - `ConfigurationError(VidbyteSdkError)` (:289-290) has no packet; `VidbyteSdkError(message, *, details=None)` is at :68-75.
  - MCP family: `McpError` (:260) through `McpAttachmentError` (:280-286); `McpProtocolError` is at :130.
  - `OutputSchemaViolationError` (:178-186).
- `vidbyte/agents/settings/loop.py` (235 lines): `AgentLoopSettings`, a plain class whose fields are at :49-67 (`max_iterations`, `max_tokens`, `max_tool_calls`, …, `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens`, `allowed_tools`, `tool_settings`, `output_contracts`, `max_contract_rejections=3`).
- Middleware:
  - `vidbyte/middleware/builtins/delegation_limits.py` (74 lines): `DelegationLimitsMiddleware(limits, *, depth)`, whose `before_tool_call` returns `deny_tool(…, metadata={"limit": "max_depth"|"max_parallel", …})` (:29-71).
  - `vidbyte/lib/dataclasses/middleware.py`: `MiddlewareDecision.continue_` (:94), `abort` (:120) and `deny_tool` (:134); `DelegationLimits` (:240).
  - `token_budget.py` (116 lines) and `cost_budget.py` (96 lines).
- `vidbyte/agents/jev/done/reviewer.py` (73 lines): the worked example of a fresh-context, tool-free, structured side agent.
  - `JevReviewer(BaseAgent)` passes `output_schema=JevReviewPayload` (:44) and `system_prompt_presets=()` (:48), and calls `history.clear()` (:54).
  - It runs `await self.arun(AgentInput(prompt=request, context_manager=window))` (:57) and checks `isinstance(reply.structured, …)` (:58).
  - It fails open on `VidbyteSdkError` (:67-70).
- `vidbyte/agents/jev/continuation/base.py` (40 lines) and `fresh.py` (129 lines): `JevContinuation(ABC)` (:24-37) defines `should_continue`, `budget_extension` and `continue_`. `JevFreshContinuation` (:31-126) runs a fresh `BaseAgent` and appends its reply as `{"role": "user", …}` (:85-86).
- `vidbyte/context/manager.py` (372 lines):
  - `copy` (:62-70).
  - `upsert(item, *, placement=END_OF_CONTEXT)` (:72-90) requires a `primitive_id` and raises on a frozen record.
  - `remove_by_id` (:157-161).
  - `render_primitives_zone` (:208-217) emits "## Context Window Primitives" and "### [id] title".
- `vidbyte/context/runtime.py`: `ContextWindowPlacement` (:30-36). `vidbyte/context/primitives/documents.py`: `TextContextItem` (:56-65).
- `vidbyte/lib/util/text.py`: `TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4` (:68); `TokenEstimate` (:88) with `count` (:92), `cut` (:97) and `cap(text, max_tokens, marker)` (:104).
- `vidbyte/middleware/compaction/context_compaction.py` (562 lines):
  - `MessageHistoryCompactionMiddleware` (:111). Its constructors include `trim_with_provider_boundaries(max_messages=None, max_tokens=None, token_counter=None)` (:163), `tool_output_sliding_window(keep_recent=2, window_mode=TRUNCATE_TOOL_RESULTS, max_chars=600)` (:173-175), `clear_tool_results_except(exclude_tools=…)` (:178-180), `scrub_bloat` (:188-190) and `trim_to_token_budget` (:158-160).
  - `before_model_call` (:217-229) compacts `ctx.provider_messages` for the outgoing call only.
  - The sliding window lives in `ToolOutputSlidingWindowCompaction` (`vidbyte/middleware/compaction/strategies.py:663-695`). It keeps `keep_recent` results **per tool name**.
- `vidbyte/tools/function_tool.py` (263 lines) and `vidbyte/tools/decorators.py` (44 lines):
  - `FunctionTool(func, *, name=None, description=None, permission=ToolPermission.SAFE, output_schema=None)` (:24-143) validates arguments in pydantic JSON mode (:194-203) and keeps a raised `ToolExecutionError`'s kind (:78-90).
  - `@tool` is at `decorators.py:23-37`.
  - `vidbyte/tools/catalog.py` (164 lines): `Tools(Sequence[BaseTool])` raises `ToolRegistrationError("Tool already exists: …")` on a duplicate name (:37-38).

## 3. Tests that cover those files

### 3.1 The pack to model: `tests/features/infinite_memory_agent/`

- Files:
  - `README.md` (30 lines; sections Folder Description / Intent, File Index, Run, Logs);
  - `FEATURE.md` (128 lines; sections High-Level Feature Description, Contract, Actors / Callers, Inputs and Preconditions, Observable Outcomes, State Transitions, Invariants, External Dependencies, Known Failure Modes, Historical Regressions, Test Suite Map, Omitted Testing Strategies);
  - `infinite_memory_fixtures.py` (556 lines);
  - `test_infinite_memory_{acceptance,context,contract,delegation,resume,verification,workspace}.py` (180, 85, 493, 609, 392, 308 and 671 lines).
- Framework: pytest with plain `def test_…` functions and `@pytest.mark.parametrize`. There is one `@pytest.mark.asyncio` (`test_infinite_memory_delegation.py:95`) and no custom markers (`--strict-markers` is on). There is no `tests/conftest.py` and no `tests/features/conftest.py`.
- Model fake: `ScriptedTree` (`infinite_memory_fixtures.py:275`) routes one script per **agent name**. `install()` patches the model seam for every agent at once (:287-295):
  ```python
  def runner_for(agent: BaseAgent) -> tuple[object, str]:
      return _ScriptedRunner(tree, agent.name), RUNNER_TYPE_TEXT
  with patch.object(BaseAgent, "_runner_for_model", new=runner_for): ...
  ```
  - Step helpers: `tool_call(name, args, usage=None)` (:135), `reply(text, usage=None)` (:140) and `fail(error)` (:145). `ModelCall` (:255) records `agent, prompt, system, messages, tools, tool_schemas`. `Gate` (:213) and `Signal` (:231) order concurrent agents without sleeps (`GUARD_SECONDS = 20.0`, :46).
  - A reply step returns `TextModelResponse(provider=ModelProvider.OPENAI, model=MODEL, text=…, raw={}, usage=…)`. A tool step returns `raw={"output": [{"type": "function_call", "name": …, "arguments": json.dumps(args), "call_id": …}]}` (:337-346).
  - The fixtures say: "Do not import anything from vidbyte.agents.infinite… at module level". The pack is written red, before the implementation.
- Contract tests to mirror in `test_infinite_memory_contract.py`:
  - `test_public_names_import_from_every_documented_path` (:141) reads `contracts/sdk-public-api.json`;
  - `test_prompt_family_has_exactly_the_forty_documented_leaves` (:172);
  - `test_enum_values_are_the_documented_lowercase_strings` (:188);
  - `test_runtime_type_resolves_and_refuses_outside_its_agent` (:209): the message starts "The 'infinite_memory' runtime is only available through InfiniteMemoryAgent", and `agent.fork()._runtime()` raises too;
  - `test_session_refuses_the_agent` (:225);
  - `test_loop_and_limit_defaults_match_the_spec` (:234);
  - `test_construction_rejects_each_invalid_setting` (:282-283, parametrized);
  - `test_construction_rejects_a_non_settings_object` (:296);
  - `test_launch_and_remember_schemas_follow_the_documented_shape` (:393);
  - `test_token_estimate_counts_characters_and_cuts_to_a_prefix` (:427);
  - `test_prompt_family_text_carries_no_coding_only_rules` (:452);
  - `test_new_modules_stay_inside_the_complexity_budget` (:471): at most 8 modules, each at most 400 lines after the header.
- `FEATURE.md` "Omitted Testing Strategies" says MCP servers are omitted: "tools added with add_tool take the same path into the catalog … so no MCP server is started".

### 3.2 MCP fakes (no real server, no subprocess)

- Patch the transport class that `attach.py` constructs. Shape: `tests/test_mcp_attachment.py` (640 lines).
  - `MockMcpStdioTransport` (:49-106) takes `command`, `env`, `request_timeout`, …; implements `start`, `request(method, params)` for `initialize`, `tools/list` and `tools/call`, and `close`; and records every instance in `instances`.
  - Activate it with `@patch("vidbyte.tools.mcp.attach.McpStdioTransport", MockMcpStdioTransport)` (:119).
  - The test then calls `await agent.attach_mcp_server(command=["myserver"])` on `build_test_agent(name=…, system_prompt=…, runner=DoneRunner())` from `tests/agent_test_support.py:68` (73 lines).
  - The same file's header lists a test for an attach "whose bridged tool name is already taken, which must attach no server".
- `TwoToolMcpTransport(MockMcpStdioTransport)` (`tests/test_agent_fork_isolation.py:119`) is patched the same way (:382). `tests/test_fork_tool.py:466` does the same.
- Client-level fakes: `FakeTransport` (`tests/test_mcp_bridge.py:30`, 318 lines) implements `async request(method, params)` and is used as `McpClient(FakeTransport())` with `McpToolBridge(registry, client, permission=…).bridge()` (:165-166).
  - `test_binary_content_is_replaced_by_placeholder` (:175) pins the image placeholder.
- Other runner fakes: `FakeRunner` and `RecordingRunner` (`tests/test_agent_runtime.py:61`, `:67`); `FakeRunner` (`tests/test_agent_tool.py:35`); `RecordingRunner` (`tests/test_jev_compute_clone.py:35`); `RecordingTracer` (`tests/test_agent_fork_isolation.py:131`); `RecordingModel` (`tests/features/system_prompt_presets/fakes.py:39`).

### 3.3 Commands

- One pack (from `tests/features/infinite_memory_agent/README.md:24`): `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`.
- One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_resume.py -q`.
- By analogy for the new pack: `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q`.
- Neighbour tests the change can break: `tests/test_mcp_attachment.py`, `tests/test_mcp_bridge.py`, `tests/test_agent_fork_isolation.py`, `tests/test_agent_runtime.py`, and the infinite and jev packs, which also touch `_LINEAR_LOOP_RUNTIMES` and the registry.
- All tests: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` (its last step is `pytest`).
- AGENTS.md does not mandate `tests/features/` packs. It names no test layout. On main there are 21 packs under `tests/features/`, among them `infinite_memory_agent`, `coding_agent`, `jev_*` and `sdk_*`.

## 4. Notes for the spec author (contradictions and gaps only)

1. **Screenshots.** The request assumes the worker "runs its 25 actions with screenshots" (§B) and that the observation diet prunes "whatever shape arrives" (§C).
   - The code shows that `McpClient._content_to_text` turns every `image` or `audio` block into the text `[image: <mime>, <n> base64 chars omitted]` (`vidbyte/tools/mcp/client.py:136-143`, `@intent mcp-binary-content-stays-out-of-prompts`) and truncates the whole result to 8,000 characters (`client.py:31`, `:109-111`).
   - The loop stores only provider-formatted text dicts (`vidbyte/agents/runtime.py:1935-1953`). No model in the SDK sees MCP screenshot pixels through the bridge today.
   - Where "observation" text arrives, it is a text snapshot, truncated at 8,000 characters.
2. **Keys from the environment.** The request says (§C) that a preset's `required_env` counts as satisfied when the key is "present in env or in os.environ".
   - `McpPresetRegistry.build_config` checks only `preset.default_env` merged with the caller's `env` (`vidbyte/tools/mcp/presets.py:400-404`). It raises `McpPresetConfigurationError(f"Preset '{preset_name}' requires the following environment variables: …")`, class at :104.
   - The server subprocess gets an allowlisted environment (`vidbyte/tools/mcp/transport.py:34-62`, `build_child_env` :80-89), so a key that is only in `os.environ` does not reach the server unless it is passed in `env`.
   - `vidbyte/tools/toolsets/coding.py:8` says "Do not read fetch keys from environment variables".
3. **Events.** The request names `InfiniteEvents` as the sibling for the events shape. It is not on main: no `InfiniteEvents`, no `JevEvents`, and no `on_event` on `JevAgent` or `InfiniteMemoryAgent` at `08f67e7f`. The only `on_event` is `MultiAgent` (`vidbyte/agents/multi/agent.py:65`). `InfiniteJournalEvent` (`vidbyte/lib/enums/infinite.py:53-59`) is a journal-record enum, not a sink.
4. **One shared browser session across orchestrator and workers.**
   - `BaseAgent.run()` closes every MCP server after each sync run (`vidbyte/agents/base.py:1107-1114` → `vidbyte/agents/mixins.py:246-262`). Servers stay open only across `arun()` or `async with` (`mixins.py:387-388`).
   - A fork starts new server subprocesses (`vidbyte/agents/fork.py:98-99`) and drops the parent's bridged tools (`fork.py:176-188`), so a worker built by `fork()` does not share the parent's browser.
   - `BaseAgent._own_tool` (`base.py:473-493`) passes non-builtin tool objects such as `McpBridgedTool` through unchanged, so a separately built `BaseAgent(tools=[…bridged tools…])` reuses the same client object.
   - The transport is bound to the event loop that started it (`transport.py:152-170`).
   - Unverified: whether two agents calling one stdio client concurrently is safe.
5. **Partition by role.**
   - Bridged tool names are the raw server names with no prefix (`vidbyte/tools/mcp/bridge.py`), so two servers that both expose, for example, `navigate` collide. `Tools` raises `ToolRegistrationError("Tool already exists: …")` (`vidbyte/tools/catalog.py:37-38`), and an attach whose tool name is taken attaches no server (`tests/test_mcp_attachment.py` header).
   - `vidbyte/tools/mcp/README.md:124-127` says disambiguation belongs in `attach.py`, and none exists.
   - The object that maps a tool back to its server is `McpServerHandle.bridged_tools` / `tool_names` (`vidbyte/tools/mcp/types.py:50-71`). `McpBridgedTool` itself carries no server or role field.
   - The agent's own tool names (for example the orchestrator tools) can also collide with server tool names. Infinite refuses reserved names at `vidbyte/agents/infinite/runtime.py:72`.
6. **Observation diet.** The request assumes "keep only the latest N observations".
   - The closest helper on main is `MessageHistoryCompactionMiddleware.tool_output_sliding_window(keep_recent=…)` (`vidbyte/middleware/compaction/context_compaction.py:173-175`). It keeps the newest `keep_recent` results **per tool name** (`vidbyte/middleware/compaction/strategies.py:683-695`), not N across all observation tools. It compacts the outgoing call only, and stored history is unchanged (`vidbyte/agents/runtime.py:1085-1094`).
   - `clear_tool_results_except(exclude_tools)` (:178-180) clears all but named tools.
7. **Presets.**
   - The `playwright` preset runs `("python", "-m", "mcp_server_playwright")` (`vidbyte/lib/config/mcp_presets.py:89-95`), not `npx @playwright/mcp`. `puppeteer` runs `npx -y @modelcontextprotocol/server-puppeteer` (:81-87). Both have `required_env=()`.
   - `browserbase` requires `BROWSERBASE_API_KEY` and `BROWSERBASE_PROJECT_ID` (:961-967). `firecrawl` requires `FIRECRAWL_API_KEY` (:105-111), `jina_reader` requires `JINA_API_KEY` (:113-119), `brave_search` requires `BRAVE_API_KEY` (:41-47), `tavily` requires `TAVILY_API_KEY` (:57-63), `exa` requires `EXA_API_KEY` (:65-71), `duckduckgo` requires none (:73-79) and `apify` requires `APIFY_API_TOKEN` (:953-959).
   - `McpPresetDefinition` has a `category` (:25-35) but no role.
   - Unverified: the tool names each real server exposes. Fakes must invent them.
8. **Usage pricing.**
   - MCP tool calls carry no price: `McpBridgedTool(BaseTool)` (`bridge.py:29`) is not a `PricedOperationTool`. `JevUsageAccount.require_accounted` (`vidbyte/agents/jev/usage.py:39-58`) fails closed on unpriced **model** calls only.
   - Vendor-billed MCP calls (Browserbase, Firecrawl) are invisible to the usage ledger.
   - The SDK already has native priced fetch tools for Firecrawl, Browserbase, Parallel and Tavily (`vidbyte/tools/builtins/operations/fetch.py`, used by `vidbyte/tools/toolsets/coding.py:29-36`), outside MCP.
   - Worker usage reaches the parent through the active ledger (`base.py:873-885`, `vidbyte/lib/usage_ledger.py:42-48`).
9. **Where `BrowserAgentTools` lives.** The areas hint puts it at `vidbyte/agents/browser/tools.py`. `prebuilt-agents.md` puts `<Agent>Tools(Tools)` in `vidbyte/tools/toolsets/<agent>.py`, with the check "The agent module imports no tool classes except the toolset". Both Infinite (`vidbyte/tools/toolsets/infinite.py`) and Coding follow the field guide.
10. **README File Index.** The request says the folder README has "a File Index and `## Notes for agents`". Jev's README has neither (`vidbyte/agents/jev/README.md`, 55 lines). Infinite's has both (:91-101, :103-115). Once a File Index exists, S020 enforces parity with the folder's files.
11. **Recheck "on a cheap model".** The request wants a fresh-context, tool-free structured call.
    - On main this is a `BaseAgent` with `output_schema=` (`vidbyte/agents/jev/done/reviewer.py:44-58`), resolved per provider by `StructuredOutputRegistry.resolve` (`vidbyte/lib/registries/structured_output.py:45-54`) into the tiers `NATIVE_SCHEMA | STRICT_TOOLS | JSON_MODE | PROMPT_ONLY` (`vidbyte/lib/enums/structured_output.py:22-32`).
    - A schema miss raises `OutputSchemaViolationError` (`base.py:1060-1076`).
    - The `goals/` family is not a recheck prompt. `vidbyte/prompts/prompts/goals/goal_prompt.md` (27 lines) is a Codex `/goal` emulation system prompt with no placeholders ("You do not claim to have Codex's native /goal tool"). It is keyed `Prompt.GOALS_GOAL_PROMPT` (`vidbyte/lib/enums/prompts.py:161`). Unverified: its consumers.
    - `jev_continuation/continue_prompt.md` takes `{request}{run_state}{handoff}{failed}{focus}`.
    - Side agents inherit the run's system-prompt presets (`base.py:866-871`). `JevReviewer` passes `system_prompt_presets=()` (`reviewer.py:48`); unverified whether `()` opts out.
12. **Context rebuild trigger.**
    - `AgentLoopSettings.compaction_trigger_tokens` and `context_window_budget` are stored and exported (`base.py:317-323`, `:630-631`, `:671-673`, `:762-763`), but I found no consumer in `vidbyte/agents/runtime.py` or `vidbyte/middleware/` (a git grep for `compaction_trigger` outside `loop.py` hits only base.py, fork.py and `lib/constants/codex.py`).
    - History-size tools that do exist: `TokenEstimate` (`vidbyte/lib/util/text.py:88-104`, 4 characters per token); `AgentRuntime._approx_output_tokens` (`runtime.py:2169-2172`); `TokenBudgetMiddleware(*, max_tokens, abort_reason="token_budget_exceeded", allow_final_response_over_budget=False)` (`vidbyte/middleware/builtins/token_budget.py:40-113`), which aborts rather than rebuilding; and `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries` (used by Infinite workers at `vidbyte/agents/infinite/launch.py:277-291`).
13. **Hard caps.** The request puts the action cap in `AgentLoopSettings(max_iterations=…)` and the caps in `vidbyte/lib/constants/browser.py`.
    - `runtime-boundaries.md` says a numeric cap on a **tool call** is a middleware `deny_tool`, and prompts must carry no numbers.
    - `AgentLoopSettings` counts iterations and tool calls (`max_tool_calls`, `vidbyte/agents/settings/loop.py:49-67`), not screenshots. No screenshot counter exists on main.
14. **Session opt-out.** `InfiniteMemoryAgent` sets `session_persistence_supported = False` (`vidbyte/agents/infinite/agent.py:45`), and its contract test pins the refusal. `JevAgent` does not set it. The request does not say which way `BrowserAgent` goes.
15. **Gate gaps.** AGENTS.md gives only `python scripts/run_ci.py`. The worktree `PYTHONPATH` split, semgrep's tracked-files rule, and `generate-sdk-public-api.py --check` come from the field guide. A commit is needed before `contracts/sdk-public-api.json` can be regenerated (`scripts/generate-sdk-public-api.py` refuses uncommitted inputs).
16. **Hand-kept counts.** `vidbyte/lib/enums/prompts.py:7-8` ("139 static prompt assets across 35" families) and `REPO_MAP.md:361` ("It holds three such bundles") are maintained by hand.
17. **`types.py` precedent.** `vidbyte/tools/mcp/types.py` defines `McpServerConfig` and `McpToolPermission` outside `vidbyte/lib/`. That predates the Placement Rules and is "not precedent" (AGENTS.md "### Existing code").
