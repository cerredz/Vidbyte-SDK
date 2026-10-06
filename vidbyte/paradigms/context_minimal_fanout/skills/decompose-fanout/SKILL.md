---
name: decompose-fanout
description: Decompose the original prompt into non-overlapping subtasks, launch one subagent per subtask, wait for all subagents, then merge and report.
---

# Decompose Fanout

## Goal

Use this skill when the original task is broad enough to benefit from multiple fresh context windows, but does not need a full design document for every branch. The parent agent gathers enough context to split the work into non-overlapping implementation prompts. Each prompt must have clear ownership, read-only context, expected output, and verification responsibility. Subagents run in parallel only when the parent has proved they will not edit the same mutable files or contracts. The parent remains responsible for launching, waiting, merging, conflict handling, and final verification. The split plan is the coordination contract that prevents parallel work from becoming overlapping work. The final result should integrate the subagent outputs into one coherent change with all blockers and skipped checks visible.

## Description

This skill is the direct fanout workflow for context-minimal implementation. It fits broad tasks with several independent ownership areas and enough clarity that each branch can be expressed as an implementation prompt instead of a design document. The parent agent performs the decomposition, writes the split plan, launches one subagent per branch, and waits for every branch to return. Each subagent receives a narrow prompt that names what it owns, what it may only read, what it must verify, and what it must report. The parent should prefer fewer, cleaner branches over many loosely defined prompts. When two branches need the same mutable area, the parent merges them instead of forcing parallelism. Integration stays in the parent context so the final result can be checked as a whole.

## Algorithm

1. Restate the original task with hard requirements, non-goals, constraints, requested verification, and any user-facing outcomes.
2. Gather enough repository context to understand ownership. Read relevant APIs, tests, docs, configuration, generated artifacts, and nearby implementation patterns before splitting.
3. Identify separable ownership areas. Consider files, public contracts, tests, migrations, docs, generated artifacts, data flow, and verification responsibilities.
4. Write a parent split plan before spawning subagents. The plan must include the global goal, global instructions, non-overlap requirements, implementation prompts, owned areas, read-only areas, commands, and reporting requirements.
5. For each implementation prompt, specify:
   - Branch title and objective.
   - Exact output expected from the subagent.
   - Owned files, contracts, tests, docs, or artifacts.
   - Read-only context the subagent may inspect.
   - Verification commands or inspection steps.
   - Stop conditions and blocker reporting requirements.
6. Apply the non-overlap test to every prompt pair. Two prompts must not both own the same file path, public API contract, test file, migration, generated artifact, or verification obligation.
7. Merge prompts that cannot be made independent. Do not split work merely to increase the number of subagents.
8. Read `references/harness-commands.md` and choose the command form for the current coding harness. If the platform is unknown, follow the discovery procedure in that reference.
9. Launch one subagent per approved implementation prompt. Include the global goal, branch prompt, owned areas, read-only areas, verification commands, and a warning not to cross ownership boundaries.
10. Wait for all subagents to finish. Track exit status, changed files, verification, blockers, conflicts, and any request to modify read-only areas.
11. Merge subagent results in the parent context. Resolve conflicts by ownership and reject edits that crossed the branch boundary without being reported first.
12. Run parent-level verification that covers the integrated result and any shared contracts.
13. Report completed branches, files changed, verification evidence, skipped checks, blockers, conflicts, and remaining integration work.

## Rules

- Do not run subagents before writing the split plan.
- Do not split work before reading enough repo context to understand ownership.
- Do not use vague prompts such as "handle backend" or "fix tests"; specify ownership and outputs.
- Do not assign the same mutable file, contract, test, migration, generated artifact, or verification responsibility to multiple prompts.
- Do not let subagents modify read-only areas.
- Do not hide conflicts. If a clean split is impossible, report it and merge the coupled work into one prompt.
- Do not inline platform command details here; keep them in `references/harness-commands.md`.
