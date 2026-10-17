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
