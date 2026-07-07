---
name: decompose-then-implement
description: Gather focused context, decompose the original task into persisted subtasks, then solve each subtask sequentially.
---

# Decompose Then Implement

## Goal

Reduce context drift on a broad coding task by turning the original request into
a written subtask list before editing, then implementing that list in order with
progress checked off as work completes.

## Description

Use this skill when one implementation agent can do the work, but the task is
large enough that the agent should answer the planning problem early and keep a
durable checklist outside the chat. The skill is an operating instruction for an
external harness. It is not the canonical Python implementation of the Vidbyte
context-minimal fanout paradigm.

## Use Cases

- A single feature spans several files but does not need parallel subagents.
- A bug fix needs repo context first, then multiple small repairs.
- A refactor needs a saved checklist so later verification can reconcile what
  changed against what was planned.
- A documentation update has several independent pages but one agent should own
  the whole change.

## Algorithm

1. Restate the original user task in one or two sentences, preserving hard
   requirements, non-goals, and requested verification.
2. Gather only the repo context needed to understand the task. Prefer targeted
   file search, symbol search, and short reads over broad file dumps.
3. Identify the smallest useful subtasks. Each subtask must have a clear output,
   likely files or contracts, and verification commands when relevant.
4. Persist the subtask list to a Markdown file before editing. Use a path that
   matches the repo convention, such as `docs/plans/<task-name>.md`, `.tasks/`,
   or another existing planning folder.
5. Use this Markdown structure:

   ```markdown
   # <Task Name> Subtask Plan

   ## Goal
   ...

   ## Constraints
   - ...

   ## Subtasks
   - [ ] <id>: <title>
     Expected output: ...
     Files or contracts: ...
     Verification: ...
   ```

6. Implement the first unchecked subtask. Keep context focused on the files and
   contracts named by that subtask.
7. After each subtask, update the Markdown checklist with completion status,
   changed files, verification run, and any blocker or scope change.
8. Continue sequentially until every required subtask is complete or blocked.
9. Run the verification commands that cover the completed work.
10. Finish with a concise report that names completed subtasks, files changed,
    commands run, and remaining blockers.

## Rules

- Do not edit before the Markdown subtask plan exists.
- Do not split into vague subtasks such as "backend" or "tests"; name concrete
  files, contracts, or user-visible outcomes.
- Do not keep the plan only in chat. Persist it in the repository or another
  user-approved working directory.
- Do not mark a subtask complete until its implementation and relevant
  verification notes are recorded.
- If the task turns out to require parallel work, stop and switch to a fanout
  skill instead of pretending the sequential plan is enough.
