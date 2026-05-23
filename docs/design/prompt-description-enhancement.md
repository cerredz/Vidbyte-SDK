# Design Doc: Prompt Description Enhancement

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-22
**Last Updated:** 2026-05-22

---

## 1. Overview

Enhance the `description` field of every prompt JSON file in the Vidbyte SDK's prompt collection from a terse 1-2 sentence summary into a comprehensive 6-8 sentence description that clearly articulates the goal, intent, use case, mechanics, and expected outcomes of each reasoning strategy. This makes the prompt catalog self-documenting for SDK users who inspect, audit, or override prompts.

---

## 2. Goals & Non-Goals

### Goals
- Expand each prompt JSON `description` field to 6-8 coherent sentences
- Cover goal, intent, when to use, how it works, and expected output for each strategy
- Maintain existing file structure, keys, and prompt template text unchanged
- Keep descriptions factual, instructional, and aligned with the strategy's purpose in the SDK

### Non-Goals
- Changing prompt template text (the `prompts` object values)
- Adding or removing prompt files
- Modifying registry loading logic
- Adding new schema fields to the JSON files
- Altering any Python source code

---

## 3. Background & Context

The Vidbyte SDK maintains a collection of 15 reasoning strategy prompts stored as JSON assets under `vidbyte/prompts/prompts/`. These are loaded by `vidbyte.lib.prompts.PromptRegistry` and surfaced to strategy classes. Currently, each file's `description` is a single short sentence (e.g., "Sequential reasoning prompt for one careful answer."). The SDK convention (documented in `skills/vidbyte-sdk/adding-prompts.md`) calls for descriptions to be 6-8 sentences. This task brings all existing prompts into compliance with that standard, making the prompt catalog usable as reference documentation.

---

## 4. Requirements

### Functional Requirements
1. Each of the 15 prompt JSON files must have its `description` field expanded to 6-8 complete sentences
2. Each description must cover: what the strategy is, its purpose, when to use it, how it works at a high level, what problems it solves, key design characteristics, and expected outputs
3. Descriptions must use factual, instructional prose — no marketing language
4. All existing fields (`name`, `key`, `prompts`) must remain unchanged
5. The registry must load all files without errors after the changes

### Non-Functional Requirements
- File sizes will increase modestly (~200-400 bytes per file)
- No performance impact (descriptions are read once at registry init)
- Backward compatible — no schema changes

---

## 5. High-Level Design

The change is a pure content update across 15 static JSON asset files. No code changes are required. Each file's `description` string will be replaced with an expanded version. The `PromptRegistry._read_record()` method already validates that `description` is a non-empty string, so the expanded descriptions will pass existing validation unchanged.

```
[PromptRegistry] --loads--> [15 JSON files] --exposes--> [Strategy classes]
                                  |
                          (description field expanded)
```

---

## 6. Detailed Design

All 15 files follow the same pattern. The only change in each file is the `description` field value.

### 6.1 chain_of_thought.json

**File(s):** `vidbyte/prompts/prompts/chain_of_thought.json`
**Type:** Modified

**Current description:** "Sequential reasoning prompt for one careful answer."

**New description (7 sentences):**
> Chain of Thought is a foundational reasoning strategy that instructs the model to work through a problem step by step before delivering a final answer. It is designed for tasks where intermediate reasoning improves accuracy, such as math problems, logical deduction, multi-step planning, or complex comparisons. The prompt directs the model to identify relevant facts, connect them methodically, check each inference against the original request, and avoid unsupported assumptions. By making the reasoning trace explicit, it reduces the risk of skipping critical steps or arriving at a plausible but incorrect answer. The strategy trades latency for correctness — each call produces a single careful answer rather than exploring alternatives. It serves as the baseline reasoning approach in the SDK and the building block that more advanced strategies (like Tree of Thoughts or Self-Consistency) extend. The final output is a concise answer preceded by visible intermediate reasoning steps, always ending with a `Final answer:` marker.

### 6.2 chain_of_draft.json

**File(s):** `vidbyte/prompts/prompts/chain_of_draft.json`
**Type:** Modified

**Current description:** "Concise reasoning prompt with an explicit word budget."

**New description (7 sentences):**
> Chain of Draft is a token-efficient reasoning strategy that enforces a strict word budget per intermediate reasoning step. It is intended for scenarios where output tokens carry a cost premium — such as high-volume agent pipelines, real-time applications, or models with tight context windows. The prompt accepts a `{max_words_per_step}` parameter that caps each reasoning step, forcing the model to distill only the details essential for correctness. Unlike Chain of Thought, which allows unbounded reasoning, Chain of Draft compresses the reasoning trace into terse, telegraphic notes that still preserve logical fidelity. It discourages the model from hiding uncertainty and requires a complete standalone final answer after the draft. The strategy is particularly effective when the reasoning path matters less than the correctness of the conclusion. It pairs well with verifier or voting strategies that can compensate for the compressed reasoning surface.

### 6.3 skeleton_of_thought.json

**File(s):** `vidbyte/prompts/prompts/skeleton_of_thought.json`
**Type:** Modified

**Current description:** "Prompts for outline-first generation and point expansion."

**New description (7 sentences):**
> Skeleton of Thought is a two-phase generation strategy that separates structural planning from detailed writing. In the first phase, the model produces a concise numbered skeleton of up to `{max_points}` distinct, logically ordered points without filling in details. This skeleton serves as a scaffold that guarantees coverage of all required topics before any prose is written. In the second phase, the model expands each skeleton point independently into polished, self-contained prose, focusing only on the assigned point. This decomposition makes the strategy ideal for long-form content generation — reports, articles, documentation, or educational material — where structural coherence across sections is critical. Because each point is expanded in isolation, the approach also enables parallel execution across multiple model calls. The final output is assembled from the individually expanded points, producing a complete document with clear logical flow.

### 6.4 tree_of_thoughts.json

**File(s):** `vidbyte/prompts/prompts/tree_of_thoughts.json`
**Type:** Modified

**Current description:** "Prompts for generating, evaluating, and finalizing reasoning branches."

**New description (8 sentences):**
> Tree of Thoughts is a multi-step reasoning strategy that generates multiple candidate reasoning branches, evaluates them, and synthesizes the best result. It is designed for complex open-ended problems where a single reasoning path may be suboptimal — such as creative writing, strategy formulation, puzzle solving, or ambiguous analysis tasks. The first phase generates `{branches}` diverse, meaningfully distinct candidate approaches, each exploring the problem from a different angle. The second phase scores each branch from 1 to 10 on correctness, feasibility, completeness, and task fit, selecting the best candidate and explaining the rationale. The third phase takes the winning branch and produces a polished final answer, correcting any small gaps identified during evaluation. This explore-then-commit pattern significantly improves answer quality at the cost of higher token consumption. It is an effective choice when the task has no single obviously correct solution path.

### 6.5 self_consistency.json

**File(s):** `vidbyte/prompts/prompts/self_consistency.json`
**Type:** Modified

**Current description:** "Prompt for independent samples used in majority voting."

**New description (7 sentences):**
> Self-Consistency is a robustness strategy that generates multiple independent reasoning samples and selects the most common answer through majority voting. It is designed for tasks where a single model call may be unreliable — particularly math problems, logical reasoning, factual questions with a definitive correct answer, and any domain where errors are stochastic rather than systematic. Each sample is generated independently using the same prompt, which instructs the model to work from first principles without relying on prior samples. The per-sample prompt identifies itself with `{index}` of `{samples}` to enable tracking and normalization. After all samples are collected, the strategy normalizes answers and selects the majority result. This approach reduces variance due to sampling temperature and catches errors that a single Chain of Thought run might miss. It is most effective when answer correctness is binary or easily comparable rather than open-ended.

### 6.6 step_back.json

**File(s):** `vidbyte/prompts/prompts/step_back.json`
**Type:** Modified

**Current description:** "Prompts for abstracting principles before solving a task."

**New description (7 sentences):**
> Step-Back Prompting is a two-phase strategy that first abstracts general principles from the task domain, then applies those principles to produce the final answer. It is designed for tasks where understanding the underlying rules or concepts yields better results than attacking the specific question directly — such as science problems, policy analysis, legal reasoning, or technical troubleshooting. In the first phase, the model identifies the durable rules, abstractions, or concepts that govern the answer domain, deliberately avoiding the original question to prevent premature conclusions. In the second phase, the model uses those principles as a lens to solve the original task, connecting each important conclusion back to the governing rules. This separation of principle extraction from application produces answers that are more principled and easier to audit. It is especially valuable when the task requires consistency with established frameworks or when surface-level answers risk violating deeper constraints.

### 6.7 vmao.json

**File(s):** `vidbyte/prompts/prompts/vmao.json`
**Type:** Modified

**Current description:** "Prompt templates used by verified multi-agent orchestration."

**New description (8 sentences):**
> Verified Multi-Agent Orchestration (VMAO) is a structured multi-agent strategy that decomposes a task into a directed acyclic graph (DAG) of sub-questions, executes them, synthesizes results, and verifies the final answer. It is designed for complex, multi-faceted tasks that benefit from decomposition — research synthesis, multi-constraint optimization, comparative analysis, or any problem where sub-questions can be answered independently. The planner agent first breaks the task into a minimal JSON DAG where each node includes an id, question, dependencies, and optional capability hints. Worker agents then answer each node independently, with the synthesizer combining all outputs into a coherent final answer. A verifier agent scores the answer (0-1) and identifies concrete gaps; if the answer is not approved, a gap planner creates follow-up nodes to close those gaps. This verify-and-repair loop ensures the final output meets the task requirements before being returned to the caller. VMAO represents the SDK's most thorough and reliable strategy at the cost of multiple sequential and parallel model calls.

### 6.8 expert_prompting.json

**File(s):** `vidbyte/prompts/prompts/expert_prompting.json`
**Type:** Modified

**Current description:** "Prompt for field-specific expert framing."

**New description (7 sentences):**
> Expert Prompting is a persona-based strategy that frames the model as a domain expert in a specified `{domain}` to elicit higher-quality, practitioner-level responses. It is designed for tasks where domain depth matters — medical analysis, legal interpretation, engineering design, financial modeling, or any field with specialized vocabulary and edge cases that a generalist would miss. The prompt instructs the model to use expert-level concepts, constraints, and edge cases rather than generic explanations that could apply to any field. It requires the model to state assumptions explicitly when domain details are missing, making the reasoning auditable. Unlike generic role-prompting, Expert Prompting sets a practitioner-level quality bar — the answer should be useful to someone already working in the field, not a beginner's introduction. This strategy is lightweight (single call) and pairs well with any other reasoning strategy to add domain depth to the reasoning process.

### 6.9 plan_and_execute.json

**File(s):** `vidbyte/prompts/prompts/plan_and_execute.json`
**Type:** Modified

**Current description:** "Prompts for planning, executing plan steps, and synthesizing."

**New description (7 sentences):**
> Plan and Execute is a three-phase strategy that separates task decomposition, step execution, and synthesis into distinct model calls. It is designed for multi-step procedural tasks — code generation, data analysis pipelines, workflow automation, or any task where sequential steps depend on prior outputs. The planner first creates a concise numbered plan with steps that each have a clear purpose and materially improve the answer. The executor then processes each step in isolation, producing concrete work products without synthesizing prematurely. Finally, the synthesizer combines all step outputs into a coherent final answer, resolving contradictions and removing redundant intermediate notes. This separation allows the executor to focus deeply on one step at a time without losing context, improving reliability for long chains of reasoning. It also enables step-level inspection and debugging of the reasoning trace.

### 6.10 paradigm_router.json

**File(s):** `vidbyte/prompts/prompts/paradigm_router.json`
**Type:** Modified

**Current description:** "Prompt for selecting the best available reasoning strategy."

**New description (7 sentences):**
> Paradigm Router is a meta-strategy that analyzes an incoming task and selects the most appropriate reasoning strategy from the available `{options}`. It is designed as a lightweight dispatch layer for agent systems that support multiple reasoning paradigms and want to route each task to the strategy best suited for its shape and expected failure mode. The router prefers decomposition-based strategies (like Plan and Execute or Skeleton of Thought) for broad writing or multi-section tasks, and voting-based strategies (like Self-Consistency) for math, logic, or fragile factual answers where a single sample may mislead. By making strategy selection explicit and inspectable, the router provides a deterministic, auditable alternative to always running the same pipeline. It returns only the exact strategy name, allowing the caller to then invoke that strategy's full prompt set without additional routing overhead.

### 6.11 multi_agent_reflexion.json

**File(s):** `vidbyte/prompts/prompts/multi_agent_reflexion.json`
**Type:** Modified

**Current description:** "Prompts for drafting, critique, and revision with critic roles."

**New description (7 sentences):**
> Multi-Agent Reflexion is a three-phase iterative improvement strategy that uses distinct agent roles — drafter, critic, and reviser — to produce higher-quality outputs through structured feedback. It is designed for tasks where quality matters more than speed and where a second-pass critique can catch errors invisible to the original drafter — such as policy documents, technical specifications, public communications, or safety-critical content. The drafter produces an initial answer specific enough for critique, preserving all constraints. One or more critic agents then review the draft from specific `{critic_role}` perspectives (e.g., "fact-checker", "legal reviewer", "accessibility auditor"), identifying concrete weaknesses and actionable corrections. The reviser applies every correction that improves accuracy or clarity, resolves conflicts between critics by prioritizing the original task, and produces a final coherent answer that reads as one seamless document. This role-separated critique loop catches errors that self-review misses by forcing distinct evaluative perspectives.

### 6.12 context_engineering.json

**File(s):** `vidbyte/prompts/prompts/context_engineering.json`
**Type:** Modified

**Current description:** "Reusable guidance for constructing operational prompts."

**New description (7 sentences):**
> Context Engineering is a meta-prompt that provides reusable guidance for constructing effective operational prompts for capable models. It is not a reasoning strategy itself but a design methodology that SDK users can apply when authoring their own custom prompts. The guidance instructs prompt authors to structure their text as dense operational context, covering seven essential dimensions: role, objective, constraints, available inputs, work procedure, output contract, and quality bar. It emphasizes concrete policy statements over vague encouragement — telling the model exactly what to do and what to avoid, rather than asking it to "try hard" or "be thorough." The prompt also advises authors to declare any assumptions the model must preserve and to explain what to avoid when it affects correctness or safety. This methodology ensures that custom prompts integrated into the SDK maintain the same rigorous, inspectable quality as the built-in strategies.

### 6.13 budget_forcing.json

**File(s):** `vidbyte/prompts/prompts/budget_forcing.json`
**Type:** Modified

**Current description:** "Prompts for continuing reasoning until a final answer marker appears."

**New description (7 sentences):**
> Budget Forcing is an iterative reasoning strategy that extends the model's effective thinking time by allowing it to continue reasoning across multiple sequential calls until it produces a satisfactory final answer. It is designed for tasks where a single forward pass may stop prematurely — complex planning, multi-constraint optimization, debugging, or any problem where the model benefits from revisiting and refining its own output. The initial prompt instructs the model to solve carefully, check assumptions, and continue looking for mistakes until the answer feels complete, ending with `Final answer:`. If the model halts without that marker, the continue prompt picks up where the previous attempt left off, double-checking assumptions, catching missing cases, and correcting errors without restarting from scratch. This call-continue loop effectively grants the model more "thinking tokens" than a single inference budget would allow, enabling deeper reasoning without changing the underlying model architecture.

### 6.14 agentic_rag.json

**File(s):** `vidbyte/prompts/prompts/agentic_rag.json`
**Type:** Modified

**Current description:** "Prompts for deciding retrieval needs and answering from retrieved context."

**New description (7 sentences):**
> Agentic RAG is a two-phase retrieval-augmented generation strategy that separates the decision of what to retrieve from the act of answering with retrieved context. It is designed for tasks that require external knowledge — fact-checking, research synthesis, documentation lookup, or any question where the model's parametric knowledge may be insufficient or outdated. In the first phase, the model formulates concise, targeted retrieval queries that separate must-have evidence from optional background, prioritizing queries that would verify the highest-risk claims. After the caller executes the retrieval (outside the strategy), the second phase instructs the model to ground all important claims in the provided material, explicitly state gaps when context is insufficient, and avoid fabricating facts. This two-phase design gives the caller control over the retrieval mechanism (vector search, API call, database query) while standardizing the query formulation and evidence-grounded answering pattern.

### 6.15 answer_convergence.json

**File(s):** `vidbyte/prompts/prompts/answer_convergence.json`
**Type:** Modified

**Current description:** "Prompt for repeated independent attempts until answers converge."

**New description (7 sentences):**
> Answer Convergence is a stability-testing strategy that generates repeated independent answers until a consistent result emerges across attempts. It is designed for tasks where answer stability indicates correctness — classification, structured data extraction, factual verification, or any task where the model should produce the same answer every time given the same input. Each attempt uses the same prompt template, which identifies itself as attempt `{index}` and instructs the model to work from the original task as the sole source of truth without relying on any other attempt. The prompts are written to produce answers that are explicit and easy to compare across samples, avoiding decorative wording that would obscure convergence. The strategy continues generating attempts until a configurable number of consecutive matching answers is reached. This approach catches sampling variance and provides a confidence signal: if answers diverge, the task may be genuinely ambiguous or beyond the model's reliable capability.

---

## 7. Data Model Changes

N/A — No schema changes. The JSON file structure (`name`, `description`, `key`, `prompts`) remains identical. Only the string value of the `description` field in each file changes.

---

## 8. API Changes

N/A — No API endpoints are affected. This is a static content change to JSON asset files.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/prompts/prompts/chain_of_thought.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/chain_of_draft.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/skeleton_of_thought.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/tree_of_thoughts.json` | Expand description to 8 sentences |
| MODIFY | `vidbyte/prompts/prompts/self_consistency.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/step_back.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/vmao.json` | Expand description to 8 sentences |
| MODIFY | `vidbyte/prompts/prompts/expert_prompting.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/plan_and_execute.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/paradigm_router.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/multi_agent_reflexion.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/context_engineering.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/budget_forcing.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/agentic_rag.json` | Expand description to 7 sentences |
| MODIFY | `vidbyte/prompts/prompts/answer_convergence.json` | Expand description to 7 sentences |

**Total:** 15 files modified, 0 created, 0 deleted.

---

## 10. Testing Plan

### Unit Tests
The existing test `test_prompt_values_are_coherent_sentence_blocks` in `tests/test_prompt_registry.py` verifies prompt value sentence counts. No new unit tests are required since this is a content-only change, but the existing tests must continue to pass.

### Integration Tests
- All 15 JSON files must load successfully through `PromptRegistry.default()`
- `PromptRegistry.default().keys()` must return all 15 keys
- The `_read_record` validation must accept the expanded descriptions (no schema violations)

### Manual Verification
1. Run `python -m pytest tests/test_prompt_registry.py -v` — all tests must pass
2. Run `python -c "from vidbyte.lib.prompts import PromptRegistry; r = PromptRegistry.default(); print(len(r.keys()))"` — must print 15
3. Spot-check 2-3 expanded descriptions to verify they are 6-8 sentences and factually accurate

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | N/A | No external dependencies | None |

---

## 12. Rollout & Deployment

- No feature flags required
- Not a breaking change — descriptions are metadata, not functional logic
- No deployment order dependencies
- Rollback: revert the commit (descriptions are purely informational)

---

## 13. Open Questions

- [ ] Should descriptions mention the original research paper or citation for each strategy? (Decision: No — keep descriptions practical and self-contained for SDK users.)

---

## 14. Alternatives Considered

### Alternative 1: Add a new `long_description` field instead of expanding `description`
- What: Keep the short `description` and add a separate field for the expanded text
- Why rejected: This would require a schema change to the JSON format and to the registry loading code. Expanding the existing `description` field achieves the goal with zero code changes and aligns with the existing `adding-prompts.md` convention.

### Alternative 2: Write descriptions as a separate markdown file
- What: Create a `docs/prompt-catalog.md` with all descriptions
- Why rejected: This separates the documentation from the data it describes, making it likely to drift out of sync. Keeping descriptions in the JSON files ensures they stay co-located with the prompt text and are inspectable through the registry API.
