# Design Doc: Create Skills Prompt

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-29
**Last Updated:** 2026-08-29

---

## 1. Overview

Add a new Markdown-backed `create_skills` prompt family to the Vidbyte SDK prompt catalog. The prompt will guide an agent through designing a narrowly scoped, portable skill directory with progressive disclosure, setup validation, deterministic scripts, optional hooks, append-only evidence, cache-aware context layout, structured user questions, and 2–3 adversarial review passes after the first implementation. The change is static prompt content plus the enum and README metadata required by the existing prompt asset loader; it does not add runtime behavior or new dependencies.

---

## 2. Goals & Non-Goals

### Goals

- Add a discoverable `Create Skills` prompt asset under the existing SDK prompt directory.
- Encode all user-supplied principles 75–88 as actionable skill-authoring guidance, including their context-economics rationale and tradeoffs.
- Incorporate the supplied Claude and Cursor source findings: skill directories, narrow scope, activation-oriented descriptions, gotchas, progressive disclosure, setup assistants, structured elicitation, tool-surface review, memory, scripts, hooks, verification, and environment governance.
- Require the generated skill plan to separate implementation guidance from product verification and to combine visual evidence with machine-checkable assertions when the target permits both.
- Require 2–3 adversarial review passes after the first implementation and resolution of all critical or notable findings before completion.
- Register the prompt through `Prompt` so `Prompts().get(...)` and the generated direct import expose the Markdown body.
- Keep the canonical `vidbyte/prompts/README.md` catalog synchronized with the new family.

### Non-Goals

- Do not create or install an actual external skill directory from this change.
- Do not add a new runtime hook engine, setup assistant implementation, browser verifier, memory store, or structured-question API to the SDK.
- Do not add provider-specific tool schemas, tool-call payloads, credentials, customer data, or network calls to the prompt asset.
- Do not change prompt interpolation, catalog loading, package-data rules, or public APIs beyond the required enum key.
- Do not add new feature test files; existing prompt-interface and package gates remain required.

---

## 3. Background & Context

- The SDK stores prompt assets under `vidbyte/prompts/prompts/`. Current authoring guidance prefers one folder per larger prompt family containing a JSON descriptor and Markdown leaf prompts, with one `Prompt` enum member per leaf.
- `vidbyte.prompts.catalog.Prompts` discovers JSON descriptors, resolves sibling Markdown files, validates non-empty text, checks enum synchronization, and generates direct import names. Package data already includes nested JSON and Markdown assets.
- `vidbyte/prompts/README.md` is the human- and machine-readable prompt family catalog and must list the new family and link to its Markdown asset.
- The supplied Claude skills source describes skills as portable directories containing instructions, scripts, references, assets, configuration, and hooks. It emphasizes narrow scope, activation-oriented descriptions, progressive disclosure, gotchas, setup questions, append-only memory, deterministic scripts, on-demand hooks, distribution, and measuring usage.
- The supplied Cursor environment source emphasizes repository inspection, configuration as code, missing-credential detection, environment validation, version history, rollback, audit logs, and scoped egress/secrets as part of an agent-ready setup.
- The supplied Claude “Seeing like an agent” source emphasizes structured question tools over free-form elicitation, revisiting tools as model capabilities change, search interfaces that let agents build context, and progressive disclosure through nested resources or specialized subagents.
- The user’s principles 75–88 extend those sources with context-surface control, separate verification, visual plus programmatic evidence, on-demand safety modes, append-only evidence, deterministic mechanics, stable tool/model surfaces, static-to-dynamic prompt ordering, cache SLOs, cache-compatible compaction, and typed question interfaces.

---

## 4. Requirements

### Functional Requirements

1. Create a JSON descriptor at `vidbyte/prompts/prompts/create_skills/create_skills.json` with `name`, `description`, `key`, and a Markdown-backed `create_skill` prompt value.
2. Create `vidbyte/prompts/prompts/create_skills/create_skill.md` as a self-contained operational prompt for creating or revising one skill directory.
3. The prompt must explicitly cover principles 75–88, without dropping the stated rationale that scoping controls context and action surface, reduces token waste/tool confusion/unsafe operations, and trades off against maintaining discovery and permission rules.
4. The prompt must make skill descriptions activation conditions and must reject broad, multi-purpose skills unless the evidence supports one coherent class of work.
5. The prompt must guide the agent to decide which instructions belong in the main skill file and which belong in references, assets, scripts, configuration, hooks, or append-only evidence files.
6. The prompt must include setup-assistant behavior for missing repository context, credentials, services, or environment prerequisites, with structured questions where a user decision is required.
7. The prompt must separate implementation from product verification, require visual evidence plus DOM/console/network/test assertions when applicable, and define expected outcomes and evidence retention.
8. The prompt must require a post-implementation sequence of 2–3 adversarial reviews, each looking for missed requirements, over-broad scope, unsafe operations, stale assumptions, tool confusion, missing setup validation, and unverifiable claims. Critical and notable findings must be fixed before completion.
9. The prompt must specify cache-safe ordering: static system guidance and tools first, project context next, session context after that, and live conversation/dynamic state last. It must treat cache hit rate as an observable production concern and make compaction reuse cache-safe prefixes where possible.
10. The prompt must specify append-only evidence for memory, decisions, observations, and review outcomes; repeatable mechanics must be delegated to scripts or libraries rather than reimplemented by the model.
11. Add `CREATE_SKILLS_CREATE_SKILL = "create_skills.create_skill"` to `vidbyte/lib/enums/prompts.py` and update its agent-readable count header.
12. Add the family and description to `vidbyte/prompts/README.md`.
13. Existing generic prompt tests and the complete SDK CI gate must load the new asset, verify enum/import parity, compile the package, and confirm the built wheel includes the asset.

### Non-Functional Requirements

- Keep the prompt provider-neutral and free of secrets, credentials, customer data, and executable tool-call JSON.
- Keep the asset reviewable as Markdown and use progressive disclosure within the prompt so the workflow is complete without forcing every implementation detail into every run.
- Preserve the catalog’s existing JSON/Markdown contract and package-data behavior.
- Do not introduce runtime network access, new dependencies, or changes to the import-time public API other than the generated prompt key.
- Maintain deterministic, inspectable completion criteria and explicit failure behavior when prerequisites, evidence, or user decisions are missing.

---

## 5. High-Level Design

The new family will use the current SDK pattern for larger prompts: a JSON descriptor identifies the family and points to a sibling Markdown body. The catalog will resolve the Markdown into plain text, map it to a new enum member, and expose it through `Prompts().get(Prompt.CREATE_SKILLS_CREATE_SKILL)` and the generated `create_skills_create_skill` import.

The Markdown body will be organized as an operational manual. It will establish the agent’s role and input boundary, define the skill qualification and activation gate, prescribe a directory/resource design, handle setup and safety, define verification evidence, place cache/context economics in the workflow, and finish with the adversarial review and output contract. The supplied source URLs will be preserved in a short source-grounding section so the asset remains auditable without requiring runtime fetching.

The README catalog will add the new family beside the other prompt families and link to the direct Markdown asset. No loader or package-data code changes are required because the existing loader already supports nested JSON descriptors and sibling Markdown files.

```text
[Prompt descriptor JSON] -> [Prompts catalog] -> [Prompt enum + direct import]
          |                         |
          v                         v
 [Create Skills Markdown]     [SDK users / agents / MCP prompt access]
```

---

## 6. Detailed Design

### 6.1 Create Skills Markdown Prompt

**File(s):** `vidbyte/prompts/prompts/create_skills/create_skill.md`
**Type:** New file

#### What it does

Provides a reusable prompt for creating or revising one agent skill directory. It converts the supplied principles and source-backed practices into a bounded procedure that an agent can execute against a repository or skill request.

#### Interface / API

The prompt is plain Markdown text resolved by the existing catalog:

```text
Prompt.CREATE_SKILLS_CREATE_SKILL -> str
from vidbyte.prompts import create_skills_create_skill
```

The prompt accepts task-specific context through the caller’s surrounding conversation or agent context. It does not define a new SDK function or tool schema.

#### Logic / Algorithm

1. Establish the role, scope, inputs, and completion boundary; treat the request and repository as evidence and identify the one recognizable class of work the skill should solve.
2. Inspect the environment and ask structured questions for missing configuration, credentials, services, or user decisions before implementation.
3. Design a portable directory boundary with a concise activation-oriented main file and progressively disclosed references, scripts/libraries, assets, configuration, hooks, and append-only evidence as needed.
4. Encode the 75–88 principles as design checks: narrow scope, separate verification, combined evidence, on-demand safety, append-only memory, deterministic mechanics, stable surfaces, static-to-dynamic ordering, cache SLO awareness, cache-compatible compaction, and typed elicitation.
5. Implement the smallest useful skill shape, preserving model flexibility and avoiding generic restatements or unnecessary tools.
6. Verify the skill using the appropriate programmatic assertions and visual evidence, record expected outcomes, and retain evidence that supports completion.
7. Run 2–3 independent adversarial reviews after the first implementation, resolve every critical or notable finding, and record the review decisions in append-only evidence.
8. Return a structured handoff containing the skill purpose, activation conditions, directory tree, setup state, verification evidence, review findings, unresolved risks, and exact follow-ups.

#### Edge Cases & Error Handling

- If the scope cannot be reduced to one coherent class of work, stop and request clarification or recommend separate skills.
- If required credentials, services, tool access, or environment prerequisites are missing, report the exact prerequisite and ask a structured question; never guess or fabricate validation.
- If a hook or operation could cause destructive or externally visible effects, keep it off by default or require explicit confirmation and a narrowly scoped safety mode.
- If visual evidence is unavailable, use the strongest available programmatic evidence and state the missing modality rather than claiming full verification.
- If cache behavior or compaction cannot be measured in the target harness, specify the intended layout and mark measurement as an explicit follow-up.
- If an adversarial reviewer identifies a critical or notable gap, do not declare completion until the gap is fixed and the affected verification is rerun.

### 6.2 Prompt Family Descriptor

**File(s):** `vidbyte/prompts/prompts/create_skills/create_skills.json`
**Type:** New file

#### What it does

Declares the `create_skills` family and maps its `create_skill` leaf to the sibling Markdown asset and canonical GitHub source URL.

#### Interface / API

```json
{
  "name": "Create Skills",
  "description": "Prompt for designing narrowly scoped, verifiable, context-efficient skill directories.",
  "key": "create_skills",
  "prompts": {
    "create_skill": {
      "path": "create_skill.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/create_skills/create_skill.md"
    }
  }
}
```

#### Logic / Algorithm

The existing `Prompts` loader discovers the descriptor, validates the four required fields, resolves the sibling Markdown, validates non-empty prompt text, and requires the matching enum value. No new loader logic is introduced.

#### Edge Cases & Error Handling

- A missing or invalid descriptor, missing Markdown file, or missing enum member must fail through the existing catalog validation and CI rather than silently creating an unavailable prompt.
- The descriptor must use snake_case family and leaf keys so generated imports remain predictable.

### 6.3 Prompt Enum Registration

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds the enum identifier required for catalog synchronization and updates the file header’s asset count to reflect the new family and leaf.

#### Interface / API

```python
CREATE_SKILLS_CREATE_SKILL = "create_skills.create_skill"
```

#### Logic / Algorithm

Place the new member with the other family-level prompt identifiers, preserving the existing uppercase snake-case member convention. The catalog will derive `create_skills_create_skill` as the direct import name.

#### Edge Cases & Error Handling

- Duplicate enum values or a descriptor/enum mismatch are rejected by the existing prompt-interface checks.
- The enum count/header must not describe a stale asset inventory after the addition.

### 6.4 Prompt README Catalog

**File(s):** `vidbyte/prompts/README.md`
**Type:** Modified

#### What it does

Adds a quick-reference row and description for the `Create Skills` family, including its direct Markdown link and purpose.

#### Interface / API

N/A - This is static human- and machine-readable documentation; it does not change a runtime API.

#### Logic / Algorithm

Add the family to the quick-reference table and add a matching description section. Keep the catalog wording activation-oriented and consistent with the prompt’s actual scope.

#### Edge Cases & Error Handling

- The README link must target the canonical GitHub path for the Markdown asset.
- The description must not imply that the SDK itself creates external skills or supplies a hook/setup runtime.

---

## 7. Data Model Changes

N/A - The prompt catalog’s JSON descriptor shape is unchanged. The new descriptor uses the existing `name`, `description`, `key`, and `prompts` fields, and the new enum value is a static identifier rather than persisted application data.

---

## 8. API Changes

N/A - No HTTP, CLI, MCP, or Python callable API shape changes are introduced. The existing prompt catalog gains one enum-keyed text record and its generated direct import as required by the established asset contract.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/create-skills-prompt.md` | Source-of-truth design for the prompt asset and catalog integration |
| CREATE | `vidbyte/prompts/prompts/create_skills/create_skills.json` | Register the new Markdown-backed prompt family |
| CREATE | `vidbyte/prompts/prompts/create_skills/create_skill.md` | Provide the operational Create Skills prompt body |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Register the prompt enum member and correct the asset-count header |
| MODIFY | `vidbyte/prompts/README.md` | Add the prompt family to the canonical catalog |
| DELETE | N/A | No existing files are removed |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing Python package dependencies | Current `pyproject.toml` constraints | Load and validate prompt assets during tests and CI | No new dependency or version impact |
| Claude skills lessons | `https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills` | Source grounding for skill directories, scope, setup, memory, scripts, hooks, progressive disclosure, and verification | Source guidance may evolve; the prompt records principles rather than fetching it at runtime |
| Cursor cloud-agent environments | `https://cursor.com/blog/cloud-agent-development-environments` | Source grounding for environment setup, validation, credentials, versioning, audit, and scoped access | Product-specific details are generalized into provider-neutral guidance |
| Claude seeing-like-an-agent | `https://claude.com/blog/seeing-like-an-agent` | Source grounding for structured questions, tool-surface review, search, and progressive disclosure | Source guidance may evolve; no runtime dependency is introduced |

---

## 11. Rollout & Deployment

- No feature flags are involved.
- This is an additive prompt-catalog change and does not alter existing prompt text or runtime behavior.
- The new JSON and Markdown assets ship with the existing package-data rules in the next SDK build.
- Rollback is a commit revert that removes the new family, enum member, and README entry; no data migration or deployment ordering is required.

---

## 12. Open Questions

- [ ] Should the display label preserve the user’s spelling `Create-skils`, or should the public catalog normalize it to `Create Skills` while using canonical `create_skills` identifiers? Proposed decision: normalize the display label and identifiers because the repository requires predictable snake_case keys and the spelling appears to be a typo.
- [ ] Should a future follow-up split product verification into a separate prompt family once the SDK has a dedicated verification asset contract? Proposed decision: keep verification guidance inside this creation prompt for now and defer a separate family until a distinct reusable verifier workflow exists.

---

## 13. Alternatives Considered

### Alternative 1: Add the content as one inline root-level JSON string

- What: Put the full prompt body directly in a new root-level JSON descriptor.
- Why rejected: The repository’s current guidance prefers Markdown-backed assets for larger prompts because Markdown is easier to review, reuse, and progressively disclose.

### Alternative 2: Create a real skill directory in the SDK repository

- What: Add a `SKILL.md`, scripts, references, and configuration as an executable skill rather than a prompt asset.
- Why rejected: The request is for a reusable SDK prompt, and the SDK prompt catalog’s contract is separate from externally installed skill directories. The prompt can teach that directory shape without pretending the SDK owns an external harness.

### Alternative 3: Add only the user’s 75–88 text verbatim without an execution workflow

- What: Store the supplied principles as a reference list with no role, sequence, setup, verification, review, or output contract.
- Why rejected: A list would preserve information but would not reliably cause an agent to create a bounded skill. The requested source review adds operational patterns that must be turned into decisions and checks.
