<!-- Context Protocol Header
Description:
    Design document for adding cognitive problem-solving actor prompts.
Purpose:
    Defines the prompt schemas, markdown assets, and enums for Explorer, Decomposer,
    and Evaluator actors in the Vidbyte SDK.
Architecture:
    System Prompt markdown assets and prompt registration.
Relations:
    Located in docs/design/cognitive-actor-prompts.md.
-->

# Design Doc: Cognitive Actor Prompts

**Status:** Draft
**Author:** Antigravity
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

This feature designs and integrates three new abstract **Cognitive Actor Prompts** into the Vidbyte SDK prompts catalog: **Explorer**, **Decomposer**, and **Evaluator**. These actors represent fundamental elements in a general problem-solving space rather than task-specific roles. To ensure complete isolation and zero duplication, this PR only adds the prompt JSON declarations, markdown files, and enum registrations, allowing them to be dynamically picked up and registered by the actor model runtime once merged.

---

## 2. Goals & Non-Goals

### Goals
- Add the `actor_runtime` prompt family JSON descriptor `vidbyte/prompts/prompts/actor_runtime/actor_runtime.json` containing references to the three new actors.
- Implement the Markdown prompt assets for `explorer.md`, `decomposer.md`, and `evaluator.md`.
- Register the corresponding prompt enum keys in `vidbyte/lib/enums/prompts.py`.
- Formulate a comprehensive unit test verifying prompt registry loading and enums in `tests/test_cognitive_prompts.py`.

### Non-Goals
- Duplicating the underlying actor model brokers, message queues, or execution classes from PR #66 (which is still in verification/merge phase).
- Implementing tool call bindings or runtime orchestration graphs in this PR.

---

## 3. Background & Context

In general problem-solving theory, complex goals are rarely solved by flat sequential plans. Instead, they require expanding the search space with alternative hypotheses (Exploration), breaking down high-level states into orthogonal sub-problems (Decomposition), and objectively scoring intermediate outcomes (Evaluation). 

While PR #66 defines the execution plumbing, providing these three general-purpose cognitive prompts directly in the SDK prompts catalog empowers developers to build abstract problem-solving swarms.

---

## 4. Requirements

### Functional Requirements

1. **Abstract Prompt Definitions**:
   - **`explorer`**: A system prompt instructing the model to expand the search space, generate alternative ideas, and brainstorm hypotheses without pruning.
   - **`decomposer`**: A system prompt instructing the model to break down high-level, complex goals into granular, independent variables or tasks.
   - **`evaluator`**: A system prompt instructing the model to assign objective confidence/value scores (0.0 to 1.0) to intermediate states based on constraint checklist completion.
2. **Markdown-Backed Structure**: Follow the Vidbyte SDK prompt standard (`skills/vidbyte-sdk/adding-prompts.md`) using a JSON descriptor referring to local Markdown files.
3. **Enum Verification**: Verify that the three new prompts are importable and accessible via `Prompts().get(...)`.

### Non-Functional Requirements
- **Validation speed**: $O(1)$ enum checks at compile time.
- **Traceability**: System prompts must be readable, reviewable, and version-controlled.

---

## 5. High-Level Design

The three new prompts are registered under the `actor_runtime` prompt family.

```text
vidbyte/prompts/prompts/actor_runtime/
  |-- actor_runtime.json  --> Lists explorer, decomposer, evaluator MD files
  |-- explorer.md         --> System instructions for divergent space expansion
  |-- decomposer.md       --> System instructions for subdividing goals
  `-- evaluator.md        --> System instructions for assigning value scores
```

When the SDK's central `Prompts` catalog initializes, it dynamically scans `vidbyte/prompts/prompts/` subdirectories, parses the JSON file, loads the corresponding `.md` assets, and registers them under the `Prompt` enum keys:
* `Prompt.ACTOR_RUNTIME_EXPLORER = "actor_runtime.explorer"`
* `Prompt.ACTOR_RUNTIME_DECOMPOSER = "actor_runtime.decomposer"`
* `Prompt.ACTOR_RUNTIME_EVALUATOR = "actor_runtime.evaluator"`

---

## 6. Detailed Design

### 6.1 [New File] Actor Runtime JSON Descriptor
**File(s):** `vidbyte/prompts/prompts/actor_runtime/actor_runtime.json`
**Type:** New file

#### What it does
Registers the three new cognitive actor prompts under the `actor_runtime` family.

#### Interface / API
```json
{
  "name": "Actor Runtime",
  "description": "System prompts for abstract cognitive problem-solving actors.",
  "key": "actor_runtime",
  "prompts": {
    "explorer": {
      "path": "explorer.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/explorer.md"
    },
    "decomposer": {
      "path": "decomposer.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/decomposer.md"
    },
    "evaluator": {
      "path": "evaluator.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/actor_runtime/evaluator.md"
    }
  }
}
```

---

### 6.2 [New File] Explorer Prompt Markdown Asset
**File(s):** `vidbyte/prompts/prompts/actor_runtime/explorer.md`
**Type:** New file

---

### 6.3 [New File] Decomposer Prompt Markdown Asset
**File(s):** `vidbyte/prompts/prompts/actor_runtime/decomposer.md`
**Type:** New file

---

### 6.4 [New File] Evaluator Prompt Markdown Asset
**File(s):** `vidbyte/prompts/prompts/actor_runtime/evaluator.md`
**Type:** New file

---

### 6.5 [Modify] Prompt Enums
**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified file

#### Interface / API
```python
class Prompt(str, Enum):
    # ...
    ACTOR_RUNTIME_EXPLORER = "actor_runtime.explorer"
    ACTOR_RUNTIME_DECOMPOSER = "actor_runtime.decomposer"
    ACTOR_RUNTIME_EVALUATOR = "actor_runtime.evaluator"
```

---

## 7. Data Model Changes
N/A

---

## 8. API Changes
N/A

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/actor_runtime/actor_runtime.json` | JSON family descriptor |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/explorer.md` | Explorer Markdown prompt asset |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/decomposer.md` | Decomposer Markdown prompt asset |
| CREATE | `vidbyte/prompts/prompts/actor_runtime/evaluator.md` | Evaluator Markdown prompt asset |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Register the three new Prompt enum keys |

---

## 10. Testing Plan

We will add a validation test script `scripts/test-cognitive-actor-prompts.py` to assert that:
- **`test_prompt_enum_resolves` [Edge Case]**: The three new enum keys resolve perfectly in the `Prompt` class.
- **`test_prompt_text_loads_correctly` [Hidden Assumption]**: `Prompts().get(Prompt.ACTOR_RUNTIME_EXPLORER)` correctly loads the complete Markdown text rather than the JSON path dictionary or empty strings.
- **`test_prompt_keys_present_in_catalog` [Silent Failure]**: The keys exist in `Prompts().keys()` and their descriptions are not empty.

---

## 11. Dependencies & External Services
N/A

---

## 12. Rollout & Deployment
This is a non-breaking additions-only release. No existing prompt enums or strategies are modified.

---

## 13. Open Questions
None. The roles and prompts are aligned.

---

## 14. Alternatives Considered
None. Adding the prompts to the central catalog is the only way to adhere to Vidbyte SDK prompt guidelines.
