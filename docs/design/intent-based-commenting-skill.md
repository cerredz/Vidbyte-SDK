# Design Doc: Intent-Based Commenting as an Agentic Engineering Skill

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-28
**Last Updated:** 2026-06-28

---

## 1. Overview

This PR adds a new agentic engineering principle to the Vidbyte SDK prompt family: **Intent-Based Commenting for Business Logic**. The principle teaches models to preserve the why and meaning behind important business/domain code by placing a simple `@intent <short-name>` multiline comment directly beside the implementation it governs.

The principle is intentionally lightweight. It does not introduce a rigid field schema or runtime parser. The rule is: name the intent, then explain the business meaning clearly enough that a future agent can rewrite the implementation without losing the rule, invariant, incident lesson, compliance requirement, or customer consequence.

---

## 2. Goals & Non-Goals

### Goals

- Add `intent_based_commenting.md` inside `vidbyte/prompts/prompts/agentic_engineering/`.
- Register it in `agentic_engineering.json` under `intent_based_commenting`.
- Add `AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING` to the `Prompt` enum.
- Add a new Principle entry to `system_prompt.md` with use cases and GitHub link.
- Teach a simple `@intent <short-name>` multiline comment style.
- Explain what counts as business/domain logic with concrete examples.
- Provide short, medium, and long examples, including an orchestrator class that follows the function-design principle.

### Non-Goals

- Does not add a linter, Semgrep rule, AST parser, or enforcement tooling.
- Does not require a fixed field schema such as `@summary`, `@why`, `@contract`, or `@survivors`.
- Does not add tests because this PR only adds static prompt assets and catalog wiring.
- Does not modify any other prompt family.
- Does not change package runtime behavior.

---

## 3. Background & Context

Agent-native code changes frequently. An agent may refactor, split, rename, move, or regenerate a function while preserving its visible behavior. That can still lose the business meaning: why a guard exists, why a state transition is forbidden, why an operation must be idempotent, or why a piece of code is ordered in a non-obvious way.

Intent-based commenting puts that meaning next to the implementation. The comment is close enough that an agent reads it as part of the code, not as optional background material. The point is not to document every line. The point is to preserve the important why for code that carries product, customer, money, compliance, recovery, or domain consequences.

---

## 4. Requirements

### Functional Requirements

1. `intent_based_commenting.md` must include `# Description`, `# Intent`, body guidance, `# Things Not to Do`, `# Checklist`, and `# Code Examples`.
2. The `# Description` section must follow this flow: the reader is writing agent-native code; the principle is intent-based commenting; intent-based commenting is nearby explanation of important business/domain meaning; the file teaches how to write it while coding.
3. The `# Intent` section must emphasize:
   - preserving the why and meaning behind important code, not just implementation;
   - keeping that why very close to the implementation;
   - placing intent beside very important business/domain logic.
4. The business/domain logic section must explain the concept at a high level and provide 10-15 concrete examples.
5. The comment structure must be `@intent <short-name>` followed by multiline prose. It must not require a fielded schema.
6. The guidance must explain that some comments are 4-5 lines and some are 40-50 lines; the goal is capturing the actual intent, not reaching a specific length.
7. The file must not include linter enforcement guidance.
8. `# Things Not to Do` must describe what makes bad intent comments.
9. `# Checklist` must describe what a model must do to propose good intent comments.
10. `# Code Examples` must include short, medium, and long examples.
11. The long example must include an orchestrator class with a clean public interface and private leaf methods, reflecting the function-design principle.
12. `agentic_engineering.json`, `prompts.py`, and `system_prompt.md` must expose the new prompt.

### Non-Functional Requirements

- The principle file must be self-contained.
- Examples should use realistic billing, subscription, idempotency, permission, or compliance language.
- The prompt should avoid rigid ceremony and keep the central rule easy to remember.

---

## 5. High-Level Design

The prompt asset is added as a new principle file and then wired into the existing prompt catalog and enum.

```text
intent_based_commenting.md
        |
        v
agentic_engineering.json
        |
        v
Prompt enum
        |
        v
system_prompt.md Principle 5
```

---

## 6. Detailed Design

### 6.1 `intent_based_commenting.md`

The new prompt defines intent-based commenting as nearby preservation of why and business/domain meaning. It includes:

- a high-level description;
- the intent of the principle;
- a definition of business/domain logic;
- a numbered list of examples that qualify;
- a simple comment structure;
- writing guidance;
- things not to do;
- a checklist;
- examples with short, medium, long, and TypeScript variants.

The central structure is:

```python
# @intent short-name-for-the-rule
# Explain the meaning of this code in plain language. Say what business or
# domain rule must survive a rewrite, why the rule matters, and what a future
# agent must not accidentally remove.
def important_domain_operation(...):
    ...
```

### 6.2 `agentic_engineering.json`

Adds:

```json
"intent_based_commenting": {
  "path": "intent_based_commenting.md",
  "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md"
}
```

The family description is updated to mention intent comments alongside error messages, file headers, folder READMEs, and function design.

### 6.3 `prompts.py`

Adds:

```python
AGENTIC_ENGINEERING_INTENT_BASED_COMMENTING = "agentic_engineering.intent_based_commenting"
```

### 6.4 `system_prompt.md`

Adds a new Principle 5 entry describing intent-based commenting and listing use cases such as billing, payment, subscription, entitlement, permission, compliance, fulfillment, reconciliation, idempotency, orchestration, and non-obvious guards.

---

## 7. Data Model Changes

N/A.

---

## 8. API Changes

N/A.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md` | New principle prompt |
| CREATE | `docs/design/intent-based-commenting-skill.md` | Design doc |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/agentic_engineering.json` | Register prompt key |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add enum value |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Add Principle 5 |

---

## 10. Dependencies & External Services

None.

---

## 11. Rollout & Deployment

No feature flag is required. This is an additive prompt asset. Rollback is a normal revert.

---

## 12. Review Feedback Applied

- Rewrote the description to the requested high-level flow.
- Rewrote the intent section around preserving why/meaning close to important code.
- Removed the standalone litmus-test section.
- Replaced the business/domain taxonomy with a high-level explanation and examples.
- Removed linter enforcement content.
- Replaced the fixed schema with a simple `@intent <short-name>` multiline comment style.
- Reworked Things Not to Do and Checklist around good and bad intent comments.
- Replaced examples with short, medium, long orchestrator, and compliance-boundary examples.

---

## Summary

**Files:** 2 created, 3 modified
**Key risks:** Minimal. The prompt intentionally avoids runtime behavior and enforcement tooling.
**Open questions:** None.
