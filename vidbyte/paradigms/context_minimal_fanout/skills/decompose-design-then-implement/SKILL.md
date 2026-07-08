---
name: decompose-design-then-implement
description: Gather context, decompose into subtasks, write per-subtask design docs that solve the work up front, then implement each design sequentially.
---

# Decompose, Design, Then Implement

## Goal

Use this skill when a task needs the hard reasoning done before code changes begin. The agent gathers enough context to understand the system, decomposes the work into ordered subtasks, and writes a design for each subtask before implementation. Each design should answer the important questions while the context window is still fresh, including ownership, contracts, edge cases, and verification. The designs become execution instructions rather than loose planning notes. Implementation then proceeds one design at a time, with the agent checking whether reality still matches the design before editing. This keeps architectural decisions visible, reduces mid-implementation drift, and makes deviations deliberate instead of accidental. The result should be a completed change whose final report can trace every edit back to a solved design item.

## Description

This skill is the design-first sequential workflow for broad but coupled work. It fits tasks where a simple checklist would miss architectural choices, compatibility concerns, or sequencing constraints. The parent agent does the reasoning up front and writes compact design documents that resolve each subtask before edits start. Each design should name the current behavior, proposed behavior, affected contracts, data or control flow, edge cases, and verification. The agent then implements the designs in dependency order, treating each one as the local source of truth unless the codebase proves it wrong. When implementation reveals a mismatch, the agent updates the design record before continuing. The final outcome is both the code change and a durable trail of the decisions that shaped it.

## Algorithm

1. Restate the original task with hard requirements, non-goals, compatibility expectations, user-visible behavior, and requested verification.
2. Gather targeted repository context for the affected area. Read public APIs, nearby implementations, tests, docs, configuration, and existing design patterns that constrain the solution.
3. Decompose the task into subtasks that can be solved in a clear sequence. Mark dependencies explicitly so later designs do not assume work that has not been implemented.
4. Create a parent plan that lists every subtask, its status, its dependency order, and the design document that will solve it.
5. Write one design document per subtask before editing. Each design must include:
   - Goal and scope.
   - Current behavior or missing behavior.
   - Proposed change.
   - Owned files, public contracts, and integration points.
   - Edge cases and failure modes.
   - Verification commands or manual checks.
   - Rejected alternatives and why they were not chosen.
6. Review all designs as a set. Merge designs that need the same mutable file, public contract, migration, generated artifact, or test responsibility.
7. Start implementation with the first unblocked design. Re-read any directly affected code before editing and confirm the design still matches the codebase.
8. Implement only the design currently in scope. If another design must change, pause and revise the parent plan rather than making a hidden cross-design edit.
9. After each design is implemented, update the parent plan with changed files, verification results, blockers, and any design deviation.
10. Continue sequentially until every design is implemented, intentionally revised, or explicitly blocked.
11. Run final verification across the integrated result and inspect any shared contracts touched by multiple designs.
12. Report completed designs, changed files, verification evidence, deviations from the designs, and unresolved blockers.

## Rules

- Do not edit before every required subtask has a design document.
- Do not let design documents become vague essays; each one must resolve concrete files, contracts, edge cases, and verification.
- Do not implement a design if it would cross another subtask's ownership area; revise the decomposition first.
- Do not silently drift from a design document. Record any deviation and why it was required by the codebase.
- Do not build behavior outside the original task just because a design made it seem convenient.
- Do not continue implementation when a design dependency is missing; reorder or revise the plan first.
