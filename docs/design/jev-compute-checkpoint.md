# Jev mid-run compute checkpoint

## What and why

Mid-run dynamic compute lets Jev decide, between the main agent's tool iterations, whether the run gets extra compute. That needs three things: a point in the loop where something can run between iterations, a component that owns what happens there, and the run brief from the previous change so the decisions can see what the agent is working on.

This change adds all three and nothing else. Enabling compute on `JevAgent` now keeps the run brief current and reports it, with exact run facts, on `JevAgent.response`. It does not yet ask Jev anything or change the run: situation recognition and the compute moves are later changes that plug into the same checkpoint.

## How it works

1. `AgentRuntime` gains one protected hook, `_after_tool_iteration(state, messages)`, called once at the end of every iteration that ran tools and did not finish, after the `after_iteration` middleware lets the loop continue and before the next model call. The base implementation does nothing, so every runtime other than `JevRuntime` behaves exactly as before. Tool calls run one at a time, so the loop state the hook receives is complete for that iteration.
2. `JevRuntimeSettings.compute` is a new optional `JevComputeSettings`. `None` (the default) disables the feature: no controller, no brief writer, and no work at the hook. `JevComputeSettings.brief` holds the `JevRunBriefSettings` from the previous change.
3. `JevAgent` builds one `JevComputeController` at construction when compute is enabled and passes it to `JevRuntime`, like the gate and the continuation.
4. `JevRuntime` calls `controller.begin(message)` once the main agent is about to run (after the preflight gate passes and when no specialist took the task) and answers `_after_tool_iteration` by calling `controller.checkpoint(state)`. The runtime holds no compute logic.
5. `JevComputeController.checkpoint` reads the run's facts and refreshes the brief when its cadence says so, through `JevRunBriefKeeper.refresh_if_due`. It reports through `JevResponse`: the latest facts, every refresh attempt, and the current verified brief.
6. `JevAgentResponse` gains `run_facts`, `run_brief`, and `run_brief_updates`.

Specialists and fresh-context continuation agents run their own agents and get no checkpoint. A writer outage never affects the run: the keeper keeps the previous brief and the main loop continues.

## Files

- `vidbyte/agents/runtime.py`: the no-op hook and its call site.
- `vidbyte/agents/jev/settings.py`: `JevComputeSettings` and `JevRuntimeSettings.compute`.
- `vidbyte/agents/jev/compute/`: new package with `JevComputeController`.
- `vidbyte/agents/jev/agent.py`, `runtime.py`, `response.py`: build, call, and report.
- `vidbyte/lib/dataclasses/jev.py`: the three `JevAgentResponse` fields.
- `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`: export `JevComputeSettings` and `JevRunBriefSettings`.
- `vidbyte/agents/jev/README.md`, `skills/jev-agent/SKILL.md`, `AGENTS.md`: document the checkpoint.
- `tests/test_jev_compute.py`.

## Risks

- The hook runs on every tool iteration of every `JevAgent` run with compute enabled. Reading facts is a linear pass over the run's tool calls, and the writer runs only when the brief's cadence says so.
- A base-runtime change: the hook is a no-op by default and is called at one place after the middleware has decided to continue, so it cannot change a run that does not override it. Existing loop tests cover the unchanged behavior.

## Verification

`tests/test_jev_compute.py` drives real `JevAgent` runs with a scripted model: the hook fires once per continuing tool iteration and never on a finishing one; disabled compute builds no writer and reports nothing; enabled compute refreshes the brief on cadence and reports facts, attempts, and the brief; a writer outage leaves the run's answer unchanged; and a chosen specialist gets no checkpoint. Then `python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH`.
