# Jev compute move: fan out the same work across helpers

## What and why

The compute checkpoint recognizes EACH_OF_SEVERAL when the main agent plans the same work on each of several items, such as auditing every file in a folder. Done in the main loop, that work is serial, and every item's reads and findings pile into one context. This change adds the fan-out move: each pending item goes to its own helper agent, the helpers run in parallel, and the main agent receives every item's report and combines them.

## How it works

1. **The subtasks are already verified.** The run brief records the group, its pending items, and the agent's own quoted plan, and Jev's EACH_OF_SEVERAL signs confirmed that the plan applies the same, substantial, requested work to each item. So no model writes the subtasks: code builds each helper's prompt (`jev_compute/fan_out_prompt`) from the request, the verified brief, the quoted plan, the group, and that helper's one item. This drops the separate subtask writer and shape questions considered earlier.
2. **Always parallel.** EACH_OF_SEVERAL is only recognized when its "each item stands on its own" sign clears the veto, so a plan whose items depend on each other never reaches this move. Helpers run concurrently, at most `JevComputeSettings.max_parallel_helpers` (default 4) at once.
3. **The subject** (`JevComputeFanOut.subject`): every pending item of the busiest group (the same lookup the recognition state used, `JevComputeStates.busiest_group`) that has not already been handed out in this run, or None when fewer than two remain. The brief marks an item done only after the main agent's responses say so, so the same group can be recognized again in the meantime. The handed-out set keeps a second fan-out from redoing an item, and it is recorded as `NO_WORK`.
4. **Budget** (`JevComputeController._fan_out`):
   - the plan is cut to the helpers the run has left (`JevComputeBudget.available_helpers`);
   - a cut below two items is `HELPER_LIMIT`;
   - the move-limit and cooldown checks then apply;
   - the move is charged for every helper it starts.
5. **Bringing results back.** One user message (`jev_compute/fan_out_result`) carries every item's report, each clipped to an even share of `JEV_COMPUTE_FAN_OUT_REPORTS_MAX_CHARS`. A failed helper's item is marked as still the main agent's to do, and items beyond the budget are listed as still the main agent's. The main agent combines the results itself; it is the reducer. Each successful helper's run is recorded as done-check evidence after the main work that preceded it.
6. **Reporting.** The move is completed when at least one helper reported, and failed (charged, with nothing appended) when none did. Its output is the message the main agent read, and its usage is every helper's usage combined without repricing (`JevComputeHelpers.combined_usage`).

The controller's act step is now uniform: each move's method checks the budget, runs the move, and calls one shared `_report` that appends the message and records the evidence. The reset move's "no stuck problem" case is now `NO_WORK` instead of `FAILED`.

## Files

- `vidbyte/agents/jev/compute/fan_out.py` (`JevComputeFanOut`), the fan-out step and shared `_report` in `controller.py`, `available_helpers` in `budget.py`, `combined_usage` in `helpers.py`, and `busiest_group` and `plan` in `states.py`.
- `vidbyte/agents/jev/settings.py`: `max_parallel_helpers`.
- `vidbyte/lib/`: `JevComputeMoveStatus.NO_WORK`; `JevComputeFanOutPlan` and `JevComputeFanOutReport`; fan-out constants.
- `vidbyte/prompts/prompts/jev_compute/`: `fan_out_prompt.md` and `fan_out_result.md`, with their `Prompt` keys and the prompts README.
- Docs: Jev README, jev-agent skill, AGENTS.md JEV table.
- `tests/test_jev_compute_fan_out.py`.

## Risks

- Parallel helpers share the environment. Items are independent by recognition, and each helper is told to touch only its own item and to report any shared change it had to make. Two helpers that both need the same shared file could still collide; isolated workspaces are the complete answer and are out of scope here.
- A fan-out is the most expensive move: up to `max_helpers` full agent runs. The budget caps it per run, and the parallelism bound caps it at any moment.

## Verification

`tests/test_jev_compute_fan_out.py`:
- the subject: the busiest group's pending items, items already handed out excluded, and the plan cut;
- bounded parallelism (peak concurrency equals the setting), each helper's prompt and evidence source, and handed-out tracking;
- the message: reports, failed items, and items left;
- combined usage;
- end to end:
  - every item goes to a helper and every report reaches the main model's next call;
  - items beyond the budget stay with the main agent;
  - a budget too small to split starts no helper;
  - all helpers failing is charged and adds nothing;
  - a second recognition of the same items finds no work.

Then `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH` and every file tracked.
