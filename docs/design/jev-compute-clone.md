# Jev dynamic compute: CLONE

## What and why

`CLONE` is a fourth dynamic-compute option and the first one that launches work. When Jev recognizes it, the checkpoint runs a few identical copies of the main agent on the remaining work from the same verified starting point, then hands their results back to the main agent, which keeps the best one and continues.

It differs from the existing options by what it bets on. `FORK_AGENT` compares *different* approaches; `CLONE` repeats the *same* approach and bets on variance between attempts (repeated sampling: coverage grows with the number of independent attempts). `FRESH_AGENT` replaces one context; `CLONE` keeps the main context and adds attempts beside it.

## How it works

1. **Option and questions.** `JevDynamicComputeOption.CLONE` (last in enum order, so it loses ties) with twelve `CLONE_*` question keys and twelve `JevComputeQuestion` instances in `vidbyte/lib/jev/compute/situations.py`, registered in `JevComputeRegistry`. Recognition, scoring, and the threshold are unchanged. The questions follow `skills/asking-jev-dynamic-compute-questions/SKILL.md`; each tests one signal that independent repeats of the same approach would help:
   - an outcome that varies between tries of the same method;
   - a failure that looks incidental rather than systematic;
   - a settled approach (no competing hypotheses);
   - a checkable result, so the main agent can tell attempts apart;
   - remaining work that can be restated from the request and brief;
   - attempts that can run without colliding writes;
   - attempts that do not need each other's intermediate results;
   - a bounded remaining unit, so attempts finish;
   - no needed user decision before the next attempt;
   - attempts whose outputs can be compared side by side;
   - a cost of one more attempt that is small relative to the work;
   - a remaining goal that still depends on the varying step.
2. **Setting.** `JevComputeSettings.clones: int = 2` (copies per launch), validated to `1..4`. `CLONE` is opt-in: the `dynamic_compute` default stays `FRESH_AGENT`, `FORK_AGENT`, `SUBAGENT`, because those remain observe-only while `CLONE` spends real compute.
3. **The technique.** `JevCloneAgent(BaseAgent)` in `vidbyte/agents/jev/compute/clone.py` is built from the main agent's `JevAgentSettings` (same model, tools, permission policy, loop settings) with an empty history. Its `attempt` classmethod runs `clones` copies concurrently on one prompt (original request + rendered verified brief) and returns the non-empty replies. A clone that raises `VidbyteSdkError` is dropped; the others still count. Because clones reply through `BaseAgent.generate_reply`, their usage reaches the run's usage ledger with no new accounting code.
4. **Wiring.** `JevComputeController.checkpoint(state, messages)` (it now receives the loop's messages from `JevRuntime._after_tool_iteration`). When the decision selects `CLONE`, it launches the clones at most once per run, records the result on `JevAgent.response.clone`, and appends one user message listing the attempts. The main loop then continues normally.
5. **Prompts.** New family `vidbyte/prompts/prompts/jev_clone/` with `clone_prompt.md` (what each clone receives) and `results_prompt.md` (what the main agent receives).

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/enums/prompts.py`: option, question keys, prompt keys.
- `vidbyte/lib/constants/jev.py`: default and maximum clone count.
- `vidbyte/lib/dataclasses/jev.py`: `JevCloneResult` and `JevAgentResponse.clone`.
- `vidbyte/lib/jev/compute/situations.py`, `compute.py`: twelve questions and registry entry.
- `vidbyte/agents/jev/settings.py`: `JevComputeSettings.clones`.
- `vidbyte/agents/jev/compute/clone.py` (new), `controller.py`, `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/response.py`.
- `vidbyte/prompts/prompts/jev_clone/` (new) and `vidbyte/prompts/README.md`.
- Tests: `tests/test_jev_compute_situations.py`, `tests/test_jev_compute_clone.py` (new).
- Docs: Jev README, compute README, dynamic-compute skill, AGENTS.md option list.

## Risks and open questions

- **Shared side effects.** Clones use the same tools as the main agent, so a clone with write tools can touch the same files. The isolated-writes question lowers the score in that case, but nothing enforces isolation. A sandboxed workspace per clone is out of scope.
- **Cost.** Each launch costs up to `clones` extra runs; the once-per-run cap and opt-in default bound it.
- **Selection.** The main agent picks among attempts by reading them; there is no separate verifier. That keeps the PR small and leaves verifier-based selection as later work.

## Verification

- Question tests: twelve questions for `CLONE`, the same shape checks as the other options, 48 total questions.
- Settings tests: default count, bounds, opt-in default options.
- Clone tests with scripted runners: a `CLONE` decision runs N clones once per run, appends one results message, records `response.clone`; a failing clone is dropped; a non-`CLONE` decision launches nothing.
- `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH`.
