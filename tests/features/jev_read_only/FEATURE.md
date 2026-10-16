# Feature: Jev read-only intent

## High-Level Feature Description

JevAgent can opt in to recognizing a request that asks for an assessment (an explanation, a diagnosis, an opinion, a recommendation, a plan, a review, or a report) rather than a change. Eight fixed Jev questions each check one piece of evidence: an assessment is asked for, it is the only result, the work leaves everything as it is, every action is only described, every change decision stays with the user, the result goes in the reply, the work needs only reading, and an answer alone meets the stated goal. When every answer reaches the threshold, the run keeps only SAFE and READ tools: the main agent is offered no tool above READ, and a `PermissionCeiling` scope makes every permission check in the run, and in every agent it starts, refuse WRITE and EXECUTE. The agent still answers in full.

## Contract

- Runtime opt-in is `JevPreflightPreset.READ_ONLY`. Its eight questions are batched with any other fixed gate questions and any specialist question in one Jev call, and every one must reach `JEV_READ_ONLY_THRESHOLD` (0.75) on its own: the threshold is both the preset's mean threshold and its per-question veto.
- A missing answer, a non-noul answer, or a transient Jev outage marks the preset unavailable and leaves the run exactly as configured. Managed credential and access denials propagate, as for every preset.
- When the preset passes, `JevRuntime` opens `JevReadOnly.ceiling(True)` right after the gate and keeps it open through specialist delegation, skill preload, run-state writing, tool narrowing, the tool selector, the bulk-work offer, the inherited loop, and `JevResponse.finished`.
- The main agent's user tools are narrowed to SAFE and READ before the tool selector runs, so the selector is asked only about tools the run can use; internal tools such as `isDone` and `run_bulk_work` are SAFE and stay.
- `PermissionPolicy.check` returns DENY for any permission outside the active ceiling, whatever the policy allows, and both `AgentRuntime` and `ToolExecutor` add `; this run allows only read, safe tools` to the denial message.
- `JevAgent.response.read_only` is True only for a run the preset limited; `JevResponse.start` resets it to False.
- `PermissionCeiling` is public through `vidbyte.tools.security`, so any caller can run any agent read-only with `with PermissionCeiling.scope(PermissionCeiling.READ_ONLY): ...`.

## Invariants

- A ceiling only narrows: a nested scope is the intersection with the active one, and it never grants what a policy withholds.
- The ceiling is a ContextVar, so asyncio tasks created inside the scope inherit it and sibling runs never see it.
- Narrowing touches only the run-local runtime's catalog; the agent's own catalog and its next run are unchanged.
- The runtime reads only the gate's `read_only_requested` flag and names no preset.

## Known Failure Modes

- A preset-wide mean hides one clear no, so a "fix it" request becomes read-only and cannot do its work.
- A prior read-only verdict survives an unavailable answer on the same gate.
- The ceiling opens after specialist delegation, so a specialist with its own allow-all policy writes in a read-only run.
- Bulk-work agents, clones, swarm helpers, or forks get the full catalog or a policy that escapes the ceiling.
- A tool the agent gains mid-run is offered and executed because only the catalog was filtered.
- The narrowed catalog leaks into the next run, or the ceiling stays active after a run raises.
- The tool selector is asked, and billed, about tools the run will discard.

## Test Suite Map

- `tests/features/jev_read_only/test_jev_read_only.py` covers the ceiling (absence, denial, restore after an exception, nesting, validation, task inheritance and isolation, `PermissionPolicy` and `ToolExecutor` capping, narrower policies), the eight questions (registration, layout, standalone literals, length, signal mapping), the gate (threshold, per-question veto, missing answers, outages, reset, opt-in absence, the shared request with BULK_WORK), `JevReadOnly`, and the runtime (offered tools, a dropped provider tools override, hidden tools, tools added mid-run and their DENIED record, vetoed requests, the next run, specialists, bulk-work agents, the tool selector, a raising run, and the response record).
- Run `python scripts/test-jev-read-only.py` for the complete offline feature pack.

## Omitted Testing Strategies

- Live TypeSafe and model-provider calls are omitted; deterministic transports and runners keep the suite offline.
- Whether Jev's answers separate questions from change requests well enough at 0.75 is a calibration question for a labeled eval set, not a unit test.
- Threads started without `contextvars.copy_context()` do not inherit the ceiling; no SDK run path starts one, so no test simulates it.
