# Design Doc: Prompt Engineering Master Prompt

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-24
**Last Updated:** 2026-05-24

---

## 1. Overview

Add a new `prompt_engineering` prompt family to the Vidbyte SDK containing a single comprehensive master prompt that serves as a canonical reference for designing high-quality system prompts. This prompt encapsulates the accumulated wisdom from production AI harnesses (Claude Code, Grok Build, opencode, Hermes, Cursor, Windsurf, Cline, Manus, Devin, and others), research literature, and practitioner experience into a structured guide organized by XML-tagged sections. When given to a capable model, it teaches the model how to construct effective prompts across every dimension: identity framing, behavioral specification, output formatting, planning architecture, memory management, attention placement, and failure-mode prevention.

---

## 2. Goals & Non-Goals

### Goals

- Add a new `prompt_engineering.json` asset under `vidbyte/prompts/prompts/` with one leaf prompt (`master_prompt`)
- Add corresponding `PROMPT_ENGINEERING_MASTER_PROMPT` enum member in `vidbyte/lib/enums/prompts.py`
- Auto-export the direct import name `prompt_engineering_master_prompt` from `vidbyte.prompts`
- Add a `PromptEngineeringPrompts` strategy bundle class in `vidbyte/prompts/strategies/strategy_prompts.py`
- The master prompt must contain: (a) a philosophy/goal description of prompt engineering, (b) a comprehensive list of XML-tagged sections each describing a dimension of prompt design with purpose, use cases, and output description
- Each section targets 3-4 paragraphs of instructional content
- Mirror the existing pattern used by `context_engineering.json` (also a meta-prompt about prompt authoring)

### Non-Goals

- No strategy implementation consuming this prompt (it is a reference asset, not consumed by an automated strategy)
- No runtime tool or function-calling integration
- No provider-specific adaptations
- No modification to the `Prompts` catalog loader logic

---

## 3. Background & Context

The Vidbyte SDK currently has 16 prompt families covering reasoning strategies (chain-of-thought, step-back), sampling strategies (self-consistency, budget-forcing), orchestration (VMAO, multi-agent reflexion), and one meta-prompt (`context_engineering`). The `context_engineering.json` prompt provides guidance on writing effective operational prompts but is terse (~6 sentences) and framed as a methodology note rather than a comprehensive reference.

Across the AI harness ecosystem, the most effective system prompts share structural patterns that have converged independently across Claude Code (110+ instructions, 2,300-3,600 tokens), Grok Build (multi-agent orchestration with four subagent types), Hermes (10-layer prompt assembly), opencode (layered assembly with AGENTS.md discovery), Cursor (per-turn environmental injection), and Cline (~11,000 character system message). The common thread is that these prompts are structured as operational manuals with labeled XML sections, explicit behavioral loops, attention-aware placement, and clear failure-mode specifications.

This feature fills the gap between the terse `context_engineering` guidance and the operational reality of production-grade prompt design by providing a comprehensive master reference that SDK users and downstream agents can consult to construct their own prompts.

---

## 4. Requirements

### Functional Requirements

1. The `prompt_engineering.json` asset must contain exactly four top-level fields: `name`, `description`, `key`, and `prompts`
2. The `prompts` object must contain exactly one key: `master_prompt`
3. The `master_prompt` text must open with a philosophy/goal statement describing the prompt engineering discipline
4. The text must then include a series of XML-tagged sections (e.g., `<role_and_persona>`, `<context_and_environment>`, etc.) each providing:
   - A 6-8 sentence description of what the section is
   - What the section tries to accomplish
   - Why and when to use it
   - Use cases and intent
   - Description of the output the section should produce
5. The enum value `prompt_engineering.master_prompt` must be accessible via `Prompts().get(Prompt.PROMPT_ENGINEERING_MASTER_PROMPT)`
6. The prompt text must be importable as `from vidbyte.prompts import prompt_engineering_master_prompt`

### Non-Functional Requirements

- The prompt text should be human-readable and self-contained (no external references needed)
- Follow the existing sentence-block convention: each prompt value is a coherent prose block
- No secrets, credentials, or provider-specific payloads in the prompt text

---

## 5. High-Level Design

A single JSON asset file is added to `vidbyte/prompts/prompts/` containing one leaf prompt. The catalog loader in `vidbyte/prompts/catalog.py` automatically discovers and exposes it — no loader changes are required because the loader iterates all `.json` files in the directory and registers every leaf prompt it finds.

```
vidbyte/prompts/prompts/prompt_engineering.json  (NEW)
    └── master_prompt  ──>  Prompt.PROMPT_ENGINEERING_MASTER_PROMPT
                                  │
            ┌─────────────────────┼──────────────────────┐
            ▼                     ▼                      ▼
    Prompts().get(...)    direct import var       PromptEngineeringPrompts
```

The prompt content itself is organized as a philosophical preamble followed by XML-tagged sections covering the full lifecycle of prompt design. The structural inspiration comes from:
- Claude Code's section-based system prompt (identity, task rules, tool policy, output/tone, conditional sections)
- The six-section convergence pattern found across all major harnesses (role, context, instructions, tools, examples, output format)
- The advanced execution strategies compiled from research and practice (plan-before-act, checkpointing, memory tiering, attention placement, compaction, etc.)

---

## 6. Detailed Design

### 6.1 `prompt_engineering.json` — New Prompt Asset

**File(s):** `vidbyte/prompts/prompts/prompt_engineering.json`
**Type:** New file

#### What it does

Stores the master prompt text as a JSON asset following the standard Vidbyte prompt family schema. The single leaf prompt (`master_prompt`) contains the full multi-section reference guide.

#### Interface / API

```json
{
  "name": "Prompt Engineering",
  "description": "...",
  "key": "prompt_engineering",
  "prompts": {
    "master_prompt": "... comprehensive prose block ..."
  }
}
```

#### Logic / Algorithm

The prompt text is structured in two parts:

**Part 1 — Philosophy Preamble (2-3 paragraphs):**
Opens by establishing the foundational understanding of what prompt engineering is: the practice of constructing generative contexts that shift a model's probability distributions. Covers the three paradigms (Elicitation, Construction, Programming), the information-theoretic framework (tokens as signal vs. noise), and the central tension between the intuition that "more detail is better" and the empirical reality of attention degradation, diminishing returns, and the need for structure over raw length.

**Part 2 — XML-Tagged Sections (15-18 sections):**
Each section follows a consistent internal structure:
1. **What it is** — 2-3 sentences defining the section's role in a prompt
2. **What it accomplishes** — 2-3 sentences on the mechanical effect inside the model
3. **Why and when to use it** — 2-3 sentences on the circumstances that make this section necessary
4. **Use cases and intent** — 2-3 sentences with concrete scenarios
5. **Output description** — 1-2 sentences on what the section should produce

Each section targets 3-4 paragraphs total. The sections covered:

1. `<role_and_persona>` — Identity assignment that conditions tone, vocabulary, and behavioral priors
2. `<task_and_objective>` — Goal specification with a clear "done" definition
3. `<context_and_environment>` — Background state injection (file structure, OS, date, project rules)
4. `<instructions_and_rules>` — Behavioral specification with positive steering and concrete policies
5. `<constraints_and_boundaries>` — Negative space definition: what NOT to do, scope limits, safety rules
6. `<output_format_and_schema>` — Output contract specifying structure, length, format, and verification criteria
7. `<examples_and_few_shot>` — Demonstrations (positive and negative) placed after instructions for recency advantage
8. `<tone_and_style>` — Communication norms: verbosity, emoji policy, reasoning visibility
9. `<plan_before_act>` — Two-mode architecture (Plan/Act) with mechanical lock enforcement
10. `<state_management_and_checkpointing>` — Progress persistence for long-running tasks
11. `<memory_tiering>` — Layered information architecture (ephemeral, session, project, permanent)
12. `<context_window_management>` — Token budget awareness, compaction strategy, summary-on-fill
13. `<attention_placement>` — Positional salience strategy countering the lost-in-the-middle problem
14. `<reflection_and_self_criticism>` — Self-evaluation loops with embedded rubrics
15. `<negative_constraints_and_failure_modes>` — Explicit failure specification: what failure looks like and what to do when uncertain
16. `<human_in_the_loop>` — Pause/confirmation points for high-cost or destructive actions
17. `<cache_and_cost_awareness>` — Prompt caching strategy: static vs. dynamic tier separation
18. `<prompt_as_operational_manual>` — Meta-design principle: the prompt as a complete cognitive operating system

#### Edge Cases & Error Handling

- The prompt text must remain valid JSON after escaping (no unescaped quotes, backslashes, or control characters in the prose)
- The `master_prompt` key must be non-empty and contain coherent prose
- The catalog loader's existing validation handles malformed JSON, empty prompts, and missing fields automatically

### 6.2 `vidbyte/lib/enums/prompts.py` — Modified

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds the new enum member `PROMPT_ENGINEERING_MASTER_PROMPT` with value `"prompt_engineering.master_prompt"`.

#### Logic

Insert a single line into the `Prompt` enum class, maintaining alphabetical ordering within the block:

```python
PROMPT_ENGINEERING_MASTER_PROMPT = "prompt_engineering.master_prompt"
```

### 6.3 `vidbyte/prompts/strategies/strategy_prompts.py` — Modified

**File(s):** `vidbyte/prompts/strategies/strategy_prompts.py`
**Type:** Modified

#### What it does

Adds a `PromptEngineeringPrompts` bundle class following the exact pattern of existing bundles.

```python
class PromptEngineeringPrompts(_PromptBundle):
    key = "prompt_engineering"
```

### 6.4 `vidbyte/prompts/__init__.py` — Modified

**File(s):** `vidbyte/prompts/__init__.py`
**Type:** Modified

#### What it does

Imports `PromptEngineeringPrompts` from the strategies module and adds it to `__all__`. The direct prompt import variable (`prompt_engineering_master_prompt`) is automatically generated by the existing `for _prompt_key, _import_name in _prompts.import_names().items()` loop — no manual variable declaration is needed.

### 6.5 `vidbyte/prompts/strategies/__init__.py` — Modified

**File(s):** `vidbyte/prompts/strategies/__init__.py`
**Type:** Modified

#### What it does

Adds `PromptEngineeringPrompts` to the strategies module's exports so it is importable.

---

## 7. Data Model Changes

N/A — No schema, database, or dataclass changes. The prompt asset follows the existing JSON family schema validated by `Prompts._validate_record`.

---

## 8. API Changes

N/A — No HTTP API endpoints are added or modified. The prompt is consumed through the existing `Prompts` class interface.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/prompt_engineering.json` | New prompt family asset with master prompt text |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add `PROMPT_ENGINEERING_MASTER_PROMPT` enum member |
| MODIFY | `vidbyte/prompts/strategies/strategy_prompts.py` | Add `PromptEngineeringPrompts` bundle class |
| MODIFY | `vidbyte/prompts/strategies/__init__.py` | Export `PromptEngineeringPrompts` |
| MODIFY | `vidbyte/prompts/__init__.py` | Import and export `PromptEngineeringPrompts` |
| MODIFY | `tests/test_prompt_registry.py` | Update sentence-count upper bound (or add exception) for master prompt |

---

## 10. Testing Plan

### Unit Tests

Existing tests that must continue to pass:

- `test_prompt_registry.py` — `test_strategy_prompts_load_from_prompt_catalog`: verifies `PromptEngineeringPrompts().export()` matches `Prompts().family("prompt_engineering")`
- `test_prompt_registry.py` — `test_prompt_values_are_coherent_sentence_blocks`: **requires update** — the current upper bound of 10 sentences per prompt is incompatible with a master reference prompt that necessarily exceeds this threshold. Options:
  - (a) Raise the upper bound to a higher value (e.g., 120) to accommodate reference-length prompts
  - (b) Add a per-family exception list for prompts that are intentionally long-form references
  - (c) Remove the upper bound entirely and keep only the minimum sentence count
- `test_prompts_interface.py` — `test_all_direct_import_names_are_exported`: automatically validates the new import name is in `__all__`
- `test_prompts_interface.py` — `test_keys_and_descriptions_are_enum_keyed`: automatically validates the new enum member
- `test_prompts_interface.py` — `test_get_accepts_prompt_enum_and_returns_text`: not directly affected but the general contract holds

### Integration Tests

N/A — No integration surface beyond the existing catalog loader which handles all families uniformly.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte` — should succeed with no syntax errors
2. Run `python -m unittest discover -s tests` — all tests pass
3. Verify `from vidbyte.prompts import prompt_engineering_master_prompt` works in a REPL
4. Verify `Prompts().get(Prompt.PROMPT_ENGINEERING_MASTER_PROMPT)` returns the full prompt text
5. Verify `PromptEngineeringPrompts().export()` returns `{"master_prompt": "..."}`

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | N/A | No new dependencies | N/A |

---

## 12. Rollout & Deployment

- No feature flags required — prompt assets are inert text and are loaded at import time
- No breaking changes — purely additive
- No deployment ordering constraints
- Rollback: remove the enum member, JSON file, and strategy bundle class; restore the test file

---

## 13. Open Questions

- [ ] **Sentence-count test bound**: The existing test enforces 4-10 sentences per prompt. The master prompt will have ~60-120+ sentences. Which approach is preferred: raise the global bound, add a family exception list, or remove the upper bound?
- [ ] **Section count**: The current plan targets 15-18 XML-tagged sections. Should this be adjusted (fewer deeper sections vs. more granular coverage)?
- [ ] **No strategy consumer**: Unlike most prompt families, this one has no automated strategy. Is that acceptable, or should a `PromptEngineeringStrategy` be built later?
- [ ] **Length concern**: Should the master prompt text itself be exempt from the "coherent sentence block" constraint (it contains structured XML tags, not pure prose)?

---

## 14. Alternatives Considered

### Alternative 1: Extend `context_engineering.json` instead of creating a new family

- What: Add the master content to the existing `context_engineering` family as additional leaf prompts
- Why rejected: `context_engineering` has a different scope (operational prompt authoring methodology, ~6 sentences). The master prompt is a fundamentally different artifact (comprehensive reference guide with 15+ XML-tagged sections). Mixing them would violate single-responsibility and make the enum key ambiguous.

### Alternative 2: Split into multiple leaf prompts per section

- What: One leaf prompt per XML section (e.g., `prompt_engineering.role_section`, `prompt_engineering.memory_section`)
- Why rejected: The sections are designed to be consumed as a single coherent reference. Fragmenting them would require consumers to assemble the parts, defeating the "master reference" purpose and adding unnecessary enum members (18+ new entries).

### Alternative 3: Embed as a standalone `.md` doc instead of a prompt asset

- What: Store the reference as a Markdown file under `docs/` rather than as a JSON prompt asset
- Why rejected: Keeping it as a prompt asset makes it available through the same SDK interface as all other prompts, enabling programmatic access, direct import, and eventual consumption by strategies or agents.
