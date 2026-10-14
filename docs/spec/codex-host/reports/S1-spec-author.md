# S1 spec author: codex-host

- **Spec:** `docs/spec/codex-host/spec.md`, revision 1, committed as `a1ee792a` on `feat/codex-host` (base `678136bd`). It is the only file in that commit.
- **This report** is not committed.
- **Counts:** G 5, NG 15, INV 42, AC 36, EC 67, FR 30, NFR 10, D 31, T 8, A 13, Q 9 (none blocking), W 20.
- **§12.3:** 28 rows, 17 CREATE and 11 MODIFY. Every AC and FR is served by at least one W.
- **Structure:** 18 `## §` sections; §16 is an empty table, and §17 holds the r1 row.

## What I read

- **Pipeline inputs:**
  - `request.md` (§A–§C);
  - `context/code-map.md`, the S0 scout's map, C1–C24;
  - `pipeline.md`;
  - the spec template from the spec-pipeline skill.
- **House rules:**
  - `AGENTS.md` and `CLAUDE.md`;
  - the `vidbyte/harnesses/` part of `REPO_MAP.md`;
  - the folder READMEs for `vidbyte/harnesses/`, `vidbyte/tools/` and `vidbyte/agents/codex/`;
  - the field-guide entries listed in spec §11.
- **Code:**
  - `vidbyte/agents/codex/`: `agent.py`, `tools.py`, `config.py`, `result.py`, `metrics.py`, `failures.py` and `transport.py`;
  - `vidbyte/lib/`: `dataclasses/codex.py`, `enums/codex.py`, `enums/failure.py`, `enums/__init__.py`, `constants/codex.py` and `errors/base.py`;
  - pricing: `vidbyte/agents/pricing/tracker.py`;
  - tools: `vidbyte/tools/catalog.py`, `base.py` and `executor.py`, the sessions tool package, `toolsets/coding.py`, and the builtins and toolsets `__init__` files;
  - MCP: `vidbyte/mcp_server/server/core.py`.
- **Lint:**
  - rules S012, S045, A001, A002, A003, A007, C006–C008, S015, S025, S060 and S062;
  - `lint/core/ruff.py` (selectors) and `lint/core/public_api_contract.py` (generated sorted, line 87);
  - `lint/mypy.ini`, and `lint/baseline.json` for reading only.
- **Tests:** `tests/test_codex_tools.py`, `tests/test_codex_failure_recovery.py`, `tests/test_session_failures.py`, `tests/agent_test_support.py`, and the `tests/features/coding_agent/` pack.
- **openai-codex 0.162.1**, from the read-only copy in the vidbyte-cli venv: `client.py`, `_run.py`, `_goal.py`, `_runtime_requirements.py` and `generated/v2_all.py`.
- **Deliberately not read:**
  - anything else under `docs/`, including `docs/design/codex-harness-agent.md`;
  - the ClaudeHost worktree;
  - the claude-host agents' output.

No gate was run and nothing was installed. That follows S1's read-only rule.

## Approaches

### B, chosen: the host drives openai-codex's public sync `CodexClient` directly

- **One process.** `CodexHost` owns one app-server process for its lifetime.
- **Bounded calls.** Every client call runs as `asyncio.wait_for(asyncio.to_thread(...), CODEX_HOST_REQUEST_TIMEOUT_SECONDS)` (300 s, the repo's existing Codex bound).
- **Typed methods carry the full params.** Each typed method (`thread_fork`, `thread_start`, `thread_resume`, `turn_start` and the rest) takes the full generated params model, so `lastTurnId`, `excludeTurns`, `approvalsReviewer`, `developerInstructions` and `dynamicTools` need no raw call.
- **Five raw calls.** Only these use `request_with_retry_on_overload`: rate limits, sandbox readiness, paged `model/list`, `review/start`, and the goal `tokenBudget` set. The last two spend money, so they get a single attempt.
- **No private attribute.** Approvals use the constructor's `approval_handler`, and S012 stays at 0 with no suppression.
- **Turn tracking.** A daemon thread per live turn reads the SDK's per-turn notification queue. A liveness monitor reads `next_notification()` and finalizes running turns when the process dies.

### A, runner-up: the high-level `AsyncCodex` API, plus its private `_client` for the five calls it lacks

- **Rejected.** The private attribute can be renamed by any pin bump without warning. The raw path would also have to call `_client.request(...)`, which takes no `timeout` keyword, so S012 fails it and only a suppression could pass it. That is forbidden.

### Rejected smaller designs

- **One app-server per call.** Every function opens and closes its own process. This fails:
  - INV-13 and FR-5: a spawned turn must outlive the call that returned its handle;
  - FR-10 to FR-12: wait, steer and interrupt need the process that is running the turn;
  - FR-13: usage notifications reach only that process.

  The six read-only module functions keep this shape on purpose (D-24).
- **A blocking spawn.** It fails INV-13. It would also hold the calling agent inside one tool call, past `CodexHarnessAgent`'s 300 s cancellation.

## Where I disagreed with the scout, the request or the house style

1. **request.md §C "append-only" for shared export lists.** This is superseded by the orchestrator's correction.
   - The rule is now: insert each new name in its sorted position, and never reorder or rewrap existing entries.
   - This matches isort (I001), the sorted `__all__` lists, and the contract JSON, which is generated sorted.
   - Codex-only lists keep their own order: the enum module's `__all__` is alphabetical after `CodexFailureClass`, and the constants module's `__all__` is in definition order, so new names go at its end.
   - Where this is written: §12.3 rows 2, 3, 4, 24 and 26, §12.4, §12.5 and §9.4.
2. **R3's `wait_codex_turn(handle, timeout)`.** The method is async, so ruff ASYNC109 (run as S045) forbids a parameter named `timeout`. The spec uses `timeout_seconds` everywhere: §8.5, the wait tool, and §12.4 (orchestrator correction 2).
3. **Raw `request()` (request.md's open question on unwrapped methods).** The answer is no.
   - The high-level client exposes no public path, and the raw `request` cannot satisfy S012.
   - The spec lists every wire call by its typed method or `request_with_retry_on_overload` (D-2, §12.4).
   - Passing `client.request` uncalled to `asyncio.to_thread` would slip past S012's call check. It is forbidden explicitly (orchestrator correction 3).
4. **AGENTS.md:31 files under 1,000 lines vs request.md §C.** The request puts the records in `vidbyte/lib/dataclasses/codex.py`, which is already 1,205 lines. The request and the placement rule win, and Q-1 stays open with the default of no split.
5. **The field guide's "static helper class over module functions" vs request.md's module functions.** The request wins: the six functions are thin `async with CodexHost()` wrappers (D-24).
6. **Name collision.** `CodexTurnOutcome` already exists, used by `vidbyte/agents/codex/agent.py`. The wait and get result is therefore `CodexTurnSnapshot`.
7. **Turn status values.** `CodexTurnStatus.RUNNING = "inProgress"` matches the wire value, following the enum module's "wire-exact" header, rather than a Vidbyte-only "running".
8. **`exclude_turns` on fork.** It only shapes the response. It never drops history from the forked thread.
9. **The CLI version.**
   - request.md says `codex-cli` 0.161.0 is on PATH. The code map found the npm package at 0.162.1, and the binary was not run.
   - The spec depends on neither number: the minimum accepted runtime is openai-codex's floor, 0.151.0 (Q-2).
10. **The stale REPO_MAP toolsets sentence stays.** The shared-file rule allows inserting the new section only.
11. **`launch_codex_subagents`.**
    - `limit` is a refusal cap that defaults to `None`, never a queue or an invented threshold (Q-5).
    - Launch starts fresh threads only.
12. **No ownership restriction** on the continue, fork, read, review and track tools (Q-8, default no). The residual risk is recorded under T-2.
13. **A missing openai-codex install** (`ImportError` at open) maps to `codex.not_installed`, with the pip next step.
14. **Model-supplied `max_output_tokens` and `timeout_seconds`** replace the toolset's `spawn_defaults` rather than being capped by them (Q-9, default no).
15. **Local reads after close or death.** `wait_codex_turn`, `get_codex_turn_result` and `track_codex_thread_usage` keep answering from recorded state after close or death (INV-6, INV-7). Every method that talks to Codex raises `codex.process_exited`.
16. **A likely merge conflict with PR B.**
    - The Codex builtins docstring bullet goes right after the `builtins.code_search` bullet.
    - Suggestion for PR B: put its Claude bullet where its own sorted import sits, so that the two bullets touch different lines.
    - The REPO_MAP section and the harnesses README bullet are written to be byte-identical in both PRs.

## Assumptions I am least sure of

- **A-1 (Windows launcher).**
  - What I assumed: `subprocess.Popen` on the npm `.cmd` launcher that `shutil.which` returns starts the app-server, and `close()` stops it.
  - If wrong: Windows opens fail, or children are orphaned.
- **A-2 (goals before the first turn).**
  - What I assumed: a fresh non-ephemeral thread has `path` set, so goal start works before any turn.
  - If wrong: every goal spawn fails, and the Q-6 alternative is needed.
- **A-3 (cumulative usage).**
  - What I assumed: the usage totals in `thread/tokenUsage/updated` are cumulative and never decrease.
  - If wrong: the per-turn output cap and the usage deltas are off.
- **A-6 (budget-only goal set).**
  - What I assumed: a `thread/goal/set` carrying only `threadId` and `tokenBudget` changes only the budget.
  - If wrong: the echo check raises `protocol_mismatch` on every goal spawn.
- **A-7 (where approvals go).**
  - What I assumed: approvals reach the client only when `approvals_reviewer=user`.
  - If wrong: T-6 widens.
- **A-12 (version parsing).**
  - What I assumed: `initialize` exposes a parseable version.
  - If wrong: every open fails with `version_unsupported`.

## Notes for S2 and the reviewer

- **The test seam** is the module attribute `vidbyte.harnesses.native.codex.connection.CodexClient`, which `__aenter__` imports lazily. Also patch `shutil.which` and `sys.platform`.
  - The fake needs no `request` method and no `model_list` method.
  - The five raw calls reach `request_with_retry_on_overload`, keyed by method name (§13).
- **Rules most likely to be broken:**
  - S012 (baseline 0);
  - A002 `# @intent` lines (any identifier containing request, retry, attempt, fallback, provider or similar);
  - A001 headers, which have no headroom;
  - S045 for anything async that takes a timeout.
- **The native `__init__`** must hash to `0374a2c8…942f497a` exactly. If a gate rejects those bytes, the run reports BLOCKED.

## Addendum r2: review round 1 (2026-10-13)

**Inputs.** I applied all 13 findings in `reports/S1-spec-review.md` (verdict SOUND WITH FIXES), plus the orchestrator's decisions for R-5 and R-9. The spec is now at revision 2, commit `b38d573a`. Each finding has a §16 row, and §17 has the r2 row. `status` stays `draft` for the scoped round-2 review.

**Sections changed.** §8, §8.5, §9, §10 and §12 all changed. So did §2, §3 (NG-8, NG-12), §4 (one import), §5, §6, §7 (FR-30, NFR-9, NFR-10), §11, §13, §14 and §15.

**Design changes:**
- **Host executor.** Calls run on a `ThreadPoolExecutor` the host owns (`CODEX_HOST_WORKER_THREADS`), never on the loop's default executor.
- **Close.** It finalizes the turns, then sends each one bounded interrupt, then closes on a daemon thread under `CODEX_HOST_CLOSE_WAIT_SECONDS`.
- **Late acceptance.** It now also covers a start request that outlives its bound. A failed or timed-out goal budget request also cancels the goal (INV-25, EC-74). I added this one myself: it is the same unowned-turn gap as R-6.
- **Death flag.** After it is set, every failure maps to `process_exited` with fixed text.
- **Wait clamp.** 240 s.
- **USER reviewer.** Rejected when the request is built (orchestrator decision).
- **Records.** The records now live in a new `codex_host` module (repo-forced).
- **Fixed texts.** §12.5 carries request.md §C's fixed texts, copied by a script and compared byte for byte.

**New facts I checked this round:**
- **The review's blob-hash pipe gives a wrong hash in Windows PowerShell 5.1.** That shell re-encodes bytes piped between two programs: `git show HEAD:vidbyte/harnesses/README.md` piped to Python printed `dbbbe043…` in PowerShell and `4075c323…` in Git Bash. §11 now reads the blob inside Python with `subprocess.run`. That form printed `4075c323…` in both shells, for the staged path and for the `HEAD:` path.
- **ruff `F` is in the lint selectors** (`lint/core/ruff.py:26-34`). So the new records module must not import `CodexClientSettings`, which no record uses. Row 6 lists exactly the records the fields need.
- **`ToolInput` comes from `vidbyte.tools.adapters`.** `codex.py` imports it under `TYPE_CHECKING`, and row 6 says the new module does the same.
- **No lint rule is scoped by file name in a way the move would trip.** C012's exemptions name `codex.py` fields, but the new records are not configuration owners, so C012 does not select them. S058 applies only to pydantic models.
- **`thread/read` with `includeTurns`** "include[s] turns and their items from rollout history", and `Turn.itemsView` defaults to `full` (`generated/v2_all.py`). These were read from the schema, not run, so the review completion read-back rests on A-14.
- **openai-codex's `_TURN_START_EXECUTOR`** passes no `max_workers`, so it gets the standard library default of min(32, CPU count + 4).

**Least sure:**
- **A-1:** does the app-server exit on stdin end-of-file on Windows? If not, it lingers after close (EC-69).
- **A-7:** do resumed threads keep their reviewer? If not, a thread started outside the host with a `user` reviewer could send approvals that hit the `accept` fallback.
- **A-14:** does the read-back have the final item by the time `turn/completed` arrives?

**For the round-2 reviewer:**
- The three judgement calls of mine are:
  - INV-25/EC-74;
  - leaving Q-3 resolved rather than open for the callback, because the callback is R3's ✗ function;
  - the §11 hash command form.
- Everything else follows the review's smallest fixes or the orchestrator's notes.
- This addendum is not committed; I staged only the spec.

## Addendum r3: review round 2, final (2026-10-13)

**Inputs.** I applied all 5 findings in `reports/S1-spec-review-r2.md` (SOUND WITH FIXES: 3 Majors, 2 Minors) with the orchestrator's seven notes, and disputed none, so there is no new Q. The spec is at revision 3, commit `81a71d00`, with `status: approved`. §16 has rows r2-1 to r2-5, and §17 has the r3 row.

**Design changes:**
- **R-1, the effective reviewer (new D-32).** After `thread/start` and `thread/resume`, and before any name, turn or goal request, the host reads the reviewer and policy that Codex reports. A `user` reviewer with any policy but `never`, granular included, is refused, naming the thread. The default path is unchanged and adds no field or setting:
  - spawn still sends the SDK's own `on-request` plus `auto_review`, so §4 passes (A-15);
  - resume sends nothing unless set, so a host-spawned thread continues (A-16);
  - a `user` thread gets the next step `overrides=CodexSpawnRequest(approvals_reviewer=AUTO_REVIEW)`, or `spawn_defaults` on the tool path.

  The runner-up I rejected was sending `auto_review` on every resume, which silently replaces a human reviewer. Review sends no resume, so it is the one residual (EC-77).
- **R-2, close.** Close now has six steps. Tool handlers are removed and closed first, as the sibling transport does. Goal runs stay registered through their cancel, then get openai-codex's goal-stream close (`finish()`, `wake_notification_reader()`, `unregister_goal_operation`). Process death runs steps 1 and 2.
- **R-3, late acceptance.**
  - `CodexConnection` owns the shielded, bounded await.
  - `future.cancel()` runs first, and the callback is attached only when it returns False.
  - A late review gets D-23's read-back.
  - Close wins: a start that returns once close has begun is registered FAILED `process_exited`, and nothing more is sent.
- **R-4, goal cleanup.** A failed goal start follows openai-codex's order: cancel, bounded by `CODEX_HOST_CLOSE_INTERRUPT_SECONDS`, then `finish()`, then `unregister_goal_operation`. The watcher starts only after the budget check passes.
- **R-5 and note 6, errors.** The USER rejection is `CodexAgentError` with `configuration.unsupported_combination` and the next step `CODEX_HOST_USER_REVIEWER_TEXT`, now worded for both paths. Every mapped error is raised `from None`, and no message uses `str(exc)`.

**My judgement calls:**
- **The construction-time operation.** I added `CodexHostOperation.VALIDATE_SPAWN_REQUEST`, because INV-8 requires a `CodexHostOperation` value and no host method runs at construction.
- **Close wins on the normal path too.** INV-6 now refuses new calls once close has begun. A start that returns during close, with its caller still waiting, is registered FAILED with `process_exited`. Without both, a turn could be registered after close step 2 and never finalized, which would break INV-6's "every turn is terminal".
- **Goal runs end the same way.** A goal run that finishes normally also gets the goal-stream close. Otherwise each finished goal run would strand one watcher thread.

**New facts I checked this round (openai-codex 0.162.1):**
- **The closed marker is raised, not returned.** `_GoalStreamClosed` subclasses `Exception`, and `next_notification()` raises any exception it dequeues. So after `wake_notification_reader()`, a blocked `next_goal_notification` raises.
- **The SDK's own goal stream closes in this order:** `finish()`, `wake_notification_reader()`, then unregister. Its start-failure path runs cancel, `finish()`, then unregister.
- **`thread/read` cannot be checked.** The `Thread` it returns carries no approval fields, so a review cannot be checked without sending a resume.
- **What the SDK sends.** `ThreadResumeParams` describes its reviewer as an override "on this thread and subsequent turns". The SDK's `thread_resume` and `thread_fork` default to sending no approval fields, and no `ApprovalMode` maps to `user`.
- **S017's scan scope** is `vidbyte/providers/`, `vidbyte/tools/`, `vidbyte/mcp_server/` and `vidbyte/lib/runners/`. `vidbyte/harnesses/` is outside it, so the `from None` rule is held by review there.
- **The classification test** requires a row only for `codex.*` codes, so `configuration.unsupported_combination` needs none.
- **`JsonRpcError.message`** holds Codex's own message, so the mapper never needs `str(exc)`.

**Least sure:**
- **A-16.** Does a thread resumed without approval fields keep its reviewer, especially one resumed from disk by a new app-server? If not, plain continues are refused with the next step, though nothing is approved silently.
- **A-1**, **A-6** and **A-14** stand as in r2.

This addendum is not committed; I staged only the spec.

## Addendum r4: S2 spec defects (2026-10-13)

**Inputs.** The S2 test author found three spec defects, and the orchestrator forwarded them as S2-1 to S2-3. This was not a review round, and the frozen tests are now the interface. I opened the named test and its helper, `_assert_owned_and_interrupted_once` in `test_codex_host_failures.py`, and grepped the pack for `limit_reached`. My rate-limit grep was broader than asked: it also matched `rateLimits`, which showed the assertions of `test_codex_host_threads.py::test_rate_limits_and_models_are_translated_across_pages`. That test does not assert `limit_reached`. I read no other test. The spec is at revision 4 and stays `status: approved`. §16 has rows S2-1 to S2-3, and §17 has the r4 row.

**Dispositions:**
- **S2-1, accepted (new D-33).** Handles are owned by value. A handle is accepted when its `(thread_id, turn_id)` names a turn this host registered, late-accepted turns included. A frozen `CodexTurnHandle` already compares by value, so the registry lookup is the whole check. INV-23, INV-11, EC-36, EC-67, §9.1 and the §9.2 wait, interrupt and `session_not_found` cells follow. The `session_not_found` next step is unchanged, because it is a `CODEX_NEXT_STEPS` value and names a remedy, not the rule. INV-33, the tool scope's rule, is unchanged.
- **S2-2, accepted (new D-34).** `limit_reached` is the wire value of `rateLimits.rateLimitReachedType` in the `account/rateLimits/read` response, or `""` when that field is absent or null. In openai-codex 0.162.1 that is `GetAccountRateLimitsResponse.rate_limits.rate_limit_reached_type`, an optional `RateLimitReachedType` with five values. The name and the `str` type stay.
- **S2-3, accepted (new D-35): no problem code.** The late-acceptance interrupt records no stop reason, as `interrupt_codex_turn` does. So a turn that Codex reports `interrupted` ends INTERRUPTED with no problem. A goal follows the goal table with no Vidbyte stop reason, and the caller's error is never copied onto the snapshot. The §9.1 INTERRUPTED line and the goal table's `paused` row now say that only D-7's timeout and output-cap labels set a problem.

**Checked against the tests.**
- The helper rebuilds `CodexTurnHandle(thread_id=…, turn_id=…)` from ids. It asserts exactly one `turn/interrupt`, an `interrupted` status, and a get equal to the waited snapshot. It asserts nothing about the problem, so D-33 and D-35 agree with it.
- The `limit_reached` hits (records test lines 151 and 244, tools test line 428) check only that the field is text and that `""` is valid. D-34 keeps both.

**Scope.** No pin adds a guard, flag, field or code path, so there is no new stated limitation. INV-11's "exactly one interrupt" already ruled out a second interrupt. No AC row, Proof cell, name, §9 signature or §12.3 row changed. The orchestrator's FYI, that late acceptance on goal start, continue and launch has no test of its own, goes to S4; I left the spec alone for it.

**Vendor read.** I read `generated/v2_all.py` in the CLI venv as text only, at `RateLimitReachedType` 3639, `RateLimitSnapshot` 9038 and `GetAccountRateLimitsResponse` 10965. §11 now cites the first two as well. Nothing was imported or run from there.

## Addendum r5: S4 findings R-8 and R-12 (2026-10-14)

**Inputs.** The orchestrator forwarded two rows of the verified S4 review, `review.md`: R-12 (Major, spec-change plus tests-only) and R-8 (Major, code plus deviation-entry). I read `review.md`, the R-2, R-8 and R-12 sections of `reports/S4-findings-verifier.md`, request.md's R2 schema lines (304, 330), and, read-only, `OutputSchemaFormatter` (`vidbyte/providers/output_schema.py`), `descriptions.py:40`, the schema branch of `wire.py` (around line 569) and the record check at `codex_host.py:205`. I also read the vendor's `TurnStartParams.outputSchema` description in the CLI venv as text. The spec is at revision 5, `status: reviewed`, `updated: 2026-10-14`. §16 has rows R-8 and R-12, and §17 has the r5 row.

**Dispositions:**
- **R-12, accepted (new D-36).** INV-21 is now one sentence. It says that `turn/start` sends the schema to Codex as `outputSchema`, and that the completed answer is checked locally with `OutputSchemaFormatter.validate`, the check `CodexHarnessAgent` also uses. A Pydantic model type must accept the whole answer. A mapping only requires the answer to parse as JSON, and its shape is left to Codex.
  - EC-32 now covers only non-JSON answers and model rejections.
  - New EC-83 accepts the undetected mapping mismatch (COMPLETED, no problem, `structured` = the parsed JSON).
  - The `codex.schema_violation` "Detected by" cell follows; its next-step text is unchanged.
  - D-36 says what the `output_schema` tool description and the `CodexSpawnRequest` docstring must state, so the repair agent can reword `descriptions.py:40` and the docstring.
  - New EC-82 keeps the rule that an unusable schema is refused before any request: a type that is not a Pydantic model, or a mapping that cannot be serialized to JSON. That is what R-2's code fix does. I changed neither §8.5 nor §9.1 for R-2.
  - R-25, the real local validator, is Q-10, non-blocking, default no. It is not built.
- **R-8, accepted.** §17 deviation 1 is struck through and marked withdrawn, citing R-8: its budget reason was wrong, because `_reject_bad_seconds` and `_reject_small_int` already own both rules. Deviation 2 stays; the S4 review confirms that INV-25 needs it.

**Judgement calls:**
- **One sentence for INV-21.** The orchestrator asked for INV-21's text in one sentence, so the refusal rule moved to EC-82 and the wording rule to D-36, rather than into INV-21 bullets.
- **AC-13 unchanged.** Its "invalid" case still holds for non-JSON answers, and the pack passes, so its test does not rely on a mapping shape mismatch. I did not open the test.
- **§12.3 row 11 untouched.** It says the translator "validates structured output through" the helper, which names the helper correctly. The orchestrator's rules forbid editing it.

**Scope.** No validator, dependency, option or field was added. The §8.4 budget, every §12.3 row, §8.5, §9.1, every AC row and the shared-file contract are unchanged. The self-check is clean: 18 sections, no ID gaps (D-36, EC-83, Q-10), 28 §12.3 rows, names unchanged. The only new path hit outside §11–§13 is D-36's request.md citation.
