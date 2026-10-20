# S5 repair, iteration 1: loop-spend-cap (vidbyte-sdk PR #1192)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap`, branch `feat/loop-spend-cap`. Start `dbe84114`; code head `0be0545d` (pushed); the record commit follows it. origin/main is still `22993b5f`, an ancestor of HEAD, so no merge was needed. The verify-log entry is `docs/spec/loop-spend-cap/verify-log.md`, iteration 1.

## Result

Every confirmed finding is closed. Every local gate is green except the one inherited local-only red that the briefing rules out as a defect. Remote CI is dispatch-only and was not run.

## Gate matrix (all run in this worktree, this iteration)

| Gate | Result | Final lines |
|---|---|---|
| Pack plus codex | PASS | `188 passed in 1.54s` |
| The S2b additions (AC-33, NFR-1, INV-13, R-M5, EC-27) | PASS | `14 passed, 123 deselected in 0.86s` |
| Area suite (briefing list plus `tests/test_jev*.py`) | PASS | `1291 passed in 11.43s` |
| `tests/test_jev*.py` alone, after R-1 | PASS | `433 passed in 3.45s` |
| `lint/run.py` (inside the source stage) | PASS | `S063 IMPROVED 4 -> 3. Lower it with: …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| Lint against base, every rule (JSON at `22993b5f` and at HEAD) | PASS, no new finding | every rule's `found` equals base; `exit_code` 0 at both |
| S009 | PASS | `"found": 346, "baseline": 350, "verdict": "IMPROVED"` |
| mypy (`--config-file lint/mypy.ini vidbyte`) | PASS | 346 errors, equal to base on (path, code, message, source line), apart from the `no-redef` line-number pair (below) |
| `scripts/run_ci.py --stage source` | FAIL, inherited only | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` / `=========== 1 failed, 7686 passed, 18 skipped in 255.74s (0:04:15) ============` / `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-loop-spend-cap).` |
| `scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| Semgrep 1.170.1 | PASS | `• Findings: 0 (0 blocking)` / `• Targets scanned: 1031` / `Ran 1 rule on 1031 files: 0 findings.` (exit 0) |
| `generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports).` |
| ruff C901 for `_delegate` | PASS | `` C901 `_delegate` is too complex (3 > 1) `` with max-complexity forced to 1 so it prints the value; 3 ≤ 10. Ruff on the file: `All checks passed!` |
| Remote checks | dispatch-only; not run by S5 | `gh pr checks`: `no checks reported on the 'feat/loop-spend-cap' branch` |

**The inherited red.**
- It fails at `test_harness_threads_surface.py:278` with `Left contains one more item: 'vidbyte/tools/builtins/fork/fork.py'`. That is row 8's file, and it is the only item.
- `git diff --name-only $(git merge-base origin/main HEAD) -- vidbyte/tools vidbyte/lib/configs` prints only `vidbyte/tools/builtins/fork/fork.py`. So the R-1 edit, which is in `vidbyte/agents/jev/`, did not widen it.
- CI skips the test: `merge_base()` calls `pytest.skip` when `origin/main` is absent (`:139-143`).
- The field guide's `local-ci-verification.md` names the same branch-scoped test, and the briefing (§4) rules it inherited.
- 7686 passed = S3's reported 7672 plus S2b's 14 new tests.

## Per finding

### R-1 (Blocker): fixed @54a11a21 (code) and @9f684068 (docs, rows 13 and 17)

**Before.** `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap tests/test_codex_output_contracts.py` gave `2 failed, 186 passed`. The failures were both `test_a_reached_cap_starts_no_specialist_the_gate_chose` cases at `:319`, with `At index 0 diff: 1 != 0`.

**Change** (`vidbyte/agents/jev/runtime.py`, `_delegate`), placed exactly as row 28 says:
```python
        # @intent a-reached-cap-starts-no-specialist
        # The specialist's own cap starts at $0 on its own ledger and
        # never sees the gate's or the run-state writer's spend, so only
        # this check stops a run whose measured spend has already
        # reached the cap.
        spend_stop = self._spend_cap_stop(iteration_count=0, tokens_used=None, contexts=())
        if spend_stop is not None:
            return self.response.finished(spend_stop, self.usage.settle())
```
- The lead comment is extended with ", and checks the spend cap before the specialist starts", and is wrapped at 72 columns as `comment-format.md` requires.
- Nothing else changed: not `_arun_metered`, not `_continue_finish_attempt`, not the header.

**After.**
- The Jev test file gives `9 passed`, and pack plus codex gives `188 passed`. The tests are unedited (`git diff --stat b3796d74 HEAD -- tests` is empty).
- **Independent probe.** It reuses the test's own `_delegated_run`, imported without editing the test:

  | Case | stop | `iteration_count` | specialist calls | `response.specialist` | measured ÷ C |
  |---|---|---|---|---|---|
  | gate decision, capped at its cost | `max_spend` | 0 | 0 | `'database'` | 1.000 |
  | relation writer, capped at one writer call | `max_spend` | 0 | 0 | `'database'` | 3.003 (3 writer calls) |
  | uncapped control | the specialist's own `max_spend` | 1 | 1 | `'database'` | 6.952 |
  | cap 1000× the decision cost | the specialist's own `max_spend` | 1 | 1 | `'database'` | 1.525 |

  - The 3.003×C in the writer case is the uncapped run-state writer's own Pre-loop segment. INV-6's Pre-loop row and the briefing (§5, "Scenario B may stop near 1.92×C") allow it. The scripted writer here bills about C per call and is called 3 times.
  - The fourth row shows that the check does not block a run below the cap.

**Docs.**
- `vidbyte/agents/README.md` now says: "JevAgent also checks it before a specialist it chose starts, so a run whose gate or run-state writer has already reached the cap starts no specialist."
- `vidbyte/agents/jev/README.md:24` now has the row-17 sentence verbatim, right after the sentence that begins "`agent.response.specialist` names the specialist that ran". The probe's `response.specialist='database'` with 0 specialist calls shows the sentence is true. The gate records the choice at `gate/gate.py:131` before `_delegate`, and `JevResponse.finished` does not touch it.

### R-2 (Major): fixed @b7e13995

**Before.** `py -3.11 -m mypy --config-file lint/mypy.ini vidbyte` exited 1 with 347 errors. The new one was `vidbyte\agents\spend_cap.py:111:119: error: Argument 2 to "resolve" of "ModelPricingRegistry" has incompatible type "str | None"; expected "str"  [arg-type]`.

**Change.** `priced = bool(runner.provider and runner.model_name and registry.resolve(ModelProvider(runner.provider), runner.model_name) is not None)`.

**After.**
- `grep spend_cap` on the full mypy output prints nothing, and the run has 346 errors.
- Against a `git archive` copy of `22993b5f`, keyed on (path, code, message, stripped source line): `A errors: 346  B errors: 346`.
- The only pair left is the `runtime.py` `no-redef` finding, whose message embeds a moved line number (`… already defined on line 1128` → `1139`; S3 added 11 lines above it).
- `lint/run.py --rule S009 --format json` reports `found: 346`. Keyed the same way against base, the only pair is that same `no-redef` one.
- **Behavior.** The truth table is identical. The R-M5 `missing_provider` and `missing_model` cases exercise this line and pass, and so does the whole refusal file.

### R-3 (Major): fixed @b3796d74 (S2b test); no source change

`test_an_uncapped_run_computes_no_spend_cap_rollup_or_price[tool_then_text, queued_drain_of_three]` passes at the code head. The R-1 check returns before any rollup when the cap is `None`, because `_spend_cap_stop`'s first statement is the `max_spend_usd is None` return. So the delegated path keeps NFR-1 too.

### R-4 (Major): fixed @b3796d74 (S2b tests); no source change

All of these pass at the code head:
- `test_a_capped_slug_model_without_a_provider_is_refused_as_the_runner_reads_it[image, unpriced]`;
- `test_a_capped_chain_whose_primary_is_unmeasurable_is_refused_naming_the_primary[unpriced_primary_priced_fallback, unpriced_primary_first_in_chain_order, image_primary_text_fallback]`.

### R-M1: fixed @de093778

"Nothing runs after a cap stop: …" became this text:

> After a cap stop no SDK step continues the stopped work: no retry, reflection, review, grading, verifier, or queued prompt, and a `MultiAgent` worker's task is blocked. Only your own `after_run` middleware and a configured auto-handoff still run, and they can still spend.

I checked that the new text is true of the code:
- `base.py:1022-1036` runs the auto-handoff, then session notification, then output delivery, then the drain.
- Delivery skips `max_spend`, because `OUTPUT_DELIVERABLE_STOP_REASONS` is `{final_response, is_done}` (`vidbyte/lib/constants/outputs.py:34-36`, read at `output/connector.py:53`).
- The drain skips a `max_spend` reply (INV-11/INV-23, killed mutant in the review's "gets right" list).
- So the only steps that can spend after the stop are `after_run` and the auto-handoff.

### R-M2: fixed @de677706

Added after the "built from the same settings, against its own spend" sentence:

> The SDK's own critic and prosecutor-defender-judge reviewer runs, and JevAgent's fixed-prompt agents, carry no cap by design: their spend counts at the parent's next check, so one review can carry a finished reply past the cap.

I checked:
- `independent_critic.py:126-130` and `prosecutor_defender_judge.py:242` build `AgentRuntimeConfig` with iterations, tokens and tool calls only.
- No Jev `done/`, `brief/` or `gate/clarification.py` module names `max_spend`.
- No cap was added (D-18).

### R-M3: fixed @0be0545d

The Spend Cap section runs from `## Spend Cap` (`:386`) to its last text line (`:431`). It is now **46 lines including the heading (45 of body)**. At `daad59fb` it was 39, which confirms the review's correction of the recorded 38.

This iteration added 7 lines:
- 2 for row 13's delegated-path sentence;
- 2 for R-M1;
- 3 for R-M2.

Both records are corrected with the current number and the `daad59fb` number:
- spec §17 "Implementation deviations (S3)";
- `reports/S3-implementer.md` deviation 2.

Row 13 asks for "at most about 36". Every clause row 13 lists (r4 included) is present, so the 46 is the re-reviewer's deviation judgment. I made no cut that would drop a required clause.

### R-M4: fixed @977086ff

This is the review's hand wrap exactly: 73/63/70/63 columns. `git diff --word-diff=porcelain` shows no word change. No line in the file passes 81 columns. `test_each_named_doc_mentions_the_cap[skills/failure/vocabulary.md]` passes (docs file `6 passed`).

### R-M5: fixed @b3796d74 (S2b tests); no source change

`test_the_unpriced_refusal_names_each_pair_once_and_marks_a_missing_part[duplicate_unpriced_fallback, unpriced_primary_repeated_as_a_fallback, missing_provider, missing_model]` passes. No test is red, so no code change was warranted (INV-13).

## Lint against base: every rule

I ran `lint/run.py --format json` at HEAD and in a `git archive` copy of `22993b5f`. The copy needs its own `git init && git add -A`, because lint discovers files with `git ls-files`. I keyed each finding on (rule, path, symbol, message, source line read from that tree).
- Every rule's `found` equals base, and `exit_code` is 0 on both.
- No rule is REGRESSED or ERRORED.
- The NEW/GONE pairs are existing findings whose text changed in S3, not in this iteration:
  - S001 F401 `AgentRuntimeConfig` unused in `base.py`: the same import line gained `AgentStopReason` (row 6).
  - S008 `BaseAgent.__init__`: C901 17 → 19, branches 17 → 19, statements 87 → 92.
  - S008 `AgentRuntime._arun_once`: C901 45 → 47, branches 44 → 46, statements 167 → 171. Both functions were in the lint baseline before this PR (S2 note in pipeline.md), and the S008 count stays 19.
  - S009 `no-redef`: the line number in its message.

## Test changes proposed

None. No test was edited, skipped or weakened. `git diff --stat b3796d74 HEAD -- tests` is empty.

## Findings I believe are wrong

None.

## Still open

- **Confirmed findings:** none.
- **Gates:** only the inherited local-only red, with evidence above.
- **Remote checks:** dispatch-only. The orchestrator dispatches `ci.yml` and `static-policy.yml` on the final head before the `--admin` merge.

## Larger moves this opens (for the orchestrator; none taken here)

1. **C3 wording.** The delegated path now stops before a specialist starts. But a run whose uncapped Jev fixed-prompt writer makes several calls before the first check can still stop well above C (3.003×C in the scripted probe). C3's `--max-spend` help should keep §9.2 rule 7's "threshold checked between steps, never a maximum bill" wording. It should not promise "at most $X".
2. **A-8 docstring.** The named follow-up, `vidbyte/lib/dataclasses/jev.py:3863` ("the specialist that ran"), is now the only text that contradicts the code, so it is cheap to close in the next Jev PR.
3. **Complexity.** `_arun_once` is at C901 47. Each new loop-wide feature adds branches there. Moving the four check points' shared plumbing out of it is a refactor PR of its own (not this one).
