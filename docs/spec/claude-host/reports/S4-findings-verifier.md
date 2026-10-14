# S4 findings verifier — claude-host

- Stage: S4 findings verifier.
- Inputs: reports/S4-review-conformance.md, S4-review-conventions.md and S4-review-engineering.md; spec.md (r4); request.md; pipeline.md; reports/S3-implementer.md.
- Diff: `origin/main...d9c5fea2`.
- HEAD: cdf44876, whose code is identical to d9c5fea2. `git diff d9c5fea2 HEAD -- vidbyte tests lint | wc -l` gives `0`.
- Output: `docs/spec/claude-host/review.md`, plus this report. No commits.

## Baseline and gate evidence (final lines)

The pack at HEAD, unmodified: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml`
```
........................................................................ [ 87%]
.....................                                                    [100%]
165 passed in 5.79s
```

Lint at HEAD, as built: `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY $W/lint/run.py`
```
S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

`git status --porcelain` after the lint showed only the three S4 review reports as untracked. The run left nothing in the tree.

## Merge map

| Original | Lens · severity | Merged | Disposition |
|---|---|---|---|
| R-C1 | conformance · Blocker | R-1 | Confirmed Blocker (code) |
| R-E2 | engineering · Blocker | R-2 | Confirmed Blocker (code); the reviewer's fix form is changed for lint A007 |
| R-V1 | conventions · Blocker | R-3 | Confirmed Blocker (code) |
| R-C3 | conformance · Major | R-4 | Confirmed Major (deviation-entry) |
| R-V2, pump chain | conventions · Blocker | R-4 | Merged with R-C3; downgraded to Major |
| R-V2, interrupt chain | conventions · Blocker | — | Refuted (row 7 prescribes this shape) |
| R-E3 | engineering · Major | R-5 | Confirmed Major (code); a smaller, principle-1-safe fix form is proposed |
| R-E4 | engineering · Major | R-6 | Confirmed Major (spec-change); absorbs R-E1's per-model case |
| R-E1 | engineering · Blocker | — | Refuted (spec rule upheld); per-model case → R-6 |
| R-E5 | engineering · Major | R-7 | Confirmed Major (code, new tests only) |
| R-C4 | conformance · Minor | R-8 | Minor, trivial |
| R-V4 | conventions · Major | R-8 (wording) + R-15 (move) | Downgraded to Minor |
| R-C5 | conformance · Minor | R-9 | Minor, trivial |
| R-V8 | conventions · Minor | R-10 | Minor, trivial |
| R-V7 | conventions · Minor | R-11 | Minor, trivial |
| R-E6 | engineering · Minor | R-12 | Minor, trivial |
| R-V5 | conventions · Minor | R-13 | Minor, trivial |
| R-V6 | conventions · Minor | R-14 | Minor, trivial |
| R-V3 | conventions · Major | R-16 | Downgraded to Minor, follow-up |
| R-C2 | conformance · Major | R-17 | Downgraded to Minor, follow-up |
| R-E7 | engineering · Minor | R-18 | Minor, follow-up |
| R-E8 | engineering · Minor | R-19 | Minor, follow-up |
| R-V9 | conventions · Minor | R-20 | Minor, follow-up ([scope-adding], NG-8) |
| (new) | verifier blind spot | R-21 | Minor, follow-up |

Totals: 3 confirmed Blockers, 4 confirmed Majors and 14 Minors. 2 findings were refuted: R-E1, and the interrupt-chain part of R-V2. 4 were downgraded: the pump part of R-V2, R-C2, R-V3 and R-V4.

## How the probes were run

Every probe is inline Python read from a Bash heredoc (`$PY -P -` with `PYTHONPATH=$W` and `PYTHONDONTWRITEBYTECODE=1`), so no file was written. Each starts with `sys.path.insert(0, W + "/tests/features/claude_host")` and `import claude_host_fixtures as fx`. Every `ClaudeHost` runs inside `fake.patched()`, the `ClaudeSdkLoader.load` seam. Candidate fixes were applied as in-memory monkeypatches, and the pack was then run in the same process with `pytest.main([...same args...])`.

## Verification of each Blocker and Major

### R-1 (R-C1) — a steered turn whose stream dies takes the interrupted prompt's code

**Setup.**
- `fake.hold(DEFAULT_PROMPT)`.
- `fake.reply(STEER, fx.init_message(), fx.END_OF_STREAM)`, or the same with `fx.CLIConnectionError("stream broke")` in place of END_OF_STREAM.
- Spawn, wait until one query has been sent, `await host.steer_claude_session(h, STEER)`, then `wait_claude_turn`.

**Output with no fix:**
```
R-C1 steered-stream-ends: failed claude.api_error | reason: The turn ended with an error result: subtype error_during_execution, terminal_reason aborted_streaming, api_error_status None, assistant errors none.
R-C1 steered-stream-raises: failed claude.api_error | reason: The turn ended with an error result: subtype error_during_execution, terminal_reason aborted_streaming, api_error_status None, assistant errors none.
R-C1 control (no steer, stream ends): failed claude.process_exited
```

**The trace:**
- `_on_result` stores the interrupted result's `is_error=True` and `subtype`/`terminal_reason` (session.py:294-306).
- `_take_steer` (session.py:250-255) clears none of them.
- `_publish` computes `result_seen = bool(self._prompts_sent) and self._results_read == self._prompts_sent` (session.py:428), which is False here.
- `classify_turn` runs `_reported` (failures.py:93) before `if not outcome.result_seen` (:98), so `if outcome.is_error:` (:174) wins.

**Spec:**
- D-3 (spec.md:465): "When the pump reads the interrupted turn's result, it sends the message with `query()`, and that next result is the handle's."
- §9.2 row 12 (spec.md:780): "The stream ended or the process exited without a result."

**With the fix** (a guard after the assistant-error loop):
```
R-C1 steered-stream-ends: failed claude.process_exited | reason: Claude Code's output ended before the turn's result arrived.
R-C1 steered-stream-raises: failed claude.process_exited | reason: receive_messages raised CLIConnectionError.
```

Pack with this fix only:
```
........................................................................ [ 87%]
.....................                                                    [100%]
165 passed in 4.29s
```

**Severity.** Kept at Blocker: the handle reports a wrong code ("Retry with backoff." instead of "Respawn, then resume by id."), and its reason describes the wrong prompt. Fix-kind: code. No spec text changes, because D-3 and INV-7 already say the steered prompt's result is the handle's.

### R-2 (R-E2) — a steer in the EC-19 window is aborted by its own interrupt

**Setup.**
- `fake.hold(DEFAULT_PROMPT, STEER)`.
- After the first query, call `client.finish("first answer")`, then `await host.steer_claude_session(h, STEER)` in the same step.
- `await fx.settle()`. If the steered prompt is still open, finish it with "steered answer".

**Output with no fix:**
```
R-E2 steer() returned None; calls ['connect', 'get_server_info', 'query', 'receive_messages', 'query', 'interrupt', 'disconnect']
R-E2 result: failed claude.api_error | text '' | terminal_reason 'aborted_streaming'
```

**The real SDK orders the wire the same way.** I read claude-agent-sdk 0.2.165 and anyio 4.15.1 as text:
- `ClaudeSDKClient.query` reaches `await self._transport.write(` (client.py:295) with no earlier await.
- `ClaudeSDKClient.interrupt` → `await self._query.interrupt()` (client.py:312) → `await self._send_control_request({"subtype": "interrupt"})` (query.py:794). That reaches `await self.transport.write(json.dumps(control_request) + "\n")` (query.py:733), and lines 706-732 contain no await.
- `SubprocessCLITransport.write` takes `async with self._write_lock:` (subprocess_cli.py:1065).
- anyio `Lock.acquire` (_backends/_asyncio.py:1953-1968) runs `await AsyncIOBackend.checkpoint_if_cancelled()`, which yields only when a cancel is pending (:2567-2579). It then sets `self._owner_task = task` before `cancel_shielded_checkpoint()`.

So whichever task calls `write` first owns the order on the wire. The pump runs first because the buffered result woke it before `steer()` created the interrupt task.

**Fix forms tried:**

| Fix | Race probe | Lint |
|---|---|---|
| Reviewer's A: `if self._prompts_sent > 1: await asyncio.sleep(0)` | `[…, 'interrupt', 'query', 'disconnect']` → `completed 'steered answer'`; pack `165 passed in 4.20s` | **Fails A007, which is blocking (severity "blocking", a007_operational_constants.py:153).** In-memory analyzer on the patched session.py text: `[(228, '1', "operational call 'sleep' receives a literal"), (229, '0', "operational call 'sleep' receives a literal")]` |
| A′: `if self._steered: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)`, with the constant = 0 in lib/constants/claude.py | `['connect', 'get_server_info', 'query', 'receive_messages', 'interrupt', 'query', 'disconnect'] -> completed 'steered answer'`; pack `165 passed in 4.21s` | `A007: [] \| S024: []` |

`_steered` is non-zero exactly when `_take_steer` has handed a steer to the pump (session.py:252-254). So A′ yields before the second and later prompts, and never before the first.

The R-E2 report also says that awaiting the interrupt task instead breaks `InterruptGraceTests::test_d_…`. I did not re-run that variant, and no recommendation depends on it.

**Severity.** Kept at Blocker: `steer()` reports success, but the steered work is lost and the handle FAILS. This inverts EC-19 (spec.md:330) and AC-9 (spec.md:275). Fix-kind: code.

### R-1 and R-2: shared root cause?

No. Both end FAILED `claude.api_error`, but through different mechanisms:
- In R-1, the steered prompt never gets a result, so `result_seen` is False and stale facts from prompt 1 win.
- In R-2, the steered prompt gets its own aborted result, so `result_seen` is True and that result's `is_error` is correct for it. The bug is the order on the wire.

| Fixes applied | R-1, stream ends | R-1, stream raises | R-1 control | R-2 race |
|---|---|---|---|---|
| none | api_error | api_error | process_exited | `query, interrupt` → api_error |
| R-1 only | process_exited | process_exited | process_exited | `query, interrupt` → api_error |
| R-2 only | api_error | api_error | process_exited | `interrupt, query` → completed |
| both | process_exited | process_exited | process_exited | `interrupt, query` → completed |

Neither fix covers the other. Pack with R-1 + R-2 + R-5 patched together:
```
........................................................................ [ 87%]
.....................                                                    [100%]
165 passed in 4.31s
```

### R-3 (R-V1) — reading SDK records by reflection hides contract drift

**Probe.**
- `del fake.history.infos[sid].summary`, simulating a 0.2.x release that renames the required `summary`.
- A `ResultMessage` with `del r.terminal_reason; del r.result`.

Output:
```
drifted SDKSessionInfo -> returned, summary=''
drifted ResultMessage -> completed None | result_text='' terminal_reason=''
```

**SDK 0.2.165 types.py** (`SDKSessionInfo` @1743, `ResultMessage` @1340):
- `session_id: str` and `summary: str` are required.
- `result: str | None = None`, `stop_reason: str | None = None` and `terminal_reason: str | None = None` are declared optional fields.
- `TaskNotificationMessage` (@1229) has no `description`. `TaskProgressMessage` (@1211) has `description: str`.

**The pin is a range.** pyproject.toml:43 has `"claude-agent-sdk>=0.2.165,<0.3.0",`, so drift can arrive without a pin change.

**Field guide** (C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/class-bound-helpers.md, section "Normalize the concrete SDK contract…"):
- :26: "**Do:** Read the pinned SDK's fields directly; preserve missing values and provider usage-snapshot meaning."
- :27: "**Because:** Generic reflection with empty defaults masks contract drift".

The section's "When" covers converting a native harness result, which is what these converters do.

**Severity.** Kept at Blocker: this contradicts a field-guide lesson, and the probe shows the masked outcome (a COMPLETED turn with empty text instead of `claude.protocol_mismatch`).

**Fix boundary** (my addition to the reviewer's fix):
- Read directly: the SDK dataclass fields.
- Keep `.get`: the plain-dict payloads, which are the initialize answer (`info.get("hooks_applied")`, session.py:212), the `usage` TypedDict (session.py:343-349), the `origin` dict's `kind` (:276) and `SessionMessage.message` (history.py:103).
- Keep `.get`: `description`, which is absent on `TaskNotificationMessage`.

Fix-kind: code.

### R-4 (R-C3 + R-V2 pump) — two-level pump chain, not recorded in §17

**The chain.**
- session.py:170: `prompt = self._take_steer() if await self._read(stream) else None`.
- session.py:238-245: `_read` calls `self._on_result`, `_on_assistant`, `_on_rate_limit` and `_on_task`.

**Why it is forced.**
- S024 (lint/rules/s024_maximum_control_flow_nesting.py) has `MAX_NESTING_DEPTH = 3` at :22. `_visit_node` counts `If`, `For`/`AsyncFor`, `With`/`AsyncWith`, `Try` and `Match`; `ast.While` is not counted. `_record` flags `depth + 1 > 3`.
- Folded into `run`, the read would sit at: outer `try` (1) → its own `try` to map `receive_messages` errors (2) → `async for` (3) → dispatch `if` (4). The `while` adds nothing. Depth 4 is flagged.
- A reader class would be class 70 against the 69/69 budget in §8.4.

**Not recorded.** §17 deviation 7 (spec.md:1483) names `_take_steer`, `_stop_waiting`, `_on_assistant` and `_refused`, but not `_read`. S3-implementer.md:253 admits the extra level.

**Rule text.**
- AGENTS.md principle 1 (AGENTS.md:23): "that second function should not call a third".
- NFR-4 (spec.md:417): "Call chains stay one level deep".

Severity and fix are adjudicated in A1 below. Fix-kind: deviation-entry.

### R-5 (R-E3) — continue racing aclose

**Setup.** `fake.history.get_session_info` is replaced, before `fake.patched()`, by a wrapper that sets `entered` and blocks on a `threading.Event`. The continue task starts, `entered` is awaited, then `await host.aclose()`, then the event is released.

**Output with no fix:**
```
aclose returned; clients: 0
continue AFTER aclose returned a handle: 9c4b7033
late client calls: ['connect', 'get_server_info', 'query', 'receive_messages'] | connected_now: 1
wait after close: action.precondition_failed
interrupt after close: action.precondition_failed
after the prompt ends by itself: connected_now: 0 | disconnect_calls: 1
```

**Reviewer's fix** (`_guard` as the first line of `_admit`):
```
continue after aclose raised: action.precondition_failed | clients: 0
```
Pack: `165 passed in 4.23s`.

**Fix (b)** (`self._guard(operation)` re-run in `continue_claude_session` right after `await ClaudeHistory.session_info(...)`, applied by exec-ing the method's own source with that one line added):
```
variant (b): continue after aclose raised action.precondition_failed | clients: 0
...
165 passed in 4.17s
```

**Why (b) is preferred.** `_admit` is a helper of `ClaudeHost`, so calling `_guard` from it makes `continue → _admit → _guard` a helper calling a helper. That is the AGENTS.md principle-1 shape R-4 is about. (b) keeps the call in the main function. Continue is the only ★ method with an await before `_admit`: host.py's awaits are at :196 for continue, and spawn (:167-175) and launch (:313-332) have none.

Spec: FR-1 (spec.md:385). Severity stays Major: the window is narrow, and the late process ends with its own turn, so it is not orphaned forever. Fix-kind: code.

### R-6 (R-E4) — a per-model rejected window blocks every model

**Code.** `usage_limited` (failures.py:116-120) checks only the status, the reset time and the overage. Neither host.py:374 nor session.py:335 looks at `rate_limit_type`, so a `seven_day_opus` window refuses a Haiku spawn and fails a Sonnet turn. The reviewer's spawn probe (`claude.usage_limited`) follows directly from these lines.

**CLI evidence.** Claude Code 2.1.296 was read by mmap from `C:/Users/422mi/.local/share/claude/versions/2.1.296` (260,489,376 bytes, the build the reviewers cited) and never executed.
- 216212890: `function x_s(e,r){if(!Tlt())return null;…` This is the vendor's rate-limit simulator. It is gated off in this build: `function Tlt(){return!1}` at 214386227.
- 216213161: `S=s["anthropic-ratelimit-unified-representative-claim"]==="seven_day_opus",A=e.includes("opus");if(S&&!A)return null;` That is, no 429 for a non-Opus model under an Opus weekly claim.
- In the same function: `if(h==="rejected"&&(!y||y==="rejected"))return new xt(429,…)`. This matches D-29's overage rule, which corroborates the rest of D-29.
- 216227817: "Switch models to keep working.", the CLI's own advice for a model-specific limit.
- 214383175: `case"opus-limit":{this.exceededLimits=[{type:"seven_day_opus",…` (cited by R-E4).
- **The binary changed during this review.** `~/.local/bin/claude.exe` auto-updated to 2.1.299 (269,231,264 bytes, mtime 2026-10-13 21:39:35 -0400). 2.1.299 keeps the same check under new names: offset 224180529, `function VCs(e,r){if(!Kut())return null;…==="seven_day_opus",v=e.includes("opus");if(S&&!v)return null;`.

**Spec.**
- D-8 (spec.md:470) rejects stopping on `allowed_warning` because "Windows update only on live streams, so a warning would block every spawn until the host closed". A per-model rejection blocks the same way, for up to 7 days.
- Against the user's words, "return semantic error messages if something goes wrong" (request.md §D, Prompt 2): refusing a Haiku spawn with "Wait until the reset time" when the CLI would serve it is a wrong semantic error.

**Confidence: medium.** The simulator is the vendor's model of the server, not an executed path, and Sonnet is assumed to match Opus (only the Opus check exists in the binary).

Fix-kind: spec-change. Spec lines: D-29 (spec.md:491), D-8 (:470), EC-7 (:318), EC-8 (:319), §9.2 row 5 (:773). Code after that: one type check in `usage_limited`, plus test rows in R-7.

### R-7 (R-E5) — mutants that survive

One process per mutant; in each, the mutant is monkeypatched in and then `pytest.main` runs the pack.

| Mutant | Change | Final line |
|---|---|---|
| M1 | overage `allowed_warning` no longer counts as allowed (`usage_limited` with `(S.ALLOWED,)`) | `165 passed in 4.21s` |
| M2 | `resets_at=None` refuses (`(window.resets_at is None or window.resets_at > time.time())`) | `165 passed in 4.24s` |
| M3 | `_interrupt_client` without the steer withdrawal (session.py:374-375) | `165 passed in 4.29s` |
| M4 | `_await_close` re-raises a cancel without `asyncio.wait({closing})` (:417) | `165 passed in 4.27s` |
| M6 (control) | `_watch` without `self._steer = None` | `FAILED …test_claude_host_stops.py::PendingSteerDiscardTests::test_the_time_budget_discards_a_pending_steer` / `1 failed, 164 passed in 4.31s` |

**Blind or weak tests.**
- The EC-19 test (stops.py:126-135) sets `self.fake.interrupt_reply = lambda: result_message(...)`, so prompt 1's result is produced inside `interrupt()` and the interrupt is always written first. It passes with R-2 present.
- test_c (stops.py:463-475) accepts either `None` or a raise for the steer. That is weak, but its status and query assertions can still fail, so it is not a test that cannot fail.

Kept at Major: every test named here can still fail, so none meets the Blocker bar of "a test that cannot fail".

Fix-kind: code, as new test cases only, with the existing 165 untouched. **New tests in S5 need the orchestrator's explicit grant.**

## Refutations and downgrades

### R-E1 — refuted (D-29 success rule)

**The bar** (from the brief): confirm a spec-change finding only if the spec rule gives a wrong outcome against the user's words, another spec invariant, or observable SDK/CLI behaviour.

**The user's words.**
- R3's error table, accepted by the user, has the row `usage_limited` | "`RateLimitEvent` rejected + `resets_at`; assistant error `rate_limit`" (request.md:876). It makes no exception for a success.
- "semantic error messages if something goes wrong" (request.md:276). The account's limit was reached during the turn, and the failure says so. The record keeps the success text and cost: the reviewer's own probe shows `result_text: 'Parser fixed; 12 tests pass.'`.

**Invariants.**
- INV-7 (spec.md:220) is about which result can end a turn ("Only the prompt's own result can end a turn (D-28)"), not how the turn is classified.
- INV-19 (one code, chosen by the precedence) holds.
- D-29 (spec.md:491) records "let a success result win over it" as the runner-up it rejected.

**CLI behaviour** (2.1.296, mmap only):
- In the grace window the CLI can inject "[Usage limit reached — grace window active. Wrap up: finish or checkpoint; don't start subagents or long work.]" (216237635), or "…Checkpoint now: finish the current step, then list up to 3 short bullets of the most impactful remaining work…" (216238025).
- Which note it uses comes from `tengu_lantern_wick_mode` (216237712). The parser `j_s` (216237842) returns `"wrap-up"`, `"next-steps"` or else `"off"`.
- The wrap-up state's `continueAfterWrapUpAt` (216212523) returns `{resetsAt, rateLimitType}` only when `turnNote==="placed"`. `YJt` (216249390) turns that into `{status:"rejected",resetsAt:…}`.

So when the note is placed, the CLI itself treats a "success" in the grace window as a turn that was cut short and should continue after the reset, which matches the spec's code and next step.

**Uncertainty.**
- With the flag at `"off"`, which is the value when it is unset, no note may be placed, and the success could be complete work.
- I did not trace where `takeTurnNote`/`markStartNotePlaced` are called, and I stopped the bundle search there, as the coordinator directed.

**Confidence in this refutation: medium.** The evidence does not show the spec rule is wrong, so it stays the spec author's choice and is not routed to repair.

**Correction to my own earlier reading.** Mid-session I first read the mode flag as "a note is placed in either setting". The parser shows a third value, `off`, so that reading was wrong. The conclusion above uses the corrected reading.

**The per-model case** that pipeline.md:103-104 flagged ("a `seven_day_opus` window on a Sonnet turn") does give a wrong outcome against CLI behaviour. It is confirmed as part of R-6.

### R-V2, interrupt chain — refuted

Row 7 (spec.md:1157) prescribes this shape:
- "When `interrupt()` returns, the sending task calls `_arm_grace(number)`."
- The grace task "starts the close task".

`steer`, `interrupt` and `_watch` start `_interrupt_client` with `asyncio.create_task` (session.py:362, :449, :478). `_arm_grace` starts `_expire` the same way (:383). Each scheduled coroutine calls at most one helper level:
- `_interrupt_client` calls `_start_close` and `_arm_grace`, and `_arm_grace` calls no helper.
- `_expire` calls `_start_close`.

Inlining `_arm_grace` would remove a name that row 7, D-4 and Round 2 R-2 (spec.md:1445) all use.

### Downgrades

- **R-V2 pump → Major (R-4).** See A1.
- **R-C2 → Minor (R-17).**
  - §9.1 (spec.md:732): "`ClaudeHost` method arguments that come from model JSON (ids, prompts, `limit`, `offset`, `timeout_seconds`, flags) are type-checked at the host boundary". Handles and requests are typed records and never come from model JSON.
  - The tool path is covered by AC-26 (spec.md:292).
  - The raw error appears only when a developer misuses a typed API, which strict mypy (S009) flags. The conformance reviewer also says "no wrong result is produced".
- **R-V3 → Minor (R-16).**
  - No written rule forbids citing an ID. intent_based_commenting.md:11 asks that "A future agent should not need to search a design doc", and the reviewer agrees that each sentence already states its rule.
  - The brief caps this at Minor without a written rule.
- **R-V4 → Minor (R-8 + R-15).** See A3.

## Adjudicated reviewer disagreements

- **A1. Pump call depth: R-V2 (Blocker) against R-C3 (Major) → Major, deviation-entry.**
  - AGENTS.md principle 1 is contradicted literally.
  - But the blocking rule S024 rejects the inlined shape, as shown under R-4, and §8.4's 69/69 class budget rejects a reader class. So no code change can satisfy every rule without a spec change.
  - Behaviour is correct, and lint passes. The defect is the spec of record, which claims NFR-4 holds and has no §17 entry.
  - The smallest fix is §17 deviation 12, as R-C3 proposed. The alternative, one extra reader class and a budget of 70, is a larger spec change, and no evidence shows the code is wrong.
- **A2. R-E1 (Blocker, spec-change) against the orchestrator's acceptance of the S2-7 pin (pipeline.md:103-104) → refuted in general; the per-model case is confirmed in R-6.** See above.
- **A3. R-V4 (Major) against R-C4 (Minor) on the same fact → Minor.**
  - Both rest on deviation 1 (spec.md:1477) being false.
  - The vocabularies are named module constants, and no behaviour is wrong.
  - house-style.md:44 sits under "## House style (applies when the repo is silent)" (:42). AGENTS.md's Placement Rules cover dataclasses and enums only.
  - Split: reword deviation 1 (R-8, trivial); move the constants (R-15, follow-up).
- **A4. R-C2: the prosecution's tie-break against §9.1's explicit scope → Minor.** §9.1 is the specific rule, and INV-2 the general one.
- **A5. Fix forms.**
  - R-E2's fix A fails blocking lint A007 → use A′.
  - R-E3's `_admit` guard adds a principle-1 chain → use (b).
  - Both alternatives were validated: race probe, pack, and for A′ also A007/S024.
- **A6. R-C1 against R-E2:** separate root causes; both are needed. See the table above.

## Blind spots the reviewers missed

1. **R-21: `aclose` does not wait for in-flight probes.**
   - Probe: `fake.disconnect_gate` is held, `check_claude_ready` runs as a task, and `aclose()` is called once the probe's disconnect has started. Output: `aclose returned while the probe's close runs: disconnect_finished=False connected_now=1 probe_done=False`.
   - INV-8 still holds: the probe closes its own client.
   - FR-1's "disconnects every client" is not met at the moment aclose returns.
   - Minor, follow-up. (The probe's second print failed on a wrong attribute name, `.ready`, after the evidence line above. That is a script error, not a product finding.)
2. **R-E2's proposed fix fails blocking lint A007** (see R-2).
3. **R-E3's proposed fix adds a principle-1 chain** (see R-5).
4. **R-V1's fix needs a boundary.** Dict payloads must keep `.get` (see R-3).
5. **The CLI binary changed mid-review** (2.1.296 → 2.1.299). Every offset in review.md and here refers to the versioned 2.1.296 file. The per-model check is confirmed unchanged in 2.1.299.

## What the implementation gets right

All the reviewers' items are kept, de-duplicated, in review.md's last section.

## Commands run (beyond the probes quoted above)

- `git log -3 --format="%h %s"` → `cdf44876 docs(spec): record claude-host S3 done and S4 start in pipeline.md` / `d9c5fea2 …` / `4e14f870 …`.
- `git grep -n "\.whole(\|def whole" -- vidbyte tests` → `vidbyte/lib/dataclasses/claude.py:119:    def whole(value: object, name: str) -> None:` (no caller).
- `git grep -n "^class AggregateExecutionError\|^class ClaudeOperationError\|^class ConfigurationError" -- vidbyte/lib/errors/base.py` → `:194`, `:198`, `:267`. On origin/main the same grep gives `194` and `235`.
- `grep -rn "seven_day_opus\|seven_day_sonnet\|SEVEN_DAY_OPUS" tests/features/claude_host vidbyte` → only the contract enum row and lib/enums/claude.py:148-149. No test pins the per-model refusal, so R-6's change breaks none of the 165 tests.
- `ls -la ~/.local/share/claude/versions/` → `2.1.295`, `2.1.296` (260489376 bytes), `2.1.299` (269231264, 2026-10-13 21:39:35).

## Constraint compliance

- I wrote only `docs/spec/claude-host/review.md` and this report. I made no source edits, and no `git checkout`/`switch`/`stash`/`reset`/`clean`/`add`/`commit`/`push`.
- I created no scratch files in the worktree. Probes ran from heredoc stdin, and patched source was analysed in memory only.
- Every `ClaudeHost` ran under `FakeClaudeSdk().patched()`. No `claude` process was started. `claude.exe` and the versioned binaries were opened read-only through mmap only.
- I installed nothing and did not touch the codex-host worktree.
- The only files I read under `docs/` were those the brief allows.
