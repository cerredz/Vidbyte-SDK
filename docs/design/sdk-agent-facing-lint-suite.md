# SDK Agent-Facing Lint Suite

## 1. Overview

Create the Vidbyte SDK's first repository-level, agent-facing lint suite. The
suite combines pinned Ruff and mypy analyses with SDK-specific AST contract
rules, translates all findings into actionable diagnostics, and freezes existing
debt with a count baseline. It becomes part of the canonical source gate invoked
by `python scripts/run_ci.py --stage source`.

The implementation follows the SDK's class-bound helper convention: the runner,
collectors, adapters, rule registry, and semantic analyzers are classes with
small static/class methods. The suite reads source only; it does not import SDK
modules or contact providers.

## 2. Goals & Non-Goals

### Goals

- Establish high-signal Python correctness, exception, datetime, async-task,
  annotation, and complexity gates through pinned Ruff selectors.
- Establish a staged mypy contract ratchet without requiring the entire current
  package to become type-clean in one change.
- Enforce async/sync HTTP transport parity, raw-client ownership, explicit
  timeouts, and response-size ceilings for untrusted-content boundaries.
- Enforce provider/model registry parity and package export integrity.
- Enforce typed public boundary errors, prevent raw exception disclosure, and
  preserve provider attempt counts in priced operation results.
- Enforce cancellation propagation, class-bound registry helper ownership, and
  README `File Index` parity where a folder already declares such an index.
- Preserve the existing Semgrep typed-Mapping boundary workflow and execute the
  new suite through the canonical local/PR source gate.
- Produce diagnostics written for a coding agent: consequence, repair shape,
  local examples, rejected shortcuts, and focused verification command.

### Non-Goals

- No runtime feature, provider API, public API, packaging, or pricing behavior change.
- No source autofix, formatting rollout, or global style rewrite.
- No ban on `Any` (`ANN401`), broad `except Exception` (`BLE001`), FastAPI-style
  call defaults (`B008`), long parameter lists (`PLR0913`), or exact header text.
- No requirement that all existing mypy/Ruff debt be fixed immediately.
- No README invention in folders that do not already use a `## File Index`.
- No execution/import of `vidbyte` during lint, because provider imports may
  resolve configuration or optional dependencies.
- No replacement of `.semgrep/typed-mapping-boundary-policy.yml` or
  `scripts/check_context_write_paths.py`; both remain independently enforced.
- No new feature-test files. Verification uses focused lint scans and existing CI.

## 3. Background & Context

The SDK currently uses compileall, a custom context write-path checker, pytest,
package build/Twine/wheel smoke checks, and a separate Semgrep policy workflow.
It does not yet run Ruff or mypy. The audit found 55 high-signal F/E findings,
public annotation debt, complexity debt, unsafe zip/task/datetime/class-default
patterns, and mypy errors that expose real async/sync transport mismatches.

`HttpTransport.request` is asynchronous while `SyncHttpTransport` owns blocking
`request`, `request_bytes`, `upload_multipart`, and `stream_request`. Several
sync provider/runners currently default to `HttpTransport`, which static typing
correctly identifies as coroutine misuse. All raw HTTP behavior belongs in
`vidbyte/lib/http/transport.py` (plus the dedicated MCP transport adapter), and
untrusted fetch/search boundaries must bound response bytes.

`ProviderModelRegistry`, `ModelProvider`, runner maps, default endpoints, and API
key environment maps are parallel declarative registries. They are currently
near parity, making a clean or low-debt rule valuable. The root package also has
a large manual export surface whose drift currently fails only at import time.

The SDK field guide requires related helpers to live on static helper classes,
configuration resolution to remain declarative, runtime boundaries to preserve
typed errors and cancellation, and local CI in a worktree to use the worktree
source via `PYTHONPATH`.

## 4. Requirements

### 4.1 Functional Requirements

- FR-1: `python lint/run.py` runs S001-S021 and exits nonzero on regression,
  analyzer error, missing baseline key, or stale baseline key.
- FR-2: `--rule`, `--format json`, `--all`, and `--update-baseline` support the
  focused agent edit/fix loop.
- FR-3: Every rule is one registered module and one independently reportable ID.
- FR-4: Ruff executes at most once per lint process with a fixed selector union;
  mypy executes at most once with the checked-in configuration.
- FR-5: Analyzer subprocess errors and malformed output fail closed with command,
  working-directory, exit code, and captured stderr.
- FR-6: The baseline is a sorted `{rule_id: count}` mapping. New debt fails; a
  lower count passes as IMPROVED and must be ratcheted downward before handoff.
- FR-7: AST rules must scan tracked package source deterministically and must not
  import or execute package modules.
- FR-8: `scripts/run_ci.py --stage source` must run the new lint suite before
  pytest, with bytecode suppression and inherited worktree `PYTHONPATH`.
- FR-9: `pyproject.toml` must pin Ruff and mypy in the dev extra so the existing
  Python 3.11/3.12 CI matrix installs the exact analyzers.
- FR-10: Existing Semgrep and context-write-path rules remain active and are not
  silently folded into a baseline.

### 4.2 Non-Functional Requirements

- NFR-1: Full lint should target under 30 seconds on a warm checkout.
- NFR-2: Output order is stable by rule, path, line, and column.
- NFR-3: The suite works on Windows and POSIX without shell-specific command strings.
- NFR-4: File reads use UTF-8 with BOM tolerance and render actionable path errors.
- NFR-5: New files have complete headers; functions use one-line signatures and
  focused class-bound helpers, with intent comments only for load-bearing policy.
- NFR-6: Rules favor explicit semantic scopes over blanket bans and document
  sanctioned boundaries in constants beside the scanner.

## 5. High-Level Design

```text
tracked vidbyte/**/*.py -------> SourceCatalog -------> SDK AST rules
          |                            |
          +------> RuffStore ----------+------> native Findings
          |
          +------> MypyStore ----------+
                                               |
baseline.json <---- BaselineStore <---- RuleRunner ----> text / JSON / exit code
```

`SourceCatalog` reads tracked Python and README files once and attaches parsed
ASTs. `RuffStore` and `MypyStore` are cached subprocess adapters. The `RuleRunner`
does not know analyzer details: every rule implements the same `check` and
`explain` contract. This makes external and custom rules indistinguishable to
the baseline/reporting layer.

## 6. Detailed Design

### 6.1 Core Components

#### CLI and runner

- Files: `lint/run.py`, `lint/core/runner.py`.
- Types: `LintApplication`, `RuleRunner`, `RunConfiguration`.
- Interface: all rules by default; focused `--rule SNNN`; text/JSON; optional
  baseline update.
- Errors: converts all rule/analyzer exceptions into ERRORED results and returns
  exit code 1; command misuse returns argparse's exit code 2.

#### Source catalogue

- File: `lint/core/discovery.py`.
- Type: `SourceCatalog` with cached `python_files()` and `readmes()` methods.
- Algorithm: obtain tracked paths using `git ls-files`, restrict to package and
  declared README surfaces, ignore generated/build/worktree paths, parse Python
  with `ast.parse`, and preserve parse errors as data.
- Errors: missing git/package roots and unreadable files include absolute target,
  operation, expected encoding, and repair action.

#### Diagnostics, report, and baseline

- Files: `lint/core/diagnostic.py`, `baseline.py`, `report.py`, `registry.py`.
- Types: immutable `Finding`, `Diagnostic`, `RuleResult`, `RunReport`; class-based
  stores/registries.
- Baseline: exact count per rule. Stale/missing entries fail except during the
  explicit baseline-update command.
- Registry: rejects duplicate IDs and renders the valid catalogue on selection errors.

#### Ruff and mypy adapters

- Files: `lint/core/ruff.py`, `lint/core/mypy.py`, `lint/mypy.ini`.
- Ruff: one `python -m ruff check vidbyte --isolated --output-format json
  --exit-zero` call with the fixed selector union.
- mypy: one `python -m mypy --config-file lint/mypy.ini vidbyte` call; parses
  machine-stable `path:line:column: severity: message [code]` output and accepts
  mypy's findings exit code while rejecting analyzer/internal failures.
- Both: no shell invocation; deterministic environment; cached immutable records.

### 6.2 Ruff Rules

#### S001 -- Python correctness foundation

- Selectors: F, E4, E7, E9.
- Protects: undefined/unused names, broken imports, syntax-class errors, and
  high-signal parser/whitespace correctness.

#### S002 -- exception cause chaining

- Selector: B904.
- Protects: error provenance when translating provider/protocol exceptions.

#### S003 -- strict zip

- Selector: B905.
- Protects: silent truncation in paired model/result/config iteration.

#### S004 -- timezone-aware datetime

- Selectors: DTZ001-DTZ012.
- Protects: trace, retry, billing, and evaluation timestamps from naive/aware drift.

#### S005 -- immutable class defaults

- Selector: RUF012.
- Protects: shared mutable state; requires `ClassVar` when sharing is intentional.

#### S006 -- async task ownership

- Selector: RUF006.
- Protects: fire-and-forget tasks from garbage collection and lost exceptions.

#### S007 -- public function annotations

- Selectors: ANN001-ANN003, ANN201-ANN206. ANN401 is excluded.
- Scope: public production functions/methods; decorators, overloads, generated
  shims, and conventional `self`/`cls` are handled by Ruff.

#### S008 -- bounded function complexity

- Selectors: C901, PLR0912, PLR0915.
- Repair: preserve orchestration in the owning class and extract coherent private
  leaf methods rather than unrelated module-level helpers.

### 6.3 Type and Transport Rules

#### S009 -- staged mypy contracts

- File: `lint/rules/s009_staged_mypy_contracts.py`.
- Runs mypy over `vidbyte/` using Python 3.11-compatible semantics,
  `check_untyped_defs`, explicit package bases, no incremental cache, concise
  error codes, and missing-import tolerance for optional integrations.
- Every current error is count debt; any new error fails regardless of code.

#### S010 -- async/sync transport parity

- File: `lint/rules/s010_transport_parity.py`.
- Algorithm: resolve constructor assignments such as
  `self._transport = transport or HttpTransport()`; map known async/sync transport
  methods; flag sync functions consuming async results without `await`, async
  functions defaulting to blocking transports, and calls to methods absent from
  the bound transport contract.
- Edge: injected protocol types that explicitly define the needed method are
  accepted; unknown dynamic receivers become mypy's responsibility.

#### S011 -- raw HTTP client ownership

- File: `lint/rules/s011_raw_http_client_ownership.py`.
- Algorithm: flag imports/calls from `httpx`, `requests`, `urllib.request`, and
  equivalent socket HTTP clients outside `vidbyte/lib/http/transport.py` and the
  dedicated `vidbyte/tools/mcp/transport.py` adapter.
- Edge: type-only imports are allowed only if they do not expose client ownership.

#### S012 -- explicit outbound timeout

- File: `lint/rules/s012_explicit_outbound_timeout.py`.
- Algorithm: flag transport/raw HTTP request calls without an explicit
  `timeout_seconds`/`timeout` argument or a constructor-bound timeout object.
- Edge: private transport leaf methods receiving a required timeout parameter
  from their public owner are compliant. MCP client calls are also compliant
  because `McpStdioTransport` binds and enforces `request_timeout` at construction.

#### S013 -- bounded untrusted responses

- File: `lint/rules/s013_bounded_untrusted_responses.py`.
- Scope: fetch/search/browser/code-search/MCP ingestion and external operation
  clients.
- Algorithm: require `max_response_bytes` or a bounded streaming/read helper at
  the call that crosses the untrusted response boundary.
- Edge: provider model JSON responses are ratcheted separately until transport
  APIs expose a uniform ceiling; local fixture/file reads are excluded.

### 6.4 Declarative Contract Rules

#### S014 -- provider/model registry parity

- File: `lint/rules/s014_provider_model_registry_parity.py`.
- Algorithm: statically extract `ModelProvider` members, default model, endpoint,
  API-key environment, alias, bare runner, and qualified provider-runner maps.
  Require complete provider-key parity, defaults present in the owning provider's
  runner catalogue, and no unknown provider prefixes.
- Edge: the intentionally generic bare `auto` alias is documented and allowed.
- Error: identify the missing/extra registry and exact member/model.

#### S015 -- public export integrity

- File: `lint/rules/s015_public_export_integrity.py`.
- Algorithm: for every package `__init__.py` with `__all__`, require unique string
  entries bound by a local definition/import; for root `vidbyte/__init__.py`, also
  require every non-private explicit import intended for the public API to appear
  in `__all__`.
- Edge: lazy `__getattr__` exports are allowed only when statically declared by a
  local lazy-export mapping.

#### S016 -- typed external-boundary errors

- File: `lint/rules/s016_typed_boundary_errors.py`.
- Scope: providers, MCP, every built-in tool, public runner methods, and CLI
  handoff boundaries.
- Algorithm: flag raises of builtin `Exception`, `RuntimeError`, `ValueError`, or
  `TypeError` that leave the boundary without translation to `vidbyte.lib.errors`.
- Edge: private parsers may use builtins when a dominating caller catches and
  translates them; typed errors subclassing builtins are compliant.

#### S017 -- no raw exception disclosure

- File: `lint/rules/s017_no_raw_exception_disclosure.py`.
- Algorithm: track caught exception names and flag `str(exc)`, `repr(exc)`, or
  direct interpolation into public `ToolResult`, provider error/result,
  structured metadata, or user-facing message constructors.
- Edge: structured internal logging is allowed; stable error kind plus a bounded,
  explicitly sanitized provider response excerpt is allowed.

#### S018 -- priced-operation attempt propagation

- File: `lint/rules/s018_priced_operation_attempts.py`.
- Scope: `vidbyte/tools/builtins/operations/` results and clients.
- Algorithm: require every success/failure result derived from an HTTP response
  to pass `response.attempts` into `_executed_result`/`_failed_result` or the
  canonical pricing metadata builder.
- Edge: validation failures before any request use zero attempts explicitly.

#### S019 -- cancellation propagation

- File: `lint/rules/s019_cancellation_propagation.py`.
- Algorithm: in async functions, flag bare/`BaseException` handlers that do not
  immediately preserve cancellation, and flag `except CancelledError` handlers
  that neither re-raise nor convert cancellation at an explicitly owned task-group boundary.
- Edge: `except Exception` is not flagged because modern `CancelledError`
  inherits `BaseException`; broad-catch accountability remains a separate concern.

#### S020 -- README file-index parity

- File: `lint/rules/s020_readme_file_index_parity.py`.
- Algorithm: only for READMEs containing `## File Index`, parse backticked/table
  file entries and compare them with tracked direct children in the folder.
- Edge: generated files, `__pycache__`, private assets, and nested folder contents
  are excluded unless the existing index explicitly declares them.

#### S021 -- class-bound registry helpers

- File: `lint/rules/s021_class_bound_registry_helpers.py`.
- Scope: `vidbyte/lib/registries/*.py` and future declared registry directories.
- Algorithm: public helper functions must be static/class methods on the owning
  registry class; module-level public functions are flagged. Dunder exports and
  private parsing helpers remain allowed.
- Consequence: keeps related registry state and behavior discoverable from one class.

### 6.5 Existing Independent Policies

- `.semgrep/typed-mapping-boundary-policy.yml` continues to enforce typed Mapping
  boundary structure in `.github/workflows/static-policy.yml`.
- `scripts/check_context_write_paths.py` continues to enforce CWP001/CWP002/CWP004
  during the source gate.
- Neither policy is count-baselined by this change because both are already
  zero-tolerance gates.

## 7. Data Model Changes

None. `lint/baseline.json` is tooling metadata with a flat integer-count schema;
it does not affect runtime serialization or persisted data.

## 8. API Changes

None. The installed `vidbyte` package exports and runtime behavior are unchanged.
The repository gains a developer-only CLI, `python lint/run.py`, and the existing
CI CLI invokes it internally without changing its public arguments.

## 9. File Change Manifest

### Files to Create (39)

- `docs/design/sdk-agent-facing-lint-suite.md` -- this approved design.
- `lint/README.md` -- folder purpose, non-goals, commands, rule catalogue, and file index.
- `lint/__init__.py`
- `lint/run.py`
- `lint/baseline.json`
- `lint/mypy.ini`
- `lint/core/__init__.py`
- `lint/core/README.md` -- core folder responsibilities, non-goals, and file index.
- `lint/core/baseline.py`
- `lint/core/diagnostic.py`
- `lint/core/discovery.py`
- `lint/core/mypy.py`
- `lint/core/registry.py`
- `lint/core/report.py`
- `lint/core/ruff.py`
- `lint/core/runner.py`
- `lint/rules/__init__.py`
- `lint/rules/README.md` -- rule folder responsibilities, non-goals, and file index.
- `lint/rules/s001_python_correctness_foundation.py`
- `lint/rules/s002_exception_cause_chaining.py`
- `lint/rules/s003_strict_zip.py`
- `lint/rules/s004_timezone_aware_datetime.py`
- `lint/rules/s005_immutable_class_defaults.py`
- `lint/rules/s006_async_task_ownership.py`
- `lint/rules/s007_public_function_annotations.py`
- `lint/rules/s008_bounded_function_complexity.py`
- `lint/rules/s009_staged_mypy_contracts.py`
- `lint/rules/s010_transport_parity.py`
- `lint/rules/s011_raw_http_client_ownership.py`
- `lint/rules/s012_explicit_outbound_timeout.py`
- `lint/rules/s013_bounded_untrusted_responses.py`
- `lint/rules/s014_provider_model_registry_parity.py`
- `lint/rules/s015_public_export_integrity.py`
- `lint/rules/s016_typed_boundary_errors.py`
- `lint/rules/s017_no_raw_exception_disclosure.py`
- `lint/rules/s018_priced_operation_attempts.py`
- `lint/rules/s019_cancellation_propagation.py`
- `lint/rules/s020_readme_file_index_parity.py`
- `lint/rules/s021_class_bound_registry_helpers.py`

### Files to Modify (2)

- `pyproject.toml` -- pin Ruff and mypy in the dev extra.
- `scripts/run_ci.py` -- invoke `python lint/run.py` in the source gate.

### Files to Delete (0)

None.

## 10. Dependencies & External Services

- Add exact dev pins `ruff==0.16.4` and `mypy==2.3.1`.
- mypy uses `ignore_missing_imports` for optional third-party integrations; no
  stub package is added in this change.
- No new runtime dependency or external service. Lint must run offline after dev
  dependencies are installed.

## 11. Rollout & Deployment

1. Create a clean isolated worktree from updated `origin/main` and a dedicated
   feature branch.
2. Commit this design document before any implementation file.
3. Build the core runner/adapters, then implement and inspect S001-S021 in order.
4. Initialize baseline counts only after representative findings for each rule
   have been manually reviewed for scope and counterexamples.
5. Run with worktree source precedence:
   `$env:PYTHONPATH=(Get-Location).Path` on PowerShell or
   `PYTHONPATH=$(pwd)` on POSIX.
6. Run `python lint/run.py`, install `.[dev]`, run
   `python scripts/run_ci.py --stage source`, then the full
   `python scripts/run_ci.py` package gate.
7. Push, open a draft PR, monitor required GitHub checks until green, and remove
   the isolated worktree after the branch is safely pushed.

Rollback is a revert of the implementation commits: source CI stops invoking the
suite and the two dev pins can be removed. No data or API rollback is required.

## 12. Open Questions

No unresolved question blocks implementation. Decisions fixed by this design:

- Count-baseline all new suite rules, preserving existing zero-tolerance Semgrep
  and context-write-path policies separately.
- Run mypy across the complete package with missing-import tolerance rather than
  presenting a misleading narrow clean subset.
- Exclude ANN401, BLE001, B008, PLR0913, and exact-header checks.
- Enforce README parity only where a File Index already asserts completeness.
- Treat binary/provider response ceilings as required at untrusted ingestion
  boundaries first; broader provider response policy can ratchet independently.

## 13. Alternatives Considered

### Add only Ruff and mypy commands to CI

Rejected because repository-specific transport, registry, export, pricing, and
documentation contracts are not expressible by those analyzers, and raw tool
output lacks the repair guidance expected by coding agents.

### Put all semantic checks in one large policy script

Rejected because independent IDs, baselines, diagnostics, and focused commands
are necessary to decompose fixes and prevent one policy from masking another.

### Execute SDK imports to compare registries and exports

Rejected because lint must be side-effect-free and optional dependencies may be
absent. Static extraction is deterministic and catches broken import surfaces
before import execution can fail.

### Require a clean Ruff/mypy migration immediately

Rejected because the existing package has material debt. A ratchet blocks every
new regression now while allowing focused cleanup to lower counts over time.
