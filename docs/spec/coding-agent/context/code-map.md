# Code map: coding-agent (S0 scout, 2026-10-10)

Repo: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent` (worktree of vidbyte-sdk 0.2.0, `requires-python >=3.11`). I opened every path below in this session. Anything I could not confirm is marked "unverified".

## 1. Rules, commands, and conventions from AGENTS.md that bind this change

### Binding text from AGENTS.md (73 lines)

- Repository Map (`AGENTS.md:9`): "Read it before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs." `REPO_MAP.md` works at folder level. It has a **File Index** and **JEV File Locations**.
- Opaque docs (`AGENTS.md:11`): "**Do not grep, glob, or read files under `docs/` as part of ordinary work**".
- Full gate (`AGENTS.md:11`): "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- Style 1, Keep Call Chains One Level Deep (`AGENTS.md:19-21`): a helper must not call another helper of its own. Calls into another class, a lower layer, or the stdlib do not count. Do not define functions inside other functions unless an API requires a callback or decorator.
- Style 2, Narrate Main Functions in Plain English (`AGENTS.md:23-25`): put short plain-English comments throughout each main function.
- Style 3, Build in Layers of Small, Single-Purpose Classes (`AGENTS.md:27-29`): "`vidbyte/lib/` is the bottom layer, domain packages such as `agents/`, `tools/`, and `context/` build on it … nothing in `vidbyte/lib/` may import from a layer above it." Imports must not form a cycle.
- Style 4, Use Validated Dataclasses for Core Inputs and Outputs (`AGENTS.md:31-33`): use `@dataclass(frozen=True, slots=True)` with strict `__post_init__` validation. Type closed-set fields with enums.
- Placement, dataclasses (`AGENTS.md:37-49`): "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`**". Never create `types.py`, `records.py`, `models.py`, or `schemas.py`. There are two exceptions:
  - a `*Settings` class that configures an agent, which lives in `vidbyte/agents/settings/` or the agent's own `settings.py`;
  - JEV preflight questions.
- Placement, enums (`AGENTS.md:51-55`): "**Every new enum … is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
- Existing code (`AGENTS.md:71-73`): "Many modules on `main` still define dataclasses or enums outside these two folders … Do not copy them as precedent."
- The `AGENTS.md placement` workflow enforces Placement Rules (`AGENTS.md:13`). `.github/workflows/agents-md-placement.yml` is workflow_dispatch only.
- AGENTS.md has no install command, no test command, no commit or PR convention, and no constants-placement rule except the JEV one (`vidbyte/lib/constants/jev.py`, `AGENTS.md:61`).

### Commands (from `scripts/run_ci.py`, `.github/workflows/*.yml`, `pyproject.toml`)

- Install the dev extra (as in ci.yml): `python -m pip install -e ".[dev]"`. The dev extra pins `build==1.5.0`, `mypy==2.3.1`, `pytest==8.3.5`, `pytest-asyncio==1.3.0`, `ruff==0.16.4`, and `twine==6.2.0`.
- Full gate: `python scripts/run_ci.py`. It accepts `--stage {all,source,package}` (default `all`) and `--dist-dir`.
- Source stage (`scripts/run_ci.py:79-93`) runs these steps in order:
  1. checks that no bytecode is tracked;
  2. `lint/run.py`;
  3. `compileall vidbyte`;
  4. `scripts/check_context_write_paths.py`;
  5. `scripts/check_context_primitive_introductions.py`;
  6. `scripts/check_reasoning_trace_contracts.py`;
  7. `python -m pytest`.
- Package stage (`scripts/run_ci.py:95-218`):
  1. build;
  2. twine check;
  3. wheel inspection, which requires `vidbyte/prompts/prompts/error_correction_auditor.md`;
  4. clean venv install;
  5. `pip check`;
  6. a smoke import with `PYTHONPATH` popped.
- Lint: `python lint/run.py`, or for one rule, `python lint/run.py --rule <ID>`. Lint is count-ratcheted against `lint/baseline.json` and scans only `git ls-files` output, so a new untracked file passes silently until `git add`.
- Public API contract: `python scripts/generate-sdk-public-api.py` writes `contracts/sdk-public-api.json`. `--check` verifies it (lint C016, baseline 0). The generator refuses to run while `vidbyte/__init__.py` or `pyproject.toml` is uncommitted.
- CI (`.github/workflows/ci.yml`) triggers only on workflow_dispatch and workflow_call:
  - the source job runs on ubuntu-latest with Python 3.11 and 3.12, doing `pip install -e ".[dev]"` and then `python scripts/run_ci.py --stage source`;
  - the package job runs on 3.11: `--stage package --dist-dir dist`.
- Semgrep is **not** in run_ci.py. It runs only in `.github/workflows/static-policy.yml` (dispatch only), with `semgrep==1.170.1`:
  - `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`
  - `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
  - The rule `no-untyped-mapping-fallback` flags an `object`/`Any` parameter followed by an `isinstance(..., Mapping/dict)` fallback.

### Lint rules a new agent, tool, or test file must satisfy (read from `lint/rules/*.py`; baselines from `lint/baseline.json`)

- **A001** file header. The module docstring needs non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, and `TESTS:`. It scans `vidbyte/`, `tests/`, and `scripts/`. Baseline 643.
- **A002** `# @intent <name>` comment. It must sit within [def-4, def+20] for any function whose identifier tokens include retry, backoff, attempt, permission, authorize, pricing/price/billing, redact, secret, persist, checkpoint, fallback, transition, transport, request, fetch, send, urlopen, provider, subprocess, or mcp. Identifiers like `create_subprocess_exec` and `permission_policy` match. Baseline 703.
- **A006** layer direction and no concrete import cycles (agents and tools are orchestration-tier; lib, providers, sessions, and sources are lower). Baseline 34.
- **A007** no bare numeric literal near timeout/retry/attempt/backoff/delay/token/char/byte/truncate/limit/budget/status/depth/interval tokens, or in such parameter defaults. Use UPPERCASE named constants. Baseline 255.
- **A008** no `print()` outside `vidbyte/cli/`. Baseline 3.
- **C001** no `raise ConfigurationError` inside a non-dataclass `*Settings` class. Baseline 26.
- **C016** `contracts/sdk-public-api.json` must equal the generator output. Baseline 0.
- **S006** (RUF006) no orphan `create_task`. Baseline 0.
- **S007** (ANN) annotate public functions. Baseline 16.
- **S008** complexity (C901/PLR0912/PLR0915). Baseline 19.
- **S012** calls named `request`, `request_bytes`, `stream_request`, `upload_multipart`, or `urlopen` need a `timeout`/`timeout_seconds` keyword (`lint/rules/s012_explicit_outbound_timeout.py:22-23`). Baseline 0.
- **S013** `.request`, `.request_bytes`, and `.stream_request` calls need `max_response_bytes`, but only under `vidbyte/tools/builtins/code_search/`, `vidbyte/tools/builtins/mcp/`, `vidbyte/tools/builtins/operations/`, and `vidbyte/tools/mcp/` (`lint/rules/s013_bounded_untrusted_responses.py:22-23`). Baseline 4.
- **S015** `__all__` entries are unique and bound, and every public name imported into `vidbyte/__init__.py` is listed in its `__all__`. Baseline 13.
- **S016** no raising builtin `Exception`/`RuntimeError`/`TypeError`/`ValueError` in `vidbyte/tools/builtins/` and other scoped dirs. Baseline 50.
- **S017** no `str(exc)` or `f"{exc}"` inside except handlers passed to `*Error(...)`, `.error(...)`, `_failed_result(...)`, or returned, within `vidbyte/tools/` and other scoped dirs. Baseline 79. The existing filesystem tools and DirectHttpFetchTool do this and are baselined.
- **S019** in async code, `CancelledError`/`BaseException`/bare `except` must re-raise. Baseline 5.
- **S020** `## File Index` README parity applies only to `vidbyte/agents/codex`, `vidbyte/agents/multi`, `vidbyte/config`, and `vidbyte/workflows`. Baseline 1.
- **S025** every `BaseTool` subclass's `ToolSpec.description` and each `ToolParameter.description` needs at least 4 sentences, with no examples. Baseline 263.
- **S039** banned APIs: `typing.TypedDict`, `typing.assert_never`, and `asyncio.Lock`. Baseline 5.
- **S041** no unspecified encoding. Baseline 0.
- **S045** (ASYNC109) an async function that takes a timeout-like parameter. Baseline 2. Ruff decides which names count (`lint/rules/s045_async_function_with_timeout.py:9`).
- **S047** (ASYNC230) no `open()` in async functions. Baseline 0.
- **S051** import sorting (I001). Baseline 259.
- **S052** (ASYNC100/105/110/220/221) no blocking subprocess calls in async functions. Baseline 0.
- **S054** (S105–108, S301/302, S501). Baseline 3.
- **S055** forbids `subprocess.*(shell=True)`, `os.system`, and `asyncio.create_subprocess_shell`. Baseline 0.
- **S060** bans `dict[str, Any]` in `vidbyte/lib/dataclasses`.
- **S061** no `open()`/`write_text`/`read_text` with a non-literal first argument unless the receiver is `.backend`. Baseline 6.

### Field-guide entries that bind this change

These are from `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`. Each check is quoted from the entry's "**Check:**" line.

- `local-ci-verification.md`, "Run the source stage with `PYTHONPATH=<worktree>` and the package stage without it". Check: "`PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` must print the worktree path."
- `local-ci-verification.md`, "Semgrep only scans git-tracked files; `git add` new files before trusting a clean scan". Check: "Scan the new path explicitly (`semgrep … <new-file>`) and confirm the rule ran on it."
- `local-ci-verification.md`, "`tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` is flaky on CI Python 3.11". Check: "Green on rerun with no code change."
- `local-ci-verification.md`, "Stage conflict resolutions before running the lint gate mid-merge". Check: "`git ls-files -u | wc -l` prints 0 before trusting a lint verdict."
- `local-ci-verification.md`, "Check S051 import sorting with ruff over the whole `vidbyte` tree, not on single files". Check: "S051 returns to its baseline count."
- `blocking-lint-invariants.md`, "S012 flags any method named `request` as an outbound call without a timeout". Check: "`python lint/run.py --rule S012`."
- `blocking-lint-invariants.md`, "A006 treats vidbyte.sessions as a lower layer than vidbyte.middleware …". Check: "`python lint/run.py --rule A006` after any change that adds an import between `vidbyte/sessions/`, `vidbyte/providers/`, or `vidbyte/sources/` (all lower-layer) and `vidbyte/agents/`, … `vidbyte/tools/`, …"
- `blocking-lint-invariants.md`, "Lib records can't expose a `dict[str, Any]` wire encoder, and `typing.TypedDict` is banned". Check: "`python lint/run.py --rule S060` and `--rule S039` stay at their baselines."
- `model-facing-tool-contracts.md`, "Make tool schemas teach the model the complete event contract". The Do line asks for 4–5 sentence descriptions for the tool and each parameter, with no examples. Check: "Inspect every ToolSpec for field count, description length, example-free prose, and validation/rendering parity; keep shared enums and constants under `vidbyte/lib`."
- `model-facing-tool-contracts.md`, "Centralize categorical vocabularies". Check: "Search the tool module for local categorical literal tuples and compare the generated parser choices with the enum values."
- `priced-operation-execution.md`, "Inject execution without replacing a priced SDK tool". Check: "Every prebuilt search/fetch tool supports the seam, default runtime behavior is unchanged, executor exceptions are redacted, and usage comes from SDK metadata."
- `provider-api-contracts.md`, "One guarded try per provider call, with typed branches and a detailed status map". Check: "Tests for each status, a raised `RuntimeError`, and `asyncio.CancelledError` from a scripted transport."
- `cli-backed-source-integrations.md` has no Check line; the entry is prose. Binding text: "centralize process execution in one library runner. The runner should own executable allowlisting, argument validation, timeout and output bounds, environment-based credential injection, cancellation, and safe error classification." Also: "Do not expose arbitrary URLs or command strings to model-facing inputs." Also: "clip untrusted output by UTF-8 byte size".
- `strict-config-dataclasses.md`, "A core settings class's constructor should be a thin adapter over one strictly validated dataclass". Check: "The settings class's own `__init__` and instance methods contain no `raise ConfigurationError` calls — every one lives on the dataclass. …"
- `strict-config-dataclasses.md`, "Keep reusable validation bounds in the shared constants package". Check: "Search the dataclass for private bound literals; each validation comparison should reference the feature's constants module."
- `strict-config-dataclasses.md`, "Local size caps are generous and derived from the vendor constants, never tight guesses". Check: "Every new bound either references a vendor constant or is at least as large as the broad cap in the same constants file."
- `runtime-boundaries.md`, "Don't duplicate general agent/loop budget settings in a sub-runtime's own Params". Check: "Grep the new `Params` dataclass's fields against `AgentLoopSettings` and any active middleware — a field name/purpose overlap is a signal to remove it, not reimplement it locally."
- `runtime-boundaries.md`, "A specialized agent's runtime is its own AgentRuntimeType, not a class-override hook". Check: "`RuntimeRegistry.resolve(AgentRuntimeType.X)` is the subclass; `BaseAgent(runtime="x")._runtime()` raises a message naming the real agent; runtime tests keep usage/speed tracker identity."
- `review-scope.md`, "\"This PR overcomplicated it\" means rebuild the feature on main, not trim the PR head". Check: "Every file in the diff is traceable to a review comment or to the feature's minimal surface (settings, gate, runtime, tests, docs)."
- `agents-md-map.md`, "Keep Map folder entries as general intent, never file, subfolder, or command references". Check: "No folder-heading description contains a backtick-quoted file name, a `.py`/`.md`/`.yml`/`.json`/`.toml` extension, a child-folder path, or a literal command (`git ...`, `python ...`, `pip ...`)."
- `class-bound-helpers.md`, "Prefer a static helper class over a bag of module-level free functions". Check: "The module's public `__all__` exports the class (and constants), not a list of peer free functions for the same concern."

## 2. Files this change will touch

No file exists for CodingAgent or for a Bash tool. The only process-spawning code in `vidbyte/` is `vidbyte/tools/mcp/transport.py:168` (`git grep create_subprocess|subprocess.run|subprocess.Popen -- vidbyte`). `vidbyte/lib/runners/` holds model runners (text, image, audio, and so on), not process runners.

### New files (none exist today; the paths are for the spec author to choose)

- **CodingAgent module under `vidbyte/agents/`.** Precedents for a single-module `BaseAgent` subclass in that folder: `vidbyte/agents/handoff.py:41` (`HandoffAgent`) and `vidbyte/agents/continual_trace.py:33` (`ContinualTraceAgent`). Package-style precedent: `vidbyte/agents/jev/agent.py` (`JevAgent`). A new subfolder needs a new folder entry in `REPO_MAP.md`, written as 4–5 general sentences per `agents-md-map.md`. A single module does not.
- **Bash tool module.** Nearest folder precedents:
  - `vidbyte/tools/builtins/`, which holds `code_execution.py`, `code_search/`, `editing/`, and `operations/`;
  - `vidbyte/tools/filesystem/`.

  REPO_MAP's `vidbyte/tools/filesystem/` entry says: "This is, in practice, the surface where a coding-oriented agent spends the large majority of its tool calls."
- **Any new record or enum.** Records go in `vidbyte/lib/dataclasses/<domain>.py`. Enums go in `vidbyte/lib/enums/<domain>.py` and are exported from `vidbyte/lib/enums/__init__.py`. `vidbyte/lib/enums/` has no tools or agents-coding module today; it holds agent_runtime, codex, config, context, continual_trace, cot_events, decision_model, failure, jev, model_modality, model_provider, multi_agent, platform, prompts, reasoning_strategies, skills, sources, speed, structured_output, and usage.
- **Any new named constant** (A007: timeouts, byte limits). `vidbyte/lib/constants/` holds codex, cot_events, failure, jev, reasoning_strategies, runners, speed, and trace, with no tools or operations module. The existing MCP subprocess constants are module-private in `vidbyte/tools/mcp/transport.py:63-65`:
  - `_DEFAULT_STDERR_MAX_BYTES = 64 * 1024`
  - `_DEFAULT_REQUEST_TIMEOUT = 30.0`
  - `_DEFAULT_SHUTDOWN_TIMEOUT = 5.0`
- **New test file(s) under `tests/`.** See §3.

### Existing files that will change

- **`vidbyte/agents/__init__.py`** (523 lines, "Context Protocol Header" docstring).
  - Today: imports every agent class and sets `Agent = BaseAgent`. Has a literal `__all__` containing "BaseAgent", "ContinualTraceAgent", "HandoffAgent", and the Jev names.
  - Change: import and export the new class.
  - Pattern: the existing literal `__all__`.
- **`vidbyte/__init__.py`** (1272 lines).
  - Today: `from vidbyte.agents import (... HandoffAgent, JevAgent, ...)` starts at line 41, with `JevAgent` at line 100. The literal `__all__` starts at line 678 ("JevAgent" at 701, "ContinualTraceAgent" at 848, "HandoffAgent" at 1046). It imports specific `vidbyte.tools.builtins.<submodule>` modules, not the `vidbyte.tools.builtins` root.
  - Change: add the class to the import block and to `__all__` (S015).
- **`contracts/sdk-public-api.json`**: regenerate with `python scripts/generate-sdk-public-api.py` after committing `vidbyte/__init__.py` (C016).
- **`vidbyte/agents/README.md`** (210 lines).
  - Today: prose plus a "## Key Modules" bullet list (base.py, client.py, fallback.py, settings/fallback.py, runtimes/, handoff.py, multi/, types.py). It has no "## File Index", so S020 does not apply.
  - Change: a Key Modules bullet, if the spec adds one.
- **`vidbyte/tools/builtins/__init__.py`** (322 lines). Changes only if a Bash tool is placed under builtins and exported.
  - Today: a literal `__all__` plus `__all__.extend(...)` for the reasoning classes.
  - Import-order note: `vidbyte/tools/builtins/fork/fork.py` imports `vidbyte.agents.runtimes.configs` and `vidbyte.agents.settings` at module top. So importing the `vidbyte.tools.builtins` package root pulls in `vidbyte.agents`.
- **`REPO_MAP.md`** (384 lines). Changes only for a new subfolder.
  - The `vidbyte/agents/` sub-entries are algorithms, contracts, jev, multi, pricing, runtimes, and settings. There is no `codex` entry, although `vidbyte/agents/codex/` exists.

### Existing files the new code consumes (read; no change expected)

- **`vidbyte/agents/base.py`** (1600 lines, "Context Protocol Header").
  - `BaseAgent.__init__` (lines 79–113) is keyword-only and takes `name`, `system_prompt`, `runtime`, `tools: Sequence[object] | Tools = ()`, `permission_policy`, `agent_loop_settings`, `max_tool_rounds`, `max_iterations`, `max_tokens`, the compaction tokens, `middleware`, `api_key`, `provider`, `model_name`, `temperature`, `timeout_seconds`, `run_id`, `description`, `capabilities`, `agent_metadata`, `context_items`, `context_manager`, `algorithm`, `metadata`, `tracer`, `trace`, `output_schema`, `handoff`, `trace_option`, and `fallback`.
  - An empty system_prompt raises `AgentExecutionError("Agent system_prompt is required.")` (line 117).
  - Line 184: `self.tools = tools if isinstance(tools, Tools) else self._catalog_from_agent_tools(self._agent_tool_items)`.
  - Line 185: `self.permission_policy = permission_policy or PermissionPolicy()`.
  - Lines 260–261 bind each tool via `_bind_agent_tool_context` (line 393), which lazy-imports `vidbyte.tools.builtins.*` inside the method.
  - `from_run_id` (line 270) calls `cls(name=…, system_prompt=…, run_id=…, **kwargs)`.
  - `add_tool` (line 315) catches only TypeError (line 319).
  - `fork` (line 443) delegates to `AgentForker.fork`.
  - `export_state` (line 449) stores sorted permission values and `tool_names`.
  - `restore` (line 479) calls `cls(name=…, system_prompt=…, runtime=…, tools=tools, middleware=…, provider=…, model_name=…, temperature=…, run_id=…, agent_loop_settings=…, timeout_seconds=…, trace_option=…, description=…, capabilities=…, agent_metadata=…, algorithm=…, metadata=…, tracer=…, trace=…, output_schema=…, permission_policy=cls._restore_permission_policy(state))`.
  - `_runtime()` (line 1205) passes `tools=self.tools` and `permission_policy=self.permission_policy` to the runtime.
  - `_catalog_from_agent_tools` (lines 1283–1290) catches only TypeError (line 1288).
  - `generate_reply` is at line 714.
- **`vidbyte/agents/jev/agent.py`** (105 lines; A001-compliant FILE/PURPOSE header).
  - `JevAgent(BaseAgent).__init__(self, settings, runtime_settings=None)` calls `super().__init__(...)` with a narrowed set.
  - `_require_metered_specialists` (lines 86–98) rejects any specialist whose `type(agent).generate_reply is not BaseAgent.generate_reply`.
- **`vidbyte/agents/handoff.py:41`**. `HandoffAgent.__init__(self, handoff=None, *, name="handoff", **kwargs: Any)` pops `handoff`, `system_prompt`, and `output_schema`, then calls `super().__init__(..., **kwargs)`. This is the pass-through precedent. Its header is "Context Protocol Header", which is not A001-compliant.
- **`vidbyte/agents/continual_trace.py:33`**. `ContinualTraceAgent.__init__(self, schema, *, name=..., trace_so_far=None, max_trace_iterations: int = 3, **kwargs: Any)` pops `tools`, `system_prompt`, `output_schema`, `handoff`, `trace_option`, and `max_iterations`, then calls `super().__init__(name=name, system_prompt=Prompts().get(...), tools=[self._tool], …, **kwargs)`. Same non-compliant header style.
- **`vidbyte/agents/fork.py`**. `AgentForker.fork` (line 38) builds a plain `BaseAgent(` (line 43). It copies the tools, `permission_policy=agent.permission_policy`, loop settings, middleware, prompt, keys, model, context, metadata, and fallback. `_clone_tool` (line 136) uses `clone_for_fork` (line 142), then `rebind_context_manager`, else the same object.
- **`vidbyte/agents/runtime.py`** (2020 lines).
  - Imports `vidbyte.tools.builtins.operations.base.PricedOperationTool` at module top (line 149).
  - `_check_permission` (line 1270) raises `PermissionDeniedError("Permission denied for tool '<name>' requiring <permission>")` (line 1275). The handler turns that into `ToolResult.error(..., metadata={"error": "permission_denied", "permission": …})` (line 1144) with state DENIED, and the loop continues.
  - `_run_tool_execute` (line 1300) wraps non-internal tools in `ToolSettings.tool_timeout_seconds` when it is set (line 1303).
  - Priced operations are recorded from the tool's metadata.
- **`vidbyte/tools/catalog.py`**. `Tools` raises `ToolRegistrationError(f"Tool already exists: {tool.name}")` at lines 38 and 79. `add(tool, *, replace=False)`, `extend`, `without`, and `subset` all return new catalogs.
- **`vidbyte/tools/base.py`** (A001 header). `BaseTool(ABC)` has abstract `spec() -> ToolSpec` and `async execute(call) -> ToolResult`, plus `validate_call`, `name`, `customize()`, `with_activity()`, and `rebind_context_manager()`.
- **`vidbyte/lib/dataclasses/tools.py`** (354 lines).
  - `ToolPermission(str, Enum)` (line 47): SAFE, READ, WRITE, EXECUTE.
  - `ToolParameter(name, type, description, required=True, default=None)`.
  - `ToolSpec(name, description, parameters=(), permission=SAFE, …)`.
  - `ToolCall`, and `ToolResult` with `success`/`error`/`failure`.
  - `vidbyte/tools/types.py` re-exports these.
- **`vidbyte/lib/dataclasses/security.py`**. `PermissionPolicy.allowed` defaults to `frozenset({SAFE, READ})` (line 33). `check` is at line 37. `allow_all()` (line 45) allows every `ToolPermission`.
- **`vidbyte/tools/builtins/code_search/base.py`**. `BaseCodeSearchTool.__init__(root_dir, *, ignore_patterns=None, max_file_bytes=1_000_000)` (line 25) resolves the root. A path that escapes it raises `ValueError("Path escapes root: …")` (line 46).
  - `glob.py:28` defines `name="glob"`, READ; parameters pattern, subdir, max_results, max_chars.
  - `grep.py:29` defines `name="grep"`, READ; parameters pattern, subdir, regex, extensions, context_lines, max_results, max_chars.
  - Neither has a fork clone hook. Descriptions are one-liners (baselined under S025).
- **`vidbyte/tools/filesystem/`** (no file headers). `FileSystemTool.__init__(config: FileSystemToolConfig)` (`_base_tool.py:14`). `_path` (line 19) calls `resolve_scoped_path`; `_require_write` (line 23) checks writes.
  - `read_text.py:14`: `read_text`, READ. Reads the whole file with no size bound.
  - `read_lines.py:15`: `read_lines`, READ (path, start, end).
  - `write_text.py:14`: `write_text`, WRITE (path, content, create_parents). Calls `_require_write` at line 29.
  - `replace_text.py:15`: `replace_text`, WRITE (path, search, replacement). Requires exactly one match and calls `_require_write` at line 31.
  - Errors come back as `ToolResult.error(self.name, str(exc))`.
- **`vidbyte/lib/dataclasses/filesystem.py:27`**. `FileSystemToolConfig(root, allow_write=False (line 31), encoding="utf-8", platform=Platform.LOCAL, backend=None)`, with no `__post_init__`.
- **`vidbyte/lib/tools/filesystem/permissions.py`**. Two errors: "Filesystem tool path escaped the configured root." (line 18) and "Filesystem writes require allow_write=True." (line 26).
- **`vidbyte/tools/builtins/editing/patch.py`**. `PatchTool.__init__(root_dir, *, encoding="utf-8")` (line 27), `name="patch_file"` (line 35), WRITE. It has no allow_write switch and returns a unified diff.
- **`vidbyte/tools/builtins/operations/base.py`**. `PricedOperationTool.__init__(self, *, client: WebOperationClient | None = None)` (line 42). Helpers: `_contract_result`, `_executed_result` (puts the payload in `metadata["operation_payload"]`), and `_failed_result`.
- **`vidbyte/tools/builtins/operations/fetch.py`** (240 lines). None of these tools sets `permission=`, so all are SAFE.
  - `FirecrawlFetchTool` (`firecrawl_fetch`, url/urls, line 45).
  - `BrowserbaseFetchTool` (`browserbase_fetch`, url and proxies, line 80).
  - `ParallelExtractTool` (`parallel_extract`, urls, line 113).
  - `TavilyExtractTool` (`tavily_extract`, urls and extract_depth, line 143).
  - `LinkupFetchTool` (`linkup_fetch`, line 176).
  - `DirectHttpFetchTool` (`direct_http_fetch`, url, line 199).
- **`vidbyte/tools/builtins/operations/clients/`** has README, `_base.py`, brave, browserbase, exa, firecrawl, parallel, and tavily. There is no linkup client.
  - `WebOperationClient.__init__(api_key, *, provider, base_url, timeout_seconds=15.0, retry=None, max_response_bytes=2_000_000, transport=None)`.
  - Defaults per client:

    | Client | timeout | max_response_bytes | Extra options |
    |---|---|---|---|
    | `FirecrawlClient(api_key, …)` | 60 | 8 MB | `only_main_content=True` |
    | `BrowserbaseClient(api_key, …)` | 30 | 4 MB | none |
    | `ParallelClient(api_key, …)` | 60 | 8 MB | none |
    | `TavilyClient(api_key, …)` | 60 | 8 MB | none |

  - None of these needs more than `api_key`. Brave and Exa are search-only.
- **`vidbyte/sources/fetches/http.py`**. `HttpFetcher(*, timeout_seconds=30.0, user_agent=…)` (line 33). `fetch` (line 38) calls `SyncHttpTransport.request_bytes(method="GET", url=…, headers=…, timeout_seconds=…)` (lines 44–49) with no `max_response_bytes`.
- **`vidbyte/lib/registries/operation_pricing.py:159`**: `("fetch", "direct_http", "default"): OperationPricing()`, which is zero cost.
- **`vidbyte/tools/mcp/transport.py`**. This is the only subprocess precedent.
  - Env allowlists: `_POSIX_ENV_KEYS` (line 33) and `_WINDOWS_ENV_KEYS` (line 45), selected by `sys.platform == "win32"` (line 70). `build_child_env` is at line 75.
  - Line 168: `asyncio.create_subprocess_exec(*self.command, stdin/stdout/stderr=PIPE, env=child_env)`.
  - Uses `asyncio.wait_for` for timeouts and a bounded stderr buffer.
  - Shutdown is terminate, then wait_for, then kill. Cancellation is re-raised.
  - Uses `asyncio.Lock` (lines 134–139), which S039 bans (baselined).
- **`vidbyte/tools/builtins/code_execution.py`**. `CodeExecutionTool` (line 111), `name="code_execution"`, no `permission=`, so SAFE. It simulates `print(...)` and runs no subprocess. Its description is the multi-sentence style that S025 wants.
- **EXECUTE-permission precedents**: `vidbyte/tools/builtins/mcp/attach_tool.py:93` (`permission=ToolPermission.EXECUTE`) and the MCP bridge in `vidbyte/tools/mcp/bridge.py`, whose default is EXECUTE.
- **`vidbyte/agents/client.py`** (56 lines). `AgentClient` methods are base, handoff, jev, continual_trace, aggregate, and multi. Adding a coding entry was not requested.

## 3. Tests that cover those files

### Framework and configuration

- pytest 8.3.5 with pytest-asyncio 1.3.0 (`pyproject.toml` `[tool.pytest.ini_options]`: `testpaths=["tests"]`, `addopts=["--strict-config","--strict-markers"]`, `asyncio_default_fixture_loop_scope="function"`).
- Three styles are in use:
  - `unittest.IsolatedAsyncioTestCase` (`tests/test_code_search_tools.py`);
  - `unittest.TestCase` with `asyncio.run` (`tests/test_filesystem_tools.py`);
  - module-level `@pytest.mark.asyncio` functions with `monkeypatch` (`tests/test_web_operation_client_retry.py`, which fakes `HttpTransport._send_once` and `transport_module.asyncio.sleep`).
- A001 scans `tests/`, so a new test file needs the FILE/PURPOSE/… header. The compliant precedents are `tests/test_web_operation_client_retry.py` and `tests/test_restore_permission_policy.py`.

### Fixtures and helpers

- **`tests/agent_test_support.py`**:
  - `OfflineTestAgent(BaseAgent)` (line 48);
  - `bind_test_runner(agent, runner, runner_type=RUNNER_TYPE_TEXT)`, which sets `agent._runner_cache[...]`;
  - `build_test_agent(*agent_args, runner, agent_type=OfflineTestAgent, **agent_options)`, which defaults provider "openai" and model "gpt-4.1-mini".
- **`tests/test_agent_tool_loop.py`** (624 lines):
  - `ToolCallingRunner(responses)` pops `FakeResponse(text, raw={"output":[{"type":"function_call","name":…,"arguments":json,"call_id":…}]})` and ends with `isDone`/`final_answer`;
  - `test_agent_denies_write_tool_by_default` asserts `reply.metadata["tool_call_states"] == ("denied","succeeded")`.
- **`tests/test_agent_base.py`**: `FakeTool`, `EchoRunner`, and `assertRaises(ToolRegistrationError)` for a duplicate `add_tool`.
- **`tests/test_jev_agent.py`**: public-API pattern. It checks root-versus-package export identity and the `VidbyteSDK().agents.jev` namespace, and pins `inspect.signature(JevAgent.__init__)`.
- **`tests/test_mcp_stdio_transport.py`**: subprocess precedent `[sys.executable, "-u", "-c", source]`, with a win32 branch at line 419. `test_cancelled_waiter_does_not_break_transport` is the known 3.11 flake.
- **Area tests:**
  - `tests/test_code_search_tools.py` (tempdir);
  - `tests/test_filesystem_tools.py` (includes `test_write_without_allow_write_returns_error`);
  - `tests/test_patch_tool.py`;
  - `tests/test_security_executor.py` (`allow_all` vs default deny);
  - `tests/test_restore_permission_policy.py`;
  - `tests/test_agent_fork_isolation.py`;
  - `tests/test_tools_catalog.py`;
  - `tests/test_tool_core.py`;
  - `tests/test_web_operation_client_retry.py`;
  - `tests/features/sdk_operation_costs/`;
  - `tests/test_agent_runtime.py`.

### Exact commands

- One file: `python -m pytest -q tests/<file>.py`
- This area: `python -m pytest -q tests/test_agent_base.py tests/test_agent_tool_loop.py tests/test_agent_fork_isolation.py tests/test_code_search_tools.py tests/test_filesystem_tools.py tests/test_patch_tool.py tests/test_security_executor.py tests/test_restore_permission_policy.py tests/test_jev_agent.py tests/test_web_operation_client_retry.py`
- All tests: `python -m pytest`
- From this worktree, prefix with `PYTHONPATH=$(pwd)` for the source stage only, per `local-ci-verification.md`. The package stage runs without it.
- Lint for the touched rules:
  - `python lint/run.py --rule A001`, and likewise for A002, A006, A007, S015, S019, S025, S039, S052, S055, and C016;
  - then `python lint/run.py`.
- Full gate: `python scripts/run_ci.py`.

## 4. Notes for the spec author

### Contradictions (request vs code)

- The request assumes a keyed WebFetch provider gives the model fetched page content ("WebFetch provider is chosen by which API key is supplied", `request.md:55`, `request.md:86`). The code shows otherwise:
  - Every keyed tool renders only `"<label>: N pages.\n1. <final_url> (<len> chars)"` via `_render_fetched_pages` (`vidbyte/tools/builtins/operations/fetch.py:39-42`).
  - Page bodies travel only in `metadata["operation_payload"]` (`operations/base.py` `_executed_result`; `vidbyte/tools/README.md`, "Priced Operation Tools").
  - Only `DirectHttpFetchTool` puts the body in `output` (`fetch.py:222`).
- The request lists Linkup as a candidate keyed provider (`request.md:103`). The code shows `LinkupFetchTool.execute` always returns `_contract_result("linkup fetch", …)` and never fetches (`fetch.py:193-196`). `vidbyte/tools/builtins/operations/clients/` has no Linkup client.
- The request says keyed tools "return a priced contract stub when no client is injected" (`request.md:41`). The code confirms this at `fetch.py:67-68, 104-105, 134-135, 167-168`. The stub is a success result and is still recorded as a priced operation by the runtime.
- The request assumes no key means `DirectHttpFetchTool` as the WebFetch fallback (`request.md:86`). The code shows it returns the entire decoded body as model output (`fetch.py:215-229`). It is fetched by `HttpFetcher` with no `max_response_bytes` (`vidbyte/sources/fetches/http.py:44-49`), and S013 does not scope `vidbyte/sources/`.
- The request expects S012/S013 to force Bash timeout and output limits (`request.md:49`, `request.md:104`). The code shows:
  - S012 matches only calls named in `REQUEST_METHODS` (`lint/rules/s012_explicit_outbound_timeout.py:22`).
  - S013 matches only `.request`/`.request_bytes`/`.stream_request` under four tool prefixes (`lint/rules/s013_bounded_untrusted_responses.py:22-23`).
  - Neither matches `asyncio.create_subprocess_exec`. The rules that do bind a subprocess tool are S052, S055, S019, S006, S039, S045, A002 ("subprocess" token), and A007 (timeout/byte literals).
- The request assumes CodingAgent can default to a permissive policy while accepting a stricter one (`request.md:44`, `request.md:73`). The code shows:
  - BaseAgent treats `None` as `PermissionPolicy()`, which is SAFE+READ only (`vidbyte/agents/base.py:185`, `vidbyte/lib/dataclasses/security.py:33`).
  - A denied call does not raise to the caller. It becomes a DENIED `ToolResult.error` and the loop continues (`vidbyte/agents/runtime.py:1270-1277`, `:1144`).
  - Write and Edit also need `FileSystemToolConfig.allow_write=True` (`vidbyte/lib/dataclasses/filesystem.py:31`, `vidbyte/lib/tools/filesystem/permissions.py:26`). `PatchTool` has no such switch (`vidbyte/tools/builtins/editing/patch.py:27`).
- The request assumes "the same settings and functionality as BaseAgent" (`request.md:54`) plus a working-folder parameter (`request.md:106`). The code shows:
  - `BaseAgent.restore` (`base.py:479`) re-invokes `cls(...)` with BaseAgent kwargs only and a caller-supplied `tools=` (default `()`).
  - `BaseAgent.from_run_id` (`base.py:270`) calls `cls(name=…, system_prompt=…, run_id=…, **kwargs)`.
  - A subclass constructor is invoked by both paths.
- The request asks what a duplicate tool name does (`request.md:105`). The code shows `_catalog_from_agent_tools` catches only TypeError (`base.py:1288`) while `Tools` raises `ToolRegistrationError("Tool already exists: …")` (`vidbyte/tools/catalog.py:38`, `:79`). A duplicate fails at construction, and `add_tool` fails the same way (`base.py:315-319`).
- The request states that a fork is a plain BaseAgent (`request.md:46`). The code confirms this (`vidbyte/agents/fork.py:43`). In addition, the code-search, filesystem, and fetch tools have no `clone_for_fork`, so a fork shares the same tool objects (`fork.py:136-142`).
- The request decides on a model-facing shell command tool (`request.md:56`, `request.md:87`). The field guide `cli-backed-source-integrations.md` says "Do not expose arbitrary URLs or command strings to model-facing inputs" and asks for one library runner owning allowlisting, bounds, cancellation, and env. No such process runner exists (`vidbyte/lib/runners/` holds model runners only).
- The request does not state a child environment for Bash. The only subprocess precedent passes an allowlisted env (`vidbyte/tools/mcp/transport.py:33-75`, `:168`).
- The request lists "REPO_MAP.md and `vidbyte/agents/README.md` entries" (`request.md:49`). The code shows REPO_MAP is folder-level only, so a single new module in `vidbyte/agents/` has no entry to add. `vidbyte/agents/README.md` has "## Key Modules", not "## File Index", so S020 does not apply to it.
- The request names `JevAgent` as the subclass to study (`request.md:91`). The code shows the closest pass-through subclasses (`handoff.py`, `continual_trace.py`) and `base.py` itself use the "Context Protocol Header", which lacks A001 fields. A001 is count-ratcheted (baseline 643), so copying that header style regresses lint. `vidbyte/agents/jev/agent.py` is A001-compliant.
- The request's tool map (`request.md:36-41`) relies on existing tools whose descriptions are one sentence (`glob.py:28`, `grep.py:29`, `fetch.py`, `vidbyte/tools/filesystem/*`). These are baselined under S025 (263). A new Bash tool must meet S025's 4-sentence minimum per description.
- The request says CI runs "on whatever OS the workflow specifies — unverified" (`request.md:72`). The code shows `.github/workflows/ci.yml` runs on ubuntu-latest only (Python 3.11/3.12) and only on workflow_dispatch or workflow_call. Windows behaviour of a Bash tool is not exercised by CI.
- The skill reference `vidbyte-gates.md` says "semgrep is part of" run_ci.py. The code shows semgrep only in `.github/workflows/static-policy.yml` (`scripts/run_ci.py:79-93` has no semgrep step).
- The field guide `priced-operation-execution.md` describes an injected "async operation executor" seam on `PricedOperationTool`. The code shows only `client: WebOperationClient | None` (`vidbyte/tools/builtins/operations/base.py:42`).

### Gaps (facts the request does not settle; no proposal)

- Three root representations exist for the file tools:
  - `root_dir` for Glob, Grep, and Patch (`code_search/base.py:25`, `patch.py:27`);
  - `FileSystemToolConfig.root` for Read, Write, and Edit (`filesystem.py:27`).

  Path-escape errors also differ: `ValueError` (`code_search/base.py:46`) versus `ToolExecutionError` (`lib/tools/filesystem/permissions.py:18`).
- `read_text` reads a whole file with no byte bound. `read_lines` bounds by line range only.
- An agent-wide tool timeout already exists: `ToolSettings.tool_timeout_seconds`, applied in `runtime.py:1300-1303`. `runtime-boundaries.md` warns against duplicating general budget settings.
- Model-facing names today are `glob`, `grep`, `read_text`/`read_lines`, `write_text`, `replace_text`/`patch_file`, and `firecrawl_fetch`/`browserbase_fetch`/`parallel_extract`/`tavily_extract`/`linkup_fetch`/`direct_http_fetch`. No `bash` tool name exists.
- `vidbyte/__init__.py` imports builtins by submodule. `vidbyte/agents/runtime.py:149` already imports `vidbyte.tools.builtins.operations.base` at module top. `vidbyte/tools/builtins/fork/fork.py` imports `vidbyte.agents.*` at module top.
- `AgentClient` (`vidbyte/agents/client.py`) has no coding entry. This was not requested.

### Unverified

- unverified: the exact runtime line where `ToolResult.output` becomes the model-visible tool message. I read that the runtime uses `result.output` and that `operation_payload` stays in metadata, but did not record the line.
- unverified: which `bash` a Python subprocess resolves on Windows. On this machine, `which -a bash` from Git Bash lists `/usr/bin/bash` (Git Bash), `/c/WINDOWS/system32/bash` (the WSL launcher), and a WindowsApps `bash`. PATH order inside a non-Git-Bash Python process was not checked.
- unverified: whether `vidbyte/agents/__init__.py` importing a module that imports the `vidbyte.tools.builtins` package root creates an import cycle (because of `tools/builtins/fork/fork.py`). Submodule imports are what existing code does.
- unverified: the exact parameter names ruff's ASYNC109 treats as timeout-like (S045 delegates to ruff, `lint/rules/s045_async_function_with_timeout.py:9`).
- unverified: whether `SandboxTransport` in `vidbyte/lib/dataclasses/sandbox.py` (the file exists; re-exported via `vidbyte/tools/security/sandbox.py`) is used anywhere. Not needed, since the user rejected it.
