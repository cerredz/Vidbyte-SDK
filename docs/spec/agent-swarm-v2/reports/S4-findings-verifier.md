# S4 findings verifier: AgentSwarm v2 (PR #1174)

Output: `docs/spec/agent-swarm-v2/review.md`. Verdict: **MERGEABLE AFTER FIXES**. The review confirms 3 Blockers, 4 Majors, and 12 Minors. Two findings were downgraded and one part was refuted. I made no commits and no source edits.

Inputs: the three S4 reviews (conformance 0 Blockers / 1 Major / 4 Minors; conventions 1 / 2 / 5; engineering 1 / 4 / 2), spec r3, test-plan, request §A/§C, AGENTS.md, and the field guide `comment-format.md`.

Abbreviations used in commands:
- `WT` = `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2`. Every Python command ran with `PYTHONPATH="$WT"`, from `$WT`.
- `V` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/6308f8f2-185f-45a5-b1b7-9102079fc8ee/scratchpad/s4verify`. These are my probes.
- `E` = `.../scratchpad/s4eng`. These are the engineering reviewer's probes. I read each one before I ran it, and I used them as leads only.

## 1. Baseline

| Check | Command | Output |
|---|---|---|
| HEAD | `git rev-parse --short HEAD` | `9e41bbb4` |
| Product diff after the reviewed head | `git diff --stat 936e3278 HEAD -- vidbyte tests` | empty |
| NG-1 / NFR-1 | `git diff --stat 39ce8b20...936e3278 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py` | empty |
| Pack | `python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` | `268 passed in 7.12s` |
| All 16 mutants | `S4MUT=<id> PYTHONPATH="$WT;$E/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p s4mut` | Survivors (`268 passed`): `keep_last_zero`, `compact_while_stopping`, `self_writer_as_peer`, `side_call_tokens_not_added`. <br>Killed: `trunc_at_cap` (1 failed), `cancel_state_swap` (2), `budget_gt` (3), `budget_ignores_total` (1), `dropped_no_plus_one` (4), `trim_records_unchanged` (3), `fail_keeps_inbox` (2), `no_post_abort` (1), `side_call_not_budgeted` (8), `stopped_recipient_queued` (2), `measure_input_not_prompt` (1), `wake_refused_not_recorded_at_turn_end` (3). |

`$E/mut/s4mut.py` was read before I ran it. It rewrites one method in memory, from the source text, and asserts that its anchor occurs exactly once. It never writes to disk.

## 2. Merge map

| Original | Lens | Original severity | Merged | Merged severity | Note |
|---|---|---|---|---|---|
| R-V2 | conventions | Major | R-1 | Blocker | Raised by calibration ("contradicts AGENTS.md"); §5.5 |
| R-E1 | engineering | Blocker | R-2 | Blocker | |
| R-C1 | conformance | Major | R-3 | Blocker | Same lines and failure as R-V1; the higher severity is kept |
| R-V1 | conventions | Blocker | R-3 | Blocker | |
| R-V3 | conventions | Major | R-4 | Major | |
| R-E3 | engineering | Major | R-5 (wording) + R-18 (retry) | Major + Minor `[scope-adding]` | Split by route; §5.2 |
| R-E4 | engineering | Major | R-6 | Major | |
| R-E5 | engineering | Major | R-7 (3 mutants) + R-12 (test-plan wording) | Major + Minor | `keep_last_zero` downgraded as equivalent |
| R-V8 | conventions | Minor | R-8 | Minor | |
| R-C2 | conformance | Minor | R-9 | Minor | Same root cause as R-E6 (trim records before the observer aborts) |
| R-E6 | engineering | Minor | R-9 | Minor | |
| R-C4 | conformance | Minor | R-10 | Minor | Same README sentence as R-V7 |
| R-V7 | conventions | Minor | R-10 | Minor | |
| R-C5 | conformance | Minor | R-11 | Minor | |
| R-V6 | conventions | Minor | R-13 | Minor | |
| R-C3 | conformance | Minor | R-14 | Minor | |
| R-V5 | conventions | Minor | R-15 | Minor | |
| R-V4 | conventions | Minor | R-16 | Minor | |
| R-E2 | engineering | Major | R-17 | Minor `[scope-adding]` | Downgraded; §3.8 |
| R-E7 | engineering | Minor `[scope-adding]` | R-19 | Minor `[scope-adding]` | |

R-V4 and R-V5 belong to the conventions reviewer's width-fix moves. They stay separate Minors because R-3 takes the test-budget route, which makes those moves optional.

## 3. Verifications (my own evidence)

### 3.1 R-1: `_end_check` → `_stop` chain. CONFIRMED, Blocker.
- `grep -n "_end_check()\|self\._stop(" vidbyte/agents/agent_swarm/runtime.py`:
  - `126` `_stop(TIMEOUT)`, in `arun`;
  - `151`, `168`, `233` `_end_check()`, in `_run_member` ×2 and `end_turn`;
  - `282` `_stop(MAX_TOKENS)`, in `record_model_call`;
  - `382/384/386` `_stop(FAILED/MAX_TURNS/QUIET)`, inside `_end_check`.
- `git show 39ce8b20:vidbyte/agents/agent_swarm/runtime.py | grep -n "def _end_check" -A16`: the base assigns `self._stop_reason = AgentSwarmStopReason.FAILED/MAX_TURNS/QUIET` directly, and the base has no `_stop`. The chain is new in this diff.
- AGENTS.md §1: "a function may call another of its own functions, but that second function should not call a third … lift that call up into the main function."
- Fix check: the pure `_end_reason()` keeps every state change in the callers' existing await-free blocks. At 151 (the stray-cancel branch), the code re-raises next without flushing, and that stays as it is. At 168 and at 233, the next line is `await self._events.flush()`. INV-12 is therefore unchanged.

### 3.2 R-2: content-only size estimate. CONFIRMED, Blocker.
- Code: member.py:119 `sum(TokenEstimate.count(str(message.get("content") or "")) …)` and member.py:128 `used += TokenEstimate.count(str(message.get("content") or ""))`.
- Real shapes:
  - Gemini results: `{"role": "user", "parts": [{"functionResponse": …}]}` (formatter.py:479-492).
  - Gemini calls: `{"role": "model", "parts": [{"functionCall": …}]}`.
  - OpenAI calls: `{"role": "assistant", "content": None, "tool_calls": […]}`.
  - OpenAI results: `{"role": "tool", "tool_call_id", "name", "content"}` (formatter.py:496-502).
- `python $V/v_keep_last_providers.py` runs the AC-17 at-trigger scenario per provider through the real loop, `ToolsFormatter`, read_lines/write_text, member runtime, and engine. Only the runner is scripted; a `GeminiAwareSwarm._respond` emits Gemini `candidates/parts` plus `usageMetadata`, and side calls are detected by the summarizer leaf in `call.system`:
  ```
  [openai read_lines] stop=quiet model_called.input_tokens=[3, 72000, 3, 3] compaction=[('auto', 72000, 2)] side_calls=1
  [anthropic read_lines] stop=quiet model_called.input_tokens=[3, 72000, 3, 3] compaction=[('auto', 72000, 2)] side_calls=1
  [gemini read_lines] stop=quiet model_called.input_tokens=[3, 72000, 3] compaction=[] side_calls=0
  [gemini read_lines] real history chars on last call: 120486
  [openai write_text] stop=quiet model_called.input_tokens=[3, 72000, 3] compaction=[] side_calls=0
  ```
  The trigger did fire for Gemini (`input_tokens` 72000): `GeminiUsage.total_prompt_tokens` falls back to `input_tokens` (pricing/base.py:74). Only `_keep_last` is wrong. The two-group write_text row stays empty even after the fix, which is correct: group rounding keeps both groups (EC-21).
- `python $V/v_write_heavy.py` (six 60,000-char write_text calls, the sixth reporting the trigger) gives `[as-is] compaction=[] side_calls=0 last call messages=10`. The trim dropped 2 of 12, so the trim is acting as the mechanism.
- With the fix applied in memory (`$V/plug/s4v_fix_keep_last.py` patches both helpers to `TokenEstimate.count(str(message))`):
  - `python $V/v_keep_last_providers_fixed.py`: gemini `compaction=[('auto', 72000, 2)] side_calls=1`; openai and anthropic unchanged.
  - `python $V/v_write_heavy.py fixed`: `compaction=[('auto', 72000, 8)] side_calls=1 last call messages=5`.
  - `PYTHONPATH="$WT;$V/plug" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p s4v_fix_keep_last`: `268 passed in 6.37s`.
- Blind-spot check (§6.1): the compacted Gemini history is a valid Gemini request.
- Settled decision: this implements "automatic compaction on the SDK's own engine" correctly. It is kept, not refuted.

### 3.3 R-3: comment width against the 400-line cap. CONFIRMED, Blocker.
- Field-guide check, head vs base (`awk 'length($0) > 72' <f> | grep -cE '^\s*#'` and the same on `git show 39ce8b20:<f>`):

  | File | Head | Base | Widest |
  |---|---|---|---|
  | runtime.py | 44 | 0 | 399 |
  | member.py | 3 | 0 | 73 |
  | agent_swarm_observer.py | 5 | — (new file) | 75 |
  | compaction.py | 0 | 0 | 72 |
  | toolset | 0 | 0 | 72 |

  Conformance counted 38 lines because it measured text after `# `. The field guide counts the indent, so 44 is the binding number.
- `python $V/rewrap_count.py <file> [ranges]` rewraps each over-wide `#` line at 72 columns, indent included:
  - runtime.py: `lines after header now: 398 | after rewrap: 471`;
  - ranges: `51-52: 2→3`, `54-57: 4→6`, `249-269: 21→25`, `319-330: 12→16`;
  - member.py: 230 → 233;
  - observer: 90 → 95.
- The cap: `assert _lines_after_header(path) <= 400` at test_agent_swarm_contract.py:834, applied to every entry of `BUDGET_MODULES` (:121-128).
- Pricing the conventions reviewer's moves:
  - Moving the tool-outcome classification (lines 55-57 and the classification inside 249-269) to `AgentSwarmTools`, and `_SECTIONS`/`_render_system_prompt`/`_build_member` to member.py, saves about 36 rewrapped lines, so runtime.py lands at about 435.
  - R-1 adds about 3–4 lines and R-4 about 2–4, so about 441.
  - Both moves are compatible with AGENTS.md §1, because calls to another class do not count, and the other modules stay under 400. But no in-place route reaches 400 without rewording or cutting narrated comments, which AGENTS.md §2 requires.
- Decision: an S2 test change is warranted, and it is the route (§5.1).

### 3.4 R-4: three hidden A002 findings. CONFIRMED, Major.
- `python lint/run.py --rule A002 --all --format json > $V/a002_all.json` gives the rule summary `{'id': 'A002', 'found': 565, 'baseline': 703, 'verdict': 'IMPROVED'}`, `exit_code 0`. The swarm entries are:
  ```
  {"path": "vidbyte/agents/agent_swarm/member.py", "line": 134, "symbol": "_compact", ... "categories": "external boundaries"}
  {"path": "vidbyte/agents/agent_swarm/runtime.py", "line": 295, "symbol": "request_compaction", ...}
  {"path": "vidbyte/agents/agent_swarm/runtime.py", "line": 301, "symbol": "take_compaction_request", ...}
  ```
- All three functions are new (spec rows 33–34 "ADD"). The ratchet only compares counts, so new findings hide behind the 138 that were removed elsewhere. The §12.4 checklist (spec.md:941) requires `@intent` on every policy branch.
- I could not run the fix itself, because the stage is read-only. The repair agent's acceptance check is the same JSON command, showing no swarm entry.

### 3.5 R-5: no model retry exists. CONFIRMED, Major. The wording is in scope; the retry is scope-adding.
- `python $E/probe_retry.py`, read first (the AC-10 script, real fixtures, without `install_model_retry`):
  ```
  stop_reason: quiet
  6 model_error builder 'ProviderRequestError: openai returned 429: rate limited, try again'
  7 agent_failed builder 'ProviderRequestError: openai returned 429: rate limited, try again'
  builder calls made: 1 of 2 scripted
  ```
- No retry exists at any layer:
  - Member tuple: `(AgentSwarmTrimMiddleware, AgentSwarmTurnMiddleware, AgentSwarmObserverMiddleware)` (member.py:223). The observer's `on_model_error` returns `continue_()`.
  - Transport: `HttpTransport.request(..., retry_count: int = 0, ...)` (transport.py:55). `openai.py:37` passes no `retry_count`, and transport.py:23-26 refuses a POST retry without an idempotency key.
  - Settings: `grep -rn max_retries vidbyte --include=*.py` finds `AgentLoopSettings.max_retries` stored (loop.py:57, :74) and copied (base.py:671, fork.py:163). No loop code reads it; runtime.py:1684 mentions it only in a docstring.
  - Middlewares: `ModelRetryMiddleware.before_run` (retry.py:41-49) and `ExponentialBackoffRetryMiddleware.before_run` (exponential_backoff_retry.py:74-88) reset `attempts` once per run. A member runs one loop for the whole swarm.
- The spec promises a mechanism that does not exist:
  - INV-23 (spec.md:221): "… so the loop's own retry decision stays untouched".
  - AC-10 (spec.md:257), Given: "a scripted model error that the loop later retries successfully".
  - EC-25 (spec.md:302), User-sees cell: "repeated `model_error` during an outage until the loop's own retries fail the member".
  - The AC-10 test uses `install_model_retry` (agent_swarm_fixtures.py:562; test_agent_swarm_stop.py:238).

### 3.6 R-6: no hysteresis. CONFIRMED, Major.
- `$V/v_hysteresis.py`: every loop call reports the size of the request it actually carried, at four characters per token, or at 1.5 for the CJK run. There is no scripted constant. One distinct 30,000-char read per iteration. Real loop, tools, and engine.
- `S4V_ITERATIONS=24 python $V/v_hysteresis.py`:
  ```
  goal     100 chars, history 4.0 chars/token: loop calls 25, summary side calls 3, compaction events 3
  goal  160000 chars, history 4.0 chars/token: loop calls 25, summary side calls 10, compaction events 10
  goal  220000 chars, history 4.0 chars/token: loop calls 25, summary side calls 21, compaction events 21
  goal     100 chars, history 1.5 chars/token: loop calls 25, summary side calls 10, compaction events 10
  ```
- With the fix in memory (`$V/plug/s4v_fix_hysteresis.py`, which also applies R-2's estimate), `S4V_GROWTH=target S4V_ITERATIONS=24 python $V/v_hysteresis_fixed.py`:
  ```
  control: 3 compactions, measured [74428, 75025, 75027]   (unchanged)
  160000-char goal: 5   measured [76585, 92304, 92305, 92307, 92307]
  220000-char goal: 6   measured [84020, 107304, 107305, 107307, 107307, 107307]
  CJK 1.5 chars/token: 5   measured [87089, 129007, 129009, 129015, 129015]
  ```
- With the growth threshold set to trigger − target (the reviewer's rule, my earlier run), the results are 3 / 4 / 4 / 4.
- `S4V_GROWTH=target PYTHONPATH="$WT;$V/plug" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p s4v_fix_hysteresis` gives `268 passed in 6.42s`. The `trigger-target` rule also passed, in an earlier run.
- Tradeoff, stated for the record: the growth rule spaces compactions out, so the real prompt can sit above the trigger between them. In the CJK run it reaches 129,015 reported tokens. The four-characters-per-token undercount behind that also governs the trim, and that undercount predates this diff. I chose `target` (27,000) over `trigger-target` (45,000) because it keeps prompts smaller.
- Settled decision: this keeps automatic compaction on the SDK engine and adds no setting. It is kept.

### 3.7 R-7: test-pack survivors. CONFIRMED, Major, for 3 of 4.
- Each survivor is observable through the public run. `S4MUT=<id> python $V/v_survivors.py` (the mutation applied from `$E/mut/s4mut.py`) against the shipped code:

  | Mutant | Shipped | Mutant |
  |---|---|---|
  | `compact_while_stopping` | `summary side calls=0`, no compaction | `summary side calls=1`, with `(16, 'model_called', 'builder'), (17, 'compaction', 'builder')` after `(13, 'swarm_stopping', '')`. A paid call after the stop. |
  | `self_writer_as_peer` | `file_changed peers: ['', '']` | `['', 'builder']` |
  | `side_call_tokens_not_added` | builder reply `tokens_used` 73512 | 72012 (the side call's 1,500 tokens are lost) |
  | `keep_last_zero` | identical output | identical output |

- The `compact_while_stopping` scenario needed older history over the target. My first version had one 5,000-char read, the engine had nothing older to summarize (EC-21), and so it showed no difference. Two 60,000-char reads fixed that.
- Why `keep_last_zero` is equivalent:
  - A seam trace (a `_keep_last` spy on the Anthropic run) printed `[('assistant','list',93), ('user','list',99072), ('assistant','list',184), ('user','list',99071), ('user','list',99071)]` and `_keep_last -> 1`. Each tool result is its own message, for every provider (formatter.py:463-502).
  - The result cap, `AGENT_SWARM_TOOL_RESULT_MAX_CHARS = 100_000` (constants:39), is about 25,000 estimated tokens, below the 27,000 target. The R-2 fix adds only the dict keys.
  - So `kept` is never 0 today.
- `SummarizeRangeCompaction.compact` (strategies.py:351-356) does `while split and kept < self.keep_last`. At 0 the loop never runs, and every group lands in `middle`. test-plan.md:91's claim that the engine's rounding guarantees the newest group is therefore false. The guarantee is member.py:132's `max(kept, 1)` (R-12).

### 3.8 R-E2: inbox over the trim. DOWNGRADED to Minor `[scope-adding]` (R-17).
- Reproduced with `python $E/probe_inbox_block.py`, read first (real fixtures; FakeTavily blocks the receiver while alice and bob each send 200,000 chars):
  ```
  20 message_delivered receiver alice
  21 message_delivered receiver bob
  22 history_trimmed receiver   dropped=1
  23 model_called receiver
  receiver's 2nd call carries alice's text: False | bob's text: False
  receiver's 2nd call message sizes: [0, 98]
  ```
- `_trim_groups_to_tokens` (strategies.py:635-647) keeps the newest whole groups that fit and skips a group over the remaining budget.
- Why it is downgraded rather than confirmed:
  - The base is identical: `git show 39ce8b20:vidbyte/agents/agent_swarm/runtime.py` has the same `_drain` at 252-262, and the base trim cap is the same `AGENT_SWARM_HISTORY_MAX_TOKENS = 90_000`.
  - The spec keeps the base behavior on purpose: row 34 says "`_drain` unchanged", and INV-8 says "Must not regress: `runtime.py:252-262` `_drain`".
  - INV-7 and INV-8 hold as written.
  - `history_trimmed dropped=1` sits on the record right after the two deliveries (G-6).
  - The fix is a delivery budget that leaves mail queued. That changes delivery semantics (INV-6..INV-11, `end_turn` parking on a non-empty inbox, the MAX_TURNS end check), so it needs a spec decision.
- Not refuted either: the user-visible risk is real, and the diff raises the agent cap from 100 to 500, which makes the many-small-reports case reachable (499 × 1,500 chars ≈ 189,000 estimated tokens). It is the first follow-up for the user.

### 3.9 Minors (pass-through checks)
- **R-9**: `python $E/probe_trim_after_stop.py`, read first, gives `13 swarm_stopping max_tokens`, `15 tool_called builder`, `16 history_trimmed builder dropped=2`, `17 agent_released builder`, "builder model calls reaching the runner: 2". Confirmed.
- **R-10**: `sed -n 110,113p vidbyte/prompts/README.md` shows "`message_sent` and the three refusals are its replies". Confirmed.
- **R-11**: README:117 names only `agent_exited` for `record_model_call` bugs. member.py:152 awaits `record_model_call` outside the fail-closed middleware. Confirmed.
- **R-13**: runtime.py:4 says "the first two also by the member runtime for its summary call". member.py:140 calls `record_model_error`, and member.py:91 calls `stopping`. dataclasses:7 says "its name in _OPTIONAL_FIELDS", but line 87 derives that tuple. Confirmed.
- **R-14**: runtime.py:256-258 reads `call.arguments.get(argument)`, while INV-26 (spec.md:224) names `metadata["path"]` / `metadata["file_path"]`. Confirmed.
- **R-8**, **R-15**, **R-16**, **R-19**: confirmed by reading member.py:63-67, runtime.py:55-57, observer:31, runtime.py:249-269, and runtime.py:375-386.

## 4. Findings touching settled decisions (request §A Prompt 5 / §C)

| Finding | Touches | Ruling |
|---|---|---|
| R-2, R-6 | "automatic compaction on the SDK's own engine" | Keep. Each makes the settled design work; no setting is added. |
| R-5 | none directly (retries were never discussed) | Keep the wording repair. The retry itself (R-18) is `[scope-adding]`. |
| R-17 (R-E2) | G-5 (500 agents), NG-10 (no message length cap) | Does not reverse either. A bounded drain is not a length cap, but it is new behavior, so `[scope-adding]`. |
| R-19 (R-E7) | NG-10 "a result-level usage field, or any other setting" | `[scope-adding]` follow-up. |
| R-1, R-3, R-4, Minors | none | Keep. |

No finding asks to reverse a settled decision, so none is refuted on that ground.

## 5. Adjudications

### 5.1 Comment width vs the 400-line cap (R-3)
- **Checks the route must satisfy:**
  - the field guide's 72-column rule, counting the indent;
  - the pack's `<= 400` assert;
  - AGENTS.md §1 (one-level calls; calls to another class do not count);
  - AGENTS.md §2 (narrated main functions, so the comment wording stays).
- **The in-place routes all fail.** Rewrapping alone gives 471. The conventions moves give about 435, and about 441 with R-1 and R-4. The moves satisfy §1 and the other modules' budgets, but no wording-preserving route reaches 400.
- **Decision: an S2 test change is warranted.**
  - The exact assertion is `tests/features/agent_swarm/test_agent_swarm_contract.py:834`, `assert _lines_after_header(path) <= 400, f"{relative} is over 400 lines after its header"`.
  - It becomes a per-module limit: 500 for `vidbyte/agents/agent_swarm/runtime.py` and 400 for every other `BUDGET_MODULES` entry, with the assertion message naming the limit.
  - Update the docstring at :826 and test-plan.md:81 to match.
  - This matches row 34 ("≤ 400 lines target per module …; hard limit 1,000") and NFR-8 ("well under 1,000").
- **Why 500:** after all the fixes runtime.py is about 478 (471, plus R-1 about 3–4, plus R-4 about 2–4), so 500 leaves about 20 lines of headroom.
- **Order:** S2 changes the test, then the implementer rewraps. Rewrapping first turns the pack red.

### 5.2 R-E3 scope
- The retry is `[scope-adding]`, for four reasons:
  - it adds a class beyond §8.4 ("8 new classes … may not exceed this budget without stopping and reporting BLOCKED");
  - the SDK's retry middlewares count attempts per run and cannot be reused as they stand;
  - transport retries need an idempotency key for POST;
  - the conversation never asked for retries.
- The in-scope repair (R-5) corrects these sentences:
  - INV-23 (spec.md:221): "so the loop's own retry decision stays untouched".
  - AC-10 (spec.md:257), Given: "a scripted model error that the loop later retries successfully".
  - EC-25 (spec.md:302), User-sees cell: "repeated `model_error` during an outage until the loop's own retries fail the member".
- It also adds the package README edge-case sentence and fixes the AC-10 test docstring (S2). review.md R-5 gives the replacement text.

### 5.3 R-E4: the minimal INV-32 change
- Only the first clause of INV-32 changes. The new text is given in review.md R-6.
- The code keeps E0 (the estimate right after the last compaction, from any trigger) on the `AgentSwarmMemberRuntime` instance. That puts no lines into runtime.py and no new map into §9.1's runtime state.
- It depends on R-2: with the content-only estimate, a Gemini member's estimate never grows, so after one compaction AUTO would never fire again.
- A `compact` request stays unconditional, which matches the tool's reply text.

### 5.4 Conformance vs engineering on FR-8
Conformance says the diff "implements every FR … of spec r3". R-2 shows that FR-8 (automatic compaction) and G-4 (`compact`) fail for Gemini members. Conformance could not see this, because `ScriptedSwarm._respond` (agent_swarm_fixtures.py:390-405) scripts only the OpenAI and Anthropic shapes. I side with engineering, on the strength of my own probe.

### 5.5 Conformance vs conventions on `_end_check` (R-1)
- Conformance's position: "`_end_check` → `_stop` is a two-level call chain. Row 34 mandates it, so it is not an NFR-8 finding."
- Conventions' position: Major, citing AGENTS.md §1.
- My ruling: the base had no chain, and row 34's own sources column cites "AGENTS.md §1–§2 … helpers one level", so the spec contradicts itself. AGENTS.md is binding for new code, and the pure-decision split keeps INV-12, so I follow AGENTS.md and correct row 34's wording.
- Severity: the calibration rule makes "contradicts AGENTS.md" a Blocker. The violation is unambiguous and new.
- I kept R-16 (R-V4, AGENTS.md §3 "one thing") as a Minor. "Record what one tool result shows" is one job with three cases, and R-3's route makes its stated cause, the line target, disappear.

## 6. Blind-spot checks [verifier]

1. **Does R-2's fix break Gemini requests?** After the fix, Gemini members compact for the first time, and the engine restores the summary as `{"role": "assistant", "content": …}` inside a Gemini history (engine.py `_context_message_to_provider`). `python $V/v_gemini_contents.py` takes the fixed run's post-compaction history and feeds it to the real `GeminiProvider._create_contents` offline:
   ```
   compaction: [('auto', 2)] | history roles after compaction: ['assistant', 'model', 'user']
   gemini contents: [('user', ['text']), ('model', ['text', 'functionCall']), ('user', ['functionResponse'])]
   problems: none
   ```
   `_gemini_turn` maps `assistant` to `model` and `content` to `parts`, and `_merge_model_turns` folds the summary into the call turn. No finding.
2. **Combined budget:** runtime.py ends at about 478 after R-1, R-3, and R-4, which fits the 500 limit. member.py is about 245 after R-2, R-4, R-6, and R-8. The observer is about 97 after R-3 and R-9. No finding.
3. **R-1 against engineering's "do not restructure `end_turn`":** R-1 changes only the call line at 233, within the same await-free block, so the two are compatible.
4. I found no other Blocker-class risk between the lenses.

## 7. Fix interactions and suggested order for S5

1. S2: change the test assert (R-3 route), add the Gemini `_respond` branch and the R-2, R-6, and R-7 tests, and fix the AC-10 docstring (R-5).
2. R-2, then R-6. R-6 uses R-2's estimate.
3. R-1, then R-4, then R-3's rewrap last, so every new comment line gets wrapped in one pass.
4. The wording repairs: R-5's spec sentences and README sentence, and row 34 for R-1.
5. The trivial Minors (R-8..R-14) can ride along.

## 8. Probe inventory (`$V`)

| File | What it shows |
|---|---|
| `rewrap_count.py` | Lines after the header, now and after a 72-column rewrap. |
| `a002_all.json` | Full A002 JSON. |
| `v_keep_last_providers.py`, `v_keep_last_providers_fixed.py` | R-2, per provider. |
| `v_write_heavy.py [fixed]` | R-2, OpenAI write-heavy history. |
| `v_hysteresis.py`, `v_hysteresis_fixed.py` | R-6 (`S4V_ITERATIONS`, `S4V_GROWTH`). |
| `v_survivors.py` | R-7 observability (`S4MUT`). |
| `v_gemini_contents.py` | §6.1. |
| `plug/s4v_fix_keep_last.py`, `plug/s4v_fix_hysteresis.py` | The proposed fixes, as in-memory pytest plugins. |
| `rerun_log.txt`, `rerun_hysteresis.txt` | Saved outputs. |
