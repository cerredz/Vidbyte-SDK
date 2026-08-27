# Design Doc: Verifier Runtime — Built-in Verifiers (Test Suite, Database Query, Lean Proof)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-27
**Last Updated:** 2026-08-27

---

## 1. Overview

PR #349 shipped the eight-pillar verifier runtime with one generic, function-wrapping
`Verifier` implementation (`CallableVerifier`) and explicitly deferred every concrete,
production-grade `Verifier` subclass as future work ("the fifteen-item catalog from the
design conversation is future work" — `docs/design/verifier-runtime.md`, Non-Goals). This
doc adds the first three: `TestSuiteVerifier` (runs a test command and gates on the
fraction of tests that passed), `DatabaseQueryVerifier` (runs a read query and gates on
its result rows), and `LeanProofVerifier` (compiles a Lean4 proof file and gates on a
clean compile with no `sorry`). It updates the existing, open PR #349 in place rather than
opening a new PR.

---

## 2. Goals & Non-Goals

### Goals
- Ship `TestSuiteVerifier`, `DatabaseQueryVerifier`, and `LeanProofVerifier` as real,
  working `Verifier` subclasses with full method bodies, each carrying its own
  gating configuration.
- Add `VerifierKind.FORMAL_PROOF` (Lean proof checking is not a code-execution check —
  its pass/fail semantics and tooling differ from `CODE_EXECUTION`).
- Add `workspace_root: str | None` to `VerifierTarget` and thread it through every
  `VerifierTargetResolver` branch — every execution-based verifier needs a directory to
  run in, and `VerifierTarget` currently has no field for it even though
  `ResolutionContext.workspace_root` already carries it one layer up.
- Follow the repository's own established convention (`field-guide/vidbyte-sdk/
  strict-config-dataclasses.md`, and the "resolve review comments on PR #349" /
  "relocate every remaining dataclass" commits already on this branch) of keeping every
  validated data contract in `vidbyte/lib/dataclasses/verifier.py`, separate from the
  behavior classes that consume it. All three new `*Config` dataclasses go there.
- Convert `vidbyte/agents/runtimes/verifier/collection.py` into a
  `vidbyte/agents/runtimes/verifier/collection/` package so the three concrete verifiers
  have a home alongside the tiered-execution engine, per the explicit instruction to
  place them in a "collection" folder.
- Keep every existing import site (`from vidbyte.agents.runtimes.verifier.collection
  import VerifierCollection, VerifierCollectionParams`, and the ~15 other dotted
  references to this package) resolving unchanged.

### Non-Goals
- No new test files (per the `design-doc-no-tests` workflow). Existing CI, lint, and
  packaging gates still run and must stay green.
- No kind→constructor registry or YAML/declarative-config resolution for verifiers —
  already called out as separately deferred in `docs/design/verifier-runtime.md`
  ("out of scope until a registry is actually needed").
- `DatabaseQueryVerifier` supports only DB-API 2.0-shaped (SQL) connections. MongoDB and
  other non-SQL stores are out of scope for this PR (see Alternatives Considered).
- No `forbidden_axioms` scanning for `LeanProofVerifier` beyond the standard `sorry`
  diagnostic — a robust custom-axiom check needs Lean's `#print axioms` machinery, which
  is a larger, separate piece of work; shipping a fragile text-search version would be a
  half-implementation, not a minimal one.
- No changes to `gate.py`, `verdict.py`, `budget.py`, `ledger.py`, `feedback.py`,
  `repair.py`, or `runtime.py` — all three verifiers plug into the existing, unchanged
  aggregation (`VerdictStrategy`) and loop-control (`VerifierRuntimeGate`) layers.

---

## 3. Background & Context

This follows directly from an in-conversation design discussion about what a "verifier"
means in this runtime and where verifier-specific gating logic belongs. The conclusion:
`gate.py` decides what an aggregated verdict does to the agent loop (kind-agnostic by
design, per its own docstring); `verdict.py`'s `VerdictStrategy` decides how N verdicts
combine; and *how one verifier decides its own pass/fail* belongs entirely on that
verifier's own configuration — exactly the shape `CallableVerifier` already established
(`Verifier.__init__(self, params: VerifierParams)` plus a second, kind-specific
constructor argument). This doc's three verifiers follow that same shape.

Separately, while auditing this branch to write this doc, a peer session pushed two
commits (`e3b0bee2`, `c7481a68`) addressing live PR #349 review feedback: every
enum/dataclass that used to live in `types.py` — `VerifierKind`, `VerifierTarget`,
`VerifierParams`, etc. — now lives in `vidbyte/lib/dataclasses/verifier.py`, with
`types.py` reduced to `VerifierExecutionMode`/`GateTrigger`/`GateDecision` plus a
backward-compatible re-export of everything else. `VerifierCollectionParams` and
`VerifierRuntimeGateParams` were deliberately left in `collection.py`/`gate.py` — moving
`VerifierCollectionParams` would create a circular import, since it holds live `Verifier`
instances (`verifiers: tuple[Verifier, ...]`) and `verifier.py` already imports
`VerifierParams` from `lib/dataclasses/verifier.py`. This doc's plan already matched that
convention's spirit; the current state below reflects the branch as of `c7481a68`, not
the branch as it stood at the start of this design conversation.

---

## 4. Requirements

### Functional Requirements
1. `TestSuiteVerifier` runs a configured shell command, parses the JUnit XML report it
   produces, and passes only when the fraction of non-failing test cases is at or above
   `pass_fraction` (default `1.0`, i.e. all tests) **and** at least one test was
   collected — an empty test run must never read as a pass.
2. `TestSuiteVerifier` supports scoping the *gate* to a subset of the report
   (`scope_path`, matched by prefix against `classname`/`file`) independently of which
   tests the command actually ran, so a harness can run a whole suite but gate only on a
   subset.
3. `DatabaseQueryVerifier` executes one parameterized read query via a caller-supplied
   connection factory and passes only when every configured gate holds: exact/min/max row
   count, an expected value on a named/positional column of the first row, and/or a
   caller-supplied row-predicate callable. At least one gate must be configured.
4. `DatabaseQueryVerifier` never interpolates `query_params` into the query string — they
   are always bound through the DB-API `cursor.execute(query, params)` parameter
   mechanism, so a harness can safely scope a query using agent-influenced data (e.g. a
   value read from `VerifierTarget.submission`) without introducing SQL injection.
5. `LeanProofVerifier` runs a configured Lean invocation against a resolved `.lean` file
   (explicit `file_path`, or the first `.lean` entry in `target.file_paths`) and passes
   only when the process exits zero, and (when `forbid_sorry`, default `True`) the
   combined stdout/stderr contains no `sorry`-usage diagnostic, and (when
   `treat_warnings_as_failure`, default `False`) no `warning:` diagnostic at all.
6. `LeanProofVerifier.applicable()` returns `False` (so the verifier is skipped, not
   failed) when no workspace or no resolvable `.lean` file is available.
7. Each concrete verifier validates that its `VerifierParams.kind` matches the kind it
   implements (`CODE_EXECUTION`, `QUERY_EXECUTION`, `FORMAL_PROOF` respectively) at
   construction time, raising `ConfigurationError` otherwise.
8. `VerifierTarget.workspace_root` is populated from `ResolutionContext.workspace_root`
   by every `VerifierTargetResolver` mode except `CUSTOM` (whose caller-supplied resolver
   is responsible for its own `VerifierTarget` construction).
9. `from vidbyte.agents.runtimes.verifier.collection import VerifierCollection,
   VerifierCollectionParams` (and every other existing dotted reference into this
   package) continues to resolve unchanged after `collection.py` becomes a package.

### Non-Functional Requirements
- Subprocess calls (`TestSuiteVerifier`, `LeanProofVerifier`) and the blocking DB-API call
  (`DatabaseQueryVerifier`) all run via `asyncio.to_thread`, not directly on the event
  loop — `VerifierCollection` runs verifiers in the same tier concurrently via
  `asyncio.gather` under `PARALLEL_WITHIN_TIER`, and a blocking call inside `check()`
  would silently serialize them.
- No new required dependency. `TestSuiteVerifier` parses JUnit XML with the stdlib
  `xml.etree.ElementTree`. `DatabaseQueryVerifier` never imports a DB driver itself — the
  caller's `connection_factory` supplies an already-configured connection, mirroring
  `vidbyte/lib/providers`'s existing "no driver imported unless a caller opts in" shape.
  `LeanProofVerifier` shells out to an external `lean`/`lake` toolchain, which is not a
  Python dependency.
- A tool/process failure (missing binary, non-zero exit, missing report file) must never
  crash the run — `VerifierCollection._run_one` already converts any exception raised
  from `check()` into a failing `VerifierVerdict`, so these verifiers let such exceptions
  propagate naturally rather than swallowing them into a false pass.
- Diagnostics strings are capped (JUnit failing-test list capped at 10 names; Lean output
  capped at 1500 characters) so one badly-behaved check cannot flood downstream feedback
  rendering (`VerifierRuntimeFeedback`).

---

## 5. High-Level Design

```
VerifierTargetResolver.resolve()
        |
        v
  VerifierTarget (+ workspace_root, new field)
        |
        v
  VerifierCollection.run()  -- tiered, per-verifier applicable()/check()
        |                                  |                    |
        v                                  v                    v
TestSuiteVerifier.check()      DatabaseQueryVerifier.check()   LeanProofVerifier.check()
 subprocess -> JUnit XML         connection_factory -> rows      subprocess -> stdout/stderr
        |                                  |                    |
        +---------------- VerifierVerdict (passed, score, diagnostics) -----------------+
                                           |
                                           v
                      VerifierVerdictPolicy.aggregate()  (unchanged)
                                           |
                                           v
                         VerifierRuntimeGate.decide()  (unchanged)
```

Each concrete verifier is a `Verifier` subclass constructed with two arguments — the
existing `VerifierParams` (name/kind/tier/blocking/depends_on/timeout) plus a new,
kind-specific `*Config` dataclass carrying its gating knobs — mirroring the exact shape
`CallableVerifier(params, fn)` already established. This was chosen over subclassing
`VerifierParams` directly; see Alternatives Considered.

`vidbyte/agents/runtimes/verifier/collection.py` becomes a package:
`collection/base.py` holds the moved-verbatim `VerifierCollection`/
`VerifierCollectionParams`; `collection/test_suite.py`, `collection/database_query.py`,
and `collection/lean_proof.py` each hold one concrete verifier;
`collection/__init__.py` re-exports all five names so every existing import of
`vidbyte.agents.runtimes.verifier.collection` is unaffected.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/dataclasses/verifier.py`

**Type:** Modified

#### What it does
Gains one new `VerifierKind` member, one new `VerifierTarget` field, two small DB-API
`Protocol` types, and the three new `*Config` dataclasses — all validated in
`__post_init__` the same way every existing dataclass in this file is.

#### Interface / API
```python
class VerifierKind(str, Enum):
    ...
    FORMAL_PROOF = "formal_proof"  # new member


@dataclass(frozen=True, slots=True)
class VerifierTarget:
    mode: TargetResolutionMode
    text: str | None = None
    file_paths: tuple[str, ...] = ()
    diff: str | None = None
    submission: Mapping[str, Any] | None = None
    context_primitives: tuple["ContextItem", ...] = ()
    workspace_root: str | None = None  # new field


class DBAPICursor(Protocol):
    description: Sequence[tuple[Any, ...]] | None
    def execute(self, query: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> object: ...
    def fetchall(self) -> Sequence[Any]: ...


class DBAPIConnection(Protocol):
    def cursor(self) -> DBAPICursor: ...
    def close(self) -> None: ...


UNSET: Any = object()  # sentinel: "no expected_value configured" (None is a legal DB value)


@dataclass(frozen=True, slots=True)
class TestSuiteVerifierConfig:
    command: tuple[str, ...]
    report_path: str
    pass_fraction: float = 1.0
    scope_path: str | None = None
    env: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class DatabaseQueryVerifierConfig:
    connection_factory: Callable[[], DBAPIConnection]
    query: str
    query_params: tuple[Any, ...] | Mapping[str, Any] = ()
    expected_row_count: int | None = None
    min_row_count: int | None = None
    max_row_count: int | None = None
    expected_value: Any = UNSET
    expected_column: str | int = 0
    row_matcher: Callable[[tuple[Any, ...]], bool] | None = None


@dataclass(frozen=True, slots=True)
class LeanProofVerifierConfig:
    lean_command: tuple[str, ...] = ("lake", "env", "lean")
    file_path: str | None = None
    forbid_sorry: bool = True
    treat_warnings_as_failure: bool = False
```

#### Logic / Algorithm
- `TestSuiteVerifierConfig.__post_init__`: `command` non-empty, `report_path` non-blank,
  `pass_fraction` in `[0.0, 1.0]` — same shape as every existing range/non-empty check in
  this file (e.g. `VerifierVerdictPolicyParams._validate_threshold_range`).
- `DatabaseQueryVerifierConfig.__post_init__`: `query` non-blank; every provided row-count
  bound is `>= 0`; `min_row_count <= max_row_count` when both given; at least one of
  {`expected_row_count`, `min_row_count`, `max_row_count`, `expected_value is not UNSET`,
  `row_matcher`} must be set, else the verifier can never fail anything and the config is
  a mistake.
- `LeanProofVerifierConfig.__post_init__`: `lean_command` non-empty.

#### Edge Cases & Error Handling
- All three raise `ConfigurationError` (matching every other dataclass in this file) at
  construction time, not at `check()` time.

---

### 6.2 `vidbyte/agents/runtimes/verifier/target.py`

**Type:** Modified

#### What it does
Threads `context.workspace_root` into every `VerifierTarget` this resolver constructs.

#### Logic / Algorithm
Each of `_resolve_final_output_text`, `_resolve_workspace_files` (both the early-return
and matched-files branches), `_resolve_workspace_diff` (both branches), and
`_resolve_structured_submission` adds `workspace_root=context.workspace_root` to its
`VerifierTarget(...)` call. `resolve()`'s context-primitives merge (lines constructing a
second `VerifierTarget` when primitives were selected) adds `workspace_root=
base.workspace_root`. The `CUSTOM` branch is untouched — it returns
`self.params.custom_resolver(context)` directly, so a custom resolver is responsible for
its own `VerifierTarget`, same as today for every other field.

#### Edge Cases & Error Handling
- `context.workspace_root` is already `str | None` on `ResolutionContext`; no new
  validation needed, this is a pure pass-through.

---

### 6.3 `vidbyte/agents/runtimes/verifier/collection/` (new package, replaces `collection.py`)

**Type:** New (package), replacing an existing file

#### What it does
`collection/base.py` is `collection.py`'s current content, moved verbatim (no logic
change — `VerifierCollection`/`VerifierCollectionParams` are untouched by this PR).
`collection/__init__.py` re-exports `VerifierCollection`, `VerifierCollectionParams`,
`TestSuiteVerifier`, `DatabaseQueryVerifier`, `LeanProofVerifier`.

#### Edge Cases & Error Handling
- N/A — pure move plus additive re-exports; `git mv` preserves file history for `base.py`.

---

### 6.4 `vidbyte/agents/runtimes/verifier/collection/test_suite.py`

**Type:** New

#### What it does
`TestSuiteVerifier(Verifier)` — runs a test command, parses its JUnit XML report, gates
on `pass_fraction`.

#### Interface / API
```python
class TestSuiteVerifier(Verifier):
    def __init__(self, params: VerifierParams, config: TestSuiteVerifierConfig) -> None: ...
    def applicable(self, target: VerifierTarget) -> bool: ...  # False when target.workspace_root is None
    async def check(self, target: VerifierTarget) -> VerifierVerdict: ...
```

#### Logic / Algorithm
1. `_validate_kind()` in `__init__`: raise `ConfigurationError` unless
   `params.kind is VerifierKind.CODE_EXECUTION`.
2. `check()`: run `self._config.command` via `asyncio.to_thread(subprocess.run, ...,
   cwd=target.workspace_root, env={**os.environ, **(config.env or {})}, check=False)`
   (non-zero exit is an expected "tests failed" signal, not an error).
3. Parse `os.path.join(target.workspace_root, config.report_path)` with
   `xml.etree.ElementTree`; iterate `<testcase>` elements; a case counts as failed when it
   has a `<failure>` or `<error>` child; when `scope_path` is set, only count cases whose
   `classname` (dots replaced with `/`) or `file` attribute starts with it.
4. `fraction_passed = (total - failed) / total if total else 0.0`; `passed = total > 0 and
   fraction_passed >= config.pass_fraction`.
5. Return `VerifierVerdict(score=fraction_passed, diagnostics=<"N/M passed" plus up to 10
   failing test names>, ...)`.

#### Edge Cases & Error Handling
- Zero collected tests: `passed=False` explicitly (never a silent pass), diagnostics say
  so plainly.
- Missing JUnit report file after the command runs: `FileNotFoundError` propagates out of
  `check()`, which `VerifierCollection._run_one` already converts into a failing verdict.
- Missing test-runner binary: `subprocess.run` raises `FileNotFoundError`; same handling.

---

### 6.5 `vidbyte/agents/runtimes/verifier/collection/database_query.py`

**Type:** New

#### What it does
`DatabaseQueryVerifier(Verifier)` — runs one parameterized read query, gates on its rows.

#### Interface / API
```python
class DatabaseQueryVerifier(Verifier):
    def __init__(self, params: VerifierParams, config: DatabaseQueryVerifierConfig) -> None: ...
    async def check(self, target: VerifierTarget) -> VerifierVerdict: ...
```

#### Logic / Algorithm
1. `_validate_kind()`: raise `ConfigurationError` unless `params.kind is
   VerifierKind.QUERY_EXECUTION`.
2. `check()` calls `asyncio.to_thread` over a sync helper that: opens `conn =
   config.connection_factory()`, runs `cursor.execute(config.query,
   config.query_params)`, returns `tuple(cursor.fetchall())`, and always `conn.close()`s
   in a `finally`.
3. Evaluates every configured gate independently against the returned rows (row count
   bounds; `expected_value` against `expected_column` of the first row, reading a mapping
   row by key or a sequence row by index; `row_matcher(rows)`), collecting one diagnostic
   message per failed gate.
4. `passed = not failures`; `score=None` (row-gate results are boolean, not fractional).

#### Edge Cases & Error Handling
- `expected_value` configured but zero rows returned: a specific failure message, not an
  `IndexError`.
- Connection/driver errors (bad credentials, unreachable host) propagate naturally into
  `VerifierCollection`'s existing exception-to-verdict handling.
- `query_params` is always passed to `cursor.execute` as a bound parameter, never
  string-formatted into `query` — the mechanism that keeps this safe even when a harness
  scopes the query using agent-influenced data.

---

### 6.6 `vidbyte/agents/runtimes/verifier/collection/lean_proof.py`

**Type:** New

#### What it does
`LeanProofVerifier(Verifier)` — compiles a `.lean` file, gates on a clean compile with no
`sorry`.

#### Interface / API
```python
class LeanProofVerifier(Verifier):
    def __init__(self, params: VerifierParams, config: LeanProofVerifierConfig) -> None: ...
    def applicable(self, target: VerifierTarget) -> bool: ...  # False when no file resolves
    async def check(self, target: VerifierTarget) -> VerifierVerdict: ...
```

#### Logic / Algorithm
1. `_validate_kind()`: raise `ConfigurationError` unless `params.kind is
   VerifierKind.FORMAL_PROOF`.
2. `_resolve_file(target)`: `config.file_path` if set, else the first entry in
   `target.file_paths` ending in `.lean`, else `None`.
3. `applicable()`: `target.workspace_root is not None and self._resolve_file(target) is
   not None`.
4. `check()`: `asyncio.to_thread(subprocess.run, (*config.lean_command, file_path),
   cwd=target.workspace_root, capture_output=True, text=True, check=False)`.
5. `output = result.stdout + result.stderr`; `sorry_found = "uses 'sorry'" in output`;
   `has_warning = "warning:" in output`; `passed = result.returncode == 0 and (not
   sorry_found if config.forbid_sorry else True) and (not has_warning if
   config.treat_warnings_as_failure else True)`.
6. `score=None` (a proof compiling is binary, not fractional).

#### Edge Cases & Error Handling
- Missing `lean`/`lake` binary: `FileNotFoundError` propagates to a failing verdict via
  the existing collection-level handling.
- **Assumption, flagged for verification against a real toolchain:** Lean4's CLI is
  assumed to emit its `sorry`-usage diagnostic containing the substring `"uses 'sorry'"`
  and warnings containing `"warning:"`, and either stream may carry them — this reads
  both stdout and stderr combined rather than assuming one. This could not be verified
  against an installed Lean toolchain in this environment; see Open Questions.

---

### 6.7 `vidbyte/agents/runtimes/verifier/__init__.py`

**Type:** Modified

#### What it does
Adds `TestSuiteVerifier`, `DatabaseQueryVerifier`, `LeanProofVerifier` (from
`.collection`) and `TestSuiteVerifierConfig`, `DatabaseQueryVerifierConfig`,
`LeanProofVerifierConfig` (from `vidbyte.lib.dataclasses.verifier`) to the package's
public surface and `__all__`, following the exact pattern `VerifierRuntimeBudgetParams`
already uses.

---

## 7. Data Model Changes

N/A — this is the `vidbyte-sdk` Python SDK, not the `vidbyte` application; there is no
database schema owned by this repository. `DatabaseQueryVerifier` reads from a database
the *harness developer* configures via `connection_factory`; the SDK itself owns no
schema for it.

---

## 8. API Changes

N/A — no HTTP surface. This PR only adds Python classes to the SDK's public package
surface (`vidbyte.agents.runtimes.verifier`).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/verifier-runtime-builtin-verifiers.md` | This design doc |
| DELETE | `vidbyte/agents/runtimes/verifier/collection.py` | Replaced by the `collection/` package |
| CREATE | `vidbyte/agents/runtimes/verifier/collection/__init__.py` | Re-exports base + 3 new verifiers |
| CREATE | `vidbyte/agents/runtimes/verifier/collection/base.py` | `VerifierCollection`/`VerifierCollectionParams`, moved verbatim |
| CREATE | `vidbyte/agents/runtimes/verifier/collection/test_suite.py` | `TestSuiteVerifier` |
| CREATE | `vidbyte/agents/runtimes/verifier/collection/database_query.py` | `DatabaseQueryVerifier` |
| CREATE | `vidbyte/agents/runtimes/verifier/collection/lean_proof.py` | `LeanProofVerifier` |
| MODIFY | `vidbyte/lib/dataclasses/verifier.py` | `FORMAL_PROOF` kind, `workspace_root` field, DB-API protocols, 3 `*Config` dataclasses |
| MODIFY | `vidbyte/agents/runtimes/verifier/target.py` | Thread `workspace_root` through every resolved `VerifierTarget` |
| MODIFY | `vidbyte/agents/runtimes/verifier/__init__.py` | Export the 3 new verifiers + 3 new configs |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| JUnit XML report | produced by caller's own test command | `TestSuiteVerifier` input | Low — stdlib parser, no new package dependency |
| DB-API 2.0 connection | caller-supplied via `connection_factory` | `DatabaseQueryVerifier` input | Low — SDK imports no driver; caller's driver choice is out of this PR's control |
| `lean`/`lake` CLI | external toolchain, not a Python package | `LeanProofVerifier` input | Medium — output-format assumption unverified against a real install; missing binary degrades safely to a failing verdict, not a crash |

---

## 11. Rollout & Deployment

- Fully additive: three new opt-in classes plus one new enum member and one new,
  default-`None` dataclass field. No existing behavior changes for any harness that does
  not construct one of these three verifiers.
- No feature flag needed — nothing is wired to run by default; a developer must
  explicitly construct `TestSuiteVerifier`/`DatabaseQueryVerifier`/`LeanProofVerifier` and
  add it to a `VerifierCollectionParams.verifiers` tuple.
- Not a breaking change. Rollback is a plain revert of the new commits.
- This PR updates the existing, open `feat/verifier-runtime` branch (PR #349) directly;
  no new PR is opened.

---

## 12. Open Questions

- [ ] Lean4's exact CLI diagnostic format (`"uses 'sorry'"`, `"warning:"`, which
  stream) is assumed from general Lean4 convention and could not be verified against an
  installed toolchain in this environment. Worth a quick manual check against the team's
  actual `lake`/`lean` version before this verifier is used in a real harness; the marker
  strings in `lean_proof.py` are the only thing that would need adjusting.
- [ ] Whether `TestSuiteVerifier` should also accept `pytest --json-report` output as an
  alternative to JUnit XML. Deferred — JUnit XML was chosen because it's the
  cross-language standard (pytest, jest, `go test` via `gotestsum`, etc. all support it),
  keeping the verifier test-runner-agnostic rather than Python-specific.
- [ ] `DatabaseQueryVerifier`'s Mongo/non-SQL support is intentionally out of scope; if a
  concrete need appears, it likely wants its own `VerifierKind` (a `find()`-shaped query
  isn't DB-API-shaped) rather than forcing it through this same class.

---

## 13. Alternatives Considered

### Alternative 1: Kind-specific `Params` as `VerifierParams` subclasses (inheritance)
- What: `TestSuiteVerifierParams(VerifierParams)` adding `command`, `pass_fraction`, etc.
  directly as extra dataclass fields.
- Why rejected: `VerifierParams`'s fields after `name`/`kind` all carry defaults, so
  Python's dataclass field-ordering rule would force every subclass-added field —
  including logically-required ones like `command` — to carry a default too, fighting the
  type system instead of expressing intent. Composition
  (`Verifier.__init__(self, params: VerifierParams, config: SomeConfig)`) has no such
  constraint and is already the shape `CallableVerifier(params, fn)` established.

### Alternative 2: A sibling `kinds/` folder instead of converting `collection.py`
- What: leave `collection.py` as a file and add `vidbyte/agents/runtimes/verifier/kinds/`
  for the concrete verifiers.
- Why rejected: the request was specifically to place these verifiers in a "collection"
  folder. Converting `collection.py` into `collection/__init__.py` + `collection/base.py`
  satisfies that literally, keeps every existing `from
  vidbyte.agents.runtimes.verifier.collection import VerifierCollection,
  VerifierCollectionParams` resolving unchanged, and reads naturally as "the collection of
  verifiers the SDK ships" rather than just the tiered-execution engine.

### Alternative 3: Raw SQL string interpolation for `DatabaseQueryVerifier`
- What: format `query_params` directly into the query string for simplicity.
- Why rejected: the moment a harness scopes a query using a value read from
  `VerifierTarget.submission` (agent-influenced data), string interpolation is a SQL
  injection vector. DB-API parameter binding (`cursor.execute(query, params)`) is the
  standard, zero-cost-to-use mechanism and was chosen instead.

### Alternative 4: `pytest --json-report` instead of JUnit XML for `TestSuiteVerifier`
- What: parse pytest's own JSON report plugin output.
- Why rejected: ties the verifier to Python/pytest specifically. JUnit XML is emitted by
  nearly every mainstream test runner across languages, keeping this verifier usable for
  agents doing non-Python work too (see Open Questions).

---

## Canonical CI Gate (Vidbyte SDK)

```bash
python -m pip install -e ".[dev]"
PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source   # from a worktree
python scripts/run_ci.py --stage package                    # no PYTHONPATH
python scripts/run_ci.py                                    # full pipeline before push
python lint/run.py                                          # focus: --rule S010; --all for every finding
```
