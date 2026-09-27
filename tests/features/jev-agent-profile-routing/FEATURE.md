# Feature: Jev Agent Profile Routing

## High-Level Feature Description

The `Jev` SDK coordinator lets application developers describe multiple configured `JevAgent` profiles and chooses the profile that best fits the current request. It uses one TypeSafe Choice call only when two or more profiles exist, applies the winner's supported settings to the main Jev run, and restores Jev configuration after success, error, or cancellation. A regression could execute the wrong provider, prompt, tools, or permissions, leak one profile's settings into a later request, or route work before clarity preflight has stopped an unclear request.

## Contract

- `JevAgentSettings` owns only a non-empty, immutable, unique-title profile array.
- Each `JevAgent` provides title, description, JSON metadata, and a linear `BaseAgent` template.
- One profile makes no routing call. Multiple profiles make one Choice call using the current request and all three profile fields.
- Code chooses the highest probability; exact ties use catalog order. There is no threshold/no-match fallback.
- Preflight runs first; a closed gate makes no profile or generative call.
- The selected profile's supported execution settings apply only during that main Jev run and are restored even after failure/cancellation.
- Routing, its full probability ranking, and TypeSafe usage are observable through `Jev.response.selection`; the main usage tracker counts the TypeSafe call once.
- A routing decision failure and a selected-agent execution failure are surfaced; neither silently runs another profile.

## Actors / Callers

- An SDK application constructs `JevAgent` profiles and passes them to `JevAgentSettings`.
- `Jev.generate_reply()` / `Jev.arun()` runs the preflight, router, and selected profile loop.
- TypeSafe Jev supplies profile probabilities; the selected BaseAgent template supplies the generative model and execution settings.
- `Jev.response` provides per-run selection and preflight outcomes.

## Inputs and Preconditions

- At least one profile exists; titles are unique; title/description are trimmed; metadata is JSON-compatible.
- Profile BaseAgents use the supported linear runtime and expose the normal BaseAgent fork/run surface.
- The current request is a non-blank string; a multi-profile route requires valid TypeSafe credentials and response data.
- Preflight/tool-selection behavior is configured separately in `JevRuntimeSettings`.
- Metadata is routing input sent to TypeSafe and must not contain secrets.

## Observable Outcomes

- One-profile run returns the profile model's normal AgentMessage and makes no TypeSafe route call.
- Multi-profile run returns the selected model's normal AgentMessage and records selection title, probability, and ranking.
- Preflight stop returns its structured clarification and no routing selection.
- Provider, model, tool, schema, or cancellation failures remain visible to the caller; Jev's original profile settings are restored.

## State Transitions

1. Start response for current request.
2. Run preflight. Closed: finish with clarification. Passed: continue.
3. Select sole profile or call TypeSafe and choose the highest probability.
4. Snapshot Jev's execution configuration, apply selected profile, and run the ordinary loop.
5. Close profile-owned MCP handles and restore the snapshot in `finally`.

Only one run at a time may mutate a Jev coordinator; a per-instance `asyncio.Semaphore(1)` serializes same-instance calls. Separate Jev objects have independent run state.

## Invariants

- Profile order is stable and is the tie-break for equal probability.
- The TypeSafe request contains the current prompt and the explicit profile fields only; no API keys or candidate model configuration are included.
- BaseAgent's existing execution, tool, trace, usage, and session logic remains the execution mechanism.
- Profile history, session, trackers, and live MCP handles are not shared with the coordinator.
- Every temporary main-agent setting is restored after success, exception, and cancellation.
- Selection results live on `Jev.response`, not in AgentResult metadata.

## External Dependencies

- TypeSafe System One DecisionModelRunner is the external decision boundary; tests replace it with scripted responses.
- Generative model runners are mocked with deterministic offline runners.
- Packaged Markdown prompt resources are loaded via `importlib.resources` and checked in package CI.
- Existing `BaseAgent`, `AgentForkSettings`, tools catalog, middleware, MCP, context, and runtime facilities provide profile configuration.

## Known Failure Modes

- Incomplete or malformed Choice distributions could select an arbitrary or missing profile.
- Trusting `answer.choice` instead of the actual highest probability could silently select a lower-ranked profile.
- Reusing a runner cache across providers could execute with a stale model.
- Applying settings after runner/context creation could mix profiles.
- Failing to restore settings after cancellation/error could leak the prior profile into a later call.
- Concurrent requests could interleave profile prompts, tools, permissions, and runner configuration.
- Preflight must not be skipped or run twice while moving selection ahead of BaseAgent runner resolution.
- Profile MCP servers must be closed without closing coordinator-owned handles.
- All-low scores still select a winner by explicit product policy; callers should understand a probability is not a correctness guarantee.

## Historical Regressions

- PR #461 initially forked a specialist and had a no-match/threshold general-agent fallback. This feature replaces that policy with settings applied to the coordinator and always-best selection.
- Existing JEV behavior requires preflight to stop before profile selection and keeps tool selection in the runtime's ordinary loop.

## Test Suite Map

- `tests/test_jev_agent.py` covers profile/catalog validation, the Choice request, max-probability and tie policy, public exports, one-profile behavior, setting restoration, failures, and concurrency.
- `tests/test_jev_preflight.py` covers the existing fixed-question gate and clarification-before-routing order.
- `tests/test_jev_tool_selector.py` covers selected-profile tool visibility and the separate runtime settings surface.
- `scripts/test-jev-agent-profile-routing.py` runs all three Jev feature modules with one PASS/FAIL line per test.
- `python scripts/run_ci.py --stage package` verifies prompt assets in the built wheel.

## Omitted Testing Strategies

- Browser tests are omitted because the feature is a Python SDK/runtime contract with no UI.
- Database/migration tests are omitted because profile catalogs and response selections are in-memory.
- Live TypeSafe/provider tests are omitted from deterministic CI; scripted transports exercise their request/response boundaries without secrets or network flakiness.
- Large-scale stress tests are omitted; the profile count is bounded by TypeSafe's 255 Choice options and the same-instance concurrency invariant has a deterministic async test.
