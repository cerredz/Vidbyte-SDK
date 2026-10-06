# Jev compute move: delegate a self-contained step

## What and why

The compute checkpoint recognizes SELF_CONTAINED_STEP when the main agent's next stated step is a real piece of work whose words, with the user's request, state everything it needs, whose result can be handed back, and that the request asks for. Done in the main loop, that step's searching, reading, and tool output all land in the main agent's context, which it then carries for the rest of the run. This change adds the last of the three moves: the step goes to a fresh helper, and the main agent receives only the report.

## How it works

1. **The helper context:** the original request is the helper's prompt; the available JEV run state and verified mid-run brief are added as typed context through `AgentInput` and `ContextManager`. The delegate does not construct a separate next-step prompt.
2. **The helper:** `JevComputeHelpers` builds a fresh linear agent with the main agent's system prompt, model, tools, and permissions. No delegate-specific task instruction is added. The same request, state, and rendered brief are delegated at most once per run, and a failed attempt is still remembered.
3. **Budget and result.** The move needs one helper and goes through the same budget check as the other moves. A completed move appends one message (`jev_compute/delegate_result`) with the clipped report and records the helper's run as done-check evidence after the main work that preceded it. A failed helper is charged and adds nothing to the loop.

With this change every recognized situation has a move: REPEATING resets, EACH_OF_SEVERAL fans out, and SELF_CONTAINED_STEP delegates.

## Files

- `vidbyte/agents/jev/compute/delegate.py` (`JevComputeDelegate`), typed input support in `helpers.py`, and the delegate step in `controller.py`.
- `vidbyte/lib/constants/jev.py`: `JEV_COMPUTE_DELEGATE_SOURCE`.
- `vidbyte/prompts/prompts/jev_compute/delegate_result.md`, with its `Prompt` key and the prompts README.
- Docs: Jev README, jev-agent skill, AGENTS.md JEV table.
- `tests/test_jev_compute_delegate.py`; `tests/test_jev_compute_reset.py` narrows its "no move" case to an unrecognized situation, since every situation now has a move.

## Risks

- A delegated step runs in the same environment as the main agent, which waits at the checkpoint while the helper works, so the two never act at the same time.
- A step the helper misreads costs one helper run. The main agent reads the report and is told to check anything it relies on.

## Verification

`tests/test_jev_compute_delegate.py`:
- the helper gets the original request plus typed run-state and verified-brief context, using the main agent's system prompt;
- an unchanged helper context is delegated once per run, and `begin` resets that;
- the report is clipped and returned without a step placeholder;
- end to end: the report reaches the main model's next call; a failed helper is charged and adds nothing; a second recognition of the same step finds no work; a blocked move starts no helper.

Then `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH` and every file tracked.
