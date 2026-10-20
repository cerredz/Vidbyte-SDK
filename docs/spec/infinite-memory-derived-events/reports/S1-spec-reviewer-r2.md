VERDICT: SOUND WITH FIXES — Checked against the code, r2 resolves all 13 r1 findings, but one test pinned by PR #1159 that §13 does not list will stop the implementer after P1, some stale comments are still unscheduled, and the line caps leave less room than the spec's own 5 % tolerance. Every fix is a local text edit.

Findings are numbered from R-14 so they cannot be confused with r1's R-1 to R-13.

## WHAT THE SPEC GETS RIGHT

- **The abort model now matches the code.**
  - A child's `Exception` is wrapped once (base.py:976-979), and the three errors that pass through unwrapped are all `VidbyteSdkError`s (errors/base.py:209, :451, :547). So the error always becomes a card (EC-27).
  - AC-13's seam is real. `_commit` catches only `ToolExecutionError` (launch.py:363), so a `RuntimeError` from a patched `commit_entry` reaches the new outer handler while `staged` is still N. `ParallelPipeline` passes it through unwrapped (pipelines/base.py:63-66). The loop returns "Tool execution failed: …", and the run goes on to `run_finished`.
  - D-22's rule is `_error_text`'s rule (launch.py:386-391).
- **D-9's journal test is the right signal.**
  - `pair_finished` sets `_cards[key]` only after the fsynced append (journal.py:111-112).
  - EC-10 (finish announced, then the sink interrupts) and EC-25 (journal write fails twice) therefore each count the pair once.
  - The double-`_finish` path (an `OSError` from the first `pair_finished`) also decrements exactly once, through the second `_finish`.
- **The phases are reshaped correctly.** Enriched fields, changed signatures and their call sites all land in P2, so the r1 breakage is gone. The one leftover is R-14.
- **The nested-cancel order and the missing `batch_finished` are consistent everywhere.** A-6, EC-3, EC-26, INV-15, D-23, the §9.1 volume list, §13, and rows 5, 6 and 12 tell the same story. My own asyncio trace agrees with both orders: `[b, a]` gives a late abort, and `[a, b]` gives none.

## FINDINGS

R-14 [Blocker] [L10] §12.3 row 9, §12.6, §13 — Row 9 (P1) breaks a pinned handoff test that §13 does not list, so the implementer stops BLOCKED after P1
- Evidence:
  - Row 9 says: "add the key to `_entry_lines`' existing details (:276) beside `file`/`line`". §9.1 maps `malformed_memory` to `workspace._entry_lines`.
  - tests/features/infinite_memory_agent/test_infinite_memory_handoff.py:248 asserts `refused.value.details == {"file": "entries.jsonl", "line": 2}`. That is the exact details dict of the workspace.py:276 raise, reached through `run_handoff` → `run_entries`.
  - §13 "Tests pinned by PR #1159 that this spec changes" lists only handoff :339-372 for that file.
  - §12.6 says "After P1: every existing test the S2 test author did not change still passes".
  - §9.4 even says this error "can reach `run_handoff` callers", but it calls the change additive.
- Failure:
  - S2 writes from §13, so it leaves :248 alone.
  - After P1 the dict gains `"rule": InfiniteRefusalRule.MALFORMED_MEMORY`, and :248 fails.
  - §14 then sends the implementer to "Ask first … a pinned test the spec did not foresee", which costs a full loop.
  - A grep of every `details ==` in `tests/` finds no other pin on a raise site this spec tags. The other hit, records :326, is the settings error, which does not change.
- Smallest fix:
  - Add to §13 "Tests pinned…", under Handoff: ":248 pins the exact details of the `_entry_lines` error; they gain `rule` = `malformed_memory` (row 9, P1)."
  - Add `handoff :248` to §12.5's S2 bullet.

R-15 [Major] [L4] §12.3 rows 1, 3, 4, 5, 12 — Not every stale comment from r1's R-7 was scheduled: comments and docstrings in touched files that this change makes false or incomplete
- Evidence, line by line at 181f1992:
  - **vidbyte/lib/constants/infinite.py:202-204.** "Reply metadata keys: the run id this package adds, and the three the agent runtime sets, which events read the stop reason, tool calls, and usage from."
    - Row 3 puts `INFINITE_ITERATIONS_METADATA_KEY` and `INFINITE_CALL_RECORDS_METADATA_KEY` in that block (":202-209"), which makes five.
    - The denial `limit`/`reason` keys and the error-details `rule` key are not reply metadata at all.
    - Row 3 rewrites only the summaries comment and the byte-arithmetic comment.
  - **vidbyte/agents/infinite/events.py:118-119.** "When each pair was launched, by pair key, for its generator's duration."
    - Row 5 has `verifier_started` set `_launched[memory.key]`, keyed by the verifier, for the verifier's duration.
    - Row 5's comment list does not include this one.
  - **events.py:4, the ROLE line.** "Built once per run by InfiniteMemoryRuntime.arun". Row 11 now also builds one in `InfiniteMemoryAgent.run_handoff`.
  - **vidbyte/lib/dataclasses/infinite.py.** The class docstrings of the 8 enriched records list their fields, and row 4 does not schedule them. For example:
    - :340 `InfiniteRefusalDetails`: "the tool that refused the call and the problem it reported";
    - :353 `InfiniteSubagentLaunchedDetails`;
    - :302 `InfiniteRunFinishedDetails`;
    - :324, :432, :481, :508, :545.

    The header's FUNCTION INVENTORY (:6) also lists every record by name, but row 4 changes only the two counts.
  - **vidbyte/lib/enums/infinite.py:106.** `InfiniteStopCause`: "Why a run stopped before it finished". It now also types `subagent_aborted.reason`.
  - **vidbyte/agents/infinite/README.md:116.** "`memory_dropped`: a verifier dropped a staged entry."
    - After FR-1 this is false: rule and unchecked drops also fire, and an unchecked drop can be attributed to the generator.
    - Row 12's "list all 22 kinds … plus the new fields of …" does not say that an existing kind's meaning must be rewritten.
- Failure: An implementer who follows §12.3 row by row (§14 "Always") leaves a false count, a false ROLE line, a misleading attribute comment, and eight under-described records. Each one draws the convention comment that r1's R-7 was raised to prevent (AGENTS.md principle 2: "never describe behavior that is gone"; A001 headers).
- Smallest fix:
  - Row 3: rewrite :202-204 to name the five runtime keys, and give the denial and refusal keys their own one-line comment.
  - Row 5: the `_launched` comment says "pair or verifier key → start time, for the generator's and verifier's durations". ROLE adds "and once per `run_handoff` call by InfiniteMemoryAgent".
  - Row 4: each enriched record's docstring names its new fields, and FUNCTION INVENTORY adds the 8 new record names.
  - Row 1: the `InfiniteStopCause` docstring adds "or a pair aborted".
  - Row 12: rewrite :116 to cover all three drop reasons.

R-16 [Major] [L11] §8.1 D-15, §15 A-10, §14 — The 5 % estimate tolerance is wider than the room the caps leave, so the two stop rules disagree, and launch.py is likely to land at its cap
- Evidence:
  - Measured lines after the header (the contract test's `_lines_after_header`) are 400 / 398 / 604, the same as §8.4.
  - The caps leave 25, 12 and 21 lines of room over the estimates: 650 − 625, 460 − 448 and 850 − 829. That is 4.0 %, 2.7 % and 2.5 %.
  - D-15 says the plan flips "if … an estimate is off by more than 5 %", and A-10 says the estimates "hold within 5 %". §14 separately says "exceeding a §8.4 line cap" stops the work.
  - My own count of row 6 comes to about 451 lines (range 446–460):
    - imports +7;
    - `execute` +5;
    - `denials` +6;
    - `__init__` +2;
    - `run` +25, of which about 12 are code and about 13 are the new narration, the reworded `@intent`, and the new `@intent an-aborted-pair…`, all wrapped at 72 columns;
    - `_commit` +4;
    - `_finish` +4.
  - The events and records estimates look honest (my counts: about 605–625 and about 815–830).
- Failure:
  - At 465 lines, launch.py is within A-10's tolerance but over its cap. The implementer then either stops BLOCKED or trims the narration that AGENTS.md principle 2 requires.
  - The comment rewrites in row 6 are the least predictable lines in the plan.
- Smallest fix:
  - Make the caps the estimate plus 5 %: events 660, launch 470, lib records 870.
  - Apply them in §2, §8.4, NFR-6, row 13 and §12.4. This is still the pre-approved, explicit S2 budget row.
  - Alternatively, keep the caps and restate D-15 and A-10 as "the cap binds; room is 25/12/21 lines".

R-17 [Minor] [L10] §8.1 D-9/D-10, §12.3 rows 5–6 — Two placements are left open, and the choice changes what S2's tests observe
- Evidence:
  - **(a) Where the decrement sits.** Row 5 pins "decrement first" for `subagent_finished`, but for `subagent_aborted` it gives only the condition (`journal.finished(pair.key) is None`).
  - **(b) Where `phase` becomes COMMIT.** D-10 and row 6 set `phase = COMMIT` "before the verdict step", but `_verdict` sits inside `if status is not FAILED:` (launch.py:252-256).
- Failure:
  - **(a)** If the decrement follows `_deliver`, a sink that raises `Exception` on `subagent_aborted` (AC-22's sink) skips it. `in_flight` then never comes back down, which breaks INV-16.
  - **(b)** If COMMIT is set inside that block:
    - a failed generator's `_finish` runs in phase `generator`;
    - `verifier_finished` runs in phase `commit`;
    - EC-10 (phase `commit` while `subagent_finished` is announced) fails for the simplest script, a blank generator.
- Smallest fix:
  - **(a)** Row 5: "`subagent_aborted` decrements first, as `subagent_finished` does."
  - **(b)** Row 6 and D-10: "set `phase = COMMIT` after the `if status is not FAILED:` block, just before `if verdict is not UNCHECKED:`".

R-18 [Minor] [L4] §12.3 row 5 — A002 will demand an `@intent` on `subagent_launched` if the attempt count is held in a variable named `attempt`
- Evidence:
  - lint/rules/a002_intent_comments.py:27 maps the token `attempt` to the "retries" category. It scans every `ast.Name` and `ast.Attribute` in a function, and `_has_intent` wants a marker within def −4 to def +20.
  - Row 5 lists A002 `@intent`s only for `_rule` and `workspace_usage`.
  - Row 4's getattr-loop pattern keeps the records safe.
- Failure: The natural `attempt = launch.journal.started.count(pair_key)` in `subagent_launched` raises A002 above its baseline, and the lint stops reading `AGENT-LINT: PASS`.
- Smallest fix: Row 5 says to pass `attempt=` as a keyword argument inline, or to give `subagent_launched` an `# @intent` (for example `an-attempt-counts-journal-starts`).

R-19 [Minor] [L9] §12.3 row 12, §11, §13 — Clerical mismatches
- Evidence:
  - Row 12 says "Notes for agents gains three bullets", then lists six.
  - §11 (r2 evidence) and §13 cite runtime.py:1341-1348 for the path an escaped error takes. In fact `_execute_tool` (runtime.py:1482-1486) first wraps it as `ToolExecutionError("Tool execution failed: {exc}", details={"error_type": …})`, and the `except ToolExecutionError` branch at :1331-1340 builds the result. The text and the metadata (`error="execution_error"`, `error_type="RuntimeError"`) are identical, so only the citation is wrong.
- Smallest fix: Change "three" to "six". Cite runtime.py:1482-1486 and :1331-1340.

## VERIFIED CLAIMS

### r1 findings: did r2 resolve each one?

| r1 | Status | Code evidence |
|---|---|---|
| R-1 | RESOLVED | The AC-13 seam exists. `_commit` catches only `ToolExecutionError` (launch.py:363). The handler runs before the re-raise, so `subagent_aborted` precedes the tool error. `gather` raises with no `return_exceptions` (pipelines/parallel.py). `_execute_tool` wraps the error as "Tool execution failed: …" (runtime.py:1482-1486), and the result is built at :1331-1340. EC-2 and EC-27 are correct. The §13 prediction for :479 now holds: a `VidbyteSdkError` stays a card. |
| R-2 | RESOLVED | D-22 mirrors `_error_text` (launch.py:386-391). AC-14 holds: the runtime re-raises the runner's own exception (runtime.py:772-818; there is no retry middleware on these agents), and base.py:976-979 wraps it once. pairs :467-479 confirms the cause chain is one level deep. |
| R-3 | RESOLVED (narrowed) | EC-26, D-23, G-3, INV-15, the §9.1 volume list, and rows 5, 6 and 12 agree. The pipeline raises past `batch_finished` (pipelines/parallel.py `run`). A consumer can still group by joining the pair key to `subagent_launched.batch`. |
| R-4 | RESOLVED | My trace of `_GatheringFuture.cancel` and `_done_callback` matches EC-3, INV-15 and A-6: flat pairs and depth-2 leaf pairs announce before `run_stopped`, and a pair waiting on its inner gather can announce after it. AC-12 and lifecycle :88 are flat (`_cancel_while_alpha_waits`, lifecycle :56-73). |
| R-5 | RESOLVED | Row 14 targets vidbyte/agents/README.md:183 (30,375 chars). The repo-wide search outside `docs/` confirms §12.5: only contracts/sdk-public-api.json:253 names `InfiniteEventKind`, and the contract lists names only. lib/enums, lib/constants and lib/dataclasses have no README. |
| R-6 | RESOLVED, except R-14 | P1 is additive: new members, records and `DETAILS_TYPES` entries, `started`, and `map_omitted`. Enriched fields and signatures move to P2 together. The only P1 break of an untouched test is handoff :248 (R-14). Stream :436 is expected red and is acknowledged. |
| R-7 | PARTIAL | All five r1 sites are scheduled with their new wording: launch.py:225-229 and :9, runtime.py:130, the events.py header, and journal.py:4. The residue is R-15. |
| R-8 | RESOLVED | journal.py:111-112 appends, then sets `_cards`. `finished` reads `_cards` (:121-123). `_finish` sets `result` before `pair_finished` (launch.py:380-382). INV-3, INV-10 and INV-16 are qualified. The decrement's placement is R-17(a). |
| R-9 | RESOLVED | `descriptions(run_id)` keeps only that run's records and dedupes by path (workspace.py:116-118, :338-351). `run_finished(journal, result, workspace)` matches across §8.5, §9.2, §9.4 and rows 5 and 7. |
| R-10 | RESOLVED | The members are appended after `TOOL_REFUSED` (§8.5, row 1), `DETAILS_TYPES` follows the same order, and A-8 is withdrawn. |
| R-11 | RESOLVED | T-2(c) is now an accepted limitation, with EC-28. `_descriptions` accepts any string (workspace.py:349), and `INFINITE_MORE_FILES` = "… and {count} more files" (constants :135). |
| R-12 | RESOLVED | `level` appears in §8.5, §9.1 (validated as ≤ `INFINITE_EVENT_PERCENT_SCALE`), the summary template, and AC-17. `cut` stays derived, as C002 requires. |
| R-13 | RESOLVED | `_worst` is at records :144. `INFINITE_CALL_RECORDS_METADATA_KEY` is used the same way in §9.3 and rows 6 and 7. It does not clash with `INFINITE_TOOL_CALLS_METADATA_KEY = "tool_call_count"` (constants :207). The new constants total exactly 18, matching §8.4 and row 3. |

### Claims r2 introduced or changed

| Claim | Verdict | Evidence |
|---|---|---|
| EC-27 / INV-19: every child `Exception` reaches the pair as a `VidbyteSdkError` | TRUE | base.py:965-979. Only `_ensure_mcp_connected()` runs before the `try` (base.py:916), and children have no MCP servers. `AllModelsFailedError(AgentExecutionError)` is at errors/base.py:209, and the other two are at :451 and :547. |
| AC-13 result text is "Tool execution failed: …", and the run reaches `run_finished` | TRUE; the cited line is wrong | runtime.py:1482-1486 → :1331-1340, not :1341-1348 (R-19) |
| D-9 never double-counts | TRUE, given "decrement first" in both methods | The EC-10, EC-25 and double-`_finish` paths were traced. The gap is R-17(a). |
| D-15 measurements and estimates | TRUE (400/398/604); the room is thin | My recount: launch ≈ 451, events ≈ 605–625, records ≈ 815–830 (R-16) |
| AC-9: quota fields equal the quota line returned to the model | TRUE | memory.py:88-89, :94-95 and :105-109 increment before the event, and `answer()` (:134-136) appends `quota()` afterwards |
| Rows 8 and 9: raise-site and call-site line numbers | TRUE | memory.py :80, :125, :187, :192, :228, :262; :176, :231, :265, :291. workspace.py has 18 sites plus :276. |
| Row 2: enum export block lines | TRUE | lib/enums/__init__.py :106-116 and :275-284 |
| §4 imports are root exports | TRUE | `vidbyte.__all__` holds all four names |
| §13: AC-36 :560 and pairs :479 predicted lists; AC-2 under default caps | TRUE | Traced against `ac2_tree` (fixtures :164) and the pairs test :542-560 |
| §13: "No test calls run_finished, batch_rejected, or tool_refused directly" | TRUE | Direct calls exist only at records :488 (`subagent_launched`) and :490, and handoff :371 (`file_written`). All three use real objects, so the quota fields build. |
| D-10 / §12.4: S024 depth exactly 3; S019 accepts the handler | TRUE | lint/rules/s024 (`MAX_NESTING_DEPTH = 3`; try counts, handlers do not); s019 requires an `ast.Raise` in a `BaseException` handler. McCabe for `run` is about 6. |
| §12.6: after P1, every untouched test still passes | FALSE | handoff :248 (R-14) |
| §12.5 / row 14: no other doc describes the stream | TRUE | See R-5 above |
| `to_tuple(item_type=int, max_items=…)` exists for `sections` | TRUE | lib/dataclasses/validation.py:203 |
| `deepest` = segments // 2 | TRUE | `INFINITE_TASK_NAME_PATTERN = ^[a-z0-9][a-z0-9-]{0,63}$` (constants :80) has no slash, and the root key is `root` (:115) |
