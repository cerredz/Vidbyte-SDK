# Verification log: An optional USD spend cap that every agent's own loop enforces

Gate set (from context/code-map.md §1, plus the commands the S5 briefing names). Run every command from the worktree root. Use `py -3.11`, and set `PYTHONPATH` inline only, never exported.
- **Pack plus codex (local):** `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap tests/test_codex_output_contracts.py`
- **Area suite (local):** the pack plus the briefing's list (`tests/features/sdk_loop_settings`, `sdk_model_usage`, `test_agent_runtime.py`, `test_session_failures.py`, `test_fork_tool.py`, `test_jev_usage_ledger.py`, `test_algorithms_honor_middleware_abort.py`, `tests/multi_agent`, `test_queued_prompt_usage.py`, `tests/features/infinite_memory_agent`, `test_reflexion_algorithm.py`, `test_independent_critic_algorithm.py`, `test_multi_provider_agentic_grader.py`) and `tests/test_jev*.py`.
- **Source stage (local; AGENTS.md's full gate):** `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`. It runs `lint/run.py`, compileall, three check scripts and the whole pytest suite.
- **Package stage (local):** `env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package`
- **Lint with no new finding against base (local):** `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py --format json`, diffed per rule against the same run at `22993b5f`. S009 alone: `--rule S009`, and `py -3.11 -m mypy --config-file lint/mypy.ini vidbyte`.
- **Semgrep (local; CI's Static policy):** `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` from the S3 semgrep venv (semgrep 1.170.1).
- **Public API contract (local):** `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check`
- **Remote checks (remote-only):** `gh pr checks`. SDK CI is dispatch-only, so the orchestrator dispatches it before merging, and S5 does not.

## Iteration 1 — 2026-10-20 12:22 UTC — agent report: reports/S5-repair-1.md

**Defects in:**
- review.md R-1 (Blocker), R-2, R-3, R-4 (Majors), and R-M1 to R-M5 (Minors).
- Spec r4 doc rows 13 (the delegated-path check in the Spend Cap section) and 17 (the A-8 sentence).
- Failing gates at `dbe84114`:
  - the two AC-33 cases, `assert (1, 1) == (0, 0)` at `test_loop_spend_cap_jev.py:319`;
  - mypy at 347 errors against base's 346.

**Hypotheses and attempts:**
- **R-1.** One hypothesis, and it held on the first try: row 28's check in `JevRuntime._delegate`, after the `begin_delegated`/`require_accounted()` block and before `specialist.agent.arun`.
  - The AC-33 cases went green with the test unedited (`9 passed` in the Jev file; pack `188 passed`).
  - `_delegate` is at C901 3.
  - Row 28's alternatives were not tried, because the tests already show they fail. A check before `begin_delegated` misses the writer's spend: test-plan.md "Mutation" says AC-33's writer case kills that placement. A check inside `_arun_metered` was ruled out by row 28's "change nothing else".
  - A runtime probe reused the AC-33 test's own `_delegated_run` helper without editing it:
    - gate case: `max_spend`, `iteration_count` 0, 0 specialist calls, `response.specialist='database'`, 1.000×C;
    - writer case: the same, with 3 writer calls, at 3.003×C. This is the uncapped writer's own Pre-loop segment, which INV-6 and the briefing allow;
    - a cap 1000× the decision cost: the specialist runs (1 call), so the check does not block below the cap.
- **R-2.** One hypothesis, and it held: the review's suggested change, which moves `registry.resolve(...) is not None` inside the same `bool(...)`.
  - The truth table is unchanged: a missing provider or model still gives False, and `resolve` still runs only when both are present.
  - The R-M5 `missing_provider`/`missing_model` cases exercise this line, and they pass.
- **R-2 measurement trap 1 (a failed attempt; do not repeat).** I ran `lint/run.py --rule S009` in a `git archive` copy of base. Every finding came back as NEW, because lint finds files with `git ls-files` (`lint/core/discovery.py:81`). In a copy with no git index, `source_line` is empty. Two fixes work: read source lines from each tree's files, or run `git init && git add -A` in the copy (needed for any other rule).
- **R-2 measurement trap 2.** Two findings will look like diffs and are not new:
  - mypy's `no-redef` on `runtime.py` embeds a line number in its message ("already defined on line 1128" at base, "1139" at head). Treat it as one finding.
  - `py -3.11 -m mypy ... vidbyte/agents/spend_cap.py` on the single file exits 1, with 340 errors, all in imported modules. Check `spend_cap` in the full run instead.
- **R-3, R-4, R-M5.** No source change. The 14 S2b tests pass at the code head (`14 passed, 123 deselected`).
- **R-M1.** First I checked what really runs after a cap stop:
  - `base.py:1022-1036` runs the auto-handoff, then session notification, then output delivery, then the drain.
  - Delivery skips `max_spend`, because `OUTPUT_DELIVERABLE_STOP_REASONS` is only `final_response`/`is_done` (`lib/constants/outputs.py:34`).
  - So the steps that still run and can spend are exactly `after_run` middleware and the auto-handoff. The review's wording is true, and "and they can still spend" was added (EC-36).
- **R-M2.** I checked that neither reviewer config carries a cap (`independent_critic.py:123-127`, `prosecutor_defender_judge.py:242`) and that no Jev fixed-prompt module names `max_spend`. Then I added one sentence.
- **Row 13 and R-M1 wrapping.** `textwrap` splits "run-state" at the hyphen, so I hand-wrapped with a minimal diff instead of reflowing (≤ 88 columns, matching the section).
- **R-M4.** I applied the review's hand wrap exactly. The word diff is empty, no line in the file passes 81 columns, and the docs test passes.
- **R-M3.** I counted from `## Spend Cap` (`:386`) to the last text line before `## Key Modules`:
  - `daad59fb`: 39 lines (the review's correction of 38 holds);
  - final: 46 lines (45 of body), which is +7: 2 for row 13, 2 for R-M1, 3 for R-M2.
- **Lint observation (not a gate failure, and not from this iteration).** S008's count stays 19, but two findings that were already in the baseline grew their numbers between base and HEAD:
  - `BaseAgent.__init__`: C901 17 → 19;
  - `AgentRuntime._arun_once`: C901 45 → 47.
  - Both come from S3's rows 6 and CP1–CP4. Iteration 1 changed neither file.

**Changes:**
| Commit | Finding | What |
|---|---|---|
| `54a11a21` | R-1 | `vidbyte/agents/jev/runtime.py`: CP1 in `_delegate`, with `@intent a-reached-cap-starts-no-specialist`; the lead comment is extended and wrapped at 72 columns |
| `b7e13995` | R-2 | `vidbyte/agents/spend_cap.py:111`: `resolve` moved inside `bool(...)` |
| `9f684068` | R-1 (rows 13, 17) | agents README: the delegated-path check. Jev README: the exact A-8 sentence |
| `de093778` | R-M1 | agents README: which steps still run after a cap stop |
| `de677706` | R-M2 | agents README: SDK-built uncapped runs (D-18) |
| `977086ff` | R-M4 | `skills/failure/vocabulary.md:106-109`: the hand wrap |
| `0be0545d` | R-M3 | spec §17 deviation and S3 report: 46 lines, and 39 at `daad59fb` |

**Gate matrix out** (code head `0be0545d`, pushed):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (pack + codex) | pack plus codex command above | PASS | `188 passed in 1.54s` |
| S2b additions incl. AC-33 | `-k` over the 6 S2b test names | PASS | `14 passed, 123 deselected in 0.86s` |
| area suite | area command above | PASS | `1291 passed in 11.43s` |
| lint (in the source stage) | `lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| lint against base, every rule | `lint/run.py --format json`, base and head | PASS, no new finding | every rule's `found` equals base; `exit_code` 0 at both. The NEW/GONE pairs are the same findings with changed numbers (S001 F401 import line; S008 C901 values; S009 `no-redef` line) |
| S009 / mypy | `lint/run.py --rule S009 --format json`; mypy command | PASS | `"found": 346, "baseline": 350, "verdict": "IMPROVED"`; mypy diff against base: only the `no-redef` line-number pair |
| ruff C901 `_delegate` | `ruff check vidbyte/agents/jev/runtime.py --config lint/ruff.toml --select C901` (max-complexity forced to 1 to print it) | PASS | `` C901 `_delegate` is too complex (3 > 1) ``, so 3 ≤ 10 |
| source stage | `run_ci.py --stage source` | FAIL, inherited only | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` / `1 failed, 7686 passed, 18 skipped in 255.74s (0:04:15)` / `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| package stage | `run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| semgrep | semgrep command above | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 1031 files: 0 findings.` (exit 0) |
| public API contract | `generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 731f094c… (vidbyte-sdk 0.4.0, 733 exports).` |
| remote checks | `gh pr checks …/pull/1192` | dispatch-only; not run by S5 | `no checks reported on the 'feat/loop-spend-cap' branch` |

The source-stage failure is the briefing's inherited local-only red:
- It asserts at `:278`, `Left contains one more item: 'vidbyte/tools/builtins/fork/fork.py'`. That is row 8's file and nothing else. The R-1 edit is not under `vidbyte/tools` or `vidbyte/lib/configs`, and `git diff --name-only $(git merge-base origin/main HEAD) -- vidbyte/tools vidbyte/lib/configs` lists only `fork.py`.
- CI skips it: `merge_base()` calls `pytest.skip` when `origin/main` is absent (`:139-143`).
- It clears on merge.
- The test tree is byte-identical to `b3796d74` (`git diff --stat b3796d74 -- tests` is empty).

**Still open:** no confirmed finding. Gates: only the inherited local-only red above, which the briefing rules is not a defect. Remote checks wait for the orchestrator's dispatch.
