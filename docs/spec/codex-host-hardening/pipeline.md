---
slug: codex-host-hardening
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-first-class
branch: feat/codex-host-first-class
base_commit: 6f5a7310c00fa919dac1b1b40f321496298e89da
pr:
until: none
started: 2026-10-17 06:50
---

# Pipeline: CodexHost production hardening and missed settings (slice 1 of 2)

The run has two slices on one branch and ships one PR. Slice 2 (`codex-host-first-class`) gets its own `docs/spec/codex-host-first-class/pipeline.md` and starts after slice 1 reaches the end of S5 (verified). S6 runs once, at the end of slice 2, and covers both specs.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 06:50 | 07:12 | reports/S0-scout.md | base_commit 6f5a7310; code-map 4 sections, 25 files |
| S1 spec + review | running | 07:13 | | reports/S1-spec-author.md, reports/S1-spec-review.md | r1 0f0d3118 (FR 37, AC 39, EC 52, W 13; 0 blocking Q); reviewer round 1 launched 08:18 |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | deferred to the end of slice 2 | | | | |

## Counters and caps
- S1 review rounds: 1/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

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

