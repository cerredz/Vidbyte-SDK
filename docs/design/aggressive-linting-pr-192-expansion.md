# Design Doc: Aggressive Linting PR 192 Expansion

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-30
**Last Updated:** 2026-06-30

---

## 1. Overview

Expand the PR #192 aggressive-linting prompt so it explicitly captures the user's full set of aggressive linting ideas while preserving the existing prompt structure. The change is documentation/prompt content only: it strengthens the existing principles for size caps, architecture boundaries, banned patterns, security checks, test-integrity gates, ratchets, duplicate-code detection, import-time side-effect bans, fail-closed coverage, and imperative error messages without adding runtime code or changing prompt catalog registration.

---

## 2. Goals & Non-Goals

### Goals

- Add every user-provided aggressive linting idea to `vidbyte/prompts/prompts/agentic_engineering/aggressive_linting.md`.
- Integrate ideas into the existing numbered principles instead of pasting a duplicated appendix.
- Make missing examples concrete with Python-oriented lint tooling where appropriate: Ruff, mypy, import-linter, Semgrep, pylint, grimp/tach-style graph checks, duplicate-code tooling, and custom AST checks.
- Preserve the existing core framing that warnings become errors, baselines ratchet stricter, code volume can itself be a violation, and linter messages should read as direct agent instructions.
- Keep the prompt catalog registration unchanged because the aggressive-linting asset already exists in `agentic_engineering.json` and the `Prompt` enum on PR #192.

### Non-Goals

- No runtime SDK code changes.
- No new prompt family, enum value, JSON catalog entry, or package-data configuration change.
- No implementation of actual lint tooling in this repository.
- No new tests or verification scripts.
- No rewrite of unrelated agentic engineering prompt files.
- No changes to the unrelated dirty local worktree files under `vidbyte/paradigms/context_minimal_fanout/`.

---

## 3. Background & Context

PR #192 is `ai/resolve-pr-186-comments` into `ai/resolve-pr-182-comments` and currently changes two prompt assets: `aggressive_linting.md` and `system_prompt.md`. The aggressive-linting prompt is already a large markdown asset with 28 principles and examples; it is loaded through `vidbyte.prompts.catalog.Prompts`, registered by `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json`, and keyed by `Prompt.AGENTIC_ENGINEERING_AGGRESSIVE_LINTING`.

The local `vidbyte-sdk` worktree is currently on `feat/context-minimal-fanout-trace` and has unrelated modified files. Implementation must therefore happen in an isolated worktree based on PR #192's head branch or fetched PR ref so the existing user changes are not touched. Because the user explicitly asked for PR #192, the implementation target is the existing PR branch context, not a new feature from `main`.

The existing PR prompt already covers many requested concepts at a high level: error-only rules, imperative messages, escape hatch closure, strict typing, stubs/TODOs, error handling, deterministic core layers, hallucinated import guards, layer contracts, blessed wrappers, complexity caps, dangerous constructs, test integrity, recurring mistake rules, fail-closed coverage, pinned toolchains, baselines/ratchets, deterministic autofix, import-time side effects, async correctness, secrets, diff-vs-merge linting, package encapsulation, fan-out/fan-in, volume budgets, duplicate detection, and shared config. The implementation should therefore focus on filling concrete gaps and making the user's mental models explicit where the current text is broad.

---

## 4. Requirements

### Functional Requirements

1. The prompt must explicitly include size/shape caps for max nesting depth, max class size by method count, cyclomatic complexity, max boolean conditions per branch, and no magic numbers.
2. The prompt must explicitly include architecture/layer rules for directed dependency graphs, no cyclic imports, public-API-only imports, sibling feature independence, fan-in caps, and fan-out caps.
3. The prompt must explicitly include banned-pattern rules for `print()`, bare/blind `except`, mutable default arguments, wildcard imports, TODO/FIXME/HACK comments, unused imports/variables/dead code, and `assert` used for runtime validation.
4. The prompt must explicitly include security rules for hardcoded secrets, string-interpolated SQL, and forcing raw HTTP calls through an internal wrapper.
5. The prompt must explicitly include test-integrity rules for banning `skip`/`xfail`, banning tests without real assertions, and enforcing a coverage ratchet/floor.
6. The prompt must explicitly preserve and strengthen the uncommon aggressive moves: warning-to-error with zero exceptions, baseline plus ratchet, code volume as a violation, duplicate-code/reinvention detection, no import-time side effects, fail-closed handling for unparseable or ungoverned files, and imperative linter messages.
7. The update must deduplicate against the existing PR #192 text: add detail to the existing relevant principles rather than creating a second disconnected list of the same ideas.
8. The prompt must remain a Markdown text asset compatible with the existing prompt loader: non-empty plain text referenced from `agentic_engineering.json`.

### Non-Functional Requirements

- Maintainability: additions should be grouped under existing headings so future reviewers can find the relevant rule family.
- Reviewability: the diff should be smaller than a wholesale rewrite and should avoid moving large unrelated sections.
- Style: prose should match the existing prompt's direct, instructional tone and Python-oriented examples.
- Compatibility: no changes should be needed to package metadata, prompt enums, or loader code.
- Safety: do not touch unrelated local worktree changes.

---

## 5. High-Level Design

This is a content integration pass on the existing aggressive-linting prompt. The implementation will modify `aggressive_linting.md` in place, inserting concrete examples into the relevant current principles:

```text
[User idea list]
       |
       v
[Existing PR #192 aggressive_linting.md principles]
       |
       +--> Principle 11/26: size and shape caps
       +--> Principle 9/24/25: architecture and import graph walls
       +--> Principle 5/6/8/12/14: banned code patterns
       +--> Principle 10/12/21: wrapper, SQL, and secret security walls
       +--> Principle 13/17: test integrity and coverage ratchet
       +--> Principle 1/2/15/17/19/27: uncommon aggressive moves
```

The core design decision is to avoid appending the user's list verbatim. PR #192 already has a mature structure; appending a standalone brainstorm would make the prompt repetitive and harder for an agent to use. Instead, each idea becomes either a concrete rule example under an existing principle, a sentence that sharpens the principle's rationale, or a checklist item where the idea belongs as a verification obligation.

---

## 6. Detailed Design

### 6.1 Aggressive Linting Prompt

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/aggressive_linting.md`
**Type:** Modified

#### What it does

This markdown file is the deep-dive prompt for the agentic engineering aggressive-linting principle. It teaches agents to author fail-closed lint rules and architecture contracts rather than relying on prose conventions.

#### Interface / API

```markdown
# Description
# Intent
# Goal
# Intuition
# Generalized Principles to Follow for Aggressive Linters
### 1. Promote Every Rule From Warning to Error
...
### 28. Distribute One Versioned Config; Shard Rules by Path
# Updating Linters as the Codebase Grows
# Things Not to Do
# Checklist
# Code Examples
```

No public code interface changes. The asset remains loaded by the existing prompt catalog.

#### Logic / Algorithm

1. Re-read the PR #192 version of `aggressive_linting.md` and map each user idea to the existing principle that already owns that rule family.
2. Add missing size/shape examples to Principle 11 and/or Principle 26:
   - AST/custom linter example for nesting depth over 3.
   - Ruff/pylint examples for class method count, branch count, boolean expression complexity, and magic-value comparisons.
3. Add missing import graph and encapsulation examples to Principles 9, 24, and 25:
   - Explicit `api -> services -> repositories -> db` layer order.
   - Cycle detection as a hard failure.
   - Public API import boundary via package `__init__.py` / api module.
   - Sibling feature isolation.
   - Fan-in and fan-out caps with imperative failure messages.
4. Add missing banned-pattern examples to Principles 5, 6, 8, 12, and 14:
   - `T20`/Semgrep for `print()`.
   - `F403/F405` for wildcard imports.
   - `ARG`, `F401`, `F841`, `ERA001`, and vulture-style dead code checks where appropriate.
   - `B006`/`B008` or custom rules for mutable defaults.
   - `S101` or custom scoped Semgrep for no runtime validation via `assert`.
5. Add security examples to Principles 10, 12, and 21:
   - Raw HTTP requests/urllib ban routed to the internal HTTP client wrapper.
   - SQL interpolation ban requiring parameterized queries.
   - Hardcoded secret detection with Bandit, Semgrep regexes, and secret scanners.
6. Add test-integrity and ratchet language to Principles 13 and 17:
   - Ban `skip`/`xfail`.
   - Assertion-free test detection.
   - Coverage floor/ratchet where current coverage is recorded and future PRs may not drop below it.
7. Strengthen "uncommon aggressive moves" where already present:
   - Principle 1: no advisory lint warnings.
   - Principle 15: fail-closed on unparseable and ungoverned files/folders.
   - Principle 17: baseline plus ratchet, never loosen.
   - Principle 19: no import-time side effects.
   - Principle 27: duplicate-code/reinvention detector.
   - Principle 2: linter messages are prompts written as direct instructions.
8. Update the Checklist and Things Not to Do only where the additions create a new verification obligation.

#### Edge Cases & Error Handling

- If a requested idea is already present, the implementation should avoid duplicating it and instead make it more explicit only if the current wording is too broad.
- If a tool-specific rule is not perfectly expressible in a named off-the-shelf linter, the prompt should present it as a custom Semgrep or AST rule rather than pretending a built-in selector exists.
- If examples use placeholder package names, keep them consistent with the existing `app.*` examples in the prompt.

### 6.2 Design Doc

**File(s):** `docs/design/aggressive-linting-pr-192-expansion.md`
**Type:** New file

#### What it does

This design doc records the approved scope before implementation, as required by the `design-doc-no-tests` workflow.

#### Interface / API

```markdown
# Design Doc: Aggressive Linting PR 192 Expansion
```

#### Logic / Algorithm

1. Capture requirements, non-goals, detailed file plan, risks, rollout, rollback, and alternatives.
2. Use this document as the implementation source of truth after user approval.

#### Edge Cases & Error Handling

- N/A - documentation-only planning artifact.

---

## 7. Data Model Changes

N/A - no schema, dataclass, database, JSON catalog, enum, or package metadata changes.

---

## 8. API Changes

N/A - no runtime API, CLI command, MCP endpoint, or prompt catalog key changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/aggressive-linting-pr-192-expansion.md` | Required design document for the scoped change |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/aggressive_linting.md` | Integrate all requested aggressive linting ideas into PR #192's existing prompt structure |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| GitHub PR #192 branch/ref | `origin/pr-192` / `ai/resolve-pr-186-comments` | Source branch for the prompt file being updated | Branch may move before implementation; re-fetch before editing |
| Existing prompt catalog loader | Local `vidbyte.prompts.catalog.Prompts` | Confirms the markdown asset remains loadable | Low; content-only change should not affect loader behavior |

---

## 11. Rollout & Deployment

- No feature flags.
- No deployment order.
- Implementation should happen in an isolated worktree based on PR #192's head branch/ref.
- Because the user specified PR #192, the expected rollout is updating that existing PR branch rather than opening an unrelated PR from `main`.
- Rollback is reverting the documentation/prompt commit on the PR branch.

---

## 12. Open Questions

- [ ] Should `system_prompt.md` be updated if the aggressive-linting prompt expansion makes the existing summary incomplete? Recommendation: do not touch it unless a final comparison shows a concrete stale claim.
- [ ] Should the implementation push directly to PR #192's head branch or create a follow-up branch targeting PR #192's base? Recommendation: update PR #192's head branch if the local GitHub permissions allow it, because the user explicitly asked to add the ideas to PR #192.

---

## 13. Alternatives Considered

### Alternative 1: Append the user list verbatim as a new section

- What: Add a new "Additional Aggressive Linting Ideas" section containing the full list.
- Why rejected: The PR file already has a detailed principle structure. A verbatim appendix would duplicate existing content and make the prompt less actionable for an agent.

### Alternative 2: Modify `system_prompt.md` only

- What: Expand the short agentic engineering system prompt summary to mention these ideas.
- Why rejected: The detailed aggressive-linting guidance lives in `aggressive_linting.md`; only that file can hold concrete examples without bloating the system prompt.

### Alternative 3: Implement real lint config in the SDK repository

- What: Add Ruff, mypy, Semgrep, import-linter, or custom AST rules to the repository.
- Why rejected: The user asked to update the aggressive-linting skill/prompt file for PR #192, not to add repo-level enforcement. Runtime/tooling changes would be a larger, separate feature.
