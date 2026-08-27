# Design Doc: Agent-Native SDK Lint Rules

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-26
**Last Updated:** 2026-08-26

---

## 1. Overview

Extend the existing Vidbyte SDK agent-facing lint suite with the selected rules
from the "Writing Agent Native Code" article: S024 and A001-A003, A005-A008.
These rules make control flow, file purpose, policy intent, diagnostic context,
dependency seams, module ownership, operational limits, and stdout behavior
explicit to future coding agents. The rules remain static, independently
selectable, and count-ratcheted so existing repository debt is visible without
turning this change into a source-wide cleanup.

---

## 2. Goals & Non-Goals

### Goals

- Add one independently reportable rule for maximum control-flow nesting.
- Require a structured agent-readable header on tracked SDK package Python files.
- Require nearby `# @intent ...` blocks on functions whose names or logic carry
  retry, permission, pricing, redaction, persistence, fallback, state-transition,
  or external-boundary policy.
- Require central SDK boundary error classes to declare a stable diagnostic-field
  contract.
- Reject bare `object` and unconstrained `Any` at injected dependency seams.
- Detect concrete-module import cycles and imports that cross the documented
  dependency layer graph.
- Require operational numeric literals to be named constants, enums, or config
  values at policy-bearing sites.
- Reject `print()` calls in importable SDK modules except the CLI console adapter.
- Keep diagnostics self-contained with consequence, repair shape, examples,
  rejected shortcuts, and focused verification commands.
- Preserve the existing S001-S021 suite, Semgrep policy, context-write checker,
  source CI, package CI, and baseline ratchet.

### Non-Goals

- Do not repair current SDK findings in this change.
- Do not change installed-package runtime behavior or public APIs.
- Do not enforce exact prose, line lengths, or a universal comment density.
- Do not require intent comments on every function.
- Do not ban all `Any`, all built-in exceptions, all numeric literals, or all
  stdout in developer-only scripts.
- Do not import or execute SDK modules while linting.
- Do not add feature-test files; verification uses focused static scans and the
  existing repository gates.
- Do not implement unselected A004 or invent additional rule IDs.

---

## 3. Background & Context

The SDK already has a repository-level lint runner on
`feat/sdk-agent-facing-lint-suite`. It provides a shared tracked-source
catalogue, isolated Ruff and mypy adapters, diagnostics, and a strict baseline
for S001-S021. The current suite does not yet cover the article's explicit
context-window constraints: deep branching, missing file context, policy logic
without intent, low-context errors, weak injected seams, cycles, unexplained
operational numbers, or library stdout.

The implementation must extend the existing rule contract rather than create a
second scanner. The SDK field guide also requires class-bound helper surfaces,
model-facing diagnostics with repair context, and worktree-aware CI verification.
The rules therefore live under `lint/rules`, use `SourceCatalog`, and report
current debt through `lint/baseline.json` instead of modifying `vidbyte` source.

---

## 4. Requirements

### Functional Requirements

1. The lint registry must load S024, A001, A002, A003, A005, A006, A007, and
   A008 as unique independently selectable rules.
2. S024 must report every control-flow construct whose nesting depth exceeds
   three, counting `if`, `for`, `try`, `with`, and `match` across a function or
   module, while treating an `elif` chain as a sibling branch rather than an
   additional semantic nesting level.
3. A001 must report tracked `vidbyte/**/*.py` files whose first header block does
   not contain purpose, ownership, architecture, modification guidance, edge
   cases, related documentation, and tests fields. The initial findings are
   baselined; new missing headers regress.
4. A002 must report load-bearing functions in the selected policy categories
   unless a nearby, non-empty `# @intent <name>` marker exists in the function's
   declaration/leading implementation block.
5. A003 must report central error classes in `vidbyte/lib/errors/` that do not
   declare all canonical context fields: `error_kind`, `expected`, `actual`,
   `safe_runtime_details`, `likely_causes`, `repair_approaches`, `related_docs`,
   and `relevant_tests`.
6. A005 must report injected arguments named for a transport, runner, store,
   client, tracer, or fetcher when their annotation is bare `object` or contains
   unconstrained `Any`; explicitly typed wire-format mappings remain exempt.
7. A006 must build a static concrete-module import graph, ignore package façade
   `__init__.py` nodes and imports nested under `TYPE_CHECKING`, report each
   newly visible directed cycle and each edge forbidden by the documented layer
   graph, and never import SDK modules.
8. A007 must report numeric literals at operational policy sites, including
   timeout/retry/budget/limit/truncation/status-code values, when the literal is
   not supplied through an uppercase named constant, enum, or configuration
   object.
9. A008 must report AST `print()` calls in `vidbyte/**/*.py` except under the
   explicitly designated `vidbyte/cli/` console adapter.
10. Every new rule must return stable `Finding` records and an agent-facing
    `Diagnostic` with contract, consequence, canonical repair, examples,
    rejected shortcuts, and focused verification.
11. The baseline must contain one reviewed integer allowance for every selected
    rule, and the canonical source stage must continue invoking the complete
    suite.

### Non-Functional Requirements

- Scans remain deterministic by tracked relative path, line, and symbol.
- Rules read source through the existing catalogue and perform no runtime
  imports, provider calls, network I/O, or source mutation.
- The added scans should remain inexpensive over the existing package and avoid
  repeated filesystem walks.
- The implementation must run on Python 3.11 and 3.12 on Windows and POSIX.
- New lint modules and documentation must use the repository's structured
  headers and class-bound helper style.
- Existing baseline allowances may be lowered after genuine source improvement,
  but never raised to conceal a regression.

---

## 5. High-Level Design

Each selected policy is a small class implementing the existing `Rule` contract.
The rule registry imports the eight modules explicitly, the shared
`SourceCatalog` supplies parsed SDK Python files, and the existing runner turns
their complete finding sets into baseline verdicts and diagnostics. No new
analyzer process or runtime dependency is introduced.

The rules use narrow, documented scopes. S024, A001, A002, A005, A007, and A008
scan package ASTs/text; A003 examines only central SDK error definitions; and
A006 builds a graph from concrete module imports. A003's canonical field tuple
and A006's layer policy are declared beside their analyzers so a future agent
can inspect and update the contract in one place.

```text
tracked vidbyte/**/*.py --> SourceCatalog --> selected AST/text analyzers
                                      |                  |
                                      +------------------+--> Finding + Diagnostic
                                                         |
baseline.json <----------- RuleRunner <------------------+--> text/JSON/exit code
```

Implementation commits will proceed in the requested order: S024, A001, A002,
A003, A005, A006, A007, and A008. Registry, README, and baseline metadata are
updated alongside the rule that first needs them, with the final complete suite
run after all rules are registered.

---

## 6. Detailed Design

### 6.1 Rule registry and documentation metadata

**File(s):** `lint/core/registry.py`, `lint/baseline.json`, `lint/README.md`, `lint/rules/README.md`
**Type:** Modified

#### What it does

Adds the selected rule module paths and rule catalogue entries while preserving
the existing explicit registry, sorted reporting, strict baseline validation,
and focused `--rule` command. Documentation records every new ID, scope, and
repair expectation.

#### Interface / API

```python
RULE_MODULES: tuple[str, ...]

class RuleRegistry:
    def all(self) -> tuple[Rule, ...]: ...
    def select(self, rule_id: str | None) -> tuple[Rule, ...]: ...
```

#### Logic / Algorithm

1. Convert the existing generated S-only module tuple to an explicit ordered
   tuple that can represent both A and S identifiers.
2. Import each new module's exported `RULE` and retain duplicate-ID validation.
3. Add reviewed current counts to the sorted baseline after focused scans.
4. Add the new IDs to both README catalogues and the file index.

#### Edge Cases & Error Handling

- A missing or stale baseline key remains a setup failure.
- A duplicate or blank rule ID remains a setup failure.
- A rule raising during analysis remains `ERRORED`, never zero findings.

### 6.2 S024 -- maximum control-flow nesting

**File(s):** `lint/rules/s024_maximum_control_flow_nesting.py`
**Type:** New file

#### What it does

Counts semantic control-flow nesting over `if`, `for`, `try`, `with`, and
`match` nodes. It reports the first node at each path beyond depth three and
stores the measured depth and construct in the finding metadata.

#### Interface / API

```python
class MaximumControlFlowNestingRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Visit each parsed package AST with a class-bound analyzer.
2. Carry the current nesting depth through control-flow bodies.
3. Count `if`, `for`, `async for`, `try`, `with`, `async with`, and `match`.
4. Traverse `elif` nodes at the parent `if` depth so an `elif` ladder does not
   become an accidental artificial depth increase.
5. Report a node when the incoming semantic depth is already three and render
   the construct/depth in the diagnostic.

#### Edge Cases & Error Handling

- `else`, `finally`, and exception handler blocks inherit the parent depth; they
  are branches, not additional constructs.
- Comprehensions are not counted because the requirement names statement-level
  constructs.
- Syntax-error source records are skipped by the existing source policy and
  remain visible to the correctness gate.

### 6.3 A001 -- agent-readable file headers

**File(s):** `lint/rules/a001_agent_readable_file_headers.py`
**Type:** New file

#### What it does

Checks the opening header block of each tracked SDK package Python file for the
canonical context fields required by the article-derived file contract.

#### Interface / API

```python
class AgentReadableFileHeadersRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Inspect only the first `HEADER_SCAN_LINES` lines before ordinary source
   content becomes the module's implementation.
2. Match the canonical markers `PURPOSE:`, `ROLE IN CODEBASE:`,
   `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`,
   `RELATED DOCS:`, and `TESTS:`.
3. Emit one finding per file with all missing markers in `extra`, making one
   repair explain the full header contract.

#### Edge Cases & Error Handling

- Existing alternate legacy headers are current debt unless they contain all
  canonical fields; the baseline preserves that debt.
- Empty marker values are treated as missing.
- The rule does not demand headers for unrelated repository scripts or test
  files; package source is the importable SDK surface in this suite.

### 6.4 A002 -- intent comments for load-bearing logic

**File(s):** `lint/rules/a002_intent_comments.py`
**Type:** New file

#### What it does

Finds functions whose declaration or leading implementation contains the
policy-bearing vocabulary for retries, permissions, pricing, redaction,
persistence, fallback, state transitions, or external boundaries and checks
for a nearby non-empty intent marker.

#### Interface / API

```python
class IntentCommentsRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Visit functions and methods, combine the function name with a bounded
   leading source window, and match only the declared policy tokens.
2. Treat `# @intent <short-name>` within the declaration/leading implementation
   window as compliant; require a non-empty slug.
3. Report the function once with matched policy categories in `extra`.

#### Edge Cases & Error Handling

- Generic functions without policy vocabulary are not flagged.
- A marker buried later in a long function does not satisfy the nearby-context
  requirement.
- The rule does not require a particular prose style after the slug, but the
  diagnostic directs authors to explain invariant, reason, and failure mode.

### 6.5 A003 -- context-rich error packets

**File(s):** `lint/rules/a003_context_rich_error_packets.py`
**Type:** New file

#### What it does

Checks central SDK error classes for an explicit stable diagnostic schema. The
schema makes an error packet useful to both a caller and a future repair agent
without forcing them to reconstruct context from a traceback.

#### Interface / API

```python
CANONICAL_DIAGNOSTIC_FIELDS: tuple[str, ...]

class ContextRichErrorPacketsRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Scan `vidbyte/lib/errors/*.py` classes whose names end in `Error`, excluding
   the root `VidbyteSdkError` contract itself.
2. Read a literal `DIAGNOSTIC_FIELDS` tuple/list/set declared on each class.
3. Require all canonical field names: error kind, expected behavior, actual
   behavior, safe runtime details, likely causes, repair approaches, related
   docs, and relevant tests.
4. Emit one finding per class with the missing field names.

#### Edge Cases & Error Handling

- Inherited error classes may satisfy the contract through an inherited literal
  only when the analyzer can resolve that base within the same scanned module;
  otherwise they must declare their own stable schema.
- Arbitrary `details` mappings without a declared field schema remain findings;
  dynamic keys are not sufficiently discoverable.
- The rule is structural and does not execute exception constructors.

### 6.6 A005 -- typed dependency seams

**File(s):** `lint/rules/a005_typed_dependency_seams.py`
**Type:** New file

#### What it does

Protects injected infrastructure boundaries from collapsing into opaque
`object`/`Any` values. The caller and the implementation need a concrete class,
abstract base, or `Protocol` to make capabilities inspectable.

#### Interface / API

```python
class TypedDependencySeamsRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Inspect parameters in package functions and methods whose names contain a
   dependency token: `transport`, `runner`, `store`, `client`, `tracer`, or
   `fetcher`.
2. Flag an exact `object` annotation or any annotation containing unconstrained
   `Any`.
3. Permit mapping/sequence annotations for explicitly wire-format parameter
   names such as `payload`, `json_body`, `headers`, and `metadata`.
4. Report the parameter and rendered annotation so the repair can introduce a
   narrow local protocol at the seam.

#### Edge Cases & Error Handling

- `self`, `cls`, variadic configuration options, and unannotated parameters are
  outside this rule's specific contract; S007 covers missing public annotations.
- `Mapping[str, Any]` remains valid for wire-format data but not for an injected
  dependency named `store` or `client`.
- Type-only imports are not executed by the analyzer.

### 6.7 A006 -- directed dependency graph

**File(s):** `lint/rules/a006_directed_dependency_graph.py`
**Type:** New file

#### What it does

Builds a concrete-module graph from relative and absolute `vidbyte` imports and
checks cycles plus a small documented layer policy. Package façade initializers
are intentionally excluded from the first version so broad re-export surfaces
do not overwhelm the signal.

#### Interface / API

```python
class DirectedDependencyGraphRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Resolve imports to tracked concrete `.py` modules; skip `__init__.py` targets
   and imports under a `TYPE_CHECKING` branch.
2. Build a source-module to target-module adjacency map with import locations.
3. Use a deterministic strongly-connected-component pass to report every
   concrete edge in a cycle.
4. Apply the documented layer policy: foundational `vidbyte.lib` modules may
   not depend on orchestration/application packages; provider and storage
   infrastructure may not depend on orchestration/application packages; and
   application façades may depend downward. Peer orchestration packages remain
   allowed until a narrower boundary is documented.

#### Edge Cases & Error Handling

- Self-imports and missing/non-package imports are ignored as no concrete edge.
- `TYPE_CHECKING` imports are ignored in this first version as specified.
- Existing cycles or violations are baseline debt; a new edge increases the
  rule's count and fails the ratchet.

### 6.8 A007 -- operational constants

**File(s):** `lint/rules/a007_operational_constants.py`
**Type:** New file

#### What it does

Detects unexplained numeric literals where they define runtime policy: time
budgets, retry counts, response/token/character ceilings, truncation lengths,
backoff values, or provider status codes.

#### Interface / API

```python
class OperationalConstantsRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Inspect numeric literals in defaults, comparisons, calls, slices, and
   lower-case assignments whose surrounding names match operational tokens.
2. Exclude booleans, uppercase named constant assignments, enums, and values
   already supplied through a named config/constant reference.
3. Report the literal once with the matched operational context and recommend a
   named constant or typed configuration field.

#### Edge Cases & Error Handling

- Ordinary arithmetic and user-facing examples without operational vocabulary
  are not findings.
- Zero/one are still findings when they define an attempt, timeout, status, or
  limit policy; their small size does not make their meaning discoverable.
- The rule is heuristic by design and keeps all token/path exceptions beside the
  analyzer for review.

### 6.9 A008 -- library stdout boundary

**File(s):** `lint/rules/a008_library_stdout_boundary.py`
**Type:** New file

#### What it does

Rejects actual AST calls to builtin `print()` in importable SDK modules while
allowing the explicit CLI console adapter to own human-facing output.

#### Interface / API

```python
class LibraryStdoutBoundaryRule(Rule):
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...
```

#### Logic / Algorithm

1. Visit `ast.Call` nodes whose callee is the bare builtin name `print`.
2. Skip files under `vidbyte/cli/`, the designated console boundary.
3. Report the call location and direct the repair toward a return value,
   structured logger, or CLI adapter.

#### Edge Cases & Error Handling

- A method named `print` is not itself a violation until it calls builtin
  `print()`; this keeps API names separate from side effects.
- Strings containing `print(` are not AST calls and are ignored.
- `logging` and structured tracer calls are compliant.

---

## 7. Data Model Changes

None. `lint/baseline.json` gains rule-count metadata only; it is not runtime
serialization, a persisted SDK schema, or a user data migration.

---

## 8. API Changes

None. The installed SDK API and runtime behavior are unchanged. The existing
developer-only `python lint/run.py --rule <ID>` CLI gains the selected IDs as
valid rule selections.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-native-lint-rules.md` | Source-of-truth design for the selected article-derived rules |
| CREATE | `lint/rules/s024_maximum_control_flow_nesting.py` | Enforce maximum semantic control-flow nesting |
| CREATE | `lint/rules/a001_agent_readable_file_headers.py` | Enforce structured SDK file headers |
| CREATE | `lint/rules/a002_intent_comments.py` | Enforce intent markers on load-bearing policy functions |
| CREATE | `lint/rules/a003_context_rich_error_packets.py` | Enforce stable diagnostic field declarations on boundary errors |
| CREATE | `lint/rules/a005_typed_dependency_seams.py` | Reject opaque injected dependency annotations |
| CREATE | `lint/rules/a006_directed_dependency_graph.py` | Enforce concrete-module graph and layer boundaries |
| CREATE | `lint/rules/a007_operational_constants.py` | Enforce named operational policy values |
| CREATE | `lint/rules/a008_library_stdout_boundary.py` | Keep stdout at the CLI boundary |
| MODIFY | `lint/core/registry.py` | Register A001-A003, A005-A008, and S024 |
| MODIFY | `lint/baseline.json` | Add reviewed count allowances for each selected rule |
| MODIFY | `lint/README.md` | Document the expanded suite and rule catalogue |
| MODIFY | `lint/rules/README.md` | Add file-index entries and rule descriptions |

**Files to create:** 9  
**Files to modify:** 4  
**Files to delete:** 0

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing Python standard library | Python 3.11+ | AST, graph, path, and text analysis | Low; already required by the SDK and lint runner |
| Existing `lint/core` contracts | Current feature-branch implementation | Shared catalogue, findings, diagnostics, and baseline | Medium; rule contract drift would affect all rules |
| Existing Ruff/mypy dev pins | `ruff==0.16.4`, `mypy==2.3.1` | Existing S001-S021 analyzer gates | Low; no new dependency or analyzer process |

No external service, provider credential, network request, or runtime package
import is needed.

---

## 11. Rollout & Deployment

1. Keep the current dirty `main` checkout untouched and use the existing lint
   suite branch as the implementation base because it is the checkout that
   contains `lint/run.py`.
2. Commit this design doc first in the isolated
   `feat/agent-native-lint-rules` worktree.
3. Implement and register S024, A001, A002, A003, A005, A006, A007, and A008 in
   order, reviewing focused JSON/text findings after each rule.
4. Initialize each new baseline allowance only after inspecting representative
   positives and counterexamples. Do not raise existing allowances.
5. Install the dev extra and verify from the worktree with
   `$env:PYTHONPATH=(Get-Location).Path` for source checks, then run:
   `python lint/run.py`, `python scripts/run_ci.py --stage source`, and the full
   `python scripts/run_ci.py`.
6. Push the branch and open a draft PR targeting `main` if GitHub CLI access is
   available; otherwise report the exact command and authentication blocker.

Rollback is a revert of the implementation commits. Removing the selected
registry entries, rule files, README entries, and baseline keys returns the
suite to S001-S021; no runtime data or package migration is required.

---

## 12. Open Questions

No unresolved question blocks implementation. The following decisions are fixed
for this change:

- A001 scopes the initial enforcement inventory to tracked importable SDK
  package files, matching the current `SourceCatalog` contract.
- A003 uses a literal `DIAGNOSTIC_FIELDS` declaration so the error packet schema
  is statically discoverable without executing constructors.
- A006 excludes package façade initializers and `TYPE_CHECKING` imports in its
  first version, as required by the selected rule proposal.
- A008 permits stdout only under `vidbyte/cli/`; other console behavior must be
  explicitly moved behind that adapter in a later source-cleanup change.

---

## 13. Alternatives Considered

### Alternative 1: Fix all current findings before enabling the rules

- What: Rewrite the package to satisfy every new rule in the same feature.
- Why rejected: The request is to establish enforceable rules; a count baseline
  lets the team repair existing debt incrementally while blocking new debt.

### Alternative 2: Put article-derived checks into Ruff configuration only

- What: Express every rule as Ruff selectors or plugins.
- Why rejected: Headers, intent semantics, error packet schemas, graph policy,
  and SDK boundary exceptions need repository-specific AST analysis and rich
  repair diagnostics that the existing adapter cannot express.

### Alternative 3: Compare imports by executing package modules

- What: Import packages and inspect `__all__`, registries, and module objects.
- Why rejected: Lint must remain side-effect-free and work without optional
  provider dependencies or credentials; static concrete-module parsing is safer.

### Alternative 4: Require a header or intent comment on every function/file

- What: Treat all code uniformly as context-bearing.
- Why rejected: It produces low-signal boilerplate and contradicts the article's
  distinction between load-bearing policy and ordinary implementation detail.
