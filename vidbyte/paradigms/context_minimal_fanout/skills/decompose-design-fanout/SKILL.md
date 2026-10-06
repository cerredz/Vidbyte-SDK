---
name: decompose-design-fanout
description: Gather context, decompose into subtasks, write per-subtask design docs, then launch one subagent per design doc and merge their results.
---

# Decompose, Design, Fanout

## Goal

Use this skill when a broad task can be implemented in parallel only after the parent agent has solved the design questions. The parent agent gathers context, decomposes the task, and writes a design document for every independent branch of work. Each design should be self-contained enough for a fresh-context subagent to implement without rediscovering the whole system. The parent keeps responsibility for architecture, ownership boundaries, integration, and final verification. Subagents receive narrow implementation authority, not permission to reinterpret the whole task. Parallelism is allowed only after the designs prove that the branches do not share mutable ownership. The final result should merge completed branches back into one coherent implementation with conflicts, skipped checks, and blockers made explicit.

## Description

This skill is the design-first fanout workflow for context-minimal implementation. It fits large changes where independent branches can run in fresh contexts, but only after the parent has resolved shared architecture and sequencing. The parent writes the split plan, creates one design per branch, checks those designs for overlap, and launches one subagent per approved design. Each subagent gets the original goal, global instructions, its design, owned areas, read-only context, verification expectations, and non-overlap rules. The parent waits for every subagent to finish before merging or making integration decisions. The parent also decides how to handle conflicts, blockers, failed checks, and design deviations. This keeps parallel implementation fast while preventing subagents from competing over the same contracts.

## Algorithm

1. Restate the original task and identify hard requirements, non-goals, shared constraints, compatibility expectations, and final verification requirements.
2. Gather targeted repository context needed to understand public contracts, mutable ownership areas, tests, docs, configuration, generated artifacts, and integration points.
3. Decompose the task into implementation branches that could be owned independently. Each branch must have distinct mutable paths, public contracts, tests, generated artifacts, and verification responsibilities.
4. Write a parent split plan before spawning subagents. The plan must include the global goal, global instructions, non-overlap requirements, branch list, design document locations, ownership summary, and final integration checklist.
5. Write one design document per branch. Each design must include:
   - Branch goal and success criteria.
   - Owned files, contracts, tests, artifacts, and verification.
   - Read-only context the subagent may inspect but not edit.
   - Proposed implementation approach.
   - Edge cases, failure modes, and compatibility concerns.
   - Explicit non-overlap reminders.
6. Compare every design against every other design. If two designs need the same mutable file, public contract, test file, migration, generated artifact, or verification responsibility, merge them or redesign the split before fanout.
7. Read `references/harness-commands.md` and choose the command form for the current coding harness. If the current platform is not listed, use that reference's discovery procedure before spawning.
8. Launch one subagent per approved design from the same repository state. Give each subagent the original goal, global instructions, its design document, owned areas, read-only areas, verification commands, and the rule that it must stop instead of crossing ownership boundaries.
9. Run subagents in parallel only when their ownership boundaries are clean. The parent must wait for every subagent process, background task, or harness task to complete, fail, or report a blocker.
10. Collect every subagent report. Record changed files, verification results, skipped checks, conflicts, blockers, and any deviation from the assigned design.
11. Merge completed branches in the parent context. Resolve conflicts according to ownership, and re-check shared contracts before accepting an integrated result.
12. Run parent-level verification across the merged result.
13. Report each design, each subagent result, files changed, verification evidence, conflicts resolved, skipped checks, blockers, and follow-up work.

## Rules

- Do not spawn subagents before the parent split plan and all branch design documents exist.
- Do not inline platform command details here; keep them in `references/harness-commands.md`.
- Do not assign the same mutable file, contract, test, migration, generated artifact, or verification responsibility to multiple subagents.
- Do not let a subagent edit outside its owned areas. A blocked subagent should report the dependency instead.
- Do not merge results until every subagent has completed, failed, or reported a blocker.
- Do not treat this skill as the SDK implementation of the paradigm. It is an external harness adapter and operating instruction.
