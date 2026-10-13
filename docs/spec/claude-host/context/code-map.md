# Code map: ClaudeHost (PR B, `feat/claude-host`)

Written by S0 (scout) on 2026-10-12, for the S1 spec author and the S1 spec reviewer.

- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host`.
- HEAD: `678136bd4358bcf9f120504cecd818d36a3d46fe`, which equals origin/main.
- Scope: the ClaudeHost ★ set in request.md §C (request.md:77-153).
- Nothing was installed, run, imported or modified to produce this file.

How to read the references:

- `path:line` is relative to the worktree root at HEAD `678136bd`. A bare `:n` means a line in the file named in that entry.
- `SDK/x` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/claude-agent-sdk-x/claude_agent_sdk-0.2.165/src/claude_agent_sdk/x`. This is claude-agent-sdk 0.2.165, an extracted third-party download. It is read-only: never import it, execute it or copy it.
- `DTS:n` is line n of `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/claude-agent-sdk-ts/x/package/sdk.d.ts`. This is TypeScript SDK 0.3.296, grepped only and used for cross-reference.
- `FG/x` is `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/x`, the workspace field guide of review-caught conventions.
- "unverified:" marks anything not confirmed by reading.

## 1. Rules, commands, and conventions that bind this change

### 1.1 Where the rules live

- `AGENTS.md` (81 lines) is the only rule file. `CLAUDE.md` is the single line `@AGENTS.md`, and `git ls-files` shows no nested AGENTS.md or CLAUDE.md.
- AGENTS.md points to two other documents:
  - `REPO_MAP.md` (62,470 characters), split into the File Index and JEV File Locations;
  - each folder's `README.md`.
- None of the folder READMEs this change touches has a `Notes for agents` section: `vidbyte/harnesses/`, `vidbyte/tools/`, `vidbyte/agents/codex/`, `vidbyte/lib/` and `vidbyte/mcp_server/`. The only such section in the repo is `vidbyte/agents/coding_context/README.md:35`, so there are no review notes to quote.
- AGENTS.md states no commit or PR conventions. §1.8 lists what the repo uses instead.

### 1.2 AGENTS.md rules, quoted under their headings

**Repository Map (AGENTS.md:7-15)**

- :9 says REPO_MAP "covers every top-level folder and each subpackage of `vidbyte/`". It continues: "Read it before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs." And: "it is expected to drift, so regenerate a wrong entry from the tree instead of patching around it."
- :11: "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder." Also: "lint rule A009 keeps every folder README at or under 40,000 characters".
- :13: "**Do not grep, glob, or read files under `docs/` as part of ordinary work**". Also: "Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- :15: the Placement Rules are "binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request by moving misplaced code". §1.4 shows that this workflow is currently manual-only.

**General Coding Style Guidelines (AGENTS.md:17-41)**

:19 says the guidelines "apply to new code and to code you change. Do not rewrite untouched code just to make it conform".

1. **Keep Call Chains One Level Deep** (:21-23).
   - "a function may call another of its own functions, but that second function should not call a third."
   - "Calls out to another class, a lower layer, or the standard library do not count toward this limit."
   - "Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator."
2. **Narrate Main Functions in Plain English** (:25-27).
   - "place short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments."
   - "When you change the steps of a main function, update its comments in the same edit".
3. **Build in Layers of Small, Single-Purpose Classes** (:29-31).
   - "a lower layer never imports a higher one, and no two modules depend on each other in a cycle."
   - "nothing in `vidbyte/lib/` may import from a layer above it."
   - "Keep files well below 1,000 lines".
   - "If describing the job of a function or a class needs the word "and", it is probably two functions or two classes."
4. **Use Validated Dataclasses for Core Inputs and Outputs** (:33-35).
   - "Functions that carry core business logic take a dataclass as input and return a dataclass as output".
   - "Each dataclass validates itself strictly when it is created, in `__post_init__` … and raises a clear error that names the field and the bad value."
   - "Prefer `@dataclass(frozen=True, slots=True)` … and type any field whose value comes from a small, closed set as an enum."
5. **Write Shared Logic Once, as a Canonical Helper in `lib/`** (:37-41).
   - "look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the option you need to it rather than copying it into a variant beside your feature."
   - "a canonical helper never imports from a layer above it".

**Placement Rules (AGENTS.md:43-81)**

- :47: "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`** … whether it is public or underscore-prefixed."
- :49: "Do not create `types.py`, `records.py`, `models.py`, or `schemas.py` modules next to the code that uses the dataclass."
- :50: "A feature package may re-export it from its own `__init__.py` as part of its public API … but the definition stays in `vidbyte/lib/dataclasses/`."
- :51: "Behavior that acts on the record lives in the layer that owns that behavior."
- :52: "If a dataclass seems to need a type from a higher layer, move the contract down (a `Protocol` or a smaller record in `vidbyte/lib/`)."
- :54-57 give the only two exceptions: agent `*Settings` classes, and JEV preflight questions.
- :61: "**Every new enum … is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
- :63: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."
- :69 applies to JEV only, but it is the constants convention Codex follows: "**a constant** in `vidbyte/lib/constants/jev.py`". The Codex precedent is `vidbyte/lib/constants/codex.py`.
- :81: "Many modules on `main` still define dataclasses or enums outside these two folders … Do not copy them as precedent." One example: `ToolStatus` and `ToolPermission` are enums defined inside `vidbyte/lib/dataclasses/tools.py:40,47`.
- **Enforcement:** no lint rule checks placement; `lint/rules/` was searched, and C001 covers settings validation, not location. The only enforcer is the LLM workflow `.github/workflows/agents-md-placement.yml` (prompt in `.github/prompts/agents-md-placement.md`), which is currently manual-only (§1.4).

### 1.3 Commands

| Purpose | Command | Source |
|---|---|---|
| Install | `python -m pip install -e ".[dev]"` | CONTRIBUTING.md:35; `.github/workflows/ci.yml:36,57` |
| Full gate (AGENTS.md's only command) | `python scripts/run_ci.py` | AGENTS.md:13; CONTRIBUTING.md:56 |
| Full gate from a worktree | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH | FG/local-ci-verification.md (the editable install points at the canonical checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk`) |
| Check which `vidbyte` is imported | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` must print the worktree path | FG/local-ci-verification.md |
| Stages | `--stage all\|source\|package` and `--dist-dir` | `scripts/run_ci.py:260-266`; CONTRIBUTING.md:61-65 |
| Lint, all rules | `python lint/run.py`; the last line reads `SDK-LINT: PASS` or `SDK-LINT: FAIL` | `lint/run.py`; `lint/core/report.py:58` |
| Lint, one rule | `python lint/run.py --rule A001`, plus `--format json`, `--all` | `lint/run.py:36-39`; CONTRIBUTING.md:67-70 |
| Baseline | `--update-baseline` exists, but request.md:232 forbids raising any number in `lint/baseline.json` | `lint/run.py:36-39` |
| Import order across the whole tree (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, then filter to your paths | FG/local-ci-verification.md |
| Tests, one file | `PYTHONPATH=$(pwd) python -m pytest tests/test_codex_tools.py` (substitute the file) | pyproject `[tool.pytest.ini_options]` (pyproject.toml:78-81) |
| Tests, one area | `PYTHONPATH=$(pwd) python -m pytest tests/test_claude_*.py`, or `-k claude` | same |
| Tests, all | `PYTHONPATH=$(pwd) python -m pytest` (testpaths = `tests`) | same |
| Semgrep (separate workflow, not in run_ci) | `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with semgrep==1.170.1 | `.github/workflows/static-policy.yml:24,30`; FG/local-ci-verification.md |
| Public-API contract | `python scripts/generate-sdk-public-api.py`, run after committing the `vidbyte/__init__.py` change; `--check` verifies only | `scripts/generate-sdk-public-api.py:13-15` |
| Before trusting lint during a merge | `git ls-files -u \| wc -l` must print 0, because unmerged paths triple lint findings | FG/local-ci-verification.md |

### 1.4 What the gate and CI actually run

- **`run_source`** (`scripts/run_ci.py:79-93`) runs, in order:
  1. the no-tracked-bytecode check;
  2. `lint/run.py`;
  3. `python -m compileall -q vidbyte`;
  4. `scripts/check_context_write_paths.py`;
  5. `scripts/check_context_primitive_introductions.py`;
  6. `scripts/check_reasoning_trace_contracts.py`;
  7. `python -m pytest`.
- **`run_package`** (:95-103) builds the distributions and runs `_verify_clean_install` (:180-196). That function installs the wheel into a fresh venv **without extras**, then `_smoke_program` (:204-218) runs `import vidbyte` and `from vidbyte import Prompts, VidbyteSDK`.
- **CI** (`.github/workflows/ci.yml`):
  - automatic triggers are removed and it runs on `workflow_dispatch` and `workflow_call` only (:3-9, "TEMPORARILY DISABLED");
  - the matrix is Python 3.11 and 3.12 (:21-23);
  - it installs `".[dev]"` only (:36,57), so the openai-codex extra is never installed in CI;
  - the source stage is at :39 and the package stage, with `--dist-dir dist`, at :60.
- **Static policy** (`.github/workflows/static-policy.yml`): semgrep 1.170.1 (:24), `semgrep --test` (:27) and `semgrep scan --error … vidbyte` (:30). It is `workflow_dispatch` only (:3-6).
  - The rule `no-untyped-mapping-fallback` in `.semgrep/typed-mapping-boundary-policy.yml` flags a parameter typed `object` or `Any` followed by `if not isinstance(x, Mapping|dict): return …`.
  - It scans `/vidbyte/**/*.py` but excludes lib/http, providers, mcp_server and tools/mcp.
- **Placement workflow** (`.github/workflows/agents-md-placement.yml:13-16`) is `workflow_dispatch` only. Its job condition reads `github.event.pull_request…` (:28).
- **No dependency check exists.** There is no lockfile, requirements file, dependency allowlist or license check (`git ls-files`).
  - `pyproject.toml` is checked only by S036/RUF200 for validity, by C016 for distribution and version, and by C015 for package-data.
  - There is no `all` extra that aggregates the others.

### 1.5 Lint mechanics that change how you work

- **Ratchet.** `lint/baseline.json` holds one count ceiling per rule. A rule whose found count exceeds its allowance is REGRESSED and fails the gate (`lint/core/baseline.py:60-68`).
  - unverified: how much slack each rule has today, because lint was not run.
- **Tracked files only.** Lint reads tracked files only (`lint/core/discovery.py:81`, `git ls-files -z`), so a new file is invisible until `git add`. Scope differs by helper:
  - `python_files()` covers `vidbyte/**/*.py` (:53-58);
  - `all_python_files()` covers **every** tracked `.py`, including tests, scripts and lint (:66-70);
  - `readmes()` covers README files (:60-64).
- **Ruff-backed rules** run once over `pyproject.toml vidbyte` with the selector list at `lint/core/ruff.py:26-34` (command at :68), so tests are not ruff-linted.
- **Banned imports.** `lint/ruff.toml` bans `typing.TypedDict`, `typing.assert_never` and `asyncio.Lock` ("Use the SDK-owned concurrency boundary.").
  - Codex works around the ban with `asyncio.Semaphore(CODEX_MAX_CONCURRENT_TURNS)` and an explaining comment at `vidbyte/agents/codex/agent.py:82-86`.
- **mypy** (`lint/mypy.ini`): Python 3.11, `check_untyped_defs`, `disallow_any_generics = True`, `ignore_missing_imports = True`. It is ratcheted as S009.

### 1.6 Lint rules most likely to bite, with today's baseline

| ID | Baseline | What it checks (rule file) | How this change trips it |
|---|---|---|---|
| A001 | 643 | Every tracked `.py` file, including tests and empty files (`a001_agent_readable_file_headers.py:69` uses `all_python_files()`), needs a docstring containing `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:` and `TESTS:` (:24-32). The regex `(?im)^\s*FIELD\s*(\S.*)$` (:53) is case-insensitive. | Every new file, including `native/__init__.py` with the contract bytes and any zero-byte test `__init__.py` (§4.1 #1). The model header is `vidbyte/lib/enums/failure.py:1-10` or `vidbyte/lib/constants/codex.py:1-10`. The sessions tools' "Context Protocol Header" style lacks `ROLE IN CODEBASE:`, so do not copy it. |
| A002 | 703 | `vidbyte/` only. A function whose name, Name ids or attribute names (split on `_` and `.`) contain a policy token needs a `# @intent <slug>` marker between def line −3 and +20. The tokens are retry, backoff, attempt, permission, authorize, pricing, price, billing, redact, secret, persist, persistence, checkpoint, fallback, transition, transport, request, fetch, send, urlopen, provider, subprocess and mcp. | Nearly every ClaudeHost function: `request`, `permission_mode`, `mcp_servers`, `fallback_model`, `persist_session`, `enable_file_checkpointing`, `billing_error`, `transport`. |
| A003 | 36 | Applies only to classes in `vidbyte/lib/errors/` (`a003_context_rich_error_packets.py:22,121`) whose name ends in `Error`. Each needs a literal `DIAGNOSTIC_FIELDS` covering error_kind, expected, actual, safe_runtime_details, likely_causes, repair_approaches, related_docs and relevant_tests. | A new Claude error class placed in `lib/errors/`. Copy `CodexAgentError` (`vidbyte/lib/errors/base.py:129-154`). Feature-local error modules such as `vidbyte/harnesses/errors.py:55` are outside A003. |
| A005 | 33 | A function parameter named transport, runner, store, client, tracer or fetcher (leading `_` stripped) that is annotated `object` or `Any`. | A parameter like `client: Any` for a `ClaudeSDKClient`. Wire names (payload, json_body, headers, metadata, options, data) are exempt. |
| A006 | 34 | Imports from a lower layer (lib, providers, sessions, sources) into orchestration (agents, context, middleware, tools, pipelines, workflows, harnesses, trace, evals, paradigms) or application (client, config, cli, mcp_server) layers, plus concrete import cycles. Function-local imports count; `TYPE_CHECKING` imports and `__init__.py` files are skipped. | Any import of `vidbyte.harnesses…` or `vidbyte.tools…` from `vidbyte/lib/dataclasses/claude.py` outside `TYPE_CHECKING`. |
| A007 | 255 | A numeric literal, including 0, near names containing timeout, retry, attempt, backoff, delay, token, char, byte, truncate, limit, budget, status, depth or interval (an exact split-part match: "tokens" does not match), or used as such a parameter's default, unless it is assigned to an UPPERCASE name. | `limit: int = 0`, `timeout_seconds: float = 30.0`, `if limit < 1`, `max_budget_usd > 0`. Move values to `vidbyte/lib/constants/claude.py`. |
| A009 | 0 | Folder README at most 40,000 characters (`a009_readme_size_limit.py:20`). Legacy ceilings are 65,000 for the codex README and 55,000 for providers (:29-32); the root README is exempt (:25). | A new README under `native/claude/` if one is written. The harnesses README (8,805 characters) has room. |
| C003 | 0 | Import targets computed from runtime data. | A lazy SDK import must be a literal `import`/`from` statement, as in Codex `_load_sdk`. |
| C006 | 104 | Reject bool, NaN and infinity before ordered comparisons in constructors and validators. | Numeric spawn fields such as `max_budget_usd`, `max_turns`, `limit` and `timeout_seconds`. |
| C007 | 16 | A bool field on `*Settings`, `*Config`, `*Configuration`, `*Policy` or `*Options` classes needs an `isinstance(bool)` check. | Bool spawn fields if the record is named that way. |
| C008 | 45 | A function named verb + primitive (verbs require, validate, ensure, normalize, coerce, check, resolve, is; primitives positive, non_negative, finite, bool, int, number, timeout, latency, limit, budget, temperature) must live in the canonical module `vidbyte/lib/dataclasses/validation.py` (`c008_shared_validator_owner.py:24`), which "does not exist yet" (:9). | Copying Codex's `_require_non_negative_int` and `_require_bool` (`vidbyte/lib/dataclasses/codex.py:69,76`) is existing C008 debt. Compliant shapes are `PauseDuration` (`vidbyte/lib/dataclasses/agents.py:132`) and `JevCount.require`. |
| C011 | 2 | A class whose name ends in Agent, Runner, Harness, Session or Machine (`_ENTRY_SUFFIXES`, `c011_agent_owned_usage_and_sync_twins.py:30`) and that defines async `arun` needs a sync `run` twin. | "Host" is not a suffix. A class named `…Session` that defines `arun` would be caught. |
| C015 | 3 | Every non-`.py` file in `vidbyte/` other than a folder README.md must be in package-data. | Any JSON or markdown asset added under `vidbyte/`. |
| C016 | 0 | `contracts/sdk-public-api.json` must byte-match what the generator derives from `vidbyte/__init__.py` `__all__` and the pyproject version (`c016_public_api_contract_current.py:3`). | Any root export. Extras are not recorded in the contract (`lint/core/public_api_contract.py:32`). |
| S006 | 0 | RUF006: a task created without keeping a reference. | A background reader task created by a non-blocking spawn. |
| S007 | 16 | ANN rules: public functions need annotations. | All public functions. |
| S008 | 19 | C901, PLR0912 and PLR0915: complexity, branch and statement counts. | The error mapper and the options translator. |
| S009 | 350 | The mypy ratchet. | New `Any`-generic or untyped code. |
| S012 | 0 | Any method **named** `request`, and outbound requests without a timeout. | A method named `request`. |
| S013 | 4 | Byte ceilings on ingestion. Scoped to tools/builtins/code_search, mcp, operations and tools/mcp (`s013_bounded_untrusted_responses.py:22`). | Out of scope unless placed there. |
| S015 | 13 | A literal `__all__` must be unique and bound, and the root module must list every public import. A dynamic `__all__` is skipped. | Every `__init__.py` this PR edits. |
| S016 | 50 | No builtin exception may leave `vidbyte/tools/builtins/` (`s016_typed_boundary_errors.py:22`). | The new `tools/builtins/claude/` package. |
| S017 | 79 | In `vidbyte/providers/`, `vidbyte/tools/`, `vidbyte/mcp_server/` and `vidbyte/lib/runners/` (`s017_no_raw_exception_disclosure.py:22`), `str(exc)`, `repr(exc)` or an f-string of the caught exception passed to `*Error(...)` or `.error(...)`, returned, or assigned to an error or message attribute. | Copying `_SessionBuiltinTool._caught` (`vidbyte/tools/builtins/sessions/_base.py:85-90`), which returns `f"{type(exc).__name__}: {exc}"`, adds findings. |
| S019 | 5 | A swallowed `CancelledError`, or a bare or `BaseException` handler without re-raise. | Wait and interrupt paths. |
| S024 | 25 | Control-flow nesting depth above 3 (`s024_maximum_control_flow_nesting.py:22`). | Message-loop parsing. |
| S025 | 263 | `ToolSpec` and `ToolParameter` descriptions in `BaseTool` subclasses need at least 4 sentences (`s025_model_facing_description_depth.py:27`). | Every new tool and parameter description. |
| S039 | 5 | TID251 banned API, including `asyncio.Lock`. | A per-session busy lock. The existing 5 are `harnesses/stores/memory.py:41`, `middleware/builtins/circuit_breaker.py:63` and `tools/mcp/transport.py:139,140,144`. |
| S040 | 0 | TID252: relative imports. | Use absolute imports only. |
| S042 | 0 | TRY002: raising a plain `Exception`. | Error mapping. |
| S045 | 2 | ASYNC109: an async function with a `timeout` parameter. "Ruff owns the timeout-name and async-function classification" (`s045_async_function_with_timeout.py:9`). | `async def wait_claude_turn(handle, timeout)` as R3 names it. |
| S051 | 259 | I001 import order, plus UP006, UP007, UP035 and UP045. | Every edited `__init__.py`: imports must sit at their sorted position (§4.1 #12). |
| S052 | 0 | ASYNC100, 105, 110, 220 and 221: blocking calls in async functions, including subprocess and busy-wait. | `subprocess.run` (for example a `claude --version` or `claude auth status` check) inside `async def`; polling loops built from `sleep`. |
| S053 | 0 | B017, B023, B028 and B039 (B023: a closure that does not bind its loop variable). | Building one `tool()` handler per `BaseTool` in a loop. |
| S055 | 0 | Shell-interpreting subprocess calls. | Any CLI call with `shell=True`. |
| S060 | 32 | No public `dict[str, Any]` encoders, and no TypedDict, in `vidbyte/sessions/`, `vidbyte/lib/dataclasses/`, `tools/types.py` and `mcp_server/schema.py`. | Records in `lib/dataclasses/claude.py` that expose the vendor's raw dicts. |
| S061 | 6 | File I/O (open, read_text, write_text, shutil copy or move, extractall) on a non-literal path outside `vidbyte/lib/tools/filesystem/backends/local.py` (`s061_bounded_safe_path.py:25`). | Reading a system-prompt file, or files to attach, inside ClaudeHost. |
| S062 | 889 | Any string built from adjacent literals. The scan covers `all_python_files()`, tests included (`s062_no_implicit_string_concatenation.py:69`). | Copying `vidbyte/tools/builtins/sessions/descriptions.py`, whose constants are built from adjacent literals (unverified: whether each currently counts). |
| S063 | 4 | `gather(return_exceptions=True)` results must be classified against `BaseException`. | `launch_claude_subagents` fan-out. |

The full ID-to-name list is in `lint/rules/README.md:16-109`. Every baseline value is in `lint/baseline.json`.

### 1.7 Conventions from the field guide and the repo skill (not in AGENTS.md)

- **Comment format** (FG/comment-format.md):
  - multi-line `#` comments are wrapped at 72 columns or fewer and sit directly above the code they explain;
  - `# @intent <name>` goes on its own first line, within 20 lines of the `def`.
- **Model-facing tool contracts** (FG/model-facing-tool-contracts.md):
  - each tool takes 6–9 meaningful fields;
  - the tool and every parameter get a general description of 4–5 sentences, with no examples;
  - categorical parameters are `str, Enum` types in `lib/enums` (use `EnumClass.values()`);
  - lists of field names go in `lib/constants`.
- **Strict config dataclasses** (FG/strict-config-dataclasses.md):
  - make the adapter a thin layer over one validated dataclass, and avoid union fields;
  - a primitive validated in two places gets its own dataclass (`PauseDuration`);
  - bounds go in `lib/constants/` with a feature prefix;
  - "Harness bridge functions take validated lib records, not loose `object`/`Mapping` inputs";
  - a callback whose shape the SDK dictates converts its input to a record as its first step;
  - private SDK access stays out of lib;
  - validate before a native fork;
  - set generous caps derived from vendor constants.
- **Class-bound helpers** (FG/class-bound-helpers.md):
  - prefer a static helper class over free functions;
  - separate Vidbyte translation from provider serialization;
  - normalize against the concrete SDK contract;
  - audit every surface, one function per translated surface;
  - read provider requests in the provider's shape;
  - a callback that must not raise uses one `try`.
- **CLI-backed integrations** (FG/cli-backed-source-integrations.md):
  - one library runner owns process execution;
  - model-facing inputs never contain command strings;
  - tool wrappers stay thin.
- **Blocking lint invariants** (FG/blocking-lint-invariants.md):
  - a new A003 class needs the full `DIAGNOSTIC_FIELDS` (follow the shape of `ReasoningTraceArgumentError`, `vidbyte/lib/errors/base.py:77`);
  - S060 and S039 forbid `dict[str, Any]` encoders and TypedDict in lib records;
  - S012 flags any method named `request`;
  - a lib record that holds a higher-layer object checks its shape under `TYPE_CHECKING` (A006);
  - C002 flags duplicated bool guards by field name;
  - A007 flags `read(CAP + 1)`.
- **Repo skill `skills/runtime-primitives/SKILL.md`** (line 3: use it for HarnessAgent adapters over coding-agent SDKs). Its rules at :33-41 include:
  - "Reject unsupported public options. Silent omission creates a false contract." (:38);
  - "Preserve cancellation and close provider clients/processes deterministically." (:40);
  - "Pin pre-1.0 SDK integrations to a reviewed compatibility range and recheck official documentation on upgrade." (:41).
- **Skill references:**
  - `references/control-matrix.md` (39 lines) classifies each Claude concept as Exact, Policy, Emulated or No. Max turns, budget, fork, resume, structured output, SDK MCP tools and `can_use_tool` are all "Exact".
  - `references/claude-agent-sdk.md:31`: "Prefer `ClaudeSDKClient` for a stateful HarnessAgent … Declare setting sources rather than assuming filesystem configuration is loaded. Use native resume/fork fields for lineage."

### 1.8 Commit and PR conventions (from the repo, not AGENTS.md)

- **PR template** (`.github/pull_request_template.md`): Motivation, Changes, Compatibility, Verification (exact commands plus four checkboxes: repo checks pass, package assets present in the wheel, docs and examples updated, no credentials, bytecode or unrelated changes), and Follow-ups. CONTRIBUTING.md:75-85 repeats this.
- **Commit subjects** on main follow `type(scope): summary (#PR)`, for example `678136bd fix(coding): read AGENTS.md and MAP.md that Windows PowerShell writes as UTF-16 (#995)`.
- **The public-API contract** must be regenerated from a clean commit. The generator "refuses while any input file differs from HEAD" and keeps `source.commit` when the derived data is unchanged (`scripts/generate-sdk-public-api.py:9,65-71`).

## 2. Files this change will touch

The request fixes this layout: host code in `vidbyte/harnesses/native/claude/`, tools in `vidbyte/tools/builtins/claude/`, and the toolset in `vidbyte/tools/toolsets/claude.py` (request.md:120-134). The spec chooses module names inside those packages.

### 2.1 New files

#### `vidbyte/harnesses/native/__init__.py` (new; shared-contract file)

- **Today:** it does not exist. `vidbyte/harnesses/` has no subpackage besides `stores/`.
- **Change:** both PRs create it "with exactly these bytes" (request.md:167-173): a four-line docstring "Native coding-harness hosts." / blank / "One subpackage per coding harness, each wrapping that harness's official SDK.".
- **Pattern:** none. The A001 conflict with these bytes is §4.1 #1.

#### `vidbyte/harnesses/native/claude/` (new package; the host)

- **Today:** it does not exist. Nothing in the repo walks harness subpackages automatically.
  - `vidbyte/harnesses/__init__.py:37-63` imports fixed modules: client, config, contracts, dataset, errors, execution, registry, serialization and stores.
  - `HarnessRegistry` (`vidbyte/harnesses/registry.py`) is a name registry, not a package scanner.
- **Change:** `ClaudeHost` (an async context manager that owns the live `ClaudeSDKClient`s, request.md:126-130), the ★ functions, the `claude.<problem>` error mapper, the single module that imports the SDK lazily, and the conversion from `BaseTool` to an SDK MCP tool.
- **Patterns to follow,** all in `vidbyte/agents/codex/` (request.md:232 says read them only):
  - **One lazy import seam:** `CodexTransport._load_sdk` (`vidbyte/agents/codex/transport.py:215-259`, a `@staticmethod`). It does a literal `from openai_codex import (…)` inside `try:`. On `except ImportError as exc:` it raises `CodexAgentError("CodexHarnessAgent requires the optional 'vidbyte-sdk[codex]' integration.", failure_code=FailureCode.CODEX_SDK_UNAVAILABLE.value, operation="load_sdk", error_type=type(exc).__name__) from exc` (:240). Vendor types appear only under `TYPE_CHECKING`, and Protocols `_CodexThread` and `_CodexClient` (:39-48) type the SDK objects.
  - **Header promise:** transport.py:1-10, "WHAT NOT TO DO IN THIS FILE: Swallow cancellation or publish raw exception text".
  - **Tool bridge:** `CodexToolBridge(tools: Tools, permission_policy: PermissionPolicy)` (`vidbyte/agents/codex/tools.py:76-79`). It turns specs into the vendor shape with the canonical helper, `ToolsFormatter.to_codex_tool(spec)` (:82). Private SDK access is confined to `_sync_client` (:96-102), which raises `CODEX_SDK_UNAVAILABLE`. `CodexToolCallHandler(executor: ToolExecutor, loop, fallback)` (:122-125) runs the Vidbyte tool through `ToolExecutor`, which applies `PermissionPolicy`.
  - **Failure translation:** `CodexFailureTranslator` (`vidbyte/agents/codex/failures.py:50`) and `CodexFailureLedger` (:99) map errors to codes using `CODEX_FAILURE_CLASSIFICATION` (`vidbyte/lib/constants/codex.py:95-174`).
  - **Concurrency without `asyncio.Lock`:** `self._turns = asyncio.Semaphore(CODEX_MAX_CONCURRENT_TURNS)` (`vidbyte/agents/codex/agent.py:86`, with the comment at :82-85).
  - **Package layout:** the codex package spreads its 2,633 Python lines over 13 modules (`__init__` 75, agent 374, config 295, context 273, contracts 228, failures 127, fallback 151, fork 144, metrics 85, middleware 210, result 229, tools 180, transport 262). Its README is 1,121 lines with a File Index at :1103-1117 and a failure-code table at about :888.
  - **Canonical schema helper for the tool conversion:** `ToolsFormatter.to_anthropic_tool(spec)` (`vidbyte/lib/tools/formatter.py:111-118`) returns `{"name", "description", "input_schema": _schema_for_spec(spec)}`.
  - **Agent-owned subprocess cleanup:** `McpAttachableMixin.close_mcp_servers()` (`vidbyte/agents/mixins.py:280-293`) is called from the sync-run wrapper in a `finally` (:242-257) and from `__aexit__` (:375-376).

#### `vidbyte/lib/dataclasses/claude.py` (new; records)

- **Today:** it does not exist. No Claude record exists anywhere: `git grep -i claude` over `vidbyte/lib` finds model names and pricing only.
- **Change:** `ClaudeSpawnRequest`, the handle, results, usage, rate-limit and readiness records, plus any request records for tools. The mapping inputs are in §2.5.10.
- **Pattern:** `vidbyte/lib/dataclasses/codex.py` (1,205 lines, already over 1,000).
  - Header at :1-10: "PURPOSE: Defines immutable inputs, settings, and outputs…" and "TESTS: python scripts/run_ci.py".
  - Imports at :12-41. Errors are raised as `ConfigurationError` from `vidbyte.lib.errors` (class at `vidbyte/lib/errors/base.py:235`).
  - Higher-layer types are imported only under `if TYPE_CHECKING:` (:43-52).
  - Every record is `@dataclass(frozen=True, slots=True)`. `CodexClientSettings` (:102-136) has `codex_bin: str = ""` and `env: Mapping[str, str] = field(default_factory=dict)`, and its `__post_init__` loops over field names.
  - `CodexToolAttachRequest` (:1082) carries `client: object` and a loop. `CodexToolCallRequest.from_params` (:1108-1150) converts a vendor `Mapping` into a record.
  - `CodexSdkTypes` (:1186-1203) holds the loaded SDK classes as fields typed `type`.
  - `__all__ = [name for name in globals() if name.startswith("Codex")]` (:1205) is dynamic, so S015 skips it.
  - The private validators `_require_text`, `_optional_text`, `_require_non_negative_int` and `_require_bool` (:55-79) are C008 debt; do not copy them.

#### `vidbyte/lib/enums/claude.py` (new; enums)

- **Today:** it does not exist.
- **Change:** closed sets such as permission mode, effort, thinking mode, setting source, rate-limit status and type, and the problem names (request.md:221).
- **Pattern:** `vidbyte/lib/enums/codex.py` (120 lines).
  - Header at :1-10, including "Enum values must match openai-codex 0.162 wire values exactly" and "Empty PROVIDER_DEFAULT sentinels are omitted before SDK calls".
  - Most classes are `class CodexApprovalMode(str, Enum)` with `PROVIDER_DEFAULT = ""` (:17-22). One is a `StrEnum` (`CodexContextAnchor`, :100).
  - The literal `__all__` is at :109-120.
- **Vendor wire values to mirror:**
  - `PermissionMode`: default, acceptEdits, plan, bypassPermissions, dontAsk, auto (`SDK/types.py:25-27`).
  - `SettingSource`: user, project, local (:33).
  - `EffortLevel`: low, medium, high, xhigh, max (:37).
  - `SdkBeta`: only "context-1m-2025-08-07" (:30).
  - `RateLimitStatus`: allowed, allowed_warning, rejected (:1391).
  - `RateLimitType` (:1392-1396): five_hour, seven_day, seven_day_opus, seven_day_sonnet, overage, per request.md:230.
  - `AssistantMessageError` (:1037-1044): 6 values.

#### `vidbyte/lib/constants/claude.py` (new; constants)

- **Today:** it does not exist.
- **Change:** the extra label, bounds, defaults and minimum version. A007 forces numeric policy values here.
- **Pattern:** `vidbyte/lib/constants/codex.py` (267 lines; header :1-10).
  - `CODEX_SDK_EXTRA = "vidbyte-sdk[codex]"` (:50).
  - `CODEX_FAILURE_CLASSIFICATION: Mapping[str, tuple[str, str, str, str]]` keyed by `FailureCode…value` (:95-174).
  - `CODEX_TOOL_CALL_TIMEOUT_SECONDS = 300.0` (:193), with its reason comment.
  - `CODEX_MAX_CONCURRENT_TURNS = 1` (:226), with its reason comment.

#### `vidbyte/tools/builtins/claude/` (new package; one tool per ★ function)

- **Today:** it does not exist.
- **Change:** "Copy the `vidbyte/tools/builtins/sessions/` layout: a `_base.py` holding shared state, one file per group of tools, and a `descriptions.py`" (request.md:122). Tools hold one `ClaudeHost` per agent (request.md:130) and return an error `ToolResult` instead of raising (request.md:148).
- **Pattern:** `vidbyte/tools/builtins/sessions/`, 11 files and 948 lines:
  - `__init__` 39, `_base` 93, `batch_fork` 91, `checkpoint` 98, `descriptions` 126, `fork` 92;
  - `resume_append` 81, `resume_output` 67, `resume_replace` 97, `rewind` 62, `session` 102.
- **`_SessionBuiltinTool(BaseTool)`** (`_base.py:30`):
  - `__init__(self, store, *, scope=None)` at :33;
  - `bind_owner(owner)` at :43;
  - `bind_session(session)` at :47;
  - `clone_for_fork()` at :52;
  - `clone_for_agent()` at :58, with `# @intent shared-session-tool-gets-configured-scope`;
  - `_denied` at :63;
  - `_optional_text` at :68, which treats JSON null as omitted (`# @intent null-optional-arg-means-default`);
  - `_caught(name, operation)` at :85-90, which wraps `SessionError` into `ToolResult.error(name, f"{type(exc).__name__}: {exc}")`. That is S017 debt.
- **`ForkTool`** (`fork.py:27-92`):
  - module constant `_TOOL_NAME = "fork"`;
  - `spec()` returns `ToolSpec(name=_TOOL_NAME, description=FORK_TOOL_DESCRIPTION, permission=ToolPermission.SAFE, input_schema={"type": "object", "additionalProperties": False, "properties": {…}})`;
  - `async def execute(self, call)` returns `self._caught(_TOOL_NAME, lambda: self._perform(call.arguments))`;
  - it imports from `vidbyte.tools.types` and `…sessions.descriptions`;
  - `__all__ = ["ForkTool"]`.
- **`descriptions.py`** (126 lines) has a one-line docstring with no A001 header. Its constants at :5-104 are built from adjacent string literals (S062).
- **A second binding precedent** is `PauseAgentTool(max_seconds=…)`, a developer-set bound on a model-facing tool (`vidbyte/tools/builtins/pause.py:87,91,94`):
  - `_DEFAULT_MAX_SECONDS = 60`;
  - `bind_agent` at :98;
  - `clone_for_fork` at :102.
  - The README describing it is `vidbyte/tools/README.md:93-101`.

#### `vidbyte/tools/toolsets/claude.py` (new; the toolset)

- **Today:** it does not exist. `vidbyte/tools/toolsets/` holds `coding.py` (138 lines) and `paradigm_minimal.py` (67 lines).
- **Change:** a `Tools` bundle of the Claude tools (request.md:123).
- **Pattern:** `class CodingAgentTools(Tools)` (`vidbyte/tools/toolsets/coding.py:47`):
  - `__init__(self, settings: CodingAgentSettings)` (:50) narrates each step, then calls `super().__init__(self.get_tools(...))`;
  - its helpers are `@staticmethod`s (:60, :80);
  - `__all__ = ["CodingAgentTools"]` (:138).
  - `Tools` is `class Tools(Sequence[BaseTool])` (`vidbyte/tools/catalog.py:27`).

#### `tests/test_claude_*.py` (new)

See §3.

### 2.2 Shared files this PR edits (the request.md:166-184 contract)

#### `vidbyte/lib/enums/failure.py` (297 lines)

- **Today:**
  - `class FailureCode(str, Enum)` (:22) is the closed vocabulary.
  - Members are grouped by category in the order configuration (:25-34), **codex (:35-46)**, input, output, contract, serialization, model, provider, tool, action, runtime, resource, session (:112-120), state, data, workflow, agent, team, usage, trace, recovery and rule (last member `RULE_EVALUATION_FAILED` at :144). The order is not alphabetical.
  - The first CODEX member is `CODEX_SDK_UNAVAILABLE = "codex.sdk_unavailable"` (:35); the last is `CODEX_RUN_OPTION_UNSUPPORTED = "codex.run_option_unsupported"` (:46). `INPUT_EMPTY` follows at :47.
  - Value format: `"<category>.<snake_case_problem>"`.
  - `category` returns the text before the first "." (:147-149).
  - `from_exception` (:159-174) reads `exc.failure_code` first, then HTTP status codes, then `_from_exception_name` (:176-218), which matches substrings of the lowercased class name such as "sessionnotfound", "sessionerror" and "timeout". The fallback is at :220-232.
  - Existing `SESSION_NOT_FOUND = "session.not_found"` is at :112.
  - The header's TESTS line is `python scripts/test-session-failure-vocabulary.py`; that script is not run by run_ci.
- **Change:** add `CLAUDE_*` members as one block, "not adjacent to the end of the `CODEX_*` block". The request's example is directly before :35 (request.md:182).
- **Other places that list members:**
  - `vidbyte/lib/constants/codex.py:95-174`, Codex members only;
  - `vidbyte/agents/codex/README.md` table near :888;
  - `tests/test_codex_failure_recovery.py:188-201` (`ClassificationCoverageTests`): every `FailureCode` whose value starts with `"codex."` must have a row in `CODEX_FAILURE_CLASSIFICATION`, and every row must name a real code;
  - `tests/test_session_failures.py:137-139`: "every public code is groupable by its first dotted component" (`"." in code.value`).
  - `skills/failure/vocabulary.md` lists no Codex codes, so it is not exhaustive.

#### `vidbyte/lib/enums/__init__.py` (235 lines)

- **Today:**
  - It imports per-domain modules in sorted order: `from vidbyte.lib.enums.agent_runtime import …` (:40) and `from vidbyte.lib.enums.codex import (` (:41-51).
  - `__all__` (:142-235) is alphabetical, with Codex entries at :153-161.
  - `CodexFailureClass` is not exported, although AGENTS.md:61 says every public enum is.
- **Change:** export each new public Claude enum. The contract says append-only (request.md:183), but see §4.1 #12.
- **Pattern:** the import block at :41-51, plus one `__all__` string per enum.

#### `vidbyte/tools/builtins/__init__.py` (325 lines)

- **Today:**
  - A "Context Protocol Header" docstring at :1-24, with no A001 `ROLE IN CODEBASE:`.
  - It eagerly imports every builtin category in module order: `bash` at :28, then `code_execution`, `code_search`, `context` …, and `sessions` at :167-176.
  - `__all__` starts at :182 (for example "ForkTool" at :241 and "PauseAgentTool" at :274) and ends with `__all__.extend(...)` for reasoning tools (:321-325).
- **Change:** export the Claude tools.
- **Note:** this file is imported at module level by `vidbyte/agents/runtime.py:151` and `vidbyte/agents/coding_context/environment.py:35`, so whatever it imports loads during `import vidbyte.agents` (§4.1 #15).

#### `vidbyte/tools/toolsets/__init__.py` (23 lines)

- **Today:** a header (:1-13), sorted imports (:17-18), and `__all__ = ["CodingAgentTools", "ParadigmMinimalToolset"]` (:20-23).
- **Change:** export the Claude toolset.

#### `vidbyte/__init__.py` (1,297 lines; only if the spec exports from the root)

- **Today:**
  - `from vidbyte.agents import (` (:41) includes `CodexHarnessAgent` (:79).
  - `from vidbyte.harnesses import (` is at :380-399, the session tools at :596-605, and `from vidbyte.tools.toolsets import CodingAgentTools, ParadigmMinimalToolset` at :611.
  - `__all__` starts at :690 and is grouped, not alphabetical: "CodingAgentTools" :716, "CodexAgentError" :999, "CodexHarnessAgent" :1010, "HarnessClient" :1073.
  - The root `__init__` imports builtins directly (:573-605).
- **Change:** whatever the spec decides (request.md:245). Each root export changes the contract (C016).

#### `contracts/sdk-public-api.json` (614 lines; generated)

- **Today:**
  - `"source": {… "commit": "f7a02bae175913f4ab1cd25d89bfce5ae78e86d0" …}` (:3), `"distribution": "vidbyte-sdk"` (:4), `"version": "0.2.1"` (:5).
  - `exports` is sorted, for example "CodexHarnessAgent" at :91.
- **Change:** regenerate only if root exports change. The file is generator output: `exports must be sorted and unique` (`lint/core/public_api_contract.py:87`), and C016 requires byte equality.

#### `REPO_MAP.md` (62,470 characters)

- **Today:** File Index entries are headings per folder:
  - `vidbyte/harnesses/` at :147 and `vidbyte/harnesses/stores/` at :151;
  - `vidbyte/tools/` at :315 and `vidbyte/tools/builtins/` at :319;
  - `vidbyte/tools/toolsets/` at :335, which says "It currently holds one such bundle" although `coding.py` and `paradigm_minimal.py` both exist.
  - There is no entry for `vidbyte/agents/codex/`.
- **Change:** add entries for the new subpackages. AGENTS.md:9 says the File Index covers each subpackage of `vidbyte/`.

#### `vidbyte/harnesses/README.md` (180 lines, 8,805 characters)

- **Today:** sections at :1 (title), :42, :92, :114, :130, :158 ("Relationship to adjacent layers") and :167 ("Key modules"). It ends with a link to a `docs/design` file. It has no File Index and no Notes for agents.
- **Change:** append mention of `native/` (request.md:183).

#### `pyproject.toml`

- **Today:**
  - `dependencies` is `pydantic>=2,<3`, `httpx>=0.27` and `PyYAML>=6,<7` (:35-39). There is no `mcp`, `anyio` or `jsonschema`.
  - `[project.optional-dependencies]` (:41) contains `codex = ["openai-codex>=0.162.1,<0.163.0"]` (:42-44) and the pinned `dev` list (:45-52).
  - package-data is at :68-76.
  - `[tool.pytest.ini_options]` (:78-81) sets `testpaths = ["tests"]`, `addopts = ["--strict-config", "--strict-markers"]` and `asyncio_default_fixture_loop_scope = "function"`, with no `asyncio_mode`.
- **Change:** add a `claude` extra (request.md:125). Only this PR touches this file (request.md:184).

### 2.3 Files this PR may edit (the request.md:166-184 contract does not cover them)

| File | Today | Why it may change |
|---|---|---|
| `vidbyte/lib/errors/base.py` | `VidbyteSdkError` :59, `ReasoningTraceArgumentError` :77 (the A003 shape), `AgentExecutionError` :125, `CodexAgentError` :129-154, `ConfigurationError` :235 | If the spec puts a Claude error class in `lib/errors/`, as Codex did. `CodexAgentError.__init__(self, message, *, failure_code, operation, error_type="")` sets `failure_code`, `operation` and all 8 diagnostic attributes and passes `details={…}` to `super().__init__`. |
| `vidbyte/lib/errors/__init__.py` | exports `CodexAgentError` (:26 import, :73 `__all__`) | Export of a new error class. |
| `vidbyte/lib/dataclasses/__init__.py` (481 lines) | re-exports Codex records (:51-67); `__all__` at :269; imports `vidbyte.context.primitives` at :19 | If records are re-exported here as Codex's are. |
| `vidbyte/lib/constants/__init__.py` (167 lines) | re-exports Codex constants (:3-11); `__all__` at :91 | If constants are re-exported here. |
| `vidbyte/agents/base.py` | `_bind_agent_tool_context` (:421-447) binds only a hard-coded list of builtin classes through local imports (AgentTool, ForkConversationTool, CreateHandoffTool, AttachMcpServerTool, RunPromptsSequentiallyTool, PauseAgentTool and `_SessionBuiltinTool`). `_own_tool` (:449-470) gives a second agent an unbound copy of those same classes only. `_unbound_copy` (:472-482) calls `clone_for_agent()` if it exists, else `clone_for_fork()`. `_bind_session_tool` (:484-490) calls any tool's `bind_session` attribute with the agent's Vidbyte `Session`. | Only if Claude tools must bind to their agent the way session tools do. The file is outside the shared-file contract (§4.1 #14). |
| `vidbyte/tools/README.md` (6,343 chars) | sections on Cooperative Pause (:93-101) and Priced Operation Tools (:103-132) | Documenting the new builtin category, if wanted. |

### 2.4 Neighbours inside the repo (read; not edited unless the spec says so)

- **`vidbyte/tools/base.py`.**
  - `class BaseTool(ABC)` (:28) has `name` (a property from `spec().name`), `with_activity`, `rebind_context_manager` and `customize`.
  - Its abstract methods are `spec() -> ToolSpec` and `async def execute(self, call: ToolCall) -> ToolResult`.
  - `validate_call(call) -> str | None` checks required parameters. **Tools are async.**
- **`vidbyte/lib/dataclasses/tools.py`.**
  - `ToolStatus` (:40); `ToolPermission` (:47-53) with members SAFE, READ, WRITE and EXECUTE; `ToolParameter` (:66).
  - `ToolSpec` (:115): `name`, `description`, `parameters`, `permission = ToolPermission.SAFE`, `metadata`, `input_schema: Mapping | None`, `binds_to_primitive`, `output_schema` and `activity`. Its `__post_init__` coerces the permission to the enum.
  - `ToolCall(tool_name, arguments, call_id, metadata, activity)` (:267).
  - `ToolResult(tool_name, status, output, metadata)` (:283) with `success()` (:298), `error()` (:314) and `failure()` (:330, an alias of `error`).
- **How the runtime reads error results** (`vidbyte/agents/runtime.py:1274-1279`). It takes `metadata["error_type"]`, or else `metadata["error"]`. `metadata["error"] == "timeout"` counts as a tool timeout (:1278). The existing key convention is `metadata={"error": <code>, "error_type": <type>}` (:1301; `vidbyte/tools/executor.py:75`).
- **Runtime tool timeout** (`vidbyte/agents/runtime.py:1448-1460`). When `ToolSettings.tool_timeout_seconds` is set (`vidbyte/agents/settings/tool.py:50`), every non-internal `tool.execute` runs under `asyncio.wait_for`, and a timeout cancels the tool coroutine.
- **`vidbyte/lib/dataclasses/security.py`.** `PermissionPolicy` (:30) defaults to allowing `{SAFE, READ}` (:33-35). `check` (:45-50) returns DENY for any other permission, and `allow_all()` is at :52-55. `ToolExecutor` applies the policy (`vidbyte/tools/executor.py:37,41,53`).
- **`vidbyte/mcp_server/`.**
  - `McpStudioServer(…, tools: Sequence[BaseTool] = (), …)` (`server/core.py:68,81`); the header at :7 names Claude as a client.
  - `StudioToolRegistry.execute` (`handlers.py:84-88`) calls `await tool.execute(ToolCall(name, arguments))` directly, with **no PermissionPolicy**.
  - Serving a new toolset therefore needs no new code: pass the tools in. WRITE tools are not gated there (§4.1 #13).
  - The `mcp_server` README is 1,918 characters, and `vidbyte/mcp_server/schema.py` is in S060 scope.
- **`vidbyte/harnesses/__init__.py`** (95 lines) imports execution (:60). `vidbyte/harnesses/execution.py:69-71` imports `vidbyte.sessions.session` at module level, and `vidbyte/sessions/session.py:25` imports `vidbyte.agents.types` at module level. See the cycle risk in §4.1 #15.
- **The sync agent loop.** `BaseAgent.run()` uses `asyncio.run(self._run_releasing_mcp(...))` (`vidbyte/agents/base.py:1018-1024`), which is a fresh event loop per sync run. `_run_releasing_mcp` closes the attached MCP subprocesses before that loop ends (`vidbyte/agents/mixins.py:242-257`, `# @intent sync-run-does-not-strand-mcp-on-closed-loop`).
- **Scripts.**
  - `scripts/test-codex-tools.py` (120 lines) is a standalone unittest loader that is not in run_ci.
  - `scripts/test-github-content-readmes.py:9-22` lists only the 12 top-level layer READMEs plus a reserved `vidbyte/shared/README.md`, and is not in run_ci.
- **No rule requires a README in every package folder.**
  - A009 only caps size.
  - S020 (README File Index parity) is opt-in.
  - C015 exempts README files.
  - Folders without a README already exist: `vidbyte/tools/builtins/`, `tools/builtins/sessions/`, `tools/toolsets/`, `lib/dataclasses/`, `lib/enums/`, `lib/constants/` and `lib/errors/`.
  - Under request.md:175, `vidbyte/harnesses/native/README.md` is therefore not created.

### 2.5 claude-agent-sdk 0.2.165: neighbour (third-party, read-only)

#### 2.5.1 Package facts

- `SDK/_version.py` is "0.2.165". `SDK/_cli_version.py:3` is `__cli_version__ = "2.1.294"`, the bundled CLI.
- The vendor `pyproject.toml` (`…/claude_agent_sdk-0.2.165/pyproject.toml`) requires Python `>=3.10` (:10). Its dependencies (:27-33) are `anyio>=4.0.0`, `sniffio`, `mcp>=1.23.0,<3.0.0` and `jsonschema>=4.20.0`.
- `SDK/__init__.py:28-30` imports `jsonschema` and `mcp.types` **at module import**. Importing the package therefore needs the whole extra.
- **Exported errors** (`SDK/__init__.py:32-39`): `ClaudeSDKError`, `CLIConnectionError`, `CLIJSONDecodeError`, `CLINotFoundError`, `ProcessError` and `ResultError`. `MessageParseError` is **not** exported. Its class is at `SDK/_errors.py:129`.
- **The user's CLI** is the file `C:/Users/422mi/.local/bin/claude.exe` (260,489,376 bytes, per `ls`); request.md:186 names it `…/claude`. Its version (2.1.296) comes from request.md and was not run.

#### 2.5.2 `ClaudeSDKClient` (`SDK/client.py`, 631 lines)

- **Docstring caveat** (:58-64): a client cannot be used across async contexts. It keeps a persistent task group from `connect()` until `disconnect()`.
- **`connect(prompt=None)`** (:93) leads to `_connect_inner` (:141-258):
  - it validates `session_store` options (:99-117);
  - `_configure_can_use_tool` (:154);
  - it collects in-process SDK MCP instances from `mcp_servers` entries whose type is "sdk" (:170-174);
  - it pulls `exclude_dynamic_sections` and `snapshot` out of a `SystemPromptPreset` (:183-195);
  - it converts `agents` (:197-205);
  - it builds the internal Query (:211-218);
  - it reads env `CLAUDE_CODE_STREAM_CLOSE_TIMEOUT` (ms, default 60000, floor 60 s) (:176-181);
  - it starts the transport and sends `initialize` (:243-244).
- **`query(prompt: str | AsyncIterable[dict], session_id="default")`** (:272-306) only writes one user JSON line, or streams dicts, to stdin. It does no turn-state check and sends no priority field. Content blocks such as images need the dict / `AsyncIterable` form.
- **Live-control methods:**
  - `interrupt()` (:308-312);
  - `set_permission_mode` (:314) and `set_model` (:341);
  - `rewind_files` (:364);
  - `reconnect_mcp_server` (:395) and `toggle_mcp_server` (:417);
  - `stop_task` (:443);
  - `get_mcp_status` (:471) and `get_context_usage` (:504).
- **`get_server_info()`** (:540-564) returns `getattr(self._query, "_initialization_result", None)`, which is the raw initialize response dict. It returns `None` while `connect()` is still running.
- **`receive_response()`** (:566-605) yields messages and stops after the first `ResultMessage`. "If no ResultMessage is received, the iterator continues indefinitely". `receive_messages()` is at :260.
- **Lifecycle:** `disconnect()` is at :607-621, and `__aenter__`/`__aexit__` at :623-631.
- **One-shot `query(*, prompt, options=None, transport=None)`** is `SDK/query.py:11-132`, which offers no interrupts, and `_internal/client.py` (`InternalClient.process_query`).

#### 2.5.3 Messages and the result

- **Assistant messages:**
  - `AssistantMessageError` (`SDK/types.py:1037-1044`) has 6 values: authentication_failed, billing_error, rate_limit, invalid_request, server_error and unknown.
  - `AssistantMessage` (:1139) has `error: AssistantMessageError | None` and `usage: dict | None`.
  - The parser passes `data.get("error")` through raw (`SDK/_internal/message_parser.py:151-224`).
  - The TS union has 13 kinds (DTS:3717): it adds oauth_org_not_allowed, account_on_hold, verification_required, overloaded, model_not_found, max_output_tokens and cloud_credential_error.
- **`ResultMessage`** (`SDK/types.py:1340-1377`) fields:
  - subtype, duration_ms, duration_api_ms, is_error, num_turns and session_id;
  - stop_reason, total_cost_usd, `usage: dict | None` and result;
  - structured_output and `model_usage: dict[str, ModelUsage] | None`;
  - permission_denials, deferred_tool_use and errors;
  - api_error_status, uuid, terminal_reason and origin.
  - The parser copies only these fields (`message_parser.py:308-341`), so the CLI's `queued_turn_count` (DTS:5755) and `user_message_uuids` (DTS:5769) are dropped.
- **Usage shapes.** `ModelUsage` (`SDK/types.py:1314-1336`) uses camelCase keys: inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens, webSearchRequests, costUSD, contextWindow and `maxOutputTokens` (:1328). `TaskUsage` (:1161-1166) is per background task.
- **System messages.** Known subtypes (task_started and others) are parsed at `message_parser.py:226-296`. Every other subtype, including `init`, becomes `SystemMessage(subtype, data)` with the raw dict (:298-302).
  - The TS `system/init` message (DTS:5971-6040) is emitted "at the start of each turn". It carries a required `claude_code_version` (DTS:5983) plus `apiKeySource`, `model`, `tools`, `mcp_servers`, `permissionMode`, `skills`, `plugins` and `plugin_errors`.
- **Unknown message types** are skipped (`message_parser.py:391-395`).

#### 2.5.4 Errors and how they surface

- **Error classes** (`SDK/_errors.py`):
  - `ClaudeSDKError` (:6);
  - `CLIConnectionError` (:10);
  - `CLINotFoundError(CLIConnectionError)` (:14-22);
  - `ProcessError(exit_code, stderr)` (:25-39);
  - `ResultError(ProcessError)` (:56-117), with subtype, errors, result, api_error_status, terminal_reason, session_id and data;
  - `CLIJSONDecodeError` (:120);
  - `MessageParseError` (:129).
- **How a failed turn reaches the caller:**
  - An `is_error` result arrives as a `ResultMessage` on the stream.
  - `ResultError` replaces `ProcessError` only when the process then exits non-zero after such a result (`SDK/_internal/query.py:512-535`).
  - The error is put on the message stream (:552-554).
  - `_error_result_text` (:85-110) builds its text.
- **Error shapes to expect:**
  - A non-zero exit raises `ProcessError` whose stderr is the placeholder "Check stderr output for details" (`SDK/_internal/transport/subprocess_cli.py:1156-1162`).
  - Control-protocol errors become a bare `Exception` (`_internal/query.py:403-406`).
  - A control-request timeout raises a bare `Exception("Control request timeout: …")` (:748-751).
  - A missing CLI raises `CLINotFoundError`. A bad cwd raises `CLIConnectionError` (`subprocess_cli.py:901-911`).
  - The batch-file reject raises `CLIConnectionError` (:415-448). The Windows cmd-metacharacter reject raises `ValueError` (:451-471).
  - A non-local plugin raises `ValueError` while the command is built (:732-738).
- **Interrupted turns.** `terminal_reason` "aborted_streaming" or "aborted_tools" means interrupted (`SDK/types.py` ResultMessage docs, :1339-1377).
- **Process cleanup.** A raw asyncio cancellation, such as `asyncio.timeout` or `wait_for`, can skip close-escalation and orphan the child. The caveat is in `close()` (`subprocess_cli.py:962-987`, caveat paragraph :978-987), which names "`asyncio.wait_for` / `asyncio.timeout` firing, a bare `task.cancel()`, loop shutdown". A still-running child stays in `_ACTIVE_CHILDREN` for the atexit reaper (:54-68).

#### 2.5.5 initialize and `get_server_info()`

- **Sending initialize.** `Query.initialize` (`SDK/_internal/query.py:309-363`) sends `{"subtype": "initialize", "hooks": …}` plus these optional keys (:339-355):
  - `agents`;
  - `excludeDynamicSections`;
  - `systemPromptSnapshot`;
  - `skills` (only when it is an explicit list);
  - `forwardSubagentText`.
  It stores the response at `self._initialization_result` (:362).
- **The response shape** (`SDKControlInitializeResponse`, DTS:4588-4640), with the fields `get_server_info()` returns:
  - `commands`, `agents`, `output_style` and `available_output_styles`;
  - `models: ModelInfo[]` and `account: AccountInfo`;
  - optional `hooks_applied`, `plugins_applied` and `sdk_mcp_manifests_parked`;
  - **`claude_code_version?`** (DTS:4623, "Absent on CLIs that predate the field");
  - `fast_mode_state` and `fast_mode_disabled_reason`.
- **`AccountInfo`** (DTS:23-34): every field is optional (`email`, `organization`, `subscriptionType`, `tokenSource`, `apiKeySource`, `apiProvider`). For third-party providers the other fields are absent.
- **`ModelInfo`** (DTS:1396-1432): `value`, `resolvedModel?`, `displayName`, `description`, `supportsEffort?`, `supportedEffortLevels?`, `supportsAdaptiveThinking?`, `supportsFastMode?` and `supportsAutoMode?`.

#### 2.5.6 Rate limits

- **Parsing.** `rate_limit_event` messages are parsed at `SDK/_internal/message_parser.py:356-376` into `RateLimitEvent(rate_limit_info, uuid, session_id)` (`SDK/types.py:1424-1435`).
- **`RateLimitInfo`** (:1397-1421) has `status`, `resets_at`, `rate_limit_type`, `utilization`, `overage_status`, `overage_resets_at`, `overage_disabled_reason` and `raw`. There is one window per event.
- **Timing.** The docstring says the event is emitted "whenever the rate limit status transitions". It arrives only on a live session's stream; no Python call reads limits on demand.

#### 2.5.7 Session history (synchronous and blocking; no process)

- **Where the files live.** The config directory is `CLAUDE_CONFIG_DIR` or `~/.claude` (`SDK/_internal/sessions.py:122-141`). `_get_worktree_paths` runs `git worktree list --porcelain` with a 5 s timeout (:388-413).
- **Reading functions:**
  - `list_sessions(directory=None, limit=None, offset=0, include_worktrees=True) -> list[SDKSessionInfo]` (:680-731).
  - `get_session_info(session_id, directory=None) -> SDKSessionInfo | None` (:739-818). It returns `None` when the session is not found, the UUID is invalid, it is a sidechain, or it has no summary.
  - `get_session_messages(session_id, directory=None, limit=None, offset=0) -> list[SessionMessage]` (:1059-1110). It returns `[]` when the session is not found.
  - Async `*_from_store` variants start at :1672.
- **The records:** `SDKSessionInfo` (`SDK/types.py:1743-1775`) and `SessionMessage` (:1778-1809).
- **`fork_session(session_id, directory=None, up_to_message_id=None, title=None) -> ForkSessionResult(session_id)`** (`SDK/_internal/session_mutations.py:240-345`; result class :233-237).
  - It raises builtin `ValueError` for an invalid id or an invalid `up_to_message_id` (:294, :296), and for "has no messages to fork" (:308).
  - It raises `FileNotFoundError` when the session is not found (:300).
  - It writes the new file with `O_EXCL` (:339).
  - Also in this module: `rename_session` :53, `tag_session` :112, `delete_session` :182.

#### 2.5.8 In-process SDK MCP server (custom tools)

- **`tool(name, description, input_schema, annotations=None)`** is at `SDK/__init__.py:251-335`.
  - `_build_input_schema` (:410-430) passes a dict through unchanged when it has a string `type` and a `properties` key, so it is already a JSON Schema.
  - Any other dict is read as `{param: python_type}`, and then **every key is required**.
- **`create_sdk_mcp_server(name, version="1.0.0", tools=None)`** is at :491-619.
  - Handler results are `{"content": […], "is_error": bool}`.
  - An exception from a handler becomes `_tool_error_result(str(e))` (:614-615).
  - The server rides in `mcp_servers` as a `{"type": "sdk", …, "instance": …}` entry. The instance is removed before `--mcp-config` is built (`subprocess_cli.py:666-692`).
- **`SDK/_internal/sdk_mcp_bridge.py`.** `SHUTDOWN_GRACE_SECONDS = 5.0` (:47). The server runs in a detached task and refuses server-to-client requests.

#### 2.5.9 Process start and CLI discovery (`SDK/_internal/transport/subprocess_cli.py`, 1,228 lines)

- **Version constants:** the minimum CLI version is 2.0.0 (:37). The minimum for verbatim prompts is 2.1.248 (:40).
- **`_find_cli()`** (:255-339) is used only when `cli_path` is None. Its order is:
  1. **the bundled CLI first** (:258-260);
  2. then `which` (on Windows, native `.exe` only);
  3. then the Windows `~/.local/bin/claude.exe` (:296).
- **`_build_command()`** (:570-795) translates options to flags (table in §2.5.10).
- **`connect()`** (:797-915):
  - **Environment** (:812-869):
    - removes `CLAUDECODE`;
    - sets `CLAUDE_CODE_ENTRYPOINT=sdk-py` unless `options.env` overrides it;
    - merges `options.env` over the inherited environment;
    - always sets `CLAUDE_AGENT_SDK_VERSION`;
    - sets `CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING=true` when checkpointing is on (:864-865);
    - sets `PWD` to `cwd`.
  - It calls `open_process(user=…)` (:880).
  - It maps `FileNotFoundError` to `CLINotFoundError` or a cwd `CLIConnectionError` (:901-911).
- **`_check_claude_version`** (:1164-1224) runs `claude -v` with a 2 s timeout and **only warns**. It is skipped when `CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK` is set.

#### 2.5.10 Mapping each `ClaudeSpawnRequest` field (request.md:101-118) to the SDK

"Field" means a `ClaudeAgentOptions` field (`SDK/types.py:1971-2437`); line numbers are in types.py. "Flag" means what `_build_command` emits (subprocess_cli.py lines). "None" means no Python field exists.

| Request field | 0.2.165 Python surface | Notes |
|---|---|---|
| `prompt` | `client.query(str \| AsyncIterable[dict])` (client.py:272) | Images need the content-block dict form. |
| `files` (`--file`) | None; no `--file` in `_build_command`, and none in the DTS flag list | Only through `extra_args` (2139; subprocess_cli.py:740-755). unverified: the flag. |
| `cwd` | `cwd` 2096 | Also sets env `PWD`. |
| `add_dirs` | `add_dirs` 2118, flag `--add-dir` (662-665) | |
| `model` | `model` 2070, flag `--model` | |
| `fallback_model` (ordered list) | `fallback_model: str \| None` 2076, a single `--fallback-model` (625-626) | §4.1 #5. |
| `effort` | `effort: EffortLevel` 2372, flag `--effort` (777-778) | |
| `thinking` | `thinking: ThinkingConfig` 2359 (`ThinkingConfig*` types.py:1817-1832), flags `--thinking adaptive\|disabled`, `--max-thinking-tokens` and `--thinking-display` (757-775) | `max_thinking_tokens` 2350 is deprecated. |
| `betas` | `betas: list[SdkBeta]` 2079; only "context-1m-2025-08-07" | |
| `system_prompt` | `system_prompt` 1996: str, `SystemPromptPreset` (types.py:40-69), `SystemPromptCustom` (:72) or `SystemPromptFile` (:81). Flags `--system-prompt`, `--append-system-prompt` and `--system-prompt-file` (576-590) | `None` sends `--system-prompt ""` (576-577). |
| `exclude_dynamic_system_prompt_sections` | `SystemPromptPreset.exclude_dynamic_sections` (types.py:46), sent in initialize as `excludeDynamicSections` | Only with the preset form. |
| `system_prompt_snapshot` | `SystemPromptPreset.snapshot` (types.py:58), sent in initialize as `systemPromptSnapshot` | Only with the preset form. |
| `builtin_tools` | `tools: list[str] \| ToolsPreset \| None` 1974, flag `--tools` (592-601) | |
| `allowed_tools` / `disallowed_tools` | 1985 / 2063, flags `--allowedTools` / `--disallowedTools` (606-616) | `skills` can add allowed tools (`_apply_skills_defaults`, 602-604). |
| `permission_mode` | `permission_mode: PermissionMode` 2025, flag `--permission-mode` | All 6 values exist in the Literal. |
| `permission_prompts` (`host` / `none`) | `permission_prompt_tool_name` 2089, flag `--permission-prompt-tool` | `_configure_can_use_tool` sets it to "stdio" when `can_use_tool` is set (types.py:1926-1949). |
| `restricted` | None in Python options, and no `restricted` option in the TS `Options` grep | unverified: what it maps to. |
| `sandbox` | `sandbox: SandboxSettings` 2331 (types.py:904-950), merged into `--settings` (656-660) | `enabled` is documented "macOS/Linux only" (types.py:920); the TS docs disagree (§4.1 #9). |
| `can_use_tool` / `hooks` | 2158 / 2176, carried over the control protocol (hooks go in initialize) | Callbacks run in our process. |
| `tools` (Vidbyte `BaseTool`s) | an `mcp_servers` entry from `create_sdk_mcp_server` (§2.5.8) | |
| `mcp_servers` / `strict_mcp_config` | 2010 (dict, str or Path), flag `--mcp-config` / 2018, flag `--strict-mcp-config` | |
| `skills` | `skills: list[str] \| "all" \| None` 2309, sent in initialize | Changes allowed_tools and setting-sources defaults. |
| `plugins` (folder, zip or URL) | `plugins: list[SdkPluginConfig]` 2343; `SdkPluginConfig` is local-only (types.py:855-862), flag `--plugin-dir` | Non-local types raise `ValueError` (732-738). DTS:6023 mentions `--plugin-url`. |
| `agents` | `agents: dict[str, AgentDefinition]` 2291, sent in initialize ("No --agents CLI flag needed", 726-727) | `AgentDefinition` (types.py:107-126) has all 13 fields R3 lists. |
| `main_agent` (`--agent`) | None; TS has `agent?` (DTS:1565) | Only through `extra_args`. |
| `setting_sources` | 2297, flag `--setting-sources=` (729-730). `None` means "all sources are loaded"; `[]` disables them; "Must include "project" to load CLAUDE.md files" | |
| `settings` | `settings: str \| None` 2105 (a path or JSON), flag `--settings` | Merged with `sandbox`. |
| `bare` / `safe_mode` | None. DTS:4217 mentions `--bare` / `CLAUDE_CODE_SIMPLE`; DTS:4207 mentions `--safe-mode` | Only through `extra_args` or `env`. |
| `max_turns` | 2050, flag `--max-turns` **only if truthy** (610-611) | |
| `max_budget_usd` | 2056, flag `--max-budget-usd` (613-614) | |
| `task_budget` | `task_budget: TaskBudget` 2430, a TypedDict with `total` (types.py:88), flag `--task-budget` (619-620) | |
| `autocompact` | None. Autocompact appears only as reported context usage (`isAutoCompactEnabled`, types.py:815) and in the TS settings keys `autoCompactWindow` (DTS:79, 9084) | unverified: the control. |
| `max_output_tokens` | **None.** No env var or option in `SDK/` or the DTS. Only `ModelUsage.maxOutputTokens` (types.py:1328; DTS:1449) and the error kind `max_output_tokens` (DTS:3717) | The request says "verify the name"; it is unresolved. |
| `session_id` | 2043, flag `--session-id=` (648-652). "Must be a valid UUID. Cannot be used with `continue_conversation` or `resume` unless `fork_session` is also set." | |
| `name` | None | unverified: any CLI flag. |
| `resume` / `continue_conversation` / `fork_session` | 2040 → `--resume=` (644-646) / 2036 → `--continue` / 2249 → `--fork-session` | |
| `resume_session_at` / `resume_drops_turn` | 2253 → `--resume-session-at=` / 2265 → `--resume-drops-turn=` (708-721) | |
| `persist_session` | None. TS has `persistSession?` (DTS:1822); DTS:6822 mentions `--no-session-persistence` | Only through `extra_args`. |
| `enable_file_checkpointing` | 2395, sent as env `CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING` | |
| `session_store` | 2403, with `session_store_flush` 2411, flag `--session-mirror` (723-724) | Validated in client.py:99-117. |
| `worktree` | None; DTS:7262 mentions the CLI `--worktree` | Only through `extra_args`. |
| `output_schema` | `output_format: dict \| None` 2387, flag `--json-schema` (780-789) | |
| `include_partial_messages` / `include_hook_events` | 2192 / 2199, flags (694-698) | |
| `forward_subagent_text` | 2207, sent in initialize | |
| `prompt_suggestions` | None. TS has `promptSuggestions?` (DTS:2077); the env var `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION` is documented at DTS:2069-2073 | |
| `cli_path` | 2099: "Uses the bundled executable if not specified." | §4.1 #7. |
| `env` / `user` | 2124 / 2189 (`open_process(user=…)`) | |
| `load_timeout_ms` | 2421: the `session_store.load()` timeout (default 60_000) | §4.1 #6. |
| `timeout_seconds` | None; this is Vidbyte-side | |

Options the request does not name: `extra_args` (2139), `max_buffer_size` (2146), `debug_stderr` (2149), `stderr` (2152, a line callback that pipes stderr only when set, subprocess_cli.py:871) and `verbatim_prompts` (2219).

### 2.6 TypeScript SDK 0.3.296 `sdk.d.ts`: neighbour (third-party, read-only; grep only)

- `Options` (DTS:1526) contains `agent?` (:1565), `extraArgs?` (:1682), `persistSession?` (:1822), `pathToClaudeCodeExecutable?` (:1984) and `promptSuggestions?` (:2077).
- **Steering evidence:**
  - `SDKUserMessage.priority?: 'now' | 'next' | 'later'` (:6323, :6417);
  - the interrupt receipt's `still_queued` (:4657-4663) and the `cancel_queued` request flag (:4647-4649);
  - the result's `queued_turn_count?` (:5755, :5859);
  - `user_message_uuids?` (:5769), which folds queued messages into a turn.
- **Effort:** `effort` on `system/init` (:6033), and the `CLAUDE_CODE_EFFORT_LEVEL` clamp note (:9054).

## 3. Tests that cover those files

### 3.1 Framework and configuration

- **Runner:** pytest 8.3.5 with pytest-asyncio 1.3.0 (pyproject `dev` :45-52), configured at pyproject.toml:78-81. `--strict-markers` is on and there is no `asyncio_mode`.
- **Async tests:** 90 test files use `unittest.IsolatedAsyncioTestCase`, 18 use `asyncio.run(`, and 11 use `pytest.mark.asyncio`.
- **Layout:** flat `tests/test_*.py` (136 files) plus `tests/features/<feature>/`.
  - `tests/__init__.py` is 651 bytes and `tests/multi_agent/__init__.py` is 89 bytes.
  - The only conftest is `tests/features/coding_agent/conftest.py`.
  - No other test package exists, so a flat `tests/test_claude_*.py` needs no `__init__.py`.
- **A001 applies to test files** (all tracked `.py` files).
  - `tests/test_codex_tools.py` carries the full header.
  - `tests/test_durable_sessions.py` and `tests/test_fork_tool.py` do not; that is existing debt.
- **S062 also scans tests.** Ruff rules (S006, S045, S051 and the others) do not.

### 3.2 Test files that cover the touched code

| File | Lines | What it shows |
|---|---|---|
| `tests/test_codex_tools.py` | 683 | The model for vendor-SDK tests. Fakes `_FakeSyncClient` (:202), `_FakeThread` (:216) and `_FakeAsyncCodex` (:233); `_fake_sdk()` (:264-282) builds a `CodexSdkTypes`. `_run_transport` (:298-312) patches the one import seam with `mock.patch.object(CodexTransport, "_load_sdk", return_value=_fake_sdk(...))`; `_reset_fake` is at :315-319. Classes run from :322 to :641, using both `unittest.TestCase` and `IsolatedAsyncioTestCase`. The missing-extra path asserts `caught.exception.failure_code == FailureCode.CODEX_SDK_UNAVAILABLE.value` (:574, :615). Real-SDK contract tests sit behind `@unittest.skipUnless(importlib.util.find_spec("openai_codex"), "requires the optional openai-codex extra")` (:640-641). The file ends with `unittest.main()`. |
| `tests/test_codex_failure_recovery.py` | 725 | `_ScriptedTransport` (:140) is injected with `agent._transport = transport` (:185). `ClassificationCoverageTests` (:188-201) checks that every `"codex."` code has a classification row and that every row names a real code; a Claude classification table would need the same pair. |
| `tests/test_durable_sessions.py` | 1,790 | The session tools are imported at :58. `SessionToolTests` (:1380) calls `await tool.execute(ToolCall(tool_name=…, arguments=…))` and asserts `result.status.value == "error"` for bad input. |
| `tests/test_fork_tool.py` | 477 | `ForkTool` behaviour and scope; no A001 header. |
| `tests/test_session_failures.py` | 612 | `test_every_code_has_category_prefix` (:137-139) covers every `FailureCode`. |
| `tests/test_mcp_studio_server.py` | 376 | Serving SDK tools over MCP. |
| `tests/test_harness_execution.py` / `tests/test_harness_redaction.py` | 204 / 146 | The `vidbyte/harnesses/` package. |
| `tests/test_readme_size_limit.py` | 43 | A009. |
| Other Codex tests | | `test_codex_agent_input_bridge` 424, `test_codex_middleware` 492, `test_codex_output_contracts` 600, `test_codex_pipelines` 450 (asserts `CODEX_RUN_OPTION_UNSUPPORTED` at :275), `test_codex_usage_tracking` 361. |

There are no tests for `vidbyte/tools/toolsets/` other than through the coding-agent features under `tests/features/coding_agent/`.

### 3.3 Constraints on new tests

- **No extras in CI.** The source stage installs `.[dev]` only (ci.yml:36), and the package smoke installs no extras. Every module must import without `claude_agent_sdk` installed, and tests must fake the SDK at the single import seam. Contract tests that need the real package must skip when `importlib.util.find_spec("claude_agent_sdk")` is None.
- **No live calls.** "Automated tests make no live calls, and CI has no Anthropic credentials" (request.md:189).
- **Do not `import vidbyte` without `PYTHONPATH=$(pwd)`.** The global editable install resolves to the canonical checkout (FG/local-ci-verification.md).

### 3.4 Commands

| Purpose | Command |
|---|---|
| One file | `PYTHONPATH=$(pwd) python -m pytest tests/test_claude_<name>.py` |
| Area (new files plus neighbours) | `PYTHONPATH=$(pwd) python -m pytest tests/test_claude_*.py tests/test_session_failures.py tests/test_mcp_studio_server.py tests/test_codex_tools.py` |
| One rule while iterating | `python lint/run.py --rule A001` (or any rule ID) |
| Full gate | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` (AGENTS.md: `python scripts/run_ci.py`) |

## 4. Notes for the spec author

### 4.1 Contradictions ("request assumes X; code shows Y")

1. **The `native/__init__.py` contract bytes fail A001.** The request assumes the four contract bytes for `vidbyte/harnesses/native/__init__.py` (request.md:167-173) pass the gate. The code shows A001 requires the seven header fields in every tracked `.py` file (`lint/rules/a001_agent_readable_file_headers.py:24-32,69`, baseline 643), so the docstring adds one A001 finding and A001 REGRESSES unless slack exists (unverified). The same applies to any zero-byte test `__init__.py` (request.md:181), though flat tests need none. request.md:174 already says what to do: make the smallest passing change and record the final bytes under OPEN ITEMS.
2. **`MessageParseError` is not importable from the package root.** The request assumes `CLIJSONDecodeError` and `MessageParseError` map to `protocol_mismatch` (request.md:144). The code shows `MessageParseError` is not exported (`SDK/__init__.py:32-39`, `__all__` :622-772); it lives in `SDK/_errors.py:129`, a private module.
3. **`ProcessError` carries no stderr text.** The request assumes `ProcessError(exit_code, stderr)` gives a useful next step (request.md:139). The code shows stderr is the placeholder "Check stderr output for details" (`SDK/_internal/transport/subprocess_cli.py:1156-1162`). Real stderr arrives only through the `stderr` callback option (types.py:2152).
4. **Budget and turn caps do not raise `ResultError` during a turn.** The request assumes `ResultError` with subtype `error_max_budget_usd` or `error_max_turns` is how budget exhaustion is detected (request.md:140). The code shows that during a live `ClaudeSDKClient` turn it arrives as a `ResultMessage` with `is_error` and a `subtype` (`SDK/types.py:1340-1377`). `ResultError` replaces `ProcessError` only when the process then exits non-zero (`SDK/_internal/query.py:512-535`).
5. **`fallback_model` is a single model.** The request assumes an "ordered list" (request.md:102). The code shows `fallback_model: str | None` (`SDK/types.py:2076`) and one `--fallback-model` flag (`subprocess_cli.py:625-626`).
6. **`load_timeout_ms` is not a process timeout.** The request lists it under Process (request.md:118). The code shows it is the timeout for `session_store.load()` and `list_subkeys()` during resume (`SDK/types.py:2421-2428`), unrelated to starting the CLI.
7. **`cli_path` must be passed explicitly.** The request assumes `cli_path` defaults to the installed `claude` (request.md:153). The code shows `_find_cli()` checks the bundled 2.1.294 CLI **first** (`subprocess_cli.py:258-260`) whenever `cli_path` is None (types.py:2099-2103). Three related facts:
   - the installed file is `C:/Users/422mi/.local/bin/claude.exe`;
   - the SDK's own version check only warns (`subprocess_cli.py:1164-1224`);
   - `claude_code_version` in the initialize response is optional (DTS:4623), while the `system/init` message carries it as required (DTS:5983) but only once a turn starts.
8. **Plugins are folders only.** The request assumes plugins accept a folder, zip or URL (request.md:111). The code shows `SdkPluginConfig` is local-only (`SDK/types.py:855-862`) and other types raise `ValueError` (`subprocess_cli.py:732-738`).
9. **The two SDKs disagree on whether sandbox works on Windows.** The request includes `sandbox` (request.md:107), and the user is on Windows.
   - The Python docstring says `SandboxSettings` is "macOS/Linux only" (`SDK/types.py:920`).
   - The TS settings describe native-Windows sandbox behaviour (DTS:8813): "on native Windows … the sandboxed process runs as a separate user … filesystem isolation stays on there".
   - unverified: which is true for CLI 2.1.296.
10. **No `max_output_tokens` control exists.** The request assumes an env var for max output tokens exists (request.md:115,133). The code shows none in `SDK/` or the DTS (grep for `max_output|MAX_OUTPUT|maxOutput`). Only `ModelUsage.maxOutputTokens` (types.py:1328) and the error kind `max_output_tokens` (DTS:3717) appear.
11. **`None` from `get_session_info()` does not always mean not found.** The request assumes `None` means `session_not_found` (request.md:146). The code shows it also returns `None` for an invalid UUID, a sidechain session, or a session with no summary (`SDK/_internal/sessions.py:739-818`). `get_session_messages` returns `[]` when not found (:1059-1110). `fork_session` raises builtin `ValueError` and `FileNotFoundError` (`SDK/_internal/session_mutations.py:294-308`).
12. **The "append-only" export lists are sorted by tooling.** The request assumes these files are append-only (request.md:183). The code shows:
    - imports in every `__init__.py` must stay in I001 sorted position (S051, `lint/core/ruff.py:31`). For example, a `…enums.claude` import belongs between :40 (`agent_runtime`) and :41 (`codex`) of `vidbyte/lib/enums/__init__.py`.
    - `vidbyte/lib/enums/__init__.py` `__all__` is alphabetical by convention (:142-235), though RUF022 is not enforced.
    - `contracts/sdk-public-api.json` exports **must** be sorted (`lint/core/public_api_contract.py:87`) and are generator output, so new names land in sorted position, not at the end.
    - The root `vidbyte/__init__.py` `__all__` is grouped, not sorted (:716 vs :999).
13. **The MCP server does not enforce permissions.** The request assumes WRITE tools are gated by `PermissionPolicy` (request.md:149). The code shows that is true inside agents (`vidbyte/tools/executor.py:41,53`), but `StudioToolRegistry.execute` runs `tool.execute(ToolCall(name, arguments))` with no policy (`vidbyte/mcp_server/handlers.py:84-88`). Serving the toolset over MCP (request.md:124) therefore exposes WRITE (spending) tools ungated.
14. **Per-agent binding may require a file outside the contract.** The request assumes "Tools hold one `ClaudeHost` per agent, the same way `_SessionBuiltinTool` holds a session store" (request.md:130) and lists the shared files. The code shows per-agent binding and copying are hard-coded class lists in `vidbyte/agents/base.py:421-482`. A tool type absent from those lists is shared as-is between agents. `agents/base.py` is not in the shared-file contract.
    - `_bind_session_tool` (:484-490) calls any `bind_session` attribute with the agent's Vidbyte `Session`, so a Claude tool must not reuse that name for a different meaning.
15. **Importing ClaudeHost from the tools package risks a circular import.** The request assumes tools in `vidbyte/tools/builtins/claude/` can import ClaudeHost from `vidbyte/harnesses/native/claude/` (request.md:120-123). The code shows this import chain:
    1. `vidbyte/tools/builtins/__init__.py` loads during `import vidbyte.agents` (via `vidbyte/agents/runtime.py:151`);
    2. importing `vidbyte.harnesses.native…` runs `vidbyte/harnesses/__init__.py:60`, which imports `execution`;
    3. `vidbyte/harnesses/execution.py:69` imports `vidbyte.sessions.session`;
    4. `vidbyte/sessions/session.py:25` imports `vidbyte.agents.types`.
    unverified: whether this raises at import time. A006 also flags concrete import cycles.
16. **The session tools' error pattern is S017 debt.** The request assumes copying the session tools' layout (request.md:122). The code shows `_caught` (`vidbyte/tools/builtins/sessions/_base.py:85-90`) returns raw exception text, which is S017 debt (baseline 79). `descriptions.py` uses adjacent string literals (S062) and has no A001 header. The modules use the "Context Protocol Header" docstring, which lacks `ROLE IN CODEBASE:` (A001).
17. **R3's `wait_claude_turn(handle, timeout)` trips S045.** That signature (request.md:95) as an `async def` with a parameter named `timeout` is ruff ASYNC109, i.e. S045 (baseline 2). unverified: whether ruff also flags names like `timeout_seconds`.
18. **Steering has no queue control in Python.** The request assumes it must verify whether a mid-turn `query()` queues or interrupts (request.md:96,235). The code shows Python `query()` writes a user line with no turn check and no priority (`SDK/client.py:272-306`). The CLI side queues messages: the DTS has `priority 'now'|'next'|'later'` (:6323), the interrupt receipt `still_queued` (:4657-4663), and the result `queued_turn_count` (:5755). The Python parser drops `queued_turn_count` (`message_parser.py:308-341`). unverified: the live behaviour on 2.1.296.
19. **Assistant error kinds are not a closed set.** The request assumes the kinds `authentication_failed`, `billing_error` and `rate_limit` map to codes (request.md:143). The code shows Python's Literal has 6 values (`SDK/types.py:1037-1044`) but the parser passes the raw string through (`message_parser.py:151-224`), and the CLI defines 13 (DTS:3717).
20. **Rate-limit data is narrower than the request assumes.** The request assumes five-hour, seven-day and per-model windows with utilization and overage (request.md:88). The code shows each `RateLimitEvent` carries **one** `RateLimitInfo` window (`SDK/types.py:1397-1435`), emitted only when the status changes, and only on a live session's stream.
21. **Usage is split across three sources.** The request assumes usage "per model" with web searches (request.md:98). The code shows:
    - per-model figures are in `ResultMessage.model_usage` as camelCase dicts (`ModelUsage`, types.py:1314-1336, which includes `webSearchRequests` and `costUSD`);
    - `ResultMessage.usage` is an untyped dict;
    - `TaskUsage` (:1161-1166) is per background task, not per session.
22. **`CodexFailureClass` is not exported.** The request assumes enums export cleanly (AGENTS.md:61). The code shows the Codex precedent does not export `CodexFailureClass` (`vidbyte/lib/enums/codex.py:82` is missing from `vidbyte/lib/enums/__init__.py:41-51`); do not copy that.
23. **The Codex records module is too large to copy wholesale.** The request assumes `vidbyte/lib/dataclasses/codex.py` as the pattern (request.md:215). The code shows it is 1,205 lines (AGENTS.md:31 says "well below 1,000"), and its validators are C008 debt (:55-79).
24. **`system_prompt=None` sends an empty prompt.** The request lists the preset as the "keep" option (request.md:103). The code shows an unset `system_prompt` sends `--system-prompt ""` (`subprocess_cli.py:576-577`), which is not Claude Code's default prompt. The preset must be passed explicitly.
25. **`session_id` has constraints.** The request lists `session_id` as "choose it up front" (request.md:116). The code shows "Must be a valid UUID. Cannot be used with `continue_conversation` or `resume` unless `fork_session` is also set." (`SDK/types.py:2043-2048`).
26. **Control failures are untyped.** The request assumes every failure maps to a typed SDK error. The code shows control-protocol failures and timeouts raise a bare `Exception` (`SDK/_internal/query.py:403-406,748-751`), for example from `interrupt()` and `initialize`.
27. **The SDK extra is heavy and imports eagerly.** The request assumes a light optional extra (request.md:125). The code shows the extra pulls `mcp`, `anyio` and `jsonschema` (vendor pyproject :27-33), and `SDK/__init__.py:28-30` imports `mcp.types` at import time.
28. **Fork lineage depends on R2's `hosts.py`.** The request quotes R2's claim that "Native" matches how `hosts.py` describes Codex and Claude (request.md:278). The code shows no `hosts.py` in this repo (`git ls-files`); the only "host" file is `lint/rules/c018_canonical_api_host.py`. unverified: which repo it lives in.
29. **Live sessions cannot outlive a sync `agent.run()`.** The request assumes spawn returns a handle and the session keeps running for a later `wait_claude_turn` (request.md:131). Two facts constrain this:
    - `BaseAgent.run()` runs each call in a fresh loop via `asyncio.run` and tears down agent-owned subprocesses before the loop closes (`vidbyte/agents/base.py:1024`; `vidbyte/agents/mixins.py:242-257`);
    - a `ClaudeSDKClient` cannot be used across async contexts (`SDK/client.py:58-64`).
    So a handle cannot survive from one sync `agent.run()` call to the next.
30. **A runtime timeout can orphan a `claude` process.** The request assumes tool calls can wait on turns. The code shows the runtime may wrap any tool call in `asyncio.wait_for(tool.execute(call), timeout=...)` (`vidbyte/agents/runtime.py:1448-1460`). The vendor warns that a raw asyncio cancellation, including `wait_for` firing or loop shutdown, can skip close-escalation and orphan the child (`subprocess_cli.py:978-987`).
31. **History functions block the event loop.** The request assumes history functions are "offline and instant" (request.md:128). The code shows they are synchronous file readers that may run `git worktree list` with a 5 s timeout (`SDK/_internal/sessions.py:388-413`), and `list_sessions` reads stat plus the head and tail of each file (:680-731). Called from `async def` tools, they block the loop. Ruff will not flag it, because it is third-party code.
32. **A shared-file contract line has no consumer.** request.md:183 lists `vidbyte/harnesses/README.md` and `REPO_MAP.md` as append-only indexes. The code shows the README has no File Index and REPO_MAP has no entry for `vidbyte/agents/codex/` today. Both PRs will add new prose rather than extend a list. The toolsets entry (REPO_MAP.md:335-337) is already stale.

### 4.2 Facts bearing on the request's open questions (request.md:234-246)

- **Steering:** see #18. Python cannot set `priority`. Whether the CLI queues a mid-turn user line in SDK mode is unverified.
- **Output-token cap:** see #10. Nothing was found.
- **`initialize` contents:** yes. `get_server_info()` returns the raw initialize dict (`SDK/client.py:540-564`), which by the DTS contains `models`, `account` and an optional `claude_code_version`. Both require a connected process (a live `claude` subprocess).
- **Readiness:**
  - `CLINotFoundError` comes from `connect()` (`subprocess_cli.py:901-911`).
  - The version is available from initialize (optional) or the `system/init` message (required, after a turn starts).
  - "Signed in" has no boolean: `AccountInfo` fields are all optional (DTS:23-34).
  - `claude auth status` exists only per R3 (unverified; not run).
- **Rate limits before any event:** no Python API reads them on demand (§2.5.6). `get_usage` is ⚑.
- **Concurrency cap:** no measured memory per process exists. The binary is 260,489,376 bytes on disk. The Codex precedent caps turns with a `Semaphore` (`vidbyte/agents/codex/agent.py:86`).
- **Version pin:** Codex pins `>=0.162.1,<0.163.0` (pyproject.toml:42-44). runtime-primitives SKILL.md:41 says to pin pre-1.0 SDKs to "a reviewed compatibility range".
- **Busy sessions:** the host's own registry is the only source. The SDK has no lock for this (`fork_session` uses `O_EXCL` only for the new file), and `asyncio.Lock` is banned (S039).
- **Tool binding and cleanup:** see #14 and #29. The precedent for agent-owned subprocess cleanup is `close_mcp_servers()` (`vidbyte/agents/mixins.py:280-293`, also called from `__aexit__` :375-376).
- **MCP:** no new code is needed to serve tools (`vidbyte/mcp_server/server/core.py:81`), but see #13.
- **Root export:** every root export changes the generated contract (C016). The CodexHost PR will regenerate the same file.
- **CI install:** CI installs `.[dev]` only (ci.yml:36,57), and the package smoke installs no extras (`scripts/run_ci.py:180-218`). Tests must fake the SDK at one import seam, as `tests/test_codex_tools.py:298-312` does.

### 4.3 Unverified

- unverified: lint slack per rule today (lint was not run). This decides whether one A001 finding from the contract bytes regresses the gate.
- unverified: whether ruff ASYNC109 matches parameter names other than `timeout`.
- unverified: whether the `tools.builtins.claude` → `harnesses.native.claude` → `harnesses/__init__` → `sessions` → `agents` chain raises at import time (#15).
- unverified: the CLI flags for `files` (`--file`), `name`, `restricted` and `autocompact`. `claude --help` was not run, and only R3 asserts them.
- unverified: the live mid-turn `query()` behaviour, and initialize contents on CLI 2.1.296. Nothing was executed.
- unverified: cross-task use of one `ClaudeSDKClient`, given the docstring caveat (client.py:58-64) against the anyio task-group internals (`SDK/_internal/_task_compat.py:7-12,147-159`).
- unverified: memory per `claude` process.
- unverified: whether each constant in `vidbyte/tools/builtins/sessions/descriptions.py` counts as an S062 finding. The S062 rule body was read only through its header and line :69.
- Verified, not open: `vidbyte/lib/dataclasses/validation.py`, C008's canonical module, does not exist (`ls` and `git ls-files` both find nothing). A validator named verb + primitive has no compliant home until one is created.
