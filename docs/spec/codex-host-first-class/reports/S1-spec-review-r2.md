VERDICT: SOUND WITH FIXES — the r2 fixes are correct and consistent across every section, but the side-chat tool can still write files through approval escalation, the weakly held stream cursor cannot be built inside the §8.4 budget, and one new tool reports every success as an error.

ROUND-1 FIXES (11 held, 2 partly):
- R-1 held. `ThreadSearchParams.json:85-86`, `tui/src/lib.rs:779-784` and `task_mentions.rs:80` agree that an omitted or empty `sourceKinds` means CLI and VS Code only. `CODEX_HOST_HELPER_SOURCE_KINDS` is CLI, VS Code, exec, app-server and unknown (`vidbyte/lib/constants/codex.py:403-409`). AC-33, EC-56 and the §13 note on the fake's filter make the test non-vacuous.
- R-2 held. `CODEX_HOST_LOAD_SAFE_GOAL_STATUSES` is every 0.163.0 `ThreadGoalStatus` except `active`, and the next step no longer loops. A-13 gains support from the TUI, which asks before resuming a paused, blocked or usage-limited goal after a load (`thread_goal_actions.rs:78-84`). One caveat: A-13's "If wrong" path, a complete-only guard with a "pause" next step, would bring the loop back.
- R-3 held. `token_budget` and `tokens_used` exist in the 0.163.0 `ThreadGoal` and in `CodexThreadGoal` (`codex_host.py:593-594`). The edit-then-resume order matches `goal_menu.rs:110-115,133-143`. A neighbouring next step is still wrong (R-17).
- R-4 held. 42 tools, 9 no-tool operations, 69 classes, 44 keys and `(42, "check_codex_ready")` agree everywhere. `EXPECTED_ENUMS` compares as a dict (`test_codex_host_records.py:535-540`), so the 9 explicit entries plus `TOOL_NAMES` cover all 25. No `TERMINALS_CLEANED_TEXT` or clean-tool text remains outside §16 and §17.
- R-5 partly. The Vidbyte-tools residual risk is now stated honestly. But the remaining claim, that `READ_ONLY` makes Codex's own commands read-only, is still false while the approval policy is inherited (R-14).
- R-6 held. The check comes after `thread/fork`, before step 7 shares the handler, and before inject and `turn/start`. `Thread` carries no approval fields, so this is the earliest point that does not resume the parent. `fork_codex_thread` starts no turn (`host.py:376-406`), so `starts_turn=False` is right. `ThreadForkResponse` has the same `AskForApproval` and `ApprovalsReviewer` types as the start and resume responses.
- R-7 partly. The lifecycle is sound in CPython (verified below), and the usage delta is computed once at no new cost. But the weak set cannot be built without a 70th class (R-15). NFR-3's host-wide figure is a formula, not an enforced bound: nothing caps live turns on a host, only `CodexToolScope.max_live_turns` for tool-started turns.
- R-8 held.
- R-9 held. All 25 normative sequences match their INVs, including load (`thread/goal/get`, `thread/resume`), and `preflight.run(spends=False)` sends only the local reviewer check and the model check (`preflight.py:83-129`).
- R-10 held.
- R-11 held.
- R-12 held.
- R-13 held. `_guard` calls `asyncio.get_running_loop()` only after the open check (`host.py:734-737`), and §13 asks for the dedicated boundary test.

WHAT THE SPEC GETS RIGHT
- **The R-6 placement needs no cleanup.** The resolved reviewer can only be known from the fork response, and checking it inside `fork` before the handler is shared leaves nothing to release.
- **D-35 is grounded in three independent Codex sources and is tested non-vacuously.** §13 tells S2 to make the fake apply Codex's default filter, so dropping the key fails AC-33.
- **D-14 and D-38 follow Codex's own TUI.** The load guard refuses only `active`. Budget-limited goals continue edit-then-resume, which keeps every goal turn tracked, and the spent-budget check reads fields that really exist.
- **R-4 and R-9 propagated with no drift.** Counts agree across §2, §8.4, §9.2, §12.3 and §13, the §9.2 tool order equals `CodexHostOperation` order filtered to tools, and every §13 pin named exists at the line given.

FINDINGS

R-14 [Major] [L7] §9.2 tool 34, D-22, INV-43, T-2, AC-36 — The side-chat tool's `READ_ONLY` sandbox does not make Codex's own commands read-only, because the inherited approval policy still lets a sandbox escape be approved
  Evidence:
  - The spec claims too much:
    - row 34: "The request is `spawn_defaults` with `thread.sandbox` and `turn.sandbox` set to `READ_ONLY`, `writable_roots=()` and `network_access=None`. That covers Codex's own commands only";
    - D-22: "That makes Codex's own commands and patches read-only";
    - T-2 lists "have Codex write files from a side chat" as controlled by that.
  - The 0.163.0 schema says otherwise:
    - `ApprovalsReviewer`: "Configures who approval requests are routed to for review. Examples include sandbox escapes, blocked network access … `auto_review` uses a carefully prompted subagent … before approving or denying the request";
    - `AskForApproval`'s granular form has `sandbox_approval`.
  - Nothing narrows who can approve:
    - the tool takes `approval_policy` and `approvals_reviewer` from `spawn_defaults` as given (`CodexSpawnRequest.approval_policy`, `codex_host.py:171-172`), or Codex resolves them from the parent and `config.toml`;
    - the host has one `approval_handler` for every thread, forks included (`connection.py:293-294`).
  Failure: A developer's scope sets `approval_policy=ON_REQUEST` and `approvals_reviewer=AUTO_REVIEW`, or the host has a handler that approves workspace edits for the main work. A model calls `start_codex_side_chat` on a thread whose turn is mid-edit. In the side turn, a write hits the `READ_ONLY` sandbox, the model asks to escalate, and the auto reviewer or the handler approves. The command then writes into the files the parent's running turn is editing: the second Codex writer D-22 says the tool must never add. AC-36 still passes, because it checks only the sandbox and the roots.
  Smallest fix: In row 34, D-22 and INV-43, the tool also sets `approval_policy=CodexApprovalPolicy.NEVER` on its request, and resets `thread.approval_mode` and `turn.approval_mode` to `PROVIDER_DEFAULT` (the record refuses the two together, `codex_host.py:228-231`). This only narrows, so it fits the settled rule that tools never widen approvals. AC-36 asserts `approvalPolicy: "never"` on both `thread/fork` and `turn/start`. It also helps D-36: `routes_to_user` is then false for every tool-started side chat, so a model retrying cannot hit the post-fork reviewer refusal, which leaves one loaded fork per call (EC-59).

R-15 [Major] [L2, L5] D-37, INV-21, §8.5 `subscribe`, §9.1 lifecycle, §12.3 row 18, §8.4 — The weakly held stream cursor needs a class the budget does not have, its natural dataclass forms raise `TypeError` at the first step, and the weak hold does no work
  Evidence:
  - What the spec asks:
    - row 18 keeps "the open cursors in a `weakref.WeakSet`";
    - D-37: "the log holds cursors weakly";
    - §8.4 counts 69 classes with no cursor class, and says "The implementer may not exceed this budget without stopping and reporting BLOCKED";
    - AGENTS.md puts every new dataclass in `vidbyte/lib/dataclasses/` and prefers `slots=True`.
  - What CPython 3.11 under `V` allows: `WeakSet.add` raises `TypeError: cannot create weak reference to 'SlotCursor' object` for an `@dataclass(slots=True)`, and `TypeError: unhashable type` for a plain `@dataclass`. It also refuses `list`, `dict`, `int`, `types.SimpleNamespace` and `object()`. Of the built-ins tried, only `frozenset` is accepted, and it is immutable and hashed by value.
  - What actually removes the cursor: with a hand-written class that has `__weakref__`, the generator's `finally` removed it in all five abandonment paths:
    - never iterated;
    - `break` on a temporary iterator;
    - `break`, then `del` of the variable;
    - the reader task cancelled;
    - a reference cycle, then `gc.collect()`.
    
    The weak reference never removed one. asyncio's async-generator finalizer schedules `aclose()`, and `asyncio.run`, like `IsolatedAsyncioTestCase`, runs `shutdown_asyncgens` at loop close.
  Failure: The implementer follows AGENTS.md and writes the cursor as a slotted record. Every `stream_codex_turn` iteration then raises a raw `TypeError` at its first step, which breaks INV-2 and fails AC-12. A weak-referenceable class instead is a 70th class, so the build stops BLOCKED under §8.4.
  Smallest fix: In D-37, INV-21, §8.5, §9.1 and row 18, replace the weak set with an integer count of reading subscriptions:
  - the generator increments the count at its first step and decrements it in its `finally`;
  - each subscription keeps its next sequence number as a generator local and computes its `GAP` from the log's oldest kept sequence;
  - the log releases its events when the turn has ended and the count is 0.
  
  The behaviour is the same, with no new class and no weakref. Optionally, EC-17's "No leak" holds only once the iterator is closed or dropped, so the docstring should recommend `contextlib.aclosing` for early exits.

R-16 [Major] [L3, L10] §9.2 tool rules (tools 30 and 32), §12.3 rows 31, 33 and 35 — Two new tools do not fit `_json`: `update_codex_turn_settings` reports every success as an error, and `wait_codex_turns` returns every snapshot's full items
  Evidence:
  - The rule: §9.2 says "each tool returns `self._json(record)`", with an exception only for the tools whose method returns `None`.
  - Tool 32 calls `update_codex_turn_settings`, which returns `CodexTurnSettingsStatus`, an enum (§8.5).
  - `_CodexHostTool._json` (`vidbyte/tools/builtins/codex/_base.py:231-240`) calls `asdict(record)` unless the record is a tuple, and `dataclasses.asdict(<str Enum member>)` raises `TypeError: asdict() should be called on dataclass instances` (checked under `V`).
  - `without_items` strips `result.items` only when the data is a dict. The single-turn wait tool relies on it (`live.py:78`), but tool 30 returns a tuple of snapshots.
  Failure:
  - **Tool 32.** A model updates its running turn's effort. Codex applies it, `_json` raises, and `_run` turns that into a `codex.api_error` result (slice-1 X8). The model is told the change failed, so it retries and sends a second `turn/settings/update`.
  - **Tool 30.** `wait_codex_turns` over many handles returns every turn's full transcript items, up to 1,024 of them in one tool result, while `wait_codex_turn` deliberately leaves them out.
  - **Tests.** S2 cannot write the expected output of either tool from the spec.
  Smallest fix: In the §9.2 rules:
  - tool 32 returns a one-sentence `TURN_SETTINGS_STATUS_TEXT`, formatted with the status value, in `controls` beside `THREAD_SETTINGS_UPDATED_TEXT`;
  - tool 30 serializes each snapshot without `result.items`, and row 31 extends `_json`'s `without_items` to tuples.
  
  AC-35 or AC-37 asserts both outputs.

R-17 [Minor] [L5, L9] §9.2 `CODEX_HOST_GOAL_NOT_RESUMABLE_NEXT_STEP`, INV-31, AC-26 — The not-resumable next step sends an active goal that nothing runs to `run_codex_goal`, which clears it and its usage
  Evidence:
  - The next step reads "Read the goal with get_codex_goal: an active goal is already running, and a complete goal is finished, so start a new one with run_codex_goal."
  - A stored goal can be `active` on a thread nothing runs:
    - a graceful close pauses goal runs (`connection.py:523-530` sends `cancel_goal_operation`);
    - a process death sends nothing (`host.py:923-934`);
    - a goal another client left behind also stays `active`.
  - `pause_codex_goal` works on a thread that is not loaded (A-3), and `resume_codex_goal` then accepts `PAUSED`.
  Failure: A host dies mid goal-run. The next host calls `resume_codex_goal(t)` and gets `configuration.invalid_argument`. An agent repairing from the packet follows the next step and calls `run_codex_goal`, which clears the goal first and loses its accumulated usage and history. That loss is exactly what INV-31 and D-38 exist to avoid, and the safe path is never named.
  Smallest fix: Reword the next step: "Read the goal with get_codex_goal. A complete goal is finished, so start a new one with run_codex_goal. An active goal that no client is running, for example after a host stopped, continues with pause_codex_goal and then resume_codex_goal."

R-18 [Minor] [L9] §12.3 row 38 — Row 38 tells the implementer to edit a docstring line that a test pins verbatim
  Evidence: Row 38 says "and update the docstring bullet (`:11`)". `vidbyte/tools/builtins/__init__.py:11` is "- Codex host tools from builtins.codex.", which holds no count. `test_codex_host_packaging.py:253-255` asserts that exact line after the code-search bullet, and §13 does not list it as superseded. The text was carried over from r1 while rows 37–39 were revised.
  Failure: An implementer edits the bullet, for example to add the 42-tool count, and fails a packaging test they may not touch (§14), so the build stops BLOCKED.
  Smallest fix: Row 38: "The docstring bullet (`:11`) stays as is; it is pinned verbatim at `test_codex_host_packaging.py:253-255`."

VERIFIED CLAIMS
1. **The search filter.** `ThreadSearchParams.json:85-86`: "When omitted or empty, defaults to interactive sources". `lib.rs:779-784` names CLI and VS Code as interactive, and `task_mentions.rs:80` sends an empty list. HELD.
2. **The fork's reviewer fields.**
   - `ThreadForkResponse` has `approval_policy` (`AskForApproval`) and a required `approvals_reviewer` (`ApprovalsReviewer`), the same types as `ThreadStartResponse` and `ThreadResumeResponse`. HELD.
   - `Thread` has no approval fields. HELD, so the check cannot come before `thread/fork`.
3. **`fork` and its caller.**
   - `CodexThreadHelpers` holds `_preflight` and `_responses` (`thread_helpers.py:85-89`). HELD.
   - Step order is read, model check, fork point, fork, handler, name (`:203-240`). HELD.
   - `fork_codex_thread` starts no turn. HELD.
4. **The budget fields.** The 0.163.0 `ThreadGoal` has `token_budget` and `tokens_used`, and `CodexThreadGoal` mirrors them. HELD.
5. **The goal statuses.**
   - 0.163.0 `ThreadGoalStatus` is `active`, `paused`, `blocked`, `usageLimited`, `budgetLimited` and `complete`, which `CodexGoalStatus` matches, plus `NONE`. The load-safe set is every status but `ACTIVE`. HELD.
   - A status Codex adds later fails earlier, at the SDK's enum validation (`codex.protocol_mismatch`). So the allow-list's fail-closed claim holds, through a different path than stated.
6. **The TUI citations.**
   - `goal_menu.rs:44-58` ("Mark it active and continue when idle"), `:110-115` (no resume for a budget-limited goal) and `:133-143` (edit sets budget-limited and complete back to active). HELD.
   - `thread_goal_actions.rs:78-84` prompts before resuming a paused, blocked or usage-limited goal after a load, which supports A-13.
7. **A-20.** `app_server_session.rs:1001-1019`: `fork_side_thread` uses `StartIfIdle`. HELD. New supporting evidence: goal calls on an ephemeral thread fail with "ephemeral thread does not support goals" (`thread_goal_actions.rs:353-366`), which makes A-20 likelier. Consider citing it.
8. **The usage delta.** `over_cap` already computes `usage_delta()` on every notification (`turns.py:136-142`), so computing it once adds no cost. No test calls `over_cap` or the moved start helpers. HELD.
9. **The end paths.** Every path that ends a turn goes through `registry.finish` and then `CodexLiveTurn.finish`: close and death in `host.py:863,881,901,920`, reviews in `reviews.py:134,145`, and events in `turn_events.py:86,89,111,139,153`. HELD, so one `close` per turn is achievable.
10. **The CPython stream experiment.** Run under `V`, Python 3.11.0:
    - which objects a `WeakSet` accepts is as stated in R-15;
    - a never-iterated generator registers nothing;
    - `finally` runs on every abandonment path.
    
    R-7's lifecycle claim HELD. The weak hold is redundant (R-15).
11. **The no-spend preflight.** `preflight.run(spends=False)` runs only `reject_user_reviewer` and the model check. HELD, so AC-3 and the §9.2 settings sequence are right.
12. **The §13 pins.**
    - The probe is `(26, "check_codex_ready")` (`test_codex_host_packaging.py:183`).
    - Three `len(tools) == 26` pins exist.
    - `NEW_ROWS = TOOL_TABLE[15:]` exists.
    - The boundary test enumerates through `inspect.getmembers`, which sees inherited methods, so it needs 22 new rows (`test_codex_host_inputs.py:216`).
    - The helper-order and operation-tail pins are at the lines given.
    - The `lib.process.__all__` pin is at `test_harness_threads_surface.py:212`.
    
    HELD.
13. **The fakes.** The fake's `thread/fork` copies the parent's reviewer and policy (`codex_host_fakes.py:857`), and `FakeThread.source` is `"appServer"` (`:161`). The fakes file is 902 lines and the support file 828. HELD.
14. **The counts.** §8.4's 69 classes are 11 + 1 + 14 + 17 + 10 + 16. There are 44 non-message keys, counted from §9.3, and 16 tools across the modules (5 + 7 + 1 + 3). The §9.2 tool order equals `CodexHostOperation` filtered to tools. HELD.
15. **The schema on approvals (R-14).** `ApprovalsReviewer` names sandbox escapes as approval requests that `auto_review` decides, and the host's approval handler serves every thread. HELD.
16. **`_json` (R-16).** `asdict` raises on an enum, and `without_items` acts only on dict data (`_base.py:231-240`). HELD.
17. **The goal lifecycle on close (R-17).** A graceful close pauses goal runs through `cancel_goal_operation`, and a process death leaves them `active`. HELD.
18. **The docstring pin (R-18).** The builtins bullet is pinned verbatim at `test_codex_host_packaging.py:253-255`. HELD, and it contradicts row 38.
