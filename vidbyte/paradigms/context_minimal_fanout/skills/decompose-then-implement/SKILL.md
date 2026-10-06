---
name: decompose-then-implement
description: Gather focused context, decompose the original task into persisted subtasks, then solve each subtask sequentially.
---

# Decompose Then Implement

## Goal

Use this skill to keep one agent effective on a broad implementation task without letting the work dissolve into an untracked mental checklist. The agent first understands the request, then converts it into a written sequence of concrete subtasks before any edit happens. The written plan becomes the working memory for the task, so the agent can return to it after each code change and verify that progress still matches the original goal. Each subtask should have a clear output, likely ownership area, and verification expectation. The agent implements subtasks in order instead of opportunistically jumping between unrelated files. This sequence reduces context drift, makes blockers visible early, and gives the final report a direct line back to the user's request.

## Description

This skill is for work that is too large for a single direct edit but still belongs with one implementation agent. The agent gathers only the context needed to make a reliable decomposition, avoiding broad repo reads that consume context without improving the plan. It then writes a durable plan with checkboxes, expected outputs, ownership notes, and verification notes. The plan should be specific enough that another agent could understand what remains without reading the whole conversation. During implementation, the agent treats one unchecked item as the current scope and avoids mixing unrelated subtasks. After each step, it updates the plan with what changed, what was verified, and what remains uncertain. The final response reports progress against the written plan instead of giving a loose summary.

## Algorithm

1. Restate the user's request in concrete terms. Preserve hard requirements, requested commands, stated non-goals, and any constraints about files, frameworks, style, or delivery.
2. Gather targeted context before planning. Search for existing symbols, nearby tests, configuration, public contracts, and local conventions that determine how the work should be split.
3. Identify the smallest useful subtasks. Each subtask must name the expected output, likely files or contracts, relevant dependencies, and the verification that would prove it is complete.
4. Persist the subtask plan before editing. Put it in the repository's existing planning location when one exists; otherwise choose a clear temporary plan location and keep the path stable for the whole task.
5. Use a checklist structure that includes:
   - Goal and constraints.
   - Ordered subtasks with stable identifiers.
   - Expected output for each subtask.
   - Files, contracts, or docs likely touched by each subtask.
   - Verification commands or inspection steps for each subtask.
   - Status notes for completion, blockers, and deviations.
6. Review the plan for vague work items. Replace labels such as "backend", "tests", or "cleanup" with concrete outcomes and ownership areas.
7. Implement only the first unchecked subtask. Read any additional local context needed for that item, make the scoped edit, and avoid opportunistic changes outside the current item.
8. After the subtask is implemented, update the plan with changed files, verification run, results, and any reason the work differed from the plan.
9. Continue sequentially until every required item is complete or explicitly blocked. If a new dependency appears, add it to the plan and place it before work that depends on it.
10. Run the verification that covers the integrated result, not only the most recent subtask.
11. Finish by reporting completed subtasks, files changed, commands run, failed or skipped checks, and remaining blockers.

## Rules

- Do not edit before the written subtask plan exists.
- Do not split into vague subtasks; name concrete files, contracts, or user-visible outcomes.
- Do not keep the plan only in chat. Persist it in the repository or another user-approved working directory.
- Do not mark a subtask complete until its implementation and relevant verification notes are recorded.
- Do not let later subtasks silently change decisions made by earlier subtasks; update the plan when the sequence changes.
- If the task turns out to require parallel work, stop and switch to a fanout skill instead of pretending the sequential plan is enough.
