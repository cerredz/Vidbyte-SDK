# S1 spec-author report: codex-host-hardening

- **Stage:** S1 spec author.
- **Branch:** `feat/codex-host-first-class`. **Base:** `6f5a7310`. **Spec commit:** `0f0d3118` ("docs(spec): add codex-host-hardening spec r1").
- **Files:**
  - Produced: `docs/spec/codex-host-hardening/spec.md` (r1, 1,212 lines).
  - This report is written but not committed.
  - No production code or tests were touched.
  - Nothing was pushed, launched or installed.
  - Every Python probe ran with `PYTHONDONTWRITEBYTECODE=1`.

## What I read

**Pipeline inputs**
- request.md
- pipeline.md
- reports/S0-scout.md
- context/code-map.md
- context/codex-gap-report.md: §0–§1, the server-request table, §5, §6, §8–§12 and Appendix B
- context/coverage-matrix.md: header plus grep
- `spec-template.md`

**Prior specs, by grepped ID range only**
- `docs/spec/codex-host/spec.md`: INV-1/9/10/11/15/23/27/28/36/37; D-2/7/13/16/27/32; EC-65/77; NG-5/13
- `docs/spec/codex-host-thread-helpers/spec.md`: INV-5/16/18/22/35; D-13/16/17; EC-14/41; Q-16/17

**Repo rules**
- AGENTS.md
- lint/README.md
- the field-guide pages cited in spec §11

**Production code, by range**
- `vidbyte/harnesses/native/codex/`:
  - host.py: 100–180, 232–520 and 575–893
  - connection.py: 100–374
  - errors.py: 55–125
  - preflight.py: 60–160
  - turns.py: 60–419
  - wire.py: 100–345 and 576–640
  - thread_helpers.py: 55–80, 120–147 and 192–279
  - skill_functions.py: 68–170 and 244–251
  - oneshot.py
- `vidbyte/lib/`:
  - `constants/codex.py`: `__all__`, the approval constants, `CODEX_HOST_USER_REVIEWER_TEXT` and `CODEX_NEXT_STEPS`
  - `dataclasses/codex_host.py`: CodexSpawnRequest, CodexModelInfo, CodexReadiness and the header
  - `enums/codex.py`, `enums/__init__.py`, `errors/base.py`:138–166, `util/__init__.py`, README.md:48
  - `enums/native_threads.py`: its import, which creates the cycle risk behind D-6
- `vidbyte/tools/builtins/codex/`: `_base.py`, `threads.py`, `delegation.py`, `descriptions.py`
- `vidbyte/agents/codex/tools.py`:150–190
- Packaging and CI: pyproject.toml, `scripts/run_ci.py`, `.github/workflows/static-policy.yml`
- Lint rule scopes: A003, A006, A007, S012, S017, S043/S044, S060, S064

**Tests**
- A test-name index of all 17 `test_codex_host_*.py` modules
- The pinned ranges of each test listed in spec §13
- `codex_host_support.py`, `codex_host_fakes.py`, `codex_host_helper_fakes.py`:214–224
- `harness_threads` surface `:193` and `:224-232`

**SDK and schema**
- Installed openai-codex 0.162.1: `client.py` (reader loop, typed methods, `_params_dict`, the runtime-field gate), `retry.py`, `errors.py`
- The 0.163.0 JSON schema in the scratchpad: ThreadForkParams, ThreadResumeParams, CurrentTimeReadResponse, ToolRequestUserInputParams and its response, ThreadGoalSetParams, Model service tiers
- In this stage I diffed the downloaded 0.163.0 wheel against the installed 0.162.1:
  - `client`, `retry`, `errors`, `_runtime_requirements`, `api` and `async_client` are byte-identical.
  - `generated/v2_all.py` differs. Both versions carry `max`/`ultra`, `Model.service_tiers` and `ModelServiceTier{id,name,description}`, `serviceTierForTurn`, the workspaceWrite `networkAccess`/`writableRoots`, `forceReload` and the turns-list `itemsView`/`sortDirection`/`limit`. Neither has `ThreadForkParams.beforeTurnId`/`deferGoalContinuation`.

**Self-checks run after writing**
- All about 110 identifiers the spec names exist in `vidbyte/` or `tests/`.
- All 24 `path::Class::test` IDs resolve to a method of the named class (AST).
- The §4 imports and attributes resolve.
- §0.1 equals request.md's prompt (673 chars).
- No file path appears outside §11–§13, apart from the document citations AGENTS.md and request.md.
- Traceability: every FR maps to an INV or AC; every AC appears in a W row; every §12.3 row serves an FR or NFR; every EC has a guard or is accepted; the CREATE count (2) equals the §8.4 budget.

## Approaches weighed

1. **The approval-handler shape.** I chose a constructor keyword, `CodexHost(approval_handler=...)`, with an async handler bridged the way dynamic tools are. The runner-up was `set_codex_approval_handler`, the name the shipped D-16 used. I rejected it for three reasons:
   - the router is built with the client in `__aenter__`;
   - a setter needs open-host, loop and swap rules, plus a lock read on the SDK reader thread;
   - nobody asked for a runtime swap.

   A sync handler was rejected because developer code would block or crash the only reader thread.
2. **Where the USER-reviewer refusal lives.** It moves from record construction to preflight step 0, active only without a handler. The alternative was a record flag such as `allow_user_reviewer`, which is a new knob that duplicates information the host already has.
3. **The smaller design** (§8.3): always decline, no handler, no logging, no forget. It fails the orchestrator's slice-1 scope (P0 handler, X7) and the user's "all layers" bar.
4. **The second smaller variant**: keep reviews in host.py. That puts host.py at about 1,010 lines, which breaks AGENTS.md §3. I chose `CodexReviews` in a new module and confirmed by grep that no test references the moved private methods.
5. **X4.** Reuse the SDK's `retry_on_overload` inside the existing `wait_for`, for four idempotent typed reads. A raw `request_with_retry_on_overload` path would drop typed validation. A hand-written loop would need an S064 deadline and duplicates a canonical helper.
6. **X7.** An explicit `forget_codex_turns` instead of an LRU cap. A cap would silently break codex-host INV-23, because handles would vanish.
7. **The `retryable` property.** A property derived from the classification table, rather than a constructor field. The property needs a function-level import: a module-level import from `lib/errors/base.py` would create a runtime cycle through the `vidbyte.lib.enums` package init, which imports `native_threads`, which imports `lib.errors`.

## Where I disagree with the scout or the request (with evidence)

1. **"X4: no retry anywhere".** Not every call lacks a retry. Non-spending raw calls already retry through `request_with_retry_on_overload` (connection.py `raw`). The gap is only the typed calls, and four of them are safe to retry. The spending typed calls (`thread/start`, `thread/resume`, `thread/fork`, `turn/start`, steer, compact) must stay single-attempt. They are not idempotent, and request.md's "safe to retry" is unverified for them (scout §"What the likely-areas list got wrong").
2. **"`thread/read` errors are all not found" is not simply wrong.** The fake answers an unknown id with -32600 and a malformed id with -32602, and a pinned test expects -32602 to end a lineage walk. So D-8 keeps both InvalidRequest and InvalidParams as not found and moves everything else to api_error or protocol_mismatch. The scout framed the whole mapping as the defect.
3. **"S7: review model and effort."** Not possible through the protocol: `ReviewStartParams` is `{threadId, target, delivery}` in 0.163.0. I specified Vidbyte-side caps only (FR-24, NG-9).
4. **"Add `config.py` to the touched files" (the scout).** Not needed. The new turn fields go on `CodexSpawnRequest`, not `CodexTurnSettings` (D-17). `CodexHarnessAgent` and its 1,205-line `dataclasses/codex.py` therefore change only by the effort enum and `client_version`, and `vidbyte/agents/codex/config.py` is untouched. The two new efforts flow through the shared enum mapping.
5. **"The tools need the new settings" (implied by the "first class" framing).** No. The orchestrator's decision is that tools never widen approvals or the sandbox, and that the tier is developer-only. Every new knob is library-only (NG-3), and each exposure is a Q with default no (Q-9, Q-10, Q-13, Q-14).
6. **"A new failure code for lost turns."** Not needed. Two tests pin the code slots (exactly four between TURN_TIMED_OUT and INPUT_EMPTY), and every new failure fits an existing code (D-27).
7. **The scout's file list included `enums/failure.py`.** It is not touched, because no new code is added.

## Assumptions I am least sure of (in order)

1. **A-5.** Codex's runtime reaction to `{"answers": {}}`, `{"permissions": {}}` and `{"action":"decline"}` is schema-valid but was never run. If Codex treats empty answers as an error, the turn fails instead of continuing. That is still fail-closed.
2. **A-1 and A-2.** The real binary's error codes for `thread/read` of an unknown id, and for `turn/steer` on an ended turn, come only from the fake. If they differ, D-8 and INV-6's second half need one more code.
3. **A-3.** Retrying `thread/name/set` is idempotent; the other three methods are pure reads.
4. **A-9.** A fork of a thread with an active goal, sent without `deferGoalContinuation`, auto-continues the goal on the fork. This is inferred from the schema text alone (EC-28, Q-8).
5. **A-11.** `inspect.iscoroutinefunction` coverage of `partial` objects and callable objects. A false refusal is loud (ConfigurationError at construction), never silent.
6. **A-12.** Tier ids from `model/list` are the values `serviceTierForTurn` accepts.

## Notes for the next agents

- **For S2.**
  - The 17 superseded tests in §13 come in groups A, B, C and G. Seven support literals change with them.
  - The live module is S2's (FR-17, D-28). It must gate on the env var plus the SDK plus `shutil.which("codex")`, and it must never print `account/read` fields.
  - The fake's `_thread_fork` ignores `beforeTurnId`, so S6 tests assert the sent params.
- **For S3.**
  - Phases P1–P4 are in §12.6. Removing the two approval constants must land in the same commit as the router (P2). Removing the record's USER raise must land in the same commit as preflight step 0 (P3).
  - The rule most likely to be broken: a module-level import of `vidbyte.lib.constants` in `lib/errors/base.py`. It causes a runtime cycle (D-6).
  - The second most likely: forgetting to insert the new constants before `"CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT"` in `__all__`.

---

## Addendum — r2 (review round 1, stacked on #1178)

Spec commit: `2b6affc1` (r2, `status: draft`). New base: `8baff3514640a5c5f110c1e2c7cea996d1640ecb` (#1178 head). Where this addendum and the r1 text above disagree, the addendum wins.

### What changed, one line each

1. Re-grounded on #1178: every `path:line`, symbol and file length in §11–§13 re-verified by script (152 citations). Three r2 drafts were off and were corrected: `_open` `:176-218`, the preflight methods `:69/:116/:132/:139`, `_reject_bad_goal` `:227`.
2. request.md §B.1 recorded as D-31…D-33 ("user decision, #1055 review", comment ids verified against request.md); the stacking is D-34 (orchestrator decision); INV-47, INV-48, NFR-11, AC-40, AC-41 and W-14 enforce them.
3. Every new value moved to `vidbyte.lib.constants.codex_host` (9 constants and 11 messages, sorted `__all__`); `vidbyte.lib.constants.codex` only changes three values and loses two names. Nothing new under `vidbyte/harnesses/native/` (C021 baseline 0).
4. Errors use the packet; r1's `" Thread: <id>."` suffix is gone. X1's mapper half is already fixed by #1178, so INV-1 is now a regression guard and X1's remaining half is the orphan-registration cleanup (INV-26, INV-28, D-11).
5. Inputs follow #1178's records: `CodexHostSetup` is new; `CodexForkRequest`, `CodexThreadListRequest`, `CodexReviewRequest`, `CodexSkillListRequest` and `CodexGoalRunRequest` are extended in place; `forget_codex_turns` uses `CodexThreadRef`. r1's `reject_list_arguments` and the preflight goal-field check are dropped.
6. R-2: a local `CodexPreflight.reject_user_reviewer` makes "refused before any request" literal for spawn, continue, launch, fork and the three run wrappers.
7. R-3: new `CodexCommandApprovalKind`; `CodexServerRequest` gains `approval_kind`, `approval_id`, `environment_id`, `started_at_ms`; `available_decisions` is tri-state; the §4 snippet checks `approval_kind`.
8. R-4: `retryable` reads a code-by-code set `CODEX_HOST_RETRYABLE_CODES` (no `fork_failed`, `process_exited`, `turn_timed_out`).
9. R-5: the router keeps `_closed`, `_pending` and the handler under one lock; `cancel_pending` closes it first at close and death; EC-3 rewritten.
10. R-6: the lost-turn path waits `CODEX_HOST_LOST_TURN_GRACE_SECONDS` (0.5 s), re-checks, interrupts, and only then logs and finishes (A-14).
11. R-7 → NG-20 and FR-36; R-8 → `fork_point` newest-first, tri-state; R-9 → §13 names the AC-7/8/9 seams and row 12 imports the tool-call timeout by name; R-10 → both new collaborators are imported inside `_open`'s existing import `try`.
12. R-11 → Q-18, not built. New Q-19 (the spawn tool's goal path refuses a non-default `spawn_defaults.turn`; T1 is superseded for that).
13. Wrapper errors now rewrite the message head as well as the operation field (`CodexErrorMapper.relabel` + `CodexAgentError.with_operation`), because a changed field with the old head would contradict the packet.
14. Size: the host module is 919 lines at base (#1178 added 26). Moving reviews alone left it near 920, so turn events move to a new `CodexTurnEvents` and the fork body to `CodexThreadHelpers.fork`; estimate about 890, ask-first at 940. Budget: 3 new files, 13 classes, 9 config keys.
15. §13 re-derived: 20 superseded tests (A1–A8, B1, C1–C3, G1–G5, I1, I2, T1). I1 and I2 are #1178's own boundary and baseline tests; T1 is new because the tool's goal call runs with a turn posture.

### R-n dispositions

R-1 accepted (stack + conventions); R-2 accepted (the reviewer's alternative); R-3, R-4, R-5 accepted; R-6 accepted and strengthened (grace + re-check; the reviewer's minimal fix is D-9's runner-up); R-7, R-8, R-9, R-10 accepted; R-11 deferred to Q-18 (default no). Review notes V-1 (D-6's import path) and V-2 (G-3 wording) accepted. All are in spec §16.

### New evidence

- **D-6 import experiment.** In a copy of the tree at the new base, a module-level `from vidbyte.lib.constants.codex_host import ...` in `lib/errors/base.py` imports cleanly, and `import vidbyte` still works. r1's cycle claim (and the reviewer's alternative reason) are both wrong; the import stays function-level as a coupling choice only. The r1 "Notes for S3" bullet about a runtime cycle is withdrawn.
- **`_open`'s SDK imports sit in one `try` that maps `ImportError` to the missing-SDK error** (`host.py:180-188`), so the new collaborators belong in that block.
- **`codex_host_inputs` already imports private helpers from `codex_host`** (`_reject_bad_seconds`, `_reject_small_int`), which is the precedent for sharing `_reject_goal_fields`.
- **`test_codex_host_tools.py:310`** runs a goal call with `_defaults()`, whose `turn` is non-default, so INV-34 changes its result (T1).
- **The pinned `__all__` tail of `vidbyte.lib.constants.codex` starts at `:626`, and the removed names sit at `:609-610`.** With nothing added to that module, the r1 note about inserting before the tail no longer applies.

### Stage E self-check (r2)

- Traceability: 48 INV, 41 AC, 37 FR, 11 NFR, 55 EC, 14 W, 6 T, 34 D, 18 Q, 15 A. Every FR except FR-36 (docstrings only, proved by AC-39) cites an INV; every INV below 41 is in an FR; INV-47/48 are covered by NFR-11; every AC is in a W row; every §12.3 row serves an FR/NFR.
- 3 CREATE rows = §8.4. Names agree across §4, §8.5 and §12.3. All tables have consistent cell counts.
- All 28 test ids in §13 resolve by AST at the new base. 126 cited existing identifiers grep-confirmed.
- No file paths in §1–§10 other than wire methods, request.md/AGENTS.md references and literal values. §0.1 is byte-identical to r1. 0 blocking Qs.

### Least-sure assumptions (r2 order)

1. **A-5** (runtime reaction to the empty and decline answers), unchanged.
2. **A-14.** A death reaches the liveness monitor within the 0.5 s grace. Not measured; if wrong, one refused interrupt is attempted (no behaviour change).
3. **A-15.** Codex accepts `decline`/`cancel` when a present `availableDecisions` omits them.
4. **A-13.** #1178 does not change before it merges; if it does, the implementer re-reads §11 and reports BLOCKED on conflicts.
5. **A-1/A-2**, as in r1.

### Notes for the next agents (supersede the r1 notes above)

- **S2:** 20 superseded tests plus the support literals listed in §13; build handler hosts as `CodexHost(settings, approval_handler=...)` like `open_host`; patch the grace in the `turn_events` module and the tool-call timeout via `patch_connection` once row 12 lands.
- **S3:** the rule most likely to be broken is C021 — run `git add` then `python lint/run.py --rule C021` after every phase. The second is the order pins: `FORGET_CODEX_TURNS` before `START_CODEX_REVIEW`, and `forget_codex_turns` defined before `start_codex_review`. Do not restyle #1178 code (NG-21); merge `origin/main`, never rebase (D-34).

---

## Addendum — r3 (review round 2, final; spec approved)

Spec commit: `804c6f0b` (r3, `status: approved`). The base is unchanged: `8baff351` (#1178, still open). Where this addendum and the earlier text disagree, this addendum wins. One correction to the r2 addendum: it said 126 cited identifiers were confirmed by grep. The correct count is 125, because one of the names checked was a probe the spec does not cite.

### What changed, one line each

1. **R-12 (Major), accepted.**
   - Fork now gates `before_turn_id` and `defer_goal_continuation` locally on `CodexClientSettings.experimental_api`, mirroring `_tool_bridge`. The gate is INV-28 step 1, via a private host helper `_reject_experimental_fork_fields`.
   - New lib message `CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE`, which brings the new messages to 12.
   - New EC-56 and an AC-22 clause. D-19 and §8.5 seam 2 now name both halves of the experimental pattern (inject after validation, and gate locally). The `collaborationMode` note for slice 2 says the same.
2. **R-13, accepted.** INV-17 states the lock's span: check, parse, schedule and add only. The lock is released before `future.result()` and taken again in the `finally`. INV-21 and row 12 cancel a snapshot, `tuple(self._pending)`.
3. **R-14, accepted.** `start_codex_review` substitutes `CodexSpawnRequest()` only when `request is None` (INV-30, row 19). The sibling `x or CodexSpawnRequest()` call sites are left as #1178 wrote them (NG-21).
4. **R-15, accepted.** §9.1 lists every mapping from absent or null to a default. EC-4 is narrowed to missing ids, wrong types and an unknown `kind`. AC-11 gains the `options: null` clause.
5. **R-16, accepted.** Only a cached model list is refreshed (INV-25, D-26). AC-20 gains the fresh-host case: exactly one `model/list` walk.
6. **R-17, accepted.**
   - A-10 is restated: every goal run ends with one `_GoalStreamClosed` watcher failure, after its snapshot is set.
   - INV-13 step (a) runs first, with no wait. Finishing a goal run before closing its stream is stated as an order every path must keep.
   - AC-8 gains a clause for a goal run that ends normally.
7. **Author-found.** `currentTime/read` is in the experimental schema only, and §9.3 says so. The answer is unchanged.
8. **Status and estimates.** `status: approved`, revision 3, a §17 r3 row, and §16 rows for R-12…R-17 plus the author note. The host-module estimate moves from about 890 to about 900 lines (ask-first stays at 940).

Nothing was disputed, so no new Q was added. Q-20 stays unused.

### New evidence (r3)

- **Stable versus experimental schema, 0.163.0.** I generated both with `codex app-server generate-json-schema --out <dir>`, once with and once without `--experimental`.
  - `ThreadForkParams` has `beforeTurnId` and `deferGoalContinuation` only in the experimental output. The `s0-schema-0163` bundle that r1 and r2 cited was the experimental one.
  - `currentTime/read` and `currentTimeAt` are experimental-only.
  - The other fields this slice sends are in the stable schema: `serviceTierForTurn`, `networkAccess`, `writableRoots`, `forceReload`, the `thread/turns/list` fields, `serviceTiers`/`defaultServiceTier`, and the approval fields `approvalId`, `environmentId` and `startedAtMs`.
  - `ReasoningEffort` is an open string ("a non-empty reasoning effort value advertised by the model"), so `max` and `ultra` need no gate.
- **The stable `ToolRequestUserInputQuestion`.** It requires only `header`, `id` and `question`. `options` is `["array","null"]`, and `isOther` and `isSecret` default to false. The params require `isBlocking`, `itemId`, `questions`, `threadId` and `turnId`.
- **Goal-stream closing.** openai-codex's `_GoalOperationState.next_notification` raises any queued exception, and `wake_notification_reader` queues `_GoalStreamClosed()`. Every goal-ending path in the host module finishes the turn before it calls `close_goal_stream`. Those paths are at `host.py:250, 762, 798, 887, 915`.
- **The fake has no model of the experimental capability.** Nothing in `codex_host_fakes.py` mentions "experimental". The only test that builds a host with `experimental_api=False` is `test_codex_host_threads.py:444`.

### Stage E self-check (r3)

- **Counts.** 48 INV, 41 AC, 37 FR, 11 NFR, 56 EC, 14 W, 6 T, 34 D, 18 Q, 15 A.
- **Tracing.** Same result as r2: only FR-36 has no INV, by design.
- **Structure.** 3 CREATE rows, which equals §8.4. Names agree across §4, §8.5 and §12.3. Every table row has its header's cell count.
- **Test ids.** All 28 resolve.
- **Paths and §0.1.** No new file paths in §1–§10. §0.1 is identical to r1.
- **Questions.** 0 blocking.

### Notes for S2, the test author (supersede the earlier notes)

- **Contract names.**
  - The handler: `CodexHost(settings, *, approval_handler=...)`.
  - The records: `CodexServerRequest`, `CodexServerAnswer`, `CodexUserInputQuestion`, `CodexUserInputOption`, `CodexUserInputAnswer` and `CodexServiceTier`.
  - The enums: `CodexServerRequestKind`, `CodexApprovalDecision` and `CodexCommandApprovalKind`.
  - Other new names: `forget_codex_turns`, `CodexAgentError.retryable` and `.with_operation`, and the log events `codex_host_call`, `codex_host_call_failed`, `codex_host_server_request`, `codex_host_server_request_fallback`, `codex_host_turn_item`, `codex_host_turn_ended`, `codex_host_turn_event_failed`, `codex_host_turn_lost` and `codex_host_tool_failed`.
- **Seams.**
  - Send server requests with `HostTestCase.ask`.
  - Handler-timeout tests use `patch_connection("CODEX_TOOL_CALL_TIMEOUT_SECONDS", ...)`.
  - Patch the grace in `vidbyte.harnesses.native.codex.turn_events`.
  - AC-8: patch `server.client.next_turn_notification` or `next_goal_notification` before the spawn.
  - AC-7: patch `CodexResponseTranslator.turn_snapshot` or `goal_snapshot`.
  - AC-9: make `stored_turn` return None first and raise second.
  - For the experimental gate, use `open_host(CodexClientSettings(experimental_api=False))` and assert that zero requests are sent.
- **What the fake cannot show.**
  - It ignores `beforeTurnId` and `deferGoalContinuation`, and it never refuses an experimental field.
  - It does not handle server-request methods; those are sent to the client.
  - It answers an unknown method with -32601.
- **The 20 superseded tests.** A1–A8, B1, C1–C3, G1–G5, I1, I2 and T1, plus the support literals listed in §13.

---

## Addendum — r4 (S2 clarifications; status stays approved)

Spec commit: `d3389171`. This revision changes spec text only. No file under `tests/` was touched, nor `test-plan.md`, nor the §6.2 Proof column; a script confirmed the Proof column is byte-identical to `f5dbb7cc`.

**What changed.** Each S2 defect (S2 report §6) is resolved, and every test choice was kept:
- **Misstatements corrected (1, 2).**
  - AC-22 and B1 now say `includeTurns` is never true. openai-codex `thread_read` always sends `{"threadId", "includeTurns": include_turns}`.
  - AC-32 and INV-37 now name the three keys and say every other key is `false`. The stable 0.163.0 `workspaceWrite` policy defaults `excludeSlashTmp` and `excludeTmpdirEnvVar` to false.
- **Choices recorded.**
  - 3: the INV-37 checks run before the goal rule. Either message conforms if it names the field.
  - 4: `{sandbox}` is the member name. The value would render `PROVIDER_DEFAULT` as an empty string.
  - 7: sandbox fields on fork, review and goal runs are refused at `turn` first.
  - 8: a pending call cancelled by `cancel_pending` logs `closing`.
  - 9: `handled_by` is `default` whenever the default answer was sent.
  - 10: `status` is the `CodexTurnStatus` wire value.
  - 11: only a router built with a handler writes the fallback WARNING.
  - 13: how `{tier}`, `{models}` and `{tiers}` render. The values are sorted and joined with `CODEX_HOST_LIST_SEPARATOR`.
- **§13 notes (5, 6, 12, 14).**
  - AC-39 is proved by keyword checks.
  - AC-40's lint half is a command; an `ast` scan stands in for it.
  - The tests use 0.2 s for AC-25 and an absolute path for AC-27.
  - AC-20's fresh-host row guards only against a double walk.
- **Test-imposed names**, now in INV-10, §8.5 and §13:
  - the watcher thread name `"codex-host-watcher"`;
  - the log record shape: the first word is the event, then `key=value` tokens, one token per value, `key=` when empty, and no `exc_info`;
  - three patch names: `turn_events.CODEX_HOST_LOST_TURN_GRACE_SECONDS`, `connection.CODEX_TOOL_CALL_TIMEOUT_SECONDS`, and `connection.retry_on_overload`, which must be openai-codex's own object.

**Schema and protocol check.** No test choice contradicts the 0.163.0 schema or protocol. Choices 4, 8, 9, 11 and 13 are logging and rendering details the schema does not govern. Choices 3 and 7 are the order of local refusals.

**Self-check.** Traceability is unchanged (48 INV, 41 AC, 56 EC, 37 FR). All 47 test ids in §6.2 and §13 resolve. Every table row has its header's cell count. §0.1 is identical to r1, and nothing was added to §1–§10 except my own text.
