# Jev compute move: delegate a self-contained step

## What and why

The compute checkpoint recognizes SELF_CONTAINED_STEP when the main agent's next stated step is a real piece of work whose words, with the user's request, state everything it needs, whose result can be handed back, and that the request asks for. Done in the main loop, that step's searching, reading, and tool output all land in the main agent's context, which it then carries for the rest of the run. This change adds the last of the three moves: the step goes to a fresh helper, and the main agent receives only the report.

## How it works

1. **The step** (`JevComputeDelegate.subject`): the brief's soonest next step, the same step Jev's questions judged, unless it was already delegated in this run. The brief drops a step only after the main agent's responses show it done, so a step can be recognized again in the meantime. The delegated set keeps a second helper from repeating it, and that attempt is recorded as `NO_WORK`.
2. **The helper sees only the request and the step** (`jev_compute/delegate_prompt`). That is safe because STATES_ALL is part of SELF_CONTAINED_STEP's veto: a step that refers to something found only during the run is never recognized. The step is marked delegated before the helper starts.
3. **Budget and result.** The move needs one helper and goes through the same budget check as the other moves. A completed move appends one message (`jev_compute/delegate_result`) with the clipped report, telling the main agent not to redo the step, and records the helper's run as done-check evidence after the main work that preceded it. A failed helper is charged and adds nothing to the loop.

With this change every recognized situation has a move: REPEATING resets, EACH_OF_SEVERAL fans out, and SELF_CONTAINED_STEP delegates.

## Files

- `vidbyte/agents/jev/compute/delegate.py` (`JevComputeDelegate`) and the delegate step in `controller.py`.
- `vidbyte/lib/constants/jev.py`: `JEV_COMPUTE_DELEGATE_SOURCE`.
- `vidbyte/prompts/prompts/jev_compute/`: `delegate_prompt.md` and `delegate_result.md`, with their `Prompt` keys and the prompts README.
- Docs: Jev README, jev-agent skill, AGENTS.md JEV table.
- `tests/test_jev_compute_delegate.py`; `tests/test_jev_compute_reset.py` narrows its "no move" case to an unrecognized situation, since every situation now has a move.

## Risks

- A delegated step runs in the same environment as the main agent, which waits at the checkpoint while the helper works, so the two never act at the same time.
- A step the helper misreads costs one helper run. The main agent reads the report and is told to check anything it relies on.

## Verification

`tests/test_jev_compute_delegate.py`:
- the helper gets only the request and the soonest step, with no brief, under the delegate evidence source;
- a step is delegated once per run whatever its outcome, and `begin` resets that;
- no stated step gives no subject, and the report is clipped;
- end to end: the report reaches the main model's next call; a failed helper is charged and adds nothing; a second recognition of the same step finds no work; a blocked move starts no helper.

Then `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH` and every file tracked.
