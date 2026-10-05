# Jev compute move: FRESH_AGENT helper

## What it does

When the combined dynamic-compute decision selects `JevDynamicComputeOption.FRESH_AGENT`, the checkpoint may start one independent helper agent. The option covers several observable signs, including a persistent failure, repeated actions without new information, and loss of continuity. It is broader than the old REPEATING situation, so the helper receives the verified run state rather than claims about a structured list of failed approaches or open errors.

The helper runs from a clean history, reviews the user's request and current run evidence, makes useful progress with its own tools, and returns a report for the main agent to consider.

## How it works

1. **Recognize an option.** `JevComputeRecognizer` sends one decision request over the shared `{request, brief, facts, recent}` state after the keeper verifies a brief refresh. The controller acts only when `decision.option` is `FRESH_AGENT`.
2. **Check the run-local budget.** `JevComputeBudget` enforces `max_moves`, `max_helpers`, and `cooldown_iterations`. Blocked attempts are recorded with the limit that stopped them. A move is charged once its helper starts, whether it returns a report or fails.
3. **Start the helper.** `JevComputeHelpers` builds a separate linear `BaseAgent` with the main agent's system prompt, model, key, tools, permissions, and configured helper iteration and token limits. Agent-bound tools are cloned. Helpers do not receive the Jev runtime or start more helpers.
4. **Provide current evidence.** `JevComputeReset` uses `JevComputeStates.build` to give the helper the clipped request, `brief.render()`, exact `JevRunFacts`, and the bounded recent numbered event lines. The prompt asks the helper to ground claims about prior work in this evidence; it does not invent approach records or open errors.
5. **Bring back the report.** A successful report is clipped and appended as one user message for the main agent's next model call. When done checks are enabled, `JevRunState.add_helper_evidence` first captures the main work up to the helper, then appends the helper's responses and tool calls in event order.
6. **Report the move.** `JevAgent.response.compute_moves` records its `FRESH_AGENT` option, iteration, status, helper count, output when completed, and usage. Decisions remain in `compute_decisions`.

Other selected options are recognized and recorded but have no move yet. A writer or decision outage, rejected brief update, blocked move, or failed helper adds no helper report to the main loop.

## Files

- `vidbyte/agents/jev/compute/`: budget, helper runner, state mapping, reset move, and controller dispatch.
- `vidbyte/agents/jev/runtime.py`: passes the live message list to the checkpoint.
- `vidbyte/agents/jev/agent.py`: passes the run state to the controller.
- `vidbyte/agents/jev/done/run_state.py`: adds helper evidence in run order.
- `vidbyte/agents/jev/settings.py`: budget and helper limits.
- `vidbyte/agents/jev/response.py` and `vidbyte/lib/dataclasses/jev.py`: move reporting records.
- `vidbyte/lib/enums/jev.py` and `vidbyte/lib/constants/jev.py`: move status and defaults.
- `vidbyte/prompts/prompts/jev_compute/`: helper instructions and the report returned to the main agent.
- `tests/test_jev_compute_reset.py`.

## Verification

`tests/test_jev_compute_reset.py` covers budget limits, helper construction and evidence extraction, the exact shared state in the helper prompt, report clipping, run-ordered done evidence, FRESH_AGENT dispatch, failed and blocked helpers, and recognized options without a move. `tests/test_jev_compute.py` and `tests/test_jev_compute_situations.py` cover the preserved checkpoint and recognition behavior.
