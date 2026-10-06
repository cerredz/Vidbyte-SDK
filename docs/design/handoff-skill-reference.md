# Design Doc: Handoff Skill Reference

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

This change updates the central Vidbyte SDK handoff skill reference so it explains the full handoff feature as it exists in the repository today: the `Handoff` primitive, preset specs, `HandoffAgent`, `BaseAgent.handoff()`, automatic post-run handoffs, the `CreateHandoffTool` mid-run authoring path, context-manager sync, behavior/eval predicates, and prompt assets. The implementation is documentation-only and should make `skills/vidbyte-sdk/handoff.md` the authoritative local guide for developers and agents working on or using handoffs.

---

## 2. Goals & Non-Goals

### Goals

- Replace or substantially expand `skills/vidbyte-sdk/handoff.md` into a complete reference for every handoff surface currently present in the SDK.
- Cover the primitive layer: `vidbyte/context/handoff/`, `Handoff`, `MinimalHandoff`, `EngineeringHandoff`, `ResearchHandoff`, `context/handoffs.py`, and root exports.
- Cover the generator layer: `vidbyte/agents/handoff.py`, `HandoffAgent.from_source_agent()`, `run_auto_handoff()`, source-run rendering, output schema construction, generation, and parsing fallbacks.
- Cover the agent surface: constructor `handoff=`, `last_handoff`, `handoffs`, `BaseAgent.handoff(spec=None, by=None)`, `record_handoff()`, `_sync_handoff_primitive()`, `_run_auto_handoff()`, and `fork()` propagation.
- Cover the tool surface: `CreateHandoffTool`, its `create_handoff(title, sections, audience?, instructions?)` contract, `binds_to_primitive="handoff"`, dynamic prior-handoff description, and stable `handoff:N` ids.
- Cover the eval/behavior surface: `agent.behavior.handoff`, `RunProbe`, and the handoff predicate methods.
- Cover the prompt asset: `vidbyte/prompts/prompts/handoff/handoff.md`, `handoff.json`, and `Prompt.HANDOFF_SYSTEM_PROMPT`.
- Include practical usage examples for on-demand handoff, auto-handoff, mid-run model-authored handoffs, standalone `HandoffAgent`, custom specs, and using a handoff as context for another agent.
- Document important operational edges: extra cost/latency, most-recent-run behavior, auto-handoff best-effort semantics, schema enforcement, parse fallback, `extra_sections`/`raw_output`, context-registry sync requirements, and preset-vs-tool tradeoffs.

### Non-Goals

- No runtime behavior changes to handoff generation, parsing, context sync, tools, or behavior predicates.
- No new handoff preset classes or public APIs.
- No changes to README, `llms.txt`, or broader usage skill files in this PR.
- No automated test additions, because this is a documentation-only skill-reference update.
- No migration of the handoff system to a top-level `vidbyte/handoff/` package.

---

## 3. Background & Context

The repository already has a handoff skill reference at `skills/vidbyte-sdk/handoff.md`, and `skills/sdk/SKILL.md` lists that file as the SDK Developer Reference entry for "Handoffs". The current handoff reference explains the original primitive and generator model, but it does not fully capture the current repository surface. In particular, it under-documents the agent-authored `CreateHandoffTool`, `record_handoff()`/context-manager sync, accumulated `agent.handoffs`, and `agent.behavior.handoff` assertions.

Repo audit findings:

- The SDK is a Python 3.11+ package configured by `pyproject.toml`, using in-repo Python modules under `vidbyte/` and markdown skill files under `skills/`.
- Existing skill references use markdown files with direct import examples, module-layout tables, invariants, and rules for extending the SDK.
- `skills/vidbyte-sdk/SKILL.md` explicitly says handoff primitive classes belong under `vidbyte/context/handoff/`, `HandoffAgent` belongs under `vidbyte/agents/handoff.py`, and handoff changes should follow `skills/vidbyte-sdk/handoff.md`.
- `skills/sdk/update-skill-files.md` requires skill files to remain accurate when SDK functionality changes.
- The handoff runtime now spans five layers: primitive/spec/output, generator, `BaseAgent` integration, builtin tool, and behavior/eval predicates.

The design should preserve the current central-file structure by updating `skills/vidbyte-sdk/handoff.md` rather than adding a parallel top-level `skills/handoff.md`, because the repository already has a registered handoff reference path.

---

## 4. Requirements

### Functional Requirements

1. `skills/vidbyte-sdk/handoff.md` must describe `Handoff` as a sectioned document that simultaneously acts as a spec, a filled artifact, and a `ContextItem` primitive.
2. The doc must list the three presets and their section shapes: `MinimalHandoff`, `EngineeringHandoff`, and `ResearchHandoff`.
3. The doc must explain custom specs using `Handoff(title=..., sections=..., instructions=...)`, including that section values in specs are authoring instructions, not produced content.
4. The doc must document on-demand handoffs from any agent via `await agent.handoff()` and `await agent.handoff(EngineeringHandoff())`.
5. The doc must document the optional `by=` parameter for passing a pre-built generator agent.
6. The doc must document automatic post-run handoffs via `BaseAgent(..., handoff=...)`, including `reply.metadata["handoff"]`, `reply.metadata["handoff_error"]`, `agent.last_handoff`, and `agent.handoffs`.
7. The doc must state that auto-handoff is best-effort and must not crash the primary reply when generation fails.
8. The doc must document the mid-run tool path using `CreateHandoffTool`, including its current tool inputs: `title`, `sections`, optional `audience`, and optional `instructions`.
9. The doc must explain that `CreateHandoffTool` lets the model design free-form section titles, records each handoff with `record_handoff()`, and assigns stable ids such as `handoff:1`.
10. The doc must explain `binds_to_primitive="handoff"` as the formal tool-to-primitive link.
11. The doc must explain how handoffs become context: `Handoff.to_context_text()`, passing filled handoffs in `context_items`, and context-registry upsert when a context manager and `primitive_id` exist.
12. The doc must document `HandoffAgent` standalone usage through `AgentClient().handoff(...)` and `HandoffAgent.from_source_agent(...)`.
13. The doc must summarize schema enforcement through `HandoffAgent.build_output_schema()`, including required spec section keys and `additionalProperties: False` when fixed titles exist.
14. The doc must summarize parsing order: structured output, raw JSON, then markdown header blocks.
15. The doc must document preservation mechanics: invented sections go to `metadata["extra_sections"]`; unparseable/no matching output goes to `metadata["raw_output"]`.
16. The doc must document behavior/eval predicates under `agent.behavior.handoff`.
17. The doc must include a module map covering all handoff-related source files.
18. The doc must include guidance for choosing between preset/spec generation and `CreateHandoffTool`.
19. The doc must include operational caveats for cost/latency, most-recent-run behavior, `fork()` propagation, and context sync.
20. The doc must preserve the existing "rules for adding a new prebuilt handoff" guidance, updated as needed to match current code.

### Non-Functional Requirements

- Documentation must be accurate against the current local repository implementation.
- Examples must use current import paths and method names.
- The reference must be skimmable by future agents, with clear headings and compact code examples.
- The update must avoid introducing new API promises that the implementation does not support.
- The doc should remain ASCII-only unless preserving existing file content requires otherwise.
- No new dependencies, services, migrations, or runtime configuration changes.

---

## 5. High-Level Design

The implementation will modify only `skills/vidbyte-sdk/handoff.md`. The updated file will become a layered reference organized around how the feature is built and used: primitive, generator, agent surface, tool surface, behavior/eval surface, prompt asset, context flow, and extension rules.

The central design decision is to document the real current tool behavior, not the older design-doc intent. Current `CreateHandoffTool` does not ask for `handoff_type` or generate through `HandoffAgent`; it accepts `title` and `sections`, records a filled `Handoff` directly, appends to `agent.handoffs`, and syncs through `record_handoff()`. The skill reference must say that clearly so future agents do not implement or use the wrong interface.

The guide will include short examples for the four main use cases: on-demand handoff after a run, automatic handoff after every run, model-authored mid-run handoffs through `CreateHandoffTool`, and standalone generation with `AgentClient().handoff(...)`. It will then describe specs, schema/parsing, context-manager sync, behavior assertions, and gotchas.

```text
skills/vidbyte-sdk/handoff.md
    |
    |-- Primitive/spec/output reference
    |-- HandoffAgent generation reference
    |-- BaseAgent on-demand and auto-handoff reference
    |-- CreateHandoffTool mid-run reference
    |-- Context item and registry flow
    |-- Behavior/eval predicate reference
    |-- Prompt asset and module map
    `-- Extension rules and operational caveats
```

---

## 6. Detailed Design

### 6.1 Design document

**File(s):** `docs/design/handoff-skill-reference.md`
**Type:** New file

#### What it does

Captures the approved implementation plan for the documentation-only handoff skill reference update.

#### Interface / API

```text
docs/design/handoff-skill-reference.md
```

#### Logic / Algorithm

1. Record repo audit findings.
2. Define the documentation requirements and non-goals.
3. Declare the file manifest and rollout plan.
4. Stop for explicit approval before implementation.

#### Edge Cases & Error Handling

- If the user wants a new top-level `skills/handoff.md` instead of updating `skills/vidbyte-sdk/handoff.md`, the manifest must be revised before implementation.
- If additional usage skill files should be updated in the same PR, the manifest must be revised before implementation.

### 6.2 Central handoff skill reference

**File(s):** `skills/vidbyte-sdk/handoff.md`
**Type:** Modified

#### What it does

Serves as the canonical developer/agent reference for the handoff feature inside the Vidbyte SDK.

#### Interface / API

```markdown
# Handoffs

## What a handoff is
## Quick use cases
## The primitive layer
## The spec system
## The generator layer
## The BaseAgent surface
## The tool layer
## Handoffs as context
## Behavior and eval assertions
## Prompt asset
## Module layout
## Operational edges
## Choosing the right handoff path
## Rules for changing handoffs
```

#### Logic / Algorithm

1. Preserve the existing high-level explanation that a handoff is a `ContextItem`, spec, and output.
2. Add a quick-start section with examples for:
   - `await agent.handoff()`
   - `await agent.handoff(EngineeringHandoff())`
   - `Agent(..., handoff=EngineeringHandoff())`
   - `CreateHandoffTool()` in `tools=[...]`
   - `AgentClient().handoff(ResearchHandoff())`
3. Add a feature map covering:
   - `vidbyte/context/handoff/base.py`
   - `vidbyte/agents/handoff.py`
   - `vidbyte/agents/base.py`
   - `vidbyte/tools/builtins/handoff/create.py`
   - `vidbyte/evals/behavior/handoff.py`
   - `vidbyte/prompts/prompts/handoff/`
4. Explain exact current tool schema:
   - Required: `title`, `sections`
   - Optional: `audience`, `instructions`
   - The model chooses free-form section titles.
5. Explain exact current generated-spec schema behavior:
   - Preset/custom specs use `HandoffAgent.build_output_schema()`.
   - Fixed title specs require exactly those section keys.
   - Free-form/no-title specs allow string additional properties.
6. Explain parsing and preservation rules:
   - Structured metadata first.
   - Raw JSON next.
   - Markdown header blocks last.
   - Extra sections and raw output are retained in metadata.
7. Add behavior/eval examples:
   - `agent.behavior.handoff.handoff_occurred()`
   - `handoff_is_filled()`
   - `handoff_count()`
   - `handoff_has_section(...)`
   - `handoff_section_contains(...)`
8. Update the module layout and extension rules.

#### Edge Cases & Error Handling

- The doc must not imply that `CreateHandoffTool` routes through `HandoffAgent`; current code builds a `Handoff` directly from provided sections.
- The doc must not imply that `CreateHandoffTool` accepts `handoff_type`, `objective`, `scope`, `non_goals`, or `custom_sections`; those appear in an older design doc but not in current source.
- The doc must explain that on-demand `agent.handoff()` summarizes the most recent run framing, not an arbitrary earlier run.
- The doc must explain that `fork()` propagates auto-handoff config, which can create unexpected extra model calls.

---

## 7. Data Model Changes

N/A - This is a documentation-only change. No Python classes, dataclasses, JSON schemas, database schemas, or context primitive shapes will be modified.

---

## 8. API Changes

N/A - This is a documentation-only change. Existing public Python APIs will only be described, not changed.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/handoff-skill-reference.md` | Design doc for the central handoff skill reference update |
| MODIFY | `skills/vidbyte-sdk/handoff.md` | Expand the central handoff reference to cover all current handoff use cases and feature layers |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Local repository files | Current working tree | Source of truth for documented behavior | Low - documentation can be checked directly against local code |

No new third-party dependencies or external services.

---

## 11. Rollout & Deployment

- No feature flags.
- No package build or release behavior changes.
- Rollout is the merge of a documentation-only PR.
- Verification after implementation should include a manual review of `skills/vidbyte-sdk/handoff.md` against the relevant source files and a lightweight markdown/diff sanity check.
- Rollback is reverting the documentation commit.

---

## 12. Open Questions

- [ ] Should this PR also update `skills/usage/available_tools.md` to list `CreateHandoffTool` in the user-facing built-in tool catalog, or should that remain a separate docs cleanup?
- [ ] Should the final handoff reference replace the existing file wholesale, or preserve more of the current wording and insert new sections around it?

---

## 13. Alternatives Considered

### Alternative 1: Add a new top-level `skills/handoff.md`

- What: Create a new central handoff file at `skills/handoff.md`.
- Why rejected: The repository already registers `skills/vidbyte-sdk/handoff.md` as the handoff reference in `skills/sdk/SKILL.md`, so a new top-level file would split the source of truth.

### Alternative 2: Update README and usage skill files instead

- What: Spread the handoff explanation across README, `skills/usage/create_agent.md`, `skills/usage/available_tools.md`, and `skills/usage/agent-behavior.md`.
- Why rejected: The user asked for a central skills/handoff file. Broader docs may need follow-up cleanup, but the core request is best satisfied by the existing central reference.

### Alternative 3: Generate reference docs from code

- What: Build an automated script to inspect the Python objects and emit markdown.
- Why rejected: This is a focused documentation update. A generator would add maintenance surface without improving the immediate accuracy of the handoff reference.
