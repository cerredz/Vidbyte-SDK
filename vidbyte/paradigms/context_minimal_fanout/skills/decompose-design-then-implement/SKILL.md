---
name: decompose-design-then-implement
description: Gather context, decompose into subtasks, write per-subtask design docs that solve the work up front, then implement each design sequentially.
---

# Decompose, Design, Then Implement

## Goal

Move the hard reasoning for a broad task to the beginning of the context window
by decomposing the task, writing a solution design for each subtask, and then
implementing those designs one by one.

## Description

Use this skill when the task is too coupled or too important to proceed from a
plain checklist. Each subtask gets a short design doc that states the intended
change, affected contracts, edge cases, verification, and rejected alternatives
before any implementation starts. The skill is an operating instruction for an
external harness, not the canonical SDK implementation of a paradigm.

## Use Cases

- A feature has several interacting code paths and needs design decisions before
  edits begin.
- A migration must be broken into ordered changes with explicit compatibility
  reasoning.
- A task is risky enough that later implementation agents should be able to read
  the design and execute without rediscovering the architecture.
- A user asks for design docs as part of implementation.

## Algorithm

1. Restate the original task, including requirements, non-goals, and verification
   expectations.
2. Gather enough targeted repo context to understand ownership boundaries,
   public APIs, tests, configuration, and user-visible behavior.
3. Decompose the task into subtasks that can be solved independently or in a
   clear sequence.
4. Create a parent Markdown plan that lists every subtask and links to its
   design doc.
5. Write one design doc per subtask before editing. Use this structure:

   ```markdown
   # <Subtask Title>

   ## Goal
   ...

   ## Current Behavior
   ...

   ## Proposed Change
   ...

   ## Files And Contracts
   ...

   ## Edge Cases
   ...

   ## Verification
   ...

   ## Rejected Alternatives
   ...
   ```

6. Review the design docs as a set. Merge subtasks that need to own the same
   mutable file, public contract, migration, test responsibility, or generated
   artifact.
7. Implement the first design doc. Treat the design as the local source of truth
   unless it conflicts with the original prompt or newly discovered repo facts.
8. After each implementation, update the parent plan with status, changed files,
   verification, and any design deviation.
9. Continue sequentially until every required design doc is implemented or
   explicitly blocked.
10. Run verification that covers the whole change, then report completed designs,
    unresolved blockers, and any deviations from the docs.

## Rules

- Do not edit before every required subtask has a design doc.
- Do not let design docs become vague essays. Each one must resolve concrete
  files, contracts, edge cases, and verification.
- Do not implement a design if it would cross another subtask's ownership area;
  revise the decomposition first.
- Do not silently drift from a design doc. Record any deviation and why it was
  required by the codebase.
- Do not build behavior outside the original task just because a design doc made
  it seem convenient.
