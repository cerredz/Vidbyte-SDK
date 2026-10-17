---
slug: codex-host-hardening
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-first-class
branch: feat/codex-host-first-class
base_commit: 8baff3514640a5c5f110c1e2c7cea996d1640ecb  # stacked on PR #1178 (was 6f5a7310, main after #1055)
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1181
until: none
started: 2026-10-17 06:50
---

# Pipeline: CodexHost production hardening and missed settings (slice 1 of 2)

The run has two slices on one branch and ships one PR. Slice 2 (`codex-host-first-class`) gets its own `docs/spec/codex-host-first-class/pipeline.md` and starts after slice 1 reaches the end of S5 (verified). S6 runs once, at the end of slice 2, and covers both specs.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 06:50 | 07:12 | reports/S0-scout.md | base_commit 6f5a7310; code-map 4 sections, 25 files |
| S1 spec + review | done | 07:13 | 10:05 | reports/S1-spec-author.md, reports/S1-spec-review.md | r1 0f0d3118 (FR 37, AC 39, EC 52, W 13; 0 blocking Q); reviewer round 1 SOUND WITH FIXES (836b23ca); r2 2b6affc1 rebased on #1178 (FR+, 3 new files, 20 superseded tests); reviewer round 2 SOUND WITH FIXES (4548f58d, 0 Blocker); r3 804c6f0b status approved |
| S2 tests | done | 10:10 | 11:40 | reports/S2-test-author.md | **S2_HEAD fadec47f** (was 09524ff4; moved by the orchestrator-granted correction of 2 assertions); 106 new tests (97 red, 8 guards, 1 live-skipped), 20 superseded + 7 support literals; red 125F/631P/3S vs baseline 1F/650P/2S; spec r4 (d3389171) aligned to test choices |
| S3 implement | done | 11:45 | 14:20 | reports/S3-implementer.md | **S3_HEAD c9150d63**; draft PR #1181 (base `ai/resolve-pr-1055-comments`, 64 files +9688/−551); 24/24 rows; budget 3 files / 13 classes / 0 deps / 9 config keys (exact); host.py 923; area 1F(inherited)/1024P/3S; source 1F(inherited)/6555P/27S; package CI passed; SDK-LINT: PASS |
| S4 adversarial review | done | 14:25 | 16:10 | reports/S4-review-{conformance,conventions,engineering}.md, reports/S4-findings-verifier.md | review.md: MERGEABLE AFTER FIXES — confirmed 4 Blocker / 6 Major / 7 Minor; refuted 0; downgraded 1 (R-V3). Owners: code R-1,R-2,R-3,R-9,R-10; test R-4,R-5,R-6,R-8; spec R-7 |
| S5 repair loop | running | 16:15 | | verify-log.md, reports/S5-repair-<k>.md | pre-step: spec r5 (R-7 + budget), S2 test additions |
| S5 re-review | pending | | | | |
| S6 PR | deferred to the end of slice 2 | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-17 06:44: Waited for PR #1055 to merge (merged at 2026-10-17T06:44:08Z as `6f5a7310`) before creating the worktree, per Prompt 3.
- 2026-10-17 06:50: **Scope.** "The codex functions that you thought about" = the P0 and P1 proposals plus the settings gaps S1–S10. The user's stated bar ("all layers … exception handle everything", Prompt 2) also brings in the §C.9 production gaps (X1–X9 and the per-function table), because new and old functions share the same connection, errors, registry and tool base. P2 is not built (Q, default no). The user can interrupt.
- 2026-10-17 06:50: **Two slices on one branch and one PR**, following the #1055 precedent (two specs in one PR). Slice 1 = hardening + settings + the approval/user-input handler (X6/S5) + X7 eviction. Slice 2 = the remaining P0/P1 new functions. This keeps each spec at the size the pipeline has handled before (#1055's two specs: 15 and 12 functions).
- 2026-10-17 06:50: Ran `git branch --unset-upstream` on `feat/codex-host-first-class`. `git worktree add -b … origin/main` had set the upstream to `origin/main`, and a bare `git push` would have targeted main. Every push must be `git push -u origin feat/codex-host-first-class`.
- 2026-10-17 06:50: Committed the research subagent's outputs as context: `context/codex-gap-report.md` and `context/coverage-matrix.md`, from the codex-cli 0.163.0 schema.
- 2026-10-17 06:50: The PR #1044 round-2 comments run as a separate, parallel subagent that only posts comments. It is not part of this pipeline.
- 2026-10-17 08:10: PR #1044 round 2 posted and verified with `gh api`:
  - top-level comment issuecomment-6231230416;
  - review 5556842425, state COMMENTED, 26 inline comments all anchored RIGHT at head 6ff98295;
  - no email or key in either;
  - the user's checkout untouched.
  
  Nothing else in this run touches #1044.
- 2026-10-17 08:17: Accepted the S1 author's move of **S4 (`collaborationMode`/plan mode) into slice 2** (spec NG-1). §C.10 lists `collaboration_mode` among the P0 plan-mode functions, which are slice 2. **Slice 2's request.md must name S4 explicitly as carried over from slice 1.**
- 2026-10-17 08:55: **Stacked the run on the user's open PR #1178** (`ai/resolve-pr-1055-comments`, head `8baff351`, one commit on top of `6f5a7310`, MERGEABLE, not a draft).
  - *Evidence:* the S1 reviewer's R-1, which I checked myself with `gh pr view 1178` and the five #1055 review comments.
  - #1178 applies the user's own #1055 review comments (now verbatim in request.md §B.1) to 11 of the 21 files in spec r1 §12.3, and adds lint C021 at baseline 0. Building on bare main would conflict in all 11 and fail C021 once #1178 merges.
  - Done with `git rebase --onto 8baff351 6f5a7310`. Docs-only commits, no conflicts. The local tag `pre-stack-backup` marks the old head; it is local only and never pushed.
  - When #1178 merges, bring main into the branch with `git merge origin/main`, never rebase plus force-push.
  - At S3, open the PR with base `ai/resolve-pr-1055-comments` while #1178 is open. GitHub retargets it to main when that branch is deleted on merge. Otherwise retarget it with `gh pr edit --base main`.
- 2026-10-17 08:55: S1 review round 1 returned SOUND WITH FIXES: 1 Blocker (R-1, #1178 conventions), 4 Major (R-2 to R-5), 6 Minor (one scope-adding, Q-18). All of it was forwarded to the author as one revision, together with the rebase.
- 2026-10-17 09:40: S1 review round 2 is focused on what r2 reshaped: §8, §8.4, §8.5, §9, §12, §13, plus INV-47/48, NFR-11 and AC-40/41. The playbook requires another round when §8, §8.5 or §12 change. This is the last allowed round (2/2), and whatever is still disputed afterwards becomes a Q-n with its default. PR #1178's head was re-checked and is still `8baff351` (open).
- 2026-10-17 10:05: Spec r3 approved after 2 review rounds (cap reached; nothing disputed). The open questions take their defaults:
  - Q-1: no P2;
  - Q-2: `VIDBYTE_CODEX_LIVE_TESTS=1`;
  - Q-3: unresolved, nothing depends on it;
  - Q-4/Q-5: permissions and elicitations keep their fixed refusals;
  - Q-6 to Q-12 and Q-15 to Q-18: no;
  - Q-13: tiers shown read-only in the `list_codex_models` tool;
  - Q-14: `max`/`ultra` stay in the tools' effort enum;
  - Q-19: refuse, never drop.
- 2026-10-17 10:08: **Test and gate interpreter = an isolated venv** at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/venv-codex163`. It holds `pip install -e ".[dev]"` from the worktree, plus `openai-codex==0.163.0`.
  - *Why the venv:* the installed 0.162.1 models lack `ModelListParams.forceReload` and `ThreadStartParams.serviceTierForTurn`, which the spec sends as stable 0.163.0 fields (S10 raises the pin). Under 0.162.1 they would be silently dropped, and the tests could never go green.
  - *Why not global:* the global env has `vidbyte-sdk` as an editable install pointing at the user's main checkout, plus openai-codex 0.162.1. A `pip install -e` from the worktree, or an SDK upgrade, would rewire or break the user's checkout. Neither was done; both were verified untouched.
  - **No stage may run `pip install` against the global interpreter.**
  - Baseline in the venv at `fba99efd`: `tests/features/codex_host` + `tests/features/harness_threads` = 650 passed, 2 skipped, 1 failed (inherited `harness_threads:193`).
- 2026-10-17 10:10: The S2 briefing authorizes the test author to edit exactly the 20 superseded tests and 7 support literals in spec §13, each to the behaviour its spec ID defines, every edit listed in test-plan.md. The template's "never modify an existing assertion" rule otherwise stands. *Reason:* the implementer may not touch tests, so §13's supersessions can only land at S2. S3/S5 then diff the test tree against S2_HEAD.
- 2026-10-17 11:40: Checked S2 myself:
  - every test edit is in a §13-named file;
  - no test was removed or skipped;
  - the red run reproduced (`test_codex_host_approvals.py` gave 11 failed);
  - all 41 ACs are in the test plan;
  - no production file was touched.
  
  The S2 agent's harness refused its report-file write ("Subagents should return findings as text, not write report files"), so I saved its inline report verbatim to `reports/S2-test-author.md`. **Every later briefing tells the agent to return the report inline if the write is refused.**
- 2026-10-17 11:40: S2 listed 14 non-blocking spec defects, where the tests chose details the spec left open. I sent them to the S1 author as a clarification-only revision (r4, `d3389171`) so the S4 conformance reviewers judge the code against a spec that matches the tests. No test, test-plan or Proof cell changed (verified by diff). No reviewer round was run, because nothing in §8 architecture or scope changed. I then set `status: tests-written`.
- 2026-10-17 11:45: S3's PR base is `ai/resolve-pr-1055-comments` while #1178 is open (see the 08:55 decision). Its drift check compares against `origin/ai/resolve-pr-1055-comments` (has #1178 moved?) and `origin/main` since `6f5a7310` (has main moved under the touched paths?), not against `origin/main` alone.
- 2026-10-17 13:30: **S3 BLOCKED on 3 source-stage failures. I adjudicated them myself, by running the tests and reading only the cited lines.**
  1. **Inherited, accepted (already decided):** `harness_threads` surface :193 (expects 120 FailureCode members, finds 167). It fails the same way on main and on #1178.
  2. **GRANTED, a test that contradicts the spec:** `test_codex_host_function_rows.py:85` asserts `details["field"] == "thread_id"`.
     - AC-41 requires only that `details["field"]` is set.
     - D-33 makes `forget_codex_turns` reuse #1178's `CodexThreadRef`, which labels the field `"forget_codex_turns thread_id"`.
     - S2's own I1 row (`test_codex_host_inputs.py:198`) and its `_field_named` helper (`test_codex_host_hardening_contract.py:110`, which accepts the bare or `"<method> <field>"` form) agree with D-33.
     - The run shows `'forget_codex_turns thread_id' != 'thread_id'`.
  3. **GRANTED, an assertion no correct implementation can pass:** `test_codex_host_approvals.py:463` asserts `reader_errors == []` after close.
     - The run shows `[TransportClosedError('Codex process closed stdout. stderr_tail=')]`, which is the SDK reader's normal EOF when close ends the process (the fake records it at `codex_host_fakes.py:521-525` on every close).
     - The test's intent, INV-15/16 "the router never raises on the reader thread", is already asserted while the host is open (approvals :183/:204/:295/:345, router :75, resilience :86).
  
  Both edits go to the S2 test author, who resumes narrowed to those two assertions. S2_HEAD moves to its fix commit.
- 2026-10-17 13:30: S3's commits cite W-/FR-/AC-/INV- IDs in the commit **bodies** ("Row 20 (P3): … FR-25, INV-31, D-22, AC-26"), not in a `[W-n]` subject tag. Commit `91cc7d4d` bundles several rows. Both were accepted as traceable; there was no history rewrite before the first push. The conventions reviewer may still comment on them.
- 2026-10-17 14:20: Checked S3 myself:
  - the tree is clean and in step with origin at `c9150d63`;
  - `git diff fadec47f..HEAD -- tests` is empty, and `lint/` is unchanged since 8baff351, so no baseline moved;
  - PR #1181 is a draft, its title starts with `[WIP]`, and its base is `ai/resolve-pr-1055-comments`;
  - the spec has `status: implemented` and `pr:` set;
  - my own run of the area suite gave 1 failed (inherited), 1024 passed, 3 skipped, and my own `lint/run.py` ended `SDK-LINT: PASS`.
- 2026-10-17 14:20: **Correction:** the lint runner's final line is `SDK-LINT: PASS`. `AGENT-LINT` does not exist under `lint/`; earlier briefings said otherwise. The global `semgrep` CLI is broken here (mcp 2.x), and `lint/run.py` does not call semgrep. S3 used the bundled `semgrep-core.exe` per changed file: 0 results on 23 files, and 1 on a file planted to break the rule. Accepted as the semgrep evidence. Nothing was installed or repaired.
- 2026-10-17 16:10: S4 checked. `review.md` has 10 confirmed rows, each with a path:line, own evidence and status `open`; nothing was refused. Spec `status: reviewed`. **Routing plan, so each role stays separate:**
  1. **Spec author r5:**
     - R-7: the `run_codex_goal` refusal must name the method. §9.2's text contradicts INV-48 and §8.5's `owner` argument.
     - The §8.4/§9.2 budget amendments the verifier says the code fixes need: config keys 9→10 and messages 12→13 for R-2; classes 13→14 for R-9's log-token helper in the existing `vidbyte/lib/util/text.py`.
     - R-10's stated limitation: calls refused before sending stay unlogged.
     - Pre-authorising the budget now avoids a predictable S5 BLOCKED. Every amendment traces to a confirmed finding of the user's own bar, so none of it adds scope.
  2. **S2 test author:**
     - mutant-killing tests for R-4 (M40), R-5 (M1), R-6 (M31) and R-8 (M2/M20/M21), each proven with the engineering reviewer's mutation plugin;
     - regression tests for R-3, R-9 and R-10, plus the two R-7 text pins (`turn_settings.py:59`, `hardening_contract.py:286`) updated to spec r5.
     
     The new S2_HEAD then follows.
  3. **S5 repair loop:** code fixes for R-1, R-2, R-3, R-7 (code side), R-9 and R-10. Minors are fixed only where trivial.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- The feature branch has **no upstream** on purpose. Push with `git push -u origin feat/codex-host-first-class`, never a bare `git push`. *Source:* S0 orchestrator.
- openai-codex's generated Pydantic models drop unknown (experimental) fields. `TurnStartParams.model_validate({..., "collaborationMode": ...})` returns no `collaborationMode` (verified with SDK 0.162.1). Experimental fields must be added to the params dict after `model_dump`, as `dynamicTools` is. *Source:* conversation verification.
- The typed `CodexClient` methods (`thread_start`/`thread_read`/`thread_list`/`account_read`/`thread_compact`/`turn_steer`) call `self.request(...)` with no overload retry. Only `request_with_retry_on_overload` retries. *Source:* conversation verification of `openai_codex/client.py`.
- `CodexErrorMapper.error(..., thread_id="thr_123").thread_id == ''` (reproduced at `ea473f63`). *Source:* conversation verification.
- Every slice-1 item (X1–X9, the per-function rows, S1–S10) is still present at 6f5a7310, each cited with path:line in code-map §4. X1, X4, X5, X6/S5 and X8 were reproduced in-process. *Source:* S0
- openai-codex runs the approval handler synchronously on its single reader thread (client.py:869-870). It cannot send a JSON-RPC error, and any exception reaches `except BaseException` → `fail_all` and kills the host. Copy the pattern in `vidbyte/agents/codex/tools.py:150-190`. *Source:* S0
- X4 must not call `client.request(...)` directly: lint S012 has a baseline of 0 and codex-host D-2 forbids it. Reuse `request_with_retry_on_overload` / `retry_on_overload`. The bound in `connection.call` already wraps the whole retry loop. *Source:* S0
- X5 (D-13, thread-helpers INV-16) and X7 (EC-65) are accepted behaviour in the shipped specs, and tests pin both. The new spec must supersede those IDs explicitly. *Source:* S0
- D-16's claim of "no decline decision" is wrong: the schemas of both binaries have `decline` and `cancel`. `review/start` accepts only threadId, target and delivery, so S7 cannot pass a model or effort through the protocol. *Source:* S0
- `collaborationMode`, `beforeTurnId` and `deferGoalContinuation` must be added after validation. `serviceTierForTurn` and the workspaceWrite options (`networkAccess`, `writableRoots`) are stable SDK fields and need no injection. *Source:* S0
- Test pins that move with this slice:
  - `CodexHostOperation` must end with exactly the 12 helpers;
  - exactly 4 codes may sit between TURN_TIMED_OUT and INPUT_EMPTY;
  - the `CodexAgentError` details dict must match exactly;
  - the router answers accept / `{}`.
  
  A custom pytest marker fails under `--strict-markers`, since no markers are registered. *Source:* S0
- CodexHost launches the PATH `codex` 0.163.0. The wheel's bundled binary and the test fake are both 0.162.1. *Source:* S0
- Size: `lib/dataclasses/codex.py` is already 1,205 lines and `host.py` is 893, so new logic goes into collaborators or new modules. *Source:* S0
- Full gate: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH (field guide `local-ci-verification.md`). Semgrep scans only tracked files, so run `git add` first. *Source:* S0
- Remote CI: `.github/workflows/ci.yml` automatic triggers are TEMPORARILY DISABLED (workflow_dispatch/workflow_call only). It installs no codex extra, so the host tests run only locally. *Source:* S0
- A pre-existing failure, independent of this slice: `tests/features/harness_threads/test_harness_threads_surface.py:193` expects 120 FailureCode members and there are 167. Classify it as inherited. *Source:* S0
- **Contract names** (spec r1 §4/§8.5):
  - `CodexHost(approval_handler=async fn)`, set when the host is built;
  - enums `CodexServerRequestKind`, `CodexApprovalDecision`, `CodexReasoningEffort.MAX/ULTRA`, and `CodexHostOperation.FORGET_CODEX_TURNS`, placed before `START_CODEX_REVIEW`;
  - records `CodexServerRequest.from_params`, `CodexServerAnswer`, `CodexUserInputQuestion/Option/Answer`, `CodexServiceTier`;
  - `CodexAgentError.retryable` (a property) and `ExceptionOrigin.describe`;
  - `forget_codex_turns`.
  
  The budget is 2 new files, `harnesses/native/codex/reviews.py` and `lib/util/exception_origin.py`, with no new FailureCodes. *Source:* S1 author
- `lib/errors/base.py` must import `CODEX_FAILURE_CLASSIFICATION` inside the body of `retryable`. A module-level import creates a runtime cycle (vidbyte.lib.enums → native_threads → lib.errors; spec D-6). *Source:* S1 author
- Ordering pins:
  - new constants go in `__all__` before `"CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT"`;
  - `forget_codex_turns` is defined before `start_codex_review`;
  - the helper-surface test pins both orders.
  
  *Source:* S1 author
- Commit pairing:
  - removing the two approval constants lands in the same commit as the router change (phase P2);
  - removing the record's USER raise lands in the same commit as preflight step 0 (phase P3).
  
  *Source:* S1 author
- Retry uses `openai_codex.retry.retry_on_overload` inside `CodexConnection.call`, and only for `CODEX_HOST_RETRIED_METHODS` (account/read, thread/read, thread/list, thread/name/set). *Source:* S1 author
- Test seam:
  - patch `connection.CodexClient` with the fake, and drive server requests through `HostTestCase.ask`;
  - never mock the router, mapper or retry helper;
  - the fake's `_thread_fork` ignores `beforeTurnId` and `deferGoalContinuation`.
  
  *Source:* S1 author
- Spec §13 lists **17 superseded tests** (groups A, B, C, G) and 7 support literals. Only S2 may change them, and only those listed. *Source:* S1 author
- Least-sure assumptions (spec §15):
  - A-5: Codex's runtime reaction to the fail-closed defaults was never run;
  - A-1/A-2: the real error codes for an unknown-thread read and an ended-turn steer come only from the fake;
  - A-3: retrying `thread/name/set` is safe;
  - A-9: fork auto-continues a goal unless `deferGoalContinuation` is set.
  
  *Source:* S1 author
- **The base is #1178's head `8baff351`, not main.** New files on it:
  - `vidbyte/lib/constants/codex_host.py` (342 lines), where every native-host constant and message lives;
  - `vidbyte/lib/dataclasses/codex_host_inputs.py` (372 lines, 16 input records, `REJECTED_FIELDS` moved in);
  - lint `lint/rules/c021_native_host_constants_in_lib.py`, which blocks top-level UPPER_CASE bindings under `vidbyte/harnesses/native/`, with a baseline of 0.
  
  `host.py` is 919 lines and `lib/dataclasses/codex.py` 1,205. *Source:* orchestrator check after S1 review
- The error format since #1178 is "`<operation> failed with <code>. <summary> The thread id was <id>. Likely cause: <cause> Next step: <step>`", built through `CodexAgentError` keywords (`likely_cause`, `method`, `related_docs`, `relevant_tests`) and `with_sentence()`. *Source:* #1178 body, S1 reviewer
- TRANSIENT failure codes in `CODEX_FAILURE_CLASSIFICATION`: `thread_resume_failed`, `fork_failed`, `response_invalid`, `usage_limited`, `session_busy`, `api_error`, `process_exited`, `turn_timed_out`. A `retryable` that only reads the class is wrong for deterministic `fork_failed` refusals and for `process_exited` on a dead host (R-4). *Source:* S1 reviewer
- Server-request wire facts (0.163.0 schema):
  - command approvals require `itemId`, `startedAtMs`, `threadId` and `turnId`;
  - they also carry `kind` (`command`, the default, or `writeStdin`), `approvalId` and `environmentId`;
  - file-change approvals have no `availableDecisions`;
  - `{}` is not a valid answer to the token-refresh or attestation requests.
  
  *Source:* S1 reviewer
- Close order: `host.py` cancels pending work at ~:213 *before* awaiting the cleanup interrupts at ~:215-223, so approvals can arrive after the cancel (R-5). `CodexClient.close` waits at most 0.5 s for the reader thread (`client.py:301-302`). `run_coroutine_threadsafe` raises only on a closed loop. *Source:* S1 reviewer
- Lazy loading: host.py loads connection, turns and wire inside `_open` (~:162-170). Any new module that depends on `turns.py` (for example `reviews.py`) must load the same way, or importing the package loads the SDK and fails the packaging test. *Source:* S1 reviewer
- Test patching:
  - watchers bind `client.next_turn_notification` and `next_goal_notification` when they start (`turns.py:157-160`), so a test must patch them before the spawn;
  - `patch_connection` patches without `create=True`;
  - `connection.py` does not import `CODEX_TOOL_CALL_TIMEOUT_SECONDS`.
  
  *Source:* S1 reviewer
- Spec r2 contract additions:
  - `CodexHostSetup`, a new input record. `VALID_RECORDS` must equal `__all__` in #1178's `test_codex_host_inputs.py`, and its boundary test (:178) needs a row for `forget_codex_turns`, which uses `CodexThreadRef`;
  - `CodexCommandApprovalKind`, a new enum;
  - `CodexTurnEvents`, which takes host.py's turn-event handling (target ~890 lines; ask-first threshold 940);
  - `CodexPreflight.reject_user_reviewer`;
  - `retryable`, decided code by code (`fork_failed`, `process_exited` and `turn_timed_out` are not retryable).
  
  Budget: 3 new files, 13 classes. *Source:* S1 author r2
- C021 scans only git-tracked files. Run `git add` before `python lint/run.py --rule C021`. *Source:* S1 author r2
- **S2_HEAD = fadec47f** (was 09524ff4). Run `git diff fadec47f..HEAD -- tests` and it must stay EMPTY for S3 and S5; only S2 may touch tests. The granted correction (`fadec47f`) changed exactly `function_rows.py:85` (field label `endswith("thread_id")`) and `approvals.py:463` (`closed == 1`, and every reader error must be the close-time `TransportClosedError`). *Source:* orchestrator
- Exact names the tests patch or identity-check:
  - `turn_events.CODEX_HOST_LOST_TURN_GRACE_SECONDS`;
  - `connection.CODEX_TOOL_CALL_TIMEOUT_SECONDS`, read inside the router's `handle`;
  - `connection.retry_on_overload`, bound with `from openai_codex.retry import retry_on_overload` (`assertIs`, so a wrapper fails).
  
  Watcher threads must be named `"codex-host-watcher"`. *Source:* S2 test author, spec r4
- Log record shape:
  - the event is the first word of a %-style `msg`;
  - single-space `key=value` tokens follow, one token per value, `key=` when empty;
  - no `exc_info`.
  
  Only a router built with a handler writes the fallback WARNING, and it must remember that after `cancel_pending`. `handled_by=default` whenever the default answer was sent. *Source:* S2, spec r4
- `CodexSandbox.PROVIDER_DEFAULT == ""`, so messages render member names. `CodexSpawnRequest.__post_init__` check groups: the sandbox group goes before the goal group. *Source:* spec r4
- 7 "collateral" red tests (in error_details, thread_helpers, threads, turns) go green from the lib §9.3 text changes alone. 8 green guards pass now and must stay green. *Source:* S2
- Gate interpreter: `run_ci.py` uses `sys.executable` for every step, and its package stage makes its own temp venv. Running it with the `venv-codex163` interpreter is fully isolated from the global env. *Source:* orchestrator check of scripts/run_ci.py:82-201
- **S3_HEAD = c9150d63.** S4 reviews `git diff origin/ai/resolve-pr-1055-comments...c9150d63`, never `origin/main`, which would include #1178's 25 files. *Source:* orchestrator
- Lint keeps a separate baseline for each rule, so the focused rules can pass while the full `lint/run.py` fails. S008 allows complexity ≤10 and ≤12 branches; S024 allows nesting ≤3 (try, if and with each add a level, elif does not). Always run the full lint before a push. *Source:* S3
- Semgrep evidence: run `site-packages/semgrep/bin/semgrep-core.exe -rules .semgrep/<rule>.yml -lang python -json <file>` on one file at a time. The global `semgrep` cannot start. *Source:* S3
- `CodexHostOperation.VALIDATE_SPAWN_REQUEST` is now unused in source but pinned by `test_codex_host_records.py:65`, so it was kept. *Source:* S3
- The workflows run only on `workflow_dispatch`, so pushing triggers no remote checks and the local gate decides. *Source:* S3, S0
- Mutation plugin: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/s4-eng/s4_mutants.py`. Run it with `S4_MUTANT=<M> PYTHONPATH="$(pwd);<scratch>/s4-eng" "$V" -B -m pytest tests/features/codex_host -q -p no:cacheprovider -p s4_mutants`; the baseline is `320 passed, 1 skipped`. Mutants run in the module's own globals, because a copied namespace gives false kills. Verifier probes: `<scratch>/s4-verify/probe_s4v_code.py`. *Source:* S4 engineering, verifier
- R-10's fix logs the late landing only on the cancel hand-over. The TimeoutError path already logs, so an unconditional `_land` log would double-record. *Source:* verifier
- R-3's fix wraps `reviews.py:141` the way its sibling paths are wrapped, and renames `CodexTurnEvents._fail` to `fail`. It has 2 callers plus the FILE inventory, and no test references it. *Source:* verifier
- R-9's log-token helper applies to every record that shows a Codex-issued id: `_log_call`, `finish` and the `turn_events` warnings, not just the router. *Source:* verifier
- R-1: re-read the field guide's `comment-format.md` before re-wrapping. Wrapped comments must still keep A002's `@intent` within 20 lines of its `def`. *Source:* verifier
