---
name: claude-harness-roadmap
description: Plan future ClaudeHarnessAgent features and Vidbyte abstraction translations using a versioned implementation baseline and official Claude Agent SDK documentation. Use for capability gaps, roadmap checklists, or selecting the next Claude harness increment.
metadata:
  short-description: Plan the next Claude harness increment
---

# Claude Harness Roadmap

Help the user identify what to add to Vidbyte's Claude harness agent, what provider control makes it possible, and what must be proven before it can ship.

This is a planning/reference skill. Reading a backlog item does not authorize its implementation, installing the optional extra, changing provider settings, or touching user accounts or credentials.

## Load only what the task needs

- For a gap audit, roadmap, or checklist, read [the future-work checklist](references/checklist.md). It contains stable task IDs, the shipped baseline, surface labels, and delivery waves.
- For translating a named Vidbyte abstraction, read [the translation map](references/translation-map.md), then the linked checklist domain.
- For claims about Claude availability, controls, or APIs, read the relevant entries in [the source index](references/sources.md) and fetch those official pages. Inspect the installed SDK's own types before promising a callable method or a field name.
- For how a capability *should* map onto Vidbyte at all — before asking whether it is built — read [`skills/claude-agent-sdk-translation/SKILL.md`](../claude-agent-sdk-translation/SKILL.md) and its feature matrix. That skill owns the disposition model; this one owns what remains.

## Establish the comparison baseline

Check the current branch and whether `vidbyte/agents/claude/` exists. The saved baseline is the `feat/claude-harness-agent` branch, inspected against documentation for `claude-agent-sdk` 0.2.152 on 2026-09-07. If the adapter is absent, state that the comparison is against that branch rather than treating it as merged.

If newer implementation exists, reconcile it with the checklist before presenting gaps. Keep implemented behavior separate from deeper extensions to that behavior.

## Produce actionable guidance

For each selected task, explain the user-visible outcome, the Claude surface, the existing Vidbyte abstraction, the proposed implementation seam, its dependencies, and its completion evidence. Use the smallest useful subset for a scoped question; return the complete grouped checklist when asked for the whole roadmap.

Distinguish:

- a public Python SDK function or `ClaudeSDKClient` method;
- a CLI-level or protocol-level behavior with no established Python wrapper;
- native configuration reachable through the adapter's existing typed records;
- application-owned composition outside Claude's loop;
- experimental, unavailable, deprecated, or platform-specific behavior.

Names such as `ClaudeSessionTransport` in the references are **proposals**, not exported SDK or Vidbyte classes. Do not emit runnable imports for them.

## Preserve semantic boundaries

Claude owns its internal loop. A hook that can approve a tool is not permission to execute that tool in Vidbyte's own executor. A native session fork copies conversation history, not project files. A provider token estimate is not a Vidbyte budget. Vidbyte middleware, compaction algorithms, MCTS, and actor-model runtimes are outer compositions, never substitutions inside Claude's loop.

Two boundaries specific to this adapter, because getting them wrong is silent:

- **A fork is lazy.** `fork()` returns a child carrying `resume` plus `fork_session`; the child has no session id of its own until its first successful run. Those two flags describe only the branch-creating turn and must not be resent once the child adopted an id, or every later turn branches again.
- **The session id must survive the raise.** A single-shot `query()` raises *after* yielding its error result. Any new transport mode must still record that result's `session_id`, or a run that hit `max_turns` becomes permanently unresumable.

Use the checklist's documented restrictions for callback ownership, permission precedence, sandbox platform gaps, and cross-host session resume. Flag an unsupported requirement clearly instead of silently approximating it.

If asked to implement a subset, first refresh its evidence against the installed SDK and define its scope using the repository's normal development workflow. Mark tasks complete only after the behavior and its verification both exist.
