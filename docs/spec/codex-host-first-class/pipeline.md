---
slug: codex-host-first-class
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-first-class
branch: feat/codex-host-first-class
base_commit: a7730107  # slice 1 (codex-host-hardening) verified HEAD; branch stacked on PR #1178
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1181
until: none
started: 2026-10-17 22:40
---

# Pipeline: CodexHost first-class Codex features (slice 2 of 2)

Slice 1 (`docs/spec/codex-host-hardening/`, status `verified`) is done on this branch. This slice adds the P0 and P1 functions from request.md §C.10 that slice 1 did not build. S6 runs once, at the end of this slice, and covers both specs. The PR already exists (draft #1181), so S3 skips creating it.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 recon | done | 22:40 | 23:05 | reports/S0-scout.md | code-map.md: 4 sections, 564 lines; per-function protocol table (§4.1); pins table (§3.4) |
| S1 spec + review | done | 23:10 | 03:10 | reports/S1-spec-author.md, reports/S1-spec-review.md, reports/S1-spec-review-r2.md | r1 fde5a8b0; round 1 SOUND WITH FIXES (1B/6M/6m, 040e56c1); r2 603519bb; round 2 SOUND WITH FIXES (0B/3M/2m, 4db45a23); **r3 d9072cdb status approved**. Budget 13 files / 69 classes / 0 deps / 46 config keys / 42 endpoints; INV 55, AC 44, EC 62, FR 36 |
| S2 tests | running | 03:15 | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR (both slices) | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-17 22:40: **The same branch, worktree and PR as slice 1.** The precedent is #1055's two specs in one PR. Slice 2's base is slice 1's verified HEAD a7730107. request.md is slice 1's verbatim conversation capture with a slice-2 header (scope, what slice 1 already built, and the machinery to reuse).
- 2026-10-17 23:05: **Queue scope is P1 add, list and start only.** request.md's "`thread/queue/*`" was the assistant's shorthand. The research the user asked to build from ("create the codex functions that you thought about") ranks `thread/queue/add|list|start` as P1 and `update|delete|reorder` as P2 (codex-gap-report.md:152, :334, matrix rows 21-25). P2 is not built (slice 1 Q-1 default).
- 2026-10-17 23:05: **`create_codex_worktree` has no app-server method.** The research's own proposal is to implement it with `git worktree add` under a Vidbyte-owned root (codex-gap-report.md:314-315). That is the design input.
  - The alternative, shelling out to `codex exec --worktree`, is out: it starts a paid Codex run.
  - Codex's managed-worktree default root is unverified, because the `codex_worktree` crate is not in the scratchpad. The spec must not claim compatibility with that root.

- 2026-10-18 00:40: **Spec r1 (fde5a8b0) checked.** It has 18 sections, 73 §12.3 rows, base_commit a7730107 and the right commit message.
  - **The queue (NG-1 / D-20 / Q-1, default "not built"): I accepted the author's evidence.** It overrides my own 23:05 scope decision.
  - **Evidence I verified myself:** `codex-src/codex-rs/tui/src/session_queue_commands.rs:34` refuses `codex queue` without the shared daemon ("Queuing must discover the shared server to avoid writing through a separate server"), and `:42-48` refuses queuing through an embedded app-server. CodexHost is always a private stdio app-server.
  - **The author's other points:**
    - the TUI never calls `thread/queue/start` or `list`, so Codex drains the queue itself and the resulting turns are untracked by the host (slice-1 INV-11);
    - inside one private server, the queue is redundant with `continue_codex_thread` and with `wait_codex_turn` followed by continue.
  - **Not stopping for the user:** the default is evidence-backed and conservative, so I don't stop. It is named in the S1 summary so the user can interrupt.

- 2026-10-18 03:10: **S1 done.** r3 (d9072cdb) has `status: approved` and 18 sections, and §16 records every finding from both rounds (R-1…R-18). The defaults I applied, all printed in the S1 summary:
  - Q-1, the queue: not built.
  - Q-2…Q-9: no.
  - Q-10 and Q-11: optional and scope-adding, not built.
  - **R-14 took a different form from the reviewer's fix.** The side-chat tool uses `DENY_ALL` approval modes, which send `approvalPolicy "never"` and no reviewer on both `thread/fork` and `turn/start`. The reviewer's explicit `NEVER` would have reached only `thread/fork`, because `turn_start` never sends explicit fields. I accepted it, since it narrows on both requests.
  - **The host stream bound is enforced (D-39):** `CodexTurnRegistry.charge_stream` with limits of 65,536 events and 32,000,000 chars.

- 2026-10-18 05:45: **S2 came back BLOCKED** with 236 tests (fa27a3ad, f8146997; report 9d3aed8c) and two spec defects. I checked both myself and answered them from the spec, without asking the user:
  - **Two missed 26-tool pins:** `test_codex_host_lifecycle.py:101` and `test_codex_host_helper_lifecycle.py:109`. §13 intends a 42-tool catalog that S3 can reach without editing tests, so this is option (a): §13 gains both rows, then S2 rewrites them.
  - **`CODEX_HOST_NO_GOAL_MESSAGE` already exists** (`constants/codex_host.py:312`, used by `run_codex_goal` and pinned at `helper_surface.py:94`). INV-48 freezes `run_codex_goal`, so this is option (a): the new message is renamed `CODEX_HOST_NO_STORED_GOAL_MESSAGE`, unused, and chosen by me over S2's `GOAL_MISSING`. That keeps it in the `NO_*GOAL` family next to the pinned `CODEX_HOST_NO_GOAL_CAUSE` and `_NEXT_STEP`.
  - **My sweep of all 47 constant names in the spec's tables** found no other collision.
  - **The S1 author's r4** (an amendment, not a review round) also resolves S2's six ambiguities, choosing only options the tests already accept.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- **Interpreter:** `V="C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/venv-codex163/Scripts/python.exe"`. It is the editable worktree install with openai-codex 0.163.0. Never use the global Python, which holds the user's editable install, and never pip. *Source:* slice 1
- **Gates:**
  - area tests: `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider`;
  - lint: `"$V" lint/run.py`, whose last line is `SDK-LINT: PASS`;
  - full gate: `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source`, then `"$V" scripts/run_ci.py --stage package` with no PYTHONPATH. Run them one at a time, because the MCP stdio timeout test is load-sensitive.
  
  At a7730107 the source stage gives `1 failed (inherited), 6588 passed, 27 skipped`, and the package stage gives `CI passed.` *Source:* slice 1
- **The inherited failure:** `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (167 != 120) is not ours. *Source:* slice 1
- **Semgrep:** the global CLI is broken, so use `C:/Users/422mi/AppData/Local/Programs/Python/Python311/Lib/site-packages/semgrep/bin/semgrep-core.exe -rules .semgrep/<rule>.yml -lang python -json <file>` and strip the leading `"."`. It scans git-tracked files only. *Source:* slice 1
- **Lint:**
  - C021 (baseline 0) allows no top-level UPPER_CASE under `vidbyte/harnesses/native/`, so constants and messages go in `vidbyte/lib/constants/codex_host.py`;
  - S008 allows complexity ≤10 and branches ≤12;
  - S024 allows nesting ≤3;
  - S012 forbids a method named `request`;
  - A002 keeps `# @intent` within 20 lines of its `def`;
  - source comments wrap at 72 columns, tests are exempt by grain.
  
  Run the full lint before every push. *Source:* slice 1
- **The user's #1055 conventions:**
  - constants and messages in lib;
  - error packets read "`<operation> failed with <code>. <summary> The thread id was <id>. Likely cause: <cause> Next step: <step>`";
  - every host function takes a strictly validated input dataclass in `vidbyte/lib/dataclasses/codex_host_inputs.py`, built right after `_guard`.
  
  *Source:* request.md §B.1
- **Slice-1 machinery to reuse:** `ExceptionOrigin.describe` (one token), `LogToken.of(value, CODEX_HOST_LOG_TOKEN_MAX_CHARS)` at log calls, the INV-7 call records, `CodexTurnEvents`, `CodexReviews`, retries through `CODEX_HOST_RETRIED_METHODS`, and post-validation injection of experimental fields, refused locally when `experimental_api=False`. *Source:* slice 1 spec
- **Log record shape:**
  - the event is the first word of a %-style msg, followed by single-space `key=value` tokens;
  - there is no `exc_info`;
  - the tests' `log_fields` is now strict, so a word with no `=` fails.
  
  *Source:* slice 1 S2
- **Push:** only `git push -u origin feat/codex-host-first-class`. Never a bare push, never force. *Source:* user constraints
- **Remote checks:** none run on push (workflow_dispatch only), so the local gate is authoritative. *Source:* slice 1
- **No paid Codex turns:** never run the `codex` binary, and never set `VIDBYTE_CODEX_LIVE_TESTS`. *Source:* user constraints
- **The raw path:** `CodexConnection.raw` (`connection.py:372`) needs a `v2_all` response model by name. Most experimental slice-2 methods have none: `thread/settings/update`, `turn/settings/update`, `collaborationMode/list`, `memory/*`, `thread/queue/*`, `thread/backgroundTerminals/*` and `thread/search`. `mcpServerStatus/list`, `thread/inject_items` and `thread/revert` do have models. *Source:* S0 scout
- **SDK models drop fields:** `TurnStartParams` drops `collaborationMode`, and `ThreadListParams` drops `parentThreadId`. `_params_dict` passes dicts through (`client.py:107-108`), so keys injected after validation reach the wire (`wire.py:207-209`, `:249-253`). *Source:* S0 scout
- **JSON null:** every `wire.py` params dump uses `exclude_none=True`, so it cannot send a JSON null. `serviceTier: null` (clear) on `thread/settings/update` and a null `developer_instructions` in plan settings both need one. *Source:* S0 scout
- **Notifications with no turnId:** the liveness monitor (`connection.py:540-548`) discards every notification without a turnId, for example `thread/settings/updated`, `mcpServer/startupStatus/updated`, `thread/archived` and `thread/queue/changed`. *Source:* S0 scout
- **Turn subscriptions:** the SDK's only multi-consumer turn subscription is private (`_subscribe_turn_notifications`, `client.py:409`). The host watcher holds the public default consumer. The router, `items` and the global queue are unbounded. *Source:* S0 scout
- **Pins:** no free failure-code or `CodexHostOperation` slot exists without editing pins (`helper_surface:245-251,253-266`, `records:63-69,432-440`, `harness_threads:176-195`). The full table is code-map §3.4. *Source:* S0 scout
- **The 1,000-line rule:**
  - `host.py` 937, `wire.py` 797, `lib/dataclasses/codex_host.py` 873, `codex_host_fakes.py` 902, `codex_host_support.py` 828;
  - `lib/dataclasses/codex.py` is already 1,205 and under "no growth" (D-17).
  
  New functions need new modules. *Source:* S0 scout
- **Two test-harness traps:** `test_codex_host_inputs.py:216` uses `iscoroutinefunction`, so it cannot see an async-generator host method. A change under `vidbyte/tools/` outside the four excluded paths fails the harness_threads branch-scope test locally. *Source:* S0 scout
- **Stashes:** never a bare `git stash`, because the stash stack is shared with other worktrees. *Source:* environment
- **Long heredocs:** a long quoted heredoc fails to parse in this Git Bash, so write docs with the Write or Edit tool. *Source:* S5 repair 2, orchestrator
- **Slice-2 contract names (r3):**
  - the mixins `CodexSettingsMethods`, `CodexStreamMethods`, `CodexThreadMethods` and `CodexGoalMethods` over `CodexHostCore`;
  - `CodexTurnStarts`, `CodexTurnEventLog` and `CodexJsonObjectResponse`;
  - `raw(method, params, parse=None)`;
  - `GitWorktrees` in its own lib module;
  - the record modules `codex_host_modes` and `codex_host_features`;
  - `CodexThreadHelpers.fork(..., *, starts_turn=False)`.
  
  *Source:* S1 author r3
- **Slice-2 seams:**
  - patchable limits `turn_stream.CODEX_HOST_STREAM_EVENT_LIMIT`, `_TEXT_LIMIT_CHARS`, `_HOST_EVENT_LIMIT` and `_HOST_TEXT_LIMIT_CHARS`, plus `turn_starts.CODEX_HOST_GOAL_RESUME_START_SECONDS`;
  - read the host totals with `host._registry.charge_stream(0, 0)`;
  - the fake answers -32601 for every slice-2 method, so new handlers go in a stateless mixin module, because `codex_host_fakes.py` is 902 lines;
  - the fake's `thread/search` must apply Codex's default source filter: an empty `sourceKinds` means cli and vscode only, and `FakeThread.source="appServer"`;
  - the fake's fork copies the parent's reviewer and policy unless params override them (`codex_host_fakes.py:857`).
  
  *Source:* S1 author r3
