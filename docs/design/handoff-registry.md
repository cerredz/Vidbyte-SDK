# Design Doc: Software-Engineering Handoffs & Handoff Registry

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

> **Stacked PR.** Builds on `feat/handoff-primitive-catalog` (PR #108), which builds on `feat/handoff-agent` (PR #105). This PR contains only the new code (15 software-engineering `Handoff` subclasses + a `HandoffRegistry`) and assumes #105 and #108 are merged. No code from those PRs is repeated. Retarget the base to `main` once they land.

---

## 1. Overview

This change adds fifteen software-engineering-specific prebuilt `Handoff` primitives — each tuned to a distinct SWE task type (code review, bug fix, refactor, performance, testing, API design, schema migration, dependency upgrade, incident response, architecture decision, codebase onboarding, CI/CD, integration, security remediation, release) — and a `HandoffRegistry` in `vidbyte/lib/registries/` that lets a developer discover every prebuilt handoff the SDK offers, inspect its structure, construct it, or build a `HandoffAgent` from it by name.

---

## 2. Goals & Non-Goals

### Goals

- Add fifteen SWE `Handoff` subclasses in `vidbyte/context/handoffs.py`, each a title + decision-oriented section map.
- Export each from `vidbyte/context/handoffs.py` `__all__`, `vidbyte/context/__init__.py`, and `vidbyte/__init__.py`.
- Add `HandoffRegistry` in `vidbyte/lib/registries/handoffs.py`, prefilled with every prebuilt handoff (3 base + 10 process-shape + 15 SWE = 28), following the existing registry conventions.
- Provide discovery helpers: `list`, `get`, `create`, `all`, `register`, `describe` (title + section map per prebuilt), and `build_agent` (construct a `HandoffAgent` from a named handoff).
- Export `HandoffRegistry` from `vidbyte/lib/registries/__init__.py` and the root `vidbyte` namespace.
- Update the handoff skill doc and add tests + a verification script.

### Non-Goals

- No changes to the base `Handoff`, `HandoffAgent`, `BaseAgent` integration, or the handoff prompt asset (owned by #105).
- No new prompt assets or `Prompt` enum members; SWE handoffs reuse the existing handoff system prompt.
- No global singleton registry instance and no category grouping (per scoping decision); the registry is instance-based like `AgentRegistry`.
- No re-implementation of any #105/#108 code.

---

## 3. Background & Context

PR #105 established the `Handoff` primitive and `HandoffAgent`; PR #108 added ten process-shape prebuilts. The skill doc documents the recipe for new prebuilts. This change applies that recipe to the software-engineering domain and adds a registry so the growing catalog is discoverable from one place, mirroring the existing `AgentRegistry`, `RuntimeRegistry`, and `ActorRegistry` under `vidbyte/lib/registries/`. The registry is instance-based and prefilled on construction (like `AgentRegistry`), and uses `ConfigurationError` for unknown names (like `ActorRegistry`/`RuntimeRegistry`).

Because the SWE handoffs subclass `Handoff` and the registry references all prebuilts (including #108's), this PR stacks on `feat/handoff-primitive-catalog`.

---

## 4. Requirements

### Functional Requirements

1. Fifteen new `Handoff` subclasses exist in `vidbyte/context/handoffs.py`, each overriding `DEFAULT_TITLE` and `default_sections()` with a non-empty ordered map.
2. All section maps are pairwise distinct across the full 28-prebuilt catalog.
3. `default_sections()` returns a fresh dict per call.
4. Each new class is exported from the three export sites and satisfies the `ContextItem` protocol and `fill()` type preservation (inherited).
5. `HandoffRegistry` is prefilled with all 28 prebuilts keyed by a stable slug (e.g. `code_review`, `tree_search`, `engineering`).
6. `HandoffRegistry.get(name)` returns the class; unknown names raise `ConfigurationError`.
7. `HandoffRegistry.create(name, **kwargs)` returns a `Handoff` instance.
8. `HandoffRegistry.register(name, cls)` adds or overrides an entry (name normalized to lowercase).
9. `HandoffRegistry.list()` returns sorted slugs; `all()` returns a dict copy.
10. `HandoffRegistry.describe()` returns, per slug, the class name, title, and full section map.
11. `HandoffRegistry.build_agent(name, **agent_kwargs)` returns a `HandoffAgent` configured with the named handoff (lazy import to avoid cycles).
12. `HandoffRegistry` is exported from `vidbyte/lib/registries/__init__.py` and root `vidbyte`.

### Non-Functional Requirements

- **Zero new runtime dependencies**; standard library only.
- **No import cycles**: the registry imports `vidbyte.context.handoffs` at module load (safe — context never imports registries) and lazily imports `HandoffAgent` inside `build_agent`.
- **Backward compatible**: purely additive.
- **Context Protocol Header** on every new file.
- **Testing**: Python `unittest`, no network — fake runners only.

---

## 5. High-Level Design

Each SWE handoff is a ~10-line `Handoff` subclass (title + section map), identical in mechanics to the existing prebuilts. The `HandoffRegistry` is a thin instance-based catalog: its `__init__` copies a module-level `_DEFAULT_HANDOFFS` mapping of slug → class (covering all 28 prebuilts) into instance state, and its methods provide discovery (`list`, `all`, `describe`), construction (`get`, `create`), extension (`register`), and a one-stop agent factory (`build_agent`).

```
vidbyte/context/handoffs.py   Handoff base + 28 prebuilt subclasses (3 + 10 + 15)
                                   ^ imported by
vidbyte/lib/registries/handoffs.py   HandoffRegistry  (slug -> class catalog)
                                   ^ lazily builds
vidbyte/agents/handoff.py            HandoffAgent (via build_agent)
```

Key decisions: (1) SWE classes live in `handoffs.py` alongside the others (their natural home); (2) registry is instance-based and prefilled, matching `AgentRegistry`, with no global singleton (per scope); (3) `build_agent` lazily imports `HandoffAgent` so the registries package has no import-time dependency on the agents runtime.

---

## 6. Detailed Design

### 6.1 SWE `Handoff` subclasses

**File(s):** `vidbyte/context/handoffs.py` — Modified (append fifteen classes + extend `__all__`)

Adds: `CodeReviewHandoff`, `BugFixHandoff`, `RefactorHandoff`, `PerformanceOptimizationHandoff`, `TestAuthoringHandoff`, `APIDesignHandoff`, `SchemaMigrationHandoff`, `DependencyUpgradeHandoff`, `IncidentResponseHandoff`, `ArchitectureDecisionHandoff`, `CodebaseOnboardingHandoff`, `CICDPipelineHandoff`, `IntegrationHandoff`, `SecurityRemediationHandoff`, `ReleaseHandoff`. Each overrides `DEFAULT_TITLE` and `default_sections()`. Full section maps in Appendix A. No other methods overridden.

### 6.2 `HandoffRegistry`

**File(s):** `vidbyte/lib/registries/handoffs.py` — New

```python
class HandoffRegistry:
    def __init__(self) -> None: ...                                  # prefill from _DEFAULT_HANDOFFS
    def register(self, name: str, handoff_cls: type[Handoff]) -> None: ...
    def get(self, name: str) -> type[Handoff]: ...                   # ConfigurationError if missing
    def create(self, name: str, **kwargs: Any) -> Handoff: ...
    def list(self) -> list[str]: ...                                 # sorted slugs
    def all(self) -> dict[str, type[Handoff]]: ...                   # dict copy
    def describe(self) -> dict[str, dict[str, Any]]: ...             # slug -> {class, title, sections}
    def build_agent(self, name: str, **agent_kwargs: Any): ...       # -> HandoffAgent (lazy import)
```

Logic: `__init__` copies `_DEFAULT_HANDOFFS`; `get`/`create`/`build_agent` resolve by normalized lowercase name; `describe` instantiates each class once to read `title` and `sections`; `build_agent` lazily imports `HandoffAgent` and passes a freshly constructed spec.

Edge cases: unknown name → `ConfigurationError` listing available names; `register` normalizes/overrides; `create` forwards kwargs to the `Handoff` constructor while `build_agent` forwards kwargs to the agent.

### 6.3 Registry package export

**File(s):** `vidbyte/lib/registries/__init__.py` — Modified. Add `HandoffRegistry` import + `__all__` entry.

### 6.4 Context + root exports

**File(s):** `vidbyte/context/__init__.py`, `vidbyte/__init__.py` — Modified. Export the fifteen SWE classes; root also exports `HandoffRegistry`.

### 6.5 Skill doc

**File(s):** `skills/vidbyte-sdk/handoff.md` — Modified. Add the SWE catalog table and a registry usage section.

### 6.6 Tests + verification script

**File(s):** `tests/test_handoff_registry.py` (new), `scripts/test_handoff_registry.py` (new).

---

## 7. Data Model Changes

N/A — no schema/database changes. Additions are in-memory `Handoff` subclasses and one registry class.

---

## 8. API Changes

N/A for HTTP. New Python exports: fifteen SWE handoff classes (from `vidbyte` and `vidbyte.context`) and `HandoffRegistry` (from `vidbyte` and `vidbyte.lib.registries`). All additive.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/handoff-registry.md` | This design doc (first commit) |
| MODIFY | `vidbyte/context/handoffs.py` | Add fifteen SWE `Handoff` subclasses + `__all__` |
| MODIFY | `vidbyte/context/__init__.py` | Export the fifteen SWE classes |
| MODIFY | `vidbyte/__init__.py` | Root exports for SWE classes + `HandoffRegistry` |
| CREATE | `vidbyte/lib/registries/handoffs.py` | `HandoffRegistry` |
| MODIFY | `vidbyte/lib/registries/__init__.py` | Export `HandoffRegistry` |
| MODIFY | `skills/vidbyte-sdk/handoff.md` | Document the SWE catalog and the registry |
| CREATE | `tests/test_handoff_registry.py` | Tests for the SWE classes and the registry |
| CREATE | `scripts/test_handoff_registry.py` | Phase 5 verification script |

---

## 10. Testing Plan

Python `unittest` with fake runners, no network. `SWE` = the fifteen new classes; `ALL` = all 28 prebuilts.

### Unit Tests

- `it('every SWE variant exposes a non-empty default_sections map')` — [Edge Case]
- `it('all 28 prebuilt section maps are pairwise distinct')` — [Silent Failure]
- `it('every SWE variant fill() returns the same subclass')` — [Silent Failure]
- `it('every SWE variant is a ContextItem and has a non-default title')` — [Hidden Assumption]
- `it('default_sections returns a fresh dict per instance for a SWE variant')` — [Hidden Failure]
- `it('registry.list() contains all 28 slugs')` — [Edge Case]
- `it('registry.get(slug) returns the matching class for several slugs')` — [Hidden Assumption]
- `it('registry.get(unknown) raises ConfigurationError listing available names')` — [Hidden Assumption]
- `it('registry.create(slug) returns a Handoff instance of the right type')` — [Edge Case]
- `it('registry.register then get/create works and normalizes case')` — [Edge Case]
- `it('registry.register overrides an existing slug')` — [Hidden Failure]
- `it('registry.describe() returns class, title, and non-empty sections for every slug')` — [Silent Failure]
- `it('registry.all() returns a copy that does not mutate registry state')` — [Hidden Failure]
- `it('two registry instances are independent (register on one does not affect the other)')` — [Hidden Failure]

### Integration Tests

- `it('registry.build_agent(slug, runner=fake).generate_handoff(...) returns a filled handoff of that type')` — [Hidden Assumption] (registry → HandoffAgent → parsed sections, end to end). Use a SWE slug with punctuated section titles (e.g. `cicd_pipeline` → "Build/Deploy Config", `api_design` → "Request/Response Schemas").
- Silent-failure path: `describe()` must reflect a freshly `register`-ed custom handoff, not a stale snapshot — [Silent Failure].
- Mock vs real: fake runner only.

### Manual / QA Test Cases

1. Given `from vidbyte import HandoffRegistry`, when `HandoffRegistry().describe()["code_review"]` is read, then it contains the title "Code Review Handoff" and a "Verdict" section — [Edge Case].
2. Given `HandoffRegistry().build_agent("bug_fix", runner=fake)`, when run, then a filled `BugFixHandoff` is produced — [Hidden Assumption].
3. Given `registry.get("does_not_exist")`, then `ConfigurationError` is raised — [Hidden Assumption].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | 3.11+ | Types, unittest | None |
| `vidbyte.context.handoffs` (PR #105/#108) | stacked branch | Base class + prebuilts referenced by the registry | Medium — unmergeable to `main` until #105/#108 land; mitigated by stacking |

No new third-party packages.

---

## 12. Rollout & Deployment

- No feature flags. Additive, backward compatible.
- **Stacked PR**; base `feat/handoff-primitive-catalog`. Merge order: #105 → #108 → `main`, then retarget this PR to `main`.
- Rollback: revert the PR; no migrations or persisted state.

---

## 13. Open Questions

- [x] Registry surface: `describe()` + `build_agent()` included; `categories()` and a global singleton excluded (per scope).
- [x] Stacking: only the new code, assuming #105/#108 merged (base `feat/handoff-primitive-catalog`).
- [ ] Slug naming for acronym classes (`CICDPipelineHandoff` → `cicd_pipeline`, `APIDesignHandoff` → `api_design`): resolved by an explicit slug map rather than derived from the class name, to avoid acronym-splitting bugs.

---

## 14. Alternatives Considered

### Alternative 1: Classmethod registry like `RuntimeRegistry`
- What: stateless registry with classmethods.
- Why rejected: `register` for custom handoffs fits an instance better, and `AgentRegistry` (instance-based, prefilled) is the closer analog for a discoverable catalog.

### Alternative 2: Derive slugs from class names automatically
- What: regex CamelCase → snake_case.
- Why rejected: acronym classes (`CICD`, `API`) split incorrectly; an explicit slug map is unambiguous.

### Alternative 3: Put SWE handoffs in a separate module
- What: a new `handoffs_swe.py`.
- Why rejected: fragments the catalog; the established home is `vidbyte/context/handoffs.py`.

---

## Appendix A — SWE handoff section maps

Each entry is `Section Title → guidance description`, implemented verbatim.

**CodeReviewHandoff** (Code Review Handoff): Scope Reviewed; Blocking Issues; Non-Blocking Suggestions; Approved Aspects; Unresolved Threads; Verdict.
**BugFixHandoff** (Bug Fix Handoff): Symptom; Reproduction; Root Cause; Fix Applied; Tests Added; Regression Risk.
**RefactorHandoff** (Refactor Handoff): Motivation; Scope & Boundaries; Behavior-Preservation Evidence; Changes by Module; Risk Areas; Follow-up Cleanups.
**PerformanceOptimizationHandoff** (Performance Optimization Handoff): Baseline Metrics; Bottlenecks Identified; Optimizations Applied; Measured Improvement; Trade-offs; Remaining Hotspots.
**TestAuthoringHandoff** (Test Authoring Handoff): Coverage Goal; Areas Covered; Test Cases Added; Gaps & Untested Paths; Flaky/Skipped Tests; Next Tests.
**APIDesignHandoff** (API Design Handoff): Purpose & Consumers; Endpoints/Contracts; Request/Response Schemas; Versioning & Compatibility; Error Model; Open Design Questions.
**SchemaMigrationHandoff** (Schema Migration Handoff): Schema Change; Migration Steps; Backfill Plan; Forward/Backward Compatibility; Data-Integrity Checks; Rollback Plan.
**DependencyUpgradeHandoff** (Dependency Upgrade Handoff): Target Versions; Breaking Changes; Code Adjustments Made; Compatibility Verification; Remaining Deprecations; Rollback.
**IncidentResponseHandoff** (Incident Response Handoff): Impact & Severity; Timeline; Current Mitigation; Root-Cause Status; Action Items; Comms Status.
**ArchitectureDecisionHandoff** (Architecture Decision Handoff): Problem & Context; Options Considered; Decision & Rationale; Consequences & Trade-offs; Open Risks; Next Steps.
**CodebaseOnboardingHandoff** (Codebase Onboarding Handoff): Goal; System Map; Key Components & Responsibilities; Entry Points & Data Flow; Conventions & Gotchas; Open Questions.
**CICDPipelineHandoff** (CI/CD Pipeline Handoff): Pipeline Goal; Stages & Status; Build/Deploy Config; Secrets & Environments; Failing/Flaky Stages; Next Steps.
**IntegrationHandoff** (Integration Handoff): Integration Goal; External Contract; Auth & Credentials; Implemented Surface; Edge Cases & Failure Modes; Untested Paths.
**SecurityRemediationHandoff** (Security Remediation Handoff): Vulnerabilities; Severity & Exploitability; Fixes Applied; Verification; Residual Risk; Remaining Items.
**ReleaseHandoff** (Release Handoff): Release Scope; Changelog; Pre-Deploy Checklist; Deploy Steps; Verification & Smoke; Rollback Plan.
