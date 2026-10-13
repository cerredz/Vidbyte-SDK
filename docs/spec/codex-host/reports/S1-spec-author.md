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
