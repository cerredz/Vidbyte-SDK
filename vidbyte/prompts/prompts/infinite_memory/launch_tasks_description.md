## Purpose

The batch of tasks to run in this call. Each task is carried out by its own pair: a fresh generator that does the work and a fresh verifier that checks and fixes it.

## How to write it

Put only independent pieces of work in the same call, because all its pairs run at the same time and none can see what a sibling is producing. Give each task clear boundaries and its own output location, so sibling pairs neither duplicate nor overwrite each other's work. Write every task for agents that cannot see this conversation, and size the batch to the work: a narrow task needs one pair, while a broad one may need several slices of comparable size.

## Rules

Every task needs a name that no other task in this call uses. The call returns one short result card per task, in the order given, after every pair has finished. The system limits how many tasks one call may carry; a batch over the limit is refused with a reason that names it, and nothing starts.
