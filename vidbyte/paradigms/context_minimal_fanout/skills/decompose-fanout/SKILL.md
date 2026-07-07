---
name: decompose-fanout
description: Decompose the original prompt into non-overlapping subtasks, launch one subagent per subtask, wait for all subagents, then merge and report.
---

# Decompose Fanout

## Goal

Reduce context load by splitting one broad task into non-overlapping subagent
prompts, running each prompt in a fresh context, and merging the results only
after every branch has finished.

## Description

This is the direct fanout version of the context-minimal paradigm. The parent
agent gathers enough context to split the task, writes a durable split plan, and
launches one subagent per branch without requiring per-branch design docs. For
platform-specific spawn examples, use `references/harness-commands.md`.

## Use Cases

- A broad implementation request has several independent ownership areas.
- Subagents can work in parallel without editing the same files or contracts.
- The parent needs to reduce context pressure by giving each branch a smaller,
  self-contained prompt.
- A design-doc phase would be too heavy for the task, but a written split plan
  is still needed.

## Algorithm

1. Read enough repository context to understand the request before splitting.
2. Identify separable ownership areas: files, public contracts, tests, docs,
   configs, migrations, generated artifacts, and verification responsibilities.
3. Write a Markdown split plan before spawning subagents:

   ```markdown
   # Context Minimal Fanout Split Plan

   ## Goal
   ...

   ## Instructions
   ...

   ## Non-Overlap Requirements
   - ...

   ## Implementation Prompts

   ### <id>: <title>

   #### Prompt
   ...

   #### Owned Paths
   - ...

   #### Read-Only Paths
   - ...

   #### Commands
   - ...

   #### Notes
   - ...
   ```

4. Apply the non-overlap test to every prompt. Two prompts must not both own the
   same file path, public API contract, test file, migration, generated
   artifact, or verification obligation. Shared context belongs under
   read-only paths.
5. Merge prompts that cannot be made independent. Do not force parallelism when
   the work has real coupling.
6. Read `references/harness-commands.md` and choose the command form for the
   current coding harness. If the platform is unknown, follow the discovery
   procedure in that reference.
7. Launch one subagent per implementation prompt. Each subagent prompt must
   include the global goal, global instructions, branch prompt, owned paths,
   read-only paths, commands, and a warning not to cross ownership boundaries.
8. Wait for all subagents to finish. Track exit status, changed files,
   verification, blockers, and conflicts for each branch.
9. Merge subagent results in the parent context. Resolve conflicts only after
   checking which branch owns the affected path or contract.
10. Run parent-level verification that covers the integrated result.
11. Report completed branches, files changed, verification, blockers, conflicts,
    and remaining integration work.

## Rules

- Do not run subagents before writing the Markdown split plan.
- Do not split work before reading enough repo context to understand ownership.
- Do not use vague prompts such as "handle backend" or "fix tests"; specify
  ownership and outputs.
- Do not assign the same mutable file, contract, test, migration, generated
  artifact, or verification responsibility to multiple prompts.
- Do not let subagents modify read-only paths.
- Do not hide conflicts. If a clean split is impossible, report it and merge the
  coupled work into one prompt.
- Do not inline platform command details here; keep them in
  `references/harness-commands.md`.
