# Jev compute move: reset a stuck problem with a fresh helper

## What and why

The compute checkpoint recognizes REPEATING when the main agent keeps retrying an approach that already failed on a problem it has not solved. An agent in that state is anchored on its own failed attempts: its context is full of them, and more turns in the same context tend to produce more of the same. This change adds the first compute move, and the shared machinery every later move uses.

When Jev recognizes REPEATING, a fresh helper agent takes the stuck problem. It starts with a clean history, is told exactly which approaches failed and which errors are open, finds the cause, fixes it, and reports. The main agent reads that report and continues.

## How it works

1. **Act on a recognized situation** (`JevComputeController._act`). After recognition, the first passing situation is acted on through one `match` case per situation. EACH_OF_SEVERAL and SELF_CONTAINED_STEP have no move yet, so they are recognized and recorded but not acted on.
2. **Budget** (`JevComputeBudget`, run-local). Before any helper starts, the move is checked against:
   - `max_moves` (default 3; `0` keeps recognition and never acts);
   - `max_helpers` (default 8);
   - `cooldown_iterations` since the last move (default 5).

   A blocked move is recorded with the limit that stopped it. A move is charged once its helper starts, whether or not the helper succeeds.
3. **Helpers** (`JevComputeHelpers`). A helper is a new `BaseAgent` on the linear runtime with the main agent's system prompt, model, key, tools, and permissions, its own `helper_max_iterations` and `helper_max_tokens`, and an empty history.
   - It is not a fork: forking a JevAgent keeps the jev runtime, which refuses to build without its gate, and shares the main agent's context manager.
   - Tools that bind to an agent are cloned (`clone_for_fork`), as `AgentForker` does.
   - Helpers have no compute checkpoint, so a helper never starts helpers.
   - An SDK failure or an empty report returns None.
4. **The reset move** (`JevComputeReset`). It takes the same stuck problem Jev's REPEATING questions judged (`JevComputeStates.stuck_problem`). It renders the `jev_compute/reset_prompt` asset with the request, the problem, every tried approach with its outcome and quoted evidence, and the open errors, and runs one helper.
5. **Bringing the result back.** The checkpoint appends one user message, rendered from `jev_compute/reset_result` with the helper's clipped report, to the main loop's messages, so the main agent reads it on its next model call. When done checks are enabled, `JevRunState.add_helper_evidence` first captures the main-loop work that preceded the helper and then appends the helper's run as an evidence segment. Done checks therefore count the helper's work as evidence, in run order.
6. **Reporting.** Every attempt is a `JevComputeMove` on `JevAgent.response.compute_moves`: completed with its report and the helper's usage, failed, or blocked by a limit.

Only a completed move changes the run. Outages, rejected refreshes, unrecognized situations, blocked moves, and failed helpers leave the main agent's messages, tools, and answer as they would be without compute.

## Files

- `vidbyte/agents/jev/compute/`: `budget.py`, `helpers.py`, `reset.py`, and the act step in `controller.py`; `states.py` exposes `stuck_problem` and `quote` for the move.
- `vidbyte/agents/jev/runtime.py`: the hook passes the loop's messages to the checkpoint.
- `vidbyte/agents/jev/agent.py`: builds the controller after the run state and passes it in.
- `vidbyte/agents/jev/done/run_state.py`: `add_helper_evidence`.
- `vidbyte/agents/jev/settings.py`: `max_moves`, `max_helpers`, `cooldown_iterations`, `helper_max_iterations`, `helper_max_tokens`.
- `vidbyte/agents/jev/response.py`: `compute_move`.
- `vidbyte/lib/`: `JevComputeMoveStatus`; `JevComputeHelperResult`, `JevComputeMove`, and `JevAgentResponse.compute_moves`; budget and helper constants.
- `vidbyte/prompts/prompts/jev_compute/` plus `Prompt` keys and the prompts README.
- Docs: Jev README, jev-agent skill, AGENTS.md JEV table.
- `tests/test_jev_compute_reset.py`.

## Risks

- A helper works in the same environment as the main agent and can change files. The reset helper works alone, while the main agent waits at the checkpoint, so the two never edit at the same time.
- A helper is a full agent run and the most expensive thing compute does. The budget caps how many run, and the cooldown keeps one long stuck stretch from setting off a move at every brief refresh.
- The existing fresh-continuation agent factory shares tool instances uncloned. That is unchanged here and worth its own fix.

## Verification

`tests/test_jev_compute_reset.py`:
- the budget's limits, order, and reset, plus settings validation;
- a helper is a separate linear agent with the main model, tools (cloned when bound), and limits;
- helper evidence extraction and the outage and empty-report paths;
- the reset prompt's content, and no helper without a stuck problem;
- the clipped result message;
- helper evidence following the main work that preceded it;
- end to end:
  - a recognized repeat runs one helper, and its report appears in the main model's next call and not before;
  - a failed helper is charged and adds nothing to the loop;
  - a blocked move starts no helper;
  - an unrecognized situation, or one without a move, starts no helper.

Then `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH` and every file tracked.
