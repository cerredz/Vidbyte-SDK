# Code map: harness browser tools (`run_/continue_/fork_<grok|opencode|muse>_with_browser`)

Scout: S0. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-browser-tools`, HEAD `845a4d9b` (= origin/main), branch `feat/harness-browser-tools`, no commits of its own. Every path below was opened in this session. Line numbers are at `845a4d9b`. Anything not checked is marked "unverified".

## 1. Rules, commands and conventions that bind this change

### 1.1 AGENTS.md (binding)

- **"1. Keep Call Chains One Level Deep"**: "a function may call another of its own functions, but that second function should not call a third." Calls into another class, a lower layer or the standard library do not count. "Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator."
- **"2. Narrate Main Functions in Plain English"**: put plain-English comments throughout the main function's body, "so that a reader can follow the whole feature by reading only the comments". "When you change the steps of a main function, update its comments in the same edit."
- **"3. Build in Layers of Small, Single-Purpose Classes"**: "nothing in `vidbyte/lib/` may import from a layer above it"; "Keep files well below 1,000 lines"; "If describing the job of a function or a class needs the word 'and', it is probably two".
- **"4. Use Validated Dataclasses for Core Inputs and Outputs"**: "Prefer `@dataclass(frozen=True, slots=True)`"; validate in `__post_init__`; "type any field whose value comes from a small, closed set as an enum."
- **"5. Write Shared Logic Once, as a Canonical Helper in `lib/`"**: "look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the option you need to it rather than copying it". A canonical helper never imports from a higher layer.
- **Placement Rules / Dataclasses**: "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`**". "Add to the existing domain module when there is one; create a new `<domain>.py` only for a new domain. Do not create `types.py`, `records.py`, `models.py`, or `schemas.py`". "If a dataclass seems to need a type from a higher layer, move the contract down".
- **Placement Rules / Enums**: "**Every new enum ... is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions." "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."
- **Placement Rules / Existing code**: older modules that define dataclasses or enums elsewhere "predate these rules. Do not copy them as precedent. Editing one in place (adding a field or a member) is fine." Moving such a module is a separate PR.
- **Repository Map**: read `REPO_MAP.md` "before you create a file, move code, or search for where something lives". Read each folder's `README.md` "to the end before you change anything inside the folder". The closing "## Notes for agents" section holds review lessons. "lint rule A009 keeps every folder README at or under 40,000 characters".
- **Two rules for every change**: "**Do not grep, glob, or read files under `docs/`** as part of ordinary work". "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- The Placement Rules "are not part of the map ... the `AGENTS.md placement` workflow enforces it on every pull request by moving misplaced code" (`.github/workflows/agents-md-placement.yml`, which runs the Codex CLI on a self-hosted runner for each PR).
- **Commit and PR conventions**: AGENTS.md states none. It mentions only the placement workflow, and REPO_MAP.md:31 describes `claude.yml`, which answers `@claude` mentions and appends lessons to folder-README "Notes for agents" sections.

None of the folder READMEs this change touches has a `## Notes for agents` section: `vidbyte/harnesses/README.md`, `vidbyte/lib/README.md`, `vidbyte/lib/registries/README.md` and `tests/features/harness_threads/README.md`.

### 1.2 Commands

| Purpose | Command | Source |
|---|---|---|
| Install (once) | `python -m pip install -e ".[dev]"` | gates reference; `.github/workflows/ci.yml:36` |
| Full gate | `python scripts/run_ci.py` (stages `all` (default), `source`, `package`) | AGENTS.md; `scripts/run_ci.py:255-272` |
| Source gate | `python scripts/run_ci.py --stage source` runs: tracked-bytecode check, `lint/run.py`, `compileall vidbyte`, `scripts/check_context_write_paths.py`, `scripts/check_context_primitive_introductions.py`, `scripts/check_reasoning_trace_contracts.py`, `python -m pytest` | `scripts/run_ci.py:79-93` |
| Package gate | `python scripts/run_ci.py --stage package` (build, twine check, clean-venv install, smoke) | `scripts/run_ci.py:95-113`; CI: `--stage package --dist-dir dist` (`ci.yml:60`) |
| Custom lint | `python lint/run.py`; `--rule <ID>`, `--all`, `--format json`. The last line must read `AGENT-LINT: PASS` | gates reference; rule headers ("Exercised by python lint/run.py --rule A00x") |
| Import sort (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | field guide `local-ci-verification.md` |
| Semgrep (separate CI job, not in run_ci.py) | `python -m pip install semgrep==1.170.1`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | `.github/workflows/static-policy.yml:24-30` |
| Root public-API contract | `python scripts/generate-sdk-public-api.py --check` (covers only root `vidbyte/__init__.py` `__all__`) | `scripts/generate-sdk-public-api.py:3`; lint C016 |
| Failure-code vocabulary | `python scripts/test-session-failure-vocabulary.py` | `vidbyte/lib/enums/failure.py` header TESTS |
| One test file | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/<file>.py` | `fake_harness.py:13` (TESTS line) |
| Area | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` | `fake_harness.py:13` |
| All tests | `python -m pytest` (`testpaths = ["tests"]`, `--strict-config --strict-markers`) | `run_ci.py:93`; `pyproject.toml:78-81` |

Machine notes, checked here:

- Use `py -3.11` (Python 3.11.0, pytest 8.3.5).
- Run from the worktree root and `import vidbyte` loads the worktree copy. Run from anywhere else and it loads the editable install at `C:\Users\422mi\vidbyte-repos\vidbyte-sdk\vidbyte` (main clone).
- Field guide `local-ci-verification.md`:
  - Use `PYTHONPATH=$(pwd)` for `--stage source` from a worktree.
  - Run `--stage package` without PYTHONPATH.
  - Semgrep scans only git-tracked files, so `git add -A` before trusting it.

### 1.3 Gate discipline (gates reference)

Never raise a number in `lint/baseline.json`, add a suppression, weaken a rule or delete a check. "A genuine false positive stays failing and is called out in the PR description."

### 1.4 Field guide rules (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`, field guide, not AGENTS.md)

- **blocking-lint-invariants.md:61-65**: "Every module under `vidbyte/harnesses/native/` is held to INV-15 and INV-20, with no allow-list". Do: "Keep module level to a docstring, imports, classes and a literal `__all__`; limit literals to docstrings, `__all__` strings, `""`, `0` and `1`; never import `vidbyte.tools`. Code that serves model-facing tools for a harness does not belong in `native/`." Check: `pytest tests/features/harness_threads/test_harness_threads_static_policy.py`.
- **blocking-lint-invariants.md (other entries)**:
  - A003: a new error class carries the literal `DIAGNOSTIC_FIELDS` 8-tuple.
  - A006: lower layers (`vidbyte.lib`, `.providers`, `.sessions`, `.sources`) never import orchestration layers (`vidbyte.agents`, `.tools`, `.harnesses`, ...).
  - S060 / S039: no `dict[str, Any]` encoders on lib records; TypedDict is banned.
  - S012: no non-HTTP method named `request`.
  - C002: derive bool guards from content.
  - A007: for a byte-capped read, use `os.fstat` before reading rather than `read(CAP+1)`.
- **local-ci-verification.md:45-50**: "Two `harness_threads` surface tests fail locally on any branch that touches `vidbyte/tools`, `vidbyte/lib/configs`, or root exports". The two tests are `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` and `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`. "Classify it as pre-existing ... do not edit the PR or the test to make it pass." CI skips them because its shallow clone has no origin/main. Same file: re-test after every merge from main.
- **strict-config-dataclasses.md**:
  - "39: Harness bridge functions take validated lib records, not loose `object`/`Mapping` inputs".
  - "61: Validate record fields through RecordFieldValidator / RecordFieldConverter; add an option rather than a private field helper". It continues: "When an option is missing ... add it as a keyword with a backward-compatible default. Check its callers in `vidbyte/harnesses/native/*` first." No `_..._field` helpers.
  - Bounds belong in `vidbyte/lib/constants/`, and caps derive from vendor facts.
- **declarative-config-resolution.md:10-12**: "New registries go in `vidbyte/lib/registries/`". Do: "Add one module there following `runtimes.py`'s shape: classmethods, lazy in-method imports to dodge cycles, `ConfigurationError` naming the available names."
- **class-bound-helpers.md:3-7**: "Prefer a static helper class over a bag of module-level free functions". Put the public surface and the private helpers on one class as `@staticmethod`. "The module's public `__all__` exports the class". A new boundary function gets an A002 `# @intent` block. Search `vidbyte/lib/` before creating a module.
- **cli-backed-source-integrations.md:3**: "keep provider-specific command construction in the provider adapter and centralize process execution in one library runner." In this repo that runner is `CliRunner`.
- **comment-format.md:3-6**: "A multi-line comment is a PEP 8 block of at most 72 columns, placed directly above the line it explains"; "Keep `# @intent <name>` on its own first line." Check: `awk 'length($0) > 72' <file> | grep -E '^\s*#'`.
- **review-scope.md:3**: "'This belongs in another PR' for a feature already on main means: leave main's files byte-identical".

### 1.5 In-file rules of the #1036 modules (headers, binding by convention)

- **`vidbyte/lib/enums/native_threads.py:8`** (verbatim): "WHAT NOT TO DO IN THIS FILE: 1. Do not add an approve-everything member (bypassPermissions, --yolo, --auto, --always-approve); the SDK never approves everything. 2. Do not import anything from vidbyte; enums sit at the bottom layer. 3. Do not turn an enum here back into a (str, Enum)." Line 7: "Add a member only when the vendor CLI adds the value ... A new problem also needs its FailureCode members and its texts in vidbyte/lib/constants/native_threads.py."
- **`vidbyte/lib/constants/native_threads.py`**:
  - Header lines 5, 7-9. Harness modules "hold no literals of their own (spec INV-15)".
  - "Do not name a constant with a password, token or secret word and give it a string (lint S054)".
  - "each code gets text written for it" (no shared texts).
  - The texts "must not contain a credential word followed by ':' or '='", because HarnessRedactor would rewrite them.
  - The timing knobs are read through the module object at call time.
- **`vidbyte/lib/dataclasses/native_threads.py:7-8`**:
  - "A config record never gets a model field: the model is an argument of every call."
  - "Do not read keys from environment variables. Do not put a key value in an error message ... Do not drop repr=False from a key field. Do not import from vidbyte.harnesses".
- **`vidbyte/harnesses/native/__init__.py:7`**: "A new harness adds its own subpackage with three functions and one config record, and this module re-exports them in the literal __all__." Every native module carries the header FILE / PURPOSE / ROLE IN CODEBASE / ARCHITECTURE NOTE / FUNCTION INVENTORY / COMMON MODIFICATION PATTERNS / WHAT NOT TO DO IN THIS FILE / KNOWN EDGE CASES / RELATED DOCS / TESTS.
- **`vidbyte/harnesses/native/hostkit/__init__.py:7`**: "Plumbing that a second harness needs goes here, in its own module, and is exported from this literal __all__."
- **`vidbyte/lib/process/__init__.py:7`**: "Add a new helper in its own module here and export it from this literal __all__." This conflicts with a test pin; see §4.
- **`vidbyte/lib/process/runner.py:8`**: "Do not pass shell=True or build a command string (lint S055) ... Do not let a child inherit the caller's stdin ... Do not wait without a bound after a kill".

### 1.6 Lint rules that bear on this change (`lint/rules/`)

| ID | File | What it enforces |
|---|---|---|
| A001 | `a001_agent_readable_file_headers.py` | Module docstring must have non-empty PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS, TESTS |
| A002 | `a002_intent_comments.py` | `# @intent <name>` near load-bearing policy, boundary and state functions |
| A003 | `a003_context_rich_error_packets.py` | Error classes expose `DIAGNOSTIC_FIELDS` |
| A006 | `a006_directed_dependency_graph.py:23-37,80-85` | Lower → orchestration/application import edges are banned, and so are cycles. Edges into `__init__.py` façades are not counted (`_is_concrete`, :64-66); `TYPE_CHECKING` imports are skipped; in-function imports count |
| A007 | `a007_operational_constants.py` | Operational literals (timeouts, caps, retries; "Zero and one remain findings when they define operational policy") must be named constants |
| A009 | `a009_readme_size_limit.py:20` | `MAXIMUM_CHARACTERS = 40_000` per folder README. Current sizes: harnesses 10,972; lib 4,037; registries 7,424; harness_threads tests 2,831 |
| S008 / S024 | `s008_bounded_function_complexity.py`, `s024_maximum_control_flow_nesting.py` | Function complexity and nesting depth |
| S015 | `s015_public_export_integrity.py` | `__all__` bindings resolve |
| S021 | `s021_class_bound_registry_helpers.py` | Registry behavior is class-owned |
| S039 / S060 | `s039_banned_api_policy.py`, `s060_typed_public_seam_mappings.py` | Banned APIs (TypedDict) and named mapping shapes at public seams |
| S051 | `s051_modernized_import_and_syntax_hygiene.py` | Sorted imports |
| S054 / S055 | `s054_bandit_security_subset.py`, `s055_no_shell_subprocess.py` | Credentials in constants; shell subprocess |
| C002 / C007 / C008 | `c002_...`, `c007_strict_bool_switches.py`, `c008_shared_validator_owner.py` | Bool guards; strict bool switches; primitive validators live in `vidbyte/lib/dataclasses/validation.py` |
| C016 | `c016_public_api_contract_current.py` | Root `__all__` matches `contracts/sdk-public-api.json` |
| C019 | `c019_platform_error_code_contract.py` | Flat snake_case literals of 3+ tokens in decision positions (constants, dict keys, comparisons) that match a platform error-code family or near-miss must be exported codes |

No lint rule exists for enum or dataclass placement, unexported enums, file length (1,000 lines), call depth or narration. The 93 files in `lint/rules/` were listed and `lint/rules/README.md` was read. Those rules are enforced by AGENTS.md review, the `AGENTS.md placement` workflow, and (for native/) the harness_threads static-policy and surface tests. A006 is the only lint rule that names `vidbyte.harnesses` (`a006_directed_dependency_graph.py:30`).

## 2. Files this change will touch

"Will change" below restates where request.md places the work (request.md:103, :342, :340), or what a requested behavior forces. It is not a design.

### 2.1 Existing files: the thread functions (`vidbyte/harnesses/native/`)

- **`vidbyte/harnesses/native/__init__.py`** (62 lines)
  - Today: header, then a literal `__all__` (line 44) of exactly 17 names: `GrokPermissionMode`, `GrokReasoningEffort`, `GrokThreadConfig`, `MuseReasoningEffort`, `MuseThreadConfig`, `NativeThreadError`, `NativeThreadResult`, `OpencodeThreadConfig` and the nine `*_thread` functions. "`import vidbyte` never imports this package."
  - Will change: re-export the `*_with_browser` functions and their records (KD-1).
  - Pattern: the public names are bound as class attributes in the subpackage `__init__` and listed in the literal `__all__`.
- **`vidbyte/harnesses/native/{grok,opencode,muse}/__init__.py`**
  - Today: bind `run_opencode_thread = OpencodeThreads.run_opencode_thread` (likewise for each harness and verb), with `__all__ = ["continue_opencode_thread", "fork_opencode_thread", "run_opencode_thread"]`.
  - Will change: three more bindings per harness.
  - Pattern: the `Class.attr` binding. The static policy allows only this form at module level in `__init__` files.
- **`vidbyte/harnesses/native/opencode/threads.py`** (`OpencodeThreads` :42, `OpencodeThreadRun` :81)
  - Public signature (:46): `async def run_opencode_thread(prompt: str, *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> NativeThreadResult`. Continue and fork (:51, :56) take `thread_id, prompt` first.
  - `_call` (:61) steps, in order:
    1. `errors = NativeErrorFactory(NativeHarness.OPENCODE, operation)`.
    2. Build `NativeThreadRequest(...)`.
    3. `settings = OpencodeThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, OpencodeThreadConfig)`.
    4. `return await OpencodeThreadRun.execute(...)`.
    5. On exceptions: `CancelledError` re-raises; `NativeThreadError` re-raises; `ConfigurationError` becomes `errors.from_configuration_error(exc, request)`; any other `Exception` becomes `errors.from_unexpected(exc, request)`.
  - `execute(request, config, errors)` (:85-115) steps:
    1. `NativeLauncher.resolve(config.opencode_command, program=OPENCODE_PROGRAM, fallback=None, ...)`.
    2. `content = OpencodeWire.config_content(request)`.
    3. `errors.register_secret(request.api_key)` and `errors.register_secret(content)`.
    4. Build `CliInvocation(argv=_argv(...), env_overlay=_environment(content), timeout_seconds=config.timeout_seconds, max_output_bytes=NATIVE_PROCESS_MAX_OUTPUT_BYTES, cwd=Path(request.workspace), stdin_text=request.prompt)`.
    5. `await CliRunner().run(invocation)`.
    6. A launch failure raises `errors.from_launch_failure`.
    7. `OpencodeWire.read(outcome, request, errors, timeout_seconds=)`.
  - `_environment(content)` (:118-126) returns `{OPENCODE_CONFIG_CONTENT, OPENCODE_DISABLE_AUTOUPDATE: "1"}`.
  - `_argv` builds `run --format=json --dir= --model= [--agent=] [--variant=] [--session=] [--fork]` in JOINED style.
  - Will change: the browser variant needs extra config members (MCP servers, permission rules) inside `OPENCODE_CONFIG_CONTENT`, plus extra env (tool keys). `execute` has no parameter for either.
  - Pattern to reuse: the `_call` guarded try and the narrated `execute`.
- **`vidbyte/harnesses/native/opencode/wire.py`** (`OpencodeWire` :36)
  - `config_content(request)` (:40-51): `{"provider": {<provider before "/">: {"options": {"apiKey": key}}}}`, plus `"skills": {"paths": [...]}` only when skills were given, passed through `json.dumps`. It takes only the request.
  - `read`: parses `CliRunner.json_objects(stdout)`, then checks `_session`, `timed_out`, `stdout_truncated`, an error event (key rejected by `ProviderAuthError` / 401 / 403), the "Session not found" stderr marker, any other vendor error, a non-zero exit, a missing session and the wrong thread. Then it builds `NativeThreadResult`.
  - `_text` keeps the text parts of the last message; `tool_use` events are ignored today.
  - Will change: a tool-call reader (request.md:256 calls it `ToolCallReader`).
- **`vidbyte/harnesses/native/grok/threads.py`** (`GrokThreads` :50, `GrokThreadRun` :89; 188 lines)
  - `execute` (:93-121) steps:
    1. `NativeLauncher.resolve(config.grok_command, program=GROK_PROGRAM, fallback=_fallback())`.
    2. `home = await asyncio.to_thread(_prepare_home, request, errors)`.
    3. `register_secret(api_key)`.
    4. Build `CliInvocation(argv=_argv, env_overlay=_environment(request, home), timeout_seconds, max_output_bytes=GROK_CLI_MAX_OUTPUT_BYTES, cwd=workspace)`, with no stdin.
    5. `run`.
    6. Launch-failure check.
    7. `GrokWire.read`.
  - `_prepare_home` (:135-153):
    - key = `sha256(os.path.normcase(str(request.workspace)))[:16]`;
    - home = `Path.home()/.vidbyte/grok-homes/<key>`;
    - `mkdir`, then `NativeSkillFolders.replace(skills, home/"skills")`;
    - an OSError becomes `LAUNCH_FAILED`.
  - `_environment` (:155-165) sets exactly `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `GROK_HOME` and `GROK_DISABLE_AUTOUPDATER=1`.
  - `_argv` (:168-186) passes `--output-format=json`, `--cwd=`, `--permission-mode=`, `[--model=]`, `[--reasoning-effort=]`, `[--resume=]`, `[--fork-session]` and `--single=<prompt>`, all JOINED.
  - Header: "Do not pass an approve-everything permission mode"; EC-27 (shared home).
  - Will change, per request.md:316-331:
    - write `$GROK_HOME/config.toml`;
    - set `GROK_CLAUDE_MCPS_ENABLED=0` and `GROK_CURSOR_MCPS_ENABLED=0`;
    - add `--allow` / `--deny` `MCPTool(...)` options;
    - switch to `--output-format=streaming-json`.
- **`vidbyte/harnesses/native/grok/wire.py`** (`GrokWire` :34)
  - `_answer` (:85-92) parses "The whole stdout as one JSON object". Check order: `timed_out`, truncated, an error object (`type == "error"`; `GROK_NOT_SIGNED_IN_MARKERS` means KEY_REJECTED, otherwise RUN_FAILED), a non-zero exit, no answer, `sessionId`, text, wrong thread.
  - Will change: reading `streaming-json` (one event per line) needs a different reader.
- **`vidbyte/harnesses/native/muse/threads.py`** (`MuseThreads` :47, `MuseThreadRun` :86; 253 lines)
  - `execute` (:90-145) steps:
    1. `launcher = MuseLauncher(config, errors)`; `prefix = launcher.resolve(request)`.
    2. `workspace = launcher.visible_path(...)`.
    3. `register_secret`.
    4. `_prepare_config` runs in a shielded `to_thread` with a cancel-safe `_discard`.
    5. Inside a try:
       - `mark = launcher.new_mark()`; `overlay = _overlay(launcher, folder)`;
       - for continue and fork: `_serve_invocation`, then `_run`, then `MuseWire.read_answer` (timeout `NATIVE_CONTROL_TIMEOUT_SECONDS`);
       - then `_exec_invocation`, `_run`, `MuseExecOutput.read`.
    6. Finally: `NativeSkillFolders.remove(folder)`, however the call ends.
  - `_prepare_config` (:149-163): `folder = Path(tempfile.mkdtemp())`; skills go to `folder/muse/skills`.
  - `_overlay` (:177-186): `MUSE_NO_AUTO_UPDATE=1`, `XDG_CONFIG_HOME=launcher.visible_path(folder)`, and `MUSE_AUTH_PATH=<folder>/muse/auth.json` (never created).
  - `_serve_invocation`: `env_remove=(META_API_KEY,)`.
  - `_exec_invocation`: `exec --json --provider meta --workspace <ws> [--session-id] [--model] [--reasoning-effort] --user-input-auto-resolve -- <prompt>` in SEPARATE style; `env_overlay = launcher.environment({**overlay, META_API_KEY: api_key}, mark)`.
  - Will change: a `muse/settings.json` (`mcpServers`) in the per-call folder (request.md:334; the schema is unverified in the request).
- **`vidbyte/harnesses/native/muse/launcher.py`** (`MusePathTranslator` :41, `MuseLauncher` :56)
  - `environment(overlay, mark)` (:96-110): in WSL mode, "WSLENV forwards exactly the overlay's names into the distro" (`name + "/u"` for every overlay name, plus `VIDBYTE_PEER_MARK`).
  - `reap(mark)` (:139) kills the processes marked by this call inside WSL. It is the only reaper in `vidbyte/lib` and `vidbyte/harnesses` (git grep `reap(`).
- **`vidbyte/harnesses/native/muse/wire.py`**: `MuseWire` (:40; batch frames, `read_answer`) and `MuseExecOutput` (:137; records, session, terminal `run.terminal.*`).
- **`vidbyte/harnesses/native/hostkit/__init__.py`**
  - Today: `__all__ = ["NativeErrorFactory", "NativeLauncher", "NativeSkillFolders"]` (:20). It lives in harnesses because it uses `HarnessRedactor` (`vidbyte/harnesses/serialization.py:65`).
  - Will change: `hostkit/browser.py` (request.md:342: "shared main flow + reaper") would be exported here.
- **`vidbyte/harnesses/native/hostkit/errors.py`** (`NativeErrorFactory` :33; 224 lines)
  - `register_secret`; `scrub` (registered secrets first, then `HarnessRedactor`, then the last 1,000 chars).
  - `failure(problem, *, request, thread_id=None, outcome=None, vendor_text=None, seconds=None, cap_bytes=None, missing_member=None, searched=None)` looks up `code = native_threads.NATIVE_THREAD_FAILURE_CODES[(self._harness, problem)]` (:100).
  - `from_configuration_error` (:129) gives `CONFIGURATION_INVALID_ARGUMENT`; `from_unexpected` (:144) gives `RUNTIME_ERROR` with the class name only; `from_launch_failure` (:161).
  - The head comes from `NATIVE_MESSAGE_HEAD.format(operation=self._operation.value, code=code.value)` (:207).
  - Header (:7): "A new problem adds its NativeThreadProblem member, its summary and observation templates, its codes in NATIVE_THREAD_FAILURE_CODES and their texts".
- **`vidbyte/harnesses/native/hostkit/launcher.py`** (`NativeLauncher` :26): `resolve(command, *, program, fallback, errors, request) -> tuple[str, ...]`. Order: the explicit command, then `CliRunner.find_program`, then the fallback. It refuses `.cmd` / `.bat` on Windows. Relevant if tool servers (`node`, `npx.cmd`) are resolved the same way.
- **`vidbyte/harnesses/native/hostkit/skills.py`** (`NativeSkillFolders` :23): `replace(skills, destination)` and `remove(folder)`. It is the pattern for writing per-call private files.

### 2.2 Existing files: lib layer

- **`vidbyte/lib/enums/native_threads.py`** (199 lines)
  - All StrEnum: NativeHarness, NativeThreadVerb, NativeThreadOperation (9), NativeThreadProblem (10), GrokPermissionMode (`default, acceptEdits, dontAsk, plan`), GrokReasoningEffort, MuseReasoningEffort, GrokFlag (8), OpencodeFlag (7), MuseFlag (8), WslFlag, ShellFlag, NativeEnvironmentVariable (12), MuseMethod, OpencodeEventType (`text, error`).
  - Will change: new operations and problems; Grok `--allow` / `--deny` flags; `GROK_*_MCPS_ENABLED` env names; the opencode `tool_use` event type.
  - Pattern: StrEnum member, value = the vendor's literal.
- **`vidbyte/lib/enums/failure.py`**
  - `FailureCode(str, Enum)`. Unlike native_threads, it is not a StrEnum.
  - It has 148 string members (counted with `ast`, `py -3.11`). The last 28 follow `RULE_EVALUATION_FAILED`: `GROK_` / `OPENCODE_` / `MUSE_` × {NOT_INSTALLED, LAUNCHER_REFUSED, LAUNCH_FAILED, KEY_REJECTED, THREAD_NOT_FOUND, TIMED_OUT, OUTPUT_TOO_LARGE, PROTOCOL_MISMATCH, RUN_FAILED}, plus `MUSE_WSL_UNAVAILABLE` (the last member). Values look like `grok.not_installed`.
  - Header: "Add a category-prefixed code with docs, mapping coverage, and a focused test".
  - `tests/test_session_failures.py:143` requires every value to contain ".".
  - Will change: new closed codes (request.md:123 `browser.tools_unavailable`, :334 `browser.mount_unsupported`). See §4 for the tests that pin this.
- **`vidbyte/lib/enums/__init__.py`** (304 lines): imports native_threads enums at :119-134 and process enums at :143, with a sorted `__all__` at :180. Every new public enum is added here (AGENTS.md).
- **`vidbyte/lib/constants/native_threads.py`** (452 lines)
  - Tables used by name:
    - `NATIVE_THREAD_FAILURE_CODES[(NativeHarness, NativeThreadProblem)] -> FailureCode` (:349-380);
    - `NATIVE_THREAD_LIKELY_CAUSES` (:383-416) and `NATIVE_THREAD_NEXT_STEPS` (:419-452): exactly the 28 codes plus `CONFIGURATION_INVALID_ARGUMENT` and `RUNTIME_ERROR`;
    - `NATIVE_THREAD_SUMMARIES` and `NATIVE_THREAD_OBSERVATIONS` keyed by problem (:290-317);
    - `NATIVE_HARNESS_LABELS` and `NATIVE_TESTED_VERSIONS` (Grok 1.0.52, opencode 1.18.31, Muse 1.0.1).
  - Caps:
    - `GROK_CLI_MAX_OUTPUT_BYTES = 4194304` (:39); `NATIVE_PROCESS_MAX_OUTPUT_BYTES = 67108864` (:40);
    - `NATIVE_ARGV_PROMPT_MAX_CHARS = 24000` (:27); `NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS = 30000` (:32). Comment at :28-31: "the 2,766 left are for the program, options, paths and ids, whose measured worst case is 608 units".
    - `GROK_JSON_OUTPUT_FORMAT = "json"` (:124); `NATIVE_ENABLED_SWITCH = "1"`.
    - opencode config member names at :153-157.
  - Will change: browser texts, codes and tables (request.md:103 puts pinned versions and URLs in a new `lib/constants/browser_tools.py`).
  - Pattern: `MappingProxyType` tables with typed annotations; each group under a comment.
- **`vidbyte/lib/dataclasses/native_threads.py`** (228 lines)
  - `NativeThreadRequest` (:63): `harness, verb, prompt, api_key (repr=False), workspace, model=None, skills=(), thread_id=None`. The prompt cap is per harness (argv prompt caps plus a Windows UTF-16 check). The key pattern is `^[!-z|~]+$`. The workspace is resolved. Skills must each hold a `SKILL.md`, be unique, and number at most 32.
  - `GrokThreadConfig` (:158), `OpencodeThreadConfig` (:176), `MuseThreadConfig` (:193).
  - `NativeThreadResult(harness, thread_id, text, text_truncated)` (:213).
  - Will change, or gain siblings: a request record for tools and tool keys, and a result with tool calls and artifacts (request.md:103).
- **`vidbyte/lib/dataclasses/process.py`**
  - `CliOption(flag, value=None)` (:36).
  - `CliInvocation(argv, env_overlay (repr=False), timeout_seconds, max_output_bytes, cwd=None, stdin_text=None (repr=False), env_remove=())` (:51-60).
  - `CliOutcome(exit_code, stdout, stderr, stdout_truncated, stderr_truncated, timed_out, launch_failure=None)` (:73-82).
- **`vidbyte/lib/dataclasses/validation.py`**
  - `RecordFieldValidator` (:37): `require_text`, `accepts_text`, `require_optional_text`, `require_text_items`, `require_command_line_units`, `require_number`, `require_int`, `require_bool`, `require_enum`, `require_argv`, `require_directory`, and `_received` (:150), which never quotes a secret-named field.
  - `RecordFieldConverter` (:161): `to_tuple`, `to_mapping` (:176, returns `MappingProxyType[str, str]`), `to_enum`, `to_path`, `to_folder`, `to_files`, `require_instance`.
  - Will change only by adding options (field guide).
- **`vidbyte/lib/dataclasses/mcp.py`** (27 lines): `McpToolDefinition` (name, description, schema). Its header says "Defines small MCP protocol data contracts". It is an existing MCP domain module; see §4.
- **`vidbyte/lib/errors/base.py`** (615 lines)
  - `NativeThreadError(AgentExecutionError)` (:560-615) has `DIAGNOSTIC_FIELDS` and the keyword fields `failure_code, harness, operation, next_step, likely_cause, thread_id, exit_code, vendor_message, error_type`.
  - `expected = f"{operation.value} returning a NativeThreadResult"` (:601); `related_docs = ("vidbyte/harnesses/README.md",)`; `relevant_tests = ("tests/features/harness_threads",)`.
- **`vidbyte/lib/process/__init__.py`**: `__all__ = ["CliArgv", "CliRunner", "ProcessStopper"]` (:19).
- **`vidbyte/lib/process/runner.py`** (372 lines)
  - `ProcessStopper.stop_tree(process, *, grace_seconds) -> int | None` (:34). On POSIX it sends SIGTERM to the group, waits a bounded time, sends SIGKILL, then `_wait_group_gone`. On Windows it runs `taskkill /T /F /PID` from `%SystemRoot%\System32`.
  - `CliRunner.run(invocation) -> CliOutcome` (:186). It never raises except `CancelledError`. Stdout and stderr are drained into byte buffers capped at `max_output_bytes` (`_drain` :334), so output is **buffered whole and returned after the leader exits; nothing is streamed**.
  - `CliRunner.find_program(program) -> str | None` (:241) searches only absolute PATH folders, with PATHEXT on Windows.
  - `CliRunner.launch(...)` (:261) builds the child environment `{n: v for os.environ if n not in env_remove}`, then `.update(env_overlay)` (:278-279), with `start_new_session=sys.platform != "win32"` (:292).
  - `CliRunner.json_objects(text) -> list[Mapping[str, object]]` (:306) parses one JSON object per line.
  - Header :9: "On Windows, taskkill /T cannot reach a grandchild of a leader that already exited".
  - Will change: request.md:342 puts the "tool cache + env-filter launcher" in `lib/process/`.
- **`vidbyte/lib/process/argv.py`**:
  - `CliArgv.build(launcher, *, command=(), options=(), style, operands=()) -> tuple[str, ...]` (:26).
  - JOINED style gives `flag=value`. SEPARATE style refuses a value that starts with `-` (a `ConfigurationError` that names the flag).
- **`vidbyte/lib/registries/__init__.py`**
  - Eagerly imports every registry module, including `agents.py`, which imports `vidbyte.agents.types` at module level (`registries/agents.py:25`), and `prompts.py`, which imports `vidbyte.prompts.catalog` (:3).
  - Will change: a `browser_tools` registry (request.md:103) would be exported here.
- **`vidbyte/lib/registries/runtimes.py`** (69 lines): the model to copy. It is `RuntimeRegistry` with classmethods `resolve` / `validate` / `supported_runtimes`, lazy in-method imports, a dict keyed by an enum, and `ConfigurationError(f"Unknown runtime type '...'. Supported: {...}")`, with `__all__ = ["RuntimeRegistry"]`.
- **`vidbyte/lib/registries/README.md`**: holds source-citation tables, "checked <date>" for pricing and provider-key formats. It is the precedent for citing the source of each pinned version or URL in a registry. It has no Notes for agents section.
- **`vidbyte/lib/registries/provider_keys.py`** (312 lines): `ProviderKeyMatcher`, a pinned-table registry whose sources are cited in the README. Only its header and imports were read.

### 2.3 New files the request places (request.md:103, :342), and what each would follow

- `vidbyte/lib/enums/browser_tools.py`: follow `vidbyte/lib/enums/native_threads.py` (StrEnum, header with the WHAT-NOT-TO-DO list), and export from `vidbyte/lib/enums/__init__.py`.
- `vidbyte/lib/dataclasses/browser_tools.py`: follow `vidbyte/lib/dataclasses/native_threads.py`: frozen, slotted; `__post_init__` through `RecordFieldValidator` / `RecordFieldConverter`; bounds from constants; key fields `repr=False`.
- `vidbyte/lib/constants/browser_tools.py`: follow `vidbyte/lib/constants/native_threads.py` (grouped constants, `MappingProxyType` tables, no credential-named string constants).
- `vidbyte/lib/registries/browser_tools.py`: follow `runtimes.py` (classmethods, `ConfigurationError` naming the available names) and cite sources in `vidbyte/lib/registries/README.md` the way `provider_keys.py` and `pricing.py` do.
- `vidbyte/lib/process/<module>.py` (tool cache, env-filter launcher): follow `runner.py` (header, static class, failures returned as record fields).
- `vidbyte/harnesses/native/hostkit/browser.py`: follow `hostkit/skills.py` and `hostkit/errors.py` (a class with static methods, the literal `__all__`, no literals).
- `vidbyte/harnesses/native/{grok,opencode,muse}/mounts.py`: follow each harness's `_environment` / `_argv` static methods. Every literal comes from lib constants or enums (INV-15).
- A new test pack (for example under `tests/features/`): follow `tests/features/harness_threads/` (`README.md` with "Folder Description / Intent", "File Index", "Logs"; `FEATURE.md` with Contract / Invariants / Test Suite Map / Omitted Testing Strategies; `conftest.py`; a stdlib-only `fake_harness.py`).

### 2.4 Neighbours read that the request asks to reuse, correct or stay separate from (open question, request.md:415)

- **`vidbyte/lib/config/mcp_presets.py`** (1,833 lines)
  - `McpPresetDefinition` (:25-36) is a frozen, slotted record with `name: str, category: str, description: str, command: tuple[str, ...], required_env: tuple[str, ...], optional_env=(), default_env: Mapping | None = None, docs_url: str | None = None`. It has no version, transport, URL, per-capability tool names or auth style. `category` is a plain str. The record predates the Placement Rules.
  - `ALL_PRESETS` is at :1693.
  - Imported by `vidbyte/lib/config/__init__.py`, `vidbyte/tools/mcp/__init__.py`, `vidbyte/tools/mcp/presets.py` and `vidbyte/agents/mixins.py`.
  - Web and browser presets (category "Search & Web Research"; 18 entries):

    | Preset | Line | `command` | `required_env` |
    |---|---|---|---|
    | BraveSearchMCP | :41 | `npx -y @modelcontextprotocol/server-brave-search` | `BRAVE_API_KEY` |
    | GoogleSearchMCP | :49 | `npx -y @modelcontextprotocol/server-google-search` | (not recorded) |
    | TavilyMCP | :57 | `python -m mcp_server_tavily` | (not recorded) |
    | ExaMCP | :65 | `npx -y @exa-labs/mcp-server` | (not recorded) |
    | DuckduckgoMCP | :73 | `python -m mcp_server_duckduckgo` | none |
    | PuppeteerMCP | :81 | `npx -y @modelcontextprotocol/server-puppeteer` | none |
    | PlaywrightMCP | :89 | `python -m mcp_server_playwright` | none |
    | SearxngMCP | :97 | (not recorded) | `SEARXNG_URL` |
    | FirecrawlMCP | :105 | `npx -y @firecrawl/mcp-server` | `FIRECRAWL_API_KEY` |
    | JinaReaderMCP | :113 | `python -m mcp_server_jina_reader` | (not recorded) |
    | PerplexityMCP | :929 | (not recorded) | (not recorded) |
    | SerperMCP | :937 | (not recorded) | (not recorded) |
    | YouSearchMCP | :945 | (not recorded) | (not recorded) |
    | ApifyMCP | :953 | `npx -y apify-mcp-server` | `APIFY_API_TOKEN` |
    | BrowserbaseMCP | :961 | `npx -y @browserbase/mcp-server` | `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID` |
    | ZenrowsMCP | :969 | `python -m mcp_server_zenrows` | (not recorded) |
    | ScrapingbeeMCP | :977 | `python -m mcp_server_scrapingbee` | (not recorded) |
    | LinkupMCP | :985 | (not recorded) | (not recorded) |

    Elsewhere: `HttpClientMCP` (:1611).
- **`vidbyte/tools/mcp/presets.py`** (502 lines)
  - `McpPresetRegistry` holds a ClassVar per preset, plus `register`, `get` (raises `McpPresetNotFoundError`), `list_presets(category)` and `build_config(preset_name, env=None, permission=McpToolPermission.EXECUTE, timeout=30.0, extra_args=None) -> McpServerConfig`.
  - `build_config` merges `default_env` and `env`; a missing `required_env` raises `McpPresetConfigurationError`; a bare-string `extra_args` is refused.
  - It registers `ALL_PRESETS` at import time. It is in the tools layer.
- **`vidbyte/tools/mcp/types.py`**
  - `McpServerConfig` (:40) is frozen and slotted: `command, name=None, permission=McpToolPermission.EXECUTE, env=None, timeout=30.0`. It is stdio only: no URL, headers or validation.
  - `McpToolPermission(str, Enum)` (:31) is defined here; it predates the Placement Rules.
  - The module imports `vidbyte.tools.base` (tools layer).
- **`vidbyte/tools/builtins/operations/clients/browserbase.py`, `firecrawl.py`**: these exist (directory listed, files not opened). Request.md:403 describes them as SDK-agent HTTP clients, not harness mounts.
- **`vidbyte/__init__.py`** (1,376 lines): imports `from vidbyte.harnesses import (...)` (:419) and never imports `native`. The root `__all__` is pinned against merge-base by the surface test, and C016 covers it.
- **`vidbyte/lib/configs/__init__.py`**: re-exports structured-output constants only. Any edit here turns `test_branch_leaves...` red locally.
- **Docs that describe native/ and will need their text updated**:
  - `vidbyte/harnesses/README.md` (Key modules, the `native/` paragraph). It names EC-27, EC-43 (Grok homes are never removed), EC-44 (SDK Grok runs read nothing from `~/.grok`) and T-6 ("opencode also reads a workspace's own `opencode.json`").
  - `REPO_MAP.md:163-165` (`vidbyte/harnesses/native/`): "There are no host objects, model-facing tools or servers here; argv building and process runs go through the canonical helpers in `vidbyte/lib/process/`."
  - `REPO_MAP.md:219-221` (`vidbyte/lib/process/`).
  - `vidbyte/lib/README.md` (Key Modules: `process/`, `registries/`, `dataclasses/validation.py`).

## 3. Tests that cover those files

### 3.1 Framework and config

- pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml:48-49`).
- `testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]`, `asyncio_default_fixture_loop_scope = "function"` (`pyproject.toml:78-81`).
- No `asyncio_mode`, so async tests carry an explicit `@pytest.mark.asyncio` (for example `test_harness_threads_argv.py:97, :141`).
- Some older suites are `unittest` (for example `tests/test_mcp_stdio_transport.py`, `McpStdioTransportHardeningTests(unittest.IsolatedAsyncioTestCase)`).

### 3.2 `tests/features/harness_threads/` (pack for #1036; all 18 files read)

Fixtures (`conftest.py`):

- Constants: `HARNESSES = ("grok", "opencode", "muse")`, `VERBS = ("run", "continue", "fork")`, `API_KEY`, `PROMPT`, `OPENCODE_MODEL = "deepseek/deepseek-v4-pro"`, `CALL_TIMEOUT_SECONDS = 60.0`, `COMMAND_FIELDS = {grok: grok_command, opencode: opencode_command, muse: muse_command}`.
- `lib_api` (:208) imports lazily: `vidbyte.lib.dataclasses.native_threads`, `.process`, `vidbyte.lib.process`, `vidbyte.lib.errors`, `vidbyte.lib.enums.native_threads`, `vidbyte.lib.enums`, `vidbyte.lib.constants.native_threads`, `FailureCode`.
- `api` (:242): `functions[(harness, verb)] = getattr(native, f"{verb}_{harness}_thread")`.
- `sandbox` (:251): a Sandbox with home, ws, skill-src, bin, tmp, fake/log and fake/state. It sets `USERPROFILE`, `HOME` and `PATH` to the sandbox, and `tempfile.tempdir` to the sandbox tmp.
- `call(harness, verb="run", prompt, *, thread_id, command, fake, config, raw_config, **arguments)` (:263) passes `<harness>_command = sandbox.command(harness, **fake)` and `timeout_seconds = 60`.
- `check_error` (:296) asserts `error.operation == NativeThreadOperation(f"{verb}_{harness}_thread")` and the INV-5 sentence order.
- Also: `fast_stop`, `wait_until`, `alive`, `wsl_ready`, `pack`.
- `Sandbox.command(program, **fields)` returns `(sys.executable, "-u", FAKE, <scenario-NNN.json>)`.
- `Sandbox.stand_in` writes a runpy stub (or an `.exe` built from pip's distlib launcher on win32) so the fake can be found on PATH.

How the fake works (`fake_harness.py`, 683 lines, stdlib only, "never imported"):

- `argv[1]` is the scenario JSON. `main` (:666) dispatches on the scenario's `program` to `run_grok`, `run_opencode`, `run_muse_exec`, `run_muse_serve` or `run_wsl`. The `mode` field (default `"ok"`) scripts failures, holds, floods and secret echoes.
- Each process logs to `log_dir/<launch#>-<role>-<pid>.jsonl`. `start_record` (:161) logs argv, cwd, stdin kind, credential digests for `CREDENTIAL_NAMES` (:34; includes `OPENCODE_CONFIG_CONTENT`), plain values for `PLAIN_NAMES` (:35-38), `opencode_config` (sanitized JSON with every `apiKey` digested, :142), skills, and the Muse auth and XDG checks.
- Grok: `parse_joined` (:248) treats any element that is not `--flag=value` or `--fork-session` as a stray, and exits 2 on strays or a missing `--single`. Threads persist under `GROK_HOME` keyed by `--cwd`. Grok prints one JSON answer; there is no streaming-json mode.
- opencode: prints JSON events, including one `tool_use` event with `part.tool == "read"` (:414).
- None of the fakes reads MCP config or starts an MCP server. Header rules: "Do not import vidbyte ... Do not contact the network or run a real vendor CLI ... Do not log a credential value ... Never use shell=True."

What each file pins that the change can collide with:

| File | Pins |
|---|---|
| `test_harness_threads_surface.py` | `EXPECTED_EXPORTS` (:31, the 17-name `native.__all__`; each subpackage `__all__` is exactly its 3 `*_thread` names), checked at :122. The exact signature of the nine coroutines (:140). `EXPECTED_ENUMS` (:35), the exact value lists of 14 enums; every one must be a StrEnum exported from `vidbyte.lib.enums` (:161). The FailureCode tail (:176-195). `CONTRACT_CONSTANTS` (:53; for example `GROK_CLI_MAX_OUTPUT_BYTES`, `GROK_PRIVATE_HOMES_PARTS`, `NATIVE_THREAD_DEFAULT_SECONDS`). `lib_api.process.__all__ == ["CliArgv", "CliRunner", "ProcessStopper"]` (:212). `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` (:224, diffs `vidbyte/tools`, `vidbyte/lib/configs` and `docs/spec/native-grok-opencode-meta-hosts` against merge-base). `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` (:235) |
| `test_harness_threads_static_policy.py` | Walks `vidbyte/harnesses/native` with `rglob("*.py")` (:29). `NAMED_MODULES` (:20) must exist. Module level holds only a docstring, imports, classes, a literal `__all__` and `Class.attr` bindings in `__init__` (:82). The only literals allowed are docstrings, `__all__` strings, `""`, `0` and `1`; f-string parts count (:92). No `vidbyte.tools` import (:25, :107). No allow-lists |
| `test_harness_threads_argv.py` | `expected_argv` (:39), the exact plain argv per harness and verb. `test_runner_gets_plain_strings_the_call_timeout_and_the_harness_cap` (:143) pins the exact `env_overlay` key sets: Grok `{XAI_API_KEY, GROK_CODE_XAI_API_KEY, GROK_HOME, GROK_DISABLE_AUTOUPDATER}` (:159); opencode `{OPENCODE_CONFIG_CONTENT, OPENCODE_DISABLE_AUTOUPDATE}` (:165); Muse exec and serve sets. It also pins `max_output_bytes` (Grok 4 MiB) |
| `test_harness_threads_errors.py` | `DIAGNOSTIC_FIELDS` (:26). `related_docs` and `relevant_tests` exist (:183-185). `test_every_code_has_its_own_likely_cause_and_next_step` (:193-198): the cause and next-step tables cover exactly the 28 codes plus `CONFIGURATION_INVALID_ARGUMENT` and `RUNTIME_ERROR`, with no shared texts |
| `test_harness_threads_credentials.py` | `os.environ` is never written (:56-76, :164-177). `test_successful_call_writes_only_where_the_spec_allows` (:182-213): nothing is added or changed in the workspace, skills or home, except under the Grok private home, where only `skills/` and `sessions/` may appear; Muse's temp folder is gone. Also the secret-echo scrubbing tests |
| `test_harness_threads_acceptance.py` | AC-1 snippet; all nine functions end to end; the opencode config equals `{"provider": {...}}` exactly on the plain path |
| `test_harness_threads_wsl.py` | `FORWARDED = {META_API_KEY/u, MUSE_NO_AUTO_UPDATE/u, XDG_CONFIG_HOME/u, MUSE_AUTH_PATH/u, VIDBYTE_PEER_MARK/u}` (:28); `len(entries) == len(FORWARDED) + 1` (:69) |
| `..._threads.py`, `..._records.py`, `..._arguments.py`, `..._skills.py`, `..._runner.py`, `..._process_bounds.py`, `..._launcher.py` | Plain continue and fork identity; record validation; refusals before any I/O; skill locations; `CliRunner` overlay and `env_remove`; timeouts, caps, cancellation and tree stops; launcher resolution and batch refusal |

### 3.3 Other tests that touch the changed files

- `tests/test_session_failures.py:143` checks every `FailureCode` value contains `.`. It is run by `python scripts/test-session-failure-vocabulary.py`.
- `tests/test_mcp_stdio_transport.py` covers the SDK's own MCP transport. It is not touched unless `vidbyte/tools/mcp` changes.
- `tests/test_readme_size_limit.py` covers A009.

### 3.4 Commands

- One file: `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_surface.py`.
- Area: `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads`.
- Static policy only: `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_static_policy.py`.
- All: `py -3.11 -m pytest`. The full gate is `python scripts/run_ci.py` (§1.2).

### 3.5 Known-red tests

1. **`tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`** (:176-195).
   - When `origin/main` exists, it reads `vidbyte/lib/enums/failure.py` at `git merge-base origin/main HEAD` and asserts `len(main_members) == 120` (:193).
   - main now has 148 members (verified by an AST count), so the test is red on any up-to-date local checkout. CI skips that part because its shallow clone has no origin/main.
   - Separately from merge-base, lines :182-184 require the tail after `RULE_EVALUATION_FAILED` to be exactly the 28 harness codes. Any FailureCode appended at the end fails it everywhere, CI included.
2. **`tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`** (:360): an `McpProtocolError` timeout flake on CI 3.11 (field guide `local-ci-verification.md`).
3. **Branch-scoped, red locally only if this branch touches `vidbyte/tools`, `vidbyte/lib/configs` or root exports**: `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` (:224), and `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` (:235) when root `__all__` changes. Untracked files under those folders also count (:231-232).
4. Unverified here (from workspace memory, not opened this session): a real-bash SDK test that times out on GitHub runners.

## 4. Notes for the spec author (contradictions and gaps; no designs)

### 4.1 Public surface and closed vocabularies

1. Request §C.0.1 assumes "`tools=`/`tool_keys=` go on all nine existing functions" (request.md:101). Code shows the nine signatures pinned exactly at `tests/features/harness_threads/test_harness_threads_surface.py:140`. KD-1 (request.md:349) separately names new `<verb>_<harness>_with_browser` functions. Adding them changes `EXPECTED_EXPORTS` (surface:31) and the 3-name subpackage `__all__` checks (surface:122).
2. The request assumes new closed codes such as `browser.tools_unavailable` and `browser.mount_unsupported` (request.md:123, :241, :334). Code shows three obstacles:
   - The FailureCode tail must equal exactly the 28 harness codes (surface:182-184). This check is independent of merge-base, so appending any member fails it.
   - Inserting before `RULE_EVALUATION_FAILED` breaks the main-order assertion (surface:194) wherever origin/main exists.
   - The likely-cause and next-step tables must hold exactly 30 codes (`test_harness_threads_errors.py:193-198`).
3. The request assumes failures go through `NativeErrorFactory`, raising "one `NativeThreadError` with a closed `FailureCode`" (KD-6). Code shows the factory reaches a code only through `NATIVE_THREAD_FAILURE_CODES[(harness, problem)]` (`hostkit/errors.py:100`; `constants/native_threads.py:349`).
   - All 28 codes are per harness, so a harness-neutral `browser.*` code has no `(harness, problem)` shape.
   - `NativeThreadProblem` (10 members) is pinned in `EXPECTED_ENUMS` (surface:35).
4. The browser functions need operation names. Code shows:
   - `NativeErrorFactory(harness, operation)` takes `NativeThreadOperation`, which has 9 pinned members (surface:35).
   - The message head prints `operation.value` (`hostkit/errors.py:207`).
   - `NativeThreadError.expected` is hard-wired to `"{operation} returning a NativeThreadResult"` (`vidbyte/lib/errors/base.py:601`).
   - `check_error` asserts `NativeThreadOperation(f"{verb}_{harness}_thread")` (`conftest.py:296`).
5. A result with tool calls and artifacts (request.md:236) is a new record. `NativeThreadResult` has exactly `harness, thread_id, text, text_truncated` (`vidbyte/lib/dataclasses/native_threads.py:213`).
6. Enum additions: every new member of `GrokFlag` (8), `NativeEnvironmentVariable` (12) or `OpencodeEventType` (`text`, `error`) changes the pinned `EXPECTED_ENUMS` lists (surface:35). Request.md:327-331 needs `--allow`, `--deny`, `streaming-json`, `GROK_CLAUDE_MCPS_ENABLED` and `GROK_CURSOR_MCPS_ENABLED`; request.md:236 needs opencode `tool_use`.

### 4.2 Injection points in the #1036 flows

7. The request assumes per-harness mount plans can be applied to the existing flows (request.md:96, :396). Code shows no `execute` method takes extra env, argv, config members or private files:
   - `execute(request, config, errors)` at `opencode/threads.py:85`, `grok/threads.py:93` and `muse/threads.py:90`.
   - `OpencodeWire.config_content(request)` builds only `provider` and `skills` (`opencode/wire.py:40-51`).
   - The plain shapes are pinned: argv (`test_harness_threads_argv.py:39`), the env-overlay key sets (argv:143-165), the opencode config (acceptance) and the Muse WSLENV set (`test_harness_threads_wsl.py:28, :69`).
8. Grok streaming. The request assumes Grok switches to `--output-format=streaming-json` to see tool calls (request.md:118, :331, :413). Code shows:
   - `GROK_JSON_OUTPUT_FORMAT = "json"` (`constants/native_threads.py:124`) is used at `grok/threads.py:172`.
   - `GrokWire._answer` parses "The whole stdout as one JSON object" (`grok/wire.py:85-92`).
   - `CliRunner.run` buffers whole output and returns after the leader exits; nothing is streamed (`lib/process/runner.py:186, :334`).
   - Grok output is capped at `GROK_CLI_MAX_OUTPUT_BYTES = 4194304` (`constants:39`, pinned in `CONTRACT_CONSTANTS`).
   - The fake grok prints one JSON answer only.
   - Unverified: how large a streaming-json run with browser tool calls gets.
9. Grok MCP leak. The request assumes `GROK_CLAUDE_MCPS_ENABLED=0` and `GROK_CURSOR_MCPS_ENABLED=0` close the leak (request.md:55, :399, :414). Code confirms `_environment` sets only four names (`grok/threads.py:155-165`), and argv:159 pins exactly that set for plain Grok, so changing the plain path also changes that test.
10. Grok private home. The request assumes Grok MCP config goes into `$GROK_HOME/config.toml` (request.md:316). Code shows:
    - The home is keyed only by a hash of the workspace and is shared by every call in that workspace (`grok/threads.py:135-153`). It is never removed (`vidbyte/harnesses/README.md`, EC-43).
    - A file written there stays for later plain `run_grok_thread` calls in the same workspace.
    - The plain-path credentials test allows only `skills/` and `sessions/` inside the home (`test_harness_threads_credentials.py:199-206`).
    - No per-home lock exists: hostkit exports only three classes (`hostkit/__init__.py:20`).
11. Grok command-line budget. The request adds `--allow=MCPTool(...)` and `--deny` options to Grok's argv (request.md:327). Code shows the Grok prompt itself rides in argv (`--single=`). The Windows budget allows 30,000 UTF-16 units for the prompt and "the 2,766 left are for the program, options, paths and ids, whose measured worst case is 608 units" (`constants/native_threads.py:28-32`). Extra options eat into that remainder.
12. Muse WSL forwarding. The request assumes tool keys reach Muse's MCP servers through env (request.md:334, :411). Code shows `MuseLauncher.environment` forwards every overlay name into WSL through WSLENV (`muse/launcher.py:96-110`), and the plain set is pinned to five entries (`wsl.py:28`).
    - In WSL mode, `XDG_CONFIG_HOME` is the `/mnt/...` form of a Windows `tempfile.mkdtemp()` folder (`muse/threads.py:149-163, :177-186`).
    - That folder is deleted in `finally` (`muse/threads.py:142-146`), so anything written there, artifacts included, is gone after the call.
13. opencode workspace config. The request assumes the run uses only the chosen tools (KD-3 layer 7). `vidbyte/harnesses/README.md` (native paragraph, T-6) says "opencode also reads a workspace's own `opencode.json`". Unverified: whether a workspace's MCP servers merge into the inline config.

### 4.3 Layering and placement

14. lib/process exports. The request places a "tool cache + env-filter launcher" in `lib/process/` (request.md:120, :244, :342). The header of `vidbyte/lib/process/__init__.py:7` says new helpers are exported from its literal `__all__`. But `test_harness_threads_surface.py:212` pins `__all__ == ["CliArgv", "CliRunner", "ProcessStopper"]`. The header and the test contradict each other.
15. The tool cache (request.md:389) writes `~/.vidbyte/tools/<name>@<version>` under the user home. The plain-path write test allows nothing under home except the Grok private home (`credentials.py:199-208`).
16. Reusing the MCP stack (open question, request.md:415). Code shows:
    - INV-20 forbids any `vidbyte.tools` import in native/ (`test_harness_threads_static_policy.py:25, :107`), and `McpServerConfig` / `McpPresetRegistry` live in the tools layer (`vidbyte/tools/mcp/types.py:40`, `presets.py`).
    - A lib module importing them is an A006 lower→orchestration edge (`a006_directed_dependency_graph.py:80-85`).
    - `McpPresetDefinition` sits in lib (`vidbyte/lib/config/mcp_presets.py:25-36`) but has no version, transport, URL or tool names, and `category` is a plain `str`.
    - Any edit under `vidbyte/tools` turns `test_branch_leaves...` red locally (§3.5 item 3).
17. Preset facts versus the request:
    - Request.md:401 says `@browserbase/mcp-server` and `@firecrawl/mcp-server` return E404 and PyPI `mcp-server-playwright` returns 404. Code names exactly those at `mcp_presets.py:965, :109, :93`. The 404 status itself is unverified here (no network).
    - Request.md:402 says "11 of its 15 web presets". Code has 18 presets in category "Search & Web Research" (`mcp_presets.py:41-119, :929-991`).
18. native/ scope. The request places `hostkit/browser.py` ("shared main flow + reaper") and `<h>/mounts.py` in native/ (request.md:342). The field guide (`blocking-lint-invariants.md:63`) says "Code that serves model-facing tools for a harness does not belong in `native/`". `REPO_MAP.md:165` says native/ has "no host objects, model-facing tools or servers". Whether compiling another program's MCP config counts as serving tools is unresolved; the spec must state it.
19. Dataclass placement. The request places records in a new `lib/dataclasses/browser_tools.py`. An MCP domain module already exists: `vidbyte/lib/dataclasses/mcp.py` (`McpToolDefinition`). AGENTS.md says "Add to the existing domain module when there is one". The spec should state which domain the records belong to.
20. Registry import cost. `vidbyte/lib/registries/__init__.py` eagerly imports `agents.py`, which imports `vidbyte.agents.types` at module level (`registries/agents.py:25`), and `prompts.py`, which imports `vidbyte.prompts.catalog` (:3). Importing any `vidbyte.lib.registries.<x>` from native/ runs that `__init__`. Unverified: whether this creates an import cycle or slows the import of `vidbyte.harnesses.native`.

### 4.4 Lifecycle, cleanup and secrets

21. Browser cleanup. The request assumes "a browser reaper kills any Chrome" (request.md:236; KD-3 layer 10). Code shows:
    - `ProcessStopper.stop_tree` reaches only the leader's process group on POSIX.
    - On Windows, `taskkill /T` "cannot reach a grandchild of a leader that already exited" (`runner.py:9`).
    - The only reaper in the SDK is Muse's WSL mark reaper (`muse/launcher.py:139`, `MUSE_REAP_SCRIPT` in constants :236-259).
    - Request.md:398 says Playwright detaches Chrome into its own group on POSIX.
22. Secret handling:
    - `errors.register_secret` exists per call. `scrub` replaces registered secrets, then runs `HarnessRedactor`, then truncates to 1,000 chars.
    - `RecordFieldValidator._received` hides values of secret-named fields (`validation.py:150`, via `CredentialKeyPolicy` at `vidbyte/lib/util/credential_keys.py:52`; not read in full).
    - The constants header forbids credential-named string constants (S054) and credential-word-plus-`:`/`=` phrasing in texts (`constants/native_threads.py:8-9`).
    - `HarnessRedactor` (`vidbyte/harnesses/serialization.py:65`) was located but not read in full; its exact patterns are unverified.
23. A001 and C019 risk. Every new module needs the A001 header fields. New snake_case constants or dict keys of three or more tokens fall under C019's platform-contract check. Unverified: whether any proposed name collides with a platform error-code family.

### 4.5 Test infrastructure

24. The request assumes a fake harness that "actually starts the fake MCP server named in the compiled config" (request.md:340, :369). Code shows `fake_harness.py` reads no MCP config, starts no server, has no Grok streaming-json mode, and logs only the fixed `CREDENTIAL_NAMES` and `PLAIN_NAMES` (`fake_harness.py:34-38`).
25. Gate reference error. `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md:19` says semgrep "is part of" `run_ci.py`. Code shows `scripts/run_ci.py:79-93` does not run semgrep; it runs in `.github/workflows/static-policy.yml:24-30`.

### 4.6 Unverified (consolidated)

- Muse `settings.json` / `mcpServers` schema (request.md:334, :411).
- The real size of Grok streaming-json output.
- The 404 status of the preset packages.
- How opencode merges a workspace `opencode.json`'s MCP servers.
- `HarnessRedactor` patterns.
- Import-cycle risk from `vidbyte.lib.registries`.
- C019 collisions.
- The real-bash known-red test.
- The contents of `vidbyte/tools/builtins/operations/clients/{browserbase,firecrawl}.py` (existence only).
- `vidbyte/lib/registries/provider_keys.py` and `pricing.py` beyond their headers.
