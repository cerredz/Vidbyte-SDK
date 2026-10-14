LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every S4 fix holds against its original probe, but R-2's yield sits after the pump has already taken the steer, so a stop or a failed steer interrupt that lands in that one loop pass no longer discards or withdraws the unsent message (INV-18, §9.2 steer row); the fix is about six lines and keeps 177/177 green.

Scope of this re-review: the branch's own commits `d9c5fea2..615fc54a` (dc9d1734, 4ad8f35d, 52a482d4, 303b8f8a, d52a1fc8, 2e0a9482, 3ce56cd4, c5d243a9, 3cf7b7c8, 5093e792, 04e0254b), checked against spec r5 (3c1f9e4c). The catch-up merge 15124156 changes no PR file. `git diff 04e0254b 15124156 -- <PR paths>` is empty.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **R-1 is fixed at the right layer.**
  - The `if not outcome.result_seen: return None` guard is at failures.py:183. It sits after the assistant-error loop, so rows 5–8 still apply to the whole turn.
  - An unsteered turn that dies before its result is still `claude.process_exited`. Probe: "unsteered END | failed | claude.process_exited".
  - An unsteered turn with the assistant error `rate_limit` and no result is still `claude.usage_limited`.
  - Do not move the guard above the assistant-error loop.
- **R-6 matches D-29 exactly.**
  - `usage_limited` (failures.py:128-130) excludes only `SEVEN_DAY_OPUS` and `SEVEN_DAY_SONNET`.
  - `seven_day_overage_included` and `five_hour` still refuse spawns and still fail a successful turn. That is R-E1, which stays refuted.
  - The model-facing description (descriptions.py:18) states the same rule.
- **R-3 and R-5 are minimal and correct.**
  - Every field the pinned SDK 0.2.165 declares optional is guarded, either with `or ""` or by a record field that accepts None (types.py:1340-1396, 1398-1422, 1743-1777).
  - `description` is read only when the message is a `TaskProgressMessage` (session.py:358-359). `.get` stays only on dict payloads.
  - R-5's second `_guard` (host.py:199) comes before anything is registered, so a refused continue holds no slot and no session id. Probe: "R-5 continue raised: action.precondition_failed | clients: 0 connected_now: 0 | registry: 0".
- **The contracts hold.**
  - Since S2_HEAD the test tree has additions only: `17 0 FEATURE.md`, `2 0 README.md`, `301 0 test_claude_host_review_gaps.py`.
  - `lint/baseline.json` is untouched.
  - The marker blob SHA-256 is `0374a2c8…942f497a`.
  - All 31 non-test paths are exactly §12.3 rows 1–31. The whole PR has 0 deleted lines.
  - Each R-7 mutant (M1–M4) still kills exactly one of the 12 new tests.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Major] [deviations / regression from R-2's fix] vidbyte/harnesses/native/claude/session.py:236-237 (with :173 and :260-265) — the steer yield runs after `_take_steer`, so an explicit interrupt, aclose or the time budget landing in that pass no longer discards the unsent steer, and a failed steer interrupt no longer withdraws it (INV-18, §9.2 steer row)
  Evidence:
  - The code at 615fc54a:
    - :173: `prompt = self._take_steer() if await self._read(stream) else None`. `_take_steer` sets `self._steer = None` and `self._steered = number`.
    - :230: `self._prompts_sent += 1`.
    - :236-237: `if self._steered: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)`.
    - :239: `await client.query(prompt)`.

    So a message exists that is taken but not yet written. The stop paths only clear the `_steer` slot, at :376, :408, :487 and :503. The withdrawal at :390 tests `self._steer is not None`. Neither path can see a message that has already been taken.
  - Probe 1, through the fake seam. A held turn; `client.finish("The first answer.")`; a task scheduled to call `interrupt_claude_turn`; then `await host.steer_claude_session(h, "focus on tests")`:
    - `steer returned None`
    - `marks [('stop-called', ['connect', 'get_server_info', 'query', 'receive_messages']), ('interrupt returned', 'running')]`
    - `calls ['connect', 'get_server_info', 'query', 'receive_messages', 'interrupt', 'query', 'interrupt', 'disconnect']`
    - `queries ['Summarize the repository layout.', 'focus on tests']`

    `interrupt_claude_turn` returned before the steered prompt was written, the prompt was written anyway, and `steer()` reported success.
  - The same probe with the pre-fix d9c5fea2 `ClaudeLiveSession` swapped in, in memory: `stop-called; calls so far [..., 'receive_messages', 'query']`. Before the fix, a stop could only land after the steered prompt was written, so this window is new.
  - Probe 2, the same setup with `host.aclose()` as the stop:
    - `aclose called; calls so far ['connect', 'get_server_info', 'query', 'receive_messages']`
    - `aclose returned; calls [..., 'interrupt', 'query', 'disconnect']`

    The steered prompt is written after aclose began.
  - Probe 3, the EC-19 window with `fake.interrupt_error` set:
    - `steer raised claude.process_exited | interrupt raised CLIConnectionError. | queries at that moment: [..., 'focus on tests']`
    - `calls [..., 'interrupt', 'query', 'disconnect']`
    - `final completed None 'steered answer'`

    The interrupt raised while the message was still unsent. The message was not withdrawn, it was then delivered, and the caller was told the steer failed. A caller that retries would send it twice.
  Failure:
  - **Path 1.** A RUNNING turn has a steer whose interrupted prompt's result has just been read. An `interrupt_claude_turn`, an `aclose` or a watchdog expiry runs during the one-pass yield. The steered prompt is still sent to Claude Code, spending money after the stop, and `steer()` returns None. INV-18 says "An explicit interrupt or an expired time budget discards a pending steer before it is sent", and says the steer call then raises `action.precondition_failed`.
  - **Path 2.** In the EC-19 window, a steer whose `interrupt()` raises leaves its unsent message in the pump. The message is sent while `steer()` raises the mapped error. The §9.2 steer row says "If `interrupt()` raises, the pending message is withdrawn (if not yet sent) and the mapped error is raised". Row 7 says "`steer()` withdraws its unsent message".
  - **Coverage.** No test covers either path. SteerWithdrawalTests raises the interrupt on a held turn whose result is not yet queued.
  Smallest fix:
  - Yield while the message is still in its slot, before it is taken.
    - Drop the yield from `_query`.
    - After `_read` returns True, `await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)` when `self._steer is not None`. One way is to make `_take_steer` async and yield at its top: `prompt = await self._take_steer() if await self._read(stream) else None`.
  - A stop or a failed interrupt in that pass then clears or withdraws `_steer`, and the take returns None.
  - Checked in memory, without touching files, by moving the yield into a wrapped `_read`:
    - the pack: `177 passed in 4.65s`;
    - Probe 1: `steer raised action.precondition_failed`, `calls [..., 'receive_messages', 'interrupt', 'disconnect']`, `final interrupted`;
    - Probe 3: `steer raised claude.process_exited`, no steered query, `final completed 'The first answer.'`.
  - The R-2 order still holds: SteerInResultWindowTests and AC-37(d) both pass.
  - Add one regression case to `test_claude_host_review_gaps.py`: Probe 3, asserting that no `query` carries the message.
  Spec IDs: INV-18, §9.2 `steer_claude_session` row, §12.3 row 7, EC-19, INV-11 (no spend after a stop)

R-C2 [Minor] [D-3 conformance, residue of R-1] vidbyte/harnesses/native/claude/session.py:260-265, 440-447 — a steered prompt that ends without its own result publishes the interrupted prompt's result fields beside the steered prompt's failure
  Evidence: the R-1 probe at 615fc54a:
  - `steered END | failed | claude.process_exited | Claude Code's output ended before the turn's result arrived. | result_text='' terminal_reason='aborted_streaming' num_turns=1`;
  - `steered CLIConnectionError | failed | claude.process_exited | receive_messages raised CLIConnectionError. | ... terminal_reason='aborted_streaming' num_turns=1`.

  `_take_steer` clears only the steer slot. `_result` and `_outcome` keep the interrupted prompt's `terminal_reason`, `num_turns`, `duration_ms`, `stop_reason`, `result_text`, `structured_output` and `permission_denials`. R-1's option (b) fixed only the classification.
  Failure: a steered handle whose steered prompt dies reports `terminal_reason='aborted_streaming'`, plus the interrupted prompt's turn count and denials, on a FAILED `process_exited` result. D-3 says "that next result is the handle's". A caller that branches on `terminal_reason`, or reuses `result_text` for a repair turn (EC-17), reads another prompt's result. The code and status are correct.
  Smallest fix: when `_take_steer` hands out a message, reset those `ClaudeTurnResult` fields to their defaults with one `replace(...)`. Keep `total_cost_usd`, which is cumulative under INV-20.
  Spec IDs: D-3, §9.1 "Turn outcome", §9.2 row 12

R-C3 [Minor] [deviations not recorded] vidbyte/lib/constants/claude.py:52-54; vidbyte/harnesses/native/claude/session.py:62-66, 335-337 — two behaviours the repair added are not in spec r5, which is about to be marked verified
  Evidence:
  - `git grep CLAUDE_STEER_YIELD_SECONDS` finds the constant and session.py only. Spec r5 lists neither the constant nor the extra pump step:
    - §12.3 row 14's constant list;
    - §9.3;
    - row 7's pump sequence ("on the prompt's own `ResultMessage` … then with a pending steer `query(message)`");
    - §17.
  - R-12 now skips a window with an unknown `status` or `overage_status` (`if kind not in _WINDOW_TYPES or status not in _WINDOW_STATUSES or unknown_overage: return`). Two spec rows disagree:
    - EC-52 (spec.md:363) still says only "without `rate_limit_type`, or with a type outside the enum".
    - §12.3 row 12 says "the converters in rows 7–9 map any failure to build these records from SDK data to `claude.protocol_mismatch`".
  - r5 (3c1f9e4c) predates 4ad8f35d and 3cf7b7c8.
  Failure: the spec no longer describes the code on two points. A later reader of EC-52 or row 12 expects an unknown status to fail the turn as `claude.protocol_mismatch`, while the code skips it. A reader of row 7 does not know that a steered prompt yields once before it is sent. Deviations must be recorded under the spec's deviation rule (§17 "Each is the simplest form…").
  Smallest fix:
  - Spec text only:
    - extend EC-52 with the unknown status and overage values, and add an exception to row 12;
    - add §17 deviation 14 for `CLAUDE_STEER_YIELD_SECONDS` and the pump's one yield before a steered prompt (its placement per R-C1);
    - list the constant in row 14.
  - No code change.
  Spec IDs: EC-52, §12.3 rows 7, 12 and 14, §17

VERIFIED CLAIMS:
- **R-1 (dc9d1734): held.**
  - Steered END → `claude.process_exited`, "Claude Code's output ended before the turn's result arrived.".
  - A steered break → "receive_messages raised CLIConnectionError.".
  - Controls: unsteered END and an unsteered break are still `process_exited`. Assistant `rate_limit` with no result is still `usage_limited`.
- **R-2 (4ad8f35d): held for its own race.**
  - SteerInResultWindowTests passes.
  - The probe calls show `'interrupt'` before the second `'query'`.
  - `test_claude_host_stops.py` passes, including AC-37(d): `35 passed` together with the gaps file.
  - The yield delays only steered queries. `_query` has one caller, and `_steered == 0` for the first prompt, because RUNNING is set with no await before it.
  - The fix introduced R-C1.
- **R-3 (52a482d4): held.**
  - A session info without `summary` → `claude.protocol_mismatch` ("get_session_info raised AttributeError.").
  - The drifted ResultMessage test passes.
  - No optional 0.2.165 field is read as if it were required. Checked against types.py: AssistantMessage :1139, TaskProgress/Notification :1211/:1229, ResultMessage :1340, RateLimitInfo :1398, SDKSessionInfo :1743, and ModelUsage keys required :1314.
- **R-5 (303b8f8a): held.** The refusal is `action.precondition_failed`, with clients 0, connected 0 and registry 0. Nothing is held before `_admit`, so there is nothing to free.
- **R-6 (d52a1fc8): held.**
  - opus and sonnet → turn `completed`, and the next haiku spawn `completed`.
  - five_hour and seven_day_overage_included → `failed claude.usage_limited`, and the next spawn is refused `claude.usage_limited`.
- **R-7 (2e0a9482): held.** In-memory mutants against the new file: M1, M2, M3 and M4 each give `1 failed, 11 passed`.
- **R-10 through R-14: held.**
  - R-10: `git grep 'def whole\|\.whole('` finds nothing.
  - R-11: `match kind:` with `case _:`.
  - R-12: its subtests pass.
  - R-13: the five ★ methods are narrated (host.py:246-326).
  - R-14: one slug per rule. The D-13 rule appears 4× as `the-developer-fixes-every-spawn-setting`, and tool_server's slug is distinct.
- **R-4, R-8, R-9 and R-19 (3c1f9e4c): held.** Spec r5 has deviation 12 and deviation 13, the corrected deviation 1, and T-2 with Q-13.
- **AC-1: held.** The §4 snippet, executed verbatim under the fake seam, prints `completed Answer: List the TODO comments in this repository.` / `0.0123`. With no CLI it prints `claude.not_installed Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.` and constructs no client.
- **Contracts: held.**
  - The test-tree numstat shows additions only.
  - The marker SHA matches.
  - The baseline diff is empty.
  - No new suppression. The only `noqa` lines are S2's fixture fakes.
  - origin/main 8387d666 is an ancestor of 615fc54a.
  - The merge touched no PR file.
- **Gates: held.**
  - The pack: `177 passed`.
  - Lint: `SDK-LINT: PASS`.
  - Remote: CI 38502267522 and Static policy 38502269091 both concluded `success` at headSha 615fc54a.

COMMANDS RUN:
- **Fix commits.** `git log --first-parent --format='%h %s' d9c5fea2..615fc54a` lists the 11 fix commits plus 15124156 and 615fc54a. Then `git show --stat` for each, and `git diff d9c5fea2 04e0254b -- vidbyte`.
- **The pack.** `PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` → `177 passed in 5.66s`.
- **The gaps file with the stop tests.** `... test_claude_host_review_gaps.py test_claude_host_stops.py` → `35 passed in 2.54s`.
- **Lint.** `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` → `SDK-LINT: PASS` / `exit=0`. `git status --short` stays empty.
- **Test-tree contract.** `git diff --numstat 9a8ecc3c..615fc54a -- tests/features/claude_host` → `17 0`, `2 0`, `301 0`.
- **Baseline.** `git diff origin/main...615fc54a -- lint/baseline.json` → empty.
- **Marker.** `git show 615fc54a:vidbyte/harnesses/native/__init__.py | sha256sum` → `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- **The merge.** `git diff --stat 04e0254b 15124156 -- <PR paths>` → empty.
- **Remote CI.** `gh run view 38502267522|38502269091 --json conclusion,headSha` → `success`, `615fc54abfff…`.
- **Probes**, inline heredocs through `fx.FakeClaudeSdk().patched()`:
  - R-1 with its controls;
  - R-5, R-6 and R-3;
  - the §4 snippet exec;
  - the R-C1 probes 1, 2 and 3;
  - the pre-fix d9c5fea2 session swapped in memory;
  - the R-C1 candidate fix in memory, giving the pack `177 passed in 4.65s` and both probes conforming;
  - the R-7 mutants M1–M4, each giving `1 failed, 11 passed`.
