# S4 findings verifier, scoped round after S5 re-review 1 — claude-host

Code under review: `origin/main...615fc54a`. Local HEAD 5e1328da adds only docs commits; `git status --short` was empty at start and at end. Spec: r5 (3c1f9e4c). Input: `reports/S5-rereview.md` only, with findings R-C1, R-C2 and R-C3. The two other review inputs were `n/a`.

Result: one confirmed Major (R-22), two Minors (R-23 code, R-24 spec text), and two parts of R-C1 refuted. Verdict: **MERGEABLE AFTER FIXES**.

## 1. Merge map

| Original | Lens | Proposed | Merged ID | Outcome |
|---|---|---|---|---|
| R-C1 | conformance (regression from R-2's fix) | Major | **R-22** | CONFIRMED, Major. Two parts refuted: the re-reviewer's aclose ordering and the INV-11 citation (refuted/downgraded table). |
| R-C2 | conformance (D-3, residue of R-1) | Minor | **R-23** | Passed through as Minor, and confirmed anyway. `trivial`, fix-kind `code`. |
| R-C3 | conformance (deviations not recorded) | Minor | **R-24** | Passed through as Minor, and confirmed anyway. `trivial`, fix-kind `spec-change`, which includes §17 deviation 14. |

Nothing was merged across findings, because the three have different root causes. R-22 and R-23 touch the same helper (`_take_steer`), so their fixes interact (§5).

## 2. Method

- **Probes.** I drove the real `ClaudeHost` through `FakeClaudeSdk().patched()`, the one seam the spec names. No `claude` process started.
- **Variants.** Each variant is a `session.py` text exec'd into the real `vidbyte.harnesses.native.claude.session` module namespace, with `host.ClaudeLiveSession` repointed to it. I restored the namespace afterwards, and each run printed `restored: True True`. I used the real module's namespace, not a fresh one, because the pack patches `vidbyte.harnesses.native.claude.session.CLAUDE_INTERRUPT_GRACE_SECONDS` (fixtures:45). A fresh module would have dodged that patch. There were three variants:
  - **current:** 615fc54a.
  - **pre-fix:** `git show d9c5fea2:vidbyte/harnesses/native/claude/session.py`.
  - **candidate:** the re-reviewer's fix, built by text edits on the current file. Optionally, R-23's reset is added too.
- **Scratch scripts (a deviation from the briefing).** The first attempt was an inline Bash heredoc, and it failed with `unexpected EOF while looking for matching ''`. That is the known "big Bash heredocs break" gotcha. So the probe scripts live in this session's scratchpad (`C:\Users\422mi\AppData\Local\Temp\claude\…\scratchpad\`: `variants.py`, `probe_rc1.py`, `pack_with.py`, `test_wouldbe_regressions.py`, `lint_diff.py`). That folder is outside the worktree. Nothing was written to the worktree except review.md and this report.
- **Bytecode.** Every run used `PYTHONDONTWRITEBYTECODE=1`.

## 3. Verification

### R-22 (from R-C1) — CONFIRMED, Major

**The code at 615fc54a.**
- session.py:173: `prompt = self._take_steer() if await self._read(stream) else None`.
- `_take_steer` (:262) empties the slot and sets `_steered`.
- The next `_query` counts the prompt (:230), then yields (:236-237: `if self._steered: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)`), then sends it (:239).
- The stop paths clear only the slot: `_watch` :376, `_expire` :408, `interrupt` :487, `close` :503. A steer's failed interrupt withdraws only when `self._steer is not None` (:390). A message that has been taken but not yet written is visible to none of them.

**Probes.** In each probe the turn is held, `client.finish("The first answer.")` queues prompt 1's result, and the stop is scheduled so it runs in the pump's yield pass. The calls below are the fake client's call log.

| Probe | current 615fc54a | pre-fix d9c5fea2 | candidate |
|---|---|---|---|
| **P1:** `interrupt_claude_turn` task scheduled after `finish()` | `interrupt returned` at `['connect','get_server_info','query','receive_messages']`; calls `[…,'receive_messages','interrupt','query','interrupt','disconnect']`; queries `['Summarize the repository layout.','focus on tests']`; steer `returned None`; final `('interrupted', None, '')` | `interrupt returned` at `[…,'receive_messages','query']`, so the stop lands after the send; steer `returned None` | steer `raised action.precondition_failed`; calls `[…,'receive_messages','interrupt','disconnect']`; queries `[first only]`; final `('interrupted', None, 'The first answer.')` |
| **P2a:** `aclose` task scheduled after `finish()` (the re-reviewer's order) | `session.close entered` at `[…,'interrupt','query']`, so `close()` runs after the send; steer `returned None` | `session.close entered` at `[…,'query','interrupt']` | same as current: `session.close entered` at `[…,'interrupt','query']`; steer `returned None`. This is correct, because the stop came after the send. |
| **P2b:** `aclose` task scheduled before `finish()` | `session.close entered` at `[…,'receive_messages','interrupt']`, then `'query'`; steer `returned None` | `session.close entered` at `[…,'query','interrupt']` | steer `raised action.precondition_failed`; calls `[…,'interrupt','disconnect']`; no second query |
| **P3:** `fake.interrupt_error = lambda: CLIConnectionError(...)` set after `finish()` | steer `raised claude.process_exited`; calls `[…,'receive_messages','interrupt','query','disconnect']`; final `('completed', None, 'steered answer')` | steer `raised claude.process_exited`; calls `[…,'receive_messages','query','interrupt','disconnect']`; final `('completed', None, 'steered answer')` | steer `raised claude.process_exited`; calls `[…,'interrupt','disconnect']`; no steered query; final `('completed', None, 'The first answer.')` |
| **P4:** the session's own `_watch(client, 0)` started before `finish()`, so its stop lands in the pass | steer `returned None`; calls `[…,'interrupt','query','interrupt','disconnect']`; final `('failed', 'claude.budget_exhausted', '')` | calls `[…,'query','interrupt','disconnect']`, so the stop lands after the send | steer `raised action.precondition_failed`; no second query; final `('failed', 'claude.budget_exhausted', 'The first answer.')` |
| **R-2 control:** `finish()`, then steer, no stop | `[…,'interrupt','query','disconnect']` → `('completed', None, 'steered answer')` | `[…,'query','interrupt','disconnect']` → `('failed', 'claude.api_error', '')`, the original R-2 bug | `[…,'interrupt','query','disconnect']` → `('completed', None, 'steered answer')` |

**Spec reading.**
- INV-18 at spec.md:245 says "An explicit interrupt or an expired time budget discards a pending steer before it is sent". spec.md:247 then says the call raises `action.precondition_failed`.
- The §9.2 steer row (spec.md:754) says "If `interrupt()` raises, the pending message is withdrawn (if not yet sent) and the mapped error is raised".
- Row 7 (spec.md:1157) says "`steer()` withdraws its unsent message".
- At 615fc54a, P1, P2b and P4 send a message after a recorded stop, and P3 leaves a message unsent at the moment its interrupt raises without withdrawing it. All four contradict those lines. The pre-fix code had no such window: the take and the write run in one step, so it conformed.

**Existing guard?** None prevents the send.
- The stop's own interrupt task is aimed at `self._prompts_sent`. That count is already 2, because it is counted before the yield, so the interrupt stops the steered prompt only after the prompt is written.
- The real SDK writes immediately. `client.query(str)` reaches `await self._transport.write(...)` with no earlier await (client.py:272-295), and the write takes `_write_lock` first (subprocess_cli.py:1063-1065). So in production too, the steered prompt reaches Claude Code and is then interrupted, which costs a little.
- The pack does not catch it: 177 pass at 615fc54a.

**Severity.** This is Major, not Blocker.
- It is a real invariant break that a human reviewer would flag. It is not a weighted-word violation: request.md §D has no steer or discard word.
- The window is one loop pass, and the turn's terminal status stays correct (INTERRUPTED, or `budget_exhausted`).
- The wrong part is the extra prompt after a stop, plus `steer()` misreporting the outcome.
- P3's caller-visible result (an error while the message is delivered) also existed before the fix. What changed is that the message is now unsent when the interrupt raises, so the spec requires the withdrawal, and the candidate delivers it.

**Smallest fix, verified.** It is the re-reviewer's fix; I found none smaller.
- Delete :231-237 from `_query`.
- Change `def _take_steer` to `async def _take_steer`, and open it with `if self._steer is not None: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)`.
- Change :173 to `prompt = await self._take_steer() if await self._read(stream) else None`.

Two alternatives are worse:
- Keeping the yield in `_query` and re-checking `_stopping` afterwards misses P3, because nothing sets `_stopping` there, and it would also have to un-count `_prompts_sent`.
- Putting the yield inside `_read` before `return True` nests four deep, which breaks S024.

Checks on the candidate:
- **The pack** (`pack_with.py rc1 tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml`):
  ```
  .................................                                        [100%]
  177 passed in 4.65s
  variant rc1 exit 0
  ```
- **The gaps and stops files**, which include SteerInResultWindowTests and AC-37(d): `35 passed in 1.85s` (rc1) and `35 passed in 1.83s` (both fixes), against `35 passed in 1.86s` for current.
- **Would-be regression cases**, never committed (scratchpad `test_wouldbe_regressions.py`):
  - current → `3 failed in 13.86s`. The P1 case fails with `AssertionError: None != 'action.precondition_failed'`, and the P3 case with ``Lists differ: ['Summarize the repository layout.', 'focus on tests'] != ['Summarize the repository layout.']``.
  - rc1 → `1 failed, 2 passed` (only R-23's case fails).
  - both → `3 passed in 13.71s`.
  - The test calls themselves take 0.02-0.03 s; the rest is pytest startup.
- **Lint, in memory** (`lint_diff.py`, a `SourceCatalog` subclass that swaps session.py's text):
  - `rules run: 90 | rules that raised: []`.
  - `current session.py findings: {}`.
  - `rc1 rules whose session.py findings differ: none` and `both … none`.
  - The longest comment line is 72 for current, rc1 and both.
  - `ruff check --config lint/ruff.toml --stdin-filename vidbyte/harnesses/native/claude/session.py -` → `0 All checks passed!` for rc1 and for both.
  - `ruff format --check` exits 1, but it does the same on the unmodified file, so it is not a gate.
- **Call depth.** `run` → `_take_steer` is an existing one-level call, and `asyncio.sleep` is the standard library. NFR-4 and AGENTS.md principle 1 are unchanged, and deviation 12 needs no edit.

### R-23 (from R-C2) — Minor, confirmed

- **Code.** `_take_steer` clears only the slot. `_result`'s result fields change only in `_on_result` (:295-306).
- **Would-be case** at 615fc54a (the steered reply is `init_message()`, then END_OF_STREAM): ``Tuples differ: ('', 'aborted_streaming', 1, 4200, '', (), None) != ('', '', None, None, '', (), None)``. These are the interrupted prompt's `terminal_reason`, `num_turns` and `duration_ms`, published on the steered handle's FAILED `claude.process_exited`.
- **With the reset** (variant rc2 or both), the case passes, `total_cost_usd` stays `0.008` (INV-20), and the pack still gives `177 passed in 4.96s` (rc2) and `177 passed in 4.66s` (both).
- **Spec.** D-3 (spec.md:465) says "that next result is the handle's". §9.1 "Turn outcome" (spec.md:691) says the outcome holds "the fields of the prompt's own latest result". The current publication contradicts the first. The code and status are right, so this is Minor.
- **Adjudication.** In the EC-19 window, the reset also drops `'The first answer.'` from the steered handle's snapshot (P2a at current shows final `('interrupted', None, 'The first answer.')`). That is what D-3 asks for, because the steer supersedes the first answer, and the text stays in the session transcript. EC-17's "result_text kept for a repair turn" concerns the turn's own result, which `_on_result` still sets.
- **Keep:** `session_id`, because a plain continue learns it from the first result (EC-34); `hooks_applied`; and `total_cost_usd`. Leave `_outcome` alone.

### R-24 (from R-C3) — Minor, confirmed

- **`grep -n STEER_YIELD docs/spec/claude-host/spec.md`** finds nothing. The constant exists at vidbyte/lib/constants/claude.py:52-54 and is used at session.py:35 and :237.
- **EC-52** (spec.md:363) says: "A rate-limit event without `rate_limit_type`, or with a type outside the enum → Skipped". The code (session.py:334-337) also skips an unknown `status` or `overage_status`.
- **Row 12** (spec.md:1162) says "the converters in rows 7–9 map any failure to build these records from SDK data to `claude.protocol_mismatch`".
- **Row 7** (spec.md:1157) lists the pump sequence with no yield. **Row 14** (spec.md:1164) lists the constants without this one, and so does §9.3.
- **Extra fact for the spec author.** The pinned SDK declares `RateLimitStatus = Literal["allowed", "allowed_warning", "rejected"]` (claude_agent_sdk/types.py:1391), and `overage_status: RateLimitStatus | None` (:1418). So the skip can only meet values that a future CLI adds. The new EC-52 text should say that such a window is skipped, not read as "overage not allowed" under D-29's wording.
- **Fix-kind.** `spec-change`, because EC-52, row 12 and row 14 are contract text. The yield goes into §17 as deviation 14, under the deviation rule at spec.md:1483. Write deviation 14 after R-22 lands, so it describes the yield at its new place: before the take, only while a steer is pending.

## 4. Adjudications

1. **R-C1 Probe 2 (aclose).** The re-reviewer's evidence ("aclose called" before the query) does not show a violation. `aclose` sets `_closed` and hands each session's `close()` to `asyncio.gather`, a new task. In that order the session's stop is recorded after the steered query in every variant (P2a). The aclose path is real only when `close()` itself lands in the pass (P2b). I recorded this partial refutation so the repair agent does not write an aclose test that cannot fail.
2. **R-C1's INV-11 citation.** INV-11 (spec.md:224-227) covers precondition failures and a stop before the first query. It does not govern a steered prompt, so I dropped it. INV-18, the §9.2 steer row and row 7 carry the finding.
3. **R-C1 severity.** I kept Major (§3).
4. **R-C2 versus losing the first answer's text.** I sided with D-3 (§3).
5. **R-C3 fix-kind.** One row, `spec-change`, with deviation 14 inside it. I did not split it, because both parts go to the same author in the same r6 edit.

## 5. Blind-spot pass

- **The rest of the repair diff.** I read every session.py, host.py and failures.py hunk of `d9c5fea2..615fc54a` (`git diff … | grep '^[+-]'`). The only new await is R-2's yield. R-3's attribute reads, R-5's re-guard, R-6's per-model check and R-12's skip add none. I found no new Blocker-class risk.
- **New windows from the candidate.** During the pre-take yield the slot is still full, so a second steer is refused ("already pending", EC-20). A caller interrupt in that pass is aimed at prompt 1, whose result is already read, so `_arm_grace(1)` does nothing, and the pump ends the turn on the empty slot.
- **A residual not raised as a finding.** If a steer's interrupt raises synchronously in the pass and a second `steer()` from another task is stored in the same pass, the second message is taken without its own yield. That reproduces R-2's order for that one message. It needs two steers in one loop pass, the first of which failed, and the same exposure exists today. I see no practical risk, so I am not raising it.
- **Fixes that interact.** R-22 and R-23 both edit `_take_steer`. Land R-22 first, then put R-23's `replace()` inside `if steer is not None:` after `self._steered = self._steers`. The "both" variant of exactly that shape gives 177 passed, all three would-be cases pass, and lint shows no difference.

## 6. Commands run (final lines)

```
# baseline pack at 615fc54a
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml
→ 177 passed in 5.81s

# R-C1 probes, three variants
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$W;$SP" $PY -P $SP/probe_rc1.py
→ (table in §3) … restored: True True

# pack with each candidate
… pack_with.py rc1 … → 177 passed in 4.65s / variant rc1 exit 0
… pack_with.py rc2 … → 177 passed in 4.96s / variant rc2 exit 0
… pack_with.py both … → 177 passed in 4.66s / variant both exit 0
… pack_with.py {current,rc1,both} test_claude_host_review_gaps.py test_claude_host_stops.py → 35 passed in 1.86s / 1.85s / 1.83s

# would-be regression cases (scratchpad only)
current → 3 failed in 13.86s · rc1 → 1 failed, 2 passed · rc2 → 2 failed, 1 passed in 14.55s · both → 3 passed in 13.71s

# lint in memory
… lint_diff.py → current session.py findings: {} / rc1 … differ: none / both … differ: none / rules run: 90 | rules that raised: []
ruff check (stdin, lint/ruff.toml) → rc1: 0 All checks passed! / both: 0 All checks passed!

# SDK source (text only)
grep … claude_agent_sdk/client.py → 295: await self._transport.write(  (first await in query)
grep … subprocess_cli.py → 1063: async def write / 1065: async with self._write_lock:
grep … types.py → 1391: RateLimitStatus = Literal["allowed", "allowed_warning", "rejected"]

git status --short → (empty), at start and after every run
```

## 7. Notes for the repair agent (iteration 2)

- **Reproduce R-22.** Hold `DEFAULT_PROMPT` and the steer. Call `client.finish("The first answer.")`, then `asyncio.ensure_future(host.interrupt_claude_turn(handle))`, then `await host.steer_claude_session(handle, msg)` directly. At 615fc54a this gives steer None plus a second query. For P3, set `fake.interrupt_error = lambda: CLIConnectionError(...)` (the fixtures' class) after `finish()`. For aclose, schedule `aclose` **before** `finish()`.
- **Never wrap the window steer** in `asyncio.wait_for`, `self.raises` or `eventually`. Catch `ClaudeOperationError` by hand. The gaps file header (WHAT NOT TO DO 4) says the same.
- **Tests and docs.** New tests go only in `tests/features/claude_host/test_claude_host_review_gaps.py`. Add one FEATURE.md "Historical Regressions" line per test, and README.md line additions only.
- **Re-read before touching session.py:** the file header (WHAT NOT TO DO 2: no steer while a prompt is open), AGENTS.md principles 1 and 2, and spec row 7, INV-18 and the §9.2 steer row. Update the header's KNOWN EDGE CASES sentence about the yield in the same commit.
- **Keep the constant.** `CLAUDE_STEER_YIELD_SECONDS` must stay a named constant; A007 blocks `asyncio.sleep(0)`.
