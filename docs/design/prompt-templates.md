<!---
# Context Protocol: docs/design/prompt-templates.md
- Description: Design document for adding the "prompt templates" feature to Vidbyte SDK.
- Purpose: Establishes a formal, approved plan for introducing intent-based, persona, and specification prompt generation templates into the SDK prompt catalog.
- Architecture:
  - Catalog-driven prompts where YAML/Markdown assets map to specific Prompt enum keys.
  - Exposes new prompts via a `PromptTemplatesPrompts` bundle in `vidbyte.prompts.strategies`.
- Relation to the codebase:
  - Serves as the authoritative architectural blueprint and validation plan for this feature.
- Similar files:
  - docs/design/prompt-api-strategies-sdk.md (similar design doc)
--->

# Design Doc: Prompt Templates

**Status:** Draft  
**Author:** Antigravity  
**Created:** 2026-05-26  
**Last Updated:** 2026-05-26  

---

## 1. Overview

This design document outlines the implementation plan for introducing a suite of high-quality "prompt templates" to the Vidbyte SDK. These templates are specialized meta-prompts that guide LLMs in generating specific types of prompt assets:
1. **Intent-Based Prompting**: For synthesizing solely intent-driven, outcome-focused prompts.
2. **Persona Prompting**: For creating immersive, high-depth persona prompts (with Identity, Role, Goal, Expertise, Tone, Constraints).
3. **Specification Prompting**: For creating criteria-driven specification prompts that map out complete "acceptance criteria" and boundaries for success.

These assets will reside in a new `templates` subdirectory under `vidbyte/prompts/prompts/`, integrated directly into the SDK's existing file-backed prompt registry and enum system.

---

## 2. Goals & Non-Goals

### Goals

- Create a modular, folder-isolated structure for template assets under `vidbyte/prompts/prompts/templates/`.
- Implement high-fidelity prompt generation templates in three Markdown files: `intent_based.md`, `persona.md`, and `specification.md`.
- Integrate templates under a unified `"templates"` registry family by providing a `templates.json` mapping file.
- Expand the `Prompt` enum with members matching these three new assets.
- Expose the templates under a `PromptTemplatesPrompts` strategy class in `vidbyte.prompts.strategies`.
- Ensure 100% test coverage for registration, catalog indexing, format rendering, and error boundaries.

### Non-Goals

- Implementing actual runtime agent reasoning loops that *consume* these templates (this is purely an SDK asset provision task).
- Creating interactive CLI commands to run prompt synthesis (the user can invoke the SDK or MCP tools with the exposed prompts).

---

## 3. Background & Context

Modern prompt engineering benefits heavily from structured prompting paradigms. By housing these paradigm generators inside the SDK, developers using Vidbyte can dynamically compile high-quality prompts on the fly (e.g., generating an expert persona for a task or automatically writing unit-test specifications for a given feature description). 
Currently, the Vidbyte SDK supports strategies like Expert Prompting, Chain of Thought, Mimic Behavior, and others. Adding a dedicated folder-isolated family for template generation aligns perfectly with current repository patterns where larger, structural prompts are saved as `.md` files and registered in the unified `Prompt` catalog via `.json` indexing files.

---

## 4. Requirements

### Functional Requirements

1. **Isolation**: Prompt templates must be placed inside `vidbyte/prompts/prompts/templates/`.
2. **JSON Catalog Indexing**: A single `templates.json` file in that folder must define the `"templates"` prompt family and map keys (`intent_based`, `persona`, `specification`) to the respective Markdown files.
3. **Intent-Based Prompt Template (`intent_based.md`)**: A template that instructs the LLM to design an intent-based prompt. The resulting prompt must focus purely on user intent, goals, context, and quality metrics without prescribing mechanical instructions or paths.
4. **Persona Prompt Template (`persona.md`)**: A template that instructs the LLM to write a comprehensive persona-based prompt specifying Identity, Role, Goal, Core Expertise (heuristics, vocabulary), Tone, and Constraints.
5. **Specification Prompt Template (`specification.md`)**: A template that instructs the LLM to write a prompt centered on exhaustive "acceptance criteria" (input constraints, functional checklist, non-functional targets, verification).
6. **SDK Registration**: The `Prompt` enum must register:
   - `Prompt.TEMPLATES_INTENT_BASED = "templates.intent_based"`
   - `Prompt.TEMPLATES_PERSONA = "templates.persona"`
   - `Prompt.TEMPLATES_SPECIFICATION = "templates.specification"`
7. **Strategy Bundle Export**: A new strategy bundle `PromptTemplatesPrompts` must be exported from `vidbyte.prompts.strategies` to retrieve all templates.

### Non-Functional Requirements

- **Design System Consistency**: Code must adhere strictly to the `[user_global]` Context Protocol rule and the SDK's Class-First Design / Single-Line signature policies.
- **Zero Overhead**: Prompts must be loaded lazily and cached using the SDK's existing `Prompts` catalog mechanism.

---

## 5. High-Level Design

The existing `Prompts` catalog automatically scans `vidbyte/prompts/prompts` and its subdirectories for JSON files.
By putting a `templates.json` index file in `vidbyte/prompts/prompts/templates/`, `Prompts._json_assets` will find it, read it, and dynamically load the referenced Markdown files (`intent_based.md`, `persona.md`, `specification.md`).

```text
[vidbyte.prompts.catalog.Prompts]
       | (loads JSON assets)
       +---> [vidbyte/prompts/prompts/templates/templates.json]
                   | (references Markdown assets)
                   +---> intent_based.md
                   +---> persona.md
                   +---> specification.md
```

This structure maintains absolute consistency with how `mimic_behavior` and `goals` prompts are registered.

---

## 6. Detailed Design

### 6.1 Prompt Enum Additions

**File:** `vidbyte/lib/enums/prompts.py`  
**Type:** Modified  

#### What it does
Exposes the three new prompt keys in the system-wide `Prompt` enum.

#### Interface / API
```python
class Prompt(str, Enum):
    # ...
    TEMPLATES_INTENT_BASED = "templates.intent_based"
    TEMPLATES_PERSONA = "templates.persona"
    TEMPLATES_SPECIFICATION = "templates.specification"
```

---

### 6.2 Prompt Strategy Bundle

**File:** `vidbyte/prompts/strategies/strategy_prompts.py`  
**Type:** Modified  

#### What it does
Exposes the new prompt family via `PromptTemplatesPrompts` to allow easy retrieval.

#### Interface / API
```python
class PromptTemplatesPrompts(_PromptBundle):
    """Bundle containing prompt generation templates (intent-based, persona, specification)."""
    key = "templates"
```

---

### 6.3 Prompt Index Catalog

**File:** `vidbyte/prompts/prompts/templates/templates.json`  
**Type:** New file  

#### What it does
Defines the `templates` family name, description, and references the Markdown files.

#### Content
```json
{
  "name": "Prompt Templates",
  "description": "Master prompts designed to generate highly optimized structural prompts for specific engineering paradigms.",
  "key": "templates",
  "prompts": {
    "intent_based": {
      "path": "intent_based.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/intent_based.md"
    },
    "persona": {
      "path": "persona.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/persona.md"
    },
    "specification": {
      "path": "specification.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/templates/specification.md"
    }
  }
}
```

---

### 6.4 Intent-Based Template

**File:** `vidbyte/prompts/prompts/templates/intent_based.md`  
**Type:** New file  

#### What it does
Houses the system prompt instructing the LLM to design an intent-based prompt for a user's task.

---

### 6.5 Persona Template

**File:** `vidbyte/prompts/prompts/templates/persona.md`  
**Type:** New file  

#### What it does
Houses the system prompt instructing the LLM to design a persona-based prompt for a role.

---

### 6.6 Specification Template

**File:** `vidbyte/prompts/prompts/templates/specification.md`  
**Type:** New file  

#### What it does
Houses the system prompt instructing the LLM to design a specification-based prompt with acceptance criteria.

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
| MODIFY | `vidbyte/lib/enums/prompts.py` | Register the three new prompt enum keys |
| MODIFY | `vidbyte/prompts/strategies/strategy_prompts.py` | Add the `PromptTemplatesPrompts` bundle class |
| MODIFY | `vidbyte/prompts/strategies/__init__.py` | Export `PromptTemplatesPrompts` from strategy module |
| MODIFY | `vidbyte/prompts/__init__.py` | Export `PromptTemplatesPrompts` and direct templates imports |
| CREATE | `vidbyte/prompts/prompts/templates/templates.json` | JSON mapping catalog for the templates family |
| CREATE | `vidbyte/prompts/prompts/templates/intent_based.md` | Markdown source for intent-based prompt template |
| CREATE | `vidbyte/prompts/prompts/templates/persona.md` | Markdown source for persona prompt template |
| CREATE | `vidbyte/prompts/prompts/templates/specification.md` | Markdown source for specification prompt template |
| MODIFY | `tests/test_prompts_interface.py` | Add unit tests for prompt template interfaces and exports |
| MODIFY | `tests/test_prompt_registry.py` | Add catalog loading validation tests |

---

## 10. Testing Plan

A comprehensive suite of test cases will verify the correct integration, validation, formatting, and structural safety of the new templates. Every test case is explicitly categorized.

### Unit & Integration Tests (pytests)

#### 1. Catalog Registration Tests
- [Edge Case] `test_templates_registered_in_enum`: Verifies that the new prompt family keys are in the `Prompt` enum and correctly parsed by `Prompts()`.
- [Hidden Failure] `test_templates_load_without_configuration_errors`: Asserts that `Prompts()._ensure_loaded()` resolves the sub-directory templates successfully without throwing configuration/JSON syntax errors.
- [Silent Failure] `test_no_duplicate_template_ids`: Validates that the keys mapped in `templates.json` do not overlap with existing keys in other families (resulting in overwritten maps).

#### 2. Strategy Bundle Tests
- [Edge Case] `test_prompt_templates_bundle_export`: Verifies that calling `PromptTemplatesPrompts().export()` returns a map containing exactly `intent_based`, `persona`, and `specification` keys with non-empty string values.
- [Hidden Assumption] `test_templates_formatted_output_structure`: Verifies that the loaded templates are fully valid UTF-8 strings containing the specific placeholder variables or structural keywords (e.g., `{task}`, `{role}`, etc.) that the system expects.

#### 3. Public exports under `vidbyte.prompts`
- [Silent Failure] `test_template_direct_imports`: Asserts that `templates_intent_based`, `templates_persona`, and `templates_specification` are available as module-level attributes on `vidbyte.prompts` and match catalog strings.

---

## 11. Dependencies & External Services

No new external dependencies or library versions are introduced. All modifications use core Python standard library modules (`enum`, `json`) and existing package structures.

---

## 12. Rollout & Deployment

This is a non-breaking, purely additive change to the Vidbyte SDK.
- There are no database migrations.
- Backward compatibility is maintained 100%.
- Deploying simply requires releasing the next minor version of the SDK.

---

## 13. Open Questions

- Should we include standard template placeholders (like `{task}`, `{role}`, `{domain}`) inside the Markdown prompt templates themselves to enable easy formatting in user code?
  - *Yes, we will structure the templates to allow formatting if developers want to inject their own context variables, or just return them as generic guidelines.*

---

## 14. Alternatives Considered

### Alternative 1: Inline JSON Strings
- **What**: Write the entire prompt text directly inside `templates.json` as JSON values (similar to `expert_prompting.json`).
- **Why rejected**: Multi-line system prompts are extremely large and hard to maintain inside JSON files due to escaping characters (`\n`, `\"`). Storing them in dedicated Markdown files under the `templates/` folder keeps them clean, easily reviewable, and follows the repo design system established by `mimic_behavior` and `goals`.
