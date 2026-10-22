# S5 repair, iteration 1: AgentSwarm v2 (PR #1174)

Branch `feat/agent-swarm` · start `21eb8164` (tests frozen at `791a8d56`) · end of fixes `6d604082` (pushed) · spec r4 · log: `verify-log.md`, iteration 1.

I fixed all 16 confirmed findings. Each is one commit, or one commit plus a README commit for R-6. Every local gate is green, apart from the three inherited `harness_threads` cases. `git diff 791a8d56..HEAD -- tests/` is empty, and so is `git diff 39ce8b20..HEAD -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/lib/dataclasses/validation.py` (NG-1). I edited no test, fixture, test-plan row, baseline or config.

## Gate matrix

| Gate | Command | Result | Final lines |
|---|---|---|---|
| pack | `PYTHONPATH=<WT> python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` | PASS | `275 passed in 7.09s` (was `4 failed, 271 passed`) |
| lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` · exit 0 |
| lint, all | `python lint/run.py --all --format json` | PASS | exit_code 0 · 90 rules: 47 CLEAN, 35 RATCHETED, 8 IMPROVED · 3,896 findings · 0 in the 8 files this run touched · 0 naming `agent_swarm` |
| A002 proof (R-4) | `python lint/run.py --rule A002 --all --format json` | PASS | swarm A002 entries `[]` · `found 562, baseline 703, verdict IMPROVED` (was 565 with the three swarm entries) |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at a319f44dfec4d2577e0707767bad87bbb7063fa8 (vidbyte-sdk 0.3.0, 650 exports).` |
| source stage | `PYTHONPATH=<WT> python scripts/run_ci.py --stage source` | inherited only | `SDK-LINT: PASS` · compileall and the three check scripts pass · `FAILED …test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `…test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` / `…test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` · `3 failed, 6518 passed, 16 skipped in 99.53s (0:01:39)` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep | 1.170.1 from `<scratchpad>/semgrep-venv/Scripts` first on PATH; `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Targets scanned: 996` · `Ran 1 rule on 996 files: 0 findings.` |
| remote CI | `gh workflow run ci.yml --ref feat/agent-swarm` → run 39689652565, headSha `6d604082c1c0…` | PASS | `success`: Source / Python 3.11 `6480 passed, 57 skipped in 119.02s (0:01:59)` · `CI passed.`; Source / Python 3.12 `SDK-LINT: PASS` · `6480 passed, 57 skipped, 19 warnings in 125.90s (0:02:05)` · `CI passed.`; Package `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote Static policy | `gh workflow run static-policy.yml --ref feat/agent-swarm` → run 39689655332, headSha `6d604082c1c0…` | PASS | `success`: `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 996 files: 0 findings.` |

The three source-stage failures are the inherited ones the briefing names, with the same assertions: `assert 148 == 120`, `Left contains 3 more items, first extra item: 'vidbyte/tools/README.md'`, and `At index 30 diff: 'AgentSwarm' != 'JevAgent'`. The field guide (`local-ci-verification.md`) documents them as branch-scoped or failing on main, and CI skips them on its shallow checkout. The pass count went from 6,511 to 6,518, which is the seven new S2 cases.

## Per finding

| ID | Commit | What changed | Evidence |
|---|---|---|---|
| R-1 | `8e71ec8c` | `_end_check` → pure `_end_reason() -> AgentSwarmStopReason \| None` (same three branches, `return` in place of `_stop`). The three callers (stray-cancel branch, `_run_member` tail, `end_turn` park) do `reason = self._end_reason()`, then `if reason is not None: self._stop(reason)`, with no `await` between. Header inventory and patterns updated. | `grep -n "_end_check\|_end_reason" runtime.py` shows no `_end_check`, and `_stop` is called only by `arun` and the three callers. The pack passes. The stop-machinery mutants are still killed (`fail_keeps_inbox` 2 failed, `stopped_recipient_queued` 2, `cancel_state_swap` 2, `wake_refused_not_recorded_at_turn_end` 3). S024 depth is 3 in the cancel branch (limit 3). |
| R-2 | `8e56aaea` | `_measured_context`'s fallback and `_keep_last` count `TokenEstimate.count(str(message))`, the whole message. | Both R-2 tests are green. `$V/v_keep_last_providers.py`: Gemini `compaction=[('auto', 72000, 2)] side_calls=1`, with OpenAI and Anthropic unchanged. `$V/v_write_heavy.py`: `[('auto', 72000, 8)] side_calls=1`. `$V/v_gemini_contents.py`: `problems: none`. |
| R-6 | `81b0672e` (+ `2567874f`, `6d604082` READMEs) | `_compacted_estimate` is set after every recorded compaction, automatic or requested. An automatic compaction also needs `estimate >= _compacted_estimate + compaction_target_tokens` (always true before the first), and a `compact` request never waits. A new static leaf `_estimate(messages)` feeds the fallback, the growth check and the snapshot, so `_measured_context` now takes `estimate: int`. | The R-6 test is green: side calls after loop calls `[4, 6, 10, 14]`. `S4V_ITERATIONS=24 python $V/v_hysteresis.py`: control measured inputs `[74428, 75025, 75027]`, unchanged. Summary calls 3 / 5 / 6 / 5 for the control, the 160k goal, the 220k goal and CJK, against 3 / 10 / 21 / 10 before. |
| R-9 | `79f3dbb8` | `AgentSwarmTrimMiddleware.before_model_call` returns `MiddlewareDecision.continue_()` before trimming once `stopping` is set, with `@intent no-trim-is-recorded-for-a-refused-call`. | The R-9 test is green. `$E/probe_trim_after_stop.py`: `13 swarm_stopping max_tokens`, `15 tool_called builder`, `16 agent_released builder`, with no `history_trimmed` after the stop (was `16 history_trimmed builder dropped=2`). The `trim_records_unchanged` mutant is still killed. |
| R-4 | `a12973e7` | `# @intent a-failed-summary-keeps-the-history` above the `try` in `_compact`, and `# @intent one-pending-compaction-per-agent` as the first body line of `request_compaction` and `take_compaction_request`. | A002 JSON: no entry names a swarm file. Found 565 → 562. |
| R-5 | `360ceab1` | The package README's Notes for agents gains the briefing's exact sentence. No retry was built (R-18). | — |
| R-7 | S2's `78b067d1` | No product change. | `compact_while_stopping` → `1 failed, 274 passed` (`test_a_compact_request_pending_at_the_stop_makes_no_summary_call_and_records_no_compaction`). `self_writer_as_peer` → `1 failed, 274 passed` (`test_one_agent_writing_one_file_twice_records_file_changed_with_no_peer_both_times`). `side_call_tokens_not_added` → `1 failed, 274 passed` (`test_the_summary_call_tokens_are_added_to_the_members_tokens_used`). All 16 S4 mutants: 15 killed, `keep_last_zero` equivalent (R-12). |
| R-8 | `19087212` | The refusal's details name the part that is missing, the swarm runtime first: `{"received_summarizer": "NoneType"}` when only the summarizer is absent. **This is a variant of the review's fix (see below).** | Probe: `AgentSwarmMemberRuntime()` → `{'received_swarm_runtime': 'NoneType'}`. `(swarm_runtime=object())` → `{'received_summarizer': 'NoneType'}`. `(summarizer=object())` → `{'received_swarm_runtime': 'NoneType'}`. The pack passes. |
| R-10 | `d01acf5e` | The prompts README now says: `message_sent` and `message_stopped_recipient` are the success replies, and `message_blank_text` and `message_unknown_recipient` the two refusals. The paragraph is rewrapped. | The four leaf files exist under `vidbyte/prompts/prompts/agent_swarm/`. |
| R-11 | `11a3847a` | The package README note adds "(or `agent_failed`, when the call is the compaction summary's)" and the reason. | `<scratchpad>/s5/probe_side_call_bug.py`, a raising `record_model_call` on the summary call only, gives `10 agent_failed RuntimeError: recording bug on the summary call`. |
| R-12 | S2's `afa17494` | No change. | test-plan.md EC-27 row carries the corrected reason. |
| R-13 | `001e2c72` | runtime.py header: the member runtime "reads stopping before it compacts, and calls record_model_call and record_model_error for its summary call". Records header: a new event field goes in `_COUNT_FIELDS`, `_TEXT_FIELDS` or `_ENUM_FIELDS`, from which `_OPTIONAL_FIELDS` is derived. | — |
| R-14 | `79f378cf` (orchestrator) | No change. | Spec §17 deviation 10 and D-14's trigger. |
| R-15 | `ea6e1b91` | New constants `AGENT_SWARM_FILE_TOOL_PATH_ARGUMENTS` (typed `Mapping[str, str]`, the `CODEX_FAILURE_CLASSIFICATION` pattern), `AGENT_SWARM_SHELL_TOOL_NAME`, `AGENT_SWARM_SHELL_TIME_LIMIT_ERROR` and `AGENT_SWARM_STOPPING_REASON` in `vidbyte/lib/constants/agent_swarm.py`, with the header updated. All four moved: both callers sit above lib, so no layer issue arose. | The pack passes. `ruff check vidbyte --config lint/ruff.toml --select I001` shows nothing for swarm files. |
| R-16 | `7e70db8a` | `_changed_path(call, result) -> str \| None` (instance, needs the root) and `_command_failure(call, result) -> str \| None` (static) are restored in `runtime.py`. `record_tool_outcome` calls each once, and neither calls another helper. The mutant anchors (`if omitted > 0:`, `peer=previous if previous != name else ""`) stay in `record_tool_outcome`. | The pack passes, and its 24 `file_changed`/`command_failed` assertions are unchanged. `self_writer_as_peer` and `trunc_at_cap` are still killed. |
| R-3 | `6455f9e9` | 52 comment lines were refilled at 72 columns, counting the indent: runtime 43, member 4, observer 5. The `@intent` line stays first, and each former one-line comment is its own paragraph. To fit 500, this iteration's own R-1 and R-4 comments are one line shorter, and `_command_failure` returns the exit-code text in one expression. | `awk 'length($0) > 72' <f> \| grep -cE '^\s*#'` gives 0 for runtime, member, observer, compaction.py, the toolset and every other swarm module. Lines after the header: runtime.py **498** (limit 500), member.py 258, observer 96, compaction.py 79, toolset 73, constants 79. A tokenize diff against the pre-rewrap commit shows identical comment words and code tokens for member and observer. For runtime, the only differences are the intended R-1, R-4 and `_command_failure` edits. |

## Proposed test change (optional; not needed for green)

R-8: the review's literal fix adds `received_summarizer` to every refusal. That would break `tests/features/agent_swarm/test_agent_swarm_contract.py::test_runtime_type_refuses_outside_a_swarm_without_calling_a_model` (line 330, `assert refused.value.details == {"received_swarm_runtime": "NoneType"}`). The test cites §13, r5 AC-12 kept, and no spec ID pins the details shape. So the test does not contradict the spec, and I did not report BLOCKED. I built the variant above instead, which keeps the test green and names the missing summarizer. If the orchestrator prefers the review's both-keys shape, the change would be:
- before: `assert refused.value.details == {"received_swarm_runtime": "NoneType"}`
- after: `assert refused.value.details == {"received_swarm_runtime": "NoneType", "received_summarizer": "NoneType"}`

Then `details` becomes `{"received_swarm_runtime": type(swarm_runtime).__name__, "received_summarizer": type(summarizer).__name__}`.

## Findings I believe are wrong

None. R-8 is right in substance, but its smallest fix conflicts with a frozen test. I resolved it differently, as explained above.

## Observation O-1 (new; needs a spec decision, not built)

r4's hysteresis (INV-32) measures growth in the four-characters-per-token estimate. For text the estimate undercounts, the measured context then climbs past the model window before the next automatic compaction. The source is `S4V_ITERATIONS=24 python $V/v_hysteresis.py`; the "before" numbers come from the same probe against an archive of `8e56aaea` (R-2 only), `<scratchpad>/s5/v_hysteresis_r2.py`.

| Case | Peak measured before R-6 | Peak measured after R-6 | Summary calls before → after |
|---|---|---|---|
| CJK-like (1.5 chars/token), short goal | 88,668 | **129,015** | 10 → 5 |
| 220,000-char English goal | 84,612 | 107,307 | 21 → 6 |
| 160,000-char English goal | 77,177 | 92,307 | 10 → 5 |
| control | 75,027 | 75,027 | 3 → 3 |

The pattern, and why it matters for a day-long 500-agent run on a 128k model, is this. The compaction target (27,000 estimated tokens) is already about 72,000 real tokens for CJK text, so a freshly compacted CJK history sits at the trigger. Hysteresis then lets it grow another 108,000 characters (about 72,000 real tokens) before it compacts again. A call near 129,000 tokens fails at the provider, and with no retry (R-5) that fails the member. The trim at 90,000 estimated tokens (360,000 characters) never caught CJK overflow either, so before R-6 the trigger was the only guard. The options for the spec author are:
- (a) Accept it, and document the limit next to the constants header's "not a real tokenizer count".
- (b) Keep r4's rule, but make compaction due regardless of growth once the measured context reaches a ceiling above the trigger. That is a new constant, an INV-32 change and a test change. S2's R-6 test pins the opposite: its scenario measures up to 126,867 tokens and expects no compaction at calls of 104,026 to 119,302 tokens (`<scratchpad>/s5/probe_r6_measured.py` prints every loop call: `[81332, 88896, 96461, 104026, 104107, 111672, 104172, 111737, 119302, 126867, 104109, 111675, 119241, 126807, 104110]`). Any useful ceiling below the window therefore also changes that test's expected `[4, 6, 10, 14]`.
- (c) Measure growth in reported tokens, against the first report after each compaction. That gives `[4, 6, 11, …]` on S2's test, so the test would change too.

I recommend (b), with a ceiling of about 110,000 measured tokens against a 128,000 window, plus S2 re-pinning the R-6 test. It keeps r4's cost bound for English, and it caps the failure mode. It flips to (a) if AgentSwarm users can be assumed to send English-like text, or if the member model's window is well above 128,000. Both (b) and (c) contradict the frozen test and the r4 text, so I built neither.

## Spec text the orchestrator may want to update (I edited no spec)

- §8.5 runtime private list (spec.md:576) still says `_end_check`; it is now `_end_reason`.
- §8.5 member leaf helpers say `_measured_context(messages) -> int`. They are now `_estimate(messages) -> int` (static) and `_measured_context(estimate) -> int`.
- §17 deviation 7 says "S5 restores the two classifiers". They are restored in `runtime.py` as `_changed_path` and `_command_failure`, not on `AgentSwarmTools`.
- R-8: the details name the first missing part (above).

## Notes

- I did not tighten the A002 baseline (703; found 562). It is a shared ratchet, and the briefing did not ask for it.
- Cost of R-6's per-iteration estimate: `str()` of the whole history every tool iteration, measured at 0.63 ms for 542,546 characters. That is negligible against a model call, even for 500 members on one loop.
- Probes written this run are under `<scratchpad>/s5/`: `rewrap.py`, `comment_words.py`, `probe_side_call_bug.py`, `v_hysteresis_r2.py` and the `r2tree/` archive. None calls a real provider.

## What remains open

- R-17, R-18 and R-19: `[scope-adding]` follow-ups for the user, status `open · follow-up`, not built.
- O-1: a spec decision.
- Nothing else. Both remote runs are green on `6d604082`. This docs-only commit is re-dispatched, and its run ids are in the STATUS block.
