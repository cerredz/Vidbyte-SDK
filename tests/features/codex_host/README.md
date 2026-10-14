# CodexHost feature tests

## Folder Description / Intent

This folder checks the public promise of `CodexHost` in `vidbyte.harnesses.native.codex`: fifteen small async functions over one `codex app-server` process, the six module functions that open a host for one call, and `CodexHostTools`, which gives each function one agent tool. The tests drive a real `CodexHost` against an in-memory app-server. The real openai-codex `CodexClient` runs over a fake pipe, so its reader thread, message router, retry helper and goal routing all run unmocked. Only three things are replaced: the subprocess, at the spec's test seam `vidbyte.harnesses.native.codex.connection.CodexClient`, plus `shutil.which` and `sys.platform`.

The implementation belongs in `vidbyte/harnesses/native/codex/` (the host, connection, wire, turns, preflight, errors and module functions), `vidbyte/lib/dataclasses/codex_host.py`, `vidbyte/lib/enums/codex.py`, `vidbyte/lib/constants/codex.py`, `vidbyte/tools/builtins/codex/` and `vidbyte/tools/toolsets/codex.py`. The contract comes from `docs/spec/codex-host/spec.md`.

## Non-Goals

- Do not run `codex` or start a real app-server. A live turn spends the user's Codex plan (NG-13), so the live half of AC-1 is manual QA.
- Do not test `CodexHarnessAgent` here. `tests/test_codex_tools.py` and the other `tests/test_codex_*.py` modules own it, and they must keep passing unchanged (NG-5).
- Do not test controls the spec leaves out: MCP permission checks (Q-7), restricting thread tools to their own toolset (Q-8), or spending ceilings (Q-9).
- Do not mock above the seam. The records, the Codex translators, `UsageTracker`, `ToolExecutor`, `PermissionPolicy`, `Tools` and `McpStudioServer` all run for real.

## File Index

- `README.md` explains the boundary of the pack and routes changes to their owners.
- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `codex_host_support.py` holds the spec's literal texts and tables, the privacy canaries, the openai-codex skip gate, `HostTestCase` (which runs a real host over the fake) and `StubCodexHost` for the tool tests.
- `codex_host_fakes.py` is the in-memory app-server. It answers as codex app-server 0.162 does, logs every request with the thread that wrote it, and offers holds, scripted failures and notification drivers.
- `test_codex_host_records.py` checks record validation, the USER reviewer refusal, the new failure codes and constants, `next_step` on `CodexAgentError`, and the enum wire values.
- `test_codex_host_packaging.py` checks import safety in a fresh interpreter, the native package marker's bytes, the export lists, and the REPO_MAP and README texts.
- `test_codex_host_bridge.py` checks `CodexToolTranslator.validate_names` and `CodexToolBridge.handler`.
- `test_codex_host_tools.py` checks the fifteen tools over a stub host: schemas, permissions, error results, the live-turn cap, `spawn_defaults`, argument checks, outputs and MCP.
- `test_codex_host_lifecycle.py` checks the section 4 snippet, binary resolution, the version gate, the call guards, close order and the module functions.
- `test_codex_host_turns.py` checks spawn, preflight, waits, results, the timeout and output cap, process death, the turn-error table, structured output, steer, interrupt and usage tracking.
- `test_codex_host_threads.py` checks continue, the field rules, launch, fork, list and read, readiness, rate limits and models, the reviewer check, dynamic tools and the agents config.
- `test_codex_host_review_goals.py` checks reviews and their registration races, and goal runs with their budget, goal table and cleanup orders.
- `test_codex_host_failures.py` checks late acceptance, the withdrawn queued start, a start accepted after close, and the privacy canaries.
- `test_codex_host_router.py` checks that the server-request router answers every request on the real reader thread and never raises.
- `test_codex_host_sdk_contract.py` pins the openai-codex surface that the host reaches outside the SDK's public API.
- `test_codex_host_review_gaps.py` pins the windows the S4 review found open: a cancellation during a review's read-back, a launch, a close or an in-flight start; an unusable `output_schema`; the problem of a late-accepted turn or goal run; a mapping `output_schema` that is only parsed as JSON; and the launch tool's cap slots.

## Logs

- 2026-10-13 - Pack added red, ahead of the implementation, from spec r3 (S2 test author). The seven modules from `test_codex_host_lifecycle.py` to `test_codex_host_sdk_contract.py` need the `codex` extra, so CI, which installs only `.[dev]`, skips them; run them locally with the extra installed.
- 2026-10-14 - Added `test_codex_host_review_gaps.py` for the S4 review findings (S5 repair). Its host classes need the `codex` extra, so CI skips them; its launch tool class runs over a stub host on CI.
- 2026-10-14 - Added classes to `test_codex_host_review_gaps.py` for the S5 re-review findings R-26 and R-27 (S5 repair 2): the unusable-schema refusal's text and cause, a schema whose walk never ends, and a user interrupt after a failed or in-flight stop. They need the `codex` extra, so CI skips them.
