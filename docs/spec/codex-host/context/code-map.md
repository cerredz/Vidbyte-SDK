# CodexHost code map (S0 scout)

Scope: request.md §C, the 14 ★ rows (15 functions), plus `CodexSpawnRequest`, `CodexHost`, the `codex.<problem>` error mapper, one tool per ★ function, a toolset, and contract tests.

- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host`.
- Base: `678136bd4358bcf9f120504cecd818d36a3d46fe`, with no commits on top. `git status --porcelain` shows only `docs/spec/codex-host/` untracked.
- `CLAUDE.md` is the single line `@AGENTS.md`.

How the facts were gathered:
- Every `path:line` below was opened in this session with `cat`, `sed -n`, `awk`, `grep -n` or `git grep`.
- Nothing was executed: no lint, pytest, gate, pip, or import.
- Anything not checked is marked **unverified**.

Third-party paths are written `openai_codex/<file>`. They are relative to `C:/Users/422mi/vidbyte-repos/vidbyte-cli/.venv/Lib/site-packages/openai_codex/` (version 0.162.1).

## 1. Rules and commands that bind this change

### AGENTS.md rules, with heading, quote and line

| # | Heading | Quote | Line |
|---|---|---|---|
| 1 | Repository Map | "Read it before you create a file, move code, or search for where something lives" … "regenerate a wrong entry from the tree instead of patching around it" | AGENTS.md:9 |
| 2 | Repository Map | Folder READMEs: "read it to the end before you change anything inside the folder"; "lint rule A009 keeps every folder README at or under 40,000 characters" | AGENTS.md:11 |
| 3 | Repository Map | "**Do not grep, glob, or read files under `docs/` as part of ordinary work**" | AGENTS.md:13 |
| 4 | Repository Map | "run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it" | AGENTS.md:13 |
| 5 | Repository Map | Placement Rules "are binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request" (§4 C27: the workflow is manual-dispatch only) | AGENTS.md:15 |
| 6 | 1. Keep Call Chains One Level Deep | "a function may call another of its own functions, but that second function should not call a third"; "Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator" | AGENTS.md:23 |
| 7 | 2. Narrate Main Functions in Plain English | "place short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments" | AGENTS.md:27 |
| 8 | 3. Build in Layers of Small, Single-Purpose Classes | "nothing in `vidbyte/lib/` may import from a layer above it"; "Keep files well below 1,000 lines" | AGENTS.md:31 |
| 9 | 4. Use Validated Dataclasses for Core Inputs and Outputs | "Prefer `@dataclass(frozen=True, slots=True)`" … "type any field whose value comes from a small, closed set as an enum" | AGENTS.md:35 |
| 10 | 5. Write Shared Logic Once, as a Canonical Helper in `lib/` | "look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the option you need to it" | AGENTS.md:41 |
| 11 | Dataclasses go in `vidbyte/lib/dataclasses/` | "Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`" | AGENTS.md:47 |
| 12 | (same) | "Do not create `types.py`, `records.py`, `models.py`, or `schemas.py` modules" | AGENTS.md:49 |
| 13 | (same) | "If a dataclass seems to need a type from a higher layer, move the contract down (a `Protocol` or a smaller record in `vidbyte/lib/`)". The only two exceptions are agent `*Settings` classes and JEV preflight questions (AGENTS.md:54-57) | AGENTS.md:52 |
| 14 | Enums go in `vidbyte/lib/enums/` | "every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions." | AGENTS.md:61 |
| 15 | (same) | "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder" | AGENTS.md:63 |
| 16 | Existing code | Older modules that define records elsewhere: "Do not copy them as precedent." | AGENTS.md:81 |

AGENTS.md has no install, lint or test commands other than `run_ci`, and no PR or commit conventions.

### Field-guide topics that apply

All topics are in `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`. Each was read in full; `init.md` is the index.

**`local-ci-verification.md`**
- In a worktree, run `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no `PYTHONPATH`. The reason given: "The editable install resolves `vidbyte` to the canonical checkout".
- Semgrep scans only git-tracked files.
- Stage merge resolutions before trusting lint. Unmerged paths triple findings, for example "A001 645→643".
- Check S051 with ruff over the whole `vidbyte` tree.

**`blocking-lint-invariants.md`**
- "S012 flags any method named `request` as an outbound call without a timeout" (S012 baseline 0).
- "A003 requires the full DIAGNOSTIC_FIELDS packet on every new class in vidbyte/lib/errors/base.py".
- "A lib record that holds a higher-layer object checks its shape, not `isinstance`". Annotate the field under `TYPE_CHECKING`; A006 counts function-local imports.
- No `dict[str, Any]` wire encoders on lib records (S060), and `TypedDict` is banned (S039).
- A007 flags literals passed to operational calls.

**`strict-config-dataclasses.md`**
- "Harness bridge functions take validated lib records, not loose `object`/`Mapping` inputs … keep private SDK attribute access out of lib (lib cannot import the optional extra)".
- "Validate inherited provider settings before creating a native fork".
- "Keep reusable validation bounds in the shared constants package".
- Local size caps should be generous.

**`class-bound-helpers.md`**
- "Prefer a static helper class over a bag of module-level free functions".
- "Separate shared abstraction translation from provider serialization".
- "A must-not-raise callback gets one try spanning parse, schedule, and wait".

**`model-facing-tool-contracts.md`**
- Give the tool and every parameter "a consistent 4–5 sentence general description", and "omit concrete examples".
- Categorical parameters are `str, Enum` classes under `vidbyte/lib/enums`.

**`provider-api-contracts.md`**
- "One guarded try per provider call, with typed branches".
- "Never catch `BaseException`, so cancellation propagates."

**`comment-format.md`**
- Multi-line comments wrap at 72 columns and sit directly above the code they explain.
- `# @intent <name>` goes on its own first line.
- This is not a lint rule.

### Commands

Run all commands from the worktree root.

| Purpose | Command | Source |
|---|---|---|
| Install | `python -m pip install -e ".[dev]"`. The dev extra excludes `codex` (`openai-codex>=0.162.1,<0.163.0`, pyproject.toml:42-44) | CONTRIBUTING.md:35; `.github/workflows/ci.yml` |
| Lint, all rules against the baseline | `python lint/run.py` | CONTRIBUTING.md:67-70 |
| Lint, one rule | `python lint/run.py --rule A001` | lint/run.py:36 |
| Lint, every finding, or JSON output | `python lint/run.py --all`, `python lint/run.py --format json` | lint/run.py:37-38 |
| Test, one file | `PYTHONPATH=$(pwd) python -m pytest -q tests/test_codex_tools.py` | header form in `tests/features/coding_agent/conftest.py`; field guide |
| Test, codex area | `PYTHONPATH=$(pwd) python -m pytest -q tests -k codex` | pytest config at pyproject.toml:78-81 |
| Gate, source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | scripts/run_ci.py:79-93; field guide |
| Gate, package stage | `python scripts/run_ci.py --stage package`, with no `PYTHONPATH` | field guide; CONTRIBUTING.md:62-64 |
| Gate, full | `python scripts/run_ci.py` | AGENTS.md:13; CONTRIBUTING.md:56 |
| Public API contract | `python scripts/generate-sdk-public-api.py`, then `--check`; `python lint/run.py --rule C016` | lint/rules/c016_public_api_contract_current.py |
| Semgrep (not part of `run_ci`) | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `semgrep==1.170.1` | .github/workflows/static-policy.yml:23-30 |

**What the source stage runs** (scripts/run_ci.py:79-93), in order:
- a check that no bytecode is tracked;
- `lint/run.py`;
- `compileall -q vidbyte`;
- three `scripts/check_*.py` checks;
- `python -m pytest`.

The package stage builds the wheel, runs twine, and installs the wheel alone into a clean venv, without `[codex]`. It then runs a smoke program that imports `vidbyte`.

**Verdicts**
- Lint ends with `SDK-LINT: PASS` or `SDK-LINT: FAIL` (lint/core/report.py:58).
- `run_ci` ends with `CI passed.` (scripts/run_ci.py:282).
- A rule fails when it is REGRESSED (found > allowance) or ERRORED (lint/core/baseline.py:60-68; lint/core/runner.py:37).
- `--update-baseline` exists (lint/run.py:39), but request.md:204 forbids raising any number in `lint/baseline.json`.

**What lint wraps**
- Lint also runs mypy over `vidbyte` with `lint/mypy.ini` (lint/core/mypy.py:56; rule S009).
- It runs ruff over `pyproject.toml vidbyte` with a wide selector list (lint/core/ruff.py:26-34, 68).
- Tests are not ruff- or mypy-checked. A001 and S062 do scan every tracked `.py` file, tests included.

### PR and commit conventions

- **Request:** draft PR only; "Never merge, never mark ready" (request.md:167). Catch up with main by merging origin/main, never by rebasing after the first push (request.md:145).
- **CONTRIBUTING.md:38-45:** work on a focused branch from the latest `main`. Do not commit bytecode, venvs, build output or credentials.
- **PR body** (CONTRIBUTING.md:75-85 and `.github/pull_request_template.md`, read in full): sections Motivation, Changes, Compatibility, Verification and Follow-ups. Verification lists the exact commands run and their output, plus a checklist.
- **Commit subjects on main** use `type(scope): summary (#PR)`, for example `fix(coding): read AGENTS.md and MAP.md that Windows PowerShell writes as UTF-16 (#995)` (`git log --oneline` at 678136bd).
- **CI is manual.** `ci.yml` triggers only on `workflow_dispatch`/`workflow_call`. It installs `.[dev]`, runs `run_ci --stage source` on 3.11 and 3.12, and runs the package job on 3.11. `static-policy.yml` (Semgrep) and `agents-md-placement.yml` are also manual-dispatch only.

## 2. Files: what they do today, what changes, the pattern to follow

Status labels:
- **NEW:** this PR creates the file.
- **EDIT:** changed in place.
- **SHARED:** on the request's append-only list (request.md:163).
- **COND:** edited only if the spec chooses that option.
- **READ:** reuse; do not change behaviour (request.md:194).
- **NEIGHBOUR:** third-party, read-only.

### 2.1 New files under `vidbyte/harnesses/native/`

**`vidbyte/harnesses/native/__init__.py`** (NEW; bytes fixed by the request)
- **Today:** does not exist. `vidbyte/harnesses/` tracks 14 files and has no `native/` (`git ls-files vidbyte/harnesses`).
- **Change:** request.md:147-153 fixes four lines: a module docstring naming "Native coding-harness hosts", LF line endings, a final newline. request.md:154 adds: "If a lint rule rejects these bytes, make the smallest change that passes and record the exact final bytes under OPEN ITEMS".
- **Pattern:** A001 rejects those bytes (§4 C1).
  - Headers that pass: `vidbyte/tools/toolsets/coding.py:1-12` (single-line `FIELD: value`) or `tests/test_codex_tools.py:1-48` (field line, then an indented value).
  - Both match A001's regex `(?im)^\s*FIELD\s*(\S.*)$` (lint/rules/a001_agent_readable_file_headers.py:51-54).
  - Nothing auto-imports `vidbyte.harnesses.native`: `vidbyte/harnesses/__init__.py:37-63` imports only its own modules and `stores`.

**`vidbyte/harnesses/native/codex/__init__.py`** (NEW)
- **Change:** exports the host and its functions. request.md:154: "Host classes are imported from their own subpackage (`vidbyte.harnesses.native.codex`)".
- **Pattern:**
  - Give the package `__init__` a list-literal `__all__` and an A001 header. S015 requires every `__all__` entry to be bound.
  - Nothing reachable from `import vidbyte` may import `openai_codex` at module level. The package-stage smoke test installs the wheel without the extra.
  - Precedent for the lazy load: `CodexTransport._load_sdk` (vidbyte/agents/codex/transport.py:215-259). It raises `CodexAgentError(failure_code=FailureCode.CODEX_SDK_UNAVAILABLE.value, operation="load_sdk")` and builds `CodexSdkTypes` (vidbyte/lib/dataclasses/codex.py:1186).

**`vidbyte/harnesses/native/codex/*.py`** (NEW: host, ★ functions, handles, error mapping; module names are the spec author's)
- **Change:** `CodexHost`, an async context manager over one app-server client plus the turns it started (request.md:117-120); 15 functions; the `codex.<problem>` mapper (request.md:124-127).
- **Translators to reuse** (§2.4):
  - `CodexContentTranslator` (vidbyte/agents/codex/config.py:121-282);
  - `CodexVidbyteTranslator.translate_input`, which takes a `str`, `AgentInput` or `CodexRunInput` and returns a `CodexRunInput` (config.py:99-118);
  - `CodexResultSerializer.from_sdk`, which turns a `TurnResult` into a `CodexRunResult` (vidbyte/agents/codex/result.py);
  - `CodexMetricsTranslator.record_usage` (vidbyte/agents/codex/metrics.py:37-50).
- **Concurrency precedent:** a one-slot `asyncio.Semaphore(CODEX_MAX_CONCURRENT_TURNS)` "rather than a Lock because the SDK bans asyncio.Lock" (vidbyte/agents/codex/agent.py:84-86).
- **Lint scope:**
  - S016 (builtin raises) and S017 (`str(exc)` into errors) do not cover `vidbyte/harnesses/`.
  - A002, A005, A007, S006, S007, S008, S009, S012, S019, S024, S039, S045, S051 and S063 scan all of `vidbyte/`.
- **Import edges:**
  - Today `vidbyte/harnesses/**` imports only `vidbyte.harnesses.*`, `vidbyte.sessions.*` and `vidbyte.lib.*`.
  - Importing `vidbyte.agents.codex.config` also pulls `vidbyte.agents.codex.tools`, which imports `vidbyte.tools.catalog` and `vidbyte.tools.executor` (config.py:9-11; tools.py:42-43).
  - A006 allows orchestration→orchestration edges but no cycles.
  - Precedent for tools importing agents at module level: `vidbyte/tools/builtins/fork/fork.py:22-23`.

**`vidbyte/harnesses/native/codex/README.md`** (optional NEW)
- No lint rule requires a README in every folder:
  - A009 only caps size (`MAXIMUM_CHARACTERS = 40_000`, lint/rules/a009_readme_size_limit.py:20).
  - S020 checks only READMEs that contain a File Index section.
  - C015 requires a README under `vidbyte/` not to be shipped. Package data covers only prompt assets (pyproject.toml:68-76).
- So `vidbyte/harnesses/native/README.md` must not be created (request.md:155-160).

### 2.2 New files under `vidbyte/tools/`

**`vidbyte/tools/builtins/codex/__init__.py`** (NEW)
- **Pattern:** `vidbyte/tools/builtins/sessions/__init__.py:17-39`: one import per tool module and a list-literal `__all__`. Its "Context Protocol Header" docstring fails A001 (it is part of the 643 debt), so do not copy the header style.
- **Exposure:** every public `BaseTool` subclass exported from `vidbyte.tools.builtins` becomes nameable from YAML through `ComponentRegistry._discover("tools")`. It is then built as `component(**options)`, and a `TypeError` or `ValueError` becomes a `ConfigurationError` (vidbyte/lib/registries/components.py:65-74, 101-124).

**`vidbyte/tools/builtins/codex/_base.py`** (NEW)
- **Pattern:** `_SessionBuiltinTool(store, *, scope)` (vidbyte/tools/builtins/sessions/_base.py:30-93). The constructor binds the dependency, and the class provides:
  - `bind_owner` (43), `bind_session` (47), `clone_for_fork` (52), `clone_for_agent` (58);
  - `_optional_text`, which treats JSON null as omitted (67-73);
  - `_caught`, which turns `SessionError` into `ToolResult.error` (85-90).
- `_caught` interpolates `exc`. That is S017 debt, and S017 covers `vidbyte/tools/`.
- **Agent binding:** `BaseAgent` binds and copies only the classes listed in `_bind_agent_tool_context` and `_own_tool` (vidbyte/agents/base.py:421-482). Forks duck-type `clone_for_agent` and `clone_for_fork` (vidbyte/agents/fork.py:181-198). See §4 C18.

**`vidbyte/tools/builtins/codex/descriptions.py`** (NEW)
- **Pattern:** `vidbyte/tools/builtins/sessions/descriptions.py` holds description constants imported by the tools, for example `fork.py:20`. It uses adjacent string literals, which is S062 debt. S062 scans every tracked `.py` file, baseline 889.
- **S025** (baseline 263) needs at least 4 sentences in each `ToolSpec.description` and `ToolParameter.description`. It resolves module constants and up to 3 import hops. It does not check `input_schema` property descriptions.

**`vidbyte/tools/builtins/codex/<group>.py`** (NEW, one file per group of tools; request.md:113)
- **Pattern:** `ForkTool` (vidbyte/tools/builtins/sessions/fork.py:27-92). `spec()` returns `ToolSpec(name, description, permission, input_schema)`, and `async execute(call)` never raises.
- **Records:**
  - `ToolSpec` (vidbyte/lib/dataclasses/tools.py:115-136) checks only that name and description are non-empty.
  - `ToolResult.error(tool_name, output, *, metadata)` (tools.py:314-327) has no code field.
  - `ToolPermission{SAFE, READ, WRITE, EXECUTE}` (tools.py:47-53).
  - The default `PermissionPolicy.allowed` is `{SAFE, READ}` (vidbyte/lib/dataclasses/security.py:30-43).
  - `BaseTool.execute` is abstract async (vidbyte/tools/base.py:83).
- **Bound precedent:** `PauseAgentTool(max_seconds=_DEFAULT_MAX_SECONDS)` (vidbyte/tools/builtins/pause.py:93-96), described in vidbyte/tools/README.md:93-101.
- **Rules in scope:** S016, S017, S025, A007, S062.

**`vidbyte/tools/toolsets/codex.py`** (NEW)
- **Pattern:** `CodingAgentTools(Tools)` (vidbyte/tools/toolsets/coding.py:47-57). Its `__init__` takes one validated settings record and calls `super().__init__(tools)`. The full A001 header is at coding.py:1-12.
- `Tools` rejects duplicate tool names with `ToolRegistrationError` (vidbyte/tools/catalog.py:30-42).

### 2.3 Edited files

**`vidbyte/lib/dataclasses/codex.py`** (EDIT; 1,205 lines)

Records it holds today:
- **`CodexClientSettings`** (101-135): `codex_bin: str = ""` (105), `env` (109), `experimental_api: bool = True` (113).
- **`CodexSubagentSettings`** (138-182): `max_concurrent_threads: int = 0` (143).
- **`CodexThreadSettings`** (185-243), fields 189-203: `approval_mode`, `base_instructions`, `cwd`, `model`, `model_provider`, `personality`, `sandbox`, `service_name`, `service_tier`, `session_start_source`, `thread_source`, `ephemeral`, `config`.
- **`CodexTurnSettings`** (246-273), fields 250-257: `approval_mode`, `cwd`, `effort`, `model`, `personality`, `sandbox`, `service_tier`, `summary`.
- **`CodexAgentSettings`** (276-296): client, thread, turn and subagents.
- **`CodexHarnessAgentSettings`** (319-413): `output_schema` (333) and `tools: tuple[ToolInput, ...]` (342), checked by `_is_tool_shaped` (81).
- **Inputs** (416-472) and **`CodexRunInput`** (484-536): items, recipient, metadata, context items and placements.
- **`CodexForkSettings`** (625-692): an agent-fork record with `system_prompt`, `codex`, `context_manager`, `output_schema`, `capabilities` and `clear_*` fields. It has no turn id.
- **Results:** `CodexUsage` (711-721); `CodexRunResult` (764-784), with `status: str`, `last_usage` and `usage_available`.
- **Requests:** `CodexUsageTranslationRequest` (844-867), `CodexToolAttachRequest` (1081), `CodexSdkTypes` (1185-1202).
- **Validators:** `_require_text` (55), `_optional_text` (60), `_require_non_negative_int` (69), `_require_bool` (76), `_is_json_value` (88).
- **Exports:** `__all__ = [name for name in globals() if name.startswith("Codex")]` (1205), so every new `Codex*` name is exported automatically.

Change and constraints:
- **Change:** add the new records here (request.md:123).
- **Constraints:**
  - The file is already past the AGENTS.md:31 guidance (§4 C26).
  - C008 (baseline 45) flags a new primitive validator defined anywhere except `vidbyte/lib/dataclasses/validation.py`, which does not exist yet (lint/rules/c008_shared_validator_owner.py:24).
  - C006 requires range checks to reject bool, NaN and inf.
  - C007 requires an `isinstance(bool)` check on bool switches in `*Settings`, `*Config`, `*Policy` and `*Options` classes.
  - C002: do not repeat a bool guard for a field name that is already guarded.
  - S060: no `dict[str, Any]` in public signatures here.
  - A006: no runtime import of `vidbyte.tools` or `vidbyte.agents`; `TYPE_CHECKING` imports only.

**`vidbyte/lib/enums/codex.py`** (EDIT; 120 lines)
- **Today:**
  - `CodexApprovalMode{"", auto_review, deny_all}` (17-22)
  - `CodexPersonality` (25-31)
  - `CodexReasoningEffort` (34-43)
  - `CodexReasoningSummary` (46-53)
  - `CodexSandbox{"", read-only, workspace-write, full-access}` (56-62)
  - `CodexThreadSource{"", user, subagent, memory_consolidation}` (65-71)
  - `CodexThreadStartSource{"", startup, clear}` (74-79)
  - `CodexFailureClass{model_retryable, transient, terminal}` (82-87)
  - `CodexInputType` (90-97)
  - `CodexContextAnchor(StrEnum)` (100-106)

  The style is `str, Enum`, with `PROVIDER_DEFAULT = ""` meaning "omit".
- **Change:** add new enums here (request.md:123).

**`vidbyte/lib/enums/__init__.py`** (EDIT; SHARED)
- **Today:** imports the codex enums at 41-51, without `CodexFailureClass`. `__all__` runs from 142 to 235.
- **Change:** append to both.

**`vidbyte/lib/enums/failure.py`** (EDIT; SHARED insertion point)
- **Today:** the `FailureCode` CODEX block runs from line 35 (`CODEX_SDK_UNAVAILABLE = "codex.sdk_unavailable"`) to line 46 (`CODEX_RUN_OPTION_UNSUPPORTED = "codex.run_option_unsupported"`). The next member is `INPUT_EMPTY` at 47. Values follow `<category>.<snake_problem>`.
- **Change:** add new members after line 46 (request.md:162).
- **Tests that bind it:** every value needs a dot (tests/test_session_failures.py:137-139), and every `codex.*` value needs a classification row (tests/test_codex_failure_recovery.py:192-202).

**`vidbyte/lib/constants/codex.py`** (EDIT)
- **Today:**
  - `CODEX_FAILURE_CLASSIFICATION: Mapping[str, tuple[str, str, str, str]]` (95-174) maps each FailureCode value to (CodexFailureClass, FailurePhase, FailureSeverity, FailureDisposition).
  - `CODEX_TOOL_CALL_TIMEOUT_SECONDS = 300.0` (193).
  - `CODEX_MAX_CONCURRENT_TURNS = 1` (226).
  - `__all__` (229-267).
- **Change:**
  - Add one row per new `codex.*` code.
  - Give every new numeric default a named constant. A007 (baseline 255) flags literals in timeout, retry, token, limit and budget contexts, including parameter defaults.

**`vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`** (COND: only if a new error class is added)
- **Today:** `CodexAgentError(AgentExecutionError)` (base.py:129-149) takes `__init__(message, *, failure_code: str, operation: str, error_type: str = "")` and has a literal `DIAGNOSTIC_FIELDS`. It is exported at errors/`__init__.py`:26,73. `vidbyte/lib/errors/` contains only these two files.
- **Constraint:** A003 (baseline 36) requires the literal eight-field `DIAGNOSTIC_FIELDS` on every new `*Error` in `vidbyte/lib/errors/`.

**`vidbyte/tools/builtins/__init__.py`** (EDIT; SHARED)
- **Today:** the sessions import block is at 167-176, and `__all__` at 182-325.
- **Change:** append.
- **Precedent:** an export assertion exists in `tests/features/coding_agent/test_coding_agent_contract.py:109`.

**`vidbyte/tools/toolsets/__init__.py`** (EDIT; SHARED; 23 lines)
- **Today:** imports `CodingAgentTools` and `ParadigmMinimalToolset` (17-18), with `__all__` at 20-23. Its "Context Protocol Header" fails A001 (debt).
- **Change:** append.

**`vidbyte/__init__.py`** (COND, decided by request.md:214; SHARED; 1,297 lines)
- **Today:**
  - Codex names come from `vidbyte.agents` (67-99), harnesses names at 380-399, `CodexAgentError` at 438-440, tools at 552-572, session tools at 596-605, toolsets at 611.
  - `__all__` is one grouped list literal (690-1297); the codex entries are at 997-1030.
- **Constraints:**
  - S015 requires every public import to appear in `__all__`.
  - Every root export changes the C016 contract.

**`contracts/sdk-public-api.json`** (COND, with root exports; SHARED)
- **Today:** version 0.2.1, 606 exports, `source.commit` f7a02bae…, codex names at 78-111.
- **Pattern:** never edit by hand. Use `scripts/generate-sdk-public-api.py`, which:
  - refuses to run while its inputs are dirty (`git status --porcelain`);
  - stamps HEAD as `source.commit`, but keeps the old commit when the data is unchanged;
  - writes LF (`contracts/.gitattributes`: `*.json text eol=lf`).
- C016 (baseline 0) fails on any difference from the generator output.

**`REPO_MAP.md`** (EDIT; SHARED)
- **Today:**
  - The `vidbyte/harnesses/` entry (147-149) describes only the trajectory envelope.
  - The `vidbyte/tools/toolsets/` entry (335-337) says "It currently holds one such bundle", but there are two.
  - There is no `vidbyte/agents/codex/` entry and no `vidbyte/tools/builtins/sessions/` entry.

**`vidbyte/harnesses/README.md`** (EDIT; SHARED; 180 lines, 8,805 characters)
- **Today:** has "Relationship to adjacent layers" (158-165) and "Key modules" (167-177). There is no File Index and no Notes for agents.

**`vidbyte/tools/README.md`** (COND; not on the shared list; 139 lines, 6,343 characters)
- **Today:** sections Key Modules (80), Cooperative Pause (93-101), Priced Operation Tools (103-132) and Related Layers (134). There is no File Index and no Notes for agents.

**`vidbyte/agents/base.py`** (COND: only if tool binding goes through the built-in lists; not on the shared list)
- **Today:** `_bind_agent_tool_context` (421-447), `_own_tool` (449-468), `_unbound_copy` (470-482), `_bind_session_tool` (484-490).

### 2.4 Read-only neighbours in this repo

**`vidbyte/agents/codex/config.py`**
- `CodexContentTranslator` (121-282) has these methods: `client_kwargs` (125), `thread_start_kwargs` (144), `thread_resume_kwargs` (164), `thread_fork_kwargs` (177), `turn_kwargs` (185), `run_input` (209) and `_thread_common` (228).
- `_thread_common` always sets `config["agents"]` from `CodexSubagentSettings` (236), and sets `developer_instructions` from the `system_prompt` argument (243).
- `_without_empty` (277) drops `None` and `""`.
- Input is `CodexAgentSettings` + `CodexSdkTypes`. Output is snake_case kwargs for the high-level `AsyncCodex` API, not raw JSON-RPC params.
- `CodexConfigurationTranslator` is an alias (285).

**`vidbyte/agents/codex/metrics.py`**
- `CodexMetricsTranslator.record_usage(CodexUsageTranslationRequest(result, settings, tracker))` (37-50) files `last_usage` once per completed turn through `tracker.record_call`.
- It returns `None` when `thread.model_provider` is set or no usage was reported (52-62).
- It imports `vidbyte.agents.pricing.records` (24).

**`vidbyte/agents/codex/result.py`**
- `CodexResultSerializer.from_sdk(thread_id, result)`.
- Imports `vidbyte.agents.types`, `vidbyte.providers.output_schema` and `vidbyte.lib.errors` (19-41).

**`vidbyte/agents/codex/transport.py`**
- The only importer of openai-codex (`_load_sdk`, 215-259).
- `run` starts one app-server per turn.
- `fork_thread` is at 121-159.

**`vidbyte/agents/codex/tools.py`**
- `CodexToolBridge` (79-119) patches `client._approval_handler` and `client.request`, reached through `request.client._client._sync` (private openai-codex attributes).
- `CodexToolCallHandler.handle` (132-172) waits at most `CODEX_TOOL_CALL_TIMEOUT_SECONDS`.
- `CodexToolTranslator` is bound to `CodexHarnessAgentSettings`.

**`vidbyte/agents/codex/failures.py`**
- `CodexFailureTranslator` maps a `CodexAgentError` to a `Failure` through `CODEX_FAILURE_CLASSIFICATION` (35-70).

**`vidbyte/agents/codex/README.md`**
- Size: 1,121 lines and 51,754 characters, against a legacy ceiling of 65,000 (a009:21).
- Has a File Index, so S020 parity applies to `vidbyte/agents/codex/`.
- Notable lines:
  - pin at 18;
  - `codex.sdk_unavailable` at 21;
  - process-level options at 148;
  - dynamic tools need `experimental_api`, are cancelled after 300 s, and are fixed at thread start (421-425);
  - fork before the first run → `fork_failed` (749);
  - the failure table (886-897);
  - "imported only inside the transport" (1093);
  - audited "against >=0.147" (1121).

**`vidbyte/tools/catalog.py`**
- `Tools(Sequence[BaseTool])` (27-60).

**`vidbyte/lib/tools/formatter.py`**
- `ToolsFormatter.to_codex_tool(spec)` (121-128).

**`vidbyte/mcp_server/`**
- `server/core.py:75-118`: `McpStudioServer(*, name, version="0.2.1", agents, tools: Sequence[BaseTool] = (), strategy_names, pipeline_names, prompt_content)`.
- `handlers.py:36`: `StudioToolRegistry`. Line 88 calls `await tool.execute(ToolCall(name, arguments))` with no `PermissionPolicy`.
- `__main__.py:23`: `McpStudioServer()` with no tools. The entry point is `vidbyte-mcp-server` (pyproject.toml:66).

**`vidbyte/tools/mcp/transport.py`**
- On win32, resolves a bare program through `shutil.which` before spawning (197-201; commit d3389d80, #986).

**`pyproject.toml`**
- Must not change (request.md:164).

**`lint/baseline.json`**
- Never raise a number (request.md:204).

### 2.5 Neighbour (third-party, read-only): openai-codex 0.162.1

**Install locations**
- In this venv the dist-info is 0.162.1, and it requires `openai-codex-cli-bin==0.162.1`.
- The global Python 3.11 also has `openai_codex-0.162.1.dist-info` and `openai_codex_cli_bin-0.162.1.dist-info` (`C:/Users/422mi/AppData/Local/Programs/Python/Python311/Lib/site-packages/`).

**`openai_codex/__init__.py`, `types.py`**
- Exported: `AsyncCodex`, `AsyncThread`, `AsyncTurnHandle`, `TurnResult`, `CodexConfig`, `ApprovalMode`, `Sandbox` and the input types.
- Exported errors: `CodexError`, `TransportClosedError`, `JsonRpcError`, `CodexRpcError`, `InvalidRequestError`, `InvalidParamsError`, `MethodNotFoundError`, `ServerBusyError`, `RetryLimitExceededError`, `is_retryable_error`.
- `AsyncCodexClient` is not exported, although `openai_codex.async_client` is importable.
- `types.py` re-exports the generated models.

**`openai_codex/api.py`**
- `AsyncCodex` (308):
  - `self._client = AsyncCodexClient(config=config)` (317) is private.
  - `asyncio.Lock()` (320).
  - `metadata` (347) returns `InitializeResponse`.
  - `account` (382).
  - `thread_start` (393-432) defaults `approval_mode` to auto_review and takes no name and no dynamic tools.
  - `thread_list` (434).
  - `thread_fork` (507-548) has no `last_turn_id`.
  - `models` (563).
- `AsyncThread` (680): `turn()` returns a handle via the private `self._codex._client._start_turn(...)` (768).
- `AsyncTurnHandle` (847):
  - `steer` sends `turn/steer` with `expected_turn_id`;
  - `interrupt`;
  - `stream` runs `asyncio.to_thread(subscription.next)` and closes the subscription in `finally`;
  - `run`.

**`openai_codex/async_client.py`**
- `AsyncCodexClient` wraps the sync `CodexClient` through `asyncio.to_thread`.
- Public `request(method, params, *, response_model)` (132-145): there is no timeout keyword, and `response_model` is required.

**`openai_codex/client.py`**
- `CodexConfig` (195-211): `codex_bin: str | None = None`, `experimental_api=True`.
- `resolve_codex_bin` (176-186):
  - if `codex_bin` is set, it must be an existing path, or a `FileNotFoundError` is raised;
  - if it is unset, the bundled binary is used.
- `start()` (242-281):
  - args are `[bin, --config kv…, "app-server", "--listen", "stdio://"]`;
  - `launch_args_override` is used verbatim;
  - the process is started with `subprocess.Popen`.
- `close()` (283-298): terminate, wait 2 s, then kill.
- `initialize()` (304-325) records the runtime version.
- `request()` (327-366): requests that carry `toolOutput`, `turnTrigger`, `serviceTierForTurn` or `excludeTurns` require runtime ≥ 0.151.0 (346-357). Nothing else checks the version.
- `thread_goal_set(thread_id, *, objective, status)` has no token budget (549-566).
- A goal operation requires an idle, persisted thread and starts a turn (599-648).
- `_start_turn` registers `pending_turn` and refuses during a goal operation (650-682; 667-671).
- `model_list` reads one page only (724-729).
- `_default_approval_handler` auto-accepts command and file-change approvals (833-839).
- The reader loop calls `fail_all` on any error (863-881).
- EOF on stdout raises `TransportClosedError` (903-911).

**`openai_codex/_run.py`**
- `TurnResult(id, status, error, started_at, completed_at, duration_ms, final_response, items, usage)` (22-33).
- A failed turn raises a plain `RuntimeError(turn.error.message)` (60-65).

**`openai_codex/_message_router.py`**
- `_prune_turn_events` drops the events of a turn that has no subscriber, unless a `pending_turn` is open (196-206).
- `fail_all` wakes every waiter.
- Calling `next()` after completion raises `TransportClosedError("Turn is no longer streaming")`.

**`openai_codex/_approval_mode.py`**
- `deny_all` maps to (`never`, `None`).
- `auto_review` maps to (`on-request`, `ApprovalsReviewer.auto_review`) (20-37).

**`openai_codex/_sandbox.py`**
- `Sandbox{read-only, workspace-write, full-access}` maps to `SandboxMode` at thread level and `SandboxPolicy` at turn level.

**`openai_codex/_goal.py`**
- Private goal-stream classes only.

**`openai_codex/_runtime_requirements.py`**
- `MINIMUM_RUNTIME_VERSION = "0.151.0"` (13).
- `require_runtime_version` raises `ValueError` (16-28).

**`openai_codex/_initialize_metadata.py`**
- `validate_initialize_metadata` raises `RuntimeError` when metadata is missing.

**`openai_codex/errors.py`**
- `map_jsonrpc_error` maps JSON-RPC codes to errors:
  - -32700 → `ParseError`
  - -32600 → `InvalidRequest`
  - -32601 → `MethodNotFound`
  - -32602 → `InvalidParams`
  - -32603 → `InternalRpc`
  - -32099..-32000 → `ServerBusy`, `RetryLimit` or `CodexRpcError`

**`openai_codex/models.py`**
- `InitializeResponse(serverInfo(name, version) | None, userAgent, platformFamily, platformOs)` (72-76).

**`openai_codex/generated/notification_registry.py`**
- `DIRECT_TURN_ID_NOTIFICATION_TYPES` (265-294) includes `ThreadTokenUsageUpdatedNotification` and `ThreadGoalUpdatedNotification`.
- `NESTED_TURN_NOTIFICATION_TYPES` is TurnCompleted and TurnStarted (296-299).
- `account/rateLimits/updated` (181) carries no turn id.

**`openai_codex/generated/v2_all.py`**, read with `grep -n` and targeted ranges only:

| ★ wire method | Request line | Params and response models (line) | High-level wrapper |
|---|---|---|---|
| `initialize` | 6905 | InitializeParams (2112-2162) | `AsyncCodex.metadata` |
| `account/read` | 7741 | GetAccountParams(refresh_token) (1859) → GetAccountResponse(account, requires_openai_auth) (8355); `Account` union of ApiKey, Chatgpt(email, plan_type), AmazonBedrock (6721) | `account` |
| `windowsSandbox/readiness` | 7582 | no params → WindowsSandboxReadiness{ready, notConfigured, updateRequired} (6648) | raw only |
| `account/rateLimits/read` | 7613 | GetAccountRateLimitsParams or None (1872) → GetAccountRateLimitsResponse (10965-11006); RateLimitSnapshot (9038); RateLimitWindow(resets_at, used_percent, window_duration_mins) (3659) | raw only |
| `model/list` | 7447 | ModelListParams(cursor, include_hidden, limit) (2783) → ModelListResponse(data, next_cursor) (8852); Model (8795) | `models(include_hidden)`, first page only |
| `thread/start` | 10625 | ThreadStartParams (10367-10404): approval_policy, approvals_reviewer, base_instructions, config, cwd, developer_instructions, ephemeral, model, model_provider, personality, sandbox, service_name, service_tier, session_start_source, thread_source | `thread_start` |
| `thread/resume` | 6914 | ThreadResumeParams (5982; `exclude_turns: bool`) | `thread_resume` |
| `thread/fork` | 10634 | ThreadForkParams (9859-9904): `last_turn_id` ("fork through, inclusive"; that turn cannot be in progress), `exclude_turns: bool` | `thread_fork`, which exposes neither |
| `thread/list` | 10661 | ThreadListParams (10121): archived, cursor, cwd, limit, model_providers, originators, search_term, section_id, sort_direction, sort_key, source_kinds, use_state_db_only → ThreadListResponse (12328) | `thread_list` |
| `thread/read` | 7138 | ThreadReadParams(include_turns, thread_id) (5733) → ThreadReadResponse(thread) (12356); Thread (12130-12286) | `AsyncThread.read` |
| `turn/start` | 12639 | TurnStartParams (12533-12630): approval_policy, approvals_reviewer, disabled_plugin_ids, effort, input, model, output_schema, sandbox_policy, service_tier, summary, thread_id, … | `AsyncThread.turn` |
| `turn/steer` | 10691 | TurnSteerParams(expected_turn_id, input, thread_id, client_user_message_id) (10517) → TurnSteerResponse(turn_id) (6427) | `AsyncTurnHandle.steer` |
| `turn/interrupt` | 7438 | TurnInterruptParams (6384) | `AsyncTurnHandle.interrupt` |
| `review/start` | 10700 | ReviewStartParams(delivery, target, thread_id) (9114) → ReviewStartResponse(review_thread_id, turn) (12056); ReviewTarget (4157-4210); ReviewDelivery{inline, detached} (4152) | raw only |
| `thread/goal/set` | 10643 | ThreadGoalSetParams(objective, origin, status, thread_id, token_budget) (9938); ThreadGoal (9906); ThreadGoalStatus{active, paused, blocked, usageLimited, budgetLimited, complete} (5334) | client `thread_goal_set`, without token budget |
| `thread/tokenUsage/updated` (notification) | 11312 | ThreadTokenUsageUpdatedNotification(thread_id, token_usage, turn_id) (10423); ThreadTokenUsage(last, total, model_context_window) (10414); TokenUsageBreakdown (6328) | read by `_run.py` |
| `turn/completed` (notification) | 12096 | TurnCompletedNotification(thread_id, turn) (11702); Turn (11655); TurnStatus{completed, interrupted, failed, inProgress} (6420); TurnError(message, codex_error_info, additional_details, misalignment) (10484) | the handle's stream |

Other models:
- `ApprovalsReviewer{user, auto_review, guardian_subagent}` (260).
- `AskForApprovalValue{untrusted, on-request, never}` plus granular variants (351-381).
- `AuthMode` (392).
- `CodexErrorInfoValue` (525): contextWindowExceeded, sessionBudgetExceeded, usageLimitExceeded, rateLimitExceeded, flexUnavailable, serverOverloaded, cyberPolicy, misalignmentPolicyViolation, tooManyDenials, internalServerError, unauthorized, badRequest, threadRollbackFailed, sandboxError, other.
- `CodexErrorInfo` union (7771).
- `ThreadSortKey{created_at, updated_at, recency_at, section_position}` (6188).
- `ThreadSourceKind` (6210).
- `ThreadForkResponse` (12288).
- `ThreadStartResponse` (12458).

### 2.6 Lint rules most likely to bite

Baselines come from `lint/baseline.json`.

| Rule | Scope | Trips on | Baseline |
|---|---|---|---|
| A001 | every tracked `.py`, including tests and `__init__` files; no empty-file exemption (a001:44-49) | a header missing any of PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS, TESTS (a001:23-32) | 643 (approximate current count also 643, unverified) |
| A002 | functions in `vidbyte/` | identifier tokens (split on `_` and `.`) such as request, send, fetch, transport, subprocess, permission, retry or attempt, without `# @intent <name>` within 20 lines | 703 |
| A003 | `*Error` classes in `vidbyte/lib/errors/` | the literal eight-field `DIAGNOSTIC_FIELDS` is missing | 36 |
| A005 | parameters named transport, runner, store, client, tracer or fetcher | typed `object` or `Any` | 33 |
| A006 | lower layers (lib, providers, sessions, sources) importing orchestration packages; cycles | runtime imports, including function-local ones; `TYPE_CHECKING` imports and `__init__` files are skipped | 34 |
| A007 | numeric literals in operational contexts (timeout, retry, token, char, byte, limit, budget, interval, …), including parameter defaults | an unnamed literal | 255 |
| C002, C006, C007, C008 | `vidbyte/lib/dataclasses/` validation | a repeated bool guard; range checks that do not reject bool, NaN or inf; a bool switch without a check; a new primitive validator outside `validation.py` | 9 / 104 / 16 / 45 |
| C015 | non-`.py` files under `vidbyte/` | a shipped README, or an asset that is not shipped | 3 |
| C016 | `contracts/sdk-public-api.json` | differs from the generator output | 0 |
| S006 | `vidbyte/` | the `asyncio.create_task` result is not stored (RUF006) | 0 |
| S007 / S008 / S009 | `vidbyte/` | missing annotations (ANN) / complexity (C901, PLR0912, PLR0915) / mypy errors | 16 / 19 / 350 |
| S012 | `vidbyte/` | a call to `request`, `request_bytes`, `stream_request`, `upload_multipart` or `urlopen` without a `timeout=` or `timeout_seconds=` keyword (s012:22-39) | 0 |
| S015 | `__init__` files | an unbound `__all__` entry; a root public import missing from `__all__` | 13 |
| S016 | providers, `tools/mcp`, `tools/builtins`, `lib/runners`, cli | raising `Exception`, `RuntimeError`, `TypeError` or `ValueError` | 50 |
| S017 | providers, `tools/`, `mcp_server/`, `lib/runners` | `str(exc)`, `repr(exc)` or `f"{exc}"` of a caught exception passed to `.error()` or `*Error()`, or returned | 79 |
| S019 / S024 / S063 | `vidbyte/` | swallowed cancellation / nesting depth > 3 / unclassified `gather(return_exceptions=True)` | 5 / 25 / 4 |
| S020 | READMEs that contain a File Index section | the index differs from the folder's direct children | 1 |
| S025 | `BaseTool` subclasses | a `ToolSpec` or `ToolParameter` description shorter than 4 sentences | 263 |
| S039 | `vidbyte/` | banned APIs `typing.TypedDict`, `typing.assert_never`, `asyncio.Lock` (lint/ruff.toml) | 5 |
| S045 | `vidbyte/` | an `async def` with a `timeout` parameter (ruff ASYNC109) | 2 |
| S051 | the whole `vidbyte/` tree | isort and modern typing (I001, UP006, UP007, UP035, UP045) | 259 |
| S060 | sessions, `lib/dataclasses`, `tools/types.py`, `mcp_server/schema.py` | `dict[str, Any]` in a public signature | 32 |
| S062 | every tracked `.py` | adjacent string literals | 889 |

## 3. Tests

### Where tests live and how they are written

**Runner and configuration**
- The runner is pytest 8.3.5, with pytest-asyncio 1.3.0 from the dev extra.
- Configuration (pyproject.toml:78-81): `testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]`, `asyncio_default_fixture_loop_scope = "function"`.

**Layout**
- 138 files directly under `tests/`: flat `test_*.py` modules plus `agent_test_support.py`, packaged by `tests/__init__.py` (651 bytes, no A001 fields).
- `tests/multi_agent/` (4 files, with an `__init__.py`).
- `tests/features/<feature>/` packs (51 files). These have no `__init__.py`, a `README.md` with a File Index (S020 parity applies), a `FEATURE.md`, an optional `conftest.py`, and test modules.
- The only tracked test `__init__.py` files are `tests/__init__.py` and `tests/multi_agent/__init__.py`. No tracked `.py` file is zero bytes.
- No two test modules share a basename; only `__init__.py` repeats.

**Codex test style**
- Codex tests are flat modules (`tests/test_codex_{agent_input_bridge,failure_recovery,middleware,output_contracts,pipelines,tools,usage_tracking}.py`).
- They use `unittest.TestCase` and `unittest.IsolatedAsyncioTestCase`. Across `tests/`, 90 files use `IsolatedAsyncioTestCase`, 11 use `pytest.mark.asyncio`, and 18 use `asyncio.run(`.
- Every codex test module has a full A001 header, for example `tests/test_codex_tools.py:1-48`.

### Fakes and fixtures

**`tests/test_codex_tools.py`**
- 196-198: `_call` answers server requests from a worker thread through `asyncio.to_thread(handler.handle, …)`.
- 202-213: `_FakeSyncClient` has `request(method, params, *, response_model=None)`, records each request, and provides `_approval_handler`.
- 216-230: `_FakeThread.run` replays `_FakeAsyncCodex.script` through the installed handler.
- 233-261: `_FakeAsyncCodex` has class-level `script`, `answers` and `instances`; an async context manager; `thread_start` and `thread_resume` sent through `_client._sync.request`.
- 264-282: `_fake_sdk()` builds `CodexSdkTypes` with passthrough constructors.
- 298-312: `_run_transport()` patches `CodexTransport._load_sdk` and `CodexResultSerializer.from_sdk`.
- 315-319: `_reset_fake()`.
- 640-680: SDK contract tests under `@unittest.skipUnless(importlib.util.find_spec("openai_codex"), "requires the optional openai-codex extra")`. They inspect the private hooks and the `MessageRouter` release behaviour.

**`tests/test_codex_failure_recovery.py`**
- 184-185: `_ScriptedTransport` is installed as `agent._transport`.
- 192-202: the classification-coverage tests.

**`tests/agent_test_support.py`** (73 lines; imported by 61 test files)
- `OfflineTestAgent` (48), `bind_test_runner` (62), `build_test_agent` (68).

**`tests/features/coding_agent/conftest.py`**
- Feature-pack fixtures that load lazily. The README says it fakes `HttpTransport._send_once`.

There is no root `tests/conftest.py`.

### Tests that bind this change indirectly

- `tests/test_codex_failure_recovery.py:192-202`: every `codex.*` FailureCode needs a `CODEX_FAILURE_CLASSIFICATION` row, and every row must name a real code.
- `tests/test_session_failures.py:137-139`: every FailureCode value contains a dot.
- `tests/test_codex_tools.py:640-680`: these contract tests run wherever `openai_codex` is importable.
  - The global Python 3.11 has 0.162.1, so they run in a local gate.
  - `ci.yml` installs only `.[dev]`, so they are skipped there.

### Commands

| Purpose | Command |
|---|---|
| One file | `PYTHONPATH=$(pwd) python -m pytest -q tests/test_codex_tools.py` |
| Codex area | `PYTHONPATH=$(pwd) python -m pytest -q tests -k codex` |
| A feature pack, if one is created | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>` |
| The full test stage as the gate runs it | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` |

None of these were run in this stage.

## 4. Notes for the spec author

Contradictions use the form "request assumes X; code shows Y at `path:line`". This section lists contradictions and facts; it does not propose designs.

### Contradictions

**C1. A001 and the shared-file bytes.**
- **Request assumes:** the four-line `vidbyte/harnesses/native/__init__.py` docstring (request.md:147-153) and the zero-byte test `__init__.py` files (request.md:161) pass the gate.
- **Code shows:**
  - A001 requires seven fields in every tracked `.py` file, with no empty-file exemption (lint/rules/a001_agent_readable_file_headers.py:23-32, 44-49, 69-73).
  - The A001 baseline is 643 (lint/baseline.json:2), and a read-only `git grep -L` approximation found exactly 643 tracked `.py` files missing at least one field (unverified).
  - So each new header-less `.py` file is a REGRESSED A001.
- request.md:154 provides an escape hatch for `native/__init__.py` only. There is none for test `__init__.py` files.
- `tests/features/*` packs carry no `__init__.py` at all.

**C2. Copying the sessions layout.**
- **Request assumes:** copy `vidbyte/tools/builtins/sessions/` (request.md:113).
- **Code shows** that those modules carry gate debt:
  - Their "Context Protocol Header" docstrings fail A001 (`sessions/_base.py:1-13`, `sessions/fork.py:1-14`, `sessions/__init__.py:1-15`).
  - `sessions/descriptions.py` uses adjacent string literals (S062).
  - `_base.py:85-90` interpolates `exc` into `ToolResult.error` (S017, whose scope covers `vidbyte/tools/`).
- Copying them verbatim regresses A001, S062 and S017.

**C3. The generic `request()` and S012.**
- **Request assumes:** the methods without wrappers use the generic `request()` (request.md:202, 208).
- **Code shows:**
  - S012 (baseline 0, lint/baseline.json:41) flags every call in `vidbyte/**` to a method named `request` that lacks a `timeout=` or `timeout_seconds=` keyword (lint/rules/s012_explicit_outbound_timeout.py:22-39, 60-68).
  - openai-codex's `request(method, params, *, response_model)` takes no timeout keyword and requires `response_model` (async_client.py:132-145; client.py:327-333).
  - The existing codex agent never calls `.request(`; it only patches it.

**C4. The public path to raw requests.**
- **Request assumes:** a public path from the high-level client (request.md:208).
- **Code shows:**
  - `AsyncCodex` holds `self._client` as a private attribute (api.py:317).
  - `AsyncCodexClient` is public only as `openai_codex.async_client.AsyncCodexClient`; it is not in `openai_codex/__init__.py`.
- ★ operations with no high-level wrapper:
  - `account/rateLimits/read`, `windowsSandbox/readiness` and `review/start`;
  - `thread/goal/set` with `tokenBudget`;
  - `thread/fork` with `lastTurnId`;
  - turn-level `approvalsReviewer` set to user or guardian_subagent;
  - `disabledPluginIds`.

**C5. Fork parameters.**
- **Request assumes:** `fork_codex_thread(thread_id, from_turn_id, exclude_turns, overrides)` (request.md:91), and R2 says "`thread/fork` accepts `last_turn_id` and `exclude_turns`" (request.md:307).
- **Code shows:**
  - `ThreadForkParams.last_turn_id` forks "through, inclusive", and the referenced turn cannot be in progress.
  - `exclude_turns` is a bool that hydrates the response, not a list of turns (v2_all.py:9859-9904).
  - `AsyncCodex.thread_fork` exposes neither field (api.py:507-548).
  - `excludeTurns` needs runtime ≥ 0.151.0 (client.py:346-357).
- Neither of the "overrides" records the request names covers this:
  - `CodexForkSettings` is an agent-fork record with `context_manager`, `capabilities` and `system_prompt`, and no turn id (lib/dataclasses/codex.py:625-640).
  - `thread_fork_kwargs` emits no turn fields (vidbyte/agents/codex/config.py:177-183).

**C6. The `codex_bin` default.**
- **Request assumes:** `codex_bin` defaults to the user's installed `codex` (request.md:109, 133, 141).
- **Code shows:**
  - `CodexClientSettings.codex_bin: str = ""` (lib/dataclasses/codex.py:105). The empty value is dropped (config.py:125-141, 277-282), so openai-codex uses its bundled binary (client.py:176-186).
  - A set value must be an existing path, or `FileNotFoundError` is raised (client.py:178-183). So the bare name `codex` fails.
- **On this machine:**
  - PATH `codex` is an npm launcher: `C:/Users/422mi/AppData/Roaming/npm/codex`, `codex.cmd`, `codex.ps1`, which run `bin/codex.js`.
  - The repo's precedent for Windows launchers resolves with `shutil.which` on win32 (vidbyte/tools/mcp/transport.py:197-201). The reason given in commit d3389d80 is that CreateProcess does not search PATHEXT.

**C7. The installed version.**
- **Request assumes:** "`codex-cli` 0.161.0 is installed on PATH" (request.md:165).
- **Code shows:**
  - `C:/Users/422mi/AppData/Roaming/npm/node_modules/@openai/codex/package.json:3` reads `"version": "0.162.1"` (file dated 2026-10-12 17:36). The binary was not executed.
  - The bundled `openai-codex-cli-bin` is also 0.162.1.
  - openai-codex's own floor is 0.151.0 (_runtime_requirements.py:13). It is enforced only when gated request fields are sent (client.py:346-357), not at `initialize` (client.py:304-325).

**C8. Approval fields.**
- **Request assumes:** `approval_policy` and `approvals_reviewer` (user / auto_review / guardian_subagent) are fields of the spawn request (request.md:104), which reuses the existing settings (request.md:123).
- **Code shows:**
  - The existing settings carry only `approval_mode: CodexApprovalMode` (lib/dataclasses/codex.py:189 for the thread, :250 for the turn).
  - `CodexApprovalMode` is `{"", auto_review, deny_all}` (lib/enums/codex.py:17-22). It maps through openai-codex `ApprovalMode` to only (on-request, auto_review) or (never, None) (_approval_mode.py:20-37), via `turn_kwargs` and `_thread_common` (config.py:194, 239).
  - On the wire, `approvals_reviewer` and `approval_policy` are separate params (v2_all.py:260, 351-381; ThreadStartParams and TurnStartParams).

**C9. `developer_instructions`.**
- **Request assumes:** `developer_instructions` is a reusable field (request.md:103).
- **Code shows:** no settings class has it; the translator takes it as its `system_prompt` argument (config.py:243).

**C10. Process-level fields.**
- **Request assumes:** `codex_bin`, `env` and `experimental_api` are per-spawn fields (request.md:109).
- **Code shows:**
  - They are fixed once per app-server process (`CodexConfig`, client.py:195-211; `CodexClientSettings`, lib/dataclasses/codex.py:105-113; codex README:148).
  - request.md:117 also says one `CodexHost` owns one app-server.

**C11. The goal budget.**
- **Request assumes:** `goal` is set through `thread/goal/set` with a `token_budget` (request.md:106, 129).
- **Code shows:**
  - `token_budget` exists only in the raw `ThreadGoalSetParams` (v2_all.py:9938).
  - `CodexClient.thread_goal_set(thread_id, *, objective, status)` has no budget parameter (client.py:549-566).
  - Activating a goal requires a persisted (non-ephemeral), idle thread, and the runtime then starts its own turn (client.py:599-648).
  - `_start_turn` refuses while a goal operation is registered (client.py:667-671).

**C12. Handle lifetime.**
- **Request assumes:** spawn returns a handle at once and `wait_codex_turn` collects the result later (request.md:121).
- **Code shows:**
  - The router drops events of a turn that has no subscriber unless a `pending_turn` is open (_message_router.py:196-206).
  - Only `_start_turn` opens one (client.py:650-682). A `review/start` subscription created after the response can therefore miss `turn/completed` and block until the transport fails.
  - `AsyncTurnHandle.stream` closes its subscription in `finally` (api.py:847-901), so each handle's events can be consumed once.
  - Every waiting stream holds a worker thread (`asyncio.to_thread`).

**C13. Typing failures.**
- **Request assumes:** every failure maps to a `codex.<problem>` code with a next step (request.md:124-127).
- **Code shows** these failure sources:
  - A failed turn raises a plain `RuntimeError(turn.error.message)` (_run.py:60-65).
  - Process death raises `TransportClosedError("Codex process closed stdout. stderr_tail=…")` (client.py:903-911), pushed to every waiter (client.py:863-881).
  - The binary path raises `FileNotFoundError` (client.py:178-183), the version check raises `ValueError` (_runtime_requirements.py:25-28), and the metadata check raises `RuntimeError` (_initialize_metadata.py).
  - JSON-RPC codes map to typed errors in `errors.py`.
  - `TurnError.codex_error_info` (v2_all.py:10484) carries `CodexErrorInfoValue` (v2_all.py:525).

**C14. The error vocabulary.**
- **Request assumes:** one shared vocabulary (request.md:125-126).
- **Code shows:**
  - R2 and R3 name the same problems differently (request.md:287-303 vs 807-830): `thread_busy`/`session_busy`, `host_exited`/`process_exited`, `thread_not_found`/`session_not_found`, `binary_unsupported`/`version_unsupported`/`not_installed`, and `token_cap_reached`/`budget_exhausted`.
  - Twelve `codex.*` codes already exist (failure.py:35-46). Two overlap: `codex.sdk_unavailable` and `codex.fork_failed`.
  - Every new code needs a classification row (§3).

**C15. The error class.**
- **Request assumes:** R2 sketches `CodexOperationError(code, operation, message, next_step)` (request.md:287-303).
- **Code shows:**
  - `CodexAgentError(message, *, failure_code, operation, error_type)` has `repair_approaches` but no `next_step` (lib/errors/base.py:129-149).
  - Any new `*Error` in `vidbyte/lib/errors/` needs the A003 packet.

**C16. Module-level functions.**
- **Request assumes:** module-level functions wrap the one-shot methods (request.md:118).
- **The field guide records** that review rejected free-function walls: "Prefer a static helper class over a bag of module-level free functions", and the module's `__all__` should export the class (`class-bound-helpers.md`). This is not a lint rule.

**C17. `track_codex_thread_usage`.**
- **Request assumes:** it wraps `thread/tokenUsage/updated` + `CodexMetricsTranslator` (request.md:97).
- **Code shows:**
  - The translator files one completed turn's `last_usage` into a tracker. It needs a `CodexRunResult`, a `CodexAgentSettings` and a `record_call` tracker, and returns `None` for a custom `model_provider` (vidbyte/agents/codex/metrics.py:37-62; lib/dataclasses/codex.py:844-867).
  - Token-usage notifications are routed per turn (notification_registry.py:265-294), so only that turn's subscriber sees them.

**C18. Tool binding.**
- **Request assumes:** tools hold one `CodexHost` per agent, "the same way `_SessionBuiltinTool` holds a session store" (request.md:120).
- **Code shows:**
  - The store is a constructor argument (sessions/_base.py:33-42).
  - Per-agent copies come only from the explicit `isinstance` lists in `vidbyte/agents/base.py:421-482`. Any other tool is shared by identity between agents (base.py:467-468).
  - Forks duck-type `clone_for_agent` and `clone_for_fork` (vidbyte/agents/fork.py:181-198).
  - `vidbyte/agents/base.py` is not on the shared append-only list (request.md:163).

**C19. MCP.**
- **Request assumes:** the existing MCP server serves the toolset without new code (request.md:115).
- **Code shows** this is true: `McpStudioServer(tools=...)` accepts any `Sequence[BaseTool]` (mcp_server/server/core.py:75-118), and a `Tools` subclass is one (tools/catalog.py:27). But:
  - `StudioToolRegistry` runs `tool.execute` with no `PermissionPolicy` check and no agent binding (vidbyte/mcp_server/handlers.py:36, 88). So the READ/WRITE opt-in (request.md:128) is not enforced over MCP.
  - The `vidbyte-mcp-server` entry point serves no tools (mcp_server/`__main__.py`:23).

**C20. Approvals during spawned work.**
- **Request assumes:** WRITE tools need an explicit opt-in (request.md:128).
- **Code shows:** inside a spawned thread, openai-codex's `_default_approval_handler` auto-accepts `item/commandExecution/requestApproval` and `item/fileChange/requestApproval` (client.py:833-839), unless a handler is installed. `CodexToolBridge` installs one by patching (vidbyte/agents/codex/tools.py:79-119).

**C21. Higher-layer types in lib.**
- **Request assumes:** R2's sketch types `tools: tuple[BaseTool, ...]` and `output_schema: type[BaseModel] | Mapping` on a record in `vidbyte/lib/dataclasses/codex.py` (request.md:268-284).
- **Code shows:**
  - `vidbyte/lib` cannot import `vidbyte.tools` (AGENTS.md:52; A006).
  - The precedent is `CodexHarnessAgentSettings.tools: tuple[ToolInput, ...]` with a `TYPE_CHECKING` import and the shape check `_is_tool_shaped` (lib/dataclasses/codex.py:81, 342), and `output_schema: type | Mapping[str, Any] | None` (333).

**C22. Spawn `name`.**
- **Request assumes:** `name` is a spawn field (request.md:107).
- **Code shows:** `ThreadStartParams` has no name field (v2_all.py:10367-10404). Names are set through `thread/name/set` (high-level `set_name`).

**C23. A `timeout` parameter.**
- **Request assumes:** the signature `wait_codex_turn(handle, timeout)` (request.md:94).
- **Code shows:**
  - S045 (baseline 2) is ruff ASYNC109, which flags async functions with a `timeout` parameter (lint/rules/s045_async_function_with_timeout.py). Whether it matches only the exact name `timeout` is unverified.
  - The repo's async APIs use `timeout_seconds` (vidbyte/lib/http/transport.py:55; vidbyte/harnesses/execution.py:184).
  - A007 needs a named constant for any default.

**C24. Model paging.**
- **Request assumes:** `list_codex_models(include_hidden)` (request.md:88).
- **Code shows:** `CodexClient.model_list` returns the first page only (client.py:724-729). `ModelListParams` has `cursor` and `limit` (v2_all.py:2783).

**C25. Thread-list sort.**
- **Request assumes:** a single `sort` argument (request.md:92).
- **Code shows:**
  - The wire has `sort_key` (`ThreadSortKey`, v2_all.py:6188) plus `sort_direction` (ThreadListParams, v2_all.py:10121).
  - Both are closed sets, so they must be enums (AGENTS.md:63).

**C26. File size.**
- **Request assumes:** new records go in `vidbyte/lib/dataclasses/codex.py` (request.md:123).
- **Code shows:**
  - That file is already 1,205 lines, against "Keep files well below 1,000 lines" (AGENTS.md:31).
  - No lint rule enforces length; a grep of `lint/rules` and `lint/core` found none.

**C27. Stale repository documentation.**
- **Request and AGENTS.md assume:** the placement workflow runs on every PR (AGENTS.md:15) and the codex README has "Notes for agents".
- **Code shows:**
  - `.github/workflows/agents-md-placement.yml` is manual-dispatch only.
  - None of the codex, harnesses, tools or mcp_server READMEs has Notes for agents.
  - The codex README failure table (886-897) lacks `contract_unmet` and `run_option_unsupported`, which exist at failure.py:43, 46.
  - The README was audited at ">=0.147" (README:1121).
  - REPO_MAP.md:337 is stale.
  - `hosts.py` (request.md:246) does not exist (`git ls-files`). The phrase "native coding-agent harnesses" appears only at `skills/runtime-primitives/references/runtime-primitives.md:5`.

**C28. `CodexFailureClass` export.**
- **AGENTS.md:61 requires:** "every public enum is added to the export list".
- **Code shows:** `CodexFailureClass` (lib/enums/codex.py:82) is root-public (`vidbyte/__init__.py`:75, 1002) but absent from `vidbyte/lib/enums/__init__.py:41-51`. This predates the change.

### Facts the request does not mention

**Import safety**
- `import vidbyte` runs in a clean venv without the `codex` extra (package stage). `ComponentRegistry` imports `vidbyte.tools.builtins` the first time a YAML tool reference is resolved (components.py:94-113).
- So any root or builtins export must load `openai_codex` lazily.

**Unwrapped-method contract tests**
- If the spec reaches private openai-codex attributes, the precedent is a `skipUnless(find_spec("openai_codex"))` contract test (tests/test_codex_tools.py:640-680). request.md:208 asks for this.

**Shared state across tool copies**
- `_SessionBuiltinTool.clone_for_agent` builds a fresh instance with the same store (sessions/_base.py:58-61). Any shared live host would likewise be shared across copies unless the clone replaces it.

**Concurrency settings**
- `CODEX_MAX_CONCURRENT_TURNS = 1` serialises turns inside `CodexHarnessAgent` (lib/constants/codex.py:226; agents/codex/agent.py:84-86).
- `CodexSubagentSettings.max_concurrent_threads` (default 0) configures Codex's native `agents.max_concurrent_threads_per_session` (config.py:253-270). It does not configure Vidbyte-run fan-out (request.md:210).

**Merge-time risk**
- The ClaudeHost PR edits the same append-only files (request.md:163). Because it was not opened (by rule), its exact line positions are unverified.

### Unverified

**Lint and test behaviour**
- The A001 count of 643 is a `git grep -L` approximation (a scratch list outside the repo), not a lint run.
- Whether ruff ASYNC109 (S045) matches only the exact parameter name `timeout`.
- Whether pytest's default import mode breaks when a test basename is duplicated across `tests/features/*` packs that have no `__init__.py`.

**Windows process and binary**
- Whether `subprocess.Popen` launches the npm `codex.cmd` on Windows, and whether `close()`'s `terminate()` reaches the node or codex child behind it.
- What `initialize` reports for the PATH binary. It was not executed.
- request.md:141's claim that the user's install "carries their login and config", where the bundled binary would not. `~/.codex` was not read.

**Gate environment**
- Whether `run_ci`'s own `PYTHONPATH` handling for the smoke run makes the field guide's split command unnecessary.
- The briefing's claim that the global editable install points at the canonical checkout.

**Files not read**
- `vidbyte/sessions/scope.py` (`SessionScope.own_runs`, used at sessions/_base.py:36).
- These test modules were seen only through grep and line counts, not read in full: `tests/test_codex_usage_tracking.py`, `tests/test_codex_pipelines.py`, `tests/test_codex_output_contracts.py`, `tests/test_codex_middleware.py`, `tests/test_codex_agent_input_bridge.py`, `tests/test_durable_sessions.py`.
