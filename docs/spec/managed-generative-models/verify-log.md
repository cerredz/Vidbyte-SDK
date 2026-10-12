# Verification log: Vidbyte-managed mode for generative model calls (lib layer)

Gate set (from context/code-map.md §1 and the S5 orchestrator briefing). Every gate runs locally from the worktree root, except (f).
- (a) pack: `env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider`
- (b) full suite: `env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider`
- (c) lint: `python lint/run.py` must end with `SDK-LINT: PASS`. Lint reads `git ls-files`, so stage new files first.
- (d) CI stages: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH.
- (e) semgrep: `<scratchpad>/semgrep-venv/Scripts/pysemgrep.exe scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off`. It scans tracked files only, so commit first.
- (f) remote checks (remote only): `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/759`. Automatic Actions triggers are disabled in this repo.

## Iteration 1 — 2026-10-11 03:36 — agent report: reports/S5-repair-1.md
**Defects in:**
- Confirmed: R-1 (Blocker); R-2, R-3, R-4, R-5 and R-6 (Major).
- Trivial Minors: M-1, M-2, M-3 (citation), M-4, M-5, M-7, M-9 and M-14.
- Gates: none red. At cad3cf59 all were green: pack 32, full suite 3004 passed / 1 skipped, SDK-LINT PASS.
- An earlier launch of this iteration died at startup and changed nothing.

**Hypotheses and attempts (in order):**
1. **R-1, R-5 and M-5: one pass over the comment blocks.**
   - Followed review.md's four moves for R-1 exactly:
     - text.py `__init__`: the pinning intent now opens the pinning block;
     - text.py `arun`: the summary became a docstring, and the routing intent sits above `transport = self._transport`;
     - gateway `request`: the summary became a docstring, the mint narration stays above uuid4, and the header intent sits above `gateway_headers`;
     - `resolved_api_key`: the BYOK narration moved above the BYOK return, wrapped.
   - For the 13 other markers (R-5) I chose one-line docstrings over deleting the summary lines. This is the #747 shape: `git show 57639080:vidbyte/tools/builtins/bash.py` and `vidbyte/tools/toolsets/coding.py` both put a one-line docstring and then `# @intent`.
   - `validate()` is different. Its narration is a body step, not a method summary, so I folded it into the `@intent` block and gave the BYOK line its own narration.
   - The `find_vidbyte_api_key` block ended on the single word "serves.", the same uneven fill R-5 flags at `model_configs.py:109-110`. A greedy 72-column fill left the dangling word, and a hyphen-breaking fill split "Vidbyte-prefixed". A 62-column fill gives even lines of 61/55/60/49.
   - M-5: added a 4-line `@intent` block to the gateway `__init__`. A002 went from 653 to 652. I did not run `--update-baseline`, because the briefing forbids baseline edits.
   - A scratch checker (`scratchpad/s5r1/check.py`) runs the real `IntentAnalyzer` on the five touched files after each edit. It found no new A002 name, and no added comment line is over 72 columns.
2. **R-2.** I applied the prescribed one-line change, and it worked first time. My own call-count probe (`scratchpad/s5r1/r2_probe.py`) shows `{is_vidbyte_managed 2, find_vidbyte_api_key 2, resolved_api_key 1}` before and `{1, 1, 0}` after. The missing-key message is unchanged.
3. **R-6 and M-9: the new file `test_managed_text_deadline.py`.**
   - I used the fake loop clock from the verifier's design and patched only the gateway module's `asyncio` name.
   - Steps 0 / 600 / 629.5 s, with M-9's 502→422 and 502→no-response cases, plus direct `validate()` calls for EC-7 and EC-3.
   - The clock starts at 1000 s rather than 0. Otherwise a deadline that ignores the loop clock (`deadline = timeout_seconds`) passes by accident. My own mutant `mut_noclock` checks this: 4 failed with the new file.
   - I did not use the refuted variants (a real clock with timeouts of 0.4/0.6 s, or steps of 629.4/629.6 s).
4. **R-3.** With only the new file staged, S020 rose to 2/1 (REGRESSED). After the granted bullet it is back to 1/1.
   - R-3 and R-6 share one commit. Split commits would leave one of them red: the file without the bullet gives 2/1, and the bullet without the file gives a stale entry.
5. **R-4.** I used the context-manager form (`with patch.dict(os.environ, {"VIDBYTE_API_KEY": ""}):`) plus `import os`, and changed no assertion.
   - Before the fix, the verifier's `vnetblock` plugin with a fake live-format key recorded 1 blocked POST to `/api/v1/models/generate`. After it, 0.
   - A scratch copy with a trailing `self.fail` fails, so the body runs.
   - With a fake key under `vnetblock`, the full suite now makes 0 attempts.
6. **M-1.** For providers this runner cannot stream, the second clause now says that streaming supports only anthropic and openai. The message still names managed mode, `TextModelRunner` and the env var, so the S2 assertions hold. openai and anthropic keep the original message.
   - EC-16's spec text was not edited: the briefing allows spec edits only for M-2, M-3 and M-4. The §17 row records the wording difference.
7. **M-2, M-3 and M-4.** These are text-only edits plus one §17 row. Interactive `git add -p` is not available, so I saved the final files, restored HEAD, and re-applied the lines one defect at a time. That gave one commit per defect, and the final spec is byte-identical to the saved copy.
8. **Commit subjects.** I reworded two unpushed commit subjects from `test(...)` and `docs(...)` to the prescribed `fix(...)`. The content did not change.

**Mutant kill table (R-6 and M-9).** Command: `MUT=<id> PYTHONPATH="<wt>;<SP>/s4eng" python -m pytest <file> -q -p no:cacheprovider -p mutplug --rootdir=<wt>`.
| Mutant | New file | Rest of the pack (without the new file) |
|---|---|---|
| no_deadline | 2 failed, 5 passed | 32 passed |
| deadline_gt | 1 failed, 6 passed | 32 passed |
| deadline_after_first | 2 failed, 5 passed | 32 passed |
| shorten_attempt | 4 failed, 3 passed | 1 failed on the first run, then 32 passed on 3 of 3 re-runs (timing-dependent) |
| resends_off_by_one | 1 failed, 6 passed | 32 passed |
| auto_shape_unchecked | 2 failed, 5 passed | 32 passed |
| mut_first (`-p mut_first`) | 2 failed, 5 passed | 32 passed |
| mut_noclock (own, `scratchpad/s5r1`) | 4 failed, 3 passed | 6 failed |

Every failure is an AssertionError on the intended line, for example `'re-sends in this call: 2' not found`, `29.5 != 630.0`, and `ConfigurationError not raised`.

**Changes:**
| Commit | Finding | Subject |
|---|---|---|
| 92d3d690 | R-1 | put each @intent block directly above the code it explains |
| 23a5e87c | R-5 | open every new @intent block with its marker line |
| 443ac21a | M-5 | give `VidbyteGatewayTransport.__init__` its @intent block |
| 745f8efe | R-2 | keep `TextModelConfig.validate`'s call chain one level deep |
| 8eea0362 | R-6, R-3, M-9 | pin the r5 retry deadline and the last-attempt rule |
| 15eb286e | R-4 | stop the legacy-mode test sending a live POST |
| 69ee8aaa | M-1 | managed streaming refusal without the dead-end advice |
| a6dbcd2c | M-7 | refresh stale header fields |
| 028b2708 | M-14 | FEATURE.md retry bullet states the r5 deadline |
| 15203ae4 | M-2 | EC-26 and the §15 risk note |
| 22a0a7ba | M-3 | NG-5 citation |
| 90459fb8 | M-4 | README and AC-18 "never billed twice" qualified, plus the §17 row |

**Gate matrix out** (head 90459fb8, all run in this worktree in this iteration):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| (a) new tests / pack | pack command above | PASS | `39 passed in 0.93s` (32 + 7 new) |
| (b) full suite | full-suite command above | PASS | `3011 passed, 1 skipped in 15.60s` |
| (b′) full suite, network-blocked, fake key | (b) plus a fake live-format `VIDBYTE_API_KEY` and `-p vnetblock` | PASS | `3011 passed, 1 skipped in 16.85s`; blocked attempts: 0 |
| (c) lint | `python lint/run.py` | PASS | `A002 IMPROVED 703 -> 652` / `S020 … 1 1 RATCHETED` / `SDK-LINT: PASS` |
| (d) CI source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `3011 passed, 1 skipped in 16.30s` / `CI passed.` |
| (d) CI package | `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| (e) semgrep | scratch-venv `pysemgrep … --metrics=off` | PASS | `• Findings: 0 (0 blocking)` / `Ran 1 rule on 872 files: 0 findings.` |
| (f) remote checks | `gh pr checks …/pull/759` | none ran | `no checks reported on the 'feat/managed-generative-models' branch`. The commit API shows 0 check runs and 0 statuses on 90459fb8, because automatic triggers are disabled. |

**Still open:**
- **Confirmed findings:** none. Every gate is green.
- **For the orchestrator to decide (outside this iteration's grants):**
  1. R-6's documentation step is not done. It would add AC-28 to spec §6.2, point `test-plan.md:20` (EC-38) at the new test, and set the test-plan header to r5. The briefing's docs list does not include test-plan.md or AC table edits.
  2. EC-16's text still shows only the openai/anthropic wording after M-1. The difference is recorded in the §17 row.
  3. Remote CI was not dispatched. #747 dispatched it by hand with `gh workflow run ci.yml --ref <branch>` and `gh workflow run static-policy.yml --ref <branch>`.
- **Follow-ups for the PR body:** M-3 (serving more providers), M-6, M-8, M-10, M-11, M-12 and M-13.
