LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The branch follows spec r4 almost row for row, and the §4 snippet runs verbatim under the fake seam, but three things need fixing: a steered turn whose stream dies takes the interrupted prompt's failure code; a non-record handle or request escapes INV-2 as a raw builtin error; and three deviations are missing from §17 or misstated there.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Scope and shared files are exact.**
  - The 31 non-test files are exactly §12.3 rows 1–31: 22 new, 9 modified, 0 lines deleted.
  - The marker blob's SHA-256 is `0374a2c8…942f497a`.
  - The 16 FailureCode members sit between `CONFIGURATION_INVALID_ARGUMENT` and `CODEX_SDK_UNAVAILABLE`. Exports are sorted inserts.
  - The REPO_MAP and README insertions match request.md byte for byte, and the `claude` extra comes before `codex`.
  - Tests are unchanged since 9a8ecc3c, `lint/baseline.json` is untouched, and there are no suppressions and no codex references.
  - Budget: 22/22 files, 69/69 classes, 1 optional dependency, 0 root exports. Do not move or re-sort any of this.
- **The surface matches the spec.**
  - The 15 ★ methods carry R3's names and map one to one onto 15 tools in §9.2 order.
  - Permissions are exactly INV-14: 9 READ, 6 WRITE. Every input schema is closed.
  - `ClaudeSpawnRequest` has the 58 §9.2 fields, with every §9.1 rule and its D-31 code. The translator uses only fields that exist on the real `ClaudeAgentOptions` 0.2.165.
  - Each of the 16 `claude.*` codes is keyed to its R3 next step.
  - Importing every INV-1 module leaves `claude_agent_sdk` unloaded.
- **The lifecycle machinery matches D-4, INV-7, INV-8, D-26 and D-28. Do not simplify it.**
  - There is one close task, started by whichever path needs it first and never cancelled (shield, then `asyncio.wait({closing})`).
  - `_stopping=True` is set at session.py:180, before the close, so publishing after the close cannot change the classification.
  - The grace is aimed by prompt number, results are filtered by origin, interrupt tasks belong to the session, and steer numbers guard EC-59.
- **`ClaudeFailureMapper` is §9.2 exactly.**
  - Subclass rows come before their bases, and `ResultError` maps by its subtype.
  - Start failures and history reads get their own next steps. `ValueError` and `TypeError` map to invalid_argument only for connect and fork (deviation 2).
  - Each reason names only the operation, the exception class or CLI vocabulary (INV-12).

FINDINGS (ranked, most severe first, max 15)
R-C1 [Blocker] [ID walk: INV-19 / D-3 / AC-9 / §9.2 rows 9–12] vidbyte/harnesses/native/claude/failures.py:174 — A steered turn whose stream ends before the steered prompt's result fails as claude.api_error, using the interrupted prompt's result instead of the stream failure
  Evidence:
  - The stale facts are stored and never cleared:
    - session.py:294-306 (`_on_result`) stores the interrupted prompt's result in `_outcome`: `is_error=True`, `subtype="error_during_execution"` and `terminal_reason="aborted_streaming"`.
    - `_take_steer` (session.py:250-255) never clears those facts.
  - The classifier reads them before it checks whether a result arrived:
    - session.py:428 computes `result_seen=bool(self._prompts_sent) and self._results_read == self._prompts_sent`, which is False once the steer has been sent.
    - But failures.py:93 runs `_reported` first, and failures.py:174 (`if outcome.is_error:`) matches the stale fact before failures.py:98 (`if not outcome.result_seen:`) is reached.
  - Inline run under the fake seam: prompt P is held, the steer S goes out, and S's scripted reply is `init_message()` followed by END_OF_STREAM, or by the fixture's `CLIConnectionError`. Output:
    `AS BUILT: stream ends -> failed claude.api_error | Retry with backoff.`
    `AS BUILT: fake CLIConnectionError -> failed claude.api_error | Retry with backoff.`
    reason: `The turn ended with an error result: subtype error_during_execution, terminal_reason aborted_streaming, api_error_status None, assistant errors none.`
    Control, the same END_OF_STREAM with no steer: `failed claude.process_exited`.
  Failure:
  - Scenario: a RUNNING turn is steered. The CLI answers the interrupt, and the pump sends the steer. Then the process dies, or the stream raises, before the steered result arrives.
  - Outcome: the handle reports `claude.api_error`, with "Retry with backoff." and a reason that describes the aborted prompt.
  - What the spec requires:
    - D-3 says the steered prompt's result is the handle's.
    - AC-9 says the final result is the steered turn's.
    - §9.2 row 12 ("The stream ended or the process exited without a result") should therefore decide: `claude.process_exited`, "Respawn, then resume by id."
  - The same stream death on an unsteered turn is classified correctly, so the code a caller sees depends on whether a steer happened.
  Smallest fix:
  - In `ClaudeFailureMapper._reported`, after the assistant-error loop (failures.py:167-169), add `if not outcome.result_seen: return None`. Rows 9–11 then read only the last prompt's own result, and row 12 decides otherwise.
  - Add a SteerTests case that pins this.
  - I tried the fix in memory (monkeypatched, no file written). Both scenarios became `failed claude.process_exited | Respawn, then resume by id.`, and the pack stayed at `165 passed`.
  Spec IDs: INV-19, D-3, D-20, AC-9, AC-6, §9.2 "Turn classification" rows 9–12

R-C2 [Major] [ID walk: INV-2; weighted word "each funciton shoulllld make sure to handle errors"] vidbyte/harnesses/native/claude/host.py:171 — Six ★ functions let AttributeError or TypeError escape when the handle or request argument is not a record
  Evidence:
  - The unguarded reads:
    - host.py:171 `if not request.prompt:`
    - host.py:270 `return await self._session(handle.handle_id, operation).wait(timeout_seconds)`; the same `handle.handle_id` read appears at :277, :289, :296 and :303.
    - host.py:325 `if several and request.session_id:`
    - host.py:331 `replace(request, prompt=prompt)`
  - INV-2 (spec.md:215): "No ★ function lets a vendor or builtin exception escape".
  - Inline run under the fake seam:
    `wait_claude_turn(None, timeout_seconds=1) -> AttributeError - | 'NoneType' object has no attribute 'handle_id'`
    `get_claude_turn_result('h-1') -> AttributeError - | 'str' object has no attribute 'handle_id'`
    `spawn_claude_session('List TODOs') -> AttributeError - | 'str' object has no attribute 'prompt'`
    `launch_claude_subagents(('a',), None, 1) -> TypeError - | replace() should be called on dataclass instances`
    `launch_claude_subagents(('a','b'), None, 1) -> AttributeError - | 'NoneType' object has no attribute 'session_id'`
    `interrupt_claude_turn({'handle_id': 'x'}) -> AttributeError - | 'dict' object has no attribute 'handle_id'`
  Failure:
  - Scenario: a developer passes the prompt text straight to `spawn_claude_session`, which is a natural mistake, or passes a handle_id string or None to a turn function.
  - Outcome: a raw AttributeError with no failure_code or next step, instead of `configuration.invalid_argument`.
  - A non-record `request` in `continue_claude_session` (host.py:203-208) has the same gap.
  - Defense considered:
    - §9.1 (spec.md:732) lists host type checks only for arguments that come from model JSON.
    - The tool path is already covered by AC-26.
  - Verdict: INV-2's last bullet is unconditional, so the tie goes to the prosecution.
  - Rated Major rather than Blocker: only typed record parameters are affected, the tools always pass records, and no wrong result is produced.
  Smallest fix:
  - Write one single-record type check once in `_ClaudeFieldRules`, as a twin of `records` (C002).
  - Call it first in the five handle methods and in spawn, continue (when `request` is given) and launch.
  - It raises `configuration.invalid_argument` with "handle must be a ClaudeSessionHandle." or "request must be a ClaudeSpawnRequest."
  Spec IDs: INV-2, D-15, FR-17

R-C3 [Major] [NFR walk; unreported deviation] vidbyte/harnesses/native/claude/session.py:170 — The pump's call chain goes two levels deep (run → _read → _on_<kind>), against NFR-4 and the §12.4 checklist, and §17 does not record it
  Evidence:
  - session.py:170 `prompt = self._take_steer() if await self._read(stream) else None`.
  - session.py:238-245: `_read` calls `self._on_result`, `self._on_assistant`, `self._on_rate_limit` and `self._on_task`.
  - The spec requires one level:
    - NFR-4 acceptance (spec.md:417): "Call chains stay one level deep (AGENTS.md principle 1)".
    - §12.4 (spec.md:1204): "helpers call only other classes or the stdlib".
    - Row 7 puts the per-kind dispatch in `run` itself.
  - S3-implementer.md:253 admits the chain is "one level deeper than principle 1 strictly allows". It cites S008 and S024 (`lint/rules/s024_maximum_control_flow_nesting.py:22`, `MAX_NESTING_DEPTH = 3`), and a dispatch inside `run`'s `try`/`while`/`async for` would reach depth 4.
  - §17 deviations 1–11 (spec.md:1477-1487) leave it out.
  - `_interrupt_client → _arm_grace`/`_start_close` (session.py:373, :377) has the same shape, but row 7 prescribes it.
  Failure: the spec of record says NFR-4 holds when it does not. A later reader, or the @claude review, will flag principle 1 and find no recorded reason. Rated Major, not Blocker: the blocking lint rule S024 makes the literal one-level shape unreachable here, so the defect is the missing record. The AGENTS.md judgment belongs to the conventions lens.
  Smallest fix:
  - Add §17 deviation 12 (row 7, NFR-4), with no code change.
  - It should say that `run → _read → _on_<kind>` stays because S024's depth limit of 3 and S008 forbid folding the `async for` dispatch into `run`.
  - It should also note that row 7 itself prescribes `_interrupt_client → _arm_grace`.
  Spec IDs: NFR-4, §12.3 row 7, §12.4 (principle 1 line)

R-C4 [Minor] [deviations] docs/spec/claude-host/spec.md:1477 — Deviation 1 says "no policy string or field key is a literal in the harness", but many field keys and one operation name still are
  Evidence:
  - session.py:212 `info.get("hooks_applied")`.
  - session.py:265-272 `usage["inputTokens"]` … `usage["costUSD"]` and `fields.get("model_usage")`.
  - probe.py:139 `model["value"]` and probe.py:144 `model.get("supportedEffortLevels")`.
  - probe.py:152 `operation="get_server_info"`, while session.py:65 defines `_INFO_OPERATION = "get_server_info"` for the same operation.
  - history.py:87-96 and :116: `fields["session_id"]`, `fields.get("created_at")` and `fields["type"]`.
  Failure:
  - A reader who trusts §17 believes the extraction to constants is complete.
  - The operation name duplicated between the probe and the session can drift apart.
  Smallest fix: reword deviation 1. It should say which names moved to constants (the operation names the mapper compares, and the initialize-answer fields the probe and session share), and that SDK record keys read through `vars()` stay literal at their single use.
  Spec IDs: §17 deviation 1, §12.3 row 14

R-C5 [Minor] [unreported deviation] vidbyte/lib/errors/base.py:198 — ClaudeOperationError sits after AggregateExecutionError rather than "directly before class ConfigurationError (:235)" as row 25 says, and §17 does not record it
  Evidence:
  - `git show d9c5fea2:vidbyte/lib/errors/base.py | grep -n "^class "` → `194:class AggregateExecutionError`, `198:class ClaudeOperationError(VidbyteSdkError)`, `230:class AgentForkError(VidbyteSdkError)`, …, `267:class ConfigurationError(VidbyteSdkError)`.
  - Row 25 (spec.md:1175) says "directly before `class ConfigurationError` (:235), after `AggregateExecutionError`".
  Failure: nothing goes wrong at run time, and row 26's export order is unaffected. The record names one placement and the file has another.
  Smallest fix: move the class block to directly above `class ConfigurationError`, or record the placement in §17.
  Spec IDs: §12.3 row 25

VERIFIED CLAIMS:
- **AC-1, §4 snippet run verbatim: held.**
  - The snippet was extracted from spec.md and run with `exec`, with `ClaudeSdkLoader.load` and `WHICH_TARGET` patched.
  - It printed `completed Found 3 TODO comments.` and then `0.0421`.
  - It used 2 fake clients (the probe and the turn), each disconnected once, and sent one query.
  - The turn's options were plan, 0.5, `C:/work/repo` and the fake cli_path.
  - With no CLI found, it printed exactly `claude.not_installed Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.` and built 0 clients.
  - The snippet is 25 lines with 3 vidbyte imports, so NFR-11 holds.
- **§5 diagram against the real call path: held, with two non-behavioral differences.**
  - Classification runs inside `_publish` after the close. This is safe because session.py:180 sets `_stopping` before the close, so `interrupt()` and `close()` do nothing to the outcome while the close runs.
  - `interrupt()` is sent from a task the session owns (row 7, r3), not by the host as the sequence diagram draws it.
- **Boundaries: held.** 31 files changed with 4018 insertions; all are §12.3 rows; 0 deletions.
- **§14 never-list: held.**
  - Tests are unchanged since 9a8ecc3c, and the baseline is unchanged.
  - There are no suppressions.
  - `_send_control_request` and `_internal` appear only in a header comment, and there is no codex reference (grep exit=1).
  - No CLI command and no root export were added.
- **§8.4 budget: held.**
  - 22 new files.
  - 68 classes in the new files, plus ClaudeOperationError, makes 69.
  - 1 optional dependency, `claude-agent-sdk>=0.2.165,<0.3.0`.
  - The largest new file is 578 lines.
- **Marker SHA-256, and REPO_MAP and README bytes: held.**
- **INV-1: held.** Importing the six modules leaves `claude_agent_sdk` out of `sys.modules`, and the pack passes with the SDK blocked.
- **INV-14 and closed schemas: held** (live listing of the 15 specs). 58 request fields, and the 16 `claude.*` codes are keyed one to one to their next steps: held.
- **§17's "34 commits (b0d6c4c3..5edf1a4d)": held.** The two commits after 5edf1a4d change docs only, in 2 files. The refactors e7382a26 and f0c84cd0 match deviations 2–4 and the §9.2 exception table.
- **D-28, D-29 and D-33 in code: held** (session.py:275-277, failures.py:117-120, host.py:204). `wait()`'s `suppress(TimeoutError)` is correct because the package requires Python 3.11 or later.
- **Did not hold:**
  - INV-19, D-3 and AC-9 for a steered turn whose stream dies (R-C1).
  - INV-2 for non-record arguments (R-C2).
  - NFR-4 call depth, which §17 does not record (R-C3).
  - Deviation 1's claim (R-C4).
  - Row 25's placement (R-C5).
- **ID walk, prosecution against defense:**
  - **FR:** FR-1..FR-25 met. FR-17 is subject to R-C2.
  - **NFR:** NFR-1..3 and NFR-5..11 met. NFR-5 rests on S3's gate claims, not re-run here; the pack was re-run with 165 passed. NFR-4 is not met (R-C3).
  - **INV:** INV-1, INV-3..18 and INV-20..26 met. INV-2 is not met for non-record arguments (R-C2). INV-19 is not met for a steered turn whose stream dies (R-C1).
  - **AC:** AC-1 met by the verbatim run. AC-2..40 met by the pack and by reading the code. AC-9 holds on its tested path but not after a steered stream death (R-C1).
  - **EC:** EC-1..61 met. EC-28, 43, 45, 46, 47, 51, 54, 55 and 61 are stated limitations, recorded in the file headers.
  - **§12.3 rows:** rows 1–6, 8–13, 15–24 and 26–31 met. The exceptions are row 7's shape (R-C3), row 14's deviation text (R-C4) and row 25's placement (R-C5).
- **Weighted words:**
  - "all the params needed" held (58 fields).
  - "semantic error messages … each funciton … handle errors" held only in part (R-C1, R-C2).
  - "connect each individual function to the vidbyte/tools folder" held (15 functions, 15 tools).
  - "small, atomic, rueusable" held for size (every file under 1,000 lines). Call depth is covered by R-C3.
  - "everything that we can do with claude code" held within R3, with ⚑ excluded as decided.
  - "4 claude subagents … only a few functions" held (`launch_claude_subagents`, AgentSnippetTests).
  - "package all of these into tools … mcp" held (ClaudeTools, served by McpStudioServer per T-4).
  - "in parallel in 2 seperate prs" held (no codex reference, and the contract files are exact).
  - "very simple agents" held (NFR-11).
- **Scope:** nothing beyond §12 was added, and no §C decision was reversed.

COMMANDS RUN:
- `git log --oneline -3` → `cdf44876 …` / `d9c5fea2 docs(spec): record implementation proof for claude-host` / `4e14f870 …`
- `git merge-base origin/main d9c5fea2` → `678136bd4358bcf9f120504cecd818d36a3d46fe`
- `git diff --stat origin/main...d9c5fea2 -- . ':!docs/spec/claude-host' ':!tests/features/claude_host'` → `31 files changed, 4018 insertions(+)`
- `git diff 9a8ecc3c..d9c5fea2 --stat -- tests/` → (empty)
- `git diff origin/main...d9c5fea2 -- lint/baseline.json` → (empty)
- `git show d9c5fea2:vidbyte/harnesses/native/__init__.py | sha256sum` → `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`
- Suppression grep over the source diff → `exit=1`. REPO_MAP and README byte check → `True 1 True`.
- `PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` → `165 passed in 5.12s`. With `sys.modules['claude_agent_sdk']=None` → `165 passed in 5.44s`.
- Inline §4 snippet run (heredoc to `$PY -P -`) → `completed Found 3 TODO comments.` / `0.0421` / `clients 2 disconnects [1, 1] queries ['List the TODO comments in this repository.']` / `claude.not_installed Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.` / `clients2 0` / `exit=0`
- Inline INV-2 demo → the six lines quoted in R-C2 / `clients constructed: 0` / `exit=0`
- Inline steered stream-death demo → the `AS BUILT` lines in R-C1, then the control `control unsteered: stream ends -> failed claude.process_exited`
- Inline trial of the fix (monkeypatched `_reported` only, then `pytest.main` on the pack) → `WITH FIX: stream ends -> failed claude.process_exited | Respawn, then resume by id.` / `WITH FIX: fake CLIConnectionError -> failed claude.process_exited | Respawn, then resume by id.` / `165 passed in 4.48s` / `PACK WITH FIX exit code: 0`
- `git show {678136bd,d9c5fea2,origin/main}:vidbyte/lib/errors/base.py | grep -n "^class "` → at the PR head, `198:class ClaudeOperationError(VidbyteSdkError)` and `267:class ConfigurationError(VidbyteSdkError)`. At the base and on main, `198:class AgentForkError` and `235:class ConfigurationError`.
- `git log --oneline 5edf1a4d..d9c5fea2` and `git diff --stat 5edf1a4d d9c5fea2` → `d9c5fea2`, `4e14f870`; `2 files changed, 302 insertions(+), 2 deletions(-)` (docs only)
- `git show --stat e7382a26` and `git show --stat f0c84cd0` → `probe.py | 12`, `dataclasses/claude.py | 6`; `failures.py | 7`, `constants/claude.py | 14`
- grep of the new files for `_send_control_request|_internal|str(exc)|codex` → header comments only; codex `exit=1`. `grep -c "^class "` over the new files → `TOTAL 68`. `wc -l` → largest file `578 vidbyte/lib/dataclasses/claude.py`.
- Inline import check → `claude_agent_sdk imported: False` / `claude codes: 16` / `next steps keyed: True` / `spawn fields: 58`
- Inline tool listing → 15 lines, 9 READ and 6 WRITE, all `closed=True` / `clients constructed: 0`
- `grep requires-python pyproject.toml` → `requires-python = ">=3.11"`. `git status --porcelain` → (empty)
