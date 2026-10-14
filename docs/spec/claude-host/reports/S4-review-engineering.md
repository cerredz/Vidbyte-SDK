LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — Lifecycle, admission and close handling are solid, but three defects need fixing before merge: D-29's row-5 rule reports successful turns as FAILED (a spec change), a steer that lands in the EC-19 window is aborted by its own interrupt, and a continue can start a turn after aclose; each has a small fix that keeps the 165-test pack green.

Reviewed: `git diff origin/main...d9c5fea2`, with `docs/spec/claude-host/` excluded (44 files, +9848). HEAD has since moved to cdf44876, which changes only `pipeline.md`, so every code line cited below is identical at d9c5fea2.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Admission is all-or-none, with no await.** `_admit` (host.py:352-382) is a plain `def` with no await (AST check). It builds every `ClaudeLiveSession` before it registers any. `spawn_claude_session` and `launch_claude_subagents` contain no await, and continue's only await (host.py:196) comes before `_admit`. So a cancelled caller can never leave a half-registered turn. The launch probe where 3 of 5 turns fail to start gives:
  - results `[failed process_exited ×3, completed ×2]`;
  - disconnects per client `[1, 1, 1, 1, 1]`, max connected 1, connected now 0;
  - a follow-up spawn that completes.
- **One close per client.** Each session has one close task (session.py:403-407) that nothing cancels. The pump, `close()`, the grace and the watchdog all reuse that task, and they wait for it through `asyncio.shield`; a cancelled waiter waits for it again before re-raising (session.py:409-418). Publishing happens only after the close (session.py:187-192). Keep this shape.
- **The grace is aimed at one prompt, and the budget has its own flag.**
  - Prompts sent and prompt results read are counted (session.py:225-231, 305-309), and `_arm_grace` skips a prompt whose result was already read (session.py:382), so AC-37(d) holds.
  - The watchdog sets `budget_expired`, never `interrupted` (session.py:359-361). A caller's interrupt and a steer's interrupt stay distinct.
- **The import boundary and secret hygiene hold.**
  - `claude_agent_sdk` is imported once (sdk.py:52), and none of the six INV-1 imports load it, even though the SDK is installed.
  - Reasons carry only the operation and the exception class (failures.py:68).
  - `env` and `headers` are declared with `repr=False` (lib/dataclasses/claude.py:273, 275, 439).

FINDINGS (ranked, most severe first, max 15)

R-E1 [Blocker] [spec: D-29/D-20 classification] vidbyte/harnesses/native/claude/failures.py:165 — A successful turn that saw a refusing rate-limit window is published FAILED `claude.usage_limited`, discarding the success. The spec requires this, so the fix needs a spec change.
  Evidence:
  - **The code applies row 5 before every result row.**
    - failures.py:165-166: `if outcome.rate_limit_rejected:` / `return FailureCode.CLAUDE_USAGE_LIMITED, "A rate-limit window that refuses new sessions arrived during the turn."`
    - session.py:335-336 sets the flag when the window arrives.
  - **The spec mandates this, so the code is conformant:**
    - D-29 (spec.md:491): "so it fails the turn even when the result is a success";
    - EC-8 (spec.md:319);
    - §9.2 row 5 (spec.md:773): "This holds even when the result is a success."
  - **Fake-SDK probe.** Input: a success result plus `rate_limit_event("seven_day_opus", "rejected", resets_at=FAR_FUTURE_RESET)`, with no overage status. Output: `status: failed | code: claude.usage_limited | next_step: Wait until the reset time, or use an API key. | result_text: 'Parser fixed; 12 tests pass.'`
  - **The same through the real SDK 0.2.165 parser.** `parse_message` received the frames `{"status":"rejected","resetsAt":4102444800,"rateLimitType":"seven_day_opus","isUsingOverage":false,"rateLimitGraceActive":true}` and a `subtype:"success"` result. Output: `published: failed claude.usage_limited | text: 'Parser fixed.' | usage cost: 0.05`.
  - **The combination is a path the CLI is built for, not a rare corner.** In Claude Code 2.1.296 (claude.exe, read through mmap only, never run):
    - the event status is the raw `anthropic-ratelimit-unified-status` header (offset 216232808);
    - the event is built at offset 228033776 (`type:"rate_limit_event",rate_limit_info:r`) and carries `rateLimitGraceActive`;
    - the CLI injects "[Usage limit reached — grace window active. Checkpoint now: finish the current step, then list up to 3 short bullets …]" (offset 216238004).

    So after a rejection, the CLI deliberately lets the turn finish and return a real result.
  - **No test covers the success case.** Every refusing-window row uses `result_message(**error_result)` (test_claude_host_turns.py:199, 373).

  Failure:
  - Input: the model finished its work (success result, result text, cost) after the plan window flipped to `rejected`.
  - Outcome: FAILED `claude.usage_limited` with "Wait until the reset time". `wait_claude_turn` and the tool output both report failure, so a caller or model that branches on status retries or drops work that was completed.
  - This inverts the weighted word "return semantic error messages if something goes wrong" (request.md §D, Prompt 2): nothing went wrong with the turn.

  Smallest fix:
  - **Spec change (spec author).** Adopt D-29's listed runner-up, "let a success result win over it". Edit D-29's last sentence, EC-8 and §9.2 row 5 so the window condition applies only to a turn with no result or an error result. The row order, and therefore D-20, stays the same.
  - **Code, then a one-line change at failures.py:165:**
    ```python
    if outcome.rate_limit_rejected and (outcome.is_error or not outcome.result_seen):
    ```
  - **Also:** add one turns-test row (a success result plus a refusing window ends COMPLETED, and the next spawn is still refused), and update the KNOWN EDGE CASES sentence in the failures.py header.
  - **Validated in-process:**
    - a success now ends `completed`;
    - the follow-up spawn is still `claude.usage_limited`;
    - the pack gives `165 run, 0 failed`.
  - **Not a code-only fix:** until the spec changes, the current code is the conformant one.

  Spec IDs: D-29, EC-8, §9.2 row 5 (the text to change); D-20 is unaffected; weighted word in request.md §D, Prompt 2.

R-E2 [Blocker] [concurrency] vidbyte/harnesses/native/claude/session.py:168-170 — A steer in the EC-19 window (the prompt's result was emitted but not yet read) is written to Claude Code before the steer's own interrupt, which then aborts the steered turn.
  Evidence:
  - **The pump runs before the steer's interrupt task.**
    - session.py:446-449 stores the message, then calls `asyncio.create_task(self._interrupt_client(client, self._prompts_sent, number))`.
    - The pump was already woken by the buffered result, so it runs first: session.py:170 `prompt = self._take_steer() if await self._read(stream) else None`, then :169 `await self._query(client, prompt)`.
  - **In claude-agent-sdk 0.2.165, neither path awaits anything before it writes.**
    - The query goes through client.py:295 `await self._transport.write(`.
    - The interrupt goes through query.py:794 `await self._send_control_request({"subtype": "interrupt"})` to query.py:733 `await self.transport.write(json.dumps(control_request) + "\n")`.
    - Both take subprocess_cli.py:1065 `async with self._write_lock:`, and the anyio lock records its owner before it yields. So whichever task calls `write` first fixes the order on the wire.
  - **The interrupt is not aimed.** The CLI's headless interrupt handler (offset 237600381) accepts `message_uuid` and `for_user_message_uuids`, but the SDK never sends either. So the interrupt stops whatever is running, which here is the steered prompt.
  - **Fake-SDK probe.** Setup: both prompts held; `client.finish("first answer")`, then `await host.steer_claude_session(...)`. Output:
    - `steer() returned: None`;
    - `calls: ['connect', 'get_server_info', 'query', 'receive_messages', 'query', 'interrupt', 'disconnect']`;
    - `status: failed | code: claude.api_error | text: '' | terminal_reason: aborted_streaming`.
  - **Control.** A steer while prompt 1 is still open gives `[... 'interrupt', 'query', ...]` and `completed 'steered answer'`.
  - **The EC-19 test cannot see this.** test_claude_host_stops.py:128 sets `self.fake.interrupt_reply = lambda: result_message(...)`, so prompt 1's result is produced inside `interrupt()` and the interrupt is always written first.

  Failure:
  - Input: a steer arrives while prompt 1's result is buffered.
  - Outcome: `steer()` reports success, but its own interrupt aborts the steered turn. The handle ends FAILED `claude.api_error` with empty text.
  - EC-19 requires "final result = the steered turn". AC-9's order, "the fake records `interrupt()`, then … `query`", is inverted.

  Smallest fix: in `_query`, count the prompt, then yield once before writing a steered prompt:
  ```python
  self._prompts_sent += 1
  if self._prompts_sent > 1:
      await asyncio.sleep(0)  # the steer's interrupt task, already scheduled, writes its interrupt first
  ```
  - **Validated in-process:**
    - race probe: `[..., 'query', 'receive_messages', 'interrupt', 'query', 'disconnect'] completed 'steered answer'`;
    - pack: `165 run, 0 failed`.
  - **Do not await the interrupt task before the query instead.** That also fixes the probe, but it fails `InterruptGraceTests::test_d_no_grace_is_armed_for_a_result_read_before_the_interrupt_returned`, because AC-37(d) needs the steered prompt sent while `interrupt()` is still pending.
  - **Add a regression test:**
    1. Hold both prompts.
    2. In the same step, call `client.finish(...)`, then `await host.steer_claude_session(...)`.
    3. Assert that `interrupt` comes before the second `query` in `client.calls`.
    4. Assert that the turn ends COMPLETED with the steered text.

  Spec IDs: EC-19, AC-9, INV-18, D-3.

R-E3 [Major] [lifecycle] vidbyte/harnesses/native/claude/host.py:196 (with `_admit` at host.py:352) — A continue that is still reading the session file when aclose runs starts a turn after aclose has returned. That turn's client is connected, and nothing can interrupt it.
  Evidence:
  - **Admission never re-checks `_closed`.**
    - The guard runs at host.py:186. Then `info = await ClaudeHistory.session_info(sdk, session_id)` at host.py:196 is the only await, and `self._admit(...)` follows at :211.
    - `_admit` never re-checks `self._closed`.
    - aclose sets `self._closed = True` at host.py:98, under the comment "Refuse every call from now on, so no new turn can start while the others stop."
  - **Fake-SDK probe.** Setup: `fake.history.get_session_info` is blocked on a `threading.Event`, which is released after `await host.aclose()`. Output:
    - `aclose returned; clients: 0`;
    - `continue AFTER aclose returned a handle: 37c5b142`;
    - `late client calls: ['connect', 'get_server_info', 'query', 'receive_messages'] | connected_now: 1`;
    - `wait after close: action.precondition_failed` and `interrupt after close: action.precondition_failed`;
    - only once the prompt ends by itself: `connected_now: 0 | disconnect_calls: 1`.

  Failure:
  - Input: a continue tool call overlaps the end of `async with ClaudeHost()`.
  - Outcome: a `claude` process keeps running, and spending, after aclose has returned, and every call that could stop it is refused.
  - FR-1 requires that "`aclose` stops every live turn and disconnects every client".

  Smallest fix: make `self._guard(operation)` the first line of `_admit`. The guard is synchronous, so registration stays free of awaits.
  - **Validated:**
    - the race now gives `continue after aclose raised: action.precondition_failed | clients: 0`;
    - pack: `165 run, 0 failed`.
  - Add the probe as a CloseTests case.

  Spec IDs: FR-1, AC-21, EC-26.

R-E4 [Major] [spec: D-29, scale] vidbyte/harnesses/native/claude/host.py:374 — A rejected window that applies to one model (`seven_day_opus`) refuses every later spawn of every model until it resets, up to 7 days, even though Claude Code still serves the other models.
  Evidence:
  - **The refusal ignores which model a window applies to.**
    - host.py:374 is `if any(ClaudeFailureMapper.usage_limited(window) for window in self._rate_limits.values()):`.
    - `usage_limited` (failures.py:116-120) checks only the status, the reset time and the overage. Neither checks the window type against the request's model.
  - **Probe.** An Opus turn saw `seven_day_opus` rejected, with no overage status. Then `spawn_claude_session(ClaudeSpawnRequest(..., model="haiku"))` gave `claude.usage_limited`.
  - **Claude Code 2.1.296 limits only Opus requests under that claim.**
    - offset 216213161: `S=s["anthropic-ratelimit-unified-representative-claim"]==="seven_day_opus",A=e.includes("opus");if(S&&!A)return null;`
    - The CLI's own mock (offset 214383175, `case"opus-limit":{this.exceededLimits=[{type:"seven_day_opus",…`) sets the unified status to `rejected`, so this event shape is real.
  - **The block cannot clear itself.** Windows update only from live streams (D-8), and the refusal stops every new stream. The block therefore clears only at `resets_at` or in a new host, which is D-8's own reason for not stopping on `allowed_warning`.

  Failure:
  - Input: a long-lived host (for example `ClaudeTools` served over MCP) whose Opus turn hit the weekly Opus cap.
  - Outcome: the host refuses every Sonnet and Haiku spawn for up to a week with "Wait until the reset time", although the CLI would run them.

  Smallest fix: this is the spec author's decision, since D-29 is still open.
  - Leave `seven_day_opus` and `seven_day_sonnet` out of `usage_limited`. In code, that is one type check.
  - These windows are still recorded and still shown by `get_claude_rate_limits`.
  - A truly refused Opus turn still fails through the assistant-error `rate_limit` row.
  - Caveat: only the Opus check was found in the binary; the Sonnet behaviour is assumed to match.
  - [scope-adding] follow-up: refuse only when the request's model matches the window.

  Spec IDs: D-29, D-8, EC-7.

R-E5 [Major] [test quality] tests/features/claude_host/test_claude_host_admission.py:348-353; test_claude_host_stops.py:126-135, 463-475 — Four guarded behaviours can be removed while the pack stays green, and the EC-19 and AC-37(c) tests cannot see what they are named for.
  Evidence:
  - **Mutation run (in-process, 165 tests per mutant):**

    | Mutant | Change | Result |
    |---|---|---|
    | M0 | baseline | 165 run, 0 failed |
    | M1 | overage `allowed_warning` no longer counts as allowed (failures.py:119) | 0 failed: SURVIVES |
    | M2 | a rejected window with `resets_at=None` refuses (failures.py:120) | SURVIVES |
    | M3 | a steer whose `interrupt()` raises keeps its message pending (session.py:374-375 removed) | SURVIVES |
    | M4 | a cancelled close waiter re-raises without waiting for the close (session.py:417 removed) | SURVIVES |
    | M6 (control) | the watchdog keeps a pending steer | killed by `PendingSteerDiscardTests.test_the_time_budget_discards_a_pending_steer` |

    The M6 kill shows the harness does detect mutants.
  - **Three plausible bugs that no test catches:** R-E2, R-E3 and M1.
  - **Blind or weak tests:**
    - The EC-19 test (stops.py:128) produces the result inside `interrupt()`.
    - test_c (stops.py:471-475) accepts either `None` or a raise. Under `ANSWER_NEVER` the steer returns before the grace ends, so the raise branch never runs.
    - EC-8's "even when its result is a success" has no test.
  - **No test could pass on main.** `git ls-tree origin/main vidbyte/harnesses/ | grep -c native` returns 0.

  Failure: a refactor ships green if it breaks any of these:
  - D-29's overage rule;
  - §12 row 7's "steer() withdraws its unsent message" (a failed steer would still be sent later, and a retry would be refused as already pending);
  - the cancel-safe close wait (INV-8).

  Smallest fix:
  - In the admission cases (admission.py:348-353), add two rows, both expected not to refuse:
    - "rejected, overage allowed_warning";
    - "rejected, resets_at None".
  - Add a SteerTests case with `fake.interrupt_error` set. Assert that the error is raised, that no `query` carries the message, and that a second steer is accepted.
  - Add a CloseTests case that cancels `aclose()` while `disconnect_gate` holds. Assert that the cancellation surfaces only after `disconnect_finished`.
  - Add the R-E2 and R-E3 regressions, and the R-E1 row once the spec is settled.

  Spec IDs: D-29, D-4 (§12 row 7), INV-8, EC-19, AC-9, AC-37.

R-E6 [Minor] [robustness] vidbyte/harnesses/native/claude/session.py:327, 330 — An unknown rate-limit status or overage value fails the whole turn as `claude.protocol_mismatch`, while an unknown window type is skipped (EC-52).
  Evidence:
  - **The conversions raise.** `status=ClaudeRateLimitStatus(info["status"])` and `ClaudeRateLimitStatus(overage)` raise `ValueError` inside `_read`, which session.py:247 maps to a protocol mismatch.
  - **Nothing upstream filters the value.** SDK 0.2.165 passes the value through raw (message_parser.py:361 `status=info["status"],`), and the CLI copies the raw header (offset 216232808).
  - **Probe:**
    - `status 'throttled' (unknown), five_hour -> failed claude.protocol_mismatch | receive_messages raised ValueError. | text: ''`;
    - overage `'blocked'` gives the same;
    - control, `unknown type 'ten_minute' (EC-52 control)`, gives `completed … 'Parser fixed.'`.

  Failure: if the server adds a new status string, every turn that receives it fails and loses its result. No current CLI value triggers this.

  Smallest fix: in `_on_rate_limit`, return early, like the type check at :322, when the status (or an overage status, if one is present) is not a `ClaudeRateLimitStatus` value.

  Spec IDs: EC-52 (the analogous rule).

R-E7 [Minor] [data/scale] vidbyte/harnesses/native/claude/session.py:78, 121, 134 — Each finished handle keeps its request, its SDK client object and every completed interrupt task until aclose, so EC-55's "one small entry per turn" understates the growth.
  Evidence:
  - **Probe:**
    - `finished turns: 3 | … each still holds its request and SDK client: True`;
    - `steered turn keeps done interrupt tasks: 3 | all done: True`.
  - **Interrupt tasks are only ever added.** `_interrupts.add(...)` appears at :362, :450 and :478, and nothing removes them.
  - The request keeps its prompt content, which can include base64 images.

  Failure: a long-lived host grows by a client object, a request and N tasks per turn. D-23's retention itself is settled; only its size is at issue.

  Smallest fix:
  - After the close in `run()`'s `finally`, set `self._client = None`. After publishing, `steer()`, `interrupt()` and `close()` all take their early or refusal paths (`_stopping` or `_closing` is already set).
  - Add `task.add_done_callback(self._interrupts.discard)`.
  - Or restate EC-55.

  Spec IDs: EC-55, D-23.

R-E8 [Minor] [security] vidbyte/harnesses/native/claude/host.py:203-208, with vidbyte/tools/toolsets/claude.py:52 — T-2 says every path field is fixed by the base request, but continue breaks that: with the default base request, a model can run Claude Code in any project folder that has a session.
  Evidence:
  - host.py:208 sets `cwd=template.cwd or info.cwd`.
  - The continue tool passes `request=self._request` whole (vidbyte/tools/builtins/claude/sessions.py:72).
  - `base = ClaudeSpawnRequest() if request is None else request` (toolsets/claude.py:52), so the default base request has `cwd=""`.
  - `list_claude_sessions` lists every project; this is accepted under Q-3.
  - T-2 (spec.md:941) says: "Every permission, sandbox, budget and path field is fixed by the developer's base request (D-13)."

  Failure:
  1. A prompt-injected model with the WRITE tools calls `list_claude_sessions` to find another project's session.
  2. It calls `continue_claude_session` on that session.
  3. Claude Code runs in that project's folder, with the developer's permission mode and that folder's project settings.

  This is a cross-project action that can write, which goes beyond T-2's accepted "read other projects' transcripts".

  Smallest fix:
  - Now, documentation only (D-27 is settled): state this in T-2 and in the KNOWN EDGE CASES of toolsets/claude.py and builtins/claude/__init__.py, and advise setting `cwd` on the base request. D-27 then refuses any session whose recorded cwd differs.
  - [scope-adding] follow-up, as a Q-item for the user: refuse a continue started from a tool when the recorded cwd differs from the base request's cwd.

  Spec IDs: T-2, D-27, D-13.

VERIFIED CLAIMS:
- **Pack green:** `165 passed in 5.61s`. HELD.
- **The riskiest test is stable.** `CloseTests::test_the_turn_ends_only_after_its_one_disconnect_finishes` passed in every run (no flake):
  - 10 separate runs now (`1 passed`, 0.87–1.10 s);
  - 25 separate runs earlier (0.78–0.82 s);
  - 700 in-process runs (300 of this test, plus 400 steer and grace tests), with 0 failures and 0 errors.

  The stops file alone: `23 passed`, 5 runs out of 5. HELD.
- **INV-1:** the SDK is installed, yet after the six imports `claude_agent_sdk loaded … False`. HELD.
- **INV-3 and a caller cancelled mid-spawn:**
  - spawn, launch and `_admit` contain no awaits; continue's only await is at line 196, before `_admit`;
  - a launch returns its handles as `['queued']`. HELD.
- **INV-5, INV-6 and INV-8 when 3 of 5 launch turns fail to start:** each client disconnected once, max connected equals the limit, connected now is 0, and a follow-up spawn completes. HELD.
- **INV-7 and INV-8 when close races the natural end:**
  - both paths reuse one `_closing` task (session.py:403-407);
  - a cancelled waiter waits again before re-raising (:416-418). HELD. (No test pins the wait-again step; see R-E5, M4.)
- **INV-18:**
  - **Two steers in a row:** the second is refused while the first is pending (session.py:442-443). HELD.
  - **A steer after the result but before the grace ends:** the result cancels the grace (:307-309), and `_arm_grace` skips a prompt whose result was already read (:382). HELD.
  - **A steer in the EC-19 window:** NOT HELD (R-E2).
- **An exception inside the pump:**
  - every SDK call is mapped at its call site (:203-204, :213-214, :230-231, :246-247);
  - the `finally` closes, then publishes (:180-192). HELD.
- **`__aexit__` while turns run:** AC-21 holds. NOT HELD for the continue race (R-E3).
- **INV-9:** `wait` uses `wait_for` on `_done.wait()` only (:494-496). HELD.
- **INV-10:** a request's path is screened, and a path that screens to empty never falls back to the host's (host.py:357-359). HELD.
- **INV-12 and T-3:** reasons name the operation and the class (failures.py:68); `repr=False` on `env` and `headers`. HELD.
- **INV-15:** the guard checks entry, close and loop (host.py:334-350). HELD; R-E3 is the FR-1 gap at its edge.
- **INV-16:** `to_thread` is used at history.py:41, 50, 67 and 76. HELD.
- **INV-20:** usage is read from every result, injected results included, before the origin check (session.py:262-274). HELD.
- **D-30** (host.py:324-328), **D-31** (lib/dataclasses/claude.py:503-512, 521-531 and 547-548, which match spec §9.1), **D-32** (failures.py:135-136, 156-157) and **D-33** (host.py:204, normcase plus abspath). HELD.
- **D-29 as written:** failures.py:116-120 implements it exactly. HELD. The defects are in the rule itself (R-E1, R-E4).
- **The sandbox `network` rule:** with no domains, `{'enabled': True}`; with `pypi.org`, `{'enabled': True, 'network': {'allowedDomains': ['pypi.org']}}`. HELD.
- **Growth:**
  - **History paging:** `limit=None` returns every item, as FR-8 and the tool's description say. Not a finding.
  - **Steer queue:** at most one steer is pending at a time.
  - **Retained objects:** see R-E7.
- **T-1 and T-4:** HELD. **T-2:** see R-E8.

COMMANDS RUN:

W is the worktree, PY is `.venvs/sdk-claude-host/Scripts/python.exe`, and every probe is inline Python run through `FakeClaudeSdk().patched()`.

**Git (read-only):**
- `git diff --stat origin/main...d9c5fea2 -- . ':(exclude)docs/spec/claude-host'`
  → `44 files changed, 9848 insertions(+)`
- `git log --oneline -5` and `git diff --stat d9c5fea2 HEAD`
  → `cdf44876 docs(spec): record claude-host S3 done…` / `docs/spec/claude-host/pipeline.md | 47 +++…`
- `git ls-tree origin/main vidbyte/harnesses/ | grep -c native`
  → `0`

**Tests:**
- `PYTHONPATH=$W $PY -P -m pytest tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml`
  → `165 passed in 5.61s`
- The same command for `test_claude_host_stops.py`, 5 runs
  → `23 passed in 2.22s` … `2.25s`
- The same command for `…::CloseTests::test_the_turn_ends_only_after_its_one_disconnect_finishes`, 10 runs
  → `1 passed in 0.87s` … `1 passed in 1.10s` (10 of 10); 25 earlier runs → `1 passed in 0.78–0.82s`
- An in-process repeat of the riskiest test plus the steer and grace tests
  → `ran 700 failures 0 errors 0 in 47.0s`

**Probes:**
- The R-E1 probe (fake SDK, then the real-SDK `parse_message` frames, then the row-5 change patched in)
  → `as built | status: failed | code: claude.usage_limited | …` / `follow-up spawn (model haiku): claude.usage_limited` / `real-SDK-parsed frames | published: failed claude.usage_limited | text: 'Parser fixed.' | usage cost: 0.05` / `with the row-5 change | status: completed …` / `pack with the row-5 change: 165 run, 0 failed, 0 errors`
- The R-E2 race probe and its control
  → `EC-19 race … calls: [… 'query', 'interrupt', 'disconnect'] … failed | claude.api_error` / `control … completed 'steered answer'`
- The R-E2 fix A, patched in
  → `race with fix A …: [… 'interrupt', 'query', 'disconnect'] completed 'steered answer'` / `pack with fix A: 165 run, 0 failed, 0 errors`
- The R-E2 fix B (await the interrupt task), run earlier
  → 1 failure: `InterruptGraceTests::test_d_no_grace_is_armed_for_a_result_read_before_the_interrupt_returned`
- The R-E3 probe and its fix
  → `as built | aclose returned; clients: 0` / `continue AFTER aclose returned a handle: 37c5b142` / `connected_now: 1` / `with _guard first in _admit | … continue after aclose raised: action.precondition_failed | clients: 0` / `pack with the fix: 165 run, 0 failed, 0 errors`
- Mutation run
  → `M1 … SURVIVES`, `M2 … SURVIVES`, `M3 … SURVIVES`, `M4 … SURVIVES`, `M6 control … 1 failed -> killed by test_claude_host_stops.PendingSteerDiscardTests.test_the_time_budget_discards_a_pending_steer`
- The unknown-status and retention probe
  → `… 'throttled' … failed claude.protocol_mismatch` / `unknown type 'ten_minute' (EC-52 control) -> completed` / `each still holds its request and SDK client: True` / `steered turn keeps done interrupt tasks: 3 | all done: True`
- The launch probe with 3 of 5 failed starts
  → `results: [('failed', 'claude.process_exited') ×3, ('completed', None) ×2]` / `disconnects per client: [1, 1, 1, 1, 1] | max connected: 1 | connected now: 0` / `follow-up: completed`
- The INV-1 and AST probe
  → `claude_agent_sdk loaded after the six imports: False` / `continue_claude_session … awaits at lines: [196]` / `_admit FunctionDef awaits at lines: []`

**Source and binary reads (read-only):**
- `grep -n` in claude_agent_sdk 0.2.165
  → `query.py:733 await self.transport.write(json.dumps(control_request) + "\n")`, `client.py:295 await self._transport.write(`, `query.py:794 … {"subtype": "interrupt"}`, `message_parser.py:361 status=info["status"],`, `subprocess_cli.py:1065 async with self._write_lock:`
- An mmap search of `C:/Users/422mi/.local/bin/claude.exe` (2.1.296; read only, never executed)
  → `size 260489376`, `214383175 case"opus-limit"…`, `216213161 S=s["anthropic-ratelimit-unified-representative-claim"]==="seven_day_o…`, `216232808 let n=e.get("anthropic-ratelimit-unified-status")||"allowed"`, `216238004 grace window active. Checkpoint now: finish the`, `228033776 type:"rate_limit_event",rate_limit_info:r`; the interrupt handler at 237600381 was found in an earlier pass.
