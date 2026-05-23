# Design Doc: Prompt Interface Simplification

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

Simplify the Vidbyte SDK prompt surface so SDK users interact with one `Prompts` class, one `Prompt` enum, and direct snake_case prompt text imports. The current upstream prompt system exposes overlapping registries, `PromptKey` dataclasses, rendered prompt wrappers, class-based overrides, and a JSON-backed registry. This change makes repository prompts plain text assets: `Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)` returns a string, prompt lookup does not accept arbitrary strings, prompt override behavior is removed, and `from vidbyte.prompts import chain_of_thought_reason_prompt` imports the prompt text directly.

---

## 2. Goals & Non-Goals

### Goals

- Replace public prompt registry usage with a public `Prompts` class.
- Add a Vidbyte prompt enum at `vidbyte/lib/enums/prompts.py`.
- Require `Prompts.get()` to accept a `Prompt` enum member and return exactly one prompt string.
- Expose all prompt keys and all prompt keys with descriptions through `Prompts`.
- Expose each individual prompt text as a snake_case direct import from `vidbyte.prompts`.
- Remove prompt override behavior from the prompt API.
- Keep prompts as plain text repository assets with no tool-call schema or tool-call execution behavior.
- Document the full process for adding a prompt under `skills/vidbyte-sdk/adding-prompts.md`.
- Update tests and examples to reflect the new prompt interface.

### Non-Goals

- No runtime prompt overrides, custom prompt directories, or file path replacement.
- No tool registry, tool call, function calling, or MCP behavior in the prompt subsystem.
- No live provider calls.
- No database, migration, or persistence changes.
- No implementation of new prompt-engineering strategies beyond adapting existing prompt consumers to the new interface.
- No automatic code generation step for prompt enums; prompt additions remain explicit source edits.

---

## 3. Background & Context

- The local checkout is on `main` at `89e2404`, behind `origin/main` by two commits. The implementation phase for this design will start by pulling `origin/main`, so the design targets the upstream prompt package now present at `origin/main`.
- `origin/main` contains both `vidbyte/prompts/registry.py` and `vidbyte/lib/prompts/registry.py`, plus prompt JSON files under `vidbyte/prompts/prompts/`.
- The public prompt API currently includes overlapping concepts: `PromptRegistry`, `prompt_registry`, `PromptKey`, `RenderedPrompt`, `BasePrompt`, `LibPromptRegistry`, and a typo-compatible `PrompRegistry`.
- Existing prompt JSON assets are grouped by family. For example, `chain_of_thought.json` contains family key `chain_of_thought` and prompt key `reason_prompt`; `vmao.json` contains `planner`, `planner_repair`, `synthesizer`, `verifier`, and `gap_planner`.
- Existing tests import `vidbyte.lib.prompts.PromptRegistry` and expect grouped dictionaries. Existing direct public exports from `vidbyte.prompts` still mention the class-based prompt system.
- The user explicitly wants snake_case direct prompt imports and enum-backed lookup instead of free-form string lookup.

---

## 4. Requirements

### Functional Requirements

1. `from vidbyte.prompts import Prompts` must import the new prompt accessor class.
2. `from vidbyte.lib.enums.prompts import Prompt` must import the prompt enum.
3. `Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)` must return the prompt text string for that exact prompt.
4. `Prompts().get("chain_of_thought.reason_prompt")` must fail because string lookup is not part of the public API.
5. Every enum value must identify one leaf prompt, not a group of prompts. The enum value format will be `<family_key>.<prompt_key>`, for example `chain_of_thought.reason_prompt`.
6. Direct imports from `vidbyte.prompts` must expose prompt text variables using snake_case names derived from enum values, for example `chain_of_thought_reason_prompt`.
7. `Prompts().keys()` must return all available prompt enum members as a tuple.
8. `Prompts().descriptions()` must return a mapping from `Prompt` enum members to human-readable descriptions.
9. `Prompts().all()` must return a mapping from `Prompt` enum members to prompt text strings.
10. Prompt loading must validate that every JSON prompt leaf has a matching `Prompt` enum member and every `Prompt` enum member has backing JSON text.
11. The prompt subsystem must not expose an override method, custom prompt directory parameter, tool-call method, or tool-call metadata.
12. Existing prompt-consuming strategy helper classes must keep returning grouped dictionaries where needed, but they must source text from `Prompts` instead of `PromptRegistry`.
13. `skills/vidbyte-sdk/adding-prompts.md` must explain every step required to add a prompt, including JSON asset edits, enum edits, direct import naming, tests, and review considerations.

### Non-Functional Requirements

- Maintainability: prompt keys are explicit in the enum so users get autocomplete and typo resistance.
- Compatibility: Python remains `>=3.11`.
- Packaging: prompt JSON files must be included in built distributions.
- Reliability: prompt catalog validation must fail early with clear SDK errors if assets and enum values diverge.
- Security: prompt docs must tell contributors not to include secrets, credentials, private customer data, or tool-call payloads in prompt assets.
- Performance: prompt JSON loading is small and may be cached in memory.
- Observability: no logging is required for prompt lookup.

---

## 5. High-Level Design

The prompt system becomes a small catalog over JSON prompt assets. `vidbyte/lib/enums/prompts.py` defines the public enum. `vidbyte/prompts/catalog.py` loads JSON files from `vidbyte/prompts/prompts/`, flattens each family prompt into leaf records, validates those leaves against the enum, and exposes the `Prompts` class. The public `vidbyte.prompts` package imports `Prompts`, imports `Prompt`, and publishes snake_case prompt text variables.

Existing prompt bundle classes such as `ChainOfThoughtPrompts` and `VMAOPrompts` can remain for strategy compatibility, but they become thin adapters over `Prompts`. The old class-based `PromptRegistry`, `PromptKey`, `RenderedPrompt`, `BasePrompt`, inline override, and `prompt_registry` singleton are removed from public exports because they conflict with the new interface and preserve override behavior the user wants removed.

```text
vidbyte/prompts/prompts/*.json
        |
        v
vidbyte.prompts.catalog.Prompts
        |
        +--> get(Prompt.X) -> str
        +--> keys() -> tuple[Prompt, ...]
        +--> descriptions() -> Mapping[Prompt, str]
        +--> direct exports in vidbyte.prompts
```

---

## 6. Detailed Design

### 6.1 Prompt Enum

**File(s):** `vidbyte/lib/enums/prompts.py`, `vidbyte/lib/enums/__init__.py`
**Type:** New file, Modified

#### What it does

Defines the only public key type accepted by `Prompts.get()`.

#### Interface / API

```python
from enum import Enum


class Prompt(str, Enum):
    AGENTIC_RAG_RETRIEVE_PROMPT = "agentic_rag.retrieve_prompt"
    AGENTIC_RAG_ANSWER_PROMPT = "agentic_rag.answer_prompt"
    ANSWER_CONVERGENCE_SAMPLE_PROMPT = "answer_convergence.sample_prompt"
    BUDGET_FORCING_INITIAL_PROMPT = "budget_forcing.initial_prompt"
    BUDGET_FORCING_CONTINUE_PROMPT = "budget_forcing.continue_prompt"
    CHAIN_OF_DRAFT_DRAFT_PROMPT = "chain_of_draft.draft_prompt"
    CHAIN_OF_THOUGHT_REASON_PROMPT = "chain_of_thought.reason_prompt"
    CONTEXT_ENGINEERING_CONTEXT_PROMPT = "context_engineering.context_prompt"
    EXPERT_PROMPTING_EXPERT_PROMPT = "expert_prompting.expert_prompt"
    MULTI_AGENT_REFLEXION_ACTOR_PROMPT = "multi_agent_reflexion.actor_prompt"
    MULTI_AGENT_REFLEXION_CRITIC_PROMPT = "multi_agent_reflexion.critic_prompt"
    MULTI_AGENT_REFLEXION_REFINE_PROMPT = "multi_agent_reflexion.refine_prompt"
    PARADIGM_ROUTER_ROUTE_PROMPT = "paradigm_router.route_prompt"
    PLAN_AND_EXECUTE_PLAN_PROMPT = "plan_and_execute.plan_prompt"
    PLAN_AND_EXECUTE_EXECUTE_PROMPT = "plan_and_execute.execute_prompt"
    PLAN_AND_EXECUTE_SYNTHESIZE_PROMPT = "plan_and_execute.synthesize_prompt"
    SELF_CONSISTENCY_SAMPLE_PROMPT = "self_consistency.sample_prompt"
    SKELETON_OF_THOUGHT_SKELETON_PROMPT = "skeleton_of_thought.skeleton_prompt"
    SKELETON_OF_THOUGHT_EXPAND_PROMPT = "skeleton_of_thought.expand_prompt"
    STEP_BACK_ABSTRACTION_PROMPT = "step_back.abstraction_prompt"
    STEP_BACK_REASONING_PROMPT = "step_back.reasoning_prompt"
    TREE_OF_THOUGHTS_BRANCH_PROMPT = "tree_of_thoughts.branch_prompt"
    TREE_OF_THOUGHTS_SCORE_PROMPT = "tree_of_thoughts.score_prompt"
    TREE_OF_THOUGHTS_FINAL_PROMPT = "tree_of_thoughts.final_prompt"
    VMAO_PLANNER = "vmao.planner"
    VMAO_PLANNER_REPAIR = "vmao.planner_repair"
    VMAO_SYNTHESIZER = "vmao.synthesizer"
    VMAO_VERIFIER = "vmao.verifier"
    VMAO_GAP_PLANNER = "vmao.gap_planner"
```

#### Logic / Algorithm

1. Enum values match JSON family key plus prompt key.
2. Enum member names are uppercase snake_case for autocomplete.
3. `vidbyte/lib/enums/__init__.py` exports `Prompt`.

#### Edge Cases & Error Handling

- Missing enum members for new JSON prompt leaves are caught by catalog validation.
- Enum values with no backing JSON text are caught by catalog validation.

---

### 6.2 Prompt Catalog And `Prompts`

**File(s):** `vidbyte/prompts/catalog.py`
**Type:** New file

#### What it does

Loads prompt assets, validates the enum-to-asset relationship, and exposes the user-facing prompt lookup API.

#### Interface / API

```python
from collections.abc import Mapping
from dataclasses import dataclass

from vidbyte.lib.enums.prompts import Prompt


@dataclass(frozen=True, slots=True)
class PromptRecord:
    key: Prompt
    text: str
    description: str
    family: str
    name: str
    import_name: str


class Prompts:
    def get(self, key: Prompt) -> str: ...
    def keys(self) -> tuple[Prompt, ...]: ...
    def descriptions(self) -> Mapping[Prompt, str]: ...
    def all(self) -> Mapping[Prompt, str]: ...
    def family(self, family_key: str) -> Mapping[str, str]: ...
    def import_names(self) -> Mapping[Prompt, str]: ...
```

#### Logic / Algorithm

1. Use `importlib.resources.files("vidbyte.prompts.prompts")` to locate JSON assets inside the installed package.
2. Read each `.json` file as an object with `name`, `description`, `key`, and `prompts`.
3. For every `prompts` entry, create a leaf id `<family_key>.<prompt_key>`.
4. Convert the leaf id to a `Prompt` enum member.
5. Generate a direct import variable name by replacing `.` with `_`, for example `chain_of_thought.reason_prompt` becomes `chain_of_thought_reason_prompt`.
6. Cache records in process memory.
7. Sort public key outputs by enum value for deterministic behavior.

#### Edge Cases & Error Handling

- If `get()` receives anything other than `Prompt`, raise `TypeError` with a short message.
- If JSON is malformed, fields are missing, prompt text is empty, or enum/assets diverge, raise `ConfigurationError`.
- `family()` is for existing internal adapters and returns prompt-name-to-text mappings for a JSON family; it is not an override API.

---

### 6.3 Public Prompt Package

**File(s):** `vidbyte/prompts/__init__.py`
**Type:** Modified

#### What it does

Replaces registry-style public exports with the simplified prompt interface and direct text exports.

#### Interface / API

```python
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

prompts = Prompts()
chain_of_thought_reason_prompt = prompts.get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)

__all__ = [
    "Prompt",
    "Prompts",
    "chain_of_thought_reason_prompt",
    ...
]
```

#### Logic / Algorithm

1. Instantiate or access the cached prompt catalog.
2. Publish module globals for every direct import name returned by `Prompts().import_names()`.
3. Export `Prompt`, `Prompts`, and all generated prompt text names.
4. Stop exporting `PromptRegistry`, `prompt_registry`, `PromptKey`, `RenderedPrompt`, `PromptVersion`, `BasePrompt`, and prompt override helpers.

#### Edge Cases & Error Handling

- Importing `vidbyte.prompts` can fail fast if prompt assets are invalid. This is acceptable because invalid package prompt assets are a developer error.

---

### 6.4 Prompt Bundle Adapters

**File(s):** `vidbyte/prompts/strategies/strategy_prompts.py`, `vidbyte/prompts/prompts/__init__.py`
**Type:** Modified

#### What it does

Keeps existing strategy-facing grouped prompt helpers while replacing registry lookups with `Prompts`.

#### Interface / API

```python
class ChainOfThoughtPrompts:
    def export(self) -> dict[str, str]: ...


class VMAOPrompts:
    def __init__(self, name: str) -> None: ...
    def export(self, **kwargs: object) -> str: ...
```

#### Logic / Algorithm

1. `_PromptBundle.export()` calls `Prompts().family(self.key)` and returns a dictionary keyed by leaf prompt name.
2. `VMAOPrompts.export()` reads `Prompts().family("vmao")[self.name]` and formats placeholders with `kwargs`.
3. Existing strategy code that consumes these bundle classes continues to receive plain strings or dictionaries of strings.

#### Edge Cases & Error Handling

- Missing family or prompt names raise `ConfigurationError`.
- Placeholder formatting errors in `VMAOPrompts.export()` surface as standard formatting errors unless an existing SDK error wrapper is already used locally.

---

### 6.5 Remove Old Registry Surface

**File(s):** `vidbyte/prompts/registry.py`, `vidbyte/lib/prompts/__init__.py`, `vidbyte/lib/prompts/registry.py`, `vidbyte/prompts/_inline.py`, `vidbyte/prompts/base.py`, `vidbyte/prompts/types.py`, `vidbyte/prompts/builtins/__init__.py`, `vidbyte/prompts/builtins/vidbyte_defaults.py`
**Type:** Modified, Deleted

#### What it does

Removes the old public prompt registry and override mechanics.

#### Interface / API

```python
# Removed from public API:
# PromptRegistry
# prompt_registry
# PromptKey
# RenderedPrompt
# PromptVersion
# BasePrompt
# PromptRegistry.override(...)
# PromptRegistry(prompt_dir=...)
```

#### Logic / Algorithm

1. Delete files whose only purpose is the class-based prompt override system.
2. Replace `vidbyte/prompts/registry.py` with either a compatibility-free re-export of `Prompts` or remove imports from it entirely.
3. Remove `vidbyte.lib.prompts.PromptRegistry` and `PrompRegistry` exports from package public surfaces.
4. Update all internal imports to use `Prompts`.

#### Edge Cases & Error Handling

- This is a breaking change for users importing `PromptRegistry` or `PromptKey`. That is intentional and should be called out in README.

---

### 6.6 Root Exports And README

**File(s):** `vidbyte/__init__.py`, `README.md`, `pyproject.toml`
**Type:** Modified

#### What it does

Updates public import examples and ensures prompt JSON assets ship with the package.

#### Interface / API

```python
from vidbyte import Prompt, Prompts
from vidbyte.prompts import chain_of_thought_reason_prompt
```

#### Logic / Algorithm

1. Root `vidbyte.__init__` exports `Prompt` and `Prompts`.
2. Root `vidbyte.__init__` stops exporting removed prompt registry types.
3. README shows enum lookup and direct text import examples.
4. `pyproject.toml` includes prompt JSON package data.

#### Edge Cases & Error Handling

- If package data is not configured, installed wheels can pass source tests but fail at runtime. Tests should include an import/lookup smoke test.

---

### 6.7 Strategy Imports That Still Use Prompt Registry

**File(s):** `vidbyte/strategies/reflexion.py`, `vidbyte/strategies/tree_of_thoughts.py`, `vidbyte/tools/builtins/document_retrieval.py`
**Type:** Modified

#### What it does

Removes stale references to `PromptRegistry`, `PromptKey`, and overridable prompt classes.

#### Interface / API

```python
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts
```

#### Logic / Algorithm

1. Reflexion strategy uses `Prompts().get(Prompt.MULTI_AGENT_REFLEXION_ACTOR_PROMPT)` and related enum members.
2. Tree-of-Thoughts strategy uses `Prompts().get(Prompt.TREE_OF_THOUGHTS_BRANCH_PROMPT)` and related enum members.
3. Static documentation text in built-in tools is updated to describe enum-backed `Prompts` instead of overridable `PromptKey` classes.

#### Edge Cases & Error Handling

- If a strategy needs runtime variable interpolation, it formats the returned prompt string locally. The prompt catalog remains plain text only.

---

### 6.8 Adding Prompt Skill Guide

**File(s):** `skills/vidbyte-sdk/adding-prompts.md`, `skills/vidbyte-sdk/SKILL.md`
**Type:** Modified

#### What it does

Documents the complete prompt addition process for future contributors.

#### Interface / API

N/A - documentation only.

#### Logic / Algorithm

The guide will instruct contributors to:

1. Decide whether the prompt is a new family or a new leaf in an existing family.
2. Use snake_case for JSON family keys and leaf prompt keys.
3. Add or edit exactly one JSON file under `vidbyte/prompts/prompts/`.
4. Include `name`, `description`, `key`, and `prompts`.
5. Keep prompt text plain, inspectable, and free of tool-call schemas.
6. Add one enum member per leaf prompt in `vidbyte/lib/enums/prompts.py`.
7. Confirm the generated direct import name, such as `family_prompt_key`.
8. Add or update prompt bundle adapters only when a strategy consumes the prompt family as a dictionary.
9. Add or update tests for enum lookup, direct import, descriptions, and strategy use.
10. Run compile and unittest verification.

#### Edge Cases & Error Handling

- The guide will explicitly warn that file path overrides and runtime overrides are not supported.

---

## 7. Data Model Changes

### 7.1 Prompt Enum

**Change type:** New

```python
class Prompt(str, Enum):
    ...
```

**Migration strategy:** Existing `PromptKey(namespace, name)` usage migrates to a concrete `Prompt` enum member.

### 7.2 PromptRecord

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class PromptRecord:
    key: Prompt
    text: str
    description: str
    family: str
    name: str
    import_name: str
```

**Migration strategy:** In-memory only. No persisted data.

---

## 8. API Changes

### 8.1 Python Prompt API

**Change type:** Modified

**Request:**

```python
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts

text = Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)
```

**Response:**

```python
"Solve the task carefully and reason step by step. ..."
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| TypeError | `Prompts.get()` receives a non-`Prompt` value |
| ConfigurationError | Prompt assets are malformed or not synchronized with the enum |

### 8.2 Python Direct Import API

**Change type:** New

**Request:**

```python
from vidbyte.prompts import chain_of_thought_reason_prompt
```

**Response:**

```python
chain_of_thought_reason_prompt == Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| ImportError | Import name does not correspond to an exported prompt |
| ConfigurationError | Prompt assets fail validation while importing `vidbyte.prompts` |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/prompt-interface-simplification.md` | Design doc for this feature |
| CREATE | `vidbyte/lib/enums/prompts.py` | Public `Prompt` enum |
| CREATE | `vidbyte/prompts/catalog.py` | New `Prompts` class and prompt asset loader |
| CREATE | `tests/test_prompts_interface.py` | Tests for enum lookup, direct imports, descriptions, and no overrides |
| MODIFY | `pyproject.toml` | Include prompt JSON files as package data |
| MODIFY | `README.md` | Document the new prompt API and direct imports |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Point contributors to the prompt addition guide |
| MODIFY | `skills/vidbyte-sdk/adding-prompts.md` | Explain the full prompt addition workflow |
| MODIFY | `vidbyte/__init__.py` | Export `Prompt` and `Prompts`; remove old prompt registry exports |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export `Prompt` |
| MODIFY | `vidbyte/prompts/__init__.py` | Expose `Prompts`, `Prompt`, and direct prompt text variables |
| MODIFY | `vidbyte/prompts/registry.py` | Remove old registry implementation or reduce to compatibility-free `Prompts` import |
| MODIFY | `vidbyte/prompts/prompts/__init__.py` | Make `VMAOPrompts` use `Prompts` |
| MODIFY | `vidbyte/prompts/strategies/strategy_prompts.py` | Make prompt bundle classes use `Prompts` |
| MODIFY | `vidbyte/strategies/reflexion.py` | Replace `PromptRegistry` and `PromptKey` with enum-backed `Prompts` |
| MODIFY | `vidbyte/strategies/tree_of_thoughts.py` | Replace `PromptRegistry` and `PromptKey` with enum-backed `Prompts` |
| MODIFY | `vidbyte/tools/builtins/document_retrieval.py` | Remove stale documentation string about overridable `PromptKey` classes |
| MODIFY | `tests/test_agent_abstractions.py` | Update prompt registry assertions for the new prompt API |
| MODIFY | `tests/test_context_dataclasses.py` | Update prompt registry assertions for the new prompt API |
| MODIFY | `tests/test_prompt_registry.py` | Rename expectations around the new `Prompts` API |
| DELETE | `vidbyte/lib/prompts/__init__.py` | Remove old JSON registry public package |
| DELETE | `vidbyte/lib/prompts/registry.py` | Remove old string-keyed registry and prompt directory override |
| DELETE | `vidbyte/prompts/_inline.py` | Remove inline override prompt support |
| DELETE | `vidbyte/prompts/base.py` | Remove class-based prompt abstraction from public package |
| DELETE | `vidbyte/prompts/types.py` | Remove `PromptKey`, `PromptVersion`, and `RenderedPrompt` |
| DELETE | `vidbyte/prompts/builtins/__init__.py` | Remove no-op class-based default registration package |
| DELETE | `vidbyte/prompts/builtins/vidbyte_defaults.py` | Remove no-op default registration hook |

Summary: 4 files created, 16 files modified, 7 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_prompts_interface.py` -> `Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT)` returns a string matching the direct import.
- `tests/test_prompts_interface.py` -> `Prompts().get("chain_of_thought.reason_prompt")` raises `TypeError`.
- `tests/test_prompts_interface.py` -> `Prompts().keys()` returns `Prompt` enum members and includes every enum value.
- `tests/test_prompts_interface.py` -> `Prompts().descriptions()` returns non-empty descriptions for every prompt key.
- `tests/test_prompts_interface.py` -> `Prompts` has no `override` attribute and exposes no tool-call methods.
- `tests/test_prompts_interface.py` -> every `Prompts().import_names()` value is importable from `vidbyte.prompts`.
- `tests/test_prompt_registry.py` -> update existing JSON prompt coherence tests to use `Prompts().all()`.
- `tests/test_agent_abstractions.py` -> update prompt assertions from grouped registry lookup to enum-backed prompt lookup.
- `tests/test_context_dataclasses.py` -> update VMAO prompt lookup to use `Prompts().family("vmao")`.

### Integration Tests

- Run the full unittest suite because the root package exports and strategy imports change.
- No network or provider integration tests are needed.

### Manual / QA Test Cases

1. Run `python -c "from vidbyte.prompts import Prompts, chain_of_thought_reason_prompt; from vidbyte.lib.enums.prompts import Prompt; print(Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT) == chain_of_thought_reason_prompt)"`.
2. Run `python -c "from vidbyte import Prompt, Prompts; print(Prompts().keys()[0])"`.
3. Try `python -c "from vidbyte.prompts import Prompts; Prompts().get('chain_of_thought.reason_prompt')"` and confirm it fails with `TypeError`.
4. Build or install the package locally and confirm JSON prompt assets are present through `Prompts().keys()`.

Verification commands:

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import Prompt, Prompts; from vidbyte.prompts import chain_of_thought_reason_prompt; print(bool(Prompts().get(Prompt.CHAIN_OF_THOUGHT_REASON_PROMPT) == chain_of_thought_reason_prompt))"
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | Enum, dataclasses, importlib.resources, JSON loading | Low |
| pydantic | >=2,<3 | Existing SDK dependency, unchanged | None |

No new dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- This is a package-only SDK change.
- This is a breaking change for callers using `PromptRegistry`, `PromptKey`, `BasePrompt`, `RenderedPrompt`, `PromptVersion`, `prompt_registry`, `LibPromptRegistry`, or `PrompRegistry`.
- Rollout is a draft PR against `main`.
- The migration path is to replace old prompt registry usage with `Prompts().get(Prompt.X)` or direct `vidbyte.prompts` snake_case imports.
- Rollback is reverting the PR.
- No deployment order, feature flags, or service migrations are involved.

---

## 13. Open Questions

- [ ] Should `Prompt` also be exported from `vidbyte.prompts`, or only from `vidbyte.lib.enums.prompts` and root `vidbyte`? Recommendation: export it from all three for ergonomics.
- [ ] Should `Prompts().descriptions()` return descriptions keyed by `Prompt` enum members or by snake_case import names? Recommendation: key by `Prompt` to keep the enum central.
- [ ] Should the old `vidbyte.lib.prompts` package be deleted immediately or kept as a temporary compatibility shim that raises a migration error? Recommendation: delete it in this first structural change to avoid preserving the registry concept.

---

## 14. Alternatives Considered

### Alternative 1: Keep `PromptRegistry` as an alias for `Prompts`

- What: Define `PromptRegistry = Prompts` so old imports keep working.
- Why rejected: The user explicitly asked to change promptRegistry to `Prompts()` and remove overrides. Keeping the name preserves the mental model we are trying to remove.

### Alternative 2: Let `Prompts.get()` accept both strings and enum members

- What: Support `Prompts().get("chain_of_thought.reason_prompt")` as a convenience.
- Why rejected: The user changed the requirement specifically to enum input so users do not mistype keys.

### Alternative 3: Generate the enum automatically from JSON at import time

- What: Build enum members dynamically from prompt assets.
- Why rejected: Dynamic enums reduce static autocomplete and make direct source review weaker. Explicit enum edits force contributors to consider the public API key.

### Alternative 4: Keep custom prompt directory overrides

- What: Preserve `PromptRegistry(prompt_dir=...)` or add `Prompts(path=...)`.
- Why rejected: The user explicitly removed prompt override support for now. Runtime prompt replacement can be designed later if needed.

### Alternative 5: Export only grouped prompt dictionaries

- What: Keep `ChainOfThoughtPrompts().export()` as the main API.
- Why rejected: The user wants one prompt enum key to return one prompt string and wants direct prompt text imports from `vidbyte.prompts`.
