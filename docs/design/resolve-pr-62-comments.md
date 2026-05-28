# Design Doc: Resolve PR 62 Comments (Prompt Templates)

**Status:** Draft  
**Author:** Antigravity (Advanced AI Coding Agent)  
**Created:** 2026-05-27  
**Last Updated:** 2026-05-27  

---

## 1. Overview

This design document outlines the technical plan for resolving all active review comments on PR #62 in the `vidbyte-sdk` repository, resolving existing merge conflicts with the `main` branch, opening a replacement pull request, and closing the old pull request. 

The original feature PR introduced high-quality **Prompt Templates** (Intent-Based, Persona-Based, and Specification-Based Prompting meta-prompts) to the SDK's file-backed prompt catalog. The review feedback focuses on removing repo-specific context headers from the raw LLM prompt assets, improving and structuring the persona template, broadening the scope of the specification template, and resolving overlapping additions in the prompt strategy bundles and exports.

---

## 2. Goals & Non-Goals

### Goals

- **Address Review Comments:**
  - Remove "Context Protocol" blocks from raw `.md` prompt templates (`intent_based.md`, `persona.md`, `specification.md`) so they do not pollute runtime LLM contexts.
  - Generalize the `specification.md` template so it applies to any task, not just software requirements.
  - Revise the `persona.md` template to state its goal (creating a persona-based prompt) in 5–6 sentences.
  - Structure `persona.md` with detailed guidelines describing every key pillar of a persona prompt (Identity, Role, Behavioral Patterns, Tone, Knowledge, Expertise, Intellect, etc.) in 3–4 sentences per section.
  - Add and describe different "types" of specifications in `specification.md` (e.g., interface/protocol, data validation, functional, formatting, etc.).
- **Resolve Merge Conflicts:**
  - Merge the changes from `feat/prompt-templates` cleanly with `main`, resolving any conflicts in `strategy_prompts.py`, `enums/prompts.py`, and public prompt inicializers.
- **Maintain Codebase Standards:**
  - Ensure all modified Python modules (`strategy_prompts.py`, `__init__.py`, etc.) contain a descriptive `Context Protocol Header` to satisfy the global workspace rules.
  - Retain class-first design and single-line signatures.
- **Create Replacement PR & Close Old PR:**
  - Establish a new worktree and branch off `main`, apply all updates, verify with tests, push the new branch, open a new PR, and close the old PR #62 with a reference link.

### Non-Goals

- Modifying how the `Prompts` catalog loads or parses `.json` and `.md` assets dynamically from directories.
- Rewriting unrelated prompt strategies (such as `mimic_behavior` or `goals`).

---

## 3. Background & Context

The Vidbyte SDK maintains a file-backed static prompts catalog loaded lazily via `Prompts` (`vidbyte/prompts/catalog.py`). To define new prompt assets:
1. Enum members are added to `Prompt` (`vidbyte/lib/enums/prompts.py`).
2. Assets are placed in `vidbyte/prompts/prompts/<family_name>/`.
3. A JSON mapping file `catalog.json` or `<family_name>.json` catalogs the assets.
4. Accessor classes subclassing `_PromptBundle` are exported under `vidbyte/prompts/strategies/`.

PR #62 introduced the `templates` family. However, the files were checked in with standard repository header comments (`Context Protocol`). These headers are extremely helpful for Python/JS source code, but when loaded as prompt string assets, they are sent directly as system instructions to external LLMs, leading to wasted input tokens and potential context confusion. Additionally, the persona and specification templates were deemed too lightweight and required structural detail and broader scopes.

---

## 4. Requirements

### Functional Requirements

1. **Remove Asset Context Headers:** Remove all `<!--- ... --->` context protocol blocks from:
   - `vidbyte/prompts/prompts/templates/intent_based.md`
   - `vidbyte/prompts/prompts/templates/persona.md`
   - `vidbyte/prompts/prompts/templates/specification.md`
2. **Generalize Specification Scope:** Replace "software requirements brief" or "software requirements" phrasing in `specification.md` with generalized terms to cover any target domain or task.
3. **Enhance Persona Template (`persona.md`):**
   - Incorporate a 5–6 sentence high-level goal block stating the precise target (generating a deeply immersive and domain-specific persona-based prompt).
   - Add structured guidelines describing the specific sections of a persona prompt: Identity, Role, Behavioral Patterns, Tone, Knowledge/Expertise, and Intellect. Each section must be described in 3–4 sentences.
4. **Expand Specification Types (`specification.md`):**
   - Add a dedicated section explaining different categories of specifications that can be generated (e.g. Functional specifications, Interface & Protocol specifications, Data & Validation specifications, Formatting & Structural specifications, Constraint & Limit specifications).
5. **Clean Merge Conflict Resolution:**
   - Resolve conflicts with additions from other parallel branches (like `MultiProviderAgenticGraderPrompts` in `strategy_prompts.py`).
   - Retain all public export routes so `vidbyte.prompts.PromptTemplatesPrompts` and the individual template strings are accessible.

### Non-Functional Requirements

- **Strict adherence to the `[user_global]` Context Protocol:** All modified or newly added Python files must have the Context Protocol block at the top.
- **Verification Script:** A dedicated Phase 5 test script (`scripts/test-prompt-templates.py`) must pass 100% and exit with code 0.

---

## 5. High-Level Design

The dynamic prompt loading flow remains unchanged. However, the assets themselves are purified and enriched:

```text
[vidbyte.prompts.catalog.Prompts]
       |
       +---> loads JSON catalog ---> [vidbyte/prompts/prompts/templates/templates.json]
       |                                   |
       |                                   +--> loads (purified) intent_based.md (No header)
       |                                   +--> loads (enriched) persona.md      (No header)
       |                                   +--> loads (enriched) specification.md  (No header)
       |
[PromptTemplatesPrompts]
       |
       +---> retrieves templates family from catalog
```

---

## 6. Detailed Design

### 6.1 Prompt Assets Refinement

#### 6.1.1 `vidbyte/prompts/prompts/templates/intent_based.md`
Remove lines 1 to 24 (the `<!--- Context Protocol ... --->` block) so the file starts directly with `# Intent-Based Prompt Generation Template`.

#### 6.1.2 `vidbyte/prompts/prompts/templates/persona.md`
- Remove the `<!--- Context Protocol ... --->` block.
- Update the overview/intro section. Insert the required 5–6 sentences explaining the high-level goal of creating a persona-based prompt.
- Add structural sections for each key pillar of a persona prompt, ensuring that each has a detailed 3–4 sentence explanation:
  - **Identity**: Sets the persona's core self-concept, age, history, and status.
  - **Role**: Defines the operational scope, responsibilities, and key behaviors.
  - **Behavioral Patterns**: Outlines decision-making strategies, typical cognitive heuristics, and habits.
  - **Tone**: Describes the precise linguistic profile, vocabulary complexity, and emotion level.
  - **Knowledge & Expertise**: Articulates the formal theories, tools, and background expertise possessed.
  - **Intellect**: Details the analytical depth, reasoning frameworks, and cognitive capabilities.

#### 6.1.3 `vidbyte/prompts/prompts/templates/specification.md`
- Remove the `<!--- Context Protocol ... --->` block.
- Change the intro to generalize "software requirements brief" into "general task or multi-disciplinary requirements brief".
- Add an explicit guide describing different types of specifications that can be synthesized:
  - **Functional Specifications**: Map out exactly what operations or results the system must achieve.
  - **Interface & Protocol Specifications**: Detail how inputs/outputs connect, including API routes or JSON schemas.
  - **Data & Validation Specifications**: Enforce type correctness, ranges, and validation constraints.
  - **Formatting & Structural Specifications**: Command precise layout rules, nesting levels, or file types.
  - **Constraint & Limit Specifications**: Command performance limits, token budgets, and security boundaries.

### 6.2 Python Code Integration & Conflict Resolution

#### 6.2.1 `vidbyte/prompts/strategies/strategy_prompts.py`
Resolve the merge conflict by keeping BOTH `MultiProviderAgenticGraderPrompts` and `PromptTemplatesPrompts` classes cleanly declared. 
Inject the `Context Protocol Header` at the top of the file.

```python
# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines strategy-specific prompt bundles for the Vidbyte SDK.
# Purpose: Groups prompts by strategy family to provide clean, unified accessors for agent pipelines.
# Architecture & Functions:
#   - _PromptBundle: Abstract base class that retrieves prompts dynamically from catalog by family key.
#   - PromptTemplatesPrompts: Accessor for the 'templates' prompt family.
# Codebase Relation:
#   - Imported by vidbyte.prompts and used by clients to fetch prompt strategies.
# Similar Files:
#   - vidbyte/prompts/catalog.py (supplies the prompt map)
# ==============================================================================
```

#### 6.2.2 `vidbyte/lib/enums/prompts.py`
Add the three template enum keys:
```python
    TEMPLATES_INTENT_BASED = "templates.intent_based"
    TEMPLATES_PERSONA = "templates.persona"
    TEMPLATES_SPECIFICATION = "templates.specification"
```
Ensure the `Context Protocol Header` is retained.

#### 6.2.3 `vidbyte/prompts/strategies/__init__.py` and `vidbyte/prompts/__init__.py`
Resolve conflicts by including `PromptTemplatesPrompts` in all dynamic exports and direct `__all__` imports. Ensure `Context Protocol Header` is present at the top of both files.

---

## 7. Data Model Changes

N/A - This change only affects prompt assets, enums, and Python imports. No database models are touched.

---

## 8. API Changes

N/A - No HTTP endpoints are modified or introduced.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add the three new prompt enum keys; retain Context Protocol header |
| MODIFY | `vidbyte/prompts/strategies/strategy_prompts.py` | Add the `PromptTemplatesPrompts` bundle class and resolve merge conflict; add Context Protocol |
| MODIFY | `vidbyte/prompts/strategies/__init__.py` | Export `PromptTemplatesPrompts` from strategy module; add Context Protocol |
| MODIFY | `vidbyte/prompts/__init__.py` | Export `PromptTemplatesPrompts` and direct templates imports; add Context Protocol |
| MODIFY | `vidbyte/prompts/prompts/templates/intent_based.md` | Remove context protocol block |
| MODIFY | `vidbyte/prompts/prompts/templates/persona.md` | Remove context protocol block; add detailed goal block and comprehensive structured guide pillars |
| MODIFY | `vidbyte/prompts/prompts/templates/specification.md` | Remove context protocol block; generalize task scope; add comprehensive types of specifications guide |
| MODIFY | `tests/test_prompts_interface.py` | Add unit tests for prompt template interfaces and exports; add Context Protocol |
| MODIFY | `tests/test_prompt_registry.py` | Add catalog loading validation tests; add Context Protocol |
| MODIFY | `scripts/test-prompt-templates.py` | Update verification test cases to validate new text shapes and ensure correct catalog loading; add Context Protocol |

---

## 10. Testing Plan

A comprehensive suite of test cases will verify the correct integration, validation, formatting, and structural safety of the new templates. Every test case is explicitly categorized.

### Automated Tests (pytest)

#### 1. Catalog Registration Tests
- **[Edge Case] `test_templates_registered_in_enum`**: Verifies that the new prompt family keys are in the `Prompt` enum and correctly parsed by `Prompts()`.
- **[Hidden Failure] `test_templates_load_without_configuration_errors`**: Asserts that `Prompts()._ensure_loaded()` resolves the sub-directory templates successfully without throwing configuration/JSON syntax errors.
- **[Silent Failure] `test_no_duplicate_template_ids`**: Validates that the keys mapped in `templates.json` do not overlap with existing keys in other families.

#### 2. Strategy Bundle Tests
- **[Edge Case] `test_prompt_templates_bundle_export`**: Verifies that calling `PromptTemplatesPrompts().export()` returns a map containing exactly `intent_based`, `persona`, and `specification` keys with non-empty string values.
- **[Hidden Assumption] `test_templates_formatted_output_structure`**: Verifies that the loaded templates are fully valid UTF-8 strings containing the specific placeholder variables or structural keywords (e.g., `{task}`, `{role}`, etc.) that the system expects.

#### 3. Public exports under `vidbyte.prompts`
- **[Silent Failure] `test_template_direct_imports`**: Asserts that `templates_intent_based`, `templates_persona`, and `templates_specification` are available as module-level attributes on `vidbyte.prompts` and match catalog strings.

#### 4. Enriched Structural Checks
- **[Edge Case] `test_templates_contain_no_context_protocols`**: Asserts that the string contents of the three loaded prompt templates contain NO context protocol keywords or markdown blocks `<!---` or `Context Protocol`.
- **[Hidden Assumption] `test_persona_contains_required_structural_pillars`**: Asserts that the persona prompt template contains sections matching `Identity`, `Role`, `Behavioral Patterns`, `Tone`, `Knowledge & Expertise`, and `Intellect`.
- **[Hidden Assumption] `test_specification_contains_specification_types`**: Asserts that the specification prompt template contains references to the expanded types of specifications.

---

## 11. Dependencies & External Services

No new external dependencies or library versions are introduced. All modifications use core Python standard library modules (`enum`, `json`) and existing package structures.

---

## 12. Rollout & Deployment

This is a non-breaking, purely additive change to the Vidbyte SDK.
- There are no database migrations.
- Backward compatibility is maintained 100%.

---

## 13. Open Questions

- **PR and Git branch coordination:** Should we base our new branch off `main`, merge `origin/feat/prompt-templates` into it, resolve conflicts, apply review fixes, and push to a new branch?
  - *Yes, that is the most robust way to ensure we do not touch the old branch while incorporating its commits, resolving merge conflicts, and adding the review fixes.*

---

## 14. Alternatives Considered

- **Preserving Context Protocol comments in `.md` files but stripping them at runtime:**
  - *Why rejected:* This would add runtime string splitting/parsing complexity and CPU overhead to prompt catalog loading. Keeping the raw files completely free of context comments is cleaner and less error-prone.

---
