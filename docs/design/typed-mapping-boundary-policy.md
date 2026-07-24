Exit code: 0
Wall time: 1.2 seconds
Output:
# Design Doc: Typed Mapping Boundary Policy

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-22
**Last Updated:** 2026-07-22

---

## 1. Overview

Add a required static-policy CI check that rejects a Python function accepting `object` or `Any`, immediately narrowing it with `isinstance(..., Mapping)` or `dict`, and returning a fallback value for non-mappings. The policy applies to SDK implementation code except explicitly named protocol and deserialization boundaries, where runtime narrowing is legitimate. Its purpose is to prevent silently absorbing programmer errors such as a list being treated as an empty progress log, while preserving validation of untrusted HTTP and MCP payloads.

---

## 2. Goals & Non-Goals

### Goals

- Block new fallback-return mapping guards on `object`/`Any` parameters in ordinary `vidbyte/` modules.
- Permit runtime mapping validation only in named HTTP, provider-response, and MCP protocol boundaries.
- Require boundary code to surface malformed protocol input as a named error response or exception rather than silently substituting a domain default.
- Make the rule deterministic, version-pinned, locally runnable, and a GitHub pull-request status check.
- Bring the one current in-scope baseline occurrence into compliance by expressing its actual accepted type in the API.

### Non-Goals

- Ban every `isinstance` check, every use of `Mapping`, or every use of `object`/`Any`.
- Add a general formatter, linter, type checker, or AI code-review service.
- Retrofit all existing external payload parsers to a new shared parsing framework.
- Modify tests under `tests/`; the policy fixture validates the static-analysis rule itself, while existing compaction tests remain the behavioral coverage for the API cleanup.
- Configure GitHub branch protection through the repository settings API.

---

## 3. Background & Context

The checked-in SDK has a tag-only PyPI publish workflow and no checked-in pull-request CI, linter, or static-policy configuration. It is a Python 3.11+ setuptools package with stdlib `unittest` tests, Pydantic and HTTPX runtime dependencies, and source under `vidbyte/`.

The proposed policy is intentionally narrower than "never use `isinstance`." The audit found legitimate mapping validation at trust boundaries: JSON HTTP response parsing in `vidbyte/lib/http/parser.py`, provider response handling under `vidbyte/providers/`, inbound MCP server handlers under `vidbyte/mcp_server/`, and remote MCP client/transport code under `vidbyte/tools/mcp/`. Those inputs originate outside the SDK's typed domain model, so runtime validation is appropriate.

The audit also found the exact problematic shape in `vidbyte/middleware/compaction/strategies.py`: `ClearExceptSystemAndLogCompaction` accepts `progress_log: object`, then `_build_progress_log` returns an empty `ProgressLog` when the value is not a mapping. That hides an invalid SDK call rather than making the accepted input contract explicit. The implementation will narrow that public constructor and helper to `Mapping[str, object] | None`; `None` remains the intentional no-progress-log value, while an arbitrary object is no longer silently converted to an empty log.

The current checkout is dirty with unrelated work and earlier uncommitted policy artifacts. Per the workflow, implementation must begin only after approval in a new worktree from clean `main`; this design is independent of those local artifacts.

---

## 4. Requirements

### Functional Requirements

1. A Semgrep policy must scan `vidbyte/**/*.py` and fail when a function parameter annotated exactly `object` or `Any` is rejected by an `isinstance(parameter, Mapping|dict)` guard that is the function's first executable statement and returns a fallback value.
2. The policy must cover both `if not isinstance(value, Mapping): return ...` and equivalent `dict` checks, including functions with other positional or keyword-only parameters.
3. The policy must exclude only these audited trust-boundary paths: `vidbyte/lib/http/**`, `vidbyte/providers/**`, `vidbyte/mcp_server/**`, and `vidbyte/tools/mcp/**`.
4. Adding another excluded boundary path must require a documented reason in the policy README and a passing boundary example in the Semgrep fixture; ordinary business, middleware, tool, and model code must not be excluded.
5. The rule must be tested with one violating fixture and one compliant fixture before scanning the SDK source.
6. The GitHub Actions workflow must run on pull requests, pushes to `main`, and manual dispatch; it must fail on a rule-test failure or a source finding.
7. `ClearExceptSystemAndLogCompaction` and `_build_progress_log` must accept `Mapping[str, object] | None`, preserving `None` as the intentional empty-log case without any `isinstance` fallback guard.
8. The workflow job must be documented as a status check that a repository administrator marks required for `main` after it is merged.

### Non-Functional Requirements

- **Performance:** The policy scans only the Python SDK source and should complete well below one minute on a GitHub-hosted runner.
- **Scalability:** Rule configuration and examples must be colocated so additional organization-specific policies can be added without changing application code.
- **Security:** The workflow receives read-only repository contents permission and uses no secrets or untrusted PR code with elevated privileges.
- **Observability:** Findings include the rule identifier, a concrete remediation, and the parameter/function context Semgrep can report.
- **Reliability / error tolerance:** Semgrep is installed at an exact version. The fixture check runs before the source scan, preventing an invalid or weakened policy from silently passing.

---

## 5. High-Level Design

The change adds one narrow Semgrep rule and one dedicated GitHub Actions workflow, rather than treating this as a general linting rollout. The rule looks for an untyped function parameter followed by a negative mapping/dict guard that returns a default value. It deliberately does not flag `isinstance` generally, nor mapping validation inside the four audited external-input boundary families.

The rule and its annotated Python fixture live together in `.semgrep/`; the fixture proves both a violating sample and a typed, `None`-optional alternative. The workflow first executes Semgrep's rule test mode, then scans the implementation tree with `--error` so findings produce a non-zero status. The compaction API is adjusted to remove the one in-scope baseline violation, keeping the full scan green without a blanket suppression.

```text
Pull request / push to main
            |
            v
GitHub Actions: static-policy
            |
            +--> Semgrep rule fixture test
            |
            +--> Semgrep scan of vidbyte/
                       |
                       +--> pass: merge may proceed
                       +--> finding: required status fails
```

---

## 6. Detailed Design

### 6.1 Typed mapping fallback policy

**File(s):** `.semgrep/typed-mapping-boundary-policy.yml`
**Type:** New file

#### What it does

Defines the repository-specific error-level rule `no-untyped-mapping-fallback`. It rejects an `object` or `Any` parameter whose first executable statement dynamically rejects it as a mapping/dict and converts it into a return fallback, except in audited protocol/deserialization paths.

#### Interface / API

```yaml
rules:
  - id: no-untyped-mapping-fallback
    languages: [python]
    severity: ERROR
    paths:
      include: ["vidbyte/**/*.py"]
      exclude:
        - "vidbyte/lib/http/**"
        - "vidbyte/providers/**"
        - "vidbyte/mcp_server/**"
        - "vidbyte/tools/mcp/**"
    pattern-either:
      - pattern: |
          def $FUNCTION(..., $VALUE: object, ...):
            if not isinstance($VALUE, Mapping):
              return ...
            ...
      # Equivalent Any and dict variants are also included.
```

#### Logic / Algorithm

1. Bind a function parameter whose annotation is `object` or `Any`.
2. Match a negative `Mapping` or `dict` runtime guard for that parameter only when it is the first executable statement.
3. Report if the guard returns a fallback instead of continuing with a statically typed value or surfacing an error.
4. Suppress findings only for the four path families listed above; each represents a documented external wire-format boundary.
5. Emit remediation text directing authors to use a concrete mapping annotation (optionally unioned with `None`) or move parsing to a designated boundary that raises/returns a protocol error.

#### Edge Cases & Error Handling

- A parameter typed `Mapping[str, object] | None` is compliant: `None` can be handled explicitly without re-identifying an arbitrary object as a mapping.
- A boundary module may still be incorrect if it silently returns a domain default; the rule's path exclusion permits runtime narrowing, not fallback swallowing. Its boundary-specific error behavior remains covered by existing protocol tests and review.
- `isinstance` checks used for `__eq__`, heterogeneous visitor dispatch, recursive serialization, or values already typed as a mapping do not match this narrow negative-fallback shape.
- New parsing locations are not automatically exempt. The allowlist is deliberately explicit to make a new trust boundary a review decision.

### 6.2 Policy documentation and fixture

**File(s):** `.semgrep/README.md`, `.semgrep/typed-mapping-boundary-policy.py`
**Type:** New files

#### What it does

Documents the policy's intent, exclusions, local commands, and suppression process. The fixture is Semgrep's rule-level contract: it carries one `# ruleid` example reproducing the rejected pattern and one compliant typed alternative.

#### Interface / API

```sh
semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py
semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte
```

#### Logic / Algorithm

1. Keep the violating fixture focused on `values: object`, a `not isinstance(values, Mapping)` guard, and a neutral fallback return.
2. Keep the compliant fixture focused on `values: Mapping[str, object] | None` and an explicit `None` behavior.
3. Document that `# nosemgrep` is a last-resort, line-scoped exception requiring a reason; it is not an alternative to adding a boundary path.
4. Document the four allowed boundary families and the requirement to update both README and fixture before expanding them.

#### Edge Cases & Error Handling

- The fixture must be scanned directly by filename, avoiding Semgrep's directory/name-discovery conventions.
- A fixture mismatch fails the workflow before source scanning, so accidentally changing the rule cannot create a green-but-inert gate.

### 6.3 Static policy workflow

**File(s):** `.github/workflows/static-policy.yml`
**Type:** New file

#### What it does

Runs the policy fixture and source scan as an independent required GitHub Actions job named `static-policy`.

#### Interface / API

```yaml
name: Static policy
on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  static-policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: python -m pip install semgrep==1.170.1
      - run: semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py
      - run: semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte
```

#### Logic / Algorithm

1. Check out the pull-request or branch revision with no write token.
2. Install the exact Semgrep CLI version used to author the policy.
3. Execute the annotated rule fixture.
4. Scan only `vidbyte/`, excluding test helpers and one-off scripts from this implementation policy.
5. Report a failing `static-policy` check when either command exits non-zero.

#### Edge Cases & Error Handling

- A Semgrep installation failure fails closed; the workflow never treats an unavailable policy engine as a pass.
- `--error` is required because a completed Semgrep scan with findings otherwise exits successfully.
- The repository administrator must require `static-policy` in GitHub branch protection; a workflow file alone cannot prevent a merge.

### 6.4 Compaction progress-log contract cleanup

**File(s):** `vidbyte/middleware/compaction/strategies.py`
**Type:** Modified

#### What it does

Removes the one in-scope baseline violation by making the existing progress-log contract explicit. `None` is the only accepted absence value; a mapping supplies progress-log fields.

#### Interface / API

```python
def _build_progress_log(raw_log: Mapping[str, object] | None) -> ProgressLog:

class ClearExceptSystemAndLogCompaction(BaseCompaction):
    def __init__(self, progress_log: Mapping[str, object] | None = None) -> None:
```

#### Logic / Algorithm

1. Change the constructor and stored value from `object` to `Mapping[str, object] | None`.
2. Change `_build_progress_log` to accept the same type.
3. Return an empty `ProgressLog` only when the optional value is explicitly `None`.
4. Build the `ProgressLog` from the already-typed mapping without `isinstance` narrowing.

#### Edge Cases & Error Handling

- Existing callers passing no log remain compatible because the default is still `None`.
- Passing a list or another arbitrary object becomes a caller contract violation instead of silently producing an empty summary. This is the intentional behavior change protected by the new policy.
- No new application test file is planned; the existing compaction test module is the relevant regression suite and must remain green.

---

## 7. Data Model Changes

N/A - this change adds static-analysis configuration and narrows an in-memory constructor/helper type contract. It changes no persisted schemas, migrations, or wire data models.

---

## 8. API Changes

N/A - there are no HTTP or MCP endpoint changes. The public Python constructor `ClearExceptSystemAndLogCompaction(progress_log=...)` is narrowed from arbitrary objects to `Mapping[str, object] | None`; this is a type-contract tightening, not a new endpoint.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/typed-mapping-boundary-policy.md` | Approved design source of truth for the policy change. |
| CREATE | `.semgrep/typed-mapping-boundary-policy.yml` | Repository-specific Semgrep policy and audited boundary path exclusions. |
| CREATE | `.semgrep/typed-mapping-boundary-policy.py` | Annotated violating/compliant policy fixture. |
| CREATE | `.semgrep/README.md` | Local usage, exemption governance, and boundary rationale. |
| CREATE | `.github/workflows/static-policy.yml` | Pull-request and main-branch enforcement workflow. |
| MODIFY | `vidbyte/middleware/compaction/strategies.py` | Replace the in-scope untyped fallback API with an explicit optional mapping contract. |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Semgrep | `1.170.1`, CI-only | Execute the repository-specific Python policy. | Low - exact version pin; future upgrades require fixture verification. |
| `actions/checkout` | `v4` | Read-only checkout for the policy job. | Low - already used by the publish workflow. |
| `actions/setup-python` | `v5` | Provide Python 3.11 for the Semgrep install. | Low - already used by the publish workflow. |
| GitHub Actions | GitHub-hosted Ubuntu runner | Run the required policy status check. | Low - no secrets or deployments. |

No runtime SDK dependency or external service integration is added.

---

## 11. Rollout & Deployment

- **Feature flags:** none.
- **Breaking change:** the compaction constructor's accepted type is narrowed; callers passing `None` or mappings retain behavior, while callers passing arbitrary non-mappings no longer receive an empty progress log.
- **Deployment order:** merge the workflow, rule, fixture, documentation, and baseline cleanup together. The workflow immediately validates the PR that introduces it.
- **Manual post-merge step:** a repository administrator enables GitHub branch protection for `main` and marks the `static-policy` status check required. Until then, the check is advisory.
- **Rollback:** revert the single feature commit/PR. This removes the workflow and policy; reverting the compaction type narrowing restores its prior permissive behavior if compatibility requires it.

---

## 12. Open Questions

- [ ] Should the `static-policy` status check be required on `main` immediately after merge, or observed as advisory for one week to gather false-positive data? Recommendation: require it immediately because the rule is narrow, fixture-tested, and baseline-clean.
- [ ] Is the `ClearExceptSystemAndLogCompaction` constructor considered public API with consumers that may pass untyped JSON-like data? Recommendation: treat the typed signature as authoritative; if an external-deserialization caller is discovered, normalize it at that caller's boundary rather than restoring the fallback.
- [ ] Should the next policy PR add a complementary rule for `Any` annotations generally (for example Ruff ANN401)? Out of scope here; this policy intentionally covers only the silent mapping-fallback pattern.

---

## 13. Alternatives Considered

### Alternative 1: Ban every `isinstance(..., Mapping)` check

- What: reject all mapping runtime checks across `vidbyte/`.
- Why rejected: HTTP, provider, and MCP payloads are external/untyped data; runtime validation is the correct defense at those trust boundaries. A blanket ban would produce false positives and encourage developers to bypass the policy.

### Alternative 2: Enforce only Ruff's `ANN401` rule

- What: enable Ruff's prohibition on `Any` annotations.
- Why rejected: it does not cover `object`, does not identify the mapping-narrowing/fallback behavior, and would create a broad pre-existing baseline unrelated to the requested policy.

### Alternative 3: Use an AI reviewer as the merge gate

- What: ask an LLM in CI whether each function's runtime type narrowing is justified.
- Why rejected: nondeterministic judgments are unsuitable for a required status check. A deterministic structural rule gives authors a reproducible failure and a clear exception process.

### Alternative 4: Scan only changed files with a baseline comparison

- What: avoid baseline remediation by reporting only findings introduced in a PR diff.
- Why rejected: modifying a file containing a legacy finding would create inconsistent outcomes, and the audited baseline contains only one in-scope violation that can be corrected cleanly. A clean full-source scan is simpler and stronger.

### Alternative 5: Put every trust-boundary exception behind `# nosemgrep`

- What: keep the rule global and annotate every valid boundary occurrence line by line.
- Why rejected: boundary status is a module-level architectural property. A documented, small path allowlist is clearer and less fragile, while line-level suppressions remain available only for exceptional cases.

