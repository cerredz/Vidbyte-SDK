---
name: decompose-design-fanout
description: Gather context, decompose into subtasks, write per-subtask design docs, then launch one subagent per design doc and merge their results.
---

# Decompose, Design, Fanout

## Goal

Use fresh context windows for parallel implementation by solving each subtask in
a design doc first, then spawning one subagent per design doc and merging the
results after all subagents finish.

## Description

This is the design-first version of context-minimal fanout. The parent agent
does the architectural thinking and writes the design docs. Subagents receive
self-contained design docs with strict ownership boundaries, so they can work in
parallel without rediscovering the full repo or editing each other's files. For
platform-specific spawn examples, use `references/harness-commands.md`.

## Use Cases

- A broad feature can be split into independent workstreams after design.
- Several implementation branches require fresh context windows but must follow
  a shared architectural decision.
- The parent agent should keep merge authority while subagents perform isolated
  edits.
- Multiple harnesses may be used, so spawn commands need to be explicit and
  easy to update in one shared reference.

## Algorithm

1. Restate the original task and identify hard requirements, non-goals, and
   verification expectations.
2. Gather targeted repository context needed to understand public contracts,
   mutable ownership areas, tests, docs, and configuration.
3. Decompose the task into non-overlapping implementation branches. Each branch
   must have distinct owned paths, owned contracts, tests, migrations, generated
   artifacts, and verification responsibilities.
4. Write a parent Markdown split plan before spawning subagents:

   ```markdown
   # Context Minimal Fanout Design Plan

   ## Goal
   ...

   ## Global Instructions
   ...

   ## Non-Overlap Requirements
   - ...

   ## Design Docs
   - [ ] <id>: <path-to-design-doc>
   ```

5. Write one design doc per branch. Each design doc must include the branch goal,
   owned paths, read-only paths, proposed change, edge cases, verification, and
   a reminder not to cross another branch's ownership boundary.
6. Check the full set of design docs for overlap. If two design docs need the
   same mutable file, public contract, test file, migration, generated artifact,
   or verification responsibility, merge them before fanout.
7. Read `references/harness-commands.md` and choose the command form for the
   current coding harness. If the current platform is not listed, use that
   reference's discovery procedure before spawning.
8. Launch one subagent per design doc from the current repository state. Give
   each subagent the original goal, global instructions, its design doc, owned
   paths, read-only paths, verification commands, and the non-overlap rules.
9. Run subagents in parallel only when their ownership boundaries are clean. The
   parent must wait for every subagent process, background task, or harness
   task to finish before merging.
10. Collect every subagent report. Reconcile changed files, verification, merge
    conflicts, skipped checks, and blockers.
11. Run integration verification from the parent context.
12. Report final status with each design doc, subagent result, files changed,
    verification, conflicts, and follow-ups.

## Rules

- Do not spawn subagents before the parent split plan and all design docs exist.
- Do not inline platform command details here; keep them in
  `references/harness-commands.md`.
- Do not assign the same mutable file, contract, test, migration, generated
  artifact, or verification responsibility to multiple subagents.
- Do not let a subagent edit outside its owned paths. A blocked subagent should
  report the dependency instead.
- Do not merge results until every subagent has completed, failed, or reported a
  blocker.
- Do not treat this skill as the SDK implementation of the paradigm. It is an
  external harness adapter and operating instruction.
