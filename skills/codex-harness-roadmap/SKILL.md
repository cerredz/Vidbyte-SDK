---
name: codex-harness-roadmap
description: Plan future CodexHarnessAgent features and Vidbyte abstraction translations using a versioned implementation baseline and official Codex documentation. Use for capability gaps, roadmap checklists, or selecting the next harness integration.
---

# Codex Harness Roadmap

Help the user identify what to add to Vidbyte's Codex harness agent, what provider control makes it possible, and what must be proven before it can ship.

This is a planning/reference skill. Reading a backlog item does not authorize its implementation, installing an extension, changing provider settings, or modifying user accounts.

## Load only what the task needs

- For a gap audit, roadmap, or checklist, read [the future-work checklist](references/checklist.md). It contains 100 stable task IDs, the PR baseline, surface labels, and delivery waves.
- For translating a named Vidbyte abstraction, read [the translation map](references/translation-map.md), then the linked checklist domain.
- For claims about Codex availability, controls, or APIs, read the relevant entries in [the source index](references/sources.md) and fetch those official pages. Inspect installed SDK signatures/generated schemas before promising a callable method.

## Establish the comparison baseline

Check the current branch and whether `vidbyte/agents/codex/` exists. The saved baseline is unmerged PR #409 at commit `c3842585`, inspected with Python SDK 0.147.0 on 2026-09-05. If the adapter is absent, use the source index's commit-pinned links and state that the comparison is against that PR. Do not silently treat the PR as merged or copy its runtime code into the checkout.

If newer implementation exists, reconcile it with the checklist before presenting gaps. Keep implemented behavior separate from deeper extensions to that behavior.

## Produce actionable guidance

For each selected task, explain the user-visible outcome, the Codex surface, the existing Vidbyte abstraction, proposed implementation seam, dependencies, and completion evidence. Use the smallest useful subset for a scoped question; return the complete grouped checklist when asked for the whole roadmap.

Distinguish:

- a public Python SDK method;
- a lower-level app-server operation;
- native config reachable through existing passthrough;
- application-owned composition;
- experimental, unavailable, or deprecated behavior.

Names such as `CodexTurnController` in the references are **proposals**, not exported SDK classes. Do not emit runnable imports for them.

## Preserve semantic boundaries

A native event is observable evidence, not necessarily an enforcement hook. A native fork copies conversation history, not project files. Codex owns its internal loop; Vidbyte middleware, budgets, sessions, and tools need individual mappings. A field called `capabilities` does not establish interface compatibility.

Use the checklist's documented restrictions for hook failures, plugin readiness, permission precedence, ephemeral sessions, and host execution. Flag an unsupported requirement clearly instead of silently approximating it.

If asked to implement a subset, first refresh its evidence and define its scope using the repository's normal development workflow. Mark tasks complete only after the behavior and relevant verification exist.
