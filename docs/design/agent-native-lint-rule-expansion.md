# Design Doc: Agent-Native Lint Rule Expansion

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-28
**Last Updated:** 2026-08-28

---

## 1. Overview

This change extends the Vidbyte SDK's existing agent-facing lint catalogue with
25 sequential Python rules, S026-S050, after the existing S025 rule on the
source branch. The rules use the repository's cached Ruff adapter to detect
specialized collection, dataclass, assertion, test, packaging, import,
encoding, exception, logging, async, YAML, and cryptographic-hash risks without
importing SDK runtime modules. Each rule remains independently selectable,
richly diagnostic, count-ratcheted, and fail-closed through python lint/run.py
and the canonical scripts/run_ci.py gate.

---

## 2. Goals & Non-Goals

### Goals

- Register and execute S026-S050 after the existing S001-S025 rules.
- Preserve one tracked-source catalogue, one cached Ruff invocation, deterministic
  records, and the existing baseline validation contract.
- Add the exact Ruff selectors for the 25 requested rules, including preview
  support where a selected rule requires it.
- Add a narrowly scoped TID251 banned-API policy for APIs that are not allowed
  in the SDK's runtime package.
- Scan pyproject.toml for RUF200 while continuing to scan the vidbyte package.
- Give every new rule agent-facing summary, consequence, repair, rejected
  shortcut, and verification guidance.
- Initialize each new allowance from a reviewed current-tree scan without
  raising existing allowances.
- Keep the current source, package, Semgrep, compile, and pytest gates
  mandatory without adding new feature-test files.

### Non-Goals

- Do not fix all existing source findings in this change; baselines freeze
  pre-existing debt for later cleanup.
- Do not change the existing S001-S025 semantics or renumber any rule.
- Do not add runtime dependencies or change the SDK's public API.
- Do not import the SDK package from the lint suite.
- Do not use Ruff's ambient project configuration; analyzer settings remain
  explicit and repository-owned.
- Do not enable unrelated broad Ruff families or convert every warning into a
  new local policy.
- Do not add new feature-test files. Existing lint and CI tests remain required.

---

## 3. Background & Context

The SDK already has an agent-facing lint package with agent-readable metadata
rules A001-A008 and S001-S025 correctness and architecture rules. Its Ruff
adapter invokes one isolated JSON scan and lets each local S rule select an
exact code. The current adapter selects a small foundation set and scans the
vidbyte package only.

The requested rules are mostly stable Ruff checks that maintained projects use
for difficult-to-see correctness failures. Two rules require extra analyzer
care: TID251 needs an explicit banned-API table, and RUF200 applies to
pyproject.toml rather than a Python module. The adapter will use a committed
lint/ruff.toml policy file and include both pyproject.toml and vidbyte in one
Ruff invocation.

The repository's field guide requires diagnostics to explain the protected
boundary, caller-visible consequence, canonical repair, rejected shortcuts, and
verification path. New rules therefore provide richer metadata than a raw Ruff
message, while Ruff remains responsible for language-level detection and edge
cases.

---

## 4. Requirements

### Functional Requirements

1. S026 must expose Ruff RUF007 for pairwise iteration through zip.
2. S027 must expose Ruff RUF008 for mutable dataclass defaults.
3. S028 must expose Ruff RUF009 for function calls in dataclass defaults.
4. S029 must expose Ruff RUF015 for unnecessary first-element allocation.
5. S030 must expose Ruff RUF017 for quadratic list summation.
6. S031 must expose Ruff RUF018 for assignments inside assertions.
7. S032 must expose Ruff RUF019 for unnecessary dictionary key checks.
8. S033 must expose Ruff RUF024 for mutable dict.fromkeys values.
9. S034 must expose Ruff RUF043 for ambiguous pytest.raises match patterns.
10. S035 must expose Ruff RUF100 for unused noqa directives.
11. S036 must expose Ruff RUF200 for invalid pyproject.toml metadata.
12. S037 must expose Ruff PGH003 for blanket type ignores.
13. S038 must expose Ruff PGH004 for blanket noqa directives.
14. S039 must expose Ruff TID251 using the repository's banned-API policy.
15. S040 must expose Ruff TID252 for relative imports.
16. S041 must expose Ruff PLW1514 for unspecified file encoding.
17. S042 must expose Ruff TRY002 at SDK public boundaries.
18. S043 must expose Ruff TRY401 for verbose exception logging.
19. S044 must expose Ruff G004 for f-string logging.
20. S045 must expose Ruff ASYNC109 for async timeout parameters.
21. S046 must expose Ruff ASYNC210 for blocking HTTP in async functions.
22. S047 must expose Ruff ASYNC230 for blocking open calls in async functions.
23. S048 must expose Ruff ASYNC251 for blocking sleeps in async functions.
24. S049 must expose Ruff S506 for unsafe YAML loading.
25. S050 must expose Ruff S324 for insecure hash usage.
26. Every rule must have a unique sequential ID, stable name, blocking severity,
    independently selectable module, registry entry, catalogue entry, and
    baseline entry.
27. Every diagnostic must identify the exact source construct, explain the SDK
    consequence, provide an actionable repair, list non-fixes, and provide the
    focused verification command.
28. Ruff must be invoked at most once per process for all Ruff-backed rules.
29. Ruff launch, configuration, process, JSON, and path failures must become
    ERRORED results rather than zero findings.
30. The full python lint/run.py and python scripts/run_ci.py gates must pass
    after baseline initialization and fail on later count increases or analyzer
    errors.

### Non-Functional Requirements

- **Determinism:** Normalize paths to repository-relative POSIX paths and sort
  findings by path, line, column, and symbol.
- **Performance:** Reuse the existing SourceCatalog and cached Ruff payload;
  adding 25 selectors must not launch 25 analyzer processes.
- **Security:** The lint suite reads tracked source and configuration only. It
  never imports target modules, executes application code, contacts services, or
  treats YAML input as data to load.
- **Reliability:** Analyzer failures and malformed records fail closed. A
  missing baseline key is a setup failure under the existing contract.
- **Adoptability:** Existing findings are initialized only after inspection;
  clean rules remain zero and existing allowances are never raised.
- **Package safety:** lint-only configuration is not included in the published
  SDK wheel and does not alter runtime package dependencies.

---

## 5. High-Level Design

The existing RuleRegistry, RuleRunner, SourceCatalog, baseline store, and
report renderer remain the sole local lint pipeline. S026-S050 are thin
RuffBackedRule classes that select one exact analyzer code and provide SDK
specific diagnostic metadata.

lint/core/ruff.py will invoke Ruff with preview enabled, an explicit
lint/ruff.toml configuration, and two scan roots: pyproject.toml and vidbyte.
The committed configuration supplies the TID251 banned API mapping. RUF200 can
therefore validate project metadata while all source rules continue to inspect
the package in the same cached payload.

    tracked source + pyproject.toml
                 |
                 v
       SourceCatalog + RuffStore (one scan)
                 |
                 v
      S026 ... S050 exact-code selectors
                 |
                 v
       diagnostics -> baseline -> report -> exit

---

## 6. Detailed Design

### 6.1 Ruff Analyzer Expansion

**File(s):** lint/core/ruff.py, lint/ruff.toml
**Type:** Modified and New file

#### What it does

Extends the existing selector list with RUF007, RUF008, RUF009, RUF015,
RUF017, RUF018, RUF019, RUF024, RUF043, RUF100, RUF200, PGH003, PGH004,
TID251, TID252, PLW1514, TRY002, TRY401, G004, ASYNC109, ASYNC210, ASYNC230,
ASYNC251, S506, and S324. It runs one explicit, preview-enabled scan with the
committed banned-API configuration and normalizes all records through the
existing fail-closed adapter.

#### Interface / API

    class RuffStore:
        @classmethod
        def records(cls) -> tuple[RuffRecord, ...]: ...

    class RuffBackedRule(Rule):
        codes: frozenset[str]
        def check(self, catalog: SourceCatalog) -> list[Finding]: ...
        def explain(self, finding: Finding) -> Diagnostic: ...

#### Logic / Algorithm

1. Build the command with pyproject.toml and vidbyte as explicit paths,
   lint/ruff.toml as the explicit configuration, --preview, --exit-zero,
   --output-format json, and --no-cache.
2. Accept Ruff status 0 or the ordinary finding status represented by
   --exit-zero, while rejecting process and payload errors.
3. Parse every record, normalize its path, and retain records from either
   pyproject.toml or vidbyte.
4. Map Python source lines through SourceCatalog; RUF200 may have no source
   line because it belongs to TOML and its diagnostic will use the Ruff message.
5. Cache the complete immutable record tuple for all S rules.

#### Edge Cases & Error Handling

- The --preview flag applies to selected preview rules without selecting
  unrelated preview families.
- TID251 settings are owned by lint/ruff.toml, not by a developer's ambient
  user configuration.
- If an analyzer path is outside the repository or a record has no valid
  location, the rule run is ERRORED.
- RUF200 is verified by running the same command against the tracked project
  metadata rather than silently omitting TOML from the source scan.

### 6.2 TID251 Banned API Policy

**File(s):** lint/ruff.toml
**Type:** New file

#### What it does

Defines the repository-owned list of APIs that should not be imported into the
SDK package. The initial list follows the researched policy pattern: selected
typing APIs that undermine the SDK's compatibility convention and
asyncio.Lock outside the approved ownership boundary.

#### Interface / API

The configuration uses Ruff's flake8-tidy-imports banned-api table:

    [lint.flake8-tidy-imports.banned-api]
    "typing.TypedDict" = { msg = "Use the SDK-approved TypedDict import." }
    "typing.assert_never" = { msg = "Use the SDK-approved assert_never import." }
    "asyncio.Lock" = { msg = "Use the SDK-owned concurrency boundary." }

#### Logic / Algorithm

1. Load the table only through the explicit Ruff configuration path.
2. Let Ruff resolve direct and from-import forms of each banned API.
3. Surface TID251 records through S039 with the configured message.
4. Add narrow exemptions only when an approved ownership boundary is recorded
   in a later design; do not weaken the global table to accommodate one file.

#### Edge Cases & Error Handling

- The rule is policy-driven; changing the banned API list changes the protected
  SDK contract and requires design review.
- A false positive is resolved by an explicit boundary or policy change, not a
  baseline increase.
- Tests are scanned consistently with the existing Ruff command unless a
  future policy documents a test-only exception.

### 6.3 Ruff Rules S026-S050

**File(s):** lint/rules/s026_*.py through lint/rules/s050_*.py
**Type:** New files

#### What it does

Each module exports one class and one RULE instance. The class declares its
exact Ruff code, four-sentence summary, SDK-specific impact, repair guidance,
and optional in-repository examples; the shared adapter supplies source facts
and the renderer supplies the fixed diagnostic section order.

#### Logic / Algorithm

1. Register and implement S026, run its focused scan, review findings, and
   initialize its baseline.
2. Repeat in numerical order through S050; never add a later ID before the
   preceding rule is registered and verifiable.
3. For analyzer findings, preserve Ruff's code and message while explaining the
   project-specific reason the construct is blocked.
4. Use a review-first severity description for semantic policies such as
   TID251, TRY002, PLW1514, ASYNC109, and S506, but keep them blocking under
   the count-ratcheted gate.
5. Verify each rule with python lint/run.py --rule Sxxx.

#### Edge Cases & Error Handling

- S506 must distinguish unsafe YAML from the SDK's approved custom safe loader;
  any exception must be narrow and documented.
- S324 findings used only for non-security checks require explicit review, not
  automatic suppression.
- TRY002, TID251, and TID252 are policy-sensitive and must not be satisfied by
  renaming symbols or moving code one frame down.
- Preview rule behavior remains tied to the pinned Ruff version.

### 6.4 Catalogue, Baseline, and Documentation

**File(s):** lint/core/registry.py, lint/baseline.json, lint/README.md,
lint/rules/README.md
**Type:** Modified

#### What it does

Adds the 25 rule modules to the stable registry, records their observed
allowances, documents the exact protected contracts, and updates the tracked
file index used by the repository's documentation parity rule.

#### Logic / Algorithm

1. Add each module path to the registry after S025 in numerical order.
2. Run python lint/run.py --rule S026 --format json and continue one ID at a
   time through S050.
3. Inspect representative true positives and counterexamples before invoking
   --update-baseline for that ID.
4. Update both README catalogues with the exact local ID, name, and purpose.
5. Run the complete lint suite and verify there are no stale baseline keys.

#### Edge Cases & Error Handling

- Any missing baseline entry fails setup; no rule may silently escape the gate.
- Existing S001-S025 counts must not increase because of unrelated changes.
- A rule that errors is not eligible for baseline initialization.
- The documentation file index must include every new module exactly once.

### 6.5 CI and Package Compatibility

**File(s):** scripts/run_ci.py, pyproject.toml
**Type:** N/A - Existing canonical gates already invoke lint/run.py and no
runtime/package dependency or CI command change is required.

#### What it does

The implementation relies on the existing pinned ruff==0.16.4 development
dependency and existing scripts/run_ci.py stages. The design records the
required worktree environment discipline: use PYTHONPATH for the source stage
and omit it for the package stage.

#### Logic / Algorithm

1. Install the existing dev extra in the isolated worktree.
2. Run PYTHONPATH=<worktree> python scripts/run_ci.py --stage source.
3. Run python scripts/run_ci.py --stage package without PYTHONPATH.
4. Run python scripts/run_ci.py in full after refinement.

#### Edge Cases & Error Handling

- The package gate must not accidentally import the canonical checkout.
- New lint configuration is repository tooling and must not enter the wheel.
- Existing tracked-bytecode and Semgrep checks remain blocking.

---

## 7. Data Model Changes

N/A - No production data, persisted DTO, database schema, migration, or
published wire format changes. lint/baseline.json remains tooling state with
its existing rule-ID-to-integer schema.

---

## 8. API Changes

N/A - No public SDK runtime API changes. The existing lint CLI gains selectable
S026-S050 IDs only; scripts/run_ci.py keeps its current command-line interface.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | docs/design/agent-native-lint-rule-expansion.md | Source-of-truth design |
| CREATE | lint/ruff.toml | Explicit TID251 banned-API configuration |
| CREATE | lint/rules/s026_pairwise_zip.py | S026 |
| CREATE | lint/rules/s027_mutable_dataclass_default.py | S027 |
| CREATE | lint/rules/s028_dataclass_default_call.py | S028 |
| CREATE | lint/rules/s029_unnecessary_first_element_allocation.py | S029 |
| CREATE | lint/rules/s030_quadratic_list_summation.py | S030 |
| CREATE | lint/rules/s031_assignment_in_assert.py | S031 |
| CREATE | lint/rules/s032_unnecessary_key_check.py | S032 |
| CREATE | lint/rules/s033_mutable_dict_fromkeys.py | S033 |
| CREATE | lint/rules/s034_ambiguous_pytest_raises_match.py | S034 |
| CREATE | lint/rules/s035_unused_noqa.py | S035 |
| CREATE | lint/rules/s036_invalid_pyproject.py | S036 |
| CREATE | lint/rules/s037_blanket_type_ignore.py | S037 |
| CREATE | lint/rules/s038_blanket_noqa.py | S038 |
| CREATE | lint/rules/s039_banned_api_policy.py | S039 |
| CREATE | lint/rules/s040_relative_imports.py | S040 |
| CREATE | lint/rules/s041_unspecified_encoding.py | S041 |
| CREATE | lint/rules/s042_raise_vanilla_class.py | S042 |
| CREATE | lint/rules/s043_verbose_log_message.py | S043 |
| CREATE | lint/rules/s044_logging_f_string.py | S044 |
| CREATE | lint/rules/s045_async_function_with_timeout.py | S045 |
| CREATE | lint/rules/s046_blocking_http_call_in_async_function.py | S046 |
| CREATE | lint/rules/s047_blocking_open_in_async_function.py | S047 |
| CREATE | lint/rules/s048_blocking_sleep_in_async_function.py | S048 |
| CREATE | lint/rules/s049_unsafe_yaml_load.py | S049 |
| CREATE | lint/rules/s050_insecure_hash.py | S050 |
| MODIFY | lint/core/ruff.py | Add selector union, preview mode, config, and TOML scan |
| MODIFY | lint/core/registry.py | Register S026-S050 |
| MODIFY | lint/baseline.json | Record 25 new allowances |
| MODIFY | lint/README.md | Document the expanded catalogue and policy |
| MODIFY | lint/rules/README.md | Add the 25 module index entries |
| DELETE | N/A | No files are deleted |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Ruff | Existing pinned dev dependency 0.16.4 | Implements all 25 analyzer rules | Preview and selector behavior must remain pinned |
| PyYAML | Existing runtime dependency | S506 reviews YAML loading in SDK source | Approved custom loaders need narrow review |
| pytest | Existing dev dependency | RUF043 validates SDK test assertions | Test regex intent must be reviewed |
| No external service | N/A | Lint runs offline over tracked files | No service or credential risk |

No new dependency installation is required.

---

## 11. Rollout & Deployment

- Commit this design document first in the isolated feature worktree.
- Implement S026 through S050 sequentially, committing logical groups only after
  each focused rule can run and its metadata is complete.
- Inspect representative findings and counterexamples before adding each
  baseline entry.
- Install the existing development extra and run the focused lint command after
  each rule.
- Run the full source gate, package gate, and combined scripts/run_ci.py after
  all rules are registered.
- This change is runtime-neutral and requires no deployment ordering or data
  migration.
- Roll back by reverting the rule/configuration commits; the runtime package
  remains unchanged.

---

## 12. Open Questions

- [ ] Should the initial TID251 banned API list expand beyond the three researched
  entries after the first SDK cleanup cycle?
- [ ] Should S041, S042, S045, and S049 remain count-ratcheted until the existing
  source debt has been reviewed by maintainers?
- [ ] Should preview-only Ruff rules be promoted to stable catalogue entries
  only after the pinned Ruff version makes them stable?

These questions do not block implementation because the initial policy is
explicit, baselined, and reversible.

---

## 13. Alternatives Considered

### Alternative 1: Reimplement Ruff checks as local AST visitors

- What: Write 25 independent Python analyzers.
- Why rejected: Ruff already maintains the language edge cases and version
  compatibility. Reimplementing them would increase false positives and create
  25 maintenance surfaces.

### Alternative 2: Run Ruff separately for every rule

- What: Give each S module its own subprocess invocation.
- Why rejected: It would make the edit/fix loop slow and cause analyzer output
  to drift between rules. The existing cached adapter is specifically designed
  to share one payload.

### Alternative 3: Use the repository's pyproject.toml as the analyzer config

- What: Put TID251 settings in the project configuration and let Ruff discover it.
- Why rejected: The SDK adapter intentionally avoids ambient configuration, and
  project Ruff settings could change analyzer behavior for unrelated tooling.
  A small explicit lint/ruff.toml keeps the policy reviewable and deterministic.

### Alternative 4: Initialize all new baselines at zero

- What: Make every new rule immediately zero-tolerance.
- Why rejected: Existing findings would make the suite unusable on day one.
  The established ratchet preserves the current freeze line while still failing
  any newly introduced violation.
