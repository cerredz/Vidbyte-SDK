# Design Doc: Aggressive Linting as an Agentic Engineering Skill

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-27
**Last Updated:** 2026-06-27

---

## 1. Overview

This PR adds a fourth agentic engineering principle to the Vidbyte SDK prompt family: **Aggressive Linting for Agent-Native Codebases**. The principle teaches models to use linters as a deterministic enforcement layer that holds architectural judgment on behalf of agents — so that correctness migrates from prose system-prompt instructions (which decay over long context windows) into fail-closed, mechanically enforced rules. It covers the full taxonomy of wall-style linting patterns (architecture, types, security, test integrity, API contracts, infra-as-code, agent-native), the operational generate→verify→repair loop that wires linters into a harness, and the escape-hatch closure strategy that prevents agents from defeating their own guardrails.

---

## 2. Goals & Non-Goals

### Goals
- Add `aggressive_linting.md` as a new principle file inside `vidbyte/prompts/prompts/agentic_engineering/`
- Register the new principle in `agentic_engineering.json` under the key `aggressive_linting`
- Add `AGENTIC_ENGINEERING_AGGRESSIVE_LINTING` to the `Prompt` enum in `vidbyte/lib/enums/prompts.py`
- Add Principle 4 entry (with use cases and GitHub link) to `system_prompt.md` so the router indexes the new skill
- Match the exact structure (Description, Intent, section body, Things Not to Do, Checklist, Code Examples) established by the existing principle files

### Non-Goals
- Does not modify or depend on PR #181's folder_readme or function_design additions (this PR bases off current main)
- Does not add test files (following the design-doc-no-tests skill contract)
- Does not install, configure, or run any real linters in the SDK itself
- Does not change any other prompt families or catalog infrastructure

---

## 3. Background & Context

The agentic engineering prompt family teaches models to produce code that is cheap for downstream agents to read, navigate, debug, and modify. The three existing principles (error messages, file headers, folder READMEs) all address how to structure the static knowledge baked into source files. A fourth principle is needed that addresses *enforced correctness* — making wrong patterns mechanically impossible rather than just unlikely or discouraged.

The conversation motivating this addition identified three moves: **cache** (read one, skip many), **steer** (make the right line the path of least resistance), and **wall** (delete the wrong move from the space of expressible programs). Walls are linters. The key insight for agents specifically is that an over-strict linter is appropriate for agents in a way it never was for human teams: agents feel no friction, so the human tradeoff between strictness and morale collapses entirely. Additionally, a lint rule re-evaluates from scratch on every run and never forgets, making it immune to the context-window decay that degrades prose instructions.

This principle also covers the operational loop: the harness mechanism that feeds lint results back into the agent's context window as imperative instructions, ties completion to exit code rather than the agent's self-report, and places the same rules in three locations (in-loop, pre-commit, CI) in decreasing speed and increasing authority.

---

## 4. Requirements

### Functional Requirements
1. `aggressive_linting.md` must follow the exact section structure of the existing principle files: `# Description`, `# Intent`, named body sections, `# Things Not to Do`, `# Checklist`, `# Code Examples`.
2. The `# Description` section must explain what aggressive linting is, why agents specifically benefit from it (context-window decay argument), and the core principle (migrate correctness from prose to mechanism).
3. The `# Intent` section must be two paragraphs: what the principle is trying to accomplish, and what failure mode it specifically addresses in agent-native codebases.
4. The body must cover at minimum: architecture/dependency walls, type-system walls, security walls, test-integrity gates, API/contract enforcement, infra-as-code policy, agent-native patterns (stub detection, error-handling discipline, hallucination guards, determinism, convention lock-in, escape-hatch closure), and the operational harness loop.
5. Each category must include: the specific linter tool name, a real config snippet or command, and the generalized principle it instantiates.
6. `# Things Not to Do` must enumerate agent-specific anti-patterns: using warnings instead of errors, linting only at CI rather than in-loop, writing messages as diagnostics rather than imperatives, failing to close escape hatches (disable comments, `any` casts, `@ts-ignore`).
7. `# Checklist` must be action-item-style, covering: before writing code (configure caps), during implementation (treat cap violations as design signals), and after completing a module (verify all escape hatches are closed).
8. `# Code Examples` must include at minimum: (a) a real ESLint/Ruff config snippet showing wall rules, (b) a Semgrep rule showing the failure-mode-to-rule pattern, and (c) a Python harness snippet showing the generate→verify→repair loop with SARIF/JSON parsing.
9. `agentic_engineering.json` must add an `aggressive_linting` entry with correct `path` and `source_url`.
10. `prompts.py` must add `AGENTIC_ENGINEERING_AGGRESSIVE_LINTING = "agentic_engineering.aggressive_linting"` grouped with the other `AGENTIC_ENGINEERING_*` entries.
11. `system_prompt.md` must add a numbered Principle 4 entry with: a one-paragraph description, a `Use Cases:` list, and a `GitHub:` URL.

### Non-Functional Requirements
- The principle file must be dense enough to serve as a self-contained reference (no relying on the conversation transcript as implicit context)
- All config snippets must use the real tool name and real config key names (no invented APIs)
- The error message / lint output format used in Code Examples must be imperative-phrased so it functions as an instruction to the agent, not a diagnostic to a human

---

## 5. High-Level Design

A new markdown file `aggressive_linting.md` is authored as a self-contained deep-dive prompt. It covers the taxonomy of wall-style linting patterns (grouped by the agent failure mode each category walls off), the three-layer enforcement model (in-loop → pre-commit → CI), the escape-hatch closure strategy, and the operational harness loop. The principle is registered in the JSON catalog so it can be fetched by key, exposed via the MCP server, and referenced by enum in SDK consumer code.

The system prompt is updated to include the new principle as Principle 4, with a use-case trigger list that matches the granularity of the existing principles' use-case lists.

```
[aggressive_linting.md]
        |
        v
[agentic_engineering.json]  <-- adds aggressive_linting key
        |
        v
[Prompt enum]  <-- adds AGENTIC_ENGINEERING_AGGRESSIVE_LINTING
        |
        v
[system_prompt.md]  <-- adds Principle 4 with use cases
```

---

## 6. Detailed Design

### 6.1 aggressive_linting.md

**File:** `vidbyte/prompts/prompts/agentic_engineering/aggressive_linting.md`
**Type:** New file

#### What it does
Serves as the deep-dive reference for the aggressive linting principle. A model that determines this principle applies to its task (by reading the use cases in system_prompt.md) fetches this file and executes its checklist.

#### Interface / API
No code interface — this is a Markdown prompt asset. Consumed by `Prompts().get(Prompt.AGENTIC_ENGINEERING_AGGRESSIVE_LINTING)` or by fetching the GitHub URL.

#### Logic / Algorithm
Section order:
1. `# Description` — what the principle is, why agents need it, the prose-to-mechanism migration argument
2. `# Intent` — two paragraphs: what it accomplishes, what failure mode it closes
3. `# The Wall: Three Enforcement Layers` — in-loop, pre-commit, CI ordering with rationale
4. `# Architecture and Dependency Walls` — dependency-cruiser, import-linter, eslint-plugin-import, @nx/enforce-module-boundaries, cycle detection
5. `# Type System as Wall` — strict tsconfig flags, exhaustiveness checks + assertNever, branded types, no-explicit-any, mypy --strict
6. `# Security Walls` — Semgrep taint mode, gitleaks pre-commit + CI, Bandit, OSV-Scanner/npm audit
7. `# Test Integrity Gates` — no-only/no-skip, diff-cover, mutation testing floor, ratchets/betterer
8. `# API and Contract Enforcement` — API Extractor snapshots, oasdiff/buf breaking, runtime validators
9. `# Infra-as-Code Policy` — Conftest/OPA, Checkov/Trivy, Kyverno admission control
10. `# Agent-Native Walls` — stub/dead-code detection (knip, vulture), error-handling discipline (no bare except, no-floating-promises), hallucination guards (import/no-unresolved, import/no-extraneous-dependencies), determinism (ban Math.random in core layers), convention lock-in (no-restricted-imports, no-restricted-syntax), escape-hatch closure (ban @ts-ignore, ban eslint-disable-file, ban type: ignore), the failure-mode-to-rule pipeline
11. `# The Operational Harness Loop` — machine-readable output, lint tool in harness, feed to context, exit-code completion gate, context budget management
12. `# Things Not to Do`
13. `# Checklist`
14. `# Code Examples`

#### Edge Cases & Error Handling
N/A — this is a prompt file, not executable code.

---

### 6.2 agentic_engineering.json

**File:** `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json`
**Type:** Modified

#### What it does
Registers `aggressive_linting` as a prompt key in the agentic engineering family so it can be resolved by the catalog.

#### Interface / API
```json
"aggressive_linting": {
  "path": "aggressive_linting.md",
  "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/aggressive_linting.md"
}
```

---

### 6.3 prompts.py

**File:** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does
Adds the typed enum key so SDK consumers can reference the new prompt without using raw strings.

#### Interface / API
```python
AGENTIC_ENGINEERING_AGGRESSIVE_LINTING = "agentic_engineering.aggressive_linting"
```
Added after the existing `AGENTIC_ENGINEERING_*` entries.

---

### 6.4 system_prompt.md

**File:** `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md`
**Type:** Modified

#### What it does
Adds Principle 4 to the router index so the model knows when to load the aggressive linting deep-dive.

#### Interface / API
New principle entry following the exact same format as Principles 1–3:
- One paragraph description
- `Use Cases:` comma-separated trigger list
- `GitHub:` URL

#### Logic / Algorithm
Use cases will cover: configuring a new module's linter before writing code, treating a lint cap violation as a design signal, adding a custom Semgrep rule for a recurring agent mistake, setting up the generate→verify→repair loop in a harness, closing an escape hatch (`@ts-ignore`, `any`, `eslint-disable`), auditing a module for unused exports and dead code, adding a CVE gate to CI, configuring diff-coverage on a PR pipeline, writing linter error messages as imperatives rather than diagnostics, banning raw dependencies in favor of blessed wrappers, enforcing layer boundaries with import-linter or dependency-cruiser, detecting stub/placeholder code before declaring a task complete, wiring a lint tool into an agent harness and feeding SARIF output to context.

---

## 7. Data Model Changes

N/A — no schema changes.

---

## 8. API Changes

N/A — no HTTP endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/aggressive_linting.md` | New principle deep-dive prompt |
| CREATE | `docs/design/aggressive-linting-skill.md` | This design doc |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json` | Register aggressive_linting key |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add AGENTIC_ENGINEERING_AGGRESSIVE_LINTING enum value |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Add Principle 4 entry |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | — | This PR adds prompt text assets only | None |

---

## 11. Rollout & Deployment

- No feature flags needed — prompt assets are additive and do not change existing behavior
- No breaking changes — existing `Prompt` enum values and JSON keys are unchanged
- No migration needed
- Rollback: revert the PR; no side effects on existing prompts

---

## 12. Open Questions

- [ ] Should the principle number in system_prompt.md be 4 (since PR #181 is unmerged, making this the true 4th principle on main)?  **Yes** — this PR bases off main which has 3 principles; this becomes Principle 4.
- [ ] Should we use `aggressive_linting` or `linting` as the key? **`aggressive_linting`** — more descriptive and matches the user's framing of the concept.

---

## 13. Alternatives Considered

### Alternative 1: Split into multiple smaller principle files (one per category)
- What: separate files for architecture-walls, security-walls, agent-native-walls, operational-loop
- Why rejected: the existing principles are comprehensive single-file deep-dives; splitting would require routing logic in system_prompt.md for sub-principles, adding complexity without clear benefit

### Alternative 2: Integrate linting content into the existing function_design.md
- What: add the linter enforcement section to function_design.md rather than creating a standalone file
- Why rejected: linting is a cross-cutting discipline that applies to architecture, security, tests, and infra — not just function shape. It deserves its own principle with its own use-case trigger list.

---

## Summary

**Files:** 2 created, 3 modified  
**Key risks:** None — purely additive prompt text assets  
**Open questions:** All resolved above

**Awaiting explicit approval before proceeding to implementation.**
