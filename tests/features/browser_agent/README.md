# BrowserAgent

## Folder Description / Intent

This folder holds the feature tests for `BrowserAgent`: an orchestrator that runs a long browser task through the developer's own browser MCP servers. The orchestrator never touches the browser itself. It hands each page-level job to a fresh episode worker through `run_episode`, keeps the original goal on a goal card it may only grow through `patch_goal`, and accepts a finish only after a fresh-context recheck. The tests are offline. Only two seams are faked: the model runner, patched at `BaseAgent._runner_for_model` and answered by agent name, and the MCP stdio transport, patched at `vidbyte.tools.mcp.attach.McpStdioTransport`. `BaseAgent`, the linear loop, `BrowserAgentRuntime`, the MCP mixin, client and bridge, the compaction middleware and engine, `ToolSettings`, the prompt catalog, and the usage tracker all run for real. The behavior itself lives in `vidbyte/agents/browser/`, with its records, enums, and constants in `vidbyte/lib/`, not here. The contract comes from `docs/spec/browser-agent/spec.md`.

The pack covers every acceptance criterion from AC-1 to AC-33 except AC-29, which existing tests already prove (see `docs/spec/browser-agent/test-plan.md`), plus the invariants and edge cases that a reviewer could otherwise delete code for without a test noticing. The test plan maps each test to the spec IDs it proves.

## File Index

- `README.md` describes the scope and how to run the pack.
- `FEATURE.md` defines the contract, the invariants, the known failure modes with the test that catches each, and the strategies left out on purpose.
- `browser_agent_fixtures.py` provides the scripted model runner routed by agent name, the fake ACTION, SEARCH, and FETCH servers, settings and agent builders, an event recorder, and readers for the goal card, tool results, prompt templates, and history sizes.
- `test_browser_agent_acceptance.py` runs the spec's section 4 snippet as written, one browser process per run, sync and async server lifetimes, a side-effect-free runtime build, and a clean record per run.
- `test_browser_agent_contract.py` covers exports, enum values, constants, the prompt family, the runtime registry and refusal, the session refusal, the overridden hooks, the `run_episode` and `patch_goal` schemas, role naming, and the complexity budget.
- `test_browser_agent_settings.py` covers required keys, blank keys, invalid server and agent settings, key secrecy in settings, the type check, defaults, and preset storage.
- `test_browser_agent_episode.py` covers the tool split between orchestrator and worker, the action cap, the screenshot cap, the observation window, the worker history trim, stuck cards, cancellation, `ready_to_submit`, recipes, card caps, episode order, and the permission policy.
- `test_browser_agent_goal.py` covers `patch_goal`, the card in every call, refusals, the full progress section, verbatim user text, and two seeded property tests for patches and the stall count.
- `test_browser_agent_recheck.py` covers the fresh-context recheck, refused finishes, periodic rechecks, the stall stop, derived `done_when`, and the fail-open and fail-closed paths.
- `test_browser_agent_rebuild.py` covers the orchestrator history rebuild after a tool iteration, at a refused `isDone`, and when one group alone is over the cap.
- `test_browser_agent_observability.py` covers events and their sink, the usage roll-up, key secrecy at run time, server names and env, reserved MCP tool names, an empty ACTION server, and duplicate tool names.

## Run

From the repository root: `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q`. One file: `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/test_browser_agent_episode.py -q`. No test starts a process, calls a provider, or reads a real key.

## Logs

- 2026-10-17 - Pack added red, ahead of the implementation, from spec r3 (S2 test author).
