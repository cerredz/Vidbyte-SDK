# Design Doc: Codex /goal System Prompt

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

Add a new `goals` prompt family to the vidbyte-sdk containing a single comprehensive system prompt that distills the Codex `/goal` tool philosophy, architecture, lifecycle, and best practices from the [OpenAI Cookbook: Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex). The prompt is intended to be used as a system-level instruction for agents that leverage Codex's goal-oriented continuation loop. It is thousands of tokens long — intentionally exceeding the existing 4–10 sentence convention — because it must encode the full mental model of goal-driven autonomous work.

---

## 2. Goals & Non-Goals

### Goals

- Create `vidbyte/prompts/prompts/goals.json` with a single `goal_prompt` that is 2,000+ tokens long, covering the following topics from the source article:
  - What Goals are (persistent thread-scoped objectives with completion conditions)
  - Goals vs. one-off prompts (the work → check → continue/complete loop)
  - How to write a strong Goal (outcome, verification surface, constraints, boundaries, iteration policy, blocked stop condition)
  - What changes when a Goal is active (objective persistence, continuation policy, evidence-based completion)
  - How Goals are architected inside Codex (thread-scoped state, lifecycle controls, dispatcher behavior, budget accounting)
  - Weak-to-strong Goal transformation with concrete examples
  - Using Goals for complex research work (Deep Hedging case study)
  - When NOT to use Goals (one-line edits, vague finish lines, hiding uncertainty)
  - Guiding philosophy: "Let the objective persist, but let evidence decide"
- Register the prompt in the `Prompt` enum as `GOALS_GOAL_PROMPT = "goals.goal_prompt"`
- Ensure the prompt is accessible via `Prompts().get(Prompt.GOALS_GOAL_PROMPT)` and `from vidbyte.prompts import goals_goal_prompt`
- Update the sentence-count validation in tests to accommodate this intentionally long prompt

### Non-Goals

- No new strategy class — this is a standalone system prompt, not a multi-stage strategy
- No runtime template variables (no `{placeholder}` interpolation) — this is a fixed instructional prompt
- No modifications to the Prompts catalog loader — it already supports arbitrary prompt lengths
- No tool-call schemas, MCP integration, or provider-specific formatting
- No changes to the core SDK runtime behavior

---

## 3. Background & Context

Codex introduced the `/goal` command (Codex 0.128.0+) as a mechanism to give Codex persistent objectives that span multiple turns. Unlike a one-off prompt where Codex works through a single instruction and waits, a Goal gives Codex a durable completion contract: a target outcome, a way to verify it, constraints to preserve, and a policy for what to try next after each attempt.

The OpenAI Cookbook article "Using Goals in Codex" (May 2026, by Raj Pathak & Stefano Fabbri) is the canonical guide. It covers the mental model, lifecycle commands (`/goal`, `/goal pause`, `/goal resume`, `/goal clear`), architecture internals, and detailed patterns for weak-to-strong Goal writing.

The vidbyte-sdk currently has 15 prompt families covering reasoning, planning, multi-agent, and routing strategies. None of them encode the Codex-specific goal-driven work loop. Adding this prompt fills that gap — making the SDK a source of truth for Codex-native autonomous work patterns.

**Why now:** Goals are a relatively new Codex feature and the article was published May 9, 2026. First-party prompt assets that encode the goal philosophy will help agents and strategies built on the vidbyte-sdk leverage this Codex capability correctly.

---

## 4. Requirements

### Functional Requirements

1. A single JSON file `goals.json` in `vidbyte/prompts/prompts/` with `name`, `description`, `key`, and `prompts` fields
2. The single prompt `goal_prompt` contains a coherent instructional text of at least 2,000 tokens covering:
   a. Definition and purpose of Goals in Codex
   b. Comparison: Goals vs. one-off prompts (prompt: ask→work→result→wait vs. goal: work→check→continue/complete)
   c. The six elements of a strong Goal: outcome, verification surface, constraints, boundaries, iteration policy, blocked stop condition
   d. Goal lifecycle: `/goal`, `/goal pause`, `/goal resume`, `/goal clear`
   e. How Goals are architected: thread-scoped state, continuation dispatcher behavior, budget handling, evidence-based completion audit
   f. Weak-to-strong Goal transformation with concrete examples (performance tuning, documentation, research)
   g. Research Goals: claim inventory, evidence mapping, reproduction levels (exact, approximate, blocked)
   h. Anti-patterns: when NOT to use a Goal
   i. Core philosophy: evidence decides completion, not model confidence
3. Enum member `GOALS_GOAL_PROMPT = "goals.goal_prompt"` added to `Prompt` enum, maintaining alphabetical order
4. Prompt accessible via all standard SDK interfaces: `Prompts().get()`, `Prompts().all()`, `Prompts().keys()`, direct imports
5. Tests pass after the addition, including updated sentence-count validation

### Non-Functional Requirements

- The prompt text is plain string content — no embedded JSON, no tool-call payloads, no secrets
- The prompt loads correctly via `importlib.resources` on all supported Python versions
- No performance impact — catalog loading adds one more file to the 15 already loaded
- No backward compatibility breaks — new enum member is additive only

---

## 5. High-Level Design

A single prompt family file `goals.json` is added to the existing `vidbyte/prompts/prompts/` directory alongside the 15 existing families. The catalog loader (`catalog.py`) already discovers all `*.json` files in that directory automatically — no changes to the loader are required.

A single enum member `GOALS_GOAL_PROMPT` is added to the `Prompt` enum in `vidbyte/lib/enums/prompts.py`. The catalog loader validates that every enum member has a corresponding JSON asset and vice versa.

The `vidbyte/prompts/__init__.py` auto-generates direct imports by replacing dots with underscores, so `goals_goal_prompt` becomes available without any additional code.

The existing test `test_prompt_values_are_coherent_sentence_blocks` enforces 4–10 sentences per prompt via regex. This test must be updated to either (a) exempt the goals prompt, or (b) validate a higher ceiling for all prompts. Option (a) is preferred to avoid unintended loosening of quality gates for other prompts.

**No strategy adapter class** is needed in `vidbyte/prompts/prompts/__init__.py` because `goals` is not a multi-prompt strategy family — it is a single system prompt used directly.

```text
goals.json ──> catalog.py ──> Prompt enum ──> Prompts().get() / direct import
                 │
                 └── validates GOALS_GOAL_PROMPT exists in Prompt enum
```

---

## 6. Detailed Design

### 6.1 goals.json (New Asset)

**File(s):** `vidbyte/prompts/prompts/goals.json`
**Type:** New file

#### What it does

Contains the goals prompt family with a single system-level prompt that teaches a model the full mental model and operational contract of Codex's `/goal` tool.

#### Interface / API

```json
{
  "name": "Codex Goals",
  "description": "A comprehensive system prompt that encodes the philosophy, architecture, lifecycle, and best practices of the Codex /goal tool. Covers what Goals are, how they differ from one-off prompts, the six elements of a strong Goal, the goal lifecycle commands, the internal architecture (thread-scoped state, continuation dispatcher, budget handling, evidence-based completion), weak-to-strong Goal transformation with concrete examples, research Goal patterns with the Deep Hedging case study, anti-patterns for when not to use Goals, and the core tenet that evidence — not model confidence — determines completion.",
  "key": "goals",
  "prompts": {
    "goal_prompt": "<2,000+ token instructional prompt text>"
  }
}
```

#### Logic / Algorithm

The prompt text is a single lengthy string organized into these major sections:

1. **Definition & Purpose** — What Goals are: persistent thread-scoped objectives with a completion condition. Goals give Codex a finish line and let the objective persist across turns.

2. **Goals vs. Prompts** — The operating model difference: a prompt says "do this next thing" (ask→work→result→wait), a Goal says "keep working until this outcome is true" (work→check→continue/complete).

3. **The Six Elements of a Strong Goal** — Outcome (what should be true), verification surface (the test/benchmark/artifact that proves it), constraints (what must not regress), boundaries (allowed files/tools/resources), iteration policy (how to choose the next action), blocked stop condition (when to stop and report).

4. **Goal Lifecycle** — Commands: `/goal` (view), `/goal <outcome>` (set), `/goal pause`, `/goal resume`, `/goal clear`. States: active, paused, complete, budget-limited.

5. **Internal Architecture** — Thread-scoped state (not global, not project-level), lifecycle controls, continuation dispatcher (event-driven, only at safe boundaries, suppressed on no-tool-call turns), budget accounting, evidence-based completion audit.

6. **Weak-to-Strong Goal Transformation** — Concrete before/after examples: performance tuning, documentation generation, research reproduction.

7. **Research Goal Pattern** — Claim inventory, evidence mapping, reproduction level taxonomy (exact replay, approximate reproduction, proxy support, blocked), the Deep Hedging case study.

8. **Anti-Patterns** — Don't use Goals for: one-line edits, simple explanations, vague finish lines ("make this better"), or hiding uncertainty from the completion condition.

9. **Core Philosophy** — "Let the objective persist, but let evidence decide." The Goal keeps the work moving; the evidence decides whether it's done. Never mark a Goal complete based on model confidence alone — always check concrete evidence (tests, benchmarks, artifacts, logs).

#### Edge Cases & Error Handling

- The prompt is a fixed string — no runtime formatting, so no `KeyError` risk from missing placeholders
- Catalog loader already handles empty strings by raising `ConfigurationError` — no change needed
- If the prompt text exceeds some maximum, the loader just stores it — no truncation risk

### 6.2 Prompt Enum (Modified)

**File(s):** `vidbyte/lib/enums/prompts.py`
**Type:** Modified

#### What it does

Adds `GOALS_GOAL_PROMPT = "goals.goal_prompt"` to the `Prompt` enum, maintaining alphabetical ordering.

#### Interface / API

```python
class Prompt(str, Enum):
    # ... existing members ...
    GOALS_GOAL_PROMPT = "goals.goal_prompt"  # inserted alphabetically after EXPERT_PROMPTING_EXPERT_PROMPT
    # ... remaining members ...
```

### 6.3 Test Updates (Modified)

**File(s):** `tests/test_prompt_registry.py`
**Type:** Modified

#### What it does

Updates the sentence-count validation to exempt the `goals_goal_prompt` from the 4–10 sentence constraint, since it is intentionally a long-form system prompt.

#### Logic

```python
def test_prompt_values_are_coherent_sentence_blocks(self) -> None:
    prompts = Prompts()
    long_form_prompts = {Prompt.GOALS_GOAL_PROMPT}

    for key, prompt in prompts.all().items():
        sentence_count = len(re.findall(r"[.!?]", prompt))
        if key in long_form_prompts:
            self.assertGreaterEqual(sentence_count, 4)  # only enforce minimum
        else:
            self.assertGreaterEqual(sentence_count, 4)
            self.assertLessEqual(sentence_count, 10)
```

### 6.4 No Strategy Adapter Needed

No changes to `vidbyte/prompts/prompts/__init__.py`. The `goals` family has a single prompt and does not require a multi-prompt strategy adapter like `VMAOPrompts`. Users access it directly via `Prompts().get(Prompt.GOALS_GOAL_PROMPT)` or `from vidbyte.prompts import goals_goal_prompt`.

---

## 7. Data Model Changes

N/A — No database schemas, types, or serialization formats change. The prompt system already supports arbitrary prompt text lengths.

---

## 8. API Changes

N/A — No HTTP endpoints or SDK method signatures change. This is purely additive: one new enum member and one new JSON asset.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/goals.json` | New prompt family asset containing the goal_prompt |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add `GOALS_GOAL_PROMPT` enum member |
| MODIFY | `tests/test_prompt_registry.py` | Exempt goals_goal_prompt from 10-sentence ceiling |

---

## 10. Testing Plan

### Unit Tests

Existing tests to verify against:

- `test_strategy_prompts_load_from_prompt_catalog` — already loads all prompts; will naturally test goals_goal_prompt loads
- `test_prompt_values_are_coherent_sentence_blocks` — modified to exempt goals_goal_prompt from the 10-sentence cap

New manual verification:

- `python -c "from vidbyte.prompts import Prompts, Prompt; p = Prompts(); print(len(p.get(Prompt.GOALS_GOAL_PROMPT)))"` — confirm the prompt loads and is >2,000 characters
- `python -c "from vidbyte.prompts import goals_goal_prompt; print(len(goals_goal_prompt))"` — confirm direct import works
- `python -c "from vidbyte.prompts import Prompts; print(Prompt.GOALS_GOAL_PROMPT in Prompts().keys())"` — confirm enum key exists

### Integration Tests

N/A — No integration surface changes. The prompt catalog is a self-contained text asset loader.

### Manual / QA Test Cases

1. Given the prompt is loaded via `Prompts().get(Prompt.GOALS_GOAL_PROMPT)`, then the returned string contains references to: `/goal`, thread-scoped state, continuation dispatcher, evidence-based completion, the six elements of a strong Goal, weak-to-strong transformation, research Goal pattern, and anti-patterns

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | N/A | No new dependencies | N/A |

---

## 12. Rollout & Deployment

- No feature flags — this is a pure text asset addition
- No breaking changes — additive enum member and new JSON file only
- Rollback: delete `goals.json`, remove `GOALS_GOAL_PROMPT` from enum, revert test changes
- No deployment order dependencies — single-repo change

---

## 13. Open Questions

- [ ] Should the prompt include `{task_description}` or `{context}` placeholder variables, or remain a fully fixed system prompt? Currently designed as fixed since the article is philosophy/instruction, not task-specific.
- [ ] Should there be a `GoalPrompts` strategy adapter in `vidbyte/prompts/prompts/__init__.py` even though there's only one prompt? Current design says no — adapters are for multi-prompt families.
- [ ] Is the `docs/design/` directory the correct location for this design doc, or should it be in a separate `skills/docs/` directory as per the design-doc skill convention?

---

## 14. Alternatives Considered

### Alternative 1: Split into multiple prompts (goal_philosophy, goal_writing, goal_architecture, goal_examples)

- What: Break the article into 4+ separate prompt assets, each focused on one aspect
- Why rejected: The user explicitly requested a single comprehensive prompt that is "thousands of tokens long." Splitting would defeat the purpose of having a one-shot system prompt that encodes the full mental model.

### Alternative 2: Use a Markdown file instead of JSON

- What: Store the prompt as `goals.md` and have the catalog loader support `.md` files
- Why rejected: The existing prompt system uses JSON exclusively. Adding Markdown support would require catalog loader changes and introduce inconsistency. JSON with a single long string value works for the existing pattern.

### Alternative 3: Keep the 4–10 sentence constraint and truncate the prompt

- What: Compress the article into 4–10 sentences
- Why rejected: Directly contradicts the user's explicit requirement for a prompt that is "thousands of tokens long" and goes into "immense detail." The whole point is comprehensive coverage.
