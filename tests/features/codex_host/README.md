# CodexHost feature tests

## Folder Description / Intent

This folder checks the public promise of `CodexHost` in `vidbyte.harnesses.native.codex`: twenty-seven small async functions over one `codex app-server` process, the six module functions that open a host for one call, and `CodexHostTools`, which gives each function one agent tool, except `delete_codex_thread`, which has none. The tests drive a real `CodexHost` against an in-memory app-server. The real openai-codex `CodexClient` runs over a fake pipe, so its reader thread, message router, retry helper and goal routing all run unmocked. Only three things are replaced: the subprocess, at the spec's test seam `vidbyte.harnesses.native.codex.connection.CodexClient`, plus `shutil.which` and `sys.platform`.

The implementation belongs in `vidbyte/harnesses/native/codex/` (the host, connection, wire, turns, preflight, errors and module functions), `vidbyte/lib/dataclasses/codex_host.py` and `codex_host_inputs.py`, `vidbyte/lib/enums/codex.py`, `vidbyte/lib/constants/codex.py` and `codex_host.py`, `vidbyte/tools/builtins/codex/` and `vidbyte/tools/toolsets/codex.py`. The contract comes from `docs/spec/codex-host/spec.md`, and the twelve thread helpers' contract from `docs/spec/codex-host-thread-helpers/spec.md`.

## Non-Goals

- Do not run `codex` or start a real app-server. A live turn spends the user's Codex plan (NG-13), so the live half of AC-1 is manual QA.
- Do not test `CodexHarnessAgent` here. `tests/test_codex_tools.py` and the other `tests/test_codex_*.py` modules own it, and they must keep passing unchanged (NG-5).
- Do not test controls the spec leaves out: MCP permission checks (Q-7), restricting thread tools to their own toolset (Q-8), or spending ceilings (Q-9).
- Do not mock above the seam. The records, the Codex translators, `UsageTracker`, `ToolExecutor`, `PermissionPolicy`, `Tools` and `McpStudioServer` all run for real.

## File Index

- `README.md` explains the boundary of the pack and routes changes to their owners.
- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, and the strategies deliberately omitted.
- `codex_host_support.py` holds the spec's literal texts and tables, the privacy canaries, the openai-codex skip gate, `HostTestCase` (which runs a real host over the fake) and `StubCodexHost` for the tool tests, `mapped_summary`, which checks a mapped message's head and its likely-cause and next-step tail and returns the summary between them, and `FieldCarryingMapper`, which wraps the connection's error mapper and records every error it maps.
- `codex_host_fakes.py` is the in-memory app-server. It answers as codex app-server 0.162 does, logs every request with the thread that wrote it, and offers holds, scripted failures and notification drivers.
- `codex_host_helper_fakes.py` is the thread-helper, goal and skill half of that app-server, a mixin that `FakeAppServer` inherits. It holds the thread-helper switches and the handlers for `thread/list`, the three `thread/goal` methods, compact, delete, `thread/turns/list` and `skills/list`, and the builders `goal_record` and `skill_entry`, which `codex_host_fakes.py` re-exports.
- `test_codex_host_records.py` checks record validation, the USER reviewer refusal, the new failure codes and constants, `next_step` on `CodexAgentError`, and the enum wire values.
- `test_codex_host_packaging.py` checks import safety in a fresh interpreter, the native package marker's bytes, the export lists, and the REPO_MAP and README texts.
- `test_codex_host_bridge.py` checks `CodexToolTranslator.validate_names` and `CodexToolBridge.handler`.
- `test_codex_host_tools.py` checks the twenty-six tools over a stub host: schemas, permissions, error results, the live-turn cap, `spawn_defaults`, argument checks, outputs and MCP.
- `test_codex_host_lifecycle.py` checks the section 4 snippet, binary resolution, the version gate, the call guards, close order and the module functions.
- `test_codex_host_turns.py` checks spawn, preflight, waits, results, the timeout and output cap, process death, the turn-error table, structured output, steer, interrupt and usage tracking.
- `test_codex_host_threads.py` checks continue, the field rules, launch, fork, list and read, readiness, rate limits and models, the reviewer check, dynamic tools and the agents config.
- `test_codex_host_review_goals.py` checks reviews and their registration races, and goal runs with their budget, goal table and cleanup orders.
- `test_codex_host_failures.py` checks late acceptance, the withdrawn queued start, a start accepted after close, and the privacy canaries.
- `test_codex_host_router.py` checks that the server-request router answers every request on the real reader thread and never raises.
- `test_codex_host_sdk_contract.py` pins the openai-codex surface that the host reaches outside the SDK's public API.
- `test_codex_host_review_gaps.py` pins the windows the S4 review found open: a cancellation during a review's read-back, a launch, a close or an in-flight start; an unusable `output_schema`; the problem of a late-accepted turn or goal run; a mapping `output_schema` that is only parsed as JSON; and the launch tool's cap slots.
- `test_codex_host_helper_surface.py` checks the thread-helpers records, `CodexSkillScope`, the four new failure codes, the twelve new operations, the new constants and message texts, and the twelve host method signatures.
- `test_codex_host_helper_tools.py` checks the eleven new tools over a stub host: their order and schemas, no delete tool, argument checks, default limits, the cap slot of the run tools, error results and outputs.
- `test_codex_host_thread_helpers.py` checks the listing walks, the summary mapping, lineage, the turn listing, compact with its goal check, delete, and the busy, unknown and reservation rules.
- `test_codex_host_goal_skills.py` checks reading a goal, the goal run and its check, the skill listing, the skill and docs runs, and the bounded read-back with its single stop.
- `test_codex_host_inputs.py` checks the validated input record each public host method builds after its call guard: every record is frozen and slotted, every bad value is refused with the field named, and every public method refuses bad input before it sends a request.
- `test_codex_host_error_details.py` checks the mapped error message and packet: the operation and code, the summary, the thread, the code's own likely cause and its next step, the method and exception type, a rebuilt error keeping every field, and a tool stating the next step once.
- `test_codex_host_helper_lifecycle.py` checks the thread-helpers section 4 snippet, the call guards, no preflight and no resume on reads, the missing-method mapping, and the privacy canaries.

## Logs

- 2026-10-13 - Pack added red, ahead of the implementation, from spec r3 (S2 test author). The seven modules from `test_codex_host_lifecycle.py` to `test_codex_host_sdk_contract.py` need the `codex` extra, so CI, which installs only `.[dev]`, skips them; run them locally with the extra installed.
- 2026-10-14 - Added `test_codex_host_review_gaps.py` for the S4 review findings (S5 repair). Its host classes need the `codex` extra, so CI skips them; its launch tool class runs over a stub host on CI.
- 2026-10-14 - Added classes to `test_codex_host_review_gaps.py` for the S5 re-review findings R-26 and R-27 (S5 repair 2): the unusable-schema refusal's text and cause, a schema whose walk never ends, and a user interrupt after a failed or in-flight stop. They need the `codex` extra, so CI skips them.
- 2026-10-16 - Added five files red, ahead of the implementation, from `docs/spec/codex-host-thread-helpers/spec.md` r3 (S2 test author, codex-host-thread-helpers), and updated the section 13 count pins from fifteen tools to twenty-six. `test_codex_host_helper_surface.py` and `test_codex_host_helper_tools.py` run on CI; the other three need the `codex` extra, so CI skips them.
- 2026-10-16 - Added five tests for the S4 review findings of codex-host-thread-helpers (S2 test author r2): the goal tool's slot after a failure or a cancel (R-1, CI-visible), delete's thread hold and its release (R-4), and the read-back's name and turn-id checks (R-8), with the fake switches `recorded_skill_name` and `input_on_earlier_turn`. The R-4 and R-8 tests need the `codex` extra, so CI skips them.
- 2026-10-16 - Split the fake app-server, which this run had grown from 899 to 1,071 lines, into `codex_host_fakes.py` (894 lines) and `codex_host_helper_fakes.py`, the thread-helper, goal and skill handlers that `FakeAppServer` inherits (S2 test author r3). Every answer is unchanged, the test files are unchanged, and `goal_record` and `skill_entry` stay reachable from `codex_host_fakes.py`.
- 2026-10-16 - Added two tests, red until the source fix, for review finding R-17 of codex-host-thread-helpers (S2 test author r4). They check that a goal or skill run whose check fails re-raises the check's `CodexAgentError` with every field kept, `error_type` and `thread_id` included, and only the `*_UNCHECKED_MESSAGE` suffix added. A stand-in for the connection's mapper sets both fields, because no codex-host path sets them yet. The tests need the `codex` extra, so CI skips them.
- 2026-10-16 - Added one test, red until the source fix, for review finding R-18 of codex-host-thread-helpers (S2 test author r5): a launch that fails midway must raise the mapped `CodexAgentError` with every field kept, `error_type` and `thread_id` included. `FieldCarryingMapper` moved from `test_codex_host_goal_skills.py` to `codex_host_support.py`, because the R-17 and R-18 tests both use it. The test needs the `codex` extra, so CI skips it.
- 2026-10-17 - Resolved the PR #1055 review. Host messages and tables moved to `vidbyte/lib/constants/codex_host.py`, so the expected texts now come from there; mapped messages gained a head, a thread sentence, a likely cause and a next step, so the equality checks read the summary through `mapped_summary`; and `FieldCarryingMapper` now records the real mapper's errors, because `CodexErrorMapper.error` sets `error_type`, `thread_id` and `method` itself. Added `test_codex_host_inputs.py` and `test_codex_host_error_details.py`; their record, builder and tool classes run on CI, and their host and exception classes need the `codex` extra.
- 2026-10-19 - Re-pinned the native marker's SHA-256 (9386 LF bytes), the repo-map section and the harnesses README bullet after merging the thread helpers and command functions (PR #1147) with the browser tools. The README check now also accepts the helpers' nested sub-bullets under the `native/` bullet before the list ends; the CodexHost wording itself is unchanged.
