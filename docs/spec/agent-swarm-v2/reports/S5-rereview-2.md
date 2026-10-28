LENS: conformance
VERDICT: SOUND — R-20, R-21 and R-22 are all fixed, nothing regressed, and each of the five new cases kills its target mutant on its own side-call-schedule assertion. What remains is three Minor, test-only or spec-text follow-ups: one growth-restart clause still has no test, one assertion is stricter than INV-33, and one AC proof cell r6 left behind.

Scope:
- `git diff ffff490a..35b05f34`, read in full: the fixture, the compaction module, FEATURE.md, the README, test-plan.md, spec r6, review.md, the S2 Round 2 report and verify-log.md. I read the five new tests and the helpers they use in full, along with `member.py` and `constants/agent_swarm.py` as they stand.
- `git diff 04cf9caa..35b05f34 -- vidbyte/` is empty. So is the same diff outside `docs/` and `tests/`.
- Paths: `<WT>` is the worktree, `<SCRATCH>` is the session scratchpad, and `RR2` is `<SCRATCH>/rereview2`. Every Python command ran with `PYTHONPATH=<WT>`, and every mutant is applied in memory only. `git status --short | wc -l` gave `0` after every run, until this report was written.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Each target mutant fails on the assertion that names its spec clause, not on a side effect.** That assertion is the summary-call schedule (`side_after`).
    - `estimate_content_only` fails `:378` (`[4]` instead of `[4, 8, 12]`) and `:416` (`[]` instead of `[5]`).
    - `snapshot_only_auto` fails `:461` (`[2, 3]` instead of `[2, 4]`).
    - `growth_strict_gt` fails `:516` on the exact-target row (`[2]`).
    - My `growth_minus_one` fails `:516` on the one-below row (`[2, 4]`).
    - My `fallback_zero` fails only `:416`, so this test is the one guard of the no-usage fallback.
    - My `growth_by_measured` fails `:333`, `:378`, `:461` and `:516`.
- **The count thresholds have thousands of tokens of margin.** These figures come from the member runtime's own estimates, read by `RR2/plug/rr2spy.py`:
    - Gemini growth: 22,686, then 30,248, around the 27,000 target.
    - No-usage history: 60,252, then 75,315, around the 72,000 trigger.
    - Restart: 15,064, then 30,128, around the 27,000 target.
  So the cases pass under any whole-message estimate tried: S2's `json`/`list`/`leaves` and my `est_json`, `both_json`, `keep_json` and `keep_leaves` all give `280 passed`. They pin INV-32 and INV-33, not `str(message)`, with the one exception in R-C2.
- **The boundary test's instrument and its self-check are sound.**
    - The spy shows that the member itself measured growth of `27000` (exact-target row) and `26999` (one-below row) at iteration 4. That is exactly what the test sized and what `:515` asserts.
    - The two rows bracket the code's threshold to one token.
    - The fixed call ids make the test independent of order: the five cases pass alone (`5 passed`), and the pack passes with its modules reversed (`280 passed`).
- **The fixture change does nothing for default callers.** `RR2/probe_fixture_default.py` answers the same default steps through the `ffff490a` fixture and the current one. The output is `identical: True` for openai, anthropic and gemini, and the counter advances the same way (`next id old/new: 8 8`). Only the boundary test passes `call_id` (`:499`, `:505`), and no module outside the pack imports the fixture.

FIX-BY-FIX JUDGEMENT
- **R-20 @ce8053ed — CONFIRMED FIXED.**
    - `RR1MUT=estimate_content_only` gives `3 failed, 277 passed`.
    - Two of the three failures are the R-20 tests, each failing on the estimate path:
        - Gemini growth fails `:378` with `summary side calls followed loop calls [4]`. Content-only growth never reaches the target after the first compaction.
        - Gemini with no usage fails `:416` with `[]`. The content-only fallback never reaches the trigger.
    - Both tests first pass their shape preconditions (`:376`/`:414`, `parts` with no `content`) and, for the no-usage test, the zero-usage precondition (`:415`).
    - The third failure is incidental; see R-C2.
- **R-21 @b4dc91d0 — CONFIRMED FIXED.**
    - `snapshot_only_auto` gives `1 failed, 279 passed`, failing the restart test at `:461` (`[2, 3]`).
    - `growth_strict_gt` gives `1 failed, 279 passed`, failing the exact-target row at `:516` (`[2]`).
    - Each fails on its own test, and its own test only.
- **R-22 @6bb264c8 — CONFIRMED FIXED.**
    - §8.5's constants block (`spec.md:456-478`) matches `vidbyte/lib/constants/agent_swarm.py` line for line: 21 of 21 lines, with no constant in the code only. That includes the four R-15 constants at `:61-67`.
    - The private list at `spec.md:580-582` names every private method of `runtime.py` (`:150`–`:503`). `_refuse` is at `:395`, `_changed_path` (an instance method) at `:463`, and `_command_failure` (static) at `:473-474`.
    - §8.4 (`:415`) and §9.1 (`:745`) match `member.py:75-77` and `:117-121`. The snapshot is taken after the rewrite, only when a summary call was made, and it is `None` before the first compaction.
    - D-10 (`:375`) and the AC-17 Given (`:264`) match `member.py:98-103`: `grown = _compacted_estimate is None or estimate >= _compacted_estimate + target`, and AUTO needs `measured >= trigger_at and grown`.
    - The new AC-17 branch has no Proof entry; see R-C3.

THE FIVE NEW CASES: does each pin the spec rule, and would it fail for the right reason?
1. `test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target` (`:347`)
    - **Pins the rule.** It encodes INV-32's growth and INV-33's whole-message count with large margins (above). It also pins INV-36 (`:382`, no trim): the history's estimate peaks at 53,032 tokens, against the 90,000-token trim.
    - **Right reason.** It fails at `:378` under `estimate_content_only`, `growth_by_measured`, `hyst_off`, `snapshot_before`, `snapshot_never` and `growth_from_trigger`.
2. `test_a_gemini_member_whose_provider_reports_no_usage_compacts_when_its_estimate_reaches_the_trigger` (`:387`)
    - **Pins the rule.** `input_tokens == _estimate(checked)` (`:421`) uses the measure that spec §8.5 itself pins (`measured = _measured_context(estimate)`, `estimate = _estimate(messages)`). It is not tied to `str()`: it passes under `est_json` and `est_leaves`. `:424` also bounds the estimate from below by the reads' own characters.
    - **Right reason.** It fails at `:416` under `estimate_content_only` and `fallback_zero`.
3. `test_a_compact_request_restarts_the_growth_an_automatic_compaction_waits_for` (`:429`)
    - **Pins the rule.** INV-32 says "since this member's last compaction", whichever trigger made it. `:460` proves that the trigger was reported on loop calls 3 and 4, so only the growth rule can hold iteration 3 back. The margins are 12,000 and 3,000 tokens.
    - **Right reason.** It fails at `:461` under `snapshot_only_auto`.
4. and 5. `test_a_repeat_automatic_compaction_is_due_at_exactly_the_target_of_growth_and_not_one_token_below` (`:471`, two rows)
    - **Measuring with `AgentSwarmMemberRuntime._estimate` is not tighter than the spec.**
        - §8.5 names `static _estimate(messages) -> int` as the growth measure. INV-33 leaves its text open, so an exact boundary can only be stated relative to that function.
        - The sizing itself uses only the four-characters-per-token rule: 4 more characters of file content add exactly 1 token, because `TokenEstimate.count` is `ceil(len/4)`.
        - The growth boundary (`:515`, `:516`) passes under `est_json`, `est_leaves`, `both_json`, `keep_json` and `keep_leaves`.
    - **The self-check is sound.**
        - `:515` is a precondition on the test's own sizing, not on the code. Under a mutated `_estimate`, it moves with the mutant.
        - The two rows produce opposite outcomes, so together they prove the code's threshold, as the test measures it, is exactly the target.
        - The spy confirms the member's own growth figures of `27000` and `26999`.
    - **Right reason.** `growth_strict_gt` fails at `:516` on the exact row, and `growth_minus_one` fails at `:516` on the one-below row.
    - **One exception.** `:519` also asserts `messages_dropped == 3`, which is stricter than INV-33 (R-C2).

REGRESSIONS INTRODUCED BY THE FIXES: none.
- The pack gives `280 passed`, in order, reversed, and with the five cases alone.
- Lint gives `SDK-LINT: PASS`.
- The product is unchanged since `04cf9caa`, and the lint baseline is untouched.
- The only lines removed under `tests/` are four rewritten header lines, the old `tool_call` signature, and three call-id expressions. No assertion was removed, and nothing was skipped or suppressed.
- Every earlier mutant keeps its verdict: 30 of the 31 are killed, and `keep_last_zero` is still the equivalent survivor. Each mutant's failure count is the same or higher than in round 1.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Minor] [spec-ID → test trace] `tests/features/agent_swarm/test_agent_swarm_compaction.py:429-465` (restart test) — no test pins where the growth count restarts: right after the rewrite, before that iteration's mail (§9.1 r6; §8.5 pseudocode `:694` before `:697`). A snapshot taken after the mail passes all 280 cases.
  Evidence:
    - `RR2MUT=snapshot_after_mail PYTHONPATH="<WT>;RR2/plug" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p rr2mut` gives `280 passed in 7.23s`. This mutant moves `self._compacted_estimate = self._estimate(messages)` (`member.py:121`) to after `collect_messages` has appended the inbox.
    - `python RR2/probe_snapshot_mail.py` uses the scripted runner. builder reports the trigger on every call and messages itself a 60,000-character note in the response that compacts:
        - shipped: `side calls after loop calls [2, 3]; compactions [('auto', 72000, 2), ('auto', 72000, 5)]`
        - mutant: `side calls after loop calls [2, 4]; compactions [('auto', 72000, 2), ('auto', 72000, 7)]`
  Failure: Take a member whose compaction iteration also delivers mail. The mutant counts that mail as already compacted, so the member's next automatic compaction waits for another full target of growth beyond the mail. INV-32 counts growth "since this member's last compaction", and §9.1 sets the snapshot "right after" it. The more mail an inbox delivers in that iteration, the longer the 90,000-token trim carries the history alone (INV-36).
  Smallest fix: S2 adds one row or test: a self-message (or a peer's message) delivered in the iteration that compacts, then one read below the target, asserting summary calls `[2, 3]`. The probe is the scenario. No product change.
  Spec IDs: INV-32, §9.1, INV-36

R-C2 [Minor] [spec-ID → test trace] `tests/features/agent_swarm/test_agent_swarm_compaction.py:519` — the exact-target row also pins that the keep count measures the new history no larger than the growth check does. INV-33 does not require that. So the row fails one conformant pairing of estimates, and it counts toward `estimate_content_only`'s kills for an incidental reason.
  Evidence:
    - `RR2MUT=est_leaves` makes the growth check count every string value of each message, with the keep count unchanged at `str(message)`. Both are whole-message counts under INV-33. Result: `1 failed, 279 passed`, `FAILED …[exactly-the-target]` at `:519`: `assert [(…'', 72000, 5)] == [(…'', 72000, 3)]`. `:515` (growth 27,000) and `:516` (`[2, 4]`) pass.
    - Under `RR1MUT=estimate_content_only`, the third failure is this same line: `At index 1 diff: (…AUTO…, '', 72000, 5) != (…, 3)`.
    - The mechanism:
        - No mail arrives, so the growth since the first compaction is exactly the growA and growB pairs.
        - "Grown by exactly the target" therefore puts those four messages exactly at the keep target. The spy shows `growth=27000`.
        - `_keep_last` keeps all four only if it measures them at most one call message larger than the growth check does.
    - The variants that pass: S2's (`S2V_EST=json|list|leaves`, each `280 passed`) either swap both estimates or make the growth measure the larger one. Mine (`keep_json`, `keep_leaves`, `est_json`, `both_json`) also each give `280 passed`.
  Failure:
    - An implementation whose growth estimate counts message text without keys, such as the engine's per-message text (the unit the trim counts in), while its keep count stays `str(message)` turns this row red, although INV-32 and INV-33 both hold.
    - test-plan.md:161 claims "So they pin INV-32 and INV-33, not the `str(message)` text", which holds only when the two estimates measure alike.
    - review.md's R-20 status line counts "3 failed", and one of the three is this incidental failure.
  Smallest fix: For the exact row's second compaction, compare only trigger, text and `input_tokens` (for example `[c[:3] for c in compactions]` for that row), or accept `messages_dropped in (3, 5)`. Add "when the growth check and the keep count measure messages alike" to test-plan.md:161. Test and doc only.
  Spec IDs: INV-33, INV-32

R-C3 [Minor] [spec drift] `docs/spec/agent-swarm-v2/spec.md:264` (AC-17 Proof) and `docs/spec/agent-swarm-v2/test-plan.md:31` — r6 added a growth branch to the AC-17 Given ("or target-sized growth since the last one"), but the Proof cell still names only tests with no earlier compaction
  Evidence:
    - `spec.md:264` Proof lists `test_a_measured_context_at_the_trigger_compacts_automatically_and_one_below_does_not` (2 rows) and `test_a_pending_request_and_the_trigger_in_one_iteration_compact_once`. `test-plan.md:31` adds the Anthropic test.
    - The tests that prove the new branch are mapped only under the INV-32 rows (`test-plan.md:86-90`):
        - `test_automatic_compaction_waits_for_a_target_of_new_history_and_a_compact_request_does_not` (`:294`)
        - `test_a_gemini_member_compacts_again_each_time_its_parts_history_grows_by_the_target` (`:347`)
        - `test_a_repeat_automatic_compaction_is_due_at_exactly_the_target_of_growth_and_not_one_token_below` (`:471`)
  Failure: A reader, or S6 when it writes the PR body from the AC table, finds no proof for the clause r6 added.
  Smallest fix: Add those three test names to the AC-17 Proof cell and to test-plan.md:31.
  Spec IDs: AC-17, INV-32

VERIFIED CLAIMS:
- **review.md R-20, "`estimate_content_only` now 3 failed, 277 passed":** HELD. Two of the failures are for the right reason and one is incidental (R-C2).
- **review.md R-21, "`snapshot_only_auto` and `growth_strict_gt` each 1 failed, 279 passed":** HELD. Each fails its own test.
- **Briefing, "no product file has changed since `04cf9caa`":** HELD. The `vidbyte/` diff is empty, and so is the diff outside `docs/` and `tests/`.
- **Briefing, "pack `280 passed`, `SDK-LINT: PASS`":** HELD. `--co` collects 280 cases. I did not run `run_ci.py` (the briefing forbids it).
- **Briefing, "remote CI and Static policy dispatched on `35b05f34`":** HELD. `gh run list` shows CI 39698849230 and Static policy 39698851420, both `success` at headSha `35b05f340c2d…`, and `origin/feat/agent-swarm` is `35b05f34`.
- **The fixture header and the S2 report, "default `call_id` keeps the session-wide counter":** HELD (probe above).
- **test-plan.md:159, "an opposite off-by-one … fails the `one-below` row":** HELD (`growth_minus_one`).
- **test-plan.md:161 / S2 report, "pass under three other whole-message estimates":** HELD for S2's three variants. The conclusion drawn from it is too broad (R-C2).
- **test-plan.md:88, "or a fallback that measures nothing":** HELD (`fallback_zero` fails `:416`).
- **AC-1:** HELD. The 16 non-blank lines of §4 match `test_agent_swarm_acceptance.py` from line 68 on, identical after dedent, and the test gives `1 passed`. Neither §4 nor the acceptance module changed since round 1.
- **§14 "Never":** HELD. The `lint/` diff over `39ce8b20...35b05f34` is empty, no `noqa`, `type: ignore`, `skip`, `xfail` or `nosemgrep` was added, and no test was weakened.
- **Not raised:**
    - D-10 says "grown by the target" without "at least". It cites INV-32, which says "at least", and the R-21 rows pin that.
    - §12.3 row 33's helper list omits `_estimate`, but it defers to the §8.5 pseudocode, which has it.
    - §8.5 marks only `_command_failure` as static, although `_budget_total`, `_failure_text` and `_early_exit_text` are static too (`runtime.py:485-503`). This predates r6 and is harmless.

COMMANDS RUN:
- **Git diffs:**
    - `git -C <WT> diff --stat 04cf9caa..35b05f34 -- vidbyte/` → empty.
    - `git -C <WT> diff --stat 04cf9caa..35b05f34 -- . ':(exclude)docs' ':(exclude)tests'` → empty.
    - `git -C <WT> diff 39ce8b20...35b05f34 -- lint/ | wc -l` → `0`.
    - `git -C <WT> diff ffff490a..35b05f34 -- tests/ | grep '^-[^-]'` → 13 lines: headers, the `tool_call` signature, and the three id expressions.
- **The pack:**
    - `python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` → `280 passed in 7.03s`.
    - With the module order reversed → `280 passed in 7.35s`.
    - The five cases alone (`-k …`) → `5 passed, 16 deselected in 0.83s`.
- **`RR1MUT=<id> PYTHONPATH="<WT>;<SCRATCH>/rereview1/mut" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p rr1mut`:**
    - `estimate_content_only` → `3 failed, 277 passed`.
    - `snapshot_only_auto` and `growth_strict_gt` → `1 failed, 279 passed` each.
    - `hyst_off`, `snapshot_before`, `snapshot_never`, `growth_from_trigger` and `keep_content_only` → `4 failed, 276 passed` each.
    - `hyst_applies_to_tool`, `trim_after_stop` and `timeout_not_classified` → `1 failed, 279 passed` each.
    - `trim_skips_always` → `3 failed, 277 passed`.
    - The three `end_reason_*` mutants with `-x` → each fails its round-1 test.
- **`S4MUT=<id> PYTHONPATH="<WT>;<SCRATCH>/s4eng/mut" … -p s4mut`:**
    - `compact_while_stopping`, `self_writer_as_peer` and `side_call_tokens_not_added` → `1 failed, 279 passed` each, on their R-7 tests.
    - `trunc_at_cap`, `budget_ignores_total`, `no_post_abort` and `measure_input_not_prompt` → 1 failed each.
    - `cancel_state_swap`, `fail_keeps_inbox` and `stopped_recipient_queued` → 2 failed each.
    - `budget_gt` and `wake_refused_not_recorded_at_turn_end` → 3 failed each.
    - `trim_records_unchanged` → 4 failed.
    - `dropped_no_plus_one` → 13 failed.
    - `side_call_not_budgeted` → 17 failed.
    - `keep_last_zero` → `280 passed` (equivalent).
- **`RR2MUT=<id> PYTHONPATH="<WT>;RR2/plug" … -p rr2mut`:**
    - `keep_json`, `est_json`, `both_json`, `keep_leaves` and `keep_ge` → `280 passed` each.
    - `est_leaves` → `1 failed` at `:519` (R-C2).
    - `growth_minus_one` → `1 failed` at `:516`, on the one-below row.
    - `fallback_zero` → `1 failed` at `:416`.
    - `growth_by_measured` → `4 failed`, at `:333`, `:378`, `:461` and `:516`.
    - `snapshot_after_mail` → `280 passed` (R-C1).
- `S2V_EST=json|list|leaves PYTHONPATH="<WT>;<SCRATCH>/s2amend2/plug" … -p s2v_alt_estimate` → `280 passed` for each.
- `RR2SPY_FILTER=compaction … -p rr2spy -s -k <five cases>` → the per-iteration estimates quoted above, including `iter 4: … growth=27000` and `growth=26999`.
- `python RR2/probe_fixture_default.py` → `openai/anthropic/gemini identical: True | next id old/new: 8 8`, `fixed id: call-X | counter after fixed: 1`.
- `[RR2MUT=snapshot_after_mail] python RR2/probe_snapshot_mail.py` → as quoted in R-C1.
- `python lint/run.py` → exit 0, `S064 RATCHETED: 4 known finding(s)…`, `SDK-LINT: PASS`, with no line naming agent_swarm.
- **Spec checks:**
    - A constants-block comparison script → 21 of 21 `MATCH`, `code-only: []`.
    - The §4 snippet comparison → `start 68 identical after dedent: True`.
    - `pytest …::test_the_section_4_snippet_runs_as_written` → `1 passed`.
- `gh run list --branch feat/agent-swarm --limit 4` → CI and Static policy `success` on `35b05f34…`.

STATUS: DONE
STAGE: S4 reviewer (conformance)
REPORT: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2/docs/spec/agent-swarm-v2/reports/S5-rereview-2.md
PRODUCED: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2/docs/spec/agent-swarm-v2/reports/S5-rereview-2.md
HEAD: no commits
SUMMARY (≤ 10 lines): VERDICT SOUND. R-20, R-21 and R-22 are CONFIRMED FIXED, with no regression: pack 280 passed (also alone and in reversed order), lint PASS, product unchanged, and every earlier mutant keeps its verdict. 0 Blocker, 0 Major, 3 Minor. Each of the five new cases kills its target mutant on its own side-call-schedule assertion, and they pin the rule rather than `str(message)`, with one exception (R-C2, the exact row's `messages_dropped == 3`). Most important: the growth count's restart point, right after the rewrite and before that iteration's mail, has no test. `snapshot_after_mail` passes all 280 cases, yet it delays the next compaction from iteration 3 to 4 in the probe.
NICHE FACTS FOR THE NEXT AGENT (≤ 8 bullets):
- My mutants: `RR2MUT=<id> PYTHONPATH="<WT>;<SCRATCH>/rereview2/plug" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider -p rr2mut`. R-C1 is `snapshot_after_mail`; R-C2 is `est_leaves`.
- R-C1 repro scenario: `<SCRATCH>/rereview2/probe_snapshot_mail.py` (builder messages itself in the response that compacts). It gives `[2, 3]` on shipped code and `[2, 4]` under the mutant.
- Spy on the member's own estimates: `-p rr2spy -s` with `RR2SPY_FILTER=<nodeid part>`. It prints per-iteration estimate, snapshot and growth.
- All three findings are tests or spec text only (S2 owns `tests/`, the orchestrator owns the spec). No product change is needed.
