# Design Doc: Intent-Based Commenting as an Agentic Engineering Skill

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-28
**Last Updated:** 2026-06-28

---

## 1. Overview

This PR adds a new agentic engineering principle to the Vidbyte SDK prompt family: **Intent-Based Commenting for Business Logic**. The principle teaches models to split code into two layers that change at different rates — a slow "intent" layer that expresses the meaning, contract, and invariants of important business logic, and a fast "implementation" layer that agents freely rewrite. Intent is pinned next to the implementation via structured `@intent` comment blocks so it survives every regeneration: the comment cannot drift because it is re-read fresh every time the agent touches the function. The principle defines what qualifies as business logic, provides a fixed comment schema with field-by-field guidance, gives the litmus test for distinguishing intent from narration, and shows how to enforce coverage with a linter.

---

## 2. Goals & Non-Goals

### Goals
- Add `intent_based_commenting.md` as a new principle file inside `vidbyte/prompts/prompts/agentic_engineering/`
- Register it in `agentic_engineering.json` under the key `intent_based_commenting`
- Add `AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING` to the `Prompt` enum
- Add a new numbered Principle entry to `system_prompt.md` with use-case trigger list and GitHub link
- Match the exact structure (`# Description`, `# Intent`, body sections, `# Things Not to Do`, `# Checklist`, `# Code Examples`) established by the existing principle files

### Non-Goals
- Does not add test files (design-doc-no-tests contract)
- Does not add a runtime comment-parser or AST tooling to the SDK itself
- Does not modify any other prompt families or catalog infrastructure
- Does not change how the linter is wired up beyond describing it in prose (linter config belongs in the harness, not the SDK prompt)
- Does not depend on PR #182 (aggressive linting) or PR #181 (folder_readme / function_design); this PR is independent and based off current main

---

## 3. Background & Context

The first three agentic engineering principles address how to structure static artifacts that agents read: error messages, file headers, and folder READMEs. A fourth principle (aggressive linting, PR #182) addresses how to make wrong code mechanically unproducible. This fifth principle addresses a different gap: even with all four prior principles in place, agents can still silently destroy meaning while preserving behavior.

The problem is that code has two layers that change at different rates. The intent — the domain rule, the idempotency guarantee, the regulatory constraint — is supposed to stay true for months. The implementation is under constant churn when agents are the primary authors; the same function may be rewritten five times in a week. Normal code fuses these layers together: the only record of what the code means is the code itself, so every rewrite puts the meaning at risk. A behavior-preserving refactor can still delete the understanding of why something is built the way it is.

Intent comments un-fuse the layers. They express the slow layer explicitly, in structured prose, pinned physically adjacent to the implementation. Because they live three lines above the function body, they are co-retrieved with the code every time the agent edits it — they cannot be missed the way a design doc can be missed. They function as the regeneration prompt the function carries with it: when the agent rewrites the body, the `@intent` block is the spec it regenerates against. This makes the intent comment the lowest-decay prompt in the system: unlike a system-prompt instruction that degrades as context fills, the `@intent` block is re-read fresh, in full, on every encounter with the function.

---

## 4. Requirements

### Functional Requirements
1. `intent_based_commenting.md` must follow the exact section structure of existing principle files: `# Description`, `# Intent`, named body sections, `# Things Not to Do`, `# Checklist`, `# Code Examples`.
2. The `# Description` section must explain: (a) what intent comments are, (b) the two-layer framing (slow intent / fast implementation), (c) why proximity to the code is the load-bearing property (co-retrieval guarantee), and (d) the intent comment as the regeneration prompt that travels with the function.
3. The `# Intent` section must be two paragraphs: what the principle accomplishes, and the specific agent failure mode it closes (silent meaning destruction during behavior-preserving rewrites).
4. The body must cover:
   - **The litmus test**: "would this comment survive a total rewrite?" — the single question that distinguishes intent from narration
   - **What counts as business logic** (the five qualifying categories: domain rules/invariants, correctness/safety/money paths, concurrency/idempotency guarantees, hard-won fixes, regulatory/compliance constraints)
   - **What does NOT qualify** (CRUD boilerplate, framework plumbing, glue code, obvious transformations)
   - **The `@intent` comment schema** — a fixed set of named fields, each with a description of what it captures and why
   - **How to write each field** — guidance for pitching content at the right level of abstraction
   - **Linter enforcement** — how a Semgrep or AST-based rule can detect business-logic functions that lack an `@intent` block
5. The `@intent` schema must include at minimum: an ID, a summary, a `@why` field (rationale / hard-won fix context), a `@contract` field (input/output invariants), a `@constraints` field (non-obvious rules the implementation must satisfy regardless of how it is written), and a `@survivors` field (cross-references to tests, ADRs, or other artifacts whose correctness depends on this intent).
6. `# Things Not to Do` must enumerate: narration instead of intent, over-tagging boilerplate, leaving `@why` empty for non-obvious code, letting `@contract` drift from the actual signature, writing `@constraints` that describe the current implementation rather than the permanent rule.
7. `# Checklist` must cover: identifying business-logic functions before writing code, writing the `@intent` block before the function body, applying the litmus test to every field, updating the `@intent` block after a rewrite rather than deleting it, verifying `@survivors` references still exist.
8. `# Code Examples` must include: (a) a Python example of a full `@intent` block on a billing/subscription function, (b) a TypeScript example on a concurrency/idempotency-critical function, and (c) a Semgrep rule that detects business-logic functions missing an `@intent` block.
9. `agentic_engineering.json` must add an `intent_based_commenting` entry with correct `path` and `source_url`.
10. `prompts.py` must add `AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING = "agentic_engineering.intent_based_commenting"` grouped with the other `AGENTIC_ENGINEERING_*` entries.
11. `system_prompt.md` must add a numbered Principle entry with a one-paragraph description, a `Use Cases:` list, and a `GitHub:` URL. (The number will be 4 on main since PR #182 is unmerged; it may need adjusting when PRs are ordered at merge time.)

### Non-Functional Requirements
- The principle file must be self-contained: a model that has never seen the motivating conversation should be able to understand the principle, apply the schema, and pass the litmus test from the file alone
- All code examples must use realistic domain language (billing, subscriptions, idempotency) consistent with the error_messages.md examples already in the family
- The `@intent` schema field names must use `@` prefix to be machine-parseable by a future linter or tooling pass

---

## 5. High-Level Design

A new markdown file `intent_based_commenting.md` is authored as a self-contained deep-dive prompt. It gives the agent a single litmus test, a precise boundary for what qualifies as business logic, a fixed comment schema, field-level writing guidance, and linter enforcement patterns. The principle is then registered in the JSON catalog, the enum, and the system prompt's Principle index so the router knows when to load it.

```
[intent_based_commenting.md]  (new principle file)
        |
        v
[agentic_engineering.json]    (adds intent_based_commenting key)
        |
        v
[Prompt enum]                 (adds AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING)
        |
        v
[system_prompt.md]            (adds new Principle entry with use-case list)
```

---

## 6. Detailed Design

### 6.1 intent_based_commenting.md

**File:** `vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md`
**Type:** New file

#### What it does
Deep-dive reference for the intent-based commenting principle. A model that determines this principle applies (by reading the use cases in system_prompt.md) fetches this file and executes its checklist.

#### Interface / API
No code interface — Markdown prompt asset. Consumed via `Prompts().get(Prompt.AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING)` or by fetching the GitHub URL.

#### Logic / Algorithm
Section order:
1. `# Description` — the two-layer framing, why proximity is the load-bearing property, the intent comment as regeneration prompt
2. `# Intent` — two paragraphs: what the principle accomplishes, which agent failure mode it closes
3. `# The Litmus Test: Would It Survive a Total Rewrite?` — the single governing question; distinguishes intent from narration; explains why narration rots under churn
4. `# What Counts as Business Logic` — the five qualifying categories with examples; explicit "does not qualify" list
5. `# The @intent Comment Schema` — all fields, each with: name, purpose, what to write, what not to write
6. `# How to Write Each Field` — concrete guidance on pitching content at the right abstraction level
7. `# Linter Enforcement` — Semgrep pattern to detect business-logic functions without `@intent` blocks; CI integration guidance
8. `# Things Not to Do`
9. `# Checklist`
10. `# Code Examples`

#### The `@intent` schema fields

| Field | Purpose |
|-------|---------|
| `@intent [ID]: [name]` | Persistent identifier + short name. ID survives renames/reorganizations. |
| `@summary` | 1–2 sentences: what this code must do. Pitched at the level of abstraction where a reimplementation cannot make it false. |
| `@why` | Why this approach was chosen, or what went wrong before. The "hard-won fix" field. |
| `@contract` | Input/output invariants: pre-conditions that must hold before entry, post-conditions guaranteed on exit. Not the type signature — the semantic contract. |
| `@constraints` | Non-obvious rules the implementation must satisfy regardless of how it is written: idempotency guarantees, ordering requirements, regulatory constraints, concurrency invariants. |
| `@survivors` | Cross-references to tests, ADRs, log entries, or other artifacts whose correctness depends on this intent being preserved. |

---

### 6.2 agentic_engineering.json

**File:** `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json`
**Type:** Modified

```json
"intent_based_commenting": {
  "path": "intent_based_commenting.md",
  "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md"
}
```

---

### 6.3 prompts.py

**File:** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

```python
AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING = "agentic_engineering.intent_based_commenting"
```
Added grouped with the other `AGENTIC_ENGINEERING_*` entries.

---

### 6.4 system_prompt.md

**File:** `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md`
**Type:** Modified

New Principle entry with:
- One-paragraph description of intent-based commenting
- Use Cases trigger list covering: identifying a business-logic function, writing `@intent` before a function body, applying the litmus test, tagging a concurrency/idempotency guarantee, tagging a hard-won fix, tagging a regulatory constraint, updating `@intent` after a rewrite, verifying `@survivors` still exist, detecting narration in an existing comment and converting it, auditing a module for untagged business logic before a PR

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
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md` | New principle deep-dive prompt |
| CREATE | `docs/design/intent-based-commenting-skill.md` | This design doc |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json` | Register intent_based_commenting key |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING enum value |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Add new Principle entry |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | — | Prompt text assets only | None |

---

## 11. Rollout & Deployment

- No feature flags needed — additive prompt assets
- No breaking changes — existing keys and enum values unchanged
- Rollback: revert the PR; no side effects

---

## 12. Open Questions

- [ ] The Principle number in system_prompt.md will be 4 on current main, but may need to be renumbered to 5 when PR #182 merges first. **Accepted risk** — the number is a display label, not a semantic key; renumbering is a trivial one-line fix.
- [ ] Should the `@intent` ID format be prescribed (e.g., `R-NNN` for rules, `I-NNN` for invariants) or left free-form? **Decision: free-form slug is better** — rigid numbering systems require a registry and add maintenance cost the principle file itself cannot enforce.

---

## 13. Alternatives Considered

### Alternative 1: Docstring-only (no schema)
- What: require intent documentation but in free-prose docstrings, no fixed field schema
- Why rejected: free prose produces inconsistent coverage and is not machine-parseable. A fixed schema makes the `@why` and `@constraints` fields individually enforceable. The schema also trains the agent to think in terms of the distinct layers (what, why, contract, constraints) rather than collapsing them into a paragraph.

### Alternative 2: External intent registry file (`INTENTS.md`)
- What: maintain a separate file listing all intent anchors, linked to from the code by ID
- Why rejected: external documents are not co-retrieved with the code. The load-bearing property of intent comments is physical proximity — the agent reads them because it has no choice. An `INTENTS.md` is a document the agent might retrieve; a comment above the function is an input it cannot avoid.

### Alternative 3: Combine with file_headers.md
- What: add intent block guidance as a section of the existing file headers principle
- Why rejected: file headers operate at file granularity; intent comments operate at function granularity. The governing logic (the litmus test, the business-logic boundary, the schema) is specific to individual functions in business-critical code and does not generalize to the header use case.

---

## Summary

**Files:** 2 created, 3 modified
**Key risks:** Principle number in system_prompt.md may need renumbering at merge time if PR #182 merges first (trivial fix)
**Open questions:** All resolved above

**Awaiting explicit approval before proceeding to implementation.**
