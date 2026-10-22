# Verification log: AgentSwarm v2 (PR #1174)

Gate set (from context/code-map.md §1 and the S5 briefing), in CI order, every command from the worktree root with `PYTHONPATH=<worktree>` unless noted:
1. Pack: `python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` (local).
2. Lint: `python lint/run.py` (last line `SDK-LINT: PASS`), plus `python lint/run.py --all --format json` with no finding in a touched file (the text output hides findings of IMPROVED rules) (local; also inside the source stage).
3. Public API: `python scripts/generate-sdk-public-api.py --check` (local).
4. Source stage: `python scripts/run_ci.py --stage source` (local; the three `harness_threads` surface cases are inherited and CI skips them on its shallow checkout).
5. Package stage: `python scripts/run_ci.py --stage package` with no `PYTHONPATH` (local).
6. Semgrep: `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` and `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, semgrep 1.170.1 from `<scratchpad>/semgrep-venv` first on `PATH`, tracked files only (local; the same steps are `static-policy.yml`).
7. Remote: `gh workflow run ci.yml --ref feat/agent-swarm` and `gh workflow run static-policy.yml --ref feat/agent-swarm`, each run's `headSha` equal to the pushed HEAD (remote only; this repo runs no checks on PRs by itself, so `gh pr checks` stays empty).

## Iteration 1 — 2026-10-21 18:55 — agent report: reports/S5-repair-1.md

**Defects in:** Blockers R-1, R-2, R-3; Majors R-4, R-5, R-6, R-7; Minors R-8 to R-16 (R-12 and R-14 already fixed upstream). Red gate: the pack, `4 failed, 271 passed` at `791a8d56` (R-2 ×2, R-6, R-9). Every other gate was green at `582c414d`.

**Hypotheses and attempts:**
- R-1 `_end_check` → pure `_end_reason() -> AgentSwarmStopReason | None`; each of the three callers does `reason = self._end_reason()` then `if reason is not None: self._stop(reason)` with no `await` between (INV-12). S024 depth stays at 3 in the stray-cancel branch. The stop-machinery mutants (`fail_keeps_inbox`, `stopped_recipient_queued`, `cancel_state_swap`, `wake_refused_not_recorded_at_turn_end`) are still killed.
- R-2 three candidate estimates. (a) `json.dumps(message)`: rejected, because `ensure_ascii` writes each CJK character as six characters. (b) The engine's `_message_text`: rejected, because it is private to `strategies.py` and needs `to_context_messages` first; for a `None` content the engine itself falls back to `str(message)` (`engine.py:_provider_message_content`). (c) `TokenEstimate.count(str(message))`: chosen. Both R-2 tests turn green, and the verifier's real-loop probes give the expected results: Gemini `compaction=[('auto', 72000, 2)] side_calls=1`, write-heavy `[('auto', 72000, 8)] side_calls=1`, and the compacted Gemini request is valid (`problems: none`).
- R-6 target-sized growth per r4 INV-32, with the snapshot taken after every recorded compaction (automatic or requested) and never after a failed or empty one. One static leaf, `_estimate(messages)`, feeds the measured-context fallback, the growth check and the snapshot, so `_measured_context` now takes the estimate (a private signature change from §8.5). Rejected without building: the trigger − target growth rule (S2's test rejects it with `[4, 6, 12]`), and growth measured in reported tokens (from the test's own trace it would give `[4, 6, 11, …]`; reasoned, not run). Control `S4V_ITERATIONS=24 python $V/v_hysteresis.py`: measured inputs `[74428, 75025, 75027]`, unchanged, and summary calls 3/5/6/5 (the verifier's fixed numbers).
- R-6 side effect found (observation O-1, not a finding). For CJK-like text at 1.5 characters per token, the same probe peaks at a measured 129,015 tokens with hysteresis, against 88,668 without it (R-2-only tree). That is over a 128,000-token window. The cause is that r4 counts growth in the four-character estimate, which undercounts that text by about 2.7×. A fix needs a spec decision, so I built none; options are in the report.
- R-8 literal fix (always add `received_summarizer`) conflicts with `test_agent_swarm_contract.py:330`, which pins `details == {"received_swarm_runtime": "NoneType"}` for a plain BaseAgent. Built instead: the details name the first missing part. A runtime given a swarm but no summarizer now reports `{"received_summarizer": "NoneType"}`, and the pinned case is unchanged. The test stays green, and the finding's case is named.
- R-9 skip the trim once `stopping` (not trim-silently); probe `$E/probe_trim_after_stop.py` now shows no `history_trimmed` after `swarm_stopping`.
- R-3, first pass: a pure rewrap (greedy fill at 72 columns, no one-word last lines, the `@intent` line first, each former one-line comment its own paragraph; script `<scratchpad>/s5/rewrap.py`, which asserts that each block keeps its words) put `runtime.py` at 503 lines after its header, over its 500. The fix was to shorten only this iteration's own new comments (R-1, R-4) and return `_command_failure`'s exit-code text in one expression. That gives 498. An independent tokenize diff (`<scratchpad>/s5/comment_words.py`) shows every pre-existing comment word unchanged. Not taken: moving the R-16 classifiers onto `AgentSwarmTools`, which would free about 20 lines but add public static methods to an exported class.
- R-7: `S4MUT=<id> … -p s4mut`. `compact_while_stopping`, `self_writer_as_peer` and `side_call_tokens_not_added` each give `1 failed, 274 passed`, and each kills its own test. All 16 S4 mutants were re-run: 15 are killed, and `keep_last_zero` is the documented equivalent mutant.

**Changes:** `8e71ec8c` R-1 · `8e56aaea` R-2 · `81b0672e` R-6 · `79f3dbb8` R-9 · `a12973e7` R-4 · `360ceab1` R-5 · `2567874f` R-6 README · `19087212` R-8 · `d01acf5e` R-10 · `11a3847a` R-11 · `001e2c72` R-13 · `ea6e1b91` R-15 · `7e70db8a` R-16 · `6455f9e9` R-3 · `6d604082` R-6 agents README. Already fixed upstream: R-7 `78b067d1`, R-12 `afa17494`, R-14 `79f378cf`.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (pack) | `python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` | PASS (275) | `275 passed in 7.09s` |
| lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s)…` · `SDK-LINT: PASS` · exit 0 |
| lint, all findings | `python lint/run.py --all --format json` | PASS | exit_code 0; 90 rules (47 CLEAN, 35 RATCHETED, 8 IMPROVED); 3,896 findings, 0 in the 8 touched files, 0 naming `agent_swarm`; A002 562 (was 565) |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at a319f44d… (vidbyte-sdk 0.3.0, 650 exports).` |
| source stage | `python scripts/run_ci.py --stage source` | inherited 3 only | `SDK-LINT: PASS` … `3 failed, 6518 passed, 16 skipped in 99.53s` · `CI failed: Command failed with exit code 1: … -m pytest`. The three failures are the `harness_threads` surface cases with the briefing's exact assertions: `assert 148 == 120`, `Left contains 3 more items, first extra item: 'vidbyte/tools/README.md'`, and `At index 30 diff: 'AgentSwarm' != 'JevAgent'` |
| package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep | `semgrep --test …` / `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 996 files: 0 findings.` |
| remote checks | `gh workflow run ci.yml` / `static-policy.yml` on `6d604082` | PASS 2/2 (headSha `6d604082c1c0…` on both) | CI 39689652565 `success`: Source 3.11 `6480 passed, 57 skipped in 119.02s` · `CI passed.`; Source 3.12 `SDK-LINT: PASS` · `6480 passed, 57 skipped, 19 warnings in 125.90s` · `CI passed.`; Package `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` · Static policy 39689655332 `success`: `1/1: ✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 996 files: 0 findings.` |

**Still open:** R-17, R-18 and R-19 (`[scope-adding]` follow-ups for the user, not built). Observation O-1, the CJK context overflow from r4's estimate-based hysteresis, needs a spec decision. Spec wording the orchestrator may want to record: §8.5 still names `_end_check` and `_measured_context(messages)`.

## Iteration 2 — 2026-10-21 — tests only (S2 amendment round 2) after post-repair re-review 1
**Defects in:** the re-review (reports/S5-rereview-1.md) confirmed R-1..R-16 FIXED and found three surviving mutants. The orchestrator re-ran them itself: `estimate_content_only`, `snapshot_only_auto`, and `growth_strict_gt` each gave `275 passed`, while the control `keep_content_only` gave `2 failed, 273 passed`. Logged as R-20 (Major), R-21 (Minor), and R-22 (Minor, spec drift) in review.md.

**What was done:**
- **No product change** (`git diff 04cf9caa..HEAD -- vidbyte/` is empty).
- **R-22:** fixed in spec r6, `6bb264c8` (orchestrator).
- **R-20, R-21:** S2, the test owner, added 5 cases. `ce8053ed` is R-20: two Gemini tests, growth recompaction and the no-usage fallback. `b4dc91d0` is R-21: a compact request restarts the growth count, plus an exact-target vs one-below boundary test. The fixture's `tool_call` gained an optional `call_id`; its default is unchanged.

**Hypotheses:** none needed. The defects were missing tests, not wrong code. S2 checked the five cases under three other whole-message estimates (JSON per message, whole-list JSON, string values only), and all three pass, so the cases pin INV-33's rule, not the `str(message)` text.

**Gate matrix (orchestrator runs at b1ecb95a):**
- Pack: `280 passed`.
- Mutants:
  - `estimate_content_only`: `3 failed, 277 passed`.
  - `snapshot_only_auto`: `1 failed, 279 passed`.
  - `growth_strict_gt`: `1 failed, 279 passed`.
  - S2 ran all 31 mutants before and after: kills went from 27 to 30, and the only survivor is `keep_last_zero` (equivalent).
- Lint: `SDK-LINT: PASS`.
- Source stage: `3 failed, 6523 passed, 16 skipped`. The 3 are the inherited `harness_threads` cases (`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`).
- Public API `--check`, package stage, and semgrep: their inputs (`vidbyte/`, `pyproject.toml`) are unchanged since 04cf9caa, where all three were green. Remote CI and Static policy re-run them on the pushed head.

**Still open:** R-17, R-18, R-19 (`[scope-adding]`, Q-6..Q-8), and A-12 / Q-9 (limitation).
