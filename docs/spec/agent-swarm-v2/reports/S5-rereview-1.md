LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — All 16 fixes hold in the code, and no fix changed behavior beyond its finding. But half of the R-2 Blocker fix has no test: `_estimate`, which feeds INV-32's fallback and growth check, can go back to counting content only while all 275 tests still pass. Under that change, every Gemini member compacts once and never again.

Scope: `git diff 582c414d..ffff490a` read in full (8 product files, 7 S2 test commits, docs), plus the whole files it touches; spec r5, request.md §A/§D, review.md, S5-repair-1.md, verify-log.md, test-plan.md. `V`, `E` and `RR` below are `<SCRATCH>/s4verify`, `<SCRATCH>/s4eng` and `<SCRATCH>/rereview1`, where `<SCRATCH>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/6308f8f2-185f-45a5-b1b7-9102079fc8ee/scratchpad`. Every Python command ran with `PYTHONPATH=<WT>`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **The repair is surgical.** A code-token diff with comments, layout and headers dropped (`python -I RR/code_tokens.py 582c414d ffff490a <5 files>`) shows only these changes: the three `_end_check()` call sites became `reason = self._end_reason()` plus `if reason is not None: self._stop(reason)`; `return` replaced `_stop` inside `_end_reason`; the two classifiers were extracted; the four literals became constants; the R-2/R-6 lines in `member.py`; the R-8 details; and the R-9 guard. `vidbyte/lib/dataclasses/agent_swarm.py` has 1,946 code tokens before and after.
- **The exactly-once machinery survived the R-1 split.** `_end_reason` (`runtime.py:447-461`) is pure and gives the same decision as `_end_check` in every state. Each caller passes its reason to `_stop` with no `await` in between (`:177-179`, `:198-200`, `:281-283`). The only other places that set the stop are `arun` (`:139`) and `record_model_call` (`:337`). The 15 non-equivalent S4 mutants are all still killed. Three new caller mutants are killed too: dropping the `_end_reason`→`_stop` pair in `end_turn`, in the stray-cancel branch, or in the `_run_member` tail.
- **R-6 handles every edge the briefing named.** The snapshot is set only after a compaction that made a summary call (`member.py:117-121`). A `compact` request never waits (`:100-101`). The growth check is always true before the first compaction (`:99`). The live list only shrinks through compaction, because the loop applies a `before_model_call` transform to the call options alone (`vidbyte/agents/runtime.py:748`, `:1085-1094`). So a trim cannot leave a stale snapshot that blocks compaction, and a failed side call keeps the last good snapshot. The S4 hysteresis probe reproduces S5's numbers exactly: 3 / 5 / 6 / 5 summary calls, with the control unchanged at `[74428, 75025, 75027]`.
- **R-3 keeps every word, and the event bytes are unchanged.** Comment-word diffs (`RR/comment_words.py`) for runtime, member and observer show only additions, plus the three module-scope comments that moved with their constants. Every swarm module has 0 comment lines over 72 columns, and `runtime.py` has 498 lines after its header. The moved constants have identical values (`"bash"`, `"timeout"`, the path-argument map, `"agent_swarm_stopping"`), and `vidbyte/lib/constants/agent_swarm.py` imports only `collections.abc`.

FIX-BY-FIX JUDGEMENT (R-1..R-16)
- R-1 @8e71ec8c — CONFIRMED FIXED. `runtime.py:447-461`: `_end_reason` makes no record and no `_stop` call. Its three callers are listed above. `grep -rn _end_check vidbyte` finds nothing. The `end_turn`, stray-cancel and tail caller mutants each fail a test, for example `test_every_agent_failing_ends_failed_with_no_replies` (TIMEOUT instead of FAILED).
- R-2 @8e56aaea — CONFIRMED FIXED in code (`member.py:139`, `:154`, `str(message)`), against the formatter's shapes (`formatter.py:381` `content: None` + `tool_calls`; `:485` `parts`). `v_keep_last_providers.py`: gemini `compaction=[('auto', 72000, 2)] side_calls=1`. `v_write_heavy.py`: `[('auto', 72000, 8)] side_calls=1`. `RR/v_gemini_contents_shipped.py` (V's probe without its in-memory patch): `problems: none`. Test coverage is incomplete; see R-C1.
- R-3 @6455f9e9 (test route c9a5d0db) — CONFIRMED FIXED. The awk check gives 0 for all 13 swarm modules, and runtime.py has 510 − 12 = 498 lines. Only additions appear in the narration (see above).
- R-4 @a12973e7 — CONFIRMED FIXED. `lint/run.py --rule A002 --all --format json`: found 562, baseline 703, and none of the findings is in an agent_swarm file. `@intent` is at `member.py:161`, `runtime.py:352`, `:360`.
- R-5 @360ceab1 (spec r4 79f378cf, docstring 2f346592) — CONFIRMED FIXED. The package README is at line 114, and the spec at INV-23 (`spec.md:221`), AC-10 (`:257`) and EC-25 (`:302`). `E/probe_retry.py` still shows `7 agent_failed builder 'ProviderRequestError: … 429 …'` with `builder calls made: 1 of 2 scripted`, so the README sentence is true.
- R-6 @81b0672e (READMEs 2567874f, 6d604082) — CONFIRMED FIXED (`member.py:92-105`, `:117-121`). The `hyst_off`, `hyst_applies_to_tool`, `snapshot_before`, `snapshot_never` and `growth_from_trigger` mutants are each killed by the R-6 test. Two are not; see R-C2. Both READMEs describe the wait.
- R-7 @78b067d1 — CONFIRMED FIXED. `compact_while_stopping`, `self_writer_as_peer` and `side_call_tokens_not_added` each give `1 failed, 274 passed`.
- R-8 @19087212 — CONFIRMED FIXED (accepted variant). Probe: `{}` → `{'received_swarm_runtime': 'NoneType'}`; `swarm_runtime` only → `{'received_summarizer': 'NoneType'}`; `summarizer` only → `{'received_swarm_runtime': 'NoneType'}`.
- R-9 @79f3dbb8 — CONFIRMED FIXED (`agent_swarm_observer.py:94-95`). `E/probe_trim_after_stop.py`: `10 history_trimmed builder dropped=2` is still recorded before the stop, `13 swarm_stopping max_tokens`, and after the stop only `15 tool_called builder` and `16 agent_released builder`. The `trim_after_stop` mutant fails the R-9 test, and the `trim_skips_always` mutant fails the AC-11 contract test, so the pre-stop path is pinned.
- R-10 @d01acf5e — CONFIRMED FIXED. `vidbyte/prompts/README.md` now names `message_sent` and `message_stopped_recipient` as the success replies, and `message_blank_text` and `message_unknown_recipient` as the two refusals, which matches `runtime.py:214`, `:216`, `:226`, `:241`.
- R-11 @11a3847a — CONFIRMED FIXED. `<SCRATCH>/s5/probe_side_call_bug.py`: `10 agent_failed RuntimeError: recording bug on the summary call`.
- R-12 @afa17494 — CONFIRMED FIXED (`test-plan.md:98`).
- R-13 @001e2c72 — CONFIRMED FIXED. The `runtime.py:4` header matches `member.py:106`, `:167`, `:179`. The `agent_swarm.py:7` header matches the `_COUNT_FIELDS`/`_TEXT_FIELDS`/`_ENUM_FIELDS` tables at `:78-87`.
- R-14 @79f378cf — CONFIRMED FIXED (`spec.md:379` D-14 trigger, `:1084` deviation 10).
- R-15 @ea6e1b91 — CONFIRMED FIXED (`constants/agent_swarm.py:61-67`). The grep for those literals in the swarm package and middleware finds nothing. The values are identical, and A006 is clean (lint PASS).
- R-16 @7e70db8a — CONFIRMED FIXED (`runtime.py:463-483`). Each classifier is called once from `record_tool_outcome` (`:310`, `:317`), and neither calls another helper. The logic is token-identical to the inlined code. `trunc_at_cap`, `self_writer_as_peer` and the new `timeout_not_classified` mutant are killed.

REGRESSIONS INTRODUCED BY THE FIXES: none in behavior. The pack passes (275) and lint passes, the contract is current, the token diff is limited to the findings, and the exactly-once events are unchanged under 19 mutants. The two coverage gaps below are in the tests written for R-2 and R-6, not in the code.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Major] [spec-ID → test trace] `vidbyte/agents/agent_swarm/member.py:135-139` — INV-33's fallback and growth-check estimate (half of the R-2 Blocker fix) has no test, so it can be reverted while the pack stays green, and every Gemini member would again stop compacting after its first compaction
  Evidence: Mutant `estimate_content_only` (`RR/mut/rr1mut.py`, in memory only) makes `_estimate` count `str(message.get("content") or "")`. `RR1MUT=estimate_content_only PYTHONPATH="<WT>;RR/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p rr1mut` gives `275 passed in 6.35s`. The matching `_keep_last` mutant (`keep_content_only`) is killed by the Gemini test, which shows the R-2 tests pin only the keep count. Both R-2 tests script usage at the trigger (`test_agent_swarm_compaction.py:229`, `:256`), so the fallback path is never reached, and their histories never reach a second compaction. Even so, test-plan.md:83 says that test catches "a size estimate that reads only `message["content"]` … no Gemini member ever compacts, automatically or on request". `python RR/probe_estimate_gaps.py` on the shipped code versus `RR1MUT=estimate_content_only`:
    - `[gemini growth]` (provider reports the trigger every call, fourteen 30,000-char reads): shipped `compaction=[('auto', 2), ('auto', 9), ('auto', 9)] side_calls=3 history_trimmed=[]`; mutant `compaction=[('auto', 2)] side_calls=1 history_trimmed=[2, 4]`
    - `[gemini no usage]` (EC-8): shipped `compaction=[('auto', 75305, 8)]`; mutant `compaction=[]`
  Failure: Take a Gemini member whose provider reports usage normally, after its first compaction, with the estimate reverted to content only. The parts history adds nothing to the estimate, so INV-32's growth condition never holds again. The 90,000-token trim becomes the mechanism, which INV-36 forbids, and that is the R-2 failure again on the common path. A member whose provider reports no usage never compacts at all. The full pack stays green throughout.
  Smallest fix: S2 adds one test, for example a Gemini variant of `test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not`: usage at the trigger on every call, fourteen 30,000-char reads, then assert summary calls after loop calls 4, 8 and 12 and no `history_trimmed`. Optionally add the `usage={}` five-read Gemini case for INV-32's fallback. Narrow test-plan.md:83's "fails if" to the keep count, or add the new test row beside it. No product change.
  Spec IDs: INV-33 ("INV-32's fallback and growth check, and this keep count"), INV-32, INV-36, EC-8, FR-8

R-C2 [Minor] [spec-ID → test trace] `vidbyte/agents/agent_swarm/member.py:99`, `:121` — two INV-32 clauses have no test: a requested compaction also resets the growth baseline, and the comparison is "at least"
  Evidence: Two mutants pass the whole pack (`275 passed`). `snapshot_only_auto` sets `_compacted_estimate` after automatic compactions only. `growth_strict_gt` changes `>=` to `>`. The R-6 test cannot tell `snapshot_only_auto` apart from the shipped code, because its tool compaction at iteration 6 leaves the same estimate as iteration 4's automatic one. `python RR/probe_estimate_gaps.py` `[tool then trigger]` (one `compact` request as the first compaction, then the trigger with one read of growth): shipped `compaction=[('tool', 3, 2)] side_calls=1`; `snapshot_only_auto` `compaction=[('tool', 3, 2), ('auto', 72000, 1)] side_calls=2`.
  Failure: A member whose first compaction was requested pays for one extra summary call at its next iteration at the trigger, which INV-32 says is not due ("grown by at least TARGET since this member's last compaction").
  Smallest fix: S2 adds one test: a `compact` request, then a call at the trigger with less than the target of growth, then assert exactly one `compaction` (`tool`). Pinning the `>=` boundary is optional.
  Spec IDs: INV-32, D-12

R-C3 [Minor] [spec drift] `docs/spec/agent-swarm-v2/spec.md:576-577`, `:456-475`, `:415`, `:740`, `:375`, `:264` — r5's "spec text brought in line with the repaired code" misses five things the repair added
  Evidence:
    - §8.5's runtime private list (`:576-577`) omits `_changed_path` and `_command_failure` (`runtime.py:463`, `:474`; `_refuse`, `:395`, was already missing).
    - §8.5's constants block, "every bound has one name" (`:456-475`), omits the four R-15 constants (`constants/agent_swarm.py:61-67`).
    - §8.4 "New collections/tables" (`:415`) and §9.1 "Runtime state" (`:740`) omit the member's `_compacted_estimate` (`member.py:77`), although §8.5's pseudocode uses it.
    - D-10 (`:375`, "it is due on a pending request or when the last real `total_prompt_tokens` is at least the trigger") states the r3 rule.
    - AC-17 (`:264`) still reads: given a member at the trigger with no request, one automatic compaction happens. That no longer holds for a member that compacted before and has grown by less than the target (INV-32/D-12, `member.py:99-103`).
  Failure: A reader who implements or tests from D-10 or AC-17 alone expects a repeat compaction that INV-32 forbids. The §8.5 inventories do not list the shipped names.
  Smallest fix: The orchestrator edits the spec text (r6): add the names to §8.5, §8.4 and §9.1, add "and, after the first compaction, the growth condition of INV-32" to D-10, and add "(before its first compaction)" to AC-17's Given. No code or test change.
  Spec IDs: INV-32, D-10, D-12, AC-17, §8.4, §8.5, §9.1

VERIFIED CLAIMS: <each claim checked and whether it held>
- S5 report "`_stop` is called only by `arun` and the three callers": HELD IN SUBSTANCE. The grep also finds `record_model_call` at `runtime.py:337` (MAX_TOKENS), which INV-12 allows. The sentence just leaves that site out.
- S5/briefing "each R-7 mutant gives exactly `1 failed, 274 passed`": HELD (all three). The other 13 S4 mutants: 12 killed, and `keep_last_zero` is still the equivalent one (`275 passed`).
- Briefing "`git diff 791a8d56..ffff490a -- tests/` is empty": HELD (empty). NG-1 diff (`vidbyte/agents/runtime.py`, `base.py`, `validation.py`): HELD (empty). `lint/` diff in the whole run: HELD (empty, so no baseline edit).
- Spec AC-1 "the §4 snippet runs as written": HELD. The 16 non-blank snippet lines in `spec.md` §4 are byte-identical to the block in `test_agent_swarm_acceptance.py:80-98`, and that test gives `1 passed` (scripted runner and FakeTavily; no real call).
- Spec INV-12 (r5) "`_end_reason` only decides; callers pass it to `_stop` in the same block": HELD (`runtime.py:177-179`, `:198-200`, `:281-283`).
- Spec INV-32 (r5) hysteresis rule and §8.5 pseudocode lines 679-691: HELD line for line (`member.py:88-123`), including setting the snapshot before `_count_side_call` and `record_compaction`.
- Spec INV-33 "every estimate counts the whole of each message": HELD in code (`member.py:139`, `:154`). The tests prove it only for the keep count (R-C1).
- test-plan.md:83 "fails if a size estimate reads only `message["content"]` … no Gemini member ever compacts": NOT HELD for `_estimate` (R-C1); HELD for `_keep_last`.
- test-plan.md:86 "fails a fix that gates a `compact` request on growth": HELD (`hyst_applies_to_tool` fails it).
- §8.4 budget: HELD. The whole run adds 16 files under `vidbyte/` and 8 new classes, plus `AgentSwarmSettings` moved; the repair adds no file, class, dependency or settings field. Every file the repair touched is in §12.3 (rows 3, 4, 30, 33, 34, 39, 42, 43).
- AC-25 gate pieces I could run: `python lint/run.py` gives `SDK-LINT: PASS` (exit 0), with no line naming agent_swarm. `generate-sdk-public-api.py --check` gives "current at a319f44d… (650 exports)". I did not run `run_ci.py` (forbidden by the briefing).
- Known limitation A-12/Q-9 (CJK peak of 129,015) reproduced exactly. Not a finding, per the briefing.

COMMANDS RUN: <each with its final lines>
- `git -C <WT> diff --stat 791a8d56..ffff490a -- tests/` → (empty); `… 39ce8b20...ffff490a -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py` → (empty); `… -- lint/` → (empty); `git status --short | wc -l` → `0` (before and after every run)
- `python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` → `275 passed in 12.72s`
- `S4MUT=<id> PYTHONPATH="<WT>;<SCRATCH>/s4eng/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p s4mut`:
    - `compact_while_stopping`, `self_writer_as_peer`, `side_call_tokens_not_added`, `trunc_at_cap`, `budget_ignores_total`, `no_post_abort`, `measure_input_not_prompt` → `1 failed, 274 passed`
    - `cancel_state_swap`, `trim_records_unchanged`, `fail_keeps_inbox`, `stopped_recipient_queued` → `2 failed, 273 passed`
    - `budget_gt`, `wake_refused_not_recorded_at_turn_end` → `3 failed, 272 passed`
    - `dropped_no_plus_one` → `8 failed, 267 passed`
    - `side_call_not_budgeted` → `12 failed, 263 passed`
    - `keep_last_zero` → `275 passed` (equivalent)
- `RR1MUT=<id> PYTHONPATH="<WT>;RR/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p rr1mut [-x]`:
    - `hyst_off`, `hyst_applies_to_tool`, `snapshot_before`, `snapshot_never`, `growth_from_trigger` → `1 failed, 274 passed` (R-6 test)
    - `snapshot_only_auto` → `275 passed`; `growth_strict_gt` → `275 passed`; `estimate_content_only` → `275 passed`
    - `keep_content_only` → FAILED `test_a_gemini_member_at_the_trigger_compacts_its_parts_history_through_one_summary_call`
    - `trim_after_stop` → FAILED `test_a_model_call_refused_after_the_stop_records_no_history_trimmed`
    - `trim_skips_always` → FAILED `test_tool_results_are_cut_and_a_long_history_is_trimmed_before_each_model_call`
    - `end_reason_dropped_in_end_turn` → FAILED `test_the_section_4_snippet_runs_as_written`
    - `end_reason_dropped_in_stray_cancel` → FAILED `test_a_cancelled_error_raised_by_on_event_while_an_agent_works_fails_that_agent`
    - `end_reason_dropped_in_run_member_tail` → FAILED `test_every_agent_failing_ends_failed_with_no_replies`
    - `timeout_not_classified` → FAILED `test_a_bash_command_that_runs_out_of_time_records_command_failed_timeout`
- `python V/v_keep_last_providers.py` → openai/anthropic/gemini read_lines `compaction=[('auto', 72000, 2)] side_calls=1`; openai write_text (two writes) `compaction=[] side_calls=0` (correct: rounding keeps both groups, so nothing older exists)
- `python V/v_write_heavy.py` → `[as-is] compaction=[('auto', 72000, 8)] side_calls=1 last call messages=5`
- `python RR/v_gemini_contents_shipped.py` → `problems: none`
- `S4V_ITERATIONS=24 python V/v_hysteresis.py` → summary calls 3 / 5 / 6 / 5; control measured `[74428, 75025, 75027]`; CJK peak 129,015
- `python E/probe_trim_after_stop.py` → `10 history_trimmed builder dropped=2` … `13 swarm_stopping max_tokens` · `15 tool_called builder` · `16 agent_released builder` · `builder model calls reaching the runner: 2`
- `python E/probe_retry.py` → `7 agent_failed builder 'ProviderRequestError: openai returned 429: rate limited, try again'` · `builder calls made: 1 of 2 scripted`
- `python <SCRATCH>/s5/probe_side_call_bug.py` → `10 agent_failed RuntimeError: recording bug on the summary call` · `stop: quiet`
- `[RR1MUT=<id>] python RR/probe_estimate_gaps.py` → as quoted in R-C1 and R-C2
- R-8 probe (`AgentSwarmMemberRuntime(**kw)`) → as quoted under R-8
- `awk 'length($0) > 72' <f> | grep -cE '^\s*#'` over 13 swarm modules → `0` each; `wc -l runtime.py` → `510` (header ends at line 12 → 498)
- `python -I RR/comment_words.py 582c414d ffff490a <runtime, member, observer>` → only inserts, plus the moved module-scope comments; `python -I RR/code_tokens.py 582c414d ffff490a <5 files>` → only the intended code changes; `agent_swarm.py` 1946 → 1946
- `python lint/run.py --rule A002 --all --format json` → exit 0, `found 562, baseline 703, verdict IMPROVED`, swarm entries `[]`
- `python lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` · `SDK-LINT: PASS` · exit 0
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at a319f44dfec4d2577e0707767bad87bbb7063fa8 (vidbyte-sdk 0.3.0, 650 exports).`
- `python -m pytest tests/features/agent_swarm/test_agent_swarm_acceptance.py::test_the_section_4_snippet_runs_as_written -q` → `1 passed in 1.13s`; spec-vs-test snippet comparison → `spec lines 16 test lines 16 identical: True`

STATUS: DONE
STAGE: S4 reviewer (conformance)
REPORT: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2/docs/spec/agent-swarm-v2/reports/S5-rereview-1.md
PRODUCED: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2/docs/spec/agent-swarm-v2/reports/S5-rereview-1.md
HEAD: no commits
SUMMARY (≤ 10 lines): VERDICT MERGEABLE AFTER FIXES. All 16 fixes are confirmed and none regressed behavior (pack 275, lint PASS, contract current, 19 mutants killed). 0 Blocker, 1 Major, 2 Minor. Most important: no test pins INV-33's whole-message `_estimate` (the fallback and growth half of R-2), so reverting it passes 275/275 while every Gemini member compacts once and then falls back to the trim.
NICHE FACTS FOR THE NEXT AGENT (≤ 8 bullets):
- Mutant plugin: `RR1MUT=<id> PYTHONPATH="<WT>;<SCRATCH>/rereview1/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p rr1mut`. R-C1 is `estimate_content_only`; R-C2 is `snapshot_only_auto` and `growth_strict_gt`.
- Observable repro: `[RR1MUT=<id>] python <SCRATCH>/rereview1/probe_estimate_gaps.py` (scenarios: Gemini no usage, tool then trigger, Gemini growth).
- `V/v_gemini_contents.py` imports an in-memory patch with the old `_measured_context(messages)` signature; run `RR/v_gemini_contents_shipped.py` against the current code instead.
- The fix for R-C1 and R-C2 is tests only (S2 owns `tests/`). R-C3 is spec text only (orchestrator, r6).
