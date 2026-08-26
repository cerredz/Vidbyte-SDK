# Design Doc: SDK Lint Suite Foundation — Python Correctness Rule (S001)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-26
**Last Updated:** 2026-08-26

---

## 1. Overview

Add the Vidbyte SDK's first lint tool: a small `lint/` package that runs Ruff
once against tracked `vidbyte/` source with a fixed, minimal selector set
(pyflakes `F`, import-placement `E4`, statement-correctness `E7`, and
parser/runtime `E9`), diagnoses every finding in agent-facing prose, and
compares the count against a frozen `lint/baseline.json` so the gate fails
only on new debt. It becomes part of `python scripts/run_ci.py --stage
source`, running before pytest.

This PR implements exactly one rule — S001, "Python correctness foundation"
— plus the runner/adapter/baseline scaffolding needed to execute it. It does
not implement mypy integration, transport/registry/export contract rules, or
any of the other rule ideas on record; those are explicitly deferred.

---

## 2. Goals & Non-Goals

### Goals

- Run Ruff exactly once per invocation against tracked `vidbyte/**/*.py`,
  scoped to selectors `F`, `E4`, `E7`, `E9`.
- Turn every finding into a diagnostic with a substantive summary, impact,
  and repair (per the repo's `diagnostic-context.md` field-guide entry), not
  a bare rule code and line number.
- Freeze existing debt in `lint/baseline.json`; fail the run only when a
  rule's finding count exceeds its baseline, or when a registered rule has
  no baseline entry (or vice versa).
- Wire the suite into `scripts/run_ci.py --stage source`, ahead of pytest.
- Pin an exact Ruff version in the `dev` extra so local runs and CI resolve
  the same analyzer.
- Shape the runner/registry/adapter split so a second rule (a future S002)
  is one new rule module plus a registry entry, not a rewrite.

### Non-Goals

- No mypy integration or staged type-contract ratchet (a separate future rule).
- No transport parity, HTTP client ownership, timeout, response-size,
  registry parity, export integrity, typed-boundary-error, exception
  disclosure, priced-operation, cancellation, README-index, or
  registry-helper rules. These were scoped in a prior, broader, unimplemented
  draft (`docs/design/sdk-agent-facing-lint-suite.md`, untracked in the
  canonical checkout as of this writing) and remain out of scope here; see
  Section 13.
- No ban on broad `except Exception` (Ruff's `BLE001`), FastAPI-style mutable
  call defaults (`B008`), long parameter lists (`PLR0913`), or any selector
  outside `F`/`E4`/`E7`/`E9`. The codebase's usage-tracking code
  (`vidbyte/agents/pricing/tracker.py`, `vidbyte/agents/runtime.py`)
  deliberately catches broad exceptions to keep a metering bug from crashing
  a host agent run; a correctness rule must not fight that pattern.
- No autofix, formatter rollout (`ruff format`), or global style rewrite.
- No new pytest test files (per this workflow's "no tests" scope). Verification
  is the lint tool's own focused commands plus the existing CI gates.
- No change to runtime behavior, public API, or packaging contents.

---

## 3. Background & Context

`vidbyte-sdk` has no lint tooling today — `pyproject.toml` has no
`[tool.ruff]` section, and `scripts/run_ci.py --stage source` runs only
`compileall`, a custom `check_context_write_paths.py`, and `pytest`. A prior
session apparently scoped a much larger 21-rule suite
(`docs/design/sdk-agent-facing-lint-suite.md`) covering correctness, mypy,
transport parity, registry parity, export integrity, and several other
SDK-specific contracts, but it was never implemented — no `lint/` directory
exists in the canonical checkout, and the file itself is untracked. This PR
does not implement that plan; it implements only its first rule (there
labeled S001) so the immediate ask — "the Python correctness rules, only" —
ships as a real, running gate, and leaves the rest as explicit, named future
work rather than silently absorbing or discarding that prior scoping.

The repo's field guide (`field-guide/vidbyte-sdk/`) sets three constraints
this design follows directly: `class-bound-helpers.md` requires related free
functions to live as `@staticmethod` methods on one named class rather than a
free-function module; `diagnostic-context.md` requires lint/analyzer output
to explain the protected boundary, caller-visible consequence, canonical
repair, and rejected shortcuts in full sentences; and
`local-ci-verification.md` documents that running any CI stage from a
worktree requires `PYTHONPATH=<worktree>` for the source stage (because the
existing editable install resolves `vidbyte` to the canonical checkout) and
no `PYTHONPATH` for the package stage (because a leaked value makes pip skip
installing the freshly built wheel).

---

## 4. Requirements

### Functional Requirements

1. `python lint/run.py` scans tracked `.py` files under `vidbyte/` and runs
   Ruff once with `--select F,E4,E7,E9 --isolated --output-format json
   --exit-zero`.
2. Findings are grouped by the one registered rule (`S001`) whose selector
   prefixes they match.
3. `lint/baseline.json` holds a sorted `{rule_id: count}` mapping. The run
   fails (nonzero exit) when a rule's finding count exceeds its baseline
   entry, when a registered rule has no baseline entry, or when the baseline
   has an entry for a rule that is not registered.
4. `--update-baseline` recomputes and writes the current per-rule counts,
   always exiting 0.
5. `--rule S001` restricts the run to one rule; omitting it runs every
   registered rule.
6. `--format json` emits a machine-readable report; the default is human
   text with the WHAT HAPPENED / WHY THIS IS BLOCKED / HOW TO FIX / VERIFY
   diagnostic shape per finding.
7. `--all` prints every finding for the selected rule(s); without it, output
   is capped at 20 findings per rule with a count of the remainder.
8. A Ruff subprocess failure to start, or unparsable JSON output, fails the
   run with the attempted command, working directory, and captured
   stderr — never a silent empty result.
9. `scripts/run_ci.py`'s `run_source()` calls `python lint/run.py` before
   `pytest`, using the same `_run_command` helper (inheriting its
   `PYTHONDONTWRITEBYTECODE` and caller-provided `PYTHONPATH`).
10. `pyproject.toml`'s `dev` extra pins an exact Ruff version.

### Non-Functional Requirements

- Full run targets under 10 seconds on a warm checkout (Ruff itself is
  sub-second; this is dominated by process startup).
- Report ordering is stable: by rule ID, then file path, then line, then
  column.
- No shell-specific command strings; works on Windows and POSIX (the repo's
  existing `_run_command` pattern already handles this).
- The lint tool never imports or executes `vidbyte` package modules — it
  only reads source text and parses Ruff's own JSON output.
- Every public class/function follows the repo's one-line-signature-plus-
  comment convention and the `scripts/`-style file header used by
  `scripts/run_ci.py`.

---

## 5. High-Level Design

```
tracked vidbyte/**/*.py --> SourceCatalog.python_files()
                                   |
                                   v
                          RuffAdapter.run(files, selectors)
                                   |
                                   v
                       tuple[RuffFinding, ...] (parsed JSON)
                                   |
                                   v
                 RuleRegistry -> [PythonCorrectnessFoundationRule]
                                   |
                                   v
                 each rule.collect(findings) -> tuple[Finding, ...]
                                   |
                                   v
        BaselineStore.evaluate(rule_id, baseline_count, len(findings))
                                   |
                                   v
                 RunReport (per-rule verdict + findings) --> DiagnosticRenderer
                                   |
                                   v
                      stdout (text or json) + process exit code
```

`LintRunner` (in `lint/core/runner.py`) is the only component that knows the
end-to-end order. It asks `SourceCatalog` for files, asks `RuffAdapter` to
run Ruff exactly once with the union of every registered rule's selectors
(today, just S001's four), asks each registered rule to `collect` its slice
of the findings, asks `BaselineStore` for a verdict per rule, and hands the
result to `DiagnosticRenderer` or the JSON encoder depending on
`--format`. Adding a second Ruff-backed rule later means adding one more
`lint/rules/sNNN_*.py` module and registering it — the adapter, baseline, and
runner do not change.

---

## 6. Detailed Design

### 6.1 `lint/core/discovery.py` — `SourceCatalog`

**File(s):** `lint/core/discovery.py` (new)
**Type:** New file

#### What it does
Lists the tracked Python files the suite is allowed to scan, so untracked
scratch files and build output are never silently included or excluded by
accident.

#### Interface / API
```python
class SourceCatalog:
    @staticmethod
    def python_files(repository_root: Path, package_root: Path) -> tuple[Path, ...]: ...
```

#### Logic / Algorithm
1. Run `git ls-files -z` from `repository_root`.
2. Keep entries under `package_root` (i.e. `vidbyte/`) whose suffix is `.py`.
3. Drop any path containing a `__pycache__` component.
4. Return the sorted tuple of absolute paths.

#### Edge Cases & Error Handling
- `git` not on PATH, or `repository_root` not a git checkout: raise
  `LintConfigurationError` naming the attempted command and directory — this
  mirrors `CiPipeline._run_command`'s existing `FileNotFoundError` handling
  in `scripts/run_ci.py`, not a new error-handling style.
- Zero matching files: return an empty tuple; the runner treats that as "no
  findings possible" rather than an error, since a partial checkout is a
  valid (if unusual) state.

---

### 6.2 `lint/core/ruff.py` — `RuffAdapter` and `RuffFinding`

**File(s):** `lint/core/ruff.py` (new)
**Type:** New file

#### What it does
Runs the pinned `ruff` once as a subprocess against the discovered files with
a selector union, and parses its JSON output into typed findings.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class RuffFinding:
    code: str
    file: Path
    line: int
    column: int
    message: str

class RuffAdapter:
    @staticmethod
    def run(package_root: Path, selectors: tuple[str, ...]) -> tuple[RuffFinding, ...]: ...
```

#### Logic / Algorithm
1. Build `[sys.executable, "-m", "ruff", "check", str(package_root),
   "--isolated", "--output-format", "json", "--exit-zero", "--select",
   ",".join(selectors)]`.
2. Run it with `subprocess.run(..., capture_output=True, text=True)`; Ruff's
   own exit code is ignored because `--exit-zero` makes it always 0 when
   Ruff itself ran successfully — a nonzero exit means Ruff failed to run at
   all (bad selector, missing interpreter), which is a hard error.
3. Parse `stdout` as JSON (a list of Ruff result objects); map each entry's
   `code`, `filename`, `location.row`, `location.column`, and `message` onto
   `RuffFinding`.
4. Sort the tuple by `(file, line, column)`.

#### Edge Cases & Error Handling
- Nonzero exit or non-JSON `stdout`: raise `LintAnalyzerError` carrying the
  full command, cwd, exit code, and captured stderr — the same shape
  `scripts/run_ci.py`'s `_run_command` already uses for `CalledProcessError`,
  so a coding agent sees one familiar failure shape across both tools.
- Empty `stdout` (no findings): return an empty tuple, not an error.
- `--isolated` is mandatory so a contributor's local Ruff config, or a future
  unrelated `pyproject.toml` `[tool.ruff]` section, cannot silently change
  what this gate checks.

---

### 6.3 `lint/core/diagnostic.py` — `Finding`, `RuleDiagnostic`, `DiagnosticRenderer`

**File(s):** `lint/core/diagnostic.py` (new)
**Type:** New file

#### What it does
Holds one rule's typed finding shape and renders it into the agent-facing
prose the field guide requires, or into a JSON-safe mapping.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    code: str
    file: Path
    line: int
    column: int
    message: str

@dataclass(frozen=True, slots=True)
class RuleDiagnostic:
    summary: str
    impact: str
    repair: str
    verify_command: str

class DiagnosticRenderer:
    @staticmethod
    def render_text(finding: Finding, diagnostic: RuleDiagnostic) -> str: ...
    @staticmethod
    def render_json(finding: Finding) -> dict[str, object]: ...
```

#### Logic / Algorithm
- `render_text` produces four labeled sections: `WHAT HAPPENED` (the finding
  location plus `diagnostic.summary`), `WHY THIS IS BLOCKED`
  (`diagnostic.impact`), `HOW TO FIX` (`diagnostic.repair`), and `VERIFY`
  (`diagnostic.verify_command`).
- `render_json` returns a flat mapping of the `Finding` fields only; the
  rule's static diagnostic text is included once at the rule level in JSON
  output, not repeated per finding, to keep `--format json` output compact.

#### Edge Cases & Error Handling
- None beyond formatting; this class never fails, since it only stringifies
  already-validated data.

---

### 6.4 `lint/core/baseline.py` — `LintVerdict` and `BaselineStore`

**File(s):** `lint/core/baseline.py` (new)
**Type:** New file

#### What it does
Loads/saves `lint/baseline.json` and decides, per rule, whether the current
finding count is clean, holding steady, improved, or a regression.

#### Interface / API
```python
class LintVerdict(str, Enum):
    CLEAN = "clean"
    RATCHETED = "ratcheted"
    IMPROVED = "improved"
    REGRESSED = "regressed"
    ERRORED = "errored"

class BaselineStore:
    @staticmethod
    def load(path: Path) -> dict[str, int]: ...
    @staticmethod
    def save(path: Path, counts: dict[str, int]) -> None: ...
    @staticmethod
    def evaluate(baseline_count: int, actual_count: int) -> LintVerdict: ...
```

#### Logic / Algorithm
- `load`/`save` read/write a sorted-key JSON mapping with a trailing
  newline, matching the repo's existing formatting habits.
- `evaluate`: `actual_count > baseline_count` → `REGRESSED`;
  `actual_count < baseline_count` → `IMPROVED`; `actual_count ==
  baseline_count == 0` → `CLEAN`; `actual_count == baseline_count > 0` →
  `RATCHETED`.
- The runner (6.6), not this class, is responsible for the separate
  "missing/stale baseline key" failure, since that is a registry/baseline
  set-membership question rather than a per-rule count comparison.

#### Edge Cases & Error Handling
- Missing `lint/baseline.json`: `load` returns an empty mapping rather than
  raising, so `--update-baseline` can create the file from nothing on first
  run.
- Malformed JSON: raise `LintConfigurationError` naming the file and the
  parse error.

---

### 6.5 `lint/core/registry.py` — `RuleRegistry`

**File(s):** `lint/core/registry.py` (new)
**Type:** New file

#### What it does
Holds the fixed list of registered rules and rejects a duplicate ID at
import time rather than at run time.

#### Interface / API
```python
class RuleRegistry:
    @staticmethod
    def all_rules() -> tuple[type[LintRule], ...]: ...
    @staticmethod
    def by_id(rule_id: str) -> type[LintRule]: ...
```

`LintRule` (in `lint/core/rule.py`, new, small) is a `Protocol` with
`rule_id: ClassVar[str]`, `ruff_selectors: ClassVar[tuple[str, ...]]`,
`diagnostic() -> RuleDiagnostic`, and `collect(findings: tuple[RuffFinding,
...]) -> tuple[Finding, ...]`.

#### Logic / Algorithm
- `all_rules()` returns a fixed tuple literal, `(PythonCorrectnessFoundationRule,)`
  today; adding S002 means appending one entry.
- `by_id` raises `LintConfigurationError` listing every valid ID when asked
  for an unregistered one, so `--rule` typos are self-diagnosing.
- A module-level assertion at import time (`len({r.rule_id for r in
  _RULES}) == len(_RULES)`) turns an accidental duplicate ID into an
  immediate import failure.

#### Edge Cases & Error Handling
- N/A beyond the above; this is a fixed, small, compile-time-checked list.

---

### 6.6 `lint/core/runner.py` — `LintRunner`

**File(s):** `lint/core/runner.py` (new)
**Type:** New file

#### What it does
Orchestrates discovery, the single Ruff invocation, per-rule collection,
baseline comparison, and report assembly.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class RuleOutcome:
    rule_id: str
    verdict: LintVerdict
    baseline_count: int
    actual_count: int
    findings: tuple[Finding, ...]

@dataclass(frozen=True, slots=True)
class RunReport:
    outcomes: tuple[RuleOutcome, ...]
    stale_baseline_keys: tuple[str, ...]
    missing_baseline_keys: tuple[str, ...]

    @property
    def passed(self) -> bool: ...

class LintRunner:
    def __init__(self, repository_root: Path, package_root: Path) -> None: ...
    def run(self, *, rule_ids: tuple[str, ...] | None) -> RunReport: ...
```

#### Logic / Algorithm
1. Resolve the rule set: `rule_ids` if given, else every registered rule.
2. `SourceCatalog.python_files(...)` (used for the empty-checkout edge case
   and to fail fast if `package_root` does not exist).
3. Union every selected rule's `ruff_selectors`, call `RuffAdapter.run` once.
4. For each selected rule: `finding_tuples = rule.collect(all_ruff_findings)`,
   wrap each into a `Finding` with `rule_id` attached, load the baseline
   count for that rule (or note it as a missing key), and call
   `BaselineStore.evaluate`.
5. Compute `stale_baseline_keys` as baseline keys with no matching selected
   rule, restricted to the *full* registry (not just `rule_ids`), so running
   `--rule S001` never reports S002's future baseline key as stale.
6. `RunReport.passed` is `True` only when every outcome's verdict is
   `CLEAN`/`RATCHETED`/`IMPROVED` and both stale/missing key tuples are empty.

#### Edge Cases & Error Handling
- Any exception raised by a rule's `collect` is caught by the runner,
  converted into an `ERRORED` outcome carrying the exception's `repr`, and
  fails the run — a broken rule must never be indistinguishable from a clean
  one, and must never crash the whole CLI without a diagnosis.

---

### 6.7 `lint/rules/s001_python_correctness_foundation.py` — `PythonCorrectnessFoundationRule`

**File(s):** `lint/rules/s001_python_correctness_foundation.py` (new)
**Type:** New file

#### What it does
Declares the S001 rule: Ruff selectors `F`, `E4`, `E7`, `E9`, and the
agent-facing diagnostic text for any finding in that selector union.

#### Interface / API
```python
class PythonCorrectnessFoundationRule:
    rule_id: ClassVar[str] = "S001"
    ruff_selectors: ClassVar[tuple[str, ...]] = ("F", "E4", "E7", "E9")

    @staticmethod
    def diagnostic() -> RuleDiagnostic: ...
    @staticmethod
    def collect(findings: tuple[RuffFinding, ...]) -> tuple[RuffFinding, ...]: ...
```

#### Logic / Algorithm
- `collect` filters `findings` to those whose `code` starts with any of
  `ruff_selectors` (e.g. `F401` matches `F`; `E402` matches `E4`; `E722`
  matches `E7`; `E999` matches `E9`).
- `diagnostic()` returns the fixed `RuleDiagnostic` described in Section 3's
  background: summary names the four selector families in plain language;
  impact distinguishes "hides a real bug" (undefined name, bare except)
  from "actively misleads a reader" (unused import/variable); repair states
  the concrete fix per code family and explicitly rejects `# noqa`
  suppression as a non-fix for this rule, since every code in this union is
  an objective defect, not a style judgment call.

#### Edge Cases & Error Handling
- None; this module is pure data plus a filter.

---

### 6.8 `lint/run.py` — CLI entry point

**File(s):** `lint/run.py` (new)
**Type:** New file

#### What it does
The `python lint/run.py` command contributors and CI invoke; mirrors
`scripts/run_ci.py`'s own shape (a `parse_args` function, a `main` function,
`if __name__ == "__main__": raise SystemExit(main())`) since that is the
nearest existing example of a CLI entry point in this repo.

#### Interface / API
```python
@dataclass(frozen=True)
class LintCliConfig:
    rule_ids: tuple[str, ...] | None
    output_format: str
    show_all: bool
    update_baseline: bool

def parse_args(argv: list[str] | None = None) -> LintCliConfig: ...
def main(argv: list[str] | None = None) -> int: ...
```

#### Logic / Algorithm
1. `parse_args` defines `--rule` (repeatable), `--format {text,json}`
   (default `text`), `--all`, `--update-baseline`.
2. `main` builds a `LintRunner` rooted at the repository root
   (`Path(__file__).resolve().parents[1]`) and `vidbyte/`.
3. If `--update-baseline`: run every registered rule regardless of `--rule`,
   write the fresh counts via `BaselineStore.save`, print the new mapping,
   return 0.
4. Otherwise: call `runner.run(rule_ids=...)`, render the report (text via
   `DiagnosticRenderer` capped at 20 findings per rule unless `--all`, or
   JSON), print a final `AGENT-LINT: PASS`/`AGENT-LINT: FAIL` line mirroring
   the main Vidbyte repo's own `lint/run.py` convention, and return `0` or
   `1` from `RunReport.passed`.

#### Edge Cases & Error Handling
- Any `LintConfigurationError`/`LintAnalyzerError` raised by the runner is
  caught here, printed to stderr with full context, and turned into exit
  code `1` — never an uncaught traceback, matching `scripts/run_ci.py`'s own
  `main()`.

---

### 6.9 `scripts/run_ci.py` — modified

**File(s):** `scripts/run_ci.py` (modify)
**Type:** Modified

#### What it does
`run_source` gains one line calling the new lint tool, before `pytest`.

#### Logic / Algorithm
Insert `self._run_command([sys.executable, str(REPOSITORY_ROOT / "lint" /
"run.py")])` between the existing `check_context_write_paths.py` call and
the `pytest` call. No other change; `_run_command` already provides
`PYTHONDONTWRITEBYTECODE` and inherits any caller-provided `PYTHONPATH`,
which is exactly what `local-ci-verification.md` requires for a worktree
run.

#### Edge Cases & Error Handling
- Unchanged: a lint failure raises `CiFailure` through the existing
  `subprocess.CalledProcessError` path in `_run_command`, printed by the
  existing `main()`.

---

### 6.10 `pyproject.toml` — modified

**File(s):** `pyproject.toml` (modify)
**Type:** Modified

Add `"ruff==0.16.4"` to `[project.optional-dependencies].dev`, alongside the
existing `build`, `pytest`, `pytest-asyncio`, `twine` pins.

---

### 6.11 `lint/README.md` — new

**File(s):** `lint/README.md` (new)
**Type:** New file

States the folder's purpose (agent-facing lint suite, read-only static
analysis, no package imports), the non-goals carried over from Section 2,
the command reference (`python lint/run.py`, `--rule`, `--format json`,
`--all`, `--update-baseline`), the current one-rule catalogue (S001), and
"how to add a rule": create `lint/rules/sNNN_*.py`, register it in
`lint/core/registry.py`, run `--update-baseline` once after manually
reviewing the new findings.

---

## 7. Data Model Changes

None. `lint/baseline.json` is tooling metadata (`{"S001": <int>}`) with no
effect on any runtime-persisted data or public type.

---

## 8. API Changes

None. `vidbyte`'s public exports and runtime behavior are unchanged. The
repository gains one developer-only CLI (`python lint/run.py`) and one new
step inside the existing `scripts/run_ci.py --stage source`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/sdk-lint-python-correctness.md` | This design |
| CREATE | `lint/__init__.py` | Package marker |
| CREATE | `lint/run.py` | CLI entry point |
| CREATE | `lint/baseline.json` | Frozen per-rule debt counts |
| CREATE | `lint/README.md` | Folder purpose, commands, rule catalogue |
| CREATE | `lint/core/__init__.py` | Package marker |
| CREATE | `lint/core/discovery.py` | `SourceCatalog` |
| CREATE | `lint/core/ruff.py` | `RuffAdapter`, `RuffFinding` |
| CREATE | `lint/core/diagnostic.py` | `Finding`, `RuleDiagnostic`, `DiagnosticRenderer` |
| CREATE | `lint/core/baseline.py` | `LintVerdict`, `BaselineStore` |
| CREATE | `lint/core/rule.py` | `LintRule` protocol, shared errors |
| CREATE | `lint/core/registry.py` | `RuleRegistry` |
| CREATE | `lint/core/runner.py` | `LintRunner`, `RuleOutcome`, `RunReport` |
| CREATE | `lint/rules/__init__.py` | Package marker |
| CREATE | `lint/rules/s001_python_correctness_foundation.py` | S001 rule |
| MODIFY | `scripts/run_ci.py` | Invoke `lint/run.py` in `run_source` |
| MODIFY | `pyproject.toml` | Pin `ruff` in the `dev` extra |
| MODIFY | `CONTRIBUTING.md` | Document the new local lint command |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `ruff` | `==0.16.4` (dev extra) | Underlying analyzer for S001 | Low; pinned exact version, `--isolated` avoids ambient config drift |

No runtime dependency changes. No network calls; the lint tool reads only
local tracked source and runs one local subprocess.

---

## 11. Rollout & Deployment

Not a breaking or user-facing change. Rollout is: implement in this worktree
→ install `ruff` standalone (not an editable reinstall of `vidbyte-sdk`,
which would repoint the shared canonical editable install other concurrent
worktrees rely on) → run S001 against the real checkout to discover the true
current finding count → hand-review a sample of those findings for scope
sanity → write `lint/baseline.json` from that real count via
`--update-baseline` → run the full local CI gate → open the PR.

Rollback is reverting the implementation commits; `scripts/run_ci.py` stops
invoking `lint/run.py` and the `ruff` dev pin can be dropped. No data or
public API rollback is required.

---

## 12. Open Questions

- [ ] The prior, broader, unimplemented `sdk-agent-facing-lint-suite.md`
      draft numbers this same rule "S001" with an intended eventual S002–S021
      family. This design keeps that ID so a future PR can extend the same
      registry without a rename; if that draft is actually live work from a
      concurrent session rather than an abandoned draft, its author should
      reconcile scope before S002 is added.

---

## 13. Alternatives Considered

### Implement the full S001–S021 suite from the existing draft in one PR

Rejected because the current ask is explicitly "the Python correctness
linter rules, only" — implementing mypy staged contracts, transport parity,
registry parity, and export integrity in the same change would both exceed
the requested scope and make review of the correctness rule itself harder to
isolate. Those rules remain named, reviewable future work rather than
silently dropped.

### Configure selectors via `pyproject.toml [tool.ruff.lint]` instead of in the rule module

Rejected because a `pyproject.toml` Ruff section is discoverable and
overridable by a contributor running bare `ruff check .`, which would let
the gate's actual selector scope drift from what `lint/run.py` enforces.
Keeping the selector tuple as a constant beside the rule class (per the field
guide's `diagnostic-context.md` spirit of "document sanctioned boundaries in
constants beside the scanner") keeps one source of truth.

### Add `flake8`/`pyflakes` directly instead of Ruff

Rejected because Ruff already subsumes pyflakes and pycodestyle in one fast
binary with structured JSON output, and the existing unimplemented draft
already standardized on Ruff for the rest of the intended suite — starting
with a different tool for S001 would mean migrating later.
