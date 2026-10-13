# Code map: native Grok, opencode and Muse hosts plus GLM/DeepSeek backend profiles

Scout S0. Base commit `aa8c380c4cd1d5791526dd545f5ef1020b28a5cc` (HEAD of the worktree, "fix(filesystem): refuse to copy a directory into itself (#1000)").
Every `path:line` below was opened in this session. Anything not checked says "unverified".
Nothing under `docs/` was read except `docs/spec/native-grok-opencode-meta-hosts/request.md`.

---

## 1. Rules, commands, and conventions that bind this change

`CLAUDE.md` is one line, `@AGENTS.md`. `AGENTS.md` is 81 lines.

### 1.1 AGENTS.md rules, quoted under their headings

**## Repository Map**
- AGENTS.md:9 says to read REPO_MAP.md "before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs."
- AGENTS.md:11: "Each folder's own `README.md` documents that folder in more depth, so read it to the end before you change anything inside the folder. Its closing `## Notes for agents` section, where one exists, records mistakes that review has already caught there". The same line says lint rule A009 caps every folder README at 40,000 characters.
- AGENTS.md:13: "**Do not grep, glob, or read files under `docs/` as part of ordinary work** … Before treating a change as complete, run the full local gate, `python scripts/run_ci.py`; none of the narrow verification scripts beside it substitutes for it."
- AGENTS.md:15: "The Placement Rules … [are] binding for all new code, and the `AGENTS.md placement` workflow enforces it on every pull request by moving misplaced code to the location it names."

**## General Coding Style Guidelines**
- **### 1. Keep Call Chains One Level Deep** (AGENTS.md:23): "a function may call another of its own functions, but that second function should not call a third … Calls out to another class, a lower layer, or the standard library do not count toward this limit. Avoid defining functions inside other functions as well, unless an API requires a callback or a decorator."
- **### 2. Narrate Main Functions in Plain English** (AGENTS.md:27): "Inside that function, place short plain-English comments throughout the body, so that a reader can follow the whole feature by reading only the comments."
- **### 3. Build in Layers of Small, Single-Purpose Classes** (AGENTS.md:31):
  - "`vidbyte/lib/` is the bottom layer, domain packages such as `agents/`, `tools/`, and `context/` build on it, and composition layers such as `pipelines/` and `paradigms/` build on those".
  - "no two modules depend on each other in a cycle".
  - "Keep files well below 1,000 lines".
- **### 4. Use Validated Dataclasses for Core Inputs and Outputs** (AGENTS.md:35):
  - "Functions that carry core business logic take a dataclass as input and return a dataclass as output".
  - "Prefer `@dataclass(frozen=True, slots=True)` … type any field whose value comes from a small, closed set as an enum."
- **### 5. Write Shared Logic Once, as a Canonical Helper in `lib/`** (AGENTS.md:39-41):
  - "`HttpTransport` in `vidbyte/lib/http/transport.py` already follows this pattern".
  - "look in `vidbyte/lib/` for a helper that already does it, and if one is close, add the option you need to it rather than copying it into a variant beside your feature."

**## Placement Rules**
- **### Dataclasses go in `vidbyte/lib/dataclasses/`** (AGENTS.md:47-57):
  - "**Every new dataclass is defined in `vidbyte/lib/dataclasses/<domain>.py`** … whether it is public or underscore-prefixed."
  - "Do not create `types.py`, `records.py`, `models.py`, or `schemas.py` modules next to the code that uses the dataclass."
  - "`vidbyte/lib/` must never import from a layer above it … move the contract down (a `Protocol` or a smaller record in `vidbyte/lib/`)."
  - There are exactly two exceptions: agent `*Settings` classes and JEV preflight questions.
- **### Enums go in `vidbyte/lib/enums/`** (AGENTS.md:61-63):
  - "**Every new enum … is defined in `vidbyte/lib/enums/<domain>.py`**, and every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`. There are no exceptions."
  - "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."
- **### Existing code** (AGENTS.md:81): "Many modules on `main` still define dataclasses or enums outside these two folders … Do not copy them as precedent." Examples of such modules are `ToolPermission` at `vidbyte/lib/dataclasses/tools.py:47` and `HarnessRunStatus` at `vidbyte/lib/dataclasses/harnesses.py:55`.

**Commit and PR conventions.** AGENTS.md states none. request.md adds the rest:
- Draft PR only. Never merge and never mark it ready.
- Never rebase after the first push, and never force-push (request.md:164; draft-only at request.md:228).

### 1.2 Commands (all verified in source)

| Purpose | Command | Evidence |
|---|---|---|
| Install (once) | `python -m pip install -e ".[dev]"` | `.github/workflows/ci.yml`; dev pins in `pyproject.toml` (pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, mypy 2.3.1) |
| Lint, all rules | `python lint/run.py`. The last line is `SDK-LINT: PASS` or `SDK-LINT: FAIL` | `lint/core/report.py:58` |
| Lint, one rule | `python lint/run.py --rule <ID>` | `lint/run.py:36` |
| Lint, every finding / JSON | `python lint/run.py --all`, `python lint/run.py --format json` | `lint/run.py:37-38` |
| Import order (S051) over the whole tree | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | field guide `local-ci-verification.md` |
| Test, one file | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>/test_<x>.py` | pattern at `tests/features/coding_agent/test_bash_tool_process_bounds.py:11` |
| Test, one area | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/<pack>` | `tests/features/coding_agent/conftest.py:11` |
| Test, all | `PYTHONPATH=$(pwd) python -m pytest` (testpaths=`["tests"]`, `--strict-config --strict-markers`) | `pyproject.toml [tool.pytest.ini_options]` |
| Source gate (from a worktree) | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | `scripts/run_ci.py:79-93`; field guide `local-ci-verification.md` |
| Package gate | `python scripts/run_ci.py --stage package` with **no** PYTHONPATH (run_ci pops it at `scripts/run_ci.py:226`) | same |
| Full gate | `python scripts/run_ci.py` (default `--stage all`) | `scripts/run_ci.py:260-265`, AGENTS.md:13 |
| Static policy (Semgrep; **not** part of run_ci) | `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1) | `.github/workflows/static-policy.yml`; field guide `local-ci-verification.md` |
| Public-API contract | `python scripts/generate-sdk-public-api.py --check`, and the same command without `--check` to regenerate after committing the source change | `scripts/generate-sdk-public-api.py:12-13`, `contracts/README.md` |

**What the source stage runs**, in order (`scripts/run_ci.py:79-93`):
1. Check that no bytecode is tracked.
2. `lint/run.py`.
3. `compileall vidbyte`.
4. `check_context_write_paths.py`, `check_context_primitive_introductions.py` and `check_reasoning_trace_contracts.py`.
5. `python -m pytest`.

The CI workflow `ci.yml` runs only on manual dispatch (workflow_dispatch), on Python 3.11 and 3.12.

**Lint is a count ratchet against `lint/baseline.json`.**
- One new finding over the baseline count fails the gate. Never raise a baseline number.
- The catalog reads `git ls-files` (`lint/core/discovery.py:5,81`), so an untracked new file is not linted at all.
- `python_files()` covers `vidbyte/**.py` only (`lint/core/discovery.py:56`). `all_python_files()`, which A001 uses, also covers tests.

### 1.3 Lint rules that new code will hit

Baseline counts are taken from `lint/baseline.json`.

| Rule (baseline) | What it demands, with evidence |
|---|---|
| **A001** (643) | **Header.** Every tracked `.py` (tests included) starts with a docstring holding non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:` and `TESTS:` (`lint/rules/a001_agent_readable_file_headers.py:23-31`). The regex is `(?im)^\s*FIELD\s*(\S.*)$` (`:53`) and it scans the first 80 lines (`:22`). The "Context Protocol Header" style (`vidbyte/__init__.py:1`, `vidbyte/tools/builtins/__init__.py:1`, `vidbyte/tools/builtins/sessions/checkpoint.py:1`, `vidbyte/tools/mcp/transport.py:1`) fails A001 and is baseline debt. The fixed bytes for `native/__init__.py` (request.md:175-186) carry all 7 fields. |
| **A002** (703) | **Intent comments.** A function whose name or identifiers contain retry, backoff, attempt, permission, authorize, pricing, price, billing, redact, secret, persist(ence), checkpoint, fallback, transition, transport, request, fetch, send, urlopen, provider, subprocess or mcp needs `# @intent <name>` within 20 lines (`lint/rules/a002_intent_comments.py:23-49`). "spawn request", `asyncio.subprocess` and `list_opencode_providers` all match. |
| **A003** (36) | **Error diagnostics.** A new class ending in `Error` under `vidbyte/lib/errors/` needs the literal `DIAGNOSTIC_FIELDS` 8-tuple (`lint/rules/a003_context_rich_error_packets.py:22,121`). Precedent: `CodexAgentError` at `vidbyte/lib/errors/base.py:129-153`. Errors under `vidbyte/harnesses/` are outside A003's scope. |
| **A005** (33) | **Typed seams.** Parameters named transport, runner, store, client, tracer or fetcher must not be typed `object` or `Any`. |
| **A006** (34) | **Layers.** Only lower layers (`vidbyte.lib/providers/sessions/sources`) importing orchestration or application modules are flagged, plus concrete cycles. `__init__.py` edges are excluded and `TYPE_CHECKING` edges are skipped (`lint/rules/a006_directed_dependency_graph.py:23-36,65-67,79-85`). So `vidbyte.harnesses.*` → `vidbyte.tools.mcp.transport` and `vidbyte.tools.builtins.*` → `vidbyte.harnesses.native.*` are allowed if they form no cycle. Today `vidbyte/harnesses/` imports only `vidbyte.lib`, `vidbyte.sessions` and itself (checked with `git grep`). |
| **A007** (255) | **Named constants.** A numeric literal near timeout, retry, attempt, backoff, delay, token, char, byte, truncate, limit, budget, status, depth or interval, or passed to sleep, urlopen, send, request, read or read_bytes, must be an UPPERCASE constant. Parameter defaults count (`lint/rules/a007_operational_constants.py:23-39`). Never write `read(CAP+1)`. |
| **A008** (3) | No `print()` outside `vidbyte/cli/`. |
| **S008** (19) | **Complexity.** Ruff C901, PLR0912 and PLR0915, at defaults of complexity 10, 12 branches and 50 statements. |
| **S011** (0) | **HTTP clients.** Importing `http.client`, `httpx`, `requests` or `urllib.request` is forbidden in `vidbyte/` except `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py` (`lint/rules/s011_raw_http_client_ownership.py:22-23`). |
| **S012** (0) | **Timeouts.** Any call to a method named `request`, `request_bytes`, `stream_request`, `upload_multipart` or `urlopen` needs a `timeout=` or `timeout_seconds=` keyword. The only exempt file is `vidbyte/tools/mcp/client.py` (`lint/rules/s012_explicit_outbound_timeout.py:21-23,36`). Do not name a non-HTTP helper `request`. |
| **S013** (n/a) | **Response bounds.** Requires `max_response_bytes`, but only under `tools/builtins/{code_search,mcp,operations}/` and `tools/mcp/` (`lint/rules/s013_bounded_untrusted_responses.py:22`). New `tools/builtins/<host>/` folders are not scoped. |
| **S015** (13) | **Exports.** `__all__` must be a literal, unique and bound. The root `vidbyte/__init__.py` must list every public import. |
| **S016** (50) | **Typed raises.** No `raise Exception/RuntimeError/TypeError/ValueError` under `providers/`, `tools/mcp/`, `tools/builtins/`, `lib/runners/` and `cli/` (`lint/rules/s016_typed_boundary_errors.py:22`). Harnesses are not scoped. |
| **S017** (79) | **No raw exception text.** No `str(exc)`, `repr(exc)` or `f"{exc}"` flowing into errors or error results under `providers/`, `tools/`, `mcp_server/` and `lib/runners/` (`lint/rules/s017_no_raw_exception_disclosure.py:22`). Harnesses are not scoped by the lint, but request.md:793 requires the same. |
| **S019** (5) | **Cancellation.** In async code, `except CancelledError`, `except BaseException` or a bare `except` must re-raise. |
| **S020** (1) | **File Index parity.** A README containing `## File Index` lists every tracked direct child with suffix .json, .md, .py, .toml, .txt, .yaml or .yml. This applies to test packs (`tests/features/coding_agent/README.md:15`) and to `vidbyte/agents/codex/README.md:1103`. |
| **S024** (25) | Control-flow nesting at most 3 levels. |
| **S025** (263) | **Description depth.** Each `ToolSpec` description and each `ToolParameter` description inside a BaseTool subclass's own `spec()` needs at least 4 sentences when statically resolvable. Constants are followed for up to 3 import hops. Descriptions inside an `input_schema` dict are not checked. |
| **S039** (5) | **Banned APIs.** `lint/ruff.toml` bans `typing.TypedDict`, `typing.assert_never` and **`asyncio.Lock`** ("Use the SDK-owned concurrency boundary"). The precedent is `asyncio.Semaphore(CODEX_MAX_CONCURRENT_TURNS)` at `vidbyte/agents/codex/agent.py:82-86`. |
| **S045** (2) | An async def with a parameter named `timeout` is flagged (Ruff ASYNC109). |
| **S051** (259) | Ruff I001, UP006, UP007, UP035 and UP045. |
| **S052** (0) | Blocking subprocess calls in async code (Ruff ASYNC220/221 and others). |
| **S054** (3) | **Bandit S105-S108.** A name matching password, pass, pwd, token or secret that is assigned a string literal can trip S105. A constant such as `X_AUTH_TOKEN_ENV = "ANTHROPIC_AUTH_TOKEN"` is a risk; that Ruff behaviour is unverified. |
| **S055** (0) | No `shell=True`, `os.system` or `create_subprocess_shell`. Use `asyncio.create_subprocess_exec` (`vidbyte/tools/mcp/transport.py:202`, `vidbyte/tools/builtins/bash.py:159`). |
| **S060** (32) | No `dict[str, Any]` in public signatures under `vidbyte/lib/dataclasses/` and `vidbyte/sessions/` (`lint/rules/s060_typed_public_seam_mappings.py:24`). |
| **S061** (6) | `open(path)` and `read_text`, `write_text`, `read_bytes` and similar with a non-literal path are flagged (relevant to reading `~/.grok/sessions/...`). |
| **S062** (889) | No implicit adjacent string concatenation, in any `.py` including tests. `vidbyte/tools/builtins/sessions/descriptions.py` is debt; do not copy it. |
| **S063** (4) | Results of `gather(..., return_exceptions=True)` must each be checked against `BaseException`, or carry an `# @intent`. |
| **S064** (4) | A retry or poll loop that sleeps must compare against a clock-derived overall deadline, or sit inside a timeout block (`lint/rules/s064_retry_overall_deadline.py:3-5`). |
| **S009** (350) | **mypy ratchet.** `python -m mypy --config-file lint/mypy.ini vidbyte` with `disallow_any_generics = True` and `check_untyped_defs = True` (`lint/mypy.ini`). A bare `dict` or `Mapping` is an error. |
| **C002** (9) | **Duplicate bool guards.** Two `isinstance(<name>, bool)` checks on the same non-generic name anywhere in the package make every site a finding. Names already guarded include timeout_seconds, max_attempts, fresh_fork, limit, seconds, index, exit_code, cost_usd, strict, version, completed, concurrency and position. |
| **C006** (104) | Numeric range guards reject bool, NaN and ±inf first. |
| **C007** (16) | A bool field on `*Settings`, `*Config`, `*Configuration`, `*Policy` or `*Options` must be proved by `isinstance(x, bool)` or by a `_require_*_bool` / `_validate_*_flag`-style validator. |
| **C008** (45) | A function named verb + primitive (require, validate, ensure, normalize, coerce, check, resolve or is, followed by positive, non_negative, finite, bool, int, number, float, timeout, latency, limit, budget, temperature or probability) that performs the check itself is flagged outside `vidbyte/lib/dataclasses/validation.py`, which does not exist yet. Do not copy `_require_bool` and `_require_non_negative_int` from `vidbyte/lib/dataclasses/codex.py`. |
| **C012** (24) | **Model fields.** A field named `provider`, `*_provider`, `model`, `model_name`, `models`, `*_model` or `*_model_name`, typed str, on a class ending Settings, Config, Configuration, Spec, Descriptor or Options (or a record one embeds), must be proved at construction by `ModelProvider(...)` or a `ProviderModelRegistry` validation call (`lint/rules/c012_provider_model_registry_validation.py:24-31,180-188`). Exemptions are per-field entries in `_EXEMPT_FIELDS` inside the rule file (`:33-46`). |
| **C015** (3) | **Wheel contents.** Every non-README file under `vidbyte/` must ship in the wheel. Package data only covers prompts and paradigms (`pyproject.toml [tool.setuptools.package-data]`), and `pyproject.toml` is reserved (request.md:202). A vendored JSON or schema file under `vidbyte/` would fail. |
| **C016** (0) | **Public API contract.** `contracts/sdk-public-api.json` must equal the generator's output for `vidbyte.__all__`. |
| **Semgrep `typed-mapping-boundary-policy`** | **No silent fallback.** Under `vidbyte/**`, a function whose parameter is `object` or `Any` and which does `if not isinstance(x, Mapping/dict): return …` is forbidden. Excluded paths: `lib/http`, `providers`, `mcp_server` and `tools/mcp`. `vidbyte/harnesses/native/**` and `vidbyte/tools/builtins/**` are not excluded. |

### 1.4 Field guide (binding preferences, trigger then preferred action)

All entries are in `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`.

- **cli-backed-source-integrations.md**
  - **When:** "a source provider ships a mature CLI".
  - **Do:** "keep provider-specific command construction in the provider adapter and centralize process execution in one library runner. The runner should own executable allowlisting, argument validation, timeout and output bounds, environment-based credential injection, cancellation, and safe error classification."
  - **Also:** "Do not expose arbitrary URLs or command strings to model-facing inputs."
  - **Tool wrappers:** "Keep tool wrappers thin: validate their scoped inputs, call the provider adapter, clip untrusted output by UTF-8 byte size, and return stable result metadata including the transport used."
- **strict-config-dataclasses.md**
  - **Settings constructors.** When defining a settings or config constructor, do "Define a `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/` that owns every validation rule in its own `__post_init__`", and "Avoid union ('or') fields on the dataclass".
  - **Bounds.** When "a strictly validated dataclass has multiple field-size, count, or numeric bounds", do "Define named feature-prefixed constants in `vidbyte/lib/constants/`".
  - **Harness bridge inputs.** When "A harness adapter function accepts a raw SDK object, event loop, or `Mapping[str, Any]`", do "Define a frozen, slotted record in `vidbyte/lib/dataclasses/<provider>.py` … Signatures the provider SDK dictates … convert to the record as their first step".
  - **Native forks.** When "A harness fork inherits context … while permitting child overrides", do "Resolve overrides … before the provider fork call … Return the child only after a provider-confirmed thread identity". The check is: "An invalid child schema makes zero native fork calls".
  - **Size caps.** When choosing a size bound for data sent to a vendor, do "Derive counts from the documented vendor limit … Set character caps at or near the existing broad caps".
  - **Keys.** From the BaseAgent-subclass entry: "Mark key fields `repr=False`."
- **class-bound-helpers.md**
  - **Helper modules.** When a module exports several related free functions, do "Put the public surface and private helpers on one class as `@staticmethod` methods".
  - **Harness translation.** When a harness adapter calls a provider SDK, do "Use a constructor-time Vidbyte translator … a separate content translator for SDK arguments, and operation collaborators for lifecycle work. Keep request/result records in `vidbyte/lib/dataclasses/`."
  - **Server requests.** When a bridge "answers provider-initiated requests", do "Parse the raw params into a lib record that mirrors the provider's wire schema field for field, and answer failures in the provider's response shape directly."
  - **Must-not-raise callbacks.** When a callback must not raise, do "One `try` covers reading the request, scheduling the coroutine, and waiting; typed `except` clauses … a single `finally` cancels the future".
- **model-facing-tool-contracts.md**
  - **Tool schemas.** When adding a model-callable builtin, do "Use 6–9 meaningful fields per event, give the tool and every parameter a consistent 4–5 sentence general description, and omit concrete examples".
  - **Categorical parameters.** When adding them, do "Define the canonical values as `str, Enum` classes under `vidbyte/lib/enums`; derive parser choices from those members (`EnumClass.values()`)".
- **provider-api-contracts.md**
  - **Vendor fidelity.** When adding provider records, do "Download the vendor's own `api.md`/`models.md` … check every field type".
  - **Provider calls.** When writing a provider adapter's public call, do "Wrap config resolution, send, parse, and normalize in one `try` … Rewrite `ProviderRequestError` per documented status (401/422/429/5xx/none) … wrap any other `Exception` as `ProviderResponseError`. Never catch `BaseException`".
- **comment-format.md**
  - **When:** writing any multi-line `#` comment.
  - **Do:** "Wrap every comment line at 72 columns … Put each block directly above the code it explains … Keep `# @intent <name>` on its own first line."
- **blocking-lint-invariants.md**
  - **Errors.** For A003 on new `lib/errors` classes, give the full `DIAGNOSTIC_FIELDS`.
  - **Wire encoders.** "Lib records can't expose a `dict[str, Any]` wire encoder" (S060), and "`typing.TypedDict` is banned" (S039).
  - **Naming.** "S012 flags any method named `request` … Give it a descriptive name".
  - **Higher-layer fields.** For a lib record holding a higher-layer object, "Annotate the field under `TYPE_CHECKING`. Validate the surface the consumer uses".
  - **Status flags.** For C002, "Drop the stored bool and expose it as a `@property`".
  - **Capped reads.** For A007, "size a capped file read with `os.fstat`".
- **declarative-config-resolution.md**
  - **Registries.** For a name to class lookup, "Add one module [under `vidbyte/lib/registries/`] following `runtimes.py`'s shape: classmethods, lazy in-method imports …, `ConfigurationError` naming the available names."
  - **Capability tables.** For per-provider capability tables, "Put fixed declarations … in `vidbyte/lib/configs/`".
- **review-scope.md**
  - When told "belongs in another PR", leave main's files byte-identical.
  - When told "overcomplicated", rebuild from `origin/main`.
- **local-ci-verification.md**
  - Run the source stage with `PYTHONPATH=$(pwd)` and the package stage without it.
  - `git add -A` before Semgrep.
  - `test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` is flaky on Python 3.11.
  - Stage merge resolutions before linting.
  - Check S051 over the whole tree.

---

## 2. Files this change will touch

Paths marked **NEW** do not exist at the base commit. `vidbyte/harnesses/native/` does not exist (`ls vidbyte/harnesses`). Its current children are `client.py`, `config.py`, `contracts.py`, `dataset.py`, `errors.py`, `execution.py`, `registry.py`, `serialization.py` and `stores/`.

### 2.1 Harness side

- **NEW `vidbyte/harnesses/native/__init__.py`**
  - **Change:** Byte-exact content from request.md:175-186, SHA-256 `0374a2c8…497a`, LF endings, no imports and no `__all__`.
  - **Lint:** Its header carries all 7 A001 fields.
  - **Pattern:** none; copy the bytes as given.

- **NEW `vidbyte/harnesses/native/grok/`, `opencode/`, `muse/`, `backends/`**
  - **Change:** A host class per package, as an async context manager.
  - **Pattern to follow:**
    - Lifecycle and error translation as in `vidbyte/agents/codex/transport.py:54-119`. One `try` per operation; `except asyncio.CancelledError: raise`; the package's own error passes through; any other `Exception` becomes a vocabulary error built only from `error_type=type(exc).__name__`, never the exception text:
      ```python
      except Exception as exc:
          raise CodexAgentError("Codex failed to execute the requested turn.",
              failure_code=FailureCode.CODEX_TURN_FAILED.value, operation="turn_run",
              error_type=type(exc).__name__) from exc
      ```
    - The header form is the A001 `FILE:` style of `vidbyte/agents/codex/transport.py:1-11`, or of `vidbyte/tools/toolsets/coding.py:1-12`, quoted below.
  - **Lint scope:** harnesses are not in the S016 or S017 scope, but they are in A001, A002, A006, A007, S012, S039, S045, S055, S064 and Semgrep.

- **Subprocess handling** (Grok ACP, `grok -p`, Muse MSP)
  - **Today:** no library process runner exists. `vidbyte/lib/runners/` holds only model runners (audio, base, decision, embedding, image, router, streaming_text, text, types, utility, video).
  - **Users of `create_subprocess_exec`:** only `vidbyte/tools/builtins/bash.py:159` and `vidbyte/tools/mcp/transport.py:202`.
  - **Kill helpers:**
    - The only process-group kill is `os.killpg` with `start_new_session=True`, on POSIX only (`bash.py:167,211`; `vidbyte/agents/coding_context/setup_commands.py:93,105`).
    - On Windows, "only Git's launcher can be killed" (`bash.py:9,205-212`).
    - There is no `taskkill`, no Job Object, no `ChildProcessTree`, and no WSL-aware kill anywhere in `vidbyte/`, according to `git grep`.
  - **Pattern for the bounded stop:** `bash.py:195-234` (`_stop`). Kill, then `wait_for(process.wait(), GRACE)` under `suppress(TimeoutError)`, then close `process._transport` in `finally`. It never raises, "because an exception here would replace a propagating CancelledError".

- **`vidbyte/tools/mcp/transport.py`** (473 lines, Context Protocol header; Q-3 option 1). Read-only today.
  - **Public API:**
    - `build_child_env(extra)` at `:80-89`: allowlisted parent environment plus caller overlays, the place to pass credentials through env.
    - `McpTransport` Protocol at `:92-100`: `async request(method, params) -> Mapping`.
    - `McpStdioTransport(command, *, env, request_timeout=30.0, shutdown_timeout=5.0, stderr_max_bytes=64KiB)` at `:112-145`, with `start()`, `request()`, `close()`, `abandon()`, `stderr_snapshot()`, `is_bound_to_running_loop()` and `closed`.
  - **Windows launcher, `:197-201`:**
    ```python
    # @intent windows-launchers-resolve-like-a-shell
    if sys.platform == "win32":
        program = shutil.which(program) or program
    ```
  - **Limits relevant to ACP and MSP:**
    - Messages without `id` (notifications) are discarded (`:416-418`).
    - Any message with an int `id` is treated as a response to a pending request (`:419-450`). A server-initiated request (`id` plus `method`, such as ACP `session/request_permission` or MSP `approval/requested`) would be routed to whichever pending future shares that id and fail it with "MCP response result must be an object", or be dropped.
    - There is no API to answer a server request.
    - `request()` has no per-call timeout keyword (`:222-226`), so any `.request(` call outside `tools/mcp/client.py` trips S012.
    - It uses `asyncio.Lock` at `:139-144` (S039 debt).
    - It raises `ValueError` in `__init__` at `:122-129` (S016 debt) and `McpProtocolError` elsewhere.
    - `close()` terminates or kills the direct child only (`:321-336`).
  - **Imports:** importing it from `vidbyte/harnesses/` is not an A006 finding. See §1.3.

- **`vidbyte/lib/http/transport.py`** (242 lines, no A001 header). This is the only module that may import `httpx` (S011) and is the opencode route.
  - `HttpTransport.request(*, method, url, headers, json_body: Mapping[str, object] | None = None, timeout_seconds=60.0, retry_count=0, backoff_seconds=0.5, backoff_multiplier=2.0, retry_status_codes=(408,409,425,429,500,502,503,504), max_response_bytes=None, idempotency_key=None, follow_redirects=False) -> HttpResponse` (`:55`).
  - It builds a new `httpx.AsyncClient` per call (`:61`).
  - An HTTP error status is returned as a response, not raised (`:64-65`).
  - `httpx.RequestError` becomes `ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc))` (`:70-71`).
  - POST retry requires an `idempotency_key` (`:57`).
  - There is no query-parameter argument, no async streaming or SSE, and no injectable client. `SyncHttpTransport.stream_request` (`:172`) is blocking.
  - **Change:** only if the spec needs an option, and per AGENTS.md:41 it is added "to it rather than copying it".

- **`vidbyte/lib/http/parser.py`** (51 lines)
  - `HttpResponseParser.parse_json_response` raises `ProviderRequestError(message, provider=…, status_code=…, response_excerpt=response.body)` on a non-2xx status (`:13-19`).
  - It reads `error.message`, a string `error`, or a top-level `message` (`:35-45`, from #990).
  - `bearer_headers(api_key)` is at `:21-23`.
  - **Pattern for:** `get_deepseek_balance` and opencode JSON.

- **Redaction (#993):** `vidbyte/harnesses/serialization.py:61-95`.
  - `HarnessSecretPolicy(CredentialKeyPolicy)`.
  - `HarnessRedactor.redact()` and `safe_error_message(error, *, max_chars=1000)`. `_ERROR_ASSIGNMENT` now matches prefixed names such as `OPENAI_API_KEY=` and `githubToken`.
  - `vidbyte/lib/util/credential_keys.py:50-76` provides `CredentialKeyPolicy.is_secret_key`, with suffixes `_api_key`, `_token`, `_secret` and `_password`.
  - `vidbyte/lib/dataclasses/failure.py:32-70` provides `FailureSafety.sanitize_mapping`, which bounds values to 500 characters and 32 items and drops secret keys.
  - **Pattern for:** "no secrets in errors". Reuse these rather than a new scrubber.

- **`vidbyte/lib/registries/models.py`** (445 lines). Read-only reuse.
  - Default models: `DEEPSEEK: "deepseek-v4-pro"` (:73), `GLM: "glm-5.2"` (:74), `META: "muse-spark-1.1"` (:77).
  - `API_KEY_ENV_VARS`: `DEEPSEEK_API_KEY` (:90), `GLM_API_KEY` (:91), `META_API_KEY` (:94).
  - `DEFAULT_ENDPOINTS`: DeepSeek `https://api.deepseek.com/v1` (:107), GLM `https://open.bigmodel.cn/api/paas/v4` (:108), Meta `https://api.meta.ai/v1` (:111).
  - `STRICT_MODEL_VALIDATION = True` (:66). `ProviderModelRegistry.validate_model` rejects uncatalogued names, which matters for C012.
  - `ModelProvider` members are at `vidbyte/lib/enums/model_provider.py:35-40`.
  - **Backend-profile registry location:**
    - By the field guide (declarative-config-resolution), a name to class registry goes in `vidbyte/lib/registries/<name>.py` and fixed capability data in `vidbyte/lib/configs/`. Today that folder holds only `structured_output.py`.
    - S021 forbids public module-level functions in registry modules.

### 2.2 Records, enums, constants, errors

- **NEW `vidbyte/lib/dataclasses/<domain>.py`** (one or more new domains)
  - **Today:** `vidbyte/lib/dataclasses/codex.py` is 1205 lines, already over 1,000, so do not grow it. `vidbyte/lib/dataclasses/harnesses.py` (138 lines) is the harness-execution domain.
  - **Pattern from `codex.py`:**
    - `@dataclass(frozen=True, slots=True)` with `__post_init__` raising `ConfigurationError`.
    - `TYPE_CHECKING` imports for higher-layer types.
    - `from_params(cls, params: Mapping[str, Any] | None)` wire constructors that read camelCase.
    - `__all__ = [name for name in globals() if name.startswith("Codex")]`. That `__all__` comprehension is resolvable by S015; unverified for the C016 resolver, but it is not used in the root `__init__`.
  - **Lint:** S060 forbids `dict[str, Any]` in public signatures here.
  - **Avoid:** its private helpers `_require_bool` and `_require_non_negative_int` are C008 debt.
  - **Note:** `vidbyte/lib/dataclasses/__init__.py` (481 lines) re-exports domains, including Codex at `:51`. It is not on the append-only list in request.md:200.

- **NEW `vidbyte/lib/enums/<domain>.py` plus `vidbyte/lib/enums/__init__.py`** (235 lines, A001 header)
  - **Change:** append imports and alphabetical `__all__` entries.
  - **Pattern:** `vidbyte/lib/enums/codex.py`. `class X(str, Enum)` with a literal `__all__`.
  - `CodexFailureClass` is not exported from `vidbyte/lib/enums/__init__.py`. Unverified whether that is intentional.

- **`vidbyte/lib/enums/failure.py`** (297 lines, A001 header)
  - **Today:** `class FailureCode(str, Enum)` at :22. Members run from :25 `CONFIGURATION_INVALID` to :144 `RULE_EVALUATION_FAILED`; :145 is blank and :146 is `@property category`, which returns the prefix before `.` (:147-149).
  - **Naming:** `CATEGORY_PROBLEM = "category.problem"`.
  - **CODEX block:** first member :35 `CODEX_SDK_UNAVAILABLE = "codex.sdk_unavailable"`, last :46 `CODEX_RUN_OPTION_UNSUPPORTED = "codex.run_option_unsupported"`. Line :34 is `CONFIGURATION_INVALID_ARGUMENT`, the spot the Claude PR uses. Line :47 is `INPUT_EMPTY`, the spot the Codex PR appends after.
  - **Insertion spots** (none touches :34/:35 or :46/:47):
    1. After :144 `RULE_EVALUATION_FAILED`, before the blank :145. This is the end of the members.
    2. Between :67 `PROVIDER_CONFIGURATION_INVALID` and :68 `TOOL_NOT_FOUND`.
    3. Between :99 `ACTION_UNEXPECTED_SIDE_EFFECT` and :100 `RUNTIME_MAX_ITERATIONS`, or between :129 `DATA_PERMISSION_DENIED` and :130 `WORKFLOW_DEFINITION_INVALID`.
  - **Header rule** (:6): "Add a category-prefixed code with docs, mapping coverage, and a focused test."

- **Failure classification table:** `vidbyte/lib/constants/codex.py:95-174`, `CODEX_FAILURE_CLASSIFICATION`.
  - **Row shape:** `FailureCode.X.value: (CodexFailureClass.<>.value, FailurePhase.<>.value, FailureSeverity.<>.value, FailureDisposition.<>.value)`.
  - **Consumer:** `vidbyte/agents/codex/failures.py:53-77` uses it, and an unknown code becomes TERMINAL/CRITICAL (`:42-47`).
  - **Enforcement:**
    - Only `codex.*` codes must have a row, per `tests/test_codex_failure_recovery.py:192-202`.
    - `tests/test_session_failures.py:139` asserts every `FailureCode` value contains ".".
    - No test or lint requires a table for other prefixes.

- **NEW `vidbyte/lib/constants/<domain>.py`**
  - **Pattern:** `vidbyte/lib/constants/codex.py`, for example `CODEX_TOOL_CALL_TIMEOUT_SECONDS = 300.0` and `CODEX_MAX_CONCURRENT_TURNS`.
  - `vidbyte/lib/constants/__init__.py` (167 lines) re-exports `codex` at `:3`.

- **`vidbyte/lib/errors/base.py`** (503 lines). Touch only if new error classes go here; they then need A003.
  - `VidbyteSdkError(message, *, details)` :59-66.
  - `McpProtocolError` :121.
  - `CodexAgentError(message, *, failure_code, operation, error_type="")` with `DIAGNOSTIC_FIELDS` :129-153.
  - `ConfigurationError` :235.
  - `ProviderRequestError(message, *, provider, status_code=None, response_excerpt=None)`, excerpt capped at 500 characters, :247-259.
  - `ProviderResponseError` :271-289.
  - `vidbyte/harnesses/errors.py` (182 lines) holds `HarnessError(VidbyteSdkError)` :55 and subclasses up to `HarnessTimeoutError` :163, outside A003's scope.

### 2.3 Tool side

- **NEW `vidbyte/tools/builtins/<host>/`**
  - **Request:** the sessions layout (`_base.py`, files, `descriptions.py`).
  - **What the layout is** (`vidbyte/tools/builtins/sessions/`):
    - `_base.py:30` defines `_SessionBuiltinTool(BaseTool)`.
    - `__init__(store, *, scope=None)` at :33 binds shared state.
    - Helpers: `bind_owner` :43, `bind_session` :47, `clone_for_fork` :52, `_denied` :63, `_optional_text` :68, `_require_bound` :79.
    - `_caught(name, operation: Callable[[], ToolResult])` at :85 wraps a **synchronous** callable and returns `ToolResult.error(name, f"{type(exc).__name__}: {exc}")` at :90, which is S017-style debt. `batch_fork.py:56` does the same.
    - Each tool file is `_TOOL_NAME = "..."` (`checkpoint.py:28`) plus a class whose `spec()` returns `ToolSpec(name=_TOOL_NAME, description=<constant from descriptions.py>, …)` (:34-37) and `async execute` returns `self._caught(...)` (:50-52), ending in `__all__` (:98).
    - `descriptions.py` uses adjacent literals (S062 debt) and has no A001 header.
  - **Base contract:**
    - `vidbyte/tools/base.py`: `BaseTool(ABC)` :30; abstract `spec()` :79; `async execute(call)` :83 (tools are async only).
    - Also `validate_call` :86 (required parameters), `_resolve_bool_argument(call, name, *, default)` :99, `_optional_argument` :111, `customize` :62 and `with_activity` :38.
  - **Records** (`vidbyte/lib/dataclasses/tools.py`):
    - `ToolPermission` SAFE/READ/WRITE/EXECUTE :47-53.
    - `ToolParameter(name, type, description, required=True, default=None)` :66.
    - `ToolSpec` :115.
    - `ToolCall` :267.
    - `ToolResult.success(tool_name, output, *, metadata)` :298 and `.error(...)` :314.
  - **Subprocess precedent** for an error result that is S017-clean: `bash.py:169-174` ("naming only the exception class").

- **`vidbyte/tools/builtins/__init__.py`** (325 lines, Context Protocol header, so A001 debt)
  - **Today:** explicit imports per category (`:28-177`), including `sessions` (`:167-176`), and an alphabetical `__all__` (`:182-319`) followed by the reasoning `.extend` (`:321-325`).
  - **Change:** append the new imports and names.
  - **Effect:** `ComponentRegistry._discover("tools")` (`vidbyte/lib/registries/components.py:101-124`) scans `vars(vidbyte.tools.builtins)` for every public `BaseTool` subclass. Every exported host tool, WRITE tools included, becomes YAML-declarable and buildable as `component(**options)`.
  - **Tests:** `tests/features/coding_agent/test_coding_agent_contract.py:109` asserts names in `vidbyte.tools.builtins.__all__`.

- **NEW `vidbyte/tools/toolsets/<host>.py` plus `vidbyte/tools/toolsets/__init__.py`**
  - **Today:** `__init__` (Context Protocol header) imports `CodingAgentTools` and `ParadigmMinimalToolset` (`:17-18`) into `__all__` (`:20-23`).
  - **Pattern:** `vidbyte/tools/toolsets/coding.py` has `class CodingAgentTools(Tools)` :47, `__init__(settings)` :50 calling `super().__init__(self.get_tools(...))` :57, `@staticmethod` helpers :59 and :79, and `__all__` :138.
  - **Header to copy** (`coding.py:1-12`, field order):
    ```
    """FILE: vidbyte/tools/toolsets/coding.py

    PURPOSE: …
    ROLE IN CODEBASE: …
    ARCHITECTURE NOTE: …
    FUNCTION INVENTORY: …
    COMMON MODIFICATION PATTERNS: …
    WHAT NOT TO DO IN THIS FILE: 1. … 2. … 3. …
    KNOWN EDGE CASES: …
    RELATED DOCS: …
    TESTS: …
    """
    ```
  - **Catalog:** `vidbyte/tools/catalog.py`, where `Tools(Sequence[BaseTool])` rejects duplicate names with `ToolRegistrationError`.

- **`vidbyte/tools/executor.py`**
  - **Today:** `ToolExecutor(registry, permission_policy=None)` defaults to `PermissionPolicy()` (`:37-41`).
  - **Order:** permission check (`:53`), a denial returns `metadata={"error": "permission_denied", …}` (`:58`), then `validate_call` (`:61`), then execute.
  - **Exceptions:** an exception becomes `ToolResult.error(f"Tool execution failed: {exc}", metadata={"error": "execution_error", …})` (`:74-75`).
  - **Policy:** `vidbyte/lib/dataclasses/security.py:30-53` sets the default `allowed` to SAFE and READ, with `check()` and `allow_all()`.
  - **Change:** none expected.

- **`vidbyte/mcp_server/`** (exposure). The change is "add code there only if it cannot already serve a toolset" (request.md:94).
  - **How tools get in:** only through `McpStudioServer(tools: Sequence[BaseTool] = ())` (`server/core.py:75-110`) into `StudioToolRegistry(tools=…)`. `_register_builtins` adds 8 `studio.*` tools and then every caller tool by `spec().name`, last one wins (`handlers.py:59-73`).
  - **Toolsets:** nothing discovers toolsets or builtins. `python -m vidbyte.mcp_server` and `vidbyte-mcp-server` build `McpStudioServer()` with no tools (`__main__.py:22-24`; `pyproject.toml [project.scripts]`).
  - **Permission claim confirmed:** `StudioToolRegistry.execute` is `return await tool.execute(ToolCall(name, arguments))` at `handlers.py:84-88`, with no `PermissionPolicy`, no `validate_call` and no timeout.
  - **Call path:** `tools_call.py:43-50` catches `Exception` into `f"Tool execution failed: {exc}"` (S017 debt) and treats `status == "error"` or output starting with `"Error:"` as an MCP error.
  - **One request at a time:** the server loop awaits each request in turn (`server/core.py:131-146`). A long `wait_*_turn` blocks every other MCP request on that server, and there is no `notifications/cancelled` handling, since unknown notifications are no-ops (`:212-214`).

### 2.4 Public surface and indexes

- **`vidbyte/__init__.py`** (1297 lines, Context Protocol header)
  - **Today:** imports at `:37-688`, including `from vidbyte.harnesses import (...)` at `:380-399` and `from vidbyte.tools.toolsets import CodingAgentTools, ParadigmMinimalToolset` at `:611`, then `__all__ = [` from `:690` to the end.
  - **Change:** append-only.
  - **Lint and tests:**
    - S015 requires every public import to be listed.
    - `tests/features/coding_agent/test_coding_agent_contract.py:107` and `tests/test_agent_modality_routing.py:193-195` assert membership in `vidbyte.__all__`.

- **`contracts/sdk-public-api.json`** (614 lines; `schema_version` 1, `version` "0.2.1", sorted `exports`)
  - **How it is written:** only by `scripts/generate-sdk-public-api.py` (152 lines), through `lint/core/public_api_contract.py` (433 lines), which reads `__all__` from the AST and never imports `vidbyte`.
  - **Refuses dirty inputs:** "Writing refuses while any input file differs from HEAD" (`scripts/generate-sdk-public-api.py:9,73-76`).
  - **Order:** "Commit the vidbyte/__init__.py or version change first, then run this script and commit the regenerated file in the same pull request" (`:7`).
  - **Gate:** C016 fails when the file is stale (`lint/rules/c016_public_api_contract_current.py:3-4`). `contracts/README.md`: "Never edit a contract by hand".

- **`REPO_MAP.md`** (append-only; File Index)
  - `#### vidbyte/harnesses/` at `:147-149` describes harnesses as RL-trajectory capture and has only `##### vidbyte/harnesses/stores/` (`:151`). There is no `native/` entry.
  - `##### vidbyte/tools/toolsets/` at `:335-337` says "It currently holds one such bundle". That is stale; there are two today.
  - `##### vidbyte/tools/security/` at `:331-333` says "Any tool that writes data … passes through this boundary before it is allowed to act". See §4.

- **`vidbyte/harnesses/README.md`** (180 lines, append-only)
  - **Today:** sections at `:1`, `:42`, `:92`, `:114`, `:130`, `## Relationship to adjacent layers` at `:158`, and `## Key modules` at `:167-180`, a bullet per module. There is no `## Notes for agents` and no `## File Index`, so S020 does not apply.
  - **Change:** append a `native/` bullet.
  - **Pattern:** "- `stores/`: `TrajectorySink` port (`base.py`) plus …".

- **`vidbyte/harnesses/__init__.py`** (95 lines)
  - **Today:** PURPOSE, ROLE, ARCHITECTURE, PUBLIC API INVENTORY, WHAT NOT TO DO, RELATED DOCS and TESTS, but no COMMON MODIFICATION PATTERNS and no KNOWN EDGE CASES, so it is in the A001 baseline. Imports at `:37-61`.
  - **Change:** not on the append-only list. request.md:173 says hosts are imported from their own subpackage, so no change is expected.

---

## 3. Tests that cover these files

- **Framework**
  - pytest 8.3.5 with pytest-asyncio 1.3.0. `asyncio_default_fixture_loop_scope="function"` is set and no `asyncio_mode`, so strict mode applies and async tests need `@pytest.mark.asyncio` (`pyproject.toml`).
  - Many modules use `unittest.IsolatedAsyncioTestCase`, for example `tests/test_mcp_stdio_transport.py:38`, or call `asyncio.run`.
  - `tests/__init__.py` exists, so `from tests.agent_test_support import …` works (`test_bash_tool_process_bounds.py:29`). There is no root `conftest.py`.
- **Layout**
  - Feature packs live in `tests/features/<pack>/`. Each has `FEATURE.md`, a `README.md` with `## File Index` (S020) and `## Logs`, an optional `conftest.py`, and `test_*.py`, with no `__init__.py`.
  - Examples: `tests/features/coding_agent/` (README :15) and `tests/features/sdk_model_catalog/`.
  - Codex tests are flat: `tests/test_codex_*.py`.
  - Every test `.py` needs an A001 header, for example `tests/features/coding_agent/conftest.py:1-12` and `tests/test_codex_tools.py:1-30`.
- **Fixture and fake patterns**
  - **Fake stdio peer:** `_python_child(source)` returns `[sys.executable, "-u", "-c", dedent(source)]` (`tests/test_mcp_stdio_transport.py:33-35`). The same file has a Windows `.cmd` launcher test that writes `@echo off\r\n"<python>" -u "<server>"` (`:534`) and a `shutil.which` argv test (`:467`).
  - **Fake HTTP:** `patch("vidbyte.lib.http.transport.httpx.AsyncClient", server.client_factory)`, where the factory returns the real `AsyncClient(..., transport=httpx.MockTransport(handler))` (`tests/test_http_transport_content_type.py:29,53-60`). Alternatively, patch `HttpTransport._send_once` (`tests/features/coding_agent/conftest.py:3-4`).
  - **Process bounds:** patch module-level time constants, assert upper bounds with slack, and keep liveness checks POSIX-only, with skip markers `posix_only` and `needs_setsid` (`test_bash_tool_process_bounds.py:35-48`).
  - **Fake SDK client:** `tests/test_codex_tools.py:16-21` (`_FakeAsyncCodex`).
- **Tests that enumerate global sets**
  - `tests/test_session_failures.py:139`: every FailureCode value contains ".".
  - `tests/test_codex_failure_recovery.py:192-202`: every `codex.*` code has a classification row, and every row is a known code.
  - `tests/features/coding_agent/test_coding_agent_contract.py:107-109`: root and builtins `__all__` membership.
  - `tests/test_agent_modality_routing.py:193-195`.
  - `tests/test_mcp_studio_server.py` covers the MCP server; its contents are unverified.
- **Commands** (from the worktree root)
  - One file: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_<x>.py`.
  - Area: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host`, and likewise `opencode_host`, `muse_host` and `native_backends` (folder names from request.md:191).
  - Existing neighbours: `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py`.

---

## 4. Notes for the spec author (contradictions and gaps; no designs)

1. **httpx**
   - **Request assumes:** opencode uses `httpx` directly (request.md:124,153,731).
   - **Code shows:**
     - S011 forbids importing `httpx` anywhere in `vidbyte/` except `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py` (`lint/rules/s011_raw_http_client_ownership.py:22-23`), with a baseline of 0.
     - The usable route is `HttpTransport.request` (`vidbyte/lib/http/transport.py:55`). It has no async streaming or SSE, no query-parameter argument, a new client on every call (`:61`), and JSON bodies only.
2. **Reusing the MCP transport (Q-3 option 1)**
   - **Request assumes:** `vidbyte/tools/mcp/transport.py` "may be reusable for ACP and MSP framing" (request.md:263,741).
   - **Code shows:**
     - It drops notifications (`:416-418`), so ACP `session/update`, `usage_update` and MSP event streams would never arrive.
     - It treats any int-`id` message as a response (`:419-450`) and cannot answer server requests, which Q-4 needs.
     - `request()` takes no per-call timeout (`:222-226`), so every `.request(` call site outside `tools/mcp/client.py` is an S012 finding (baseline 0).
   - **Layers:** A006 itself allows `harnesses → tools.mcp` (§1.3).
3. **Copying the sessions layout**
   - **Request assumes:** copy `builtins/sessions/` "_base.py … descriptions.py" (request.md:92,261).
   - **Code shows:** that folder uses:
     - the non-A001 Context Protocol header (`checkpoint.py:1`);
     - raw exception text in errors (`_base.py:90`, `batch_fork.py:56`), in S017's scope;
     - adjacent-literal descriptions (S062 debt);
     - a **synchronous** `_caught(name, Callable[[], ToolResult])` (`_base.py:85`), while host operations are async.
4. **Classification rows**
   - **Request asks:** whether each new FailureCode needs a classification row (request.md:266).
   - **Code shows:** only `codex.*` codes are forced to have one, by `tests/test_codex_failure_recovery.py:192-202`. No table, test or lint covers other prefixes. The failure.py header (:6) asks for "docs, mapping coverage, and a focused test" without naming a table.
5. **Permission enforcement over MCP**
   - **Request's claim is confirmed:** "MCP server … runs tools without a PermissionPolicy check" (request.md:277). `vidbyte/mcp_server/handlers.py:84-88` calls `tool.execute` directly, with no permission check, no `validate_call` and no timeout.
   - **Contradicted text:** `REPO_MAP.md:333` says every writing tool "passes through this boundary before it is allowed to act".
   - **No automatic exposure:** the MCP server serves only tools passed to `McpStudioServer(tools=…)` (`server/core.py:75-110`), and `__main__` passes none (`__main__.py:23`).
6. **YAML exposure:** every public `BaseTool` exported from `vidbyte.tools.builtins` becomes YAML-declarable (`vidbyte/lib/registries/components.py:101-124`), WRITE (spending) tools included. request.md does not mention this.
7. **Serial MCP server:** it awaits one request at a time (`server/core.py:131-146`). A blocking `wait_*_turn` tool stalls all other MCP calls, and MCP cancellation notifications are ignored (`:212-214`).
8. **300 s cap from Codex:** when these tools run as dynamic tools inside a Codex agent, each call is cut at `CODEX_TOOL_CALL_TIMEOUT_SECONDS = 300.0` (`vidbyte/lib/constants/codex.py:193`; `vidbyte/agents/codex/tools.py:150-168`). The future is cancelled, so a tool's coroutine sees `CancelledError`. Under `BaseAgent`, `ToolSettings.tool_timeout_seconds` (`vidbyte/agents/runtime.py:1449-1451`) can impose a similar cut.
9. **Process kill**
   - **Request assumes:** the host can "kill the process tree inside WSL" (request.md:368,598) and reap children.
   - **Code shows:** no process-tree kill exists. POSIX code uses `os.killpg` with `start_new_session` (`bash.py:167,211`). Windows code kills the direct child only, and bash.py documents this as a known limit (`bash.py:9`). `McpStdioTransport.close()` kills the direct child only (`:321-336`).
   - **No library runner:** the field guide's "one library runner" for CLI processes does not exist in `vidbyte/lib/runners/`.
10. **Muse `.cmd` shim**
    - **Source:** the research file `muse-shim-muse.cmd.txt`, untrusted and not verified live.
    - **Content:** `wsl.exe -d MuseUbuntu1 -- /usr/local/bin/muse %*`.
    - **Consequences:**
      - `shutil.which("muse")` in the MCP transport (`:200-201`) would resolve to a `.cmd`, so arguments pass through `cmd.exe` `%*` parsing.
      - Killing the direct child stops `cmd.exe`, not `wsl.exe` or the in-distro `muse`. Whether `wsl.exe` relays the kill is unverified.
11. **Muse SDK:** request.md:598 says MuseHost "Talks MSP through `muse-code-sdk`", but Q-2 defaults to no new dependency (request.md:730-737) and `pyproject.toml` is reserved (request.md:202). These conflict.
12. **Locks:** `asyncio.Lock` is banned (S039, `lint/ruff.toml`). The SDK precedent is `asyncio.Semaphore(1)` (`vidbyte/agents/codex/agent.py:82-86`). `McpStdioTransport` itself uses `asyncio.Lock` (`:139-144`) as baseline debt.
13. **The `timeout` parameter name:** S045 (Ruff ASYNC109) flags an async def parameter named `timeout`. Tool or host signatures such as `wait_opencode_turn(id, timeout)` in the catalog need another name; `timeout_seconds` matches S012's keyword.
14. **C012 versus vendor model strings**
    - **The rule:** a `model` or `*_model` str field on a class ending Settings, Config, Configuration, Spec, Descriptor or Options must be proved at construction through `ProviderModelRegistry` (`lint/rules/c012_provider_model_registry_validation.py:24-27`), and the registry is strict (`models.py:66`).
    - **The conflict:** Grok, opencode (`provider/model`), Muse and Claude-backend names such as `glm-5.3[1m]` and `deepseek-flash[1m]` (request.md:374,382) are not in that catalog.
    - **Exemptions:** these exist only as per-field rows inside the rule file (`:33-46`). Editing that file may count as weakening a rule; unverified.
15. **GLM endpoint:** the existing GLM entry is BigModel `https://open.bigmodel.cn/api/paas/v4` (`models.py:108`), while the backend profile needs Z.ai's Anthropic-compatible endpoint (request.md:371, Q-13). request.md cites `models.py:90-107`; the endpoints are actually at `:107-111`.
16. **Public-API regeneration:** changing `vidbyte/__init__.py` needs a commit before `scripts/generate-sdk-public-api.py` will write, because it refuses dirty inputs (`:73-76`). The contract file therefore lands in a later commit than the export change, and C016 fails in between.
17. **Wheel contents:** C015 plus a frozen `pyproject.toml` means no non-`.py`, non-README file (vendored MSP or OpenAPI JSON, fixtures) can live under `vidbyte/`.
18. **Stale REPO_MAP entries:** the toolsets entry says one bundle (`REPO_MAP.md:337`). The harnesses entry describes RL-trajectory capture only (`:149`); native hosts do not match that description.
19. **No `Notes for agents`** section exists in any README of a touched folder (`git grep "## Notes for agents"` finds only AGENTS.md, REPO_MAP.md and `vidbyte/agents/coding_context/README.md`). `vidbyte/agents/codex/README.md` has a `## File Index` (`:1103`), so S020 applies if a file is added there; nothing is expected to be.
20. **Codex README httpx snippet:** `vidbyte/agents/codex/README.md:337,353` shows `import httpx` inside a user `@tool`. That is user code and outside `vidbyte/` lint scope, not a precedent for SDK code.
21. **Unverified items**
    - Whether `--check` and C016 compare `source.commit`.
    - Ruff S105 behaviour on `*_TOKEN_ENV` constant names.
    - The contents of `tests/test_mcp_studio_server.py`.
    - Whether `CodexFailureClass` was left out of `lib/enums/__init__` on purpose.
    - Live vendor behaviour of grok, opencode or muse; none was run.
